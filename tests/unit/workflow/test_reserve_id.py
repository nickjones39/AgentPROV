"""``tools/reserve_id.py``: one ledger for decision numbers, regen-batch items, spec items and routing ids (D-423)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import reserve_id as ri
from wf_support import commit, git, write

TOOL = Path(ri.__file__).resolve()

DECISIONS_TEXT = """# Decisions

## Addendum D

- **D-1 (U-15).** First.
- **D-150 (2026-10-12, phase 10f: profiles; user-approved).**
  - Nested text.
  - **Addendum 2 (2026-10-13).** Not a definition.
- **D-151 (2026-10-12, phase 10f: fixtures).**
- **D-151 addendum (2026-10-13, later).** Not a second definition.
- **D-189:** reserved.
"""

REGEN_TEXT = """# Regeneration batch

| # | Item | Source | Changes | Notes |
|---|---|---|---|---|
| 1 | B1: payloads | x | y | z |
| — | remeasured | x | y | z |
| U6-a | checker | x | y | z |
| 28 | Inspect strings | x | y | z |

Text between.

| 99 | Another table | not items |

## Item 18 (implemented)
## Items 26 and 27 (implemented)
"""

SPEC_TEXT = """# D. Adapters

### D.2.9 Notes

1. **Placement.** a
2. **Layering.** b

```
3. not an item, inside a fence
```

### D.9.5 Resolutions

1. **One.** x
   1. nested, ignored
2. **Two.** y

Deviations:

1. **Dev one.** z
2. **Dev two.** w

### D.6.13 Census

1. **A.** a
2. **B.** b

**Behaviour.**
3. **C.** c

**Census** (a paragraph whose wrapped line starts with a number): counts 1,
220. Measured here, a wrapped line.
"""

AGENTS_TEXT = """# AGENTS.md

