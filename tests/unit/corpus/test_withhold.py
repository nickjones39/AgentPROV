"""Withholding at sealing (:mod:`agentprov.corpus.withhold`; HL H.4.1, H.4.5; G.9.5, G.9.6; D-230..D-236).

Synthetic, in-memory corpora only (rows, origins, members and file bytes built here): the policy parser and its bounded
pattern grammar, the chunked scanner (matches across a chunk boundary; only rule ids leave it), and every cause of the
planner: purge tombstones, snapshot raw policy ``withhold`` (single and several snapshots; *withhold wins*), profile rules
with ``executions`` and ``object`` scope, a hit in a derived file, the container closure, the merge of several causes, the
register entries it adds, and its refusals (an unexplained ``release.withheld``; an object without an origin). The fake
canary values are assembled at run time and never printed; assertions compare booleans, never the values.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import pytest

from agentprov.corpus import withhold as wh
from agentprov.corpus.dedup import source_key
from agentprov.corpus.index import IndexRow, RawRef
from agentprov.corpus.layout import CorpusLayout
from agentprov.corpus.purge import Tombstone
from agentprov.corpus.register import RegisterEntry
from agentprov.corpus.withheld import encode_withheld
from agentprov.raw.members import MemberRow
from agentprov.raw.origins import Origin, OriginRow

#: A fake canary credential, assembled at run time (no source file holds it whole); never printed.
CANARY = "AKIA" + "FAKE" + "CANARY" + "0000000042"
LAYOUT = CorpusLayout("/nonexistent")
C1, C2 = "1" * 40, "2" * 40
PROFILE = {"id": "tst-profile", "version": 1, "sha256": "sha256:" + "9" * 64}


def _hex(n: int) -> str:
    return f"{n:064x}"


O1, O2, O3, CONTAINER, MEMBER = (_hex(n) for n in (1, 2, 3, 4, 5))
EX1, EX2, EX3 = ("ex_" + c * 26 for c in "abc")


def _git(commit: str, path: str = "runs/x.json") -> Origin:
    return Origin.from_json({"blob_sha1": "c" * 40, "commit": commit, "kind": "git", "path": path,
                             "repo": "https://github.com/o/r"})


def _row(ex: str, *shas: str, snapshots: Sequence[str] = ("s1",)) -> IndexRow:
    raw = (RawRef(shas[0], "primary", True), *(RawRef(s, "supporting", True) for s in shas[1:]))
    return IndexRow(ex=ex, mode="import", unit="agent_execution", source_id="tst", snapshot_ids=tuple(snapshots),
                    source_key=source_key(shas[0], {"p": ""}), raw=raw, n_origins=1, adapter="tst.adapter@0.1.0",
                    profile="tst-profile@1", aer_digest="ab" * 32, aer_path=LAYOUT.aer_relpath(ex),
                    stages={"raw": "ok", "aer": "ok"}, status="ok", completeness="unverifiable", execution_observed=True,
                    issues=(), attempt=None)  # fmt: skip


def _label(sha: str) -> str:
    return f"raw/objects/{sha[:2]}/{sha}.json"


class Corpus:
    """A synthetic working corpus: rows, origins, members, stored bytes and derived-file bytes."""

    def __init__(self, rows: Sequence[IndexRow], *, origins: Mapping[str, Sequence[Origin]] | None = None,
                 stored: Mapping[str, bytes] | None = None, derived: Mapping[str, bytes] | None = None,
                 members: Sequence[MemberRow] = (), register: Sequence[RegisterEntry] = (),
                 tombstones: Sequence[Tombstone] = (), snapshots: Mapping[str, tuple[str, Any]] | None = None,
                 artefacts: Mapping[str, Sequence[Mapping[str, Any]]] | None = None, chunk: int = 1 << 20) -> None:
        self.rows = list(rows)
        cited = {ref.sha256 for row in rows for ref in row.raw}
        self.stored = dict(stored if stored is not None else {sha: b'{"clean": true}' for sha in cited})
        default = {sha: [_git(C1)] for sha in cited | set(self.stored)}
        chosen = default if origins is None else origins
        self.origins = [OriginRow(sha, o) for sha, group in sorted(chosen.items()) for o in group]
        self.derived = dict(derived or {})
        self.members, self.register, self.tombstones = list(members), list(register), list(tombstones)
        self.snapshots = snapshots or {"s1": ("include", {"commit": C1, "kind": "git"})}
        self.artefacts = dict(artefacts or {})
        self.chunk = chunk

    def _bytes(self, label: str) -> bytes:
        if label in self.derived:
            return self.derived[label]
        return self.stored[label.rsplit("/", 1)[-1].split(".", 1)[0]]

    def stream(self, label: str) -> Iterator[bytes]:
        data = self._bytes(label)
        for i in range(0, len(data), self.chunk):
            yield data[i:i + self.chunk]

    def plan(self, policy: wh.WithholdPolicy | None = None) -> wh.WithholdPlan:
        return wh.plan_withholding(
            rows=self.rows, register=self.register, members=self.members, origins=self.origins,
            present={sha: (_label(sha), len(data)) for sha, data in self.stored.items()}, tombstones=self.tombstones,
            snapshots=self.snapshots, stream=self.stream,
            derived=lambda row: [label for label in (row.aer_path,) if label in self.derived],
            artefacts=lambda row: self.artefacts.get(row.ex, ()), policy=policy, decided_on="2026-10-12",
        )  # fmt: skip


def _policy(text: str) -> wh.WithholdPolicy:
    policy = wh.parse_policy(tomllib.loads(text), profile_id=PROFILE["id"], profile_version=PROFILE["version"],
                             profile_sha256=PROFILE["sha256"])
    assert policy is not None
    return policy


CANARY_POLICY = '''
[withhold]
reason = "secret"
public_note = "planted canary credential (benchmark design); value never recorded"
scan_rules = ["aws-access-token"]
[[withhold.rules]]
id = "canary-key"
pattern = "AKIA[0-9A-Z]{20}"
'''


# ================================================================================================ the policy
def test_a_profile_without_a_withhold_table_has_no_policy():
    assert wh.parse_policy({"profile": {}}, profile_id="p", profile_version=1, profile_sha256=PROFILE["sha256"]) is None


def test_a_valid_policy_parses_and_records_ids_kinds_and_scopes_only():
    policy = _policy(CANARY_POLICY + '''
[[withhold.rules]]
id = "token-marker"
marker = "(token:"
scope = "object"
reason = "personal_data"
public_note = "attacker token marker"
''')
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [
        ("canary-key", "pattern", "executions", "secret"), ("token-marker", "marker", "object", "personal_data")]
    assert policy.width == 24 and policy.ref == "tst-profile@1"
    record = policy.record().to_json()
    assert record == {"profile": {"id": "tst-profile", "sha256": PROFILE["sha256"], "version": 1},
                      "rules": [{"id": "canary-key", "kind": "pattern", "scope": "executions"},
                                {"id": "token-marker", "kind": "marker", "scope": "object"}],
                      "scan_rules": ["aws-access-token"]}


@pytest.mark.parametrize("table", [
    '[withhold]\nreason = "secret"\npublic_note = "n"\nrules = []',
    '[withhold]\nreason = "dangerous"\npublic_note = "n"\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"',
    '[withhold]\nreason = "secret"\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"',
    '[withhold]\nreason = "secret"\npublic_note = "two\\nlines"\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\nextra = 1\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\n[[withhold.rules]]\nid = "a"\nmarker = "MRK"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\n[[withhold.rules]]\nid = "a"\nmarker = "MA\\nRK"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"\npattern = "x"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\n[[withhold.rules]]\nid = "A!"\nmarker = "MARK"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"\nscope = "all"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"\n'
    '[[withhold.rules]]\nid = "a"\nmarker = "MORE"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\nscan_rules = ["no spaces"]\n[[withhold.rules]]\nid = "a"\nmarker = "MARK"',
    '[withhold]\nreason = "secret"\npublic_note = "n"\n[[withhold.rules]]\nid = "a"\npattern = "(a)+"',
])  # fmt: skip
def test_a_malformed_policy_is_refused_with_exit_4(table):
    with pytest.raises(wh.WithholdError) as refused:
        wh.parse_policy(tomllib.loads(table), profile_id="p", profile_version=1, profile_sha256=PROFILE["sha256"])
    assert refused.value.code == "corpus.withhold.policy" and refused.value.exit_code == 4


@pytest.mark.parametrize(("pattern", "width"), [
    ("AKIA[0-9A-Z]{16}", 20), ("sk-[a-f0-9]{8,32}", 35), (r"\d{4}", 4), ("x?y", 2), (r"\-\[x\]", 4),
    ("[^a-z]{2}", 2), ("[]a]b", 2),
])  # fmt: skip
def test_the_pattern_grammar_computes_the_longest_match(pattern, width):
    regex, computed = wh.compile_pattern(pattern)
    assert computed == width and regex.pattern == pattern.encode()


@pytest.mark.parametrize("pattern", [
    "", "a*", "a+", "(ab)", "a|b", ".", "a{2,}", "a{,3}", "a{300}", "a{0}", r"\1", r"\b", "^a", "a$", "(?=a)", "[a",
    "a{2", "]", "é", "a\tb", r"[\q]", "a" * 257,
])  # fmt: skip
def test_the_pattern_grammar_refuses_unbounded_or_backtracking_constructs(pattern):
    with pytest.raises(wh.WithholdError):
        wh.compile_pattern(pattern)


def test_the_scanner_finds_matches_across_chunk_boundaries_and_returns_rule_ids_only():
    policy = _policy(CANARY_POLICY + '[[withhold.rules]]\nid = "marker"\nmarker = "(token:"\n')
    data = b"x" * 100 + b"prefix " + CANARY.encode() + b"0000 and (token: here"
    for size in (1, 3, 7, 50, 1 << 20):
        chunks = [data[i:i + size] for i in range(0, len(data), size)]
        assert wh.scan_chunks(chunks, policy.rules) == frozenset({"canary-key", "marker"}), size
    assert wh.scan_chunks([b"clean" * 1000], policy.rules) == frozenset()
    assert wh.scan_chunks([b"AKIA" + b"lowercase" * 3], policy.rules) == frozenset()


def test_the_scanner_closes_an_iterator_it_stops_early():
    closed = []

    def gen() -> Iterator[bytes]:
        try:
            yield b"MARKER"
            yield b"more"
        finally:
            closed.append(True)

    rule = wh.Rule("m", "marker", "executions", "secret", "n", needle=b"MARKER", width=6)
    assert wh.scan_chunks(gen(), [rule]) == {"m"} and closed == [True]


# ================================================================================================ the planner
def test_nothing_to_withhold_is_an_empty_plan():
    plan = Corpus([_row(EX1, O1)]).plan(_policy(CANARY_POLICY))
    assert plan.empty and plan.document is None and plan.objects == frozenset() and plan.register == ()


def test_a_tombstone_withholds_its_object_and_the_executions_that_cite_it():
    corpus = Corpus([_row(EX1, O1), _row(EX2, O2)], stored={O2: b"{}"}, origins={O1: [_git(C1)], O2: [_git(C1)]},
                    tombstones=[Tombstone(O1, "secret", "2026-10-01")],
                    artefacts={EX1: [{"sha256": O1, "bytes": 77, "media": "application/json"}]})
    plan = corpus.plan()
    assert plan.objects == {O1} and plan.executions == {EX1} and plan.present == {}
    assert plan.document is not None
    (entry,) = plan.document.entries
    assert (entry.reason, entry.basis, entry.decided_on, entry.affected_executions) == ("secret", "purge", "2026-10-01",
                                                                                         (EX1,))
    assert (entry.bytes, entry.media_type, entry.finding) == (77, "application/json", None)
    assert entry.origins == (_git(C1).to_json(),)
    assert [(e.subject, e.code, e.disposition, e.detail) for e in plan.register] == [
        ({"ex": EX1}, "release.withheld", "withheld", "a cited raw object was purged (G.9.6)")]
    (execution,) = plan.document.executions
    assert execution.ex == EX1 and execution.snapshot_ids == ("s1",) and execution.digests == {"aer": "sha256:" + "ab" * 32}


def test_a_purge_register_entry_is_kept_not_duplicated():
    existing = RegisterEntry({"ex": EX1}, "release.withheld", "info", "package", "withheld",
                             detail="a cited raw object was purged (G.9.6)")
    corpus = Corpus([_row(EX1, O1)], stored={}, origins={O1: [_git(C1)]}, register=[existing],
                    tombstones=[Tombstone(O1, "secret", "2026-10-01")])
    plan = corpus.plan()
    assert plan.executions == {EX1} and plan.register == ()


def test_a_release_withheld_entry_that_no_cause_explains_refuses_the_seal():
    stray = RegisterEntry({"ex": EX1}, "release.withheld", "info", "package", "withheld", detail="x")
    with pytest.raises(wh.WithholdError) as refused:
        Corpus([_row(EX1, O1)], register=[stray]).plan()
    assert refused.value.code == "corpus.withhold.unexplained" and refused.value.exit_code == 4


def test_a_withheld_object_without_an_origin_refuses_the_seal():
    corpus = Corpus([_row(EX1, O1)], stored={}, origins={}, tombstones=[Tombstone(O1, "secret", "2026-10-01")])
    with pytest.raises(wh.WithholdError) as refused:
        corpus.plan()
    assert refused.value.code == "corpus.withhold.no_origin"


def test_a_single_withhold_snapshot_withholds_everything():
    corpus = Corpus([_row(EX1, O1), _row(EX2, O2, O3)],
                    snapshots={"s1": ("withhold", {"commit": C1, "kind": "git"})})
    plan = corpus.plan()
    assert plan.objects == {O1, O2, O3} and plan.executions == {EX1, EX2}
    assert plan.present == {sha: _label(sha) for sha in (O1, O2, O3)}
    assert plan.document is not None and {(e.reason, e.basis) for e in plan.document.entries} == {("licence", "raw_policy")}
    assert plan.document.entries[0].public_note == "snapshot s1 has raw policy withhold (H.4.1)"
    assert {e.detail for e in plan.register} == {"the snapshot's raw policy is withhold (H.4.1)"}


def test_with_several_snapshots_withhold_wins_for_shared_rows_and_objects():
    corpus = Corpus(
        [_row(EX1, O1, snapshots=("s1",)), _row(EX2, O2, snapshots=("s2",)), _row(EX3, O3, snapshots=("s1", "s2"))],
        origins={O1: [_git(C1)], O2: [_git(C2)], O3: [_git(C1), _git(C2)], CONTAINER: [_git(C2, "a.zip")]},
        stored={O1: b"{}", O2: b"{}", O3: b"{}", CONTAINER: b"PK"},
        snapshots={"s1": ("include", {"commit": C1, "kind": "git"}), "s2": ("withhold", {"commit": C2, "kind": "git"})},
    )
    plan = corpus.plan()
    assert plan.executions == {EX2, EX3}
    assert plan.objects == {O2, O3, CONTAINER}  # the uncited container's pin is the withhold snapshot's


def _canary_corpus(scope: str) -> tuple[Corpus, wh.WithholdPolicy]:
    policy = _policy(CANARY_POLICY.replace('pattern = "AKIA[0-9A-Z]{20}"', f'pattern = "AKIA[0-9A-Z]{{20}}"\nscope = "{scope}"'))
    corpus = Corpus([_row(EX1, O1, O2), _row(EX2, O3, O2), _row(EX3, O3)],
                    stored={O1: b'{"ok": 1}', O2: b'{"env": "' + CANARY.encode() + b'"}', O3: b"{}"})
    return corpus, policy


def test_a_profile_rule_with_executions_scope_withholds_the_object_and_every_citing_execution():
    corpus, policy = _canary_corpus("executions")
    plan = corpus.plan(policy)
    assert plan.objects == {O2} and plan.executions == {EX1, EX2}
    assert plan.document is not None
    (entry,) = plan.document.entries
    assert (entry.reason, entry.basis, entry.public_note) == (
        "secret", "profile_rule", "planted canary credential (benchmark design); value never recorded")
    assert entry.finding is not None and entry.finding.to_json() == {
        "detector": "agentprov-withhold/1", "fingerprint": f"{_label(O2)}:canary-key", "rule": "tst-profile@1:canary-key"}
    assert plan.document.policies[0].profile_id == "tst-profile"
    data = encode_withheld(plan.document)
    leaked = CANARY.encode() in data or CANARY[:8].encode() in data
    assert leaked is False  # the ledger holds rule ids and digests, never the value


def test_a_profile_rule_with_object_scope_withholds_only_the_object():
    corpus, policy = _canary_corpus("object")
    plan = corpus.plan(policy)
    assert plan.objects == {O2} and plan.executions == frozenset() and plan.register == ()
    assert plan.document is not None and plan.document.entries[0].affected_executions == ()
    assert plan.document.executions == ()


def test_a_hit_in_a_derived_file_withholds_the_execution_and_its_primary_object():
    corpus, policy = _canary_corpus("object")
    corpus.stored[O2] = b"{}"
    corpus.derived[LAYOUT.aer_relpath(EX3)] = b'{"text": "' + CANARY.encode() + b'"}'
    plan = corpus.plan(policy)
    assert plan.executions == {EX3} and plan.objects == {O3}
    assert plan.document is not None
    (entry,) = plan.document.entries
    assert entry.affected_executions == (EX3,) and entry.finding is not None
    assert entry.finding.fingerprint == f"{LAYOUT.aer_relpath(EX3)}:canary-key"


def test_a_container_holding_a_withheld_member_is_withheld_at_object_level():
    member = MemberRow(CONTAINER, "cd" * 32, "run.json", 8, "0" * 8, 10, MEMBER, "selected")
    corpus = Corpus([_row(EX1, MEMBER), _row(EX2, O1)],
                    origins={CONTAINER: [_git(C1, "a.zip")], O1: [_git(C1)],
                             MEMBER: [Origin.from_json({"container": CONTAINER, "crc32": "0" * 8, "kind": "member",
                                                        "label": "run.json", "method": 8, "size": 10})]},
                    stored={CONTAINER: b"PK", MEMBER: b"{}", O1: b"{}"}, members=[member],
                    tombstones=[Tombstone(MEMBER, "personal_data", "2026-10-02")])
    corpus.stored.pop(MEMBER)
    plan = corpus.plan()
    assert plan.objects == {MEMBER, CONTAINER} and plan.executions == {EX1} and plan.present == {CONTAINER: _label(CONTAINER)}
    assert plan.document is not None
    entries = {e.sha256: e for e in plan.document.entries}
    assert (entries[CONTAINER].reason, entries[CONTAINER].basis, entries[CONTAINER].affected_executions) == (
        "personal_data", "container", ())
    assert entries[MEMBER].bytes == 10  # the size raw/members.jsonl kept for the purged member


def test_an_execution_withheld_through_an_archive_upgraded_by_its_member_takes_the_basis_that_withheld_it():
    """Ultrareview raw-withhold #1: an execution cites a stored archive directly, the archive is withheld for a cause
    that carries the execution (raw policy, licence), and a selected member of it is withheld for a higher-priority
    reason (a secret canary). The archive's entry is then reason secret, basis container, with the execution affected;
    the execution's register detail must come from the cause that withheld it (raw_policy), never from the container
    closure, which withholds no execution (H.4.5 item 3). It used to raise KeyError('container')."""
    member = MemberRow(CONTAINER, "cd" * 32, "run.json", 8, "0" * 8, 10, MEMBER, "selected")
    corpus = Corpus([_row(EX1, CONTAINER, snapshots=("s2",)), _row(EX2, O1, snapshots=("s1",))],
                    origins={CONTAINER: [_git(C2, "a.zip")], O1: [_git(C1)],
                             MEMBER: [Origin.from_json({"container": CONTAINER, "crc32": "0" * 8, "kind": "member",
                                                        "label": "run.json", "method": 8, "size": 10})]},
                    stored={CONTAINER: b"PK", MEMBER: b'{"k": "' + CANARY.encode() + b'"}', O1: b"{}"},
                    members=[member],
                    snapshots={"s1": ("include", {"commit": C1, "kind": "git"}),
                               "s2": ("withhold", {"commit": C2, "kind": "git"})})
    plan = corpus.plan(_policy(CANARY_POLICY))
    assert plan.executions == {EX1} and plan.objects == {CONTAINER, MEMBER}
    assert plan.document is not None
    entries = {e.sha256: e for e in plan.document.entries}
    assert (entries[CONTAINER].reason, entries[CONTAINER].basis, entries[CONTAINER].affected_executions) == (
        "secret", "container", (EX1,))
    assert [(e.subject, e.detail) for e in plan.register] == [
        ({"ex": EX1}, "the snapshot's raw policy is withhold (H.4.1)")]
    encode_withheld(plan.document)  # a valid ledger (encode validates first)


def test_several_causes_merge_into_one_entry_by_priority():
    corpus = Corpus([_row(EX1, O1)], stored={}, origins={O1: [_git(C1)]},
                    tombstones=[Tombstone(O1, "secret", "2026-10-03")],
                    snapshots={"s1": ("withhold", {"commit": C1, "kind": "git"})})
    plan = corpus.plan()
    assert plan.document is not None
    (entry,) = plan.document.entries
    assert (entry.reason, entry.basis, entry.decided_on) == ("secret", "purge", "2026-10-03")
    assert entry.affected_executions == (EX1,)


def test_rescan_never_scans_package_copies_or_the_checksums():
    policy = _policy(CANARY_POLICY + '[[withhold.rules]]\nid = "marker"\nmarker = "(token:"\n')
    files = {"rules/tst-profile.profile.toml": b'marker = "(token:"', "schemas/withheld-0.1.schema.json": b"(token:",
             "checksums.sha256": b"(token:", "DATASHEET.md": b"clean", "aer/aa/x.aer.jsonl": b"(token: here"}
    assert wh.released_labels(files) == ["DATASHEET.md", "aer/aa/x.aer.jsonl"]
    assert wh.rescan(files, lambda label: iter([files[label]]), policy) == [("aer/aa/x.aer.jsonl", "marker")]


# ================================================================================================ the profile loader
def test_a_source_profile_with_a_withhold_table_parses_and_one_without_is_unchanged():
    """``adapters/profiles.py`` admits the ``[withhold]`` table (D-234; it stays unvalidated there, adapters/ being below
    corpus/), and :func:`withhold.policy_of_profile` reads it from the real profile bytes, with no injection."""
    import hashlib
    from importlib import resources

    from agentprov.adapters.profiles import load_profile, parse_profile

    shipped = resources.files("agentprov").joinpath("adapters", "agentdojo", "profiles",
                                                   "agentdojo-upstream.profile.toml").read_bytes()
    plain = parse_profile(shipped)
    assert plain.sha256 == load_profile("agentdojo-upstream").sha256 and "withhold" not in plain.data
    assert wh.policy_of_profile(shipped, profile_id="agentdojo-upstream", profile_version=1) is None
    declared = shipped + CANARY_POLICY.encode()
    profile = parse_profile(declared)
    assert profile.data["withhold"]["reason"] == "secret" and profile.sha256 == hashlib.sha256(declared).hexdigest()
    policy = wh.policy_of_profile(declared, profile_id=profile.id, profile_version=profile.version)
    assert policy is not None and [r.id for r in policy.rules] == ["canary-key"]
    assert policy.profile_sha256 == "sha256:" + profile.sha256


# ================================================================================================ issue rules (D-311)
#: A synthetic namespace and issue code: no catalogue declares them, so the tests inject the lookup.
FLAG = "toyfam.canary_flagged"
ISSUE_POLICY = f'''
[withhold]
reason = "secret"
public_note = "the source flags a planted canary in this execution; value never recorded"
[[withhold.rules]]
id = "canary-flagged"
issue = "{FLAG}"
[[withhold.rules]]
id = "canary-key"
pattern = "AKIA[0-9A-Z]{{20}}"
scope = "object"
'''


def _declared(code: str) -> bool:
    return code == FLAG


def _flagged(row: IndexRow, *codes: str) -> IndexRow:
    from dataclasses import replace

    return replace(row, issues=tuple(sorted(codes)))


def _issue_entry(ex: str, code: str = "map." + FLAG) -> RegisterEntry:
    return RegisterEntry(subject={"ex": ex}, code=code, severity="warning", stage="map", disposition="sealed",
                         detail="2 canary-flagged event(s)")


def test_an_issue_rule_parses_in_the_exact_form_phase_10m_declares():
    table = {"withhold": {"reason": "secret", "public_note": "n",
                          "rules": [{"id": "canary-flagged", "issue": "mcphunt.canary_flagged"}]}}
    policy = wh.parse_policy(table, profile_id="mcphunt", profile_version=1, profile_sha256="sha256:" + "0" * 64)
    assert policy is not None and len(policy.rules) == 1
    (rule,) = policy.rules
    assert (rule.kind, rule.scope, rule.code, rule.register_code) == ("issue", "executions", "mcphunt.canary_flagged",
                                                                      "map.mcphunt.canary_flagged")
    assert policy.issue_rules == policy.rules and policy.byte_rules == () and policy.width == 1
    assert policy.record().rules == (("canary-flagged", "issue", "executions"),)


@pytest.mark.parametrize("rule", [
    {"id": "r", "issue": FLAG, "scope": "executions"},  # an issue rule has no scope
    {"id": "r", "issue": FLAG, "scope": "object"},
    {"id": "r", "issue": FLAG, "marker": "CANARY-"},  # exactly one selector
    {"id": "r", "issue": FLAG, "pattern": "AKIA[0-9]{4}"},
    {"id": "r", "issue": "canary_flagged"},  # not <namespace>.<code>
    {"id": "r", "issue": "map.toyfam.canary_flagged"},  # the register form is not the seal code
    {"id": "r", "issue": "Toyfam.Canary"},
    {"id": "r", "issue": ""},
    {"id": "r", "issue": 7},
    {"id": "r", "issue": "toyfam." + "x" * 200},
])  # fmt: skip
def test_a_malformed_issue_rule_is_refused(rule):
    table = {"withhold": {"reason": "secret", "public_note": "n", "rules": [rule]}}
    with pytest.raises(wh.WithholdError) as refused:
        wh.parse_policy(table, profile_id="p", profile_version=1, profile_sha256="sha256:" + "0" * 64)
    assert refused.value.code == "corpus.withhold.policy" and refused.value.exit_code == 4


def test_two_rules_naming_one_issue_code_are_refused():
    table = {"withhold": {"reason": "secret", "public_note": "n",
                          "rules": [{"id": "a", "issue": FLAG}, {"id": "b", "issue": FLAG}]}}
    with pytest.raises(wh.WithholdError, match="one rule"):
        wh.parse_policy(table, profile_id="p", profile_version=1, profile_sha256="sha256:" + "0" * 64)


def test_an_unknown_issue_code_is_refused_at_policy_parse():
    text = ISSUE_POLICY.replace(FLAG, "toyfam.no_such_code")
    with pytest.raises(wh.WithholdError, match="not declared") as refused:
        wh.parse_policy(tomllib.loads(text), profile_id="p", profile_version=1, profile_sha256="sha256:" + "0" * 64,
                        issue_declared=_declared)
    assert refused.value.code == "corpus.withhold.policy"
    policy = wh.parse_policy(tomllib.loads(ISSUE_POLICY), profile_id="p", profile_version=1,
                             profile_sha256="sha256:" + "0" * 64, issue_declared=_declared)
    assert policy is not None and [r.id for r in policy.issue_rules] == ["canary-flagged"]


def test_declared_issue_codes_reads_the_catalogue_the_corpus_records():
    from agentprov.aer.rules import load_catalogue

    version = load_catalogue("inspect").version
    declared = wh.declared_issue_codes({"inspect": version})
    assert declared("inspect.sample_limit") and not declared("inspect.no_such_code")
    assert not declared("agentdojo.pipeline_name_mismatch")  # a namespace the corpus does not record declares nothing
    assert not wh.declared_issue_codes({"inspect": version + 1000})("inspect.sample_limit")  # an unshipped version
    assert not wh.declared_issue_codes({"zzz": 1})("zzz.x")


def test_load_policy_checks_issue_codes_against_the_recorded_catalogues():
    from agentprov.aer.rules import load_catalogue

    catalogues = {"inspect": load_catalogue("inspect").version}
    good = ISSUE_POLICY.replace(FLAG, "inspect.sample_limit").encode()
    policy = wh.load_policy(good, profile_id="p", profile_version=1, catalogues=catalogues)
    assert policy is not None and policy.issue_rules[0].code == "inspect.sample_limit"
    with pytest.raises(wh.WithholdError, match="not declared"):
        wh.load_policy(ISSUE_POLICY.encode(), profile_id="p", profile_version=1, catalogues=catalogues)
    assert wh.load_policy(b'[profile]\nid = "p"\n', profile_id="p", profile_version=1, catalogues={}) is None


def test_a_profile_without_an_issue_rule_parses_as_before():
    policy = _policy(CANARY_POLICY)
    assert policy.byte_rules == policy.rules and policy.issue_rules == ()
    assert wh.issue_backstop(policy, [_issue_entry(EX1)], [_row(EX1, O1)]) == []
    corpus = Corpus([_row(EX1, O1), _row(EX2, O2)], stored={O1: b"key " + CANARY.encode(), O2: b"clean"})
    plan = corpus.plan(policy)
    assert plan.document is not None and plan.document.format == "agentprov-withheld/0.1"
    assert plan.document.schema_resource == "withheld-0.1.schema.json"
    assert b'"agentprov-withheld/0.1"' in encode_withheld(plan.document)


def test_an_issue_rule_withholds_flagged_executions_that_share_one_raw_object():
    """MCPHunt's shape (D-289 (c)): one raw object holds several traces; only the flagged ones leave with it."""
    policy = _policy(ISSUE_POLICY)
    rows = [_flagged(_row(EX1, O1), "map." + FLAG), _row(EX2, O1), _row(EX3, O1)]
    corpus = Corpus(rows, stored={O1: b'{"traces": []}'}, register=[_issue_entry(EX1), _issue_entry(EX3)])
    plan = corpus.plan(policy)
    assert plan.executions == {EX1, EX3}  # EX1 by its row's issues, EX3 by its register entry
    assert plan.objects == {O1}
    assert plan.document is not None
    (entry,) = plan.document.entries
    assert (entry.reason, entry.basis, entry.affected_executions) == ("secret", "profile_rule", (EX1, EX3))
    assert entry.finding is not None and entry.finding.rule == "tst-profile@1:canary-flagged"
    assert entry.finding.fingerprint == min(f"{LAYOUT.aer_relpath(ex)}:canary-flagged" for ex in (EX1, EX3))
    assert plan.document.format == "agentprov-withheld/0.2"
    assert plan.document.schema_resource == "withheld-0.2.schema.json"
    assert [p.to_json()["rules"] for p in plan.document.policies] == [[
        {"id": "canary-flagged", "kind": "issue", "scope": "executions"},
        {"id": "canary-key", "kind": "pattern", "scope": "object"}]]
    assert {e.subject["ex"] for e in plan.register} == {EX1, EX3}
    encoded = encode_withheld(plan.document)
    assert b"canary_flagged" not in encoded and FLAG.encode() not in encoded  # rule ids only, never the code or a value


