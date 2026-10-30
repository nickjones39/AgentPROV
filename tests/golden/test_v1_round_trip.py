"""Gates A1 and A2: transcript/v1 -> AER -> transcript/v1 view, from the AER alone (J.3.2; K.7.2; DoD Q.5; AD-02).

For every golden pair::

    A  = map(raw artefact)                                     # adapter adprov.transcript_v1, profile adprov-v1
    A1: jcs(render(A)) == jcs(strict_json_loads(B))            # JCS bytes: value identity
    A2: serialise(render(A)) == B                              # bytes: byte identity

Both compare byte strings, never decoded values with ``==`` (K.1(9)). The view runs on an AER read back from disk with
every file-opening function patched to raise, so it provably reads nothing from raw (K.7.1 step 2). Each AER passes the
release-mode validator with its locators resolved against the digest-checked artefact; mapping is repeated in a T1
worker and must give the same file bytes (determinism across processes, C.11.7).

Golden inputs: ``agentprov.testing.golden.golden_dir()`` (``$AGENTPROV_GOLDEN_DIR``, default
``tests/fixtures/agentdojo_prov_v1/golden``), in the repository index layout (J.2.2) or the research workspace's
``golden_index.json``. The four MIG-10 hazard pairs (R-59) are read from the frozen baseline corpus when
``$AGENTPROV_BASELINE_CORPUS`` names the old repository and the workspace index lacks them. Gate B1 (the compat graph from
the rendered view) runs when the compat port is importable. Failures print ids, pointers and sha256 values only.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_artefact, seal_job_result
from agentprov.adapters.types import Origin
from agentprov.aer.reader import load_aer
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import jcs_bytes
from agentprov.testing import golden
from agentprov.views.transcript_v1 import render, serialise

BASELINE_COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"
BASELINE_ENV = "AGENTPROV_BASELINE_CORPUS"
#: J.2.1 (R-59): the MIG-10 hazard pairs, by stem relative to the tree root, with their transcript sha256 prefixes.
MIG10 = {
    "R09": ("corpus-prov", "meta-llama_llama-3.3-70b-instruct/prov/important_instructions/"
            "workspace_user_task_10_x_injectiontask7_injection", "5ff4202511e75ab6"),
    "R10": ("corpus-prov", "google_gemini-2.5-flash/prov/injecagent/workspace_user_task_7_x_injectiontask9_injection",
            "b9f1f0a257db09cf"),
    "C08": ("corpus-og-agentdojo-runs-prov", "gpt-4o-2024-05-13-transformers_pi_detector/prov/benign/"
            "workspace_user_task_33_benign", "982b2700fb1a5b43"),
    "C09": ("corpus-og-agentdojo-runs-prov", "gpt-4o-2024-05-13/prov/important_instructions_no_model_name/"
            "banking_user_task_11_x_injectiontask2_injection", "8423069c006e2a9d"),
}


class Pair(NamedTuple):
    id: str
    transcript: Path
    graph: Path
    sha256: str  # full hex, or a 16-hex prefix for the MIG-10 pairs read from the baseline corpus
    corpus_relpath: str


def _pairs() -> list[Pair]:
    root = golden.golden_dir()
    index = root / "golden_index.json"
    pairs: list[Pair] = []
    if index.is_file():
        data = json.loads(index.read_bytes())
        if isinstance(data, dict):
            for t in data["traces"]:
                source = str(t["source_transcript"])
                relpath = source.split("/corpus/", 1)[1] if "/corpus/" in source else t["golden_transcript"]
                pairs.append(Pair(t["id"], root / t["golden_transcript"].removeprefix("golden/"),
                                  root / t["golden_graph"].removeprefix("golden/"), t["transcript_sha256"], relpath))
        else:
            fixtures = root.parent.parent
            for entry in data:
                if entry.get("kind") != "v1_pair":
                    continue
                files = {f["role"]: f for f in entry["files"]}
                relpath = str(entry.get("origin", {}).get("corpus_relpath") or files["v1_transcript"]["path"])
                pairs.append(Pair(entry["id"], fixtures / files["v1_transcript"]["path"],
                                  fixtures / files["compat_graph"]["path"], files["v1_transcript"]["sha256"], relpath))
    baseline = os.environ.get(BASELINE_ENV, "").strip()
    have = {p.id for p in pairs}
    if baseline:
        corpus = Path(baseline).expanduser() / "corpus"
        for pair_id, (tree, stem, prefix) in MIG10.items():
            if pair_id not in have and (corpus / tree / f"{stem}.transcript.json").is_file():
                rel = f"{tree}/{stem}"
                pairs.append(Pair(pair_id, corpus / f"{rel}.transcript.json", corpus / f"{rel}.json", prefix,
                                  f"{rel}.transcript.json"))
    return pairs


PAIRS = _pairs()


def _require() -> None:
    if not PAIRS:
        reason = golden.golden_skip_reason() or "golden fixtures not found"
        if os.environ.get("CI"):
            pytest.fail(reason)
        pytest.skip(reason)


def _ids() -> list[Any]:
    return [pytest.param(p, id=p.id) for p in PAIRS] or [pytest.param(None, id="no-golden-fixtures")]


def _origin(pair: Pair) -> Origin:
    return Origin.corpus("AgentDojo-PROV", "2.3", pair.corpus_relpath, producer_commit=BASELINE_COMMIT)


def _source(pair: Pair) -> bytes:
    raw = pair.transcript.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest.startswith(pair.sha256), f"{pair.id}: fixture sha256 {digest} does not match the index"
    return raw


class _Store:
    def __init__(self, raw: bytes) -> None:
        self.sha, self.raw = hashlib.sha256(raw).hexdigest(), raw

    def has(self, sha256: str) -> bool:
        return sha256 == self.sha

    def size(self, sha256: str) -> int:
        return len(self.raw)

    def read_bytes(self, sha256: str) -> bytes:
        return self.raw


_MAPPED: dict[str, bytes] = {}


def _aer(pair: Pair, tmp: Path) -> tuple[bytes, Any]:
    """The pair's AER bytes and the document read back from disk (mapped once per session)."""
    if pair.id not in _MAPPED:
        outcome, _ = map_artefact(_source(pair), _origin(pair), profile_id="adprov-v1")
        assert not outcome.degenerate, f"{pair.id}: degenerate AER ({outcome.error_code})"
        _MAPPED[pair.id], _info = aer_bytes(outcome)
    path = tmp / f"{pair.id}.aer.jsonl"
    path.write_bytes(_MAPPED[pair.id])
    return _MAPPED[pair.id], load_aer(path)


