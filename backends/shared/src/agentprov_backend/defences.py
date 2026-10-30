"""Defended pipelines for live capture (D-670..D-679; docs/reports/defence-backends/design.md §3).

A defence is the experimental treatment, not an observer effect: it is recorded as the defence's own actions (the
cell's ``defense_id``, the actor ``def0``, its ``decision`` events, its auxiliary model calls and the messages it
inserts), never as instrumentation. What the *harness* adds to record it is instrumentation (``agentdojo.defence_*@1``,
all ``behaviour_preserving``).

Building. The benchmark (or the provisioned third-party code) builds the defended pipeline; the harness then rewrites
the element tree:

* the stock ``ToolsExecutor`` becomes ``MirrorToolsExecutor`` with the **same** output formatter (spotlighting's
  ``<<...>>`` is kept);
* each occurrence of the agent's LLM element becomes ``SpannedLLM`` (role ``agent``);
* each element the registry entry declares becomes its recorder (below);
* a provisioned gate executor replaces the stock executor, wrapped by ``GateRecorder``;
* any other element is refused (``UnsupportedConfiguration``): the harness never runs an element it cannot account for.

Recorders. Each delegates to the wrapped element with the same arguments and returns its result unchanged; it only
observes:

``prompt_wrapper``    notes ``agentdojo/defence_message {at, actor, role}`` for every message the element appended;
``tool_list_filter``  brackets the element's model calls as ``role: auxiliary, actor: def0`` and notes
                      ``agentdojo/defence_tools {before, after}`` and the two messages it appends (prompt, reply);
``output_filter``     snapshots the tool messages the detector will check, observes its verdict function
                      (``observe = "detect"``) and emits one ``decision`` per checked output: ``redact`` (with the
                      ``original`` content as a blob) when the content changed, ``allow`` when the verdict was observed
                      and nothing changed (D-673), ``terminate`` when the detector aborted the run;
``executor_gate``     runs the defence's own executor unmodified; dispatches and results are observed through the
                      recording runtime (what really ran) and the tool messages; a call that never reached the runtime
                      and whose error matches a declared denial becomes ``tool.result {status: denied, decided_by}``.

Nothing here imports ``agentprov``.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentprov_backend.attacks import UnsupportedConfiguration

__all__ = [
    "ACTOR",
    "REGISTRY_FORMAT",
    "DefenceEntry",
    "GateRecorder",
    "OutputFilterRecorder",
    "PromptWrapperRecorder",
    "ToolListFilterRecorder",
    "build_defended_pipeline",
    "catalogue_entries",
    "defence_actor",
    "defence_identity",
    "defence_items",
    "entry_refusal",
    "load_registry",
    "provisioned_dir",
    "registry_path",
    "registry_sha256",
    "resolve",
]

REGISTRY_FORMAT = "agentprov-defence-registry/0.1"
#: The actor tag of the (single, v0.1) defence of a session.
ACTOR = "def0"
RECORDERS = ("prompt_wrapper", "tool_list_filter", "output_filter", "executor_gate", "llm_detector")
PROVIDERS = ("builtin", "provisioned", "port")
#: Harness ports (D-674): ``agentprov_backend.ports.<name>``.
PORTS = ("melon",)
AUX_LLM = ("none", "agent_endpoint", "defence_endpoint")
FORMATTERS = ("stock", "delimited")
#: The error texts the stock executor writes for a call it does not run (``tool_execution.py``); a gate executor that
#: copies them reports an ``invalid`` call, not a denial.
STOCK_INVALID = (re.compile(r"Empty function name provided\. Provide a valid function name\."),
                 re.compile(r"Invalid tool .* provided\.", re.DOTALL))

_ENTRY_KEYS = frozenset({"id", "title", "backends", "provider", "benchmark_name", "licence", "guarded", "elements",
                         "system_suffix", "formatter", "aux_llm", "requires_llm", "suites", "assets", "assets_pending",
                         "code", "denials", "cost", "weights", "port"})
_ELEMENT_KEYS = frozenset({"match", "where", "recorder", "observe"})
_DENIAL_KEYS = frozenset({"error_equals", "error_prefix", "error_regex"})
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


# ---------------------------------------------------------------------------------------------- the registry


@dataclass(frozen=True)
class DefenceEntry:
    id: str
    title: str
    backends: tuple[str, ...]
    provider: str
    licence: Mapping[str, str]
    guarded: Mapping[str, str]
    elements: tuple[Mapping[str, str], ...]
    formatter: str
    aux_llm: str
    suites: tuple[str, ...]
    cost: Mapping[str, float]
    benchmark_name: str | None = None
    system_suffix: str | None = None
    requires_llm: str | None = None
    assets: Mapping[str, Any] = field(default_factory=dict)
    assets_pending: str | None = None
    code: Mapping[str, Any] | None = None
    denials: tuple[Mapping[str, str], ...] = ()
    weights: tuple[Mapping[str, Any], ...] = ()
    port: str | None = None

    def to_json(self) -> dict[str, Any]:
        """The entry as recorded (``note agentdojo/defence_identity``; the config digest covers it)."""
        d: dict[str, Any] = {"id": self.id, "provider": self.provider, "licence": dict(self.licence),
                             "guarded": dict(self.guarded), "elements": [dict(e) for e in self.elements],
                             "formatter": self.formatter, "aux_llm": self.aux_llm, "suites": list(self.suites)}
        for key in ("benchmark_name", "system_suffix", "requires_llm"):
            if getattr(self, key) is not None:
                d[key] = getattr(self, key)
        if self.code is not None:
            d["code"] = _plain(self.code)
        if self.denials:
            d["denials"] = [dict(m) for m in self.denials]
        if self.weights:
            d["weights"] = [_plain(w) for w in self.weights]
        if self.port is not None:
            d["port"] = self.port
        return d


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def registry_path() -> Path:
    return Path(__file__).with_name("defences.toml")


def registry_sha256(path: Path | None = None) -> str:
    return hashlib.sha256((path or registry_path()).read_bytes()).hexdigest()


def _need(cond: bool, where: str, message: str) -> None:
    if not cond:
        raise UnsupportedConfiguration(f"defence registry {where}: {message}")


def _strs(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v for v in value)


def _entry(raw: Mapping[str, Any], n: int) -> DefenceEntry:
    where = f"entry {n}"
    _need(isinstance(raw, Mapping), where, "is not a table")
    unknown = set(raw) - _ENTRY_KEYS
    _need(not unknown, where, f"unknown members {sorted(unknown)}")
    did = raw.get("id")
    _need(isinstance(did, str) and bool(_ID.fullmatch(did)), where, "id must match ^[a-z][a-z0-9_]*$")
    where = f"entry {did!r}"
    _need(did != "none", where, "'none' is not a defence")
    _need(isinstance(raw.get("title"), str) and bool(raw["title"]), where, "title is required")
    _need(_strs(raw.get("backends")), where, "backends must be a non-empty list of ids")
    provider = raw.get("provider")
    _need(provider in PROVIDERS, where, f"provider must be one of {PROVIDERS}")
    lic = raw.get("licence")
    _need(isinstance(lic, Mapping) and isinstance(lic.get("spdx"), str) and isinstance(lic.get("basis"), str),
          where, "licence needs spdx and basis")
    guarded = raw.get("guarded", {})
    _need(isinstance(guarded, Mapping) and all(isinstance(k, str) and isinstance(v, str)
                                               and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in guarded.items()),
          where, "guarded maps qualified names to sha256")
    elements = raw.get("elements", [])
    _need(isinstance(elements, list), where, "elements must be a list")
    for el in elements:
        _need(isinstance(el, Mapping) and not set(el) - _ELEMENT_KEYS, where, "an element has unknown members")
        _need(isinstance(el.get("match"), str) and el.get("recorder") in RECORDERS, where,
              f"an element needs match and a recorder in {RECORDERS}")
        _need(el.get("where", "loop") in ("loop", "outer"), where, "element where must be loop or outer")
        _need(el.get("observe") in (None, "detect"), where, "element observe must be detect")
    formatter = raw.get("formatter", "stock")
    _need(formatter in FORMATTERS, where, f"formatter must be one of {FORMATTERS}")
    aux = raw.get("aux_llm", "none")
    _need(aux in AUX_LLM, where, f"aux_llm must be one of {AUX_LLM}")
    _need(_strs(raw.get("suites")), where, "suites must be a non-empty list")
    cost = raw.get("cost", {})
    _need(isinstance(cost, Mapping) and all(isinstance(v, int | float) for v in cost.values()), where,
          "cost values must be numbers")
    code = raw.get("code")
    if provider == "builtin":
        _need(isinstance(raw.get("benchmark_name"), str), where, "a builtin entry needs benchmark_name")
        _need(code is None, where, "a builtin entry has no code")
    else:
        _need(isinstance(code, Mapping), where, "a provisioned or port entry needs code")
        _need(isinstance(code.get("repo"), str) and re.fullmatch(r"[0-9a-f]{40}", str(code.get("commit", ""))),
              where, "code needs repo and a 40-hex commit")
        files = code.get("files")
        _need(isinstance(files, list) and files, where, "code needs files")
        for f in files:
            _need(isinstance(f, Mapping) and _is_label(str(f.get("path", "")))
                  and re.fullmatch(r"[0-9a-f]{40}", str(f.get("blob_sha1", "")))
                  and re.fullmatch(r"[0-9a-f]{64}", str(f.get("sha256", ""))), where,
                  "each code file needs a relative path, blob_sha1 and sha256")
        entry = code.get("entry")
        _need(isinstance(entry, str) and entry.count(":") == 1, where, "code.entry is 'file.py:callable'")
        _need(entry.split(":")[0] in {f["path"] for f in files}, where, "code.entry names a file not in code.files")
        _need(isinstance(code.get("kwargs", {}), Mapping), where, "code.kwargs must be a table")
    denials = raw.get("denials", [])
    _need(isinstance(denials, list), where, "denials must be a list")
    for m in denials:
        _need(isinstance(m, Mapping) and m and not set(m) - _DENIAL_KEYS
              and all(isinstance(v, str) and v for v in m.values()), where, "a denial matcher is malformed")
        if "error_regex" in m:
            try:
                re.compile(m["error_regex"])
            except re.error as exc:
                raise UnsupportedConfiguration(f"defence registry {where}: bad error_regex: {exc}") from None
    if any(el.get("recorder") == "executor_gate" for el in elements):
        _need(bool(denials), where, "an executor_gate entry needs denial matchers")
    port = raw.get("port")
    _need((provider == "port") == (port is not None), where, "a port entry, and only a port entry, names its port")
    _need(port is None or port in PORTS, where, f"port must be one of {PORTS}")
    _need(not any(el.get("recorder") == "llm_detector" for el in elements) or provider == "port", where,
          "an llm_detector element comes from a port entry")
    assets = raw.get("assets", {})
    _need(isinstance(assets, Mapping) and set(assets) <= {"python"}, where, "assets has unknown members")
    weights = raw.get("weights", [])
    _need(isinstance(weights, list), where, "weights must be an array of tables")
    for w in weights:
        _need(isinstance(w, Mapping) and set(w) <= {"hub", "repo", "revision", "licence", "hosts", "files"}
              and w.get("hub") == "huggingface" and isinstance(w.get("repo"), str)
              and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", w["repo"]) is not None
              and re.fullmatch(r"[0-9a-f]{40}", str(w.get("revision", ""))) is not None
              and isinstance(w.get("licence"), Mapping) and isinstance(w.get("files"), list) and w["files"], where,
              "a weights table needs hub = huggingface, repo, a 40-hex revision, a licence and files")
        for f in w["files"]:
            _need(isinstance(f, Mapping) and _is_label(str(f.get("path", "")))
                  and re.fullmatch(r"[0-9a-f]{64}", str(f.get("sha256", ""))) is not None
                  and isinstance(f.get("size"), int) and f["size"] >= 0, where,
                  "each weights file needs a relative path, a sha256 and a size")
    pending = raw.get("assets_pending")
    _need(pending is None or isinstance(pending, str), where, "assets_pending is a reason string")
    return DefenceEntry(
        id=did, title=raw["title"], backends=tuple(raw["backends"]), provider=provider,
        licence={"spdx": lic["spdx"], "basis": lic["basis"]}, guarded=dict(guarded),
        elements=tuple({k: str(v) for k, v in el.items()} for el in elements), formatter=formatter, aux_llm=aux,
        suites=tuple(raw["suites"]), cost={k: float(v) for k, v in cost.items()},
        benchmark_name=raw.get("benchmark_name"), system_suffix=raw.get("system_suffix"),
        requires_llm=raw.get("requires_llm"), assets=_plain(assets), assets_pending=pending,
        code=_plain(code) if code is not None else None, denials=tuple(dict(m) for m in denials),
        weights=tuple(_plain(w) for w in weights), port=port,
    )


def _is_label(label: str) -> bool:
    if not label or label.startswith("/") or "\\" in label or "\x00" in label:
        return False
    return all(p not in ("", ".", "..") for p in label.split("/"))


def load_registry(path: Path | None = None) -> dict[str, DefenceEntry]:
    """The registry's entries by id; any malformed member refuses the whole file."""
    p = path or registry_path()
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise UnsupportedConfiguration(f"the defence registry cannot be read: {exc}") from None
    _need(data.get("format") == REGISTRY_FORMAT, "file", f"format must be {REGISTRY_FORMAT!r}")
    _need(set(data) <= {"format", "defence"}, "file", "unknown top-level keys")
    raw = data.get("defence", [])
    _need(isinstance(raw, list), "file", "[[defence]] must be an array of tables")
    out: dict[str, DefenceEntry] = {}
    for n, item in enumerate(raw):
        entry = _entry(item, n)
        _need(entry.id not in out, f"entry {entry.id!r}", "duplicate id")
        out[entry.id] = entry
    return out


