"""``agentprov package`` seal mode and ``validate --card`` (MN N.2.11, N.2.5(7); HL-T8).

The CLI gathers the build inputs (spec, card, changes and the statements table from a ``corpora/`` directory, the
package's profiles, the licence files, the git facts) and seals a copy of a small working corpus; the summary is a valid
``agentprov-cli-summary/0.1`` document carrying the content digest. A refused precondition exits 4 and a missing spec
exits 2. The deposit mode is tested in ``test_package_deposit_cmd.py``.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_CORPUS_TESTS = Path(__file__).resolve().parents[1] / "unit" / "corpus"
if str(_CORPUS_TESTS) not in sys.path:
    sys.path.insert(0, str(_CORPUS_TESTS))

import seal_support as ss  # noqa: E402


@pytest.fixture
def setup(tmp_path_factory, tmp_path, monkeypatch):
    from agentprov.cli import package

    monkeypatch.setattr(package, "git_facts", lambda repo=package.REPO_ROOT: (ss.COMMIT, True))
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: True)
    corpus = ss.working_corpus(tmp_path_factory, tmp_path / "work" / "mini")
    spec_dir = tmp_path / "corpora" / "mini-agentdojo"
    spec_dir.mkdir(parents=True)
    (spec_dir / "corpus-spec.toml").write_text(ss.SPEC)
    (spec_dir / "CARD.md").write_text(ss.CARD)
    (spec_dir / "CHANGES.toml").write_text(ss.CHANGES)
    shutil.copy(ss.REPO / "corpora" / "datasheet-statements.toml", tmp_path / "corpora" / "datasheet-statements.toml")
    licence = tmp_path / "LICENSE.txt"
    licence.write_bytes(b"test licence text\n")
    return corpus, spec_dir / "corpus-spec.toml", licence


def test_package_seals_and_reports_the_digests(cli, setup, check_summary):
    corpus, spec, licence = setup
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["corpus"]["state"] == "sealed" and summary["corpus"]["content_digest"].startswith("sha256:")
    assert summary["counters"]["executions"] == 3
    assert "root digest sha256:" in run.err
    assert (corpus / "corpus.json").is_file() and not corpus.with_name("mini.partial").exists()
    datasheet = (corpus / "DATASHEET.md").read_text()
    assert "| source_id | profile | group |" in datasheet  # the stats field-group table (R-57), not the placeholder
    assert "it was not computed by this build" not in datasheet


@pytest.mark.parametrize("dry_run", [False, True])
def test_the_summary_writes_a_corpus_under_home_as_home(cli, setup, tmp_path, monkeypatch, dry_run):
    # CC-21: corpus.root used to be the literal path while options.corpus was written "<home>/..." (N.1.12(7))
    corpus, spec, licence = setup
    monkeypatch.setenv("HOME", str(tmp_path))
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--json", *(["--dry-run"] if dry_run else []))
    assert run.code == 0, run.err
    assert str(tmp_path) not in run.out and str(tmp_path) not in run.err
    assert run.json()["corpus"]["root"] == "<home>/work/mini"


def test_package_dry_run_writes_nothing(cli, setup):
    corpus, spec, licence = setup
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--dry-run", "--json")
    assert run.code == 0, run.err
    assert run.json()["dry_run"] is True and not corpus.exists()


def test_a_dry_run_inside_a_git_work_tree_is_refused_like_the_real_run(cli, setup, tmp_path, monkeypatch):
    # CC-20: the read-only git guard used to be skipped under --dry-run, so the dry run exited 0 where the real run exits 4
    from agentprov.cli import package

    corpus, spec, licence = setup
    (tmp_path / "work" / ".git").mkdir()
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: False)
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--dry-run", "--json")
    assert run.code == 4, run.err
    assert not corpus.exists()


def test_a_missing_licence_file_is_refused_with_exit_4(cli, setup):
    corpus, spec, _ = setup
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec), "--json")
    assert run.code == 4
    assert run.json()["outcome"] == "refused"


def test_a_missing_spec_is_a_usage_error(cli, setup, tmp_path):
    corpus, _, _ = setup
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(tmp_path / "nope.toml"))
    assert run.code == 2


def test_seal_mode_takes_one_corpus_and_a_version(cli, setup, tmp_path):
    corpus, spec, licence = setup
    assert cli("package", "--corpus", str(corpus), "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec",
               str(spec)).code == 2
    assert cli("package", "--corpus", str(corpus), "--spec", str(spec), "--licence-file", f"LICENSE={licence}").code == 2


def test_rerunning_package_resumes_a_seal_killed_before_the_swap(cli, setup):
    # CB-9: a seal killed with no Python exception after corpus.json says sealed: true is finished by the next run
    import os

    from agentprov.corpus import package

    corpus, spec, licence = setup
    argv = ("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec), "--licence-file",
            f"LICENSE={licence}", "--json")
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child never returns into pytest
        try:
            package._verify_chain = lambda _root: os._exit(137)
            cli(*argv)
        finally:
            os._exit(1)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 137 and not corpus.exists()
    run = cli(*argv)
    assert run.code == 0, run.err
    summary = run.json()
    assert summary["corpus"]["state"] == "sealed" and summary["counters"]["executions"] == 3
    assert any("resumed an interrupted seal" in str(n) for n in summary["notices"])
    assert (corpus / "corpus.json").is_file() and not corpus.with_name("mini.partial").exists()


@pytest.mark.parametrize("bad", ["2026-02-30", "2026-13-45", "0000-00-00", "2026/10/12"])
def test_an_impossible_or_malformed_release_date_is_a_usage_error(cli, setup, bad):
    # CB-18: release.created of a sealed corpus is never an impossible date (H.2.13); a bad format is exit 2, not 70.
    corpus, spec, licence = setup
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--release-date", bad)
    assert run.code == 2, run.err
    assert "--release-date is YYYY-MM-DD" in run.err
    assert not corpus.exists()


def test_an_out_of_range_source_date_epoch_is_a_usage_error(cli, setup, monkeypatch):
    # CB-18: a SOURCE_DATE_EPOCH past 9999-12-31T23:59:59Z cannot become release.created: exit 2, not an internal error.
    corpus, spec, licence = setup
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(10**12))
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}")
    assert run.code == 2, run.err
    assert "SOURCE_DATE_EPOCH" in run.err
    assert not corpus.exists()


@pytest.mark.parametrize("epoch", ["\u0661\u0662\u0663", "\u00b2"])
def test_a_non_ascii_digit_source_date_epoch_is_not_a_number(cli, setup, monkeypatch, epoch):
    # CB-18b (CC-19): str.isdigit accepts Arabic-Indic and superscript digits; SOURCE_DATE_EPOCH is ASCII digits only,
    # so these are ignored like any other non-numeric value (created: null), never 1970-01-01T00:02:03Z or exit 70.
    corpus, spec, licence = setup
    monkeypatch.setenv("SOURCE_DATE_EPOCH", epoch)
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}")
    assert run.code == 0, run.err
    release = json.loads((corpus / "corpus.json").read_text())["release"]
    assert release["created"] is None and release["source_date_epoch"] is None


def test_validate_card(cli, tmp_path):
    good = ss.REPO / "corpora" / "rope" / "CARD.md"
    assert cli("validate", "--card", str(good)).code == 0
    bad = tmp_path / "CARD.md"
    bad.write_text("---\nmode: import\n---\nThe corpus has 396 runs and is lossless.\n")
    run = cli("validate", "--card", str(bad), "--json")
    assert run.code == 1
    codes = {f["code"] for f in run.json()["failures"]}
    assert {"card.H.9(3)", "card.NC-ALL-03"} <= codes


def _events(path: Path) -> list[dict]:
    import json

    return [e for e in map(json.loads, path.read_text().splitlines()) if e["event"] not in ("run", "heartbeat")]


def test_package_and_verify_write_stage_events_to_the_progress_file(cli, setup, tmp_path):
    """CLI robustness item 5: package and verify wrote nothing to --progress-file (N.1.14 names both)."""
    corpus, spec, licence = setup
    events = tmp_path / "seal.jsonl"
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--progress", "off", "--progress-file", str(events))
    assert run.code == 0, run.err
    seen = _events(events)
    assert seen[0]["event"] == "start" and seen[0]["command"] == "package" and seen[-1]["event"] == "end"
    assert seen[0]["total"] == 7 and [e["unit"] for e in seen if e["event"] == "unit_done"] == [
        "withhold", "executions", "manifest", "write", "checksums", "chain", "swap"]
    checked = tmp_path / "verify.jsonl"
    assert cli("verify", "--corpus", str(corpus), "--progress-file", str(checked)).code == 0
    seen = _events(checked)
    assert seen[0]["event"] == "start" and seen[0]["command"] == "verify" and seen[0]["plan"] == "level chain"
    assert [(e["unit"], e["status"]) for e in seen if e["event"] == "unit_done"] == [("verify.chain", "ok")]
    assert seen[-1]["event"] == "end" and seen[-1]["units_done"] == 1


def test_a_corpus_that_skipped_prov_conformance_cannot_be_sealed_and_fails_verify(cli, setup):
    """G2c-5 (D-432): the mark ``validation.prov_conformance: "skipped"`` makes the corpus unvalidated."""
    import json

    corpus, spec, licence = setup
    manifest_path = corpus.with_name(corpus.name + ".partial") / "corpus.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["validation"] = {**(manifest.get("validation") or {}), "prov_conformance": "skipped"}
    manifest_path.write_text(json.dumps(manifest))
    checked = cli("verify", "--corpus", str(corpus.with_name(corpus.name + ".partial")), "--json")
    assert checked.code == 1 and checked.json()["issues_by_code"].get("corpus.validation.prov_conformance_skipped") == 1
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--json")
    assert run.code == 4 and "[package.refused.prov_conformance]" in run.err, run.err
    assert not (corpus / "corpus.json").exists()


@pytest.mark.parametrize("spec_mode", ["import", "live"])
def test_a_live_corpus_with_only_import_rows_is_refused(cli, setup, spec_mode):
    """D-666: a native-log live corpus (the Inspect harness) has a `mode: live` manifest and `mode: import` rows, because
    each row's primary artefact is the native log. `package` refuses it from the manifest, before the spec check and
    whatever the spec's mode, so the row check is not the only guard."""
    import dataclasses

    from agentprov.corpus import package as corpus_package
    from agentprov.corpus.spec import load_spec

    corpus, spec, licence = setup
    partial = corpus.with_name(corpus.name + ".partial")
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    assert rows and {r["mode"] for r in rows} == {"import"} and {r["attempt"] for r in rows} == {None}
    manifest = json.loads((partial / "corpus.json").read_text())
    manifest["mode"] = "live"
    (partial / "corpus.json").write_text(json.dumps(manifest))
    if spec_mode == "import":
        run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
                  "--licence-file", f"LICENSE={licence}", "--json")
        assert run.code == 5 and "[package.unsupported.live]" in run.err, run.err
        assert not (corpus / "corpus.json").exists()
    else:  # a spec that agrees with the manifest's mode: the spec check would pass, the manifest check still refuses
        live_spec = dataclasses.replace(load_spec(spec), mode="live")
        with pytest.raises(corpus_package.PackageRefusedError) as refused:
            corpus_package._check_working(manifest, live_spec, "0.1.0")
        assert refused.value.code == "package.unsupported.live" and refused.value.exit_code == 5


