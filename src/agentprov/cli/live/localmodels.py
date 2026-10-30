"""Local model servers: discovery, fingerprint and the observed identity of the model that will run (D-691..D-693).

One implementation serves ``agentprov models``, ``run`` (the N.2.1a(1) preflight, the dry-run model block, the plan's
``local_model`` and the per-cell re-observation) and, through the CLI, the GUI's model picker.

**Network.** Only loopback hosts are contacted, and the connected peer must be a loopback address (the
``presets.preflight_local_server`` method). ``http.client`` is used, never ``urllib``, which honours ``HTTP_PROXY`` and
could carry a loopback request to a remote proxy. No redirect is followed, and every request has a 5 s timeout and a
bounded body (8 MiB). The one credential ever sent is the endpoint's own optional key (``api_key_env`` on a local
entry, D-827), as a bearer header, to a loopback server only (never to a LAN address); it is never recorded. The only POST is Ollama's ``/api/show``, which reads metadata and does
not load the model. Nothing here runs inference.

**Untrusted data.** Every response is parsed by ``agentprov.ingest`` (strict JSON under ``IngestLimits``), and only
checked members are kept: ids must be labels, other strings are bounded and printable, numbers are finite and
non-negative. Ids are never used as paths. Each response's sha256 is kept, and the identity record cites it.

**Files.** The model's files are found without trusting the server: the HF cache (``models--org--name``), LM Studio's
models folder (``downloadsFolder`` in its settings) or a directory the operator names (``--model-dir``). The walk is
bounded (depth 3, 512 entries, regular files, symlinks must stay inside the root). File bytes are hashed, never parsed.
Weight digests come from HF blob names (64-hex LFS names: a cache claim, recorded as such) or are computed, with a
digest cache in ``$AGENTPROV_HOME/cache/model-digests.jsonl`` keyed by device, inode, size and mtime. **No absolute
path is recorded**: directories are labelled relative to their models root.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import stat
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from agentprov.errors import AgentProvError, IngestError

__all__ = [
    "IDENTITY_FORMAT",
    "LISTING_FORMAT",
    "DigestCache",
    "LocalModelError",
    "LoopbackClient",
    "ServerListing",
    "detect_server",
    "identity_sha256",
    "list_server",
    "local_endpoint_names",
    "local_endpoints",
    "model_identity",
    "resolve_local",
]

LISTING_FORMAT: Final = "agentprov-local-models/0.1"
#: 0.2 (D-736): load and serving state moved out of ``server_identity`` into ``observed_state``; ``server.version_source``.
IDENTITY_FORMAT: Final = "agentprov-local-model/0.2"
#: D-736: per server kind, the native facts that describe load or serving state rather than the model. They change when
#: a model is loaded, a slot count is set or a response is re-read, so they are recorded as ``observed_state`` and kept
#: out of every identity digest. (Ollama's ``context_length`` is the model's own and stays; LM Studio's is the loaded
#: instance's setting.) ``show_sha256`` is a raw-response digest, already cited in ``listing.responses``.
STATE_FIELDS: Final[Mapping[str, frozenset[str]]] = {
    "lmstudio": frozenset({"loaded_instances", "parallel", "context_length"}),
    "llamacpp": frozenset({"total_slots"}),
}
DROPPED_FIELDS: Final = frozenset({"show_sha256", "build_info"})  # cited response; llama.cpp's version (server.version)
#: Where each kind's server version comes from (``None``: the server does not expose one; nothing is guessed).
VERSION_SOURCES: Final[Mapping[str, str | None]] = {
    "ollama": "GET /api/version", "llamacpp": "GET /props build_info", "vllm": "GET /version", "lmstudio": None,
}
MAX_BODY_BYTES: Final = 8 * 1024 * 1024
TIMEOUT_S: Final = 5.0
MAX_MODELS: Final = 2000
MAX_WALK_ENTRIES: Final = 512
MAX_WALK_DEPTH: Final = 3
#: An id the server serves: a label (no control characters, no leading ``.``/``/``), never a path.
_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+/ -]{0,199}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"(sha256:)?[0-9a-f]{64}")
WEIGHT_SUFFIXES: Final = (".safetensors", ".gguf", ".npz", ".bin", ".pt", ".pth")
#: The registry server kinds that have a fingerprint of their own; ``omlx`` and ``mlx_lm`` serve only the OpenAI
#: routes, so they are recorded as ``openai_generic`` (the kind is then not confirmed, only not contradicted).
SIGNED_KINDS: Final = ("ollama", "lmstudio", "llamacpp", "vllm")
GENERIC: Final = "openai_generic"


class LocalModelError(AgentProvError):
    """A local-server condition: exit 3 (unreachable, bad listing, model not served) or 4 (refused: not loopback, the
    wrong server kind, a remote model). Messages never quote response text unescaped."""

    code = "run.local"
    exit_code = 3


def _refused(code: str, message: str) -> LocalModelError:
    return LocalModelError(message, code=f"run.local.{code}", exit_code=4)


def _unavailable(code: str, message: str) -> LocalModelError:
    return LocalModelError(message, code=f"run.local.{code}", exit_code=3)


# ----------------------------------------------------------------------------------------------------------------
# Checked values
# ----------------------------------------------------------------------------------------------------------------


def _label(value: Any) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) and ".." not in value.split("/") else None


def _text(value: Any, limit: int = 160) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit or not value.isprintable():
        return None
    return value


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**63 else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if value == value and abs(value) < 1e18 and value >= 0 else None  # NaN never passes strict JSON


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _digest(value: Any) -> str | None:
    if isinstance(value, str) and _DIGEST.fullmatch(value):
        return "sha256:" + value.removeprefix("sha256:")
    return None


def _dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _drop_none(d: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def identity_sha256(record: Mapping[str, Any]) -> str:
    """The JCS digest of the parts of an identity record that name the model (server identity and files)."""
    from agentprov.io.canonical import jcs_bytes, sha256_hex

    core = {k: record.get(k) for k in ("endpoint", "server", "model_id", "server_identity", "files")}
    server = dict(_dict(core["server"]))
    server.pop("fingerprint_sha256", None)  # which probe answered is evidence, not identity
    core["server"] = server
    return "sha256:" + sha256_hex(jcs_bytes(core))


# ----------------------------------------------------------------------------------------------------------------
# The loopback client
# ----------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    path: str
    status: int
    body: bytes
    sha256: str

    def json(self) -> Any:
        """The body as strict JSON (``agentprov.ingest``), or ``None`` when it is not."""
        from agentprov.ingest.limits import IngestLimits
        from agentprov.ingest.loaders import strict_json_loads

        if self.status != 200:
            return None
        try:
            return strict_json_loads(self.body, IngestLimits())
        except IngestError:
            return None

    def cite(self) -> dict[str, Any]:
        return {"path": self.path, "status": self.status, "sha256": self.sha256}


def loopback_target(base_url: str, *, allow_lan: bool = False) -> tuple[str, int, str]:
    """``(host, port, base_path)`` of a local base URL; refuses anything but http(s) on a loopback host (exit 4), or,
    with ``allow_lan`` (``--allow-lan-endpoint``, D-698), on a literal private address."""
    from agentprov_capture.endpoints import EndpointError, is_loopback_host, is_private_lan_host, validate_base_url

    try:
        host = validate_base_url(base_url, allow_lan=allow_lan)
    except EndpointError as exc:
        raise _refused("url", f"the base URL is refused ({exc.code})") from None
    if not is_loopback_host(host) and not (allow_lan and is_private_lan_host(host)):
        raise _refused("not_loopback", "local model discovery connects to loopback hosts only (a private LAN address "
                                       "needs --allow-lan-endpoint)")
    parts = urlsplit(base_url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, port, parts.path.rstrip("/")


class LoopbackClient:
    """GET (and Ollama's metadata POST) against one loopback server. See the module docstring for the rules."""

    def __init__(self, base_url: str, *, timeout: float = TIMEOUT_S, allow_lan: bool = False,
                 connection: Callable[..., http.client.HTTPConnection] | None = None,
                 api_key: str | None = None) -> None:
        from agentprov_capture.endpoints import is_loopback_host

        self.base_url = base_url
        self.host, self.port, self.base_path = loopback_target(base_url, allow_lan=allow_lan)
        #: a LAN target (D-698): the connected peer must then be exactly that address
        self.lan = not is_loopback_host(self.host)
        if api_key is not None and self.lan:  # D-827: a key never leaves the machine (as the worker's rule)
            raise _refused("lan_key", "an endpoint key is never sent to a LAN address")
        self._api_key = api_key or None
        self.https = urlsplit(base_url).scheme == "https"
        self.timeout = timeout
        self._connection = connection
        self.log: list[Response] = []

    def _conn(self) -> http.client.HTTPConnection:
        if self._connection is not None:
            return self._connection(self.host, self.port, timeout=self.timeout)
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=self.timeout)

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Response | None:
        """One exchange; ``None`` when nothing answered. ``path`` starting with ``/v1``-style base routes is taken as
        given (absolute on the server)."""
        data = None if body is None else json.dumps(body, ensure_ascii=True, sort_keys=True).encode("ascii")
        headers = {"Accept": "application/json", "User-Agent": "agentprov-local-models"}
        if self._api_key is not None:  # D-827: only after the peer check below has passed is anything sent
            headers["Authorization"] = f"Bearer {self._api_key}"
        if data is not None:
            headers["Content-Type"] = "application/json"
        conn = self._conn()
        try:
            try:
                conn.connect()
                peer = conn.sock.getpeername()[0] if conn.sock is not None else ""
                address = ipaddress.ip_address(str(peer).split("%")[0])
                if not (address == ipaddress.ip_address(self.host) if self.lan else address.is_loopback):
                    raise _refused("not_loopback", "the connected peer is not the endpoint's address")
                conn.request(method, path, body=data, headers=headers)
                resp = conn.getresponse()
                status = resp.status
                raw = resp.read(MAX_BODY_BYTES + 1)
            except LocalModelError:
                raise
            except (OSError, http.client.HTTPException, ValueError):
                return None
        finally:
            conn.close()
        if len(raw) > MAX_BODY_BYTES:
            raw = b""
            status = -1  # oversize: treated as no usable answer, never parsed
        out = Response(path, status, bytes(raw), "sha256:" + hashlib.sha256(raw).hexdigest())
        self.log.append(out)
        return out

    def get(self, path: str) -> Response | None:
        return self.request("GET", path)

    def get_json(self, path: str) -> tuple[Response | None, Any]:
        resp = self.get(path)
        return resp, (resp.json() if resp is not None else None)

    def openai_path(self, route: str) -> str:
        return f"{self.base_path}/{route}"


