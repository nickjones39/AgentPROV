"""The user guide's deploy workflow (``.github/workflows/pages.yml``) runs only on a manual dispatch, asks for exactly
the Pages permissions, and pins every action by full commit SHA. It is dispatched only after the go-live steps of
``docs/user-guide/_go-live.md``; until the repository is public, GitHub Pages cannot serve it at all."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / ".github" / "workflows" / "pages.yml"
GATE = "github.event_name == 'workflow_dispatch'"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(PAGES.read_text(encoding="utf-8"))


def test_pages_is_dispatch_only() -> None:
    doc = _workflow()
    on = doc.get("on", doc.get(True))  # YAML 1.1 reads a bare `on` key as True
    assert on == {"workflow_dispatch": None}, on
    for name, job in doc["jobs"].items():
        assert job.get("if") == GATE, f"job {name} must carry if: {GATE}"


def test_pages_has_exactly_the_pages_permissions() -> None:
    assert _workflow()["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
    for name, job in _workflow()["jobs"].items():
        assert "permissions" not in job, f"job {name} must not widen the permissions"


def test_every_action_is_pinned_by_full_commit_sha() -> None:
    uses = [step["uses"] for job in _workflow()["jobs"].values() for step in job.get("steps", []) if "uses" in step]
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), ref


def test_pages_builds_strictly_from_the_docs_group_only() -> None:
    text = PAGES.read_text(encoding="utf-8")
    assert "uv sync --frozen --only-group docs" in text
    assert "mkdocs build --strict" in text


def test_pages_publishes_the_landing_page_at_the_root_and_the_guide_under_docs() -> None:
    """D-1000: MkDocs builds into _site/docs (mkdocs.yml site_dir), the landing page (site/) is copied to _site/, and
    _site is what is uploaded."""
    text = PAGES.read_text(encoding="utf-8")
    assert "cp -R site/. _site/" in text
    assert text.index("mkdocs build --strict") < text.index("cp -R site/. _site/")
    uploads = [step for job in _workflow()["jobs"].values() for step in job.get("steps", [])
               if str(step.get("uses", "")).startswith("actions/upload-pages-artifact@")]
    assert [step["with"]["path"] for step in uploads] == ["_site"]
