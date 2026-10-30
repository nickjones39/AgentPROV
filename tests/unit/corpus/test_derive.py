"""``agentprov derive`` / ``agentprov recompute`` and ``agentprov.corpus.derive`` (HL H.8; MN N.2.3, N.2.4; K RPR-1..5, 8, 9;
HL-T5, T6, T14, T15; DoD Q.14, Q.30; DECISIONS D-30, D-32, D-37, D-43).

Source corpora are small working corpora imported from the committed fixtures (``derive_support``); every test that
changes one works on a copy, and every command runs under ``testing.fs_guard`` to prove the source unchanged (PLAN rule
4). Fixture text is never printed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.cli.main import main
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.testing import fs_guard

ADPROV_PAIRS = 3


# ------------------------------------------------------------------------------------------------ helpers
@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


class Run:
    def __init__(self, code: int, out: str, err: str) -> None:
        self.code, self.out, self.err = code, out, err

    @property
    def summary(self) -> dict[str, Any]:
        return json.loads(self.out.splitlines()[-1])

    @property
    def counters(self) -> dict[str, int]:
        return self.summary["counters"]


def run(capsys: pytest.CaptureFixture[str], *argv: str, guard: Path | None = None) -> Run:
    """Run the CLI in-process with ``--json``; with ``guard``, fail if anything below that tree changes."""
    capsys.readouterr()
    if guard is not None:
        with fs_guard.unchanged(guard):
            code = main([*argv, "--json", "--progress", "off"])
    else:
        code = main([*argv, "--json", "--progress", "off"])
    out, err = capsys.readouterr()
    return Run(code, out, err)


def copy_corpus(src: Path, dest: Path) -> Path:
    """A writable copy of ``<src>.partial`` as ``<dest>.partial``; returns ``dest``."""
    shutil.copytree(ds.partial(src), ds.partial(dest), symlinks=True)
    return dest


def files(root: Path) -> dict[str, bytes]:
    return ds.tree_bytes(root)


@pytest.fixture(scope="module")
def corpora(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Path]]:
    tmp = tmp_path_factory.mktemp("sources")
    yield {
        "agentdojo": ds.agentdojo_corpus(tmp, count=2),
        "adprov": ds.adprov_corpus(tmp, count=ADPROV_PAIRS),
    }


@pytest.fixture(scope="module")
def inspect_aer(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The survey AgentHarm log imported to the AER stage only (the container family; fast)."""
    return ds.inspect_corpus(tmp_path_factory.mktemp("inspect"), until="aer")


# ------------------------------------------------------------------------------------------------ RPR-1, Q.14, D-30
@pytest.mark.parametrize("family", ["agentdojo", "adprov"])
@pytest.mark.parametrize("stages", ["sem,prov,validation", None])
def test_recompute_dry_run_reports_zero_differences(capsys, corpora, family, stages):
    """RPR-1 / Q.14: re-deriving from the stored AERs, and re-mapping from the stored raw objects, gives 0 differences."""
    src = corpora[family]
    argv = ["recompute", "--corpus", str(src), "--dry-run", "--in-process"]
    if stages:
        argv += ["--stages", stages]
    result = run(capsys, *argv, guard=ds.partial(src))
    assert result.code == 0, result.err
    c = result.counters
    assert c["identical"] == c["selected"] > 0
    assert c["unexplained_change"] == c["changed_explained"] == c["failed"] == c["corpus_unexplained"] == 0
    assert result.summary["dry_run"] is True


@pytest.mark.parametrize("family", ["agentdojo", "adprov", "inspect"])
def test_a_remap_from_the_stored_raw_gives_byte_identical_aer(capsys, request, tmp_path, family):
    """D-30 acceptance: re-mapping each fixture family from its stored raw objects (no network) gives the same AER bytes,
    origins, members and register."""
    # only the fixture this family needs (a worker that runs one parameter never builds the other's corpora)
    src = request.getfixturevalue("inspect_aer") if family == "inspect" else request.getfixturevalue("corpora")[family]
    out = tmp_path / "new"
    result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--stages", "expand,aer", "--in-process",
                 guard=ds.partial(src))
    assert result.code == 0, result.err
    old, new = files(ds.partial(src)), files(ds.partial(out))
    aer = sorted(k for k in old if k.startswith("aer/"))
    assert aer and all(old[k] == new[k] for k in aer)
    for name in ("raw/origins.jsonl", "raw/members.jsonl", "register.jsonl", "validation/results.jsonl"):
        assert old.get(name) == new.get(name), name
    assert {k for k in old if k.startswith("raw/objects/")} == {k for k in new if k.startswith("raw/objects/")}
    assert result.counters["identical"] == result.counters["selected"]


