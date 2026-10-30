"""The ``qwencode.json`` reader (docs/architecture D.24.1, D.24.2; D-570, D-577). Prints nothing of fixture content."""

from __future__ import annotations

import hashlib
import json

import pytest
import qwencode_support as support

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.qwencode.dialect import (
    API_SAMPLE,
    FLAG_TRUNCATED,
    QwenJsonReader,
    parse_label,
    parse_output,
)
from agentprov.adapters.runner.importer import _AuxListing
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, Origin
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

BASE = "results/Qwen/qwen3-coder-30b-a3b-instruct"


def test_label_grammar():
    f = parse_label(f"{BASE}/S2/bash/trajectory/qwen_17_23_sh_S2.json")
    assert f is not None and (f.prefix, f.target, f.language, f.scenario, f.payload, f.suffix) == ("", "S2", "bash", "17", "23", "sh")
    assert f.case_key == "17_23" and f.directory == f"{BASE}/S2/bash/trajectory"
    assert parse_label(f"/local/x/{BASE}/S1/python/trajectory/qwen_3_25_S1.json").prefix == "local/x/"  # type: ignore[union-attr]
    for bad in (f"{BASE}/S2/bash/trajectory/qwen_17_23_S1.json", f"{BASE}/S4/bash/trajectory/qwen_1_1_S4.json",
                f"{BASE}/S1/ruby/trajectory/qwen_1_1_S1.json", f"{BASE}/S1/python/trajectory/{API_SAMPLE}",
                "results/OH/m/S1/python/trajectory/qwen_1_1_S1.json"):
        assert parse_label(bad) is None, bad


class _Tree:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels

    def walk(self):
        for label in self.labels:
            yield CandidateArtefact(label, 1, Origin.local("/x/" + label))


def test_primaries_and_api_samples():
    profile = load_profile(support.PROFILE)
    d = f"{BASE}/S1/python/trajectory"
    labels = [f"{d}/qwen_1_2_S1.json", f"{d}/{API_SAMPLE}", f"{d}/._qwen_1_2_S1.json", f"{d}/qwen_1_2_S1.stderr.log"]
    chosen = [c.label for c in QwenJsonReader().iter_artefacts(_Tree(labels), profile)]  # type: ignore[arg-type]
    assert chosen == [f"{d}/qwen_1_2_S1.json"]  # the API sample is never a primary


def test_sniff_and_register_detail():
    reader, limits = QwenJsonReader(), IngestLimits()
    ok = reader.sniff(support.tree()[0][support.by_criterion("python")], label="", limits=limits)
    assert ok.match and ok.dialect == "qwencode.json" and ok.variant == "v0.21" and ok.flags == frozenset()
    empty = reader.sniff(b"", label="", limits=limits)
    assert empty.reasons == ("qwencode.empty_output",) and reader.register_detail(empty.reasons) == "qwencode.empty_output"
    other = json.dumps([{"type": "system", "subtype": "init", "qwen_code_version": "0.30.0"}]).encode()
    assert reader.sniff(other, label="", limits=limits).match  # every JSON array matches (NF-17): the mapper refuses it
    assert reader.sniff(b'{"a": 1}', label="", limits=limits).reasons == ("qwencode.sniff.not_array",)
    assert reader.sniff(b"not json", label="", limits=limits).reasons[0].startswith("ingest.")
    assert reader.register_detail(("qwencode.sniff.not_array",)) is None


