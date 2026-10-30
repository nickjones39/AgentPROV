"""Batched merge train: N green branches, one gate run, fast-forward ``main`` (D-420, user-approved 2026-10-14).

Usage::

    uv run python tools/merge_train.py plan  B1 B2 B3              # merges only, in a scratch worktree (dry run)
    uv run python tools/merge_train.py run   B1 B2 B3 --bisect     # merges + ONE gate run; bisects on red
    uv run python tools/merge_train.py run   B1 B2 B3 --bisect --push --approval "<the user's words>"
    uv run python tools/merge_train.py status [RUN_ID]

**What it does** (design ``docs/reports/workflow-tools/design.md`` §1):

1. Starts from the local ``origin/main`` ref (``--fetch`` runs ``git fetch origin`` first; the only network step, and
   opt-in) in a new detached scratch worktree ``$AGENTPROV_HOME/merge-train/<run-id>/wt``. It never writes in a
   session's worktree and never deletes anything (old train worktrees are the orchestrator's to remove; ``status``
   lists them).
2. Admits each branch only if its session's status file (``tools/session_status.py``) records a green suite on the
   branch's exact head (``--allow-unverified`` turns the refusal into a recorded warning). ``review/*`` and
   ``review-base/*`` are always refused.
3. Merges the branches in order with ``git merge --no-ff``. A conflict stops the train (``--skip-conflicting`` drops
   that branch and goes on), except a conflict confined to *generated* files: those are resolved by running their
   generator (``tools/gen_docs.py --write``, ``tools/regen_pins.py --write --attribute``, when the merged tree has
   them; ``tools/gen_registry.py --write`` for the registry lists; ``tools/gen_readme_sources.py --write`` and
   ``tools/gen_readme_corpora.py --write`` for the generated blocks, after merging README's hand-written
   parts normally), never by hand. The cheap
   generators also run after every merge, folded into that merge commit, so drift is fixed before the gate. A generator that fails, or refuses an unattributed pin move, stops the train.
4. Runs the gate on the merged head: the full suite through ``tools/suite_queue.py`` (when the merged tree has it),
   ruff, mypy, the Unicode check and the ``--check`` modes of the generators. ``--gate`` replaces the list.
5. Green and ``--push``: checks that ``origin/main`` still equals the base (after a fetch when ``--fetch``), then
   ``git push origin <head>:refs/heads/main``: no ``--force`` and no ``+``, so the remote refuses anything but a
   fast-forward. ``--push`` needs a non-empty ``--approval`` text, the user's approval as given in the invoking session;
   the tool records it and cannot check it.
6. Red and ``--bisect``: re-runs the gate on the full head once (a pass there means "not reproducible": nothing is
   pushed). Otherwise it binary-searches the first-parent merge commits for the first red prefix, ejects that branch
   (``interaction`` if the branch was green on its own), and re-merges the remaining branches on the last green prefix,
   repeating until the head is green or no branch is left.

Everything is recorded in ``$AGENTPROV_HOME/merge-train/<run-id>/report.json`` (gate logs beside it). One train runs
at a time (``flock`` on ``$AGENTPROV_HOME/merge-train/train.lock``).

Exit codes: 0 green (pushed if asked), 1 red or not reproducible, 2 refused, conflict or usage, 3 ``main`` moved.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import fnmatch
import json
import os
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import agentprov_home, git, git_ok, read_json, safe_text, utc_now, write_json_atomic  # noqa: E402
from session_status import load as load_status  # noqa: E402
from session_status import sessions_dir  # noqa: E402

REFUSED_PREFIXES = ("review/", "review-base/")
EXIT_GREEN, EXIT_RED, EXIT_REFUSED, EXIT_MOVED = 0, 1, 2, 3


@dataclass(frozen=True)
class Resolver:
    """A generator that owns some files: a merge conflict confined to them is resolved by running ``command``.

    ``block``: the file is hand-written except for the generated block between these two marker lines (README.md's
    source tables). Its hand-written parts are merged normally with the block blanked on all three sides; a conflict
    there is a real conflict. ``after_merge``: the generator is cheap and also runs after every merge, so a block that
    merged cleanly but stale is regenerated before the gate (folded into that merge commit, so bisect prefixes stay
    consistent)."""

    name: str
    tool: str  # path in the merged tree; the resolver is used only if it exists there
    patterns: tuple[str, ...]
    command: tuple[str, ...]  # ``{base}`` is the base commit; ``{branches}`` every branch commit merged so far
    block: tuple[str, str] | None = None
    after_merge: bool = False
    #: further generated blocks of the same file, each ``(tool, (begin, end), command)``, used when that tool is in the
    #: merged tree (README.md holds the source tables and the corpora listing)
    more: tuple[tuple[str, tuple[str, str], tuple[str, ...]], ...] = ()
    ready: str | None = None  # a path that must exist in the merged tree before the resolver owns anything (BF-6)
    #: for a branch whose own commit lacks ``ready`` (started before the split, so its edits are in the generated
    #: file only): run this first on a clean merge, and refuse a conflicted one (step 4a)
    adopt: tuple[str, ...] | None = None
    #: directories whose new files the command may create (a target's parts, D-1003): staged with ``add -A``
    outputs: tuple[str, ...] = ()


def _pin_patterns() -> tuple[str, ...]:
    """The files that ``tools/regen_pins.py --write`` rewrites whole, from its own family table (BF-7). Left out:
    ``C_data_model.md`` and ``README.md`` (hand-written around generated parts) and the pins of a family that can be
    skipped (it needs a cache or a tool that may be absent): a skipped family would leave the conflicted file as
    ``ours`` without a word."""
    from regen_pins import C_SPEC, FAMILIES  # same directory; read-only use of the table

    return tuple(pin for f in FAMILIES if f.write and not f.requires and not f.tool for pin in f.pins
                 if pin not in (C_SPEC, "README.md"))


def _gen_docs(target: str, path: str, ready: str, parts: str | None = None) -> Resolver:
    """A split doc: ``--write`` regenerates it from the fragments. A branch from before the split added its entries to
    the generated file only, so ``--write`` alone would drop them: ``--adopt`` first moves them into fragments.
    ``parts``: the directory of the file's generated parts (D-1003), owned and staged with it."""
    return Resolver(f"generated docs ({target})", "tools/gen_docs.py", (path, *([f"{parts}/*.md"] if parts else [])),
                    ("uv", "run", "python", "tools/gen_docs.py", "--write", target), after_merge=True, ready=ready,
                    adopt=("uv", "run", "python", "tools/gen_docs.py", "--adopt", target),
                    outputs=(parts,) if parts else ())