def test_an_issue_rule_and_a_pattern_rule_combine():
    """The pattern rule stays the backstop: an unflagged trace whose derived record holds a canary leaves too."""
    policy = _policy(ISSUE_POLICY)
    rows = [_flagged(_row(EX1, O1), "map." + FLAG), _row(EX2, O2), _row(EX3, O2)]
    corpus = Corpus(rows, stored={O1: b"clean", O2: b"clean"},
                    derived={LAYOUT.aer_relpath(EX2): b"aws " + CANARY.encode()})
    plan = corpus.plan(policy)
    assert plan.executions == {EX1, EX2} and plan.objects == {O1, O2}


def test_an_issue_rule_without_a_flagged_execution_withholds_nothing():
    plan = Corpus([_row(EX1, O1), _flagged(_row(EX2, O2), "map.toyfam.other")]).plan(_policy(ISSUE_POLICY))
    assert plan.empty and plan.executions == frozenset()


def test_the_issue_backstop_finds_a_released_carrier_from_any_record():
    policy = _policy(ISSUE_POLICY)
    released = [_flagged(_row(EX1, O1), "map." + FLAG), _row(EX2, O1), _row(EX3, O1)]
    register = [_issue_entry(EX2), _issue_entry("ex_" + "d" * 26)]  # the last one was withheld: no row
    hits = wh.issue_backstop(policy, register, released, {EX3: [FLAG], EX1: ["toyfam.other"]})
    assert hits == [(EX1, "canary-flagged"), (EX2, "canary-flagged"), (EX3, "canary-flagged")]
    assert wh.issue_backstop(policy, register, released[2:]) == []
    assert wh.issue_carriers(policy, register) == {"canary-flagged": {EX2, "ex_" + "d" * 26}}


