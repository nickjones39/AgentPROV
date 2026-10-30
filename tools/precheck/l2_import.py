"""Level 2 of the corpus pre-check: import a part's sampled labels through the product pipeline into a scratch corpus.

    uv run python tools/precheck/l2_import.py --sample SAMPLE.json --corpus DIR --source S --part P
        [--jobs N] [--mode dev|release] [--until STAGE] [--strategy any-glob|per-label|prune] [--limit N]
        [--summary-json PATH] [--cache DIR] [--input PATH] [--no-seed] [--allow-first-mapping]
    uv run python tools/precheck/l2_import.py --recipes          # every part's tree recipe (or why it is blocked)

Run it through the queue (README §4): ``uv run python tools/suite_queue.py --class import --cpu 2 --label
precheck-<corpus_id> -- uv run python tools/precheck/l2_import.py ...``. ``DIR`` must lie under
``$AGENTPROV_HOME/migration-work/precheck/`` (never under ``corpora/``); the writer creates ``DIR.partial``.

**Trees.** Each part is imported with :func:`agentprov.adapters.runner.importer.import_source` on the tree class the CLI
or the family's trial driver builds (``RECIPES``; ``--recipes`` prints them): a git pin from the verified fetch cache
(``GitPinTree``, what ``agentprov import --fetch`` builds; ``--input CLONE`` builds the CLI's ``LocalTree`` +
``PinCheck('blob')`` instead), a staging bare clone seeded into a scratch cache with ``tools/agentdojo/phase10d_trial.py``
(``seed``, ``_fetcher_recipe``: covering pathspecs when blobs are absent), the AgentDojo-PROV listing pin (``LocalTree`` +
``PinCheck('listing')``), a staged download pin as an archive input (``tools/inspect/phase10p_trial.py`` ``_tree``:
``verify_download`` or ``verify_parts`` then ``ArchiveTree``), or the DTap trees (``tools/dtap/import_dtap.py``: runs
``LocalTree`` + blob pin check, ``tasks`` context tree, the LFS objects as ``PinnedObject``; the blob listings are read from
the staged bare clones with ``git ls-tree`` instead of hashing the worktree), or the phase-10j trees
(``tools/agentdojo/phase10j_trial.py`` ``_tree``: the part's own pin, a git pin as ``GitPinTree`` over a scratch cache
seeded by its ``seed`` from the phase-10c bare clone (covering pathspecs when blobs are absent), a ``zenodo`` pin as an
``ArchiveTree`` of the staged deposit after ``verify_download``; nested containers are expanded by the importer from the
profile's ``[import] nested``). The CLI status gate is bypassed on purpose, as every trial driver does (planned parts).

**Selection.** The pre-registered selection is ``ImportFilters(include_paths=<the sampled labels, glob-escaped>)``. The
product ANDs ``include_paths`` (``importer.py`` ``discover``: ``all(_match(label, g) ...)``), so a list of several labels
selects nothing. Strategies:

* ``any-glob`` (default): one ``include_paths`` entry, a ``str`` subclass ``AnyOf`` holding the escaped globs, recorded in
  ``corpus.json`` as ``precheck:any-of:<n>:sha256:<digest of the escaped globs>``; a process-local shim of the
  importer's matcher answers it as the OR of the escaped globs (every other glob goes to the product matcher unchanged).
  A hook on discovery checks, **before anything is mapped**, that the kept candidates are exactly the sampled labels, and
  stops (exit 3) otherwise.
* ``per-label``: one import per label (``include_paths=(escaped label,)``) into the same corpus (resumable; the manifest
  records the last selection). Pure product API, slower (an archive input is stored and expanded again each time).
* ``prune``: git or local trees only: the sampled units stay in the tree, every other candidate of the reader is
  dropped from the listing (context artefacts and auxiliaries stay), as ``phase10d_trial._sample`` does, repeated until the
  reader's candidates are exactly the sample (a reader may promote a file once its neighbours are gone: DTap takes a
  directory's judge file only where no trajectory is left). It stops (exit 3) before anything is mapped when the
  candidates still differ or a sampled unit's own inputs (``auxiliary_for``) changed. The manifest then
  records no filter, so the scratch corpus can be sealed (``package`` refuses partial corpora) for the withholding check
  of a sealed copy; it must never leave the scratch area.

Archive inputs select whole members by chain label (``<container>!/<member>``); an Inspect ``.eval``, a credleak cell, an
autogen ``runs.jsonl`` and an MCPHunt document are selected whole (their executions cannot be subsampled by path).
``--limit`` passes the product's per-unit limit through. Dev mode by default (``--mode release`` is allowed by
``import_source``; only the CLI forbids filters with ``--release``).

The summary (``--summary-json``, default ``DIR.l2-import.json``) holds the ImportReport (counters, issues by code,
failures, register rows), the recipe, the selection check and the pin verification counts; paths as ``~``, labels only,
never source text.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sys
import time
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import (  # noqa: E402
    IMPORT_FORMAT,
    agentprov_home,
    escape_label,
    guard_scratch,
    load_tool,
    precheck_root,
    scrub,
    sha256_file,
    sha256_text,
    tilde,
    write_json,
)

# ================================================================================================ recipes
STAGING: Final = Path("staging")  # relative to $AGENTPROV_HOME
UPSTREAM: Final = Path.home() / "Desktop" / "PhD" / "Labs"

#: git pins read from the shared, verified fetch cache (``agentprov import --fetch``; ``--input CLONE`` gives the CLI's
#: ``--input --verify-against-pin`` tree). The stored E2 imports used the clones under AgentPROV-upstream (same origins).
GIT_CACHE: Final = {
    ("agentdojo", "head"), ("agentdojo", "2024-06"), ("agentdyn", "a"), ("agentdyn", "b"), ("agentdyn", "c"),
    ("rope", "head"), ("autodojo", "rope-slice"), ("agent-security-tools-survey", "agentharm"),
    ("agent-security-tools-survey", "agentdojo-runs"), ("mandate-agentdojo-eval", "head"), ("kexin-xu-01-agentharm", "logs"),
    ("fragfuse-agentharm", "logs"), ("atia-benchmark", "logs"),
}
#: Pin role for parts whose own name is no pin (the CLI needs ``--pin head`` for AgentDyn b and c).
PIN_ROLE: Final = {("agentdyn", "b"): "head", ("agentdyn", "c"): "head"}
#: git pins staged as bare partial clones (phase 10c/10f/10g/10l), seeded into a scratch cache by phase10d_trial.seed.
SEEDED: Final = {
    "interbolt-agentdojo": "10c/interbolt/interbolt-agentdojo.git", "melon-agentdojo": "10c/melon/MELON.git",
    "glitch-agentdojo": "10c/glitch/Glitch.git", "mohameduk-agentdojo": "10c/mohameduk/agentdojo.git",
    "tacit-agentdojo": "10c/tacit/Tacit.git", "geryon-agentdojo": "10c/geryon/geryon.git",
    "hilarytorn-trajectory-poisoning": "10c/hilarytorn/in-context-trajectory-poisoning.git",
    "yockcheng-prompt-injection-harness": "10c/yockcheng/prompt-injection-harness.git",
    "shreeyavarma-llm-safety": "10c/shreeyavarma/llm_safety.git", "gate-agentdojo": "10c/gate/gate.git",
    "sentry-agentdojo": "10c/sentry/SENTRY-Anytime-Valid-E-Process-Monitoring-of-LLM-Agent-Action-Streams.git",
    "bookkeeper-agentdojo": "10c/bookkeeper/bookkeeper.git", "aiauthz-agentdojo": "10c/aiauthz/aiAuthZ.git",
    "kongminos-agentdojo": "10c/kongminos/jspace-agentdojo-950.git", "ceferisbarov-agentdojo": "10c/ceferisbarov/agentdojo.git",
    "linyxus-agentdojo": "10c/linyxus/agentdojo.git", "craibench-agentdojo": "10c/craibench/CrAIBench.git",
    "menelaus29-ipi-multidomain": "10c/menelaus29/ipi-multidomain-agent-study.git",
    "llm-lock-agentdojo": "10c/llm-lock/llm-lock.git", "drift": "10c/ref-drift/DRIFT.git",
    "openagentsafety": "10g/openagentsafety.git", "whistlebench": "10f/whistlebench/whistlebench.git",
}
#: The AgentDojo-PROV listing pin (another project folder; read only).
LISTING: Final = {("adprov-v1", "release"): UPSTREAM / "AgentDojo-PROV-framework" / "corpus" / "corpus-prov"}
#: Staged download pins (archive inputs): the directory that holds the pinned file (its pinned path below it).
ARCHIVE: Final = {
    ("seagent-agentdojo", "head"): STAGING / "10f" / "seagent-zenodo-23218779",
    ("credleak-p15b", "head"): STAGING / "10k" / "v3",
    ("autogen-guard-placement", "v1.0"): STAGING / "10e" / "zenodo_23025259",
    ("what-surrounds", "runs-named"): STAGING / "10m" / "zenodo_21944598",
    ("code-agent-misalignment-geminicli", "results-raw"): STAGING / "10e" / "zenodo_20404563",
    **{("controlarena-persistent", p): STAGING / "10p" / "hf_idacy_control-arena"
       for p in ("zip-3-001", "zip-3-002", "zip-3-003", "batch-runs", "auditor")},
}
DTAP_RUNS_COMMIT: Final = "836caf2fdd78b888ddd14fb62dc038e932e17898"
DTAP_TASKS_COMMIT: Final = "a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04"
#: Phase-10j sources (wave 7): trees from tools/agentdojo/phase10j_trial.py, one pin per part (Kavach: three git pins).
PHASE10J: Final = frozenset({"authority-caps-agentdojo", "ipi-defenses-agentdojo", "dca-agentdojo", "kavach-agentdojo",
                             "environmentoptim-agentdojo", "drift1-agentdojo"})
_DCA_HELD: Final = (
    "import held until D-455 lands (orchestrator, 2026-10-15); today a url pin is not an archive input of the runner "
    "(DOWNLOAD_PIN_KINDS zenodo/hf; routing R-10j-3), and the phase-10j trial did not import it either (census only); "
    "R-10j-4/R-10j-5 keep 3 logs from sealing. L1 only")
#: Parts L2 cannot import faithfully today (the reason is printed; README §4 records them as blocked).
BLOCKED: Final = {
    ("dca-agentdojo", "v1"): _DCA_HELD, ("dca-agentdojo", "drift"): _DCA_HELD,
    ("redcode-exec-openhands", "head"): (
        "six same-role download pins and the outcomes, prompts and dataset in the separate supp zip: auxiliary_for looks "
        "in the same listing only and ContextTree takes no archive, so every unit would lack its score (runner gap, not "
        "routed); interim: tools/openhands/map_census.py redcode"),
    ("mcphunt", "head"): (
        "RB-1 (reader not multi_execution), RB-2 (64 MiB element limit outside [import] limits), RB-3 (results over "
        "1 MiB not carved); no offline pin vouching (HF tree not in the fetch cache; LFS objects need PinnedObject)"),
    ("agentops-bench", "pilot-v1-seeded"): (
        "the tasks zip is a context pin that only the unmerged phase-10i follow-up driver (p20 ZipContextTree) can serve; "
        "without it the task join (D-194) fails for every unit"),
    ("agentdojo", "live"): "no raw data (live capture part)", ("autodojo", "live"): "no raw data (live capture part)",
    ("agentdyn", "live"): "no raw data (live capture part)",
    ("agentharm", "live"): "no raw data (live part, Inspect harness)",
    ("agentdyn", "d"): "owned by drift (check under drift · head)",
    ("agentdyn", "history"): "blob:none clone, no blobs staged; no history importer",
    ("adprov-v1", "converted-legacy"): "compat oracle (never imported)",
    ("drift", "history"): "out of scope (README §1); reference-policy snapshot",
    ("foobench", "fixture"): "synthetic test fixture source (out of the listing)",
}
#: First mappings of parts that have never been mapped through the product path (decision of the AgentDyn owner).
FIRST_MAPPING: Final = {("agentdyn", "b")}


def recipe_kind(source: str, part: str) -> str:
    key = (source, part)
    if key in BLOCKED:
        return "blocked"
    if key in GIT_CACHE:
        return "git-cache"
    if source in SEEDED:
        return "git-seeded"
    if key in LISTING:
        return "listing"
    if key in ARCHIVE:
        return "archive"
    if key == ("dtap", "head"):
        return "dtap"
    if source in PHASE10J:
        return "phase10j"
    return "unknown"


@dataclass
class Built:
    """Everything ``import_source`` needs for one part, plus what the summary records about it."""

    source: str  # the source imported (the serving source of a ``via`` part)
    part: str
    requested: tuple[str, str]
    corpus_id: str
    profile: Any
    pin: dict[str, Any] | None
    tree: Any
    pin_check: Any = None
    context_trees: list[Any] = field(default_factory=list)
    pinned_objects: list[Any] = field(default_factory=list)
    select: dict[str, frozenset[str]] = field(default_factory=dict)
    recipe: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


def _capability(source: str, part: str) -> Any:
    from agentprov.adapters.registry import get_source

    caps = [c for c in get_source(source).capabilities if c.part == part]
    if not caps:
        raise SystemExit(f"{source} has no registry part {part!r}")
    return caps[0]


def _pin(profile: Any, part: str, role: str | None) -> dict[str, Any] | None:
    """The CLI's pin choice (``cli/import_.py`` ``_pin``)."""
    pins = [_thaw(p) for p in profile.data.get("source", {}).get("pins", ())]
    if role:
        return next((p for p in pins if p.get("role") == role), None)
    for predicate in (lambda p: p.get("part") == part and p.get("primary") is True,
                      lambda p: p.get("role") == part, lambda p: p.get("part") == part):
        found = next((p for p in pins if predicate(p)), None)
        if found is not None:
            return found
    return None


