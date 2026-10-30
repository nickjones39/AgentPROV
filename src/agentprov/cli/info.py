"""``agentprov info`` (alias ``sources``): versions, source registry, installation, host (MN N.2.9; D.3.5; DECISIONS D-7).

The source registry (``agentprov.adapters.registry``) is rendered per part, with its gated statuses and caveats, through
``agentprov.adapters.registry.render``: nothing about a source is hand-written, and no status is printed that the
registry does not hold. ``info SOURCE`` (or ``--source``) adds the part details, the shipped profiles and their pins, the
licence policy and the evidence references. ``--matrix`` and ``--must-not-claim`` need the claims library of D.3.1
(``registry/claims.py``), which is not part of this build, and refuse with exit 5. Also reported: the version axes, the
installed extras and tools, the interpreter and its advisory (AD-16), ``$AGENTPROV_HOME``, built backend environments,
the probed host profile and the isolation grade (D-7). It runs no benchmark and uses no network.

``info`` never runs a subprocess other than the host probes of ``agentprov.host`` and the allocation-rate calibration
worker that grades the isolation (the same calibration the worker pool uses).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import (
    CliUsageError,
    CommandResult,
    Context,
    Refusal,
    UnsupportedCapability,
    redact_personal,
    safe_text,
)
from agentprov.envinfo import interpreter_advisory
from agentprov.io.canonical import jcs_bytes
from agentprov.aer import READABLE_VERSIONS
from agentprov.corpus.manifest import CORPUS_FORMATS
from agentprov.versions import VERSIONS, __version__

_REGISTRY_NOTE: Final = (
    "Statuses are the gated values of the registry (D.3.2): supported only after the full pinned snapshot is imported "
    "through agentprov import with zero crashes and the counts are recorded in docs/reports/ (HON-10)."
)
_CLAIMS_NOTE: Final = "The claims library (agentprov.adapters.registry.claims, D.3.1) is not part of this build."
_EXTRAS: Final = (("live", "dotenv"), ("render", "pydot"), ("shacl", "pyshacl"), ("zenodo", "agentprov_zenodo"))
_TOOLS: Final = ("git", "uv", "dot")
_ENV_MARKER: Final = "AGENTPROV_ENV.json"
_MAX_ENVS: Final = 50
_MARKER_KEYS: Final = ("status", "commit", "commit8", "lock_sha256", "python", "sandbox_status")


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "info",
        aliases=["sources"],
        parents=[shared],
        help="versions, the source registry, installed extras and tools, host and isolation grade",
        description="Show versions, the source registry (per part, gated statuses), installation and host (N.2.9).",
        allow_abbrev=False,
    )
    p.set_defaults(command="info", handler=run_info, feedback=False)
    p.add_argument("source", nargs="?", metavar="SOURCE", help="a registered source id: parts, profiles, pins, licence")
    p.add_argument("--source", dest="source_opt", metavar="SOURCE", help="same as SOURCE")
    what = p.add_mutually_exclusive_group()
    what.add_argument("--matrix", action="store_true", help="the compatibility matrix (needs the claims library; deferred)")
    what.add_argument("--must-not-claim", action="store_true", help="the must-not-claim items (need the claims library; deferred)")
    p.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="payload format (default text)")


# --------------------------------------------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------------------------------------------


def agentprov_home() -> Path:
    raw = os.environ.get("AGENTPROV_HOME")
    return Path(raw) if raw else Path.home() / ".agentprov"


def _probe_host() -> tuple[dict[str, Any], dict[str, Any]]:
    """The host profile record and the isolation grade (D-7). Spawns the calibration worker where it is needed."""
    from agentprov.host import Calibration, constants_for, detect_host

    profile = detect_host()
    caps = profile.caps
    if caps.hard_memory_cap.value != "none":
        calibration = Calibration.skipped("a hard memory cap is enforced")
    elif caps.rss_sampler.value == "none":
        calibration = Calibration.skipped("no RSS sampler")
    else:
        from agentprov.io.workers import get_calibration

        calibration = get_calibration(profile)
    constants = constants_for(profile, calibration)
    isolation = {
        "grade": constants.grade,
        "reasons": list(constants.grade_reasons),
        "calibration": calibration.status,
        "default_workers": constants.default_workers,
    }
    return profile.to_record(), isolation


def _backend_environments(home: Path) -> list[dict[str, Any]]:
    """Built backend environments under ``$AGENTPROV_HOME/envs`` with their marker facts (no benchmark is imported)."""
    from agentprov.errors import IngestError
    from agentprov.ingest import IngestLimits, strict_json_loads

    envs = home / "envs"
    try:
        names = sorted(n for n in os.listdir(envs) if (envs / n).is_dir() and not (envs / n).is_symlink())
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for name in names[:_MAX_ENVS]:
        entry: dict[str, Any] = {"name": safe_text(name, 80), "marker": False}
        marker = envs / name / _ENV_MARKER
        try:
            if marker.is_file() and not marker.is_symlink() and marker.stat().st_size <= 64 * 1024:
                data = strict_json_loads(marker.read_bytes(), IngestLimits())
                entry["marker"] = True
                if isinstance(data, dict):
                    for key in _MARKER_KEYS:
                        if key in data and isinstance(data[key], str | int | bool):
                            entry[key] = safe_text(data[key], 120)
        except (OSError, IngestError):
            entry["marker"] = "unreadable"
        out.append(entry)
    return out


def _escape(value: Any) -> Any:
    """Registry and profile data are trusted package data, but every string is still escaped (D.3.5 rule 3); nothing is
    truncated, so a part's caveat is shown whole (R-15; CD-1)."""
    if isinstance(value, str):
        return safe_text(value, None)
    if isinstance(value, dict):
        return {k: _escape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_escape(v) for v in value]
    return value