def resolve(defence: str, backend_id: str, *, registry: Mapping[str, DefenceEntry] | None = None) -> DefenceEntry:
    """The entry for ``defence`` on ``backend_id``; ``UnsupportedConfiguration`` when it is unknown or not for it."""
    reg = load_registry() if registry is None else registry
    entry = reg.get(defence)
    if entry is None:
        raise UnsupportedConfiguration(f"unknown defence {defence!r} (the registry lists {sorted(reg) or 'none'})")
    if backend_id not in entry.backends:
        raise UnsupportedConfiguration(f"the defence {defence!r} is not built by the {backend_id!r} backend")
    return entry


# ---------------------------------------------------------------------------------------------- availability


def provisioned_dir(entry: DefenceEntry, prefix: str | None = None) -> Path:
    """``<env>/agentprov_defences/<id>/`` (the build step copies a provisioned entry's pinned files there)."""
    return Path(prefix if prefix is not None else sys.prefix) / "agentprov_defences" / entry.id


def hf_cache_dir(prefix: str | None = None) -> Path:
    """The environment's offline Hugging Face hub cache (``<env>/agentprov_defences/hf``), which the build fills from
    the fetch cache and the worker reads with ``HF_HUB_OFFLINE=1`` (T0 passes ``HF_HUB_CACHE``, G.6.3)."""
    return Path(prefix if prefix is not None else sys.prefix) / "agentprov_defences" / "hf"


