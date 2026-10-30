"""Regeneration-batch item 108 (the D-510 safeguard, fail closed) with item 106's EnvironmentOptim rows: a selected file
whose label names an account directory is held (``select.redaction_pending``) unless a redaction rule of its profile
covers that segment. Synthetic trees under made-up account names only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov.adapters.account_paths import account_shapes, covered, redaction_patterns
from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter

ACCOUNT = "zq7synthetic"
EO_REPO = "https://github.com/omseeth/EnvironmentOptim"
EO_COMMIT = "febf82d8d1d8344d6c19e9fd172b51e52d68416a"


# ------------------------------------------------------------------------------------------------ the shapes
@pytest.mark.parametrize(("label", "shapes"), [
    (f"runs/_ceph_ssd_students_{ACCOUNT}_qwen3_5/banking/x.json", [("munged_cluster", 1)]),
    (f"runs/_home_{ACCOUNT}_ckpt/x.json", [("munged_home", 1)]),
    (f"logs/home/{ACCOUNT}/run/x.json", [("slashed_home", 2)]),
    (f"data/Users/{ACCOUNT}/a.json", [("slashed_users", 2)]),
    (f"mfs1/u/{ACCOUNT}/r/x.json", [("slashed_mfs1", 2)]),
    ("home/user/x.json", []),  # AgentDojo's fictional sandbox user
    ("runs/home_assistant_v2/x.json", []),
    ("runs/qwen/home_dir/x.json", []),
    ("runs/x_home_y_z/a.json", []),
])
def test_account_shapes(label, shapes):
    assert [(s.shape, s.segment) for s in account_shapes(label)] == shapes


def test_a_matching_redaction_pattern_covers_the_segment():
    label = f"runs/_ceph_ssd_students_{ACCOUNT}_qwen3_5/banking/x.json"
    (shape,) = account_shapes(label)
    rule = {"pattern": r"^_ceph_ssd_students_(?P<span>[^_/]+)_(?P<leaf>qwen3_5(?:-[0-9]+B)?)$"}
    assert covered(label, shape, redaction_patterns([rule]))
    assert not covered(label, shape, redaction_patterns([{"pattern": r"^_home_"}]))


def test_a_match_that_misses_the_account_does_not_cover_it():
    """Pre-round review #19: a pattern matching elsewhere in the segment redacts nothing there."""
    label = f"runs/_home_{ACCOUNT}_ckpt/x.json"
    (shape,) = account_shapes(label)
    assert not covered(label, shape, redaction_patterns([{"pattern": r"ckpt"}]))
    assert covered(label, shape, redaction_patterns([{"pattern": r"_home_(?P<span>[^_]+)_"}]))


def test_a_labels_allowlist_covers_only_its_listed_accounts():
    """Pre-round review #19: a dtap-style token rule (D-607) matches every token, but redacts only the tokens whose
    salted label it lists; an unlisted account stays uncovered (fail closed)."""
    import hashlib

    label = f"logs/home/{ACCOUNT}/run/x.json"
    (shape,) = account_shapes(label)
    token = r"(?<![A-Za-z0-9])(?P<span>[A-Za-z0-9]++)"
    listed = hashlib.sha256(f"p\0{ACCOUNT}".encode()).hexdigest()[:12]
    assert covered(label, shape, redaction_patterns([{"pattern": token, "labels": [listed]}]), salt="p")
    assert not covered(label, shape, redaction_patterns([{"pattern": token, "labels": ["0" * 12]}]), salt="p")
    assert not covered(label, shape, redaction_patterns([{"pattern": token, "labels": [listed]}]), salt="other-profile")


# ------------------------------------------------------------------------------------------------ the importer
def _log(pipeline_name: str) -> bytes:
    """A synthetic v0.k11 TraceLogger log (as tests/adapters/agentdojo's base_log)."""
    call = {"function": "send_money", "args": {"recipient": "X", "amount": 10.0}, "id": "call_1"}
    doc = {"suite_name": "banking", "pipeline_name": pipeline_name, "user_task_id": "user_task_1",
           "injection_task_id": "injection_task_2", "attack_type": "important_instructions",
           "injections": {"vec_a": "payload A"},
           "messages": [{"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Pay the bill."},
                        {"role": "assistant", "content": None, "tool_calls": [call]},
                        {"role": "tool", "content": "done", "tool_call_id": "call_1", "tool_call": call, "error": None},
                        {"role": "assistant", "content": "Paid.", "tool_calls": None}],
           "error": None, "utility": True, "security": False, "duration": 3.0}
    return json.dumps(doc, indent=4).encode("utf-8")


def _v1_log(pipeline_name: str) -> bytes:
    """The same log as AgentDojo 0.1.35 writes it (v1.k14: content blocks, placeholder_args, version fields)."""
    doc = json.loads(_log(pipeline_name))
    for message in doc["messages"]:
        if message["content"] is not None:
            message["content"] = [{"type": "text", "content": message["content"]}]
        for call in message.get("tool_calls") or ():
            call["placeholder_args"] = None
        if message["role"] == "tool":
            message["tool_call"]["placeholder_args"] = None
    doc["messages"][-1]["tool_calls"] = []
    doc.update(benchmark_version="v1.2.1", evaluation_timestamp="2026-08-17 10:22:40", agentdojo_package_version="0.1.35")
    return json.dumps(doc, indent=4).encode("utf-8")


def _run(source: str, root: Path, out: Path, part: str, **vouch: Any) -> tuple[Any, list[dict[str, Any]]]:
    with CorpusWriter(out) as corpus:
        report = import_source(source, LocalTree(root), corpus=corpus, part=part, until="aer", in_process=True,
                               pin_check=support.vouch(root, **vouch))
    partial = Path(str(out) + ".partial")
    register = [json.loads(line) for line in (partial / "register.jsonl").read_text().splitlines()]
    return report, register