def test_rescan_ignores_issue_rules():
    policy = _policy(ISSUE_POLICY.split("[[withhold.rules]]\nid = \"canary-key\"")[0])
    assert policy.byte_rules == ()
    assert wh.rescan(["aer/x.jsonl"], lambda label: iter([FLAG.encode()]), policy) == []


# ================================================================================================ linked objects (D-315)
DESCRIPTOR, PART1, PART2, PART3, SOURCE, BLOB = (_hex(n) for n in (20, 21, 22, 23, 24, 25))
PARTS = (PART1, PART2, PART3)


def _split_corpus(*, hit: str) -> Corpus:
    """One execution whose primary is a member of a split archive (a descriptor and three byte parts); the canary sits
    in the member (``hit == "member"``) or, readable, in one part only (``hit == "part"``: a stored zip)."""
    member = MemberRow(DESCRIPTOR, "cd" * 32, "run.json", 8, "0" * 8, 10, MEMBER, "selected")
    origins = {DESCRIPTOR: [Origin.split("deposit.zip", list(PARTS))],
               MEMBER: [Origin.from_json({"container": DESCRIPTOR, "crc32": "0" * 8, "kind": "member",
                                          "label": "run.json", "method": 8, "size": 10})],
               **{p: [_git(C1, f"deposit.zip.part-{i}")] for i, p in enumerate(PARTS)}}
    stored = {DESCRIPTOR: b'{"archive": "zip"}', MEMBER: b"{}", PART1: b"x\x9c", PART2: b"\x00\x01", PART3: b"\x02"}
    if hit == "member":
        stored[MEMBER] = b'{"key": "' + CANARY.encode() + b'"}'
    else:
        stored[PART2] = b"PK..." + CANARY.encode()
    return Corpus([_row(EX1, MEMBER), _row(EX2, O1)], origins={**origins, O1: [_git(C1)]},
                  stored={**stored, O1: b"{}"}, members=[member])


