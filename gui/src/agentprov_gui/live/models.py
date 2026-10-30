"""Run Live's model picker: a client of ``agentprov models`` (D-691, D-692, D-730..D-735; reverse parity D-700). No Qt.

The GUI has no discovery code of its own: every list and identity record is the CLI's JSON, and every picker action is
one ``agentprov models`` call (:func:`list_argv`, :func:`refresh_argv`, :func:`identity_argv`).

* **Local endpoints** (``ollama``, ``lmstudio``, …): ``models --endpoint NAME`` lists what the running server serves
  (``agentprov-local-models/0.1``); a model it serves but cannot run here (remote, not servable) is listed as not
  usable. ``--model-id ID`` gives the identity record a live run records (``agentprov-local-model/0.2``).
* **API providers** (``openrouter``, ``anthropic``, …): ``models --endpoint NAME --refresh-if-stale`` shows the dated
  cached list and fetches only under the user's standing consent (the setting ``models.auto_refresh``) when the cache
  is over 24 h old (D-733); **Refresh List** is ``--allow-network`` (R2, confirmed). A key comes only from the keychain
  (``--keychain``, D-702), never ``.env``: without a stored key the GUI fetches only a public list (OpenRouter's, and those listed through it) and
  otherwise asks for the key first.
* Neither: the price table's models (``agentprov prices list``), as before.

Every string from a list or record is data: the view escapes it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

from agentprov_gui.live.plan import Endpoint

__all__ = ["IDENTITY_FORMAT", "LOCAL_FORMAT", "PROVIDER_ENDPOINTS", "PROVIDER_FORMAT", "PUBLIC_MODEL_LISTS",
           "ModelChoice", "ModelList", "identity_argv", "identity_lines", "is_provider", "list_argv", "parse_identity",
           "parse_list", "refresh_argv", "refresh_blocked"]

LOCAL_FORMAT: Final = "agentprov-local-models/0.1"
PROVIDER_FORMAT: Final = "agentprov-provider-models/0.1"
IDENTITY_FORMAT: Final = "agentprov-local-model/0.2"
#: the API providers ``agentprov models`` keeps a list for (``cli/live/providermodels.py``; a test keeps them equal)
PROVIDER_ENDPOINTS: Final = ("anthropic", "deepseek", "gemini", "glm", "llama", "openai", "openrouter", "qwen")
#: providers whose model list is public, fetched without a key: OpenRouter's, and the providers whose models the CLI
#: lists through OpenRouter (``OPENROUTER_PREFIXES``). A test keeps this equal to the CLI's rule.
PUBLIC_MODEL_LISTS: Final = ("gemini", "glm", "llama", "openrouter", "qwen")
_LIMITS: Final = IngestLimits().replace(max_json_bytes=32 * 1024 * 1024, max_json_depth=16)


@dataclass(frozen=True, slots=True)
class ModelChoice:
    id: str
    note: str = ""  # facts to show beside the id (size, quantization, lifecycle, price status)
    usable: bool = True  # a local model the server marks remote or not servable is not


@dataclass(frozen=True, slots=True)
class ModelList:
    endpoint: str
    kind: str  # local | provider
    state: str  # local: up | down; provider: fresh | stale | none
    detail: str  # one status line (data: escaped by the view)
    choices: tuple[ModelChoice, ...] = ()

    @property
    def usable_ids(self) -> list[str]:
        return [c.id for c in self.choices if c.usable]


def is_provider(endpoint: Endpoint) -> bool:
    return not endpoint.local and endpoint.name in PROVIDER_ENDPOINTS


def _key_options(endpoint: Endpoint, key_stored: bool) -> list[str] | None:
    """``--keychain`` when the key is stored; nothing for a public list; ``None`` when a fetch would need a key the
    keychain does not hold (the CLI would then read ``.env``, which the GUI never lets it do)."""
    if endpoint.api_key_env and key_stored:
        return ["--keychain"]
    if endpoint.name in PUBLIC_MODEL_LISTS or not endpoint.api_key_env:
        return []
    return None


def list_argv(endpoint: Endpoint, *, key_stored: bool, allow_lan: bool = False) -> list[str] | None:
    """The ``agentprov models`` call that fills the picker, or ``None`` when the CLI has no list for this endpoint."""
    if endpoint.local:
        return ["models", "--endpoint", endpoint.name, "--format", "json", *_local_key_options(endpoint, allow_lan),
                *(["--allow-lan-endpoint"] if allow_lan else [])]
    if not is_provider(endpoint):
        return None
    keys = _key_options(endpoint, key_stored)
    # under models.auto_refresh a stale cache is refreshed (D-733); without a usable key, the cache only
    return ["models", "--endpoint", endpoint.name, "--format", "json",
            *(["--refresh-if-stale", *keys] if keys is not None else [])]


def refresh_blocked(endpoint: Endpoint, *, key_stored: bool) -> str | None:
    """Why **Refresh List** is not offered for ``endpoint``, or ``None`` when it is."""
    if not is_provider(endpoint):
        return "only an API provider's list is fetched; a local server is asked directly"
    if _key_options(endpoint, key_stored) is None:
        return f"{endpoint.api_key_env} is not in the keychain (Store Key… first)"
    return None


def refresh_argv(endpoint: Endpoint, *, key_stored: bool) -> list[str] | None:
    """``models --allow-network`` (R2: the provider's registry host only; no tokens, no cost), or ``None``."""
    if refresh_blocked(endpoint, key_stored=key_stored) is not None:
        return None
    keys = _key_options(endpoint, key_stored) or []
    return ["models", "--endpoint", endpoint.name, "--allow-network", *keys, "--format", "json"]


def identity_argv(endpoint: Endpoint, model_id: str, *, allow_lan: bool = False, hash_weights: bool = True) -> list[str]:
    """The identity record of a local model (weight digests are cached by the CLI; ``--no-hash-weights`` is quick)."""
    return ["models", "--endpoint", endpoint.name, "--model-id", model_id, "--format", "json",
            *_local_key_options(endpoint, allow_lan),
            *([] if hash_weights else ["--no-hash-weights"]), *(["--allow-lan-endpoint"] if allow_lan else [])]


def _local_key_options(endpoint: Endpoint, allow_lan: bool) -> list[str]:
    """``--keychain`` for a local server that has an optional key (D-827), so the CLI reads the keychain and never
    ``.env``: a stored key is sent, and a missing one (or no keychain) means the server is asked without a key. Never
    toward a LAN address, where no key is sent."""
    return ["--keychain"] if endpoint.local and endpoint.api_key_env and not allow_lan else []


def _load(out: bytes) -> dict[str, Any] | None:
    try:
        doc = strict_json_loads(out.strip(), _LIMITS)
    except (IngestError, ValueError):  # not strict JSON within the limits: "no list", never a crash
        return None
    return doc if isinstance(doc, dict) else None


def _s(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _gb(value: Any) -> str | None:
    return f"{value / 1e9:.1f} GB" if isinstance(value, int) and not isinstance(value, bool) else None


def _local_choice(row: Mapping[str, Any]) -> ModelChoice | None:
    mid = _s(row.get("id"))
    if not mid:
        return None
    facts = [x for x in (_s(row.get("params")), _s(row.get("quantization")), _gb(row.get("size_bytes"))) if x]
    flags = [f for f, on in (("loaded", row.get("loaded") is True), ("tools", row.get("tool_use") is True),
                             ("remote", row.get("remote") is True), ("not servable", row.get("servable") is False))
             if on]
    usable = row.get("remote") is not True and row.get("servable") is not False
    return ModelChoice(mid, " · ".join([*facts, *flags]), usable)


def parse_list(endpoint: Endpoint, code: int, out: bytes, err: bytes = b"") -> ModelList:
    """The picker's list from an ``agentprov models --format json`` call (a failure is a list with no choices)."""
    doc = _load(out) if code == 0 else None
    if endpoint.local:
        entries = doc.get("endpoints") if doc and doc.get("format") == LOCAL_FORMAT else None
        entry = next((e for e in entries or [] if isinstance(e, dict) and e.get("endpoint") == endpoint.name), None)
        if entry is None:
            reason = err.decode("utf-8", "replace").strip().splitlines()[-1:] or [f"exit {code}"]
            return ModelList(endpoint.name, "local", "down", f"{endpoint.name}: no listing ({reason[0][:200]})")
        if entry.get("status") != "up":
            return ModelList(endpoint.name, "local", "down",
                             f"{endpoint.name}: down ({_s(entry.get('reason')) or 'unreachable'})")
        rows = [c for r in entry.get("models") or [] if isinstance(r, dict) and (c := _local_choice(r)) is not None]
        raw_server = entry.get("server")
        server: dict[str, Any] = raw_server if isinstance(raw_server, dict) else {}
        kind = " ".join(x for x in (_s(server.get("kind_observed")), _s(server.get("version"))) if x)
        usable = sum(c.usable for c in rows)
        return ModelList(endpoint.name, "local", "up", f"{endpoint.name}: up ({kind or 'server'}), {len(rows)} "
                         f"model(s), {usable} usable here", tuple(rows))
    if doc is None or doc.get("format") != PROVIDER_FORMAT:
        return ModelList(endpoint.name, "provider", "none", f"{endpoint.name}: no model list (exit {code})")
    choices = []
    for m in doc.get("models") or []:
        if isinstance(m, dict) and _s(m.get("id")):
            facts = [x for x in (_s(m.get("display_name")), _s(m.get("lifecycle")), _s(m.get("price_status"))) if x]
            choices.append(ModelChoice(m["id"], " · ".join(facts)))
    for m in doc.get("not_listed") or []:  # priced, but the provider's list does not show it (lists can lag)
        if isinstance(m, dict) and _s(m.get("id")):
            choices.append(ModelChoice(m["id"], "priced · not in the provider's list"))
    fetched = _s(doc.get("fetched_at"))
    if fetched is None:
        state, detail = "none", f"{endpoint.name}: no cached model list (Refresh List fetches it; network)"
    else:
        state = "stale" if doc.get("stale") is True else "fresh"
        detail = (f"{endpoint.name}: {len(choices)} model(s), list fetched {fetched}"
                  + (" (over 24 h old)" if state == "stale" else "") + f" ({_s(doc.get('source')) or 'cache'})")
    return ModelList(endpoint.name, "provider", state, detail, tuple(choices))


def parse_identity(code: int, out: bytes) -> dict[str, Any] | None:
    doc = _load(out) if code == 0 else None
    return doc if doc is not None and doc.get("format") == IDENTITY_FORMAT else None


def identity_lines(record: Mapping[str, Any]) -> Sequence[str]:
    """A short summary of an identity record for the dialog's header (the full record is shown as JSON below it)."""
    raw_server = record.get("server")
    server: Mapping[str, Any] = raw_server if isinstance(raw_server, Mapping) else {}
    files = record.get("files") if isinstance(record.get("files"), dict) else None
    lines = [f"model {record.get('model_id')} on {record.get('endpoint') or '-'} ({record.get('base_url')})",
             f"server {server.get('kind')} {server.get('version') or ''}".rstrip(),
             f"identity {record.get('identity_sha256')}"]
    if files:
        hashed = "weights hashed" if files.get("weights_hashed") else "weights not hashed (size only)"
        lines.append(f"files: {len(files.get('files') or [])} ({files.get('method')}; {hashed})")
    else:
        lines.append(f"files: none ({record.get('files_reason')})")
    return lines