RESOLVERS: tuple[Resolver, ...] = (
    # Before the migration gen_docs --write does nothing, so these files are owned only once split (BF-6).
    _gen_docs("decisions", "docs/architecture/DECISIONS.md", "docs/architecture/decisions", "docs/architecture/decision-log"),
    _gen_docs("regen-batch", "docs/reports/analysis/regen-batch.md", "docs/reports/analysis/regen-batch"),
    _gen_docs("agents", "AGENTS.md", "docs/agents"),
    Resolver("spec labels", "tools/spec_labels.py", ("docs/architecture/item-labels.json",),
             ("uv", "run", "python", "tools/spec_labels.py", "--write"), ready="docs/architecture/item-labels.json"),
    Resolver("registry lists", "tools/gen_registry.py",
             ("src/agentprov/adapters/registry/_sources.py", "src/agentprov/adapters/registry/_factories.py"),
             ("uv", "run", "python", "tools/gen_registry.py", "--write"), after_merge=True,
             ready="src/agentprov/adapters/registry/_legacy_order.py"),
    Resolver("README generated blocks", "tools/gen_readme_sources.py", ("README.md",),
             ("uv", "run", "python", "tools/gen_readme_sources.py", "--write"),
             block=("<!-- BEGIN generated: sources (tools/gen_readme_sources.py --write) -->",
                    "<!-- END generated: sources -->"), after_merge=True),
    # The corpus listing moved from README.md to the user guide on 2026-10-22; each guide page holds one block.
    Resolver("user guide corpus listing", "tools/gen_readme_corpora.py", ("docs/user-guide/14-corpora.md",),
             ("uv", "run", "python", "tools/gen_readme_corpora.py", "--write"),
             block=("<!-- BEGIN generated: corpora (tools/gen_readme_corpora.py --write) -->",
                    "<!-- END generated: corpora -->"), after_merge=True),
    Resolver("user guide CLI reference", "tools/gen_user_guide_cli.py", ("docs/user-guide/11-cli-reference.md",),
             ("uv", "run", "python", "tools/gen_user_guide_cli.py", "--write"),
             block=("<!-- BEGIN generated: cli (tools/gen_user_guide_cli.py --write) -->",
                    "<!-- END generated: cli -->"), after_merge=True),
    Resolver("test pins", "tools/regen_pins.py", _pin_patterns(),
             ("uv", "run", "python", "tools/regen_pins.py", "--write", "--attribute", "{base}", "{branches}")),
)


