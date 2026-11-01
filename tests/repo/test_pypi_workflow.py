"""The PyPI publish workflow (``.github/workflows/pypi.yml``, D-1012) builds from the release tag itself (review UC-45):
it checks out ``refs/tags/<tag>`` (an unqualified ref resolves a branch of the same name first), checks the input is a
release tag before anything is checked out, and asserts that the checked-out commit is the tag's."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PYPI = ROOT / ".github" / "workflows" / "pypi.yml"


def _build_steps() -> list[dict[str, Any]]:
    doc = yaml.safe_load(PYPI.read_text(encoding="utf-8"))
    return list(doc["jobs"]["build"]["steps"])


def test_the_build_checks_out_the_tag_ref_without_credentials() -> None:
    steps = _build_steps()
    checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkouts) == 1
    assert checkouts[0]["with"] == {"ref": "refs/tags/${{ inputs.tag }}", "persist-credentials": False}
    first = steps.index(checkouts[0])
    assert any("^v[0-9]+" in str(s.get("run", "")) for s in steps[:first]), "the tag name is checked before checkout"


def test_the_build_asserts_the_commit_is_the_tag_s() -> None:
    runs = "\n".join(str(s.get("run", "")) for s in _build_steps())
    assert '"$(git rev-parse HEAD)" = "$(git rev-parse "refs/tags/$TAG^{commit}")"' in runs
    assert "git describe --tags --exact-match HEAD" in runs


def test_the_tag_input_reaches_shell_steps_only_through_the_environment() -> None:
    for step in _build_steps():
        assert "${{" not in str(step.get("run", "")), "no expression is expanded inside a run script"
    assert re.search(r"ref: refs/tags/\$\{\{ inputs\.tag \}\}", PYPI.read_text(encoding="utf-8"))