# ----------------------------------------------------------------------------------------------------------------
# Fingerprint
# ----------------------------------------------------------------------------------------------------------------


@dataclass
class ServerObservation:
    kind: str  # one of SIGNED_KINDS or GENERIC
    version: str | None
    evidence: list[Response] = field(default_factory=list)

    def fingerprint_sha256(self) -> str:
        from agentprov.io.canonical import jcs_bytes, sha256_hex

        return "sha256:" + sha256_hex(jcs_bytes([r.cite() for r in self.evidence]))


def _openai_ids(doc: Any) -> list[dict[str, Any]] | None:
    data = _dict(doc).get("data")
    if not isinstance(data, list) or len(data) > MAX_MODELS:
        return None
    out = []
    for item in data:
        ident = _label(_dict(item).get("id"))
        if ident is not None:
            out.append(dict(_dict(item), id=ident))
    return out


def detect_server(client: LoopbackClient) -> ServerObservation:
    """Which server answers at ``client``'s base URL. Unreachable: exit 3. Every signed kind's own route is tried, so a
    server of another kind on a shared default port (8000, 8080) is named, never mistaken for the expected one."""
    models, doc = client.get_json(client.openai_path("models"))
    if models is None:
        raise _unavailable("unreachable", "the local server did not answer")
    if models.status in (401, 403):  # D-827: the server wants a key (oMLX can be set up with one)
        raise _unavailable("unauthorized", f"GET {client.openai_path('models')} was refused (HTTP {models.status}): the "
                                           "server wants an API key")
    if _openai_ids(doc) is None:
        raise _unavailable("bad_listing", f"GET {client.openai_path('models')} is not an OpenAI-style model listing "
                                          f"(HTTP {models.status})")
    r, version = client.get_json("/api/version")
    if r is not None and isinstance(_dict(version).get("version"), str):
        tags, tdoc = client.get_json("/api/tags")
        if tags is not None and isinstance(_dict(tdoc).get("models"), list):
            return ServerObservation("ollama", _text(version["version"], 40), [models, r, tags])
    r, doc2 = client.get_json("/api/v1/models")
    if r is not None and isinstance(_dict(doc2).get("models"), list) and all(
            isinstance(_dict(m).get("key"), str) for m in doc2["models"]):
        evidence = [models, r]
        greeting, gdoc = client.get_json("/lmstudio-greeting")  # D-736: LM Studio's own self-identification
        if greeting is not None and _dict(gdoc).get("lmstudio") is True:
            evidence.append(greeting)
        return ServerObservation("lmstudio", None, evidence)  # no version over HTTP (checked on 0.4.23; D-736)
    r, props = client.get_json("/props")
    if r is not None and ("total_slots" in _dict(props) or "default_generation_settings" in _dict(props)):
        build = _dict(props).get("build_info")
        return ServerObservation("llamacpp", _text(build, 80), [models, r])
    r, vdoc = client.get_json("/version")
    owners = {str(_dict(m).get("owned_by")) for m in (_openai_ids(doc) or [])}
    if r is not None and isinstance(_dict(vdoc).get("version"), str) and owners <= {"vllm"}:
        return ServerObservation("vllm", _text(vdoc["version"], 40), [models, r])
    return ServerObservation(GENERIC, None, [models])