def train_root() -> Path:
    return agentprov_home() / "merge-train"


def default_gates(tree: Path, run_id: str) -> list[list[str]]:
    """The merge gate for the merged tree: what each session runs before a push, plus the generators' checks.

    With ``tools/ci_local.py`` in the tree (D-462) that is one command: the local CI's default jobs (the full suite
    through the queue, capture, the backend jobs offline, the secrets scan, the generated-file and pin checks)."""
    if (tree / "tools" / "ci_local.py").is_file():
        return [["uv", "run", "python", "tools/ci_local.py", "--label", f"merge-train {run_id}"]]
    if (tree / "tools" / "suite_queue.py").is_file():
        suite = ["uv", "run", "python", "tools/suite_queue.py", "--label", f"merge-train {run_id}", "--",
                 "pytest", "-n", "10", "--dist", "loadgroup", "-p", "no:randomly"]
    else:
        suite = ["uv", "run", "pytest"]
    gates = [suite, ["uv", "run", "ruff", "check", "."], ["uv", "run", "mypy"],
             ["uv", "run", "python", "tools/check_unicode.py"]]
    for tool in ("tools/regen_pins.py", "tools/gen_docs.py", "tools/gen_registry.py", "tools/gen_readme_sources.py"):
        if (tree / tool).is_file():
            gates.append(["uv", "run", "python", tool, "--check"])
    return gates


# --------------------------------------------------------------------------------------------------- admission


def branch_status(name: str, sha: str, sdir: Path) -> dict[str, Any] | None:
    """The status document of the session on branch ``name`` (the one with the newest heartbeat), if any."""
    best = None
    for path in sorted(sdir.glob("*.json")) if sdir.is_dir() else []:
        doc = load_status(path)
        if doc and doc.get("branch") == name and (best is None or doc.get("heartbeat_at", "") > best.get(
                "heartbeat_at", "")):
            best = doc
    return best


