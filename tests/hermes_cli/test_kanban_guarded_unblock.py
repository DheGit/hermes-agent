"""Native compare-and-swap continuation unblocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from hermes_cli import kanban as kc
from hermes_cli import kanban_db as kb


@pytest.fixture
def kanban_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _blocked(
    conn, *, kind: str = "capability", offer: str | None = None, parent: str | None = None
) -> tuple[str, int]:
    task_id = kb.create_task(conn, title="guarded unblock", assignee="worker")
    assert kb.claim_task(conn, task_id) is not None
    if offer:
        kb.add_comment(conn, task_id, "Astro", offer)
    if parent:
        kb.link_tasks(conn, parent_id=parent, child_id=task_id)
    assert kb.block_task(conn, task_id, reason="need a response", kind=kind)
    return task_id, kb.list_events(conn, task_id)[-1].id


def _unblock(conn, task_id: str, event_id: int, *, continuation_id: str = "c-1") -> bool:
    return kb.unblock_task(
        conn,
        task_id,
        expected_event_id=event_id,
        continuation_id=continuation_id,
        continuation_note="Astro supplied the missing answer.",
        expected_block_kind="capability",
    )


def test_guarded_unblock_adds_one_atomic_comment_and_event(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        task_id, event_id = _blocked(
            conn, offer="Independent test results are ready for review."
        )
        assert _unblock(conn, task_id, event_id)

        assert kb.get_task(conn, task_id).status == "ready"
        comments = kb.list_comments(conn, task_id)
        assert [(c.author, c.body) for c in comments] == [
            ("Astro", "Independent test results are ready for review."),
            ("scheduler", "UNBLOCK: Astro supplied the missing answer.")
        ]
        unblocked = [e for e in kb.list_events(conn, task_id) if e.kind == "unblocked"]
        assert len(unblocked) == 1
        assert unblocked[0].payload["continuation_id"] == "c-1"


def test_guarded_unblock_cannot_reuse_consumed_continuation_after_reblock(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        task_id, event_id = _blocked(conn)
        assert _unblock(conn, task_id, event_id)
        assert kb.claim_task(conn, task_id) is not None
        assert kb.block_task(conn, task_id, reason="again", kind="capability")
        reblock_event = kb.list_events(conn, task_id)[-1].id

        assert not _unblock(conn, task_id, reblock_event)
        assert kb.get_task(conn, task_id).status in {"blocked", "triage"}
        assert len(kb.list_comments(conn, task_id)) == 1


def test_guarded_unblock_rejects_stale_event_and_keeps_card_blocked(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        task_id, event_id = _blocked(conn)
        kb.add_comment(conn, task_id, "human", "Do not continue yet.")

        assert not _unblock(conn, task_id, event_id)
        assert kb.get_task(conn, task_id).status == "blocked"
        assert [c.author for c in kb.list_comments(conn, task_id)] == ["human"]


def test_guarded_unblock_requires_complete_guard_and_allowed_block_kind(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        task_id, event_id = _blocked(conn)
        with pytest.raises(ValueError, match="requires expected_event_id"):
            kb.unblock_task(conn, task_id, expected_event_id=event_id)
        with pytest.raises(ValueError, match="expected_block_kind"):
            kb.unblock_task(
                conn,
                task_id,
                expected_event_id=event_id,
                continuation_id="c-1",
                continuation_note="note",
                expected_block_kind="dependency",
            )


def test_guarded_unblock_refuses_wrong_kind_status_and_archived_card(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        task_id, event_id = _blocked(conn)
        assert not kb.unblock_task(
            conn,
            task_id,
            expected_event_id=event_id,
            continuation_id="c-1",
            continuation_note="note",
            expected_block_kind="transient",
        )
        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (task_id,))
        assert not _unblock(conn, task_id, event_id)
        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET status = 'archived' WHERE id = ?", (task_id,))
        assert not _unblock(conn, task_id, event_id)


def test_guarded_unblock_preserves_parent_gate_and_refuses_review_resume(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        parent = kb.create_task(conn, title="unfinished parent")
        task_id, event_id = _blocked(conn, parent=parent)
        assert _unblock(conn, task_id, event_id)
        assert kb.get_task(conn, task_id).status == "todo"

        review_task = kb.create_task(conn, title="review block", assignee="worker")
        implementation = kb.claim_task(conn, review_task)
        assert implementation is not None
        assert kb.request_review(
            conn,
            review_task,
            summary="ready",
            reviewer="reviewer",
            expected_run_id=implementation.current_run_id,
        )
        review = kb.claim_review_task(conn, review_task)
        assert review is not None
        assert kb.block_task(
            conn,
            review_task,
            reason="review needs input",
            kind="capability",
            expected_run_id=review.current_run_id,
        )
        review_event = kb.list_events(conn, review_task)[-1].id
        assert not _unblock(conn, review_task, review_event, continuation_id="c-review")
        assert kb.get_task(conn, review_task).status == "blocked"


def test_guarded_unblock_rolls_back_comment_if_event_write_fails(
    kanban_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with kb.connect_closing() as conn:
        task_id, event_id = _blocked(conn)
        original = kb._append_event

        def fail_unblocked(*args, **kwargs):
            if args[2] == "unblocked":
                raise RuntimeError("injected failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(kb, "_append_event", fail_unblocked)
        with pytest.raises(RuntimeError, match="injected failure"):
            _unblock(conn, task_id, event_id)

        assert kb.get_task(conn, task_id).status == "blocked"
        assert kb.list_comments(conn, task_id) == []


def test_unguarded_unblock_and_cli_guard_validation_remain_compatible(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        task_id, _ = _blocked(conn)
        assert kb.unblock_task(conn, task_id)
        assert kb.get_task(conn, task_id).status == "ready"

    assert kc._cmd_unblock(
        argparse.Namespace(
            task_ids=[task_id],
            reason="note",
            expected_event_id=1,
            continuation_id=None,
            expected_block_kind=None,
        )
    ) == 2


def test_show_json_exposes_comment_and_event_ids(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="show IDs")
        comment_id = kb.add_comment(conn, task_id, "human", "answer")
        event_id = kb.list_events(conn, task_id)[-1].id

    payload = json.loads(kc.run_slash(f"show {task_id} --json"))
    assert payload["task"]["block_kind"] is None
    assert payload["comments"][-1]["id"] == comment_id
    assert payload["events"][-1]["id"] == event_id