def test_an_uncovered_account_directory_is_held(tmp_path):
    """agentdojo-upstream declares no redaction rule: the account-path file is held, the other one is mapped."""
    root = tmp_path / "in"
    plain = "runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_2.json"
    held = f"runs/_ceph_ssd_students_{ACCOUNT}_qwen3_5/banking/user_task_1/important_instructions/injection_task_2.json"
    for rel, name in ((plain, "gpt-4o-2024-05-13"), (held, held.split("/")[1])):
        support._write(root, rel, _log(name))
    report, register = _run("agentdojo", root, tmp_path / "c", "head")
    assert report.counters["mapped"] == 1
    (row,) = [r for r in register if r["code"] == "select.redaction_pending"]
    assert "munged_cluster in segment 1" in row["detail"] and ACCOUNT not in row["detail"]


@pytest.mark.usefixtures("environmentoptim_registered")  # excluded (D-901): registered for the test only
def test_environmentoptim_maps_its_redacted_arms_by_their_rows(tmp_path):
    """Item 106: the profile's rule covers the munged cluster directory, so the file is mapped under its arm row
    (Qwen3.5-9B) and no account form reaches the AER; an uncovered shape is still held."""
    root = tmp_path / "in"
    arm = "benign_injection/10dataset/checkpoint_1"
    covered_dir = f"_ceph_ssd_students_{ACCOUNT}_qwen3_5"
    good = f"runs/{arm}/{covered_dir}/banking/user_task_1/important_instructions/injection_task_2.json"
    bad = f"runs/_home_{ACCOUNT}_x/banking/user_task_1/important_instructions/injection_task_2.json"
    support._write(root, good, _v1_log(covered_dir))
    support._write(root, bad, _v1_log("x"))
    report, register = _run("environmentoptim-agentdojo", root, tmp_path / "c", "head", repo=EO_REPO, commit=EO_COMMIT)
    assert report.counters["mapped"] == 1
    assert [r["detail"] for r in register if r["code"] == "select.redaction_pending"] == [
        "account-path shape (munged_home in segment 1) with no covering redaction rule (D-510, item 108)"]
    partial = tmp_path / "c.partial"
    (row,) = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    data = (partial / row["paths"]["aer"]).read_bytes()
    assert ACCOUNT.encode() not in data
    agent = next(r for r in map(json.loads, data.splitlines()) if r.get("id") == "agent")
    assert agent["model"]["requested"] == "Qwen3.5-9B"


@pytest.mark.usefixtures("environmentoptim_registered")  # excluded (D-901): registered for the test only
def test_a_degenerate_unit_under_a_redacted_arm_holds_no_account(tmp_path):
    """A log the profile does not map (here a v0.k11 log; EnvironmentOptim declares v1.k14 only) is sealed degenerate;
    its header names the raw path too, and the profile's rule redacts it there (item 105)."""
    root = tmp_path / "in"
    covered_dir = f"_ceph_ssd_students_{ACCOUNT}_qwen3_5"
    rel = f"runs/benign_injection/10dataset/checkpoint_1/{covered_dir}/banking/user_task_1/important_instructions/injection_task_2.json"
    support._write(root, rel, _log(covered_dir))
    report, _register = _run("environmentoptim-agentdojo", root, tmp_path / "c", "head", repo=EO_REPO, commit=EO_COMMIT)
    assert report.counters["degenerate"] == 1
    partial = tmp_path / "c.partial"
    (row,) = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    assert ACCOUNT.encode() not in (partial / row["paths"]["aer"]).read_bytes()


def test_a_held_file_stays_in_the_listing_a_listing_pin_is_checked_against(tmp_path):
    """Pre-round review #7: the hold runs after RD-3's ``pin_candidates`` snapshot, so a listing pin is checked over the
    whole listing; the held file is registered, never imported, and no other file becomes ``blob_mismatch``."""
    import hashlib

    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import READERS
    from agentprov.adapters.runner import resolve_factory
    from agentprov.adapters.runner.importer import PinCheck, listing_sha256

    root = tmp_path / "tree"
    held = f"m/prov/home/{ACCOUNT}/y.transcript.json"
    files = {"m/prov/a/x.transcript.json": b"{}", held: b"[]"}
    for rel, data in files.items():
        support._write(root, rel, data)
    pin = {"role": "release", "kind": "git", "repo": "https://github.com/nickjones39/agentdojo-prov",
           "commit": "579a908354b93361efe0905ffb7623256aa96a06", "tree": "corpus/corpus-prov", "expected_files": 2,
           "listing_sha256": listing_sha256([(k, hashlib.sha256(v).hexdigest()) for k, v in files.items()])}
    profile = load_profile("adprov-v1")
    hook = resolve_factory(READERS[str(profile.data["import"]["dialect"])])().listing_origin
    check = PinCheck("listing", pin, listing_origin=hook)
    with CorpusWriter(tmp_path / "corpus") as writer:
        report = import_source("adprov", LocalTree(root), corpus=writer, profile_id="adprov-v1", part="release", pin=pin,
                               pin_check=check, in_process=True, until="aer")
    assert check.listing_ok
    assert [e for e in report.register if e["code"] == "raw.origin.blob_mismatch"] == []
    (row,) = [e for e in report.register if e["code"] == "select.redaction_pending"]
    assert "slashed_home" in row["detail"] and ACCOUNT not in row["detail"]  # the subject keeps the raw path (D-510)