def admit(repo: Path, branches: Sequence[str], sdir: Path, allow_unverified: bool
          ) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve each branch to a commit and check it; returns the admitted entries and the refusals."""
    admitted, refusals = [], []
    for name in branches:
        if name.startswith(REFUSED_PREFIXES):
            refusals.append(f"{name}: review branches are never merged by the train")
            continue
        sha = git_ok(["rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"], repo)
        if not sha:
            refusals.append(f"{name}: no such branch or commit")
            continue
        status = branch_status(name, sha, sdir)
        suite = (status or {}).get("last_suite") or {}
        verified = suite.get("commit") == sha and suite.get("result") == "green"
        entry: dict[str, Any] = {"branch": name, "sha": sha, "verified": verified, "warnings": []}
        if not verified:
            why = ("no session status file" if status is None else
                   f"last suite {suite.get('result', 'none')} on {str(suite.get('commit', '-'))[:10]}, head {sha[:10]}")
            if not allow_unverified:
                refusals.append(f"{name}: not green on its exact head ({why})")
                continue
            entry["warnings"].append(f"unverified: {why}")
        admitted.append(entry)
    return admitted, refusals


# --------------------------------------------------------------------------------------------------- the train


@dataclass
class Train:
    repo: Path
    run_id: str
    rundir: Path
    wt: Path
    base_ref: str
    base_sha: str
    report: dict[str, Any] = field(default_factory=dict)
    gate_cache: dict[str, bool] = field(default_factory=dict)
    merged_shas: list[str] = field(default_factory=list)  # branch commits merged on the current chain
    gates: list[list[str]] | None = None
    log: Callable[[str], None] = print

    def save(self) -> None:
        self.report["updated_at"] = utc_now()
        write_json_atomic(self.rundir / "report.json", self.report)

    def g(self, *args: str, check: bool = True) -> str:
        return git(list(args), self.wt, check=check)

    def create_worktree(self) -> None:
        self.rundir.mkdir(parents=True, exist_ok=True)
        git(["worktree", "add", "--detach", "--quiet", str(self.wt), self.base_sha], self.repo)

    def merge(self, entry: dict[str, Any], k: int, n: int, skip_conflicting: bool) -> str:
        """Merge one branch; returns ``merged``, ``resolved``, ``skipped`` or ``conflict``."""
        msg = f"Merge branch '{entry['branch']}' (merge train {self.run_id}, {k}/{n})"
        out = subprocess.run(["git", "merge", "--no-ff", "--no-edit", "-m", msg, entry["sha"]], cwd=self.wt,
                             capture_output=True, text=True, env=dict(os.environ, GIT_NO_LAZY_FETCH="1"))
        if out.returncode == 0:
            return "merged"
        conflicted = [p for p in self.g("diff", "--name-only", "--diff-filter=U").splitlines() if p]
        entry["conflicts"] = conflicted
        if not conflicted:
            self.g("merge", "--abort", check=False)
            entry["error"] = out.stderr.strip()[-2000:]
            return "conflict"
        plan = self.resolution_plan(conflicted)
        legacy = [r.name for r, _files in plan or [] if self.predates(r, entry["sha"])]
        if legacy:
            # Ours would lose the branch's entries and theirs main's; the fragments cannot hold a text conflict.
            entry["error"] = (f"{', '.join(legacy)}: the branch predates the split; merge main into the branch, keep "
                              "both sides of the generated file, run tools/gen_docs.py --adopt and commit")
            self.g("merge", "--abort", check=False)
            return "skipped" if skip_conflicting else "conflict"
        if plan is not None:
            # Start each generated file from our side, so no generator ever reads conflict markers; a file with a
            # generated block keeps both sides' hand-written parts (or is a real conflict).
            for resolver, files in plan:
                for path in files:
                    if resolver.block is None:
                        self.g("checkout", "--ours", "--", path)
                    elif not self.merge_outside_block(path, self.blocks(resolver)):
                        entry["error"] = f"{path}: a conflict outside the generated block"
                        self.g("merge", "--abort", check=False)
                        return "skipped" if skip_conflicting else "conflict"
            for resolver, files in plan:
                for command in self.commands(resolver):
                    cmd: list[str] = []
                    for c in command:
                        if c == "{branches}":
                            cmd += [*self.merged_shas, entry["sha"]]
                        else:
                            cmd.append(c.replace("{base}", self.base_sha))
                    res = subprocess.run(cmd, cwd=self.wt, capture_output=True, text=True)
                    entry.setdefault("resolved_by", []).append({"resolver": resolver.name, "files": files,
                                                                "command": cmd, "exit": res.returncode,
                                                                "output": (res.stdout + res.stderr)[-4000:]})
                    if res.returncode != 0:
                        self.g("merge", "--abort", check=False)
                        return "conflict"
            # The generators may rewrite more generated files than the conflicted ones: stage every tracked change,
            # and the new files of a resolver's output directories.
            self.g("add", "--", *conflicted)
            self.g("add", "-u")
            self.stage_outputs([r for r, _files in plan])
            if not [p for p in self.g("diff", "--name-only", "--diff-filter=U").splitlines() if p]:
                self.g("commit", "--no-edit", "--quiet", "-m", msg + " [generated files regenerated]")
                return "resolved"
        self.g("merge", "--abort", check=False)
        return "skipped" if skip_conflicting else "conflict"

    def blocks(self, resolver: Resolver) -> list[tuple[str, str]]:
        """The generated blocks of the resolver's file whose generator is in the merged tree."""
        return [b for b in [resolver.block, *(blk for tool, blk, _cmd in resolver.more
                                              if (self.wt / tool).is_file())] if b is not None]

    def commands(self, resolver: Resolver) -> list[tuple[str, ...]]:
        """The resolver's command, then those of its further blocks whose generator is in the merged tree."""
        return [resolver.command, *(cmd for tool, _blk, cmd in resolver.more if (self.wt / tool).is_file())]

    def merge_outside_block(self, path: str, blocks: list[tuple[str, str]]) -> bool:
        """Three-way merge of ``path`` with every generated block blanked on every side; writes the result (blocks
        blanked, for the generators to fill) and returns True when the hand-written parts merge cleanly."""

        def blank(text: str) -> str:
            for begin, end in blocks:
                if begin in text and end in text.split(begin, 1)[1]:
                    head, rest = text.split(begin, 1)
                    text = f"{head}{begin}\n{end}{rest.split(end, 1)[1]}"
            return text

        with tempfile.TemporaryDirectory() as tmp:
            sides = []
            for stage, name in ((2, "ours"), (1, "base"), (3, "theirs")):
                shown = subprocess.run(["git", "show", f":{stage}:{path}"], cwd=self.wt, capture_output=True,
                                       text=True)
                side = Path(tmp) / name
                side.write_text(blank(shown.stdout if shown.returncode == 0 else ""), encoding="utf-8")
                sides.append(str(side))
            merged = subprocess.run(["git", "merge-file", "-p", *sides], cwd=self.wt, capture_output=True, text=True)
        if merged.returncode != 0:
            return False
        (self.wt / path).write_text(merged.stdout, encoding="utf-8")
        return True

    def predates(self, resolver: Resolver, sha: str) -> bool:
        """The branch commit ``sha`` lacks the resolver's ``ready`` path although the merged tree has it."""
        return (resolver.adopt is not None and resolver.ready is not None and self.available(resolver)
                and git_ok(["cat-file", "-e", f"{sha}:{resolver.ready}"], self.wt) is None)

    def regenerate_after_merge(self, sha: str | None = None) -> list[str]:
        """Run the cheap generators present in the merged tree; fold any change into the merge commit (local and
        unpublished). For a branch ``sha`` from before a split, the resolver's ``adopt`` runs first. Returns the
        names of the generators that changed something."""
        changed = []
        for resolver in RESOLVERS:
            if not resolver.after_merge or not self.available(resolver):
                continue
            # --branch: the merged branch, not the train's HEAD, decides whether it started before the split
            first = [(*resolver.adopt, "--branch", sha)] if sha is not None and resolver.adopt and self.predates(
                resolver, sha) else []
            staged = set(self.g("diff", "--cached", "--name-only").splitlines())
            for command in [*first, *self.commands(resolver)]:
                res = subprocess.run(list(command), cwd=self.wt, capture_output=True, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"{resolver.name}: {(res.stdout + res.stderr).strip()[-1500:]}")
            if first and resolver.ready is not None:
                self.g("add", "-A", "--", resolver.ready)  # the fragments --adopt created are new files
            self.stage_outputs([resolver])  # a new part file is a new file too
            # changed in the worktree, or fragments just staged, and not yet staged by an earlier generator
            if self.g("diff", "--name-only") or set(self.g("diff", "--cached", "--name-only").splitlines()) - staged:
                self.g("add", "-u")
                changed.append(resolver.name)
        if changed:
            self.g("commit", "--amend", "--no-edit", "--quiet")
        return changed

    def stage_outputs(self, resolvers: list[Resolver]) -> None:
        """Stage every change, new files included, under the resolvers' output directories."""
        for d in (d for r in resolvers for d in r.outputs):
            if (self.wt / d).exists():
                self.g("add", "-A", "--", d)

    def available(self, resolver: Resolver) -> bool:
        """The resolver's tool is in the merged tree, and so is its ``ready`` path (a migrated target)."""
        return (self.wt / resolver.tool).is_file() and (resolver.ready is None or (self.wt / resolver.ready).exists())

    def resolution_plan(self, conflicted: list[str]) -> list[tuple[Resolver, list[str]]] | None:
        """Resolvers covering every conflicted file, or None if any file belongs to no available generator."""
        plan: dict[str, tuple[Resolver, list[str]]] = {}
        for path in conflicted:
            owner = next((r for r in RESOLVERS if self.available(r)
                          and any(fnmatch.fnmatch(path, pat) for pat in r.patterns)), None)
            if owner is None:
                return None
            plan.setdefault(owner.name, (owner, []))[1].append(path)
        return list(plan.values())

    def gate(self, sha: str, label: str) -> bool:
        """Run the gate on ``sha`` (cached per commit); True if every command exits 0."""
        if sha in self.gate_cache:
            return self.gate_cache[sha]
        if self.g("rev-parse", "HEAD") != sha:
            self.g("checkout", "--quiet", "--detach", sha)
        gates = self.gates if self.gates is not None else default_gates(self.wt, self.run_id)
        results = []
        ok = True
        for i, cmd in enumerate(gates):
            logname = f"gate-{sha[:10]}-{i}.log"
            started = time.monotonic()
            with (self.rundir / logname).open("w", encoding="utf-8") as fh:
                rc = subprocess.run(cmd, cwd=self.wt, stdout=fh, stderr=subprocess.STDOUT).returncode
            results.append({"command": cmd, "exit": rc, "seconds": round(time.monotonic() - started, 1),
                            "log": logname, "summary": _summary(self.rundir / logname)})
            if rc != 0:
                ok = False
                break  # the first failing gate decides; the rest would not change the verdict
        self.report.setdefault("gate_runs", []).append({"commit": sha, "label": label, "green": ok,
                                                        "results": results, "at": utc_now()})
        self.gate_cache[sha] = ok
        self.save()
        self.log(f"merge-train: gate {'green' if ok else 'RED'} on {sha[:10]} ({label})")
        return ok


