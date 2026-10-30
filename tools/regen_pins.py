"""One pin regenerator: every test pin, rebuilt by the existing regenerators in dependency order (D-424, D-425).

Usage::

    uv run python tools/regen_pins.py --list                   # the families, their pins and inputs
    uv run python tools/regen_pins.py --check                  # CI / merge train: exit 1 if a pin is stale
    uv run python tools/regen_pins.py --check --family dtap c16-copies
    uv run python tools/regen_pins.py --affected [--base origin/main]   # families whose inputs changed
    uv run python tools/regen_pins.py --write [--family F ...]          # rewrite pins in this worktree
    uv run python tools/regen_pins.py --write --attribute BASE BRANCH...   # merge train: regenerate, then attribute

Rule (proposed for AGENTS.md, D-429): **pin conflicts are resolved by re-running this tool, never by hand-merging
digests.**

**Families** (design ``docs/reports/workflow-tools/design.md`` §4). This is an orchestrator over the regenerators that
already exist (``AGENTPROV_REGEN_*`` test switches and the ``tools/`` generators), not a re-implementation. The one
new check is ``c16-copies``: the C.16 spec blocks equal their vector files, every vector's seal hashes its records,
the digest table rows and the C.14.5 SEM example name the sealed digests, and the hand-kept copies in tests agree.
``c16-copies`` is check-only until the D-31 and deferrals part-C branches have merged (they edit those lines by hand).

Out of scope on purpose: the format-freeze pins (changed only with a format version bump), the compat oracle's
``PORT_MANIFEST.json`` (invariant 8), and data pins of upstream bytes (fixture and zip digests, the D-249 split-part
pins). These pin *inputs*; rewriting them would hide an input change.

Regenerators run with the suite's write guard on and ``AGENTPROV_TEST_WRITE_ALLOW`` naming the family's declared pins
(:func:`allowed_writes`).

**``--check``** runs every selected family's write command in a scratch worktree of ``HEAD``
(``$AGENTPROV_HOME/regen-pins/wt``, reused, detached, never in a session's worktree; its virtual environment is
``$AGENTPROV_HOME/regen-pins/venv``; a second repository, such as the public export, gets its own pair under
``regen-pins/repos/<digest>/``), then compares the pin files with ``HEAD``. It runs each family twice and fails
if the two runs differ (invariant 4); ``--once`` skips the second run. A family whose inputs are not on this machine
(a cache under ``$AGENTPROV_HOME``) is skipped with the reason, never failed.

**``--attribute BASE BRANCH...``** (after ``--write``, used by the merge train on a pin conflict): every pin that now
differs from ``BASE`` must also differ from ``BASE`` on at least one of the branches (per key for JSON objects, per
file otherwise). An unattributed change is a digest move no session predicted; it exits 1 and lists the keys.

Exit codes: 0 current, 1 stale / nondeterministic / unattributed, 2 usage or a regenerator crashed.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import agentprov_home, git, git_ok, safe_text  # noqa: E402

UV_PYTHON = ("uv", "run", "python")
UV_PYTEST = ("uv", "run", "pytest", "-q", "-p", "no:cacheprovider")


@dataclass(frozen=True)
class Family:
    name: str
    pins: tuple[str, ...]  # files the family writes (globs allowed)
    inputs: tuple[str, ...]  # path prefixes or globs whose change can move the pins
    write: tuple[str, ...] = ()  # command run at the worktree root; empty for check-only families
    env: tuple[tuple[str, str], ...] = ()
    deps: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()  # paths under $AGENTPROV_HOME that must exist, else the family is skipped
    check: Callable[[Path], list[str]] | None = None  # in-process check (returns problems) for check-only families
    tool: str | None = None  # a generator that may not exist in every tree yet; the family is skipped without it


def _pytest(env: str, *tests: str, k: str | None = None) -> dict[str, Any]:
    cmd = (*UV_PYTEST, *tests) + (("-k", k) if k else ())
    return {"write": cmd, "env": ((env, "1"),)}


AGENTDOJO_INPUTS = ("src/agentprov/adapters/agentdojo/", "src/agentprov/adapters/runner/", "src/agentprov/aer/",
                    "src/agentprov/ingest/", "tests/fixtures/agentdojo", "tests/adapters/agentdojo/")
SHARED_INPUTS = ("src/agentprov/aer/", "src/agentprov/adapters/runner/", "src/agentprov/adapters/types.py",
                 "src/agentprov/ingest/")
PROV_INPUTS = ("src/agentprov/prov/", "src/agentprov/sem/", "src/agentprov/aer/", "src/agentprov/adapters/",
               "tests/fixtures/agentprov_prov_v1/", "tests/fixtures/agentdojo_prov_v1/", "tests/golden/")


# --------------------------------------------------------------------------------------------------- C.16 copies

C_SPEC = "docs/architecture/C_data_model.md"
C_DIR = "docs/architecture/examples/C"
VECTORS = (("C.16.1", "agentdojo_2024_pi_detector.aer.jsonl"), ("C.16.2", "adprov_v1_llama_injecagent.aer.jsonl"),
           ("C.16.3", "stac_case_223.aer.jsonl"), ("C.16.4", "rope_denial_qwen_autodojo.aer.jsonl"))
SEM_EXAMPLE = ("C.16.2", "adprov_v1_llama_injecagent.sem.jsonl")
#: Hand-kept copies: (file, regex with one group, the vector whose value it copies, which value). ``@0.2`` names the
#: ``aer/0.2`` copy of a vector under ``examples/C/aer-0.2/`` (deferrals part C, C.21): the mapper tests pin what the
#: writer seals today, the KAT test the frozen ``aer/0.1`` vector.
COPIES = (
    ("tests/unit/aer/test_seal.py", r'records\[-1\]\["records_sha256"\] == "([0-9a-f]{64})"', "C.16.1", "digest"),
    ("tests/adapters/adprov/test_mapping.py", r'info\.execution_digest == "([0-9a-f]{64})"', "C.16.2@0.2", "digest"),
    ("tests/adapters/agentdojo/aer_digests.json", r'"C\.16\.1": "([0-9a-f]{64})"', "C.16.1@0.2", "file_sha256"),
)


def _lines(data: bytes) -> list[bytes]:
    return [line for line in data.split(b"\n") if line]


def seal_facts(data: bytes) -> dict[str, Any]:
    """The seal's claims and what the records actually hash to: the execution digest is sha256 over every record
    line before the seal, each with its LF; ``n_records`` counts every line, the seal included."""
    lines = _lines(data)
    seal = json.loads(lines[-1])
    actual = hashlib.sha256(b"".join(line + b"\n" for line in lines[:-1])).hexdigest()
    return {"claimed": seal.get("records_sha256"), "actual": actual, "n_claimed": seal.get("n_records"),
            "n_actual": len(lines), "file_sha256": hashlib.sha256(data).hexdigest()}


def spec_blocks(spec: str) -> dict[str, str]:
    """The first ```jsonl block under each ``### C.16.x`` heading."""
    out: dict[str, str] = {}
    current = None
    lines = spec.split("\n")
    i = 0
    while i < len(lines):
        head = re.match(r"^###\s+(C\.16\.\d+)\b", lines[i])
        if head:
            current = head.group(1)
        elif lines[i].startswith("```jsonl") and current and current not in out:
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out[current] = "\n".join(lines[i + 1:j]) + "\n"
            i = j
        i += 1
    return out


