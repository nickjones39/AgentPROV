"""``agentprov fetch``: populate the verified, extraction-free fetch cache (MN N.2.2, N.1.11; G.7.5; HL H.4.3).

Two modes, one command:

``agentprov fetch --corpus DIR [--only sha256:HEX ...]``
    The referenced-raw mode of N.2.2. It reads ``DIR/raw/REFERENCES.json`` (untrusted, parsed strictly), resolves each
    object against the in-package profile pins and fetches and verifies it into the cache. It never writes into the corpus,
    never accepts a gate or licence, and reports an object it cannot or may not fetch as ``unverified``.

``agentprov fetch --profile ID [--pin ROLE ...] [--path PREFIX ...]``
    The acquisition mode (this build's resolution of "pinned-fetch recipes"): fetch the pins of a shipped source profile.
    Without ``--pin`` the profile's primary pins are fetched. For a git pin the commit is brought into a bare repository
    (no checkout) and every blob under the pin's tree is read back with its SHA-1 recomputed; for a download pin the file is
    verified against the pinned size, MD5 and SHA-256 before it is published.

``agentprov fetch --profile ID --history [--pin ROLE ...]``
    The history mode (D.6.16): instead of the pinned tree, bring the **full history without blobs** of each git pin's commit
    into a separate store (``<cache>/git-history``) and compute the introducing-commit index of the pinned tree from it. A later
    ``import`` that finds the index records ``introduced_in_commit`` on each file's git origin (rules
    ``agentdojo.committed_no_later_than@1`` and ``agentdojo.benchmark_era_from_commit@1`` read it); without it the origins are
    unchanged. The index is derived and keyed by the pinned commit; an existing one is reused (no network).

Network use needs ``--allow-network`` (exit 4 without it, N.1.11(1)); ``--dry-run`` prints the plan and never needs it. A
download of 100 MiB or more also needs ``--i-consent-to-large-download`` (the consent of U-07). Exit codes: 0 everything
present and verified; 1 a failure or a mismatch; 2 usage; 3 environment (no ``git``, a cache inside a repository); 4 refusal.
The cache is ``--cache-dir``, else ``$AGENTPROV_UPSTREAM_CACHE``, else ``$AGENTPROV_HOME/cache``; each real retrieval is
appended to ``acquisitions.jsonl`` there.
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import replace
from importlib import resources
from pathlib import Path
from typing import Any

from agentprov.adapters.profiles import profile_families
from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.paths import open_evidence
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent
from agentprov.raw.fetch import (
    LARGE_DOWNLOAD_BYTES,
    FetchError,
    FetchResult,
    Fetcher,
    NetworkRefusedError,
    Recipe,
    recipes_from_source,
    resolve_cache_dir,
)
from agentprov.raw.references import (
    ReferencesError,
    fetch_command_hint,
    parse_references,
    resolve_reference,
    select,
    verify_reference,
)

_HEX64 = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "fetch",
        parents=[shared],
        help="fetch pinned upstream bytes into the verified cache (needs --allow-network)",
        description="Populate the verified, extraction-free fetch cache from in-package pins (N.2.2; G.7.5).",
        allow_abbrev=False,
    )
    p.set_defaults(command="fetch", handler=run_fetch, feedback=True)
    src = p.add_argument_group("what to fetch (exactly one)")
    src.add_argument("--corpus", metavar="DIR", help="fetch the objects of DIR/raw/REFERENCES.json (the corpus is never written)")
    src.add_argument("--profile", metavar="ID", help="fetch the pins of a shipped source profile")
    sel = p.add_argument_group("selection")
    sel.add_argument("--only", action="append", default=[], metavar="sha256:HEX", help="with --corpus: only this object (repeatable)")
    sel.add_argument("--pin", action="append", default=[], metavar="ROLE", help="with --profile: a pin role (repeatable; default: the primary pins)")
    sel.add_argument("--history", action="store_true", help="with --profile: fetch the blobless full history of the git pins and compute the introducing-commit index (D.6.16)")
    sel.add_argument("--path", action="append", default=[], metavar="PREFIX", help="with --profile: a path prefix inside a git pin (repeatable)")
    net = p.add_argument_group("network and cache")
    net.add_argument("--cache-dir", metavar="DIR", help="cache directory (default $AGENTPROV_UPSTREAM_CACHE, else $AGENTPROV_HOME/cache)")
    net.add_argument("--allow-network", action="store_true", help="permit the network access fetching needs (required unless --dry-run)")
    net.add_argument(
        "--i-consent-to-large-download",
        action="store_true",
        help=f"consent to a download of {LARGE_DOWNLOAD_BYTES // (1024 * 1024)} MiB or more (U-07)",
    )
    net.add_argument("--dry-run", action="store_true", help="print the plan; no network and no writes")


def _check_options(args: argparse.Namespace) -> None:
    if (args.corpus is None) == (args.profile is None):
        raise CliUsageError("agentprov fetch: exactly one of --corpus DIR or --profile ID is required")
    if args.corpus is not None and (args.pin or args.path):
        raise CliUsageError("agentprov fetch: --pin and --path go with --profile, not --corpus")
    if args.history and args.profile is None:
        raise CliUsageError("agentprov fetch: --history goes with --profile")
    if args.history and args.path:
        raise CliUsageError("agentprov fetch: --history indexes the whole pinned tree; --path does not apply")
    if args.profile is not None and args.only:
        raise CliUsageError("agentprov fetch: --only goes with --corpus, not --profile")
    for value in args.only:
        if not _HEX64.fullmatch(value):
            raise CliUsageError(f"agentprov fetch: --only expects sha256:<64 hex>, got {safe_text(value, 80)!r}")
    if args.profile is not None and not _PROFILE_ID.fullmatch(args.profile):
        raise CliUsageError("agentprov fetch: --profile is a bare profile id")
    if args.corpus is not None and not Path(args.corpus).is_dir():
        raise CliUsageError("agentprov fetch: --corpus is not a directory")
    if not args.dry_run and not args.allow_network:
        raise NetworkRefusedError("fetch needs --allow-network: the network is never used implicitly (N.1.11)")


def _source_table(profile_id: str) -> Any:
    from agentprov.adapters.profiles import load_profile
    from agentprov.errors import ProfileError

    try:
        return load_profile(profile_id).data.get("source", {})
    except ProfileError as exc:
        if str(exc).startswith("no profile"):  # an unknown id is a usage error; a malformed shipped profile stays exit 70
            raise CliUsageError(f"agentprov fetch: no profile {safe_text(profile_id, 60)!r} is shipped in the package") from None
        raise


def _profile_recipes(profile_id: str, roles: list[str], paths: list[str], result: CommandResult) -> list[Recipe]:
    recipes, skipped = recipes_from_source(_source_table(profile_id))
    for role, reason in skipped:
        result.notices.append(f"pin {safe_text(role, 60)} is not fetchable yet: {safe_text(reason, 160)}")
    if roles:
        known = {r.role for r in recipes}
        missing = [r for r in roles if r not in known]
        if missing:
            raise CliUsageError(f"agentprov fetch: no fetchable pin with role {safe_text(missing[0], 60)!r} in profile {safe_text(profile_id, 60)!r}")
        chosen = [r for r in recipes if r.role in roles]
    else:
        chosen = [r for r in recipes if r.primary]
    if not chosen:
        raise CliUsageError(f"agentprov fetch: profile {safe_text(profile_id, 60)!r} has no fetchable primary pin; name one with --pin")
    if paths:
        chosen = [replace(r, paths=tuple(paths)) if r.kind == "git" else r for r in chosen]
    return chosen


def _shipped_profile_ids() -> list[str]:
    """The ids of the source profiles shipped in the package (package data only; no adapter module is imported)."""
    found: dict[str, None] = {}
    for family in profile_families():
        folder = resources.files("agentprov") / "adapters" / family / "profiles"
        try:
            names = sorted(n.name for n in folder.iterdir() if n.name.endswith(".profile.toml"))
        except (FileNotFoundError, NotADirectoryError):
            names = []
        for name in names:
            found[name.removesuffix(".profile.toml")] = None
    return list(found)


def _all_recipes() -> list[Recipe]:
    """Every fetchable pin of every shipped profile: the in-package origins a reference may resolve against."""
    out: list[Recipe] = []
    for profile_id in _shipped_profile_ids():
        recipes, _ = recipes_from_source(_source_table(profile_id))
        out.extend(recipes)
    return out


def _describe(recipe: Recipe) -> str:
    return safe_text(recipe.origin_label(), 200)


def guard_cache(cache: Path, corpus: str | None = None) -> None:
    """Refuse a fetch cache inside a sealed corpus (G1) or overlapping the corpus a command reads (G2): every fetch writes
    the cache, and N.2.2 says the corpus is never written. Read-only, so a dry run applies it too (N.1.6(5))."""
    from agentprov.corpus.derive import is_inside
    from agentprov.corpus.layout import assert_writable

    assert_writable(cache)
    if corpus is not None and (is_inside(cache, Path(corpus)) or is_inside(Path(corpus), cache)):
        raise AgentProvError("the fetch cache overlaps the corpus (G2); give --cache-dir outside it",
                             code="raw.fetch.cache_in_corpus", exit_code=4)


def run_fetch(ctx: Context) -> CommandResult:
    args = ctx.args
    _check_options(args)
    result = CommandResult(dry_run=bool(args.dry_run))
    cache = resolve_cache_dir(args.cache_dir, ctx.env)
    guard_cache(cache, args.corpus)
    consent = "--allow-network" + (" --i-consent-to-large-download" if args.i_consent_to_large_download else "")
    fetcher = Fetcher(
        cache,
        allow_network=bool(args.allow_network),
        consent=consent,
        large_download_consent=bool(args.i_consent_to_large_download),
        env=ctx.env,
    )
    if args.profile is not None and args.history:
        return _fetch_history(args, fetcher, result, ctx.progress)
    if args.profile is not None:
        return _fetch_profile(args, fetcher, result, ctx.progress)
    return _fetch_references(args, fetcher, result)


def _unit(progress: Progress, label: str, status: str, started: float, codes: tuple[str, ...] = ()) -> None:
    """One recipe's ``unit_done`` (N.1.14): a fetch reports per recipe like any long-running command."""
    progress.emit(ProgressEvent("unit_done", unit=label, status=status, duration_s=time.monotonic() - started, codes=codes))