def kind_matches(expected: str, observed: str) -> bool:
    """A signed kind must be observed as itself; ``omlx`` and ``mlx_lm`` accept the generic OpenAI server only."""
    if expected in SIGNED_KINDS:
        return observed == expected
    return observed == GENERIC


# ----------------------------------------------------------------------------------------------------------------
# Listings
# ----------------------------------------------------------------------------------------------------------------


@dataclass
class ServerListing:
    endpoint: str | None
    base_url: str
    expected_kind: str | None
    server: ServerObservation
    rows: list[dict[str, Any]]
    native: dict[str, Mapping[str, Any]]  # id -> the checked native entry (identity source)
    openai: Response
    native_response: Response | None
    lan: bool = False  # reached on a private LAN address (D-698)

    def row(self, model_id: str) -> dict[str, Any] | None:
        return next((r for r in self.rows if r["id"] == model_id), None)

    def ids(self, *, servable_only: bool = True) -> list[str]:
        return [r["id"] for r in self.rows if r["servable"] or not servable_only]


def _row(model_id: str, servable: bool, **facts: Any) -> dict[str, Any]:
    return {"id": model_id, "servable": servable, "remote": bool(facts.pop("remote", False)), **_drop_none(facts)}


def _ollama_rows(doc: Any, served: set[str]) -> tuple[list[dict[str, Any]], dict[str, Mapping[str, Any]]]:
    rows: list[dict[str, Any]] = []
    native: dict[str, Mapping[str, Any]] = {}
    for item in _list(_dict(doc).get("models"))[:MAX_MODELS]:
        entry = _dict(item)
        name = _label(entry.get("name")) or _label(entry.get("model"))
        if name is None:
            continue
        details = _dict(entry.get("details"))
        remote = any(k in entry for k in ("remote_host", "remote_model")) or name.endswith("-cloud") \
            or ":cloud" in name or "-cloud:" in name
        checked = _drop_none({
            "digest": _digest(entry.get("digest")), "size_bytes": _count(entry.get("size")),
            "format": _text(details.get("format"), 40), "family": _text(details.get("family"), 60),
            "families": [f for f in (_text(x, 60) for x in _list(details.get("families"))[:16]) if f] or None,
            "parameter_size": _text(details.get("parameter_size"), 40),
            "quantization_level": _text(details.get("quantization_level"), 40),
            "remote_host": _text(entry.get("remote_host"), 200),
        })
        native[name] = checked
        rows.append(_row(name, name in served, family=checked.get("family"), params=checked.get("parameter_size"),
                         quantization=checked.get("quantization_level"), format=checked.get("format"),
                         size_bytes=checked.get("size_bytes"), digest=checked.get("digest"), remote=remote))
    return rows, native


def _lmstudio_rows(doc: Any, served: set[str],
                   not_chat: set[str]) -> tuple[list[dict[str, Any]], dict[str, Mapping[str, Any]]]:
    rows: list[dict[str, Any]] = []
    native: dict[str, Mapping[str, Any]] = {}
    for item in _list(_dict(doc).get("models"))[:MAX_MODELS]:
        entry = _dict(item)
        key = _label(entry.get("key"))
        if key is None:
            continue
        if entry.get("type") not in (None, "llm", "vlm"):
            not_chat.add(key)  # embedding and decision models are not chat models (LM Studio lists them in /v1/models)
            continue
        quant = _dict(entry.get("quantization"))
        caps = _dict(entry.get("capabilities"))
        loaded = [_dict(i) for i in _list(entry.get("loaded_instances"))[:16]]
        parallel = [_count(_dict(i.get("config")).get("parallel")) for i in loaded]
        context = [_count(_dict(i.get("config")).get("context_length")) for i in loaded]
        checked = _drop_none({
            "key": key, "publisher": _label(entry.get("publisher")), "display_name": _text(entry.get("display_name")),
            "architecture": _text(entry.get("architecture"), 60), "format": _text(entry.get("format"), 20),
            "quantization": _text(quant.get("name"), 40), "bits_per_weight": _number(quant.get("bits_per_weight")),
            "size_bytes": _count(entry.get("size_bytes")), "params": _text(entry.get("params_string"), 40),
            "max_context_length": _count(entry.get("max_context_length")),
            "trained_for_tool_use": _flag(caps.get("trained_for_tool_use")),
            "loaded_instances": len(loaded),
            "parallel": next((p for p in parallel if p is not None), None),
            "context_length": next((c for c in context if c is not None), None),
        })
        native[key] = checked
        rows.append(_row(key, key in served, display_name=checked.get("display_name"),
                         publisher=checked.get("publisher"), architecture=checked.get("architecture"),
                         params=checked.get("params"), quantization=checked.get("quantization"),
                         format=checked.get("format"), size_bytes=checked.get("size_bytes"),
                         context_length=checked.get("context_length") or checked.get("max_context_length"),
                         loaded=bool(loaded), parallel=checked.get("parallel"),
                         tool_use=checked.get("trained_for_tool_use")))
    return rows, native