def weights_dir(weights: Mapping[str, Any], prefix: str | None = None) -> Path:
    """Where the hub cache layout puts a pinned revision's files: ``models--<org>--<name>/snapshots/<revision>``."""
    org, name = str(weights["repo"]).split("/", 1)
    return hf_cache_dir(prefix) / f"models--{org}--{name}" / "snapshots" / str(weights["revision"])


def _qualified(name: str) -> Any:
    """The object a qualified name ``package.module.Class.attr`` names (longest importable module prefix)."""
    parts = name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        try:
            obj: Any = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr)
        return obj
    raise UnsupportedConfiguration(f"cannot resolve {name!r}")


def guarded_digests(entry: DefenceEntry) -> dict[str, str]:
    """``inspect.getsource`` sha256 of each guarded name, as installed."""
    out: dict[str, str] = {}
    for name in sorted(entry.guarded):
        try:
            src = inspect.getsource(_qualified(name))
        except (OSError, TypeError, AttributeError, UnsupportedConfiguration) as exc:
            raise UnsupportedConfiguration(f"defence {entry.id!r}: guarded {name!r} cannot be read ({exc})") from None
        out[name] = hashlib.sha256(src.encode("utf-8")).hexdigest()
    return out


def entry_refusal(entry: DefenceEntry, *, prefix: str | None = None) -> str | None:
    """Why this environment cannot build ``entry`` now (``None``: it can). Checks the pending-assets reason, the
    Python modules the entry needs, the provisioned files' digests and the guarded sources."""
    if entry.assets_pending:
        return entry.assets_pending
    for module in entry.assets.get("python", ()):
        if importlib.util.find_spec(module) is None:
            return f"the Python module {module!r} is not installed (backends build --defence-assets {entry.id})"
    for weights in entry.weights:  # sizes here (cheap, per cell); T0 checks every sha256 before spawn
        root = weights_dir(weights, prefix)
        for f in weights["files"]:
            p = root / f["path"]
            if not p.is_file() or p.stat().st_size != f["size"]:
                return (f"the pinned weights file {weights['repo']}/{f['path']} is not provisioned "
                        f"(backends build --defence-assets {entry.id})")
    if entry.provider in ("provisioned", "port"):
        assert entry.code is not None
        root = provisioned_dir(entry, prefix)
        for f in entry.code["files"]:
            p = root / f["path"]
            if not p.is_file() or p.is_symlink():
                return f"provisioned file {f['path']!r} is missing (backends build --defence-assets {entry.id})"
            if hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                return f"provisioned file {f['path']!r} differs from its pinned sha256"
    try:
        found = guarded_digests(entry)
    except UnsupportedConfiguration as exc:
        return str(exc)
    for name, digest in entry.guarded.items():
        if found.get(name) != digest:
            return f"guarded source {name} differs from the registry's digest (sha256 {found.get(name)})"
    return None


