"""Contract checks for the optional agent-merge-conflict-arbiter skill asset.

Reads only the SKILL.md markdown asset — no .py source reads, no network.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = (
    REPO_ROOT
    / "optional-skills"
    / "autonomous-ai-agents"
    / "agent-merge-conflict-arbiter"
    / "SKILL.md"
)

REQUIRED_SECTIONS = [
    "## When to Use",
    "## Prerequisites",
    "## How to Run",
    "## Quick Reference",
    "## Procedure",
    "## Pitfalls",
    "## Verification",
]


def _frontmatter_and_body():
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must open with frontmatter"
    m = re.search(r"\n---\s*\n", content[3:])
    assert m, "frontmatter must close with ---"
    fm_text = content[3 : m.start() + 3]
    body = content[m.end() + 3 :]
    fm = {}
    for line in fm_text.splitlines():
        km = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if km:
            fm[km.group(1)] = km.group(2).strip().strip('"')
    return fm, body


def test_skill_file_exists():
    assert SKILL_PATH.is_file()


def test_frontmatter_required_fields():
    fm, _ = _frontmatter_and_body()
    for field in ("name", "description", "version", "author", "license", "platforms"):
        assert field in fm, f"missing frontmatter field: {field}"
    assert fm["name"] == "agent-merge-conflict-arbiter"


def test_description_hardline():
    fm, _ = _frontmatter_and_body()
    desc = fm["description"]
    assert len(desc) <= 60, f"description is {len(desc)} chars; hardline is 60"
    assert desc.endswith("."), "description must end with a period"
    assert desc.count(".") == 1, "description must be one sentence"


def test_body_size_within_bundled_norms():
    content = SKILL_PATH.read_text(encoding="utf-8")
    lines = content.count("\n") + 1
    assert 80 <= lines <= 260, f"SKILL.md is {lines} lines; expected ~100-200"