def _registry() -> dict[str, Any]:
    from agentprov.adapters.registry.render import registry_rows

    return _escape(registry_rows())


def collect() -> dict[str, Any]:
    """Everything ``info`` reports, as a JSON-able mapping (also the ``--format json`` payload)."""
    advisory = interpreter_advisory()
    home = agentprov_home()
    cache_env = os.environ.get("AGENTPROV_UPSTREAM_CACHE")
    host, isolation = _probe_host()
    return {
        "agentprov_version": __version__,
        "versions": dict(VERSIONS),
        "readable": {"aer": [f"aer/{v}" for v in READABLE_VERSIONS], "corpus_format": sorted(CORPUS_FORMATS)},
        "registry": {**_registry(), "note": _REGISTRY_NOTE},
        "installation": {
            "extras": {name: importlib.util.find_spec(module) is not None for name, module in _EXTRAS},
            "tools": {tool: shutil.which(tool) is not None for tool in _TOOLS},
            "interpreter": {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
                "interpreter_advisory": None if advisory is None else advisory.to_json(),
            },
            "agentprov_home": redact_personal(str(home)),
            "cache_dir": redact_personal(cache_env if cache_env else str(home / "cache")),
            "backend_environments": _backend_environments(home),
        },
        "host": {"profile": host, "isolation": isolation},
    }


