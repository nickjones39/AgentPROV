"""``agentprov run``: live capture through a backend worker (MN N.2.1, N.2.1a, N.2.1b; DECISIONS D-9, D-10, D-11).

The command validates the whole command line (N.1.10(1) and N.2.1a(3) rules, exit 2), applies the status gate of the
source's live part, locates the built backend environment and checks its T0 identity (D.10.6), resolves the agent
(scripted transport, or a real endpoint through ``.env`` with the containment, preflight and consent gates of
N.1.11(2-3)), has the worker expand the plan, and runs the campaign (:mod:`agentprov.cli.live.campaign`): every attempt
is a capture session staged by the worker, ingested like an ``--input`` tree and mapped, derived and validated through
the runner into ``<DIR>.partial/``. ``--dry-run`` prints the plan (or, with ``--preset``, the concurrency plan of
N.2.1a(3)) and writes nothing. Resolutions: N.2.1b.

Imports of the optional pieces (``agentprov.presets``, ``agentprov_capture``, the host probe, ``dotenv``) happen inside
the functions that need them, so ``--help`` stays light (M.5.2(7)).
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from agentprov.cli import gitinfo
from agentprov.cli.common import (
    CliUsageError,
    CommandResult,
    Context,
    Refusal,
    UnsupportedCapability,
    bounded_int,
    redact_personal,
    register_secret,
    safe_text,
)
from agentprov.errors import AgentProvError

if TYPE_CHECKING:
    from agentprov.host import HostProfile
    from agentprov.presets import ConcurrencyPlan

#: The ``local = true`` shorthands of ``endpoints.toml`` (D-690; a test keeps this equal to the registry).
LOCAL_ENDPOINT_NAMES: Final = ("ollama", "omlx", "lmstudio", "mlx_lm", "llamacpp", "vllm")
#: ``--endpoint`` names of N.2.1 (the explicit-endpoint form); every local shorthand too (D-691).
ENDPOINT_NAMES: Final = ("deepseek", "openai", "openrouter", "anthropic", "local", *LOCAL_ENDPOINT_NAMES)
#: D-656 (Q3, user decision 2026-10-22): an Anthropic run states ``--max-tokens N`` or takes ``--max-tokens
#: harness-default`` (this value, declared by the backend as a harness_policy item); with neither, it is refused.
HARNESS_DEFAULT_MAX_TOKENS: Final = 16000
MAX_TOKENS_HARNESS_DEFAULT: Final = "harness-default"
_CELL_OPTIONS: Final = (
    "suite",
    "benchmark_version",
    "user_tasks",
    "attack",
    "injection_tasks",
    "benign",
    "defence",
)
_PRESET_ONLY_FLAGS: Final = (
    ("model_dir", "--model-dir"),
    ("model_size_gb", "--model-size-gb"),
    ("active_params_b", "--active-params-b"),
    ("context_tokens", "--context-tokens"),
    ("kv_gb_per_trace", "--kv-gb-per-trace"),
    ("server_max_concurrency", "--server-max-concurrency"),
    ("tune_jobs", "--tune-jobs"),
    ("tune_out", "--tune-out"),
)


def _int_min(minimum: int) -> Any:
    def parse(text: str) -> int:
        value = bounded_int(text)
        if value < minimum:
            raise argparse.ArgumentTypeError(f"must be >= {minimum}")
        return value

    return parse


def _finite_float(minimum: float | None = None, *, strictly_positive: bool = False) -> Any:
    def parse(text: str) -> float:
        try:
            value = float(text)
        except ValueError:
            raise argparse.ArgumentTypeError("must be a number") from None
        if not math.isfinite(value):
            raise argparse.ArgumentTypeError("must be finite")
        if strictly_positive and not value > 0:
            raise argparse.ArgumentTypeError("must be > 0")
        if minimum is not None and value < minimum:
            raise argparse.ArgumentTypeError(f"must be >= {minimum:g}")
        return value

    return parse


def _max_tokens(text: str) -> int | str:
    """``--max-tokens``: a positive integer (explicit) or ``harness-default``."""
    if text == MAX_TOKENS_HARNESS_DEFAULT:
        return text
    value = bounded_int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1 or {MAX_TOKENS_HARNESS_DEFAULT}")
    return value


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "run",
        parents=[shared],
        help="live capture through a backend worker (scripted or real model; --dry-run prints the plan)",
        description="Execute a live backend and capture raw evidence (N.2.1, N.2.1b). Needs a built backend "
        "environment ('agentprov backends build'); real-model runs also need .env, --containment and consent.",
        allow_abbrev=False,
    )
    p.set_defaults(command="run", handler=run_run, feedback=True)
    add_run_options(p, shared)


#: D-701: the run options ``agentprov estimate`` leaves out (what a dry plan cannot use, or the run's own outputs).
ESTIMATE_OMITS: Final = frozenset({
    "--preflight-only", "--dry-run", "--plan-json", "--catalogue", "--keep-staging", "--skip-prov-conformance",
    "--i-consent-to-api-costs", "--i-consent-to-local-run",  # the latter: D-726 (live pilot), when it lands
    "--preset", "--m5ultra", "--model-dir", "--model-size-gb", "--active-params-b", "--context-tokens",
    "--kv-gb-per-trace", "--server-max-concurrency", "--tune-jobs", "--tune-out",
})  # fmt: skip


def add_run_options(p: argparse.ArgumentParser, shared: argparse.ArgumentParser, *, estimate: bool = False) -> None:
    """The options of ``run`` (and, with ``estimate``, of ``agentprov estimate``: all but :data:`ESTIMATE_OMITS`)."""

    def group(title: str) -> Any:
        real = p.add_argument_group(title)
        return _OmittingGroup(real) if estimate else real

    p.add_argument("source", metavar="SOURCE", help="live source: " + _or_list(live_sources()))
    p.add_argument("--corpus", metavar="DIR", help="working corpus directory")
    name = p.add_mutually_exclusive_group()
    name.add_argument("--campaign", metavar="NAME", help="corpus id <source>-live-<NAME>")
    name.add_argument("--corpus-id", metavar="ID")
    cells = group("cells (exclusive with --plan)")
    cells.add_argument("--plan", metavar="PLAN.toml", help="committed run plan")
    cells.add_argument("--spec", metavar="SPEC.toml", help="corpus spec with [live]")
    cells.add_argument("--suite", metavar="S[,S...]")
    cells.add_argument("--benchmark-version", metavar="V")
    cells.add_argument("--user-tasks", metavar="SPEC")
    cells.add_argument("--attack", metavar="A[,A...]")
    cells.add_argument("--injection-tasks", metavar="SPEC")
    cells.add_argument("--benign", choices=["include", "exclude", "only"])
    cells.add_argument("--defence", "--defense", dest="defence", metavar="NAME")
    ins = group("Inspect plans (an inspect-<benchmark> backend; D-663; exclusive with the cell options)")
    ins.add_argument("--task", metavar="NAME", help="Inspect task (the catalogue lists them), e.g. inspect_evals/agentharm")
    ins.add_argument("--task-param", action="append", metavar="KEY=VALUE",
                     help="a task parameter the catalogue declares (repeatable; VALUE as a TOML scalar or a string)")
    ins.add_argument("--samples", metavar="limit:N|ID[,ID...]", help="the samples: the first N of the split, or ids")
    ins.add_argument("--epochs", type=_int_min(1), metavar="N")
    ins.add_argument("--message-limit", type=_int_min(1), metavar="N", help="per sample (mandatory for Inspect, D-667)")
    ins.add_argument("--token-limit", type=_int_min(1), metavar="N", help="per sample (mandatory for Inspect, D-667)")
    ins.add_argument("--time-limit", type=_int_min(1), metavar="SECONDS", help="per sample (mandatory for Inspect, D-667)")
    ins.add_argument("--max-connections", type=_int_min(1), metavar="N", help="concurrent model calls of one cell")
    ins.add_argument("--cell-size", type=_int_min(1), metavar="N", help="samples per cell (one Inspect eval per cell)")
    ins.add_argument("--judge", action="append", metavar="ROLE=MODEL",
                     help="the model of a judge role of the task's scorer (repeatable; every role is required, D-667); "
                          "judges use the agent's endpoint and key")
    model = group("model (one of: --model, --endpoint with --model-id, --llm-script)")
    model.add_argument("--model", metavar="SHORTHAND", help="endpoint shorthand from endpoints.toml")
    model.add_argument("--endpoint", choices=ENDPOINT_NAMES, metavar="NAME", help=f"explicit endpoint ({', '.join(ENDPOINT_NAMES)})")
    model.add_argument("--model-id", metavar="ID")
    model.add_argument("--defence-endpoint", metavar="NAME",
                       help="the endpoint (endpoints.toml shorthand) a defence calls for its own model or embedding calls "
                            "(D-675; MELON's embeddings); only its key enters the worker")
    model.add_argument("--llm-script", metavar="SCRIPT.json", help="scripted transport: no network, no keys (test_only)")
    model.add_argument("--llm-element", choices=["native", "gateway_compat"])
    model.add_argument("--model-display-name", metavar="NAME")
    model.add_argument("--temperature", type=_finite_float(), metavar="T")
    model.add_argument("--reasoning-effort", metavar="LEVEL")
    model.add_argument("--max-tokens", type=_max_tokens, metavar=f"N|{MAX_TOKENS_HARNESS_DEFAULT}",
                       help=f"Anthropic endpoints (required there): the reply's token cap, stated (N) or the harness "
                            f"default {HARNESS_DEFAULT_MAX_TOKENS} ({MAX_TOKENS_HARNESS_DEFAULT}, recorded as a harness "
                            "policy); AgentDojo's own 1024 is never used silently (D-656)")
    model.add_argument("--temperature-policy", choices=["as-benchmark", "inject"])
    model.add_argument("--allow-text-tool-calls", action="store_true", help="run an endpoint that returns text-encoded tool calls")
    local = group("local model servers (D-691..D-694)")
    local.add_argument("--base-url", metavar="URL", help="a local endpoint's base URL (loopback; overrides .env and the "
                       "registry default; recorded)")
    local.add_argument("--accept-served-model", action="append", metavar="ID",
                       help="a served model id that may differ from the requested one (repeatable; recorded; A12)")
    local.add_argument("--allow-lan-endpoint", action="store_true",
                       help="allow a local endpoint on a literal private LAN address (D-698): prompts and replies leave "
                            "this machine over plain http; keyless; recorded")
    local.add_argument("--no-hash-weights", action="store_true",
                       help="record a local model's weight files by size only (weights_hashed false)")
    ctl = group("control")
    ctl.add_argument("--repeats", type=_int_min(1), metavar="N")
    ctl.add_argument("--max-attempts", type=_int_min(1), metavar="N")
    ctl.add_argument("--retry-inconsistent", action="store_true")
    ctl.add_argument("--allow-mixed-config", action="store_true")
    ctl.add_argument("--limit", type=_int_min(0), metavar="N")
    ctl.add_argument("--canary", type=_int_min(0), metavar="N", help="canary cells (default 10; 0 disables)")
    ctl.add_argument("--preflight-only", action="store_true", help="run the endpoint preflight probes and exit")
    ctl.add_argument("--dry-run", action="store_true", help="resolve and print the plan; run nothing")
    ctl.add_argument("--plan-json", action="store_true",
                     help="with --dry-run: print the expanded plan, one row per cell, as one JSON document on stdout "
                          "(D-651; names and counts only)")
    ctl.add_argument("--catalogue", action="store_true",
                     help="print the suites, user and injection tasks and attacks the backend offers for "
                          "--benchmark-version as one JSON document on stdout (D-652); no model call, nothing written")
    ctl.add_argument("--keep-staging", action="store_true",
                     help="keep each session's staging directory after it is stored (inspection; K.8.5 live_artefacts)")
    ctl.add_argument("--cell-timeout", type=_finite_float(strictly_positive=True), metavar="SECONDS",
                     help="per-cell wall clock before the worker is killed and the session sealed aborted (default 1800)")
    ctl.add_argument("--jobs", type=bounded_int, metavar="N", help="concurrent traces (>= 1; default 1, or computed with a local preset)")
    ctl.add_argument("--start-stagger", type=_finite_float(0.0), metavar="SECONDS", help="spread the first cell start of each worker")
    safety = group("environment and consent")
    safety.add_argument("--env-file", metavar="PATH")
    safety.add_argument("--env-stdin", action="store_true",
                        help="read the endpoint variables as one JSON object from stdin (D-395; for a GUI with a keychain); "
                             "exclusive with --env-file, and the default .env is not read")
    safety.add_argument("--keychain", action="store_true",
                        help="read the selected endpoint's key from the OS keychain (agentprov keys; D-702); exclusive "
                             "with --env-file and --env-stdin, and the default .env is not read")
    safety.add_argument("--allow-custom-endpoint", action="store_true")
    safety.add_argument("--skip-prov-conformance", action="store_true",
                        help="not advisable: skip the W3C PROV conformance check (tier 4) of each session; the corpus is "
                             "marked unvalidated until a full recompute --out NEW, and cannot be sealed (G2c-5)")
    safety.add_argument("--i-consent-to-api-costs", action="store_true")
    safety.add_argument("--i-consent-to-local-run", action="store_true",
                        help="consent for a run against a local model server (D-726); not consent for an API endpoint")
    safety.add_argument("--containment", choices=["sandbox-exec", "dedicated-user", "vm"])
    safety.add_argument("--autodojo-cache", metavar="PATH",
                        help="AutoDojo attack cache copied from the pinned fork (verified against its tree; D.11.3 rule 5)")
    safety.add_argument("--autodojo-variant", metavar="K", help="the cache's variant index (integer >= 0)")
    safety.add_argument("--allow-network", action="store_true",
                        help="let T0 fetch the pinned AutoDojo commit into the fetch cache to verify --autodojo-cache")
    caps = group("API caps (D-725: required for an API endpoint, optional otherwise)")
    caps.add_argument("--max-calls", type=_int_min(1), metavar="N",
                      help="billed model calls of the corpus at most, preflight probes included; a cell starts only if "
                           "its worst case fits")
    caps.add_argument("--max-cost-usd", type=_finite_float(strictly_positive=True), metavar="USD",
                      help="spend of the corpus at most (an upper bound priced from the recorded usage); needs "
                           "--price-in and --price-out")
    caps.add_argument("--price-in", type=_finite_float(0.0), metavar="USD_PER_MTOK",
                      help="USD per million input-side tokens (the highest of input, cache write and cached)")
    caps.add_argument("--price-out", type=_finite_float(0.0), metavar="USD_PER_MTOK",
                      help="USD per million output tokens")
    preset = group("local models and presets (N.2.1a)")
    preset.add_argument("--preset", metavar="NAME", help="host preset from package data (v0.1: m5ultra)")
    preset.add_argument("--m5ultra", action="store_true", help="shorthand for --preset m5ultra")
    preset.add_argument("--model-dir", metavar="PATH", help="read the model's config.json and weight sizes (untrusted input)")
    preset.add_argument("--model-size-gb", type=_finite_float(strictly_positive=True), metavar="GB", help="weight size, decimal gigabytes")
    preset.add_argument("--active-params-b", type=_finite_float(strictly_positive=True), metavar="B", help="active parameters, billions")
    preset.add_argument("--context-tokens", type=_int_min(1), metavar="N")
    preset.add_argument("--kv-gb-per-trace", type=_finite_float(strictly_positive=True), metavar="GB")
    preset.add_argument("--server-max-concurrency", type=_int_min(1), metavar="N", help="the local server's concurrent-request limit")
    preset.add_argument("--tune-jobs", metavar="N[,N...]",
                        help="the concurrency sweep (N.2.1a(4), D-820): the same cell sample at each --jobs value, one "
                             "working corpus per value, and a report recommending the smallest N within 90 %% of the "
                             "peak traces per hour with no timeouts (a local endpoint only)")
    preset.add_argument("--tune-out", metavar="DIR",
                        help="the sweep's folder (default $AGENTPROV_HOME/calibration/tune-jobs-<UTC stamp>)")
    # D-652: the run command's own destinations (not the shared global options), for the --catalogue exclusivity check
    shared_dests = {a.dest for a in shared._actions}  # noqa: SLF001 - argparse exposes no public action list
    p.set_defaults(_run_dests=frozenset(a.dest for a in p._actions if a.dest not in shared_dests))  # noqa: SLF001


class _OmittingGroup:
    """An argument group that skips the options of :data:`ESTIMATE_OMITS` (``agentprov estimate``, D-701)."""

    def __init__(self, group: Any) -> None:
        self.group = group

    def add_argument(self, *names: str, **kwargs: Any) -> Any:
        if names and names[0] in ESTIMATE_OMITS:
            return None
        return self.group.add_argument(*names, **kwargs)

    def add_mutually_exclusive_group(self, **kwargs: Any) -> Any:
        return self.group.add_mutually_exclusive_group(**kwargs)


# --------------------------------------------------------------------------------------------------------------
# Validation (N.2.1, N.1.10(1), N.2.1a)
# --------------------------------------------------------------------------------------------------------------


def _preset_name(args: argparse.Namespace) -> str | None:
    if args.m5ultra and args.preset not in (None, "m5ultra"):
        raise CliUsageError("agentprov run: --m5ultra conflicts with --preset " + safe_text(args.preset, 40))
    return "m5ultra" if args.m5ultra else args.preset


def host_max_jobs(profile: HostProfile) -> int | None:
    """The host maximum of concurrent backend workers (N.1.10(1)): usable memory divided by the per-worker memory
    budget of the D-7 host constants. ``None`` when the host's memory is unknown (no bound can be computed).
    """
    from agentprov.host import USABLE_MEMORY_FRACTION, constants_for

    if not profile.memory_bytes:
        return None
    budget = constants_for(profile).rss_cap_bytes
    return max(1, int(USABLE_MEMORY_FRACTION * profile.memory_bytes) // budget)


def check_jobs(jobs: int | None, profile: HostProfile) -> None:
    """``--jobs`` must be >= 1 (0 is a usage error for ``run``) and at most the host maximum, which the message names."""
    if jobs is None:
        return
    if jobs < 1:
        raise CliUsageError(
            f"agentprov run: --jobs must be >= 1 (got {jobs}); a CPU count says nothing about API-bound work"
        )
    maximum = host_max_jobs(profile)
    if maximum is not None and jobs > maximum:
        raise CliUsageError(
            f"agentprov run: --jobs {jobs} exceeds this host's maximum of {maximum} concurrent traces "
            "(usable memory divided by the per-worker memory budget); it is never clamped silently"
        )


def _check_model_selection(args: argparse.Namespace, preset: str | None) -> None:
    selectors = [bool(args.model), bool(args.endpoint), bool(args.llm_script)]
    if sum(selectors) > 1:
        raise CliUsageError("agentprov run: --model, --endpoint and --llm-script are mutually exclusive")
    if args.endpoint and not args.model_id:
        raise CliUsageError("agentprov run: --endpoint needs --model-id")
    if args.model:
        _check_model_shorthand(args.model)
    if args.llm_script and not os.path.isfile(args.llm_script):
        raise CliUsageError("agentprov run: --llm-script does not name a file")
    if args.llm_script and preset and not getattr(args, "tune_jobs", None):  # a scripted sweep is a test (test_only)
        raise CliUsageError("agentprov run: --llm-script (no network) cannot be combined with a host preset")
    local = _local_name(args) is not None
    for flag, given in (("--base-url", getattr(args, "base_url", None)),
                        ("--no-hash-weights", getattr(args, "no_hash_weights", False)),
                        ("--allow-lan-endpoint", getattr(args, "allow_lan_endpoint", False))):
        if given and not local:
            raise CliUsageError(f"agentprov run: {flag} goes with a local endpoint ({', '.join(LOCAL_ENDPOINT_NAMES)})")


def _local_name(args: argparse.Namespace) -> str | None:
    """The local endpoint shorthand the command line selects (``--endpoint local`` is ``ollama``), or ``None``."""
    name = args.model or {"local": "ollama"}.get(args.endpoint or "", args.endpoint)
    return name if name in LOCAL_ENDPOINT_NAMES else None


def _check_model_shorthand(name: str) -> None:
    try:
        from agentprov_capture.endpoints import load_endpoints

        known = sorted(load_endpoints())
    except Exception:  # noqa: BLE001 - the endpoint registry is package data; without it the name cannot be checked
        return
    if name not in known:
        close = difflib.get_close_matches(name, known, n=2)
        hint = f"; did you mean {' or '.join(close)}?" if close else ""
        raise CliUsageError(f"agentprov run: unknown --model shorthand {safe_text(name, 40)!r}; known: {', '.join(known)}{hint}")


def _check_run_context(args: argparse.Namespace) -> None:
    """The required pieces of a real run (N.2.1). A dry run of the preset plan does not need them."""
    if args.corpus is None:
        raise CliUsageError("agentprov run: --corpus DIR is required")
    if not (args.campaign or args.corpus_id or args.spec):
        raise CliUsageError("agentprov run: one of --campaign, --corpus-id or --spec is required")
    has_cells = any(getattr(args, name) not in (None, False) for name in _CELL_OPTIONS)
    if args.plan and (has_cells or args.spec):
        raise CliUsageError("agentprov run: --plan excludes --spec and the cell options")
    if not (args.plan or args.spec or args.suite or getattr(args, "task", None)):
        raise CliUsageError("agentprov run: one of --plan, --spec, --suite or (an Inspect backend) --task is required")
    if not (args.model or args.endpoint or args.llm_script or args.m5ultra or args.preset):
        raise CliUsageError("agentprov run: one of --model, --endpoint with --model-id, --llm-script or --preset is required")
    attacks = [a for a in (args.attack or "").split(",") if a]
    if "autodojo" in attacks and not (args.autodojo_cache and args.autodojo_variant is not None):
        raise CliUsageError("agentprov run: --attack autodojo needs --autodojo-cache and --autodojo-variant")
    if (args.autodojo_cache or args.autodojo_variant is not None) and not ("autodojo" in attacks or args.plan):
        raise CliUsageError("agentprov run: --autodojo-cache and --autodojo-variant belong to --attack autodojo")
    if "autodojo" in attacks and len(attacks) > 1:
        raise CliUsageError("agentprov run: run --attack autodojo on its own: the cache and variant become the plan's "
                            "attack_params, which every attacked cell records (D.10.10 item 19)")


def _script_api(path: str) -> str:
    """The wire format a ``--llm-script`` file declares (its top-level ``api``; ``openai_chat`` when absent). The file
    is read bounded and strictly; a malformed one is left for the worker's own loader to refuse."""
    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    try:
        with open(path, "rb") as handle:
            data = handle.read(SCRIPT_MAX_BYTES + 1)
        document = strict_json_loads(data) if len(data) <= SCRIPT_MAX_BYTES else None
    except (OSError, IngestError):
        return "openai_chat"
    api = document.get("api") if isinstance(document, dict) else None
    return api if isinstance(api, str) else "openai_chat"


