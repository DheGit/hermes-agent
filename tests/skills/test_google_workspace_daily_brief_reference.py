"""Tests for the google-workspace daily-brief reference."""
import re
from pathlib import Path

GWS_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "productivity"
    / "google-workspace"
)
REF_PATH = GWS_DIR / "references" / "daily-brief.md"
SKILL_PATH = GWS_DIR / "SKILL.md"


def test_reference_exists():
    assert REF_PATH.is_file()


def test_no_standalone_daily_brief_skill():
    """The brief ships as a reference, not a sibling skill."""
    repo_root = GWS_DIR.parents[2]
    assert not (repo_root / "skills" / "productivity" / "google-workspace-daily-brief").exists()