def _openai_rows(items: list[dict[str, Any]], kind: str) -> tuple[list[dict[str, Any]], dict[str, Mapping[str, Any]]]:
    rows: list[dict[str, Any]] = []
    native: dict[str, Mapping[str, Any]] = {}
    for item in items:
        meta = _dict(item.get("meta"))
        checked = _drop_none({
            "owned_by": _text(item.get("owned_by"), 60), "root": _label(item.get("root")),
            "max_model_len": _count(item.get("max_model_len")), "n_params": _count(meta.get("n_params")),
            "size_bytes": _count(meta.get("size")), "n_ctx_train": _count(meta.get("n_ctx_train")),
        })
        native[item["id"]] = checked
        rows.append(_row(item["id"], True, size_bytes=checked.get("size_bytes"),
                         context_length=checked.get("max_model_len") or checked.get("n_ctx_train"),
                         params=str(checked["n_params"]) if "n_params" in checked else None))
    return rows, native


def list_server(base_url: str, *, endpoint: str | None = None, expected_kind: str | None = None,
                client: LoopbackClient | None = None, allow_lan: bool = False,
                api_key: str | None = None) -> ServerListing:
    """The models a running local server serves, enriched from its native listing. A server of a different kind than
    the endpoint names is refused (exit 4). ``api_key``: the endpoint's optional key (D-827)."""
    client = client or LoopbackClient(base_url, allow_lan=allow_lan, api_key=api_key)
    try:
        server = detect_server(client)
    except LocalModelError as exc:
        if exc.code != "run.local.unauthorized":
            raise
        raise _unavailable("unauthorized", f"{exc}; {_key_hint(endpoint, sent=client._api_key is not None)}") from None
    if expected_kind is not None and not kind_matches(expected_kind, server.kind):
        raise _refused("wrong_server", f"the server at this base URL is {server.kind}, not {expected_kind}")
    openai = server.evidence[0]
    items = _openai_ids(openai.json()) or []
    served = {i["id"] for i in items}
    native_resp: Response | None = None
    not_chat: set[str] = set()
    if server.kind == "ollama":
        native_resp = server.evidence[2]
        rows, native = _ollama_rows(native_resp.json(), served)
    elif server.kind == "lmstudio":
        native_resp = server.evidence[1]
        rows, native = _lmstudio_rows(native_resp.json(), served, not_chat)
    else:
        rows, native = _openai_rows(items, server.kind)
    known = {r["id"] for r in rows} | not_chat
    rows += [_row(i, True) for i in sorted(served - known)]  # served ids the native listing did not name
    rows.sort(key=lambda r: (not r["servable"], r["id"]))
    return ServerListing(endpoint, base_url, expected_kind, server, rows, native, openai, native_resp, lan=client.lan)


def local_key_variable(endpoint: str | None) -> str | None:
    """A local entry's optional key variable (``api_key_env``, D-827); ``None`` for any other endpoint or none."""
    from agentprov_capture.endpoints import EndpointError, get_endpoint

    try:
        entry = get_endpoint(endpoint) if endpoint else None
    except EndpointError:
        return None
    return entry.api_key_env if entry is not None and entry.local else None


def _key_hint(endpoint: str | None, *, sent: bool) -> str:
    """What to do about a refused listing: the endpoint's key variable by name (never a value)."""
    from agentprov_capture.endpoints import EndpointError, get_endpoint

    try:
        variable = get_endpoint(endpoint).api_key_env if endpoint else None
    except EndpointError:
        variable = None
    if variable is None:
        return "this endpoint has no key setting (api_key_env); turn the server's key off, or use an endpoint that has one"
    if sent:
        return f"the {variable} that was sent was not accepted"
    return f"store it with 'agentprov keys set {variable}' (the keychain first; .env is the fallback)"