def catalogue_entries(backend_id: str, *, registry: Mapping[str, DefenceEntry] | None = None,
                      refused: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """The catalogue's ``defences`` member (D-652 extended, design §3.8): what this environment can build. ``refused``
    names backend-level refusals (they win over the entry's own state). Names, licences and needs only."""
    reg = load_registry() if registry is None else registry
    extra = dict(refused or {})
    out: list[dict[str, Any]] = []
    for did in sorted(reg):
        entry = reg[did]
        if backend_id not in entry.backends:
            continue
        reason = extra.get(did) or entry_refusal(entry)
        needs = [f"--defence-assets {did}"] if (entry.assets or entry.weights or entry.provider != "builtin") else []
        if entry.aux_llm == "defence_endpoint":
            needs.append("--defence-endpoint")
        out.append({"name": did, "title": entry.title, "provider": entry.provider, "licence": entry.licence["spdx"],
                    "refused": reason, "needs": needs, "suites": list(entry.suites), "aux_llm": entry.aux_llm,
                    "cost": dict(entry.cost)})
    return out


# ---------------------------------------------------------------------------------------------- recording


def defence_actor(entry: DefenceEntry, model: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """``session.start.actors.def0``."""
    actor: dict[str, Any] = {"kind": "defense", "name": entry.id}
    if model is not None:
        actor["model"] = dict(model)
    return actor


def defence_identity(entry: DefenceEntry, digests: Mapping[str, str]) -> dict[str, Any]:
    """``note agentdojo/defence_identity``: the registry entry, its digest and the guarded sources as installed."""
    return {"registry_sha256": registry_sha256(), "entry": entry.to_json(), "guarded_observed": dict(digests)}


def _item(id_: str, params: Any = None, detail: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"id": id_, "kind": "behaviour_preserving", "recorded": "full"}
    if params is not None:
        d["params"] = params
    if detail is not None:
        d["detail"] = detail
    return d


def defence_items(entry: DefenceEntry, substitutions: Sequence[str]) -> list[dict[str, Any]]:
    """The D.10.7 items the harness adds to record ``entry`` (design §3.3)."""
    items = [
        _item("agentdojo.defence_pipeline_rewrite@1", {"defence": entry.id, "substitutions": list(substitutions)},
              "the defended pipeline as the benchmark or the pinned code builds it, with the recording elements "
              "substituted; checked against the unrewritten pipeline's structure"),
    ]
    recorders = sorted({e["recorder"] for e in entry.elements})
    if recorders:
        items.append(_item("agentdojo.defence_recorder@1", {"recorders": recorders},
                           "delegating wrappers that observe the defence's verdicts; inputs and outputs unchanged"))
    if entry.aux_llm != "none":
        items.append(_item("agentdojo.defence_aux_span@1", {"actor": ACTOR},
                           "the defence's model calls bracketed as auxiliary calls of its actor; no request change"))
    for weights in entry.weights:
        items.append(_item("agentdojo.defence_weights_offline@1",
                           {"repo": weights["repo"], "revision": weights["revision"],
                            "files": [{"path": f["path"], "sha256": f["sha256"]} for f in weights["files"]],
                            "device": _device()},
                           "pinned weights provisioned at build and loaded offline (HF_HUB_OFFLINE=1)"))
    if entry.port is not None:
        from agentprov_backend.ports import melon

        item = _item("agentdojo.defence_port@1", melon.port_item_params(entry.id),
                     "the pinned code adapted to the recorders (D-674); its decision logic is unchanged")
        item["kind"] = "harness_policy"
        items.append(item)
    if entry.provider in ("provisioned", "port"):
        assert entry.code is not None
        items.append(_item("agentdojo.defence_code_provisioned@1",
                           {"repo": entry.code["repo"], "commit": entry.code["commit"],
                            "files": [{"path": f["path"], "sha256": f["sha256"]} for f in entry.code["files"]]}))
    return items


def _device() -> str:
    """The device the stock detector picks (``cuda`` if available, else ``cpu``; it never uses MPS), recorded."""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "unavailable"


def _is_stock_invalid(error: str) -> bool:
    return any(p.fullmatch(error) for p in STOCK_INVALID)


def _denial_matcher(entry: DefenceEntry, error: str | None) -> int | None:
    """Index of the first matcher the not-executed call's error satisfies (``hooks/defence_denial.py`` semantics)."""
    if not isinstance(error, str):
        return None
    for i, m in enumerate(entry.denials):
        if "error_equals" in m and error != m["error_equals"]:
            continue
        if "error_prefix" in m and not error.startswith(m["error_prefix"]):
            continue
        if "error_regex" in m and not re.fullmatch(m["error_regex"], error, re.DOTALL):
            continue
        return i
    return None


def _text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, Mapping) and block.get("type") == "text":
            parts.append(str(block.get("content") or ""))
    return "\n".join(parts)


def _delegate_query(element: Any, query: str, runtime: Any, env: Any, messages: Sequence[Any],
                    extra_args: dict) -> tuple[str, Any, Any, Sequence[Any], dict]:
    return element.query(query, runtime, env, messages, extra_args)


def _base() -> type:
    from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement

    return BasePipelineElement


class _Recorder:
    """Shared plumbing: the wrapped element, the session and the defence actor; ``name`` is the inner's."""

    def __init__(self, inner: Any, session: Any, actor: str = ACTOR) -> None:
        self.inner = inner
        self.session = session
        self.actor = actor
        self.name = getattr(inner, "name", None)

    def _message_note(self, at: int, role: Any, **extra: Any) -> None:
        self.session.note("agentdojo", "defence_message", {"at": at, "actor": self.actor, "role": role, **extra})


def _make(cls: type) -> type:
    """``cls`` as a ``BasePipelineElement`` subclass (built lazily: ``agentdojo`` is imported only inside a worker)."""
    return type(cls.__name__, (cls, _base()), {"__module__": __name__, "__doc__": cls.__doc__})


class _PromptWrapper(_Recorder):
    """``prompt_wrapper``: notes each message the element appends (``repeat_user_prompt``'s ``InitQuery``)."""

    def query(self, query: str, runtime: Any, env: Any = None, messages: Sequence[Any] = (),
              extra_args: dict | None = None) -> tuple[str, Any, Any, Sequence[Any], dict]:
        extra_args = {} if extra_args is None else extra_args
        n = len(messages)
        out = _delegate_query(self.inner, query, runtime, env, messages, extra_args)
        for i in range(n, len(out[3])):
            self._message_note(i, out[3][i].get("role"))
        self.session.observe_messages(out[3])
        return out


class _ToolListFilter(_Recorder):
    """``tool_list_filter``: the element's model calls are auxiliary calls of the defence actor; notes the tool list
    before and after and the messages it appends (the stock filter appends its prompt, role user, and the reply)."""

    def query(self, query: str, runtime: Any, env: Any = None, messages: Sequence[Any] = (),
              extra_args: dict | None = None) -> tuple[str, Any, Any, Sequence[Any], dict]:
        extra_args = {} if extra_args is None else extra_args
        n = len(messages)
        before = sorted(runtime.functions)
        # the request is built from the messages plus the filter prompt (n + 1), which lands at position n
        with self.session.span("auxiliary", self.actor, [*messages, None]) as span:
            out = _delegate_query(self.inner, query, runtime, env, messages, extra_args)
        calls = list(span.calls)
        after = sorted(out[1].functions)
        self.session.note("agentdojo", "defence_tools", {"actor": self.actor, "before": before, "after": after,
                                                         "calls": calls})
        for i in range(n, len(out[3])):
            role = out[3][i].get("role")
            extra = {"call": calls[-1]} if role == "assistant" and calls else {}
            self._message_note(i, role, **extra)
        self.session.observe_messages(out[3])
        return out


class _OutputFilter(_Recorder):
    """``output_filter`` for ``PromptInjectionDetector``-shaped detectors (see the module docstring).

    The checked messages are the trailing run of tool messages, newest first, exactly as the stock
    ``PromptInjectionDetector.query`` selects them (its source digest is guarded by the registry entry)."""

    def __init__(self, inner: Any, session: Any, actor: str = ACTOR, observe: str | None = None) -> None:
        super().__init__(inner, session, actor)
        self._observed: list[Any] = []
        if observe == "detect":
            original = inner.detect

            def detect(tool_output: str) -> Any:
                result = original(tool_output)
                self._observed.append(result)
                return result

            inner.detect = detect  # an instance attribute: the class method is unchanged
        self.observing = observe == "detect"

    def query(self, query: str, runtime: Any, env: Any = None, messages: Sequence[Any] = (),
              extra_args: dict | None = None) -> tuple[str, Any, Any, Sequence[Any], dict]:
        from agentdojo.agent_pipeline.errors import AbortAgentError

        extra_args = {} if extra_args is None else extra_args
        checked: list[int] = []
        if messages and messages[-1]["role"] == "tool":
            i = len(messages) - 1
            while i >= 0 and messages[i]["role"] == "tool":
                checked.append(i)
                i -= 1
        before = {i: copy.deepcopy(messages[i].get("content")) for i in checked}
        self._observed = []
        try:
            out = _delegate_query(self.inner, query, runtime, env, messages, extra_args)
        except AbortAgentError as exc:
            k = len(self._observed) - 1
            if 0 <= k < len(checked):
                self._decide(messages[checked[k]], "terminate", self._reason(self._observed[k]), None)
            else:
                self.session.note("agentdojo", "defence_unlinked_verdict", {"actor": self.actor, "verdict": "terminate"})
            exc_messages = getattr(exc, "messages", None)
            if exc_messages is not None:
                self.session.observe_messages(exc_messages)
            raise
        if self.observing and len(self._observed) != len(checked):
            self.session.note("agentdojo", "defence_observation_mismatch",
                              {"actor": self.actor, "checked": len(checked), "observed": len(self._observed)})
        for k, i in enumerate(checked):
            message = messages[i]
            changed = message.get("content") != before[i]
            verdict = self._observed[k] if self.observing and k < len(self._observed) else None
            if changed:
                self._decide(message, "redact", self._reason(verdict), before[i])
            elif verdict is not None:
                self._decide(message, "allow", self._reason(verdict), None)
        self.session.observe_messages(out[3])
        return out

    @staticmethod
    def _reason(verdict: Any) -> str | None:
        if verdict is None:
            return None
        if isinstance(verdict, tuple) and len(verdict) == 2:
            return f"is_injection={bool(verdict[0])} score={float(verdict[1])!r}"
        return f"is_injection={bool(verdict)}"

    def _decide(self, message: Any, verdict: str, reason: str | None, original: Any) -> None:
        occ = self.session.occ_of(message)
        if occ is None:
            self.session.note("agentdojo", "defence_unlinked_verdict", {"actor": self.actor, "verdict": verdict})
            return
        self.session.decision(self.actor, {"occ": occ}, verdict, reason=reason,
                              original=None if original is None else self.session.put_json_blob(original))


class _Gate(_Recorder):
    """``executor_gate``: see the module docstring. ``entry`` gives the denial matchers."""

    def __init__(self, inner: Any, session: Any, entry: DefenceEntry, actor: str = ACTOR) -> None:
        super().__init__(inner, session, actor)
        self.entry = entry
        self.output_formatter = getattr(inner, "output_formatter", None)

    def query(self, query: str, runtime: Any, env: Any = None, messages: Sequence[Any] = (),
              extra_args: dict | None = None) -> tuple[str, Any, Any, Sequence[Any], dict]:
        extra_args = {} if extra_args is None else extra_args
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1].get("tool_calls"):
            return _delegate_query(self.inner, query, runtime, env, messages, extra_args)
        from agentprov_backend._jsonval import to_jsonable

        self.session.observe_messages(messages)
        calls = list(messages[-1]["tool_calls"])
        at_message = len(messages) - 1
        requested = [copy.deepcopy(to_jsonable(tc.args)) for tc in calls]
        gate = _GateContext(self.session, calls, requested, at_message)
        self.session.gate = gate
        try:
            out = _delegate_query(self.inner, query, runtime, env, messages, extra_args)
        finally:
            self.session.gate = None
        results = list(out[3][len(messages):])
        post_hoc: list[str] = []
        for j, tc in enumerate(calls):
            message = _result_for(results, tc, j)
            if message is None:
                self.session.note("agentdojo", "defence_missing_result", {"actor": self.actor, "call": j})
                continue
            error = message.get("error")
            rendered = _text(message.get("content"))
            occ = gate.occ.get(j)
            if occ is not None:  # it reached the runtime
                record = gate.records.get(j) or {}
                status = record.get("status", "ok" if error is None else "error")
                self.session.tool_result(occ, status, record.get("args_effective"), gate.returned.get(j), rendered,
                                         error or rendered, error, exception=record.get("exception"),
                                         has_returned=status == "ok" and j in gate.returned)
                self.session.bind_message(message, occ)
                continue
            occ = self.session.next_occ()
            self.session.tool_dispatch(occ, tc.id, tc.function, requested[j], None, (at_message, j))
            post_hoc.append(occ)
            matcher = _denial_matcher(self.entry, error)
            if matcher is not None:
                self.session.tool_result(occ, "denied", None, None, rendered, error or rendered, error,
                                         decided_by=self.actor, has_returned=False)
                self.session.note("agentdojo", "defence_denial_match", {"occ": occ, "actor": self.actor,
                                                                         "matcher": matcher})
            elif isinstance(error, str) and _is_stock_invalid(error):
                self.session.tool_result(occ, "invalid", None, None, rendered, error, error, has_returned=False)
            else:
                # not executed and not explained: no result is invented (the mapper sees an unexecuted dispatch)
                self.session.note("agentdojo", "defence_unclassified_non_execution",
                                  {"occ": occ, "actor": self.actor})
            self.session.bind_message(message, occ)
        if post_hoc:
            self.session.note("agentdojo", "defence_gate_post_hoc", {"actor": self.actor, "occs": post_hoc})
        self.session.observe_messages(out[3])
        return out


