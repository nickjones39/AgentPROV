"""The ``inspect.whistlebench@2`` semantics profile (D-601 addendum 2, user decision 2026-10-21; docs/architecture
D.9.14, C.14.1-C.14.4; H.2.5).

The tool table and the scorer table are read from the pinned ``highagency/`` code (class I; every entry cites a path,
a git blob id and lines). Checked over synthetic WhistleBench-band AERs and the committed pinned log:
* tools follow the table, unlisted tools are fail-closed;
* letter grades C/I become outcomes only for listed scorers in listed suites; ``email_whistleblowing`` gets none;
* tier 3 in release mode and tier 4; determinism;
* the cited code: each blob id is the file at the pinned commit and each line range is inside it (read from the staged
  clone when present, as data, never run);
* tables that over-claim are refused.
Nothing here prints log content (R-42).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import inspect_support as support
import pytest

from agentprov.adapters.inspect.semantics import build_profile
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.sem.engine import annotate, dumps_sem
from agentprov.sem.profiles import SemanticsProfileError, profile_digest
from agentprov.sem.types import Annotation, SemanticsProfile
from agentprov.sem.validate import validate_sem_document

SEM_DIR = support.REPO / "src" / "agentprov" / "adapters" / "inspect" / "semantics"
TABLES = SEM_DIR / "inspect.whistlebench-2" / "tables.toml"
FIXTURE_DIR = support.REPO / "tests" / "fixtures" / "inspect" / "whistlebench"
CLONE = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov")) / "staging" / "10f" / "whistlebench" / (
    "whistlebench" + ".git")
COMMIT = "9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc"
HIGH_AGENCY = "highagency/high_agency"
DELIBERATION = "highagency/high_agency_deliberation_awareness"
RULES = {"inspect.tool_table@1", "inspect.unknown_tool@1", "inspect.scorer_letter_table@1"}
#: version 1's data digest: unchanged by version 2 (D-31; v1 stays shipped as it was)
V1_SHA256 = "c62f5567a562"


def profile() -> SemanticsProfile:
    return load_semantics_profile("inspect.whistlebench", 2)


def _scores() -> dict[str, Any]:
    return {
        "email_whistleblowing": {"value": {"gov_whistleblowing": "C", "media_whistleblowing": "I",
                                           "internal_whistleblowing": "I"}, "explanation": "Synthetic."},
        "test_awareness": {"value": {"evaluation_awareness": "I", "hypothetical_recognition": "C"}, "explanation": "S."},
        "refusal": {"value": "C", "explanation": "Synthetic."},
    }


def _sample(sid: str, scores: dict[str, Any]) -> dict[str, Any]:
    """basic_sample with WhistleBench tool names (send_email for get_x) and WhistleBench scores."""
    text = json.dumps(support.basic_sample(sid)).replace('"get_x"', '"send_email"')
    sample = json.loads(text)
    sample["scores"] = scores
    return sample  # type: ignore[no-any-return]


def _doc(tmp_path: Path, *, task: str = HIGH_AGENCY, scores: dict[str, Any] | None = None) -> AerDocument:
    header = support.synthetic_header("0.3.130")
    header["eval"]["task"] = task
    imported = support.import_log(support.build_eval(header, {"s1_epoch_1.json": _sample("s1", scores or _scores())}),
                                  tmp_path, profile=load_profile("whistlebench"))
    (unit,) = imported.units
    assert not unit.outcome.degenerate
    return load_aer_bytes(unit.data)


@pytest.fixture(scope="module")
def committed(tmp_path_factory: pytest.TempPathFactory) -> list[AerDocument]:
    source = FIXTURE_DIR / "SOURCE.json"
    if not source.is_file():
        pytest.skip("the whistlebench fixture is absent")
    (entry,) = json.loads(source.read_bytes())
    imported = support.import_log((FIXTURE_DIR / entry["file"]).read_bytes(), tmp_path_factory.mktemp("wb-sem2"),
                                  path=entry["path"], profile=load_profile("whistlebench"))
    return [load_aer_bytes(u.data) for u in imported.units]


def _outcomes(doc: AerDocument, anns: list[Annotation]) -> dict[str, dict[str, Any]]:
    names = {r["id"]: r["name"] for r in doc.of_kind("judgement")}
    return {names[a.target]: a.value for a in anns if a.type == "outcome"}


# ------------------------------------------------------------------------------------------------ the profile
def test_version_2_is_selected_and_version_1_stays_as_shipped():
    prof = profile()
    assert (prof.id, prof.version, dict(prof.rules), dict(prof.ns), prof.taint_policy) == \
        ("inspect.whistlebench", 2, {"inspect": 2}, {}, None)
    assert prof.sha256 == profile_digest({"tables.toml": TABLES.read_bytes()})
    assert load_semantics_profile("inspect.whistlebench", 1).sha256.startswith(V1_SHA256)
    (part,) = get_source("whistlebench").capabilities
    assert part.semantics == ("inspect.whistlebench@2",)


def test_every_cited_rule_is_class_i_active_in_the_declared_catalogue_version():
    cat = load_catalogue("inspect", 2)
    for ref in RULES:
        entry = cat.get(ref)
        assert entry is not None and entry.citable and entry.status == "active" and entry.cls == "I", ref


def test_tools_follow_the_table_and_unlisted_tools_are_fail_closed(tmp_path):
    table = {t["name"]: t for t in tomllib.loads(TABLES.read_text(encoding="utf-8"))["tool"]}
    doc = _doc(tmp_path)
    text = json.dumps(support.basic_sample("s2"))  # get_x: a tool the table does not list
    header = support.synthetic_header("0.3.130")
    header["eval"]["task"] = HIGH_AGENCY
    other = support.import_log(support.build_eval(header, {"s2_epoch_1.json": json.loads(text)}), tmp_path / "other",
                               profile=load_profile("whistlebench")).units[0]
    for d in (doc, load_aer_bytes(other.data)):
        anns = list(profile().annotate(d))
        by_target = {(a.target, a.type): a for a in anns}
        seen = 0
        for te in d.of_kind("tool_execution"):
            a = by_target[(te["id"], "role")]
            listed = table.get(te["name"])
            assert a.value == (listed["roles"] if listed else ["unknown"])
            assert a.rule == (("inspect.tool_table@1",) if listed else ("inspect.unknown_tool@1",))
            seen += 1
        for msg in d.of_kind("message"):
            for i, part in enumerate(msg["parts"]):
                listed = table.get(part.get("name"))
                if part["t"] == "tool_call":
                    assert by_target[(f"{msg['id']}#{i}", "role")].value == (listed["roles"] if listed else ["unknown"])
                elif part["t"] == "tool_result":
                    value = by_target[(f"{msg['id']}#{i}", "integrity")].value
                    assert value == (listed["integrity"] if listed else "unknown") and value != "trusted"
        assert seen
    assert table["send_email"]["roles"] == ["send_sink"] and table["write_file"]["roles"] == ["write_sink"]


def test_letter_grades_become_outcomes_only_for_listed_scorers_and_suites(tmp_path):
    doc = _doc(tmp_path)
    outcomes = _outcomes(doc, list(profile().annotate(doc)))
    assert outcomes == {
        "refusal": {"claim": "inspect.refusal", "holds": True},
        "test_awareness.evaluation_awareness": {"claim": "inspect.evaluation_awareness", "holds": False},
        "test_awareness.hypothetical_recognition": {"claim": "inspect.hypothetical_recognition", "holds": True},
    }  # email_whistleblowing.*: not in the release, so no outcome
    # a listed scorer in an unlisted suite, and a value that is not C or I, get no outcome
    other = _doc(tmp_path / "suite", task=DELIBERATION)
    assert "refusal" not in _outcomes(other, list(profile().annotate(other)))
    partial = _doc(tmp_path / "p", scores={"refusal": {"value": "P", "explanation": "S."}})
    assert _outcomes(partial, list(profile().annotate(partial))) == {}
    snitch = _doc(tmp_path / "snitch", task=DELIBERATION, scores={
        "gov_snitching": {"value": "C"}, "media_snitching": {"value": "I"}, "internal_snitching": {"value": "I"},
        "deliberation_analysis": {"value": "C"}})
    assert _outcomes(snitch, list(profile().annotate(snitch))) == {
        "gov_snitching": {"claim": "inspect.snitch_attempt_government", "holds": True},
        "media_snitching": {"claim": "inspect.snitch_attempt_media", "holds": False},
        "internal_snitching": {"claim": "inspect.snitch_attempt_internal", "holds": False},
        "deliberation_analysis": {"claim": "inspect.concluded_evaluation", "holds": True},
    }


def test_a_harness_default_judgement_gets_no_outcome(tmp_path):
    doc = _doc(tmp_path)
    records = [dict(r, origin="harness_default") if r.get("k") == "judgement" else r for r in doc.records]
    forged = AerDocument(doc.header, records, doc.seal, doc.execution_digest, doc.file_sha256)
    assert not [a for a in profile().annotate(forged) if a.type == "outcome"]


def test_tier_3_and_tier_4_pass_on_synthetic_and_committed_aers(tmp_path, committed):
    from agentprov.prov.engine import derive
    from agentprov.validate import validate_prov

    prof = profile()
    docs = [_doc(tmp_path), _doc(tmp_path / "d", task=DELIBERATION, scores={"gov_snitching": {"value": "C"}}),
            *committed[:10]]
    claims = set()
    for doc in docs:
        sem = annotate(doc, prof)
        assert json.loads(dumps_sem(sem).split(b"\n", 1)[0])["rules"] == {"inspect": 2} == {
            "inspect": doc.header["rules"]["inspect"]}
        report = validate_sem_document(sem, doc, catalogues=RuleRegistry.default(), mode="release", profile=prof)
        assert report.ok, [(f.code, f.pointer) for f in report.errors]
        result = derive(doc, [sem], sem_profiles={(prof.id, prof.version): prof})
        prov = validate_prov(result.prov_json, doc, sems=[sem])
        assert prov.ok, [(o.id, sorted(o.codes())) for o in prov.outcomes if o.status == "fail"]
        claims |= {a.value["claim"] for a in prof.annotate(doc) if a.type == "outcome"}
    assert "inspect.snitch_attempt_government" in claims and "inspect.refusal" in claims


def test_annotate_is_deterministic(tmp_path):
    first, second = _doc(tmp_path / "a"), _doc(tmp_path / "b")
    assert dumps_sem(annotate(first, profile())) == dumps_sem(annotate(second, profile()))


# ------------------------------------------------------------------------------------------------ the cited code
def _citations() -> list[dict[str, Any]]:
    doc = tomllib.loads(TABLES.read_text(encoding="utf-8"))
    assert doc["code"] == {"repo": "https://github.com/legobridge/whistlebench", "commit": COMMIT}
    return [c for kind in ("tool", "scorer") for e in doc[kind] for c in e["code"]]


def test_every_entry_cites_a_path_blob_and_lines():
    cited = _citations()
    assert cited and all(c["path"].startswith("highagency/") and len(c["blob"]) == 40 for c in cited)


def test_the_cited_blobs_are_the_pinned_files_and_the_lines_are_inside_them():
    if not CLONE.is_dir():
        pytest.skip("the staged whistlebench clone is absent")
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    for c in _citations():
        found = subprocess.run(["git", "--git-dir", str(CLONE), "rev-parse", f"{COMMIT}:{c['path']}"],
                               capture_output=True, env=env, check=True).stdout.decode().strip()
        assert found == c["blob"], c["path"]
        data = subprocess.run(["git", "--git-dir", str(CLONE), "cat-file", "blob", c["blob"]],
                              capture_output=True, env=env, check=True).stdout
        assert hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == c["blob"]  # noqa: S324 - git's blob id
        n = len(data.decode("utf-8").splitlines())
        for part in c["lines"].split(","):
            lo, _, hi = part.strip().partition("-")
            assert 1 <= int(lo) <= int(hi or lo) <= n, (c["path"], c["lines"])


# ------------------------------------------------------------------------------------------------ over-claims
def _variant(old: str, new: str) -> dict[str, bytes]:
    text = TABLES.read_text(encoding="utf-8")
    assert old in text
    return {"tables.toml": text.replace(old, new, 1).encode()}


@pytest.mark.parametrize(("old", "new"), [
    ('integrity = "untrusted"', 'integrity = "trusted"'),  # tool output is never trusted
    ('roles = ["write_sink"]', 'roles = ["unknown"]'),  # a listed tool needs a known role
    ('claim = "inspect.refusal"', 'claim = "attack_succeeded"'),  # no core claim (no attacker)
    ('claim = "inspect.refusal"', 'claim = "refusal"'),  # claims are namespaced
    ('suites = ["highagency/high_agency"]', 'suites = []'),
    ('code = [{ path = "highagency/whistlebench/tools.py", blob = "73f5950a9a812585f7317a33e2edda8ffef533b6", lines = "26-53" }]',
     'code = []'),  # every entry cites code
    ('lines = "26-53"', 'lines = "all"'),
    ('reason = "writes the given content', 'polarity = "x"\nreason = "writes the given content'),  # closed keys
])
def test_a_table_that_over_claims_is_refused(old: str, new: str):
    with pytest.raises(SemanticsProfileError):
        build_profile("inspect.whistlebench", 2, _variant(old, new), "0" * 64)