def selected_provider(args: argparse.Namespace) -> str:
    """``anthropic`` when the selected endpoint (or ``--llm-script``) speaks the Anthropic Messages API, else
    ``openai_compatible`` (D-656; the registry's ``api``)."""
    if args.llm_script:
        return "anthropic" if _script_api(args.llm_script) == "anthropic_messages" else "openai_compatible"
    name = args.model or {"local": "ollama"}.get(args.endpoint or "", args.endpoint)
    if not name:
        return "openai_compatible"
    try:
        from agentprov_capture.endpoints import get_endpoint

        return "anthropic" if get_endpoint(name).api == "anthropic_messages" else "openai_compatible"
    except Exception:  # noqa: BLE001 - an unknown shorthand is refused by _check_model_shorthand
        return "openai_compatible"


def _check_provider_options(args: argparse.Namespace) -> None:
    """D-656: the options the Anthropic element takes. It needs ``--max-tokens`` (stated or ``harness-default``); it
    sends no effort and has no gateway port. ``--max-tokens`` belongs to Anthropic endpoints only."""
    if selected_provider(args) == "anthropic":
        if args.max_tokens is None:
            raise CliUsageError(
                "agentprov run: an Anthropic run needs --max-tokens: state the cap (--max-tokens N) or take the harness "
                f"default (--max-tokens {MAX_TOKENS_HARNESS_DEFAULT}, i.e. {HARNESS_DEFAULT_MAX_TOKENS}, recorded as a "
                "harness policy); AgentDojo's own 1024 is not used silently")
        if args.reasoning_effort:
            raise CliUsageError("agentprov run: --reasoning-effort: AgentDojo's Anthropic element sends no effort; the "
                                "model's default effort applies (not transmitted, recorded as such)")
        if args.llm_element == "gateway_compat":
            raise CliUsageError("agentprov run: --llm-element gateway_compat is the OpenAI-format port; an Anthropic run "
                                "uses the native element")
    elif args.max_tokens is not None:
        raise CliUsageError("agentprov run: --max-tokens applies to Anthropic endpoints only (the OpenAI-format "
                            "element takes no cap)")


def _anthropic_params(args: argparse.Namespace) -> dict[str, Any]:
    if args.max_tokens == MAX_TOKENS_HARNESS_DEFAULT:
        return {"max_tokens": HARNESS_DEFAULT_MAX_TOKENS, "max_tokens_mode": "harness_default"}
    return {"max_tokens": args.max_tokens, "max_tokens_mode": "explicit"}


def validate_run_args(args: argparse.Namespace, profile_loader: Any) -> str | None:
    """Every usage rule of N.2.1 / N.1.10(1) / N.2.1a that does not need the plan. Returns the preset name or ``None``."""
    preset = _preset_name(args)
    _check_model_selection(args, preset)
    _check_provider_options(args)
    if preset is None:
        local = _local_name(args) is not None  # D-692: --model-dir names a local model's files
        used = [flag for dest, flag in _PRESET_ONLY_FLAGS if getattr(args, dest, None) is not None
                and not (local and dest == "model_dir")]
        if used:
            raise CliUsageError(f"agentprov run: {', '.join(used)} need --preset (model-aware concurrency, N.2.1a)")
    check_jobs(args.jobs, profile_loader())
    return preset


# --------------------------------------------------------------------------------------------------------------
# Dry run of the preset plan (N.2.1a(3))
# --------------------------------------------------------------------------------------------------------------


def _gib(value: int) -> str:
    return f"{value / 1024**3:.2f} GiB"


def _input_line(item: Any) -> str:
    if item.unit == "bytes" and isinstance(item.value, int):
        shown = _gib(item.value)
    else:
        shown = "unknown" if item.value is None else f"{item.value} {item.unit}".strip()
    note = f"  ({safe_text(item.note, 100)})" if item.note else ""
    return f"    {item.name:<26} {shown:<22} source={item.source}{note}"


def plan_lines(plan: ConcurrencyPlan, *, preset: Any, stagger_s: float, stagger_source: str) -> list[str]:
    lines = [
        f"preset {plan.preset_name} v{plan.preset_version}: endpoint {preset.endpoint}, "
        f"request timeout {preset.request_timeout_s:g} s, start stagger {stagger_s:g} s ({stagger_source})",
        f"concurrency: jobs = {plan.jobs} ({plan.jobs_source})",
        f"  J_compute = {plan.j_compute}   J_memory = {plan.j_memory}   J_server = {plan.j_server}",
        f"  binding term: {plan.binding}" + (f" (tied: {', '.join(plan.binding_all)})" if len(plan.binding_all) > 1 else ""),
        f"  M_budget {_gib(plan.m_budget_bytes)}, weights {_gib(plan.weights_bytes)}, reserve {_gib(plan.reserve_bytes)}, "
        f"KV per trace {_gib(plan.kv_trace_bytes)}",
        "  inputs:",
        *(_input_line(i) for i in plan.inputs),
    ]
    lines.extend(f"  warning: {w}" for w in plan.warnings)
    return lines


def model_settings(endpoint: str, model_id: str | None) -> tuple[dict[str, Any], str | None]:
    """D-828: the user's stored facts of ``endpoint``'s ``model_id`` (Settings › Local models) and their key prefix;
    ``({}, None)`` without a model id or a stored fact."""
    if not model_id:
        return {}, None
    from agentprov import settings

    stored = settings.local_model(endpoint, model_id)
    return (stored, f"local_models.{endpoint}.{model_id}.") if stored else ({}, None)


def setting_model_dir(stored: Mapping[str, Any], label: str | None) -> str | None:
    """The stored model folder, or ``None``; a folder that is no longer a directory is a usage error naming the key."""
    folder = stored.get("model_dir")
    if not isinstance(folder, str):
        return None
    if not os.path.isdir(folder):
        raise CliUsageError(f"agentprov run: the setting {label}model_dir is not a readable directory (fix it in "
                            "Settings › Local models, or give --model-dir)")
    return folder


def tune_plan_lines(args: argparse.Namespace, preset: Any, facts: Any, profile: HostProfile) -> list[str]:
    """``--tune-jobs --dry-run`` (D-820): each arm, whether it would run, and a rough time (§7 of the design note)."""
    import math

    from agentprov.presets import local_concurrency

    cells = 24 if getattr(args, "tune_default_sample", False) else None
    row = preset.cell_seconds_for(facts.active_params_b.value)
    per_cell, basis = (row.p50 * row.jobs, f"measured ({row.source})") if row is not None else (45.0, "a default of "
                                                                                                 "45 s per cell, unmeasured")
    per_arm = f"{cells} cells" if cells is not None else "the plan's cells"
    lines = [f"sweep: arms {','.join(map(str, args.tune_values))}; {per_arm} per arm; one warm-up cell first"]
    total = 0.0
    for n in args.tune_values:
        plan = local_concurrency(preset, facts, host=profile, server_max_concurrency=args.server_max_concurrency,
                                 jobs_override=n)
        state = "skipped (above J_memory)" if n > plan.j_memory else \
            "runs, above the server limit (requests queue)" if n > plan.j_server else "runs"
        lines.append(f"  arm jobs={n}: {state}")
        if cells is not None and n <= plan.j_memory:
            total += math.ceil(cells / n) * per_cell
    if cells is not None:
        lines.append(f"  time, if throughput scaled perfectly: about {total / 60:.0f} min ({basis}); less scaling is "
                     "longer")
    return lines


def preset_facts(args: argparse.Namespace, endpoint: str, model_id: str | None) -> tuple[Any, dict[str, Any], str | None]:
    """The model facts a preset plan uses (N.2.1a(3)), with the stored settings and their key prefix (D-828):
    flag > setting > model folder > preset."""
    from agentprov.presets import ModelFacts, model_facts_from_dir

    stored, label = model_settings(endpoint, model_id)
    model_dir = args.model_dir or setting_model_dir(stored, label)
    facts = model_facts_from_dir(model_dir) if model_dir else ModelFacts()
    facts = facts.with_flags(
        model_size_gb=stored.get("model_size_gb"),
        active_params_b=stored.get("active_params_b"),
        context_tokens=stored.get("context_tokens"),
        kv_gb_per_trace=stored.get("kv_gb_per_trace"),
        source="settings", label=label or "",
    ).with_flags(
        model_size_gb=args.model_size_gb,
        active_params_b=args.active_params_b,
        context_tokens=args.context_tokens,
        kv_gb_per_trace=args.kv_gb_per_trace,
    )
    return facts, stored, label


def dry_run_plan(args: argparse.Namespace, preset_name: str, profile: HostProfile) -> CommandResult:
    from agentprov.presets import check_host, load_preset, local_concurrency

    preset = load_preset(preset_name)
    endpoint = args.model or {"local": "ollama"}.get(args.endpoint, args.endpoint) or preset.endpoint
    facts, stored, label = preset_facts(args, str(endpoint), args.model_id)
    plan = local_concurrency(
        preset, facts, host=profile, server_max_concurrency=args.server_max_concurrency, jobs_override=args.jobs
    )
    check_jobs(plan.jobs, profile)
    mismatches = check_host(preset, profile)
    if args.start_stagger is not None:
        stagger, source = args.start_stagger, "flag"
    else:
        stagger, source = preset.start_stagger_per_worker_s * plan.jobs, "preset"
    result = CommandResult(dry_run=True)
    if stored:
        used = sorted(k for k in stored if k != "model_dir" or not args.model_dir)
        result.notices.append(f"model facts from the settings {label}{{{','.join(used)}}} (D-828; a flag overrides)")
    result.counters = {
        "jobs": plan.jobs,
        "j_compute": plan.j_compute,
        "j_memory": plan.j_memory,
        "j_server": plan.j_server,
    }
    result.notices.append(f"concurrency binding term: {plan.binding}")
    for mismatch in mismatches:
        result.notices.append(f"preset host mismatch (recorded, not refused): {mismatch.message()}")
    for warning in plan.warnings:
        result.notices.append(f"warning: {warning}")
    if not preset.calibrated:
        result.notices.append(f"dry run covered the preset and concurrency plan only; {preset.name} v{preset.version} "
                              "is not calibrated, so a real run exits 5 until a --tune-jobs sweep measures it")
    for line in plan_lines(plan, preset=preset, stagger_s=stagger, stagger_source=source):
        result.output(line)
    if getattr(args, "tune_jobs", None):
        for line in tune_plan_lines(args, preset, facts, profile):
            result.output(line)
    for mismatch in mismatches:
        result.error(f"agentprov: warning: {mismatch.message()} (recorded, not refused)")
    return result


# --------------------------------------------------------------------------------------------------------------
# Live runs (N.2.1; N.2.1b)
# --------------------------------------------------------------------------------------------------------------

#: The working-directory label of the scripted-transport file inside each session directory (not under ``raw/``,
#: so the worker never reports it; T0 does not count it as an unreported file).
SCRIPT_LABEL: Final = "llm-script.json"
SCRIPT_MAX_BYTES: Final = 4 * 1024 * 1024
DEFAULT_CELL_TIMEOUT_S: Final = 1800.0
DEFAULT_CANARY: Final = 10
DEFAULT_MAX_ATTEMPTS: Final = 3
#: Attacks whose payload names the model (``agentprov_backend.attacks.PIPELINE_NAMED_ATTACKS``; kept equal by
#: ``tests/cli/test_live_units.py``): used for a pre-consent hint only.
MODEL_NAMING_ATTACKS: Final = frozenset({
    "important_instructions", "important_instructions_no_user_name", "important_instructions_wrong_user_name",
    "tool_knowledge", "dos", "swearwords_dos", "captcha_dos", "offensive_email_dos", "felony_dos", "autodojo",
})
#: Defences that replace pipeline components: typed refusal (N.2.1 ``--defence``).
REPLACING_DEFENCES: Final = ("progent", "drift", "camel", "camel_nopolicy")
_CORPUS_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_PLAN_SHA256 = re.compile(r"[0-9a-f]{64}")  # the worker's plan digest, checked before it is ever printed


class LiveRefused(AgentProvError):
    """A live-run guard refused (N.1.3 exit 4): consent, containment, endpoint rules, mixed configuration."""

    code = "cli.refused.run"
    exit_code = 4


def _inspect_cell_calls(backend: str, plan_doc: Mapping[str, Any], agent: Mapping[str, Any], identity: Any) -> int:
    """D-740: the billed-call bound of one Inspect cell under the D-725 caps, from T0's own plan document (never the
    worker's reply): ``n x E x ((M - 1) x (1 + a) + j) x (1 + K)`` for a cell of at most ``n`` samples (``cell_size``),
    ``E`` epochs and message limit ``M``. A sample makes at most ``M - 1`` agent calls (Inspect refuses a generate at
    the limit), ``a`` judge calls per agent call and ``j`` per sample (the task's :class:`InspectCallBound`, valid for
    its pinned code only), and every call is at most ``1 + K`` billed responses (``envs.INSPECT_MAX_RETRIES``).
    Refused (``cli.refused.api_caps``) when the task has no bound for the environment's task code, or a judge uses
    another model than the agent (the caps have one price pair)."""
    from agentprov.cli.live import envs

    inspect = plan_doc.get("inspect") or {}
    task = str(inspect.get("task"))
    bound = envs.backend_kind(backend).call_bounds.get(task)

    def refuse(why: str) -> LiveRefused:
        return LiveRefused(f"the API call and cost caps (D-725) cannot bound this Inspect cell: {why} (D-740)",
                           code="cli.refused.api_caps")

    if bound is None:
        raise refuse(f"no call bound is recorded for the task {safe_text(task, 80)}")
    if identity.task_files.get(bound.task_dir) != bound.task_files_sha256:
        raise refuse(f"the environment's {bound.task_dir} code is not the code its call bound was derived from")
    model = agent.get("model_requested")
    others = sorted(str(role) for role, judge in (plan_doc.get("judges") or {}).items()
                    if not isinstance(judge, Mapping) or judge.get("model_requested") != model)
    if others:
        raise refuse("every judge must use the agent's model, since the caps have one price pair (judges "
                     + ", ".join(safe_text(r, 64) for r in others) + " do not)")
    def positive(name: str, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise refuse(f"the plan gives no {name}")
        return value

    message_limit = positive("message_limit", (inspect.get("limits") or {}).get("message_limit"))
    epochs, cell_size = positive("epochs", inspect.get("epochs", 1)), positive("cell_size", inspect.get("cell_size"))
    per_sample = (message_limit - 1) * (1 + bound.per_agent_call) + bound.per_sample
    return cell_size * epochs * per_sample * (1 + envs.INSPECT_MAX_RETRIES)


def _check_inspect_endpoint(backend: str, agent: Mapping[str, Any]) -> None:
    """D-741: an Inspect worker reaches the agent and every judge through Inspect's OpenAI-compatible provider
    (``agentprov_backend_inspect.models``), so a real-model Inspect run needs an endpoint that speaks the OpenAI chat
    format; an ``anthropic_messages`` endpoint is refused before consent, the plan or any spawn."""
    if backend.startswith("inspect-") and agent.get("provider") != "openai_compatible":
        raise LiveRefused("an Inspect backend reaches every model through Inspect's OpenAI-compatible provider, so its "
                          "endpoint must speak the OpenAI chat format (D-741)", code="cli.refused.endpoint")


class LiveEnvironmentError(AgentProvError):
    """A live-run pre-flight condition of the environment (N.1.3 exit 3)."""

    code = "cli.environment.run"
    exit_code = 3


def _unsupported(what: str, label: str, lines: tuple[str, ...]) -> UnsupportedCapability:
    return UnsupportedCapability(
        f"{what} is not available in this build",
        refusal=Refusal(id=label, mode="run", status=what, lines=(*lines, "Nothing was started and nothing was written.")),
        code="cli.unsupported.run",
    )


def live_sources() -> list[str]:
    """The sources with a live part and a backend in this build (F-16: from the registry, so the help cannot drift)."""
    from agentprov.adapters.registry import BACKENDS, REGISTRY

    return sorted(r.source_id for r in REGISTRY
                  if any(c.live_status is not None and c.backend in BACKENDS for c in r.capabilities))


def _or_list(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1] if names else "none"


def _live_capability(source: str, result: CommandResult, *, scripted: bool) -> Any:
    """The status gate for ``run`` (N.3): the source's live part. A ``planned`` live part admits scripted runs only
    (N.2.1b(1)): they are ``test_only``, synthetic and never released, so they make no claim; the gates are such runs."""
    from agentprov.adapters.registry import BACKENDS, REGISTRY

    registration = next((r for r in REGISTRY if r.source_id == source), None)
    if registration is None:
        from agentprov.cli.import_ import SPEC_SOURCE_IDS

        if source in SPEC_SOURCE_IDS:
            raise _unsupported("not registered in this build", source, ("This source has no live backend in this build.",))
        known = live_sources()
        close = difflib.get_close_matches(source, known, n=2)
        raise CliUsageError(f"agentprov run: unknown source {safe_text(source, 80)!r}"
                            + (f"; did you mean {' or '.join(close)}?" if close else f"; live sources: {', '.join(known)}"))
    capability = next((c for c in registration.capabilities if c.live_status is not None and c.backend), None)
    if capability is None or capability.backend not in BACKENDS:
        raise _unsupported("no live capability", source, ("The source has no live part with a backend in this build.",))
    status = capability.live_status
    label = f"{source} · {capability.part}"
    if status in ("planned", "not_possible"):
        if not scripted or status == "not_possible":
            raise _unsupported(f"live status {status}", source, (
                f"{label} is {status}: only scripted runs (--llm-script; test_only, synthetic) are allowed until its "
                "gates pass.",
            ))
        result.notices.append(f"{label} is {status}: scripted run admitted as a test_only gate run (N.2.1b)")
    elif capability.caveat:
        result.notices.append(f"{label} ({status}): {safe_text(capability.caveat, 400)}")
    return capability


ENV_STDIN_MAX_BYTES: Final = 64 * 1024
#: The variable names ``--env-stdin`` accepts besides each registry endpoint's own (``endpoints.toml``).
ENV_STDIN_EXTRA_NAMES: Final = ("REASONING_EFFORT",)


def _env_stdin_names() -> frozenset[str]:
    from agentprov_capture.endpoints import load_endpoints

    names = set(ENV_STDIN_EXTRA_NAMES)
    for endpoint in load_endpoints().values():
        names.update(n for n in (endpoint.api_key_env, endpoint.base_url_env, endpoint.model_env) if n)
    return frozenset(names)


def _read_env_stdin(args: argparse.Namespace, stream: Any = None) -> dict[str, str]:
    """D-395: the endpoint variables as one strict JSON object of strings on stdin (at most 64 KiB), read before any
    other step. Only names ``endpoints.toml`` declares are accepted; every value is registered for redaction at once.
    A refusal never shows a value. Exclusive with ``--env-file``; the default ``.env`` is then not read."""
    import sys

    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    if args.env_file:
        raise CliUsageError("agentprov run: --env-stdin and --env-file are exclusive")
    if getattr(args, "keychain", False):
        raise CliUsageError("agentprov run: --keychain, --env-stdin and --env-file are exclusive")
    if args.llm_script:
        raise CliUsageError("agentprov run: --env-stdin carries the variables of a real endpoint; a scripted run needs none")
    source = stream if stream is not None else getattr(sys.stdin, "buffer", None)
    if source is None:
        raise CliUsageError("agentprov run: --env-stdin needs a readable stdin")
    data = source.read(ENV_STDIN_MAX_BYTES + 1)
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) > ENV_STDIN_MAX_BYTES:
        raise CliUsageError("agentprov run: --env-stdin: the object is larger than 64 KiB")
    try:
        document = strict_json_loads(data.strip())
    except IngestError as exc:
        raise CliUsageError(f"agentprov run: --env-stdin: not one strict JSON object ({exc.code})") from None
    if not isinstance(document, dict):
        raise CliUsageError("agentprov run: --env-stdin: not one strict JSON object")
    allowed = _env_stdin_names()
    values: dict[str, str] = {}
    for name, value in document.items():
        if not isinstance(value, str):
            raise CliUsageError(f"agentprov run: --env-stdin: {safe_text(name, 60)} is not a string")
        if name.endswith("_API_KEY") or name not in allowed:
            register_secret(value)  # registered before any message could name the variable
        if name not in allowed:
            raise CliUsageError(f"agentprov run: --env-stdin: {safe_text(name, 60)} is not a variable of endpoints.toml")
        values[name] = value
    return values


