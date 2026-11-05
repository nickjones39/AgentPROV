"""Command forms (design Appendix A) and the job specification built from them (design §3 "Write", §8.4). No Qt.

A form is a declarative table of fields, each mapped to one CLI option (or a positional). A :class:`JobSpec` is the
exact argv a form produces, with its **risk tier computed from the final argv** (not from the form), so an option typed
into "additional options" still raises the tier:

* R0 read-only; R1 writes local data; R2 network or paid model calls (``--allow-network``, ``--fetch``,
  ``--i-consent-*``); R3 publishing does not exist (no command uploads).
* ``purge`` is R1 and destructive: the confirmation asks for the object's first 8 hex digits, then ``--yes`` is added.

The GUI never adds ``--show-content`` (S2: content is shown from the read model) and never the option that reads an environment file (S7). The
global options every job gets (progress, log and summary files in the job directory, ``--no-colour``) are added by the
job manager, not here.

:data:`LOOKS` says how Runs › New Job shows each form (D-1060: sections, plain labels, captions, modes, what sits under
Advanced). It is presentation only and never changes the argv a form produces.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

__all__ = [
    "COMMON_LOOKS",
    "CONFORMANCE_OPTION",
    "FORMS",
    "GLOBAL_LOOKS",
    "LOOKS",
    "TIERS",
    "CommandForm",
    "Field",
    "FormError",
    "FormLook",
    "JobSpec",
    "Look",
    "Mode",
    "Segment",
    "build_spec",
    "has_form_words",
    "resume_spec",
    "tier_of_argv",
]

TIERS: Final = ("R0", "R1", "R2")
#: G2c-5: the CLI option that skips tier 4 (the W3C PROV conformance check). Detected per command from ``--help``,
#: because it lands in steps (derive, validate and verify first; the import stage after D-414).
CONFORMANCE_OPTION: Final = "--skip-prov-conformance"
#: Options the GUI never passes (S2, S7) and the reason shown when they are typed.
REFUSED_OPTIONS: Final[Mapping[str, str]] = {
    "--show-content": "content is shown only by the viewer, under S2",
    "--log-content": "content never goes to job logs (S2)",
    "--env-file": "the GUI never reads or passes .env (S7)",  # S7: refused
    "--progress-file": "set by the job manager",
    "--log-file": "set by the job manager",
    "--summary-json": "set by the job manager",
    "--json": "the summary is read from the job directory",
    CONFORMANCE_OPTION: "use the PROV conformance box (§8.3a)",  # GR-2: the box is the only route to the skip
    "--control-file": "set by the job manager (D-394)",
}
#: D-654: options the GUI sets itself, per command ("*" = every command), with where it sets them.
MANAGED_OPTIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "*": {"--progress": "job manager (status)", "--progress-format": "job manager", "--progress-file": "job manager",
          "--log-file": "job manager", "--summary-json": "job manager", "--no-colour": "job manager",
          "--control-file": "job manager, when the CLI offers it (D-394)"},
    "run": {"--keychain": "Run Live: the CLI reads the endpoint key from the OS keychain itself (D-702)",
            "--i-consent-to-api-costs": "Run Live: added only after the consent tick (§8.3)",
            "--i-consent-to-local-run": "Run Live: after the consent tick, for a local endpoint (D-726)",
            "--catalogue": "Run Live: the attack and task lists (D-652)",
            CONFORMANCE_OPTION: "the PROV conformance box (§8.3a)"},
    "import": {CONFORMANCE_OPTION: "the PROV conformance box (§8.3a)"},
    "derive": {CONFORMANCE_OPTION: "the PROV conformance box (§8.3a)"},
    "recompute": {CONFORMANCE_OPTION: "the PROV conformance box (§8.3a)"},
    "purge": {"--yes": "added after the typed 8-hex confirmation (§8.4)"},
    "estimate": {"--keychain": "Run Live: the estimate's dry plan with the model's key, when the keychain holds it "
                              "and the live part admits real runs (D-701, D-702)"},
    "models": {"--keychain": "Run Live's model picker: the CLI reads the provider key from the OS keychain (D-702, D-730)"},
    "assist": {"--keychain": "Help › Assistant: the CLI reads the endpoint key from the OS keychain itself (D-702, D-1010)"},
    "keys set": {"--stdin": "Settings › Keys: the value goes on stdin from the password field (never argv)"},
    "jobs kill": {"--yes": "Runs › Force Kill: after the GUI's own confirmation"},
    "jobs prune": {"--yes": "Settings › Jobs: after the user confirms the listed jobs"},
    "devrun prune": {"--yes": "Runs › Dev Run…: devrun start prunes old runs itself; a manual prune asks first"},
    "keys delete": {"--yes": "Settings › Keys: after the GUI's own confirmation"},
    "update install": {"--confirm": "About › Download and Install…: added only after the confirmation that names the "
                                    "folder replaced and the rollback (D-1065)"},
}
#: D-654: options never reachable from the GUI, each with its reason ("*" = every command).
EXCLUDED_OPTIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "*": {"--version": "read by Settings › Installation (agentprov --version --json), not a job option",
          "--show-content": "S2: content is shown only by the viewer",
          "--log-content": "S2: content never goes to job logs",
          "--content-chars": "only with --show-content, which the GUI never sets",
          "--json": "the summary is read from the job directory (--summary-json)"},
    "run": {"--env-file": "S7: the GUI never reads or passes .env (keys come from the keychain)",  # S7: refused
            "--env-stdin": "for clients holding keys themselves; the GUI passes --keychain instead (D-702)",
            "--plan-json": "the dry-plan document; agentprov estimate makes it for the GUI (D-651, D-701)"},
    "estimate": {"--env-file": "S7: the GUI never reads or passes .env (keys come from the keychain)",  # S7: refused
                 "--env-stdin": "for clients holding keys themselves; the GUI passes --keychain instead (D-702)"},
    "models": {"--env-file": "S7: the GUI never reads or passes .env (keys come from the keychain)",  # S7: refused
               "--env-stdin": "for clients holding keys themselves; the GUI passes --keychain instead (D-702)"},
    "backends build": {"--env-file": "S7: the GUI never reads or passes .env (not read by the build)"},  # S7: refused
    "assist": {"--env-file": "S7: the GUI never reads or passes .env (keys come from the keychain)"},  # S7: refused
    "update rollback": {"--yes": "the app offers no rollback button (D-1065): the install's result shows the "
                                 "rollback command, run in a terminal (on Windows once the app has quit)"},
}
#: D-654: argparse aliases of a command the GUI reaches under its other name.
ALIASES: Final[Mapping[str, str]] = {"sources": "info", "convert": "import"}
#: D-654: options a pending decision adds to the CLI that the GUI will set itself once they exist (absent until it lands).
PENDING_MANAGED: Final[Mapping[str, Mapping[str, str]]] = {}
#: Flags that reach the network, cost money or consent to a run (R2). The live pilot's (D-725, D-726): the local-run
#: consent, and the API caps, which only an API-endpoint run carries (already R2 by its cost consent).
_R2_FLAGS: Final = ("--allow-network", "--fetch", "--i-consent-to-large-download", "--i-consent-to-api-costs",
                     "--env-stdin", "--keychain", "--i-consent-to-local-run", "--max-calls", "--max-cost-usd",
                     "--price-in", "--price-out", "--confirm-r2")
_DESTRUCTIVE: Final = ("purge",)
_SHA256: Final = re.compile(r"sha256:[0-9a-f]{64}")
_CONFORMANCE_NOTE: Final = ("PROV conformance check (tier 4) skipped: the corpus stays unvalidated until a full recompute "
                             "(--out NEW --stages sem,prov,validation) validates it")


class FormError(ValueError):
    """A form value that cannot become a valid argv (the message names the field, never data)."""


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    label: str
    kind: str  # path | dir | text | int | float | bool | choice | list | multi (a repeated option, one value each)
    option: str | None  # None: positional
    choices: tuple[str, ...] = ()
    required: bool = False
    tier: str = "R0"  # the tier this field raises the job to when it is set
    default: Any = None
    help: str = ""
    writes: bool = False  # the value names a corpus (or directory) the job writes
    advanced: bool = False  # shown under "More options" (D-654: every CLI option is reachable)
    pending: str = ""  # a decision whose CLI option may not exist in this checkout yet (shown only when --help has it)
    pending_choices: tuple[str, ...] = ()  # choices a pending decision adds to the CLI (absent until it lands)


@dataclass(frozen=True, slots=True)
class CommandForm:
    name: str
    words: tuple[str, ...]  # subcommand words: ("import",) or ("backends", "build")
    title: str
    tier: str  # base tier
    fields: tuple[Field, ...]
    writer: bool = False  # takes a corpus write (single-writer rule)
    slot: str | None = None  # a global slot (fetch, backends build) for network or environment jobs
    release_option: bool = False  # the command has --release
    prov_generating: bool = False  # runs PROV validation: the D-432 conformance box applies (§8.3a and its addendum)
    reads_corpus: str | None = None  # the field naming a corpus that is read
    tool: str | None = None  # a repository tool run with the checkout's interpreter (tools/ci_local.py), not the CLI
    menu: bool = True  # listed in Runs › New Job (run has its own Run Live dialog)


@dataclass(frozen=True, slots=True)
class JobSpec:
    """What a job will run: the subcommand argv (without the program and the global options), its tier, the corpus it
    writes (if any) and facts for the confirmation."""

    command: str
    argv: tuple[str, ...]
    tier: str
    label: str
    writes: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    slot: str | None = None
    destructive: bool = False
    release: bool = False
    notes: tuple[str, ...] = ()
    conformance_skipped: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)


def _max_tier(*tiers: str) -> str:
    return max(tiers, key=TIERS.index)


def _is_r2(name: str) -> bool:
    """GR-45: an R2 flag, or a prefix of one that an argparse allowing abbreviations (tools/ci_local.py) expands to it."""
    return name in _R2_FLAGS or (name.startswith("--") and len(name) > 2 and any(f.startswith(name) for f in _R2_FLAGS))


def tier_of_argv(argv: Sequence[str], base: str) -> str:
    """The tier of a subcommand argv: the base tier, raised by every flag that reaches the network or costs money."""
    tier = base
    for token in argv:
        name = token.split("=", 1)[0]
        if _is_r2(name):
            tier = _max_tier(tier, "R2")
        elif name in ("--out", "--report", "--break-stale-lock", "--yes") and tier == "R0":
            tier = "R1"
    if "--dry-run" in argv and tier == "R1" and not any(_is_r2(t.split("=", 1)[0]) for t in argv):
        tier = "R0"  # a dry run takes no lock and writes nothing (research §Q7)
    return tier


# ----------------------------------------------------------------------------------------------- the table
def F(key: str, label: str, kind: str, option: str | None, **kw: Any) -> Field:
    return Field(key, label, kind, option, **kw)


#: D-654: the global options a job may set (Runs › New Job › More options). Placed after the subcommand words.
GLOBAL_FIELDS: Final = (
    Field("g_verbose", "Verbose log (-v; DEBUG in the job log)", "bool", "--verbose", advanced=True),
    Field("g_quiet", "Quiet stderr (WARNING and above)", "bool", "--quiet", advanced=True),
    Field("g_log_format", "stderr log format", "choice", "--log-format", choices=("", "text", "json"), advanced=True),
    Field("g_progress_interval", "Progress heartbeat interval (seconds)", "float", "--progress-interval",
          advanced=True),
    Field("g_progress_max_bytes", "Progress file rotation size (bytes)", "int", "--progress-max-bytes", advanced=True),
    Field("g_max_listed", "Failures listed in the summary", "int", "--max-listed", advanced=True),
    Field("g_break_stale_lock", "Remove a stale lock first (writers; confirmed)", "bool", "--break-stale-lock",
          tier="R1", advanced=True),
)
_JOBS = F("jobs", "Workers (--jobs; 0 = host default)", "int", "--jobs", default=None)
_DRY = F("dry_run", "Dry run (writes nothing)", "bool", "--dry-run")
_PROV = F("prov_spec", "PROV spec", "choice", "--prov-spec", choices=("", "agentprov-prov/0.1"))
_SELECT = F("select", "Select (KEY=VALUE[,VALUE…])", "text", "--select")
_IN_PROCESS = F("in_process", "Debugging only: run the workers in this process", "bool", "--in-process", advanced=True)
_NO_VCACHE = F("no_validation_cache", "Do not use the validation cache", "bool", "--no-validation-cache", advanced=True)

#: D-1065: ``agentprov update``'s bundle platforms (``agentprov.update.releases.PLATFORMS``, which the GUI does not
#: import: it loads the fetch layer; tests/test_cli_parity.py checks the choices against the CLI's)
UPDATE_PLATFORMS: Final = ("macos-arm64", "macos-x86_64", "windows-x64", "windows-arm64", "linux-x86_64",
                           "linux-aarch64")
_UPDATE_APP = (F("bundle", "The desktop app's folder (AgentPROV.app, or the AgentPROV folder)", "dir", "--bundle"),
               F("gui_version", "The desktop app's version (X.Y.Z)", "text", "--gui-version"))
_UPDATE_PLATFORM = F("platform", "Bundle platform (default: this machine's)", "choice", "--platform",
                     choices=("", *UPDATE_PLATFORMS), advanced=True)
_UPDATE_DIR = F("dir", "Staging folder (default: $AGENTPROV_HOME/update/staging/PLATFORM)", "dir", "--dir",
                advanced=True)
_JSON = F("format", "Format", "choice", "--format", choices=("text", "json"), default="json")


def _backend_envs() -> tuple[str, ...]:
    """``backends build`` choices: the registered backends (``adapters.registry.BACKENDS``), never a fixed list."""
    from agentprov.adapters.registry import BACKENDS

    return tuple(sorted(BACKENDS))


def _live_sources() -> tuple[str, ...]:
    """The backend picker's sources (``live.backends``: a live capability with a registered backend)."""
    from agentprov_gui.live.backends import live_backends

    return tuple(b.source for b in live_backends())