def check_c16_copies(root: Path) -> list[str]:
    """Problems with the C.16 vectors, their spec blocks, digest rows and hand-kept copies (empty if consistent)."""
    problems: list[str] = []
    spec_path = root / C_SPEC
    if not spec_path.is_file():
        return [f"{C_SPEC} missing"]
    spec = spec_path.read_text(encoding="utf-8")
    blocks = spec_blocks(spec)
    facts: dict[str, dict[str, Any]] = {}
    for ex, name in VECTORS:
        vector = root / C_DIR / name
        if not vector.is_file():
            problems.append(f"{ex}: vector {name} missing")
            continue
        data = vector.read_bytes()
        f = facts[ex] = seal_facts(data)
        if f["claimed"] != f["actual"] or f["n_claimed"] != f["n_actual"]:
            problems.append(f"{ex}: vector {name} seal claims {str(f['claimed'])[:16]}…/{f['n_claimed']} records, "
                            f"records hash to {f['actual'][:16]}…/{f['n_actual']}")
        block = blocks.get(ex)
        if block is None:
            problems.append(f"{ex}: no jsonl block in {C_SPEC}")
        elif block.encode("utf-8") != data:
            b = seal_facts(block.encode("utf-8"))
            problems.append(f"{ex}: spec block differs from {name} (block records hash to {b['actual'][:16]}…, "
                            f"its seal claims {str(b['claimed'])[:16]}…)")
        row = re.search(rf"^\| {re.escape(ex)} [^\n]*$", spec, flags=re.M)
        if row is None:
            problems.append(f"{ex}: no digest table row")
        else:
            cells = [c.strip() for c in row.group(0).strip("|").split("|")]
            if str(f["n_actual"]) not in cells:
                problems.append(f"{ex}: digest row record count is not {f['n_actual']}")
            if f"`{f['actual']}`" not in row.group(0):
                problems.append(f"{ex}: digest row does not name the execution digest {f['actual'][:16]}…")
    for ex, name in VECTORS:  # the aer/0.2 copies (C.21): each a sealed file of its own
        copy = root / C_DIR / "aer-0.2" / name
        if copy.is_file():
            f = facts[f"{ex}@0.2"] = seal_facts(copy.read_bytes())
            if f["claimed"] != f["actual"] or f["n_claimed"] != f["n_actual"]:
                problems.append(f"{ex}: aer-0.2/{name} seal claims {str(f['claimed'])[:16]}…, records hash to "
                                f"{f['actual'][:16]}…")
    sem = root / C_DIR / SEM_EXAMPLE[1]
    if sem.is_file() and SEM_EXAMPLE[0] in facts:
        want = f"sha256:{facts[SEM_EXAMPLE[0]]['actual']}"
        if want not in sem.read_text(encoding="utf-8"):
            problems.append(f"C.14.5: {SEM_EXAMPLE[1]} does not cite {want[:23]}…")
        elif want not in spec:
            problems.append(f"C.14.5: the SEM example in {C_SPEC} does not cite {want[:23]}…")
    for rel, pattern, ex, which in COPIES:
        path = root / rel
        if not path.is_file() or ex not in facts:
            continue
        found = re.findall(pattern, path.read_text(encoding="utf-8"))
        want = facts[ex]["actual" if which == "digest" else "file_sha256"]
        if not found:
            problems.append(f"{rel}: no {ex} copy found")
        elif any(v != want for v in found):
            problems.append(f"{rel}: {ex} copy is not {want[:16]}…")
    return problems