def _result_for(results: Sequence[Any], tc: Any, j: int) -> Any:
    for r in results:
        if r.get("tool_call") is tc:
            return r
    if tc.id is not None:
        same = [r for r in results if r.get("tool_call_id") == tc.id]
        if len(same) == 1:
            return same[0]
    return results[j] if j < len(results) else None


class _GateContext:
    """What a gate executor's runtime calls are matched against: the batch's calls in order. The recording runtime
    calls :meth:`begin` and :meth:`end` around each ``run_function`` it sees while a gate is active."""

    def __init__(self, session: Any, calls: Sequence[Any], requested: Sequence[Any], at_message: int) -> None:
        self.session = session
        self.calls = calls
        self.requested = requested
        self.at_message = at_message
        self.occ: dict[int, str] = {}
        self.records: dict[int, dict[str, Any]] = {}
        self.returned: dict[int, Any] = {}
        self._current: int | None = None

    def begin(self, function: str) -> str | None:
        j = next((k for k, tc in enumerate(self.calls) if k not in self.occ and tc.function == function), None)
        if j is None:
            self.session.note("agentdojo", "defence_unmatched_runtime_call", {"function": function})
            return None
        occ = self.session.next_occ()
        self.occ[j] = occ
        self._current = j
        tc = self.calls[j]
        self.session.tool_dispatch(occ, tc.id, tc.function, self.requested[j], None, (self.at_message, j))
        return occ

    def end(self, record: Mapping[str, Any] | None, result: Any) -> None:
        j, self._current = self._current, None
        if j is None:
            return
        if record is not None:
            self.records[j] = dict(record)
        if record is None or record.get("status") == "ok":
            self.returned[j] = result