def test_a_withheld_split_member_withholds_the_descriptor_and_every_byte_part():
    plan = _split_corpus(hit="member").plan(_policy(CANARY_POLICY))
    assert plan.objects == {MEMBER, DESCRIPTOR, *PARTS} and plan.executions == {EX1}
    assert plan.document is not None
    entries = {e.sha256: e for e in plan.document.entries}
    assert entries[DESCRIPTOR].basis == "container"
    for part in PARTS:
        assert (entries[part].reason, entries[part].basis, entries[part].affected_executions) == ("secret", "container", ())
        assert entries[part].public_note == wh.LINK_NOTES["part"]
        assert entries[part].origins == ({"blob_sha1": "c" * 40, "commit": C1, "kind": "git",
                                          "path": f"deposit.zip.part-{PARTS.index(part)}", "repo": "https://github.com/o/r"},)


def test_a_withheld_byte_part_withholds_its_descriptor_and_the_other_parts_but_not_the_members():
    policy = _policy(CANARY_POLICY + 'scope = "object"\n')
    plan = _split_corpus(hit="part").plan(policy)
    assert plan.objects == {DESCRIPTOR, *PARTS} and plan.executions == frozenset()  # the member stays (D-232)
    assert plan.document is not None
    entries = {e.sha256: e for e in plan.document.entries}
    assert entries[PART2].basis == "profile_rule"
    assert entries[DESCRIPTOR].public_note == wh.LINK_NOTES["descriptor"]
    assert {entries[p].public_note for p in (PART1, PART3)} == {wh.LINK_NOTES["part"]}