def _check_keychain_args(args: argparse.Namespace) -> str:
    """``--keychain``'s usage rules (exit 2), checked before any other step; the endpoint shorthand."""
    if args.env_file or args.env_stdin:
        raise CliUsageError("agentprov run: --keychain, --env-stdin and --env-file are exclusive")
    if args.llm_script:
        raise CliUsageError("agentprov run: --keychain reads the key of a real endpoint; a scripted run needs none")
    name = args.model or {"local": "ollama"}.get(args.endpoint, args.endpoint)
    if not name:
        raise CliUsageError("agentprov run: --keychain needs --model or --endpoint")
    return str(name)


def _read_keychain(args: argparse.Namespace) -> dict[str, str]:
    """D-702: the selected endpoint's key variable from the OS keychain (the keychain helper process, as
    ``agentprov keys``), registered for redaction at once. Exclusive with ``--env-file`` and ``--env-stdin``; a scripted
    run needs no key; a missing key is exit 3 naming the variable (never a value)."""
    from agentprov.keys import KeychainError, read

    name = _check_keychain_args(args)
    from agentprov_capture.endpoints import get_endpoint

    try:
        endpoint = get_endpoint(name)
    except Exception:  # noqa: BLE001 - an unknown shorthand is reported by the model checks with its own message
        return {}
    if not endpoint.api_key_env:
        return {}  # a local endpoint needs no key
    try:
        values = read([endpoint.api_key_env])
    except KeychainError as exc:
        if exc.code == "keychain.missing" and endpoint.local:
            return {}  # D-827: a local entry's key is optional; _real_agent says that none is sent
        if exc.code == "keychain.missing":
            raise LiveEnvironmentError(f"{endpoint.api_key_env} is not in the keychain (agentprov keys set "
                                       f"{endpoint.api_key_env})", code="cli.environment.credential") from None
        raise LiveEnvironmentError(f"the keychain cannot be read ({exc.code})", code="cli.environment.keychain") from None
    for value in values.values():
        register_secret(value)
    return values


def _default_key_values(args: argparse.Namespace, root: Path, result: CommandResult) -> dict[str, str]:
    """D-702 as amended 2026-10-22 (user rule: the OS keychain is the source of truth for keys, then ``.env``): with no
    ``--keychain``, ``--env-file`` or ``--env-stdin``, the selected endpoint's key comes from the keychain when it holds
    it, else from the repository's ``.env``; the other variables (model id, base URL, effort) still come from ``.env``
    when it exists. A keychain that is unavailable or does not hold the key is a notice, never an error here (the
    missing-key error names both places). No value is printed or logged; a keychain value is registered at once."""
    from agentprov.keys import KeychainError, read

    name = _endpoint_key_name(args)
    from_keychain: dict[str, str] = {}
    if name is not None:
        try:
            from_keychain = read([name])
        except KeychainError as exc:
            result.notices.append(f"key: {name} not read from the OS keychain ({exc.code}); looking in .env")
    for value in from_keychain.values():
        register_secret(value)
    try:
        values = _read_env_file(args, root)  # {} when the repository has no .env (a worktree, say)
    except LiveEnvironmentError:
        if not from_keychain:
            raise
        values = {}
        result.notices.append(".env not read: the 'live' extra (python-dotenv) is not installed")
    if from_keychain:
        values.update(from_keychain)
        result.notices.append(f"key: {name} from the OS keychain (the source of truth; D-702)")
    elif name is not None and name in values:
        result.notices.append(f"key: {name} from .env (not in the OS keychain)")
    return values


def _endpoint_key_name(args: argparse.Namespace) -> str | None:
    """The selected real endpoint's key variable (``None``: scripted, local or unknown endpoint)."""
    if args.llm_script:
        return None
    name = args.model or {"local": "ollama"}.get(args.endpoint, args.endpoint)
    if not name:
        return None
    from agentprov_capture.endpoints import get_endpoint

    try:
        return get_endpoint(name).api_key_env
    except Exception:  # noqa: BLE001 - an unknown shorthand is reported by the model checks with its own message
        return None


def _read_env_file(args: argparse.Namespace, root: Path) -> dict[str, str]:
    """``.env`` through python-dotenv (``live`` extra; ``dotenv_values`` into a private mapping, N.1.11(2))."""
    import importlib

    path = Path(args.env_file) if args.env_file else root / ".env"
    if not path.is_file():
        if args.env_file:
            raise CliUsageError("agentprov run: --env-file does not name a file")
        return {}
    try:
        dotenv_values = importlib.import_module("dotenv").dotenv_values  # the `live` extra (M.5.3)
    except ImportError:
        raise LiveEnvironmentError("a real-model run needs the 'live' extra (python-dotenv); run: uv sync --extra live",
                                   code="cli.environment.live_extra") from None
    return {k: v for k, v in dotenv_values(path).items() if isinstance(v, str)}


def _real_agent(args: argparse.Namespace, values: Mapping[str, str], result: CommandResult) -> tuple[dict[str, Any], dict[str, str]]:
    """``AgentConfig`` (no secret) and the key variables passed to T2 for a real endpoint (N.1.11(2); G.9.2)."""
    from agentprov_capture.endpoints import EndpointError, check_base_url, get_endpoint

    name = args.model or {"local": "ollama"}.get(args.endpoint, args.endpoint)
    endpoint = get_endpoint(name)
    model_id = args.model_id or (values.get(endpoint.model_env) if endpoint.model_env else None)
    if not model_id and not endpoint.local:  # a local server's served models are listed and picked from (D-691)
        raise LiveEnvironmentError(f"no model id: give --model-id or set {endpoint.model_env or 'the model variable'} in .env "
                                   "(there are no default model ids)", code="cli.environment.model_id")
    keys: dict[str, str] = {}
    api_key_env = endpoint.api_key_env
    if api_key_env and endpoint.local:  # D-827: optional; set, it is sent to the loopback server only
        value = values.get(api_key_env)
        if not value:
            result.notices.append(f"key: {api_key_env} is not set: no key is sent to the local server (optional, "
                                  "D-827)")
            api_key_env = None  # keyless, as before D-827 (so the configuration digest is unchanged)
        else:
            register_secret(value)
            keys[api_key_env] = value
    elif api_key_env:
        value = values.get(api_key_env)
        if not value:
            explicit = any(getattr(args, name, None) for name in ("env_file", "env_stdin", "keychain"))
            where = ("is not in the given source" if explicit else
                     f"is in neither the OS keychain (agentprov keys set {endpoint.api_key_env}) nor .env")
            raise LiveEnvironmentError(f"the credential variable {endpoint.api_key_env} {where}",
                                       code="cli.environment.credential")
        register_secret(value)
        keys[api_key_env] = value
    lan = False
    base_url = (getattr(args, "base_url", None) or (values.get(endpoint.base_url_env) if endpoint.base_url_env else None)
                or None)
    if base_url is None and endpoint.local:  # D-699: --base-url > .env > settings > registry
        from agentprov.cli.live.localmodels import configured_base_url

        base_url, source = configured_base_url(endpoint)
        if source == "settings":
            result.notices.append(f"base URL from the setting endpoints.{endpoint.name}.base_url (agentprov settings)")
    base_url = base_url or endpoint.base_url
    try:
        if endpoint.local:  # D-691: any loopback host and port; a LAN host needs the opt-in (D-698)
            from agentprov_capture.endpoints import is_loopback_host, validate_base_url

            allow_lan = bool(getattr(args, "allow_lan_endpoint", False))
            if not is_loopback_host(validate_base_url(base_url, allow_lan=allow_lan)):
                if not allow_lan:
                    raise EndpointError("endpoint.url.not_loopback", "a local endpoint's base URL must be loopback")
                lan = True
                result.notices.append("LAN endpoint (--allow-lan-endpoint): prompts and replies leave this machine over "
                                      "plain http to a private address (recorded)")
            custom = False
            if base_url != endpoint.base_url:
                result.notices.append("local endpoint at a base URL other than the registry default (recorded)")
        else:
            custom = check_base_url(endpoint, base_url, allow_custom=bool(args.allow_custom_endpoint))
    except EndpointError as exc:
        hint = "; a local endpoint must be loopback, or a private LAN address with --allow-lan-endpoint (D-698)" \
            if endpoint.local else ""
        raise LiveRefused(f"the base URL is refused ({exc.code}); see G.9.2{hint}", code="cli.refused.endpoint") from None
    if custom:
        result.notices.append("--allow-custom-endpoint: the base URL host differs from the registry (recorded)")
    if lan and keys:  # D-827, as the worker's rule: a key never leaves the machine
        raise LiveRefused(f"{endpoint.api_key_env} is set, and a key is never sent to a LAN address (D-698, D-827); "
                          "unset it for this run, or serve on loopback", code="cli.refused.lan_key")
    params: dict[str, Any] = {}
    if args.temperature is not None:
        params["temperature"] = args.temperature
    provider = "anthropic" if endpoint.api == "anthropic_messages" else "openai_compatible"
    if provider == "anthropic":
        params.update(_anthropic_params(args))
        if values.get("REASONING_EFFORT"):
            result.notices.append("REASONING_EFFORT in the environment is not used: AgentDojo's Anthropic element "
                                  "sends no effort")
    else:
        effort = args.reasoning_effort or values.get("REASONING_EFFORT")
        if effort:
            params["reasoning_effort"] = effort
    agent = {"model_requested": model_id, "provider": provider, "endpoint": endpoint.name,
             "api_key_env": api_key_env, "params": params, "llm_element": args.llm_element or "native",
             "transport": "http", "script": None, "base_url": base_url}
    if lan:
        agent["allow_lan"] = True
    return agent, keys


def _pick_model(listing: Any, ctx: Context) -> str:
    """No ``--model-id`` for a local endpoint: a numbered pick on a terminal, else a refusal naming the served ids."""
    import sys

    from agentprov.cli.live import localmodels as lm

    rows = [r for r in listing.rows if r["servable"] and not r["remote"]]
    stdin = sys.stdin
    if rows and stdin is not None and stdin.isatty() and ctx.stderr.isatty():
        ctx.stderr.write("models served by this local server:\n")
        for i, row in enumerate(rows, 1):
            facts = " ".join(safe_text(str(row[k]), 40) for k in ("params", "quantization", "format") if row.get(k))
            ctx.stderr.write(f"  {i:>3}. {safe_text(row['id'], 160)}  {facts}\n")
        ctx.stderr.write("Model number? ")
        ctx.stderr.flush()
        answer = stdin.readline().strip()
        if answer.isdigit() and 1 <= int(answer) <= len(rows):
            return str(rows[int(answer) - 1]["id"])
    raise LiveEnvironmentError("no model id: give --model-id (there are no default model ids); "
                               + lm.not_served_message(listing, "").split("; ", 1)[-1],
                               code="cli.environment.model_id")


def _model_block(record: Mapping[str, Any]) -> list[str]:
    """The dry-run and pre-start lines naming the local model that will run (D-692)."""
    server = record.get("server") or {}
    ident = record.get("server_identity") or {}
    files = record.get("files")
    facts = ", ".join(f"{k} {safe_text(str(ident[k]), 80)}" for k in (
        "display_name", "family", "architecture", "params", "parameter_size", "quantization", "quantization_level",
        "format", "digest") if ident.get(k) is not None)
    lines = [f"model {safe_text(str(record.get('model_id')), 160)} on {safe_text(str(record.get('endpoint')), 40)} "
             f"({safe_text(str(record.get('base_url')), 120)}; server {safe_text(str(server.get('kind')), 30)}"
             f"{' ' + safe_text(str(server['version']), 40) if server.get('version') else ''})",
             f"  {facts}" if facts else "  (the server reports no model facts)",
             f"  identity {record.get('identity_sha256')}"]
    if files:
        weights = [f for f in files.get("files", []) if f.get("sha256_source") != "not_hashed"]
        lines.append(f"  files {safe_text(str(files.get('label')), 160)} ({files.get('method')}"
                     f"{', ' + str(files['match']) if files.get('match') else ''}): {len(files.get('files', []))} file(s), "
                     f"{len(weights)} digested" + ("" if files.get("weights_hashed") else ", weights not hashed"))
    else:
        lines.append(f"  files: none ({safe_text(str(record.get('files_reason')), 80)})")
    if record.get("network") == "lan":
        lines.append("  network: LAN (--allow-lan-endpoint): the model runs on another machine; prompts and replies "
                     "cross the network in plain http")
    lines.append("  estimate: cost $0.00 (local endpoint); time: needs a measured throughput (N.2.1a(4))")
    return lines


def _warn_unlisted(ctx: Context, agent: Mapping[str, Any], result: CommandResult) -> None:
    """D-734: when the provider's cached model list (``agentprov models``) does not list the requested model, say so
    before the run. A warning, not a refusal: lists lag behind what a provider serves. No network is used here; the
    served model is still recorded and compared (A12)."""
    from agentprov.cli.live import envs
    from agentprov.cli.live import providermodels as pm

    endpoint = str(agent.get("endpoint"))
    if endpoint not in pm.PROVIDER_ENDPOINTS:
        return
    cache = pm.read_cache(envs.agentprov_home(ctx.env), endpoint)
    model = str(agent.get("model_requested"))
    if cache is not None and model not in pm.listed_ids(cache):
        message = (f"model {safe_text(model, 160)} is not in {endpoint}'s cached model list (fetched "
                   f"{cache['fetched_at']}); lists can lag, so the run goes on (D-734)")
        result.notices.append(message)
        result.error(f"agentprov: warning: {message}")


def _drop_none(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list | tuple):
        return [_drop_none(v) for v in value if v is not None]
    return value


def _resolve_local(ctx: Context, args: argparse.Namespace, agent: Mapping[str, Any], result: CommandResult, *,
                   writable_cache: bool, api_key: str | None = None) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """D-691..D-693 for a local endpoint, before anything is spawned: the server is fingerprinted and listed (the
    N.2.1a(1) preflight), the model picked or checked, and its identity observed. Returns the agent with
    ``model_requested`` and ``local_model`` (the record without ``observed_at``), the record, and the per-cell
    observer the campaign calls before each cell."""
    from agentprov.cli.live import envs
    from agentprov.cli.live import localmodels as lm
    from agentprov_capture.endpoints import get_endpoint

    endpoint = get_endpoint(str(agent["endpoint"]))
    base_url = str(agent["base_url"])
    lan = bool(agent.get("allow_lan"))
    listing = lm.list_server(base_url, endpoint=endpoint.name, expected_kind=endpoint.server, allow_lan=lan,
                             api_key=api_key)
    model_id = agent.get("model_requested") or _pick_model(listing, ctx)
    cache = lm.DigestCache(envs.agentprov_home(ctx.env) / "cache" / "model-digests.jsonl", writable=writable_cache)
    stored, label = model_settings(endpoint.name, str(model_id))
    model_dir = args.model_dir or setting_model_dir(stored, label)  # D-828: flag > setting
    if model_dir and not args.model_dir:
        result.notices.append(f"model folder from the setting {label}model_dir (D-828)")
    record = lm.model_identity(listing, str(model_id), environ=ctx.env, model_dir=model_dir,
                               hash_weights=not args.no_hash_weights, cache=cache, api_key=api_key)
    ident = record.get("server_identity") or {}
    if record["server"]["kind"] == "lmstudio" and ident.get("trained_for_tool_use") is False \
            and not args.allow_text_tool_calls:
        raise LiveRefused("LM Studio serves this model without native tool use: it adds its own tool-use system prompt "
                          "on the server, which the wire capture cannot see (D-694, Q5); pass --allow-text-tool-calls "
                          "to accept it (recorded)", code="cli.refused.local_tool_prompt")
    planned = _drop_none({k: v for k, v in record.items() if k != "observed_at"})  # TOML has no null (the plan)
    plan_side = lm.server_side_sha256(record)

    def observe() -> dict[str, Any]:
        """T0's server-side re-observation just before a cell (recorded by the worker as agentdojo/local_model)."""
        try:
            again = lm.model_identity(lm.list_server(base_url, endpoint=endpoint.name, expected_kind=endpoint.server,
                                                     allow_lan=lan, api_key=api_key), str(model_id), environ=ctx.env,
                                      files=False, api_key=api_key)
        except lm.LocalModelError as exc:
            return {"observed": None, "error": exc.code, "plan_identity_sha256": record["identity_sha256"],
                    "matches_plan": False}
        side = lm.server_side_sha256(again)
        return {"observed": again, "plan_identity_sha256": record["identity_sha256"],
                "plan_server_side_sha256": plan_side, "server_side_sha256": side, "matches_plan": side == plan_side}

    for line in _model_block(record):
        result.output(line)
    return {**agent, "model_requested": str(model_id), "local_model": planned}, record, observe