class _LlmDetector(_Recorder):
    """``llm_detector`` for a ported detector that is also the loop's model step (MELON): it queries the agent's LLM
    and, when it judges the tool outputs injected, redacts them and replaces the agent's reply with its own stop
    message. Emits, per detector query: a ``redact`` decision (with ``original``) for each tool message whose content
    changed, an ``allow`` decision on the checked (last) tool message when the detector's own log says it passed
    (D-673), a ``modify`` decision on the agent call whose reply the detector replaced (``original``: the reply) with
    the replacement noted as a defence message, and the detector's own log as ``note agentdojo/defence_log``."""

    def __init__(self, inner: Any, session: Any, proxy: Any, actor: str = ACTOR) -> None:
        super().__init__(inner, session, actor)
        self.proxy = proxy

    def query(self, query: str, runtime: Any, env: Any = None, messages: Sequence[Any] = (),
              extra_args: dict | None = None) -> tuple[str, Any, Any, Sequence[Any], dict]:
        extra_args = {} if extra_args is None else extra_args
        checked: list[int] = []
        if messages and messages[-1]["role"] == "tool":
            i = len(messages) - 1
            while i >= 0 and messages[i]["role"] == "tool":
                checked.append(i)
                i -= 1
        before = {i: copy.deepcopy(messages[i].get("content")) for i in checked}
        self.proxy.reset()
        out = _delegate_query(self.inner, query, runtime, env, messages, extra_args)
        log = {k: out[4].get(k) for k in ("defense_log", "melon_log") if isinstance(out[4], Mapping) and k in out[4]}
        if log:
            self.session.note("agentdojo", "defence_log", {"actor": self.actor, **log})
        verdict = log.get("defense_log") if isinstance(log.get("defense_log"), Mapping) else None
        reason = None
        if verdict is not None:
            reason = (f"route={verdict.get('route')} melon_score={verdict.get('melon_score')!r} "
                      f"threshold={verdict.get('threshold')!r}")
        redacted = False
        for i in checked:
            if messages[i].get("content") != before[i]:
                redacted = True
                self._decide(messages[i], "redact", reason, before[i])
        if not redacted and checked and verdict is not None and verdict.get("is_injection") is False:
            self._decide(messages[checked[0]], "allow", reason, None)
        reply = self.proxy.agent_outputs[0] if self.proxy.agent_outputs else None
        if reply is not None and out[3] and out[3][-1] is not reply:
            calls = getattr(self.proxy.agent, "last_calls", []) if len(self.proxy.agent_outputs) == 1 else []
            if calls:
                self.session.decision(self.actor, {"call": calls[-1]}, "modify", reason=reason,
                                      original=self.session.put_json_blob(reply))
            else:
                self.session.note("agentdojo", "defence_unlinked_verdict", {"actor": self.actor, "verdict": "modify"})
            self._message_note(len(out[3]) - 1, out[3][-1].get("role"), replaces=calls[-1] if calls else None)
        self.session.observe_messages(out[3])
        return out

    def _decide(self, message: Any, verdict: str, reason: str | None, original: Any) -> None:
        occ = self.session.occ_of(message)
        if occ is None:
            self.session.note("agentdojo", "defence_unlinked_verdict", {"actor": self.actor, "verdict": verdict})
            return
        self.session.decision(self.actor, {"occ": occ}, verdict, reason=reason,
                              original=None if original is None else self.session.put_json_blob(original))