def test_every_json_array_is_sealed():
    """NF-17 (regen item 123): a selected run output (a label in the D.24.1 grammar) that is a JSON array matches
    ``sniff``; one of an unsupported Qwen Code version is a degenerate AER with ``unsupported_variant``, one of the wrong
    shape a degenerate AER with ``unparseable_artefact`` (D.2.8 case 3), never ``select.not_execution_artefact``. Valid
    JSON that is not an array stays valid input of another kind (D.2.8 case 4)."""
    from agentprov.adapters.runner import NotOfDialect

    runs_files, supp_files = dict(support.tree()[0]), support.tree()[1]
    label = support.by_criterion("python")
    real = runs_files[label]
    init = {"type": "system", "subtype": "init", "qwen_code_version": "0.22.0"}
    cases = {
        "version 0.22": (json.dumps([init, {"type": "result", "subtype": "success"}]).encode(), "unsupported_variant"),
        "no version": (json.dumps([{"type": "system", "subtype": "init"}]).encode(), "unsupported_variant"),
        "real run, version 0.22": (json.dumps([{**m, "qwen_code_version": "0.22.0"} if i == 0 else m
                                               for i, m in enumerate(json.loads(real))]).encode(), "unsupported_variant"),
        "no init": (json.dumps([{"type": "assistant", "message": {}}, {"type": "result"}]).encode(), "unparseable_artefact"),
        "array of strings": (b'["a"]', "unparseable_artefact"),
        "empty array": (b"[]", "unparseable_artefact"),
    }
    for name, (data, code) in cases.items():
        runs_files[label] = data
        m = support.map_files(label, runs_files, supp_files)
        assert m.outcome.degenerate and code in m.codes(), (name, m.codes())
        assert m.header["task"]["task_id"] == parse_label(label).case_key  # type: ignore[union-attr]
    runs_files[label] = json.dumps({"type": "system", "subtype": "init", "qwen_code_version": "0.21.0"}).encode()
    with pytest.raises(NotOfDialect):
        support.map_files(label, runs_files, supp_files)


def test_auxiliary_plan():
    runs_files, supp_files = support.tree()
    label = support.by_criterion("python")
    f = parse_label(label)
    assert f is not None
    plan = support.plan(label, runs_files, supp_files)
    assert plan["score"] == f"supp:results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    assert plan["rules"] == "supp:OH_evaluation/execution_rules.md"
    assert ("dataset" in plan) == (f.target == "S1") and ("prompt" in plan) == (f.target != "S1")
    flat = QwenJsonReader().auxiliary_for(label, _AuxListing(sorted(runs_files) + sorted(supp_files), {}))
    assert flat["score"] == plan["score"].split(":", 1)[1]  # one tree holding both zips: plain labels
    assert QwenJsonReader().auxiliary_for("not/a/label", _AuxListing([], {})) == {}


CUT = 65536  # the harness's capture cap (qwencode:CaptureCut)
_INIT = {"type": "system", "subtype": "init", "qwen_code_version": "0.21.0", "cwd": "/app/caf\u00e9"}  # non-ASCII head
_TAIL = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "a}b\\\"c\u00e9"}], "usage": {"n": -1.5e+3}}},
         {"type": "user", "message": {"content": "x}y"}, "ok": True, "none": None, "f": False, "n": 12}]


def _cut(tail: list, at: int, *, head_extra: bytes = b"", raw: bytes | None = None) -> tuple[bytes, list]:
    """A 65,536-byte capture cut ``at`` bytes into the serialised ``tail`` messages (or the ``raw`` tail bytes):
    ``[init, pad, *tail]`` with the pad's text sized so that the cut falls there. Returns the bytes and the messages."""
    tail_bytes = json.dumps(tail, ensure_ascii=True).encode()[1:] if raw is None else raw  # without its "["
    def head(n: int) -> bytes:
        return json.dumps([_INIT, {"type": "assistant", "pad": "x" * n}]).encode()[:-1] + head_extra + b", "
    n = CUT - at - len(head(0))
    data = (head(n) + tail_bytes)[:CUT]
    assert len(head(n)) == CUT - at and len(data) == CUT
    return data, [_INIT, {"type": "assistant", "pad": "x" * n}, *tail]


def test_salvage_of_a_cut_output():
    limits = IngestLimits()
    full = json.dumps([{"type": "system", "subtype": "init"}, {"type": "assistant", "message": {"content": [{"t": "}"}]}},
                       {"type": "user", "message": {"content": "x}y"}}]).encode()
    whole = parse_output(full, limits)
    assert whole.cut is None and len(whole.messages) == 3
    tail_len = len(json.dumps(_TAIL).encode()) - 1
    ends = [len(json.dumps(_TAIL[: k + 1]).encode()) - 2 for k in range(len(_TAIL))]  # each tail element's end
    for at in range(1, tail_len - 1):  # every cut of the tail salvages the complete leading messages only
        data, msgs = _cut(_TAIL, at)
        part = parse_output(data, limits)
        kept = 2 + sum(1 for e in ends if e <= at)
        assert part.cut is not None and part.cut + part.dropped == CUT, at
        assert part.messages == msgs[:kept], at
    with pytest.raises(IngestError):
        parse_output(b'[{"type": "sys', limits)  # nothing complete to keep (and not a 64 KiB capture cut)
    with pytest.raises(MalformedArtefact):
        parse_output(b'[{"type": "user"}]', limits)
    cut = support.tree()[0][support.by_criterion("truncated_capture")]
    assert len(cut) == 65536
    item = next(QwenJsonReader().parse(cut, ArtefactRef("a0", hashlib.sha256(cut).hexdigest(), len(cut), "application/json",
                                                          Origin.local("/x/t.json")), limits=limits))
    assert item.flags == frozenset({FLAG_TRUNCATED}) and item.value["cut"] + item.value["dropped"] == 65536


