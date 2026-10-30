"""``release.toml`` (H.10.2), the release-scan check (G.9.4) and related identifiers (H.10.5)."""

from __future__ import annotations

import pytest

from agentprov.release.metadata import (
    GITLEAKS_CONFIG_SHA256,
    GITLEAKS_VERSION,
    PATH_SCAN_TOOL,
    PATH_SCAN_VERSION,
    RELEASE_SCAN_FORMAT,
    DepositMetadataError,
    Related,
    ScanRefusedError,
    check_release_scan,
    corpus_related,
    merge_related,
    parse_release_toml,
)

GOOD = b'''title = "AgentPROV corpora"
description_preamble = "Execution records."
keywords = ["provenance", "agent security"]
concept_doi = "10.5281/zenodo.1234567"

[[creators]]
name = "A. Author"
orcid = "0000-0002-1825-0097"
affiliation = "A University"

[[creators]]
name = "B. Author"

[[related]]
identifier = "10.5281/zenodo.20692312"
scheme = "DOI"
relation = "IsNewVersionOf"
'''


def test_a_complete_release_toml_parses():
    meta = parse_release_toml(GOOD)
    assert meta.title == "AgentPROV corpora" and meta.concept_doi == "10.5281/zenodo.1234567"
    assert [c.name for c in meta.creators] == ["A. Author", "B. Author"] and meta.creators[0].orcid == "0000-0002-1825-0097"
    assert meta.related == (Related("IsNewVersionOf", "DOI", "10.5281/zenodo.20692312"),)
    assert meta.version is None


@pytest.mark.parametrize("bad", [
    b"not toml [",
    b'title = "t"\nkeywords = []\ndescription_preamble = ""\n',  # no creators
    b'title = "t"\nkeywords = []\ndescription_preamble = ""\ncreators = []\n',
    GOOD.replace(b'orcid = "0000-0002-1825-0097"', b'orcid = "1234"'),
    GOOD.replace(b'concept_doi = "10.5281/zenodo.1234567"', b'concept_doi = "zenodo:1"'),
    GOOD.replace(b'relation = "IsNewVersionOf"', b'relation = "IsFriendOf"'),
    GOOD.replace(b'scheme = "DOI"', b'scheme = "Mastodon"'),
    GOOD + b'publisher = "x"\n',  # closed table
    GOOD.replace(b'keywords = ["provenance", "agent security"]', b'keywords = ["a", "a"]'),
    GOOD + b'version = "one"\n',
])  # fmt: skip
def test_malformed_release_toml_is_a_usage_error(bad):
    with pytest.raises(DepositMetadataError) as exc:
        parse_release_toml(bad)
    assert exc.value.exit_code == 2


_GITLEAKS = {"name": "gitleaks", "version": GITLEAKS_VERSION, "config_sha256": GITLEAKS_CONFIG_SHA256}
_PATH_SCAN = {"name": PATH_SCAN_TOOL, "version": PATH_SCAN_VERSION}


def _scan(findings, digest="sha256:" + "a" * 64, tools=None):
    return {"findings": findings, "format": RELEASE_SCAN_FORMAT,
            "target": {"corpus_id": "c", "kind": "corpus", "root_digest": digest},
            "tools": tools if tools is not None else [_GITLEAKS, _PATH_SCAN]}  # fmt: skip


def _check(doc, withheld=()):
    return check_release_scan(doc, corpus_id="c", root_digest="sha256:" + "a" * 64, withheld_fingerprints=withheld,
                              scan_sha256="sha256:" + "0" * 64)


def test_a_real_finding_is_admitted_only_when_withheld():
    real = [{"fingerprint": "raw/objects/ab/x.json:aws-access-token:4", "triage": "real", "reason": "a leaked key"}]
    with pytest.raises(ScanRefusedError) as exc:
        _check(_scan(real))
    assert exc.value.code == "release.refused.scan_real"
    summary = _check(_scan(real), withheld=["raw/objects/ab/x.json:aws-access-token:4"])
    assert summary.by_triage == {"real": 1}
    assert summary.tools == (("agentprov-path-scan", "6"), ("gitleaks", "8.30.1"))


def test_pinned_account_is_admitted_only_for_an_account_path_in_raw():
    """D-604 item 7: a third-party account in a raw object ships as pinned; ``pinned-account`` anywhere else (a derived
    record, another rule) is refused, since a derived record must be redacted instead."""
    ok = [{"fingerprint": "raw/objects/ab/x.json:account-path:3", "path": "raw/objects/ab/x.json", "rule": "account-path",
           "triage": "pinned-account", "reason": "pinned at the source (D-186 (c))"},
          {"fingerprint": "raw/objects/cd/y.zip#2:account-path:1", "path": "raw/objects/cd/y.zip#2", "rule": "account-path",
           "triage": "pinned-account", "reason": "an archive member, pinned"}]  # fmt: skip
    assert _check(_scan(ok)).by_triage == {"pinned-account": 2}
    for path, rule in (("aer/00/x.aer.jsonl", "account-path"), ("raw/objects/ab/x.json", "github-pat"),
                       ("prov/00/x.json", "account-path")):  # fmt: skip
        bad = [{"fingerprint": f"{path}:{rule}:3", "path": path, "rule": rule, "triage": "pinned-account", "reason": "x"}]
        with pytest.raises(ScanRefusedError) as exc:
            _check(_scan(bad))
        assert exc.value.code == "release.refused.scan_pinned"