def _fail(result: CommandResult, subject: str, exc: AgentProvError, stage: str) -> int:
    code = exc.code if "." in exc.code else "raw.fetch.error"
    result.failures.append({"subject": {"path": safe_text(subject, 300)}, "stage": stage, "code": code, "detail": safe_text(str(exc), 300)})
    result.issues_by_code[code] = result.issues_by_code.get(code, 0) + 1
    result.error(f"{safe_text(subject, 120)}: {code}: {safe_text(str(exc), 240)}")
    return exc.exit_code


def _finish(result: CommandResult, counters: dict[str, int], codes: list[int]) -> CommandResult:
    result.counters = counters
    if not codes:
        result.exit_code = 0
    elif len(set(codes)) == 1:
        result.exit_code = codes[0]
    else:
        result.exit_code = 1
    return result


def _fetch_profile(args: argparse.Namespace, fetcher: Fetcher, result: CommandResult,
                   progress: Progress = NULL_PROGRESS) -> CommandResult:
    recipes = _profile_recipes(args.profile, args.pin, args.path, result)
    counters = {"recipes": len(recipes), "fetched": 0, "cached": 0, "failed": 0, "files_verified": 0, "bytes_verified": 0}
    codes: list[int] = []
    progress.emit(ProgressEvent("start", total=len(recipes), fields={"command": "fetch", "plan": "profile pins",
                                                                     "source": safe_text(args.profile, 80)}))
    for recipe in recipes:
        label = _describe(recipe)
        started = time.monotonic()
        progress.emit(ProgressEvent("unit_start", unit=label))
        if args.dry_run:
            plan = fetcher.plan(recipe)
            state = "cached" if plan.cached else "would fetch"
            extra = f", {plan.expected_bytes} bytes" if plan.expected_bytes is not None else ""
            large = " (large: needs --i-consent-to-large-download)" if plan.large else ""
            result.output(f"{label}: {state} from {safe_text(plan.host, 80)}{extra}{large}")
            counters["cached" if plan.cached else "fetched"] += 1
            _unit(progress, label, "cached" if plan.cached else "would_fetch", started)
            continue
        try:
            outcome = fetcher.fetch(recipe)
            counters["fetched" if outcome.network_used else "cached"] += 1
            files, size = _verify(fetcher, recipe, outcome)
            counters["files_verified"] += files
            counters["bytes_verified"] += size
            for problem in outcome.problems:
                codes.append(1)
                result.failures.append({"subject": {"path": safe_text(recipe.origin_label(), 300)}, "stage": "fetch", "code": "raw.fetch.expectation", "detail": safe_text(problem, 300)})
                result.issues_by_code["raw.fetch.expectation"] = result.issues_by_code.get("raw.fetch.expectation", 0) + 1
                result.error(f"{label}: {safe_text(problem, 240)}")
            result.output(_line(label, outcome, files, size))
            _unit(progress, label, "fetched" if outcome.network_used else "cached", started,
                  ("raw.fetch.expectation",) if outcome.problems else ())
        except (FetchError, IngestError) as exc:
            counters["failed"] += 1
            codes.append(_fail(result, recipe.origin_label(), exc, "fetch"))
            _unit(progress, label, "failed", started, (exc.code,))
    if not args.dry_run:
        result.info(f"fetched {counters['fetched']}, cached {counters['cached']}, failed {counters['failed']} of {counters['recipes']} recipe(s)")
        result.info(f"cache: {safe_text(fetcher.cache_dir, 200)}")
    return _finish(result, counters, codes)