def _carved_corpus(stored: Mapping[str, bytes]) -> Corpus:
    origins = {SOURCE: [_git(C1)], BLOB: [Origin.carved(SOURCE, {"p": "/messages/3/content"}, "base64")]}
    return Corpus([_row(EX1, SOURCE)], origins=origins, stored=stored)


def test_a_withheld_source_withholds_the_values_carved_from_it():
    plan = _carved_corpus({SOURCE: b'{"k": "' + CANARY.encode() + b'"}', BLOB: b"\x89PNG"}).plan(_policy(CANARY_POLICY))
    assert plan.objects == {SOURCE, BLOB} and plan.executions == {EX1}
    assert plan.document is not None
    entries = {e.sha256: e for e in plan.document.entries}
    assert (entries[BLOB].basis, entries[BLOB].public_note) == ("container", wh.LINK_NOTES["carved"])


def test_a_carved_value_hit_in_its_decoded_form_withholds_its_source():
    """The source holds the value encoded (base64 here), so only the carved blob matches the pattern."""
    import base64

    stored = {SOURCE: b'{"k": "data:;base64,' + base64.b64encode(CANARY.encode()) + b'"}', BLOB: CANARY.encode()}
    corpus = _carved_corpus(stored)
    assert not corpus.plan(None).objects
    plan = corpus.plan(_policy(CANARY_POLICY + 'scope = "object"\n'))
    assert plan.objects == {SOURCE, BLOB}
    assert plan.document is not None
    entries = {e.sha256: e for e in plan.document.entries}
    assert (entries[BLOB].basis, entries[SOURCE].basis) == ("profile_rule", "container")
    assert entries[SOURCE].public_note == wh.LINK_NOTES["source"]


