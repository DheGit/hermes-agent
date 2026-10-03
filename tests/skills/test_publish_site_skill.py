"""Tests for the optional-skills/web-development/publish-site skill.

Structural + internal-consistency checks only (stdlib + pytest, no network).
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "optional-skills" / "web-development" / "publish-site"
SKILL_MD = SKILL_DIR / "SKILL.md"

VALID_PLATFORMS = {"linux", "macos", "windows"}


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(skill_text: str) -> dict:
    """Parse the YAML frontmatter with stdlib only (flat key: value fields)."""
    m = re.match(r"^---\n(.*?)\n---\n", skill_text, re.DOTALL)
    assert m, "SKILL.md must open with '---' delimited YAML frontmatter"
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if line.startswith((" ", "\t")) or ":" not in line:
            continue  # nested metadata keys — not needed here
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm


def test_skill_file_exists():
    assert SKILL_MD.is_file(), f"missing {SKILL_MD}"


def test_frontmatter_parses(frontmatter: dict):
    assert frontmatter.get("name") == "publish-site"
    assert frontmatter.get("version"), "version field required"
    assert frontmatter.get("license") == "MIT"
    assert "Hermes Agent" in frontmatter.get("author", "")


def test_description_length_and_period(frontmatter: dict):
    desc = frontmatter.get("description", "").strip().strip('"')
    assert desc, "no description field"
    assert len(desc) <= 60, f"description is {len(desc)} chars (>60): {desc!r}"
    assert desc.endswith("."), "description must end with a period"


def test_platforms_list_valid(frontmatter: dict):
    raw = frontmatter.get("platforms", "")
    platforms = [p.strip() for p in raw.strip("[]").split(",") if p.strip()]
    assert platforms, "platforms list must be non-empty"
    assert set(platforms) <= VALID_PLATFORMS, f"invalid platforms: {platforms}"
    # gh/wrangler/netlify are all cross-platform — the skill keeps all three.
    assert set(platforms) == VALID_PLATFORMS


def test_no_dangling_skill_view_references(skill_text: str):
    """Every skill_view(name='...') reference must target a shipped skill."""
    targets = re.findall(r"skill_view\(\s*name\s*=\s*['\"]([^'\"]+)['\"]", skill_text)
    for name in targets:
        hits = list((REPO / "skills").glob(f"**/{name}/SKILL.md")) + list(
            (REPO / "optional-skills").glob(f"**/{name}/SKILL.md")
        )
        assert hits, f"skill_view reference to non-shipped skill: {name}"


def test_category_description_exists():
    desc = REPO / "optional-skills" / "web-development" / "DESCRIPTION.md"
    assert desc.is_file(), "optional web-development category needs a DESCRIPTION.md"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