- **Phase 10f** (branch `phase-10f`). Decisions D-150–D-159.
- **Workflow tools**. Decisions D-420–D-429 (proposals).
- **Suite perf**. D-400..D-409.
- See docs/reports/phase10k/routing.md for R-10k-1 and R-10k-2.
"""


def test_parse_decisions() -> None:
    defs = ri.parse_decisions(DECISIONS_TEXT, "main")
    assert [d.number for d in defs] == [1, 150, 151, 189]
    assert defs[1].fingerprint == "2026-10-12 phase 10f"
    assert defs[0].fingerprint == "u-15"


def test_an_umbrella_range_bullet_is_not_a_definition() -> None:
    """``- **D-390..D-399 (…)**`` announces a block; the real ``- **D-390 (…)**`` follows (bug pass BF-11)."""
    text = ("- **D-390..D-399 (2026-10-14, GUI research: proposals).** Umbrella.\n"
            "- **D-390 (2026-10-14, GUI research: toolkit).** First.\n"
            "- **D-440–D-449 (2026-10-14, macOS design).** Umbrella.\n"
            "- **D-440 (2026-10-14, macOS design: HIG).** First.\n")
    defs = ri.parse_decisions(text, "main")
    assert [(d.number, d.line) for d in defs] == [(390, 2), (440, 4)]
    assert ri.find_problems(ri.Survey(definitions=defs), "main")["duplicates"] == []


def test_amendments_and_to_blocks_are_not_definitions() -> None:
    """``D-621 amendment 2`` and ``D-660 to D-669`` were reported as duplicates of D-621 and as D-660 (2026-10-22)."""
    text = ("- **D-660 to D-669 (2026-10-22, Inspect harness).** Block.\n"
            "- **D-621 (2026-10-22, binding checks).** The decision.\n"
            "- **D-621 amendment (2026-10-22, minors).** One.\n"
            "- **D-621 amendment 2 (2026-10-22, V-2).** Two.\n")
    defs = ri.parse_decisions(text, "main")
    assert [(d.number, d.line) for d in defs] == [(621, 2)]
    assert ri.find_problems(ri.Survey(definitions=defs), "main")["duplicates"] == []


def test_parse_regen_batch_reads_only_the_item_table() -> None:
    defs = ri.parse_regen_batch(REGEN_TEXT, "main")
    rows = [d.number for d in defs if d.scope == ""]
    sections = [d.number for d in defs if d.scope == "section"]
    assert rows == [1, 28] and sections == [18, 26, 27]


def test_parse_spec_items() -> None:
    defs, jumps = ri.parse_spec_items(SPEC_TEXT, "main")
    lists: dict[str, list[int]] = {}
    for d in defs:
        lists.setdefault(d.scope, []).append(d.number)
    # The wrapped "220." is reported as a jump but is not an item (bug pass BF-10); "3." after a bold label is one.
    assert lists == {"D.2.9": [1, 2], "D.9.5": [1, 2], "D.9.5b": [1, 2], "D.6.13": [1, 2, 3]}
    assert defs[0].fingerprint == "placement."
    assert jumps == [{"list": "D.6.13", "after": 3, "number": 220, "ref": "main", "path": ri.SPEC, "line": 32}]
    taken = ri.taken_numbers("spec-item", "D.6.13", [], ri.Survey(definitions=defs))
    assert ri.next_range(taken, 1, 1) == (4, 4)


def test_parse_agents_ranges_and_routing() -> None:
    assert ri.parse_agents_ranges(AGENTS_TEXT) == [(150, 159), (420, 429), (400, 409)]
    ids = {(d.scope, d.number) for d in ri.parse_routing_ids(AGENTS_TEXT + "RT-3 and RW-1.\n", "main", "AGENTS.md")}
    assert ids == {("R-10k", 1), ("R-10k", 2), ("RT", 3), ("RW", 1)}


def _seed_repo(repo: Path) -> None:
    write(repo, ri.DECISIONS, DECISIONS_TEXT)
    write(repo, ri.REGEN_BATCH, REGEN_TEXT)
    write(repo, ri.SPEC, SPEC_TEXT)
    write(repo, ri.AGENTS, AGENTS_TEXT)
    write(repo, "docs/reports/phase10k/routing.md", "R-10k-1: x\nR-10k-3: y\n")
    sha = commit(repo, "docs")
    git(repo, "update-ref", "refs/remotes/origin/main", sha)


def _main(repo: Path, *args: str) -> int:
    return ri.main(["-C", str(repo), *args])


def test_reserve_decisions_skips_everything_used_or_announced(repo: Path, isolated_env: Path,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    git(repo, "switch", "-q", "-c", "phase-x")
    assert _main(repo, "reserve", "decision", "--purpose", "phase x") == 0
    assert capsys.readouterr().out.strip() == "D-430–D-439"
    assert _main(repo, "reserve", "decision", "--count", "3", "--purpose", "more") == 0
    assert capsys.readouterr().out.strip() == "D-440–D-442"
    ledger, bad = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")
    assert bad == 0 and [(r["first"], r["last"]) for r in ledger] == [(430, 439), (440, 442)]
    assert ledger[0]["session"] == "phase-x" and ledger[0]["branch"] == "phase-x" and ledger[0]["source"] == "reserve"
    mirror = [json.loads(x) for x in (repo / ri.MIRROR).read_text(encoding="utf-8").splitlines()]
    assert [r["rid"] for r in mirror] == [r["rid"] for r in ledger]


def test_decisions_in_parts_are_taken(repo: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D-1003: once DECISIONS.md is an index, its entries are in the parts and are scanned there."""
    _seed_repo(repo)
    write(repo, ri.DECISIONS, "# Decisions\n\n## Addendum D\n\n| Part |\n")
    write(repo, "docs/architecture/decision-log/DECISIONS-0250-0499.md", DECISIONS_TEXT + "- **D-430 (2026-10-30).**\n")
    commit(repo, "decisions in parts")
    assert _main(repo, "reserve", "decision", "--purpose", "after the parts", "--no-mirror") == 0
    assert capsys.readouterr().out.strip() == "D-440–D-449"