def _summary(log: Path) -> str:
    """The last pytest-style summary line of a gate log, if any (for the report; the log itself is kept)."""
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines[-50:]):
        if " passed" in line or " failed" in line or " error" in line:
            return safe_text(line.strip("= "), 300)
    return ""


def merge_all(train: Train, entries: list[dict[str, Any]], skip_conflicting: bool
              ) -> tuple[list[dict[str, Any]], bool]:
    """Merge ``entries`` on the current HEAD, recording each merge commit.

    Returns the merged entries in order and whether the train stopped at a conflict.
    """
    merged: list[dict[str, Any]] = []
    n = len(entries)
    for k, entry in enumerate(entries, 1):
        outcome = train.merge(entry, k, n, skip_conflicting)
        entry["outcome"] = outcome
        if outcome in ("merged", "resolved"):
            try:
                entry["regenerated"] = train.regenerate_after_merge(entry["sha"])
            except RuntimeError as exc:
                entry["outcome"], entry["error"] = "conflict", f"regenerating after the merge failed: {exc}"
                train.log(f"merge-train: {k}/{n} {entry['branch']} STOPPED: {entry['error'][:300]}")
                train.save()
                return merged, True
            entry["merge_commit"] = train.g("rev-parse", "HEAD")
            train.merged_shas.append(entry["sha"])
            merged.append(entry)
            train.log(f"merge-train: {k}/{n} {entry['branch']} {outcome}")
        else:
            train.log(f"merge-train: {k}/{n} {entry['branch']} {outcome.upper()}: "
                      f"{', '.join(entry.get('conflicts', [])) or entry.get('error', '')}")
            if outcome == "conflict":
                train.save()
                return merged, True
        train.save()
    return merged, False


