"""Tests for the built-in /plan command (formerly the bundled `plan` skill).

Covers the shared prompt builder (agent.plan_prompt.build_plan_prompt) and the
registry wiring that makes /plan a first-class command on every surface —
CLI, gateway messengers, and TUI. The skill-to-builtin move exists precisely
so /plan survives the Telegram/Discord command-menu caps that trimmed it as
an alphabetical skill entry.
"""

from agent.plan_prompt import build_plan_prompt


class TestBuildPlanPrompt:
    def test_task_is_included_verbatim(self):
        task = "migrate the auth provider to OIDC with zero downtime"
        prompt = build_plan_prompt(task)
        assert task in prompt


class TestPlanRegistryWiring:
    def test_plan_is_registered_and_resolves(self):
        from hermes_cli.commands import resolve_command

        cmd = resolve_command("plan")
        assert cmd is not None
        assert cmd.name == "plan"

    def test_plan_is_not_cli_only(self):
        # /plan must reach messaging gateways — the whole point of the
        # builtin conversion is menu visibility on Telegram/Discord.
        from hermes_cli.commands import resolve_command

        assert not resolve_command("plan").cli_only

    def test_plan_reaches_gateway_dispatch(self):
        from hermes_cli.commands import GATEWAY_KNOWN_COMMANDS

        assert "plan" in GATEWAY_KNOWN_COMMANDS

    def test_plan_in_telegram_bot_commands(self):
        from hermes_cli.commands import telegram_bot_commands

        names = {n for n, _ in telegram_bot_commands()}
        assert "plan" in names

    def test_no_bundled_plan_skill_remains(self):
        # The bundled skill was removed with the builtin conversion; a
        # leftover copy would collide with the core command at scan time
        # (scan_skill_commands skips core-colliding skill slugs with a
        # warning, so the skill would be silently unreachable).
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        assert not (repo_root / "skills" / "software-development" / "plan").exists()