def test_linked_objects_lists_split_and_carved_groups():
    rows = [OriginRow(DESCRIPTOR, Origin.split("deposit.zip", list(PARTS))), OriginRow(PART1, _git(C1)),
            OriginRow(BLOB, Origin.carved(SOURCE, {"p": "/a"}, "utf8"))]
    assert wh.linked_objects(rows) == [("split", (DESCRIPTOR, *PARTS)), ("carved", (BLOB, SOURCE))]


def test_without_split_or_carved_origins_the_closure_is_unchanged():
    corpus = Corpus([_row(EX1, O1), _row(EX2, O2)], stored={O1: b"key " + CANARY.encode(), O2: b"clean"})
    plan = corpus.plan(_policy(CANARY_POLICY))
    assert plan.objects == {O1} and plan.executions == {EX1}


# ================================================================================================ the member closure
def _member(container: str, sha: str | None, label: str = "m.json", disposition: str = "selected") -> MemberRow:
    return MemberRow(container, "cd" * 32, label, 8, "0" * 8, 10 if sha else None, sha, disposition)


def _facts(rows: Sequence[IndexRow], members: Sequence[MemberRow]) -> Any:
    return wh._Facts(rows, (), members, (), {}, (), {}, lambda _label: iter(()), lambda _row: [], lambda _row: ())


def test_the_planner_closure_equals_purges_member_closure_at_every_level():
    """Ultrareview raw-withhold #6 (CB-1 kept): the planner walks the container map it built once; for every digest its
    citing set equals the one member_closure (purge's closure) gives, through nesting, a shared member, an unselected
    row and a cycle."""
    a, b, c, d, e, f = (_hex(n) for n in range(40, 46))
    members = [_member(a, b, "b.zip"), _member(b, c, "c.zip"), _member(c, a, "loop.zip"), _member(a, d, "d.json"),
               _member(b, d, "d2.json"), _member(e, f, "f.json"), _member(e, None, "skip.bin", "not_selected")]
    rows = [_row("ex_" + ch * 26, sha) for ch, sha in zip("abcdef", (a, b, c, d, e, f), strict=True)]
    planner = wh._Planner(_facts(rows, members), None, None)
    for sha in (a, b, c, d, e, f, O1):
        closure = wh.member_closure(members, sha)
        expected = set().union(*(planner.cites.get(s, set()) for s in {sha, *closure}))
        assert planner.citing(sha) == expected, sha


class _CountingList(list):
    """A list that counts the full passes made over it (``iter``)."""

    passes = 0

    def __iter__(self):  # type: ignore[no-untyped-def]
        type(self).passes += 1
        return super().__iter__()


def test_planning_a_held_archive_reads_the_member_rows_a_bounded_number_of_times():
    """Ultrareview raw-withhold #6: a withhold snapshot holding an archive withholds every member object and asks for
    the citing executions of each; that used to rebuild the container map from every member row on each call (objects x
    rows, hours for a 44k-member archive). The rows are now read a fixed number of times, whatever their count."""
    n = 300
    shas = [_hex(1000 + i) for i in range(n)]
    members = _CountingList(_member(CONTAINER, sha, f"m{i}.json") for i, sha in enumerate(shas))
    member_origins = {sha: [Origin.member(CONTAINER, f"m{i}.json", 8, "0" * 8, 10)] for i, sha in enumerate(shas)}
    corpus = Corpus([_row(EX1, CONTAINER, snapshots=("s2",)), _row(EX2, shas[0], snapshots=("s2",))],
                    origins={CONTAINER: [_git(C2, "a.zip")], **member_origins},
                    stored={CONTAINER: b"PK", **{sha: b"{}" for sha in shas}}, members=members,
                    snapshots={"s2": ("withhold", {"commit": C2, "kind": "git"})})
    corpus.members = members
    _CountingList.passes = 0
    plan = corpus.plan()
    assert plan.objects == {CONTAINER, *shas} and plan.executions == {EX1, EX2}
    assert _CountingList.passes <= 3, _CountingList.passes  # was > n: one full pass per withheld object


def _scan_size(members: Sequence[MemberRow], sha: str) -> int | None:
    """The size lookup as ``_size_and_media`` did it before the index (a pass over every member row)."""
    sizes = {m.size for m in members if m.sha256 == sha and m.size is not None}
    return next(iter(sizes)) if len(sizes) == 1 else None


def _scan_chain(members: Sequence[MemberRow], present: Mapping[str, tuple[str, int]], sha: str) -> str:
    """``_chain`` as it was before the index (a pass over every member row per level)."""
    from agentprov.ingest.quote import escape_untrusted_line

    names: list[str] = []
    current, seen = sha, set()
    while current not in seen and len(names) < 8:
        seen.add(current)
        row = min((m for m in members if m.sha256 == current and m.disposition == "selected" and m.label is not None),
                  key=lambda m: (m.container, m.label or ""), default=None)
        if row is None:
            break
        names.append(escape_untrusted_line(row.label or "", max_chars=120))
        current = row.container
    top = present.get(current, (current[:12], 0))[0]
    return "!/".join([escape_untrusted_line(top, max_chars=120), *reversed(names)])


