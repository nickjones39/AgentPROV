"""``agentprov import`` (alias ``convert``): ingest released artefacts into a working corpus (MN N.2.2; D.2.9).

The command resolves the source (registry id or alias, N.3.1), applies the status gate (N.3: ``planned``,
``not_possible``, a part role without an import, or a source this build does not register exit 5; ``supported`` and
``partial`` proceed with their caveat; ``via`` redirects), resolves the profile pin, acquires the origin and hands the
tree to :func:`agentprov.adapters.runner.importer.import_source`, which stores, expands, maps, seals, derives and
validates into ``<DIR>.partial/`` (H.1.5).

Origins (``--input PATH`` or ``--fetch``):

* ``--input`` reads a directory or one file in place through ``agentprov.ingest.paths`` (G.3.6) and needs
  ``--verify-against-pin``: a git pin whose tree listing is in the fetch cache (a blob-id match records the pinned ``git``
  origin), or a pin that records a J.1.4 tree-listing digest (the AgentDojo-PROV trees; a digest match records the
  frozen-corpus origin). Without a cached listing the check needs ``--allow-network`` to fetch the pin (exit 4
  otherwise). A file the pin does not vouch for is registered ``raw.origin.blob_mismatch`` and not imported. An
  unverified ``local`` origin is refused (exit 4) because the AER writer seals every AER in release mode, where a local
  origin is an error (C.17 AER-V20); N.2.2's dev-only local import is therefore not available.
* **Archive inputs** (D-200): when the profile's pin is a download pin (a Zenodo, Hugging Face or URL file), ``--input FILE
  --verify-against-pin`` checks the file against the pin offline (name, size, MD5 when pinned, SHA-256;
  ``raw.fetch.verify_download``) and imports its members: the archive is stored with the pin's origin, expanded in
  place by the ``expand`` stage (never extracted) and every selected member is mapped as a whole file (origin
  ``member``). A ``.zip`` under a git pin is still refused (exit 5). A URL file (D-455) also needs its recorded retrieval
  time: the fetch cache's acquisition record (``--fetch``) or the pin's ``retrieved_at``; with neither it is refused
  (exit 3, ``raw.origin.unpinned``), never stamped with the time of the import.
* ``--fetch`` reads the blobs of the profile's git pin from the verified fetch cache (``raw.fetch``), or, for a download
  pin, the verified file in the cache (downloaded with ``--allow-network``; 100 MiB or more also needs
  ``--i-consent-to-large-download``), imported as an archive input. Without ``--allow-network`` the cache is the only
  source (D-220): a cached pin is imported offline and an uncached one is refused (``raw.fetch.not_cached``, exit 4);
  with it, the network is used only when the cache lacks the pin (N.1.11). ``--fetch --dry-run`` needs no network and
  maps only when the pin is cached.

Phase-6 deferrals, each refused with a message: ``--spec`` (corpus specs, H.1.6), ``--prov-spec adprov-v2.3-compat``
(the compat oracle runs through ``agentprov migrate gate B``), ``--pipeline`` (an index facet), an archive ``--input``
under a git pin, and ``--fetch`` of a URL pin. ``--until sem`` stops after the SEM stage (the registry part's semantics profiles; C.14).
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from agentprov.cli import gitinfo
from agentprov.cli.common import (
    CliUsageError,
    CommandResult,
    Context,
    Refusal,
    UnsupportedCapability,
    bounded_int,
    redact_personal,
    safe_text,
)
from agentprov.errors import AgentProvError

_UNTIL = ("raw", "aer", "sem", "prov", "validation")
_SELECT = re.compile(r"[A-Za-z][A-Za-z0-9_]*=[^=,][^=]*")
_CORPUS_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SPEC_ID: Final = "agentprov-prov/0.1"
COMPAT_SPEC: Final = "adprov-v2.3-compat"

#: N.3.1 CLI aliases: alias -> (source id, part or None).
ALIASES: Final[dict[str, tuple[str, str | None]]] = {
    "agentdojo-logs": ("agentdojo", None),
    "agentdojo-upstream": ("agentdojo", None),
    "agentdojo-prov-v1": ("adprov-v1", None),
    "multiturn-agent-attack": ("stac", None),
    "inspect": ("agent-security-tools-survey", "agentharm"),
}
#: The v0.1 source ids of D.3.3 / N.3.1. An id here that this build does not register is refused (exit 5); any other id
#: is a usage error (exit 2) with suggestions (N.1.3).
SPEC_SOURCE_IDS: Final = (
    "agentdojo", "adprov-v1", "rope", "autodojo", "agentdyn", "drift", "mandate-agentdojo-eval",
    "agent-security-tools-survey", "stac", "ciaware-bench", "agentdojo-inspect", "midojo", "adi",
)  # fmt: skip


class GuardRefusedError(AgentProvError):
    """An output-tree guard (N.1.9) refused: overlapping trees, or a local origin in release mode. Exit 4."""

    code = "cli.refused.guard"
    exit_code = 4


def _non_negative(text: str) -> int:
    value = bounded_int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _positive(text: str) -> int:
    value = _non_negative(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "import",
        aliases=["convert"],
        parents=[shared],
        help="ingest released artefacts into a working corpus (store, map, seal, derive, validate)",
        description="Ingest released artefacts into DIR.partial (N.2.2): raw store, AER, PROV and validation.",
        allow_abbrev=False,
    )
    p.set_defaults(command="import", handler=run_import, feedback=True)
    p.add_argument("source", nargs="?", metavar="SOURCE", help="registry source id or alias; optional with --spec")
    p.add_argument("--corpus", metavar="DIR", help="the working corpus directory (written as DIR.partial)")
    where = p.add_argument_group("origin")
    where.add_argument("--input", metavar="PATH", help="local origin: a directory or one file, read in place")
    where.add_argument("--fetch", action="store_true",
                       help="read the profile's pin from the verified fetch cache (offline unless --allow-network)")
    where.add_argument("--allow-network", action="store_true",
                       help="with --fetch: fetch the pin when the cache lacks it (otherwise refused: raw.fetch.not_cached)")
    where.add_argument("--cache-dir", metavar="DIR", help="fetch cache (default $AGENTPROV_UPSTREAM_CACHE, else $AGENTPROV_HOME/cache)")
    where.add_argument("--verify-against-pin", action="store_true", help="record the pinned origin for --input files the pin vouches for")
    where.add_argument("--i-consent-to-large-download", action="store_true",
                       help="with --fetch of a download pin: consent to a download of 100 MiB or more (U-07)")
    where.add_argument("--context", action="append", default=[], metavar="ROLE=PATH",
                       help="a local copy of a declared context pin (checked against the pin); default: the fetch cache")
    where.add_argument("--no-context", action="append", default=[], metavar="ROLE",
                       help="map without a declared context role (its per-unit artefacts are then absent; a notice, "
                            "and the role is recorded in the snapshot's context_skipped)")
    prof = p.add_argument_group("profile and snapshot")
    prof.add_argument("--profile", metavar="ID", help="import profile (default: the registry's profile for the part)")
    prof.add_argument("--pin", metavar="ROLE", help="profile pin role, e.g. 2024-06 or release")
    prof.add_argument("--snapshot", metavar="ID", help="snapshot id inside the corpus (default: the registry part)")
    prof.add_argument("--spec", metavar="SPEC.toml", help="committed corpus spec (deferred in this build)")
    prof.add_argument("--corpus-id", metavar="ID", help="corpus id (default: the registry's corpus id for the part)")
    filt = p.add_argument_group("selection")
    filt.add_argument("--suite", metavar="S")
    filt.add_argument("--attack", metavar="A")
    filt.add_argument("--pipeline", metavar="P")
    filt.add_argument("--variant", metavar="V")
    filt.add_argument("--select", action="append", default=[], metavar="KEY=VALUE[,VALUE...]", help="AER-header filter (repeatable)")
    filt.add_argument("--limit", type=_non_negative, metavar="N", help="map at most N new units (0 maps nothing)")
    filt.add_argument("--sample", type=_positive, metavar="N",
                      help="dev runs: a deterministic sample of N executions, chosen before mapping (D-529; partial corpus)")
    filt.add_argument("--sample-mode", choices=["first", "spread", "random"], default=None,
                      help="with --sample: first N by key (default), round-robin over the reader's arms, or seeded random")
    filt.add_argument("--seed", metavar="S", help="with --sample-mode random: the seed (recorded in the manifest)")
    stage = p.add_argument_group("stages")
    stage.add_argument("--until", choices=_UNTIL, help="stop after this stage (default: validation)")
    stage.add_argument("--prov-spec", action="append", default=[], metavar="SPEC", help=f"PROV spec (repeatable; default {SPEC_ID})")
    mode = p.add_argument_group("mode")
    mode.add_argument("--retry-failed", action="store_true", help="re-process units whose row has status failed")
    mode.add_argument("--release", action="store_true", help="release mode: strict checks, no filters, no --limit, no --in-process")
    mode.add_argument("--skip-prov-conformance", action="store_true",
                      help="dev mode only, not advisable: skip the W3C PROV conformance check (tier 4); the corpus is "
                           "marked unvalidated until a full recompute --out NEW, and cannot be sealed (G2c-5)")
    mode.add_argument("--jobs", type=_non_negative, default=0, metavar="N", help="worker processes (0 = host default; default 0)")
    mode.add_argument("--in-process", action="store_true", help="debugging only: run expand, map and prov in this process")
    mode.add_argument("--size-hints", metavar="DIR",
                      help="a previous version of this corpus (read-only): its stored PROV sizes set each prov job's "
                           "memory charge, so more jobs run at once (D-554; timing only, never outputs)")
    mode.add_argument("--allow-hardlinks", action="store_true", help="accept st_nlink > 1 files in an --input tree")
    mode.add_argument("--no-validation-cache", action="store_true",
                      help="do not store the tier-4 round trips in $AGENTPROV_HOME/cache/tier4 (D-550)")
    mode.add_argument("--dry-run", action="store_true", help="run every in-memory stage; write nothing")
    mode.add_argument("--artefacts", action="store_true",
                      help="with --dry-run: scan the mapped executions for source-data artefacts and print the per-class table (D.15.4)")  # fmt: skip
    lim = p.add_argument_group("tier-1 overrides")
    lim.add_argument("--max-file-bytes", type=_positive, metavar="N")
    lim.add_argument("--max-json-depth", type=_positive, metavar="N")


# ------------------------------------------------------------------------------------------------ pre-flight
def _check_options(args: argparse.Namespace) -> None:
    """Pre-flight option checks of N.2.2 and N.1.7: usage errors (2), then refusals (4)."""
    if not args.source and not args.spec:
        raise CliUsageError("agentprov import: SOURCE is required unless --spec is given")
    if args.corpus is None:
        raise CliUsageError("agentprov import: --corpus DIR is required")
    if args.input is not None and args.fetch:
        raise CliUsageError("agentprov import: --input and --fetch are mutually exclusive")
    if args.input is None and not args.fetch:
        raise CliUsageError("agentprov import: one of --input PATH or --fetch is required")
    if args.input is not None and not os.path.exists(args.input):
        raise CliUsageError("agentprov import: --input does not exist")
    if args.verify_against_pin and args.input is None:
        raise CliUsageError("agentprov import: --verify-against-pin goes with --input (--fetch reads the pin itself)")
    for expression in args.select:
        if not _SELECT.fullmatch(expression):
            raise CliUsageError(f"agentprov import: --select expects KEY=VALUE[,VALUE...], got {safe_text(expression, 80)!r}")
    if args.release:
        if args.limit is not None or args.select or args.suite or args.attack or args.pipeline or args.variant:
            raise CliUsageError("agentprov import: --release forbids --limit and every filter (--select, --suite, --attack, --pipeline, --variant)")
        if args.sample is not None:
            raise CliUsageError("agentprov import: --release forbids --sample (a sample is a partial corpus, never released)")
    if args.sample is not None and args.limit is not None:
        raise CliUsageError("agentprov import: --sample and --limit are exclusive")
    if args.sample is None and (args.sample_mode is not None or args.seed is not None):
        raise CliUsageError("agentprov import: --sample-mode and --seed go with --sample N")
    if (args.sample_mode == "random") != (args.seed is not None):
        raise CliUsageError("agentprov import: --seed S goes with --sample-mode random, and random needs it")
    if args.artefacts and not args.dry_run:
        raise CliUsageError("agentprov import: --artefacts goes with --dry-run (the table of a sealed corpus is 'agentprov stats --artefacts')")
    if args.release and args.in_process:
        raise AgentProvError("--in-process is refused together with --release (G.4.9)", code="cli.refused.in_process", exit_code=4)
    if args.skip_prov_conformance and args.release:
        raise CliUsageError("agentprov import: --skip-prov-conformance is a dev-mode option; --release always runs tier 4")
    if args.skip_prov_conformance and (args.until or "validation") != "validation":
        raise CliUsageError("agentprov import: --skip-prov-conformance applies to an import that validates "
                            "(--until validation); this one runs no tier 4")
    seen_roles: set[str] = set()
    for entry in args.context:
        role, sep, path = str(entry).partition("=")
        if not sep or not role or not path:
            raise CliUsageError(f"agentprov import: --context expects ROLE=PATH, got {safe_text(entry, 80)!r}")
        if role in seen_roles:  # NF-27: never "the last one wins"
            raise CliUsageError(f"agentprov import: --context names role {safe_text(role, 40)!r} twice")
        seen_roles.add(role)
        if role in args.no_context:
            raise CliUsageError(f"agentprov import: --context and --no-context both name {safe_text(role, 40)!r}")
        if not os.path.exists(path):
            raise CliUsageError(f"agentprov import: --context {safe_text(role, 40)}: the path does not exist")


def _deferred(what: str, label: str, lines: tuple[str, ...]) -> UnsupportedCapability:
    return UnsupportedCapability(
        f"{what} is not available in this build",
        refusal=Refusal(id=label, mode="import", status=f"{what} is deferred in this build", lines=lines),
        code="cli.unsupported.import",
    )


def _filters(args: argparse.Namespace) -> Any:
    from agentprov.adapters.runner.importer import SELECT_KEYS, ImportFilters

    if args.pipeline:
        raise _deferred("--pipeline", "--pipeline", (
            "The pipeline is an index facet (H.3.3); index facets are not built yet (they follow the corpus layer, phase 11).",
            "Select by an AER header field instead: --select suite=..., task=..., attack=..., defense=..., variant=...",
        ))
    select: dict[str, set[str]] = {}
    for key, value in (("suite", args.suite), ("attack", args.attack)):
        if value:
            select.setdefault(key, set()).add(value)
    for expression in args.select:
        key, _, values = expression.partition("=")
        if key not in SELECT_KEYS:
            raise CliUsageError(
                f"agentprov import: --select key {safe_text(key, 40)!r} is not supported in this build; "
                f"keys: {', '.join(sorted(SELECT_KEYS))} (AER header fields; index facets arrive with SEM)"
            )
        select.setdefault(key, set()).update(v for v in values.split(",") if v)
    variants = frozenset({args.variant}) if args.variant else None
    return ImportFilters(variants=variants, select={k: frozenset(v) for k, v in sorted(select.items())})


# ------------------------------------------------------------------------------------------------ status gate
def _resolve_source(label: str, result: CommandResult) -> tuple[str, str | None]:
    from agentprov.adapters.registry import REGISTRY

    registered = {r.source_id for r in REGISTRY}
    if label in ALIASES:
        source, part = ALIASES[label]
        result.notices.append(f"alias {safe_text(label, 60)} resolves to source {source}" + (f" (part {part})" if part else ""))
        result.info(f"agentprov: '{safe_text(label, 60)}' is an alias of '{source}'")
        label_part = part
    else:
        source, label_part = label, None
    if source in registered:
        return source, label_part
    shown = safe_text(source, 80)
    if source in SPEC_SOURCE_IDS:
        raise UnsupportedCapability(
            f"cannot import {shown!r}: the source is not registered in this build",
            refusal=Refusal(
                id=source, mode="import", status="not registered in this build",
                lines=("Its importer is planned for a later phase; no reader, mapper or profile ships in this build.",
                       "Nothing was read from the input and nothing was written."),
            ),
            code="cli.unsupported.import",
        )  # fmt: skip
    choices = sorted(registered | set(ALIASES))
    close = difflib.get_close_matches(source, choices, n=3)
    hint = f"; did you mean {', '.join(close)}?" if close else f"; registered sources: {', '.join(sorted(registered))}"
    # the message is escaped once, where it is printed (main: safe_text per line)
    raise CliUsageError(f"agentprov import: unknown source id '{source[:80]}'{hint}")


def _capability(source: str, part: str | None, args: argparse.Namespace) -> tuple[Any, Any]:
    """The registration and the import capability of the requested part (N.3.1)."""
    from agentprov.adapters.registry import get_source

    registration = get_source(source)
    caps = list(registration.capabilities)
    wanted = args.snapshot if args.snapshot and part is None and any(c.part == args.snapshot for c in caps) else part
    if wanted is None and args.pin:
        wanted = next((c.part for c in caps if c.part == args.pin), None)
        if wanted is None and caps and caps[0].profile:
            from agentprov.adapters.profiles import load_profile

            pins = load_profile(caps[0].profile).data.get("source", {}).get("pins", ())
            wanted = next((str(p.get("part")) for p in pins if p.get("role") == args.pin and p.get("part")), None)
    if wanted is None:
        importable = [c for c in caps if c.role == "source" and c.import_status is not None]
        if len(importable) == 1:
            wanted = importable[0].part
        elif not importable:
            wanted = caps[0].part if caps else None
        else:
            raise CliUsageError(
                f"agentprov import: source {source} has several importable parts ({', '.join(c.part for c in importable)}); "
                "name one with --snapshot or --pin"
            )
    capability = next((c for c in caps if c.part == wanted), None)
    if capability is None:
        raise CliUsageError(f"agentprov import: source {source} has no part {safe_text(str(wanted), 40)!r}")
    return registration, capability


def _gate(source: str, capability: Any, result: CommandResult) -> str:
    """N.3.1 status gate. Returns the source to import (``via`` redirects); raises the exit-5 refusal otherwise."""
    status = capability.import_status
    label = f"{source} · {capability.part}"
    if capability.via:
        result.notices.append(f"{label}: imported via source {capability.via} (registry via)")
        return str(capability.via)
    if capability.role != "source" or status in (None, "planned", "not_possible"):
        reason = {None: "no import capability", "planned": "planned", "not_possible": "not possible"}.get(status, str(status))
        if capability.role != "source":
            reason = f"part role {capability.role} has no import"
        lines = tuple(safe_text(capability.caveat, 300).split("\n")) if capability.caveat else ()
        raise UnsupportedCapability(
            f"cannot import {label!r}: {reason}",
            refusal=Refusal(id=source, mode="import", status=f"{reason} (part {capability.part})",
                            lines=(*lines, "Nothing was read from the input and nothing was written.")),
            code="cli.unsupported.import",
        )
    if capability.caveat:
        result.notices.append(f"{label} ({status}): {safe_text(capability.caveat, 400)}")
    return source


def _served(part: Any, args: argparse.Namespace, result: CommandResult) -> tuple[Any, Any, str | None]:
    """A ``via`` part (D.3.1; D.6.13): the serving source's import part, and the attack that selects the part's
    executions in it (``[family.<ns>.attack_provenance] attack`` of the part's own profile; ``None`` when it names none).
    The slice is imported into the serving source's corpus as a filtered (partial) working corpus."""
    from agentprov.adapters.profiles import load_profile

    attack: str | None = None
    if part.profile:
        table = load_profile(str(part.profile)).family_table().get("attack_provenance")
        if isinstance(table, Mapping) and isinstance(table.get("attack"), str):
            attack = str(table["attack"])
    served = argparse.Namespace(**{**vars(args), "snapshot": None, "pin": None})
    registration, capability = _capability(str(part.via), None, served)
    if attack is not None:
        result.notices.append(f"{part.via} · {capability.part}: the slice is its executions with attack "
                              f"{safe_text(attack, 60)} (--select attack={safe_text(attack, 60)} implied)")
    return registration, capability, attack


def _restrict_attack(filters: Any, attack: str) -> Any:
    """``filters`` with the attack selection narrowed to ``attack`` (a user selection is intersected, never widened)."""
    from dataclasses import replace

    select = dict(filters.select)
    chosen = select.get("attack")
    select["attack"] = frozenset({attack}) if chosen is None else frozenset(chosen) & {attack}
    return replace(filters, select=dict(sorted(select.items())))


# ------------------------------------------------------------------------------------------------ pins and origins
def _pin(profile: Any, args: argparse.Namespace, part: str) -> dict[str, Any] | None:
    pins = [dict(p) for p in profile.data.get("source", {}).get("pins", ()) if isinstance(p, dict) or hasattr(p, "get")]
    if args.pin:
        chosen = next((p for p in pins if p.get("role") == args.pin), None)
        if chosen is None:
            raise CliUsageError(f"agentprov import: profile {profile.id} has no pin with role {safe_text(args.pin, 40)!r}")
        return chosen
    primaries = [p for p in pins if p.get("part") == part and p.get("primary") is True]
    if len(primaries) > 1:  # D-932: never silently the first of several inputs (each is its own snapshot)
        roles = ", ".join(safe_text(str(p.get("role")), 40) for p in primaries)
        raise CliUsageError(f"agentprov import: part {safe_text(part, 40)} of profile {profile.id} has {len(primaries)} "
                            f"primary pins ({roles}); name one with --pin, and its snapshot with --snapshot")
    for predicate in (lambda p: p.get("part") == part and p.get("primary") is True,
                      lambda p: p.get("role") == part, lambda p: p.get("part") == part):
        found = next((p for p in pins if predicate(p)), None)
        if found is not None:
            return found
    return None


def _recipe(profile: Any, pin: dict[str, Any]) -> Any:
    from agentprov.raw.fetch import Recipe

    canonical = profile.data.get("source", {}).get("canonical_repo")
    return Recipe.from_pin(pin, canonical_repo=canonical if isinstance(canonical, str) else None)


def _fetcher(args: argparse.Namespace, ctx: Context) -> Any:
    from agentprov.raw.fetch import Fetcher, resolve_cache_dir

    from agentprov.cli.fetch import guard_cache

    cache = resolve_cache_dir(args.cache_dir, ctx.env)
    guard_cache(cache)  # the corpus is checked against the cache by _disjoint
    large = bool(getattr(args, "i_consent_to_large_download", False))
    consent = "--allow-network" + (" --i-consent-to-large-download" if large else "")
    return Fetcher(cache, allow_network=bool(args.allow_network) and not args.dry_run, consent=consent,
                   large_download_consent=large, env=ctx.env)


def _cached_tree(fetcher: Any, recipe: Any, args: argparse.Namespace, result: CommandResult, why: str
                 ) -> tuple[bool, Any]:
    """Make the pinned commit available: ``(True, fetch result)`` when this call fetched it, ``(True, None)`` when it was
    already cached, ``(False, None)`` in a dry run that would fetch. Without ``--allow-network`` the cache is the only
    source (D-220): a pin it holds is served offline, and a pin it lacks is refused (``raw.fetch.not_cached``, exit 4)."""
    from agentprov.raw.fetch import NotCachedError

    plan = fetcher.plan(recipe)
    if plan.cached:
        return True, None
    if args.dry_run:
        result.output(f"would fetch {safe_text(recipe.origin_label(), 200)} from {safe_text(plan.host, 80)} ({why})")
        return False, None
    if not args.allow_network:
        raise NotCachedError(
            f"{why}: {safe_text(recipe.origin_label(), 200)} is not in the fetch cache and the network is not allowed; rerun "
            f"with --allow-network or run 'agentprov fetch --profile <id> --pin {safe_text(recipe.role, 40)} "
            "--allow-network' first (N.1.11)", exit_code=4)
    return True, fetcher.fetch(recipe)


def _note_fetch(result: CommandResult, recipe: Any, outcome: Any) -> Any:
    """The summary notices of one fetch result: each pin expectation problem, and the network use (N.1.11(1))."""
    for problem in outcome.problems:
        result.notices.append(f"pin expectation: {safe_text(problem, 200)}")
    if outcome.network_used:
        result.notices.append(f"fetched {safe_text(recipe.origin_label(), 200)} (network)")
    return outcome


def _tree(args: argparse.Namespace, ctx: Context, profile: Any, pin: dict[str, Any] | None, limits: Any,
          result: CommandResult) -> tuple[Any, Any]:
    """The source tree and the pin check (``None`` without ``--verify-against-pin``)."""
    from agentprov.adapters.registry import READERS
    from agentprov.adapters.runner import resolve_factory
    from agentprov.adapters.runner.importer import (
        DOWNLOAD_PIN_KINDS,
        ArchiveTree,
        GitPinTree,
        LocalTree,
        PinCheck,
        UnpinnedInputError,
    )

    download = pin is not None and pin.get("kind") in DOWNLOAD_PIN_KINDS
    if args.fetch:
        if pin is None or not (pin.get("kind") == "git" or download):
            raise _deferred("--fetch of this pin", profile.id, (
                "Only git pins and download pins of Zenodo, Hugging Face or URL files are fetched by import in this build.",
                "Fetch others with 'agentprov fetch --profile ID --pin ROLE' and import with --input.",
            ))
        if download and _is_split(pin):
            return _fetched_split(args, ctx, pin, limits, result), None
        recipe = _recipe(profile, pin)
        fetcher = _fetcher(args, ctx)
        available, fetched = _cached_tree(fetcher, recipe, args, result, "--fetch")
        if not available:
            return None, None
        outcome = _note_fetch(result, recipe, fetched if fetched is not None else fetcher.fetch(recipe))
        if download:
            if recipe.sha256 is None or outcome.sha256 is None or outcome.bytes is None:
                raise UnpinnedInputError("the download pin records no SHA-256, so it cannot vouch for an imported archive")
            return ArchiveTree(outcome.path, pin=pin, sha256=outcome.sha256, size=outcome.bytes, limits=limits,
                               retrieved_at=outcome.retrieved_at), None  # fmt: skip
        return GitPinTree(fetcher, recipe, limits=limits), None
    path = Path(args.input)
    if download and pin is not None:
        return _archive_input(args, profile, pin, path, limits), None
    if path.is_file() and path.suffix.lower() in (".zip",):
        raise _deferred("an archive --input under a git pin", str(path.name), (
            "Archive inputs are read through the expand stage when the profile pins the archive itself (a Zenodo,",
            "Hugging Face or URL file, D-200, D-455); this profile's pin is a git tree.",
            "Import the tree with --fetch or --input DIR.",
        ))
    tree = LocalTree(path, limits=limits, allow_hardlinks=bool(args.allow_hardlinks))
    if args.allow_hardlinks:
        result.notices.append("--allow-hardlinks: files with several hard links are accepted (recorded)")
    if not args.verify_against_pin:
        raise UnpinnedInputError(
            "--input needs --verify-against-pin: an unverified file could carry only a local origin, which the AER writer "
            "refuses (every AER is sealed in release mode; C.17 AER-V20); or read the pin itself with --fetch"
        )
    if pin is None:
        raise CliUsageError(f"agentprov import: profile {profile.id} has no pin to verify against")
    if pin.get("listing_sha256"):
        reader = resolve_factory(READERS[str(profile.data.get("import", {}).get("dialect"))])()
        hook = getattr(reader, "listing_origin", None)
        if hook is None:
            raise UnpinnedInputError("--verify-against-pin: the family records no origin for a listing-verified file")
        return tree, PinCheck("listing", pin, listing_origin=hook)
    if pin.get("kind") != "git":
        raise UnpinnedInputError("--verify-against-pin: the pin is neither a git tree nor a tree-listing digest")
    recipe = _recipe(profile, pin)
    fetcher = _fetcher(args, ctx)
    available, fetched = _cached_tree(fetcher, recipe, args, result, "--verify-against-pin")
    if not available:
        return None, None
    if fetched is not None:
        _note_fetch(result, recipe, fetched)
    entries, _skipped = fetcher.git_tree(recipe)
    listing = {e.path: e.oid for e in entries if e.is_blob}
    return tree, PinCheck("blob", pin, listing=listing, repo=recipe.repo, history=fetcher.history_index(recipe))


# ------------------------------------------------------------------------------------------------ per-unit inputs (D-530)
def _per_unit_inputs(args: argparse.Namespace, ctx: Context, profile: Any, primary: dict[str, Any] | None, tree: Any,
                     limits: Any, result: CommandResult) -> tuple[list[Any], list[Any], list[Path]] | None:
    """D-530: the context trees of every role a profile declares (``[import] context_artefacts`` entries
    ``"<role>:<glob>"``, runner item R2) and the pinned objects of its ``lfs_object`` pins (R3, item 6).

    A role is resolved from ``--context ROLE=PATH`` (a local copy checked against the role's pin) or else from the verified
    fetch cache (fetched with ``--allow-network``); ``--no-context ROLE`` maps without it, is reported as a notice and is recorded in the snapshot's ``context_skipped`` (D-221). A
    role that resolves neither way is refused (exit 4), so an import never silently drops its per-unit artefacts. An LFS
    object is taken for a pointer the input holds, verified by the object's sha256. Returns ``(contexts, objects, local
    inputs)``, or ``None`` in a dry run that would fetch."""
    from agentprov.adapters.runner.importer import ContextTree, PinnedObject, UnpinnedInputError
    from agentprov.adapters.types import Origin

    pins = [dict(p) for p in profile.data.get("source", {}).get("pins", ()) if hasattr(p, "get")]
    imp = profile.data.get("import", {})
    roles = sorted({r for r, sep, _g in (str(e).partition(":") for e in imp.get("context_artefacts", ())) if sep})
    given = {r: path for r, _sep, path in (str(e).partition("=") for e in args.context)}
    unknown = sorted((set(given) | set(args.no_context)) - set(roles))
    if unknown:
        raise CliUsageError(f"agentprov import: profile {profile.id} declares no context role {safe_text(unknown[0], 40)!r}")
    contexts: list[Any] = []
    local: list[Path] = []
    for role in roles:
        if role in args.no_context:
            result.notices.append(f"--no-context {safe_text(role, 40)}: units are mapped without their {safe_text(role, 40)} "
                                  "context artefacts")
            continue
        pin = next((p for p in pins if p.get("role") == role and p is not primary), None)
        if pin is None:
            raise CliUsageError(f"agentprov import: profile {profile.id} names context role {safe_text(role, 40)!r} but no pin")
        if role in given:
            local.append(Path(given[role]))
        globs = [g for r, sep, g in (str(e).partition(":") for e in imp.get("context_artefacts", ())) if sep and r == role]
        resolved = _context_tree(args, ctx, profile, pin, given.get(role), limits, result, role, globs)
        if resolved is None:
            return None
        contexts.append(ContextTree(role, resolved[0], resolved[1], pin=pin))
    objects: list[Any] = []
    lfs = [p for p in pins if p.get("role") == "lfs_object"]
    labels = {c.label for c in tree.walk()} if lfs else set()
    for pin in (p for p in lfs if str(p.get("file", p.get("path"))) in labels):
        recipe = _recipe(profile, pin)
        if recipe.sha256 is None:  # NF-28: an LFS object is vouched for by its sha256 alone (as the primary path)
            raise UnpinnedInputError(f"the lfs_object pin of {safe_text(str(pin.get('file')), 120)} records no SHA-256, so it "
                                     "cannot vouch for an imported object")
        fetcher = _fetcher(args, ctx)
        available, fetched = _cached_tree(fetcher, recipe, args, result,
                                          f"the LFS object of {safe_text(str(pin.get('file')), 120)}")
        if not available:
            return None
        outcome = _note_fetch(result, recipe, fetched if fetched is not None else fetcher.fetch(recipe))
        origin = Origin.hf(str(recipe.repo or ""), str(recipe.revision or ""), str(recipe.file or ""))
        objects.append(PinnedObject(str(recipe.file), origin, str(outcome.path), str(outcome.sha256), int(outcome.bytes or 0)))
    return contexts, objects, local


def _context_tree(args: argparse.Namespace, ctx: Context, profile: Any, pin: dict[str, Any], path: str | None,
                  limits: Any, result: CommandResult, role: str, globs: Sequence[str] = ()) -> tuple[Any, Any] | None:
    """One context role's tree and pin check: a download pin is an archive context (D-530), a git pin a pinned tree."""
    from agentprov.adapters.runner.importer import (
        DOWNLOAD_PIN_KINDS,
        ArchiveTree,
        GitPinTree,
        LocalTree,
        PinCheck,
        UnpinnedInputError,
    )
    from agentprov.ingest.paths import open_evidence
    from agentprov.raw.fetch import verify_download

    why = f"the {safe_text(role, 40)} context pin (give --context {safe_text(role, 40)}=PATH, or --no-context {safe_text(role, 40)})"
    if _is_split(pin) or pin.get("kind") not in (*DOWNLOAD_PIN_KINDS, "git"):
        raise _deferred("a context pin of this kind", profile.id, (
            "Context pins are git trees or single downloaded files (Zenodo, Hugging Face) in this build.",
            f"Map without it with --no-context {safe_text(role, 40)}.",
        ))
    recipe = _recipe(profile, pin)
    if pin.get("kind") in DOWNLOAD_PIN_KINDS:
        if recipe.sha256 is None:  # NF-28: md5 and size alone never vouch for an imported context archive
            raise UnpinnedInputError(f"the {safe_text(role, 40)} context pin records no SHA-256, so it cannot vouch for an "
                                     "imported archive")
        if path is not None:
            resolved = Path(os.path.realpath(path))
            with open_evidence(str(resolved.parent), resolved.name, limits) as handle:
                sha256, _md5, size = verify_download(handle, resolved.name, recipe)
            return ArchiveTree(resolved, pin=pin, sha256=sha256, size=size, limits=limits), None
        fetcher = _fetcher(args, ctx)
        available, fetched = _cached_tree(fetcher, recipe, args, result, why)
        if not available:
            return None
        outcome = _note_fetch(result, recipe, fetched if fetched is not None else fetcher.fetch(recipe))
        # PR-11 #4 (D-455): a url pin's retrieval time comes from the cache's acquisition record, as for a primary input
        return ArchiveTree(outcome.path, pin=pin, sha256=str(outcome.sha256), size=int(outcome.bytes or 0), limits=limits,
                           retrieved_at=getattr(outcome, "retrieved_at", None)), None
    fetcher = _fetcher(args, ctx)
    available, fetched = _cached_tree(fetcher, recipe, args, result, why)
    if not available:
        return None
    if fetched is not None:
        _note_fetch(result, recipe, fetched)
    if path is None:
        return GitPinTree(fetcher, recipe, limits=limits), None
    entries, _skipped = fetcher.git_tree(recipe)
    listing = {e.path: e.oid for e in entries if e.is_blob}
    # NF-27: a PATH that holds none of the role's pinned files would pass the pin check vacuously and map every unit
    # without its context
    role_files = [rel for rel in listing if any(_glob_match(rel, g) for g in globs)]
    if not any(os.path.isfile(os.path.join(path, *rel.split("/"))) for rel in role_files):
        raise CliUsageError(f"agentprov import: --context {safe_text(role, 40)}: the path holds none of the pin's "
                            f"{safe_text(role, 40)} files")
    return (LocalTree(Path(path), limits=limits, allow_hardlinks=bool(args.allow_hardlinks)),
            PinCheck("blob", pin, listing=listing, repo=recipe.repo, history=fetcher.history_index(recipe)))


def _glob_match(label: str, glob: str) -> bool:
    """The runner's include/exclude matcher (``fnmatch`` over a POSIX label, ``**/`` also matching zero directories)."""
    import fnmatch

    return fnmatch.fnmatchcase(label, glob) or ("**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1)))


def _is_split(pin: dict[str, Any] | None) -> bool:
    from agentprov.raw.fetch import is_split_pin

    return is_split_pin(pin)


def _fetched_split(args: argparse.Namespace, ctx: Context, pin: dict[str, Any], limits: Any, result: CommandResult) -> Any:
    """``--fetch`` of a split download pin (D-249): every part from the verified cache (fetched with ``--allow-network``),
    in the pin's order; U-07's consent counts the total of the parts (``require_split_consent``)."""
    from agentprov.adapters.runner.importer import ArchiveTree, UnpinnedInputError
    from agentprov.raw.fetch import part_recipes, require_split_consent

    recipes = part_recipes(pin)
    fetcher = _fetcher(args, ctx)
    if not all(fetcher.plan(r).cached for r in recipes):
        require_split_consent(recipes, bool(getattr(args, "i_consent_to_large_download", False)))
    parts = []
    for recipe in recipes:
        available, fetched = _cached_tree(fetcher, recipe, args, result, "--fetch")
        if not available:
            return None
        outcome = _note_fetch(result, recipe, fetched if fetched is not None else fetcher.fetch(recipe))
        if outcome.sha256 is None or outcome.bytes is None:
            raise UnpinnedInputError("a split part records no SHA-256, so it cannot vouch for an imported archive")
        parts.append((outcome.path, outcome.sha256, outcome.bytes))
    return ArchiveTree.split(parts, pin=pin, limits=limits)


def _archive_input(args: argparse.Namespace, profile: Any, pin: dict[str, Any], path: Path, limits: Any) -> Any:
    """``--input FILE`` under a download pin (D-200, D-201): the file is checked against the pin offline (name, size, MD5
    when pinned, SHA-256) and imported as an archive input. ``--verify-against-pin`` is required, as for every input."""
    from agentprov.adapters.runner.importer import ArchiveTree, UnpinnedInputError
    from agentprov.ingest.paths import open_evidence
    from agentprov.raw.fetch import verify_download

    if not args.verify_against_pin:
        raise UnpinnedInputError(
            "--input needs --verify-against-pin: an archive the pin does not vouch for could carry only a local origin, "
            "which the AER writer refuses (C.17 AER-V20); or read the pin itself with --fetch"
        )
    if _is_split(pin):  # D-249: --input DIR holds the parts; each is found by its pinned file name and checked
        from agentprov.raw.fetch import part_recipes, verify_parts

        if not path.is_dir():
            raise CliUsageError(f"agentprov import: profile {profile.id} pins an archive in byte parts; --input names the "
                                "directory that holds the parts")
        directory = os.path.realpath(path)
        recipes = part_recipes(pin)
        checked = verify_parts(lambda name: open_evidence(directory, name, limits), recipes)
        parts = [(os.path.join(directory, str(r.file).rsplit("/", 1)[-1]), sha, size)
                 for r, (sha, size) in zip(recipes, checked, strict=True)]  # fmt: skip
        return ArchiveTree.split(parts, pin=pin, limits=limits)
    if not path.is_file():
        raise CliUsageError(f"agentprov import: profile {profile.id} pins a downloaded file; --input names that file")
    if not args.verify_against_pin:
        raise UnpinnedInputError(
            "--input needs --verify-against-pin: an archive the pin does not vouch for could carry only a local origin, "
            "which the AER writer refuses (C.17 AER-V20); or read the pin itself with --fetch"
        )
    recipe = _recipe(profile, pin)
    resolved = Path(os.path.realpath(path))
    with open_evidence(str(resolved.parent), resolved.name, limits) as handle:
        sha256, _md5, size = verify_download(handle, path.name, recipe)
    return ArchiveTree(resolved, pin=pin, sha256=sha256, size=size, limits=limits)


# ------------------------------------------------------------------------------------------------ corpus guards
def _final_dir(corpus: str) -> Path:
    path = Path(corpus)
    if path.name.endswith(".partial"):
        path = path.with_name(path.name[: -len(".partial")])
    return Path(os.path.abspath(path))


def _inside(a: Path, b: Path) -> bool:
    try:
        Path(os.path.realpath(a)).relative_to(os.path.realpath(b))
    except ValueError:
        return False
    return True


def _disjoint(partial: Path, others: list[Path]) -> None:
    """G2 (N.1.9): the output tree and every input tree are disjoint."""
    for other in others:
        if _inside(partial, other) or _inside(other, partial):
            raise GuardRefusedError("the corpus directory overlaps an input or the fetch cache (G2); choose another --corpus")


# ------------------------------------------------------------------------------------------------ command
def run_import(ctx: Context) -> CommandResult:
    args = ctx.args
    _check_options(args)
    result = CommandResult(dry_run=bool(args.dry_run))
    if args.spec:
        label = args.source or args.spec
        raise _deferred("--spec", str(label), (
            "Committed corpus specs (H.1.6) arrive with corpus sealing (phase 11); import a source by id with",
            "--input PATH or --fetch. Nothing was read from the input and nothing was written.",
        ))
    source, alias_part = _resolve_source(str(args.source), result)
    registration, capability = _capability(source, alias_part, args)
    source = _gate(source, capability, result)
    via_attack: str | None = None
    if capability.via:  # D.3.1 via: the part is imported through the serving source's own import part
        registration, capability, via_attack = _served(capability, args, result)
        source = _gate(source, capability, result)
    specs = list(dict.fromkeys(args.prov_spec or [SPEC_ID]))
    if COMPAT_SPEC in specs:
        raise _deferred(f"--prov-spec {COMPAT_SPEC}", source, (
            "The adprov-v2.3-compat regression oracle (R-55) is not written into import corpora in this build;",
            "its byte identity runs through 'agentprov migrate gate B'.",
        ))
    unknown = [s for s in specs if s != SPEC_ID]
    if unknown:
        raise CliUsageError(f"agentprov import: unknown --prov-spec {safe_text(unknown[0], 60)!r}; this build derives {SPEC_ID}")
    filters = _filters(args)
    if via_attack is not None:
        filters = _restrict_attack(filters, via_attack)

    from agentprov.adapters.profiles import load_profile
    from agentprov.corpus.index import IndexLog
    from agentprov.corpus.layout import CorpusLayout, partial_dir
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.errors import ProfileError
    from agentprov.ingest.limits import IngestLimits

    try:
        profile = load_profile(args.profile or capability.profile)
    except ProfileError as exc:
        if args.profile and str(exc).startswith("no profile"):
            raise CliUsageError(f"agentprov import: no profile {safe_text(args.profile, 60)!r} is shipped in the package") from None
        raise
    if profile.source_id != source:
        raise CliUsageError(f"agentprov import: profile {profile.id} belongs to source {profile.source_id}, not {source}")
    part = str(capability.part)
    snapshot = args.snapshot or part
    corpus_id = args.corpus_id or capability.corpus_id or source
    if not _CORPUS_ID.fullmatch(corpus_id) or len(corpus_id) > 64:
        raise CliUsageError("agentprov import: --corpus-id must match ^[a-z0-9]+(-[a-z0-9]+)*$ (at most 64 characters)")
    limits = IngestLimits()
    if args.max_file_bytes:
        limits = limits.replace(max_artefact_bytes=args.max_file_bytes)
    if args.max_json_depth:
        limits = limits.replace(max_json_depth=args.max_json_depth)
    pin = _pin(profile, args, part)
    tree, pin_check = _tree(args, ctx, profile, pin, limits, result)
    if tree is None:  # a dry run without the pin in the cache: the plan was printed, nothing maps
        result.counters = {"seen": 0}
        result.notices.append("dry run: the pin is not cached, so nothing was mapped (N.1.6)")
        return result
    per_unit = _per_unit_inputs(args, ctx, profile, pin, tree, limits, result)  # D-530
    if per_unit is None:
        result.counters = {"seen": 0}
        result.notices.append("dry run: a context pin or LFS object is not cached, so nothing was mapped (N.1.6)")
        return result
    final = _final_dir(args.corpus)
    partial = partial_dir(final)
    inputs = [Path(args.input), *per_unit[2]] if args.input else list(per_unit[2])
    if args.fetch or args.verify_against_pin or per_unit[0] or per_unit[1]:
        from agentprov.raw.fetch import resolve_cache_dir

        inputs.append(resolve_cache_dir(args.cache_dir, ctx.env))
    _disjoint(partial, inputs)
    if args.dry_run:
        _dry_run_guards(final, partial)
    if args.in_process:
        result.notices.append("--in-process: expand, map and prov ran in the CLI process (debugging only; G.4.9)")

    from agentprov.adapters.runner.importer import import_source
    from agentprov.cli.checks import finish_validation_cache, validation_cache

    cache = validation_cache(ctx)
    common: dict[str, Any] = dict(
        profile_id=profile.id, filters=filters, limit=args.limit, mode="release" if args.release else "dev", part=part,
        snapshot_id=snapshot, corpus_id=corpus_id, until=args.until or "validation", prov_specs=specs,
        workers=args.jobs, in_process=bool(args.in_process), limits=limits, retry_failed=bool(args.retry_failed),
        progress=ctx.progress, pin_check=pin_check, pin=pin, validation_cache=cache,
        prov_conformance=not args.skip_prov_conformance, context_trees=per_unit[0], pinned_objects=per_unit[1],
        context_skipped=sorted(set(args.no_context)),  # D-221 (NF-29): recorded in the snapshot
        drain=True,  # D-394: import honours a --control-file drain; a re-map never does (PR-6)
    )  # fmt: skip
    if args.sample is not None:  # D-529
        from agentprov.adapters.runner.importer import ImportSample

        common["sample"] = ImportSample(args.sample, args.sample_mode or "first", args.seed)
    if args.dry_run and args.artefacts:
        report, table_rows, scanned = _import_and_scan(source, tree, common, limits, args, result)
        _result(result, report, args, corpus_id, partial)
        _artefact_table(result, table_rows, scanned, args)
        finish_validation_cache(result, cache)
        return result
    from agentprov.io import workers as worker_pool

    if args.size_hints:  # D-554: the pools of this import charge jobs by the previous version's PROV sizes
        worker_pool.set_default_charge_policy(_size_hint_policy(Path(args.size_hints), limits))
    try:
        if args.dry_run:
            resume = None
            if partial.is_dir() and CorpusLayout(partial).executions.exists():
                resume = IndexLog.load(CorpusLayout(partial).executions, CorpusLayout(partial), limits)
            report = import_source(source, tree, corpus=None, dry_run=True, resume_index=resume, **common)
        else:
            with CorpusWriter(final, limits=limits, release=bool(args.release), command="import",
                              break_stale_lock=bool(args.break_stale_lock), build_step=gitinfo.build_step("import")) as writer:
                report = import_source(source, tree, corpus=writer, **common)
    finally:
        worker_pool.set_default_charge_policy(None)
    _result(result, report, args, corpus_id, partial)
    finish_validation_cache(result, cache)
    return result


def _size_hint_policy(previous: Path, limits: Any) -> Any:
    """D-554: ``charge(job, store_root)`` for an import, from a previous version of the corpus, read only through its
    index. A ``prov`` job is charged prov-perf's model over the stored PROV size of the execution with the same source key
    (stable across mapping and profile versions; read from the job's staged AER header, the parent's own sealed file);
    any other job, or a key without a hint, is charged its kind's RSS cap. A charge decides when a job starts, never what
    it produces."""
    from agentprov.corpus.dedup import source_key
    from agentprov.corpus.reader import CorpusReader
    from agentprov.ingest.loaders import strict_json_loads
    from agentprov.io.workers import WorkerLimits, prov_charge

    reader = CorpusReader.open(previous)
    sizes: dict[str, int] = {}
    for row in reader.index():
        recorded = (row.prov_paths or {}).get("agentprov-prov/0.1")
        if recorded is not None:
            try:
                sizes[row.source_key] = (reader.root / recorded).stat().st_size
            except OSError:
                continue
    caps = WorkerLimits()

    def charge(job: Any, store_root: Path | None) -> int:
        cap = (job.limits or caps).for_kind(job.kind).rss_bytes  # D-931: a job's own limits (a source's map cap)
        if job.kind != "prov" or store_root is None or not job.inputs:
            return cap
        sha = str(job.inputs[0]["sha256"])
        try:
            with open(store_root / sha[:2] / f"{sha}.jsonl", "rb") as handle:
                header = strict_json_loads(handle.readline(limits.max_jsonl_line_bytes + 1), limits, record=True)
            key = header["source_key"]
            size = sizes.get(source_key(str(key["sha256"]), key["loc"]))
        except (OSError, KeyError, TypeError, ValueError, AgentProvError):
            return cap
        return cap if size is None else prov_charge(size, cap=cap)

    return charge


def _dry_run_guards(final: Path, partial: Path) -> None:
    """The read-only guards ``CorpusWriter.open`` applies, so a dry run refuses what the real run refuses (N.1.6(5)):
    an existing final directory, a tree inside a sealed corpus (G1) and one inside a git work tree (G3). No lock, no
    write."""
    from agentprov.corpus.layout import assert_outside_git_work_tree, assert_writable
    from agentprov.io.atomic import DestinationExistsError

    if os.path.lexists(final):
        raise DestinationExistsError("the final corpus directory already exists")
    assert_writable(partial)
    assert_outside_git_work_tree(partial)  # as the writer does: without an is_ignored callback (fail closed)


# ------------------------------------------------------------------------------------------------ --dry-run --artefacts
def _import_and_scan(source: str, tree: Any, common: dict[str, Any], limits: Any, args: argparse.Namespace,
                     result: CommandResult) -> tuple[Any, list[Any], int]:
    """Run the import into a private temporary corpus, scan every mapped execution, delete the temporary corpus.

    N.2.2 and D.15.4: ``import --dry-run --artefacts`` reads and maps and writes nothing to a corpus. The mapped AERs
    (and SEM files) have to exist somewhere to be scanned, so they go into a throwaway working tree below a fresh
    temporary directory that is removed in every case; the requested ``--corpus`` is never touched or resumed.
    """
    import shutil
    import tempfile

    from agentprov.adapters.runner.importer import import_source
    from agentprov.artefacts import discover_catalogues, scan, table
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.writer import CorpusWriter

    scratch = tempfile.mkdtemp(prefix="agentprov-artefacts-")
    try:
        final = Path(scratch) / "scan"
        with CorpusWriter(final, limits=limits, release=bool(args.release), command="import --dry-run --artefacts") as writer:
            report = import_source(source, tree, corpus=writer, **common)
        reader = CorpusReader.open(final, limits=limits)
        catalogues = discover_catalogues()
        findings = []
        unscannable = 0
        rows = reader.index()
        for row in rows:
            try:
                doc = reader.read_aer(row)
                sem = next(iter(reader.read_sem_all(row).values()), None) if row.sem_paths else None
                findings.extend(scan([*doc.records, doc.seal], catalogues, sem_records=sem.records if sem is not None else None))
            except AgentProvError:
                unscannable += 1
        if unscannable:
            result.notices.append(f"{unscannable} mapped execution(s) could not be read back for the artefact scan")
        result.notices.append("artefact scan: the mapped executions were held in a private temporary corpus, deleted afterwards")
        return report, table(findings, n_executions=len(rows)), len(rows)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _artefact_table(result: CommandResult, rows: list[Any], scanned: int, args: argparse.Namespace) -> None:
    from agentprov.io.canonical import jcs_bytes

    result.counters.update({"artefact_classes": len(rows), "artefact_scanned": scanned,
                            "artefact_unclassified": sum(1 for r in rows if r.handling is None)})
    result.output(f"artefact table: {scanned} execution(s) scanned, {len(rows)} artefact class(es) (locators only, no content)")
    for row in rows:
        share = "-" if row.proportion is None else f"{100 * row.proportion:.1f}%"
        handling = row.handling or "unclassified"
        first = ", ".join(safe_text(ex, 80) for ex in row.first)
        result.output(f"  {safe_text(row.artefact_id, 80)}  [{safe_text(handling, 40)}]  executions={row.executions}  hits={row.hits}  share={share}  first: {first}")
    if not rows:
        result.output("  no artefacts found")
    if not args.json:
        document = {"format": "agentprov-artefact-table/0.1", "n_executions": scanned, "rows": [r.to_json() for r in rows]}
        result.payload = jcs_bytes(document) + b"\n"


def _result(result: CommandResult, report: Any, args: argparse.Namespace, corpus_id: str, partial: Path) -> CommandResult:
    result.counters = dict(report.counters)
    result.issues_by_code = dict(report.issues_by_code)
    result.failures = list(report.failures)
    result.notices.extend(report.notices)
    if report.partial:
        why = "a filter, --limit or --sample was given for a snapshot (N.1.7)"
        if report.incomplete:  # D-610: a stopped run's snapshot is partial too
            why += ", or a run stopped before it ran to the end (N.1.10)"
        result.notices.append(f"partial working corpus: {why}; package refuses it")
    result.corpus = {
        "content_digest": None,
        "corpus_id": corpus_id,
        "root": redact_personal(str(partial)),
        "state": "working",
    }
    result.exit_code = report.exit_code
    c = report.counters
    verb = "would import" if args.dry_run else "imported"
    result.info(
        f"agentprov import: {verb} {c['mapped']} unit(s) from {c['seen']} candidate(s): {c['sealed_clean']} sealed clean, "
        f"{c['sealed_with_issues']} with issues, {c['degenerate']} degenerate, {c['failed']} failed; "
        f"{c['registered']} registered, {c['duplicates']} duplicate(s), {c['skipped_resume']} resumed, {c['filtered']} filtered, "
        f"{c['excluded']} excluded"
    )
    if not args.dry_run:
        result.info(f"agentprov import: working corpus {redact_personal(str(partial))} ({c['annotated']} annotated, {c['derived']} derived, {c['validated']} validated)")
    for failure in report.failures[:20]:
        subject = failure["subject"]
        shown = subject.get("ex") or subject.get("path") or ""
        result.error(f"  failed: {safe_text(shown, 120)} [{failure['stage']}] {failure['code']}")
    for notice in result.notices:
        result.info(f"notice: {safe_text(notice, 400)}")
    return result