FAMILIES: tuple[Family, ...] = (
    Family("history", ("src/agentprov/adapters/agentdojo/tables/agentdojo-history.table.toml",),
           ("tools/agentdojo/history_table.py",), write=(*UV_PYTHON, "tools/agentdojo/history_table.py"),
           requires=("cache",)),
    Family("agentdojo-aer", tuple(f"tests/adapters/agentdojo/{n}_digests.json" for n in (
        "aer", "head_aer", "rope_aer", "mandate_aer", "survey_aer", "phase10d_aer", "history_aer")), AGENTDOJO_INPUTS,
        deps=("history",), **_pytest("AGENTPROV_REGEN_AGENTDOJO_AER", *(f"tests/adapters/agentdojo/{t}.py" for t in (
            "test_mapper", "test_v1_import", "test_rope", "test_mandate", "test_survey", "test_phase10d_sources",
            "test_history_fields")))),
    Family("agentdyn-aer", ("tests/adapters/agentdojo/agentdyn_aer_digests.json",), AGENTDOJO_INPUTS,
           deps=("history",), **_pytest("AGENTPROV_REGEN_AGENTDYN_AER", "tests/adapters/agentdojo/test_agentdyn.py")),
    Family("drift-aer", ("tests/adapters/agentdojo/drift_aer_digests.json",), AGENTDOJO_INPUTS,
           **_pytest("AGENTPROV_REGEN_DRIFT_AER", "tests/adapters/agentdojo/test_drift.py")),
    Family("credleak", ("tests/adapters/credleak/golden/aer_digests.json",),
           ("src/agentprov/adapters/credleak/", "tests/fixtures/credleak", "tests/adapters/credleak/", *SHARED_INPUTS),
           **_pytest("AGENTPROV_REGEN_CREDLEAK_GOLDEN", "tests/adapters/credleak/test_mapper.py")),
    Family("dtap", ("tests/adapters/dtap/golden/aer_digests.json", "tests/adapters/dtap/golden/sem_prov_digests.json"),
           ("src/agentprov/adapters/dtap/", "tests/fixtures/dtap", "tests/adapters/dtap/", "src/agentprov/prov/",
            "src/agentprov/sem/", *SHARED_INPUTS),
           **_pytest("AGENTPROV_REGEN_DTAP_GOLDEN", "tests/adapters/dtap/test_mapper.py",
                     "tests/adapters/dtap/test_semantics.py")),
    Family("foobench", ("tests/adapters/foobench/golden/trace-001.aer.jsonl",),
           ("tests/adapters/foobench/", "tests/fixtures/foobench", *SHARED_INPUTS), deps=("foobench-fixture",),
           **_pytest("AGENTPROV_REGENERATE_GOLDEN", "tests/adapters/foobench/test_mapper.py", k="golden")),
    Family("inspect", ("tests/fixtures/inspect/expected/*.aer.jsonl",),
           ("src/agentprov/adapters/inspect/", "tests/fixtures/inspect", "tests/adapters/inspect/", *SHARED_INPUTS),
           **_pytest("AGENTPROV_REGEN_INSPECT_GOLDEN", "tests/adapters/inspect/test_survey.py")),
    Family("c161", (f"{C_DIR}/agentdojo_2024_pi_detector.aer.jsonl", f"{C_DIR}/aer-0.2/agentdojo_2024_pi_detector.aer.jsonl",
                    C_SPEC), AGENTDOJO_INPUTS,
           write=(*UV_PYTHON, "tools/agentdojo/regen_c161.py", "--write"), deps=("agentdojo-aer",)),
    Family("c16-copies", (), (C_DIR, C_SPEC, "tests/unit/aer/test_seal.py", "tests/adapters/adprov/test_mapping.py",
                              "tests/adapters/agentdojo/aer_digests.json"), deps=("c161", "agentdojo-aer"),
           check=check_c16_copies),
    Family("golden-prov", ("tests/golden/prov_digests.json",), PROV_INPUTS, deps=("agentdojo-aer",),
           **_pytest("AGENTPROV_REGEN_PROV_DIGESTS", "tests/golden/test_prov_derive.py")),
    Family("gate-d", ("tests/golden/gate_d_digests.json",), PROV_INPUTS, deps=("agentdojo-aer",),
           **_pytest("AGENTPROV_REGEN_GATE_D_DIGESTS", "tests/golden/test_gate_d.py")),
    Family("vocab", ("src/agentprov/prov/vocab.py",), ("tools/gen_vocab_py.py", "src/agentprov/prov/",
                                                       "src/agentprov/vocab/"),
           write=(*UV_PYTHON, "tools/gen_vocab_py.py")),
    Family("semdiff", ("docs/compat/semantic-diff.md",), ("tools/gen_semdiff_tables.py", "src/agentprov/prov/"),
           write=(*UV_PYTHON, "tools/gen_semdiff_tables.py")),
    Family("ns", ("docs/ns/apv-0.2.ttl",), ("tools/sync_ns.py", "src/agentprov/prov/", "src/agentprov/vocab/"),
           write=(*UV_PYTHON, "tools/sync_ns.py")),
    Family("foobench-fixture", ("tests/fixtures/foobench/**/*",), ("tools/gen_foobench_fixture.py",),
           write=(*UV_PYTHON, "tools/gen_foobench_fixture.py")),
    Family("readme-sources", ("README.md",), ("src/agentprov/adapters/registry/", "tools/gen_readme_sources.py"),
           write=(*UV_PYTHON, "tools/gen_readme_sources.py", "--write"), tool="tools/gen_readme_sources.py"),
    Family("readme-corpora", ("docs/user-guide/14-corpora.md",),
           ("tools/gen_readme_corpora.py", "tools/readme_corpora.toml", "src/agentprov/adapters/"),
           write=(*UV_PYTHON, "tools/gen_readme_corpora.py", "--write"), tool="tools/gen_readme_corpora.py"),
    Family("user-guide-cli", ("docs/user-guide/11-cli-reference.md",), ("tools/gen_user_guide_cli.py", "src/agentprov/"),
           write=(*UV_PYTHON, "tools/gen_user_guide_cli.py", "--write"), tool="tools/gen_user_guide_cli.py"),
)


