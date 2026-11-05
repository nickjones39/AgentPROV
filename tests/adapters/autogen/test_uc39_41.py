"""D-1063 (regen-batch row 176; review UC-39, UC-40, UC-41), autogen: a lone UTF-16 surrogate in a typed text field or an
object key is replaced by U+FFFD with a disclosure (the D-378 pass, ``autogen.lone_surrogate_replaced@1``); a string
over 1 MiB is not inlined (the D-934 pattern, ``autogen.content_not_inlined@1``); a token count outside the AER's
integer range stays out of the typed usage (verbatim in ``ext.autogen.usage_unmapped``). Before, the writer refused
each such run. Inputs are derived from the committed tool-arm fixture in memory, never written to disk."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import autogen_support as support
import pytest

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

LONE = "autogen.lone_surrogate_replaced@1"
NOT_INLINED = "autogen.content_not_inlined@1"
CUT = "cut mid-emoji \ud83d"
MIB = 1 << 20
BIG = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(MIB // 64 + 1))[: MIB + 1]


@pytest.fixture(autouse=True)
def _fixtures_present():
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed AutoGen fixtures are absent")


def _lines(data: bytes) -> list[Any]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _dump(rows: list[Any]) -> bytes:
    return "".join(json.dumps(r) + "\n" for r in rows).encode()  # ensure_ascii: a lone surrogate is an escape


def _map(row_change: Callable[[dict[str, Any]], None] | None = None,
         event_change: Callable[[dict[str, Any]], None] | None = None) -> support.Mapped:
    members = dict(support.fixture_members())
    rows = _lines(members[support.TOOL_ARM][0])
    run_id = rows[0]["run_id"]
    if row_change is not None:
        row_change(rows[0])
    members[support.TOOL_ARM] = (_dump(rows), members[support.TOOL_ARM][1])
    if event_change is not None:
        label = next(lb for lb in members if lb.endswith("results/phase6/tool/events.jsonl"))
        events = _lines(members[label][0])
        for e in events:
            if isinstance(e, dict) and e.get("run_id") == run_id:
                event_change(e)
        members[label] = (_dump(events), members[label][1])
    unit, aux = support.units(support.TOOL_ARM, members)[0]
    mapped = support.map_unit_of(unit, aux)
    assert "adapter_defect" not in mapped.codes() and not mapped.outcome.degenerate
    report = validate_records([*mapped.doc.records, mapped.doc.seal], store=None, catalogues=RuleRegistry.default(),
                              mode="release")
    assert report.ok, [(f.code, f.pointer) for f in report.findings][:5]
    return mapped


def _task_text(value: str) -> Callable[[dict[str, Any]], None]:
    """The run's task message (source user): the agents' texts must agree with the event log, the task's need not."""
    def change(row: dict[str, Any]) -> None:
        m = next(m for m in row["messages"] if m.get("type") == "TextMessage" and m.get("source") == "user")
        m["text"] = value
        m["raw"]["content"] = value
    return change


def _issue_ids(mapped: support.Mapped, code: str) -> list[str]:
    return [i for issue in mapped.issues if issue["code"] == code for i in issue["ids"]]


