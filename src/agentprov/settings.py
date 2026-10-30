"""User settings shared by the CLI and the GUI (D-703; reverse CLI parity D-700): ``$AGENTPROV_HOME/settings.json``.

One store, one implementation: ``agentprov settings list|get|set|unset`` and the GUI (which calls that command) read and
write the same file through this module. Never a key or other secret (keys live in the OS keychain, D-702), never corpus
text.

* **Closed schema.** :data:`SCHEMA` lists every key pattern with its type and bounds (and an optional validator); a key
  outside it is refused, so the file cannot become a dumping ground. A stored value that no longer validates reads as
  unset (and :func:`problems` names it).
* **Document:** ``{"format": "agentprov-settings/0.1", "values": {KEY: VALUE}}``, written atomically under a resource lock
  (``settings.json.lock``) with read-modify-write, so the CLI and the GUI can both write. Read with the strict loader.
* **Precedence** is the caller's (for example ``--base-url`` > the environment > ``endpoints.<name>.base_url`` > the
  registry default); :func:`get` returns ``None`` for an unset key, never a default.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["LOCAL_MODEL_FIELDS", "SCHEMA", "SETTINGS_FORMAT", "Key", "SettingsError", "get", "items", "local_model",
           "local_model_key", "path", "problems", "set", "unset"]

SETTINGS_FORMAT: Final = "agentprov-settings/0.1"
MAX_BYTES: Final = 1024 * 1024
_LIMITS: Final = IngestLimits().replace(max_json_bytes=MAX_BYTES, max_json_depth=8)
Value = str | int | float | bool | list[str]


class SettingsError(AgentProvError):
    """A key outside the schema or a value it refuses (exit 2)."""

    code = "settings.invalid"
    exit_code = 2


# ---------------------------------------------------------------------------------------------- validators
#: Private address ranges a LAN endpoint may use (D-698, the local-endpoints session). A copy of
#: agentprov_capture.endpoints.is_private_lan_host's ranges: dedupe once D-698 is on the base.
_LAN_NETS: Final = tuple(ipaddress.ip_network(n) for n in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7"))
_LOOPBACK_HOSTS: Final = ("127.0.0.1", "::1", "localhost")


def local_base_url(value: str) -> str | None:
    """``endpoints.<name>.base_url``: http(s) on loopback or a literal private IP; no user info, query or fragment;
    never a host name (other than ``localhost``). ``None`` when good, else the reason."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return "not a URL"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "needs http:// or https:// and a host"
    if parts.username or parts.password or parts.query or parts.fragment:
        return "no user info, query or fragment"
    host = parts.hostname
    if host in _LOOPBACK_HOSTS:
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "a loopback host or a literal private IP address, not a host name"
    if ip.is_loopback or any(ip in net for net in _LAN_NETS):
        return None
    return "a loopback or private (LAN) address only"


_DOI: Final = re.compile(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+")
_ORCID: Final = re.compile(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]")
#: A Zenodo community identifier (the uploader's ``--community`` pattern).
_COMMUNITY: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}")
#: The AgentDojo-PROV concept DOI: AgentPROV is never deposited under it (D-5).
_FORBIDDEN_CONCEPT: Final = "10.5281/zenodo.20692312"


def concept_doi(value: str) -> str | None:
    """``zenodo.concept_doi`` (D-880): a DOI, never the AgentDojo-PROV concept (D-5)."""
    if _DOI.fullmatch(value) is None:
        return "not a DOI 10.NNNN/..."
    return "the AgentDojo-PROV concept DOI: AgentPROV is never deposited under it (D-5)" \
        if value == _FORBIDDEN_CONCEPT else None


def orcid(value: str) -> str | None:
    return None if _ORCID.fullmatch(value) else "not an ORCID iD 0000-0000-0000-000X"


def community(value: str) -> str | None:
    return None if _COMMUNITY.fullmatch(value) else "not a Zenodo community identifier (lower-case letters, digits, - and _)"


def model_folder(value: str) -> str | None:
    """``local_models.<endpoint>.<model id>.model_dir``: an absolute path (a folder the user names; checked when it is
    read, not here). ``None`` when good, else the reason."""
    if not os.path.isabs(value):
        return "an absolute path"
    return None