# ------------------------------------------------------------------------------------------------ D-960: archived profile
def _as_built_with_profile_v1(partial: Path) -> bytes:
    """Relabel the working corpus as imported with ``agentdojo-upstream@1`` (archived since v2): the source and stage
    records name v1 and its digest. Returns v1's bytes. The records themselves are v2's; package reads the label."""
    import hashlib
    from importlib import resources

    data = resources.files("agentprov").joinpath("adapters", "agentdojo", "profiles", "archive",
                                                 "agentdojo-upstream.profile.v1.toml").read_bytes()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    manifest = json.loads((partial / "corpus.json").read_text("utf-8"))
    manifest["sources"][0]["profile"].update(version=1, sha256=digest)
    for entry in (manifest.get("profiles") or {}).get("source") or ():
        if entry.get("id") == "agentdojo-upstream":
            entry.update(version=1, sha256=digest)
    (partial / "corpus.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", "utf-8")
    derivation = json.loads((partial / "derivation.json").read_text("utf-8"))
    for stage in derivation["stages"]:
        if stage.get("stage") == "aer":
            stage["profile"], stage["profile_sha256"] = "agentdojo-upstream@1", digest
    (partial / "derivation.json").write_text(json.dumps(derivation, sort_keys=True, indent=2) + "\n", "utf-8")
    return data


def test_a_corpus_built_with_an_archived_profile_version_is_sealed_with_it_d960(cli, setup):
    corpus, spec, licence = setup
    archived = _as_built_with_profile_v1(corpus.with_name("mini.partial"))
    spec.write_text(ss.SPEC.replace('profile = "agentdojo-upstream@2"', 'profile = "agentdojo-upstream@1"'))
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--json")
    assert run.code == 0, run.err
    assert (corpus / "rules" / "agentdojo-upstream.profile.toml").read_bytes() == archived
    source = json.loads((corpus / "corpus.json").read_text("utf-8"))["sources"][0]
    assert source["profile"]["version"] == 1


def test_a_profile_version_the_package_does_not_ship_is_a_usage_error_d960(cli, setup):
    corpus, spec, licence = setup
    spec.write_text(ss.SPEC.replace('profile = "agentdojo-upstream@2"', 'profile = "agentdojo-upstream@9"'))
    run = cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec),
              "--licence-file", f"LICENSE={licence}", "--dry-run", "--json")
    assert run.code == 2 and "ships no such version" in run.err
