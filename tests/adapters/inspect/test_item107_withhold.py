"""D-604 for the two AgentHarm Inspect profiles (regeneration-batch item 107; user decision 2026-10-21): the shipped
``[withhold]`` rules parse, hit the raw shapes they target, and never hit what the redaction leaves in derived records
(D-235: a derived hit would withhold the execution). Made-up account names only."""

from __future__ import annotations

from pathlib import Path

from agentprov.corpus.withhold import policy_of_profile, scan_chunks

REPO = Path(__file__).resolve().parents[3]
PROFILES = REPO / "src" / "agentprov" / "adapters" / "inspect" / "profiles"


def _policy(profile_id: str):
    policy = policy_of_profile((PROFILES / f"{profile_id}.profile.toml").read_bytes(), profile_id=profile_id,
                               profile_version=2)
    assert policy is not None
    return policy


def test_fragfuse_withholds_a_users_account_path_and_not_its_label():
    policy = _policy("fragfuse-agentharm")
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [
        ("users-account-path", "pattern", "object", "personal_data")]
    assert scan_chunks([b'"traceback": "File \\"/Users/zq7synthetic/proj/run.py\\""'], policy.rules)
    assert not scan_chunks([b'"traceback": "File \\"/Users/<account>/proj/run.py\\""'], policy.rules)


def test_kexin_withholds_a_named_dataset_location_only():
    policy = _policy("kexin-xu-01-agentharm")
    assert [(r.id, r.scope, r.reason) for r in policy.rules] == [("dataset-location-home", "object", "personal_data")]
    assert scan_chunks([b'{"dataset":{"name":"x","location":"/home/zq7synth/.cache/x"}}'], policy.rules)
    assert not scan_chunks([b'{"dataset":{"name":"x","location":"/home/ubuntu/.cache/x"}}'], policy.rules)  # generic
    assert not scan_chunks([b'"content": "see /home/zq7synth/notes.txt"'], policy.rules)  # benchmark content, unanchored
