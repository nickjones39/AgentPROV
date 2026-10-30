"""The ``geminicli.stream_json`` reader (docs/architecture D.23.1, D.23.2; D-330, D-331). Prints nothing of fixture content."""

from __future__ import annotations

import geminicli_support as support
import pytest

from agentprov.adapters.geminicli.dialect import (
    SIBLING_ROLES,
    STREAM,
    VERDICT,
    GeminiStreamReader,
    parse_events,
    parse_label,
)
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner.importer import _AuxListing
from agentprov.adapters.types import CandidateArtefact, Origin
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits

ROOT = "RESULTS_build/cells"


def test_label_grammar():
    f = parse_label(f"{ROOT}/gemini_cli__glm-4.7-probe/SK-XSSESCAPE__m10/{STREAM}")
    assert f is not None and (f.root, f.scaffold, f.model, f.skeleton, f.variant) == (
        "RESULTS_build", "gemini_cli", "glm-4.7-probe", "SK-XSSESCAPE", "m10")
    assert f.directory == f"{ROOT}/gemini_cli__glm-4.7-probe/SK-XSSESCAPE__m10"
    assert f.manifest == "RESULTS_build/manifest.csv"
    assert parse_label(f"/local/x/{ROOT}/gemini_cli__MiniMax-M2/SK-SQLRAW__m01/{VERDICT}") is not None  # a prefix is tolerated
    for bad in (f"{ROOT}/gemini_cli/SK-X__m01/{STREAM}", f"{ROOT}/gemini_cli__m/SK-X__1/{STREAM}", f"x/gemini_cli__m/SK-X__m01/{STREAM}",
                f"{ROOT}/gemini_cli__m/sk-x__m01/{STREAM}"):
        assert parse_label(bad) is None, bad


class _Tree:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels

    def walk(self):
        for label in self.labels:
            yield CandidateArtefact(label, 1, Origin.local("/x/" + label))


def test_primary_is_stream_else_verdict():
    profile = load_profile(support.PROFILE)
    d1, d2 = f"{ROOT}/gemini_cli__MiniMax-M2/SK-A__m01", f"{ROOT}/gemini_cli__MiniMax-M2/SK-A__m02"
    other = f"{ROOT}/codex_cli__MiniMax-M2/SK-A__m01"
    labels = [f"{d1}/{STREAM}", f"{d1}/{VERDICT}", f"{d1}/fs_before.json", f"{d2}/{VERDICT}", f"{d2}/events.jsonl",
              f"{other}/{VERDICT}", "RESULTS_build/manifest.csv", "RESULTS_build/README.md", f"{d1}/._{STREAM}"]
    chosen = [c.label for c in GeminiStreamReader().iter_artefacts(_Tree(labels), profile)]  # type: ignore[arg-type]
    assert chosen == [f"{d1}/{STREAM}", f"{d2}/{VERDICT}"]  # the other scaffold's verdict is excluded (out of scope)


def test_sniff_classifies_streams_verdicts_and_empty():
    reader, limits = GeminiStreamReader(), IngestLimits()
    stream_dir = support.by_criterion("ok_with_text_and_calls")
    ok = reader.sniff(support.file_bytes(f"{stream_dir}/{STREAM}"), label="", limits=limits)
    assert ok.match and ok.dialect == "geminicli.stream_json" and ok.variant == "v1"
    empty = support.by_criterion("empty_stream")
    assert reader.sniff(support.file_bytes(f"{empty}/{STREAM}"), label="", limits=limits).reasons == ("geminicli.empty_stream",)
    verdict = reader.sniff(support.file_bytes(f"{stream_dir}/{VERDICT}"), label="", limits=limits)
    assert not verdict.match and verdict.reasons == ("geminicli.no_stream",)
    assert reader.register_detail(verdict.reasons) == "geminicli.no_stream"
    assert reader.sniff(b'{"type":"message"}\n', label="", limits=limits).reasons == ("geminicli.sniff.first_event",)
    assert reader.sniff(b"[1]\n", label="", limits=limits).reasons == ("geminicli.sniff.not_object",)
    assert reader.register_detail(("geminicli.sniff.first_event",)) is None


def test_auxiliary_plan_names_siblings_and_manifest():
    d = support.by_criterion("ok_with_text_and_calls")
    files = support.files_of(d)
    primary, plan = support.plan(d, {**files, "RESULTS_build/manifest.csv": b""})
    assert primary == f"{d}/{STREAM}"
    names = {label.rsplit("/", 1)[-1] for label in files} - {STREAM}
    assert plan == {**{SIBLING_ROLES[n]: f"{d}/{n}" for n in names}, "manifest": "RESULTS_build/manifest.csv"}
    _primary, without = support.plan(d, files)
    assert "manifest" not in without
    assert GeminiStreamReader().auxiliary_for("not/a/label", _AuxListing([], {})) == {}


def test_parse_fails_closed_on_framing():
    limits = IngestLimits()
    good = b'{"type":"init","timestamp":"t"}\n{"type":"result"}\n'
    assert [n for n, _e in parse_events(good, limits)] == [0, 1]
    with pytest.raises(IngestError):
        parse_events(good.replace(b"\n", b"\r\n"), limits)
    with pytest.raises(IngestError):
        parse_events(good[:-1], limits)  # no final newline
    with pytest.raises(MalformedArtefact):
        parse_events(b'{"type":"message"}\n', limits)
    with pytest.raises(MalformedArtefact):
        parse_events(b'{"type":"init"}\n[1]\n', limits)
    items = list(GeminiStreamReader().parse(good, _ref(good), limits=limits))
    assert len(items) == 1 and [e["line"] for e in items[0].value["events"]] == [0, 1]


def _ref(data: bytes):
    import hashlib

    from agentprov.adapters.types import ArtefactRef

    return ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), "application/x-ndjson", Origin.local("/x/s.jsonl"))