def _fetch_history(args: argparse.Namespace, fetcher: Fetcher, result: CommandResult,
                   progress: Progress = NULL_PROGRESS) -> CommandResult:
    recipes = [r for r in _profile_recipes(args.profile, args.pin, [], result) if r.kind == "git"]
    counters = {"recipes": len(recipes), "fetched": 0, "cached": 0, "failed": 0, "indexed_blobs": 0, "introducing_commits": 0}
    codes: list[int] = []
    progress.emit(ProgressEvent("start", total=len(recipes), fields={"command": "fetch", "plan": "history",
                                                                     "source": safe_text(args.profile, 80)}))
    for recipe in recipes:
        label = _describe(recipe)
        started = time.monotonic()
        progress.emit(ProgressEvent("unit_start", unit=label))
        if args.dry_run:
            plan = fetcher.plan_history(recipe)
            if plan.cached:
                state = "index cached"
            else:
                state = "would index from the cached history" if not plan.needs_network else "would fetch the blobless history"
            result.output(f"{label}: {state} ({safe_text(plan.host, 80)})")
            counters["cached" if plan.cached else "fetched"] += 1
            _unit(progress, label, "cached" if plan.cached else "would_fetch", started)
            continue
        try:
            outcome = fetcher.fetch_history(recipe)
        except AgentProvError as exc:
            counters["failed"] += 1
            codes.append(_fail(result, recipe.origin_label(), exc, "fetch"))
            _unit(progress, label, "failed", started, (exc.code,))
            continue
        _unit(progress, label, "fetched" if outcome.network_used else "cached", started)
        counters["fetched" if outcome.network_used else "cached"] += 1
        counters["indexed_blobs"] += len(outcome.index.rows)
        counters["introducing_commits"] += len(outcome.index.commits)
        if outcome.network_used:
            how = "fetched"
        else:
            how = "indexed from the cached history" if outcome.index_created else "index already cached"
        result.output(f"{label}: {how}; {len(outcome.index.rows)} blob(s), {len(outcome.index.commits)} introducing commit(s)")
    if not args.dry_run:
        result.info(f"history: fetched {counters['fetched']}, cached {counters['cached']}, failed {counters['failed']} of {counters['recipes']} recipe(s)")
        result.info(f"cache: {safe_text(fetcher.cache_dir, 200)}")
    return _finish(result, counters, codes)