def test_recompute_out_writes_a_new_working_version_with_full_rows(capsys, corpora, tmp_path):
    src = corpora["agentdojo"]
    out = tmp_path / "v2"
    result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process", guard=ds.partial(src))
    assert result.code == 0, result.err
    new = ds.partial(out)
    assert not out.exists() and new.is_dir() and not (new / ".agentprov.lock").exists()
    rows = ds.rows(new)
    assert rows and all({"cell", "ev", "facets", "logical_key", "oracles"} <= set(r) for r in rows)
    manifest = json.loads((new / "corpus.json").read_text())
    derived_from = manifest["derived_from"]
    assert derived_from["state"] == "working" and derived_from["corpus_id"] == "agentdojo"
    assert derived_from["manifest_sha256"] == "sha256:" + sha256_hex((ds.partial(src) / "corpus.json").read_bytes())
    assert derived_from["recomputed"] == ["aer", "sem", "prov", "validation"] and derived_from["root_digest"] is None
    assert manifest["sealed"] is False and manifest["state"] == "working" and manifest["oracle_specs"] == []
    assert manifest["counts"]["executions"] == len(rows)
    assert result.summary["corpus"]["state"] == "working"
    import jsonschema

    schema = Path(__file__).resolve().parents[2] / "cli" / "schemas" / "cli-summary-0.1.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema.read_text())).validate(result.summary)


# ------------------------------------------------------------------------------------------------ RPR-5
def test_derivation_versions_are_recorded(capsys, corpora, tmp_path):
    """RPR-5: adapter (id + SemVer), profile and catalogues (integer versions and digests), engine, spec, libraries,
    interpreter and lockfile digest."""
    src = corpora["agentdojo"]
    out = tmp_path / "v2"
    assert run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process").code == 0
    derivation = json.loads((ds.partial(out) / "derivation.json").read_text())
    stages = {s["stage"]: s for s in derivation["stages"]}
    assert set(stages) == {"aer", "sem", "prov", "validation"}
    aer = stages["aer"]
    assert re.fullmatch(r"[a-z.]+@\d+\.\d+\.\d+", aer["adapter"]) and aer["profile"] == "agentdojo-upstream@2"
    assert all(isinstance(v, int) for v in aer["rules"].values()) and set(aer["rules_sha256"]) == set(aer["rules"])
    assert stages["prov"]["spec"] == "agentprov-prov/0.1" and set(stages["prov"]["serialisers"]) == {"prov", "rdflib"}
    assert all(s["fn_digest"].startswith("sha256:") for s in stages.values())
    assert derivation["python"]["implementation"] and derivation["lockfile_sha256"].startswith("sha256:")
    producer = json.loads((ds.partial(out) / "corpus.json").read_text())["producer"]
    assert "rfc8785" in producer["key_distributions"] and producer["python"]["version"]


# ------------------------------------------------------------------------------------------------ HL-T5, HL-T6, RPR-2
def _tamper_prov(root: Path, *, to_float: bool = True) -> str:
    """Change one stored PROV value without changing its meaning for Python ``==`` (``N`` -> ``N.0``), and record the new
    file digest in the index so that the source stays internally consistent. Returns the execution id."""
    partial = ds.partial(root)
    row = ds.rows(partial)[0]
    path = partial / row["paths"]["prov"]["agentprov-prov/0.1"]["json"]
    data = path.read_bytes()
    changed, n = re.subn(rb'"apv:bytes":(\d+)', rb'"apv:bytes":\1.0', data, count=1)
    assert n == 1
    os.chmod(path, 0o644)
    path.write_bytes(changed)
    digest = "sha256:" + sha256_hex(changed)

    def change(r: dict[str, Any]) -> dict[str, Any]:
        r["digests"]["prov"]["agentprov-prov/0.1"]["json"] = digest
        return r

    ds.rewrite_row(partial, row["ex"], change)
    return str(row["ex"])


def test_a_type_only_change_is_an_unexplained_change(capsys, corpora, tmp_path):
    """HL-T5, HL-T6, RPR-2: ``3`` -> ``3.0`` in a stored PROV attribute is detected (bytes, not ``==``), no version
    differs, so recompute reports ``unexplained_change`` and exits 1; ``--show-diff`` names the attribute."""
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    ex = _tamper_prov(src)
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "sem,prov,validation",
                 "--show-diff", "1", guard=ds.partial(src))
    assert result.code == 1
    assert result.counters["unexplained_change"] == 1 and result.counters["identical"] == result.counters["selected"] - 1
    assert f"unexplained_change: {ex}" in result.err
    assert any("apv:bytes" in line and ".0 -> " in line for line in result.err.splitlines())