#: ``run`` (design §8.1; the Run Live dialog builds it): every option of ``agentprov run`` except the ones the GUI sets
#: itself (``--env-stdin``, ``--i-consent-to-api-costs``, ``--plan-json``, ``--catalogue``: :data:`MANAGED_OPTIONS`) or
#: refuses (the environment-file option, S7). A real model (``--model`` / ``--endpoint``) without ``--dry-run`` is R2 (``--env-stdin``).
RUN_FIELDS: Final = (
    F("source", "Backend (live source)", "choice", None, choices=_live_sources(), required=True),
    F("corpus", "Working corpus (outside the repository)", "dir", "--corpus", writes=True),
    F("campaign", "Campaign name (corpus id <source>-live-<name>)", "text", "--campaign"),
    F("corpus_id", "Corpus id", "text", "--corpus-id", advanced=True),
    F("plan", "Run plan (PLAN.toml; instead of the cell options)", "path", "--plan", advanced=True),
    F("spec", "Corpus spec with [live] (deferred in this build)", "path", "--spec", advanced=True),
    F("suite", "Suites (comma list)", "text", "--suite"),
    F("benchmark_version", "Benchmark version", "text", "--benchmark-version"),
    F("user_tasks", "User tasks (all, ids, or index ranges)", "text", "--user-tasks"),
    F("attack", "Attacks (comma list)", "text", "--attack"),
    F("injection_tasks", "Injection tasks (all, ids, or index ranges)", "text", "--injection-tasks"),
    F("benign", "Benign cells", "choice", "--benign", choices=("", "include", "exclude", "only")),
    F("defence", "Defence (a registry id the live profile allows; agentdojo-live v3 allows the first set, others exit 5; D-677)", "text",
      "--defence", advanced=True),
    # D-663 (Inspect harness): the plan of an inspect-<benchmark> backend; exclusive with the cell options above
    F("task", "Inspect task (an Inspect backend's catalogue)", "text", "--task"),
    F("task_param", "Inspect task parameters (KEY=VALUE)", "multi", "--task-param", advanced=True),
    F("samples", "Inspect samples (limit:N, or ids)", "text", "--samples"),
    F("epochs", "Inspect epochs", "int", "--epochs", advanced=True),
    F("message_limit", "Inspect message limit per sample", "int", "--message-limit"),
    F("token_limit", "Inspect token limit per sample", "int", "--token-limit"),
    F("time_limit", "Inspect time limit per sample (seconds)", "int", "--time-limit"),
    F("max_connections", "Inspect concurrent model calls per cell", "int", "--max-connections", advanced=True),
    F("cell_size", "Inspect samples per cell", "int", "--cell-size", advanced=True),
    F("judge", "Inspect judges (ROLE=MODEL; the agent's endpoint and key)", "multi", "--judge"),
    F("model", "Endpoint shorthand (endpoints.toml)", "text", "--model"),
    F("endpoint", "Explicit endpoint", "choice", "--endpoint",
      choices=("", "deepseek", "openai", "openrouter", "anthropic", "local", "ollama", "omlx", "lmstudio", "mlx_lm", "llamacpp", "vllm"),
      pending_choices=("anthropic", "ollama", "omlx", "lmstudio", "mlx_lm", "llamacpp", "vllm"),
      advanced=True),  # D-656 adds anthropic, D-691 the local server shorthands, to the CLI's choices
    F("model_id", "Model id", "text", "--model-id"),
    # D-691..D-698 (local model servers): pending until the local-endpoints branch is on this checkout's base
    F("base_url", "Local server base URL (loopback, or a LAN address with the opt-in)", "text", "--base-url",
      pending="D-691", advanced=True),
    F("accept_served_model", "Accepted served model ids (A12)", "multi", "--accept-served-model", pending="D-691",
      advanced=True),
    F("no_hash_weights", "Do not hash a local model's weight files", "bool", "--no-hash-weights", pending="D-691",
      advanced=True),
    F("allow_lan_endpoint", "Allow a LAN model server (prompts leave this machine over plain http)", "bool",
      "--allow-lan-endpoint", pending="D-698", advanced=True),
    F("defence_endpoint", "Defence endpoint (a defence's own model or embedding calls; D-675)", "text",
      "--defence-endpoint", advanced=True),
    F("max_tokens", "Max tokens (Anthropic endpoints: a number or harness-default)", "text", "--max-tokens",
      pending="D-656"),
    F("max_calls", "API cap: billed model calls of the corpus at most (D-725)", "int", "--max-calls"),
    F("max_cost_usd", "API cap: spend of the corpus in USD at most (D-725)", "float", "--max-cost-usd"),
    F("price_in", "Cap pricing: USD per million input-side tokens (D-725)", "float", "--price-in"),
    F("price_out", "Cap pricing: USD per million output tokens (D-725)", "float", "--price-out"),
    F("llm_script", "Scripted transport (SCRIPT.json; no network, no keys)", "path", "--llm-script"),
    F("llm_element", "LLM element", "choice", "--llm-element", choices=("", "native", "gateway_compat"), advanced=True),
    F("model_display_name", "Model display name", "text", "--model-display-name", advanced=True),
    F("temperature", "Temperature", "float", "--temperature", advanced=True),
    F("reasoning_effort", "Reasoning effort", "text", "--reasoning-effort", advanced=True),
    F("temperature_policy", "Temperature policy", "choice", "--temperature-policy",
      choices=("", "as-benchmark", "inject"), advanced=True),
    F("allow_text_tool_calls", "Allow text-encoded tool calls", "bool", "--allow-text-tool-calls", advanced=True),
    F("repeats", "Repeats", "int", "--repeats"),
    F("max_attempts", "Max attempts per unit", "int", "--max-attempts"),
    F("retry_inconsistent", "Retry inconsistent units", "bool", "--retry-inconsistent", advanced=True),
    F("allow_mixed_config", "Allow mixed configurations in one corpus", "bool", "--allow-mixed-config", advanced=True),
    F("limit", "Limit (cells)", "int", "--limit", advanced=True),
    F("canary", "Canary cells (0 disables)", "int", "--canary"),
    F("preflight_only", "Preflight probe only", "bool", "--preflight-only"),
    F("dry_run", "Dry run (plan only)", "bool", "--dry-run"),
    F("keep_staging", "Keep staging directories", "bool", "--keep-staging", advanced=True),
    F("cell_timeout", "Cell timeout (seconds)", "float", "--cell-timeout"),
    F("jobs", "Concurrent traces (--jobs)", "int", "--jobs"),
    F("start_stagger", "Start stagger (seconds)", "float", "--start-stagger", advanced=True),
    F("allow_custom_endpoint", "Allow a custom endpoint base URL", "bool", "--allow-custom-endpoint", advanced=True),
    F("containment", "Containment", "choice", "--containment", choices=("", "sandbox-exec", "dedicated-user", "vm")),
    F("autodojo_cache", "AutoDojo attack cache", "path", "--autodojo-cache", advanced=True),
    F("autodojo_variant", "AutoDojo variant", "text", "--autodojo-variant", advanced=True),
    F("allow_network", "Allow network (fetch the pinned AutoDojo commit)", "bool", "--allow-network", tier="R2",
      advanced=True),
    F("preset", "Host preset (D-822, D-823)", "text", "--preset", advanced=True),
    F("m5ultra", "m5ultra preset (calibrated, version 2; D-823)", "bool", "--m5ultra", advanced=True),
    F("model_dir", "Model directory (preset)", "dir", "--model-dir", advanced=True),
    F("model_size_gb", "Model size, GB (preset)", "float", "--model-size-gb", advanced=True),
    F("active_params_b", "Active parameters, billions (preset)", "float", "--active-params-b", advanced=True),
    F("context_tokens", "Context tokens (preset)", "int", "--context-tokens", advanced=True),
    F("kv_gb_per_trace", "KV cache GB per trace (preset)", "float", "--kv-gb-per-trace", advanced=True),
    F("server_max_concurrency", "Server max concurrency (preset)", "int", "--server-max-concurrency", advanced=True),
    F("tune_jobs", "Concurrency sweep: --jobs values, e.g. 1,2,4,6,8,12 (preset; D-820)", "text", "--tune-jobs",
      advanced=True),
    F("tune_out", "Concurrency sweep folder (preset; D-820)", "dir", "--tune-out", advanced=True),
)

