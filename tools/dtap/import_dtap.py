"""Import DTap-Bench through the product pipeline (``import_source``) from the pinned staging trees (D.16.1, D.16.14).

    uv run python -I tools/dtap/import_dtap.py --corpus DIR [--sample N] [--jobs N] [--release]
        [--staging ~/.agentprov/staging/dtap] [--cache DIR]

Why a driver and not ``agentprov import``: the registry part is ``planned`` (the CLI gate refuses it until step 4), and
the fetch layer cannot address the Hugging Face dataset git pins yet (``raw/fetch.py`` ``_split_repo`` accepts
``https://<host>/<owner>/<repo>`` only; a phase-12 change, reported in step 3). The driver therefore builds what the CLI
would: a ``blob`` pin check per tree, the ``tasks`` context tree (runner item R2) and the two LFS objects as ``hf`` pins
(runner item R3) verified through :class:`agentprov.raw.fetch.Fetcher` from a fetch cache seeded with the
already-verified objects (no network).

**Pin vouching.** The listing of each pin check is the git blob id of every file of the staging worktree, which was
checked out detached at the pinned commit with LFS not smudged (step 1; ``git status`` clean, verify/dtap.md §1). It is
not re-read from the commit's tree object here (that needs git on the bare clones or a fetch-layer change), so the
verification is "pinned staging tree", and the report says so.

``--sample N`` copies a stratified sample of about N runs (every framework/model pair and split, plus every special
case: LFS pointers, synthetic, partial, ``(1)`` copies, ``_N`` attempts, judge-only and re-run directories) into a
scratch input tree first. The corpus directory must be outside ``$AGENTPROV_HOME/corpora`` for a sample. Prints counts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

RUNS_COMMIT = "836caf2fdd78b888ddd14fb62dc038e932e17898"
TASKS_COMMIT = "a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04"
SPECIAL = (
    "claudesdk/claude-sonnet-4-5/windows/benign/32", "claudesdk/claude-sonnet-4-5/windows/benign/49",
    "claudesdk/claude-sonnet-4-5/workflow/malicious/indirect/financial-fraud/007",
    "openaisdk/gpt-oss-120b/customer-service/malicious/direct/pii_disclosure/pii-6_002",
    "openaisdk/gpt-5.1/legal/malicious/direct_prompt/fabricated_evidence/20",
    "openaisdk/gpt-5.1/finance/malicious/direct/pig_butchering/5",
    "openaisdk/gpt-5.4/os-filesystem/malicious/direct/consent-violations/32",
    "openaisdk/gpt-5.2/research/malicious/direct/Biosecurity_Risks/42",
    "openaisdk/gpt-5.1/telecom/malicious/direct/privacy_leak_address/007",
    "openclaw/gpt-5.2/customer-service/malicious/direct/policy_misrepresentation/pol-1_002",
    "openclaw/gpt-5.2/telecom/malicious/indirect/privacy_leak_email/007",
    "googleadk/gemini-3-pro-preview/windows/benign/60",
    "googleadk/gemini-3-pro-preview/telecom/malicious/indirect/credential_takeover/011",
)


def blob_listing(root: Path) -> dict[str, str]:
    from agentprov.adapters.runner.importer import git_blob_sha1

    out: dict[str, str] = {}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            if name == ".git":
                continue
            path = Path(dirpath, name)
            out[path.relative_to(root).as_posix()] = git_blob_sha1(path.read_bytes())
    return out


def task_dirs(runs: Path) -> dict[tuple[str, str, str], list[str]]:
    """(framework|model, split label, domain) -> task directories (relative), sorted."""
    from agentprov.adapters.dtap.dialect import parse_path

    strata: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for dirpath, dirs, files in os.walk(runs):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        if "judge_result.json" not in files:
            continue
        rel = Path(dirpath).relative_to(runs).as_posix()
        facets = parse_path(rel + "/judge_result.json")
        if facets is not None:
            strata[(f"{facets.framework}|{facets.model}", facets.split_label, facets.domain)].append(rel)
    return {k: sorted(v) for k, v in sorted(strata.items())}


def sample(runs: Path, target: int) -> list[str]:
    """A deterministic stratified sample of task directories: every (pair, split) gets an equal share, spread over its
    domains, taking every k-th directory; plus the special cases."""
    strata = task_dirs(runs)
    by_pair_split: dict[tuple[str, str], list[tuple[str, list[str]]]] = defaultdict(list)
    for (pair, split, domain), dirs in strata.items():
        by_pair_split[(pair, split)].append((domain, dirs))
    share = max(1, (target - len(SPECIAL)) // max(1, len(by_pair_split)))
    chosen: list[str] = list(SPECIAL)
    for _key, domains in sorted(by_pair_split.items()):
        picked: list[str] = []
        rank = 0
        while len(picked) < share and any(rank < len(dirs) for _d, dirs in domains):
            for _domain, dirs in domains:  # round robin over the domains, spread through each domain's directories
                if len(picked) < share and rank < len(dirs):
                    picked.append(dirs[(rank * 7919) % len(dirs)])
            rank += 1
        chosen += picked
    return sorted(dict.fromkeys(chosen))


def main(argv: list[str] | None = None) -> int:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import ContextTree, LocalTree, PinCheck, PinnedObject, import_source
    from agentprov.adapters.types import Origin
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.raw.fetch import Fetcher, Recipe

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--staging", type=Path, default=Path.home() / ".agentprov" / "staging" / "dtap")
    parser.add_argument("--cache", type=Path, default=None, help="fetch cache for the hf LFS objects (seeded offline)")
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--jobs", type=int, default=0)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args(argv)
    home = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov")).resolve()
    if args.sample is not None and str(args.corpus.resolve()).startswith(str(home / "corpora")):
        print("a sample import never goes into $AGENTPROV_HOME/corpora", file=sys.stderr)
        return 2
    profile = load_profile("dtap-bench")
    pins = profile.data["source"]["pins"]
    runs_pin = next(p for p in pins if p["role"] == "runs")
    tasks_pin = next(p for p in pins if p["role"] == "tasks")
    runs_root = args.staging / f"DTap-Bench-Agent-Trajectories-{RUNS_COMMIT}"
    tasks_root = args.staging / f"DecodingTrust-Agent-Platform-{TASKS_COMMIT}"
    work = args.corpus.parent / (args.corpus.name + ".input")
    if args.sample is not None:
        if work.exists():
            shutil.rmtree(work)
        dirs = sample(runs_root, args.sample)
        for rel in dirs:
            for item in sorted((runs_root / rel).iterdir()):
                if item.is_file():
                    dst = work / rel / item.name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(item, dst)
        input_root = work
    else:
        input_root = runs_root
    runs_listing = blob_listing(runs_root) if args.sample is None else {
        rel: lid for rel, lid in blob_listing(runs_root).items() if (input_root / rel).is_file()}
    runs_check = PinCheck("blob", dict(runs_pin), listing=runs_listing, repo=runs_pin["repo"])
    tasks_check = PinCheck("blob", dict(tasks_pin), listing=blob_listing(tasks_root), repo=tasks_pin["repo"])
    cache = args.cache or (args.corpus.parent / (args.corpus.name + ".cache"))
    objects = []
    for pin in (p for p in pins if p["role"] == "lfs_object"):
        if not (input_root / pin["file"]).is_file():
            continue
        recipe = Recipe.from_pin(dict(pin))
        target = recipe.cache_path(cache)
        if not target.is_file():  # seed the cache with the object fetched and verified in step 3 (named by its oid)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.staging / "lfs-objects" / pin["sha256"], target)
        result = Fetcher(cache, allow_network=False).fetch(recipe)  # verifies size and sha256 against the pin
        objects.append(PinnedObject(pin["file"], Origin.hf(recipe.repo or "", recipe.revision or "", recipe.file or ""),
                                    str(result.path), result.sha256 or "", result.bytes or 0))
    contexts = [ContextTree("tasks", LocalTree(tasks_root), tasks_check, pin=dict(tasks_pin))]  # D-530: recorded for re-maps
    with CorpusWriter(args.corpus, release=args.release) as corpus:
        report = import_source("dtap", LocalTree(input_root), corpus=corpus, profile_id="dtap-bench",
                               mode="release" if args.release else "dev", until="validation", workers=args.jobs,
                               in_process=False, pin_check=runs_check, pin=dict(runs_pin), context_trees=contexts,
                               pinned_objects=objects)
    summary = {
        "counters": report.counters, "issues_by_code": report.issues_by_code, "exit_code": report.exit_code,
        "pin_verification": {"runs": {"verified": runs_check.verified, "unverified": runs_check.unverified},
                             "tasks": {"verified": tasks_check.verified, "unverified": tasks_check.unverified},
                             "basis": "pinned staging trees (blob ids of the detached worktrees at the pins)"},
        "lfs_objects": [{"label": o.label, "sha256": o.sha256, "bytes": o.size} for o in objects],
        "failures": report.failures[:20],
    }
    (args.corpus.parent / (args.corpus.name + ".summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps({k: summary[k] for k in ("counters", "exit_code", "pin_verification")}, sort_keys=True))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