def test_show_diff_lines_from_corpus_data_cannot_start_a_new_output_line(capsys, corpora, tmp_path):
    """CC-4: ``--show-diff`` prints node ids and keys taken from the (untrusted) stored PROV; a line break in one is
    escaped, so the corpus cannot forge a line of the command's own output (N.1.13; N.2.4(5))."""
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    partial = ds.partial(src)
    row = ds.rows(partial)[0]
    path = partial / row["paths"]["prov"]["agentprov-prov/0.1"]["json"]
    document = json.loads(path.read_bytes())
    document.setdefault("entity", {})["x\nFORGED LINE\tend"] = {}
    data = jcs_bytes(document)
    os.chmod(path, 0o644)
    path.write_bytes(data)

    def change(r: dict[str, Any]) -> dict[str, Any]:
        r["digests"]["prov"]["agentprov-prov/0.1"]["json"] = "sha256:" + sha256_hex(data)
        return r

    ds.rewrite_row(partial, row["ex"], change)
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "prov",
                 "--show-diff", "1")
    assert result.code == 1
    lines = (result.out + result.err).splitlines()
    assert any("FORGED LINE" in line for line in lines)  # the diff names the node ...
    assert not any(line.startswith("FORGED LINE") for line in lines)  # ... on the line it belongs to
    assert "\t" not in result.out + result.err


def test_a_declared_version_change_explains_the_difference(capsys, corpora, tmp_path):
    """H.8.4(2): the same output change is ``changed_explained`` when the recorded stage declares another version."""
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    _tamper_prov(src)
    derivation_path = ds.partial(src) / "derivation.json"
    derivation = json.loads(derivation_path.read_text())
    for stage in derivation["stages"]:
        if stage["stage"] == "prov":
            stage["options"] = {**stage["options"], "context_encoding": "collection"}
    derivation_path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "sem,prov,validation")
    assert result.code == 0, result.err
    assert result.counters["changed_explained"] == 1 and result.counters["unexplained_change"] == 0


def test_a_code_digest_only_change_with_identical_outputs_passes(capsys, corpora, tmp_path):
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    derivation_path = ds.partial(src) / "derivation.json"
    derivation = json.loads(derivation_path.read_text())
    for stage in derivation["stages"]:
        if stage["stage"] == "prov":
            stage["engine_code_sha256"] = "sha256:" + "0" * 64
    derivation_path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "sem,prov,validation")
    assert result.code == 0 and result.counters["identical"] == result.counters["selected"]
    assert any("code digest changed" in n for n in result.summary["notices"])


# ------------------------------------------------------------------------------------------------ RPR-4
def test_tampered_raw_bytes_are_refused_before_anything_is_derived(capsys, corpora, tmp_path):
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    objects = sorted((ds.partial(src) / "raw" / "objects").rglob("*.json"))
    os.chmod(objects[0], 0o644)
    objects[0].write_bytes(objects[0].read_bytes() + b" ")
    out = tmp_path / "new"
    result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process", guard=ds.partial(src))
    assert result.code == 1 and "raw.digest.mismatch" in result.err
    assert not ds.partial(out).exists() and not out.exists()