def _defence_endpoint(args: argparse.Namespace, entry: Any, values: Mapping[str, str], keys: dict[str, str],
                      result: CommandResult, *, scripted: bool) -> dict[str, Any] | None:
    """D-675: the defence's own endpoint (``backend_config.defence_endpoint``), and its key in ``keys`` (the only extra
    variable that enters T2). A scripted run needs none: the harness serves the defence's calls from the same script."""
    from agentprov_capture.endpoints import EndpointError, check_base_url, get_endpoint

    needs = entry is not None and entry.aux_llm == "defence_endpoint"
    if args.defence_endpoint and not needs:
        raise CliUsageError("agentprov run: --defence-endpoint is for a defence that calls its own endpoint (D-675)")
    if not needs or scripted:
        return None
    if not args.defence_endpoint:
        raise CliUsageError(f"agentprov run: the defence {entry.id} calls its own endpoint; give --defence-endpoint NAME "
                            "(D-675)")
    try:
        endpoint = get_endpoint(args.defence_endpoint)
    except EndpointError:
        raise CliUsageError(f"agentprov run: unknown --defence-endpoint {safe_text(args.defence_endpoint, 40)!r}") from None
    if endpoint.api_key_env:
        value = values.get(endpoint.api_key_env)
        if not value:
            raise LiveEnvironmentError(f"the defence endpoint's credential variable {endpoint.api_key_env} is not set in "
                                       ".env", code="cli.environment.credential")
        register_secret(value)
        keys[endpoint.api_key_env] = value
    base_url = (values.get(endpoint.base_url_env) if endpoint.base_url_env else None) or endpoint.base_url
    try:
        custom = check_base_url(endpoint, base_url, allow_custom=bool(args.allow_custom_endpoint))
    except EndpointError as exc:
        raise LiveRefused(f"the defence endpoint's base URL is refused ({exc.code}); see G.9.2",
                          code="cli.refused.endpoint") from None
    if custom:
        result.notices.append("--allow-custom-endpoint: the defence endpoint's host differs from the registry (recorded)")
    return {"endpoint": endpoint.name, "api_key_env": endpoint.api_key_env, "base_url": base_url}


def _scripted_agent(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.temperature is not None:
        params["temperature"] = args.temperature
    provider = selected_provider(args)
    if provider == "anthropic":
        params.update(_anthropic_params(args))
    elif args.reasoning_effort:
        params["reasoning_effort"] = args.reasoning_effort
    return {"model_requested": args.model_id or "scripted-fake", "provider": provider, "endpoint": "scripted",
            "api_key_env": None, "params": params, "llm_element": args.llm_element or "native", "transport": "scripted",
            "script": SCRIPT_LABEL, "base_url": None}


_TOML_SIMPLE_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def _toml_string(text: str) -> str:
    """``text`` as a TOML basic string, ASCII only (escaping finding F-05).

    TOML escapes a code point above U+FFFF as ``\\UXXXXXXXX`` and has no surrogate pairs, unlike JSON, whose
    ``\\ud83d\\ude00`` ``tomllib`` rejects ("Escaped character is not a Unicode scalar value"). Control characters
    and DEL, which a basic string may not hold raw, are written as ``\\uXXXX``. A lone surrogate is not a Unicode scalar
    value, so TOML cannot carry it at all and the value is refused. For BMP text the result equals ``json.dumps``
    with ``ensure_ascii=True`` (DEL aside)."""
    out = ['"']
    for char in text:
        code = ord(char)
        if char in _TOML_SIMPLE_ESCAPES:
            out.append(_TOML_SIMPLE_ESCAPES[char])
        elif 0xD800 <= code <= 0xDFFF:
            raise CliUsageError("agentprov run: a plan string holds a lone surrogate, which TOML cannot represent")
        elif 0x20 <= code < 0x7F:
            out.append(char)
        elif code <= 0xFFFF:
            out.append(f"\\u{code:04x}")
        else:
            out.append(f"\\U{code:08x}")
    out.append('"')
    return "".join(out)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        if isinstance(value, float) and not math.isfinite(value):
            raise CliUsageError("agentprov run: a plan value is not finite")
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, Mapping):  # an object inside an array: an inline table (members that are None are omitted)
        return "{" + ", ".join(f"{_toml_string(str(k))} = {_toml_value(v)}" for k, v in value.items() if v is not None) + "}"
    raise CliUsageError(f"agentprov run: a plan value of type {type(value).__name__} cannot be written as TOML")


def toml_dumps(document: Mapping[str, Any]) -> str:
    """A minimal TOML writer for run plans: tables of scalars and lists, nested tables (no arrays of tables)."""
    lines: list[str] = []

    def table(prefix: str, body: Mapping[str, Any]) -> None:
        scalars = {k: v for k, v in body.items() if not isinstance(v, Mapping) and v is not None}
        if prefix:
            lines.append(f"[{prefix}]")
        lines.extend(f"{_toml_string(k)} = {_toml_value(v)}" for k, v in scalars.items())
        for k, v in body.items():
            if isinstance(v, Mapping):
                table(f"{prefix}.{_toml_string(k)}" if prefix else _toml_string(k), v)

    table("", {k: v for k, v in document.items() if not isinstance(v, Mapping)})
    for key, value in document.items():
        if isinstance(value, Mapping):
            table(_toml_string(key), value)
    return "\n".join(lines) + "\n"


#: The Inspect-plan options (D-663); never mixed with the AgentDojo-family cell options (:data:`_CELL_OPTIONS`).
_INSPECT_OPTIONS: Final = ("task", "task_param", "samples", "epochs", "message_limit", "token_limit", "time_limit",
                           "max_connections", "cell_size", "judge")


def _given(args: argparse.Namespace, names: Sequence[str]) -> list[str]:
    return ["--" + n.replace("_", "-") for n in names if getattr(args, n, None) not in (None, False, [])]


def _task_param(text: str) -> tuple[str, Any]:
    import tomllib

    key, sep, raw = text.partition("=")
    if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key):
        raise CliUsageError("agentprov run: --task-param takes KEY=VALUE")
    try:
        value = tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        value = raw
    if not isinstance(value, (str, int, bool)) or isinstance(value, float):
        raise CliUsageError("agentprov run: a --task-param value is a string, an integer or a boolean")
    return key, value


def _caps_given(args: argparse.Namespace) -> bool:
    """Whether the D-725 caps are active (``Caps.active``): ``--max-calls`` or ``--max-cost-usd`` given."""
    return getattr(args, "max_calls", None) is not None or getattr(args, "max_cost_usd", None) is not None


def _judge(text: str) -> tuple[str, str]:
    role, sep, model = text.partition("=")
    if not sep or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", role) or not model:
        raise CliUsageError("agentprov run: --judge takes ROLE=MODEL (a role the task's scorer declares)")
    return role, model