def bisect(train: Train, merged: list[dict[str, Any]], green: int) -> int:
    """Index of the first branch whose prefix is red, given prefix ``green`` is green and the full prefix red.

    Prefix ``j`` is the merge commit of ``merged[j - 1]`` (prefix 0 is the base).
    """
    lo, hi = green, len(merged)  # invariant: prefix lo green, prefix hi red
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if train.gate(merged[mid - 1]["merge_commit"], f"bisect prefix {mid}/{len(merged)}"):
            lo = mid
        else:
            hi = mid
    return hi - 1


@contextlib.contextmanager
def single_train(root: Path) -> Iterator[bool]:
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / "train.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def run_train(a: argparse.Namespace, repo: Path, log: Callable[[str], None] = print) -> int:
    if a.push and not (a.approval or "").strip():
        log("merge-train: --push needs --approval with the user's approval, quoted")
        return EXIT_REFUSED
    if a.fetch:
        git(["fetch", "--quiet", "origin"], repo)
    base_sha = git_ok(["rev-parse", "--verify", "--quiet", f"{a.base}^{{commit}}"], repo)
    if not base_sha:
        log(f"merge-train: no base {a.base}")
        return EXIT_REFUSED
    admitted, refusals = admit(repo, a.branches, (a.sessions_dir or sessions_dir()).expanduser(), a.allow_unverified)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(2)
    rundir = train_root() / run_id
    train = Train(repo=repo, run_id=run_id, rundir=rundir, wt=rundir / "wt", base_ref=a.base, base_sha=base_sha,
                  gates=[shlex.split(g) for g in a.gate] if a.gate else None, log=log)
    train.report = {"run_id": run_id, "mode": a.cmd, "base": {"ref": a.base, "sha": base_sha},
                    "requested": list(a.branches), "admitted": admitted, "refusals": refusals,
                    "push_requested": bool(a.push), "approval": a.approval or "", "started_at": utc_now(),
                    "repo": str(repo)}
    for r in refusals:
        log(f"merge-train: refused {r}")
    if refusals and not a.skip_refused:
        train.report["result"] = "refused"
        rundir.mkdir(parents=True, exist_ok=True)
        train.save()
        return EXIT_REFUSED
    if not admitted:
        log("merge-train: nothing to merge")
        return EXIT_REFUSED
    train.create_worktree()
    train.report["worktree"] = str(train.wt)
    entries = [dict(e) for e in admitted]
    merged, stopped = merge_all(train, entries, a.skip_conflicting)
    train.report["merged"], train.report["attempted"] = merged, entries
    if stopped:
        train.report["result"] = "conflict"
        train.save()
        return EXIT_REFUSED
    if not merged:
        train.report["result"] = "nothing merged"
        train.save()
        return EXIT_REFUSED
    head = train.g("rev-parse", "HEAD")
    train.report["head"] = head
    if a.cmd == "plan":
        train.report["result"] = "planned"
        train.save()
        log(f"merge-train: plan {run_id}: {len(merged)} branch(es) merge onto {base_sha[:10]} -> {head[:10]}")
        return EXIT_GREEN

    start = base_sha
    green_prefix = 0
    ejected: list[dict[str, Any]] = []
    while True:
        if train.gate(head, "head"):
            break
        if not a.bisect:
            train.report["result"] = "red"
            train.save()
            return EXIT_RED
        train.gate_cache.pop(head, None)
        if train.gate(head, "head re-run"):
            train.report["result"] = "not reproducible"
            train.save()
            log("merge-train: the head failed once and passed once; nothing is pushed")
            return EXIT_RED
        k = bisect(train, merged, green_prefix)
        culprit = merged[k]
        culprit["ejected"] = "interaction" if culprit.get("verified") else "red"
        ejected.append(culprit)
        log(f"merge-train: ejected {culprit['branch']} ({culprit['ejected']}; prefix {k + 1} is the first red one)")
        start = merged[k - 1]["merge_commit"] if k > 0 else start
        green_prefix = k
        rest = [dict(e, outcome=None, merge_commit=None) for e in merged[k + 1:]]
        train.g("checkout", "--quiet", "--detach", start)
        train.merged_shas = [e["sha"] for e in merged[:k]]
        remerged, stopped = merge_all(train, rest, a.skip_conflicting)
        merged = merged[:k] + remerged
        train.report["merged"], train.report["ejected"] = merged, ejected
        if stopped:  # without the ejected branch, a later one no longer merges cleanly
            train.report["result"] = "conflict after ejection"
            train.save()
            return EXIT_REFUSED
        if len(merged) == k:  # nothing left on top of the green prefix
            head = start
            if start == base_sha:
                train.report["result"] = "red"
                train.save()
                return EXIT_RED
            break
        head = train.g("rev-parse", "HEAD")

    train.report["head"] = head
    train.report["result"] = "green"
    train.save()
    log(f"merge-train: green head {head[:10]} with {', '.join(e['branch'] for e in merged)}")
    if not a.push:
        return EXIT_GREEN
    if a.fetch:
        git(["fetch", "--quiet", "origin"], repo)
    now_base = git_ok(["rev-parse", "--verify", "--quiet", f"{a.base}^{{commit}}"], repo)
    if now_base != base_sha:
        train.report["result"] = "main moved"
        train.save()
        log(f"merge-train: {a.base} moved from {base_sha[:10]} to {(now_base or '?')[:10]}; start a new train")
        return EXIT_MOVED
    remote, _, branch = a.base.partition("/")
    out = subprocess.run(["git", "push", remote, f"{head}:refs/heads/{branch}"], cwd=repo, capture_output=True,
                         text=True, env=dict(os.environ, GIT_NO_LAZY_FETCH="1"))
    train.report["push"] = {"exit": out.returncode, "output": (out.stdout + out.stderr)[-2000:], "at": utc_now()}
    train.report["result"] = "pushed" if out.returncode == 0 else "push failed"
    train.save()
    log(f"merge-train: push {'done' if out.returncode == 0 else 'FAILED'}: {safe_text(out.stderr.strip(), 300)}")
    return EXIT_GREEN if out.returncode == 0 else EXIT_MOVED