# ------------------------------------------------------------------------------------------------ RPR-3 and resume
def test_an_interrupted_run_leaves_the_source_unchanged_and_resumes(capsys, corpora, tmp_path, monkeypatch):
    """RPR-3: a failure after N writes leaves the source byte-identical; the same command then resumes NEW.partial and
    gives the same bytes as an uninterrupted run."""
    from agentprov.corpus import derive

    src = corpora["agentdojo"]
    reference = tmp_path / "reference"
    assert run(capsys, "recompute", "--corpus", str(src), "--out", str(reference), "--in-process",
               "--stages", "sem,prov,validation", "--no-reuse").code == 0
    real = derive.Derivation._finish_unit
    calls = {"n": 0}

    def flaky(self: Any, *args: Any, **kwargs: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        real(self, *args, **kwargs)

    monkeypatch.setattr(derive.Derivation, "_finish_unit", flaky)
    out = tmp_path / "new"
    argv = ("recompute", "--corpus", str(src), "--out", str(out), "--in-process", "--stages", "sem,prov,validation",
            "--no-reuse")
    interrupted = run(capsys, *argv, guard=ds.partial(src))
    assert interrupted.code == 130 and ds.partial(out).is_dir() and len(ds.rows(ds.partial(out))) == 1
    monkeypatch.setattr(derive.Derivation, "_finish_unit", real)
    resumed = run(capsys, *argv, guard=ds.partial(src))
    assert resumed.code == 0, resumed.err
    assert resumed.counters["resumed"] == 1
    assert _without_reuse_record(files(ds.partial(out))) == _without_reuse_record(files(ds.partial(reference)))
    other = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process", "--stages", "expand,aer")
    assert other.code == 4  # another stage set in the same .partial is refused


# ------------------------------------------------------------------------------------------------ RPR-8, RPR-9
def _without_isolation(tree: dict[str, bytes]) -> dict[str, bytes]:
    manifest = json.loads(tree["corpus.json"])
    manifest["producer"].pop("isolation")
    return {**tree, "corpus.json": jcs_bytes(manifest)}


def _without_reuse_record(tree: dict[str, bytes]) -> dict[str, bytes]:
    derivation = json.loads(tree["derivation.json"])
    derivation.pop("reuse", None)
    return {**tree, "derivation.json": jcs_bytes(derivation)}


def test_outputs_do_not_depend_on_the_worker_count(capsys, corpora, tmp_path):
    """RPR-8: --jobs 1, --jobs 4 and --in-process give identical bytes (the recorded producer.isolation aside)."""
    src = corpora["agentdojo"]
    trees = []
    for name, extra in (("j1", ["--jobs", "1", "--no-reuse"]), ("j4", ["--jobs", "4", "--no-reuse"]),
                        ("ip", ["--in-process", "--no-reuse"])):
        out = tmp_path / name
        result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), *extra, guard=ds.partial(src))
        assert result.code == 0, result.err
        trees.append(files(ds.partial(out)))
    assert trees[0] == trees[1]
    assert _without_isolation(trees[0]) == _without_isolation(trees[2])
    assert trees[0]["corpus.json"] != trees[2]["corpus.json"]


def test_batch_size_follows_the_worker_count_within_bounds():
    """D-895: 64 units per worker, between the old fixed 256 and 1024."""
    from agentprov.corpus.derive import DEFAULT_BATCH, MAX_BATCH, batch_for

    assert [batch_for(n) for n in (0, 1, 4, 8, 16, 36)] == [DEFAULT_BATCH, 256, 256, 512, 1024, MAX_BATCH]


@pytest.mark.parametrize("stages", ["sem,prov,validation", None])
def test_outputs_do_not_depend_on_the_batch_size(capsys, corpora, tmp_path, monkeypatch, stages):
    """D-895: one unit per batch (re-derive and, by default, the re-map's importer) gives the bytes of the default
    batch, so a batch size that follows the worker count cannot change an output."""
    import agentprov.corpus.derive as derive_mod

    src = corpora["agentdojo"]
    trees = []
    for name, size in (("default", None), ("one", 1)):
        if size is not None:
            monkeypatch.setattr(derive_mod, "batch_for", lambda _workers, size=size: size)
        out = tmp_path / name
        argv = ["recompute", "--corpus", str(src), "--out", str(out), "--jobs", "2", "--no-reuse"]
        result = run(capsys, *argv, *(["--stages", stages] if stages else []), guard=ds.partial(src))
        assert result.code == 0, result.err
        trees.append(files(ds.partial(out)))
    assert trees[0] == trees[1]


def _set_prov_code_digest(root: Path) -> None:
    path = ds.partial(root) / "derivation.json"
    derivation = json.loads(path.read_text())
    stage = next(s for s in derivation["stages"] if s["stage"] == "prov")
    stage["engine_code_sha256"] = "sha256:" + "0" * 64
    body = {k: v for k, v in stage.items() if k != "fn_digest"}
    stage["fn_digest"] = "sha256:" + sha256_hex(jcs_bytes(body))
    path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")


@pytest.mark.parametrize("stages", ["sem,prov,validation", "expand,aer"])
def test_the_reuse_cache_gives_the_bytes_of_a_full_recompute(capsys, corpora, tmp_path, stages):
    """D-30 reuse cache: with an unchanged key the source outputs are carried, and the result is byte-identical to a full
    recompute (--no-reuse) for --jobs 1 and 4; the reuse record lists what was recomputed."""
    src = corpora["agentdojo"]
    n = len(ds.rows(ds.partial(src)))
    trees = []
    for name, extra in (("r1", ["--jobs", "1"]), ("r4", ["--jobs", "4"]), ("n1", ["--jobs", "1", "--no-reuse"]),
                        ("n4", ["--jobs", "4", "--no-reuse"])):
        out = tmp_path / name
        result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--stages", stages, *extra,
                     guard=ds.partial(src))
        assert result.code == 0, result.err
        trees.append(files(ds.partial(out)))
        record = json.loads(trees[-1]["derivation.json"])["reuse"]
        if "--no-reuse" in extra:
            assert record == {"enabled": False} and result.counters["recomputed"] == n
        else:
            assert record == {"enabled": True, "recomputed": 0, "recomputed_executions": [], "reused": n}
            assert result.counters["reused"] == n
    assert len({tuple(sorted(_without_reuse_record(t).items())) for t in trees}) == 1