# --------------------------------------------------------------------------------------------------- selection


def ordered(families: Sequence[Family], names: Sequence[str] | None) -> list[Family]:
    """The selected families (all if ``names`` is None) in dependency order; dependencies are not added."""
    by_name = {f.name: f for f in families}
    unknown = [n for n in names or () if n not in by_name]
    if unknown:
        raise ValueError(f"unknown famil{'y' if len(unknown) == 1 else 'ies'}: {', '.join(unknown)}")
    wanted = set(names) if names is not None else set(by_name)
    out: list[Family] = []
    seen: set[str] = set()

    def visit(f: Family, stack: tuple[str, ...]) -> None:
        if f.name in seen:
            return
        if f.name in stack:
            raise ValueError(f"dependency cycle: {' -> '.join((*stack, f.name))}")
        for dep in f.deps:
            if dep in by_name:
                visit(by_name[dep], (*stack, f.name))
        seen.add(f.name)
        if f.name in wanted:
            out.append(f)

    for f in families:
        visit(f, ())
    return out


def _matches(path: str, spec: str) -> bool:
    return path.startswith(spec) if not any(c in spec for c in "*?[") else fnmatch.fnmatch(path, spec)


def affected(families: Sequence[Family], changed: Sequence[str]) -> list[str]:
    """Families with an input or a pin among ``changed`` paths, plus every family that depends on one of them."""
    hit = {f.name for f in families if any(_matches(p, s) for p in changed for s in (*f.inputs, *f.pins))}
    grew = True
    while grew:
        grew = False
        for f in families:
            if f.name not in hit and hit & set(f.deps):
                hit.add(f.name)
                grew = True
    return [f.name for f in families if f.name in hit]