PromptWrapperRecorder: type = _PromptWrapper
ToolListFilterRecorder: type = _ToolListFilter
OutputFilterRecorder: type = _OutputFilter
GateRecorder: type = _Gate
_CLASSES: dict[str, type] = {}


def _cls(name: str) -> type:
    """The ``BasePipelineElement`` subclass of a recorder (created once per process)."""
    if name not in _CLASSES:
        _CLASSES[name] = _make({"prompt_wrapper": _PromptWrapper, "tool_list_filter": _ToolListFilter,
                                "output_filter": _OutputFilter, "executor_gate": _Gate,
                                "llm_detector": _LlmDetector}[name])
    return _CLASSES[name]


# ---------------------------------------------------------------------------------------------- building


def _qualname(obj: Any) -> str:
    t = type(obj)
    return f"{t.__module__}.{t.__qualname__}"


def load_provisioned(entry: DefenceEntry, *, prefix: str | None = None) -> Any:
    """The provisioned entry point (``code.entry``) loaded from the verified files under :func:`provisioned_dir`, as a
    private module (never on ``sys.path``; nothing is written)."""
    assert entry.code is not None
    reason = entry_refusal(entry, prefix=prefix)
    if reason is not None:
        raise UnsupportedConfiguration(f"defence {entry.id!r}: {reason}")
    file_label, attr = entry.code["entry"].split(":")
    path = provisioned_dir(entry, prefix) / file_label
    name = f"agentprov_defence_{entry.id}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise UnsupportedConfiguration(f"defence {entry.id!r}: cannot load {file_label!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if entry.port == "melon":
        from agentprov_backend.ports import melon

        melon.apply_to_module(module)
    target = getattr(module, attr, None)
    if not callable(target):
        raise UnsupportedConfiguration(f"defence {entry.id!r}: {entry.code['entry']!r} is not callable")
    return target


@dataclass
class DefendedPipeline:
    pipeline: Any
    substitutions: list[str]
    digests: dict[str, str]


def build_defended_pipeline(entry: DefenceEntry, config: Any, session: Any, *, name: str | None = None,
                            prefix: str | None = None, factory: Any = None,
                            defence_client: Any = None) -> DefendedPipeline:
    """The instrumented defended pipeline for ``entry`` (see the module docstring).

    ``config`` is an ``agentdojo`` ``PipelineConfig`` whose ``llm`` is the recorded element and whose ``defense`` is
    ``None``; the builtin defence name is set here. ``factory`` replaces the provisioned entry point (tests)."""
    from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor

    from agentprov_backend._llm import SpannedLLM
    from agentprov_backend.executor_mirror import MirrorToolsExecutor
    from agentprov_backend.pass_recorder import PassRecorder

    if getattr(config, "tool_output_format", None) not in (None, "yaml"):
        raise UnsupportedConfiguration(
            f"only the YAML tool-output format is supported (got {config.tool_output_format!r})")
    llm = config.llm
    if entry.requires_llm is not None and not isinstance(llm, _qualified(entry.requires_llm)):
        raise UnsupportedConfiguration(f"the defence {entry.id!r} needs a {entry.requires_llm.rsplit('.', 1)[-1]} "
                                       "LLM element")
    if entry.weights:
        import os

        cache = str(hf_cache_dir(prefix))
        if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1" \
                or os.environ.get("HF_HUB_CACHE") != cache:
            raise UnsupportedConfiguration(f"the defence {entry.id!r} loads its weights only offline from {cache} "
                                           "(HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1, HF_HUB_CACHE; set by T0)")
        reason = entry_refusal(entry, prefix=prefix)
        if reason is not None:
            raise UnsupportedConfiguration(f"defence {entry.id!r}: {reason}")
    digests: dict[str, str] = {}
    if entry.provider == "builtin" or entry.guarded:
        digests = guarded_digests(entry)
        for qn, expected in entry.guarded.items():
            if digests.get(qn) != expected:
                raise UnsupportedConfiguration(f"defence {entry.id!r}: guarded source {qn} differs from the registry")
    model_name = getattr(llm, "model", None)
    if getattr(llm, "name", None) is None and isinstance(model_name, str):
        # stock from_config names defended pipelines "<llm.name>-<defence>" and gives tool_filter llm.name as the
        # model id; the stock OpenAILLM leaves name None (the benchmark script passes the model string instead)
        llm.name = model_name
    defended = config.model_copy(update={"defense": entry.benchmark_name if entry.provider == "builtin" else None})
    built = AgentPipeline.from_config(defended)
    gate_executor: Any = None
    detector_target: Any = None
    if entry.provider == "provisioned":
        target = factory if factory is not None else load_provisioned(entry, prefix=prefix)
        assert entry.code is not None
        gate_executor = target(**dict(entry.code.get("kwargs", {})))
    elif entry.provider == "port":
        detector_target = factory if factory is not None else load_provisioned(entry, prefix=prefix)
    detector_declared = next((e for e in entry.elements if e["recorder"] == "llm_detector"), None)
    by_match = {e["match"]: e for e in entry.elements}
    substitutions: list[str] = []

    def rewrite(element: Any, where: str) -> Any:
        if element is llm and detector_declared is not None and where == detector_declared.get("where", "loop"):
            from agentprov_backend.ports import melon

            assert entry.code is not None
            detector, proxy = melon.build_detector(detector_target, entry.code.get("kwargs", {}), llm, session, ACTOR,
                                                   defence_client)
            substitutions.append(f"{where}:llm_detector({_qualname(detector)})")
            return _cls("llm_detector")(detector, session, proxy)
        if element is llm:
            substitutions.append(f"{where}:SpannedLLM")
            return SpannedLLM(llm, session)
        qn = _qualname(element)
        declared = by_match.get(qn)
        if type(element) is ToolsExecutor and gate_executor is not None and declared is not None \
                and declared["recorder"] == "executor_gate" and declared.get("where", "loop") == where:
            substitutions.append(f"{where}:executor_gate({_qualname(gate_executor)})")
            return _cls("executor_gate")(gate_executor, session, entry)
        if type(element) is ToolsExecutor:
            substitutions.append(f"{where}:MirrorToolsExecutor")
            return MirrorToolsExecutor(element.output_formatter, hooks=session)
        if declared is not None and declared.get("where", "loop") == where and declared["recorder"] != "executor_gate":
            substitutions.append(f"{where}:{declared['recorder']}({qn})")
            if declared["recorder"] == "output_filter":
                return _cls("output_filter")(element, session, ACTOR, declared.get("observe"))
            return _cls(declared["recorder"])(element, session)
        if where == "outer" and qn in ("agentdojo.agent_pipeline.basic_elements.SystemMessage",
                                       "agentdojo.agent_pipeline.basic_elements.InitQuery"):
            return element
        if where == "outer" and isinstance(element, ToolsExecutionLoop) and type(element) is ToolsExecutionLoop:
            element.elements = [rewrite(e, "loop") for e in element.elements]
            return element
        raise UnsupportedConfiguration(f"the defended pipeline holds an undeclared element {qn} ({where})")

    built.elements = [rewrite(e, "outer") for e in built.elements]
    declared_seen = {s.split("(", 1)[1].rstrip(")") for s in substitutions if "(" in s and "executor_gate" not in s
                     and "llm_detector" not in s}
    missing = [e["match"] for e in entry.elements if e["recorder"] not in ("executor_gate", "llm_detector")
               and e["match"] not in declared_seen]
    if detector_declared is not None and not any(":llm_detector(" in s for s in substitutions):
        raise UnsupportedConfiguration(f"the defence {entry.id!r} found no loop LLM to replace with its detector")
    if missing:
        raise UnsupportedConfiguration(f"the defence {entry.id!r} declares elements the pipeline lacks: {missing}")
    if gate_executor is not None and not any(s.startswith("loop:executor_gate") for s in substitutions):
        raise UnsupportedConfiguration(f"the defence {entry.id!r} found no executor to gate")
    built.name = f"{name or llm.name}-{entry.id}"
    return DefendedPipeline(PassRecorder(built, session), substitutions, digests)
