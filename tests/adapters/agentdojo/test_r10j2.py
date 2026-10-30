"""R-10j-2 (regeneration-batch item 95, D.6.14 item 11): the agentdyn part ``history``, the 621 logs (620
drift.k18.messages, one v1.k14.incomplete) of ``runs/gpt-4o-mini-2024-07-18-drift/`` at AgentDyn 785b9127, which the head
pin's directory of the same name replaced.

A part with its own pin selects its pin's files whatever ``variant_labels`` says (the runner), and its files resolve
identity against the part's own table (``[identity] part_tables``), chosen by their git origin commit. Synthetic placement
of a pinned AgentDyn variant C fixture; no history blob is in the repository."""

from __future__ import annotations

import json
from typing import Any

import pytest
from test_agentdyn import FIXTURES, REPO_URL, _fixture

from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import NotSelected, map_artefact_total, own_pin_part
from agentprov.adapters.types import Origin
from agentprov.testing import golden

HISTORY = "785b9127961c438f4db889c717949e2390dfee19"
HEAD = "5353cf7615b135cace8d07c8f12dac53a16b6db3"
DIRECTORY = "gpt-4o-mini-2024-07-18-drift"
V2 = "418fbcbd38a9"  # the agentdyn profile v2 bytes (main before item 95), archived


def _history_log(pipeline_name: str = "gpt-4o-mini-2024-07-18") -> tuple[bytes, str]:
    """A variant C (drift.k18.messages) fixture moved under the history directory, with the pipeline name its logs carry."""
    entry = _fixture("gpt-5.1-2025-11-13-drift")
    doc: dict[str, Any] = json.loads((FIXTURES / entry["sample_file"]).read_bytes())
    doc["pipeline_name"] = pipeline_name
    path = entry["original_path"].replace("gpt-5.1-2025-11-13-drift", DIRECTORY)
    assert f"runs/{DIRECTORY}/" in path
    return json.dumps(doc, indent=4).encode("utf-8"), path


def _map(raw: bytes, path: str, commit: str, part: str) -> Any:
    origin = Origin.git(REPO_URL, commit, path, golden.git_blob_sha1(raw))
    outcome, _unit = map_artefact_total(raw, origin, profile_id="agentdyn", part=part)
    assert not outcome.degenerate
    return outcome


def _agent(outcome: Any) -> dict[str, Any]:
    return next(r for r in outcome.records if r.get("id") == "agent")


def _codes(outcome: Any) -> set[str]:
    return {i["code"] for i in outcome.issues}


def test_profile_3_adds_the_part_and_keeps_version_2():
    profile = load_profile("agentdyn")  # v4 since D-933 (part b's census); v3 is archived as round 1 records it
    assert profile.version == 4 and "history" in profile.data["profile"]["parts"]
    assert load_profile("agentdyn", 3).sha256.startswith("b827b7d987d679306a66")
    (pin,) = [p for p in profile.data["source"]["pins"] if p["role"] == "history"]
    assert (pin["part"], pin["commit"], pin["expected_files"]) == ("history", HISTORY, 621)
    assert load_profile("agentdyn", 2).sha256.startswith(V2)
    assert list(family_table(profile).part_rows) == [HISTORY]
    assert family_table(load_profile("agentdyn", 2)).part_rows == {}


def test_a_part_with_its_own_pin_selects_its_files():
    profile = load_profile("agentdyn")
    assert own_pin_part(profile, "history") and not own_pin_part(profile, "a") and not own_pin_part(profile, "c")
    raw, path = _history_log()
    assert _map(raw, path, HISTORY, "history")
    with pytest.raises(NotSelected):  # the head importer of part a still leaves C files to part c
        map_artefact_total(raw, Origin.git(REPO_URL, HEAD, path, golden.git_blob_sha1(raw)), profile_id="agentdyn", part="a")


def test_an_own_pin_part_never_selects_another_commits_files():
    """Bug pass NF-30: part ``history`` selects the files of its pin only. A head file named under it (``--snapshot history
    --pin head``) is not selected, whatever its variant, so the head's 47,723 files cannot become part ``history``."""
    raw, path = _history_log()
    with pytest.raises(NotSelected, match="its own pin"):
        map_artefact_total(raw, Origin.git(REPO_URL, HEAD, path, golden.git_blob_sha1(raw)), profile_id="agentdyn",
                           part="history")
    assert _map(raw, path, HISTORY, "history")  # the same bytes at the part's pin are selected


def test_a_history_file_resolves_against_the_history_row():
    raw, path = _history_log()
    outcome = _map(raw, path, HISTORY, "history")
    assert _agent(outcome)["model"]["requested"] == "gpt-4o-mini-2024-07-18"
    assert "agentdojo.pipeline_name_mismatch" not in _codes(outcome)
    defence = next(r for r in outcome.records if r.get("kind") == "defense")
    assert defence["name"] == "drift"


def test_the_same_directory_at_head_keeps_the_head_row():
    """At the head pin the directory holds variant A runs; its row names no pipeline_name, so the C log's differs from the
    directory and is reported: the head table was used, not the history one."""
    raw, path = _history_log()
    outcome = _map(raw, path, HEAD, "c")
    assert "agentdojo.pipeline_name_mismatch" in _codes(outcome)


def test_a_history_log_with_another_pipeline_name_is_reported():
    raw, path = _history_log("gpt-4o-mini")
    assert "agentdojo.pipeline_name_mismatch" in _codes(_map(raw, path, HISTORY, "history"))