@dataclass(frozen=True, slots=True)
class Key:
    pattern: str  # a regex over the full key
    kind: str  # str | int | float | bool | list | choice
    help: str
    lo: float | None = None
    hi: float | None = None
    choices: tuple[str, ...] = ()
    validator: Callable[[str], str | None] | None = None

    def matches(self, key: str) -> bool:
        return re.fullmatch(self.pattern, key) is not None


_NAME = r"[a-z0-9_-]{1,40}"
_PART = r"[A-Za-z0-9_.-]{1,80}"
_COMMANDS = r"(import|derive|recompute|validate|verify|render|run)"
#: a served model id as a key segment (D-828): a label, never a path (it may hold ``.``, ``:`` and ``/``; the endpoint
#: before it and the field after it are fixed, so the full-key match stays unambiguous)
_MODEL = r"[A-Za-z0-9_][A-Za-z0-9_.:/@+-]{0,199}"
#: the model facts a user can give per local model (D-828): the run flags of N.2.1a(3), in the same units
LOCAL_MODEL_FIELDS: Final = ("model_dir", "model_size_gb", "active_params_b", "context_tokens", "kv_gb_per_trace")

SCHEMA: Final[tuple[Key, ...]] = (
    Key(rf"endpoints\.{_NAME}\.base_url", "str", "a local endpoint's base URL (loopback or LAN; D-691, D-698)",
        validator=local_base_url),
    # a local model's facts (Settings › Local models; D-828): used when the run flag is not given
    Key(rf"local_models\.{_NAME}\.{_MODEL}\.model_dir", "str", "the model's folder (--model-dir; an absolute path)",
        validator=model_folder),
    Key(rf"local_models\.{_NAME}\.{_MODEL}\.model_size_gb", "float", "weight size, decimal GB (--model-size-gb)",
        0.001, 100_000),
    Key(rf"local_models\.{_NAME}\.{_MODEL}\.active_params_b", "float",
        "active parameters, billions (--active-params-b)", 0.001, 100_000),
    Key(rf"local_models\.{_NAME}\.{_MODEL}\.context_tokens", "int", "context tokens per trace (--context-tokens)",
        1, 100_000_000),
    Key(rf"local_models\.{_NAME}\.{_MODEL}\.kv_gb_per_trace", "float", "KV cache per trace, decimal GB "
        "(--kv-gb-per-trace)", 0.001, 100_000),
    # dev runs (design §19; D-544)
    Key(r"devrun\.samples", "int", "executions per source/part", 0, 100_000),
    Key(rf"devrun\.override\.{_NAME}(\.{_PART})?", "int",
        "executions for one source (devrun.override.SOURCE) or source/part (…SOURCE.PART); 0 skips it", 0, 100_000),
    Key(r"devrun\.(include|exclude)", "list", "source or source/part names"),
    Key(r"devrun\.sample_mode", "choice", "first, spread or random", choices=("first", "spread", "random")),
    Key(r"devrun\.seed", "int", "seed for random sampling", 0, 2**31 - 1),
    Key(r"devrun\.keep", "int", "dev-run folders kept", 1, 1000),
    Key(r"devrun\.queue_cpu", "int", "CPUs a dev-run step reserves in the job queue", 1, 256),
    Key(r"devrun\.prov_conformance", "bool", "run the PROV conformance check in dev runs"),
    Key(r"devrun\.live\.transport", "choice", "scripted or real", choices=("scripted", "real")),
    Key(r"devrun\.live\.tasks_per_suite", "int", "user tasks per suite", 1, 1000),
    Key(r"devrun\.live\.attacks_per_task", "int", "attacks per task", 0, 100),
    Key(r"devrun\.live\.suites", "list", "suites (empty: all)"),
    Key(r"devrun\.live\.call_cap", "int", "model calls before the run is drained", 0, 1_000_000),
    Key(r"devrun\.live\.cost_cap", "float", "USD the p90 estimate must stay under", 0, 1_000_000),
    # estimate defaults (D-653)
    Key(r"estimate\.default\.(calls|tokens_in|tokens_cached|tokens_out|seconds)_(p50|p90)", "float",
        "a default assumption for the estimate", 0, 10_000_000),
    # compute (Settings › Compute)
    Key(rf"compute\.jobs\.{_COMMANDS}", "int", "default --jobs for a command (0: the host default)", 0, 512),
    Key(r"compute\.queue_heavy", "bool", "run heavy jobs through the shared job queue"),
    Key(r"compute\.queue_cpu", "int", "CPUs a queued job reserves", 1, 256),
    Key(r"compute\.preset", "str", "the host preset Run live's Tune uses (m5ultra, or a preset name)",
        validator=lambda v: None if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", v) else "a preset name ([a-z0-9_-])"),
    Key(r"compute\.start_stagger", "float", "live runs: --start-stagger in seconds", 0, 3600),
    Key(r"compute\.validation_cache_gib", "float", "the tier-4 round-trip cache's size cap in GiB (D-894; unset: 2; "
        "32 on the Mac Studio)", 1, 4096),
    # the job queue's machine budget for jobs `agentprov jobs start` runs (D-704: AGENTPROV_JOB_*_BUDGET)
    Key(r"compute\.cpu_budget", "int", "the job queue's CPU budget (AGENTPROV_JOB_CPU_BUDGET)", 1, 4096),
    Key(r"compute\.mem_gib_budget", "float", "the job queue's memory budget in GiB (AGENTPROV_JOB_MEM_GIB_BUDGET)",
        0.001, 1_000_000),
    Key(r"compute\.gate_n", "int", "test gate workers (pytest -n)", 1, 256),
    # continuous integration (Settings › CI; D-431)
    Key(r"ci\.default_target", "choice", "local, github or mac-studio", choices=("local", "github", "mac-studio")),
    # provider model lists (agentprov models, the local-endpoints session's D-730..D-739): off until switched on
    Key(r"models\.auto_refresh", "bool", "refresh each provider's model list at most once every 24 h (network)"),
    # jobs (D-704)
    Key(r"jobs\.retention", "int", "ended jobs kept", 10, 10_000),
    Key(r"jobs\.retention_days", "int", "days an ended job is kept", 1, 3650),
    Key(r"jobs\.continue_on_failure", "bool", "batches continue after exit 4 or 70"),
    # D-880: the GUI's Zenodo pane. Prefills only: release.toml stays the record (H.10.2) and the uploader's --target
    # keeps no default (D-790). The tokens live in the OS keychain (agentprov keys), never here.
    Key(r"zenodo\.target_preselect", "choice", "the target the Create Zenodo drafts dialog preselects (never a default "
        "of --target)", choices=("sandbox", "production")),
    Key(r"zenodo\.communities", "list", "Zenodo community identifiers for new drafts (--community)", validator=community),
    Key(r"zenodo\.concept_doi", "str", "the AgentPROV concept DOI for a new version (prefills release.toml concept_doi)",
        validator=concept_doi),
    Key(r"zenodo\.creators\.[0-9]{1,2}\.(name|affiliation)", "str", "a default creator (prefills release.toml "
        "[[creators]])"),
    Key(r"zenodo\.creators\.[0-9]{1,2}\.orcid", "str", "a default creator's ORCID iD", validator=orcid),
)


def _schema(key: str) -> Key:
    for k in SCHEMA:
        if k.matches(key):
            return k
    raise SettingsError(f"unknown setting {key[:80]!r}; see 'agentprov settings list --schema'")


def coerce(key: str, value: Any) -> Value:
    """``value`` (a CLI string or a JSON value) as the key's type, or :class:`SettingsError`."""
    k = _schema(key)
    try:
        if k.kind == "bool":
            if isinstance(value, bool):
                out: Value = value
            elif isinstance(value, str) and value.lower() in ("true", "false", "yes", "no", "1", "0", "on", "off"):
                out = value.lower() in ("true", "yes", "1", "on")
            else:
                raise ValueError
        elif k.kind == "int":
            if isinstance(value, bool):
                raise ValueError
            out = int(value)
        elif k.kind == "float":
            if isinstance(value, bool):
                raise ValueError
            out = float(value)
            if not math.isfinite(out):
                raise ValueError
        elif k.kind == "list":
            items_ = value if isinstance(value, list) else [v for v in str(value).replace(",", " ").split() if v]
            if not all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_./:@-]{1,120}", v) for v in items_):
                raise ValueError
            out = [str(v) for v in items_][:1000]
        else:
            if not isinstance(value, str) or len(value) > 500 or any(ord(c) < 32 for c in value):
                raise ValueError
            out = value
    except (TypeError, ValueError):
        raise SettingsError(f"{key}: not a valid {k.kind}") from None
    if isinstance(out, int | float) and not isinstance(out, bool) and (
            (k.lo is not None and out < k.lo) or (k.hi is not None and out > k.hi)):
        raise SettingsError(f"{key}: out of range [{k.lo:g}, {k.hi:g}]")
    if k.kind == "choice" and out not in k.choices:
        raise SettingsError(f"{key}: one of {', '.join(k.choices)}")
    if k.validator is not None:
        for item in out if isinstance(out, list) else [out] if isinstance(out, str) else []:
            reason = k.validator(item)
            if reason is not None:
                raise SettingsError(f"{key}: {reason}")
    return out