def _text_record(mapped: support.Mapped, pointer_value: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    (rec,) = [r for r in mapped.of("message") if any(pointer_value(p) for p in r.get("parts", ()))]
    return rec


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    mapped = _map(_task_text(CUT))
    rec = _text_record(mapped, lambda p: p.get("text") == "cut mid-emoji \N{REPLACEMENT CHARACTER}")
    k = next(i for i, p in enumerate(rec["parts"]) if p.get("text") == "cut mid-emoji \N{REPLACEMENT CHARACTER}")
    assert rec["evf"][f"/parts/{k}/text"] == "D" and f"{LONE}#/parts/{k}/text" in rec["rule"]
    assert rec["id"] in _issue_ids(mapped, "autogen.lone_surrogate_replaced")


def test_a_lone_surrogate_in_a_source_key_is_replaced():
    def change(row: dict[str, Any]) -> None:
        row["messages"][0]["raw"]["models_usage"] = {"k\ud800": 1}  # copied into ext.autogen.models_usage
    mapped = _map(change)
    assert "exec" in _issue_ids(mapped, "autogen.lone_surrogate_replaced")


def test_a_lone_surrogate_in_call_arguments_keeps_the_run():
    """The arguments string itself holds the lone surrogate (an escape in the run file): it is not UTF-8, so it is not
    decoded as JSON (``autogen.arguments_not_json``) and the typed ``args_raw`` is replaced."""
    def change(row: dict[str, Any]) -> None:
        m = next(m for m in row["messages"] if m.get("type") == "ToolCallRequestEvent")
        for c in m["raw"]["content"]:
            c["arguments"] = '{"q": "x \ud800"}'
    mapped = _map(change)
    (rec,) = [r for r in mapped.of("message") if any(p.get("t") == "tool_call" for p in r.get("parts", ()))][:1]
    k = next(i for i, p in enumerate(rec["parts"]) if p.get("t") == "tool_call")
    assert rec["parts"][k]["args_raw"] == '{"q": "x \N{REPLACEMENT CHARACTER}"}'
    assert f"{LONE}#/parts/{k}/args_raw" in rec["rule"] and rec["id"] in _issue_ids(mapped, "autogen.lone_surrogate_replaced")


def test_a_run_without_lone_surrogates_or_big_strings_cites_neither_rule():
    mapped = _map()
    assert not _issue_ids(mapped, "autogen.lone_surrogate_replaced") and not _issue_ids(mapped, "autogen.content_not_inlined")
    assert not any(r.startswith((LONE, NOT_INLINED)) for rec in mapped.records for r in rec.get("rule", ()))


def test_a_string_over_1_mib_is_not_inlined():
    mapped = _map(_task_text(BIG))
    raw = BIG.encode()
    digest = {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    rec = _text_record(mapped, lambda p: p.get("t") == "other" and p.get("value") == digest)
    k = next(i for i, p in enumerate(rec["parts"]) if p.get("t") == "other")
    assert rec["parts"][k] == {"t": "other", "type": "text", "value": digest}
    assert rec["evf"][f"/parts/{k}/value"] == "D" and f"{NOT_INLINED}#/parts/{k}/value" in rec["rule"]
    assert rec["id"] in _issue_ids(mapped, "autogen.content_not_inlined")


def test_a_string_of_exactly_1_mib_stays_inline():
    exact = BIG[:MIB]
    mapped = _map(_task_text(exact))
    assert _text_record(mapped, lambda p: p.get("text") == exact)
    assert not _issue_ids(mapped, "autogen.content_not_inlined")


@pytest.mark.parametrize("bad", [2**60, -1])
def test_a_count_outside_the_aer_range_stays_out_of_the_typed_usage(bad):
    def change(e: dict[str, Any]) -> None:
        if e.get("kind") == "llm_response" and isinstance(e.get("usage"), dict):
            e["usage"]["prompt_tokens"] = bad
    mapped = _map(event_change=change)
    calls = [mc for mc in mapped.of("model_call") if "usage_unmapped" in mc.get("ext", {}).get("autogen", {})]
    assert calls
    for mc in calls:
        assert "input_tokens" not in mc.get("usage", {})
        unmapped = mc["ext"]["autogen"]["usage_unmapped"]["prompt_tokens"]
        assert unmapped == ({"$int": str(bad)} if bad > 0 else bad)


def test_a_count_at_the_aer_limit_is_typed():
    top = 2**53 - 1

    def change(e: dict[str, Any]) -> None:
        if e.get("kind") == "llm_response" and isinstance(e.get("usage"), dict):
            e["usage"]["prompt_tokens"] = top
    mapped = _map(event_change=change)
    calls = [mc for mc in mapped.of("model_call") if "usage" in mc]
    assert calls and all(mc["usage"]["input_tokens"] == top for mc in calls)


# ------------------------------------------------------------------------------------------------ AU-RC-1, AU-RC-2, AU-NC-307
def _digest(text: str) -> dict[str, Any]:
    raw = text.encode("utf-8", "surrogatepass")
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def _citations_resolve(record: dict[str, Any]) -> None:
    from agentprov.aer.locators import pointer_exists

    for ref in record.get("rule", []):
        _rid, sep, pointer = ref.partition("#")
        assert not sep or pointer_exists(record, pointer) or pointer in record.get("unk", {}), ref
    for pointer in record.get("evf", {}):
        assert pointer_exists(record, pointer), pointer


def _arguments(value: str) -> Callable[[dict[str, Any]], None]:
    def change(row: dict[str, Any]) -> None:
        m = next(m for m in row["messages"] if m.get("type") == "ToolCallRequestEvent")
        for c in m["raw"]["content"]:
            c["arguments"] = value
    return change


def _call_record(mapped: support.Mapped) -> tuple[dict[str, Any], int]:
    rec = [r for r in mapped.of("message") if any(p.get("t") == "tool_call" for p in r.get("parts", ()))][0]
    return rec, next(i for i, p in enumerate(rec["parts"]) if p.get("t") == "tool_call")


def test_a_text_over_1_mib_with_a_lone_surrogate_moves_its_citation():
    """AU-RC-1 (D-1063): the D-378 citation at ``/parts/<k>/text`` follows the part to ``/parts/<k>/value``; before, it
    dangled (``aer.ref.dangling``) and the run sealed ``adapter_defect``."""
    mapped = _map(_task_text(BIG + "\ud83d"))
    rec = _text_record(mapped, lambda p: p.get("t") == "other")
    k = next(i for i, p in enumerate(rec["parts"]) if p.get("t") == "other")
    assert f"{LONE}#/parts/{k}/value" in rec["rule"] and f"{NOT_INLINED}#/parts/{k}/value" in rec["rule"]
    assert not any(r.endswith(f"#/parts/{k}/text") for r in rec["rule"])
    _citations_resolve(rec)


def test_an_arguments_string_over_1_mib_leaves_args_raw_for_ext():
    """AU-NC-307 (D-1063): a FunctionCall ``arguments`` string over 1 MiB put a digest object into the typed
    ``args_raw`` (``aer.schema.pattern``). The decoded ``args`` keep their own digest; ``args_raw`` leaves the part and its
    digest stands at ``ext.autogen.args_raw_not_inlined.<k>``, D under ``autogen.content_not_inlined@1``."""
    arguments = json.dumps({"q": BIG})
    mapped = _map(_arguments(arguments))
    rec, k = _call_record(mapped)
    part = rec["parts"][k]
    assert "args_raw" not in part and part["args"] == {"q": _digest(BIG)}
    assert rec["ext"]["autogen"]["args_raw_not_inlined"] == {str(k): _digest(arguments)}
    pointer = f"/ext/autogen/args_raw_not_inlined/{k}"
    assert rec["evf"][pointer] == "D" and f"{NOT_INLINED}#{pointer}" in rec["rule"]
    assert f"{NOT_INLINED}#/parts/{k}/args/q" in rec["rule"]
    assert rec["id"] in _issue_ids(mapped, "autogen.content_not_inlined")
    _citations_resolve(rec)


def test_a_utf16_argument_whose_base64_exceeds_1_mib_is_its_digest():
    """AU-RC-2 (D-1063): an argument value with a lone surrogate (an escape in the arguments JSON) is ``{"$utf16": ...}``
    in ``args``; when its base64 exceeds 1 MiB the whole value becomes the digest of the decoded text."""
    text = "a" * 400_000 + "\ud800"
    mapped = _map(_arguments(json.dumps({"q": text})))
    rec, k = _call_record(mapped)
    assert rec["parts"][k]["args"]["q"] == _digest(text) and isinstance(rec["parts"][k]["args_raw"], str)
    assert f"{NOT_INLINED}#/parts/{k}/args/q" in rec["rule"]
    _citations_resolve(rec)