def show_status(run_id: str | None) -> int:
    root = train_root()
    runs = sorted(p for p in root.glob("*/report.json")) if root.is_dir() else []
    if run_id:
        runs = [p for p in runs if p.parent.name == run_id]
        if not runs:
            print(f"merge-train: no run {safe_text(run_id)}")
            return EXIT_REFUSED
        print(json.dumps(read_json(runs[0]), indent=2, sort_keys=True, ensure_ascii=True))
        return EXIT_GREEN
    for path in runs:
        try:
            rep = read_json(path)
        except (OSError, ValueError):
            continue
        branches = ", ".join(e.get("branch", "?") for e in rep.get("merged", rep.get("admitted", [])))
        wt = "worktree kept" if (path.parent / "wt").exists() else "no worktree"
        print(f"{path.parent.name}  {safe_text(rep.get('mode', '?'), 5):<5} {safe_text(rep.get('result', '?'), 18):<18} "
              f"{safe_text(branches, 100)}  ({wt})")
    return EXIT_GREEN


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("-C", dest="cwd", type=Path, default=Path.cwd(), help="any worktree of the repository")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        s = sub.add_parser(name, allow_abbrev=False)
        s.add_argument("branches", nargs="+")
        s.add_argument("--base", default="origin/main")
        s.add_argument("--fetch", action="store_true", help="git fetch origin first (network)")
        s.add_argument("--sessions-dir", type=Path)
        s.add_argument("--allow-unverified", action="store_true",
                       help="admit branches without a green suite on their head (recorded as a warning)")
        s.add_argument("--skip-refused", action="store_true", help="go on without refused branches")
        s.add_argument("--skip-conflicting", action="store_true", help="drop a conflicting branch and go on")
        s.add_argument("--gate", action="append", help="a gate command (repeatable; replaces the default gate)")
        s.add_argument("--bisect", action="store_true", help="on red, find and eject the failing branch")
        s.add_argument("--push", action="store_true", help="fast-forward the base branch on green (never forced)")
        s.add_argument("--approval", help="the user's push approval, quoted from the invoking session")
    st = sub.add_parser("status", allow_abbrev=False)
    st.add_argument("run_id", nargs="?")
    a = p.parse_args(argv)
    if a.cmd == "status":
        return show_status(a.run_id)
    if a.cmd == "plan":
        a.bisect = a.push = False
    top = git_ok(["rev-parse", "--show-toplevel"], a.cwd)
    if top is None:
        print(f"merge-train: {a.cwd} is not inside a git worktree")
        return EXIT_REFUSED
    with single_train(train_root()) as mine:
        if not mine:
            print("merge-train: another train is running")
            return EXIT_REFUSED
        return run_train(a, Path(top))


if __name__ == "__main__":
    raise SystemExit(main())