def test_the_planner_member_index_gives_the_results_of_the_member_scans():
    """Ultra raw-withhold EXTRA (the #6 pattern): ``_size_and_media`` and ``_chain`` read an index of the member rows built
    once; for every digest they give what the per-object scans gave: nesting, one object under two containers (equal and
    different sizes), the smallest (container, label) among several, unselected and rejected rows, a cycle, a long chain."""
    a, b, c, d, e, f, g = (_hex(n) for n in range(60, 67))
    deep = [_hex(n) for n in range(70, 82)]
    members = [_member(a, b, "b.zip"), _member(b, c, "c.zip"), _member(c, d, "z.json"), _member(a, d, "y.json"),
               _member(e, d, "x.json"), _member(e, f, "f.json"), MemberRow(a, "cd" * 32, "f2.json", 8, "0" * 8, 11, f, "selected"),
               _member(b, None, "skip.bin", "not_selected"), MemberRow(c, "cd" * 32, None, 8, "0" * 8, None, None, "rejected",
                                                                       "ingest.archive.crc"),
               _member(g, a, "loop.zip"), _member(a, g, "back.zip"),
               *(_member(deep[i], deep[i + 1], f"n{i}.zip") for i in range(len(deep) - 1))]
    present = {a: ("raw/objects/a.zip", 5), e: ("raw/objects/e.zip", 9), deep[0]: ("raw/objects/top.zip", 1)}
    facts = wh._Facts([], (), members, (), present, (), {}, lambda _label: iter(()), lambda _row: [], lambda _row: ())
    planner = wh._Planner(facts, None, None)
    for sha in (a, b, c, d, e, f, g, *deep, O1):
        expected_size = present[sha][1] if sha in present else _scan_size(members, sha)
        assert planner._size_and_media(sha) == (expected_size, None), sha
        assert planner._chain(sha) == _scan_chain(members, present, sha), sha


def test_the_planner_document_reads_the_member_rows_a_bounded_number_of_times():
    """The size and chain lookups of every withheld object no longer pass over every member row (objects x rows)."""
    n = 200
    shas = [_hex(2000 + i) for i in range(n)]
    members = _CountingList(_member(CONTAINER, sha, f"m{i}.json") for i, sha in enumerate(shas))
    _CountingList.passes = 0
    planner = wh._Planner(_facts([], members), None, None)
    for sha in shas:
        assert planner._size_and_media(sha) == (10, None)
        assert planner._chain(sha).endswith(f"!/m{shas.index(sha)}.json")
    assert _CountingList.passes <= 1, _CountingList.passes  # was 1 + 3n


@pytest.mark.parametrize("change", [{"disposition": []}, {"disposition": "rejected", "code": [], "label": None, "size": None}])
def test_a_members_row_of_the_wrong_type_gives_no_released_members(change):
    """Ultra raw-withhold #10: a tampered ``raw/members.jsonl`` whose closed-vocabulary field is an array or object does
    not parse, so it gives nothing (every member is then read through its container), never a ``TypeError``."""
    import json

    row = {"container": "sha256:" + "a" * 64, "crc32": "00000000", "disposition": "not_selected",
           "fn_digest": "sha256:" + "b" * 64, "label": "m.json", "method": 0, "sha256": None, "size": 1, **change}
    files = {"raw/members.jsonl": json.dumps(row).encode() + b"\n", "raw/origins.jsonl": b""}
    assert wh._released_members(files, lambda label: [files[label]]) == []


# ================================================================================================ D-961: withhold-object
def _address_policy(held: frozenset[str], objects: frozenset[str]) -> wh.WithholdPolicy:
    policy = wh.load_policy(b'[profile]\nid = "tst-profile"\n', profile_id="tst-profile", profile_version=1, catalogues={},
                            addresses=held, object_addresses=objects)
    assert policy is not None
    return policy


def _archive_corpus(archive_bytes: bytes) -> Corpus:
    """SEAgent's shape: one stored deposit archive whose selected member (stored as its own object) is EX1's primary;
    the address sits in the archive's own bytes (an unselected member or a member name), not in the member or any
    derived file."""
    member = MemberRow(CONTAINER, "cd" * 32, "run.json", 8, "0" * 8, 10, MEMBER, "selected")
    return Corpus([_row(EX1, MEMBER), _row(EX2, O1)],
                  origins={CONTAINER: [_git(C1, "a.zip")], O1: [_git(C1)],
                           MEMBER: [Origin.from_json({"container": CONTAINER, "crc32": "0" * 8, "kind": "member",
                                                      "label": "run.json", "method": 8, "size": 10})]},
                  stored={CONTAINER: archive_bytes, MEMBER: b'{"clean": true}', O1: b'{"clean": true}'}, members=[member])


#: Fake addresses assembled at run time; only their digests reach the policy.
_HELD, _OBJECT = "@".join(("held.person", "example.org")), "@".join(("object.person", "example.org"))


def test_a_withhold_object_address_in_a_container_withholds_the_container_alone_d961():
    from agentprov.corpus.personas import address_digest

    plan = _archive_corpus(f"PK unselected {_OBJECT} end".encode()).plan(
        _address_policy(frozenset(), frozenset({address_digest(_OBJECT.encode())})))
    assert plan.objects == {CONTAINER} and plan.executions == frozenset()  # before D-961: {EX1}, through citing()
    assert plan.document is not None
    (entry,) = plan.document.entries
    assert (entry.reason, entry.basis, entry.affected_executions) == ("personal_data", "profile_rule", ())
    assert entry.finding is not None and entry.finding.rule == "tst-profile@1:email-withheld"


def test_a_withhold_address_in_a_raw_object_withholds_executions_only_through_their_own_records_d963():
    from agentprov.corpus.personas import address_digest

    held, obj = frozenset({address_digest(_HELD.encode())}), frozenset({address_digest(_OBJECT.encode())})
    for text in (f"PK {_HELD} end", f"PK {_HELD} and {_OBJECT} end"):  # in the container's bytes only: it goes alone
        plan = _archive_corpus(text.encode()).plan(_address_policy(held, obj))
        assert plan.executions == frozenset() and plan.objects == {CONTAINER}
    corpus = _archive_corpus(f"PK {_HELD} end".encode())
    corpus.derived[LAYOUT.aer_relpath(EX1)] = f'{{"text": "{_HELD}"}}'.encode()  # EX1's own record holds it
    plan = corpus.plan(_address_policy(held, obj))
    assert plan.executions == {EX1} and {CONTAINER, MEMBER} <= plan.objects


def test_a_shared_raw_object_withholds_only_the_execution_whose_record_holds_the_address_d963():
    """memo-ozdincer's shape: one results file is the primary of several executions; only EX1's record holds the
    address. Before D-963 every execution citing the file was withheld."""
    from agentprov.corpus.personas import address_digest

    corpus = Corpus([_row(EX1, O1), _row(EX2, O1), _row(EX3, O2)], stored={O1: f"results {_HELD}".encode(), O2: b"{}"})
    corpus.derived[LAYOUT.aer_relpath(EX1)] = f'{{"text": "{_HELD}"}}'.encode()
    plan = corpus.plan(_address_policy(frozenset({address_digest(_HELD.encode())}), frozenset()))
    assert plan.executions == {EX1} and plan.objects == {O1}  # EX2 stays released; its raw object is withheld


