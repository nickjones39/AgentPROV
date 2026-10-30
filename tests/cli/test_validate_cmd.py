"""``agentprov validate`` (MN N.2.5): the AER tier, honest skips, refusals of what is not built, the raw-store adapter."""

from __future__ import annotations

import os

import pytest

from agentprov.cli.checks import open_store
from agentprov.cli.common import redact_personal


def test_a_valid_file_passes_and_skipped_work_is_reported_not_hidden(cli, valid_aer):
    run = cli("validate", str(valid_aer), "--json")
    assert run.code == 0, run.err
    document = run.json()
    assert document["counters"]["passed_with_skips"] == 1 and document["counters"]["passed"] == 0
    notices = " | ".join(document["notices"])
    for tier in ("sem", "prov", "linkage"):
        assert f"tier {tier} is not implemented in this build and was not run (skipped, not passed)" in notices
    assert "raw-store checks (V20, V21): no store given" in notices
    assert document["dry_run"] is False and document["corpus"] is None
    assert document["options"]["files"] == [redact_personal(str(valid_aer))]  # N.1.12(7): <home> on Windows tmp


def test_with_a_store_the_locator_checks_run(cli, valid_aer, raw_store):
    run = cli("validate", str(valid_aer), "--store", str(raw_store), "--json")
    assert run.code == 0, run.err
    notices = " | ".join(run.json()["notices"])
    assert "raw-store checks" not in notices


def test_a_store_without_the_cited_object_fails_the_locator_checks(cli, valid_aer, tmp_path):
    empty = tmp_path / "empty"
    (empty / "objects").mkdir(parents=True)
    run = cli("validate", str(valid_aer), "--store", str(empty), "--json")
    assert run.code == 1
    assert any(f["code"].startswith("aer.") for f in run.json()["failures"])


def test_store_must_be_a_directory(cli, valid_aer, tmp_path):
    assert cli("validate", str(valid_aer), "--store", str(tmp_path / "nope")).code == 2


def test_strict_fails_while_anything_was_skipped(cli, valid_aer, raw_store):
    run = cli("validate", str(valid_aer), "--store", str(raw_store), "--strict", "--json")
    assert run.code == 1
    codes = {f["code"] for f in run.json()["failures"]}
    assert codes == {"validate.check.skipped"}
    assert run.json()["issues_by_code"]["validate.check.skipped"] >= 1


def test_tiers_aer_alone_with_strict_still_fails_for_the_validators_own_skips(cli, valid_aer, raw_store):
    run = cli("validate", str(valid_aer), "--store", str(raw_store), "--tiers", "aer", "--strict", "--json")
    document = run.json()
    # no tier is "not run" now, but the validator still lists the profile-digest check as skipped (no digests given)
    assert not any("not implemented" in n for n in document["notices"])
    assert run.code == 1
    assert [f["detail"] for f in document["failures"]] == ["profile digest (V35): no package profile digests given"]


def test_release_implies_strict_and_requests_every_tier(cli, valid_aer):
    run = cli("validate", str(valid_aer), "--release", "--json")
    document = run.json()
    assert run.code == 1
    assert document["options"]["release"] is True
    assert any("tier shacl is not implemented" in n for n in document["notices"])
    assert any("tier regression is not implemented" in n for n in document["notices"])


def test_release_and_strict_are_mutually_exclusive(cli, valid_aer):
    assert cli("validate", str(valid_aer), "--release", "--strict").code == 2


def test_an_invalid_file_fails_with_codes_and_locations_but_no_file_text(cli, broken_aer):
    run = cli("validate", str(broken_aer), "--json")
    assert run.code == 1
    document = run.json()
    assert document["counters"]["failed"] == 1
    assert all("this is not json" not in f["detail"] for f in document["failures"])
    assert run.err.count("FAILED") == 1


def test_a_truncated_or_empty_file_is_a_failure_not_a_crash(cli, tmp_path):
    empty = tmp_path / "empty.aer.jsonl"
    empty.write_bytes(b"")
    run = cli("validate", str(empty), "--json")
    assert run.code == 1
    assert run.json()["failures"]


def test_many_files_each_get_a_row_and_failures_are_sorted(cli, valid_aer, broken_aer):
    run = cli("validate", str(broken_aer), str(valid_aer), "--json")
    document = run.json()
    assert run.code == 1
    assert document["counters"]["files"] == 2
    assert document["counters"]["passed_with_skips"] == 1 and document["counters"]["failed"] == 1