def _render_without_raw(document: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """``render`` with ``open``, ``io.open`` and ``Path.read_bytes``/``read_text``/``open`` patched to raise."""

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the transcript/v1 view tried to open a file: it must read nothing from raw (AD-02)")

    # the field table is package data, read once and cached; load it before the patch (it is not raw evidence)
    from agentprov.views import transcript_v1 as view

    view.field_table(), view.usage_map(), view.layout("meta")

    with monkeypatch.context() as patch:
        for target, name in ((builtins, "open"), (io, "open"), (Path, "read_bytes"), (Path, "read_text"), (Path, "open")):
            patch.setattr(target, name, refuse)
        return render(document)


def test_the_golden_set_has_released_and_converted_pairs():
    _require()
    ids = {p.id for p in PAIRS}
    assert {f"R{n:02d}" for n in range(1, 9)} | {f"C{n:02d}" for n in range(1, 8)} <= ids


@pytest.mark.parametrize("pair", _ids())
def test_gate_a1_jcs_value_identity(pair: Pair, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _require()
    raw = _source(pair)
    _data, document = _aer(pair, tmp_path)
    rendered = _render_without_raw(document, monkeypatch)
    produced, expected = jcs_bytes(rendered), jcs_bytes(strict_json_loads(raw))
    golden.assert_bytes_equal(expected, produced, what=f"{pair.id} A1 (JCS of render(map(v1)) vs JCS of v1)")


@pytest.mark.parametrize("pair", _ids())
def test_gate_a2_byte_identity(pair: Pair, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _require()
    raw = _source(pair)
    _data, document = _aer(pair, tmp_path)
    produced = serialise(_render_without_raw(document, monkeypatch))
    golden.assert_bytes_equal(raw, produced, what=f"{pair.id} A2 (serialise(render(map(v1))) vs v1)")


@pytest.mark.parametrize("pair", _ids())
def test_mapped_aer_passes_the_release_validator(pair: Pair, tmp_path: Path):
    _require()
    raw = _source(pair)
    data, _document = _aer(pair, tmp_path)
    profile = load_profile("adprov-v1")
    validator = AerValidator(store=_Store(raw), catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(profile.id, profile.version): profile.sha256})
    for line in data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok, f"{pair.id}: {sorted({f.code + ' ' + f.pointer for f in report.errors})}"
    assert report.passed and not report.skipped, f"{pair.id}: skipped {report.skipped}"


def test_mapping_in_t1_workers_gives_the_same_bytes(tmp_path: Path):
    """The ``map`` job in spawned workers seals byte-identical AER to the in-process path (C.11.7; G.4.8)."""
    _require()
    from agentprov.io.workers import Job, WorkerPool
    from agentprov.raw.store import RawObjectStore

    store = RawObjectStore(tmp_path / "raw")
    jobs = []
    for pair in PAIRS:
        put = store.put(_source(pair), ext="json")
        jobs.append(Job(key=pair.id, kind="map", inputs=({"sha256": put.sha256, "role": "primary"},),
                        params={"profile": "adprov-v1", "origin": _origin(pair).to_json()}))
    pool = WorkerPool(workers=2, store_root=store.objects_dir)
    by_key = {r.key: r for r in pool.run(jobs)}
    for pair in PAIRS:
        result = by_key[pair.id]
        assert result.ok, f"{pair.id}: {result.error!r}"
        info = seal_job_result(result.json, tmp_path / f"{pair.id}.aer.jsonl")
        expected, _ = _aer(pair, tmp_path)
        assert (tmp_path / f"{pair.id}.aer.jsonl").read_bytes() == expected, f"{pair.id}: worker AER differs"
        assert info.n_records == len(expected.splitlines())


@pytest.mark.parametrize("pair", _ids())
def test_gate_b1_compat_graph_from_the_view(pair: Pair, tmp_path: Path):
    """J.3.3 B1: the compat oracle on ``render(map(v1))`` reproduces the stored graph bytes."""
    _require()
    compat = pytest.importorskip("agentprov.prov.compat.adprov_v2_3")
    if not pair.graph.is_file():
        pytest.skip(f"{pair.id}: no stored graph")
    _data, document = _aer(pair, tmp_path)
    produced = compat.SPEC.serialise(compat.SPEC.build(render(document)))
    golden.assert_bytes_equal(pair.graph.read_bytes(), produced, what=f"{pair.id} B1 (compat graph from the view)")