def test_reserve_other_kinds(repo: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    assert _main(repo, "reserve", "regen-item", "--purpose", "a", "--no-mirror") == 0
    assert _main(repo, "reserve", "spec-item", "--list", "D.2.9", "--purpose", "b", "--no-mirror") == 0
    assert _main(repo, "reserve", "spec-item", "--list", "D.9.5b", "--purpose", "c", "--no-mirror") == 0
    assert _main(repo, "reserve", "spec-item", "--list", "D.77.1", "--purpose", "new list", "--no-mirror") == 0
    assert _main(repo, "reserve", "routing", "--prefix", "R-10k", "--purpose", "d", "--no-mirror") == 0
    assert capsys.readouterr().out.split("\n")[:5] == [
        "regen-batch item 29", "D.2.9 item 3", "D.9.5b item 3", "D.77.1 item 1", "R-10k-4"]
    assert not (repo / ri.MIRROR).exists()
    with pytest.raises(SystemExit):
        _main(repo, "reserve", "spec-item", "--purpose", "no list")
    with pytest.raises(SystemExit):
        _main(repo, "reserve", "routing", "--prefix", "bad prefix", "--purpose", "x")


def test_numbers_on_other_branches_are_taken(repo: Path, isolated_env: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    git(repo, "switch", "-q", "-c", "other")
    write(repo, ri.SPEC, SPEC_TEXT.replace("2. **Layering.** b", "2. **Layering.** b\n3. **Other's item.** c"))
    commit(repo, "other adds D.2.9 item 3 without a reservation")
    git(repo, "switch", "-q", "main")
    assert _main(repo, "reserve", "spec-item", "--list", "D.2.9", "--purpose", "mine", "--no-mirror") == 0
    assert capsys.readouterr().out.strip() == "D.2.9 item 4"


def test_concurrent_reservations_never_share_a_number(repo: Path, isolated_env: Path) -> None:
    _seed_repo(repo)
    procs = [subprocess.Popen([sys.executable, str(TOOL), "-C", str(repo), "reserve", "regen-item", "--purpose",
                               f"p{i}", "--no-mirror"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for i in range(8)]
    outs = [p.communicate(timeout=120) for p in procs]
    assert all(p.returncode == 0 for p in procs), [o[1] for o in outs]
    got = sorted(int(o[0].split()[-1]) for o in outs)
    assert got == list(range(29, 37))
    ledger, bad = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")
    assert bad == 0 and len(ledger) == 8


def test_scan_reports_duplicates_collisions_and_jumps(repo: Path, isolated_env: Path,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    git(repo, "switch", "-q", "-c", "ingest")
    write(repo, ri.SPEC, SPEC_TEXT.replace("2. **Layering.** b", "2. **Layering.** b\n3. **Container members.** c"))
    commit(repo, "ingest item 3")
    git(repo, "switch", "-q", "-c", "stream", "main")
    write(repo, ri.SPEC, SPEC_TEXT.replace("2. **Layering.** b", "2. **Layering.** b\n3. **Streamed files.** c"))
    write(repo, ri.DECISIONS, DECISIONS_TEXT + "- **D-150 (2026-10-13, another session).**\n")
    commit(repo, "stream item 3 and a second D-150")
    git(repo, "switch", "-q", "-c", "stacked", "ingest")  # contains ingest's item: same content, no collision
    git(repo, "switch", "-q", "main")
    assert _main(repo, "scan", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["duplicates"] == [{"label": "D-150", "ref": "stream", "path": ri.DECISIONS, "lines": [6, 12]}]
    assert out["collisions"] == [{"label": "D.2.9 item 3", "variants": [
        {"fingerprint": "container members.", "refs": ["ingest", "stacked"]},
        {"fingerprint": "streamed files.", "refs": ["stream"]}]}]
    assert {(j["ref"], j["list"], j["number"]) for j in out["jumps"]} >= {("origin/main", "D.6.13", 220)}
    assert _main(repo, "scan", "--strict") == 1
    text = capsys.readouterr().out
    assert "collision  D.2.9 item 3" in text and "duplicate  D-150" in text and "jump       D.6.13: 3 -> 220" in text


def test_inherited_duplicates_are_reported_once(repo: Path, isolated_env: Path,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    git(repo, "switch", "-q", "-c", "old-base")
    write(repo, ri.REGEN_BATCH, REGEN_TEXT.replace("| 28 |", "| 1 | duplicate row | x | y | z |\n| 28 |"))
    commit(repo, "a duplicate row 1")
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/main", sha)  # main took it
    git(repo, "switch", "-q", "-c", "late-branch")
    write(repo, "x.txt", "x\n")
    commit(repo, "branch work")
    assert _main(repo, "--scan-ref", "origin/main", "--scan-ref", "late-branch", "scan", "--json") == 0
    dups = json.loads(capsys.readouterr().out)["duplicates"]
    assert {d["ref"] for d in dups} == {"origin/main", ":worktree"}
    assert _main(repo, "--scan-ref", "origin/main", "--scan-ref", "late-branch", "scan", "--json", "--all") == 0
    dups = json.loads(capsys.readouterr().out)["duplicates"]
    assert {d["ref"] for d in dups} == {"origin/main", "late-branch", ":worktree"}


def test_review_branches_are_not_scanned(repo: Path) -> None:
    _seed_repo(repo)
    git(repo, "branch", "review/old")
    git(repo, "branch", "review-base/old")
    git(repo, "branch", "feature")
    assert ri.Repo(repo).refs("origin/main") == ["origin/main", "feature", "main"]


def test_seed_then_scan_has_nothing_unreserved(repo: Path, isolated_env: Path,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    assert _main(repo, "scan", "--json") == 0
    assert json.loads(capsys.readouterr().out)["unreserved"] == []  # no ledger yet: not reported
    assert _main(repo, "reserve", "decision", "--purpose", "x", "--no-mirror") == 0
    capsys.readouterr()
    assert _main(repo, "scan", "--json") == 0
    assert "D-150" in {u["label"] for u in json.loads(capsys.readouterr().out)["unreserved"]}
    assert _main(repo, "seed") == 0
    assert _main(repo, "seed") == 0
    assert capsys.readouterr().out.strip().endswith("seeded 0 record(s) into "
                                                    f"{isolated_env / 'ids' / 'ledger.jsonl'}")
    assert _main(repo, "scan", "--json") == 0
    assert json.loads(capsys.readouterr().out)["unreserved"] == []
    assert _main(repo, "list", "--kind", "decision") == 0
    listing = capsys.readouterr().out
    assert "D-150–D-159" in listing and "D-420–D-429" in listing and "D-430–D-439" in listing


def test_sync_imports_the_mirror_once(repo: Path, isolated_env: Path, tmp_path: Path,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    assert _main(repo, "reserve", "decision", "--purpose", "on machine A") == 0
    sha = commit(repo, "mirror")
    git(repo, "update-ref", "refs/remotes/origin/main", sha)
    other_ids = tmp_path / "machine-b-ids"
    assert _main(repo, "--ids-dir", str(other_ids), "sync") == 0
    assert _main(repo, "--ids-dir", str(other_ids), "sync") == 0
    assert "0 record(s) imported" in capsys.readouterr().out.splitlines()[-1]
    a, _ = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")
    b, _ = ri.read_ledger(other_ids / "ledger.jsonl")
    assert a == b
    capsys.readouterr()
    assert _main(repo, "--ids-dir", str(other_ids), "reserve", "decision", "--purpose", "B", "--no-mirror") == 0
    assert capsys.readouterr().out.strip() == "D-440–D-449"


def test_damaged_ledger_lines_are_skipped(isolated_env: Path) -> None:
    path = isolated_env / "ids" / "ledger.jsonl"
    path.parent.mkdir(parents=True)
    good = {"rid": "r1", "kind": "decision", "scope": "", "first": 5, "last": 9}
    path.write_text(json.dumps(good) + "\n{torn\n" + json.dumps({"kind": "planet"}) + "\n\n", encoding="utf-8")
    records, bad = ri.read_ledger(path)
    assert records == [good] and bad == 2


def test_append_after_a_missing_final_newline_keeps_both_records(isolated_env: Path) -> None:
    """A ledger without its final newline (a hand edit, a short write) must not glue the next record onto the last one,
    which would hide both and hand the same range out again (bug pass BF-8)."""
    ids = isolated_env / "ids"

    def reserve(purpose: str) -> tuple[int, int]:
        rec = ri.reserve(kind="decision", scope="", count=10, align=10, session="s", branch="b", purpose=purpose,
                         ledger_dir=ids, sv=ri.Survey(), mirror=None, host="h")
        return rec["first"], rec["last"]

    one = reserve("one")
    ledger = ids / "ledger.jsonl"
    ledger.write_bytes(ledger.read_bytes().rstrip(b"\n"))
    two, three = reserve("two"), reserve("three")
    records, bad = ri.read_ledger(ledger)
    assert len({one, two, three}) == 3
    assert bad == 0 and len(records) == 3


def test_a_mirror_the_gitignore_ignores_is_not_written(repo: Path, isolated_env: Path,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    """D-1004: the public export leaves out docs/workflow/ and ignores it; a reservation there stays in the ledger."""
    write(repo, ".gitignore", "/docs/workflow/\n")
    commit(repo, "public-style ignore")
    assert _main(repo, "reserve", "decision", "--purpose", "public clone") == 0
    assert not (repo / ri.MIRROR).exists()
    assert f"{ri.MIRROR} is ignored here" in capsys.readouterr().err
    ledger, _ = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")
    assert [r["purpose"] for r in ledger] == ["public clone"]


def test_mirror_union_merge_keeps_every_reservation(repo: Path, isolated_env: Path) -> None:
    """The mirror is the one ``merge=union`` file: unique, never-edited JSON lines survive a union merge intact."""
    _seed_repo(repo)
    write(repo, ".gitattributes", f"{ri.MIRROR} merge=union\n")
    commit(repo, "union rule")
    git(repo, "switch", "-q", "-c", "a")
    assert _main(repo, "reserve", "decision", "--purpose", "a") == 0
    commit(repo, "a reserves")
    git(repo, "switch", "-q", "-c", "b", "main")
    assert _main(repo, "reserve", "decision", "--purpose", "b") == 0
    commit(repo, "b reserves")
    git(repo, "merge", "-q", "--no-edit", "a")
    merged, bad = ri.read_ledger(repo / ri.MIRROR)
    ledger, _ = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")
    assert bad == 0
    assert sorted(r["rid"] for r in merged) == sorted(r["rid"] for r in ledger)
    assert sorted((r["first"], r["last"]) for r in merged) == [(430, 439), (440, 449)]


def test_claim_an_explicit_range(repo: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A branch that wrote D.2.9 items 3-5 before reserving claims exactly those numbers."""
    _seed_repo(repo)
    args = ["reserve", "spec-item", "--list", "D.2.9", "--no-mirror"]
    assert _main(repo, *args, "--first", "3", "--count", "3", "--purpose", "mine", "--session", "a") == 0
    assert capsys.readouterr().out.strip() == "D.2.9 items 3–5"
    assert _main(repo, *args, "--first", "5", "--count", "2", "--purpose", "theirs", "--session", "b") == 2
    assert "reserved by a" in capsys.readouterr().err
    assert _main(repo, *args, "--first", "4", "--count", "2", "--purpose", "again", "--session", "a") == 0
    assert capsys.readouterr().out.strip() == "D.2.9 items 4–5 (already yours)"
    ledger, _ = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")
    assert [(r["first"], r["last"], r["source"]) for r in ledger] == [(3, 5, "claim")]


def test_seed_records_do_not_block_a_claim(repo: Path, isolated_env: Path) -> None:
    _seed_repo(repo)
    assert _main(repo, "seed") == 0  # covers D.2.9 items 1-2 as "seed"
    assert _main(repo, "reserve", "spec-item", "--list", "D.2.9", "--first", "1", "--count", "2", "--purpose",
                 "the branch that wrote them", "--no-mirror") == 0


def test_void_withdraws_a_reservation(repo: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    assert _main(repo, "reserve", "spec-item", "--list", "D.2.9", "--count", "11", "--purpose", "too many") == 0
    assert capsys.readouterr().out.strip() == "D.2.9 items 3–13"
    (wrong,) = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")[0]
    assert _main(repo, "void", wrong["rid"], "--reason", "reserved a spurious range") == 0
    assert capsys.readouterr().out.strip() == f"void D.2.9 items 3–13 ({wrong['rid']})"
    ledger, _ = ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")
    assert ri.effective(ledger) == []
    assert ri.taken_numbers("spec-item", "D.2.9", ledger, ri.Survey()) == set()
    mirror, _ = ri.read_ledger(repo / ri.MIRROR)
    assert [r.get("void") for r in mirror] == [None, wrong["rid"]]  # the withdrawal travels with the branch
    assert _main(repo, "list", "--kind", "spec-item") == 0
    assert "D.2.9 items 3–13 [void]" in capsys.readouterr().out
    assert _main(repo, "void", wrong["rid"], "--reason", "twice") == 2
    assert "already void" in capsys.readouterr().err
    assert _main(repo, "void", "no-such-rid", "--reason", "x") == 2
    assert _main(repo, "reserve", "spec-item", "--list", "D.2.9", "--purpose", "next", "--no-mirror") == 0
    assert capsys.readouterr().out.strip() == "D.2.9 item 3"  # the voided numbers are free again


def test_scan_require_reserved_fails_only_on_new_unreserved_definitions(repo: Path, isolated_env: Path,
                                                                        capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    assert _main(repo, "seed") == 0  # the base's definitions are covered
    gate = ["--scan-ref", "origin/main", "scan", "--strict", "--require-reserved"]
    assert _main(repo, *gate) == 0
    write(repo, ri.SPEC, SPEC_TEXT.replace("2. **Layering.** b", "2. **Layering.** b\n3. **New item.** c"))
    capsys.readouterr()
    assert _main(repo, *gate) == 1
    assert "unreserved-new D.2.9 item 3" in capsys.readouterr().out
    assert _main(repo, "reserve", "spec-item", "--list", "D.2.9", "--first", "3", "--purpose", "new", "--no-mirror") == 0
    assert _main(repo, *gate) == 0
    assert _main(repo, "--scan-ref", "origin/main", "scan", "--strict") == 0  # without the flag: duplicates only


# --------------------------------------------------------------------------------------------------- section headings

SECTIONS_TEXT = """# K. Testing

## K.19 Gates

### K.19.1 Local CI

```
### K.19.1 inside a fence: not a heading
```

#### K.19.1a Lettered follow-up

### §K.19.2 With a section sign
"""


def test_parse_spec_sections() -> None:
    defs = ri.parse_spec_sections(SECTIONS_TEXT, "main", "docs/architecture/K_testing.md")
    assert [(d.label, d.line, d.fingerprint) for d in defs] == [
        ("section K.19", 3, "gates"), ("section K.19.1", 5, "local ci"),
        ("section K.19.1a", 11, "lettered follow-up"), ("section K.19.2", 13, "with a section sign")]
    assert ri.find_problems(ri.Survey(definitions=defs), "main")["duplicates"] == []  # 1a is not a second 1


def test_one_section_number_on_two_headings_is_a_duplicate(repo: Path, isolated_env: Path,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    """In one file or across two (a number heads one section in the whole spec); the gate fails on it."""
    _seed_repo(repo)
    gate = ["--scan-ref", "origin/main", "scan", "--strict"]
    assert _main(repo, *gate) == 0
    write(repo, ri.SPEC, SPEC_TEXT + "\n### D.6.13 Census again\n")
    capsys.readouterr()
    assert _main(repo, *gate) == 1
    lines = [n for n, line in enumerate((SPEC_TEXT + "\n### D.6.13 Census again\n").splitlines(), 1)
             if line.startswith("### D.6.13")]
    assert f"duplicate  section D.6.13: :worktree:{ri.SPEC} lines {lines[0]}, {lines[1]}" in capsys.readouterr().out
    write(repo, ri.SPEC, SPEC_TEXT)
    write(repo, "docs/architecture/K_testing.md", "### D.9.5 Misplaced copy\n")
    assert _main(repo, *gate, "--json") == 1
    dups = json.loads(capsys.readouterr().out)["duplicates"]
    d95 = next(n for n, line in enumerate(SPEC_TEXT.splitlines(), 1) if line.startswith("### D.9.5"))
    assert dups == [{"label": "section D.9.5", "ref": ":worktree", "lines": [d95, 1],
                     "path": f"{ri.SPEC}, docs/architecture/K_testing.md",
                     "where": [f"{ri.SPEC}:{d95}", "docs/architecture/K_testing.md:1"]}]
    assert _main(repo, *gate) == 1
    assert f"duplicate  section D.9.5: :worktree:{ri.SPEC}:{d95}, docs/architecture/K_testing.md:1" in (
        capsys.readouterr().out)


def test_a_held_branch_section_collides_with_one_main_gained_since(repo: Path, isolated_env: Path,
                                                                   capsys: pytest.CaptureFixture[str]) -> None:
    """The D.6.21 case: a held branch writes ``### D.6.21 TraceLogger`` while another branch's D.6.21 lands on main.
    Reported before the held branch merges main (also by the gate run in its worktree), and as a duplicate after."""
    _seed_repo(repo)
    git(repo, "switch", "-q", "-c", "held")
    write(repo, ri.SPEC, SPEC_TEXT + "\n### D.6.21 TraceLogger robustness\n")
    commit(repo, "held: D.6.21")
    git(repo, "switch", "-q", "-c", "deposits", "main")
    write(repo, ri.SPEC, SPEC_TEXT + "\n### D.6.21 Deferred deposits\n")
    git(repo, "update-ref", "refs/remotes/origin/main", commit(repo, "deposits: D.6.21 lands on main"))
    git(repo, "switch", "-q", "held")
    capsys.readouterr()
    assert _main(repo, "scan", "--json") == 0
    assert json.loads(capsys.readouterr().out)["collisions"] == [{"label": "section D.6.21", "variants": [
        {"fingerprint": "deferred deposits", "refs": ["origin/main"]},
        {"fingerprint": "tracelogger robustness", "refs": [":worktree", "held"]}]}]
    assert _main(repo, "--scan-ref", "origin/main", "scan", "--strict") == 1  # the ci_local ids form, in held
    git(repo, "merge", "-q", "-s", "ours", "--no-edit", "origin/main")  # resolved by keeping both sections
    write(repo, ri.SPEC, SPEC_TEXT + "\n### D.6.21 Deferred deposits\n\n### D.6.21 TraceLogger robustness\n")
    commit(repo, "merge resolution keeps both")
    capsys.readouterr()
    assert _main(repo, "--scan-ref", "origin/main", "scan", "--strict") == 1
    assert "duplicate  section D.6.21" in capsys.readouterr().out
    git(repo, "switch", "-q", "-c", "unrelated", "origin/main")  # main itself and its descendants: no collision
    write(repo, "x.txt", "x\n")
    commit(repo, "unrelated")
    capsys.readouterr()
    assert _main(repo, "--scan-ref", "origin/main", "scan", "--strict") == 0


def test_reserve_a_section_number(repo: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _seed_repo(repo)
    git(repo, "switch", "-q", "-c", "other")
    write(repo, ri.SPEC, SPEC_TEXT + "\n### D.6.21 Someone else's section\n")
    commit(repo, "other: D.6.21 without a reservation")
    git(repo, "switch", "-q", "main")
    assert _main(repo, "reserve", "spec-section", "--list", "D.6", "--purpose", "mine", "--no-mirror") == 0
    assert capsys.readouterr().out.strip() == "section D.6.22"
    with pytest.raises(SystemExit):
        _main(repo, "reserve", "spec-section", "--list", "D.6.x", "--purpose", "bad")
    assert _main(repo, "seed") == 0
    assert all(r["kind"] != "spec-section" or r["source"] != "seed"
               for r in ri.read_ledger(isolated_env / "ids" / "ledger.jsonl")[0])  # headings are never seeded
    write(repo, ri.SPEC, SPEC_TEXT + "\n### D.6.22 Mine\n\n### D.6.23 Not reserved\n\n### D.6.22a Lettered\n")
    gate = ["--scan-ref", "origin/main", "scan", "--strict", "--require-reserved"]
    capsys.readouterr()
    assert _main(repo, *gate) == 0  # section reservations are not required by --require-reserved alone
    assert _main(repo, *gate, "--require-reserved-sections") == 1
    out = capsys.readouterr().out
    assert "unreserved-new section D.6.23" in out and "D.6.22 " not in out and "D.6.22a" not in out
