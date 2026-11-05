"""P4: ``verify --level rederive --sample`` stages and re-hashes only the raw closure of the sampled executions.

The corpus: FooBench traces imported from a split zip deposit (D-249), so every primary artefact is a **member** object
of the split descriptor (whose byte parts are objects of their own), and FooBench's mapper wrapped to **carve** a string
of the primary into a blob (D-218), as ``test_carved_blobs`` does. Two executions with disjoint primaries: the closure of
one must hold its member objects, their container, the container's parts and the carved blob with its source, and none of
the other execution's own objects; the verify report must be the one that staging every object gives. Fixture bytes are
read by the test, never printed. No network.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.foobench.mapper import FooMapper
from agentprov.adapters.runner.importer import ArchiveTree, import_source
from agentprov.corpus.derive import Derivation
from agentprov.corpus.writer import CorpusWriter
from agentprov.raw.fetch import part_recipes, verify_parts
from agentprov.raw.store import RawObjectStore

REPO = Path(__file__).resolve().parents[3]
FOO = REPO / "tests" / "fixtures" / "foobench"
DOI = "10.5281/zenodo.7"
#: the counters that count what was staged (P4 changes them, and only them)
STAGING = ("rederive_raw_copied", "rederive_raw_linked", "rederive_raw_verified")


@pytest.fixture
def carving(monkeypatch: pytest.MonkeyPatch) -> None:
    """FooBench's mapper carves its primary's task (line 0, ``/task``) into a blob (D-218): one blob per execution."""
    original = FooMapper.map
    pointer = "/task"

    def map_(self: Any, unit: Any, ctx: Any) -> list[dict[str, Any]]:
        records = [dict(r) for r in original(self, unit, ctx)]
        ref = ctx.carve({"line": 0, "p": pointer}, "utf8")
        artefact = next(r for r in records if r.get("k") == "artefact" and "content" in r)
        artefact["content"] = ref
        return records

    monkeypatch.setattr(FooMapper, "map", map_)


def _variant(trace: bytes) -> bytes:
    """Another execution: trace-001 with another task (distinct bytes, so a distinct primary object)."""
    first, rest = trace.split(b"\n", 1)
    header = json.loads(first)
    header["task"] = f"{header['task']}-b"
    return json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n" + rest


def _deposit(root: Path) -> tuple[dict[str, Any], ArchiveTree]:
    trace = (FOO / "trace-001.jsonl").read_bytes()
    members = {
        "deposit/a/traces/trace-001.jsonl": trace,
        "deposit/a/traces/sub-trace-001.jsonl": (FOO / "sub-trace-001.jsonl").read_bytes(),
        "deposit/a/traces/screenshot-0.png": (FOO / "screenshot-0.png").read_bytes(),
        "deposit/b/traces/trace-002.jsonl": _variant(trace),
        "deposit/README.txt": b"not selected\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    data = buf.getvalue()
    root.mkdir(parents=True)
    paths, parts = [], []
    for k, start in enumerate(range(0, len(data), 1500)):
        chunk = data[start : start + 1500]
        path = root / f"deposit.zip.part-{k:04d}"
        path.write_bytes(chunk)
        paths.append(path)
        parts.append({"file": path.name, "bytes": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest(),
                      "md5": hashlib.md5(chunk).hexdigest()})  # fmt: skip
    pin = {"role": "fixture", "kind": "zenodo", "doi": DOI, "record": 7, "file": "deposit.zip", "archive": "split-zip",
           "parts": parts}  # fmt: skip
    checked = verify_parts(lambda name: (root / name).open("rb"), part_recipes(pin))
    return pin, ArchiveTree.split([(p, sha, size) for p, (sha, size) in zip(paths, checked, strict=True)], pin=pin)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _hex(value: str) -> str:
    return value.removeprefix("sha256:")


@pytest.fixture
def corpus(tmp_path: Path, carving: None) -> Path:
    pin, tree = _deposit(tmp_path / "in")
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source("foobench", tree, corpus=writer, profile_id="foobench", part="fixture", pin=pin,
                               in_process=True)
    assert not report.failures and report.counters["mapped"] == 2, report.counters
    return tmp_path / "c.partial"


def _verify(root: Path, seed: str) -> Any:
    from agentprov.corpus.verify import verify_corpus
    from agentprov.stats.source import import_hooks

    return verify_corpus(root, level="rederive", sample=1, seed=seed, import_hooks=import_hooks(), in_process=True)


def _without_staging(document: dict[str, Any]) -> dict[str, Any]:
    return {**document, "counters": {k: v for k, v in document["counters"].items() if k not in STAGING}}


@pytest.mark.parametrize("seed", ["a", "b", "c", "d"])
def test_a_sample_stages_its_closure_and_reports_what_staging_everything_reports(corpus, monkeypatch, seed):
    rows = {row["ex"]: row for row in _jsonl(corpus / "executions.jsonl")}
    origins = _jsonl(corpus / "raw" / "origins.jsonl")
    members = {_hex(m["sha256"]): _hex(m["container"]) for m in _jsonl(corpus / "raw" / "members.jsonl") if m.get("sha256")}
    carved = {_hex(o["sha256"]): _hex(o["origin"]["from"]) for o in origins if o["origin"]["kind"] == "carved"}
    split = next(o for o in origins if o["origin"]["kind"] == "split")
    descriptor, parts = _hex(split["sha256"]), {_hex(p) for p in split["origin"]["parts"]}
    assert len(carved) == 2 and set(carved.values()) <= set(members)  # each carved from a member object

    verified: list[str] = []
    original_verify = RawObjectStore.verify

    def spy(self: RawObjectStore, sha256: str) -> int:
        verified.append(sha256)
        return original_verify(self, sha256)

    monkeypatch.setattr(RawObjectStore, "verify", spy)
    sampled = _verify(corpus, seed)
    closure = set(verified)
    verified.clear()
    with monkeypatch.context() as everything:
        everything.setattr(Derivation, "input_closure", lambda self: None)  # stage every object, as before P4
        full = _verify(corpus, seed)
    staged_all = set(verified)

    ex = sampled_ex(sampled, rows)
    mine = {_hex(r["sha256"]) for r in rows[ex]["raw"]}
    others = {_hex(r["sha256"]) for e, row in rows.items() if e != ex for r in row["raw"]} - mine
    primary = next(_hex(r["sha256"]) for r in rows[ex]["raw"] if r["role"] == "primary")
    blob = next(b for b, source in carved.items() if source == primary)
    # the closure: its own objects, the container of its member objects and the container's parts (D-249), and the
    # blob carved from its primary (D-218); none of the other execution's own objects
    assert primary in members and members[primary] == descriptor
    assert mine | {descriptor, blob} | parts <= closure
    assert not (others & closure) and others <= staged_all
    assert closure < staged_all
    assert sampled.counters["rederive_raw_verified"] == len(closure) < full.counters["rederive_raw_verified"]
    assert sampled.counters["rederive_identical"] + sampled.counters.get("rederive_unverified", 0) >= 1
    assert _without_staging(sampled.to_json()) == _without_staging(full.to_json())
    assert sampled.ok == full.ok


def sampled_ex(report: Any, rows: dict[str, Any]) -> str:
    """The sampled execution (``sample_executions`` with the report's seed)."""
    from agentprov.corpus.verify import sample_executions

    (ex,) = sample_executions(sorted(rows), 1, report.sample["seed"])
    return ex


def test_the_seeds_sample_each_execution(corpus):
    from agentprov.corpus.verify import sample_executions

    rows = sorted(row["ex"] for row in _jsonl(corpus / "executions.jsonl"))
    assert {sample_executions(rows, 1, seed)[0] for seed in "abcd"} == set(rows)
