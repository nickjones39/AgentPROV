"""D-430: ``recompute`` at this package of a corpus recorded under other profile or catalogue versions is a drift report.

A dry run lists the drift per stage (``version drift: ...`` notices) and classifies as before; a writing recompute
(``--out``) refuses before anything is written, because the output would mix versions (H.2.5). A corpus recorded under
the current versions recomputes as before. The source corpus is the small AgentDojo working corpus of ``derive_support``;
"built under v1" is its recorded ``aer`` stage pointed at the archived v1 profile and catalogue (their real digests, so
the rules check passes). Fixture text is never printed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.aer.rules import load_catalogue
from agentprov.cli.main import main
from agentprov.testing import fs_guard

PROFILE = "agentdojo-upstream"


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return ds.agentdojo_corpus(tmp_path_factory.mktemp("drift-src"), count=1)


def _run(capsys: pytest.CaptureFixture[str], *argv: str, guard: Path) -> tuple[int, dict[str, Any], str]:
    capsys.readouterr()
    with fs_guard.unchanged(guard):
        code = main([*argv, "--json", "--progress", "off", "--in-process"])
    out, err = capsys.readouterr()
    lines = out.splitlines()
    return code, (json.loads(lines[-1]) if lines else {}), err


def _copy(src: Path, dest: Path) -> Path:
    shutil.copytree(ds.partial(src), ds.partial(dest), symlinks=True)
    return dest


def _record_v1(root: Path) -> None:
    """Point the recorded ``aer`` stage at the archived v1 profile and agentdojo catalogue (as a pre-D-31 corpus)."""
    path = ds.partial(root) / "derivation.json"
    derivation = json.loads(path.read_text())
    old = load_profile(PROFILE, 1)
    assert old.version == 1 and load_profile(PROFILE).version > 1
    for stage in derivation["stages"]:
        if stage["stage"] == "aer":
            assert stage["profile"] == f"{PROFILE}@{load_profile(PROFILE).version}"
            stage["profile"], stage["profile_sha256"] = f"{PROFILE}@1", "sha256:" + old.sha256
            stage["rules"] = {**stage["rules"], "agentdojo": 1}
            stage["rules_sha256"] = {**stage["rules_sha256"], "agentdojo": "sha256:" + load_catalogue("agentdojo", 1).digest}
    path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")


def test_a_dry_run_reports_the_drift_per_stage(capsys, source, tmp_path):
    src = _copy(source, tmp_path / "src")
    _record_v1(src)
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", guard=ds.partial(src))
    assert code == 0, err
    drift = [n for n in summary["notices"] if n.startswith("version drift: ")]
    current = load_catalogue("agentdojo").version
    assert f"version drift: aer: source profile {PROFILE} v1 recorded, v{load_profile(PROFILE).version} current" in drift
    assert f"version drift: aer: catalogue agentdojo v1 recorded, v{current} current" in drift
    # the stored AERs are this build's (only the record says v1), so the outputs compare as before; nothing is refused
    assert summary["counters"]["unexplained_change"] == summary["counters"]["failed"] == 0


def test_a_writing_recompute_refuses_a_mixed_version_output(capsys, source, tmp_path):
    src = _copy(source, tmp_path / "src")
    _record_v1(src)
    out = tmp_path / "new"
    code, _summary, err = _run(capsys, "recompute", "--corpus", str(src), "--out", str(out), guard=ds.partial(src))
    assert code == 4
    assert "re-import to upgrade, or recompute at the building commit" in err and "agentdojo v1 recorded" in err
    assert not out.exists() and not ds.partial(out).exists()


def test_a_corpus_at_the_current_versions_recomputes_as_before(capsys, source, tmp_path):
    src = _copy(source, tmp_path / "src")
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", guard=ds.partial(src))
    assert code == 0, err
    assert not [n for n in summary["notices"] if n.startswith("version drift: ")]
    assert summary["counters"]["identical"] == summary["counters"]["selected"]
    out = tmp_path / "new"
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--out", str(out), guard=ds.partial(src))
    assert code == 0, err
    assert ds.partial(out).is_dir() and summary["counters"]["identical"] == summary["counters"]["selected"]


def _record_corpus_0_1(root: Path) -> None:
    """Record the corpus as an ``agentprov-corpus/0.1`` / ``aer/0.1`` build (P-1: the format axes are declared versions)."""
    path = ds.partial(root) / "corpus.json"
    manifest = json.loads(path.read_text())
    manifest["format"] = "agentprov-corpus/0.1"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    path = ds.partial(root) / "derivation.json"
    derivation = json.loads(path.read_text())
    for stage in derivation["stages"]:
        if stage["stage"] == "aer":
            stage["format"] = "aer/0.1"
    path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")


FORMAT_DRIFT = (
    "version drift: aer: format aer/0.1 recorded, aer/0.2 current",
    "version drift: corpus: format agentprov-corpus/0.1 recorded, agentprov-corpus/0.2 current",
    "version drift: prov: vocabulary apv 0.1.0 recorded (by agentprov-corpus/0.1), apv 0.2.0 current",
)


def test_a_dry_run_of_a_0_1_corpus_names_the_format_and_vocabulary_drift_p1(capsys, source, tmp_path):
    src = _copy(source, tmp_path / "src")
    _record_corpus_0_1(src)
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", guard=ds.partial(src))
    assert code == 0, err
    drift = [n for n in summary["notices"] if n.startswith("version drift: ")]
    assert all(line in drift for line in FORMAT_DRIFT), drift


def test_a_writing_recompute_of_a_0_1_corpus_is_refused_not_upgraded_p1(capsys, source, tmp_path):
    src = _copy(source, tmp_path / "src")
    _record_corpus_0_1(src)
    out = tmp_path / "new"
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--out", str(out), guard=ds.partial(src))
    assert code == 4 and summary["outcome"] == "refused"
    assert "aer/0.1 recorded, aer/0.2 current" in err and "apv 0.1.0 recorded" in err
    assert not out.exists() and not ds.partial(out).exists()
    # P-3: the refusal is in the summary, not only in the notices
    refusal = summary["refusal"]
    assert refusal is not None and refusal["status"] == "corpus.derive.version_drift" and refusal["mode"] == "recompute"
    assert refusal["lines"] and "re-import to upgrade" in " ".join(refusal["lines"])
    # RC-8: each drift is a line of its own, so no reason is cut by the 300-character line limit
    assert all(line.removeprefix("version drift: ") in refusal["lines"] for line in FORMAT_DRIFT), refusal["lines"]


def test_a_sem_prov_recompute_of_a_0_1_corpus_is_refused_for_the_vocabulary_p1(capsys, source, tmp_path):
    src = _copy(source, tmp_path / "src")
    _record_corpus_0_1(src)
    out = tmp_path / "new"
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--stages", "sem,prov,validation",
                              guard=ds.partial(src))
    assert code == 4, err
    assert "apv 0.1.0 recorded (by agentprov-corpus/0.1), apv 0.2.0 current" in err
    assert "aer: format" not in err  # no re-map: the records stay as they are
    assert not ds.partial(out).exists()


def test_the_format_and_vocabulary_drift_lead_the_refusal_rc18(capsys, source, tmp_path):
    # re-check RC-18: with profile and catalogue drift as well, the lines that decide the refusal come first, so a
    # capped summary.refusal never loses them
    src = _copy(source, tmp_path / "src")
    _record_v1(src)
    _record_corpus_0_1(src)
    out = tmp_path / "new"
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--out", str(out), guard=ds.partial(src))
    assert code == 4, err
    lines = summary["refusal"]["lines"]
    assert lines[1:1 + len(FORMAT_DRIFT)] == [line.removeprefix("version drift: ") for line in FORMAT_DRIFT], lines
    assert any("agentdojo v1 recorded" in line for line in lines[1 + len(FORMAT_DRIFT):]), lines
    assert "<U+000A>" not in err

# ------------------------------------------------------------------------------------------------ D-640: the aprov version
APROV_V1 = "sha256:79b0a1e78dc7d9c057c7918792dc13ec32e330a070e34696a7875dedb39c6442"  # archived, D-621


def _record_aprov(root: Path, digest: str, version: int | None) -> None:
    """Point the recorded ``prov`` stage at another aprov catalogue: ``version`` recorded, or (``None``) only its digest
    (a corpus built before D-640)."""
    path = ds.partial(root) / "derivation.json"
    derivation = json.loads(path.read_text())
    for stage in derivation["stages"]:
        if stage["stage"] == "prov":
            stage["rules_sha256"] = digest
            stage.pop("rules", None)
            if version is not None:
                stage["rules"] = {"aprov": version}
    path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")


def test_the_prov_stage_records_the_aprov_version(source):
    from agentprov.prov.specs import load_spec

    derivation = json.loads((ds.partial(source) / "derivation.json").read_text())
    prov = next(s for s in derivation["stages"] if s["stage"] == "prov")
    spec = load_spec()
    assert prov["rules"] == {"aprov": spec.catalogue_version} and prov["rules_sha256"] == "sha256:" + spec.catalogue_sha256


@pytest.mark.parametrize("version", [1, None], ids=["recorded", "digest-only"])
def test_an_archived_aprov_version_is_drift_not_a_mismatch(capsys, source, tmp_path, version):
    from agentprov.prov.specs import load_spec

    src = _copy(source, tmp_path / "src")
    _record_aprov(src, APROV_V1, version)
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", guard=ds.partial(src))
    assert code == 0, err
    current = load_spec().catalogue_version
    assert f"version drift: prov: catalogue aprov v1 recorded, v{current} current" in summary["notices"]
    assert not [n for n in summary["notices"] if n.startswith("rules.mismatch")]


def test_unknown_aprov_bytes_are_a_mismatch(capsys, source, tmp_path):
    src = _copy(source, tmp_path / "src")
    _record_aprov(src, "sha256:" + "0" * 64, None)
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", guard=ds.partial(src))
    assert [n for n in summary["notices"] if n.startswith("rules.mismatch") and "aprov" in n]
    assert not [n for n in summary["notices"] if "catalogue aprov v" in n]


def test_the_aprov_version_of_a_stage():
    from agentprov.corpus.authority import prov_catalogue_ok, prov_catalogue_version
    from agentprov.prov.specs import load_spec

    spec = load_spec()
    current = "sha256:" + spec.catalogue_sha256
    assert prov_catalogue_version({"rules_sha256": current}) == spec.catalogue_version
    assert prov_catalogue_version({"rules_sha256": APROV_V1}) == 1
    assert prov_catalogue_version({"rules_sha256": "sha256:" + "0" * 64}) is None
    assert prov_catalogue_version({"rules": {"aprov": 1}, "rules_sha256": APROV_V1}) == 1
    assert prov_catalogue_ok({"rules_sha256": APROV_V1}) and prov_catalogue_ok({"rules_sha256": current})
    assert not prov_catalogue_ok({"rules": {"aprov": spec.catalogue_version}, "rules_sha256": APROV_V1})
