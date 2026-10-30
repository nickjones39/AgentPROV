"""Redaction of workstation account paths in the agentdojo family's AERs (DECISIONS D-476, user-approved 2026-10-14; the
Inspect family's D-182 design, ``docs/reports/phase10h/redaction-design.md``, applied to this family's logged strings).

A source profile declares a closed table ``[[family.agentdojo.redact]]`` of rules ``{id, scope, pattern, replacement,
leaf?, note?}``. A rule's scope names which logged strings of a unit it may rewrite:

``scope = "model_id"``
    the unit's observed model strings (the results-container ``model``, D-470);
``scope = "pipeline_name"``
    the unit's logged pipeline name (TraceLogger ``pipeline_name``; phase 10j's EnvironmentOptim logs a munged cluster
    home path, D-255).

An observed string the rule's pattern matches is replaced **as a whole string** wherever the AER holds it: in values
(also inside longer strings), as an object key, and in its JSON-Pointer-escaped form, where a pointer names it (``ext.lex``
pointers, ``evf``/``unk`` keys, scoped rule citations; BF-21). Benchmark content and model output are never matched by
pattern, only these exact observed strings, so an exact observed value cannot reach other content by accident.

A replacement is literal text plus two placeholders:

``{span12}``
    the first 12 hex digits of SHA-256 over ``<salt> NUL <span>``, where the span is the pattern's named group ``span``
    when it has one, else the whole match. The salt is the profile id. Distinct spans stay distinct, the same span gets
    the same label in every log of the profile, and the label cannot be reversed alone.
``{leaf}``
    the pattern's named group ``leaf`` when it has one; else the match's last path segment when it matches the rule's
    ``leaf`` pattern; else ``?``.

Each redacted pointer is tagged ``D`` (never above its record's class) and cites :data:`RULE`; ``ext.rescont.redacted``
lists ``{p, rule: "<profile id>@<version>#<rule id>"}``. The original and its full digest are never recorded; source
locators keep pointing at the raw field, and raw bytes are never touched (invariant 3; D-186 (c)). Two different matched
strings producing one label is a profile defect (:class:`~agentprov.errors.ProfileError`).

:func:`redact_value` is the pure single-value form, for a mapper that needs the redacted label before it builds records
(identity resolution compares the pipeline name with identity-table rows, which list only redacted labels).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from functools import partial
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.aer.canon import pointer_escape
from agentprov.errors import ProfileError

__all__ = ["NAMESPACE", "NAMESPACE_IRI", "RULE", "SCOPES", "RedactRule", "Redactor", "parse_redact_rules", "redact_value"]

RULE: Final = "rescont.value_redacted@1"
NAMESPACE: Final = "rescont"
NAMESPACE_IRI: Final = "https://w3id.org/agentprov/ns/rescont#"
SCOPES: Final = frozenset({"model_id", "pipeline_name"})
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")
_ID: Final = re.compile(r"[a-z][a-z0-9_]*")
_KEYS: Final = frozenset({"id", "scope", "pattern", "replacement", "leaf", "note"})
#: Record members that hold no copied value: never rewritten as values (``evf``/``unk`` keys and rule pointers follow a
#: renamed key separately).
_SKIP: Final = frozenset({"k", "id", "ev", "evf", "rule", "unk", "src", "after"})


@dataclass(frozen=True, slots=True)
class RedactRule:
    """One ``[[family.agentdojo.redact]]`` rule."""

    id: str
    scope: str
    pattern: re.Pattern[str]
    replacement: str
    leaf: re.Pattern[str] | None


def parse_redact_rules(entries: Iterable[Any], where: str) -> tuple[RedactRule, ...]:
    """The profile's redaction rules; :class:`ProfileError` for an unknown key or scope, a pattern that does not compile
    or can match the empty string, a duplicate id, or a replacement with a placeholder other than ``{span12}``/``{leaf}``
    (``{leaf}`` needs a ``leaf`` pattern or a ``(?P<leaf>…)`` group)."""
    out: list[RedactRule] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        at = f"{where} redact[{i}]"
        if not isinstance(entry, Mapping):
            raise ProfileError(f"{at}: a table")
        unknown = set(entry) - _KEYS
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
        has_leaf = leaf is not None or "leaf" in compiled.groupindex
        if any(n not in ("span12", "leaf") for n in names) or ("leaf" in names and not has_leaf):
            raise ProfileError(f"{at}: the replacement uses only literal text, {{span12}} and {{leaf}} (with a leaf pattern "
                               "or a (?P<leaf>...) group)")
        rest = _PLACEHOLDER.sub("", replacement)
        if "{" in rest or "}" in rest:
            raise ProfileError(f"{at}: an unbalanced brace in the replacement")
        out.append(RedactRule(rid, str(scope), compiled, replacement, leaf))
    return tuple(out)


def _render(rule: RedactRule, match: re.Match[str], *, salt: str) -> str:
    """The label of one match. Fails closed (bug pass NF-11): a zero-width match redacts nothing, and a label that still
    holds the matched span is no redaction, so both are profile defects, never a silently "redacted" pointer."""
    if match.group(0) == "":
        raise ProfileError(f"redaction rule {rule.id!r}: a zero-width match redacts nothing (lookarounds, \\b)")
    span = match.group("span") if "span" in rule.pattern.groupindex and match.group("span") is not None else match.group(0)
    digest = hashlib.sha256(f"{salt}\0{span}".encode("utf-8", "surrogatepass")).hexdigest()[:12]
    if "leaf" in rule.pattern.groupindex:
        leaf = match.group("leaf") or "?"
    else:
        leaf = match.group(0).rstrip("/").rsplit("/", 1)[-1]
        if rule.leaf is None or rule.leaf.fullmatch(leaf) is None or span in leaf:  # a slashless value is all span
            leaf = "?"
    label = rule.replacement.replace("{span12}", digest).replace("{leaf}", leaf)
    if span in label:
        raise ProfileError(f"redaction rule {rule.id!r}: its label still holds the matched span")
    return label


def redact_value(rules: Sequence[RedactRule], scope: str, value: str, *, salt: str) -> tuple[str, str | None]:
    """The redacted form of one observed ``value`` of ``scope``: ``(label, rule id)`` under the first rule of that scope
    whose pattern matches, else ``(value, None)``. Pure; the label is the one :class:`Redactor` writes into the AER."""
    if scope not in SCOPES:
        raise ValueError(f"unknown redaction scope {scope!r}")
    for rule in rules:
        if rule.scope != scope:
            continue
        label = rule.pattern.sub(partial(_render, rule, salt=salt), value)
        if label != value:
            return label, rule.id
    return value, None


class Redactor:
    """The redaction of one unit (module docstring). ``observed`` maps a scope to the unit's logged strings of it."""

    def __init__(self, profile_id: str, profile_version: int, rules: Sequence[RedactRule],
                 observed: Mapping[str, Iterable[str]]) -> None:
        self.profile = f"{profile_id}@{profile_version}"
        self.salt = profile_id
        self.rules = tuple(rules)
        labels: dict[str, str] = {}  # label -> original (in memory only: the collision check)
        found: dict[str, tuple[str, str]] = {}
        for scope, values in sorted(observed.items()):
            for value in sorted({v for v in values if isinstance(v, str) and v}, key=lambda v: (-len(v), v)):
                label, rid = redact_value(self.rules, scope, value, salt=self.salt)
                if rid is None or value in found:
                    continue
                prior = labels.setdefault(label, value)
                if prior != value:
                    raise ProfileError(f"redaction rule {rid!r} gives one label to two different strings (D-476)")
                found[value] = (label, rid)
                escaped = pointer_escape(value)
                if escaped != value:  # the value inside a JSON Pointer (BF-21)
                    found[escaped] = (pointer_escape(label), rid)
        #: observed string -> (label, rule id), longest first so that a longer string wins inside another
        self.ids: dict[str, tuple[str, str]] = dict(sorted(found.items(), key=lambda kv: (-len(kv[0]), kv[0])))

    @property
    def active(self) -> bool:
        return bool(self.ids)

    def label(self, value: str) -> str:
        """The redacted form of one string as it would appear in a record (identity unless it holds an observed string)."""
        return self._replace(value)[0]

    def _replace(self, text: str) -> tuple[str, list[str]]:
        used: list[str] = []
        for original, (label, rid) in self.ids.items():
            if original in text:
                text = text.replace(original, label)
                used.append(rid)
        return text, used

    def apply(self, record: dict[str, Any], cite: Callable[[str], str]) -> list[tuple[str, str]]:
        """Redact one finished record in place; return ``(pointer, rule id)`` per redacted value or key. ``cite(pointer)`` is
        the mapper's scoped citation of :data:`RULE`."""
        if not self.active:
            return []
        done: list[tuple[str, str]] = []

        def walk(node: Any, tokens: tuple[str, ...]) -> Any:
            if isinstance(node, dict) and set(node) == {"$utf16"} and isinstance(node["$utf16"], str):
                # bug pass NF-10: a string with a lone surrogate is stored as UTF-16BE in base64 (C.11.4); decode it,
                # redact, and re-encode, so an observed string cannot survive in encoded form
                try:
                    decoded = base64.b64decode(node["$utf16"], validate=True).decode("utf-16-be", "surrogatepass")
                except (binascii.Error, UnicodeDecodeError, ValueError):
                    return node
                text, used = self._replace(decoded)
                if not used:
                    return node
                done.append(("".join("/" + pointer_escape(t) for t in tokens), used[0]))
                return {"$utf16": base64.b64encode(text.encode("utf-16-be", "surrogatepass")).decode("ascii")}
            if isinstance(node, str):
                text, used = self._replace(node)
                if used:
                    done.append(("".join("/" + pointer_escape(t) for t in tokens), used[0]))
                return text
            if isinstance(node, dict):
                out: dict[str, Any] = {}
                for key, item in node.items():
                    new_key = key
                    if isinstance(key, str):  # BF-21: an observed string as an object key
                        new_key, used = self._replace(key)
                        if used:
                            done.append(("".join("/" + pointer_escape(t) for t in (*tokens, new_key)), used[0]))
                    out[new_key] = walk(item, (*tokens, new_key))
                return out
            if isinstance(node, list):
                return [walk(item, (*tokens, str(i))) for i, item in enumerate(node)]
            return node

        for key in [k for k in record if k not in _SKIP]:
            record[key] = walk(record[key], (key,))
        # pointers that name a renamed key follow it: evf and unk keys, scoped rule citations (never values themselves)
        for name in ("evf", "unk"):
            if isinstance(record.get(name), dict):
                record[name] = {self._replace(k)[0] if isinstance(k, str) else k: v for k, v in record[name].items()}
        if isinstance(record.get("rule"), list):
            record["rule"] = [self._replace(r)[0] if isinstance(r, str) else r for r in record["rule"]]
        if done:
            evf = record.setdefault("evf", {})
            rules = record.setdefault("rule", [])
            floor = "I" if record.get("ev") == "I" else "D"
            for pointer, _rid in done:
                evf[pointer] = "I" if evf.get(pointer) == "I" else floor
                ref = cite(pointer)
                if ref not in rules:
                    rules.append(ref)
            record["evf"] = dict(sorted(evf.items()))
            listing = [{"p": pointer, "rule": f"{self.profile}#{rid}"} for pointer, rid in done]
            ext = record.setdefault("ext", {}).setdefault(NAMESPACE, {})
            ext["redacted"] = [*ext.get("redacted", []), *listing]
        return done
