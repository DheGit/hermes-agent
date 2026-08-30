#!/usr/bin/env python3
"""``/plan`` — build the plan-mode prompt that turns the user's request into a
saved markdown implementation plan, with no execution.

``/plan`` used to be a bundled skill (``skills/software-development/plan``)
whose auto-generated slash command fell off the capped Telegram/Discord command
menus for most installs (skills are the only tier trimmed at the platform
caps, alphabetically — ``plan`` sat past the cutoff). It is now a first-class
built-in: this module builds ONE prompt that instructs the live agent to

  1. Stay in planning mode for the turn — read-only inspection is allowed,
     but no implementation, no mutating commands, no side effects.
  2. Write a concrete, bite-sized, TDD-shaped markdown plan under
     ``.hermes/plans/`` in the active workspace via ``write_file``.

There is no engine and no model-tool footprint: the agent does the work with
its existing toolset, so this works identically on local, Docker, and remote
terminal backends. Every surface (CLI ``/plan``, gateway ``/plan``, TUI
``/plan``) calls :func:`build_plan_prompt` and feeds the result to the agent
as a normal turn — same pattern as ``/learn`` and ``/init``, preserving
prompt-cache invariants (no system-prompt or history mutation).
"""

from __future__ import annotations

# The plan-mode ground rules + authoring craft, distilled from the retired
# bundled skill (v2.0.0, writing-craft adapted from obra/superpowers).
# Embedded in the prompt so the agent plans the way a maintainer would.
_PLAN_MODE_RULES = """\
For this turn, you are in PLAN MODE — planning only.

- Do not implement code.
- Do not edit project files except the plan markdown file itself.
- Do not run mutating terminal commands, commit, push, or perform external
  actions.
- You may inspect the repo or other context with read-only commands/tools
  when needed.
- Your deliverable is a markdown plan saved inside the active workspace under
  `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md` (create the directory if
  needed; Hermes file tools are backend-aware, so this relative path keeps
  the plan with the workspace on local, docker, ssh, modal, and daytona
  backends). If the runtime provides a specific target path, use that exact
  path instead.
"""

_PLAN_CRAFT = """\
Write the plan for an implementer with zero context for the codebase and
questionable taste. A good plan makes implementation obvious — if someone has
to guess, the plan is incomplete.

Structure (include the sections that are relevant):
- Goal — one sentence.
- Current context / assumptions.
- Architecture / proposed approach — 2-3 sentences.
- Step-by-step tasks. Each task is bite-sized (2-5 minutes of focused work),
  and names exact file paths (`src/models/user.py`, not "the model file") when
  the outcome requires file changes. Include code, commands, and expected
  outputs only where they remove implementation guesswork or prove the outcome.
- Tests / validation — include only the evidence needed to prove the outcome;
  where TDD is relevant, show the failing test, minimal implementation, and
  passing test cycle.
- Risks, tradeoffs, and open questions.

Principles: DRY, YAGNI, TDD, frequent commits. Avoid vague tasks ("add
authentication"), incomplete code ("add validation here"), and unverifiable
steps ("test it works" — instead: the exact command and its expected output).

Before saving or presenting the plan, make it irreducible:
1. State the required outcome and what evidence would prove it.
2. Subtraction first: attempt to remove each proposed implementation item. If
   its removal would make the outcome fail or become unprovable, restore that
   item; otherwise leave it out. Continue until no remaining item can be
   removed without that consequence.
3. Apply the same removal test to verification steps and keep only the evidence
   needed to prove the outcome.

Do not assume every plan needs setup, infrastructure, edge-case, integration,
cleanup, documentation, complete-code, or expected-output work. Keep any of
those only when the required outcome or its proof actually depends on it.

Interaction style:
- If the request is clear enough, write the plan directly.
- If it is genuinely underspecified, ask a brief clarifying question instead
  of guessing.
- After saving the plan, reply briefly with what you planned and the saved
  path, and offer to execute it (e.g. via subagent-driven development) —
  but do not start executing in this turn.
"""


def build_plan_prompt(task: str = "") -> str:
    """Build the plan-mode prompt for the live agent.

    Args:
        task: What to plan. Empty → infer the task from the current
            conversation context (mirrors the retired skill's behavior and
            issue #36821's "plan from context" expectation).
    """
    task = (task or "").strip()
    if task:
        task_block = f"Task to plan:\n{task}\n"
    else:
        task_block = (
            "No explicit task was given with /plan — infer the task from the "
            "current conversation context (the thing we have been discussing "
            "or working toward). If the conversation does not imply a task, "
            "ask a brief clarifying question.\n"
        )
    return (
        "[/plan — plan mode]\n\n"
        + _PLAN_MODE_RULES
        + "\n"
        + task_block
        + "\n"
        + _PLAN_CRAFT
    )