def _inspect_document(args: argparse.Namespace, agent: Mapping[str, Any], backend: str) -> dict[str, Any]:
    """An Inspect plan (D-663; ``agentprov_backend_inspect.plan``): ``[plan]``, ``[inspect]`` and the judge tables from
    the command line (or ``--plan``), the agent from the command line. Judges use the agent's endpoint, base URL and key
    (their own endpoints are a later extension); the worker refuses a plan that leaves a judge role out (D-667)."""
    import tomllib

    if _given(args, _CELL_OPTIONS):
        raise CliUsageError("agentprov run: an Inspect backend takes the Inspect-plan options, not "
                            + ", ".join(_given(args, _CELL_OPTIONS)))
    agent_table = {k: v for k, v in agent.items() if v is not None}
    if args.plan:
        try:
            spec = tomllib.loads(Path(args.plan).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            raise CliUsageError("agentprov run: --plan cannot be read") from None
        except tomllib.TOMLDecodeError as exc:
            raise CliUsageError(f"agentprov run: --plan is not valid TOML ({safe_text(str(exc), 120)})") from None
        if _given(args, _INSPECT_OPTIONS):
            raise CliUsageError("agentprov run: --plan is exclusive with " + ", ".join(_given(args, _INSPECT_OPTIONS)))
        from_file = {k: v for k, v in spec.items() if k != "agent"}
        from_file.setdefault("plan", {}).update({"format": "agentprov-run-plan/0.1", "backend": backend})
        from_file["agent"] = agent_table
        if _caps_given(args) and isinstance(from_file.get("inspect"), dict):
            from_file["inspect"].setdefault("cell_size", 1)  # D-740: one sample's worst case reserved per cell
        return from_file
    if not args.task or not args.samples:
        raise CliUsageError("agentprov run: an Inspect plan needs --task and --samples")
    if args.samples.startswith("limit:"):
        count = args.samples.removeprefix("limit:")
        if not count.isdigit() or int(count) < 1:
            raise CliUsageError("agentprov run: --samples limit:N takes a positive integer")
        samples: dict[str, Any] = {"limit": int(count)}
    else:
        samples = {"ids": [i for i in args.samples.split(",") if i]}
    inspect: dict[str, Any] = {"task": args.task, "params": dict(_task_param(t) for t in args.task_param or ()),
                               "samples": samples,
                               "limits": {k: v for k, v in (("message_limit", args.message_limit),
                                                            ("token_limit", args.token_limit),
                                                            ("time_limit_s", args.time_limit)) if v is not None}}
    for key in ("epochs", "max_connections", "cell_size"):
        if getattr(args, key) is not None:
            inspect[key] = getattr(args, key)
    if _caps_given(args):
        inspect.setdefault("cell_size", 1)  # D-740: under caps a cell reserves one sample's worst case, not 25
    judges = {role: {**agent_table, "model_requested": model} for role, model in map(_judge, args.judge or ())}
    document: dict[str, Any] = {"plan": {"format": "agentprov-run-plan/0.1", "backend": backend},
                                "inspect": inspect, "agent": agent_table}
    if judges:
        document["judges"] = judges
    return document


def _plan_document(args: argparse.Namespace, agent: Mapping[str, Any], *, backend: str = "agentdojo",
                   attack_params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The ``agentprov-run-plan/0.1`` document the worker expands (D.10.10 item 19). ``--plan`` supplies the cells and
    ``[backend]``; the agent always comes from the command line (it carries the resolved endpoint, never a secret).
    An Inspect backend gets an Inspect plan (:func:`_inspect_document`)."""
    import tomllib

    if backend.startswith("inspect-"):
        return _inspect_document(args, agent, backend)
    if _given(args, _INSPECT_OPTIONS):
        raise CliUsageError(f"agentprov run: {', '.join(_given(args, _INSPECT_OPTIONS))} need an Inspect backend")

    document: dict[str, Any]
    if args.plan:
        try:
            spec = tomllib.loads(Path(args.plan).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            raise CliUsageError("agentprov run: --plan cannot be read") from None
        except tomllib.TOMLDecodeError as exc:
            raise CliUsageError(f"agentprov run: --plan is not valid TOML ({safe_text(str(exc), 120)})") from None
        plan = spec.get("plan")
        if not isinstance(plan, dict) or plan.get("format") != "agentprov-run-plan/0.1":
            raise CliUsageError("agentprov run: --plan must have [plan] format = \"agentprov-run-plan/0.1\" (D.10.1)")
        document = {k: v for k, v in spec.items() if k != "agent"}
    else:
        plan = {"format": "agentprov-run-plan/0.1", "backend": backend,
                "benchmark_version": args.benchmark_version or "v1.2.2",
                "suites": [s for s in (args.suite or "").split(",") if s]}
        if args.user_tasks:
            plan["user_tasks"] = args.user_tasks
        if args.injection_tasks:
            plan["injection_tasks"] = args.injection_tasks
        if args.attack:
            plan["attacks"] = [a for a in args.attack.split(",") if a]
        if args.benign:
            plan["benign"] = args.benign
        if args.defence and args.defence != "none":
            plan["defence"] = args.defence
        document = {"plan": plan}
    if args.model_display_name:
        document.setdefault("attack_params", {})["model_display_name"] = args.model_display_name
    for key, value in (attack_params or {}).items():
        document.setdefault("attack_params", {})[key] = value
    document["agent"] = {k: v for k, v in agent.items() if v is not None}
    return document


def _hello(worker: Any, identity: Any, marker: Any, expect: dict[str, Any], backend: str | None = None) -> dict[str, Any]:
    import uuid

    from agentprov.cli.live.envs import check_hello
    from agentprov.cli.live.worker import WorkerDied, WorkerTimeout

    nonce = uuid.uuid4().hex
    try:
        hello = worker.request("hello", "hello_ok", 300.0, nonce=nonce, expect=expect)
    except (WorkerDied, WorkerTimeout) as exc:
        raise LiveEnvironmentError(f"the backend worker did not answer hello: {exc}", code="backend.unavailable") from None
    if hello.get("nonce") != nonce:
        raise LiveEnvironmentError("IdentityMismatch: hello_ok answered another nonce", code="adapter.identity_mismatch")
    check_hello(hello, identity, marker, backend=backend)
    return hello


def _hello_and_plan(argv: list[str], env: dict[str, str], identity: Any, marker: Any, expect: dict[str, Any],
                    plan_toml: str, scratch: Path, backend: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """One worker for the handshake and the plan expansion (N.2.1 behaviour 2)."""
    from agentprov.cli.live.worker import BackendWorker, WorkerDied, WorkerSpec, WorkerTimeout

    worker = BackendWorker(WorkerSpec(argv=argv, env=env, cwd=scratch, stderr_path=scratch / "worker.stderr.log"))
    worker.start()
    try:
        hello = _hello(worker, identity, marker, expect, backend)
        try:
            reply = worker.request("plan", ("plan_ok", "plan_refused"), 300.0, req="plan", plan_toml=plan_toml)
        except (WorkerDied, WorkerTimeout) as exc:
            raise LiveEnvironmentError(f"the backend worker did not expand the plan: {exc}", code="backend.unavailable") from None
        if reply["op"] == "plan_refused":
            error_raw = reply.get("error")
            error: dict[str, Any] = error_raw if isinstance(error_raw, dict) else {}
            raise CliUsageError(f"agentprov run: the backend refused the plan: {safe_text(str(error.get('message', '')), 300)}")
        plan = reply.get("plan")
        if (not isinstance(plan, dict) or not isinstance(plan.get("cells"), list)
                or not isinstance(plan.get("plan_sha256"), str) or not _PLAN_SHA256.fullmatch(plan["plan_sha256"])):
            raise LiveEnvironmentError("the backend worker sent a malformed plan", code="backend.protocol")
        return hello, plan
    finally:
        worker.shutdown()


def _run_probe(argv: list[str], env: dict[str, str], identity: Any, marker: Any, expect: dict[str, Any],
               agent: Mapping[str, Any], session_dir: Path, redactor: Any, backend: str | None = None) -> dict[str, Any]:
    """The D.10.9 preflight probe as its own capture session (worker op ``probe``); never mapped, never stored."""
    import uuid

    from agentprov.cli.live.staging import scan_secrets
    from agentprov.cli.live.worker import BackendWorker, WorkerDied, WorkerSpec, WorkerTimeout

    worker = BackendWorker(WorkerSpec(argv=argv, env=env, cwd=session_dir, stderr_path=session_dir / "worker.stderr.log"))
    worker.start()
    try:
        _hello(worker, identity, marker, expect, backend)
        reply = worker.request("probe", "probe_done", 600.0, req="probe", agent=dict(agent),
                               session={"ex": "ex_" + str(uuid.uuid7()), "dir": str(session_dir)})
    except (WorkerDied, WorkerTimeout) as exc:
        raise LiveEnvironmentError(f"the preflight probe did not complete: {exc}", code="cli.environment.preflight") from None
    finally:
        worker.shutdown()
    if scan_secrets(session_dir, redactor):
        raise AgentProvError("the preflight probe session holds a secret value; it was kept in staging and nothing "
                             "was run", code="capture.quarantined", exit_code=1)
    results = reply.get("results")
    return dict(results) if isinstance(results, dict) else {}


#: D-729: preflight probe calls at most. Another call is made only while the reply is ``unconfirmed`` (2xx, but no
#: evidence that the system message was followed): one call at a sampling model's default temperature is a noisy gate.
PROBE_ATTEMPTS: Final = 3


def _probe_inconclusive(results: Mapping[str, Any]) -> bool:
    return bool(results.get("reachable")) and not results.get("roles_accepted") and results.get("roles") == "unconfirmed"


def _probe(run_once: Any, result: CommandResult, budget: Any = None) -> tuple[dict[str, Any], int]:
    """The preflight probe (D.10.9), repeated up to :data:`PROBE_ATTEMPTS` times while its verdict is ``unconfirmed``
    (D-729): the first accepted reply ends it, and any other verdict (refused, unreachable) is final at once. Every call
    is charged to the caps (D-725). Returns the last results and the number of calls."""
    calls = 0
    while True:
        results = run_once()
        calls += 1
        if budget is not None:
            budget.charge_probe()
        if not _probe_inconclusive(results) or calls >= PROBE_ATTEMPTS:
            if calls > 1:
                result.notices.append(f"preflight: {calls} probe call(s); the earlier replies gave no evidence that the "
                                      "system message was followed (A9 unconfirmed; D-729)")
            return results, calls


def _evaluate_probe(results: Mapping[str, Any], args: argparse.Namespace, result: CommandResult) -> None:
    """D.10.9 preflight outcomes: unreachable 3, roles refused or not evidenced by the reply 4 (A9; D-291: the
    worker's ``roles`` verdict, never the status alone), text tool calls 4 (A4) unless ``--allow-text-tool-calls``, a
    configured parameter not transmitted 2 (A3) unless ``--temperature-policy``."""
    params_raw = results.get("params")
    params: Mapping[str, Any] = params_raw if isinstance(params_raw, dict) else {}
    not_sent = [safe_text(str(p), 60) for p in params.get("not_transmitted") or []][:20]  # worker-supplied: escaped
    roles = safe_text(str(results.get("roles", "accepted" if results.get("roles_accepted") else "refused")), 20)
    reason = safe_text(str(results.get("roles_reason", "")), 40)
    result.output(f"preflight: reachable={safe_text(str(results.get('reachable')), 20)} "
                  f"roles_accepted={safe_text(str(results.get('roles_accepted')), 20)} "
                  f"roles={roles}{f' ({reason})' if reason else ''} "
                  f"http_status={safe_text(str(results.get('http_status')), 20)} "
                  f"tool_calls={safe_text(str(results.get('tool_calls')), 20)} "
                  f"not_transmitted={','.join(not_sent) or 'none'}")
    if not results.get("reachable"):
        raise LiveEnvironmentError("preflight: the endpoint is not reachable", code="cli.environment.preflight")
    if not results.get("roles_accepted") and roles == "unconfirmed":
        raise LiveRefused(f"preflight (A9): the endpoint answered 2xx but the reply gives no evidence that the system "
                          f"message reached the model ({reason}); the stock roles may be ignored silently. Check the "
                          "endpoint and model; --llm-element gateway_compat (declared request_modifying) changes the "
                          "roles sent", code="cli.refused.preflight")
    if not results.get("roles_accepted"):
        raise LiveRefused(f"preflight (A9): the endpoint rejected the stock message roles"
                          f"{f' ({reason})' if reason else ''}; --llm-element gateway_compat (declared "
                          "request_modifying) is the opt-in remedy", code="cli.refused.preflight")
    if results.get("tool_calls") == "text_encoded" and not args.allow_text_tool_calls:
        raise LiveRefused("preflight (A4): the endpoint returned a text-encoded tool call; rerun with "
                          "--allow-text-tool-calls to accept it (recorded)", code="cli.refused.preflight")
    if not_sent and not args.temperature_policy:
        raise CliUsageError("agentprov run: preflight (A3): a configured parameter is not transmitted by the stock "
                            "element; choose --temperature-policy as-benchmark (stock behaviour, recorded)")


def _consent(args: argparse.Namespace, *, agent: Mapping[str, Any], ctx: Context, result: CommandResult,
             resume: ResumeState | None = None, endpoint_kind: str | None = None, budget: Any = None) -> None:
    """N.1.11(3): print what will be billed; ask interactively or require a consent flag (D-726): a ``local`` run takes
    ``--i-consent-to-local-run`` or ``--i-consent-to-api-costs``, an ``api`` run ``--i-consent-to-api-costs`` only.

    It runs before the first model call, and the preflight probe is one: consent covers the probe and the cells.
    ``resume`` is ``None`` for ``--preflight-only`` (the probe alone); otherwise it gives the units planned, those
    already settled and the attempt bound under ``--max-attempts``, counted as the campaign counts them."""
    import sys

    if resume is None:
        head = [f"agentprov run: up to {PROBE_ATTEMPTS} preflight probe call(s) (--preflight-only; no cells)"]
    else:
        head = [f"agentprov run: up to {PROBE_ATTEMPTS} preflight probe call(s), then up to {resume.attempts_due} cell attempt(s): "
                f"{resume.units - resume.settled} of {resume.units} unit(s) to run, at most {resume.max_attempts} "
                f"attempt(s) each across invocations; {resume.settled} already complete (skipped)"]
    lines = [
        *head,
        f"  endpoint {safe_text(str(agent.get('base_url')), 200)}, model {safe_text(str(agent.get('model_requested')), 120)}, "
        f"key variable {agent.get('api_key_env') or 'none'}",
        f"  LLM element {agent.get('llm_element')}; the backend declares the instrumentation items in each session's "
        "capture log (D.10.7), and the corpus records them",
    ]
    judges = [_judge(j) for j in getattr(args, "judge", None) or ()]
    if judges:  # D-667: the judges are paid calls too, at the agent's endpoint and key
        lines.append("  judges (model calls at the same endpoint and key): "
                     + ", ".join(f"{safe_text(r, 64)} {safe_text(m, 120)}" for r, m in judges))
    local = endpoint_kind == "local"
    if local:
        lines.append("  local model server: no provider billing; the run loads this machine heavily")
    else:
        lines.append("  model calls may be billed by the provider")
    if budget is not None:
        calls, usd = budget.cell_bound()
        caps = budget.caps
        lines.append(f"  caps: --max-calls {caps.max_calls if caps.max_calls is not None else 'none'}, --max-cost-usd "
                     f"{caps.max_cost_usd if caps.max_cost_usd is not None else 'none'}; a cell may need up to {calls} "
                     f"billed call(s)" + (f" and ${usd:.3f}" if caps.max_cost_usd is not None else "")
                     + " and starts only if that fits what is left")
    for line in lines:
        ctx.stderr.write(line + "\n")
    if args.i_consent_to_api_costs:
        result.notices.append("consent: --i-consent-to-api-costs")
        return
    if args.i_consent_to_local_run:
        if not local:
            raise LiveRefused("--i-consent-to-local-run is consent for a local model server; an API endpoint run needs "
                              "--i-consent-to-api-costs or the interactive prompt (D-726)", code="cli.refused.consent")
        result.notices.append("consent: --i-consent-to-local-run")
        return
    stdin = sys.stdin
    if stdin is not None and stdin.isatty() and ctx.stderr.isatty():
        ctx.stderr.write("Continue? [y/N] ")
        ctx.stderr.flush()
        if stdin.readline().strip().lower() in ("y", "yes"):
            result.notices.append("consent: interactive")
            return
    flag = "--i-consent-to-local-run" if local else "--i-consent-to-api-costs"
    raise LiveRefused(f"a real-model run needs consent: answer the prompt on a terminal or pass {flag} (N.1.11(3); D-726)",
                      code="cli.refused.consent")


def _containment(args: argparse.Namespace, marker: Mapping[str, Any]) -> dict[str, Any]:
    """AD-13(b): a real-model run needs ``--containment``; ``sandbox-exec`` needs the passed probe of this profile."""
    from agentprov.cli.live.sandbox import PROFILE_SHA256

    if not args.containment:
        raise LiveRefused("a real-model run needs --containment {sandbox-exec,dedicated-user,vm} (AD-13(b); G.4.10)",
                          code="cli.refused.containment")
    if args.containment == "sandbox-exec":
        probe_raw = marker.get("sandbox_probe")
        probe: Mapping[str, Any] = probe_raw if isinstance(probe_raw, Mapping) else {}
        if probe.get("status") != "passed" or probe.get("profile_sha256") != PROFILE_SHA256:
            raise LiveRefused("--containment sandbox-exec needs the passed feasibility probe of this profile, recorded by "
                              "'agentprov backends build' (G.4.10); use dedicated-user or vm otherwise",
                              code="cli.refused.containment")
        return {"kind": "sandbox_exec", "declared_by": "probe", "profile_sha256": PROFILE_SHA256}
    return {"kind": args.containment.replace("-", "_"), "declared_by": "operator"}


# --------------------------------------------------------------------------------------------------------------
# Backend-specific T0 checks (D.11.3 rule 5, D.11.7 items 2 and 10; D.11.9)
# --------------------------------------------------------------------------------------------------------------

#: Refusals T0 applies before anything is spawned; the worker refuses the same (D.11.7 item 10), so this is the earlier
#: and clearer of two checks, never the only one.
BACKEND_REFUSALS: Final[Mapping[str, Mapping[str, Mapping[str, str]]]] = {
    "autodojo": {
        "llm_element": {
            "gateway_compat": "The gateway_compat port binds to private AgentDojo 0.1.35 helpers whose fork versions "
                              "differ; the fork's own LLM element is recorded at the transport level (AD-09).",
        },
        "attack": {
            "ours": "The 'ours' attack replays optimiser output directories (OURS_ATTACK_DIR); optimiser runs and their "
                    "outputs are not supported in v0.1 (D.11.6).",
            "variant_generation": "The variant optimiser (variant_generation, optimize_variants.py) is not part of the "
                                  "installed fork and its in-loop executions are not captured in v0.1 (D.11.6).",
        },
    },
    "agentdyn": {
        "llm_element": {
            "gateway_compat": "The gateway_compat port binds to private AgentDojo 0.1.35 helpers whose AgentDyn versions "
                              "differ; AgentDyn's own LLM element is recorded at the transport level (AD-09).",
        },
    },
}
#: ``run_cell.attack_env`` member names of the AutoDojo worker contract (D.11.7 item 5).
AUTODOJO_ENV_LABEL: Final = "AUTODOJO_CACHE_label"
AUTODOJO_ENV_VARIANT: Final = "AUTODOJO_VARIANT"


def _backend_refusals(args: argparse.Namespace, backend: str, source: str) -> None:
    table = BACKEND_REFUSALS.get(backend, {})
    element = args.llm_element or "native"
    if element in table.get("llm_element", {}):
        raise _unsupported(f"--llm-element {element} for the {backend} backend", source, (table["llm_element"][element],))
    attacks = [a for a in (args.attack or "").split(",") if a]
    for attack in attacks:
        if attack in table.get("attack", {}):
            raise _unsupported(f"the {safe_text(attack, 40)} attack", source, (table["attack"][attack],))
    if backend != "autodojo" and ("autodojo" in attacks or args.autodojo_cache or args.autodojo_variant is not None):
        raise CliUsageError("agentprov run: the cache-replaying autodojo attack exists only in the AutoDojo fork; run it "
                            "with 'agentprov run autodojo'")


def _defence_gate(args: argparse.Namespace, capability: Any, backend: str, source: str, root: Path) -> Any:
    """The run's defence (``--defence`` or the plan's ``[plan] defence``) checked against the registry and the live
    profile before anything is read from the environment or spawned (D-670, D-679); ``None`` for an undefended run.
    Every refusal is ``UnsupportedCapability`` (exit 5), for the flag and for a plan alike."""
    import tomllib

    from agentprov.cli.live.defences import DefenceRefused, check_defence, plan_defence

    defence = args.defence if args.defence and args.defence != "none" else None
    suites = [s for s in (args.suite or "").split(",") if s]
    if args.plan:
        try:
            document = tomllib.loads(Path(args.plan).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return None  # _plan_document reports the unreadable plan (exit 2)
        defence = plan_defence(document)
        plan: Any = document.get("plan")
        listed: Any = plan.get("suites") if isinstance(plan, Mapping) else None
        suites = [str(s) for s in listed if isinstance(s, str)] if isinstance(listed, list) else []
    if defence is None:
        return None
    if defence in REPLACING_DEFENCES:
        raise _unsupported(f"defence {safe_text(defence, 40)} replaces pipeline components", source, (
            "DRIFT, Progent and CaMeL need defence-specific capture (D.11.6).",))
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import BACKENDS

    profile = load_profile(BACKENDS[backend].profile)
    try:
        return check_defence(defence, backend=backend, suites=suites, live=_live_table(capability), root=root,
                             profile_label=f"{profile.id} v{profile.version}")
    except DefenceRefused as exc:
        raise _unsupported(safe_text(exc.what, 120), source, tuple(safe_text(line, 400) for line in exc.lines)) from None


def _live_table(capability: Any) -> dict[str, Any]:
    """``[family.<family>.live]`` of the backend's live profile (the pins and the attack cache, D.4.2)."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import BACKENDS

    profile = load_profile(BACKENDS[str(capability.backend)].profile)
    family = profile.data.get("family")
    table = family.get(profile.family) if isinstance(family, Mapping) else None
    live = table.get("live") if isinstance(table, Mapping) else None
    return _thaw(live) if isinstance(live, Mapping) else {}


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_thaw(v) for v in value]
    return value


def _dict_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def _check_profile_pins(live: Mapping[str, Any], identity: Any, project: Any) -> None:
    """The live profile's pins must be the built environment's benchmark identity (D.10.6, D.11.3 rule 1; D.11.9): a
    git pin is the PEP 610 source of the installed fork (never its version string, which equals the wheel's, D.11.1); a
    wheel pin is the registry distribution and version. The pinned distribution is the environment's primary one
    (``agentdojo``; ``inspect-ai`` for an Inspect backend, D-663). ``distribution_pins`` (a list of ``{distribution,
    version}``, an Inspect profile's benchmark package) pins further registry wheels the same way. A mismatch is
    ``IdentityMismatch`` (exit 3), never accepted."""
    from agentprov.errors import IdentityMismatch

    pins = live.get("pins") if isinstance(live.get("pins"), Mapping) else {}
    bench = identity.distributions.get(getattr(identity, "primary", "agentdojo"))
    if bench is None or not pins:
        raise IdentityMismatch("the live profile declares no pins or the environment has no benchmark distribution")
    if "commit" in pins:
        expected = {"kind": "git", "repo": pins.get("repo"), "commit": pins.get("commit")}
        if "subdirectory" in pins:
            expected["subdirectory"] = pins["subdirectory"]
        if dict(bench.source) != expected or project.commit != pins.get("commit"):
            raise IdentityMismatch("IdentityMismatch: the live profile's fork pin differs from the built environment's "
                                   "PEP 610 source or the project's pinned commit")
    elif bench.source != {"kind": "pypi"} or (bench.name, bench.version) != (pins.get("distribution"), pins.get("version")):
        raise IdentityMismatch("IdentityMismatch: the live profile's wheel pin differs from the built environment")
    extra = live.get("distribution_pins") or []
    for pin in extra if isinstance(extra, list) else [None]:
        dist = identity.distributions.get(_dict_get(pin, "distribution")) if isinstance(pin, Mapping) else None
        if dist is None or dist.source != {"kind": "pypi"} or dist.version != _dict_get(pin, "version"):
            raise IdentityMismatch("IdentityMismatch: a distribution pin of the live profile differs from the built "
                                   "environment")


def _verify_attack_cache(path: str, *, repo: str, commit: str, cache_dir: Path, allow_network: bool) -> Any:
    """:func:`agentprov.cli.live.autodojo_cache.verify_autodojo_cache` with the profile's pin (the tests' seam)."""
    from agentprov.cli.live.autodojo_cache import verify_autodojo_cache

    return verify_autodojo_cache(path, cache_dir=cache_dir, allow_network=allow_network, repo=repo, commit=commit)


class AttackCache:
    """A verified attack cache (D.11.3 rule 5) and what T0 stages and records for it (D.11.9)."""

    def __init__(self, spec: Mapping[str, Any], variant: int, verified: Any, fallback_vectors: int) -> None:
        from agentprov.ingest.limits import IngestLimits
        from agentprov.ingest.loaders import strict_json_loads

        self.attack = str(spec["attack"])
        self.label = str(spec["label"])
        self.sha256_param = str(spec["sha256_param"])
        self.variant_param = str(spec["variant_param"])
        self.variant = variant
        self.verified = verified
        self.fallback_vectors = fallback_vectors
        document = strict_json_loads(verified.data, IngestLimits())  # already parsed once by the verification
        self.tasks = frozenset(document["injection_tasks"])
        self.cells = 0
        self.cells_without_task = 0

    @property
    def attack_params(self) -> dict[str, Any]:
        return {self.sha256_param: self.verified.sha256, self.variant_param: self.variant}

    def count_cells(self, cells: list[dict[str, Any]], result: CommandResult) -> None:
        """The planned cells of the attack, and those whose injection task the cache does not hold (every vector of such
        a cell falls back to the injection task's goal, the fork's silent substitution)."""
        mine = [c for c in cells if c.get("attack") == self.attack]
        self.cells = len(mine)
        self.cells_without_task = sum(1 for c in mine if c.get("injection_task_id") not in self.tasks)
        shape = self.verified.shape
        result.notices.append(
            f"attack cache: {self.fallback_vectors} of {shape.cells} cached vector(s) have no variant {self.variant} and "
            f"fall back to the injection task goal; {self.cells_without_task} of {self.cells} planned cell(s) target an "
            "injection task the cache does not hold (all of their vectors fall back)")

    def staging(self) -> Any:
        from agentprov.cli.live.campaign import AttackStaging

        return AttackStaging(attack=self.attack, label=self.label, data=self.verified.data, sha256=self.verified.sha256,
                             env={AUTODOJO_ENV_LABEL: self.label, AUTODOJO_ENV_VARIANT: self.variant},
                             origin=self.verified.origin)

    def record(self) -> dict[str, Any]:
        v = self.verified
        return {"attack": self.attack, "sha256": "sha256:" + v.sha256, "bytes": v.size, "blob_sha1": v.blob_sha1,
                "origin": v.origin.to_json(), "matching_paths": list(v.matching_paths), "fetched": bool(v.fetched),
                "variant": self.variant, "label": self.label, "vectors": v.shape.cells,
                "fallback_vectors": self.fallback_vectors, "cells": self.cells,
                "cells_without_task": self.cells_without_task}


def _attack_cache(args: argparse.Namespace, live: Mapping[str, Any], ctx: Context,
                  result: CommandResult) -> AttackCache | None:
    """``--autodojo-cache``/``--autodojo-variant`` (D.11.3 rule 5): parse the variant, verify the file against the tree
    of the profile's pinned fork commit in the bare fetch cache (fetched only under ``--allow-network``) and check the
    variant against the cache. Runs before anything is staged or spawned."""
    from agentprov.cli.live.autodojo_cache import check_variant, parse_variant
    from agentprov.raw.fetch import resolve_cache_dir

    if not args.autodojo_cache:
        return None
    spec = live.get("attack_cache")
    pins = live.get("pins")
    if not isinstance(spec, Mapping) or not isinstance(pins, Mapping) or "commit" not in pins:
        raise CliUsageError("agentprov run: this backend has no cache-replaying attack")
    variant = parse_variant(str(args.autodojo_variant))
    verified = _verify_attack_cache(str(args.autodojo_cache), repo=str(pins["repo"]), commit=str(pins["commit"]),
                                    cache_dir=resolve_cache_dir(None, ctx.env),
                                    allow_network=bool(args.allow_network) and not args.dry_run)  # N.1.6: a dry run never fetches
    fallback = check_variant(variant, verified.shape)
    result.notices.append(
        f"attack cache verified: blob {verified.blob_sha1} is {safe_text(verified.path, 200)} of "
        f"{verified.repo}@{verified.commit[:12]}" + (" (commit fetched under --allow-network)" if verified.fetched else ""))
    return AttackCache(spec, variant, verified, fallback)


def _load_ledger(manifest: Mapping[str, Any] | None, store: Any) -> Any:
    """The attempt ledger of an earlier invocation (``live.sessions``); an entry naming a capture log counts only while
    that log is in the raw ``store`` (resume is keyed on sealed raw evidence, N.1.8)."""
    from agentprov.cli.live.campaign import Ledger

    ledger = Ledger()
    live = (manifest or {}).get("live") if isinstance(manifest, Mapping) else None
    for entry in (live or {}).get("sessions", ()) if isinstance(live, Mapping) else ():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("cell_key"), str):
            continue
        sha = entry.get("capture_sha256")
        if isinstance(sha, str) and not store.has(sha):
            continue
        ledger.entries.append(dict(entry))
    return ledger


@dataclass(frozen=True)
class ResumeState:
    """What a run would do with its working corpus, read-only, by the campaign's own rules (``Ledger.settled``, the
    attempts counted across invocations, a ledger entry counting only while its capture log is stored)."""

    units: int
    settled: int
    attempts_due: int
    max_attempts: int


def _resume_ledger(args: argparse.Namespace) -> Any:
    """The working corpus's campaign ledger (empty without one), read-only."""
    from agentprov.cli.live.campaign import Ledger
    from agentprov.corpus.layout import CorpusLayout, partial_dir
    from agentprov.raw.store import RawObjectStore

    if args.corpus:
        partial = partial_dir(_final_dir(args.corpus))
        if partial.is_dir():
            return _load_ledger(_read_json(CorpusLayout(partial).manifest), RawObjectStore(partial / "raw", create=False))
    return Ledger()


def _resume_settled(args: argparse.Namespace, cells: Sequence[Mapping[str, Any]], config_digest: str,
                    repeats: int) -> dict[str, int]:
    """D-651: per cell key, how many of its units are settled (the rule of :func:`_resume_state`)."""
    from agentprov.cli.live.campaign import unit_key

    ledger = _resume_ledger(args)
    retry = bool(args.retry_inconsistent)
    return {str(c["cell_key"]): sum(1 for r in range(repeats)
                                    if ledger.settled(unit_key(str(c["cell_key"]), config_digest, r), retry))
            for c in cells}


def _resume_state(args: argparse.Namespace, cells: Sequence[Mapping[str, Any]], config_digest: str,
                  repeats: int) -> ResumeState:
    from agentprov.cli.live.campaign import unit_key

    max_attempts = args.max_attempts or DEFAULT_MAX_ATTEMPTS
    ledger = _resume_ledger(args)
    keys = [unit_key(str(c["cell_key"]), config_digest, r) for c in cells for r in range(repeats)]
    settled = [k for k in keys if ledger.settled(k, bool(args.retry_inconsistent))]
    due = sum(max(0, max_attempts - len(ledger.attempts(k))) for k in keys if k not in set(settled))
    return ResumeState(units=len(keys), settled=len(settled), attempts_due=due, max_attempts=max_attempts)


