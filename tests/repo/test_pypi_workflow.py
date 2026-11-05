"""The PyPI publish workflow (``.github/workflows/pypi.yml``, D-1012) builds from the release tag itself (review UC-45):
it checks out ``refs/tags/<tag>`` (an unqualified ref resolves a branch of the same name first), checks the input is a
release tag before anything is checked out, and asserts that the checked-out commit is the tag's."""

from __future__ import annotations

import re
import tomllib
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


#: The packages pypi.yml publishes from one tag, by their pyproject files.
PUBLISHED = ("pyproject.toml", "capture/pyproject.toml", "zenodo/pyproject.toml")


def _name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    assert match, requirement
    return match[0]


def test_published_packages_require_their_siblings_at_the_release_version() -> None:
    """AU-TWF-13: the three packages are published together from one tag, so each requires its siblings at exactly that
    version; a bare requirement let ``pip install agentprov==X`` take whatever ``agentprov-capture`` is newest."""
    projects = [tomllib.loads((ROOT / f).read_text(encoding="utf-8"))["project"] for f in PUBLISHED]
    versions = {p["name"]: p["version"] for p in projects}
    assert len(set(versions.values())) == 1, versions
    requirements = [(p["name"], r) for p in projects for r in
                    [*p.get("dependencies", ()), *(r for rs in p.get("optional-dependencies", {}).values() for r in rs)]]
    siblings = [(who, r) for who, r in requirements if _name(r) in versions]
    assert {_name(r) for _who, r in siblings} == {"agentprov", "agentprov-capture", "agentprov-zenodo"}
    for who, r in siblings:
        assert r == f"{_name(r)}=={versions[_name(r)]}", f"{who} requires {r!r}"