def test_a_changed_reuse_key_recomputes(capsys, corpora, tmp_path):
    """A code-digest change of the prov stage invalidates the cache: every execution is recomputed (and identical)."""
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    _set_prov_code_digest(src)
    out = tmp_path / "new"
    result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process", "--stages",
                 "sem,prov,validation")
    assert result.code == 0, result.err
    record = json.loads((ds.partial(out) / "derivation.json").read_text())["reuse"]
    rows = ds.rows(ds.partial(src))
    assert record["recomputed_executions"] == sorted(r["ex"] for r in rows) and record["reused"] == 0
    assert result.counters["identical"] == len(rows)


@pytest.mark.parametrize("key", ["adapter_code_sha256", "engine_code_sha256"])
def test_a_changed_aer_code_digest_recomputes(capsys, corpora, tmp_path, key):
    """BF-33 stop-gap: the SEM/PROV/validation code imports modules outside its own digest scope (the family's citation
    module, aer/evidence.py, aer/reader.py), so reuse also needs the aer stage's recorded code digests to equal this
    build's. A different recorded aer code digest recomputes every execution."""
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    path = ds.partial(src) / "derivation.json"
    derivation = json.loads(path.read_text())
    stage = next(s for s in derivation["stages"] if s["stage"] == "aer")
    stage[key] = "sha256:" + "0" * 64
    path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")
    out = tmp_path / "new"
    result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process", "--stages",
                 "sem,prov,validation")
    assert result.code == 0, result.err
    record = json.loads((ds.partial(out) / "derivation.json").read_text())["reuse"]
    assert record["reused"] == 0 and record["recomputed"] == len(ds.rows(ds.partial(src)))


def test_outputs_do_not_depend_on_directory_listing_order(capsys, corpora, tmp_path, monkeypatch):
    """RPR-9: ``os.scandir`` and ``Path.iterdir`` returning reversed entries change no output byte."""
    src = corpora["agentdojo"]
    plain = tmp_path / "plain"
    assert run(capsys, "recompute", "--corpus", str(src), "--out", str(plain), "--in-process").code == 0
    real_scandir, real_iterdir = os.scandir, Path.iterdir

    class Reversed:
        def __init__(self, path: Any = ".") -> None:
            self._it = real_scandir(path)
            self._entries = list(self._it)[::-1]

        def __iter__(self) -> Iterator[Any]:
            return iter(self._entries)

        def __enter__(self) -> Reversed:
            return self

        def __exit__(self, *exc: object) -> None:
            self._it.close()

        def close(self) -> None:
            self._it.close()

    monkeypatch.setattr(os, "scandir", Reversed)
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(sorted(real_iterdir(self), reverse=True)))
    shuffled = tmp_path / "shuffled"
    assert run(capsys, "recompute", "--corpus", str(src), "--out", str(shuffled), "--in-process").code == 0
    monkeypatch.undo()
    assert files(ds.partial(plain)) == files(ds.partial(shuffled))


# ------------------------------------------------------------------------------------------------ HL-T14, HL-T15
def test_a_differing_member_row_fails_the_remap(capsys, inspect_aer, tmp_path):
    """HL-T14: recompute re-runs expand; a member row that differs from what expand produces is an unexplained corpus
    change (exit 1)."""
    from agentprov.raw.members import decode_members, encode_members

    src = copy_corpus(inspect_aer, tmp_path / "src")
    path = ds.partial(src) / "raw" / "members.jsonl"
    rows = decode_members(path.read_bytes())
    target = next(i for i, r in enumerate(rows) if r.disposition == "not_selected")
    import dataclasses

    flipped = format(int(rows[target].crc32, 16) ^ 1, "08x")
    rows[target] = dataclasses.replace(rows[target], crc32=flipped)
    path.write_bytes(encode_members(rows))
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "expand,aer",
                 guard=ds.partial(src))
    assert result.code == 1
    assert result.counters["corpus_unexplained"] == 1
    assert any("raw/members.jsonl differs" in n and "UNEXPLAINED" in n for n in result.summary["notices"])


