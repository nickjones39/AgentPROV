"""``tools/regen_pins.py``: one orchestrator over the pin regenerators, ``--check`` in a scratch worktree (D-424/425).

The real families run the repository's own regenerators and are exercised by the merge gate, not here. These tests
use small stand-in families (Python commands in a temporary repository) for the mechanics, and synthetic C.16
vectors for the ``c16-copies`` check.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
import regen_pins as rp
import re as _re
from wf_support import commit, git, write

GEN = """import hashlib, json, pathlib, sys
inputs = sorted(pathlib.Path('inputs').glob('*.txt'))
pins = {p.stem: hashlib.sha256(p.read_bytes()).hexdigest()[:12] for p in inputs}
pathlib.Path('pins').mkdir(exist_ok=True)
pathlib.Path('pins/digests.json').write_text(json.dumps(pins, indent=1, sort_keys=True) + '\\n')
"""
RANDOM = "import os, pathlib; pathlib.Path('pins').mkdir(exist_ok=True); " \
         "pathlib.Path('pins/random.txt').write_text(os.urandom(8).hex())"


def _has(out: str, family: str, rest: str) -> bool:
    return _re.search(rf"^{_re.escape(family)} +{_re.escape(rest)}", out, flags=_re.M) is not None


def fam(name: str, script: str, pins: tuple[str, ...], **kw) -> rp.Family:
    return rp.Family(name, pins, kw.pop("inputs", ("inputs/",)), write=(sys.executable, "-c", script), **kw)


DIGESTS = fam("digests", GEN, ("pins/digests.json",))


@pytest.fixture
def pinned(repo: Path) -> Path:
    write(repo, "inputs/a.txt", "a\n")
    write(repo, "inputs/b.txt", "b\n")
    write(repo, "gen.py", GEN)
    assert rp.write_families(repo, [DIGESTS], log=lambda _m: None)[0].status == "written"
    commit(repo, "pins")
    return repo


def _check(repo: Path, families, *args: str, capsys=None) -> int:
    return rp.main(["-C", str(repo), "--check", *args], families=families)


def test_check_current_then_stale(pinned: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _check(pinned, [DIGESTS]) == 0
    assert _has(capsys.readouterr().out, "digests", "current")
    write(pinned, "inputs/a.txt", "changed\n")
    commit(pinned, "input moved, pins not regenerated")
    assert _check(pinned, [DIGESTS]) == 1
    assert _has(capsys.readouterr().out, "digests", "stale  pins/digests.json")
    assert git(pinned, "status", "--porcelain") == ""  # the check wrote nothing here
    scratch = isolated_env / "regen-pins" / "wt"
    assert scratch.is_dir() and git(scratch, "rev-parse", "HEAD") == git(pinned, "rev-parse", "HEAD")


def test_a_second_repository_gets_its_own_scratch_worktree(pinned: Path, isolated_env: Path, tmp_path: Path,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    """P-3a dry run: the public export is another repository; it cannot check its commits out in the first one's
    worktree, so it gets its own directory under ``regen-pins/repos/``, and the first keeps ``regen-pins/wt``."""
    assert _check(pinned, [DIGESTS], "--once") == 0
    other = tmp_path / "export"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    for rel in ("inputs/a.txt", "inputs/b.txt", "gen.py", "pins/digests.json"):
        write(other, rel, (pinned / rel).read_text(encoding="utf-8"))
    commit(other, "export")
    assert _check(other, [DIGESTS], "--once") == 0
    assert _has(capsys.readouterr().out, "digests", "current")
    base = isolated_env / "regen-pins"
    (mine,) = (base / "repos").iterdir()
    assert git(mine / "wt", "rev-parse", "HEAD") == git(other, "rev-parse", "HEAD")
    assert git(base / "wt", "rev-parse", "HEAD") == git(pinned, "rev-parse", "HEAD")
    assert rp.scratch_base(pinned, base) == base and rp.scratch_base(other, base) == mine


def test_check_reports_nondeterminism_failures_and_missing_inputs(pinned: Path, isolated_env: Path,
                                                                  capsys: pytest.CaptureFixture[str]) -> None:
    families = [DIGESTS, fam("random", RANDOM, ("pins/random.txt",)),
                fam("broken", "raise SystemExit(4)", ("pins/none.txt",)),
                fam("cached", GEN, ("pins/digests.json",), requires=("cache",))]
    assert _check(pinned, families) == 2
    out = capsys.readouterr().out
    assert _has(out, "random", "nondeterministic")
    assert _has(out, "broken", "failed") and "exit 4" in out
    assert _has(out, "cached", "skipped") and "needs $AGENTPROV_HOME/cache" in out
    assert _check(pinned, families[:2], "--once") == 1  # one run cannot see nondeterminism: the new pin is stale
    assert _has(capsys.readouterr().out, "random", "stale")


def test_write_rewrites_pins_here(pinned: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(pinned, "inputs/c.txt", "c\n")
    assert rp.main(["-C", str(pinned), "--write"], families=[DIGESTS]) == 0
    assert set(json.loads((pinned / "pins/digests.json").read_text())) == {"a", "b", "c"}
    assert rp.main(["-C", str(pinned), "--write", "--family", "nope"], families=[DIGESTS]) == 2


def test_attribution(pinned: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = git(pinned, "rev-parse", "HEAD")
    git(pinned, "switch", "-q", "-c", "moves-a")
    write(pinned, "inputs/a.txt", "a2\n")
    rp.write_families(pinned, [DIGESTS], log=lambda _m: None)
    branch_a = commit(pinned, "a moves")
    git(pinned, "switch", "-q", "-c", "merged", base)
    write(pinned, "inputs/a.txt", "a2\n")
    assert rp.main(["-C", str(pinned), "--write", "--attribute", base, branch_a], families=[DIGESTS]) == 0
    write(pinned, "inputs/b.txt", "b2\n")  # a change no branch made
    assert rp.main(["-C", str(pinned), "--write", "--attribute", base, branch_a], families=[DIGESTS]) == 1
    assert "unattributed pin change: pins/digests.json [b]" in capsys.readouterr().out


def test_attribution_per_file_for_non_json(pinned: Path) -> None:
    base = git(pinned, "rev-parse", "HEAD")
    write(pinned, "pins/blob.bin", "one")
    branch = commit(pinned, "blob")
    write(pinned, "pins/other.bin", "x")
    assert rp.attribute(pinned, ["pins/blob.bin", "pins/other.bin"], base, [branch]) == ["pins/other.bin"]
    assert rp.attribute(pinned, ["pins/digests.json"], base, [branch]) == []


def test_order_and_selection() -> None:
    a = rp.Family("a", (), ("x/",), deps=("b",))
    b = rp.Family("b", (), ("y/",))
    c = rp.Family("c", ("pins/c.json",), ("z/",), deps=("a",))
    assert [f.name for f in rp.ordered([a, b, c], None)] == ["b", "a", "c"]
    assert [f.name for f in rp.ordered([a, b, c], ["c", "b"])] == ["b", "c"]
    with pytest.raises(ValueError, match="unknown"):
        rp.ordered([a, b], ["zz"])
    with pytest.raises(ValueError, match="cycle"):
        rp.ordered([rp.Family("p", (), (), deps=("q",)), rp.Family("q", (), (), deps=("p",))], None)
    assert rp.affected([a, b, c], ["y/file.py"]) == ["a", "b", "c"]
    assert rp.affected([a, b, c], ["pins/c.json"]) == ["c"]
    assert rp.affected([a, b, c], ["docs/other.md"]) == []
    globbed = rp.Family("g", (), ("tests/adapters/*/golden/*",))
    assert rp.affected([globbed], ["tests/adapters/dtap/golden/aer_digests.json"]) == ["g"]


def test_real_family_table_is_well_formed() -> None:
    names = [f.name for f in rp.ordered(rp.FAMILIES, None)]
    assert len(names) == len(set(names)) == len(rp.FAMILIES)
    for f in rp.FAMILIES:
        assert set(f.deps) <= set(names), f.name
        assert f.write or f.check is not None, f.name
        assert all(not p.startswith("/") for p in (*f.pins, *f.inputs)), f.name
    # out of scope by design: input pins and frozen files are never rewritten
    pins = " ".join(p for f in rp.FAMILIES for p in f.pins)
    assert "PORT_MANIFEST" not in pins and "test_format_freeze" not in pins and ".profile.toml" not in pins


def test_list(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert rp.main(["-C", str(repo), "--list"]) == 0
    out = capsys.readouterr().out
    assert _has(out, "c16-copies", "check-only") and "AGENTPROV_REGEN_GATE_D_DIGESTS=1" in out


# --------------------------------------------------------------------------------------------------- C.16 copies


def _vector(seed: str, n: int) -> bytes:
    records = [json.dumps({"k": "rec", "id": f"{seed}{i}"}, separators=(",", ":")).encode() for i in range(n - 1)]
    digest = hashlib.sha256(b"".join(r + b"\n" for r in records)).hexdigest()
    seal = json.dumps({"k": "seal", "n_records": n, "records_sha256": digest}, separators=(",", ":")).encode()
    return b"".join(r + b"\n" for r in records) + seal + b"\n"


def _c16_tree(root: Path) -> dict[str, bytes]:
    vectors = {ex: _vector(ex, 3 + i) for i, (ex, _name) in enumerate(rp.VECTORS)}
    facts = {ex: rp.seal_facts(data) for ex, data in vectors.items()}
    parts = ["# C\n", "| Example | Artefact | Records | ex | Preimage | Execution digest |", "|---|---|---|---|---|---|"]
    parts += [f"| {ex} demo | `x` | {facts[ex]['n_actual']} | `ex` | `p` | `{facts[ex]['actual']}` |"
              for ex, _ in rp.VECTORS]
    parts.append(f'\nSEM: {{"aer_digest":"sha256:{facts["C.16.2"]["actual"]}"}}\n')
    for ex, name in rp.VECTORS:
        parts += [f"### {ex} demo", "", "```jsonl", vectors[ex].decode().rstrip("\n"), "```", ""]
        write(root, f"{rp.C_DIR}/{name}", vectors[ex].decode())
    write(root, rp.C_SPEC, "\n".join(parts))
    write(root, f"{rp.C_DIR}/{rp.SEM_EXAMPLE[1]}", f'{{"aer_digest":"sha256:{facts["C.16.2"]["actual"]}"}}\n')
    write(root, "tests/unit/aer/test_seal.py",
          f'assert records[-1]["records_sha256"] == "{facts["C.16.1"]["actual"]}"\n')
    write(root, "tests/adapters/adprov/test_mapping.py", f'assert info.execution_digest == "{facts["C.16.2"]["actual"]}"\n')
    write(root, "tests/adapters/agentdojo/aer_digests.json", json.dumps({"C.16.1": facts["C.16.1"]["file_sha256"]}))
    return vectors


def test_c16_copies_consistent_tree(tmp_path: Path) -> None:
    _c16_tree(tmp_path)
    assert rp.check_c16_copies(tmp_path) == []


def test_c16_copies_finds_each_kind_of_drift(tmp_path: Path) -> None:
    vectors = _c16_tree(tmp_path)
    spec = tmp_path / rp.C_SPEC
    text = spec.read_text()
    # a spec block edited without a reseal (the C.16.4 case found on main, 2026-10-14)
    block4 = vectors["C.16.4"].decode()
    spec.write_text(text.replace(block4.split("\n")[0], block4.split("\n")[0].replace("rec", "REC"), 1))
    problems = rp.check_c16_copies(tmp_path)
    assert len(problems) == 1 and problems[0].startswith("C.16.4: spec block differs")
    spec.write_text(text)
    vector3 = tmp_path / rp.C_DIR / rp.VECTORS[2][1]
    vector3.write_bytes(vectors["C.16.3"].replace(b'"id":"C.16.30"', b'"id":"C.16.3X"'))
    assert any(p.startswith("C.16.3: vector") and "seal claims" in p for p in rp.check_c16_copies(tmp_path))
    vector3.write_bytes(vectors["C.16.3"])
    write(tmp_path, "tests/unit/aer/test_seal.py", 'assert records[-1]["records_sha256"] == "' + "0" * 64 + '"\n')
    assert rp.check_c16_copies(tmp_path) == ["tests/unit/aer/test_seal.py: C.16.1 copy is not "
                                             f"{rp.seal_facts(vectors['C.16.1'])['actual'][:16]}…"]


def test_c16_copies_rows_and_sem(tmp_path: Path) -> None:
    _c16_tree(tmp_path)
    spec = tmp_path / rp.C_SPEC
    spec.write_text(spec.read_text().replace("| C.16.2 demo | `x` | 4 |", "| C.16.2 demo | `x` | 5 |"))
    sem = tmp_path / rp.C_DIR / rp.SEM_EXAMPLE[1]
    sem.write_text('{"aer_digest":"sha256:' + "f" * 64 + '"}\n')
    assert rp.check_c16_copies(tmp_path) == ["C.16.2: digest row record count is not 4",
                                             f"C.14.5: {rp.SEM_EXAMPLE[1]} does not cite sha256:"
                                             f"{rp.seal_facts((tmp_path / rp.C_DIR / rp.VECTORS[1][1]).read_bytes())['actual'][:16]}…"]


def test_regenerators_keep_the_write_guard_on_and_allow_only_their_pins(pinned: Path, isolated_env: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite's write guard (D-402) stays on for a regenerator; AGENTPROV_TEST_WRITE_ALLOW names only the family's
    declared outputs (a glob pin allows its directory), so an undeclared write still fails."""
    monkeypatch.setenv("AGENTPROV_TEST_WRITE_GUARD", "enforce")
    monkeypatch.setenv("AGENTPROV_TEST_WRITE_ALLOW", "caller/value")
    probe = fam("probe", "import json, os, pathlib; pathlib.Path('pins').mkdir(exist_ok=True); "
                         "pathlib.Path('pins/guard.json').write_text(json.dumps([os.environ.get(k) for k in "
                         "('AGENTPROV_TEST_WRITE_GUARD', 'AGENTPROV_TEST_WRITE_ALLOW')]))",
                ("pins/guard.json", "out/*.aer.jsonl"))
    assert rp.write_families(pinned, [probe], log=lambda _m: None)[0].status == "written"
    guard, allow = json.loads((pinned / "pins/guard.json").read_text())
    assert guard == "enforce"
    assert allow.split(os.pathsep) == ["out", "pins/guard.json"]
    assert rp.allowed_writes(rp.Family("g", ("tests/fixtures/inspect/expected/*.aer.jsonl", "a/b.json"), ())) == [
        "a/b.json", "tests/fixtures/inspect/expected"]

def test_a_family_whose_tool_is_not_in_the_tree_is_skipped(pinned: Path, isolated_env: Path) -> None:
    later = rp.Family("later", ("README.md",), ("x/",), write=(sys.executable, "tools/not_here.py", "--write"),
                      tool="tools/not_here.py")
    (outcome,) = rp.write_families(pinned, [later], log=lambda _m: None)
    assert outcome.status == "skipped" and "tools/not_here.py is not in this tree" in outcome.detail
    readme = next(f for f in rp.FAMILIES if f.name == "readme-sources")
    assert readme.tool == "tools/gen_readme_sources.py" and readme.pins == ("README.md",)