def listing_document(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    return {"format": LISTING_FORMAT, "endpoints": list(entries)}


def listing_entry(listing: ServerListing) -> dict[str, Any]:
    return {
        "endpoint": listing.endpoint, "base_url": listing.base_url, "status": "up",
        "server": {"kind_expected": listing.expected_kind, "kind_observed": listing.server.kind,
                   "version": listing.server.version},
        "listing_sha256": listing.openai.sha256, "models": listing.rows,
    }


def down_entry(endpoint: str | None, base_url: str, kind: str | None, exc: LocalModelError) -> dict[str, Any]:
    status = "refused" if exc.exit_code == 4 else "down"
    return {"endpoint": endpoint, "base_url": base_url, "status": status, "reason": exc.code,
            "server": {"kind_expected": kind, "kind_observed": None, "version": None}, "models": []}


# ----------------------------------------------------------------------------------------------------------------
# Files and digests
# ----------------------------------------------------------------------------------------------------------------


class DigestCache:
    """sha256 of large files keyed by ``(st_dev, st_ino, size, mtime_ns)``. Reads always; writes only when
    ``writable`` (a dry run writes nothing, N.1.6). The cache file is local evidence of nothing: a stale or edited
    entry costs a recomputation at most once the key changes, and a hostile line is skipped."""

    def __init__(self, path: Path | None, *, writable: bool) -> None:
        self.path = path
        self.writable = writable and path is not None
        self.entries: dict[str, str] = {}
        if path is not None and path.is_file():
            try:
                with path.open("rb") as fh:
                    for line in fh.read(16 * 1024 * 1024).splitlines()[:100_000]:
                        try:
                            row = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(row, dict) and isinstance(row.get("k"), str) and _HEX64.fullmatch(
                                str(row.get("sha256"))):
                            self.entries[row["k"]] = row["sha256"]
            except OSError:
                pass

    @staticmethod
    def key(st: os.stat_result) -> str:
        return f"{st.st_dev}:{st.st_ino}:{st.st_size}:{st.st_mtime_ns}"

    def get(self, st: os.stat_result) -> str | None:
        return self.entries.get(self.key(st))

    def put(self, st: os.stat_result, digest: str) -> None:
        k = self.key(st)
        if self.entries.get(k) == digest:
            return
        self.entries[k] = digest
        if self.writable and self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.path.open("a", encoding="ascii") as fh:
                fh.write(json.dumps({"k": k, "sha256": digest}, sort_keys=True) + "\n")


def _hash_file(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def _inside(child: Path, root: Path) -> bool:
    try:
        child.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass
class FileFacts:
    method: str
    label: str
    snapshot_commit: str | None = None
    files: list[dict[str, Any]] = field(default_factory=list)
    weights_hashed: bool = True
    problems: list[str] = field(default_factory=list)
    match: str | None = None  # how the directory was tied to the served model (LM Studio)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"method": self.method, "label": self.label, "snapshot_commit": self.snapshot_commit,
               "files": self.files, "weights_hashed": self.weights_hashed}
        if self.problems:
            out["problems"] = sorted(set(self.problems))
        if self.match is not None:
            out["match"] = self.match
        return out


def walk_model_dir(root: Path, label: str, method: str, *, hash_weights: bool, cache: DigestCache,
                   blobs: Path | None = None) -> FileFacts:
    """Digest every regular file under ``root`` (bounded; symlinks must stay inside ``root``, or inside ``blobs`` for an
    HF snapshot, whose 64-hex blob names give the digest without reading the file)."""
    facts = FileFacts(method, label, weights_hashed=hash_weights)
    real_root = Path(os.path.realpath(root))
    real_blobs = Path(os.path.realpath(blobs)) if blobs is not None else None
    seen = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        here, depth = stack.pop()
        try:
            entries = sorted(os.scandir(here), key=lambda e: e.name)
        except OSError:
            facts.problems.append("unreadable_dir")
            continue
        for entry in entries:
            seen += 1
            if seen > MAX_WALK_ENTRIES:
                facts.problems.append("too_many_entries")
                stack.clear()
                break
            if entry.name.startswith("."):
                continue
            path = Path(entry.path)
            real = Path(os.path.realpath(path))
            allowed = _inside(real, real_root) or (real_blobs is not None and _inside(real, real_blobs))
            if not allowed:
                facts.problems.append("symlink_outside_root")
                continue
            try:
                st = os.stat(real)
            except OSError:
                facts.problems.append("unreadable_file")
                continue
            rel = path.relative_to(root).as_posix()
            if stat.S_ISDIR(st.st_mode):
                if depth + 1 < MAX_WALK_DEPTH and not entry.is_symlink():
                    stack.append((path, depth + 1))
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            weight = entry.name.lower().endswith(WEIGHT_SUFFIXES)
            row: dict[str, Any] = {"name": rel, "size": st.st_size}
            if real_blobs is not None and _inside(real, real_blobs) and _HEX64.fullmatch(real.name):
                row["sha256"], row["sha256_source"] = "sha256:" + real.name, "hf_blob_name"
            elif weight and not hash_weights:
                row["sha256"], row["sha256_source"] = None, "not_hashed"
            else:
                cached = cache.get(st) if weight else None
                try:
                    digest = cached or _hash_file(real)
                except OSError:
                    facts.problems.append("unreadable_file")
                    continue
                if weight and cached is None:
                    cache.put(st, digest)
                row["sha256"], row["sha256_source"] = "sha256:" + digest, "computed"
            facts.files.append(row)
    facts.files.sort(key=lambda r: r["name"])
    return facts


def hf_cache_root(environ: Mapping[str, str]) -> Path:
    if environ.get("HF_HUB_CACHE"):
        return Path(environ["HF_HUB_CACHE"]).expanduser()
    if environ.get("HF_HOME"):
        return Path(environ["HF_HOME"]).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def hf_snapshot(repo_id: str, *, environ: Mapping[str, str], hash_weights: bool, cache: DigestCache) -> FileFacts | None:
    """``models--org--name`` in the HF cache: the ``refs/main`` snapshot (the revision a server loads by default)."""
    parts = repo_id.split("/")
    if len(parts) != 2 or not all(_label(p) and "/" not in p and p not in (".", "..") for p in parts):
        return None
    repo = hf_cache_root(environ) / f"models--{parts[0]}--{parts[1]}"
    ref = repo / "refs" / "main"
    try:
        commit = ref.read_bytes()[:100].decode("ascii").strip() if ref.is_file() else ""
    except (OSError, UnicodeDecodeError):
        commit = ""
    if not _HEX40.fullmatch(commit):
        return None
    snap = repo / "snapshots" / commit
    if not snap.is_dir():
        return None
    facts = walk_model_dir(snap, repo_id, "hf_cache", hash_weights=hash_weights, cache=cache, blobs=repo / "blobs")
    facts.snapshot_commit = commit
    return facts


def lmstudio_models_root(environ: Mapping[str, str]) -> Path:
    """``downloadsFolder`` from LM Studio's settings (strict, bounded parse), else ``~/.lmstudio/models``."""
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    home = Path(environ.get("LMSTUDIO_HOME") or Path.home() / ".lmstudio")
    settings = home / "settings.json"
    try:
        if settings.is_file() and settings.stat().st_size <= 4 * 1024 * 1024:
            folder = _dict(strict_json_loads(settings.read_bytes(), IngestLimits())).get("downloadsFolder")
            if isinstance(folder, str) and folder.isprintable() and Path(folder).is_absolute():
                return Path(folder)
    except (OSError, IngestError):
        pass
    return home / "models"


#: the folder search (D-828): at most this many entries are listed per directory; no file is opened
MAX_FIND_ENTRIES: Final = 4096
FOLDERS_FORMAT: Final = "agentprov-model-folders/0.1"
_HEX_SUFFIX = re.compile(r"-[0-9a-f]{8,64}")


def omlx_home(environ: Mapping[str, str]) -> Path:
    """oMLX's data folder (``OMLX_HOME``, else ``~/.omlx``): its ``models/`` and ``gguf/`` hold the served models."""
    return Path(environ.get("OMLX_HOME") or Path.home() / ".omlx").expanduser()


def _subdirs(folder: Path) -> list[os.DirEntry[str]]:
    """The visible subfolders of ``folder`` (links followed), at most :data:`MAX_FIND_ENTRIES` entries listed."""
    out: list[os.DirEntry[str]] = []
    try:
        with os.scandir(folder) as it:
            for n, entry in enumerate(it):
                if n >= MAX_FIND_ENTRIES:
                    break
                if not entry.name.startswith(".") and entry.is_dir(follow_symlinks=True):
                    out.append(entry)
    except OSError:
        return []
    return sorted(out, key=lambda e: e.name)


def _looks_like_model(folder: Path) -> bool:
    """A folder with a ``config.json``, weight files or oMLX's ``split/`` GGUF shards (names only; nothing opened)."""
    try:
        names = [e.name for _, e in zip(range(MAX_FIND_ENTRIES), os.scandir(folder), strict=False)]
    except OSError:
        return False
    return "config.json" in names or "split" in names or any(n.endswith((".safetensors", ".gguf")) for n in names)


def find_model_folders(model_id: str, *, environ: Mapping[str, str] | None = None) -> list[dict[str, str]]:
    """Folders that may hold ``model_id``'s files (D-828, the GUI's Find Folder), for the user to pick from:
    oMLX's ``models/`` (``NAME`` or ``ORG/NAME``) and ``gguf/`` (``NAME`` or ``NAME-<hex>``), the Hugging Face cache
    (``models--ORG--NAME``, its ``refs/main`` snapshot) and LM Studio's models folder. A ``:suffix`` (an oMLX context
    alias or an Ollama tag) is not part of a folder name. Names are compared, never trusted as paths: only folders
    found by listing the roots are returned, and no file is opened. Each entry is ``{path, source}``."""
    env = os.environ if environ is None else environ
    base = model_id.split(":", 1)[0]
    if not _label(base) or base in (".", "..") or ".." in base.split("/"):
        return []
    name = base.rsplit("/", 1)[-1]
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(folder: Path, source: str) -> None:
        real = os.path.realpath(folder)
        if real not in seen and _looks_like_model(Path(real)):
            seen.add(real)
            found.append({"path": str(folder), "source": source})

    omlx = omlx_home(env)
    for entry in _subdirs(omlx / "models"):
        if entry.name == name:
            add(Path(entry.path), "omlx")
        elif entry.name == base.split("/", 1)[0] or not _looks_like_model(Path(entry.path)):
            for sub in _subdirs(Path(entry.path)):
                if sub.name == name:
                    add(Path(sub.path), "omlx")
    for entry in _subdirs(omlx / "gguf"):
        if entry.name == name or (entry.name.startswith(name) and _HEX_SUFFIX.fullmatch(entry.name[len(name):])):
            add(Path(entry.path), "omlx_gguf")
    repo = "models--" + base.replace("/", "--")
    hf = hf_cache_root(env) / repo
    if "/" not in name and hf.is_dir():
        ref = hf / "refs" / "main"
        try:
            commit = ref.read_bytes()[:100].decode("ascii").strip() if ref.is_file() else ""
        except (OSError, UnicodeDecodeError):
            commit = ""
        snaps = _subdirs(hf / "snapshots")
        pick = [s for s in snaps if s.name == commit] if _HEX40.fullmatch(commit) else snaps[-1:] if len(snaps) == 1 else []
        for snap in pick:
            add(Path(snap.path), "hf_cache")
    lms = lmstudio_models_root(env)
    for entry in _subdirs(lms):
        for sub in _subdirs(Path(entry.path)):
            if sub.name == name and ("/" not in base or entry.name == base.split("/", 1)[0]):
                add(Path(sub.path), "lmstudio")
    return found


def _tree_size(root: Path) -> int | None:
    """The total size of the regular files under ``root`` (the bounded walk's rules; no file is read)."""
    total, seen = 0, 0
    real_root = Path(os.path.realpath(root))
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        here, depth = stack.pop()
        try:
            entries = list(os.scandir(here))
        except OSError:
            return None
        for entry in entries:
            seen += 1
            if seen > MAX_WALK_ENTRIES:
                return None
            if entry.name.startswith("."):
                continue
            real = Path(os.path.realpath(entry.path))
            if not _inside(real, real_root):
                continue
            try:
                st = os.stat(real)
            except OSError:
                return None
            if stat.S_ISDIR(st.st_mode):
                if depth + 1 < MAX_WALK_DEPTH and not entry.is_symlink():
                    stack.append((Path(entry.path), depth + 1))
            elif stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


def lmstudio_dir(entry: Mapping[str, Any], *, environ: Mapping[str, str], hash_weights: bool,
                 cache: DigestCache) -> tuple[FileFacts | None, str | None]:
    """The LM Studio model directory of a served key. LM Studio's key is not the directory name (observed on 0.4.23:
    key ``qwen3-8b-abliterated-v2`` for ``mlx-community/Qwen3-8B-abliterated-v2-mxfp4``), so a candidate is a directory
    under the entry's publisher whose name, case-insensitively, equals the key or starts with ``key-``; it is accepted
    only when exactly one candidate's total file size equals the ``size_bytes`` the server reports (``match``:
    ``name_and_size``). An exact name without a size to compare is accepted as ``name_only``. Otherwise no directory
    (``not_found`` or ``ambiguous``): nothing is guessed."""
    key = str(entry.get("key", ""))
    publisher = entry.get("publisher")
    name = key
    if "/" in key:
        publisher, name = key.split("/", 1)
    if not isinstance(publisher, str) or "/" in name or not name or publisher in (".", ".."):
        return None, "unresolved"
    pub_dir = lmstudio_models_root(environ) / publisher
    want = entry.get("size_bytes")
    lowered = name.lower()
    try:
        candidates = sorted((e for e in os.scandir(pub_dir) if e.is_dir() and not e.is_symlink()
                             and (e.name.lower() == lowered or e.name.lower().startswith(lowered + "-"))),
                            key=lambda e: e.name)
    except OSError:
        return None, "not_found"
    if isinstance(want, int):
        sized = [e for e in candidates if _tree_size(Path(e.path)) == want]
        chosen, match = (sized[0], "name_and_size") if len(sized) == 1 else (None, None)
        if len(sized) > 1:
            return None, "ambiguous"
    else:
        exact = [e for e in candidates if e.name.lower() == lowered]
        chosen, match = (exact[0], "name_only") if len(exact) == 1 else (None, None)
    if chosen is None:
        return None, "not_found"
    facts = walk_model_dir(Path(chosen.path), f"{publisher}/{chosen.name}", "lmstudio_dir", hash_weights=hash_weights,
                           cache=cache)
    facts.match = match
    return facts, None


def operator_dir(path: str, *, hash_weights: bool, cache: DigestCache) -> FileFacts:
    """``--model-dir``: a directory (or one model file) the operator names. Its label is the last path component."""
    p = Path(path)
    if p.is_file():
        st = p.stat()
        cached = cache.get(st) if hash_weights else None
        digest = (cached or _hash_file(p)) if hash_weights else None
        if digest and not cached:
            cache.put(st, digest)
        facts = FileFacts("operator_dir", p.name, weights_hashed=hash_weights)
        facts.files.append({"name": p.name, "size": st.st_size, "sha256": f"sha256:{digest}" if digest else None,
                            "sha256_source": "computed" if digest else "not_hashed"})
        return facts
    if not p.is_dir():
        raise LocalModelError("--model-dir does not name a directory or file", code="run.local.model_dir", exit_code=2)
    return walk_model_dir(p, p.name, "operator_dir", hash_weights=hash_weights, cache=cache)


# ----------------------------------------------------------------------------------------------------------------
# The identity record
# ----------------------------------------------------------------------------------------------------------------


def _ollama_show(client: LoopbackClient, model_id: str) -> tuple[dict[str, Any], Response | None]:
    resp = client.request("POST", "/api/show", {"model": model_id})
    doc = resp.json() if resp is not None else None
    if not isinstance(doc, Mapping):
        return {}, resp
    info = _dict(doc.get("model_info"))
    arch = _text(info.get("general.architecture"), 60)

    def text_digest(key: str) -> str | None:
        value = doc.get(key)
        return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest() if isinstance(value, str) else None

    facts = _drop_none({
        "capabilities": sorted(c for c in (_text(x, 40) for x in _list(doc.get("capabilities"))[:32]) if c) or None,
        "architecture": arch,
        "parameter_count": _count(info.get("general.parameter_count")),
        "context_length": _count(info.get(f"{arch}.context_length")) if arch else None,
        "template_sha256": text_digest("template"), "parameters_sha256": text_digest("parameters"),
        "modelfile_sha256": text_digest("modelfile"), "show_sha256": resp.sha256 if resp is not None else None,
    })
    return facts, resp


def model_identity(listing: ServerListing, model_id: str, *, client: LoopbackClient | None = None,
                   environ: Mapping[str, str] | None = None, model_dir: str | None = None, hash_weights: bool = True,
                   cache: DigestCache | None = None, files: bool = True, now: datetime | None = None,
                   api_key: str | None = None) -> dict[str, Any]:
    """The ``agentprov-local-model/0.2`` record of ``model_id``: observed facts only, each citing a response digest or a
    file digest. Load and serving state is ``observed_state``, outside ``identity_sha256`` (D-736). A model the server does not serve is refused (exit 3, with the served ids); a remote one (exit 4).
    ``files=False`` skips the file part (the per-cell re-observation compares the server side only)."""
    env = os.environ if environ is None else environ
    row = listing.row(model_id)
    if row is None or not row["servable"]:
        raise _unavailable("model_not_served", not_served_message(listing, model_id))
    if row["remote"]:
        raise _refused("remote_model", "the server marks this model as remote (inference would leave the machine)")
    client = client or LoopbackClient(listing.base_url, allow_lan=listing.lan, api_key=api_key)
    cache = cache or DigestCache(None, writable=False)
    native = dict(listing.native.get(model_id, {}))
    cites = [listing.openai.cite()] + ([listing.native_response.cite()] if listing.native_response else [])
    file_facts: FileFacts | None = None
    files_reason: str | None = None if files else "not_requested"
    kind = listing.server.kind
    if kind == "ollama":
        show, resp = _ollama_show(client, model_id)
        native.update(show)
        if resp is not None:
            cites.append(resp.cite())
        files_reason = files_reason or "ollama_manifest_digest"  # the digest names the blobs; no directory walk
    elif kind == "llamacpp":
        resp, props = client.get_json("/props")
        if resp is not None:
            cites.append(resp.cite())
            p = _dict(props)
            path = p.get("model_path")
            native.update(_drop_none({
                "total_slots": _count(p.get("total_slots")),
                "model_file": _label(os.path.basename(path)) if isinstance(path, str) else None,
                "chat_template_sha256": "sha256:" + hashlib.sha256(p["chat_template"].encode("utf-8")).hexdigest()
                if isinstance(p.get("chat_template"), str) else None,
                "build_info": _text(p.get("build_info"), 80),
            }))
    if files and model_dir is not None:
        file_facts = operator_dir(model_dir, hash_weights=hash_weights, cache=cache)
        if kind == "llamacpp" and native.get("model_file") and native["model_file"] not in (
                file_facts.label, *(f["name"] for f in file_facts.files)):
            raise _refused("model_dir_mismatch", "--model-dir does not hold the file the server reports loading")
    elif files and listing.lan:  # the files are on the other machine: a same-named copy here proves nothing (D-698)
        files_reason = None
    elif files and kind == "lmstudio":
        file_facts, files_reason = lmstudio_dir(native, environ=env, hash_weights=hash_weights, cache=cache)
    elif files and kind == "llamacpp":
        files_reason = "no_directory_known (give --model-dir)"
    elif files and kind != "ollama":  # vllm and the generic OpenAI servers (oMLX, mlx_lm): an HF repo id finds its cache snapshot
        repo = native.get("root") or model_id
        file_facts = hf_snapshot(str(repo), environ=env, hash_weights=hash_weights, cache=cache) \
            if isinstance(repo, str) and "/" in repo else None
        files_reason = None if file_facts is not None else "no_directory_known (give --model-dir)"
    state_fields = STATE_FIELDS.get(kind, frozenset())
    observed_state = {k: v for k, v in native.items() if k in state_fields}
    native = {k: v for k, v in native.items() if k not in state_fields and k not in DROPPED_FIELDS}
    source = VERSION_SOURCES.get(kind) if kind in VERSION_SOURCES else None
    record: dict[str, Any] = {
        "format": IDENTITY_FORMAT,
        "observed_at": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoint": listing.endpoint,
        "base_url": listing.base_url,
        "network": "lan" if listing.lan else "loopback",  # D-698: a LAN model runs off this machine
        "server": {"kind": kind, "kind_expected": listing.expected_kind, "version": listing.server.version,
                   "version_source": source if listing.server.version is not None else "not exposed by the server",
                   "fingerprint_sha256": listing.server.fingerprint_sha256()},
        "model_id": model_id,
        "listing": {"responses": cites, "entry": row},
        "server_identity": native,  # facts that name the model only (D-736)
        "observed_state": observed_state,  # load and serving state: recorded, never part of an identity digest
        "files": file_facts.to_json() if file_facts is not None else None,
        "files_reason": (files_reason or ("lan_host_files_unavailable (give --model-dir for a shared copy)"
                                          if listing.lan else None)) if file_facts is None else None,
    }
    record["identity_sha256"] = identity_sha256(record)
    return record


def not_served_message(listing: ServerListing, model_id: str) -> str:
    """The refusal for an id the server does not serve: the served ids (labels, checked) and the closest ones."""
    import difflib

    ids = listing.ids()
    close = difflib.get_close_matches(model_id, ids, n=3)
    shown = ", ".join(ids[:30]) + (f", ... ({len(ids)} in all)" if len(ids) > 30 else "")
    return (f"the model id is not served by this server; served: {shown or 'none'}"
            + (f"; did you mean {' or '.join(close)}?" if close else ""))


def server_side(record: Mapping[str, Any]) -> dict[str, Any]:
    """The server-observable part of a record (what the per-cell re-observation compares)."""
    return {"server_kind": _dict(record.get("server")).get("kind"), "model_id": record.get("model_id"),
            "server_identity": record.get("server_identity"),
            "entry": {k: v for k, v in _dict(_dict(record.get("listing")).get("entry")).items()
                      if k not in ("loaded", "parallel", "context_length")}}


def server_side_sha256(record: Mapping[str, Any]) -> str:
    from agentprov.io.canonical import jcs_bytes, sha256_hex

    return "sha256:" + sha256_hex(jcs_bytes(server_side(record)))  # server_identity holds no state (D-736)


# ----------------------------------------------------------------------------------------------------------------
# Registry helpers
# ----------------------------------------------------------------------------------------------------------------


def local_endpoints() -> dict[str, Any]:
    """The ``local = true`` entries of ``endpoints.toml`` by name."""
    from agentprov_capture.endpoints import load_endpoints

    return {n: e for n, e in sorted(load_endpoints().items()) if e.local}


def local_endpoint_names() -> list[str]:
    return list(local_endpoints())


def configured_base_url(entry: Any, *, home: Path | None = None) -> tuple[str, str]:
    """A local endpoint's base URL when no ``--base-url`` (and, for ``run``, no ``.env`` value) is given: the user's
    setting ``endpoints.<name>.base_url`` (``agentprov settings``, D-703; D-699), else the registry default. Returns
    ``(url, source)`` with source ``settings`` or ``registry``. The settings module refuses a host name, userinfo, query
    or fragment when the value is set, and reads a malformed stored value as unset."""
    from agentprov import settings

    value = settings.get(f"endpoints.{entry.name}.base_url", home=home)
    if isinstance(value, str) and value:
        return value, "settings"
    return str(entry.base_url), "registry"


def resolve_local(endpoint: str | None, base_url: str | None, *,
                  allow_lan: bool = False) -> tuple[str | None, str, str | None]:
    """``(endpoint name, base URL, expected server kind)`` for ``--endpoint`` and/or ``--base-url``. A base URL alone
    has no expected kind (the server is fingerprinted and recorded). ``localhost`` is accepted: the D-664 profile's
    ``localhost:PORT`` rule covers ``::1`` too, and its probe checks it; a LAN host name is refused (not loopback)."""
    from agentprov_capture.endpoints import EndpointError, get_endpoint

    if base_url is not None:
        loopback_target(base_url, allow_lan=allow_lan)
    if endpoint is None:
        if base_url is None:
            raise LocalModelError("give --endpoint or --base-url", code="run.local.usage", exit_code=2)
        return None, base_url, None
    try:
        entry = get_endpoint(endpoint)
    except EndpointError:
        raise LocalModelError(f"unknown endpoint; local endpoints: {', '.join(local_endpoint_names())}",
                              code="run.local.usage", exit_code=2) from None
    if not entry.local:
        raise _refused("not_local", "model discovery is for local endpoints only (loopback servers)")
    if base_url is None:
        base_url, _source = configured_base_url(entry)
        loopback_target(base_url, allow_lan=allow_lan)
    return entry.name, base_url, entry.server