def test_a_code_only_expand_change_explains_the_member_rows_fn_digest(capsys, inspect_aer, tmp_path, monkeypatch):
    """P-2 (BF-39): every ``raw/members.jsonl`` row records the ``expand`` ``fn_digest``, so a code-only expand change
    (same declared identity, other ``engine_code_sha256``) moved every row although no member changed, and recompute
    exited 1 on every archive corpus. Rows that differ only in the ``fn_digest`` of an expansion paired by declared
    identity are a refactor (H.8.4(2)): a notice, exit 0."""
    import agentprov.raw.members as members

    src = copy_corpus(inspect_aer, tmp_path / "src")
    monkeypatch.setattr(members, "engine_code_sha256", lambda: "f" * 64)
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "expand,aer",
                 guard=ds.partial(src))
    assert result.code == 0, result.summary["notices"]
    assert result.counters["corpus_unexplained"] == 0
    assert any("raw/members.jsonl" in n and "fn_digest" in n for n in result.summary["notices"])


def test_a_member_change_under_a_code_only_expand_change_still_fails(capsys, inspect_aer, tmp_path, monkeypatch):
    """P-2: only the ``fn_digest`` label is mapped; any other difference of a row is still unexplained (HL-T14)."""
    import dataclasses

    import agentprov.raw.members as members
    from agentprov.raw.members import decode_members, encode_members

    src = copy_corpus(inspect_aer, tmp_path / "src")
    path = ds.partial(src) / "raw" / "members.jsonl"
    rows = decode_members(path.read_bytes())
    target = next(i for i, r in enumerate(rows) if r.disposition == "not_selected")
    rows[target] = dataclasses.replace(rows[target], crc32=format(int(rows[target].crc32, 16) ^ 1, "08x"))
    path.write_bytes(encode_members(rows))
    monkeypatch.setattr(members, "engine_code_sha256", lambda: "f" * 64)
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "expand,aer",
                 guard=ds.partial(src))
    assert result.code == 1
    assert result.counters["corpus_unexplained"] == 1


def test_non_canonical_member_rows_are_not_relabelled_as_a_refactor(capsys, inspect_aer, tmp_path, monkeypatch):
    """RC-7: the P-2 relabel decodes and re-encodes the source raw/members.jsonl, so a source row with the same fields
    but other bytes (reordered keys, white space; decode accepts both) came out canonical and was reported as a refactor.
    Only canonical bytes are relabelled; these are compared, and reported, as they are."""
    import json

    import agentprov.raw.members as members
    from agentprov.raw.members import decode_members

    src = copy_corpus(inspect_aer, tmp_path / "src")
    path = ds.partial(src) / "raw" / "members.jsonl"
    data = path.read_bytes()
    first, _, rest = data.partition(b"\n")
    reordered = dict(reversed(list(json.loads(first).items())))
    altered = json.dumps(reordered, separators=(", ", ": ")).encode() + b"\n" + rest
    assert altered != data and decode_members(altered) == decode_members(data)  # same rows, other bytes
    path.write_bytes(altered)
    monkeypatch.setattr(members, "engine_code_sha256", lambda: "f" * 64)
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "expand,aer",
                 guard=ds.partial(src))
    assert result.code == 1
    assert result.counters["corpus_unexplained"] == 1
    assert not any("raw/members.jsonl" in n and "fn_digest" in n for n in result.summary["notices"])


def test_catalogue_authority_mismatch_and_unavailable(capsys, corpora, tmp_path):
    """HL-T15: a swapped rules/ copy gives rules.mismatch and a swapped recorded catalogue digest aer.rules.drift (D-460);
    recompute still derives from the package (0 differences); an unshipped catalogue version gives rules.unavailable."""
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    partial = ds.partial(src)
    (partial / "rules").mkdir()
    (partial / "rules" / "agentdojo.rules.toml").write_bytes(b"# not the package catalogue\n")
    derivation_path = partial / "derivation.json"
    derivation = json.loads(derivation_path.read_text())
    aer = next(s for s in derivation["stages"] if s["stage"] == "aer")
    aer["rules_sha256"]["aer"] = "sha256:" + "1" * 64
    derivation_path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "sem,prov,validation",
                 guard=partial)
    assert result.code == 0, result.err
    # the rules/ copy is rules.mismatch; a recorded aer catalogue digest that differs at a shipped version is drift (D-460)
    assert result.summary["issues_by_code"]["rules.mismatch"] == 1
    assert result.summary["issues_by_code"]["aer.rules.drift"] == 1
    assert result.counters["identical"] == result.counters["selected"]
    aer["rules"]["agentdojo"] = 99
    derivation_path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "sem,prov,validation")
    assert result.summary["issues_by_code"].get("rules.unavailable", 0) >= 1


# ------------------------------------------------------------------------------------------------ D-43
def test_a_live_corpus_cannot_be_remapped_but_can_be_rederived(capsys, corpora, tmp_path):
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    manifest_path = ds.partial(src) / "corpus.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["mode"] = "live"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    refused = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--stages", "aer", guard=ds.partial(src))
    assert refused.code == 5
    ok = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "sem,prov,validation")
    assert ok.code == 0, ok.err


