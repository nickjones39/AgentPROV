"""Host presets, model facts, model-aware concurrency and the local-server preflight (MN N.2.1a; DECISIONS D-9, D-10).

Layout: this module holds the code; the data is ``presets/presets.toml`` beside it. ``presets/`` is a data directory
with no ``__init__.py`` (M.0 rule 2; the same arrangement as ``aer/rules.py`` and ``aer/rules/``), so this module wins
the import and the data is read through :mod:`importlib.resources`.

Everything here is pure or bounded:

* :func:`load_preset` reads package data; :func:`check_host` compares a preset with a ``HostProfile`` (facts only, no
  ``sys.platform``); a mismatch is reported, never refused (N.2.1a(2)).
* :func:`model_facts_from_dir` reads a model directory as **untrusted input**: ``config.json`` only through
  ``agentprov.ingest`` (no-follow open, bounded strict JSON), weight sizes by ``stat`` (weights are never read).
  Facts the config does not give stay unknown; nothing is guessed.
* :func:`local_concurrency` is a pure function from preset, facts and host to a :class:`ConcurrencyPlan` carrying the
  three terms of N.2.1a(3), the binding one, and every input with its source.
* :func:`preflight_local_server` is the only network code: a loopback-only ``GET <base>/models`` through the stdlib.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import math
import os
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any, Final, Literal
from urllib.parse import urlsplit

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest import IngestLimits, open_evidence, strict_json_loads
from agentprov.ingest.quote import escape_untrusted

if TYPE_CHECKING:
    from agentprov.host import HostProfile
    from agentprov_capture.endpoints import Endpoint

__all__ = [
    "GB",
    "GIB",
    "PRESET_ALIASES",
    "ComputeRow",
    "ConcurrencyPlan",
    "ExpectedHost",
    "Fact",
    "HostMismatch",
    "MoEInfo",
    "ModelFacts",
    "PlanInput",
    "PreflightResult",
    "Preset",
    "PresetUsageError",
    "ServerPreflightError",
    "check_host",
    "gb_to_bytes",
    "load_preset",
    "local_concurrency",
    "model_facts_from_dir",
    "preflight_local_server",
    "preset_record",
]

GIB: Final = 1024**3
GB: Final = 10**9  # the `--model-size-gb` and `--kv-gb-per-trace` flags are decimal gigabytes
PRESET_ALIASES: Final[dict[str, str]] = {"m5ultra": "m5ultra"}

Source = Literal["model_dir", "flag", "settings", "preset", "default", "unknown"]


# --------------------------------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------------------------------


class PresetUsageError(AgentProvError):
    """A usage error (CLI exit 2): unknown preset, model does not fit, facts missing, invalid jobs."""

    code = "run.preset.usage"
    exit_code = 2


class ServerPreflightError(AgentProvError):
    """The local-server preflight failed. Exit 3 for an unreachable server, a bad listing or an unlisted model
    (N.2.1a(1)); exit 4 (refused, N.1.3) for a non-loopback or non-https URL."""

    code = "run.endpoint.preflight"
    exit_code = 3


# --------------------------------------------------------------------------------------------------------------
# Preset data
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExpectedHost:
    os_family: str
    arch: str
    min_memory_gib: int


@dataclass(frozen=True, slots=True)
class ComputeRow:
    """``max_active_params_b`` None is the catch-all row (A above the previous bound)."""

    max_active_params_b: float | None
    jobs: int
    #: ``measured`` (a ``run --tune-jobs`` recommendation) or ``provisional`` (D-823); ``None`` before version 2
    basis: str | None = None


@dataclass(frozen=True, slots=True)
class CellSeconds:
    """A measured time basis for the local-run estimate (D-826, Q5): the wall seconds per cell of the recommended arm
    of a ``--tune-jobs`` sweep, for models up to ``max_active_params_b`` (``None``: the catch-all row)."""

    max_active_params_b: float | None
    p50: float
    p90: float
    jobs: int
    source: str


@dataclass(frozen=True, slots=True)
class Preset:
    name: str
    version: int
    description: str
    endpoint: str
    expected_host: ExpectedHost
    start_stagger_per_worker_s: float
    request_timeout_s: float
    gpu_budget_fraction: float
    reserve_gib: float
    per_worker_reserve_gib: float
    compute_caps: tuple[ComputeRow, ...]
    default_context_tokens: int
    kv_bytes: int
    kv_trace_fallback_gib: float
    server_max_concurrency_default: int
    evidence: tuple[tuple[str, str], ...]  # (claim, source)
    data_sha256: str  # digest of presets.toml (recorded with the preset, M.1.3)
    #: D-823: measured on the target machine (``run --tune-jobs``); live runs with an uncalibrated preset are refused
    calibrated: bool = False
    calibration: str | None = None  # the committed report the measured values come from
    cell_seconds: tuple[CellSeconds, ...] = ()  # D-826: the local-run estimate's time basis

    def to_json(self) -> dict[str, Any]:
        """Every value the preset sets, JSON-serialisable (the ``resolved`` block of the producer record)."""
        return {
            "name": self.name,
            "version": self.version,
            "data_sha256": self.data_sha256,
            "endpoint": self.endpoint,
            "expected_host": {
                "os_family": self.expected_host.os_family,
                "arch": self.expected_host.arch,
                "min_memory_gib": self.expected_host.min_memory_gib,
            },
            "start_stagger_per_worker_s": self.start_stagger_per_worker_s,
            "request_timeout_s": self.request_timeout_s,
            "gpu_budget_fraction": self.gpu_budget_fraction,
            "reserve_gib": self.reserve_gib,
            "per_worker_reserve_gib": self.per_worker_reserve_gib,
            "compute_caps": [{"max_active_params_b": r.max_active_params_b, "jobs": r.jobs,
                              **({"basis": r.basis} if r.basis is not None else {})} for r in self.compute_caps],
            "default_context_tokens": self.default_context_tokens,
            "kv_bytes": self.kv_bytes,
            "kv_trace_fallback_gib": self.kv_trace_fallback_gib,
            "server_max_concurrency_default": self.server_max_concurrency_default,
            "evidence": [{"claim": c, "source": s} for c, s in self.evidence],
            "calibrated": self.calibrated,
            **({"calibration": self.calibration} if self.calibration is not None else {}),
            **({"cell_seconds": [{"max_active_params_b": c.max_active_params_b, "p50": c.p50, "p90": c.p90,
                                  "jobs": c.jobs, "source": c.source} for c in self.cell_seconds]}
               if self.cell_seconds else {}),
        }

    def cell_seconds_for(self, active_params_b: float | None) -> CellSeconds | None:
        """The measured seconds-per-cell row for a model of ``active_params_b`` (D-826); unknown A takes the last
        (largest) row, as ``J_compute`` does. ``None`` when the preset has none, or when the last row has a bound and A
        is unknown or above it (no class was measured there: the estimate keeps the priors' time)."""
        if not self.cell_seconds:
            return None
        for row in self.cell_seconds:
            bound = row.max_active_params_b
            if bound is None or (active_params_b is not None and active_params_b <= bound):
                return row
        return None


def _num(table: Mapping[str, Any], key: str, *, positive: bool = True, integer: bool = False) -> Any:
    value: Any = table.get(key)
    kind = "integer" if integer else "number"
    ok = isinstance(value, int) if integer else isinstance(value, int | float)
    if ok and not isinstance(value, bool):
        floor = 1e-300 if positive else 0
        if value >= floor:
            return value
    raise AgentProvError(
        f"preset data: {key} must be a {'positive' if positive else 'non-negative'} {kind}", code="preset.data", exit_code=70
    )


def _parse_preset(name: str, table: Mapping[str, Any], digest: str) -> Preset:
    def bad(why: str) -> AgentProvError:
        return AgentProvError(f"preset data {name!r}: {why}", code="preset.data", exit_code=70)

    host = table.get("expected_host")
    if not isinstance(host, dict) or not isinstance(host.get("os_family"), str) or not isinstance(host.get("arch"), str):
        raise bad("expected_host needs os_family and arch")
    rows_raw = table.get("compute_caps")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise bad("compute_caps must be a non-empty array of tables")
    rows: list[ComputeRow] = []
    previous = 0.0
    for i, raw in enumerate(rows_raw):
        bound = raw.get("max_active_params_b")
        last = i == len(rows_raw) - 1
        if last != (bound is None):
            raise bad("only the last compute_caps row may omit max_active_params_b (it is the catch-all)")
        if bound is not None:
            if isinstance(bound, bool) or not isinstance(bound, int | float) or not float(bound) > previous:
                raise bad("compute_caps bounds must increase")
            previous = float(bound)
        basis = raw.get("basis")
        if basis is not None and basis not in ("measured", "provisional"):
            raise bad("compute_caps basis must be measured or provisional")
        rows.append(ComputeRow(None if bound is None else float(bound), _num(raw, "jobs", integer=True), basis))
    fraction = _num(table, "gpu_budget_fraction")
    if fraction > 1:
        raise bad("gpu_budget_fraction must be in (0, 1]")
    evidence = tuple((str(e["claim"]), str(e["source"])) for e in table.get("evidence", []))
    calibrated = table.get("calibrated", False)
    if not isinstance(calibrated, bool):
        raise bad("calibrated must be a boolean")
    calibration = table.get("calibration")
    if calibration is not None and not isinstance(calibration, str):
        raise bad("calibration names the committed report (a string)")
    if calibrated and (calibration is None or any(r.basis is None for r in rows)):
        raise bad("a calibrated preset names its calibration report and the basis of every compute_caps row")
    secs: list[CellSeconds] = []
    previous = 0.0
    raw_secs = table.get("cell_seconds", [])
    for i, raw in enumerate(raw_secs if isinstance(raw_secs, list) else []):
        bound = raw.get("max_active_params_b")
        if bound is None and i != len(raw_secs) - 1:
            raise bad("only the last cell_seconds row may omit max_active_params_b (it is the catch-all)")
        if bound is not None:
            if isinstance(bound, bool) or not isinstance(bound, int | float) or not float(bound) > previous:
                raise bad("cell_seconds bounds must increase")
            previous = float(bound)
        p50, p90 = float(_num(raw, "p50")), float(_num(raw, "p90"))
        if p90 < p50:
            raise bad("cell_seconds p90 must be >= p50")
        secs.append(CellSeconds(None if bound is None else float(bound), p50, p90, _num(raw, "jobs", integer=True),
                                str(raw.get("source", ""))))
    return Preset(
        name=name,
        version=_num(table, "version", integer=True),
        description=str(table.get("description", "")),
        endpoint=str(table.get("endpoint", "")),
        expected_host=ExpectedHost(host["os_family"], host["arch"], _num(host, "min_memory_gib", integer=True)),
        start_stagger_per_worker_s=_num(table, "start_stagger_per_worker_s", positive=False),
        request_timeout_s=_num(table, "request_timeout_s"),
        gpu_budget_fraction=float(fraction),
        reserve_gib=_num(table, "reserve_gib", positive=False),
        per_worker_reserve_gib=_num(table, "per_worker_reserve_gib", positive=False),
        compute_caps=tuple(rows),
        default_context_tokens=_num(table, "default_context_tokens", integer=True),
        kv_bytes=_num(table, "kv_bytes", integer=True),
        kv_trace_fallback_gib=_num(table, "kv_trace_fallback_gib"),
        server_max_concurrency_default=_num(table, "server_max_concurrency_default", integer=True),
        evidence=evidence,
        data_sha256=digest,
        calibrated=calibrated,
        calibration=calibration,
        cell_seconds=tuple(secs),
    )


@cache
def _load_all() -> dict[str, Preset]:
    raw = resources.files("agentprov").joinpath("presets").joinpath("presets.toml").read_bytes()
    doc = tomllib.loads(raw.decode("utf-8"))
    if doc.get("format") != 1 or not isinstance(doc.get("presets"), dict):
        raise AgentProvError("preset data: unsupported presets.toml format", code="preset.data", exit_code=70)
    digest = hashlib.sha256(raw).hexdigest()
    return {name: _parse_preset(name, table, digest) for name, table in sorted(doc["presets"].items())}


def load_preset(name: str) -> Preset:
    """Load a preset (or alias) from package data. Unknown name: :class:`PresetUsageError` (``run.preset.unknown``)."""
    key = PRESET_ALIASES.get(name, name)
    presets = _load_all()
    if key not in presets:
        raise PresetUsageError(
            f"unknown preset {escape_untrusted(name)!r}; known: {sorted(presets)}", code="run.preset.unknown"
        )
    return presets[key]


# --------------------------------------------------------------------------------------------------------------
# Host check
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HostMismatch:
    """One way the host differs from the preset's expectation. Recorded and warned, never refused."""

    field: str  # os_family | arch | memory_bytes
    expected: str
    actual: str

    def message(self) -> str:
        return f"host {self.field} is {self.actual}, preset expects {self.expected}"

    def to_json(self) -> dict[str, str]:
        return {"field": self.field, "expected": self.expected, "actual": self.actual}


def check_host(preset: Preset, host: HostProfile) -> list[HostMismatch]:
    """Compare the probed facts with ``preset.expected_host`` (D-7: facts, not ``sys.platform``)."""
    exp = preset.expected_host
    out: list[HostMismatch] = []
    if host.os_family != exp.os_family:
        out.append(HostMismatch("os_family", exp.os_family, host.os_family))
    if host.arch != exp.arch:
        out.append(HostMismatch("arch", exp.arch, host.arch))
    need = exp.min_memory_gib * GIB
    if host.memory_bytes is None:
        out.append(HostMismatch("memory_bytes", f">= {exp.min_memory_gib} GiB", "unknown"))
    elif host.memory_bytes < need:
        out.append(HostMismatch("memory_bytes", f">= {exp.min_memory_gib} GiB", f"{host.memory_bytes / GIB:.1f} GiB"))
    return out


# --------------------------------------------------------------------------------------------------------------
# Model facts
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Fact[T]:
    """A value with where it came from: ``model_dir | flag | settings | preset | default``, or ``unknown`` (value
    None). ``settings`` is a user's ``local_models.*`` setting (D-828)."""

    value: T | None
    source: Source
    note: str = ""

    @property
    def known(self) -> bool:
        return self.value is not None


_UNKNOWN: Final[Fact[Any]] = Fact(None, "unknown")


@dataclass(frozen=True, slots=True)
class MoEInfo:
    num_experts: int
    experts_per_tok: int


@dataclass(frozen=True, slots=True)
class ModelFacts:
    """What is known about the model. Unknown stays unknown: no field is ever estimated from another source."""

    weights_bytes: Fact[int] = _UNKNOWN
    active_params_b: Fact[float] = _UNKNOWN
    total_params_b: Fact[float] = _UNKNOWN
    layers: Fact[int] = _UNKNOWN
    kv_heads: Fact[int] = _UNKNOWN
    head_dim: Fact[int] = _UNKNOWN
    context_tokens: Fact[int] = _UNKNOWN
    kv_bytes: Fact[int] = _UNKNOWN  # bytes per KV element
    kv_bytes_per_trace: Fact[int] = _UNKNOWN  # explicit KV_trace (`--kv-gb-per-trace`)
    moe: Fact[MoEInfo] = _UNKNOWN  # unknown also when the model is dense or the config is silent
    followed_symlinks: bool = False  # a symlink in the model directory was followed (Hugging Face cache layout)
    notes: tuple[str, ...] = ()

    def with_flags(
        self,
        *,
        model_size_gb: float | None = None,
        active_params_b: float | None = None,
        context_tokens: int | None = None,
        kv_gb_per_trace: float | None = None,
        source: Source = "flag",
        label: str = "",
    ) -> ModelFacts:
        """Apply the manual flags; a flag overrides (or replaces) what the model directory gave. With
        ``source="settings"`` the values are a user's ``local_models.*`` settings (D-828), applied before the flags;
        ``label`` is the settings key prefix the notes cite."""
        out = self

        def note(flag: str, field: str) -> str:
            return f"{label}{field}" if source == "settings" else flag

        if model_size_gb is not None:
            out = replace(out, weights_bytes=Fact(gb_to_bytes(model_size_gb), source,
                                                  note("--model-size-gb", "model_size_gb")))
        if active_params_b is not None:
            if not active_params_b > 0:
                raise PresetUsageError("--active-params-b must be > 0", code="run.model.flag")
            out = replace(out, active_params_b=Fact(float(active_params_b), source,
                                                    note("--active-params-b", "active_params_b")))
        if context_tokens is not None:
            if context_tokens < 1:
                raise PresetUsageError("--context-tokens must be >= 1", code="run.model.flag")
            out = replace(out, context_tokens=Fact(int(context_tokens), source,
                                                   note("--context-tokens", "context_tokens")))
        if kv_gb_per_trace is not None:
            out = replace(out, kv_bytes_per_trace=Fact(gb_to_bytes(kv_gb_per_trace), source,
                                                       note("--kv-gb-per-trace", "kv_gb_per_trace")))
        return out

    def to_json(self) -> dict[str, Any]:
        def one(f: Fact[Any]) -> dict[str, Any]:
            value = {"num_experts": f.value.num_experts, "experts_per_tok": f.value.experts_per_tok} if isinstance(f.value, MoEInfo) else f.value
            return {"value": value, "source": f.source, "note": f.note}

        out: dict[str, Any] = {
            name: one(getattr(self, name))
            for name in (
                "weights_bytes", "active_params_b", "total_params_b", "layers", "kv_heads", "head_dim",
                "context_tokens", "kv_bytes", "kv_bytes_per_trace", "moe",
            )
        }
        out["followed_symlinks"] = self.followed_symlinks
        out["notes"] = list(self.notes)
        return out


def gb_to_bytes(gb: float) -> int:
    """Decimal gigabytes (the flag unit) to bytes, rounded to an integer."""
    if isinstance(gb, bool) or not isinstance(gb, int | float) or not math.isfinite(gb) or gb <= 0:
        raise PresetUsageError("a size flag must be a positive finite number of GB", code="run.model.flag")
    return round(Fraction(str(gb)) * GB)


#: The largest architecture integer read from config.json. Real models are orders of magnitude below it (vocabularies of
#: a few hundred thousand, hidden sizes in the tens of thousands); a larger value in the untrusted file is left unknown,
#: so the derived counts stay finite and every recorded fact stays inside the JSON integer domain.
MAX_ARCHITECTURE_INT: Final = 2**24


def _posint(cfg: Mapping[str, Any], key: str) -> int | None:
    value = cfg.get(key)
    ok = isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_ARCHITECTURE_INT
    return value if ok else None


#: ``model_type`` values whose decoder is a standard gated-MLP transformer, so the structural parameter count below
#: applies. Any other type leaves the active parameter count unknown (a wrong guess would raise ``jobs``).
_GATED_MLP_TYPES: Final = frozenset(
    {"llama", "mistral", "mixtral", "qwen2", "qwen2_moe", "qwen3", "qwen3_moe", "gemma", "gemma2", "gemma3_text", "phi3", "olmo2", "granite"}
)
#: Config keys that change the parameter structure in ways the formula does not model (MLA, hybrid or linear
#: attention, dense-then-sparse layer mixes).
_UNMODELLED_KEYS: Final = ("kv_lora_rank", "layer_types", "full_attention_interval", "linear_num_value_heads", "first_k_dense_replace")
_EXPERT_COUNT_KEYS: Final = ("num_experts", "num_local_experts", "n_routed_experts")


def _structural_params(cfg: Mapping[str, Any], experts: MoEInfo | None) -> tuple[int, int] | None:
    """(total, active) parameter counts from the declared architecture, or None when a field or a feature is not
    modelled. Counts attention, gated-MLP (3 matrices), router, shared experts, embedding and an untied output head;
    norms and biases (< 0.1 %) are ignored. Checked against Qwen3-30B-A3B (about 30.5 B total, 3.3 B active)."""
    if cfg.get("model_type") not in _GATED_MLP_TYPES or any(cfg.get(k) for k in _UNMODELLED_KEYS):
        return None
    if cfg.get("mlp_only_layers") or cfg.get("decoder_sparse_step") not in (None, 1):
        return None
    h, layers, heads = _posint(cfg, "hidden_size"), _posint(cfg, "num_hidden_layers"), _posint(cfg, "num_attention_heads")
    vocab, tie = _posint(cfg, "vocab_size"), cfg.get("tie_word_embeddings")
    if h is None or layers is None or heads is None or vocab is None or not isinstance(tie, bool):
        return None
    kv = _posint(cfg, "num_key_value_heads") or heads
    hd = _posint(cfg, "head_dim") or (h // heads if h % heads == 0 else None)
    if hd is None:
        return None
    attn = h * heads * hd + 2 * h * kv * hd + heads * hd * h
    embed = vocab * h * (1 if tie else 2)
    if experts is None:
        inter = _posint(cfg, "intermediate_size")
        if inter is None:
            return None
        total = embed + layers * (attn + 3 * h * inter)
        return total, total
    expert_inter = _posint(cfg, "moe_intermediate_size") or (
        _posint(cfg, "intermediate_size") if cfg.get("model_type") == "mixtral" else None
    )
    if expert_inter is None:
        return None
    shared = 0
    shared_inter = _posint(cfg, "shared_expert_intermediate_size")
    if shared_inter is not None:
        shared += 3 * h * shared_inter + h  # shared expert and its gate
    n_shared = _posint(cfg, "n_shared_experts")
    if n_shared is not None:
        shared += n_shared * 3 * h * expert_inter
    router = h * experts.num_experts
    per_expert = 3 * h * expert_inter
    common = embed + layers * (attn + router + shared)
    return common + layers * experts.num_experts * per_expert, common + layers * experts.experts_per_tok * per_expert


def _stat_weight(entry: os.DirEntry[str]) -> os.stat_result:
    """``stat`` of a ``*.safetensors`` entry, following links. The weights are never opened. A seam so that tests can
    declare multi-gigabyte sizes without allocating them (no behaviour of its own)."""
    return entry.stat(follow_symlinks=True)


def _weight_sizes(entries: list[os.DirEntry[str]], suffix: str) -> tuple[list[int], int, bool]:
    """``(sizes, refused, followed a link)`` of the ``suffix`` files among ``entries``, by ``stat`` only: a weight file
    is never opened, and one that does not resolve to a regular file is counted as refused."""
    sizes: list[int] = []
    refused = 0
    followed = False
    for entry in entries:
        if not entry.name.endswith(suffix):
            continue
        link = entry.is_symlink()
        try:
            st = _stat_weight(entry)  # stat only: the weights are never opened
        except OSError:
            refused += 1
            continue
        if not stat.S_ISREG(st.st_mode):
            refused += 1
            continue
        followed = followed or link
        sizes.append(st.st_size)
    return sizes, refused, followed


def _read_config(path: str, limits: IngestLimits) -> Any:
    """Read ``path`` (a resolved regular file) under the ingest byte cap and parse it with the strict loader."""
    # The path is already resolved, so a link at the leaf is a race; the one no-follow opener refuses it (hard links are
    # allowed: a model directory may be a hard-linked copy).
    try:
        with open_evidence(os.path.dirname(path), os.path.basename(path), limits, allow_hardlinks=True) as fp:
            st = os.fstat(fp.fileno())
            if not stat.S_ISREG(st.st_mode):
                raise PresetUsageError("config.json is not a regular file", code="run.model.config")
            if st.st_size > limits.max_json_bytes:
                raise IngestError("ingest.size.file", f"file of {st.st_size} bytes exceeds the limit",
                                  limit=limits.max_json_bytes)
            data = fp.read(limits.max_json_bytes + 1)
    except OSError:  # unreadable (permissions, I/O): an unusable path, like the stat failures above (exit 2)
        raise PresetUsageError("config.json cannot be read", code="run.model.config") from None
    return strict_json_loads(data, limits)


def model_facts_from_dir(path: str, *, limits: IngestLimits | None = None) -> ModelFacts:
    """Read the model facts of a model directory named by ``--model-dir`` (N.2.1a(3)).

    This is user-supplied local configuration, not raw evidence, so it deliberately does not use the no-follow
    ``ingest.paths`` evidence opener (CLAUDE.md invariant 3 governs raw source data). Real model directories are often
    Hugging Face cache layouts (``snapshots/<rev>/config.json -> ../../blobs/<hash>``), where a no-follow rule would make
    the feature unusable. Symlinks of the model directory's files are therefore followed, each resolved target must be a
    regular file, and ``followed_symlinks`` is recorded in the facts. The content is still untrusted: ``config.json`` is
    opened on its resolved target, bounded by the ingest byte cap, and parsed only by ``strict_json_loads``. Weight bytes
    are never read: the weight size is the sum of the top-level ``*.safetensors`` sizes from ``stat`` (with none, of the
    ``*.gguf`` shards, top-level or in oMLX's ``split/`` subfolder; D-828). A weight file that
    cannot be resolved to a regular file makes the weight size unknown (a partial sum would undercount silently).

    Raises :class:`PresetUsageError` for a path that is not a directory, and ``IngestError`` for hostile content.
    """
    limits = limits or IngestLimits()
    root = os.path.realpath(path)
    if not os.path.isdir(root):
        raise PresetUsageError("--model-dir is not a readable directory", code="run.model.dir")
    notes: list[str] = []
    followed = False
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        raise PresetUsageError("--model-dir is not a readable directory", code="run.model.dir") from None
    # D-828: GGUF weights count too, when there are no *.safetensors: top-level *.gguf (a llama.cpp or LM Studio
    # folder), else oMLX's GGUF layout, whose shards are links in a split/ subfolder
    label, shard_sizes, refused, link_seen = "*.safetensors", *_weight_sizes(entries, ".safetensors")
    if not shard_sizes and not refused:
        label, shard_sizes, refused, link_seen = "*.gguf", *_weight_sizes(entries, ".gguf")
    if not shard_sizes and not refused:
        split = os.path.join(root, "split")
        if os.path.isdir(split):
            try:
                split_entries = sorted(os.scandir(split), key=lambda e: e.name)
            except OSError:
                split_entries = []
            label, shard_sizes, refused, link_seen = "split/*.gguf", *_weight_sizes(split_entries, ".gguf")
    followed = followed or link_seen
    weights: Fact[int]
    if refused:
        notes.append(f"{refused} {label} entr(y/ies) not resolvable to a regular file; weight size unknown")
        weights = _UNKNOWN
    elif shard_sizes:
        weights = Fact(sum(shard_sizes), "model_dir", f"sum of {len(shard_sizes)} {label} sizes (stat)")
    else:
        notes.append("no top-level *.safetensors or *.gguf files (nor split/*.gguf); weight size unknown")
        weights = _UNKNOWN

    cfg: Any = None
    cfg_path = os.path.join(root, "config.json")
    if os.path.lexists(cfg_path):
        link = os.path.islink(cfg_path)
        resolved = os.path.realpath(cfg_path)
        try:
            is_regular = stat.S_ISREG(os.stat(resolved).st_mode)
        except OSError:
            is_regular = False
        if not is_regular:
            notes.append("config.json does not resolve to a regular file; architecture facts unknown")
        else:
            followed = followed or link
            cfg = _read_config(resolved, limits)
    else:
        notes.append("no config.json; architecture facts unknown")
    if followed:
        notes.append("followed_symlinks: true (symbolic links in the model directory were followed)")
        if weights.value is not None:
            weights = Fact(weights.value, "model_dir", weights.note + "; followed_symlinks: true")
    if cfg is not None and not isinstance(cfg, dict):
        raise PresetUsageError("config.json is not a JSON object", code="run.model.config")
    facts = ModelFacts(weights_bytes=weights, followed_symlinks=followed)
    if cfg is None:
        return replace(facts, notes=tuple(notes))

    text = cfg.get("text_config")
    if isinstance(text, dict) and _posint(cfg, "num_hidden_layers") is None:
        cfg = {**{k: v for k, v in cfg.items() if k != "text_config"}, **text}
        notes.append("architecture fields read from config.json text_config")

    def md(value: int | None, what: str = "") -> Fact[int]:
        return _UNKNOWN if value is None else Fact(value, "model_dir", what)

    oversized = {k for k, v in cfg.items() if isinstance(v, int) and not isinstance(v, bool) and v > MAX_ARCHITECTURE_INT}
    if oversized:
        notes.append(f"config.json integers above {MAX_ARCHITECTURE_INT} are not architecture facts: left unknown")
    layers = _posint(cfg, "num_hidden_layers")
    heads = _posint(cfg, "num_attention_heads")
    kv = _posint(cfg, "num_key_value_heads")
    kv_note = ""
    if kv is None and heads is not None and "num_key_value_heads" not in oversized:
        kv, kv_note = heads, "num_key_value_heads absent: equals num_attention_heads (multi-head attention)"
    hd = _posint(cfg, "head_dim")
    hd_note = ""
    hidden = _posint(cfg, "hidden_size")
    if hd is None and hidden is not None and heads is not None and hidden % heads == 0:
        hd, hd_note = hidden // heads, "hidden_size / num_attention_heads"
    if any(cfg.get(k) for k in ("kv_lora_rank", "layer_types", "full_attention_interval")):
        notes.append("latent or hybrid attention: KV per trace from layers x kv_heads x head_dim is an upper bound")

    expert_keys = [k for k in _EXPERT_COUNT_KEYS if _posint(cfg, k) is not None]
    per_tok = _posint(cfg, "num_experts_per_tok")
    moe: Fact[MoEInfo] = _UNKNOWN
    experts: MoEInfo | None = None
    if len(expert_keys) == 1 and per_tok is not None:
        experts = MoEInfo(int(cfg[expert_keys[0]]), per_tok)
        moe = Fact(experts, "model_dir", f"{expert_keys[0]}, num_experts_per_tok")
    elif expert_keys or per_tok is not None:
        notes.append("incomplete or ambiguous expert fields: active parameters not derived")
    counts = None if (expert_keys or per_tok is not None) and experts is None else _structural_params(cfg, experts)
    active: Fact[float] = _UNKNOWN
    total: Fact[float] = _UNKNOWN
    if counts is not None:
        total = Fact(counts[0] / 1e9, "model_dir", "derived from config.json architecture fields (structural count)")
        active = Fact(counts[1] / 1e9, "model_dir", "derived from config.json architecture fields (structural count)")
    else:
        notes.append("active parameters not derivable from config.json; give --active-params-b")

    return replace(
        facts,
        active_params_b=active,
        total_params_b=total,
        layers=md(layers),
        kv_heads=md(kv, kv_note) if kv is not None else _UNKNOWN,
        head_dim=md(hd, hd_note) if hd is not None else _UNKNOWN,
        moe=moe,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlanInput:
    name: str
    value: Any
    unit: str
    source: Source
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "unit": self.unit, "source": self.source, "note": self.note}


@dataclass(frozen=True, slots=True)
class ConcurrencyPlan:
    """The result of N.2.1a(3). ``jobs`` is the concurrency to use; the rest explains it.

    ``jobs_source`` is ``computed`` (``max(1, min(J_compute, J_memory, J_server))``) or ``flag`` (``--jobs``; the three
    terms are still computed so a dry run can show them). ``binding`` names the term that equals the minimum, with ties
    resolved in the order memory, compute, server; ``binding_all`` lists every tied term.
    """

    preset_name: str
    preset_version: int
    jobs: int
    jobs_source: Literal["computed", "flag"]
    j_compute: int
    j_memory: int
    j_server: int
    binding: Literal["memory", "compute", "server"]
    binding_all: tuple[str, ...]
    m_budget_bytes: int
    weights_bytes: int
    reserve_bytes: int  # R at `jobs` workers
    kv_trace_bytes: int
    inputs: tuple[PlanInput, ...]
    warnings: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """The plan for the ``corpus.json`` producer block (``preset.resolved.concurrency``) and ``--dry-run``."""
        return {
            "jobs": self.jobs,
            "jobs_source": self.jobs_source,
            "terms": {"j_compute": self.j_compute, "j_memory": self.j_memory, "j_server": self.j_server},
            "binding": self.binding,
            "binding_all": list(self.binding_all),
            "m_budget_bytes": self.m_budget_bytes,
            "weights_bytes": self.weights_bytes,
            "reserve_bytes": self.reserve_bytes,
            "kv_trace_bytes": self.kv_trace_bytes,
            "inputs": [i.to_json() for i in self.inputs],
            "warnings": list(self.warnings),
        }


def _gib_to_bytes(gib: float) -> int:
    return int(Fraction(str(gib)) * GIB)


def _pos_int_flag(value: int | None, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise PresetUsageError(f"{name} must be an integer >= 1", code="run.jobs.invalid")


def local_concurrency(
    preset: Preset,
    facts: ModelFacts,
    *,
    host: HostProfile,
    server_max_concurrency: int | None = None,
    jobs_override: int | None = None,
) -> ConcurrencyPlan:
    """``jobs = max(1, min(J_compute, J_memory, J_server))`` for a local endpoint (N.2.1a(3)). Pure.

    * ``J_compute``: the preset's ``compute_caps`` row for the active parameter count ``A``; unknown ``A`` takes the
      last (most conservative) row.
    * ``J_memory = floor((M_budget - W - R) / KV_trace)`` with ``M_budget = fraction x host memory``,
      ``R = reserve + per_worker_reserve x workers`` and ``KV_trace = 2 x layers x kv_heads x head_dim x context x
      kv_bytes``. The workers in ``R`` are the jobs actually run, so ``J_memory`` is the largest ``J`` with
      ``J x KV_trace <= M_budget - W - reserve - per_worker_reserve x J`` (a closed form; the formula is circular
      otherwise). Unknown KV geometry uses the preset's fallback (4 GiB).
    * ``J_server``: ``server_max_concurrency`` if given, else the preset default.

    ``W + R(1 worker) >= M_budget`` is a usage error (``run.model.does_not_fit``, exit 2). Unknown weights are a usage
    error too (``run.model.facts_missing``): a weight size cannot be defaulted. ``jobs_override`` (``--jobs``) replaces
    ``jobs`` but the terms are still computed; exceeding the computed minimum adds a warning.
    """
    _pos_int_flag(jobs_override, "--jobs")
    _pos_int_flag(server_max_concurrency, "--server-max-concurrency")
    inputs: list[PlanInput] = []
    warnings: list[str] = []

    if host.memory_bytes is None:
        raise PresetUsageError("host physical memory is unknown; cannot compute the memory budget", code="run.host.memory_unknown")
    fraction = Fraction(str(preset.gpu_budget_fraction))
    m_budget = int(fraction * host.memory_bytes)
    inputs.append(PlanInput("physical_memory", host.memory_bytes, "bytes", "default", f"host probe: {host.memory_how}"))
    inputs.append(PlanInput("gpu_budget_fraction", preset.gpu_budget_fraction, "ratio", "preset"))
    inputs.append(PlanInput("m_budget", m_budget, "bytes", "preset", "gpu_budget_fraction x physical_memory"))

    w_fact = facts.weights_bytes
    if w_fact.value is None:
        raise PresetUsageError(
            "model weight size is unknown: give --model-dir or --model-size-gb", code="run.model.facts_missing"
        )
    w = w_fact.value
    inputs.append(PlanInput("weights_bytes", w, "bytes", w_fact.source, w_fact.note))

    reserve0 = _gib_to_bytes(preset.reserve_gib)
    per_worker = _gib_to_bytes(preset.per_worker_reserve_gib)
    inputs.append(PlanInput("reserve_bytes", reserve0, "bytes", "preset", "fixed part of R"))
    inputs.append(PlanInput("per_worker_reserve_bytes", per_worker, "bytes", "preset"))
    if w + reserve0 + per_worker >= m_budget:
        raise PresetUsageError(
            f"the model does not fit: weights {w / GIB:.1f} GiB + reserve {(reserve0 + per_worker) / GIB:.1f} GiB "
            f">= budget {m_budget / GIB:.1f} GiB",
            code="run.model.does_not_fit",
        )

    # KV per trace
    if facts.kv_bytes_per_trace.value is not None:
        kv = facts.kv_bytes_per_trace.value
        inputs.append(PlanInput("kv_trace_bytes", kv, "bytes", facts.kv_bytes_per_trace.source, facts.kv_bytes_per_trace.note))
    elif facts.layers.known and facts.kv_heads.known and facts.head_dim.known:
        ctx_f = facts.context_tokens if facts.context_tokens.known else Fact(preset.default_context_tokens, "preset")
        kvb_f = facts.kv_bytes if facts.kv_bytes.known else Fact(preset.kv_bytes, "preset")
        assert facts.layers.value is not None and facts.kv_heads.value is not None and facts.head_dim.value is not None
        assert ctx_f.value is not None and kvb_f.value is not None
        kv = 2 * facts.layers.value * facts.kv_heads.value * facts.head_dim.value * ctx_f.value * kvb_f.value
        inputs.append(PlanInput("layers", facts.layers.value, "count", facts.layers.source, facts.layers.note))
        inputs.append(PlanInput("kv_heads", facts.kv_heads.value, "count", facts.kv_heads.source, facts.kv_heads.note))
        inputs.append(PlanInput("head_dim", facts.head_dim.value, "count", facts.head_dim.source, facts.head_dim.note))
        inputs.append(PlanInput("context_tokens", ctx_f.value, "tokens", ctx_f.source, ctx_f.note))
        inputs.append(PlanInput("kv_bytes", kvb_f.value, "bytes/element", kvb_f.source, kvb_f.note))
        inputs.append(PlanInput("kv_trace_bytes", kv, "bytes", "model_dir" if "model_dir" in (facts.layers.source, facts.kv_heads.source, facts.head_dim.source) else "flag", "2 x layers x kv_heads x head_dim x context x kv_bytes"))
    else:
        kv = _gib_to_bytes(preset.kv_trace_fallback_gib)
        inputs.append(PlanInput("kv_trace_bytes", kv, "bytes", "preset", "KV geometry unknown: preset fallback"))
        warnings.append("KV per trace unknown (layers, kv_heads or head_dim missing): using the preset fallback")
    if kv < 1:
        raise PresetUsageError("KV per trace must be >= 1 byte", code="run.model.flag")

    # J_compute
    a = facts.active_params_b.value
    row = preset.compute_caps[-1]
    if a is not None:
        row = next(r for r in preset.compute_caps if r.max_active_params_b is None or a <= r.max_active_params_b)
        inputs.append(PlanInput("active_params_b", a, "billions", facts.active_params_b.source, facts.active_params_b.note))
    else:
        inputs.append(PlanInput("active_params_b", None, "billions", "preset", "unknown: most conservative compute row"))
        warnings.append("active parameters unknown: using the most conservative compute row")
    j_compute = row.jobs
    j_server_flag = server_max_concurrency
    j_server = j_server_flag if j_server_flag is not None else preset.server_max_concurrency_default
    inputs.append(
        PlanInput("server_max_concurrency", j_server, "requests", "flag" if j_server_flag is not None else "preset")
    )

    # J_memory: largest J with J x KV <= M - W - R0 - r x J
    avail = m_budget - w - reserve0
    j_memory = max(0, avail // (kv + per_worker))
    floor_applied = j_memory < 1
    if floor_applied:
        warnings.append("memory allows no complete trace slot: jobs floored to 1 (the model barely fits)")

    terms = {"memory": max(j_memory, 1), "compute": j_compute, "server": j_server}
    minimum = min(terms.values())
    tied = tuple(name for name in ("memory", "compute", "server") if terms[name] == minimum)
    binding = tied[0]
    jobs = max(1, min(j_compute, j_memory, j_server))
    jobs_source: Literal["computed", "flag"] = "computed"
    if jobs_override is not None:
        jobs, jobs_source = jobs_override, "flag"
        if jobs_override > minimum:
            warnings.append(f"--jobs {jobs_override} exceeds the computed {minimum} ({binding} binds)")
    inputs.append(PlanInput("jobs", jobs, "workers", "flag" if jobs_override is not None else "default", "concurrent traces"))
    return ConcurrencyPlan(
        preset_name=preset.name,
        preset_version=preset.version,
        jobs=jobs,
        jobs_source=jobs_source,
        j_compute=j_compute,
        j_memory=j_memory,
        j_server=j_server,
        binding=binding,  # type: ignore[arg-type]
        binding_all=tied,
        m_budget_bytes=m_budget,
        weights_bytes=w,
        reserve_bytes=reserve0 + per_worker * jobs,
        kv_trace_bytes=kv,
        inputs=tuple(inputs),
        warnings=tuple(warnings),
    )


def corpus_json(value: Any) -> Any:
    """``value`` for corpus-layer JSON, which holds no floating-point number (H.1.4(3)): every float becomes its decimal
    string (``0.75`` -> ``"0.75"``, ``1.0`` -> ``"1.0"``); integers, strings, booleans and nulls are kept (D-823)."""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Mapping):
        return {str(k): corpus_json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [corpus_json(v) for v in value]
    return value


def preset_record(
    preset: Preset,
    plan: ConcurrencyPlan | None = None,
    *,
    start_stagger_s: float | None = None,
    request_timeout_s: float | None = None,
    host_mismatches: list[HostMismatch] | None = None,
) -> dict[str, Any]:
    """The ``corpus.json`` producer-block value ``preset{name, version, resolved{...}}`` (N.2.1a(2)).

    ``resolved`` holds every preset value, the run values after explicit flags (``start_stagger_s``: the total spread
    in seconds, ``per_worker x jobs`` unless a flag overrides it; ``request_timeout_s``), the concurrency plan and any
    host mismatch. An explicit flag overrides the preset value and is recorded with source ``flag``.
    """
    resolved: dict[str, Any] = preset.to_json()
    jobs = plan.jobs if plan is not None else None
    if start_stagger_s is not None:
        resolved["start_stagger_s"] = {"value": start_stagger_s, "source": "flag"}
    elif jobs is not None:
        resolved["start_stagger_s"] = {"value": preset.start_stagger_per_worker_s * jobs, "source": "preset"}
    resolved["request_timeout_s"] = (
        {"value": request_timeout_s, "source": "flag"}
        if request_timeout_s is not None
        else {"value": preset.request_timeout_s, "source": "preset"}
    )
    if plan is not None:
        resolved["concurrency"] = plan.to_json()
    resolved["host_mismatches"] = [m.to_json() for m in host_mismatches or []]
    return {"name": preset.name, "version": preset.version, "resolved": resolved}


# --------------------------------------------------------------------------------------------------------------
# Server preflight
# --------------------------------------------------------------------------------------------------------------

#: A model listing is small; refuse a response larger than this before parsing it.
MAX_LISTING_BYTES: Final = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """A successful preflight. ``listing_sha256`` is the digest of the exact ``GET <base>/models`` response bytes."""

    base_url: str
    url_path: str
    model_id: str
    status: int
    listing_sha256: str
    listed_models: int
    model_listed: bool = field(default=True)


def _fail(code: str, message: str, *, exit_code: int | None = None) -> ServerPreflightError:
    return ServerPreflightError(message, code=f"run.endpoint.preflight.{code}", exit_code=exit_code)


def preflight_local_server(endpoint: str | Endpoint, model_id: str, *, timeout: float = 5.0) -> PreflightResult:
    """``GET <base>/models`` on a loopback server and check ``model_id`` is listed (N.2.1a(1)).

    A non-loopback host is refused before any connection. For the name ``localhost`` the connected peer address is
    checked to be loopback before the request is sent. No redirect is followed, no credential is sent, and response
    text never enters an error message. Failures raise :class:`ServerPreflightError`: exit 4 for a refused (non-loopback or malformed) URL, exit 3 otherwise.
    """
    from agentprov_capture.endpoints import EndpointError, is_loopback_host, validate_base_url

    base = endpoint if isinstance(endpoint, str) else endpoint.base_url
    try:
        host = validate_base_url(base)
    except EndpointError as exc:
        raise _fail("url", f"base URL refused ({exc.code})", exit_code=4) from None
    if not is_loopback_host(host):
        raise _fail("not_loopback", "the preflight connects to loopback hosts only", exit_code=4)
    if not isinstance(model_id, str) or not model_id:
        raise PresetUsageError("a model id is required for the server preflight", code="run.model.id_missing")
    if not (isinstance(timeout, int | float) and 0 < timeout <= 60):
        raise ValueError("timeout must be in (0, 60] seconds")

    parts = urlsplit(base)
    https = parts.scheme == "https"
    port = parts.port or (443 if https else 80)
    path = parts.path.rstrip("/") + "/models"
    conn_cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
    conn = conn_cls(host, port, timeout=timeout)
    try:
        try:
            conn.connect()
            peer = conn.sock.getpeername()[0] if conn.sock is not None else ""
            if not ipaddress.ip_address(peer.split("%")[0]).is_loopback:
                raise _fail("not_loopback", "the connected peer is not a loopback address", exit_code=4)
            conn.request("GET", path, headers={"Accept": "application/json", "User-Agent": "agentprov-preflight"})
            resp = conn.getresponse()
            status = resp.status
            body = resp.read(MAX_LISTING_BYTES + 1)
        except ServerPreflightError:
            raise
        except (OSError, http.client.HTTPException, ValueError):
            raise _fail("unreachable", "the local server did not answer") from None
    finally:
        conn.close()
    if status != 200:
        raise _fail("http_status", f"GET {path} returned HTTP {status}")
    if len(body) > MAX_LISTING_BYTES:
        raise _fail("bad_listing", "the model listing is larger than the limit")
    digest = hashlib.sha256(body).hexdigest()
    try:
        doc = strict_json_loads(body, IngestLimits())
    except AgentProvError as exc:
        raise _fail("bad_listing", f"the model listing is not strict JSON ({getattr(exc, 'code', 'error')})") from None
    data = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(data, list) or not all(isinstance(m, dict) and isinstance(m.get("id"), str) for m in data):
        raise _fail("bad_listing", "the model listing is not an OpenAI-style {data: [{id}]} document")
    ids = {m["id"] for m in data}
    if model_id not in ids:
        raise _fail("model_not_listed", f"model id {escape_untrusted(model_id)!r} is not served ({len(ids)} model(s) listed)")
    return PreflightResult(base, path, model_id, status, digest, len(ids))
