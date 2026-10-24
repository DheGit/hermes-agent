"""ACP delivery-capability contracts."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import threading

from acp_adapter.server import HermesACPAgent
from acp_adapter.session import SessionState
from gateway.session_context import async_delivery_supported, reset_session_vars


def test_acp_turn_declares_async_delivery_unsupported():
    """A completed delegate must return before ACP's request-scoped turn ends."""
    observed = []

    class FakeAgent:
        def run_conversation(self, **_kwargs):
            observed.append(async_delivery_supported())
            return {"final_response": "done", "messages": []}

    state = SessionState(session_id="acp-session", agent=FakeAgent(), cwd="/tmp")
    loop = asyncio.new_event_loop()
    reset_session_vars()
    try:
        result = HermesACPAgent()._run_agent_turn(
            state=state,
            session_id="acp-session",
            user_text="delegate this",
            user_content="delegate this",
            conn=None,
            loop=loop,
            approval_cb=None,
            edit_approval_requester=None,
        )
    finally:
        reset_session_vars()
        loop.close()

    assert result["final_response"] == "done"
    assert observed == [False]


def test_acp_parent_receives_complete_delegated_plan_inline_and_consumes_it(monkeypatch):
    """Regression: ACP must not end on a dispatch handle and strand the completed plan."""
    import tools.delegate_tool as delegate_tool

    plan = {
        "title": "LedgerLite rollout",
        "summary": "Replace the placeholder flow with a durable reviewed workflow.",
        "items": [
            {"id": "inspect", "description": "Trace persistence and authorization boundaries."},
            {"id": "implement", "description": "Persist the canonical plan and render its bound review."},
            {"id": "verify", "description": "Exercise approval, execution, and completion evidence."},
        ],
    }
    plan_text = json.dumps(plan, separators=(",", ":"))
    fake_child = type("Child", (), {"_subagent_id": "planner"})()
    child_started = threading.Event()
    child_release = threading.Event()
    review_consumed = threading.Event()
    dispatched = []
    consumed = {}

    def child_result(task_index, goal, child=None, parent_agent=None, **_kwargs):
        child_started.set()
        assert child_release.wait(timeout=5), "test never released the delegated child"
        return {
            "task_index": task_index,
            "status": "completed",
            "summary": plan_text,
            "api_calls": 2,
            "duration_seconds": 3.0,
            "model": "planner-model",
            "exit_reason": "completed",
        }

    credentials = {
        "model": "planner-model", "provider": None, "base_url": None, "api_key": None,
        "api_mode": None, "command": None, "args": None,
    }
    monkeypatch.setattr(delegate_tool, "_build_child_agent", lambda **_kwargs: fake_child)
    monkeypatch.setattr(delegate_tool, "_run_single_child", child_result)
    monkeypatch.setattr(delegate_tool, "_resolve_delegation_credentials", lambda *_args, **_kwargs: credentials)
    monkeypatch.setattr(
        "tools.async_delegation.dispatch_async_delegation_batch",
        lambda *_args, **kwargs: dispatched.append(kwargs) or {"delegation_id": "lost-plan"},
    )

    def store_plan(payload):
        consumed["plan"] = payload["plan"]
        return {"plan_hash": "sha256:" + "1" * 64, "plan_version": 1}

    def publish_review(payload):
        assert consumed["plan"] == plan
        assert "inspect" in payload["html"] and "implement" in payload["html"] and "verify" in payload["html"]
        consumed["review"] = payload
        review_consumed.set()
        return {"review_hash": "sha256:" + "2" * 64, "status": "published"}

    permitted = {"td_lane_store_plan": store_plan, "td_lane_publish_plan_review": publish_review}

    class ParentAgent:
        _delegate_depth = 0
        _subagent_id = None

        def run_conversation(self, **_kwargs):
            delegated = json.loads(delegate_tool.delegate_task(
                goal="return the complete canonical plan", background=True, parent_agent=self,
            ))
            returned = delegated["results"][0]["summary"]
            assert returned == plan_text
            assert "/tmp/" not in returned and "path" not in returned.lower()
            complete_plan = json.loads(returned)
            stored = permitted["td_lane_store_plan"]({"plan": complete_plan})
            review = "<main>" + " ".join(item["id"] for item in complete_plan["items"]) + "</main>"
            published = permitted["td_lane_publish_plan_review"]({"html": review, **stored})
            return {"final_response": json.dumps(published), "messages": []}

    state = SessionState(session_id="acp-plan", agent=ParentAgent(), cwd="/tmp")
    loop = asyncio.new_event_loop()
    reset_session_vars()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            turn = executor.submit(
                HermesACPAgent()._run_agent_turn,
                state=state, session_id="acp-plan", user_text="plan this", user_content="plan this",
                conn=None, loop=loop, approval_cb=None, edit_approval_requester=None,
            )
            assert child_started.wait(timeout=5), "delegated child did not start"
            assert not turn.done(), "ACP turn returned before delegated completion"
            assert not dispatched
            assert not review_consumed.is_set()
            child_release.set()
            result = turn.result(timeout=5)
    finally:
        child_release.set()
        reset_session_vars()
        loop.close()

    assert not dispatched
    assert review_consumed.is_set()
    assert consumed["plan"] == plan
    assert consumed["review"]["plan_version"] == 1
    assert json.loads(result["final_response"])["status"] == "published"