# ------------------------------------------------------------------------------------------------ D-37, Q.30
def test_derive_writes_compat_graphs_flagged_as_regression_oracle(capsys, corpora, tmp_path):
    """D-37 / Q.30 / HL-T19: ``derive --prov-spec adprov-v2.3-compat`` regenerates the baseline graph bytes from the AER
    (gate B), flags them ``apv:RegressionOracle`` in the rows and the manifest, and prints the notice."""
    src = corpora["adprov"]
    out = tmp_path / "with-compat"
    result = run(capsys, "derive", "--corpus", str(src), "--out", str(out), "--prov-spec", "adprov-v2.3-compat",
                 "--views", "transcript-v1", "--in-process", guard=ds.partial(src))
    assert result.code == 0, result.err
    assert any("apv:RegressionOracle" in n for n in result.summary["notices"])
    new = ds.partial(out)
    expected = ds.adprov_graph_digests(ADPROV_PAIRS)
    rows = ds.rows(new)
    produced = set()
    for row in rows:
        assert row["oracles"] == {"adprov-v2.3-compat": {"gate_report": None, "status": "apv:RegressionOracle"}}
        produced.add(sha256_hex((new / row["paths"]["prov"]["adprov-v2.3-compat"]["json"]).read_bytes()))
        view = new / "views" / "transcript-v1" / row["paths"]["aer"].split("/")[1] / f"{row['ex']}.transcript.json"
        assert view.is_file()
    assert produced == expected
    manifest = json.loads((new / "corpus.json").read_text())
    assert manifest["oracle_specs"] == [{"gate_report": None, "spec": "adprov-v2.3-compat", "status": "apv:RegressionOracle"}]
    assert manifest["prov_specs"] == ["agentprov-prov/0.1", "adprov-v2.3-compat"]
    stages = [s["stage"] for s in json.loads((new / "derivation.json").read_text())["stages"]]
    assert stages[-2:] == ["views", "compat"]
    again = run(capsys, "recompute", "--corpus", str(out), "--dry-run", "--in-process", guard=new)
    assert again.code == 0 and again.counters["identical"] == again.counters["selected"]
    assert any("apv:RegressionOracle" in n for n in again.summary["notices"])


def test_compat_is_not_applicable_outside_the_view_families(capsys, inspect_aer, tmp_path):
    src = inspect_aer
    out = tmp_path / "new"
    result = run(capsys, "derive", "--corpus", str(src), "--out", str(out), "--stages", "views",
                 "--prov-spec", "adprov-v2.3-compat", "--in-process")
    assert result.code == 0, result.err
    assert not list((ds.partial(out) / "prov").glob("adprov-v2.3-compat/*/*")) if (ds.partial(out) / "prov").exists() else True
    assert not (ds.partial(out) / "views").exists()


# ------------------------------------------------------------------------------------------------ derive adds layers
def test_derive_adds_the_missing_layers_of_an_aer_only_corpus(capsys, tmp_path):
    src = ds.agentdojo_corpus(tmp_path, name="aer-only", count=1, until="aer")
    out = tmp_path / "derived"
    result = run(capsys, "derive", "--corpus", str(src), "--out", str(out), "--in-process", guard=ds.partial(src))
    assert result.code == 0, result.err
    row = ds.rows(ds.partial(out))[0]
    assert set(row["stages"]) == {"aer", "prov", "raw", "sem", "validation"} and "facets" in row
    assert ds.rows(ds.partial(src))[0]["digests"]["aer"] == row["digests"]["aer"]
    again = run(capsys, "recompute", "--corpus", str(out), "--dry-run", "--in-process", "--stages", "sem,prov,validation")
    assert again.code == 0 and again.counters["identical"] == 1


def test_derive_refuses_a_layer_present_at_another_version(capsys, corpora, tmp_path):
    src = copy_corpus(corpora["agentdojo"], tmp_path / "src")
    derivation_path = ds.partial(src) / "derivation.json"
    derivation = json.loads(derivation_path.read_text())
    next(s for s in derivation["stages"] if s["stage"] == "prov")["spec"] = "agentprov-prov/0.0"
    derivation_path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")
    result = run(capsys, "derive", "--corpus", str(src), "--out", str(tmp_path / "new"), "--stages", "prov")
    assert result.code == 4 and "version_mismatch" in result.err