# --------------------------------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------------------------------


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def render(data: dict[str, Any], fmt: str) -> str:
    """Text or Markdown rendering. Every data-derived string already went through ``safe_text`` in :func:`collect`."""
    md = fmt == "markdown"

    def head(title: str) -> list[str]:
        return ["", f"## {title}" if md else title, ""] if md else ["", title]

    versions = data["versions"]
    emitted = " ".join(versions[k] for k in ("aer", "sem", "capture", "prov_spec", "ontology", "corpus_format"))
    lines = [f"# agentprov {data['agentprov_version']}" if md else f"agentprov {data['agentprov_version']}"]
    lines.append(f"formats: {emitted}")
    readable = data["readable"]
    lines.append(f"readable: {' '.join(readable['aer'])} {' '.join(readable['corpus_format'])}")
    lines.append(f"regression oracle (on request only): {versions['compat_spec']}")
    lines += head("Sources")
    lines += _registry_lines(data["registry"])
    inst = data["installation"]
    interp = inst["interpreter"]
    advisory = interp["interpreter_advisory"]
    lines += head("Installation")
    lines.append(f"  python            {interp['version']} ({interp['implementation']})")
    if advisory is None:
        lines.append("  interpreter_advisory  none")
    else:
        lines.append(
            f"  interpreter_advisory  below {advisory['floor']}: missing fixes for {', '.join(advisory['missing'])}; "
            "release mode refuses archive and compressed-stream ingestion"
        )
    lines.append("  extras            " + ", ".join(f"{k}: {_yes(v)}" for k, v in inst["extras"].items()))
    lines.append("  tools             " + ", ".join(f"{k}: {_yes(v)}" for k, v in inst["tools"].items()) + "  (versions are not probed)")
    lines.append(f"  AGENTPROV_HOME    {inst['agentprov_home']}")
    lines.append(f"  cache             {inst['cache_dir']}")
    envs = inst["backend_environments"]
    if not envs:
        lines.append("  backend envs      none built")
    for env in envs:
        facts = " ".join(f"{k}={env[k]}" for k in _MARKER_KEYS if k in env)
        lines.append(f"  backend env       {env['name']} marker={env['marker']} {facts}".rstrip())
    prof = data["host"]["profile"]
    iso = data["host"]["isolation"]
    lines += head("Host")
    lines.append(f"  os / arch         {prof['os_family']} {prof['os_release']} / {prof['arch']} (machine {prof['machine']})")
    memory = prof["memory_bytes"]
    lines.append(
        f"  cpus / memory     {prof['cpu_count']} / " + ("unknown" if memory is None else f"{memory / 1024**3:.1f} GiB")
    )
    caps = prof["capabilities"]
    for name in ("rlimits", "rlimit_as_enforced", "rss_sampler", "tree_kill", "hard_memory_cap"):
        cap = caps[name]
        value = ", ".join(cap["value"]) if isinstance(cap["value"], list) else cap["value"]
        lines.append(f"  {name:<17} {value}  ({cap['how']})")
    reasons = f" ({'; '.join(iso['reasons'])})" if iso["reasons"] else ""
    lines.append(f"  isolation grade   {iso['grade']}{reasons}; calibration {iso['calibration']}")
    return "\n".join(lines)


def _registry_lines(registry: dict[str, Any]) -> list[str]:
    """The D.3.5 table: one row per part, fixed columns, and the numbered caveats below it."""
    from agentprov.adapters.registry.render import status_text

    width = max([44, *(len(f"{row['source_id']} · {row['part']}") + 2 for row in registry["parts"])])  # a long label keeps its gap
    lines = [f"  registry {registry['date']}", f"  {'SOURCE · PART':<{width}}{'ROLE':<16}{'IMPORT':<14}{'LIVE':<10}POLICY"]
    notes: list[str] = []
    for row in registry["parts"]:
        mark = ""
        if row["caveat"]:
            notes.append(row["caveat"])
            mark = f" [{len(notes)}]"
        policy = row["policy"] + (" (restricted)" if row["restricted"] else "")
        lines.append(
            f"  {row['source_id'] + ' · ' + row['part']:<{width}}{row['role']:<16}{status_text(row['import']) + mark:<14}"
            f"{status_text(row['live']):<10}{policy}"
        )
    for number, note in enumerate(notes, 1):
        lines.append(f"  [{number}] {note}")
    lines.append(f"  {registry['note']}")
    return lines