def _verify(fetcher: Fetcher, recipe: Recipe, outcome: FetchResult) -> tuple[int, int]:
    """Read every blob under a git recipe with its SHA-1 recomputed; a download was verified while it was stored."""
    if recipe.kind != "git":
        return (1, outcome.bytes or 0)
    files = size = 0
    for blob in fetcher.iter_git_blobs(recipe):
        files += 1
        size += len(blob.data)
    return files, size


def _line(label: str, outcome: FetchResult, files: int, size: int) -> str:
    how = "fetched" if outcome.network_used else "already cached"
    if outcome.recipe.kind == "git":
        return f"{label}: {how}; {files} blob(s), {size} bytes verified by git blob id; {outcome.gitlinks} gitlink(s) not fetched"
    return f"{label}: {how}; {outcome.bytes} bytes verified ({outcome.verified})"


def _read_references(root: str) -> bytes:
    try:
        with open_evidence(root, "raw/REFERENCES.json") as stream:
            return stream.read()
    except FileNotFoundError:
        raise CliUsageError("agentprov fetch: the corpus has no raw/REFERENCES.json (nothing is referenced)") from None
    except IngestError as exc:
        raise CliUsageError(f"agentprov fetch: raw/REFERENCES.json cannot be read safely ({exc.code})") from None


