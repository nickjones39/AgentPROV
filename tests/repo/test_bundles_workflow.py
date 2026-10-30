"""D-750: ``.github/workflows/bundles.yml`` builds the GUI bundles on manual dispatch only, with read-only
permissions, every action pinned by its full commit SHA, the D-750 runners, artifacts with a retention, no release
step and no secret."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "bundles.yml"


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict[str, Any]]:
    return [step for job in _workflow()["jobs"].values() for step in job["steps"]]


def test_manual_dispatch_only_and_every_job_gated() -> None:
    workflow = _workflow()
    assert set(workflow[True]) == {"workflow_dispatch"}  # YAML 1.1 reads the key `on` as True
    for name, job in workflow["jobs"].items():
        assert job["if"] == "github.event_name == 'workflow_dispatch'", name


def test_read_only_permissions() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in _workflow()["jobs"].values())


def test_every_action_is_pinned_by_a_full_sha() -> None:
    uses = [step["uses"] for step in _steps() if "uses" in step]
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u) for u in uses), uses


def test_the_d750_runners() -> None:
    legs = _workflow()["jobs"]["bundle"]["strategy"]["matrix"]["include"]
    assert {leg["os"] for leg in legs} == {"ubuntu-22.04", "ubuntu-24.04-arm", "windows-latest"}
    assert {leg["os"]: leg["glibc_floor"] for leg in legs}["ubuntu-24.04-arm"] == "2.39"


def test_artifacts_with_retention_and_no_release_or_secret() -> None:
    uploads = [s for s in _steps() if s.get("uses", "").startswith("actions/upload-artifact@")]
    assert len(uploads) == 1 and 1 <= int(uploads[0]["with"]["retention-days"]) <= 30
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text and "gh release" not in text and "release-action" not in text.lower()
    assert "action-gh-release" not in text and "contents: write" not in text


def test_checkout_keeps_no_credentials() -> None:
    checkout = next(s for s in _steps() if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False
