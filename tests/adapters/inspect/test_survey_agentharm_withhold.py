"""D-811: the ``survey-agentharm@2`` ``[withhold]`` rule (post-check PC-ast-survey-agentharm S2; user decision 2026-10-24,
option (a); D-604 object scope, as kexin's ``dataset-location-home``, item 107).

Each of the survey's six AgentHarm ``.eval`` logs records Inspect's ``eval.dataset.location``, a dataset cache under one
named third-party account's home directory, in its ``header.json`` member (stored as a raw object of its own) and in
its ``_journal/start.json`` member (not selected, so read only by the decoded-archive scan). The rule withholds the six
header objects at seal, and container closure withholds their six ``.eval`` archives; every execution stays released.
The unit tests use made-up account names only. The census test (marker ``full_corpus``) scans the pinned snapshot in
a local clone (``$AGENTPROV_SURVEY_CLONE``) through :mod:`agentprov.ingest.archives` and compares labels and digests,
never the value.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from agentprov.adapters.profiles import load_profile
from agentprov.corpus.withhold import policy_of_profile, scan_chunks
from agentprov.ingest.archives import iter_zip_members, open_zip

REPO = Path(__file__).resolve().parents[3]
PROFILES = REPO / "src" / "agentprov" / "adapters" / "inspect" / "profiles"
#: A made-up account name, assembled at run time.
ACCOUNT = "zq7" + "synthx"
#: The pinned snapshot's logs: label -> (sha256 of the .eval, sha256 of its header.json member), census 2026-10-24.
WITHHELD = {
    "agentharm/results/coder_benign/2026-08-22T02-58-36-00-00_agentharm-benign_Mw9cYAge9JkjQ9D9FPrGKU.eval":
        ("fc1e516f34d6b49ff05748e950d1ecae51d569203a1c4ec778912a62c58d24e6",
         "8e86d3ce28fc78f4919df441a6036876f7a5a4068c02dd55989edf18548a2d94"),
    "agentharm/results/coder_harmful/2026-08-22T01-56-09-00-00_agentharm_DHQwUgVrD8EonG5RWLd9b6.eval":
        ("3be29f23d7977eed5c7ac7acd333deb7f3f93b4de829ccb2abb86422a1c585a5",
         "5ac78e51ddfc15cec87d439cf09a9e42c2aea631e206f9a0ac347eefb48ccb8f"),
    "agentharm/results/gptoss_benign/2026-08-21T23-10-42-00-00_agentharm-benign_JArEBkqSNv9uTu7zWGRkiQ.eval":
        ("165eb60c5758ac18a4355bee2599349fb9ce104a277ad59c43e4e71be2323946",
         "655ac59e381f3486be8d2f022ea5728b9e8c88d0baa039284144c2c31703ef1e"),
    "agentharm/results/gptoss_harmful/2026-08-21T21-23-06-00-00_agentharm_TQQjY9dzdqeuyNhWvATriR.eval":
        ("c9eafb4b685d55b3029250913e6aed5290a1468295388f5f656202f4cb5c0ad0",
         "9b6feb8ee59dd3db351d53b7cfad37ac4f21f15236da3d91a0e34b6aa6a741dd"),
    "agentharm/results/qwen14_benign/2026-08-22T08-34-50-00-00_agentharm-benign_6NAdYckpcsjaiPHVAzGAxP.eval":
        ("9ebe03f92279f268284e6735dcc493c937cdc4eaa5aa15a931be2a7a3088511a",
         "754609adf0399317e7a0a464d325a4c2d1dd9dee395a0d6ddfee84fd0eb7b3d9"),
    "agentharm/results/qwen14_harmful/2026-08-22T04-27-45-00-00_agentharm_oJoW34k6hj7evSdbggsgrm.eval":
        ("0b2d10a042ed7a6d913dcc3303b246c6cea14d16b1fc4f97db5cc5101574fc71",
         "2040b443f66519c18ed39f68093987f1ca4fb3a54b1db1d2aea0fd627c0964c3"),
}
CLONE_ENV = "AGENTPROV_SURVEY_CLONE"
DEFAULT_CLONE = Path.home() / "Desktop/PhD/Labs/AgentPROV-upstream/agent-security-tools-survey"


def _policy(version: int = 2):
    path = PROFILES / ("survey-agentharm.profile.toml" if version == 2 else
                       f"archive/survey-agentharm.profile.v{version}.toml")
    return policy_of_profile(path.read_bytes(), profile_id="survey-agentharm", profile_version=version)


def test_version_2_declares_one_object_scope_personal_data_rule_as_kexin():
    assert load_profile("survey-agentharm").version == 2
    policy = _policy()
    assert policy is not None
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [
        ("dataset-location-home", "pattern", "object", "personal_data")]
    kexin = policy_of_profile((PROFILES / "kexin-xu-01-agentharm.profile.toml").read_bytes(),
                              profile_id="kexin-xu-01-agentharm", profile_version=2)
    assert kexin is not None and policy.rules[0].regex.pattern == kexin.rules[0].regex.pattern  # the same compiled pattern


def test_the_rule_hits_the_header_and_journal_shape():
    rules = _policy().rules
    home = ("/ho" + "me/") + ACCOUNT
    assert scan_chunks([f'{{"dataset":{{"name":"agentharm","location":"{home}/.cache/inspect_evals/x"}}}}'.encode()],
                       rules)


def test_the_rule_leaves_generic_accounts_benchmark_content_and_placeholders_alone():
    rules = _policy().rules
    assert not scan_chunks([b'{"dataset":{"location":"/home/ubuntu/.cache/x"}}'], rules)  # under the 7-character floor
    assert not scan_chunks([("see /ho" + "me/" + ACCOUNT + "/notes.txt").encode()], rules)  # not the header key
    assert not scan_chunks([b'{"dataset":{"location":"/home/<account>/.cache/x"}}'], rules)  # a placeholder


def test_version_1_has_no_policy_so_a_corpus_recorded_under_it_must_never_be_sealed():
    """ast-survey-agentharm-rg1 recorded survey-agentharm@1: it is kept as evidence and never sealed or deposited."""
    assert _policy(1) is None
    assert load_profile("survey-agentharm", 1).sha256 == (
        "b303208a27fc42d50d067d064e0209fc1b83d53ae62283fa7c0d3afd41d9feaa")  # as the rg1 corpus records it


def _clone() -> Path | None:
    root = Path(os.environ[CLONE_ENV]) if os.environ.get(CLONE_ENV) else DEFAULT_CLONE
    return root if (root / "agentharm" / "results").is_dir() else None


@pytest.mark.full_corpus
def test_census_at_the_pin_hits_exactly_the_six_headers_and_their_journals():
    root = _clone()
    if root is None:
        pytest.skip(f"the survey clone at the pinned commit is absent (${CLONE_ENV})")
    rules = _policy().rules
    headers: dict[str, tuple[str, str]] = {}
    other: dict[str, list[str]] = {}
    for path in sorted((root / "agentharm").rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        label = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if path.suffix != ".eval":
            assert not scan_chunks([data], rules), label
            continue
        with path.open("rb") as fp, open_zip(fp, release=False) as archive:
            for member in iter_zip_members(archive):
                if member.disposition != "selected" or not scan_chunks(member.iter_chunks(), rules):
                    continue
                if member.label == "header.json":
                    headers[label] = (hashlib.sha256(data).hexdigest(),
                                      hashlib.sha256(archive.read_member(member)).hexdigest())
                else:
                    other.setdefault(label, []).append(str(member.label))
    assert headers == WITHHELD
    assert other == {label: ["_journal/start.json"] for label in WITHHELD}  # not stored as objects; inside the .eval