def _fetch_references(args: argparse.Namespace, fetcher: Fetcher, result: CommandResult) -> CommandResult:
    try:
        references = parse_references(_read_references(args.corpus))
    except ReferencesError as exc:
        raise CliUsageError(f"agentprov fetch: {exc}") from None
    chosen = select(references, args.only)
    wanted = {o.removeprefix("sha256:") for o in args.only}
    for missing in sorted(wanted - {r.sha256 for r in references}):
        raise CliUsageError(f"agentprov fetch: sha256:{missing[:16]}... is not referenced by this corpus")
    recipes = _all_recipes()
    counters = {"references": len(chosen), "verified": 0, "unpinned": 0, "unverified": 0, "failed": 0}
    codes: list[int] = []
    for ref in chosen:
        subject = f"sha256:{ref.sha256}"
        resolution = resolve_reference(ref, recipes)
        if resolution.status == "unpinned":
            counters["unpinned"] += 1
            codes.append(1)
            result.failures.append({"subject": {"path": subject}, "stage": "resolve", "code": "raw.reference.unpinned_origin", "detail": "no in-package profile pin matches any origin; it is never contacted"})
            result.issues_by_code["raw.reference.unpinned_origin"] = result.issues_by_code.get("raw.reference.unpinned_origin", 0) + 1
            result.error(f"{subject[:23]}: raw.reference.unpinned_origin: not contacted")
            continue
        if resolution.status == "blocked":
            counters["unverified"] += 1
            codes.append(1)
            needs = ", ".join(sorted(set(ref.requires) & {"hf-gate-acceptance", "authors-permission"}))
            result.notices.append(f"unverified {subject[:23]}: needs {needs}, which this command never accepts for you")
            result.error(f"{subject[:23]}: unverified: needs {needs}")
            continue
        assert resolution.recipe is not None
        if args.dry_run:
            plan = fetcher.plan(resolution.recipe)
            result.output(f"{subject[:23]}: {'cached' if plan.cached else 'would fetch'} from {safe_text(plan.host, 80)}")
            counters["verified"] += 0
            continue
        try:
            verify_reference(fetcher, resolution)
            counters["verified"] += 1
            result.output(f"{subject[:23]}: verified")
        except (FetchError, IngestError) as exc:
            counters["failed"] += 1
            codes.append(_fail(result, subject, exc, "verify"))
    for ref in chosen:
        if any(f["subject"]["path"] == f"sha256:{ref.sha256}" for f in result.failures):
            result.info("  to retry: " + fetch_command_hint(safe_text(args.corpus, 200), ref.sha256))
    return _finish(result, counters, codes)
