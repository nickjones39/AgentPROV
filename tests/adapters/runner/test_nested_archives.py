"""Container members of archive inputs and declared nested archives (ingest-formats-3; D-380..D-387).

* **Depth 2 (D-380, R-10p-6).** An Inspect ``.eval`` (a container dialect) that is a member of an archive input (a split
  zip, a ``tar.zst``) is expanded at level 2 through the container path and mapped; D-200's exit-5 refusal is lifted.
* **Depth 3 (D-381 (a), D-382, D-383).** A zip inside the archive input, declared by ``[import] nested``, is stored as its
  own member object (streamed with commit-on-verify when it is above the global member bound) and expanded with the
  archive selection; its ``.eval`` members open at level 3 under the declared ``max_depth``.
* Chain labels and register subjects (D-384), duplicates (D-385), ``derivation.json`` with several ``expand`` entries
  (F-2), the re-map selection guard, resume, recompute, ``verify`` and determinism.

Every archive is built here from synthetic Inspect logs (``inspect_support``; no real sample, no fixture file). The
deflated members use compression level 0, as the real nested zips are (incompressible ``.eval`` inside), so that a byte
can be flipped inside a member without breaking its deflate stream.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import import_support as support
import pytest

import agentprov.adapters.runner as runner_pkg
import agentprov.adapters.runner.importer as importer
from agentprov.adapters.profiles import parse_profile
from agentprov.adapters.runner.importer import ArchiveTree, IdentityRefusedError, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.ingest.limits import KIB, IngestLimits
from agentprov.raw.fetch import part_recipes, verify_parts

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "adapters" / "inspect", _TESTS / "security"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
import inspect_support as insp  # noqa: E402
from format_support import tar_bytes, zstd_stream  # noqa: E402

SOURCE, PROFILE, PART = "agent-security-tools-survey", "survey-agentharm", "agentharm"
DOI = "10.5281/zenodo.7"
LOGS = "agentharm/results/m_s"  # the shipped profile's include is agentharm/results/**/*.eval
#: a global member bound small enough that every synthetic nested zip is streamed (D-383); .eval logs stay below it
SMALL = IngestLimits(max_member_bytes=64 * KIB)
#: incompressible, deterministic padding (40 KiB, below SMALL's bound; two of them make an inner zip above it)
FILLER = b"".join(hashlib.sha256(i.to_bytes(4, "big")).digest() for i in range(40 * 32))
NESTED = '''
[[import.nested]]
id = "zips"
pattern = "logs/*.zip"
max_member_bytes = 268435456
max_depth = 3
note = "synthetic nested zips"
'''


# ------------------------------------------------------------------------------------------------ building blocks
def _eval(n: int, *, samples: int = 1) -> bytes:
    """A synthetic, band-shaped Inspect log; ``n`` makes its bytes distinct (eval and sample ids)."""
    header = insp.synthetic_header()
    header["eval"]["eval_id"] = f"SyntheticEvalId{n:08d}"
    header["eval"]["run_id"] = f"SyntheticRunId{n:09d}"
    built = {}
    for k in range(samples):
        sample = insp.basic_sample(f"s{n}-{k}")
        sample["uuid"] = f"SynthUuid{n:06d}{k:07d}"
        built[f"s{n}-{k}_epoch_1.json"] = sample
    return insp.build_eval(header, built)


def _zip(members: Mapping[str, bytes], *, method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, (2026, 6, 10, 0, 0, 0))
            info.compress_type = method
            archive.writestr(info, data, compresslevel=0 if method == zipfile.ZIP_DEFLATED else None)
    return buf.getvalue()


def _split(root: Path, data: bytes, *, name: str = "logs.zip", parts: int = 3) -> tuple[dict[str, Any], ArchiveTree]:
    """``data`` cut into ``parts`` byte parts in ``root``, its Zenodo split pin and the verified tree (D-249)."""
    root.mkdir(parents=True, exist_ok=True)
    size = -(-len(data) // parts)
    chunks = [data[i : i + size] for i in range(0, len(data), size)]
    paths, declared = [], []
    for k, chunk in enumerate(chunks):
        path = root / f"{name}.part-{k:04d}"
        path.write_bytes(chunk)
        paths.append(path)
        declared.append({"file": path.name, "bytes": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest()})
    pin = {"role": "fixture", "kind": "zenodo", "doi": DOI, "record": 7, "file": name, "archive": "split-zip",
           "parts": declared}  # fmt: skip
    checked = verify_parts(lambda n: (root / n).open("rb"), part_recipes(pin))
    return pin, ArchiveTree.split([(p, sha, sz) for p, (sha, sz) in zip(paths, checked, strict=True)], pin=pin)


def _single(root: Path, data: bytes, name: str) -> tuple[dict[str, Any], ArchiveTree]:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    pin = {"role": "fixture", "kind": "zenodo", "doi": DOI, "record": 7, "file": name, "sha256": sha, "bytes": len(data)}
    return pin, ArchiveTree(root / name, pin=pin, sha256=sha, size=len(data))


def _profile(monkeypatch: pytest.MonkeyPatch, extra: str = NESTED, *, include: str = '["**/*.eval"]') -> Any:
    """The shipped survey profile with ``[import] nested`` added (a test variant; phase 10p's profile adopts it)."""
    text = (Path(importer.__file__).resolve().parents[1] / "inspect" / "profiles" / f"{PROFILE}.profile.toml").read_text()
    text = text.replace('include = ["agentharm/results/**/*.eval"]', f"include = {include}")
    text = text.replace("\n[family.inspect]\n", f"{extra}\n[family.inspect]\n", 1)
    profile = parse_profile(text.encode("utf-8"), source="test-variant")
    monkeypatch.setattr(importer, "load_profile", lambda _pid: profile)
    monkeypatch.setattr(runner_pkg, "load_profile", lambda _pid: profile)
    return profile


def _import(tree: Any, pin: dict[str, Any], corpus: Path, **kwargs: Any) -> Any:
    kwargs.setdefault("in_process", True)
    kwargs.setdefault("until", "aer")
    with CorpusWriter(corpus, limits=kwargs.get("limits")) as writer:
        return import_source(SOURCE, tree, corpus=writer, profile_id=PROFILE, part=PART, pin=pin, **kwargs)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _origins(partial: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _jsonl(partial / "raw" / "origins.jsonl"):
        out.setdefault(row["sha256"].removeprefix("sha256:"), []).append(row["origin"])
    return out


def _subjects(partial: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for entry in _jsonl(partial / "register.jsonl"):
        if "path" in entry["subject"]:
            out.setdefault(entry["code"], []).append(entry["subject"]["path"])
    return out


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------------ depth 2 (R-10p-6)
def test_eval_members_of_a_split_zip_are_expanded_at_level_2_and_mapped(tmp_path, monkeypatch):
    logs = {f"{LOGS}/a.eval": _eval(1, samples=2), f"{LOGS}/b.eval": _eval(2)}
    pin, tree = _split(tmp_path / "in", _zip({**logs, "README.txt": b"not selected\n"}))
    calls: list[str] = []
    for name in ("map_whole_files", "map_containers"):
        original = getattr(importer._Pipeline, name)
        monkeypatch.setattr(importer._Pipeline, name,
                            lambda self, batch, _o=original, _n=name: calls.append(_n) or _o(self, batch))
    report = _import(tree, pin, tmp_path / "c")
    assert not report.failures and report.counters["mapped"] == 3
    assert calls and set(calls) == {"map_containers"}  # D-380 review item 2: never the whole-file path
    partial = tmp_path / "c.partial"
    origins = _origins(partial)
    descriptor = next(sha for sha, os_ in origins.items() if os_[0]["kind"] == "split")
    for label, data in logs.items():
        (origin,) = origins[_sha(data)]
        assert origin["kind"] == "member" and origin["container"] == descriptor and origin["label"] == label
    members = _jsonl(partial / "raw" / "members.jsonl")
    assert {m["container"].removeprefix("sha256:") for m in members} == {descriptor, *(_sha(d) for d in logs.values())}
    for row in _jsonl(partial / "executions.jsonl"):
        header = json.loads((partial / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
        assert header["artifacts"][0]["origin"]["container"] in {_sha(d) for d in logs.values()}
    stages = json.loads((partial / "derivation.json").read_text())["stages"]
    assert [s["stage"] for s in stages] == ["expand", "expand", "aer"]  # the archive's and the .eval members' (F-2)


def test_eval_members_of_a_tar_zst_are_expanded_at_level_2(tmp_path):
    logs = {f"{LOGS}/a.eval": _eval(1)}
    pin, tree = _single(tmp_path / "in", zstd_stream(tar_bytes(list(logs.items()))), "logs.tar.zst")
    report = _import(tree, pin, tmp_path / "c")
    assert not report.failures and report.counters["mapped"] == 1


def test_an_archive_input_of_a_container_dialect_needs_an_include(tmp_path, monkeypatch):
    _profile(monkeypatch, "", include="[]")
    pin, tree = _split(tmp_path / "in", _zip({f"{LOGS}/a.eval": _eval(1)}))
    with pytest.raises(importer.AgentProvError) as refused:
        _import(tree, pin, tmp_path / "c")
    assert refused.value.code == "adapter.archive_input" and refused.value.exit_code == 5


# ------------------------------------------------------------------------------------------------ depth 3 (R-10p-1)
def _nested_input(tmp: Path, *, direct: Mapping[str, bytes] | None = None,
                  inner: Mapping[str, bytes] | None = None) -> tuple[dict[str, Any], ArchiveTree, bytes]:  # fmt: skip
    inner_zip = _zip({**(inner if inner is not None else {"logs/x.eval": _eval(10), "logs/y.eval": _eval(11)}),
                      "logs/filler-1.bin": FILLER, "logs/filler-2.bin": FILLER[::-1]})  # not selected; they make the
    # inner zip larger than SMALL's member bound
    outer = _zip({"logs/inner.zip": inner_zip, **(direct or {}), "logs/stdout.txt": b"run output\n"})
    pin, tree = _split(tmp / "in", outer)
    return pin, tree, inner_zip


def test_a_declared_nested_zip_is_stored_streamed_and_its_eval_members_open_at_level_3(tmp_path, monkeypatch):
    _profile(monkeypatch)
    pin, tree, inner_zip = _nested_input(tmp_path, direct={"logs/d.eval": _eval(3)})
    assert len(inner_zip) > SMALL.max_member_bytes  # streamed (D-383)
    report = _import(tree, pin, tmp_path / "c", limits=SMALL)
    assert not report.failures and report.counters["mapped"] == 3
    partial = tmp_path / "c.partial"
    origins = _origins(partial)
    descriptor = next(sha for sha, os_ in origins.items() if os_[0]["kind"] == "split")
    (zip_origin,) = origins[_sha(inner_zip)]  # the inner zip is its own member object (D-381 (a))
    assert zip_origin == {"container": descriptor, "crc32": f"{zipfile.crc32(inner_zip) & 0xFFFFFFFF:08x}",
                          "kind": "member", "label": "logs/inner.zip", "method": 8, "size": len(inner_zip)}  # fmt: skip
    for n, label in ((10, "logs/x.eval"), (11, "logs/y.eval")):
        (origin,) = origins[_sha(_eval(n))]
        assert origin["container"] == _sha(inner_zip) and origin["label"] == label
    stages = [s for s in json.loads((partial / "derivation.json").read_text())["stages"] if s["stage"] == "expand"]
    assert len(stages) == 3 and len({s["fn_digest"] for s in stages}) == 3  # input tree, nested zip, .eval members


def test_without_a_depth_allowance_the_nested_eval_is_refused_at_level_3(tmp_path, monkeypatch):
    _profile(monkeypatch, NESTED.replace("max_depth = 3\n", ""))
    pin, tree, _inner = _nested_input(tmp_path)
    report = _import(tree, pin, tmp_path / "c", limits=SMALL)
    assert report.counters["mapped"] == 0
    subjects = _subjects(tmp_path / "c.partial")
    assert sorted(subjects["ingest.archive.depth"]) == ["logs.zip!/logs/inner.zip!/logs/x.eval",
                                                        "logs.zip!/logs/inner.zip!/logs/y.eval"]


# ------------------------------------------------------------------------------------------------ differential
def _by_execution(partial: Path) -> dict[str, bytes]:
    return {row["ex"]: (partial / row["paths"]["aer"]).read_bytes() for row in _jsonl(partial / "executions.jsonl")}


def _records(aer: bytes) -> tuple[Any, list[bytes]]:
    """An AER without its source-profile digest: the header (``profile`` removed) and every record line (the seal
    covers the header, so it is left out)."""
    lines = aer.split(b"\n")
    header = json.loads(lines[0])
    header.pop("profile")
    return header, [line for line in lines[1:] if line and json.loads(line).get("k") != "seal"]


def _eval_rows(partial: Path, eval_sha: str) -> list[dict[str, Any]]:
    return [m for m in _jsonl(partial / "raw" / "members.jsonl") if m["container"] == "sha256:" + eval_sha]


def test_one_eval_gives_the_same_rows_and_aers_from_a_tree_a_split_zip_a_nested_zip_and_a_tar_zst(tmp_path, monkeypatch):
    log = _eval(7, samples=2)
    label = f"{LOGS}/a.eval"
    # (i) a file of a pinned tree (the git-tree container path, depth 1)
    root = tmp_path / "tree"
    (root / LOGS).mkdir(parents=True)
    (root / label).write_bytes(log)
    with CorpusWriter(tmp_path / "i") as writer:
        import_source(SOURCE, importer.LocalTree(root), corpus=writer, part=PART, in_process=True, until="aer",
                      pin_check=support.vouch(root, repo=support.SURVEY, commit=support.SURVEY_COMMIT))
    # (ii) a member of a split zip (depth 2); (iv) a member of a tar.zst (depth 2)
    pin, tree = _split(tmp_path / "in2", _zip({label: log}))
    _import(tree, pin, tmp_path / "ii")
    pin, tree = _single(tmp_path / "in4", zstd_stream(tar_bytes([(label, log)])), "logs.tar.zst")
    _import(tree, pin, tmp_path / "iv")
    # (iii) a member of a declared nested zip inside a split zip (depth 3; streamed)
    variant = _profile(monkeypatch, include='["agentharm/results/**/*.eval"]')
    pin, tree, _inner = _nested_input(tmp_path / "n", inner={label: log})
    _import(tree, pin, tmp_path / "iii", limits=SMALL)
    partials = [tmp_path / f"{case}.partial" for case in ("i", "ii", "iii", "iv")]
    executions = [_by_execution(p) for p in partials]
    assert len(executions[0]) == 2 and executions[1] == executions[3] == executions[0]
    # (iii) maps through the test-variant profile (it declares the nested zip): its header names that profile, and the
    # seal covers the header; every record is byte-identical
    assert {ex: _records(d) for ex, d in executions[2].items()} == {ex: _records(d) for ex, d in executions[0].items()}
    assert all(json.loads(d.split(b"\n", 1)[0])["profile"]["sha256"] == variant.sha256 for d in executions[2].values())
    rows = [_eval_rows(p, _sha(log)) for p in partials]
    assert rows[0] and rows[1] == rows[3] == rows[0]
    # (iii) ran under SMALL's member bound, which enters the expand fn_digest (limits_sha256); nothing else differs
    assert [{k: v for k, v in r.items() if k != "fn_digest"} for r in rows[2]] == [
        {k: v for k, v in r.items() if k != "fn_digest"} for r in rows[0]]


def test_a_streamed_and_a_read_whole_nested_zip_store_the_same_objects_and_rows(tmp_path, monkeypatch):
    import agentprov.raw.members as members

    streamed: list[int] = []
    original = members._stream_member
    monkeypatch.setattr(members, "_stream_member", lambda *a: streamed.append(1) or original(*a))
    _profile(monkeypatch)
    pin, tree, _inner = _nested_input(tmp_path)
    _import(tree, pin, tmp_path / "small", limits=SMALL)
    assert streamed == [1]
    pin, tree, _inner = _nested_input(tmp_path / "again")
    _import(tree, pin, tmp_path / "default")
    assert streamed == [1]  # under the default bound the inner zip is read whole (D-58), as before
    skip = ("corpus.json", "derivation.json", "raw/members.jsonl")  # the limits record and the fn_digest they enter
    small, default = (support.tree_bytes(tmp_path / f"{n}.partial", skip=skip) for n in ("small", "default"))
    assert small == default
    rows = [[{k: v for k, v in m.items() if k != "fn_digest"} for m in _jsonl(tmp_path / f"{n}.partial" / "raw" /
                                                                              "members.jsonl")] for n in ("small", "default")]
    assert rows[0] == rows[1]


# ------------------------------------------------------------------------------------------------ subjects (D-384)
def test_rejections_at_levels_3_and_4_have_one_prefixed_subject_each(tmp_path, monkeypatch):
    _profile(monkeypatch)
    stored = _eval(12)  # members stored (method 0): one byte can be flipped inside a sample's JSON
    stored = insp.build_eval(json.loads(zipfile.ZipFile(io.BytesIO(stored)).read("header.json")),
                             {"s12-0_epoch_1.json": json.loads(zipfile.ZipFile(io.BytesIO(stored)).read(
                                 "samples/s12-0_epoch_1.json"))}, method=zipfile.ZIP_STORED)  # fmt: skip
    sample = bytearray(stored)
    at = bytes(sample).index(b"Synthetic final answer.")
    sample[at] ^= 0x01  # the sample's CRC no longer matches: a level-4 member defect
    inner = bytearray(_zip({"logs/x.eval": bytes(sample), "logs/y.eval": _eval(11), "logs/z.eval": _eval(13)}))
    at = bytes(inner).index(_eval(13)[200:240])
    inner[at] ^= 0x01  # logs/z.eval's CRC no longer matches: a level-3 member defect
    outer = _zip({"logs/inner.zip": bytes(inner)})
    pin, tree = _split(tmp_path / "in", outer)
    report = _import(tree, pin, tmp_path / "c", limits=SMALL)
    subjects = _subjects(tmp_path / "c.partial")
    assert sorted(subjects["ingest.archive.crc"]) == [
        "logs.zip!/logs/inner.zip!/logs/x.eval!/samples/s12-0_epoch_1.json",  # level 4: a sample of a level-3 .eval
        "logs.zip!/logs/inner.zip!/logs/z.eval",  # level 3: a .eval of the nested zip
    ]
    assert all(s.count("logs.zip!/") == 1 for paths in subjects.values() for s in paths)  # never a doubled prefix
    assert report.counters["mapped"] == 1  # logs/y.eval


# ------------------------------------------------------------------------------------------------ duplicates (D-385)
def test_a_byte_duplicate_nested_and_direct_is_mapped_once_with_both_origins(tmp_path, monkeypatch):
    _profile(monkeypatch)
    pin, tree, inner_zip = _nested_input(tmp_path, direct={"logs/x.eval": _eval(10)})
    report = _import(tree, pin, tmp_path / "c", limits=SMALL)
    assert report.counters["mapped"] == 2 and report.counters["duplicates"] == 1
    partial = tmp_path / "c.partial"
    # candidates go in chain-label byte order: logs/inner.zip!/logs/x.eval is first, the direct logs/x.eval collapses
    assert _subjects(partial)["dedup.collapsed"] == ["logs.zip!/logs/x.eval"]
    origins = _origins(partial)[_sha(_eval(10))]
    assert sorted(o["container"] for o in origins) == sorted([_sha(inner_zip), next(
        sha for sha, os_ in _origins(partial).items() if os_[0]["kind"] == "split")])


def test_a_truncated_direct_log_and_its_complete_nested_copy_are_never_related(tmp_path, monkeypatch):
    _profile(monkeypatch)
    pin, tree, _inner = _nested_input(tmp_path, direct={"logs/x.eval": _eval(10)[:1024]})
    report = _import(tree, pin, tmp_path / "c", limits=SMALL)
    assert report.counters["mapped"] == 2 and report.counters["duplicates"] == 0
    subjects = _subjects(tmp_path / "c.partial")
    assert subjects["ingest.archive.format"] == ["logs.zip!/logs/x.eval"] and "dedup.collapsed" not in subjects


def test_a_second_snapshot_with_the_direct_copy_collapses_on_the_eval(tmp_path, monkeypatch):
    _profile(monkeypatch)
    pin, tree, _inner = _nested_input(tmp_path)
    _import(tree, pin, tmp_path / "c", limits=SMALL, snapshot_id="nested")
    pin2, tree2 = _split(tmp_path / "in2", _zip({"logs/x.eval": _eval(10)}), name="direct.zip")
    report = _import(tree2, pin2, tmp_path / "c", limits=SMALL, snapshot_id="direct")
    assert report.counters["duplicates"] == 1 and report.counters["mapped"] == 0
    rows = _jsonl(tmp_path / "c.partial" / "executions.jsonl")
    assert sorted(sorted(r["snapshot_ids"]) for r in rows) == [["direct", "nested"], ["nested"]]


# ------------------------------------------------------------------------------------------------ resume and identity
def test_a_resume_with_the_same_nested_selection_continues_and_a_changed_one_is_refused(tmp_path, monkeypatch):
    _profile(monkeypatch)
    pin, tree, _inner = _nested_input(tmp_path, direct={"logs/d.eval": _eval(3)})
    first = _import(tree, pin, tmp_path / "c", limits=SMALL, limit=1)
    assert first.counters["mapped"] == 1
    again = _import(tree, pin, tmp_path / "c", limits=SMALL)
    assert again.counters["mapped"] == 2 and again.counters["skipped_resume"] == 1
    _import(tree, pin, tmp_path / "whole", limits=SMALL)
    assert support.tree_bytes(tmp_path / "c.partial", skip=("corpus.json",)) == support.tree_bytes(
        tmp_path / "whole.partial", skip=("corpus.json",))
    with pytest.raises(IdentityRefusedError, match="expand"):  # the same selections under other limits
        _import(tree, pin, tmp_path / "c")
    _profile(monkeypatch, NESTED.replace('pattern = "logs/*.zip"', 'pattern = "logs/**/*.zip"'))
    with pytest.raises(IdentityRefusedError):  # another nested selection: another profile (G4)
        _import(tree, pin, tmp_path / "c", limits=SMALL)


# ------------------------------------------------------------------------------------------------ recompute and verify
def _cli(args: list[str], tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[int, Any]:
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    capsys.readouterr()
    code = main([*args, "--json", "--progress", "off"])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


def test_recompute_and_chain_replay_a_nested_import(tmp_path, monkeypatch, capsys):
    from agentprov.corpus.verify import verify_corpus

    _profile(monkeypatch)
    pin, tree, _inner = _nested_input(tmp_path, direct={"logs/x.eval": _eval(10), "logs/d.eval": _eval(3)})
    _import(tree, pin, tmp_path / "c")
    partial = tmp_path / "c.partial"
    code, summary = _cli(["recompute", "--corpus", str(partial), "--dry-run", "--no-reuse", "--in-process"], tmp_path,
                         monkeypatch, capsys)  # fmt: skip
    assert code == 0, summary
    assert summary["counters"]["identical"] == summary["counters"]["selected"] == 3
    chain = verify_corpus(partial, level="chain")  # every member object at every level re-hashed and CRC-checked
    assert chain.counters["members_checked"] == len([m for m in _jsonl(partial / "raw" / "members.jsonl")
                                                     if m["disposition"] == "selected"])  # fmt: skip
    # a working tree has no checksums yet; the test-variant profile is not the package's (verify reads the package)
    assert {f.code for f in chain.findings} <= {"checksums.absent", "rules.mismatch"}, chain.findings


def test_rederive_and_chain_pass_with_an_eval_listed_under_two_containers(tmp_path):
    from agentprov.corpus.verify import verify_corpus
    from agentprov.stats.source import import_hooks

    log = _eval(5, samples=2)
    corpus = tmp_path / "c"
    pin, tree = _split(tmp_path / "in1", _zip({f"{LOGS}/a.eval": log, f"{LOGS}/b.eval": _eval(6)}))
    _import(tree, pin, corpus, snapshot_id="one", until="validation")
    pin, tree = _split(tmp_path / "in2", _zip({f"{LOGS}/copy.eval": log}), name="more.zip")
    report = _import(tree, pin, corpus, snapshot_id="two", until="validation")
    assert report.counters["duplicates"] == 2  # each of the log's two executions collapses (H.7.2)
    partial = tmp_path / "c.partial"
    containers = {m["container"] for m in _jsonl(partial / "raw" / "members.jsonl") if m["sha256"] == "sha256:" + _sha(log)}
    assert len(containers) == 2  # F-3: one object, two archives
    rederive = verify_corpus(partial, level="rederive", import_hooks=import_hooks())
    assert rederive.counters.get("rederive_identical") == 3, rederive.counters
    chain = verify_corpus(partial, level="chain")
    assert {f.code for f in chain.findings} <= {"checksums.absent"}, chain.findings


def test_a_re_map_refuses_an_archive_selection_the_source_did_not_record(tmp_path, monkeypatch, capsys):
    _profile(monkeypatch)
    pin, tree, _inner = _nested_input(tmp_path)
    _import(tree, pin, tmp_path / "c")
    _profile(monkeypatch, NESTED.replace('pattern = "logs/*.zip"', 'pattern = "logs/**/*.zip"'))
    code, _summary = _cli(["recompute", "--corpus", str(tmp_path / "c.partial"), "--dry-run", "--no-reuse",
                           "--in-process"], tmp_path, monkeypatch, capsys)  # fmt: skip
    assert code == 4


def test_rederive_refuses_an_archive_selection_the_source_did_not_record(tmp_path, monkeypatch):
    # deferrals review: StoredRawTree is shared by recompute and verify --level rederive, so both refuse
    from agentprov.corpus.verify import verify_corpus
    from agentprov.stats.source import import_hooks

    _profile(monkeypatch)
    pin, tree, _inner = _nested_input(tmp_path)
    _import(tree, pin, tmp_path / "c")
    _profile(monkeypatch, NESTED.replace('pattern = "logs/*.zip"', 'pattern = "logs/**/*.zip"'))
    with pytest.raises(IdentityRefusedError, match="selection"):  # refused before anything is re-derived
        verify_corpus(tmp_path / "c.partial", level="rederive", import_hooks=import_hooks())