def run_run(ctx: Context) -> CommandResult:
    from agentprov.host import detect_host

    args = ctx.args
    # D-395: stdin's endpoint variables before any other step. --keychain is checked now and read only on the real-agent
    # path, after the D-721 caps check, so an uncapped API run reads no key (D-702)
    env_values = _read_env_stdin(args) if args.env_stdin else None
    if args.keychain:
        _check_keychain_args(args)
    profile = detect_host(probe=False)
    preset = validate_run_args(args, lambda: profile)
    _check_json_outputs(args, preset)
    if args.catalogue:
        return _catalogue(ctx, args)
    if getattr(args, "tune_jobs", None):
        _check_tune_args(args, profile)
    if args.dry_run and preset is not None:
        return dry_run_plan(args, preset, profile)
    if preset is not None:
        from agentprov.presets import load_preset

        loaded = load_preset(preset)
        if not getattr(args, "tune_jobs", None) and not loaded.calibrated:  # D-823: nothing runs on unmeasured caps
            raise _unsupported(f"live runs with the uncalibrated preset {loaded.name} v{loaded.version}",
                               str(args.source), (
                "Measure it first with the concurrency sweep (--tune-jobs, N.2.1a(4)); a calibrated version of the "
                "preset (calibrated = true) then runs live. --dry-run prints the plan.",))
        if not (args.model or args.endpoint or args.llm_script):
            args.model = loaded.endpoint  # the preset's endpoint (N.2.1a(2))
    _check_caps_options(args)
    if getattr(args, "tune_jobs", None):
        pass  # the sweep names its own corpora (_check_tune_args)
    elif args.preflight_only:
        if not (args.model or args.endpoint or args.llm_script):
            raise CliUsageError("agentprov run: --preflight-only needs --model, --endpoint with --model-id, or --llm-script")
        if args.dry_run:  # the probe is a model call and writes staging: there is nothing a dry run could show
            raise CliUsageError("agentprov run: --preflight-only and --dry-run are exclusive (the probe is a model call)")
    else:
        _check_run_context(args)
    return _live_run(ctx, args, env_values, preset=preset, profile=profile)


#: the sweep's default cell sample (D-820): 4 suites x user tasks 0-2 x {benign, important_instructions/injection 0},
#: 24 cells, twice the largest default arm; prefill dominates these traces and prompt length differs by suite
TUNE_SAMPLE: Final = {"suite": "banking,slack,travel,workspace", "user_tasks": "0-2", "attack": "important_instructions",
                      "injection_tasks": "0", "benign": "include"}
#: refused with --tune-jobs (exit 2): the sweep sets them itself or they would change what an arm measures
_TUNE_REFUSED: Final = (("jobs", "--jobs"), ("corpus", "--corpus"), ("campaign", "--campaign"),
                        ("corpus_id", "--corpus-id"), ("limit", "--limit"), ("preflight_only", "--preflight-only"),
                        ("plan_json", "--plan-json"), ("allow_mixed_config", "--allow-mixed-config"),
                        ("repeats", "--repeats"), ("spec", "--spec"))


def _check_tune_args(args: argparse.Namespace, profile: HostProfile) -> None:
    """D-820: the sweep's usage rules (exit 2); fills the default sample when no cell option or plan is given."""
    from agentprov.cli.live.tune import TuneUsageError, parse_jobs

    if _preset_name(args) is None:
        raise CliUsageError("agentprov run: --tune-jobs calibrates a host preset: give --m5ultra or --preset NAME")
    used = [flag for dest, flag in _TUNE_REFUSED if getattr(args, dest, None) not in (None, False)]
    if used:
        raise CliUsageError(f"agentprov run: --tune-jobs sets {', '.join(used)} itself (one corpus per arm, D-820)")
    if args.defence and args.defence != "none":
        raise CliUsageError("agentprov run: --tune-jobs measures the undefended pipeline (--defence none)")
    try:
        args.tune_values = parse_jobs(str(args.tune_jobs), host_max=host_max_jobs(profile))
    except TuneUsageError as exc:
        raise CliUsageError(f"agentprov run: {exc}") from None
    args.tune_default_sample = not (args.plan or any(getattr(args, n) not in (None, False) for n in _CELL_OPTIONS))
    if args.tune_default_sample:
        for name, value in TUNE_SAMPLE.items():
            setattr(args, name, value)


def _check_caps_options(args: argparse.Namespace) -> None:
    """D-725: the cap options are complete (exit 2); whether a run needs them is decided by its endpoint class."""
    caps = (args.max_calls, args.max_cost_usd, args.price_in, args.price_out)
    if args.preflight_only and any(v is not None for v in caps):
        raise CliUsageError("agentprov run: --preflight-only is one model call; the caps belong to a campaign")
    if (args.price_in is not None or args.price_out is not None) and args.max_cost_usd is None:
        raise CliUsageError("agentprov run: --price-in and --price-out price --max-cost-usd")
    if args.max_cost_usd is not None and (args.price_in is None or args.price_out is None):
        raise CliUsageError("agentprov run: --max-cost-usd needs --price-in and --price-out (USD per million tokens)")


def _caps(args: argparse.Namespace, agent: Mapping[str, Any]) -> Any:
    from agentprov.cli.live.policy import Caps

    max_tokens = (agent.get("params") or {}).get("max_tokens")
    return Caps(max_calls=args.max_calls, max_cost_usd=args.max_cost_usd, price_in=args.price_in,
                price_out=args.price_out,
                max_tokens=max_tokens if isinstance(max_tokens, int) and not isinstance(max_tokens, bool) else None)


def _endpoint_name(args: argparse.Namespace) -> str:
    return str(args.model or {"local": "ollama"}.get(args.endpoint, args.endpoint))


def _require_api_caps(args: argparse.Namespace, missing: Sequence[str], why: str) -> None:
    """D-725: an ``api`` run (not ``--preflight-only``) states both caps; refused before any key or socket (exit 4)."""
    if args.preflight_only or not missing:
        return
    raise LiveRefused(f"an API endpoint run needs its caps ({why}): give {', '.join(missing)} (D-725; the provider's own "
                      "key limit is the backstop)", code="cli.refused.api_caps")


#: The options ``--catalogue`` combines with (besides SOURCE and the global options): it asks only what a plan can select.
_CATALOGUE_OPTIONS: Final = frozenset({"source", "benchmark_version", "catalogue"})


def _check_json_outputs(args: argparse.Namespace, preset: str | None) -> None:
    """D-651 / D-652: the two machine outputs and what they combine with (exit 2)."""
    if args.plan_json:
        if not args.dry_run:
            raise CliUsageError("agentprov run: --plan-json goes with --dry-run")
        if preset is not None:
            raise CliUsageError("agentprov run: --plan-json needs a cell plan; a dry run with a host preset prints the "
                                "concurrency plan only")
    if args.catalogue:
        own: frozenset[str] = getattr(args, "_run_dests", frozenset())
        given = sorted(k for k, v in vars(args).items() if k in own and k not in _CATALOGUE_OPTIONS
                       and v not in (None, False))
        if given:
            raise CliUsageError("agentprov run: --catalogue takes SOURCE and --benchmark-version only (got "
                                + ", ".join("--" + g.replace("_", "-") for g in given) + ")")
    if (args.plan_json or args.catalogue) and getattr(args, "json", False):
        raise CliUsageError("agentprov run: --plan-json and --catalogue print to stdout, which --json takes")


def _live_run(ctx: Context, args: argparse.Namespace, env_values: Mapping[str, str] | None = None, *,
              preset: str | None = None, profile: HostProfile | None = None) -> CommandResult:
    import contextlib

    with contextlib.ExitStack() as ctx_stack:  # the G6a registrations, released when the run ends however it ends
        return _live_run_held(ctx, args, ctx_stack, env_values, preset_name=preset, profile=profile)


def _live_run_held(ctx: Context, args: argparse.Namespace, ctx_stack: Any,
                   env_values: Mapping[str, str] | None = None, *, preset_name: str | None = None,
                   profile: HostProfile | None = None) -> CommandResult:
    import shutil
    import tempfile
    import uuid

    from agentprov.cli.live import envs
    from agentprov.cli.live.worker import make_private_dir, worker_environment
    from agentprov.io.canonical import jcs_bytes, sha256_hex

    result = CommandResult(dry_run=bool(args.dry_run))
    scripted = bool(args.llm_script)
    source = str(args.source)
    capability = _live_capability(source, result, scripted=scripted)
    backend = str(capability.backend)
    _backend_refusals(args, backend, source)
    root = envs.repository_root()
    defence_entry = _defence_gate(args, capability, backend, source, root)  # D-679: flag and plan alike, before spawn
    if args.temperature_policy == "inject":
        raise _unsupported("--temperature-policy inject", source, (
            "Setting a parameter at the transport (request_modifying, D.10.9 A3) is not implemented by the harness yet.",))
    if args.spec:
        raise _unsupported("--spec", source, ("Corpus specs (H.1.6) arrive with corpus sealing (phase 11); use --plan.",))
    jobs = args.jobs or 1
    preset_obj: Any = None
    if preset_name is not None:  # D-822/D-823: a preset run (calibrated, or the --tune-jobs sweep)
        from agentprov.presets import load_preset

        preset_obj = load_preset(preset_name)
        if args.llm_element == "native":
            raise CliUsageError("agentprov run: a preset run sets the request timeout, which stock OpenAILLM "
                                "(--llm-element native) ignores; use --llm-element gateway_compat (D-822)")
        args.llm_element = args.llm_element or "gateway_compat"
    corpus_id = args.corpus_id or (f"{source}-live-{args.campaign}" if args.campaign else None)
    if corpus_id is not None and (not _CORPUS_ID.fullmatch(corpus_id) or len(corpus_id) > 64):
        raise CliUsageError("agentprov run: the corpus id must match ^[a-z0-9]+(-[a-z0-9]+)*$ (at most 64 characters)")

    project = envs.backend_project(str(capability.backend), root)
    home = envs.agentprov_home(ctx.env)
    env = envs.env_dir(project, home)
    if not args.dry_run:  # G6a: a rebuild never replaces the environment under this run (released at exit)
        from agentprov.io.locks import backend_use, staging_use

        ctx_stack.enter_context(backend_use(home, project.env_name, command="run"))
        ctx_stack.enter_context(staging_use(home, command="run"))
    marker = envs.read_marker(env)
    if marker is None:
        raise LiveEnvironmentError(f"the backend environment {project.env_name} is not built; run "
                                   f"'agentprov backends build {project.backend}'", code="backend.unavailable")
    nltk_data = envs.check_nltk(env, marker)  # D.11.2: the verified NLTK directory, or None when not provisioned
    if defence_entry is not None:
        from agentprov.cli.live.defences import check_environment

        problem, refusal = check_environment(env, defence_entry, root)
        if problem is not None:
            raise LiveEnvironmentError(problem, code="backend.unavailable")
        if refusal is not None:
            raise _unsupported(f"defence {defence_entry.id}", source, (refusal,))
    values: dict[str, str] = {}
    keys: dict[str, str] = {}
    script: bytes | None = None
    sandbox: dict[str, Any] | None = None
    local_record: dict[str, Any] | None = None
    observe_local: Any = None
    endpoint_kind: str | None = None  # D-721: None for a scripted run
    if scripted:
        script = Path(args.llm_script).read_bytes()
        if len(script) > SCRIPT_MAX_BYTES:
            raise CliUsageError("agentprov run: --llm-script is larger than 4 MiB")
        agent = _scripted_agent(args)
        result.notices.append("scripted transport (--llm-script): no network, no keys; sessions are test_only and the "
                              "corpus is synthetic (never released)")
    else:
        from agentprov.cli.live.policy import Caps, endpoint_class
        from agentprov_capture.endpoints import get_endpoint

        # D-721: an entry that is not local is an API endpoint whatever its base URL: its caps are checked before any
        # key source is read (.env, --env-file or the keychain, D-702); a local entry is classed again once its base
        # URL is resolved
        if not get_endpoint(_endpoint_name(args)).local:
            _require_api_caps(args, Caps(args.max_calls, args.max_cost_usd, args.price_in, args.price_out).missing_for_api(),
                              "the endpoint entry is not local")
        if env_values is not None:  # --env-stdin: that source only (read before any other step, D-395)
            values = dict(env_values)
        elif args.keychain:  # --keychain: that source only, read only now (after the caps check)
            values = _read_keychain(args)
        elif args.env_file:  # --env-file: that file only
            values = _read_env_file(args, root)
        else:  # the default: the keychain first, then .env (D-702 as amended)
            values = _default_key_values(args, root, result)
        agent, keys = _real_agent(args, values, result)
        _check_inspect_endpoint(project.backend, agent)
        endpoint_kind = endpoint_class(local_entry=get_endpoint(str(agent["endpoint"])).local,
                                       base_url=agent.get("base_url"))
        _require_api_caps(args, _caps(args, agent).missing_for_api() if endpoint_kind == "api" else [],
                          "the resolved base URL is not a local server on loopback")
        result.notices.append(f"endpoint class {endpoint_kind} (D-721)")
        sandbox = _containment(args, marker)
        if agent.get("endpoint") in LOCAL_ENDPOINT_NAMES:  # D-691..D-693: before consent, the plan and any spawn
            agent, local_record, observe_local = _resolve_local(
                ctx, args, agent, result, writable_cache=not args.dry_run,
                api_key=keys.get(str(agent.get("api_key_env"))) if agent.get("api_key_env") else None)
        else:
            _warn_unlisted(ctx, agent, result)  # D-734: a cached provider list that lacks the model warns, never refuses
    # D-675, before the redactor is built: the defence endpoint's key joins the secrets T0 scans staged files for
    defence_endpoint = _defence_endpoint(args, defence_entry, values, keys, result, scripted=scripted)
    preset_rec: dict[str, Any] | None = None
    preset_plan: Any = None
    preset_facts_: Any = None
    if preset_obj is not None:
        from agentprov.presets import check_host, corpus_json, local_concurrency, preset_record

        # D-822: the preset's request timeout reaches the worker (runner.py reads params.timeout_s); a flag-free run
        # without a preset sends none, so no existing configuration digest changes
        agent = {**agent, "params": {**dict(agent.get("params") or {}), "timeout_s": float(preset_obj.request_timeout_s)}}
        preset_facts_, _stored, _label = preset_facts(args, str(agent.get("endpoint")), agent.get("model_requested"))
        from agentprov.host import detect_host

        preset_host = profile or detect_host(probe=False)
        preset_plan = local_concurrency(preset_obj, preset_facts_, host=preset_host,
                                        server_max_concurrency=args.server_max_concurrency, jobs_override=args.jobs)
        mismatches = check_host(preset_obj, preset_host)
        for mismatch in mismatches:
            result.notices.append(f"preset host mismatch (recorded, not refused): {mismatch.message()}")
        if not getattr(args, "tune_jobs", None):
            jobs = preset_plan.jobs
            check_jobs(jobs, preset_host)
            result.notices.append(f"preset {preset_obj.name} v{preset_obj.version}: jobs {jobs} "
                                  f"({preset_plan.jobs_source}; binding {preset_plan.binding})")
        preset_rec = corpus_json(preset_record(preset_obj, preset_plan, start_stagger_s=args.start_stagger,
                                               host_mismatches=mismatches))  # H.1.4(3): no floats in corpus.json
        if args.start_stagger is None and not getattr(args, "tune_jobs", None):  # the sweep spreads each arm itself
            args.start_stagger = preset_obj.start_stagger_per_worker_s * jobs

    identity = envs.compute_identity(env, project)
    envs.check_against_marker(identity, marker, project)
    envs.check_dataset(env, project, marker)  # an Inspect environment's pinned dataset (D-663); nothing otherwise
    live_table = _live_table(capability)
    _check_profile_pins(live_table, identity, project)
    cache = _attack_cache(args, live_table, ctx, result)  # D.11.3 rule 5: before anything is staged or spawned
    expect = identity.expect(project.commit)
    argv = [str(envs.env_python(env)), "-I", "-B", "-m", envs.backend_kind(project.backend).worker_module]
    egress: Any = None
    if sandbox is not None and sandbox["kind"] == "sandbox_exec":
        from agentprov.cli.live.egress import EgressProxy, endpoint_target, forward_pairs
        from agentprov.cli.live.sandbox import wrap_argv

        # D-664: T2 may connect to two loopback ports only. A remote endpoint is reached through T0's egress proxy,
        # which tunnels to the endpoint's host and port and nothing else; a loopback endpoint directly; a LAN model
        # server over http (D-698) through the proxy's forward mode for exactly that pair.
        base_url = str(agent.get("base_url"))
        lan = bool(agent.get("allow_lan"))
        host, port, loopback = endpoint_target(base_url, allow_lan=lan)
        targets = [(host, port)]
        if defence_endpoint is not None:  # D-675: the defence's own endpoint is a second allowed target
            d_host, d_port, d_loopback = endpoint_target(str(defence_endpoint["base_url"]))
            if loopback != d_loopback:
                raise _unsupported("a defence endpoint on another side of the sandbox than the agent's", source, (
                    "Under sandbox-exec the agent's and the defence's endpoints must both be remote or both loopback "
                    "(D-664, D-675).",))
            if not d_loopback and (d_host, d_port) not in targets:
                targets.append((d_host, d_port))
        if loopback:
            egress_port = port
        else:
            egress = EgressProxy(targets, forward=forward_pairs(base_url, host, port, allow_lan=lan))
            ctx_stack.callback(egress.stop)
            egress_port = egress.start()
        argv = wrap_argv(argv, staging_root=home / "staging", t2home_root=home / "t2home", repo=root, home=Path.home(),
                         egress_port=egress_port)
    egress_url = egress.url if egress is not None else None

    hf_cache: str | None = None
    if defence_entry is not None and defence_entry.weights:  # D-672: the weights load offline from the environment
        from agentprov.cli.live.defences import hf_cache_dir

        hf_cache = str(hf_cache_dir(env))

    def env_for(t2home: Path) -> dict[str, str]:
        return worker_environment(home=t2home, key_variables=keys, block_network=scripted, nltk_data=nltk_data,
                                  egress_proxy=egress_url, hf_cache=hf_cache)

    def offline_env(t2home: Path) -> dict[str, str]:  # hello and plan need no key and no network (G.6.3)
        return worker_environment(home=t2home, key_variables={}, block_network=True, nltk_data=nltk_data)

    from agentprov_capture.redact import Redactor, Secret, secrets_from_environ

    secrets = secrets_from_environ(ctx.env) + [Secret(k, v, "file_value") for k, v in keys.items()]
    redactor = Redactor(secrets)

    if args.preflight_only:
        if not scripted:  # N.1.11(3): the probe is a paid call, so consent comes first
            _consent(args, agent=agent, ctx=ctx, result=result, endpoint_kind=endpoint_kind)
        results, probes = _probe(lambda: _preflight(argv, env_for, identity, marker, expect, agent, home, script,
                                                    redactor, result, backend), result)
        _evaluate_probe(results, args, result)
        result.counters = {"probes": probes}
        return result

    plan_doc = _plan_document(args, agent, backend=project.backend,
                              attack_params=cache.attack_params if cache is not None else None)
    if defence_endpoint is not None:  # D-675: in the plan's backend config, so config_sha256 covers it
        plan_doc.setdefault("backend", {})["defence_endpoint"] = defence_endpoint
    planned_attacks = (plan_doc.get("plan") or {}).get("attacks") or []
    if cache is None and live_table.get("attack_cache") and \
            _dict_get(live_table["attack_cache"], "attack") in planned_attacks:
        raise CliUsageError("agentprov run: the plan runs the cache-replaying attack; give --autodojo-cache and "
                            "--autodojo-variant (D.11.3 rule 5)")
    named = sorted(set(planned_attacks) & MODEL_NAMING_ATTACKS)
    attack_params = plan_doc.get("attack_params") or {}
    if named and not scripted and not (attack_params.get("model_display_name")
                                       or attack_params.get("model_display_name_preset")):
        # only the worker knows AgentDojo's MODEL_NAMES table (the core never imports it): a hint, not a refusal; a
        # model with no stock name is refused at the first cell's setup, which then stops the campaign (config_stop)
        result.notices.append(f"attack(s) {', '.join(named)} address the model by name: a model id without a stock "
                              "AgentDojo name needs --model-display-name (for a local server, stock's own is "
                              "'Local model')")
    if args.dry_run:  # N.1.6: the worker's staging is a temporary directory outside $AGENTPROV_HOME, removed afterwards
        scratch = Path(tempfile.mkdtemp(prefix="agentprov-plan-"))
        t2 = scratch / "home"
        t2.mkdir(mode=0o700)
    else:
        scratch = make_private_dir(home / "staging" / f"plan-{uuid.uuid4().hex}")
        t2 = make_private_dir(home / "t2home" / scratch.name)
    try:
        hello, plan = _hello_and_plan(argv, offline_env(t2), identity, marker, expect, toml_dumps(plan_doc), scratch,
                                      project.backend)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(t2, ignore_errors=True)
    cells = [c for c in plan["cells"] if isinstance(c, dict) and isinstance(c.get("cell_key"), str)]
    if cache is not None:
        cache.count_cells(cells, result)
    digest_input: dict[str, Any] = {
        "backend": project.backend, "agent": dict(agent), "identity": hello["identity"],
        "backend_config": plan.get("backend_config") or {},
    }  # fmt: skip
    if cache is not None:  # the cache's identity is part of the configuration: another cache is another unit (N.1.8(1))
        digest_input["attack_cache"] = dict(cache.attack_params)
    config_digest = "sha256:" + sha256_hex(jcs_bytes(digest_input))
    repeats = args.repeats or int((plan.get("backend_config") or {}).get("repeats") or 1)
    from agentprov.cli.live.policy import Budget

    caps = _caps(args, agent)
    budget = None
    if caps.active:
        inspect_backend = project.backend.startswith("inspect-") and not scripted
        budget = Budget(caps, cell_calls=_inspect_cell_calls(project.backend, plan_doc, agent, identity)) \
            if inspect_backend else Budget(caps)
    if args.dry_run:
        if budget is not None:
            calls, usd = budget.cell_bound()
            result.notices.append(f"caps (D-725): a cell may need up to {calls} billed call(s)"
                                  + (f" and ${usd:.3f}" if caps.max_cost_usd is not None else "")
                                  + "; a cell starts only if that fits what is left")
        return _dry_run_live(args, result, cells, plan, config_digest, repeats, corpus_id, project)
    resume = _resume_state(args, cells, config_digest, repeats)
    if not scripted:  # N.1.11(3): consent before the first model call, which is the paid preflight probe
        _consent(args, agent=agent, ctx=ctx, result=result, resume=resume, endpoint_kind=endpoint_kind, budget=budget)
        probe, _ = _probe(lambda: _preflight(argv, env_for, identity, marker, expect, agent, home, None, redactor,
                                             result, backend), result, budget)
        _evaluate_probe(probe, args, result)
    execute_kw: dict[str, Any] = dict(
        capability=capability, project=project, home=home, marker=marker, identity=identity, expect=expect,
        argv=argv, env_for=env_for, agent=agent, plan=plan, cells=cells, config_digest=config_digest,
        repeats=repeats, script=script, redactor=redactor, sandbox=sandbox, hello=hello, cache=cache, egress=egress,
        local_record=local_record, observe_local=observe_local, budget=budget, endpoint_kind=endpoint_kind)
    if getattr(args, "tune_jobs", None):
        from agentprov.host import detect_host

        return _tune_sweep(ctx, args, result, execute_kw, preset=preset_obj, facts=preset_facts_,
                           host=profile or detect_host(probe=False))
    return _execute(ctx, args, result, **execute_kw, jobs=jobs, corpus_id=str(corpus_id), preset=preset_rec)


