"""``agentprov verify`` behaviour beyond the tamper table (H.5.5; N.2.6; N.1.7; D-38, D-39; U4).

Working trees and tombstones, sampling, ``--against-pins`` with an injected listing, release-mode rules, the public API
and ``stats`` entry points, and the two places that run ``verify --level chain`` for other commands: ``seal()`` (N.2.11
step 3) and the deposit builder's injected verifier (H.10.1(3)).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import verify_support as vs

from agentprov.corpus.verify import (
    FAILED,
    TOMBSTONED,
    UNVERIFIED,
    VerifyUsageError,
    git_blob_sha1,
    sample_executions,
    verify_corpus,
)
from agentprov.testing import fs_guard


# ------------------------------------------------------------------------------------------------ sampling
def test_the_sample_is_seeded_uniform_without_replacement_and_order_free():
    ids = [f"ex_{i:026d}" for i in range(50)]
    first = sample_executions(ids, 10, "seed-a")
    assert first == sample_executions(list(reversed(ids)), 10, "seed-a") == sorted(set(first))
    assert len(first) == 10 and set(first) <= set(ids)
    assert sample_executions(ids, 10, "seed-b") != first
    assert sample_executions(ids, 99, "s") == sorted(ids)
    hits = {ex: 0 for ex in ids}
    for seed in range(400):
        for ex in sample_executions(ids, 5, str(seed)):
            hits[ex] += 1
    assert min(hits.values()) > 10 and max(hits.values()) < 80  # every id is drawn, none dominates (expected 40)


def test_sampled_verification_is_deterministic(sealed):
    a = verify_corpus(sealed, level="chain", sample=2, seed="s1")
    b = verify_corpus(sealed, level="chain", sample=2, seed="s1")
    assert a.ok and b.ok and a.sample == b.sample == {"n": 2, "of": 3, "seed": "s1"}
    assert a.counters["executions_checked"] == 2
    assert any("under --sample" in n for n in a.notices)


def test_sampled_rederive_checks_only_the_sample(sealed):
    from agentprov.stats.source import import_hooks

    report = verify_corpus(sealed, level="rederive", sample=1, seed="x", import_hooks=import_hooks())
    assert report.ok and report.counters["rederive_identical"] == 1
    assert any("corpus-level files" in n for n in report.notices)


@pytest.mark.parametrize("kwargs", [{"sample": 1}, {"seed": "s"}, {"sample": 1, "seed": "s", "release": True,
                                                                       "root_digests": ("sha256:" + "0" * 64,)},
                                    {"release": True}, {"root_digests": ("sha256:xyz",)}, {"level": "deep"}])
def test_usage_errors(sealed, kwargs):
    with pytest.raises(VerifyUsageError):
        verify_corpus(sealed, **kwargs)


def test_cli_usage_errors(cli, sealed):
    assert cli("verify", "--corpus", str(sealed), "--sample", "2").code == 2
    assert cli("verify", "--corpus", str(sealed), "--release").code == 2  # D-39: --root-digest required in tree mode
    assert cli("verify", "--corpus", str(sealed), "--sample", "1", "--seed", "a", "--release",
               "--root-digest", vs.root_digest(sealed)).code == 2
    assert cli("verify", "--corpus", str(sealed), "--root-digest", "md5:00").code == 2
    assert cli("verify", "--corpus", str(sealed), "--allow-network").code == 2
    assert cli("verify", "--corpus", str(sealed.parent / "nothing")).code == 2


# ------------------------------------------------------------------------------------------------ working trees
@pytest.fixture
def working(tmp_path: Path) -> Path:
    import derive_support as ds

    return ds.partial(ds.agentdojo_corpus(tmp_path))


def test_a_working_tree_has_no_checksums_to_verify(cli, working):
    with fs_guard.unchanged(working):
        run = cli("verify", "--corpus", str(working), "--json")
    assert run.code == 0, run.err  # dev mode: unverified checks are reported, not failed
    document = run.json()
    assert document["issues_by_code"] == {"checksums.absent": 1} and document["corpus"]["state"] == "working"
    assert document["failures"][0]["detail"].startswith("unverified:")
    report = verify_corpus(working, level="chain")
    assert report.passed() and not report.passed(release=True) and not report.ok


def test_a_purged_object_is_tombstoned_never_silently_missing(working):
    from agentprov.corpus.purge import apply, plan_corpus

    sha = json.loads((working / "executions.jsonl").read_text("utf-8").splitlines()[0])["raw"][0]["sha256"][7:]
    apply(plan_corpus(working, sha, "secret"))
    report = verify_corpus(working, level="chain")
    tombs = [f for f in report.findings if f.status == TOMBSTONED]
    assert [f.code for f in tombs] == ["raw.tombstoned"] and "(secret)" in tombs[0].detail
    assert not [f for f in report.findings if f.status == FAILED]  # missing because purged: not a failure
    # purge leaves the emptied shard directory behind: not closed-world, reported (sealing would refuse it)
    assert {f.code for f in report.findings if f.status == UNVERIFIED} <= {"checksums.absent", "corpus.tree.empty_dir"}
    assert report.passed() and not report.passed(release=True)


# ------------------------------------------------------------------------------------------------ --against-pins
def _listing(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (root / "raw" / "origins.jsonl").read_text("utf-8").splitlines():
        row = json.loads(line)
        out[row["origin"]["path"]] = row["origin"]["blob_sha1"]
    return out


def test_against_pins_with_a_pinned_tree_listing(sealed):
    listing = _listing(sealed)
    report = verify_corpus(sealed, level="chain", against_pins=True, pin_listing=lambda repo, commit: listing)
    assert report.ok and report.counters["origins_checked"] == 3
    forged = {path: "f" * 40 for path in listing}
    report = verify_corpus(sealed, level="chain", against_pins=True, pin_listing=lambda repo, commit: forged)
    assert report.codes() == {"raw.origin.blob_mismatch": 3}


def test_git_blob_id():
    assert git_blob_sha1([b"hello ", b"world\n"], 12) == "3b18e512dba79e4c8300dd08aeb37f8e728b8dad"


# ------------------------------------------------------------------------------------------------ entry points
def test_api_and_stats_levels(sealed):
    from agentprov import api
    from agentprov.stats.source import open_corpus

    for level in ("checksums", "chain", "rederive"):
        report = api.verify_corpus(sealed, level=level)
        assert report.ok and report.level == level
        opened = api.open_corpus(sealed, verify=level)  # type: ignore[arg-type]
        assert opened.verification == level and opened.verified and opened.root_digest == vs.root_digest(sealed)
    assert open_corpus(sealed, verify="chain").verification == "chain"


def test_seal_runs_verify_chain(sealed):
    from agentprov.corpus.manifest import ManifestError
    from agentprov.corpus.package import _verify_chain

    _verify_chain(sealed)
    prov = vs.first_file(sealed, "prov")
    prov.write_bytes(prov.read_bytes().replace(b"agentprov", b"agentprox", 1))
    vs.regenerate_checksums(sealed)
    with pytest.raises(ManifestError) as caught:
        _verify_chain(sealed)
    assert caught.value.code == "corpus.manifest.verify" and "index.digest.prov" in str(caught.value)


def test_the_deposit_command_injects_the_chain_verifier(sealed, tmp_path):
    import release_support as rs

    from agentprov.cli.deposit import verify_chain

    result = verify_chain(sealed)
    assert (result.level, result.ok) == ("chain", True)
    report = rs.build([sealed], tmp_path / "deposit", verify=verify_chain)
    assert report.corpora[0]["verification"] == {"level": "chain"}
    assert not any("not available" in n for n in report.notices)
    copy = vs.first_file(sealed, "prov")
    copy.write_bytes(copy.read_bytes() + b" ")
    vs.regenerate_checksums(sealed)
    bad = verify_chain(sealed)
    assert not bad.ok and "index.digest.prov" in bad.detail


def test_a_report_serialises(sealed):
    report = verify_corpus(sealed, level="chain")
    document: dict[str, Any] = report.to_json()
    assert document["passed"] and document["ok"] and document["level"] == "chain" and document["mode"] == "tree"
    assert report.exit_code == 0 and UNVERIFIED == "unverified"


# ------------------------------------------------------------------------------------------------ unreadable PROV member
def test_a_symlinked_prov_file_is_a_finding_not_an_exception(sealed, tmp_path):
    """A PROV file the reader refuses to open (here a link, never followed) is a ``corpus.read.prov`` finding, like an
    unreadable AER or SEM file, and every other check still runs (ultra seal-release #4)."""
    prov = vs.first_file(sealed, "prov")
    copy = tmp_path / "outside.json"
    copy.write_bytes(prov.read_bytes())
    prov.unlink()
    prov.symlink_to(copy)
    report = verify_corpus(sealed, level="chain")
    assert report.codes().get("corpus.read.prov") == 1 and report.exit_code == 1
    assert report.counters["executions_checked"] == 3


def test_a_prov_member_over_the_limits_is_a_finding_not_an_exception(sealed, monkeypatch):
    """The read itself fails (an archive member over the limits, a corrupt stream): a finding, not a raised error."""
    from agentprov.corpus.reader import CorpusReader, CorpusReadError

    label = vs.first_file(sealed, "prov").relative_to(sealed).as_posix()
    original = CorpusReader.read_bytes

    def read_bytes(self: CorpusReader, name: str, *, stored: bool = False) -> bytes:
        if name == label:
            raise CorpusReadError(f"{name}: cannot be read (ingest.limit.bytes)", code="corpus.read.unreadable")
        return original(self, name, stored=stored)

    monkeypatch.setattr(CorpusReader, "read_bytes", read_bytes)
    report = verify_corpus(sealed, level="chain")
    assert report.codes() == {"corpus.read.prov": 1}
    assert next(f for f in report.findings if f.code == "corpus.read.prov").detail.endswith("(corpus.read.unreadable)")


def test_verify_parses_prov_under_the_prov_document_limit(working, monkeypatch):
    """D-935 follow-up: ``verify --level chain`` parses each PROV file under the PROV-document limit (256 MiB), not the
    64 MiB raw-input limit, so a long run's large PROV-JSON (DTap: 68-76 MB) is not reported as prov.invalid."""
    import agentprov.ingest.loaders as loaders
    from agentprov.ingest.limits import PROV_DOCUMENT_JSON_BYTES

    seen: list[int] = []
    original = loaders.strict_json_loads

    def spy(data: Any, limits: Any = None, **kw: Any) -> Any:
        if limits is not None and isinstance(data, bytes) and data[:1] == b"{" and b'"bundle"' in data[:4096]:
            seen.append(limits.max_json_bytes)
        return original(data, limits, **kw) if limits is not None else original(data, **kw)

    monkeypatch.setattr(loaders, "strict_json_loads", spy)
    report = verify_corpus(working, level="chain")
    assert seen and set(seen) == {PROV_DOCUMENT_JSON_BYTES}
    assert "prov.invalid" not in report.codes()


def test_render_reads_prov_under_the_prov_document_limit(tmp_path):
    from agentprov.ingest.limits import MIB
    from agentprov.render.source import CorpusSource, read_prov_document

    doc = b'{"entity": "' + b"x" * (64 * MIB + 1) + b'"}'
    (tmp_path / "big.prov.json").write_bytes(doc)
    source = CorpusSource(root=tmp_path, corpus_id=None, state="working", rows=(), used_partial=False)
    assert len(read_prov_document(source, "big.prov.json")["entity"]) == 64 * MIB + 1
