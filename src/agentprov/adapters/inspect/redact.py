"""Redaction of workstation account paths in Inspect AERs (DECISIONS D-182, user-approved 2026-10-13; design
``docs/reports/phase10h/redaction-design.md``; R-10p-3; D-601).

A source profile declares a closed table ``[[family.inspect.redact]]`` of rules ``{id, scope, pattern, replacement,
leaf?, pointers?, note?}``. The mapper runs :meth:`Redactor.apply` over every finished record:

``scope = "model_id"``
    The observed model-id strings of the unit (header ``eval.model`` and ``eval.model_roles.*.model``, every model
    event's ``model`` and ``output.model``, ``requested_model``, and every message's ``model``) that the pattern matches
    are replaced **as whole strings** wherever the AER holds them, also inside longer harness strings (state patches,
    logger lines). An exact observed id cannot reach benchmark content by accident.
``scope = "harness_text"``
    The pattern is applied only to harness-written values the mapper copies into ``ext`` or ``params``: the run scope's
    sample ``error`` (with its ``traceback`` and ``traceback_ansi``) and its ``error_retries`` (the errors of earlier
    attempts, with the same fields; D-601), events kept in ``ext`` (error and logger events), the execution's
    ``sample_metadata`` and ``task_args``, the bench actor's ``revision`` and ``code.repo`` (the mapper copies
    ``eval.revision.origin`` there; D-601) and the agent actor's ``params`` (``model_generate_config``). Header
    ``eval.metadata`` (e.g. control-arena's ``micro_protocol.prompt_file``) is listed too; the mapper does not copy it
    today. Messages, tool calls, tool results, fixtures and judgements are never touched: they are content. A rule may
    narrow itself with ``pointers``: record-relative pointers, each one of these classes or below one; the rule then
    applies only to strings at or below them (D-601: a traceback rule kept out of the logger events, which quote the
    model's tool arguments).

A replacement is built from literal text and two placeholders only: ``{span12}`` (the first 12 hex digits of SHA-256
over ``<profile id> NUL <matched span>``: distinct spans stay distinct, the same span gets the same label in every log,
and the label cannot be reversed alone) and ``{leaf}`` (the span's last path segment when it matches the rule's ``leaf``
pattern, else ``?``). Each redacted pointer is tagged ``D`` (never above its record's class) and cites
``inspect.value_redacted@1``; ``ext.inspect.redacted`` lists ``{p, rule: "<profile id>@<version>#<rule id>"}``; one info
issue ``inspect.value_redacted`` counts them. Neither the original nor its full digest is recorded; locators keep
pointing at the raw field, and raw bytes are never touched (invariant 3). Two different spans producing one label in a
unit is a profile defect (:class:`ProfileError`). So a literal-only replacement (no placeholder; D-601's ``redacted``
for URL userinfo, where no digest of a credential may be recorded) admits one span per unit: a second distinct span
fails the unit closed instead of collapsing silently.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.aer.canon import pointer_escape
from agentprov.errors import ProfileError

__all__ = ["HARNESS_POINTERS", "RULE", "RedactRule", "Redactor", "observed_model_ids", "parse_redact_rules"]

RULE: Final = "inspect.value_redacted@1"
SCOPES: Final = frozenset({"model_id", "harness_text"})
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")
_ID: Final = re.compile(r"[a-z][a-z0-9_]*")
#: Record-relative pointers whose strings are harness-written (``harness_text`` scope), by record kind ("*": any kind).
HARNESS_POINTERS: Final[Mapping[str, tuple[str, ...]]] = {
    "scope": ("/ext/inspect/error", "/ext/inspect/error_retries"),
    "execution": ("/ext/inspect/sample_metadata", "/ext/inspect/task_args", "/ext/inspect/metadata"),
    "actor": ("/ext/inspect/revision", "/code/repo", "/params"),
    "*": ("/ext/inspect/events",),
}
_ALL_HARNESS: Final = frozenset(p for pointers in HARNESS_POINTERS.values() for p in pointers)


def _under(pointer: str, prefixes: Iterable[str]) -> bool:
    return any(pointer == p or pointer.startswith(p + "/") for p in prefixes)


@dataclass(frozen=True, slots=True)
class RedactRule:
    """One ``[[family.inspect.redact]]`` rule."""

    id: str
    scope: str
    pattern: re.Pattern[str]
    replacement: str
    leaf: re.Pattern[str] | None
    #: ``harness_text`` only: the pointer classes the rule is narrowed to (``None``: every class of the record's kind)
    pointers: tuple[str, ...] | None = None


def parse_redact_rules(entries: Iterable[Any], where: str) -> tuple[RedactRule, ...]:
    """The profile's redaction rules; :class:`ProfileError` for an unknown key or scope, a pattern that does not compile
    or can match the empty string, a duplicate id, a replacement with a placeholder other than ``{span12}``/``{leaf}``
    (or ``{leaf}`` without a ``leaf`` pattern), or ``pointers`` other than a non-empty list of distinct harness pointer
    classes (or pointers below one) on a ``harness_text`` rule."""
    out: list[RedactRule] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        at = f"{where} redact[{i}]"
        if not isinstance(entry, Mapping):
            raise ProfileError(f"{at}: a table")
        unknown = set(entry) - {"id", "scope", "pattern", "replacement", "leaf", "pointers", "note"}
        if unknown:
            raise ProfileError(f"{at}: unknown keys {sorted(unknown)}")
        rid, scope, pattern, replacement = entry.get("id"), entry.get("scope"), entry.get("pattern"), entry.get("replacement")
        if not isinstance(rid, str) or _ID.fullmatch(rid) is None or rid in seen:
            raise ProfileError(f"{at}: id is a unique lower-case name")
        seen.add(rid)
        if scope not in SCOPES:
            raise ProfileError(f"{at}: scope is one of {sorted(SCOPES)}")
        if not isinstance(pattern, str) or not isinstance(replacement, str) or not replacement:
            raise ProfileError(f"{at}: pattern and replacement are strings")
        try:
            compiled = re.compile(pattern)
            leaf = re.compile(entry["leaf"]) if "leaf" in entry else None
        except (re.error, TypeError) as exc:
            raise ProfileError(f"{at}: a pattern does not compile ({exc})") from None
        if compiled.fullmatch("") is not None:
            raise ProfileError(f"{at}: the pattern matches the empty string")
        names = _PLACEHOLDER.findall(replacement)
        if any(n not in ("span12", "leaf") for n in names) or (("leaf" in names) and leaf is None):
            raise ProfileError(f"{at}: the replacement uses only literal text, {{span12}} and {{leaf}} (with a leaf pattern)")
        if "{" in _PLACEHOLDER.sub("", replacement) or "}" in _PLACEHOLDER.sub("", replacement):
            raise ProfileError(f"{at}: an unbalanced brace in the replacement")
        pointers: tuple[str, ...] | None = None
        if "pointers" in entry:
            given = entry["pointers"]
            if (scope != "harness_text" or not isinstance(given, Sequence) or isinstance(given, str) or not given
                    or not all(isinstance(q, str) and _under(q, _ALL_HARNESS) for q in given)
                    or len(set(given)) != len(given)):
                raise ProfileError(f"{at}: pointers is a list of distinct harness pointer classes (or pointers below one) "
                                   "on a harness_text rule")
            pointers = tuple(given)
        out.append(RedactRule(rid, str(scope), compiled, replacement, leaf, pointers))
    return tuple(out)


class Redactor:
    """The redaction of one unit (module docstring). ``rules`` from the profile; ``model_ids`` the unit's observed
    model-id strings."""

    def __init__(self, profile_id: str, profile_version: int, rules: Sequence[RedactRule], model_ids: Iterable[str]) -> None:
        self.profile = f"{profile_id}@{profile_version}"
        self.salt = profile_id
        self.rules = tuple(rules)
        self.harness = tuple(r for r in self.rules if r.scope == "harness_text")
        self.labels: dict[str, str] = {}  # label -> original span (in memory only: the collision check)
        #: observed model id -> (redacted label, rule id), longest first so that a longer id wins inside a string
        self.ids: dict[str, tuple[str, str]] = {}
        for model_id in sorted({m for m in model_ids if isinstance(m, str) and m}, key=lambda m: (-len(m), m)):
            for rule in (r for r in self.rules if r.scope == "model_id"):
                label = self._sub(rule, model_id)
                if label != model_id:
                    self.ids[model_id] = (label, rule.id)
                    # the id inside a JSON Pointer (an ext.lex key-order pointer, an evf or unk key): its escaped form
                    escaped = pointer_escape(model_id)
                    if escaped != model_id:
                        self.ids[escaped] = (pointer_escape(label), rule.id)
                    break
        self.ids = dict(sorted(self.ids.items(), key=lambda kv: (-len(kv[0]), kv[0])))

    @property
    def active(self) -> bool:
        return bool(self.rules)

    def _render(self, rule: RedactRule, span: str) -> str:
        # fails closed, as the agentdojo module (bug pass NF-11, regeneration-batch item 132): a zero-width match
        # redacts nothing, a slashless span is never its own leaf, and a label still holding the span is a defect
        if span == "":
            raise ProfileError(f"redaction rule {rule.id!r}: a zero-width match redacts nothing (lookarounds, \\b)")
        digest = hashlib.sha256(f"{self.salt}\0{span}".encode("utf-8", "surrogatepass")).hexdigest()[:12]
        leaf = span.rstrip("/").rsplit("/", 1)[-1]
        if rule.leaf is None or rule.leaf.fullmatch(leaf) is None or leaf == span.rstrip("/"):
            leaf = "?"
        label = rule.replacement.replace("{span12}", digest).replace("{leaf}", leaf)
        if span in label:
            raise ProfileError(f"redaction rule {rule.id!r}: its label still holds the matched span")
        prior = self.labels.setdefault(label, span)
        if prior != span:
            raise ProfileError(f"redaction rule {rule.id!r} gives one label to two different spans (D-182)")
        return label

    def _sub(self, rule: RedactRule, text: str) -> str:
        return rule.pattern.sub(lambda m: self._render(rule, m.group(0)), text)

    def _model_ids(self, text: str) -> tuple[str, list[str]]:
        used: list[str] = []
        for original, (label, rid) in self.ids.items():
            if original in text:
                text = text.replace(original, label)
                used.append(rid)
        return text, used

    def apply(self, record: dict[str, Any], cite: Callable[[str], str]) -> list[tuple[str, str]]:
        """Redact one finished record in place; return ``(pointer, rule id)`` per redacted string. ``cite(pointer)`` is
        the mapper's scoped citation of :data:`RULE`."""
        if not self.active:
            return []
        kind = str(record.get("k"))
        harness = (*HARNESS_POINTERS.get(kind, ()), *HARNESS_POINTERS["*"]) if self.harness else ()
        done: list[tuple[str, str]] = []

        def walk(node: Any, tokens: tuple[str, ...]) -> Any:
            if isinstance(node, dict) and set(node) == {"$utf16"} and isinstance(node["$utf16"], str):
                # bug pass NF-10 (item 132): a lone-surrogate string is stored as UTF-16BE in base64 (C.11.4)
                try:
                    decoded = base64.b64decode(node["$utf16"], validate=True).decode("utf-16-be", "surrogatepass")
                except (binascii.Error, UnicodeDecodeError, ValueError):
                    return node
                text = walk(decoded, tokens)
                return node if text == decoded else {
                    "$utf16": base64.b64encode(str(text).encode("utf-16-be", "surrogatepass")).decode("ascii")}
            if isinstance(node, str):
                pointer = "".join("/" + pointer_escape(t) for t in tokens)
                text, used = self._model_ids(node)
                if _under(pointer, harness):
                    for rule in self.harness:
                        if rule.pointers is not None and not _under(pointer, rule.pointers):
                            continue
                        new = self._sub(rule, text)
                        if new != text:
                            text = new
                            used.append(rule.id)
                if used:
                    done.append((pointer, used[0]))
                return text
            if isinstance(node, dict):
                out: dict[str, Any] = {}
                for key, item in node.items():
                    new_key = key
                    if isinstance(key, str):  # BF-21: a model id as an object key (ext.inspect.model_usage)
                        new_key, used = self._model_ids(key)
                        if used:
                            done.append(("".join("/" + pointer_escape(t) for t in (*tokens, new_key)), used[0]))
                    out[new_key] = walk(item, (*tokens, new_key))
                return out
            if isinstance(node, list):
                return [walk(item, (*tokens, str(i))) for i, item in enumerate(node)]
            return node

        for key in [k for k in record if k not in ("k", "id", "ev", "evf", "rule", "unk", "src", "after")]:
            record[key] = walk(record[key], (key,))
        # pointers that name a renamed key follow it (evf and unk keys, scoped rule citations); not values themselves
        for field in ("evf", "unk"):
            if isinstance(record.get(field), dict):
                record[field] = {self._model_ids(k)[0] if isinstance(k, str) else k: v for k, v in record[field].items()}
        if isinstance(record.get("rule"), list):
            record["rule"] = [self._model_ids(r)[0] if isinstance(r, str) else r for r in record["rule"]]
        if done:
            evf = record.setdefault("evf", {})
            rules = record.setdefault("rule", [])
            floor = "I" if record.get("ev") == "I" else "D"
            for pointer, _rid in done:
                evf[pointer] = "I" if evf.get(pointer) == "I" else floor
                ref = cite(pointer)
                if ref not in rules:
                    rules.append(ref)
            listing = [{"p": pointer, "rule": f"{self.profile}#{rid}"} for pointer, rid in done]
            ext = record.setdefault("ext", {}).setdefault("inspect", {})
            ext["redacted"] = [*ext.get("redacted", []), *listing]
        return done


def observed_model_ids(header: Mapping[str, Any], events: Sequence[Mapping[str, Any]],
                       messages: Iterable[Mapping[str, Any]]) -> list[str]:
    """The model-id strings the unit records in model fields (module docstring, ``model_id`` scope)."""
    raw_ev = header.get("eval")
    ev: Mapping[str, Any] = raw_ev if isinstance(raw_ev, Mapping) else {}
    out: list[Any] = [ev.get("model")]
    roles = ev.get("model_roles")
    if isinstance(roles, Mapping):
        out += [r.get("model") for r in roles.values() if isinstance(r, Mapping)]
    for e in events:
        if e.get("event") == "model":
            out += [e.get("model"), e.get("requested_model")]
            output = e.get("output")
            if isinstance(output, Mapping):
                out.append(output.get("model"))
    out += [m.get("model") for m in messages if isinstance(m, Mapping)]
    return sorted({m for m in out if isinstance(m, str) and m})