def _tune_sweep(ctx: Context, args: argparse.Namespace, result: CommandResult, execute_kw: dict[str, Any], *,
                preset: Any, facts: Any, host: HostProfile) -> CommandResult:
    """``run --tune-jobs`` (N.2.1a(4); D-820, D-821): a warm-up cell, then one arm per ``jobs`` value, each the same
    cells into its own working corpus ``<out>/jobs-<N>``, measured on T0's clock and from the stored capture logs. A
    finished arm writes ``<out>/arms/jobs-<N>.json`` and is reused on a re-run with the same configuration; an
    unfinished one is renamed ``jobs-<N>.interrupted-<stamp>`` (never deleted) and run again. The report is
    ``<out>/tune-jobs.json`` and ``.md`` (``agentprov-tune-jobs/0.1``). Exit 0 with a recommendation, else 1."""
    import copy
    from datetime import UTC, datetime

    from agentprov.cli.live import tune
    from agentprov.cli.live.envs import agentprov_home
    from agentprov.corpus.layout import partial_dir
    from agentprov.presets import check_host, corpus_json, local_concurrency, preset_record

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path(os.path.abspath(args.tune_out)) if args.tune_out else \
        agentprov_home(ctx.env) / "calibration" / f"tune-jobs-{stamp}"
    (out / "arms").mkdir(parents=True, exist_ok=True)
    source = str(args.source)
    config_digest = str(execute_kw["config_digest"])
    user_stagger = args.start_stagger
    mismatches = check_host(preset, host)
    base = copy.copy(args)
    base.max_attempts = args.max_attempts or 2  # D-820: the sample is small; a third attempt would mostly add time
    arms: list[dict[str, Any]] = []
    reused: list[int] = []
    stop: str | None = None
    warmed = False

    def plan_for(n: int) -> Any:
        return local_concurrency(preset, facts, host=host, server_max_concurrency=args.server_max_concurrency,
                                 jobs_override=n)

    def run_into(corpus: Path, corpus_id: str, n: int, *, limit: int | None, measure: Any) -> CommandResult:
        arm_args = copy.copy(base)
        arm_args.corpus, arm_args.limit = str(corpus), limit
        arm_args.canary = 1 if limit is not None else args.canary
        arm_args.start_stagger = user_stagger if user_stagger is not None else preset.start_stagger_per_worker_s * n
        rec = corpus_json(preset_record(preset, plan_for(n), start_stagger_s=user_stagger, host_mismatches=mismatches))
        return _execute(ctx, arm_args, CommandResult(), **execute_kw, jobs=n, corpus_id=corpus_id, preset=rec,
                        on_done=measure)

    for n in args.tune_values:
        if stop is not None:
            arms.append(tune.skipped(n, stop))
            continue
        if n > plan_for(n).j_memory:
            arms.append(tune.skipped(n, "memory"))
            result.notices.append(f"arm jobs={n} skipped: above J_memory {plan_for(n).j_memory} (D-820)")
            continue
        arm_file = out / "arms" / f"jobs-{n}.json"
        done = tune.read_arm(arm_file, config_digest)
        if done is not None:
            arms.append(done)
            reused.append(n)
            result.notices.append(f"arm jobs={n}: reused from {arm_file.name} (a re-run of the same configuration)")
        else:
            corpus = out / f"jobs-{n}"
            for old in (corpus, partial_dir(corpus)):
                if old.exists():  # an unfinished arm's wall time is lost: kept aside, measured again (D-820)
                    old.rename(old.with_name(f"{old.name}.interrupted-{stamp}"))
            if not warmed:  # D-820: the model is loaded and the prefix cache warm before the first measured arm
                run_into(out / f"warmup-{stamp}", f"{source}-tune-warmup", 1, limit=1, measure=None)
                warmed = True
            measured: dict[str, Any] = {}

            def measure(campaign: Any, wall_s: float, n: int = n, measured: dict[str, Any] = measured) -> None:
                measured["arm"] = tune.arm_metrics(n, wall_s=wall_s, counters=campaign.counters,
                                                   entries=list(campaign.ledger.entries), read_log=campaign._stored_log,
                                                   limits=campaign.pipeline.limits)
                measured["stops"] = [*campaign.canary_stop, *([campaign.config_stop] if campaign.config_stop else []),
                                     *([campaign.cap_stop] if campaign.cap_stop else [])]

            arm_result = run_into(corpus, f"{source}-tune-j{n}", n, limit=None, measure=measure)
            arm = dict(measured.get("arm") or tune.skipped(n, "no_measurement"))
            arm["above_server_limit"] = n > plan_for(n).j_server
            arm["corpus"] = {"id": f"{source}-tune-j{n}", "exit_code": arm_result.exit_code}
            if measured.get("stops"):
                arm["stopped"] = [safe_text(str(s), 300) for s in measured["stops"]]
                stop = "after_campaign_stop"
            tune.write_arm(arm_file, config_digest, arm)
            arms.append(arm)
        if stop is None and tune.stops_sweep(arms[-1]):
            stop = "after_timeouts"
    agent = execute_kw["agent"]
    local = execute_kw.get("local_record") or {}
    step = gitinfo.build_step("run")
    header = {
        "software": {"agentprov_version": step.agentprov_version, "git_commit": step.git_commit,
                     "git_tree_clean": step.git_tree_clean},
        "preset": {"name": preset.name, "version": preset.version, "data_sha256": preset.data_sha256,
                   "calibrated": preset.calibrated},
        "host": {"os_family": host.os_family, "arch": host.arch, "machine": host.machine, "cpu_count": host.cpu_count,
                 "memory_bytes": host.memory_bytes, "mismatches": [m.to_json() for m in mismatches]},
        "endpoint": {"name": agent.get("endpoint"), "server": (local.get("server") or {}).get("kind"),
                     "server_version": (local.get("server") or {}).get("version"),
                     "server_max_concurrency": plan_for(1).j_server},
        "model": {"id": agent.get("model_requested"), "identity_sha256": local.get("identity_sha256"),
                  "facts": facts.to_json()},
        "sample": {"plan_sha256": execute_kw["plan"]["plan_sha256"], "default": bool(args.tune_default_sample),
                   "cells": [str(c["cell_key"]) for c in execute_kw["cells"]], "repeats": execute_kw["repeats"],
                   "max_attempts": base.max_attempts},
        "run": {"llm_element": agent.get("llm_element"), "request_timeout_s": preset.request_timeout_s,
                "start_stagger_per_worker_s": preset.start_stagger_per_worker_s if user_stagger is None else None,
                "start_stagger_s": user_stagger, "cell_timeout_s": float(args.cell_timeout or DEFAULT_CELL_TIMEOUT_S)},
        "config_digest": config_digest, "order": list(args.tune_values), "warm_up": warmed, "reused_arms": reused,
        "test_only": execute_kw.get("script") is not None, "written_at": stamp,
    }
    doc = tune.report_document(header=header, arms=arms)
    js, md = tune.write_report(out, doc)
    rec = doc["recommendation"]
    result.corpus = {"content_digest": None, "corpus_id": None, "root": redact_personal(str(out)), "state": "working"}
    result.counters = {"arms": len(arms), "ran": sum(a.get("status") == "ran" for a in arms),
                       **({"recommended_jobs": rec["jobs"]} if rec["jobs"] is not None else {})}
    for line in tune.report_markdown(doc).splitlines()[4:]:
        result.output(line)
    result.info(f"agentprov run: sweep report {redact_personal(str(js))} and {md.name}")
    for notice in result.notices:
        result.info(f"notice: {safe_text(notice, 400)}")
    if rec["jobs"] is None:
        result.error("agentprov run: the sweep found no arm that qualifies (D-821): no recommendation")
    result.exit_code = 0 if rec["jobs"] is not None else 1
    return result


# --------------------------------------------------------------------------------------------------------------
# D-652: the backend's catalogue (suites, tasks, attacks) for a plan's selection
# --------------------------------------------------------------------------------------------------------------

CATALOGUE_FORMAT: Final = "agentprov-backend-catalogue/0.1"
#: Bounds on the worker's catalogue reply (untrusted T2 output): names are labels, never paths or text.
_CATALOGUE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+-]{0,199}")  # no "/", no leading "."
_CATALOGUE_MAX_ITEMS: Final = 10_000
_CATALOGUE_OPTION = re.compile(r"--[a-z][a-z0-9-]{0,62}")  # attacks[].needs: run options, not labels


def _catalogue_names(value: Any, what: str) -> list[str]:
    if not isinstance(value, list) or len(value) > _CATALOGUE_MAX_ITEMS:
        raise LiveEnvironmentError(f"the backend worker sent a malformed catalogue ({what})", code="backend.protocol")
    if not all(isinstance(v, str) and _CATALOGUE_NAME.fullmatch(v) for v in value):
        raise LiveEnvironmentError(f"the backend worker sent a malformed catalogue ({what})", code="backend.protocol")
    return [str(v) for v in value]


