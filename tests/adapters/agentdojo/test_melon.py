"""MELON defence messages (quirk ``agentdojo.melon_defence_messages``, hook ``hooks/melon.py``; pre-check
PC-melon-agentdojo-03/04, D-586; regeneration-batch item 113).

The stop and block replies are tested on the real fixtures. The fixtures hold no MELON-R warning, so the insert case is
tested on a real fixture with a synthetic warning inserted at index 0 and a profile variant that lists that synthetic
text's digest in place of a logged one. Failures print ids and tokens only."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import phase10d_support as p10d

from agentdojo_support import map_bytes
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.io.canonical import sha256_hex

MELON = next(s for s in p10d.SOURCES if s.name == "melon")
STOP = "2159212be3c9e6d9584b4b11635bed85d81df6951c7c2722e9656fab3fb0a796"
BLOCK = "c839063e917cfa9e1a8392af446872912442b35abd88ac6372b91b76348fe503"
RECOVERY = "82ce7af3a0fbff78e1479e6a93b5cd6f9c0dbce863d19280fca59d20ecbb18bd"
WARNING = "Synthetic defence warning."
AUTHORED = "agentdojo.defence_authored_message@1"


def _text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list) and all(isinstance(b, dict) and b.get("type") == "text" for b in content):
        return "\n".join(str(b.get("content")) for b in content)
    return None


def _digest(content: Any) -> str | None:
    text = _text(content)
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


def test_the_stop_message_is_a_terminate_decision_by_the_defence():
    seen: set[str] = set()
    for entry in p10d.fixture_entries(MELON):
        m = p10d.map_fixture(MELON, entry)
        p10d.ok(m)
        doc = json.loads(p10d.fixture_bytes(MELON, entry))
        last = len(doc["messages"]) - 1
        final = m.get(f"m{last}")
        digest = _digest(doc["messages"][last].get("content")) if doc["messages"][last]["role"] == "assistant" else None
        if digest not in (STOP, BLOCK):
            assert not [r for r in m.of_kind("decision") if r.get("verdict") == "terminate"], entry["original_path"]
            continue
        seen.add(digest)
        (dc,) = [r for r in m.of_kind("decision") if r.get("verdict") == "terminate"]
        assert final["actor"] == dc["actor"] == "def0" and final["generated_by"] == dc["id"]
        assert dc["rule"][0] == AUTHORED and dc["ev"] == "I" and dc["unk"]["/original"] == "overwritten"
        mc = m.get(dc["subject"])
        assert mc["k"] == "model_call" and mc["actor"] == "agent"  # the model call is kept
        assert not [r for r in m.records if r.get("generated_by") == mc["id"]]  # its reply is not recorded
        assert f"{AUTHORED}#/actor" in final["rule"] and final["evf"]["/actor"] == "I"
    assert seen == {STOP, BLOCK}


def _with_insert(defence_dir: str) -> tuple[bytes, str]:
    """A real fixture of ``defence_dir`` with a synthetic warning inserted at index 0 (as MELON-R inserts its own)."""
    entry = next(e for e in p10d.fixture_entries(MELON) if f"/{defence_dir}/" in e["original_path"])
    doc = json.loads(p10d.fixture_bytes(MELON, entry))
    doc = copy.deepcopy(doc)
    doc["messages"].insert(0, {"role": "system", "content": [{"type": "text", "content": WARNING}]})
    return json.dumps(doc, indent=4).encode("utf-8"), entry["original_path"]


def _profile_listing_the_synthetic_warning() -> Any:
    text = (p10d.REPO / "src/agentprov/adapters/agentdojo/profiles/melon-agentdojo.profile.toml").read_text(encoding="utf-8")
    assert RECOVERY in text
    synthetic = hashlib.sha256(WARNING.encode("utf-8")).hexdigest()
    return parse_profile(text.replace(RECOVERY, synthetic).encode("utf-8"), source="test-variant")


def test_a_recovery_insert_is_the_defence_and_the_default_prompt_stays_the_harness():
    raw, path = _with_insert("gpt-4o-mini-2024-07-18-melon_r")
    m = map_bytes(raw, path, profile=_profile_listing_the_synthetic_warning())
    p10d.ok(m)
    insert, prompt = m.get("m0"), m.get("m1")
    assert insert["role"] == prompt["role"] == "system"
    assert insert["actor"] == "def0" and f"{AUTHORED}#/actor" in insert["rule"] and insert["evf"]["/actor"] == "I"
    assert "ext" not in insert  # a defence insert carries no prompt-variant label
    assert prompt["actor"] == "bench" and "agentdojo.system_prompt_by_digest@1#/actor" in prompt["rule"]
    assert prompt["ext"]["agentdojo"]["system_prompt_variant"] == "agentdojo_default"
    assert not m.issues("agentdojo.system_prompt_unrecognised")


def test_an_insert_of_another_defence_keeps_the_positional_rule():
    """The synthetic warning is listed for MELON-R only; in a base-MELON file it is not attributed to the defence."""
    raw, path = _with_insert("gpt-4o-2024-05-13-melon_sm")
    m = map_bytes(raw, path, profile=_profile_listing_the_synthetic_warning())
    p10d.ok(m)
    assert m.get("m0")["actor"] == "bench" and m.issues("agentdojo.system_prompt_unrecognised")
    assert "actor" not in m.get("m1")  # a later system message with no hook author stays unattributed


def test_the_profile_lists_the_logged_texts_and_drops_the_old_prompt_label():
    profile = load_profile("melon-agentdojo")
    assert profile.version == 2
    text = (p10d.REPO / "src/agentprov/adapters/agentdojo/profiles/melon-agentdojo.profile.toml").read_bytes()
    assert sha256_hex(text) == profile.sha256
    assert [v.label for v in family_table(profile).prompt_variants] == ["agentdojo_default"]
    assert all(d.encode() in text for d in (STOP, BLOCK, RECOVERY))


def test_a_lone_surrogate_in_a_system_message_never_breaks_the_hook():
    """The full suite caught it (test_item7_surrogates): the hook's digest is taken with surrogatepass, so a lone
    surrogate (D-23) in a system message the hook reads (here a later one, in a MELON-R file) is no adapter defect, and
    the text matches no listed digest. (A lone surrogate in the first system message still breaks the pre-existing
    prompt-variant digest, with or without the hook; reported to the family owner.)"""
    entry = next(e for e in p10d.fixture_entries(MELON) if "/gpt-4o-mini-2024-07-18-melon_r/" in e["original_path"])
    doc = json.loads(p10d.fixture_bytes(MELON, entry))
    doc["messages"].insert(1, {"role": "system", "content": "warning \ud800 text"})
    m = map_bytes(json.dumps(doc, indent=4).encode("utf-8"), entry["original_path"], profile=load_profile("melon-agentdojo"))
    assert "adapter_defect" not in m.codes and not m.outcome.degenerate
    assert "actor" not in m.get("m1")  # a later system message no hook attributes stays unattributed, as in version 1