def render_source(detail: dict[str, Any]) -> str:
    """``info SOURCE``: parts, profiles and pins, licence and evidence references (escaped by the caller)."""
    from agentprov.adapters.registry.render import status_text

    lines = [f"{detail['source_id']}: {detail['name']} (family {detail['family']})", "", "Parts"]
    for row in detail["parts"]:
        target = f" (v0.1 target {row['import_target']})" if row["import_target"] and row["import_target"] != row["import"] else ""
        lines.append(f"  {row['part']}: role {row['role']}, evidence {row['evidence']}, import {status_text(row['import'])}{target}, "
                     f"live {status_text(row['live'])}")
        for key in ("profile", "corpus_id", "via", "owner"):
            if row[key]:
                lines.append(f"    {key}: {row[key]}")
        if row["sealed"]:
            lines.append(f"    sealed: {', '.join(row['sealed'])}")
        if row["dialects"]:
            lines.append(f"    dialects: {', '.join(row['dialects'])} · variants {', '.join(row['variants'])}")
        if row["caveat"]:
            lines.append(f"    caveat: {row['caveat']}")
    lines += ["", "Profiles"]
    for pid, profile in detail["profiles"].items():
        lines.append(f"  {pid} v{profile['version']} sha256 {profile['sha256']}")
        for pin in profile["pins"]:
            fields = [str(pin.get(k)) for k in ("kind", "repo", "commit", "doi", "tree") if pin.get(k)]
            lines.append(f"    pin {pin.get('role')}: {' '.join(fields)}")
    lic = detail["licence"]
    lines += ["", "Licence", f"  {lic['spdx']} (data {lic['data_licence']}), policy {lic['policy']}", f"  basis: {lic['basis']}"]
    lines += [f"  restriction: {r}" for r in lic["restrictions"]]
    lines += [f"  attribution: {a}" for a in lic["attribution"]]
    lines += [f"  unassessed: {u}" for u in lic["unassessed"]]
    lines += ["", "Evidence", *(f"  {ref}" for ref in detail["evidence_refs"])]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------
# Command
# --------------------------------------------------------------------------------------------------------------


def _needs_claims(what: str, label: str) -> UnsupportedCapability:
    return UnsupportedCapability(
        f"{what} needs the claims library, which is not part of this build",
        refusal=Refusal(id=label, mode="info", status="the claims library is not part of this build", lines=(_CLAIMS_NOTE,)),
        code="cli.unsupported.info",
    )


def _source_info(source: str, args: argparse.Namespace) -> CommandResult:
    from agentprov.adapters.registry import REGISTRY
    from agentprov.adapters.registry.render import source_detail

    try:
        detail = _escape(source_detail(source))
    except KeyError:
        known = ", ".join(r.source_id for r in REGISTRY)
        raise CliUsageError(f"agentprov info: {safe_text(source, 80)!r} is not a registered source; registered: {known}") from None
    result = CommandResult()
    result.counters = {"parts": len(detail["parts"])}
    text = jcs_bytes(detail) + b"\n" if args.format == "json" else (render_source(detail) + "\n").encode("utf-8")
    if args.json:
        for line in text.decode("utf-8").splitlines():
            result.info(line)
    else:
        result.payload = text
    return result


def run_info(ctx: Context) -> CommandResult:
    args = ctx.args
    if args.source and args.source_opt and args.source != args.source_opt:
        raise CliUsageError("agentprov info: SOURCE and --source name different sources")
    source = args.source or args.source_opt
    if args.matrix:
        raise _needs_claims("--matrix", "--matrix")
    if args.must_not_claim:
        raise _needs_claims("--must-not-claim", "--must-not-claim")
    if source:
        return _source_info(source, args)
    data = collect()
    result = CommandResult()
    result.counters = {"sources_registered": len(data["registry"]["sources"]),
                       "extras_installed": sum(data["installation"]["extras"].values())}
    advisory = data["installation"]["interpreter"]["interpreter_advisory"]
    if advisory is not None:
        result.notices.append(
            f"interpreter below {advisory['floor']}: release mode refuses archive and compressed-stream ingestion (AD-16)"
        )
    if data["host"]["isolation"]["grade"] == "degraded":
        result.notices.append("isolation grade is degraded: release mode would refuse (exit 3)")
    if args.format == "json":
        text = jcs_bytes(data) + b"\n"
    else:
        text = (render(data, args.format) + "\n").encode("utf-8")
    if args.json:
        # --json puts the summary document on stdout, so the human rendering goes to stderr (N.1.2, N.1.4)
        for line in text.decode("utf-8").splitlines():
            result.info(line)
    else:
        result.payload = text
    return result