def pin_files(root: Path, family: Family) -> list[str]:
    out: set[str] = set()
    for spec in family.pins:
        if any(c in spec for c in "*?["):
            out.update(str(p.relative_to(root)) for p in root.glob(spec) if p.is_file())
        else:
            out.add(spec)
    return sorted(out)


# --------------------------------------------------------------------------------------------------- running


@dataclass
class Outcome:
    family: str
    status: str  # current | stale | nondeterministic | skipped | failed | written | unchanged
    files: list[str] = field(default_factory=list)
    detail: str = ""


def _snapshot(root: Path, family: Family) -> dict[str, bytes | None]:
    snap: dict[str, bytes | None] = {}
    for rel in pin_files(root, family):
        p = root / rel
        snap[rel] = p.read_bytes() if p.is_file() else None
    return snap


def allowed_writes(family: Family) -> list[str]:
    """What a family's regenerator may write under the suite's write guard (tests/conftest.py, D-402): its declared
    pin files, or for a glob pin the directory before the first wildcard. Everything else stays refused, so a
    regenerator that writes an undeclared file fails instead of passing silently."""
    out = []
    for spec in family.pins:
        if any(c in spec for c in "*?["):
            head = spec[:min(spec.index(c) for c in "*?[" if c in spec)]
            out.append(head.rsplit("/", 1)[0] if "/" in head else ".")
        else:
            out.append(spec)
    return sorted(set(out))