def test_aer_option_accepts_any_suffix_and_repeats(cli, valid_aer, tmp_path):
    odd = tmp_path / "record.dat"
    odd.write_bytes(valid_aer.read_bytes())
    run = cli("validate", "--aer", str(odd), "--aer", str(valid_aer), "--aer", str(odd), "--json")
    assert run.code == 0, run.err
    assert run.json()["counters"]["files"] == 2  # a repeated path is validated once


def test_unknown_suffix_is_a_usage_error_naming_the_alternative(cli, tmp_path):
    odd = tmp_path / "record.dat"
    odd.write_bytes(b"x")
    run = cli("validate", str(odd))
    assert run.code == 2 and "--aer" in run.err


def test_nothing_to_validate_is_a_usage_error(cli):
    assert cli("validate").code == 2


def test_other_tiers_files_are_refused_as_unsupported(cli, tmp_path):
    prov = tmp_path / "x.prov.json"
    prov.write_bytes(b"{}")
    run = cli("validate", str(prov), "--json")
    assert run.code == 5
    assert run.json()["refusal"]["status"] == "the prov tier is not implemented in this build"


@pytest.mark.parametrize(
    "flags",
    [["--report", "r.json"], ["--prov-spec", "s"], ["--sample", "3"], ["--seed", "1"]],
)
def test_corpus_mode_options_are_refused_in_file_mode(cli, valid_aer, flags):
    run = cli("validate", str(valid_aer), *flags)
    assert run.code == 5
    assert "corpus mode" in run.err


def test_files_with_corpus_are_a_usage_error(cli, valid_aer):
    assert cli("validate", str(valid_aer), "--corpus", "d").code == 2


def test_card_with_files_is_a_usage_error(cli, valid_aer):
    """``--card`` lints one card (phase 11, N.2.5(7)); combined with files it is a usage error."""
    assert cli("validate", str(valid_aer), "--card", "c.md").code == 2


def test_unknown_tier_is_a_usage_error(cli, valid_aer):
    assert cli("validate", str(valid_aer), "--tiers", "aer,bogus").code == 2


def test_not_requesting_the_aer_tier_validates_nothing_and_says_so(cli, valid_aer):
    run = cli("validate", str(valid_aer), "--tiers", "sem", "--json")
    assert run.json()["counters"]["files"] == 0
    assert any("nothing was validated" in n for n in run.json()["notices"])


def test_dry_run_is_accepted_and_marked(cli, valid_aer):
    run = cli("validate", str(valid_aer), "--dry-run", "--json")
    assert run.code == 0 and run.json()["dry_run"] is True


def test_validation_never_modifies_its_input(cli, valid_aer):
    before = valid_aer.read_bytes(), os.stat(valid_aer).st_mtime_ns
    cli("validate", str(valid_aer))
    assert (valid_aer.read_bytes(), os.stat(valid_aer).st_mtime_ns) == before


def make_symlink(link, target):
    """Create a symlink or skip: the capability is probed, not inferred from the operating system (D-7)."""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create symbolic links")


def test_a_symlinked_file_is_refused_by_the_no_follow_open(cli, valid_aer, tmp_path):
    link = tmp_path / "link.aer.jsonl"
    make_symlink(link, valid_aer)
    run = cli("validate", str(link), "--json")
    assert run.code == 1
    assert run.json()["failures"][0]["code"] == "ingest.path.symlink"


def test_directory_store_finds_objects_with_any_extension(raw_store):
    import aer_support as s

    store = open_store(raw_store)
    assert store.has(s.ARTEFACT_SHA) and store.size(s.ARTEFACT_SHA) == len(s.ARTEFACT_BYTES)
    assert store.read_bytes(s.ARTEFACT_SHA) == s.ARTEFACT_BYTES
    assert not store.has("0" * 64)
    with pytest.raises(KeyError):
        store.size("0" * 64)
    with pytest.raises(KeyError):
        store.read_bytes("0" * 64)


def test_directory_store_rejects_non_digest_names_before_touching_the_filesystem(raw_store):
    store = open_store(raw_store)
    for bad in ("../../etc/passwd", "AB" * 32, "ab", "", "a" * 63 + "/"):
        assert not store.has(bad)


def test_store_refuses_symlinked_objects(raw_store, tmp_path):
    from agentprov.raw.store import RawStoreError

    import aer_support as s

    shard = raw_store / "objects" / s.ARTEFACT_SHA[:2]
    real = next(shard.iterdir())
    outside = tmp_path / "outside"
    outside.write_bytes(b"x")
    real.unlink()
    make_symlink(real, outside)
    with pytest.raises(RawStoreError):  # a symlink inside the store is tampering, never "absent"
        open_store(raw_store).has(s.ARTEFACT_SHA)