def test_salvage_only_for_a_capture_cut():
    """NF-14 (regen item 120): only an output of exactly 65,536 bytes whose strict error is ``ingest.json.syntax`` at the
    end of the input (the token the cut leaves open) is salvaged; every other strict-loader rejection is re-raised, so
    the runner seals the D.2.8 case-3 degenerate AER instead of mapping a prefix and dropping the rest silently."""
    limits = IngestLimits()
    good, _msgs = _cut(_TAIL, 30)
    assert parse_output(good, limits).cut is not None
    small = good[: CUT - 1]  # the same cut, one byte short of the capture cap
    bad: dict[str, bytes] = {
        "not 65,536 bytes": small,
        "invalid UTF-8": _cut(_TAIL, 30, head_extra=b', {"t": "\xff"}')[0],
        "duplicate key": _cut(_TAIL, 30, head_extra=b', {"t": 1, "t": 2}')[0],
        "NaN": _cut(_TAIL, 30, head_extra=b', {"t": NaN}')[0],
        "syntax error before the cut": _cut(_TAIL, 30, head_extra=b', {"t" 1}')[0],
        "syntax error in the cut message": _cut([], 30, raw=b'{"type": "user" "message": "abcdefghijklmnopqrstuvwxyz')[0],
    }
    complete = json.dumps([_INIT, {"type": "assistant", "pad": ""}]).encode() + b"\n"
    bad["trailing data"] = complete + b"X" * (CUT - len(complete))
    for name, data in bad.items():
        assert len(data) == (CUT - 1 if name == "not 65,536 bytes" else CUT), name
        with pytest.raises(IngestError) as strict:
            strict_json_loads(data, limits)
        with pytest.raises(IngestError) as info:
            parse_output(data, limits)
        assert info.value.code == strict.value.code, name
    # mapped: the derived run is a degenerate AER (unparseable_artefact), not a salvaged prefix
    runs_files, supp_files = dict(support.tree()[0]), support.tree()[1]
    label = support.by_criterion("python")
    runs_files[label] = runs_files[label] + b"\nXYZ"
    m = support.map_files(label, runs_files, supp_files)
    assert "unparseable_artefact" in m.codes() and "salvage" not in m.header.get("ext", {}).get("qwencode", {})


def test_salvage_is_bounded(monkeypatch):
    """NF-15 (regen item 121): salvage is one forward pass for the element boundaries and one strict parse of the kept
    prefix (plus one per kept message to check its span): an adversarial capture cut (hundreds of messages with ``}`` in
    their strings, the cut inside a string of 3,000 ``}``) costs O(messages) strict parses and well under a second."""
    import time

    from agentprov.adapters.qwencode import dialect

    msgs = [_INIT, *({"type": "user", "message": {"content": "}" * (k % 5)}} for k in range(600))]
    head = json.dumps(msgs).encode()[:-1] + b", "
    data = (head + b'{"type": "assistant", "text": "' + b"}" * 3000 + b"a" * CUT)[:CUT]
    calls = [0]
    real = dialect.strict_json_loads

    def counting(*args, **kwargs):
        calls[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(dialect, "strict_json_loads", counting)
    started = time.perf_counter()
    parsed = dialect.parse_output(data, IngestLimits())
    elapsed = time.perf_counter() - started
    assert parsed.messages == msgs and parsed.cut == len(head) - 2 and parsed.cut + parsed.dropped == CUT
    assert calls[0] <= len(msgs) + 3, calls[0]
    assert elapsed < 1.0, elapsed