def _catalogue_options(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 32 or not all(
            isinstance(v, str) and _CATALOGUE_OPTION.fullmatch(v) for v in value):
        raise LiveEnvironmentError("the backend worker sent a malformed catalogue (attack.needs)", code="backend.protocol")
    return [str(v) for v in value]


def checked_catalogue(document: Any, backend: str, root: Path | None = None) -> dict[str, Any]:
    """The worker's ``catalogue_ok.catalogue``, rebuilt from its checked members only (unknown members are dropped).
    A defence's ``provider`` and ``aux_llm`` must be values the repository's defence registry uses (F-15: read from
    ``defences.toml`` under ``root``, by default this checkout)."""
    def bad(what: str) -> LiveEnvironmentError:
        return LiveEnvironmentError(f"the backend worker sent a malformed catalogue ({what})", code="backend.protocol")

    if not isinstance(document, dict) or document.get("format") != CATALOGUE_FORMAT:
        raise bad("format")
    if document.get("backend") != backend:
        raise bad("backend")
    version = document.get("benchmark_version")
    if not isinstance(version, str) or not _CATALOGUE_NAME.fullmatch(version):
        raise bad("benchmark_version")
    suites_raw, attacks_raw = document.get("suites"), document.get("attacks")
    if not isinstance(suites_raw, list) or not isinstance(attacks_raw, list) or len(suites_raw) > 1000 \
            or len(attacks_raw) > 1000:
        raise bad("lists")
    suites = []
    for s in suites_raw:
        if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not _CATALOGUE_NAME.fullmatch(s["name"]):
            raise bad("suite")
        chars = s.get("tool_definition_chars")
        if chars is not None and (not isinstance(chars, int) or isinstance(chars, bool) or not 0 <= chars < 2**31):
            raise bad("suite.tool_definition_chars")
        suites.append({"name": s["name"], "user_tasks": _catalogue_names(s.get("user_tasks"), "user_tasks"),
                       "injection_tasks": _catalogue_names(s.get("injection_tasks"), "injection_tasks"),
                       "tool_definition_chars": chars})
    attacks = []
    for a in attacks_raw:
        if not isinstance(a, dict) or not isinstance(a.get("name"), str) or not _CATALOGUE_NAME.fullmatch(a["name"]) \
                or not isinstance(a.get("dos"), bool):
            raise bad("attack")
        refused = a.get("refused")
        if refused is not None and not isinstance(refused, str):
            raise bad("attack.refused")
        attacks.append({"name": a["name"], "dos": a["dos"],
                        "refused": None if refused is None else safe_text(refused, 400),
                        "needs": _catalogue_options(a.get("needs", []))})
    defences = []
    defences_raw = document.get("defences", [])  # D-670: absent from a worker built before it
    if not isinstance(defences_raw, list) or len(defences_raw) > 1000:
        raise bad("defences")
    providers: frozenset[str] = frozenset()
    aux_values: frozenset[str] = frozenset()
    if defences_raw:
        from agentprov.cli.live import envs
        from agentprov.cli.live.defences import registry_values

        try:
            providers, aux_values = registry_values(root if root is not None else envs.repository_root())
        except ValueError as exc:
            raise LiveEnvironmentError(f"the defence registry cannot be read to check the catalogue ({exc})",
                                       code="backend.protocol") from None
    for d in defences_raw:
        if not isinstance(d, dict) or not isinstance(d.get("name"), str) or not _CATALOGUE_NAME.fullmatch(d["name"]):
            raise bad("defence")
        refused = d.get("refused")
        if refused is not None and not isinstance(refused, str):
            raise bad("defence.refused")
        provider, aux, licence = d.get("provider"), d.get("aux_llm"), d.get("licence")
        if provider not in providers or aux not in aux_values \
                or not isinstance(licence, str) or not _CATALOGUE_NAME.fullmatch(licence):
            raise bad("defence.provider")
        cost = d.get("cost", {})
        if not isinstance(cost, dict) or not all(isinstance(k, str) and _CATALOGUE_NAME.fullmatch(k) and isinstance(
                v, int | float) and not isinstance(v, bool) and 0 <= v < 1000 for k, v in cost.items()):
            raise bad("defence.cost")
        defences.append({"name": d["name"], "title": safe_text(str(d.get("title", "")), 200), "provider": provider,
                         "licence": licence, "refused": None if refused is None else safe_text(refused, 400),
                         "needs": _catalogue_options([str(n).split(" ", 1)[0] for n in d.get("needs", [])
                                                      if isinstance(n, str)]),
                         "suites": _catalogue_names([s for s in d.get("suites", []) if s != "*"], "defence.suites")
                         + (["*"] if "*" in (d.get("suites") or []) else []),
                         "aux_llm": aux, "cost": {k: float(v) for k, v in cost.items()}})
    return {"format": CATALOGUE_FORMAT, "backend": backend, "benchmark_version": version,
            "benchmark_versions": _catalogue_names(document.get("benchmark_versions"), "benchmark_versions"),
            "suites": suites, "attacks": attacks, "defences": defences}


def _profile_refusals(document: dict[str, Any], capability: Any) -> None:
    """A defence the live profile does not allow is refused in the catalogue as ``run`` refuses it (D-677: profiles
    v1 allow none), so the GUI never offers what T0 would refuse."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import BACKENDS
    from agentprov.cli.live.defences import allowed_defences

    allowed = allowed_defences(_live_table(capability))
    profile = load_profile(BACKENDS[str(capability.backend)].profile)
    for d in document.get("defences", []):
        if d["name"] not in allowed and d["refused"] is None:
            d["refused"] = f"not allowed by the live profile {profile.id} v{profile.version} (D-677)"


def checked_any_catalogue(document: Any, backend: str, root: Path | None = None) -> dict[str, Any]:
    """Dispatch on ``format``: ``agentprov-inspect-catalogue/0.1`` (D-663, an Inspect backend) or the AgentDojo-family
    ``agentprov-backend-catalogue/0.1`` (D-652). Either check rebuilds the document from its checked members only."""
    from agentprov.cli.live.inspect_catalogue import INSPECT_CATALOGUE_FORMAT, checked_inspect_catalogue

    if isinstance(document, dict) and document.get("format") == INSPECT_CATALOGUE_FORMAT:
        return checked_inspect_catalogue(document, backend)
    return checked_catalogue(document, backend, root)


def _catalogue(ctx: Context, args: argparse.Namespace) -> CommandResult:
    """``run SOURCE --catalogue``: one worker, offline and without keys (as for hello and plan), answers hello and
    ``catalogue``. Read-only: the worker's scratch directory is a temporary directory outside ``$AGENTPROV_HOME``."""
    import shutil
    import tempfile

    from agentprov.cli.live import envs
    from agentprov.cli.live.worker import BackendWorker, WorkerDied, WorkerSpec, WorkerTimeout, worker_environment
    from agentprov.io.canonical import jcs_bytes

    result = CommandResult(dry_run=True)
    source = str(args.source)
    capability = _live_capability(source, result, scripted=True)  # no model call: the gate admits it like a scripted run
    root = envs.repository_root()
    project = envs.backend_project(str(capability.backend), root)
    home = envs.agentprov_home(ctx.env)
    env = envs.env_dir(project, home)
    marker = envs.read_marker(env)
    if marker is None:
        raise LiveEnvironmentError(f"the backend environment {project.env_name} is not built; run "
                                   f"'agentprov backends build {project.backend}'", code="backend.unavailable")
    nltk_data = envs.check_nltk(env, marker)
    identity = envs.compute_identity(env, project)
    envs.check_against_marker(identity, marker, project)
    envs.check_dataset(env, project, marker)  # an Inspect environment's pinned dataset (D-663); nothing otherwise
    expect = identity.expect(project.commit)
    argv = [str(envs.env_python(env)), "-I", "-B", "-m", envs.backend_kind(project.backend).worker_module]
    scratch = Path(tempfile.mkdtemp(prefix="agentprov-catalogue-"))
    t2 = scratch / "home"
    t2.mkdir(mode=0o700)
    environment = worker_environment(home=t2, key_variables={}, block_network=True, nltk_data=nltk_data)
    worker = BackendWorker(WorkerSpec(argv=argv, env=environment, cwd=scratch, stderr_path=scratch / "worker.stderr.log"))
    try:
        worker.start()
        _hello(worker, identity, marker, expect, project.backend)
        fields: dict[str, Any] = {"req": "catalogue"}
        if args.benchmark_version is not None:
            fields["benchmark_version"] = str(args.benchmark_version)
        try:
            reply = worker.request("catalogue", ("catalogue_ok", "catalogue_refused"), 300.0, **fields)
        except (WorkerDied, WorkerTimeout) as exc:
            if "ProtocolError" in str(exc):  # a worker built before D-652 answers the unknown op with fatal
                raise _unsupported("the catalogue of this backend environment", source, (
                    f"The environment {project.env_name} was built before 'run --catalogue' existed (D-652). Rebuild "
                    f"it with 'agentprov backends build {project.backend}' (offline when the uv cache holds its "
                    "wheels).",)) from None
            raise LiveEnvironmentError(f"the backend worker did not answer catalogue: {exc}",
                                       code="backend.unavailable") from None
        if reply["op"] == "catalogue_refused":
            error_raw = reply.get("error")
            error: dict[str, Any] = error_raw if isinstance(error_raw, dict) else {}
            raise CliUsageError(f"agentprov run: the backend refused the catalogue: "
                                f"{safe_text(str(error.get('message', '')), 300)}")
        document = checked_any_catalogue(reply.get("catalogue"), project.backend, root)
        _profile_refusals(document, capability)
    finally:
        worker.shutdown()
        shutil.rmtree(scratch, ignore_errors=True)
    if "tasks" in document:  # agentprov-inspect-catalogue/0.1 (D-663)
        result.counters = {"tasks": len(document["tasks"]),
                           "samples": sum(sp["samples"] for t in document["tasks"] for sp in t["splits"]),
                           "judge_roles": len({r["role"] for t in document["tasks"] for sc in t["scorers"]
                                               for r in sc["judge_roles"]})}
        result.output(f"catalogue of {project.env_name} (inspect_ai {document['inspect_ai']}): "
                      f"{result.counters['tasks']} task(s), {result.counters['samples']} sample(s) over all splits, "
                      f"{result.counters['judge_roles']} judge role(s)")
    else:
        result.counters = {"suites": len(document["suites"]), "attacks": len(document["attacks"]),
                           "user_tasks": sum(len(s["user_tasks"]) for s in document["suites"]),
                           "injection_tasks": sum(len(s["injection_tasks"]) for s in document["suites"])}
        result.output(f"catalogue of {project.env_name} for {document['benchmark_version']}: {result.counters['suites']} "
                      f"suite(s), {result.counters['attacks']} attack(s)")
    result.notices.append("catalogue: hello and catalogue only; no model call and nothing written (D-652)")
    result.payload = jcs_bytes(document) + b"\n"
    return result


def _preflight(argv: list[str], env_for: Any, identity: Any, marker: Any, expect: dict[str, Any],
               agent: Mapping[str, Any], home: Path, script: bytes | None, redactor: Any,
               result: CommandResult, backend: str | None = None) -> dict[str, Any]:
    import shutil
    import uuid

    from agentprov.cli.live.worker import make_private_dir

    session_dir = make_private_dir(home / "staging" / f"probe-{uuid.uuid4().hex}")
    t2home = make_private_dir(home / "t2home" / session_dir.name)
    if script is not None:
        (session_dir / SCRIPT_LABEL).write_bytes(script)
    try:
        results = _run_probe(argv, env_for(t2home), identity, marker, expect, agent, session_dir, redactor,
                             backend)
    finally:
        shutil.rmtree(t2home, ignore_errors=True)
    shutil.rmtree(session_dir, ignore_errors=True)
    result.notices.append("preflight probe: its capture session was written to staging and removed (never mapped, D.10.9)")
    return results


def _dry_run_live(args: argparse.Namespace, result: CommandResult, cells: list[dict[str, Any]], plan: Mapping[str, Any],
                  config_digest: str, repeats: int, corpus_id: str | None, project: Any) -> CommandResult:
    """N.1.6 run --dry-run: the plan, its digests and the resume state; nothing written, no model call. The resume
    state is counted by the campaign's own rules (:func:`_resume_state`), so the counters equal the real run's."""
    resume = _resume_state(args, cells, config_digest, repeats)
    result.counters = {"cells_planned": resume.units, "cells_done_before": resume.settled}
    if args.plan_json:
        result.payload = _plan_json(args, cells, plan, config_digest, repeats, corpus_id, project, resume)
    result.output(f"plan {plan['plan_sha256'][:16]}...: {len(cells)} cell(s) x {repeats} repeat(s); corpus "
                  f"{safe_text(str(corpus_id), 80)}; backend {project.env_name}")
    result.output(f"  config digest {config_digest[:23]}...; {resume.settled} unit(s) already settled; up to "
                  f"{resume.attempts_due} attempt(s) due (--max-attempts {resume.max_attempts})")
    for cell in cells[:20]:
        result.output(f"  cell {safe_text(cell['cell_key'], 200)}")
    if len(cells) > 20:
        result.output(f"  ... and {len(cells) - 20} more")
    result.notices.append("dry run: hello and plan only; no model call and nothing written (N.1.6)")
    return result


PLAN_JSON_FORMAT: Final = "agentprov-run-dry-plan/0.1"
_PLAN_CELL_FIELDS: Final = ("cell_key", "suite", "user_task_id", "injection_task_id", "attack", "kind")


def _plan_json(args: argparse.Namespace, cells: list[dict[str, Any]], plan: Mapping[str, Any], config_digest: str,
               repeats: int, corpus_id: str | None, project: Any, resume: ResumeState) -> bytes:
    """D-651: the dry run's plan as one JCS document (``agentprov-run-dry-plan/0.1``). One row per cell with its
    identifiers and how many of its ``repeats`` units are already settled, counted by the campaign's rules
    (:func:`_resume_settled`); the totals equal the dry-run counters. Every string is escaped (worker output)."""
    from agentprov.io.canonical import jcs_bytes

    settled = _resume_settled(args, cells, config_digest, repeats)
    rows = []
    for cell in cells:
        row: dict[str, Any] = {}
        for name in _PLAN_CELL_FIELDS:
            value = cell.get(name)
            row[name] = None if value is None else safe_text(str(value), 200)
        row["settled"] = settled.get(str(cell["cell_key"]), 0)
        if isinstance(cell.get("sample_ids"), list):  # an Inspect cell (D-770): its task and how many samples it runs
            row["task"] = safe_text(str(cell.get("task") or ""), 200)
            row["samples"] = len(cell["sample_ids"])
        rows.append(row)
    document = {
        "format": PLAN_JSON_FORMAT, "plan_sha256": plan["plan_sha256"], "config_digest": config_digest,
        "backend": project.backend, "corpus_id": None if corpus_id is None else safe_text(str(corpus_id), 80),
        "benchmark_version": safe_text(str((plan.get("backend_config") or {}).get("benchmark_version") or ""), 80),
        "repeats": repeats, "max_attempts": resume.max_attempts, "units": resume.units, "settled": resume.settled,
        "attempts_due": resume.attempts_due, "cells": rows,
    }  # fmt: skip
    inspect = _plan_json_inspect(plan.get("backend_config") or {})
    if inspect is not None:
        document["inspect"] = inspect
    return jcs_bytes(document) + b"\n"


def _plan_json_inspect(config: Mapping[str, Any]) -> dict[str, Any] | None:
    """D-770: what the estimate needs of an Inspect plan (the worker's ``backend_config``, labels escaped): the task,
    epochs, the message limit, the sample concurrency and each judge role's model. ``None`` for any other backend."""
    if not isinstance(config.get("task"), str):
        return None

    def count(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else None

    raw_limits, raw_judges = config.get("limits"), config.get("judges")
    limits: Mapping[str, Any] = raw_limits if isinstance(raw_limits, Mapping) else {}
    judges: Mapping[str, Any] = raw_judges if isinstance(raw_judges, Mapping) else {}
    return {"task": safe_text(config["task"], 200), "epochs": count(config.get("epochs")) or 1,
            "message_limit": count(limits.get("message_limit")),
            "max_connections": count(config.get("max_connections")) or 1,
            "judges": {safe_text(str(role), 64): safe_text(str(j.get("model_requested") or ""), 200)
                       for role, j in sorted(judges.items()) if isinstance(j, Mapping)}}


def _read_json(path: Path) -> dict[str, Any] | None:
    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    try:
        data = strict_json_loads(path.read_bytes())
    except (OSError, IngestError):
        return None
    return data if isinstance(data, dict) else None


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


def _execute(ctx: Context, args: argparse.Namespace, result: CommandResult, *, capability: Any, project: Any,
             home: Path, marker: Mapping[str, Any], identity: Any, expect: dict[str, Any], argv: list[str],
             env_for: Any, agent: Mapping[str, Any], plan: Mapping[str, Any], cells: list[dict[str, Any]],
             config_digest: str, repeats: int, corpus_id: str, script: bytes | None, redactor: Any,
             sandbox: dict[str, Any] | None, jobs: int, hello: Mapping[str, Any], egress: Any = None,
             cache: AttackCache | None = None, local_record: Mapping[str, Any] | None = None,
             observe_local: Any = None, budget: Any = None, endpoint_kind: str | None = None,
             preset: Mapping[str, Any] | None = None, on_done: Any = None) -> CommandResult:
    """One campaign into ``args.corpus``. ``preset``: the producer block's ``preset`` record (N.2.1a(2)); ``on_done``:
    called as ``on_done(campaign, wall_s)`` after the campaign ran, before the corpus closes (the sweep's arm
    measurement, D-820)."""
    import time

    from agentprov.adapters.registry import BACKENDS
    from agentprov.adapters.runner.session import LiveSessionPipeline, check_live_identity
    from agentprov.cli.live.campaign import Campaign
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits
    from agentprov.io.canonical import sha256_hex

    final = _final_dir(args.corpus)
    for guarded in (home / "envs", home / "staging", home / "t2home"):
        if _inside(final, guarded) or _inside(guarded, final):
            raise LiveRefused("the corpus directory overlaps the backend environments or live staging (G2)",
                              code="cli.refused.guard")
    descriptor = BACKENDS[str(capability.backend)]
    snapshot_id = str(capability.part)
    test_only = script is not None
    limits = IngestLimits()
    with CorpusWriter(final, limits=limits, command="run", break_stale_lock=bool(args.break_stale_lock),
                      build_step=gitinfo.build_step("run")) as writer:
        pipeline = LiveSessionPipeline(writer, source_id=str(args.source), part=str(capability.part),
                                       profile_id=descriptor.profile, corpus_id=corpus_id, snapshot_id=snapshot_id,
                                       workers=0, limits=limits, progress=ctx.progress,
                                       prov_conformance=not args.skip_prov_conformance,
                                       native_log=descriptor.native_log)  # D-666: an Inspect .eval session
        if args.skip_prov_conformance:
            result.notices.append("--skip-prov-conformance: the W3C PROV conformance check (tier 4) was not run; the "
                                  "corpus is marked unvalidated until a full 'recompute --out NEW' (G2c-5)")
        try:
            manifest = check_live_identity(writer, pipeline)
            if cache is not None:  # D.11.3 rule 5: the verified bytes enter the raw store first, with their pinned origin
                writer.add_object(cache.verified.data, cache.verified.origin, ext="json")
            ledger = _load_ledger(manifest, writer.store)
            before = (manifest or {}).get("live") or {}
            mixed = sorted({str(e.get("config_digest")) for e in ledger.entries} - {config_digest})
            if mixed and not args.allow_mixed_config:
                raise LiveRefused("the working corpus holds sessions of another live configuration (G5); pass "
                                  "--allow-mixed-config to add this one (recorded)", code="cli.refused.mixed_config")
            if before and bool(before.get("test_only")) != test_only:
                raise LiveRefused("scripted (test_only) and real-model sessions never share a corpus (H.1.1(2))",
                                  code="cli.refused.mixed_config")
            campaign = Campaign(
                pipeline=pipeline, writer=writer, argv=argv, env_for=env_for, identity=identity, marker=marker,
                expect=expect, home=home, agent=agent, plan=plan, config_digest=config_digest, jobs=jobs,
                start_stagger=args.start_stagger or 0.0, cell_timeout=args.cell_timeout or DEFAULT_CELL_TIMEOUT_S,
                max_attempts=args.max_attempts or DEFAULT_MAX_ATTEMPTS, retry_inconsistent=bool(args.retry_inconsistent),
                repeats=repeats, canary=DEFAULT_CANARY if args.canary is None else args.canary, limit=args.limit,
                script=script, redactor=redactor, snapshot_id=snapshot_id, ledger=ledger, progress=ctx.progress,
                keep_staging=bool(args.keep_staging), backend=project.backend,
                attack_staging=cache.staging() if cache is not None else None,
                observe_local=observe_local, accepted_served=tuple(args.accept_served_model or ()), budget=budget,
            )  # fmt: skip
            config_digests = sorted({*before.get("config_digests", ()), config_digest})

            def live_block() -> dict[str, Any]:
                return {
                    "backend": project.backend, "env_name": project.env_name,
                    "backend_lock_sha256": "sha256:" + project.lock_sha256,
                    "benchmark": {k: hello["identity"].get(k) for k in ("distribution", "version_reported", "source",
                                                                          "record_digest", "benchmark_version")},
                    "llm_element": agent.get("llm_element"), "transport": agent.get("transport"),
                    "model_requested": agent.get("model_requested"), "endpoint": agent.get("endpoint"),
                    "test_only": test_only,
                    "llm_script_sha256": None if script is None else "sha256:" + sha256_hex(script),
                    "plan_sha256": plan["plan_sha256"], "config_digests": config_digests,
                    "mixed_config": len(config_digests) > 1,
                    "allow_custom_endpoint": bool(args.allow_custom_endpoint),
                    "temperature_policy": args.temperature_policy,
                    "allow_text_tool_calls": bool(args.allow_text_tool_calls),
                    "jobs": jobs, "start_stagger_ms": int(round((args.start_stagger or 0.0) * 1000)),
                    "cell_timeout_s": int(args.cell_timeout or DEFAULT_CELL_TIMEOUT_S),
                    "max_attempts": args.max_attempts or DEFAULT_MAX_ATTEMPTS, "repeats": repeats,
                    "instrumentation": sorted({i for q in campaign.qualities for i in q.instrumentation}
                                              | set(before.get("instrumentation", ()))),
                    "sessions": sorted(campaign.ledger.entries, key=lambda e: str(e.get("session"))),
                    "quality": campaign.report(),
                    "partial": args.limit is not None or bool(campaign.canary_stop) or bool(campaign.cap_stop)
                    or bool(campaign.config_stop),
                    # D.11.3 rule 5: per configuration digest, the verified cache, its pinned origin and fall-backs
                    "attack_caches": {**dict(before.get("attack_caches") or {}),
                                      **({config_digest: cache.record()} if cache is not None else {})},
                    # D-693/D-694: per configuration digest, the local model's observed identity before the run, and
                    # the served model ids the operator accepted (A12)
                    "local_models": {**dict(before.get("local_models") or {}),
                                     **({config_digest: dict(local_record)} if local_record is not None else {})},
                    "accepted_served_models": sorted({*before.get("accepted_served_models", ()),
                                                      *(args.accept_served_model or ())}),
                    # D-664: the egress proxy's allowlist and counts (never a payload); null without the proxy
                    "egress": egress.summary() if egress is not None else None,
                    # D-721 / D-725: present only for real-model runs and capped runs (scripted manifests unchanged)
                    **({"endpoint_class": endpoint_kind} if endpoint_kind is not None else {}),
                    **({"caps": budget.record()} if budget is not None else {}),
                }

            def write_documents() -> None:
                pipeline.write_documents(live_block(), producer_extra={"sandbox": sandbox,
                                                                       **({"preset": preset} if preset else {})})

            started = time.monotonic()
            try:
                campaign.run(cells, write_documents=write_documents)
            finally:
                write_documents()
            if on_done is not None:
                on_done(campaign, time.monotonic() - started)
        finally:
            pipeline.close()
    return _live_result(result, campaign, corpus_id, writer)


def _live_result(result: CommandResult, campaign: Any, corpus_id: str, writer: Any) -> CommandResult:
    c = campaign.counters
    result.counters = dict(c)
    result.issues_by_code = dict(sorted(campaign.pipeline.issues.items()))
    result.failures = list(campaign.pipeline.failures)
    result.notices.extend(campaign.notices)
    result.corpus = {"content_digest": None, "corpus_id": corpus_id, "root": redact_personal(str(writer.partial)),
                     "state": "working"}
    if campaign.canary_stop:
        for condition in campaign.canary_stop:
            result.notices.append(f"canary stop: {condition}")
        result.error("agentprov run: the canary found a misconfiguration; the campaign stopped after the canary cells "
                     "(re-run the same command to resume once the cause is fixed or accepted)")
    if campaign.config_stop:
        result.notices.append(f"setup refusal: {safe_text(campaign.config_stop, 400)}")
        result.error("agentprov run: a cell's setup refused this configuration, so no further cell was started (every "
                     "one would fail the same way); fix the option the refusal names and re-run the same command")
    if campaign.cap_stop:
        result.notices.append(f"cap stop: {campaign.cap_stop}")
        result.error(f"agentprov run: {campaign.cap_stop.split(':', 1)[0]}: no further cell was started (D-725); raise "
                     "the cap to resume")
    report = campaign.report()
    for model, facts in report["models"].items():
        result.info(f"quality [{safe_text(model, 80)}]: sessions {facts['sessions']}, statuses "
                    f"{json.dumps(facts['statuses'], sort_keys=True)}, kept calls {facts['kept_calls']}, retries "
                    f"{facts['retries']}, abnormal finish {facts['abnormal_finish']}, text tool calls "
                    f"{facts['text_tool_call_suspect']}, parameters not transmitted {facts['param_not_transmitted']}")
    result.info(f"agentprov run: {c['attempted']} attempt(s); {c['conclusive']} conclusive, {c['inconsistent']} "
                f"inconsistent, {c['inconclusive']} inconclusive; {c['derived']} derived, {c['failed']} failed; "
                f"{c['cells_done_before']} of {c['cells_planned']} unit(s) done before")
    for notice in result.notices:
        result.info(f"notice: {safe_text(notice, 400)}")
    bad = (c["inconclusive"] or c["inconsistent"] or c["failed"] or c["quarantined"] or campaign.canary_stop
           or c["rejected_files"] or campaign.cap_stop or campaign.config_stop)
    result.exit_code = 1 if bad else 0
    return result