def _git_env_listing(bare: Path, commit: str) -> dict[str, str]:
    """Path -> blob id of every blob of ``commit`` in a staged bare clone (no lazy fetch, file protocol only)."""
    trial = load_tool("agentdojo/phase10d_trial.py")
    out: dict[str, str] = {}
    for entry in trial._git(bare, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if entry:
            head, path = entry.split(b"\t", 1)
            mode_kind_oid = head.split()
            if mode_kind_oid[1] == b"blob":
                out[path.decode("utf-8")] = mode_kind_oid[2].decode("ascii")
    return out


def build(source: str, part: str, *, cache: Path | None, input_path: Path | None, scratch: Path | None,
          seed_cache: bool = True, allow_first_mapping: bool = False) -> Built:
    """The tree (and pin check, context trees, pinned objects) of ``source · part`` (see the module docstring)."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import (
        ContextTree,
        GitPinTree,
        LocalTree,
        PinCheck,
        PinnedObject,
    )
    from agentprov.ingest.limits import IngestLimits
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir
    from agentprov.raw.origins import Origin

    kind = recipe_kind(source, part)
    if kind == "blocked":
        raise SystemExit(f"{source} · {part}: blocked for L2: {BLOCKED[(source, part)]}")
    if kind == "unknown":
        raise SystemExit(f"{source} · {part}: no L2 recipe")
    if (source, part) in FIRST_MAPPING and not allow_first_mapping:
        raise SystemExit(f"{source} · {part}: never mapped through the product path; an L2 import would be a first "
                         "mapping (owner's decision). Pass --allow-first-mapping once it is decided.")
    capability = _capability(source, part)
    serving, served_part = source, part
    select: dict[str, frozenset[str]] = {}
    notes: list[str] = []
    if capability.via:  # D.3.1: the AutoDojo slice is imported through ROPE with the slice's attack selected
        table = load_profile(str(capability.profile)).family_table().get("attack_provenance")
        attack = str(table["attack"]) if isinstance(table, Mapping) and isinstance(table.get("attack"), str) else None
        serving = str(capability.via)
        served = next(c for c in _capability_list(serving) if c.role == "source" and c.import_status is not None)
        served_part = str(served.part)
        capability = served
        if attack:
            select["attack"] = frozenset({attack})
            notes.append(f"via {serving} · {served_part}: --select attack={attack} implied (CLI _served)")
    profile = load_profile(str(capability.profile))
    pin = _pin(profile, served_part, PIN_ROLE.get((source, part)))
    corpus_id = str(capability.corpus_id or serving)
    limits = IngestLimits()
    built = Built(serving, served_part, (source, part), corpus_id, profile, pin, None, select=select, notes=notes)
    home = agentprov_home()
    if kind == "git-cache":
        assert pin is not None
        recipe = Recipe.from_pin(pin, canonical_repo=profile.data["source"].get("canonical_repo"))
        fetcher = Fetcher(resolve_cache_dir(str(cache) if cache else None))
        if not fetcher.plan(recipe).cached:
            raise SystemExit(f"{source} · {part}: the pinned commit is not in the fetch cache {tilde(fetcher.cache_dir)}; "
                             "no fetch is made here (the user's yes is needed for network)")
        if input_path is not None:  # the CLI's --input CLONE --verify-against-pin
            entries, _skipped = fetcher.git_tree(recipe)
            listing = {e.path: e.oid for e in entries if e.is_blob}
            built.tree = LocalTree(input_path, limits=limits)
            built.pin_check = PinCheck("blob", pin, listing=listing, repo=recipe.repo,
                                       history=fetcher.history_index(recipe))
            built.recipe = {"kind": kind, "tree": "LocalTree+PinCheck(blob)", "input": tilde(input_path),
                            "cache": tilde(fetcher.cache_dir), "history_index": fetcher.history_index(recipe) is not None}
        else:
            built.tree = GitPinTree(fetcher, recipe)
            built.recipe = {"kind": kind, "tree": "GitPinTree", "cache": tilde(fetcher.cache_dir),
                            "commit": recipe.commit, "paths": list(recipe.paths),
                            "history_index": built.tree.history is not None}
    elif kind == "git-seeded":
        trial = load_tool("agentdojo/phase10d_trial.py")
        bare = home / STAGING / SEEDED[source]
        scratch_cache = cache or ((scratch or precheck_root() / corpus_id) / "cache")
        _p, recipe0, _pin0 = trial._recipe(profile.id)
        if not Fetcher(scratch_cache).plan(recipe0).cached:
            if not seed_cache:
                raise SystemExit(f"{source} · {part}: scratch cache {tilde(scratch_cache)} not seeded (drop --no-seed)")
            scratch_cache.mkdir(parents=True, exist_ok=True)
            seeded = trial.seed(profile.id, bare, scratch_cache)
            notes.append(f"seeded {tilde(scratch_cache)} from {tilde(bare)}: {seeded['objects']} objects, "
                         f"{seeded['absent_blobs']} absent blobs")
        _profile, fetcher, recipe, pin, absent = trial._fetcher_recipe(profile.id, scratch_cache)
        built.pin = pin
        built.tree = GitPinTree(fetcher, recipe)
        built.recipe = {"kind": kind, "tree": "GitPinTree (phase10d_trial._fetcher_recipe)", "cache": tilde(scratch_cache),
                        "seed_from": tilde(bare), "commit": recipe.commit, "covering_paths": len(recipe.paths),
                        "absent_blobs": len(absent), "history_index": built.tree.history is not None}
    elif kind == "listing":
        assert pin is not None
        from agentprov.adapters.registry import READERS
        from agentprov.adapters.runner import resolve_factory

        root = input_path or LISTING[(source, part)]
        reader = resolve_factory(READERS[str(profile.data["import"]["dialect"])])()
        tree = LocalTree(root, limits=limits)
        check = _prepared_listing(PinCheck, pin, reader)
        candidates = list(reader.iter_artefacts(_listed(list(tree.walk())), profile))
        PinCheck.prepare(check, tree, candidates)  # the J.1.4 listing over every candidate, before any filter
        built.tree, built.pin_check = tree, check
        built.recipe = {"kind": kind, "tree": "LocalTree+PinCheck(listing, prepared over all candidates)",
                        "input": tilde(root), "listing_candidates": len(candidates), "listing_ok": check.listing_ok}
        if not check.listing_ok:
            notes.append("the J.1.4 listing digest over the full candidate set does NOT equal the pin: origins stay local")
    elif kind == "archive":
        assert pin is not None
        p10p = load_tool("inspect/phase10p_trial.py")
        root = input_path or (home / ARCHIVE[(source, part)])
        built.tree = p10p._tree(pin, root, limits)
        built.recipe = {"kind": kind, "tree": "ArchiveTree" + (".split" if built.tree.archive_parts else ""),
                        "input": tilde(root), "file": pin.get("file") or pin.get("path"), "sha256": built.tree.sha256}
    elif kind == "phase10j":
        trial = load_tool("agentdojo/phase10j_trial.py")
        part_pins = dict(trial._pins(profile))
        if served_part not in part_pins:
            raise SystemExit(f"{source} · {part}: not a part of profile {profile.id}")
        pin = _thaw(part_pins[served_part])
        built.pin = pin
        if pin["kind"] == "git":
            scratch_cache = cache or ((scratch or precheck_root() / corpus_id) / "cache")
            repo = profile.data["source"].get("canonical_repo")
            git_pins = [_thaw(p) for _part, p in trial._pins(profile) if p["kind"] == "git"]
            if not all(Fetcher(scratch_cache).plan(Recipe.from_pin(p, canonical_repo=repo)).cached for p in git_pins):
                if not seed_cache:
                    raise SystemExit(f"{source} · {part}: scratch cache {tilde(scratch_cache)} not seeded (drop --no-seed)")
                scratch_cache.mkdir(parents=True, exist_ok=True)
                seeded = trial.seed(profile.id, scratch_cache)  # every git pin of the profile, in part order (the trial's)
                notes.append(f"seeded {tilde(scratch_cache)} from the phase-10c bare clone: "
                             + ", ".join(f"{r['part']} {r['objects']} objects, {r['absent_blobs']} absent blobs" for r in seeded))
            built.tree, info = trial._tree(profile, served_part, pin, scratch_cache)
            built.recipe = {"kind": kind, "tree": "GitPinTree (phase10j_trial._tree)", "cache": tilde(scratch_cache),
                            "seed_from": tilde(trial.STAGING / trial.BARES[str(repo)]), "commit": info["commit"],
                            "covering_paths": len(built.tree.recipe.paths), "absent_blobs": info["absent_blobs"],
                            "history_index": built.tree.history is not None}
        else:
            if input_path is not None:
                raise SystemExit("--input is not used for a phase-10j archive part (the staged deposit is the trial's)")
            built.tree, info = trial._tree(profile, served_part, pin, cache or Path("."))
            built.recipe = {"kind": kind, "tree": "ArchiveTree (phase10j_trial._tree)",
                            "input": tilde(trial.STAGING / trial.ARCHIVES[pin["sha256"]]), "file": info["file"],
                            "sha256": info["sha256"], "nested": len(profile.data["import"].get("nested", ()))}
    elif kind == "dtap":
        pins = [_thaw(p) for p in profile.data["source"]["pins"]]
        runs_pin = next(p for p in pins if p["role"] == "runs")
        tasks_pin = next(p for p in pins if p["role"] == "tasks")
        dtap = home / STAGING / "dtap"
        runs_root = input_path or dtap / f"DTap-Bench-Agent-Trajectories-{DTAP_RUNS_COMMIT}"
        tasks_root = dtap / f"DecodingTrust-Agent-Platform-{DTAP_TASKS_COMMIT}"
        runs_check = PinCheck("blob", runs_pin, listing=_git_env_listing(dtap / "DTap-Bench-Agent-Trajectories.git",
                                                                          DTAP_RUNS_COMMIT), repo=runs_pin["repo"])
        tasks_check = PinCheck("blob", tasks_pin, listing=_git_env_listing(dtap / "DecodingTrust-Agent-Platform.git",
                                                                            DTAP_TASKS_COMMIT), repo=tasks_pin["repo"])
        lfs_cache = cache or ((scratch or precheck_root() / corpus_id) / "cache")
        objects = []
        for lfs in (p for p in pins if p["role"] == "lfs_object"):
            recipe = Recipe.from_pin(lfs)
            target = recipe.cache_path(lfs_cache)
            if not target.is_file():  # seeded with the object verified in phase 10b step 3 (named by its sha256)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dtap / "lfs-objects" / lfs["sha256"], target)
            result = Fetcher(lfs_cache, allow_network=False).fetch(recipe)  # size and sha256 against the pin
            objects.append(PinnedObject(lfs["file"], Origin.hf(recipe.repo or "", recipe.revision or "", recipe.file or ""),
                                        str(result.path), result.sha256 or "", result.bytes or 0))
        built.pin, built.tree, built.pin_check = runs_pin, LocalTree(runs_root, limits=limits), runs_check
        built.context_trees = [ContextTree("tasks", LocalTree(tasks_root, limits=limits), tasks_check,
                                           pin=dict(tasks_pin))]  # D-530: recorded for re-maps (as tools/dtap/import_dtap.py)
        built.pinned_objects = objects
        built.recipe = {"kind": kind, "tree": "LocalTree+PinCheck(blob from staged bare clone ls-tree)",
                        "input": tilde(runs_root), "context": {"tasks": tilde(tasks_root)}, "pinned_objects": len(objects),
                        "lfs_cache": tilde(lfs_cache)}
    return built


def _capability_list(source: str) -> list[Any]:
    from agentprov.adapters.registry import get_source

    return list(get_source(source).capabilities)


def _listed(items: Sequence[Any]) -> Any:
    from agentprov.adapters.runner.importer import _Listed

    return _Listed(items)


def _prepared_listing(pin_check_cls: Any, pin: Mapping[str, Any], reader: Any) -> Any:
    """A listing ``PinCheck`` whose ``prepare`` is a no-op once it was prepared over the full candidate list: the
    importer prepares it over the filtered candidates (``importer.py`` ``run``), which never match the pinned digest."""

    class PreparedListing(pin_check_cls):
        def prepare(self, tree: Any, candidates: Sequence[Any]) -> None:
            return None

    hook = getattr(reader, "listing_origin", None)
    if hook is None:
        raise SystemExit("the family records no origin for a listing-verified file")
    return PreparedListing("listing", pin, listing_origin=hook)


def _reader(built: Built) -> Any:
    from agentprov.adapters.registry import READERS
    from agentprov.adapters.runner import resolve_factory

    return resolve_factory(READERS[str(built.profile.data["import"]["dialect"])])()


def candidate_labels(built: Built) -> list[str]:
    """The reader's candidate labels of a git or local tree (what the importer selects before any filter)."""
    return [c.label for c in _reader(built).iter_artefacts(_listed(list(built.tree.walk())), built.profile)]


def auxiliary_plans(built: Built, labels: Iterable[str]) -> dict[str, dict[str, str]]:
    """Per label, the reader's ``auxiliary_for`` plan over the tree's current listing (the importer's ``_AuxListing``;
    context-tree refs are left out, so only primary-tree inputs are compared). Empty for a reader without one."""
    reader = _reader(built)
    if not callable(getattr(reader, "auxiliary_for", None)):
        return {}
    from agentprov.adapters.runner.importer import _AuxListing

    listing = _AuxListing([c.label for c in built.tree.walk()], {})
    return {label: dict(reader.auxiliary_for(label, listing)) for label in labels}


# ================================================================================================ selection
class AnyOf(str):
    """One ``include_paths`` entry that stands for the OR of the escaped globs it holds (see the module docstring)."""

    globs: tuple[str, ...]
    labels: frozenset[str]

    def __new__(cls, labels: Sequence[str]) -> AnyOf:
        globs = tuple(escape_label(label) for label in sorted(labels))
        obj = super().__new__(cls, f"precheck:any-of:{len(globs)}:sha256:{sha256_text(globs)}")
        obj.globs = globs
        obj.labels = frozenset(labels)
        return obj


class SampleMismatchError(Exception):
    """The kept candidates are not exactly the sampled labels (raised before any unit is mapped)."""


@contextlib.contextmanager
def any_of_matcher(any_of: AnyOf, seen: dict[str, Any], *, strict: bool = True) -> Iterator[None]:
    """Shim the importer's glob matcher for ``any_of`` and check discovery's kept candidates.

    The entry is recognised as the :class:`AnyOf` object (an import) or by its recorded string (a ``recompute`` or
    ``verify --level rederive`` replays ``corpus.json``'s selection as plain strings). With ``strict`` a discovery that
    keeps anything other than exactly the sampled labels raises :class:`SampleMismatchError` before any unit is mapped;
    otherwise the difference is only recorded in ``seen``."""
    import fnmatch

    from agentprov.adapters.runner import importer

    original_match = importer._match
    original_discover = importer._Pipeline.discover
    marker = str(any_of)

    def match(label: str, glob: str) -> bool:
        if isinstance(glob, AnyOf) or glob == marker:
            return label in any_of.labels and any(fnmatch.fnmatchcase(label, g) for g in any_of.globs)
        return bool(original_match(label, glob))

    def discover(self: Any) -> Any:
        candidates = original_discover(self)
        kept = {c.label for c in candidates}
        missing, extra = sorted(any_of.labels - kept), sorted(kept - any_of.labels)
        seen.setdefault("discoveries", []).append({"kept": len(kept), "missing": len(missing), "extra": len(extra)})
        seen["kept"] = sorted(kept)
        seen["n_candidates"] = len(candidates)
        if missing or extra:
            seen["missing"], seen["extra"] = missing, extra
            if strict:
                raise SampleMismatchError(f"{len(missing)} sampled label(s) not selected, {len(extra)} extra")
        return candidates

    importer._match = match
    importer._Pipeline.discover = discover  # type: ignore[method-assign]
    try:
        yield
    finally:
        importer._match = original_match
        importer._Pipeline.discover = original_discover  # type: ignore[method-assign]


def prune_tree(built: Built, sample: Sequence[str]) -> dict[str, int]:
    """Drop every reader candidate that is not sampled from a git or local tree (``phase10d_trial._sample``), again after
    each round until the reader's candidates are exactly the sample. :class:`SampleMismatchError` (before anything is
    mapped) when a sampled label is no candidate, when the candidates never become the sample, or when the pruned
    listing changes a sampled unit's own inputs (``auxiliary_for``: a dropped attempt sibling). R3 pinned objects (DTap's
    LFS objects) are kept only for a sampled label, so the manifest records no object the corpus does not hold."""
    from agentprov.adapters.runner.importer import GitPinTree, LocalTree

    tree = built.tree
    if not isinstance(tree, (GitPinTree, LocalTree)):
        raise SystemExit("--strategy prune works on git and local trees only (an archive lists members after expand)")
    wanted = set(sample)
    units = set(candidate_labels(built))
    missing = sorted(wanted - units)
    if missing:
        raise SampleMismatchError(f"{len(missing)} sampled label(s) are not candidates of the tree")
    before = auxiliary_plans(built, sorted(wanted))
    hidden: set[str] = set()
    if isinstance(tree, GitPinTree):
        entries = dict(tree.entries)

        def hide(labels: set[str]) -> None:
            hidden.update(labels)
            tree.entries = {p: e for p, e in entries.items() if p not in hidden}
    else:
        listed = list(tree.walk())  # walked once; every round filters the same listing

        def walk() -> Iterator[Any]:
            return (c for c in listed if c.label not in hidden)

        tree.walk = walk  # type: ignore[method-assign]

        def hide(labels: set[str]) -> None:
            hidden.update(labels)

    drop, rounds = units - wanted, 0
    while drop:
        rounds += 1
        hide(drop)
        drop = set(candidate_labels(built)) - wanted
    kept = set(candidate_labels(built))
    if kept != wanted:
        raise SampleMismatchError(f"after pruning, {len(wanted - kept)} sampled label(s) are no candidate")
    changed = sum(1 for label, plan in auxiliary_plans(built, sorted(wanted)).items() if plan != before.get(label))
    if changed:
        raise SampleMismatchError(f"pruning changes the inputs of {changed} sampled unit(s) (a dropped sibling the reader "
                                  "reads); use --strategy any-glob")
    pinned = list(getattr(built, "pinned_objects", None) or ())
    built.pinned_objects = [o for o in pinned if o.label in wanted]  # an R3 object stands for its pointer's label
    return {"candidates": len(units), "dropped": len(hidden), "kept": len(kept), "rounds": rounds,
            "pinned_objects_kept": len(built.pinned_objects), "pinned_objects_dropped": len(pinned) - len(built.pinned_objects)}


# ================================================================================================ guards
def model_id_redactions(profile: Any) -> list[str]:
    """Ids of the profile's ``[[family.inspect.redact]]`` rules with ``scope = "model_id"`` (D-182, regeneration-batch
    item 107: kexin profile v2 redacts the local-checkpoint model ids in the AER)."""
    rules = ((profile.data.get("family") or {}).get("inspect") or {}).get("redact") or ()
    return sorted(str(r.get("id")) for r in rules if isinstance(r, Mapping) and r.get("scope") == "model_id")


def kexin_local_path_guard(built: Built, sample: Sequence[str]) -> int | None:
    """Refuse a sample holding an AgentHarm local-path-model log while the resolved profile carries no ``model_id``
    redaction (profile v1: D-182 not applied, R-H1). ``None`` (not checked) when it does: the redaction (item 107) and the
    object withholding (D-604) then cover these logs. Returns the number checked; never prints a model id."""
    if model_id_redactions(built.profile):
        return None
    p10h = load_tool("inspect/phase10h_trial.py")
    tree = built.tree
    flagged = 0
    if hasattr(tree, "entries") and hasattr(tree, "fetcher"):  # GitPinTree: one batch from the fetch cache
        blobs = (b.data for b in tree.fetcher.iter_git_blobs(tree.recipe, [tree.entries[p] for p in sample]))
    else:  # LocalTree (--input CLONE)
        blobs = (tree.open(p) for p in sample)
    for data in blobs:
        if p10h._local_path_model(data):
            flagged += 1
    if flagged:
        raise SystemExit(f"{flagged} sampled log(s) name a local-path model (account path) and profile "
                         f"{built.profile.id}@{built.profile.version} redacts no model id; re-draw the sample with "
                         "l2_sample.py --exclude-facet 'model=<local-path-model>' (D-182, R-H1)")
    return len(sample)


def redaction_pending_guard(built: Built, sample: Sequence[str]) -> int:
    """Refuse a sample holding a label the profile excludes as ``select.redaction_pending`` (EnvironmentOptim's local-Qwen
    logs, D-255; controlarena's D-345 logs): such a unit may not reach a scratch import before its redaction exists. The
    match is the importer's (``_match`` on the member's own label). Returns the number of globs checked."""
    from agentprov.adapters.runner.importer import _match

    globs = [str(e["glob"]) for e in built.profile.data.get("import", {}).get("exclude", ())
             if isinstance(e, Mapping) and "glob" in e and e.get("code") == "select.redaction_pending"]
    hits = [label for label in sample if any(_match(label.rsplit("!/", 1)[-1], g) for g in globs)]
    if hits:
        raise SystemExit(f"{len(hits)} sampled label(s) are select.redaction_pending in the profile; re-draw the sample "
                         "with l2_sample.py --exclude-profile-code select.redaction_pending")
    return len(globs)


# ================================================================================================ import
def _report_json(report: Any) -> dict[str, Any]:
    failures = [{"stage": f.get("stage"), "code": f.get("code"), "path": scrub(str((f.get("subject") or {}).get("path", "")))}
                for f in report.failures]
    register = report.register
    return {
        "exit_code": report.exit_code, "counters": dict(report.counters),
        "issues_by_code": dict(sorted(report.issues_by_code.items())),
        "n_failures": len(failures), "failures": failures[:200],
        "register_codes": dict(sorted(Counter(str(r.get("code")) for r in register).items())),
        "n_register": len(register),
        "register": [{"code": r.get("code"), "severity": r.get("severity"), "stage": r.get("stage"),
                      "disposition": r.get("disposition"), "subject": {k: scrub(str(v), 400) for k, v in
                                                                         (r.get("subject") or {}).items()},
                      "detail": scrub(str(r.get("detail") or ""), 200)} for r in register[:500]],
        "notices": [scrub(n, 400) for n in report.notices[:40]], "partial": report.partial,
        "profile": {"id": report.profile, "version": report.profile_version, "sha256": report.profile_sha256},
        "adapter": f"{report.adapter}@{report.adapter_version}", "rules": dict(report.rules),
    }


def run(built: Built, sample: Sequence[str], corpus: Path, *, jobs: int, mode: str, until: str, strategy: str,
        limit: int | None) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ImportFilters, import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    guard_scratch(corpus)
    limits = IngestLimits()
    common: dict[str, Any] = dict(
        corpus_id=built.corpus_id, profile_id=built.profile.id, mode=mode, part=built.part, snapshot_id=built.part,
        until=until, workers=jobs, limits=limits, pin_check=built.pin_check, pin=built.pin,
        context_trees=built.context_trees, pinned_objects=built.pinned_objects, limit=limit,
    )
    selection: dict[str, Any] = {"strategy": strategy, "n_sample": len(sample)}
    reports: list[Any] = []
    started = time.perf_counter()
    if strategy == "any-glob":
        seen: dict[str, Any] = {}
        any_of = AnyOf(sample)
        filters = ImportFilters(include_paths=(any_of,), select=built.select)
        selection["include_paths"] = [str(any_of)]
        try:
            with any_of_matcher(any_of, seen), CorpusWriter(corpus, limits=limits, release=mode == "release",
                                                           command="import") as writer:
                reports.append(import_source(built.source, built.tree, corpus=writer, filters=filters, **common))
        except SampleMismatchError as exc:
            selection.update(error=str(exc), missing=[scrub(m) for m in seen.get("missing", [])][:50],
                             n_missing=len(seen.get("missing", [])), n_extra=len(seen.get("extra", [])))
            return {"selection": selection, "ok": False, "elapsed_s": round(time.perf_counter() - started, 1)}
        selection.update(n_selected=len(seen.get("kept", [])), n_candidates=seen.get("n_candidates"))
    elif strategy == "per-label":
        empty: list[str] = []
        for label in sample:
            filters = ImportFilters(include_paths=(escape_label(label),), select=built.select)
            with CorpusWriter(corpus, limits=limits, release=mode == "release", command="import") as writer:
                report = import_source(built.source, built.tree, corpus=writer, filters=filters, **common)
            reports.append(report)
            if report.counters.get("seen", 0) < 1:
                empty.append(label)
        selection.update(n_selected=len(sample) - len(empty), n_missing=len(empty), missing=[scrub(m) for m in empty][:50])
        if empty:
            selection["error"] = f"{len(empty)} sampled label(s) selected nothing"
    elif strategy == "prune":
        selection["prune"] = prune_tree(built, sample)
        common["pinned_objects"] = built.pinned_objects  # only the sampled labels' R3 objects (prune_tree)
        filters = ImportFilters(select=built.select)
        with CorpusWriter(corpus, limits=limits, release=mode == "release", command="import") as writer:
            reports.append(import_source(built.source, built.tree, corpus=writer, filters=filters, **common))
        selection["n_selected"] = selection["prune"]["kept"]
    else:
        raise SystemExit(f"unknown strategy {strategy!r}")
    merged = _merge_reports(reports)
    ok = "error" not in selection
    return {"selection": selection, "ok": ok, "report": merged, "elapsed_s": round(time.perf_counter() - started, 1)}


def _merge_reports(reports: Sequence[Any]) -> dict[str, Any]:
    """One report (``any-glob``, ``prune``) as is; ``per-label`` reports summed (counters, issues, failures, register)."""
    if len(reports) == 1:
        return _report_json(reports[0])
    parts = [_report_json(r) for r in reports]
    out = dict(parts[-1])
    for key in ("counters", "issues_by_code", "register_codes"):
        total: Counter[str] = Counter()
        for p in parts:
            total.update(p[key])
        out[key] = dict(sorted(total.items()))
    out["failures"] = [f for p in parts for f in p["failures"]][:200]
    out["n_failures"] = sum(p["n_failures"] for p in parts)
    out["register"] = [r for p in parts for r in p["register"]][:500]
    out["n_register"] = sum(p["n_register"] for p in parts)
    out["exit_code"] = max(p["exit_code"] for p in parts)
    out["imports"] = len(parts)
    return out


def _pin_verification(built: Built) -> dict[str, Any] | None:
    check = built.pin_check
    if check is None:
        return None
    return {"kind": check.kind, "verified": check.verified, "unverified": check.unverified,
            "listing_ok": getattr(check, "listing_ok", None)}


# ================================================================================================ CLI
def _print_recipes() -> None:
    from agentprov.adapters.registry import REGISTRY

    for registration in REGISTRY:
        for cap in registration.capabilities:
            kind = recipe_kind(registration.source_id, cap.part)
            why = BLOCKED.get((registration.source_id, cap.part), "")
            print(f"{registration.source_id} · {cap.part}: {kind}" + (f" ({why})" if why else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--recipes", action="store_true", help="print every part's recipe and exit")
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--source")
    parser.add_argument("--part")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--mode", choices=("dev", "release"), default="dev")
    parser.add_argument("--until", default="validation")
    parser.add_argument("--strategy", choices=("any-glob", "per-label", "prune"), default="any-glob")
    parser.add_argument("--limit", type=int, default=None, help="the product's per-unit limit (multi-execution parts)")
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--cache", type=Path, help="fetch cache (git-cache: default the shared one; seeded: scratch)")
    parser.add_argument("--input", type=Path, help="git-cache: a clone at the pin (CLI --input --verify-against-pin); "
                                                   "listing/archive/dtap: the staged root")
    parser.add_argument("--no-seed", action="store_true", help="never seed a scratch cache")
    parser.add_argument("--allow-first-mapping", action="store_true", help="agentdyn b: the owner decided a first mapping")
    args = parser.parse_args(argv)
    if args.recipes:
        _print_recipes()
        return 0
    for name in ("sample", "corpus", "source", "part"):
        if getattr(args, name) is None:
            parser.error(f"--{name} is required")
    guard_scratch(args.corpus)
    sample_doc = json.loads(args.sample.read_text(encoding="utf-8"))
    if (sample_doc.get("source"), sample_doc.get("part")) != (args.source, args.part):
        raise SystemExit("the sample file names another source or part")
    sample = [str(label) for label in sample_doc["labels"]]
    if len(set(sample)) != len(sample) or not sample:
        raise SystemExit("the sample lists no label, or a label twice")
    built = build(args.source, args.part, cache=args.cache, input_path=args.input,
                  scratch=args.corpus.parent, seed_cache=not args.no_seed, allow_first_mapping=args.allow_first_mapping)
    checked, redacted = None, None
    if args.source == "kexin-xu-01-agentharm":
        checked = kexin_local_path_guard(built, sample)
        redacted = model_id_redactions(built.profile) or None
    pending_globs = redaction_pending_guard(built, sample)
    result = run(built, sample, args.corpus, jobs=args.jobs, mode=args.mode, until=args.until, strategy=args.strategy,
                 limit=args.limit)
    summary = {
        "format": IMPORT_FORMAT, "source": args.source, "part": args.part, "imported_as": f"{built.source} · {built.part}",
        "corpus_id": built.corpus_id, "corpus": tilde(str(args.corpus) + ".partial"),
        "profile": {"id": built.profile.id, "version": built.profile.version, "sha256": built.profile.sha256},
        "recipe": built.recipe, "notes": built.notes, "select": {k: sorted(v) for k, v in built.select.items()},
        "mode": args.mode, "until": args.until, "jobs": args.jobs, "limit": args.limit,
        "sample": {"file": tilde(args.sample), "sha256": sha256_file(args.sample), "n": len(sample)},
        "local_path_model_guard": checked, **({"model_id_redactions": redacted} if redacted else {}),
        "pin_verification": _pin_verification(built), **result,
        **({"redaction_pending_guard": {"globs": pending_globs, "refused": 0}} if pending_globs else {}),
    }
    out = args.summary_json or args.corpus.with_name(args.corpus.name + ".l2-import.json")
    write_json(out, summary)
    sel = result["selection"]
    print(json.dumps({"ok": result["ok"], "selected": sel.get("n_selected"), "sample": len(sample),
                      "counters": (result.get("report") or {}).get("counters"), "summary": tilde(out)}, sort_keys=True))
    if not result["ok"]:
        return 3
    return int((result.get("report") or {}).get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
