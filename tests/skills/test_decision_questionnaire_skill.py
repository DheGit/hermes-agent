"""Tests for optional-skills/productivity/decision-questionnaire."""

import re
from pathlib import Path

import pytest
import yaml

SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "optional-skills"
    / "productivity"
    / "decision-questionnaire"
    / "SKILL.md"
)


def _frontmatter():
    text = SKILL_MD.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md missing YAML frontmatter"
    return yaml.safe_load(m.group(1))


class TestFrontmatter:
    def test_name_matches_directory(self):
        assert _frontmatter()["name"] == "decision-questionnaire"

    def test_description_length_and_period(self):
        desc = _frontmatter()["description"]
        assert len(desc) <= 60
        assert desc.endswith(".")

    def test_license_and_platforms(self):
        fm = _frontmatter()
        assert fm["license"] == "MIT"
        assert set(fm["platforms"]) == {"linux", "macos", "windows"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