# ---------------------------------------------------------------------------------------------- the store
def path(home: Path | None = None) -> Path:
    if home is None:
        raw = os.environ.get("AGENTPROV_HOME")
        home = Path(raw).expanduser() if raw else Path.home() / ".agentprov"
    return Path(os.path.abspath(home)) / "settings.json"


def _read(p: Path) -> dict[str, Any]:
    try:
        with open(p, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SettingsError(f"the settings file cannot be read ({type(exc).__name__})") from None
    if len(data) > MAX_BYTES:
        raise SettingsError("the settings file is larger than 1 MiB")
    try:
        doc = strict_json_loads(data.rstrip(b"\n"), _LIMITS)
    except IngestError as exc:
        raise SettingsError(f"the settings file is not strict JSON ({exc.code})") from None
    if not isinstance(doc, dict) or doc.get("format") != SETTINGS_FORMAT or not isinstance(doc.get("values"), dict):
        raise SettingsError("the settings file is not an agentprov-settings/0.1 document")
    return dict(doc["values"])


def _valid(values: Mapping[str, Any]) -> Iterator[tuple[str, Value]]:
    for key, value in sorted(values.items()):
        try:
            yield key, coerce(key, value)
        except SettingsError:
            continue


def get(key: str, *, home: Path | None = None) -> Value | None:
    _schema(key)
    return dict(_valid(_read(path(home)))).get(key)


def items(prefix: str = "", *, home: Path | None = None) -> dict[str, Value]:
    return {k: v for k, v in _valid(_read(path(home))) if k.startswith(prefix)}


def local_model_key(endpoint: str, model_id: str, field: str) -> str:
    """The settings key of one local model fact (D-828); :class:`SettingsError` when the id cannot be a key."""
    if field not in LOCAL_MODEL_FIELDS:
        raise SettingsError(f"unknown local model field {field[:40]!r}")
    key = f"local_models.{endpoint}.{model_id}.{field}"
    _schema(key)
    return key


def local_model(endpoint: str, model_id: str, *, home: Path | None = None) -> dict[str, Value]:
    """The stored facts of one local model (D-828), by field name; ``{}`` when none are set or the id cannot be a key.
    Nothing is defaulted: the caller's precedence is flag > setting > model folder > preset."""
    prefix = f"local_models.{endpoint}.{model_id}."
    try:
        _schema(prefix + LOCAL_MODEL_FIELDS[0])
    except SettingsError:
        return {}
    return {k[len(prefix):]: v for k, v in items(prefix, home=home).items() if k[len(prefix):] in LOCAL_MODEL_FIELDS}


def problems(*, home: Path | None = None) -> list[str]:
    """Stored keys that no longer validate (they read as unset)."""
    out = []
    for key, value in sorted(_read(path(home)).items()):
        try:
            coerce(key, value)
        except SettingsError as exc:
            out.append(str(exc))
    return out


def _write(home: Path | None, change: Callable[[dict[str, Any]], None]) -> None:
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.io.locks import ResourceLock

    p = path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    with ResourceLock(p.with_name("settings.json.lock"), what="the settings file", command="settings"):
        values = _read(p)
        change(values)
        doc = {"format": SETTINGS_FORMAT, "values": dict(sorted(values.items()))}
        atomic_write_bytes(p, json.dumps(doc, sort_keys=True, indent=1).encode("utf-8") + b"\n", mode=0o600)


def set(key: str, value: Any, *, home: Path | None = None) -> Value:  # noqa: A001 - the API name the callers use
    clean = coerce(key, value)
    _write(home, lambda values: values.__setitem__(key, clean))
    return clean


def unset(key: str, *, home: Path | None = None) -> bool:
    _schema(key)
    found = [False]

    def change(values: dict[str, Any]) -> None:
        found[0] = values.pop(key, None) is not None

    _write(home, change)
    return found[0]