@pytest.mark.parametrize("doc", [
    {"format": "other"},
    _scan([], tools=[]),
    _scan([], tools=[{"name": "trufflehog", "version": "3"}]),  # gitleaks is the one scanner of v0.1
    _scan([{"triage": "false-positive", "reason": "x"}]),  # no fingerprint
    {**_scan([]), "target": {"corpus_id": "other", "kind": "corpus", "root_digest": "sha256:" + "a" * 64}},
])  # fmt: skip
def test_malformed_scans_are_refused(doc):
    with pytest.raises(ScanRefusedError):
        _check(doc)


@pytest.mark.parametrize("tools", [
    [{**_GITLEAKS, "version": "8.18.4"}, _PATH_SCAN],  # another gitleaks: other default rules
    [{k: v for k, v in _GITLEAKS.items() if k != "config_sha256"}, _PATH_SCAN],  # the rule set is not recorded
    [{**_GITLEAKS, "config_sha256": "0" * 64}, _PATH_SCAN],  # another rule set
    [_GITLEAKS],  # no path scan: no home path, account path or secret-shape search
    [_GITLEAKS, {**_PATH_SCAN, "version": "3"}],  # an older path scan: no D-600 secret shapes
    [_GITLEAKS, _PATH_SCAN, {**_GITLEAKS, "version": "8.18.4"}],  # gitleaks twice
])  # fmt: skip
def test_a_scan_from_an_unpinned_scanner_is_refused(tools):
    """G.9.4: the scan must come from the pinned gitleaks with the committed rule set and from the current path scan
    (ultra seal-release #2); a document that only names gitleaks is not enough."""
    assert _check(_scan([])).tools == (("agentprov-path-scan", PATH_SCAN_VERSION), ("gitleaks", GITLEAKS_VERSION))
    with pytest.raises(ScanRefusedError) as exc:
        _check(_scan([], tools=tools))
    assert exc.value.code == "release.refused.scan_tools" and exc.value.exit_code == 4


def test_related_identifiers_come_only_from_the_corpus():
    manifest = {"corpus_id": "c", "licences": {"attribution": ["Cite arXiv:2406.13352 and the survey"]},
                "sources": [{"source_id": "s", "snapshots": [{"snapshot_id": "head",
                    "origin": {"kind": "git", "repo": "https://github.com/o/r", "commit": "a" * 40},
                    "alt_origins": [{"kind": "zenodo", "doi": "10.5281/zenodo.22135957"}, {"kind": "zenodo"}]}]}]}  # fmt: skip
    related = corpus_related(manifest, {"s": {"concept_doi": "10.5281/zenodo.22135956", "paper": "none found"}})
    assert {(r.relation, r.scheme, r.identifier) for r in related} == {
        ("IsDerivedFrom", "DOI", "10.5281/zenodo.22135956"),
        ("IsDerivedFrom", "DOI", "10.5281/zenodo.22135957"),
        ("IsDerivedFrom", "URL", "https://github.com/o/r/tree/" + "a" * 40),
        ("References", "arXiv", "arXiv:2406.13352"),
    }
    assert corpus_related({"corpus_id": "c"}, {}) == []  # nothing recorded: nothing invented
    merged = merge_related([related, [Related("References", "arXiv", "arXiv:2406.13352", "release.toml")]])
    assert len(merged) == 4


def test_a_context_trees_pinned_origin_is_a_related_identifier_d221():
    manifest = {"corpus_id": "c", "sources": [{"source_id": "s", "snapshots": [{"snapshot_id": "head",
        "origin": {"kind": "git", "repo": "https://github.com/o/r", "commit": "a" * 40}, "alt_origins": [],
        "context": [{"role": "tasks", "origin": {"kind": "git", "repo": "https://github.com/o/tasks", "commit": "b" * 40}},
                    {"role": "supp", "origin": {"kind": "zenodo", "doi": "10.5281/zenodo.9", "file": "supp.zip"}}]}]}]}  # fmt: skip
    related = {(r.relation, r.scheme, r.identifier) for r in corpus_related(manifest, {})}
    assert ("IsDerivedFrom", "URL", "https://github.com/o/tasks/tree/" + "b" * 40) in related
    assert ("IsDerivedFrom", "DOI", "10.5281/zenodo.9") in related