# ------------------------------------------------------------------------------------------------ D-32 raw objects
def test_raw_objects_are_copied_by_default_and_linked_with_link_raw(capsys, corpora, tmp_path):
    src = corpora["agentdojo"]
    source_objects = sorted((ds.partial(src) / "raw" / "objects").rglob("*.json"))
    for name, extra, linked in (("copied", [], False), ("linked", ["--link-raw"], True)):
        out = tmp_path / name
        result = run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process",
                     "--stages", "sem,prov,validation", *extra, guard=ds.partial(src))
        assert result.code == 0, result.err
        for obj in source_objects:
            target = ds.partial(out) / obj.relative_to(ds.partial(src))
            assert target.read_bytes() == obj.read_bytes()
            assert os.path.samefile(target, obj) is linked
        assert result.counters["raw_linked" if linked else "raw_copied"] == len(source_objects)


def test_a_dry_run_tree_lies_on_the_sources_filesystem_and_links_raw_objects(capsys, corpora, monkeypatch):
    """Perf round 2, item 1a: the private tree is made by ``scratch_tree`` next to the source's filesystem (here
    ``$AGENTPROV_HOME/tmp``), so every raw object is hard-linked, never copied, and the tree is removed afterwards."""
    from agentprov.corpus import scratch

    src = corpora["agentdojo"]
    made: list[Path] = []
    real = scratch.scratch_tree

    def spy(prefix: str, near: str | os.PathLike[str]) -> Path:
        made.append(real(prefix, near))
        return made[-1]

    monkeypatch.setattr("agentprov.cli.derive.scratch_tree", spy)
    result = run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process", "--stages", "sem,prov,validation",
                 guard=ds.partial(src))
    assert result.code == 0, result.err
    home_tmp = Path(os.environ["AGENTPROV_HOME"]) / "tmp"
    assert [p.parent for p in made] == [home_tmp] and not made[0].exists()
    assert result.counters["raw_copied"] == 0 and result.counters["raw_linked"] > 0
    assert not any("hard links are not possible" in n for n in result.summary["notices"])


# ------------------------------------------------------------------------------------------------ guards and usage
def test_output_guards_and_usage_errors(capsys, corpora, tmp_path):
    src = corpora["agentdojo"]
    exists = tmp_path / "exists"
    exists.mkdir()
    assert run(capsys, "recompute", "--corpus", str(src), "--out", str(exists)).code == 4
    inside = ds.partial(src) / "nested"
    assert run(capsys, "recompute", "--corpus", str(src), "--out", str(inside), guard=ds.partial(src)).code == 4
    assert run(capsys, "recompute", "--corpus", str(src)).code == 2
    assert run(capsys, "recompute", "--corpus", str(src), "--out", str(tmp_path / "x"), "--dry-run").code == 2
    assert run(capsys, "derive", "--corpus", str(src)).code == 2
    assert run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--stages", "bogus").code == 2
    assert run(capsys, "recompute", "--corpus", str(tmp_path / "missing"), "--dry-run").code == 2
    assert run(capsys, "derive", "--corpus", str(src), "--out", str(tmp_path / "y"), "--stages", "aer").code == 2


def test_trig_is_written_outside_the_corpus_only(capsys, corpora, tmp_path):
    src = corpora["agentdojo"]
    first, second = tmp_path / "trig1", tmp_path / "trig2"
    result = run(capsys, "derive", "--corpus", str(src), "--trig", str(first), guard=ds.partial(src))
    assert result.code == 0, result.err
    assert result.counters["trig_written"] == len(ds.rows(ds.partial(src)))
    assert run(capsys, "derive", "--corpus", str(src), "--trig", str(second)).code == 0
    assert files(first) == files(second) and (first / "trig.sha256").is_file()
    assert any("TriG listing sha256:" in n for n in result.summary["notices"])
    refused = run(capsys, "derive", "--corpus", str(src), "--trig", str(ds.partial(src) / "trig"), guard=ds.partial(src))
    assert refused.code == 4


def test_trig_into_a_corpus_final_directory_or_a_sealed_corpus_is_refused(capsys, corpora, tmp_path):
    """CC-7: ``--trig`` may not name the final directory of the source or the new working corpus (package seals into
    it, and a writer refuses an existing one), nor a directory inside another sealed corpus (G1, G2, G8)."""
    src = corpora["agentdojo"]
    work = copy_corpus(src, tmp_path / "work")
    refused = run(capsys, "derive", "--corpus", str(work), "--trig", str(work), guard=ds.partial(work))
    assert refused.code == 4 and not work.exists()
    new = tmp_path / "new"
    refused = run(capsys, "derive", "--corpus", str(src), "--out", str(new), "--trig", str(new), "--in-process")
    assert refused.code == 4 and not new.exists() and not ds.partial(new).exists()  # refused before any unit
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "corpus.json").write_text('{"sealed": true}')
    refused = run(capsys, "derive", "--corpus", str(src), "--trig", str(sealed / "trig"))
    assert refused.code == 4 and not (sealed / "trig").exists()