def run_write(root: Path, family: Family, *, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    # The guard stays on: AGENTPROV_TEST_WRITE_ALLOW names only this family's outputs (it used to be switched off).
    allow = os.pathsep.join(allowed_writes(family))
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", **dict(family.env), **(extra_env or {}))
    env["AGENTPROV_TEST_WRITE_ALLOW"] = allow
    out = subprocess.run(list(family.write), cwd=root, capture_output=True, text=True, env=env)
    return out.returncode, (out.stdout + out.stderr)[-3000:]


def missing_requirements(family: Family) -> list[str]:
    home = agentprov_home()
    return [r for r in family.requires if not (home / r).exists()]


def write_families(root: Path, families: Sequence[Family], *, extra_env: dict[str, str] | None = None,
                   log: Callable[[str], None] = print) -> list[Outcome]:
    outcomes = []
    for f in families:
        missing = missing_requirements(f)
        if missing:
            outcomes.append(Outcome(f.name, "skipped", detail=f"needs $AGENTPROV_HOME/{', '.join(missing)}"))
            continue
        if f.tool and not (root / f.tool).is_file():
            outcomes.append(Outcome(f.name, "skipped", detail=f"{f.tool} is not in this tree"))
            continue
        if f.check is not None and not f.write:
            problems = f.check(root)
            outcomes.append(Outcome(f.name, "stale" if problems else "current", detail="; ".join(problems)))
            continue
        before = _snapshot(root, f)
        rc, output = run_write(root, f, extra_env=extra_env)
        after = _snapshot(root, f)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        if rc != 0 and not changed:
            outcomes.append(Outcome(f.name, "failed", detail=f"exit {rc}: {safe_text(output[-600:], 600)}"))
        else:
            outcomes.append(Outcome(f.name, "written" if changed else "unchanged", changed,
                                    "" if rc == 0 else f"exit {rc} (a pin test fails until its pins are rewritten)"))
        log(f"regen-pins: {f.name}: {outcomes[-1].status} {', '.join(changed)}".rstrip())
    return outcomes


@contextlib.contextmanager
def scratch_lock(base: Path) -> Iterator[None]:
    base.mkdir(parents=True, exist_ok=True)
    fd = os.open(base / "lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def scratch_base(repo: Path, base: Path) -> Path:
    """``base`` while its worktree belongs to ``repo`` (or there is none yet), else this repository's own directory under
    ``base/repos/``: another clone, such as the public export (P-3a), cannot check its commits out in that worktree."""
    wt = base / "wt"
    if not (wt / ".git").exists():
        return base
    mine = Path(git(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo)).resolve()
    theirs = git_ok(["rev-parse", "--path-format=absolute", "--git-common-dir"], wt)
    if theirs is not None and Path(theirs).resolve() == mine:
        return base
    return base / "repos" / hashlib.sha256(str(mine).encode("utf-8")).hexdigest()[:16]


def prepare_scratch(repo: Path, commit: str, base: Path) -> Path:
    """The reused scratch worktree, reset to ``commit`` (detached; only this tool writes there)."""
    wt = base / "wt"
    if not (wt / ".git").exists():
        git(["worktree", "add", "--detach", "--quiet", str(wt), commit], repo)
    git(["checkout", "--quiet", "--detach", "--force", commit], wt)
    git(["reset", "--quiet", "--hard", commit], wt)
    git(["clean", "-q", "-fd"], wt)  # untracked files only; ignored ones (caches) are kept
    return wt


def check_families(repo: Path, families: Sequence[Family], *, twice: bool, base: Path,
                   log: Callable[[str], None] = print) -> list[Outcome]:
    commit = git(["rev-parse", "HEAD"], repo)
    with scratch_lock(base):
        base = scratch_base(repo, base)
        extra = {"UV_PROJECT_ENVIRONMENT": str(base / "venv")}
        wt = prepare_scratch(repo, commit, base)
        first = write_families(wt, families, extra_env=extra, log=log)
        results = []
        produced = {f.name: _snapshot(wt, f) for f in families}
        if twice:
            prepare_scratch(repo, commit, base)
            second = {o.family: o for o in write_families(wt, families, extra_env=extra, log=lambda _m: None)}
        for o in first:
            if o.status in ("skipped", "failed", "current", "stale"):
                results.append(o)
                continue
            fam = next(f for f in families if f.name == o.family)
            if twice and (second[o.family].status != o.status or _snapshot(wt, fam) != produced[o.family]):
                results.append(Outcome(o.family, "nondeterministic", o.files, "two runs produced different pins"))
            elif o.status == "written":
                results.append(Outcome(o.family, "stale", o.files, "pins differ from HEAD"))
            else:
                results.append(Outcome(o.family, "current"))
        return results


# --------------------------------------------------------------------------------------------------- attribution


def _at(repo: Path, rev: str, rel: str) -> bytes | None:
    out = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=repo, capture_output=True,
                         env=dict(os.environ, GIT_NO_LAZY_FETCH="1"))
    return out.stdout if out.returncode == 0 else None


def _keys(data: bytes | None) -> dict[str, Any] | None:
    if data is None:
        return None
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def attribute(root: Path, files: Sequence[str], base: str, branches: Sequence[str]) -> list[str]:
    """Pin changes (vs ``base``) in ``root`` that no branch made: per key for JSON objects, per file otherwise."""
    unexplained = []
    for rel in files:
        now_path = root / rel
        now = now_path.read_bytes() if now_path.is_file() else None
        then = _at(root, base, rel)
        if now == then:
            continue
        theirs = [_at(root, b, rel) for b in branches]
        now_k, then_k = _keys(now), _keys(then)
        if now_k is not None and (then_k is not None or then is None):
            then_k = then_k or {}
            for key in sorted(set(now_k) | set(then_k)):
                if now_k.get(key) == then_k.get(key):
                    continue
                moved_by = [b for b, t in zip(branches, theirs, strict=True)
                            if (_keys(t) or {}).get(key) != then_k.get(key)]
                if not moved_by:
                    unexplained.append(f"{rel} [{key}]")
        elif not any(t != then for t in theirs):
            unexplained.append(rel)
    return unexplained


# --------------------------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None, families: Sequence[Family] | None = None) -> int:
    fams = tuple(families if families is not None else FAMILIES)
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("-C", dest="cwd", type=Path, default=Path.cwd())
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--affected", action="store_true")
    p.add_argument("--family", nargs="+", help="only these families (dependencies are not added)")
    p.add_argument("--base", default="origin/main", help="--affected: compare with this ref")
    p.add_argument("--once", action="store_true", help="--check: one run instead of two")
    p.add_argument("--attribute", nargs="+", metavar="REV", help="--write: BASE BRANCH... (see the docstring)")
    a = p.parse_args(argv)
    top = git_ok(["rev-parse", "--show-toplevel"], a.cwd)
    if top is None:
        print(f"regen-pins: {a.cwd} is not inside a git worktree", file=sys.stderr)
        return 2
    root = Path(top)
    try:
        selected = ordered(fams, a.family)
    except ValueError as exc:
        print(f"regen-pins: {exc}", file=sys.stderr)
        return 2

    if a.list:
        for f in ordered(fams, None):
            mode_txt = "check-only" if f.check is not None and not f.write else " ".join(
                [*(f"{k}={v}" for k, v in f.env), *f.write])
            print(f"{f.name:<17} {mode_txt}")
            print(f"{'':<17} pins: {', '.join(f.pins) or '(copies, see docstring)'}")
            if f.deps or f.requires:
                print(f"{'':<17} after: {', '.join(f.deps) or '-'}; needs: {', '.join(f.requires) or '-'}")
        return 0

    if a.affected:
        merge_base = git_ok(["merge-base", a.base, "HEAD"], root)
        if merge_base is None:
            print(f"regen-pins: no merge-base with {a.base}", file=sys.stderr)
            return 2
        changed = (git_ok(["diff", "--name-only", merge_base], root) or "").splitlines()
        changed += (git_ok(["ls-files", "--others", "--exclude-standard"], root) or "").splitlines()
        print("\n".join(affected(fams, changed)))
        return 0

    if a.write:
        dirty = git_ok(["status", "--porcelain"], root)
        outcomes = write_families(root, selected)
        failed = [o for o in outcomes if o.status == "failed"]
        for o in outcomes:
            if o.status in ("skipped", "failed") or o.detail:
                print(f"regen-pins: {o.family}: {o.status}: {o.detail}")
        if a.attribute:
            changed = sorted({f for o in outcomes for f in o.files})
            unexplained = attribute(root, changed, a.attribute[0], a.attribute[1:])
            for u in unexplained:
                print(f"regen-pins: unattributed pin change: {safe_text(u)}")
            if unexplained:
                return 1
        if dirty:
            print("regen-pins: note: the worktree had uncommitted changes before this run")
        return 2 if failed else 0

    # --check
    if git_ok(["status", "--porcelain", "--untracked-files=no"], root):
        print("regen-pins: note: uncommitted changes are not checked; this checks HEAD")
    outcomes = check_families(root, selected, twice=not a.once, base=agentprov_home() / "regen-pins")
    worst = 0
    for o in outcomes:
        line = f"{o.family:<17} {o.status}"
        if o.files:
            line += f"  {', '.join(o.files)}"
        if o.detail:
            line += f"  ({safe_text(o.detail, 400)})"
        print(line)
        if o.status in ("stale", "nondeterministic"):
            worst = max(worst, 1)
        elif o.status == "failed":
            worst = 2
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