def test_a_withhold_object_address_in_a_derived_file_still_withholds_its_execution_d961():
    from agentprov.corpus.personas import address_digest

    corpus = _archive_corpus(b"PK clean")
    corpus.derived[LAYOUT.aer_relpath(EX2)] = f'{{"text": "{_OBJECT}"}}'.encode()
    plan = corpus.plan(_address_policy(frozenset(), frozenset({address_digest(_OBJECT.encode())})))
    assert plan.executions == {EX2} and O1 in plan.objects  # no released file may hold it (the chain backstop)


def test_the_recorded_address_rule_is_the_same_with_or_without_withhold_object_digests_d961():
    from agentprov.corpus.personas import address_digest

    a, b = frozenset({address_digest(_HELD.encode())}), frozenset({address_digest(_OBJECT.encode())})
    assert _address_policy(a, b).record() == _address_policy(a | b, frozenset()).record()
    assert _address_policy(frozenset(), b).record().rules == (("email-withheld", "address", "executions"),)


# ---------------------------------------------------------------------------------------------- D-964: spec-listed objects
def _listed_policy(objects: frozenset[str] = frozenset(), executions: frozenset[str] = frozenset(),
                   profile: bytes = b'[profile]\nid = "tst-profile"\n') -> wh.WithholdPolicy:
    policy = wh.load_policy(profile, profile_id="tst-profile", profile_version=1, catalogues={},
                            listed=(objects, executions))
    assert policy is not None
    return policy


def test_a_listed_object_is_withheld_alone_with_reason_secret_d964():
    """A raw object the spec lists is withheld alone, even as the primary of an execution: the executions stay."""
    corpus = Corpus([_row(EX1, O1), _row(EX2, O2, O3)])
    plan = corpus.plan(_listed_policy(frozenset({O1, O3})))
    assert plan.objects == {O1, O3} and plan.executions == frozenset()
    assert plan.document is not None and plan.document.format == "agentprov-withheld/0.5"
    for entry in plan.document.entries:
        assert (entry.reason, entry.basis, entry.affected_executions) == ("secret", "profile_rule", ())
        assert entry.finding is not None and entry.finding.rule == "tst-profile@1:secret-withheld"
    assert plan.document.policies[0].rules == (("secret-withheld", "object", "object"),)


def test_a_listed_execution_is_withheld_with_its_primary_object_d964():
    """A PROV-file finding: the spec lists the execution; it goes with its primary object, as a derived-file hit does."""
    corpus = Corpus([_row(EX1, O1, O2), _row(EX2, O3)])
    plan = corpus.plan(_listed_policy(executions=frozenset({EX1})))
    assert plan.executions == {EX1} and plan.objects == {O1}  # the supporting object O2 stays
    assert plan.document is not None
    (entry,) = plan.document.entries
    assert (entry.reason, entry.affected_executions) == ("secret", (EX1,))


def test_a_listed_object_or_execution_the_corpus_does_not_hold_refuses_the_seal_d964():
    corpus = Corpus([_row(EX1, O1)])
    for policy in (_listed_policy(frozenset({O2})), _listed_policy(executions=frozenset({EX3}))):
        with pytest.raises(wh.WithholdError) as caught:
            corpus.plan(policy)
        assert caught.value.code == "corpus.withhold.policy"


def test_the_object_rule_is_never_a_byte_rule_and_joins_a_profile_and_an_address_rule_d964():
    from agentprov.corpus.personas import address_digest

    profile = (b'[profile]\nid = "tst-profile"\n[withhold]\nreason = "secret"\npublic_note = "canary"\n'
               b'[[withhold.rules]]\nid = "canary"\nmarker = "' + CANARY.encode() + b'"\n')
    policy = wh.load_policy(profile, profile_id="tst-profile", profile_version=1, catalogues={},
                            addresses=frozenset({address_digest(_HELD.encode())}), listed=(frozenset({O1}), frozenset()))
    assert policy is not None
    assert [r.id for r in policy.rules] == ["canary", "email-withheld", "secret-withheld"]
    assert "secret-withheld" not in {r.id for r in policy.byte_rules} and len(policy.listed_rules) == 1
    corpus = Corpus([_row(EX1, O1), _row(EX2, O2)], stored={O1: b'{"clean": true}', O2: CANARY.encode()})
    plan = corpus.plan(policy)
    assert plan.objects == {O1, O2} and plan.executions == {EX2}  # the canary withholds EX2 (scope executions)
    assert wh.rescan([_label(O1)], corpus.stream, policy, decode=False) == []  # an object rule matches no bytes


def test_without_a_listed_entry_the_policy_and_the_plan_are_unchanged_d964():
    assert wh.load_policy(b'[profile]\nid = "tst-profile"\n', profile_id="tst-profile", profile_version=1,
                          catalogues={}) is None
    profile = (b'[profile]\nid = "tst-profile"\n[withhold]\nreason = "secret"\npublic_note = "canary"\n'
               b'[[withhold.rules]]\nid = "canary"\nmarker = "' + CANARY.encode() + b'"\n')
    plain = wh.load_policy(profile, profile_id="tst-profile", profile_version=1, catalogues={})
    empty = wh.load_policy(profile, profile_id="tst-profile", profile_version=1, catalogues={},
                           listed=(frozenset(), frozenset()))
    assert plain == empty


def test_a_profile_rule_named_secret_withheld_is_refused_d964():
    profile = (b'[profile]\nid = "tst-profile"\n[withhold]\nreason = "secret"\npublic_note = "canary"\n'
               b'[[withhold.rules]]\nid = "secret-withheld"\nmarker = "' + CANARY.encode() + b'"\n')
    with pytest.raises(wh.WithholdError):
        wh.load_policy(profile, profile_id="tst-profile", profile_version=1, catalogues={},
                       listed=(frozenset({O1}), frozenset()))


def test_the_listed_backstop_reports_what_is_still_released_d964():
    policy = _listed_policy(frozenset({O1, O2}), frozenset({EX1, EX2}))
    released = wh.listed_backstop(policy, [_label(O1), _label(O3), "aer/aa/x.aer.jsonl"], [_row(EX2, O3), _row(EX3, O3)])
    assert released == [("object", O1), ("execution", EX2)]
    assert wh.listed_backstop(policy, [_label(O3)], [_row(EX3, O3)]) == []


def test_withhold_listed_reads_the_spec_table_d964():
    from pathlib import Path

    spec = (Path(__file__).resolve().parents[3] / "corpora" / "mcphunt" / "corpus-spec.toml").read_bytes()
    assert wh.withhold_listed(spec) == (frozenset(), frozenset())
    table = f'\n[withhold]\ndecided_by = "a review"\nobjects = ["sha256:{O1}"]\nexecutions = ["{EX1}"]\n'.encode()
    assert wh.withhold_listed(spec + table) == (frozenset({O1}), frozenset({EX1}))