#: D-701: ``agentprov estimate`` takes the run options less these (cli/run.py ESTIMATE_OMITS), and adds its own.
_ESTIMATE_OMITS: Final = frozenset({
    "--preflight-only", "--dry-run", "--plan-json", "--catalogue", "--keep-staging", "--skip-prov-conformance",
    "--i-consent-to-api-costs", "--i-consent-to-local-run",  # the latter: D-726 (live pilot), when it lands
    "--preset", "--m5ultra", "--model-dir", "--model-size-gb", "--active-params-b", "--context-tokens",
    "--kv-gb-per-trace", "--server-max-concurrency", "--tune-jobs", "--tune-out",
})  # fmt: skip
ESTIMATE_FIELDS: Final = (
    *(replace(f, writes=False) for f in RUN_FIELDS if f.option not in _ESTIMATE_OMITS),  # a dry plan writes nothing
    F("stats_corpus", "Corpora to measure (the viewer's open corpora)", "multi", "--stats-corpus"),
    F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
)

FORMS: Final[Mapping[str, CommandForm]] = {
    f.name: f
    for f in (
        CommandForm("info", ("info",), "Info", "R0", (
            F("source", "Source (optional)", "text", None),
            F("source_opt", "Source (as an option)", "text", "--source", advanced=True),
            F("matrix", "Compatibility matrix", "bool", "--matrix", advanced=True),
            F("must_not_claim", "Must-not-claim items", "bool", "--must-not-claim", advanced=True),
            F("format", "Format", "choice", "--format", choices=("text", "json", "markdown"), default="json"),
        )),
        # D-1010: Help › Assistant runs it with the conversation on stdin; as a job it answers one --question
        CommandForm("assist", ("assist",), "Ask the Assistant (Help › Assistant)", "R0", (
            F("question", "Question", "text", "--question"),
            F("endpoint", "Endpoint", "text", "--endpoint"),
            F("model_id", "Model id", "text", "--model-id"),
            F("base_url", "Local server base URL (loopback)", "text", "--base-url"),
            F("server", "Local server kind", "choice", "--server",
              choices=("", "llamacpp", "lmstudio", "mlx_lm", "ollama", "omlx", "other", "splash", "strata", "vllm")),
            F("list_models", "List the local server's models (no model is called)", "bool", "--list-models"),
            F("allow_network", "Allow the request to an API provider (network)", "bool", "--allow-network", tier="R2"),
            F("context_chars", "Characters of documentation sent", "int", "--context-chars", advanced=True),
            F("show_context", "Print the passages only (no model is called)", "bool", "--show-context", advanced=True),
            F("page", "The app page the question is about (D-1041)", "choice", "--page",
              choices=("", "Viewer", "Runs", "Logs", "System", "Licences", "Package", "Docs"), advanced=True),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="text"),
        ), menu=False),
        CommandForm("models", ("models",), "Model lists (local servers and API providers)", "R0", (
            F("endpoint", "Endpoint", "choice", "--endpoint",
              choices=("", "anthropic", "deepseek", "gemini", "glm", "llama", "openai", "openrouter", "qwen",
                       "llamacpp", "lmstudio", "mlx_lm", "ollama", "omlx", "vllm")),
            F("allow_network", "Fetch the provider's model list now (network)", "bool", "--allow-network", tier="R2"),
            F("refresh_if_stale", "Refresh only when models.auto_refresh is on and the list is older than 24 h", "bool",
              "--refresh-if-stale"),
            F("base_url", "Base URL (loopback)", "text", "--base-url", pending="D-691"),
            F("model_id", "Model id (show its identity)", "text", "--model-id", pending="D-691"),
            F("model_dir", "Model directory or file", "path", "--model-dir", pending="D-691", advanced=True),
            F("find_folders", "List the folders that may hold the model (with the model id; D-828)", "bool",
              "--find-folders", advanced=True),
            F("no_hash_weights", "Do not hash weight files", "bool", "--no-hash-weights", pending="D-691",
              advanced=True),
            F("allow_lan_endpoint", "Allow a LAN address", "bool", "--allow-lan-endpoint", pending="D-698",
              advanced=True),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json", pending="D-691"),
        )),
        CommandForm("validate", ("validate",), "Validate a corpus", "R0", (
            F("corpus", "Corpus", "dir", "--corpus"),
            F("files", "Files (instead of a corpus; space separated)", "list", None, advanced=True),
            F("aer", "AER files (one per line or space separated)", "multi", "--aer", advanced=True),
            F("store", "Raw store directory (file mode)", "dir", "--store", advanced=True),
            F("tiers", "Tiers (comma list)", "text", "--tiers", help="aer,sem,prov,linkage,shacl,regression"),
            _PROV,
            F("strict", "Strict", "bool", "--strict"),
            F("release", "Release mode", "bool", "--release"),
            F("report", "Report file (outside the corpus)", "path", "--report", tier="R1"),
            F("sample", "Sample N", "int", "--sample"),
            F("seed", "Seed", "int", "--seed"),
            F("card", "Lint a corpus card (CARD.md)", "path", "--card", advanced=True),
            _JOBS, _IN_PROCESS, _NO_VCACHE,
            F("dry_run", "Dry run", "bool", "--dry-run", advanced=True),
        ), release_option=True, reads_corpus="corpus"),  # validate is the check itself: it has no skip flag
        CommandForm("verify", ("verify",), "Verify a corpus or deposit", "R0", (
            F("corpus", "Corpus, deposit or .meta.zip", "path", "--corpus", required=True),
            F("level", "Level", "choice", "--level", choices=("checksums", "chain", "rederive"), default="chain"),
            F("root_digest", "Root digests (sha256:…; one per corpus)", "multi", "--root-digest"),
            F("release", "Release mode", "bool", "--release"),
            F("sample", "Sample N", "int", "--sample"),
            F("seed", "Seed", "int", "--seed"),
            F("against_pins", "Compare with the pins", "bool", "--against-pins"),
            F("allow_network", "Allow network (with --against-pins)", "bool", "--allow-network", tier="R2"),
            F("cache_dir", "Fetch cache", "dir", "--cache-dir"),
            _JOBS, _IN_PROCESS, _NO_VCACHE,
        ), release_option=True, reads_corpus="corpus"),
        CommandForm("render", ("render",), "Render graphs", "R1", (
            F("corpus", "Corpus", "dir", "--corpus", required=True),
            F("ex", "Execution ids (space separated)", "list", "--ex"),
            _SELECT,
            F("limit", "Limit", "int", "--limit"),
            F("bundle", "Bundles", "choice", "--bundle", choices=("core", "all"), default="core"),
            F("format", "Formats (comma list)", "text", "--format", default="svg"),
            F("direction", "Direction", "choice", "--direction", choices=("LR", "TB"), default="LR"),
            F("out", "Output directory (never inside a corpus)", "dir", "--out", writes=True),
            F("max_edges", "Max edges per graph", "int", "--max-edges", advanced=True),
            _JOBS, _DRY,
        ), reads_corpus="corpus"),
        CommandForm("derive", ("derive",), "Derive a new corpus version", "R1", (
            F("corpus", "Source corpus", "dir", "--corpus", required=True),
            F("out", "New corpus (must not exist; NEW.partial resumes)", "dir", "--out", required=True, writes=True),
            _PROV,
            F("stages", "Stages (comma list)", "text", "--stages", help="sem,prov,validation,views"),
            F("views", "View", "choice", "--views", choices=("", "transcript-v1")),
            F("semantics_profile", "Semantics profiles (ID@N)", "multi", "--semantics-profile"),
            F("link_raw", "Hard-link raw objects", "bool", "--link-raw"),
            F("no_reuse", "Recompute every execution", "bool", "--no-reuse"),
            F("trig", "TriG output directory", "dir", "--trig", writes=True),
            _JOBS, _IN_PROCESS, _NO_VCACHE, _DRY,
        ), writer=True, prov_generating=True, reads_corpus="corpus"),
        CommandForm("recompute", ("recompute",), "Recompute and compare", "R1", (
            F("corpus", "Source corpus", "dir", "--corpus", required=True),
            F("dry_run", "Dry run (compare only; writes nothing)", "bool", "--dry-run", default=True),
            F("out", "New corpus (instead of a dry run)", "dir", "--out", writes=True),
            _PROV,
            F("stages", "Stages (comma list)", "text", "--stages", help="expand,aer,sem,prov,validation,views"),
            F("show_diff", "Show the first N differences", "int", "--show-diff"),
            F("strict", "Strict", "bool", "--strict"),
            F("link_raw", "Hard-link raw objects", "bool", "--link-raw"),
            F("no_reuse", "Recompute every execution", "bool", "--no-reuse"),
            _JOBS, _IN_PROCESS, _NO_VCACHE,
        ), writer=True, prov_generating=True, reads_corpus="corpus"),
        CommandForm("import", ("import",), "Import a source", "R1", (
            F("source", "Source (optional with --spec)", "text", None),
            F("corpus", "Corpus (written as DIR.partial)", "dir", "--corpus", required=True, writes=True),
            F("input", "Local input (with Verify against the pin)", "path", "--input"),
            F("verify_against_pin", "Verify against the pin", "bool", "--verify-against-pin"),
            F("fetch", "Read the pin from the fetch cache", "bool", "--fetch", tier="R2"),
            F("allow_network", "Allow network (with --fetch)", "bool", "--allow-network", tier="R2"),
            F("cache_dir", "Fetch cache", "dir", "--cache-dir"),
            F("large_download", "I consent to a large download", "bool", "--i-consent-to-large-download", tier="R2"),
            F("context", "Context inputs (ROLE=PATH)", "multi", "--context", advanced=True),
            F("no_context", "Context roles to leave out (ROLE)", "multi", "--no-context", advanced=True),
            F("profile", "Profile", "text", "--profile"),
            F("pin", "Pin role", "text", "--pin"),
            F("snapshot", "Snapshot", "text", "--snapshot"),
            F("spec", "Corpus spec (SPEC.toml; deferred in this build)", "path", "--spec", advanced=True),
            F("corpus_id", "Corpus id", "text", "--corpus-id"),
            F("suite", "Suite", "text", "--suite"),
            F("attack", "Attack", "text", "--attack"),
            F("pipeline", "Pipeline", "text", "--pipeline", advanced=True),
            F("variant", "Variant", "text", "--variant"),
            _SELECT,
            F("limit", "Limit", "int", "--limit"),
            F("sample", "Sample N executions", "int", "--sample"),
            F("sample_mode", "Sample mode", "choice", "--sample-mode", choices=("", "first", "spread", "random")),
            F("seed", "Seed (with random sampling)", "int", "--seed"),
            F("until", "Until stage", "choice", "--until", choices=("", "raw", "aer", "sem", "prov", "validation")),
            _PROV,
            F("retry_failed", "Retry failed units", "bool", "--retry-failed"),
            F("release", "Release mode", "bool", "--release"),
            _JOBS, _IN_PROCESS,
            F("size_hints", "Size-hints directory", "dir", "--size-hints", advanced=True),
            F("allow_hardlinks", "Accept hard-linked input files", "bool", "--allow-hardlinks", advanced=True),
            _NO_VCACHE,
            F("artefacts", "Print the artefact table (locators only)", "bool", "--artefacts", advanced=True),
            F("max_file_bytes", "Max file bytes", "int", "--max-file-bytes"),
            F("max_json_depth", "Max JSON depth", "int", "--max-json-depth"),
            _DRY,
        ), writer=True, release_option=True, prov_generating=True),
        CommandForm("fetch", ("fetch",), "Fetch pinned upstream bytes", "R2", (
            F("corpus", "Corpus (its REFERENCES.json)", "dir", "--corpus"),
            F("only", "Only object (sha256:…)", "text", "--only"),
            F("profile", "Profile", "text", "--profile"),
            F("pin", "Pin role", "text", "--pin"),
            F("history", "Full blobless history", "bool", "--history"),
            F("path", "Path prefix", "text", "--path"),
            F("cache_dir", "Fetch cache", "dir", "--cache-dir"),
            F("allow_network", "Allow network", "bool", "--allow-network", tier="R2"),
            F("large_download", "I consent to a large download", "bool", "--i-consent-to-large-download", tier="R2"),
            _DRY,
        ), slot="cache"),
        CommandForm("stats", ("stats",), "Statistics", "R0", (
            F("corpus", "Corpus", "dir", "--corpus", required=True),
            F("tables", "Tables (comma list)", "text", "--tables"),
            F("artefacts", "Artefact table", "bool", "--artefacts", advanced=True),
            F("per_execution", "Per execution", "bool", "--per-execution"),
            F("prov_spec", "PROV spec", "choice", "--prov-spec", choices=("", "agentprov-prov/0.1", "adprov-v2.3-compat")),
            _SELECT,
            F("format", "Format", "choice", "--format", choices=("json", "text", "csv", "markdown"), default="json"),
            F("out", "Export to file", "path", "--out", tier="R1"),
        ), reads_corpus="corpus"),
        CommandForm("package_seal", ("package",), "Seal a working corpus", "R1", (
            F("corpus", "Working corpus (DIR or DIR.partial)", "dir", "--corpus", required=True, writes=True),
            F("corpus_version", "Corpus version (X.Y.Z)", "text", "--corpus-version", required=True),
            F("spec", "Corpus spec", "path", "--spec"),
            F("licence_file", "Licence file (NAME=PATH)", "text", "--licence-file"),
            F("release_date", "Release date (YYYY-MM-DD)", "text", "--release-date"),
            _DRY,
        ), writer=True),
        CommandForm("package_deposit", ("package",), "Build a deposit draft (never uploads)", "R1", (
            F("deposit", "Deposit output directory", "dir", "--deposit", required=True, writes=True),
            F("corpus", "Sealed corpora (space separated)", "list", "--corpus", required=True),
            F("metadata", "release.toml", "path", "--metadata", required=True),
            F("release_date", "Release date (YYYY-MM-DD)", "text", "--release-date"),
            F("max_archive_bytes", "Max archive bytes", "int", "--max-archive-bytes"),
            F("mixed", "Allow mixed licence classes", "bool", "--allow-mixed-licence-classes"),
            _DRY,
        )),
        # D-947: the index-only umbrella of a collection, built from the part records' draft receipts (never uploads)
        CommandForm("package_index", ("package",), "Build a collection index deposit (never uploads)", "R1", (
            F("index", "Index output directory", "dir", "--index", required=True, writes=True),
            F("part", "Part receipts (DIR.zenodo-TARGET-draft-receipt.json; space separated)", "list", "--part",
              required=True),
            F("corpus", "Sealed corpora of those parts (space separated)", "list", "--corpus", required=True),
            F("metadata", "release.toml", "path", "--metadata", required=True),
            F("release_date", "Release date (YYYY-MM-DD)", "text", "--release-date", required=True),
            _DRY,
        )),
        CommandForm("purge", ("purge",), "Purge a leaked object (irreversible)", "R1", (
            F("object", "Object (sha256:…)", "text", None, required=True),
            F("reason", "Reason", "choice", "--reason", choices=("secret", "personal_data"), required=True),
            F("corpus", "Working corpus", "dir", "--corpus", writes=True),
            F("cache", "From the fetch cache instead", "bool", "--cache"),
            F("cache_dir", "Fetch cache", "dir", "--cache-dir"),
            _DRY,
        ), writer=True),
        CommandForm("ci_local", (), "Run CI locally (tools/ci_local.py)", "R1", (
            F("only", "Only these job ids (comma list)", "text", "--only"),
            F("skip", "Skip these job ids (comma list)", "text", "--skip"),
            F("with_dispatch", "Also the dispatch-only jobs", "bool", "--with-dispatch-jobs"),
            F("allow_network", "Allow network (downloads; ask first)", "bool", "--allow-network", tier="R2"),
            F("strict", "A skipped or unavailable job fails the run", "bool", "--strict"),
            F("json", "Report as JSON", "bool", "--json", default=True),
        ), tool="tools/ci_local.py"),
        CommandForm("prices_refresh", ("prices", "refresh"), "Refresh model prices (OpenRouter; network)", "R2", (
            F("allow_network", "Allow network (one public URL, openrouter.ai)", "bool", "--allow-network", tier="R2",
              default=True),
            F("from_file", "Import a saved response instead (no network)", "path", "--from-file", advanced=True),
            F("fetched", "Its fetch date (YYYY-MM-DD)", "text", "--fetched", advanced=True),
            F("if_stale", "Only when no snapshot was written today and prices.auto_refresh is on (the daily refresh)",
              "bool", "--if-stale", advanced=True),
        )),  # D-650, D-701: confirmed every time from New Job; D-1062: Run Live's daily refresh starts it --if-stale
        CommandForm("priors_build", ("priors", "build"), "Build cost figures from my corpora (estimate priors)", "R1", (
            F("corpus", "Sealed corpora (default: every sealed corpus under $AGENTPROV_HOME/corpora)", "multi",
              "--corpus"),
            F("jobs", "Worker processes (0: the host default; a few leave the machine to other work)", "int", "--jobs",
              default=8),
            F("min_executions", "Leave out a row with fewer executions (default 5)", "int", "--min-executions",
              advanced=True),
            F("format", "Format", "choice", "--format", choices=("", "text", "json"), advanced=True),
        )),  # D-1062: $AGENTPROV_HOME/estimate/priors-local.json; reads every AER of the sealed corpora
        CommandForm("backends_build", ("backends", "build"), "Build a backend environment", "R1", (
            F("backend", "Backend", "choice", None, choices=_backend_envs(), required=True),
            F("offline_check", "Check an existing build only", "bool", "--offline-check"),
            F("allow_network", "Allow network (uv downloads)", "bool", "--allow-network", tier="R2"),
            F("defence_assets", "Defence assets to provision (registry ids, comma list; D-670)", "text",
              "--defence-assets", advanced=True),
            F("defence_source", "Local tree with the defences' pinned code (verified by digest)", "dir",
              "--defence-source", advanced=True),
            _DRY,
        ), slot="backends"),
        CommandForm("inspect", ("inspect",), "Inspect an execution, file or corpus", "R0", (
            F("target", "Target (execution id, file or corpus root)", "text", None, required=True),
            F("corpus", "Corpus", "dir", "--corpus"),
            F("view", "View", "choice", "--view", choices=("summary", "records", "transcript", "transcript-v1",
                                                          "timeline", "evidence", "sem", "prov", "raw", "detect")),
            F("record", "One record (id)", "text", "--record"),
            F("bundle", "PROV bundles", "choice", "--bundle", choices=("", "core", "inference", "assessment", "toplevel",
                                                                     "all")),
            F("max_chars", "Characters per value (with content; the GUI never shows content here)", "int",
              "--max-chars", advanced=True),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="text"),
        ), reads_corpus="corpus"),
        *(CommandForm(f"migrate_{gate.replace('-', '_')}", ("migrate", gate), title, "R1", (
            *((F("gate_name", "Gate", "choice", None, choices=("G0", "A", "B", "D", "E"), required=True),)
              if gate == "gate" else ()),
            F("scope", "Scope", "choice", "--scope", choices=("", "golden", "full")),
            F("workers", "Workers", "int", "--workers"),
            F("release", "Release mode", "bool", "--release"),
            F("report", "Report file", "path", "--report"),
            F("reports_dir", "Reports directory (default: this job's folder)", "dir", "--reports-dir"),
            F("config", "Migration config", "path", "--config"),
            _IN_PROCESS,
            *((F("corpus", "Corpus", "dir", "--corpus"), F("limit", "Limit", "int", "--limit"),
               F("accept_gap", "Accept a gap (release, converted, native)", "multi", "--accept-gap"))
              if gate in ("gate-d", "gate") else ()),
            *((F("semdiff_dir", "semdiff directory", "dir", "--semdiff-dir"),) if gate in ("gate-e", "gate") else ()),
        ), release_option=True) for gate, title in (
            ("verify-baseline", "Migration: verify the baseline (G0)"), ("gate-a", "Migration gate A"),
            ("gate-b", "Migration gate B"), ("gate-d", "Migration gate D"), ("gate-e", "Migration gate E"),
            ("gate", "Migration gate (by name)"))),
        # D-700: the GUI's own settings and keys go through these commands (Settings › Keys, Prices, Estimate, Dev
        # Runs, Compute, Jobs); the forms record that route for D-654 and are not in the New Job menu
        CommandForm("settings_list", ("settings", "list"), "Settings: list", "R0", (
            F("prefix", "Key prefix", "text", "--prefix"), F("schema", "The schema", "bool", "--schema"),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("settings_get", ("settings", "get"), "Settings: get", "R0", (
            F("key", "Key", "text", None, required=True),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("settings_set", ("settings", "set"), "Settings: set", "R1", (
            F("key", "Key", "text", None, required=True), F("value", "Value", "text", None, required=True),
        ), menu=False),
        CommandForm("settings_unset", ("settings", "unset"), "Settings: unset", "R1", (
            F("key", "Key", "text", None, required=True),
        ), menu=False),
        CommandForm("keys_status", ("keys", "status"), "Keys: status", "R0", (
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("keys_list", ("keys", "list"), "Keys: list", "R0", (
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("keys_set", ("keys", "set"), "Keys: store (Settings › Keys)", "R1", (
            F("name", "Key variable", "text", None, required=True),
        ), menu=False),
        CommandForm("keys_delete", ("keys", "delete"), "Keys: delete (Settings › Keys)", "R1", (
            F("name", "Key variable", "text", None, required=True),
        ), menu=False),
        CommandForm("prices_list", ("prices", "list"), "Prices: list", "R0", (
            F("endpoint", "Endpoint", "text", "--endpoint"),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("prices_get", ("prices", "get"), "Prices: get", "R0", (
            F("endpoint", "Endpoint", "text", None, required=True), F("model", "Model id", "text", None, required=True),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("prices_set", ("prices", "set"), "Prices: set an override (Settings › Prices)", "R1", (
            F("endpoint", "Endpoint", "text", None, required=True), F("model", "Model id", "text", None, required=True),
            F("input", "Input, USD per million tokens", "text", "--input", required=True),
            F("output", "Output, USD per million tokens", "text", "--output", required=True),
            F("cached_input", "Cached input, USD per million tokens", "text", "--cached-input"),
            F("cache_write", "Cache write, USD per million tokens", "text", "--cache-write"),
            F("as_of", "As of (YYYY-MM-DD)", "text", "--as-of"),
        ), menu=False),
        CommandForm("prices_unset", ("prices", "unset"), "Prices: remove an override (Settings › Prices)", "R1", (
            F("endpoint", "Endpoint", "text", None, required=True), F("model", "Model id", "text", None, required=True),
        ), menu=False),
        CommandForm("prices_status", ("prices", "status"), "Prices: when they were refreshed (Run Live)", "R0", (
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),  # D-1062: Run Live's daily refresh reads it
        CommandForm("priors_show", ("priors", "show"), "Estimate priors: show (local and shipped)", "R0", (
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        # D-1065: Check for Updates (About, the start-up notice, Settings › Updates) runs these; not in the New Job menu
        CommandForm("update_status", ("update", "status"), "Updates: the last check (About; no network)", "R0", (
            *_UPDATE_APP, _UPDATE_PLATFORM, _JSON,
        ), menu=False),
        CommandForm("update_check", ("update", "check"), "Updates: check for a new release (About; network)", "R2", (
            F("allow_network", "Allow network (one public URL, api.github.com)", "bool", "--allow-network", tier="R2",
              default=True),
            F("if_stale", "Only once a day, while update.auto_check is on (the start-up check)", "bool", "--if-stale"),
            *_UPDATE_APP, _UPDATE_PLATFORM, _JSON,
        ), menu=False),
        CommandForm("update_download", ("update", "download"), "Updates: download and verify (About; network)", "R2", (
            F("allow_network", "Allow network (GitHub's release files)", "bool", "--allow-network", tier="R2",
              default=True),
            _UPDATE_DIR, _UPDATE_PLATFORM, _JSON,
        ), menu=False),
        CommandForm("update_install", ("update", "install"), "Updates: install the verified download (About)", "R2", (
            *_UPDATE_APP, _UPDATE_DIR, _UPDATE_PLATFORM, _JSON,
        ), menu=False),  # --confirm only after About's confirmation (MANAGED_OPTIONS)
        CommandForm("update_rollback", ("update", "rollback"), "Updates: back to the previous version", "R1", (
            F("bundle", "The desktop app's folder", "dir", "--bundle", required=True), _UPDATE_PLATFORM, _JSON,
        ), menu=False),  # --yes: EXCLUDED_OPTIONS (the app shows the command; it offers no rollback button)
        CommandForm("estimate", ("estimate",), "Estimate a live run (Run Live)", "R0", ESTIMATE_FIELDS, menu=False),
        # D-704: the GUI's job manager is the core's; Runs starts, follows and controls jobs through these commands
        CommandForm("jobs_start", ("jobs", "start"), "Jobs: start", "R1", (
            F("label", "Label", "text", "--label"), F("writes", "Writes (corpora)", "multi", "--writes"),
            F("reads", "Reads (corpora)", "multi", "--reads"),
            F("slot", "Global slot", "choice", "--slot", choices=("", "network", "backends")),
            F("with_control_file", "Control file (drain)", "bool", "--with-control-file"),
            F("queue_cpu", "Through the job queue, CPUs", "int", "--queue-cpu"),
            F("progress_level", "Progress level", "choice", "--progress-level", choices=("", "status", "steps")),
            F("tool", "Repository tool (tools/NAME.py)", "text", "--tool"), F("note", "Notes", "multi", "--note"),
            F("meta", "Facts recorded with the job (KEY=VALUE)", "multi", "--meta"),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
            F("argv", "The job's agentprov arguments", "list", None, required=True),
        ), menu=False),
        CommandForm("jobs_list", ("jobs", "list"), "Jobs: list", "R0", (
            F("state", "State", "choice", "--state", choices=("", "running", "ended", "all")),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("jobs_show", ("jobs", "show"), "Jobs: show", "R0", (
            F("job_id", "Job", "text", None, required=True),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("jobs_follow", ("jobs", "follow"), "Jobs: follow", "R0", (
            F("job_id", "Job", "text", None, required=True), F("timeout", "Timeout (s)", "float", "--timeout"),
            F("log", "Log records instead of progress", "bool", "--log"),
        ), menu=False),
        *(CommandForm(f"jobs_{name}", ("jobs", name), f"Jobs: {name}", "R1", (
            F("job_id", "Job", "text", None, required=True),
            *((F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),)
              if name == "resume" else ()),
        ), menu=False) for name in ("stop", "kill", "drain", "resume")),
        CommandForm("jobs_cancel", ("jobs", "cancel"), "Jobs: cancel", "R1", (  # D-1061: stop, and resume refuses it
            F("job_id", "Job", "text", None, required=True),
        ), menu=False),
        CommandForm("batch_create", ("batch", "create"), "Batch: create", "R1", (
            F("spec", "Step list (a file)", "path", None), F("stdin", "The step list on stdin", "bool", "--stdin"),
            F("label", "Label", "text", "--label"),
            F("concurrency", "Steps at a time", "int", "--concurrency"),
            F("continue_on_failure", "Continue after exit 4 or 70", "bool", "--continue-on-failure"),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        *(CommandForm(f"batch_{name}", ("batch", name), f"Batch: {name}", "R1", (
            F("batch_id", "Batch", "text", None, required=True),
            F("confirm_r2", "Confirm its R2 steps", "bool", "--confirm-r2", tier="R2"),
            *((F("interval", "Seconds between ticks", "float", "--interval"),) if name == "run" else
              (F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),)),
        ), menu=False) for name in ("start", "resume", "run")),
        CommandForm("batch_stop", ("batch", "stop"), "Batch: stop", "R1", (
            F("batch_id", "Batch", "text", None, required=True), F("steps", "Also its running steps", "bool", "--steps"),
            F("wait", "Seconds to wait for them to end", "float", "--wait"),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("batch_list", ("batch", "list"), "Batch: list", "R0", (
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("batch_show", ("batch", "show"), "Batch: show", "R0", (
            F("batch_id", "Batch", "text", None, required=True),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("devrun_plan", ("devrun", "plan"), "Dev run: plan", "R0", (
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("devrun_start", ("devrun", "start"), "Dev run: start (Runs › Dev Run…)", "R1", (
            F("confirm_r2", "Confirm the imports' fetch-cache reads", "bool", "--confirm-r2", tier="R2"),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("devrun_list", ("devrun", "list"), "Dev run: list", "R0", (
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("devrun_prune", ("devrun", "prune"), "Dev run: prune", "R1", (
            F("keep", "Keep the newest", "int", "--keep"),
        ), menu=False),
        CommandForm("jobs_prune", ("jobs", "prune"), "Jobs: prune", "R1", (
            F("keep", "Keep the newest", "int", "--keep"), F("max_age_days", "Max age (days)", "int", "--max-age-days"),
            F("format", "Format", "choice", "--format", choices=("text", "json"), default="json"),
        ), menu=False),
        CommandForm("run", ("run",), "Run live (capture)", "R1", RUN_FIELDS, writer=True, release_option=False,
                    prov_generating=True, menu=False),
    )
}


# ----------------------------------------------------------------------------------------------- presentation
# D-1060: how Runs › New Job shows a form (sections, plain labels, captions, the right control). Presentation only:
# the argv is always the Field's and build_spec's; a form or field without an entry here still renders cleanly.
@dataclass(frozen=True, slots=True)
class Look:
    """How New Job shows one field. Empty values fall back: the section to "Save to" (a field that names what the job
    writes), "Output" (``format``) or "Options"; the label to the field's label without its trailing parenthesis, which
    becomes the caption; ``advanced`` to the field's own flag."""

    section: str = ""
    label: str = ""
    caption: str = ""
    unit: str = ""
    placeholder: str = ""  # a number's or a blank choice's unset text ("Default (8)"); "" gives "Default"
    advanced: bool | None = None  # under the one "Advanced: …" disclosure
    when: str = ""  # shown (and set) only while another field is set: "KEY" (any value) or "KEY=VALUE"
    folder: bool | None = None  # a path field's Choose… picks a folder (default: for a "dir" field)
    inline: str = ""  # shown after the control of another field or mode (its KEY), in its row; the caption goes to the tip


@dataclass(frozen=True, slots=True)
class Segment:
    """One choice of a :class:`Mode`: its text and the fields shown (and set) while it is chosen."""

    text: str
    shows: tuple[str, ...] = ()
    tip: str = ""


@dataclass(frozen=True, slots=True)
class Mode:
    """Two to four exclusive ways to fill a form, as a segmented control (rule 6): the fields of the other segments
    are hidden and left out of the command. ``flag``: a bool field the mode itself sets (on for ``flag_segment``, off
    otherwise; it has no row of its own). The first segment whose fields the preset fills is chosen, else
    ``default``."""

    key: str
    label: str
    segments: tuple[Segment, ...]
    section: str = ""
    caption: str = ""
    tip: str = ""
    flag: str = ""
    flag_segment: int = 0
    default: int = 0

    def owns(self) -> tuple[str, ...]:
        return (*((self.flag,) if self.flag else ()), *(k for s in self.segments for k in s.shows))


@dataclass(frozen=True, slots=True)
class FormLook:
    """A form's presentation: per-field looks, its modes, the words naming what its Advanced disclosure holds and
    ``says``, what Continue will do as one plain sentence (New Job's "What happens" card): ``(condition, text)`` clauses
    joined in order, each kept only when its condition holds and every ``{KEY}`` it names is set. A condition is
    comma-separated terms that must all hold: ``KEY`` (set), ``!KEY`` (not set) or ``KEY=VALUE``; ``""`` always holds.
    ``{KEY:name}`` gives a path's last part (each one's, for a list), ``{KEY:short}`` a digest's first 8 hex digits.
    A form without ``says`` is described by its title."""

    fields: Mapping[str, Look] = field(default_factory=dict)
    modes: tuple[Mode, ...] = ()
    advanced: str = ""
    says: tuple[tuple[str, str], ...] = ()


_RUN = "Run"
#: looks shared by the fields of the same key in every form (a form's own look replaces them)
COMMON_LOOKS: Final[Mapping[str, Look]] = {
    "jobs": Look(_RUN, "Workers", unit="processes", placeholder="Default (host)", advanced=True),
    "dry_run": Look(_RUN, "Dry run", "Writes nothing", advanced=True),
    "prov_spec": Look(_RUN, "PROV spec", placeholder="Default", advanced=True),
    "in_process": Look(_RUN, "Run the workers in this process", "Debugging only", advanced=True),
    "no_validation_cache": Look(_RUN, "Do not use the validation cache", advanced=True),
    "release": Look("", "Release mode", "Strict checks; no filters, limits or samples"),
    "select": Look("", "Select", "KEY=VALUE[,VALUE…]: an AER-header filter"),
    "format": Look("Output", "Format"),
    "cache_dir": Look("", "Fetch cache", placeholder="Default ($AGENTPROV_HOME/cache)"),
}
#: the global options of every CLI job (D-654), under Advanced › Logging and progress
GLOBAL_LOOKS: Final[Mapping[str, Look]] = {
    "g_verbose": Look("Logging and progress", "Verbose log", "DEBUG records in the job log"),
    "g_quiet": Look("Logging and progress", "Quiet", "Only warnings and errors on stderr"),
    "g_log_format": Look("Logging and progress", "Log format", "Of stderr"),
    "g_progress_interval": Look("Logging and progress", "Progress heartbeat", unit="seconds"),
    "g_progress_max_bytes": Look("Logging and progress", "Progress file rotation", unit="bytes"),
    "g_max_listed": Look("Logging and progress", "Failures listed", "In the job's summary"),
    "g_break_stale_lock": Look("Logging and progress", "Remove a stale lock first",
                               "Writers only; confirmed before the job starts"),
}
_SAMPLE = Look("What to check", "Sample", "A sample of N executions instead of all", unit="executions",
               placeholder="All")
_SEED = Look("What to check", "Seed", "Of the sample", when="sample")
#: per form (by :attr:`CommandForm.name`)
LOOKS: Final[Mapping[str, FormLook]] = {
    "import": FormLook({
        "source": Look("Source", "Source", "A registry source id; optional with a corpus spec"),
        "input": Look("Source", "Input", "A folder or one file, read in place", folder=True),
        "verify_against_pin": Look("Source", "Verify against the pin",
                                   "Records the pinned origin of the files the pin vouches for"),
        "allow_network": Look("Source", "Download if not cached", "Otherwise an uncached pin is refused",
                              inline="origin"),
        "large_download": Look("Source", "Allow a large download", "100 MiB or more", when="allow_network"),
        "cache_dir": Look("Fetch the pin", "Fetch cache", "Where the pinned bytes are kept",
                          placeholder="Default ($AGENTPROV_HOME/cache)", advanced=True),
        "snapshot": Look("Source", "Snapshot", placeholder="Default (the registry part)"),
        "corpus": Look("Save to", "Working corpus", "A new folder, outside the repository (DIR.partial while "
                                                    "it is written)"),
        "limit": Look("How much", "N", "The first N new units are mapped", unit="units", inline="how_much"),
        "sample": Look("How much", "N", "A deterministic sample, chosen before mapping", unit="executions",
                       inline="how_much"),
        "sample_mode": Look("How much", "Sampling", "Default: the first N by key"),
        "seed": Look("How much", "Seed", "Required by random sampling", when="sample_mode=random"),
        "until": Look(_RUN, "Stop after stage", placeholder="All stages (default)", advanced=True),
        "retry_failed": Look(_RUN, "Retry failed units", "Every failed unit; no limit or sample", advanced=True),
        "release": Look(_RUN, "Release mode", "Strict checks; no filters, limits or samples", advanced=True),
        "profile": Look("Profile and pin", "Profile", placeholder="Default (the registry's)", advanced=True),
        "pin": Look("Profile and pin", "Pin role", "Such as 2024-06 or release", advanced=True),
        "corpus_id": Look("Profile and pin", "Corpus id", placeholder="Default (the registry's)", advanced=True),
        "spec": Look("Profile and pin", "Corpus spec", "SPEC.toml; deferred in this build", advanced=True),
        "context": Look("Profile and pin", "Context inputs", "ROLE=PATH, a local copy of a context pin",
                        advanced=True),
        "no_context": Look("Profile and pin", "Context roles left out", "ROLE", advanced=True),
        "suite": Look("Selection", "Suite", advanced=True),
        "attack": Look("Selection", "Attack", advanced=True),
        "pipeline": Look("Selection", "Pipeline", advanced=True),
        "variant": Look("Selection", "Variant", advanced=True),
        "select": Look("Selection", "Select", "KEY=VALUE[,VALUE…]: an AER-header filter", advanced=True),
        "max_file_bytes": Look("Limits", "Largest file", unit="bytes", advanced=True),
        "max_json_depth": Look("Limits", "Deepest JSON nesting", unit="levels", advanced=True),
        "size_hints": Look("Limits", "Size hints", "A folder of size hints", advanced=True),
        "allow_hardlinks": Look("Limits", "Accept hard-linked input files", advanced=True),
        "artefacts": Look("Limits", "Print the artefact table", "With a dry run; locators only", advanced=True),
    }, modes=(
        Mode("origin", "Get the data", (
            Segment("Fetch the pin", ("allow_network", "large_download", "cache_dir"),
                    "Reads the profile's pin from the verified fetch cache (--fetch)."),
            Segment("Local folder", ("input", "verify_against_pin"),
                    "Reads a local folder or file in place (--input)."),
        ), section="Source", flag="fetch", flag_segment=0, default=1),
        Mode("how_much", "Executions", (
            Segment("All", (), "Every unit of the snapshot (no --limit or --sample)."),
            Segment("First N", ("limit",), "At most N new units (--limit N)."),
            Segment("Sample N", ("sample", "sample_mode", "seed"),
                    "A deterministic sample of N executions, chosen before mapping (--sample N)."),
        ), section="How much"),
    ), advanced="fetch cache, stages, workers, dry run, pin, selection, limits, logging, extra arguments",
       says=(("", "Imports "), ("!limit,!sample", "every unit"), ("limit", "the first {limit} new units"),
             ("sample", "a sample of {sample} executions"), ("source", " of {source}"),
             ("source,snapshot", " snapshot {snapshot}"), ("input", " from {input:name}, read in place"),
             ("", " into the new working corpus"), ("corpus", " {corpus:name}"), ("", "."),
             ("fetch,!allow_network", " The pin must already be in the fetch cache."),
             ("fetch,allow_network", " The pin is downloaded if it is not cached."),
             ("input,verify_against_pin", " The files are checked against the pin."))),
    "derive": FormLook({
        "corpus": Look("Source", "Source corpus"),
        "out": Look("Save to", "New corpus", "Must not exist yet; NEW.partial resumes"),
        "stages": Look("What to derive", "Stages", "sem, prov, validation, views", placeholder="Default (all)"),
        "views": Look("What to derive", "View", placeholder="None"),
        "semantics_profile": Look("What to derive", "Semantics profiles", "ID@N", advanced=True),
        "link_raw": Look(_RUN, "Hard-link raw objects", advanced=True),
        "no_reuse": Look(_RUN, "Recompute every execution", advanced=True),
        "trig": Look("Save to", "TriG output folder", advanced=True),
    }, advanced="stages, workers, dry run, conformance, logging, extra arguments",
       says=(("", "Derives a new corpus version"), ("corpus", " from {corpus:name}"), ("out", " into {out:name}"),
             ("stages", " (stages {stages})"), ("views", " with the {views} view"), ("", "."),
             ("trig", " TriG files go to {trig:name}."))),
    "recompute": FormLook({
        "corpus": Look("Source", "Source corpus"),
        "out": Look("Result", "New corpus", "Must not exist yet"),
        "link_raw": Look("Result", "Hard-link raw objects"),
        "stages": Look("What to compare", "Stages", "expand, aer, sem, prov, validation, views",
                       placeholder="Default (all)"),
        "show_diff": Look("What to compare", "Differences shown", "The first N", unit="differences"),
        "strict": Look("What to compare", "Strict"),
        "no_reuse": Look(_RUN, "Recompute every execution", advanced=True),
    }, modes=(
        Mode("result", "Result", (
            Segment("Compare only", (), "A dry run: recompute and compare; writes nothing (--dry-run)."),
            Segment("Write a new corpus", ("out", "link_raw"), "Recompute into a new corpus (--out NEW)."),
        ), section="Result", flag="dry_run", flag_segment=0),
    ), advanced="PROV spec, workers, conformance, logging, extra arguments",
       says=(("", "Recomputes"), ("corpus", " {corpus:name}"), ("stages", " (stages {stages})"),
             ("", " and compares the result with what it holds"), ("dry_run", "; writes nothing"),
             ("out", "; writes the new corpus {out:name}"), ("", "."),
             ("show_diff", " Shows the first {show_diff} differences."))),
    "validate": FormLook({
        "corpus": Look("Source", "Corpus"),
        "files": Look("Source", "Files", "Separated by spaces"),
        "aer": Look("Source", "AER files", "Separated by spaces"),
        "store": Look("Source", "Raw store", "A folder (file mode)"),
        "tiers": Look("What to check", "Tiers", "aer, sem, prov, linkage, shacl, regression",
                      placeholder="Default (all)"),
        "strict": Look("What to check", "Strict"),
        "release": Look("What to check", "Release mode", "Strict checks; no samples"),
        "sample": _SAMPLE, "seed": _SEED,
        "card": Look("What to check", "Corpus card", "Lints a CARD.md", advanced=True),
        "report": Look("Save to", "Report file", "Outside the corpus"),
    }, modes=(
        Mode("what", "Check", (
            Segment("A corpus", ("corpus",), "A corpus directory (--corpus)."),
            Segment("Files", ("files", "aer", "store"), "Files instead of a corpus (FILES, --aer, --store)."),
        ), section="Source"),
    ), advanced="PROV spec, workers, corpus card, logging, extra arguments",
       says=(("", "Validates"), ("corpus", " the corpus {corpus:name}"), ("files", " the files {files:name}"),
             ("aer", " the AER files {aer:name}"), ("!corpus,!files,!aer", " a corpus or files"),
             ("tiers", " at the tiers {tiers}"), ("sample", " on a sample of {sample} executions"),
             ("release", " in release mode"), ("", "."), ("report", " The report goes to {report:name}."))),
    "verify": FormLook({
        "corpus": Look("Source", "Corpus or deposit", "A corpus, a deposit or a .meta.zip"),
        "level": Look("What to check", "Level"),
        "release": Look("What to check", "Release mode"),
        "sample": _SAMPLE, "seed": _SEED,
        "against_pins": Look("What to check", "Compare with the pins"),
        "allow_network": Look("What to check", "Download what is not cached", when="against_pins"),
        "cache_dir": Look("What to check", "Fetch cache", placeholder="Default ($AGENTPROV_HOME/cache)",
                          when="against_pins"),
        "root_digest": Look("What to check", "Root digests", "sha256:…, one per corpus", advanced=True),
    }, advanced="root digests, workers, logging, extra arguments",
       says=(("", "Verifies"), ("corpus", " {corpus:name}"), ("level", " at the {level} level"),
             ("sample", " on a sample of {sample} executions"), ("release", " in release mode"),
             ("against_pins", " and compares it with the pins"),
             ("against_pins,allow_network", ", downloading what is not cached"), ("", "."))),
    "render": FormLook({
        "corpus": Look("Source", "Corpus"),
        "ex": Look("Source", "Executions", "Execution ids, separated by spaces", placeholder="All"),
        "select": Look("Source", "Select", "KEY=VALUE[,VALUE…]: an AER-header filter"),
        "limit": Look("Source", "Limit", unit="graphs", placeholder="None"),
        "bundle": Look("Graphs", "Bundles"),
        "format": Look("Graphs", "Formats", "A comma list, such as svg,png"),
        "direction": Look("Graphs", "Direction", "Left to right or top to bottom"),
        "out": Look("Save to", "Output folder", "Never inside a corpus"),
        "max_edges": Look("Graphs", "Largest graph", unit="edges", advanced=True),
    }, advanced="edges, workers, dry run, logging, extra arguments"),
    "fetch": FormLook({
        "corpus": Look("What to fetch", "Corpus", "Its REFERENCES.json names the pins"),
        "only": Look("What to fetch", "Only object", "sha256:…"),
        "profile": Look("What to fetch", "Profile"),
        "pin": Look("What to fetch", "Pin role"),
        "path": Look("What to fetch", "Path prefix"),
        "history": Look("What to fetch", "Full blobless history"),
        "cache_dir": Look("Save to", "Fetch cache", placeholder="Default ($AGENTPROV_HOME/cache)"),
        "allow_network": Look("Network", "Allow network"),
        "large_download": Look("Network", "Allow a large download", "100 MiB or more"),
    }),
    "stats": FormLook({
        "corpus": Look("Source", "Corpus"),
        "tables": Look("What to count", "Tables", "A comma list", placeholder="Default (all)"),
        "per_execution": Look("What to count", "Per execution"),
        "prov_spec": Look("What to count", "PROV spec", placeholder="Default"),
        "select": Look("What to count", "Select", "KEY=VALUE[,VALUE…]: an AER-header filter"),
        "out": Look("Output", "Export to file"),
        "artefacts": Look("What to count", "Artefact table", advanced=True),
    }),
    "package_seal": FormLook({
        "corpus": Look("Corpus", "Working corpus", "DIR or DIR.partial"),
        "corpus_version": Look("Release", "Corpus version", "X.Y.Z"),
        "release_date": Look("Release", "Release date", "YYYY-MM-DD", placeholder="Today"),
        "spec": Look("Release", "Corpus spec"),
        "licence_file": Look("Release", "Licence file", "NAME=PATH"),
    }, says=(("", "Seals the working corpus"), ("corpus", " {corpus:name}"),
             ("corpus_version", " as version {corpus_version}"), ("release_date", ", released {release_date}"),
             ("", "."))),
    "package_deposit": FormLook({
        "deposit": Look("Save to", "Deposit folder", "The draft is built here; nothing is uploaded"),
        "corpus": Look("Source", "Sealed corpora", "Separated by spaces"),
        "metadata": Look("Source", "Release metadata", "release.toml"),
        "release_date": Look("Release", "Release date", "YYYY-MM-DD", placeholder="Today"),
        "max_archive_bytes": Look("Release", "Largest archive", unit="bytes"),
        "mixed": Look("Release", "Allow mixed licence classes"),
    }, says=(("", "Builds a deposit draft"), ("deposit", " in {deposit:name}"), ("corpus", " from {corpus:name}"),
             ("", "; nothing is uploaded."))),
    "package_index": FormLook({
        "index": Look("Save to", "Index folder", "The draft is built here; nothing is uploaded"),
        "part": Look("Source", "Part receipts", "DIR.zenodo-TARGET-draft-receipt.json, separated by spaces"),
        "corpus": Look("Source", "Sealed corpora", "Of those parts, separated by spaces"),
        "metadata": Look("Source", "Release metadata", "release.toml"),
        "release_date": Look("Release", "Release date", "YYYY-MM-DD"),
    }, says=(("", "Builds a collection index deposit"), ("index", " in {index:name}"),
             ("corpus", " for {corpus:name}"), ("", "; nothing is uploaded."))),
    "purge": FormLook({
        "object": Look("Object", "Object", "sha256: and 64 hex digits"),
        "reason": Look("Object", "Reason"),
        "corpus": Look("Remove from", "Working corpus"),
        "cache_dir": Look("Remove from", "Fetch cache", placeholder="Default ($AGENTPROV_HOME/cache)"),
        "dry_run": Look("Check first", "Dry run", "Shows what would be removed; removes nothing"),
    }, modes=(
        Mode("where", "Remove from", (
            Segment("A working corpus", ("corpus",), "Purge the object from a working corpus (--corpus)."),
            Segment("The fetch cache", ("cache_dir",), "Purge it from the fetch cache instead (--cache)."),
        ), section="Remove from", flag="cache", flag_segment=1),
    ), says=(("!dry_run", "Removes the object"), ("dry_run", "Shows what removing the object would do"),
             ("object", " {object:short}"), ("reason", " ({reason})"), ("!cache", " from the working corpus"),
             ("!cache,corpus", " {corpus:name}"), ("cache", " from the fetch cache"), ("", "."),
             ("!dry_run", " Irreversible: Continue asks for the object's first 8 hex digits."),
             ("dry_run", " A dry run: nothing is removed."))),
    "ci_local": FormLook({
        "only": Look("Jobs", "Only", "Job ids, a comma list", placeholder="All"),
        "skip": Look("Jobs", "Skip", "Job ids, a comma list"),
        "with_dispatch": Look("Jobs", "Also the dispatch-only jobs"),
        "strict": Look("Jobs", "Strict", "A skipped or unavailable job fails the run"),
        "json": Look("Output", "Report as JSON"),
        "allow_network": Look("Network", "Allow network", "Downloads; ask first"),
    }),
    "prices_refresh": FormLook({
        "from_file": Look("Prices", "Saved response", "A file; no network"),
        "fetched": Look("Prices", "Fetched on", "YYYY-MM-DD"),
        "if_stale": Look("Daily refresh", "Only when stale", "No snapshot today, and prices.auto_refresh is on",
                         advanced=True),
    }, modes=(
        Mode("from", "Prices from", (
            Segment("openrouter.ai", (), "Fetch one public URL, openrouter.ai (--allow-network)."),
            Segment("A saved response", ("from_file", "fetched"), "Import a saved response instead (--from-file)."),
        ), section="Prices", flag="allow_network", flag_segment=0),
    ), advanced="daily refresh, logging, extra arguments",
       says=(("allow_network", "Fetches the current model prices from openrouter.ai (one public URL)"),
             ("!allow_network", "Imports the saved price response"), ("!allow_network,from_file", " {from_file:name}"),
             ("!allow_network,fetched", " fetched on {fetched}"),
             ("if_stale", ", only when no snapshot was written today and prices.auto_refresh is on"), ("", "."))),
    "priors_build": FormLook({
        "corpus": Look("Source", "Sealed corpora", "Default: every sealed corpus under $AGENTPROV_HOME/corpora"),
        "jobs": Look(_RUN, "Workers", "0: the host default; a few leave the machine to other work",
                     unit="processes"),
        "min_executions": Look(_RUN, "Fewest executions per row", unit="executions", placeholder="Default (5)",
                               advanced=True),
    }, says=(("", "Builds cost figures for Run Live's quote from"), ("corpus", " {corpus:name}"),
             ("!corpus", " every sealed corpus under $AGENTPROV_HOME/corpora"),
             ("jobs", " with {jobs} worker processes"), ("", ". Nothing is written into a corpus."))),
    "backends_build": FormLook({
        "backend": Look("Backend", "Backend"),
        "offline_check": Look("Backend", "Check an existing build only"),
        "allow_network": Look("Backend", "Allow network", "uv downloads"),
        "defence_assets": Look("Defences", "Defence assets", "Registry ids, a comma list", advanced=True),
        "defence_source": Look("Defences", "Defence source", "A local tree with the pinned code", advanced=True),
    }),
    "inspect": FormLook({
        "target": Look("Target", "Target", "An execution id, a file or a corpus root"),
        "corpus": Look("Target", "Corpus"),
        "view": Look("View", "View"),
        "record": Look("View", "One record", "Its id"),
        "bundle": Look("View", "PROV bundles", placeholder="Default"),
        "max_chars": Look("View", "Characters per value", "With content; the GUI never shows content here",
                          advanced=True),
    }),
    "settings_set": FormLook(says=(("", "Sets the setting"), ("key", " {key}"), ("value", " to {value}"), ("", "."))),
    "settings_unset": FormLook(says=(("", "Removes the setting"), ("key", " {key}"), ("", "."))),
    "batch_create": FormLook(says=(
        ("", "Creates a batch"), ("label", " labelled {label}"), ("spec", " from the step list {spec:name}"),
        ("stdin", " from the step list on stdin"), ("concurrency", ", {concurrency} steps at a time"),
        ("continue_on_failure", ", continuing after a step exits 4 or 70"), ("", "."))),
    "batch_stop": FormLook(says=(("", "Stops the batch"), ("batch_id", " {batch_id}"),
                                 ("steps", " and its running steps"),
                                 ("wait", ", waiting up to {wait} seconds for them to end"), ("", "."))),
}

#: GR-20: the options that take a path or directory (every form's path, dir and corpus-list fields). A job's cwd is its
#: own job directory, so a relative or "~" value there would name a tree no GUI check, lock test or viewer looks at.
_PATH_OPTIONS: Final = frozenset([*(f.option for form in FORMS.values() for f in form.fields
                                   if f.option and (f.kind in ("path", "dir") or f.option == "--corpus")), "--aer",
                                "--stats-corpus"])
_NOT_ABSOLUTE: Final = "give an absolute path; jobs run in their own folder"


def _path(text: str, label: str) -> str:
    """GR-20: a path value with "~" expanded; a relative path is refused. The one string feeds argv, writes and reads."""
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise FormError(f"{label}: {_NOT_ABSOLUTE}")
    return str(path)


def _looks_relative(value: str) -> bool:
    """GR-68: a value of an option outside the form table (validate --aer, --store, --card …) that reads as a relative
    or "~" path: it starts with "~", "./" or "../", or is "." or "..", or holds a "/" without being absolute. Plain
    words (ids, enum values, numbers), KEY=VALUE selections and URLs pass."""
    if value.startswith("-") or "=" in value or "://" in value:
        return False
    return (value.startswith(("~", "./", "../")) or value in (".", "..")
            or ("/" in value and not Path(value).is_absolute()))


def _text(value: Any, label: str) -> str:
    text = str(value).strip()
    if "\x00" in text or "\n" in text or "\r" in text:
        raise FormError(f"{label}: one line, no control characters")
    if text.startswith("-"):  # GR-1: a field value never becomes an option (a refused one, or one swallowing a value)
        raise FormError(f"{label}: must not start with '-'")
    return text


def _tool_options(form: CommandForm, tokens: Sequence[str], where: str) -> None:
    """GR-45: a tool form's tokens name only the options the form declares, exactly (``--x`` or ``--x=value``). The
    tool's argparse expands abbreviations ("--allow" is --allow-network) and a second "-C" moves the run to another
    checkout, so every other token starting with "-" is refused."""
    allowed = form_options(form)
    if any(t.startswith("-") and t.split("=", 1)[0] not in allowed for t in tokens):
        raise FormError(f"{where}: {form.tool} takes only {', '.join(allowed)}, spelled in full")


def _retry_without_cap(command: str, names: set[str]) -> None:
    """``agentprov import`` refuses --retry-failed with --limit or --sample (AU-IMP-1: a retry drops every failed row
    of the snapshot before re-mapping, so a cap would leave the rows past it with no index row or register entry)."""
    if command == "import" and "--retry-failed" in names and names & {"--limit", "--sample"}:
        raise FormError("Retry failed units re-processes every failed unit: it cannot be combined with --limit or "
                        "--sample")


def build_spec(form: CommandForm, values: Mapping[str, Any], *, extra: str = "", label: str = "",
               conformance: bool = True, conformance_option: str | None = None) -> JobSpec:
    """The :class:`JobSpec` of ``form`` filled with ``values`` (missing keys use the field default).

    ``extra`` is "additional options", split like a POSIX shell line (no shell is ever run). ``conformance=False``
    unticks the D-432 box; it needs ``conformance_option`` (the CLI's flag, when it has one)."""
    argv: list[str] = list(form.words)
    user: list[str] = []  # GR-1: every token the user typed (field values, additional options), scanned at the end
    positionals: list[str] = []
    writes: list[str] = []
    reads: list[str] = []
    tier = form.tier
    for f in (*form.fields, *(GLOBAL_FIELDS if form.tool is None else ())):
        value = values.get(f.key, f.default)
        # `is False`, not `in (..., False)`: 0 == False, and a 0 or 0.0 the user typed is a value, not "unset"
        if value is None or value is False or value == "" or (f.kind == "list" and not value):
            if f.required:
                raise FormError(f"{f.label} is required")
            continue
        if f.kind == "bool":
            argv.append(str(f.option))
        elif f.kind == "int":
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise FormError(f"{f.label}: a whole number") from None
            if number < 0:
                raise FormError(f"{f.label}: not negative")
            argv += [str(f.option), str(number)]
        elif f.kind == "float":
            try:
                real = float(value)
            except (TypeError, ValueError):
                raise FormError(f"{f.label}: a number") from None
            if real != real or real in (float("inf"), float("-inf")) or real < 0:
                raise FormError(f"{f.label}: a finite number, not negative")
            argv += [str(f.option), repr(real)]
        elif f.kind == "multi":  # an argparse "append" option: --opt a --opt b
            items = value if isinstance(value, list | tuple) else _text(value, f.label).split()
            items = [_text(v, f.label) for v in items if str(v).strip()]
            if f.option in _PATH_OPTIONS:
                items = [_path(v, f.label) for v in items]
            user += items
            for item in items:
                argv += [str(f.option), item]
        elif f.kind == "list":
            items = value if isinstance(value, list | tuple) else _text(value, f.label).split()
            items = [_text(v, f.label) for v in items if str(v).strip()]
            if f.option in _PATH_OPTIONS:
                items = [_path(v, f.label) for v in items]
            user += items
            if f.option is None:
                positionals += items
            else:
                argv += [str(f.option), *items]
            if f.writes:
                writes += items
        else:
            text = _text(value, f.label)
            user.append(text)
            if f.kind == "choice" and f.choices and text not in f.choices:
                raise FormError(f"{f.label}: not one of the offered values")
            if f.kind in ("path", "dir"):
                text = _path(text, f.label)
            elif f.option == "--licence-file":  # GR-68: NAME=PATH; the CLI reads PATH as given (no "~", cwd-relative)
                name, eq, path = text.partition("=") if "=" in text else ("", "", text)
                text = f"{name}{eq}{_path(path, f.label)}"
            if f.option is None:
                positionals.append(text)
            else:
                argv += [str(f.option), text]
            if f.writes:
                writes.append(text)
            if form.reads_corpus == f.key:
                reads.append(text)
        tier = _max_tier(tier, f.tier)
    if form.name == "purge" and not _SHA256.fullmatch(str(values.get("object", ""))):
        raise FormError("Object: sha256: followed by 64 hex digits")
    if form.name == "purge" and not values.get("cache") and not values.get("corpus"):
        raise FormError("Purge needs a working corpus or the fetch cache")
    if form.name == "validate" and not (values.get("corpus") or values.get("files") or values.get("aer")):
        raise FormError("Validate needs a corpus, files or AER files")
    notes: list[str] = []
    if extra.strip():
        try:
            more = shlex.split(extra, posix=True)
        except ValueError:
            raise FormError("Additional options: unbalanced quotes") from None
        if any(ord(c) < 32 or ord(c) == 127 for token in more for c in token):  # GR-18: e.g. a pasted NUL
            raise FormError("Additional options: no control characters")
        if form.tool is not None:
            _tool_options(form, more, "Additional options")
        for i, token in enumerate(more):  # GR-20: "--out v" and "--out=v" alike; the value is never rewritten here
            name, eq, value = token.partition("=")
            given = [value] if eq else more[i + 1:i + 2]
            if name in _PATH_OPTIONS and any(not Path(v).is_absolute() for v in given):
                raise FormError(f"Additional options: {name}: {_NOT_ABSOLUTE}")
            if name.startswith("-") and any(_looks_relative(v) for v in given):  # GR-68: --aer, --store, --card …
                raise FormError(f"Additional options: {name}: {_NOT_ABSOLUTE}")
        if form.tool is None:  # GR-47: the field is the only route ("--out X" here would dodge the writer checks)
            fields = set(form_options(form))
            for name in (t.split("=", 1)[0] for t in more):
                if name in fields:
                    raise FormError(f"Additional options: {name} is a form field; set it there")
        user += more
        argv += more
    for token in user:  # not the tokens the GUI adds itself (the conformance option; the job manager's files)
        name = token.split("=", 1)[0]
        refused = REFUSED_OPTIONS.get(CONFORMANCE_OPTION if name == conformance_option else name)
        if refused:
            raise FormError(f"Additional options: {name} is not allowed ({refused})")
    names = {t.split("=", 1)[0] for t in argv}  # GR-2: option names, so "--limit=5" counts as "--limit"
    if form.prov_generating and not conformance:
        if "--release" in names:
            raise FormError("The PROV conformance check cannot be skipped in release mode (§8.3a)")
        if form.name == "recompute" and "--out" not in names:
            raise FormError("Recompute skips the PROV conformance check only when it writes a new corpus (--out)")
        if conformance_option is None:
            raise FormError("Skipping the PROV conformance check needs a CLI option this CLI does not have (G2c-5)")
        argv.append(conformance_option)
        notes.append(_CONFORMANCE_NOTE)
    argv += positionals
    release = "--release" in names
    if release and names & {"--select", "--limit", "--sample", "--in-process"}:
        raise FormError("Release mode forbids --select, --limit, --sample and --in-process")
    _retry_without_cap(form.name, names)
    final_tier = tier_of_argv(argv, _max_tier(tier, form.tier))
    if form.name == "recompute" and {"--out", "--dry-run"} <= names:
        raise FormError("Recompute: choose a dry run or a new corpus, not both")
    if form.name == "recompute" and not names & {"--out", "--dry-run"}:
        raise FormError("Recompute: choose a dry run or a new corpus")
    if "--dry-run" in names:
        writes = []
    return JobSpec(
        command=form.name,
        argv=tuple(argv),
        tier=final_tier,
        label=label or f"{form.title}" + (f" · {Path(writes[0]).name}" if writes else ""),
        writes=tuple(writes),
        reads=tuple(reads),
        slot=_slot(form, argv),
        destructive=form.name in _DESTRUCTIVE and "--dry-run" not in names,
        release=release,
        notes=tuple(notes),
        conformance_skipped=not conformance and form.prov_generating,
    )


def resume_spec(command: str, argv: Sequence[str], recorded_tier: str, label: str, *, tool: Sequence[str] = (),
                writes: Sequence[str] = (), slot: str | None = None, extra: Mapping[str, Any] | None = None) -> JobSpec:
    """GR-3: the spec that resumes a recorded job, rebuilt from its argv (job.json is not trusted for the safety facts).

    Every ``--yes`` goes (the confirmation adds it back after the typed digits); the tier is the highest of the record's,
    the form's and the argv's; destructive, release mode and the conformance skip come from the argv. A refused option,
    or a skip the form rules forbid, raises :class:`FormError`. A tool job (``tool`` is its program) must start with that
    program, followed only by the form's own options (GR-45), and resumes raw, with its own argv. Any other job must start
    with its form's words, and its slot comes from the argv (GR-46)."""
    form = FORMS.get(command)
    if form is None:
        raise FormError("This job's command is not one the GUI runs")
    base = _max_tier(form.tier, recorded_tier) if recorded_tier in TIERS else form.tier
    if form.tool is not None:
        if not tool or tuple(argv[: len(tool)]) != tuple(tool):
            raise FormError(f"This job does not run {form.tool} of the configured checkout")
        _tool_options(form, argv[len(tool):], "This job")
        return JobSpec(command, tuple(argv), tier_of_argv(argv[len(tool):], base), label, writes=tuple(writes),
                       slot=slot, extra={**(extra or {}), "raw": True})
    if not has_form_words(form, argv):
        raise FormError(f"This job does not run {' '.join(form.words)}")
    argv = [a for a in argv if a != "--yes"]
    names = {t.split("=", 1)[0] for t in argv}
    for name in sorted(names):
        refused = REFUSED_OPTIONS.get(name) if name != CONFORMANCE_OPTION else None
        if refused:
            raise FormError(f"{name} is not allowed ({refused})")
    skipped = CONFORMANCE_OPTION in names
    if skipped and (not form.prov_generating or "--release" in names
                    or (form.name == "recompute" and "--out" not in names)):
        raise FormError("The PROV conformance check cannot be skipped for this job (§8.3a)")
    release = "--release" in names
    if release and names & {"--select", "--limit", "--sample", "--in-process"}:
        raise FormError("Release mode forbids --select, --limit, --sample and --in-process")
    _retry_without_cap(form.name, names)
    return JobSpec(
        command=command,
        argv=tuple(argv),
        tier=tier_of_argv(argv, base),
        label=label,
        writes=tuple(writes),
        slot=_slot(form, argv),
        destructive=command in _DESTRUCTIVE and "--dry-run" not in argv,
        release=release,
        notes=(_CONFORMANCE_NOTE,) if skipped else (),
        conformance_skipped=skipped,
        extra=dict(extra or {}),
    )


def has_form_words(form: CommandForm, argv: Sequence[str]) -> bool:
    """GR-46: whether a recorded argv starts with its form's subcommand words (Resume and batch revalidation alike)."""
    return tuple(argv[: len(form.words)]) == form.words


def _slot(form: CommandForm, argv: Sequence[str]) -> str | None:
    """The global slot (§4.4): the fetch cache (``fetch``, ``import --fetch``, ``verify --against-pins``; no lock covers
    the cache) or backend environment builds."""
    if form.name == "fetch" or (form.name == "import" and "--fetch" in argv) or "--against-pins" in argv:
        return "cache"
    return form.slot


def form_options(form: CommandForm) -> list[str]:
    """Every option string a form can emit (checked against the CLI's ``--help`` by a test)."""
    return sorted({f.option for f in form.fields if f.option})


def option_table() -> dict[str, dict[str, str]]:
    """D-654: per CLI command path (``"import"``, ``"backends build"``, ``"migrate gate-d"``), every option the GUI
    reaches and how (``field:<form>``, ``global``, ``managed: …``), plus ``<positional>`` entries for positionals. The
    parity test compares it with the argparse tree; :data:`EXCLUDED_OPTIONS` lists the rest with reasons."""
    out: dict[str, dict[str, str]] = {}
    for form in FORMS.values():
        if form.tool is not None:
            continue
        row = out.setdefault(" ".join(form.words), {})
        for f in form.fields:
            row[f.option or f"<{f.key}>"] = f"field:{form.name}"
        for f in GLOBAL_FIELDS:
            row.setdefault(str(f.option), "global")
    for command, managed in (*MANAGED_OPTIONS.items(), *PENDING_MANAGED.items()):
        targets = list(out) if command == "*" else [command]
        for target in targets:
            for option, how in managed.items():
                out.setdefault(target, {}).setdefault(option, f"managed: {how}")
    return out
