"""D-1065: ``.github/workflows/release.yml`` drafts a release with ``SHA256SUMS`` (signed when the key is configured),
and ``tools/release_assets.py`` assembles the files from a bundles run.

The workflow keeps the other workflows' properties: manual dispatch only, read-only by default, every action pinned
by its full commit SHA, checkouts without credentials, inputs reaching shell steps only through the environment; the
write permission and the signing secret belong to the one approved ``publish`` job, which only drafts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
_spec = importlib.util.spec_from_file_location("release_assets", ROOT / "tools" / "release_assets.py")
assert _spec is not None and _spec.loader is not None
release_assets = importlib.util.module_from_spec(_spec)
sys.modules["release_assets"] = release_assets
_spec.loader.exec_module(release_assets)


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(job: str | None = None) -> list[dict[str, Any]]:
    jobs = _workflow()["jobs"]
    return [s for name, j in jobs.items() if job in (None, name) for s in j["steps"]]


def test_manual_dispatch_only_and_every_job_gated() -> None:
    wf = _workflow()
    assert set(wf[True]) == {"workflow_dispatch"}  # YAML 1.1 reads the key `on` as True
    assert set(wf[True]["workflow_dispatch"]["inputs"]) == {"tag", "bundles_run_id"}
    for name, job in wf["jobs"].items():
        assert job["if"] == "github.event_name == 'workflow_dispatch'", name


def test_permissions_are_minimal_and_only_publish_writes() -> None:
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["assemble"]["permissions"] == {"contents": "read", "actions": "read"}
    assert wf["jobs"]["publish"]["permissions"] == {"contents": "write"}
    assert wf["jobs"]["publish"]["environment"] == {"name": "release"}
    assert wf["defaults"] == {"run": {"shell": "bash"}}  # -eo pipefail


def test_every_action_is_pinned_and_every_checkout_drops_its_credentials() -> None:
    uses = [s["uses"] for s in _steps() if "uses" in s]
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u) for u in uses), uses
    checkouts = [s for s in _steps() if s.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 1 and checkouts[0]["with"]["persist-credentials"] is False
    assert checkouts[0]["with"]["ref"] == "refs/tags/${{ inputs.tag }}"
    assert not any(s.get("uses", "").startswith("actions/checkout@") for s in _steps("publish"))


def test_inputs_and_secrets_reach_shell_steps_only_through_the_environment() -> None:
    for step in _steps():
        assert "${{" not in str(step.get("run", "")), step.get("name")
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("secrets.") == 1 and "secrets.RELEASE_SIGNING_KEY" in text
    signing = [s for s in _steps() if "RELEASE_SIGNING_KEY" in str(s.get("env", {}))]
    assert len(signing) == 1 and signing[0] in _steps("publish")
    assert 'rm -f "$key"' in signing[0]["run"] and "umask 077" in signing[0]["run"]


def test_the_tag_is_checked_before_checkout_and_the_commit_is_the_tag_s() -> None:
    steps = _steps("assemble")
    first = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("actions/checkout@"))
    assert any("^v[0-9]+" in str(s.get("run", "")) for s in steps[:first])
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    assert '"$(git rev-parse HEAD)" = "$(git rev-parse "refs/tags/$TAG^{commit}")"' in runs


def test_the_release_is_a_draft_with_sha256sums_and_a_verified_signature() -> None:
    runs = "\n".join(str(s.get("run", "")) for s in _steps("publish"))
    assert "gh release create" in runs and "--draft" in runs and "--verify-tag" in runs
    assert "ssh-keygen -q -Y sign -f \"$key\" -n file files/SHA256SUMS" in runs
    assert "ssh-keygen -Y verify -f allowed_signers" in runs and "sha256sum --check --strict SHA256SUMS" in runs
    assert "RELEASE_SIGNING_KEY is not set" in runs  # a listed key without the secret fails the run
    assemble = "\n".join(str(s.get("run", "")) for s in _steps("assemble"))
    assert "tools/release_assets.py" in assemble and "src/agentprov/update/data/allowed_signers" in assemble


# ---------------------------------------------------------------------------------------------- release_assets.py

COMMIT = "a" * 40


def _leg(root: Path, built_name: str, *, version: str = "0.2.0", commit: str = COMMIT, ok: bool = True,
         clean: bool = True, digest: str | None = None) -> None:
    leg = root / f"agentprov-gui-{built_name}"
    leg.mkdir(parents=True)
    package = leg / built_name
    package.write_bytes(built_name.encode())
    (leg / "bundle-report.json").write_text(json.dumps({
        "ok": ok, "versions": {"agentprov-gui": version, "agentprov": version},
        "source": {"commit": commit, "basis": "checkout HEAD", "tree_clean": clean},
        "package": {"path": str(package), "sha256": digest or hashlib.sha256(package.read_bytes()).hexdigest()}}))


BUILT = ("AgentPROV-macos-arm64.dmg", "AgentPROV-macos-x86_64.dmg", "AgentPROV-windows-amd64.zip",
         "AgentPROV-windows-arm64.zip", "AgentPROV-linux-x86_64.tar.gz", "AgentPROV-linux-aarch64.tar.gz")


def test_assemble_writes_the_release_files_and_their_sums(tmp_path: Path) -> None:
    for name in BUILT:
        _leg(tmp_path / "bundles", name)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "agentprov-0.2.0-py3-none-any.whl").write_bytes(b"whl")
    (dist / "agentprov-0.2.0.tar.gz").write_bytes(b"sdist")
    (dist / ".gitignore").write_bytes(b"*")  # uv build's; not a release file
    source = tmp_path / "AgentPROV-0.2.0-source.tar.gz"
    source.write_bytes(b"src")
    out = tmp_path / "out"
    sums = release_assets.assemble(tag="v0.2.0", commit=COMMIT, bundles=tmp_path / "bundles", dist=dist,
                                   source=source, out=out)
    lines = sums.read_text().splitlines()
    names = [line.split("  ", 1)[1] for line in lines]
    assert names == sorted(names) and "AgentPROV-windows-x64.zip" in names and "AgentPROV-windows-amd64.zip" not in names
    assert set(names) == set(release_assets.BUNDLES) | {"agentprov-0.2.0-py3-none-any.whl", "agentprov-0.2.0.tar.gz",
                                                         "AgentPROV-0.2.0-source.tar.gz"}
    for line in lines:
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    # agentprov update reads the list it writes
    from agentprov.update.verify import parse_sums

    assert set(parse_sums(sums.read_bytes())) == set(names)
    done = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"], cwd=out, capture_output=True, text=True)
    assert done.returncode == 0 or "not found" in done.stderr  # shasum is optional on a test machine


@pytest.mark.parametrize(("change", "why"), [
    ({"version": "0.1.9"}, "not version"), ({"commit": "b" * 40}, "commit"), ({"clean": False}, "clean tree"),
    ({"ok": False}, "did not pass"), ({"digest": "0" * 64}, "sha256"),
])
def test_a_bundle_whose_report_does_not_match_the_tag_is_refused(tmp_path: Path, change: dict[str, Any],
                                                                 why: str) -> None:
    for name in BUILT:
        _leg(tmp_path / "bundles", name, **(change if name == BUILT[0] else {}))
    with pytest.raises(release_assets.ReleaseError, match=why):
        release_assets.assemble(tag="v0.2.0", commit=COMMIT, bundles=tmp_path / "bundles", dist=None, source=None,
                                out=tmp_path / "out")


def test_a_missing_bundle_is_refused(tmp_path: Path) -> None:
    for name in BUILT[1:]:
        _leg(tmp_path / "bundles", name)
    with pytest.raises(release_assets.ReleaseError, match="six bundles"):
        release_assets.assemble(tag="v0.2.0", commit=COMMIT, bundles=tmp_path / "bundles", dist=None, source=None,
                                out=tmp_path / "out")
