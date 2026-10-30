"""Redaction of third-party workstation account segments in the openhands family's tool output (DECISIONS D-604, D-606,
user-approved 2026-10-21; the D-476 grammar of :mod:`agentprov.adapters.agentdojo.redact`, copied into this family so
that the family owns its rules and its catalogue entry).

A source profile declares a closed table ``[[family.openhands.redact]]`` of rules ``{id, scope, pattern, replacement,
leaf?, note?}``. One scope exists:

``scope = "tool_output"``
    the text of the parts of every ``message`` record of role ``tool`` (``/parts/<i>/text``): the observation content
    the environment returned to the agent (OpenAgentSafety's browser pages, GitLab issues, build logs). D-604: account
    paths inside fetched content are third-party data the agent did not author, so they are redacted there; text the
    model wrote (assistant messages, tool-call arguments, the copies of a command in ``ext.openhands.extras``),
    fixtures and judgements are never touched.

Unlike the D-476 scopes, whose patterns pick whole observed strings, a ``tool_output`` pattern is applied **inside** the
text: every match is replaced, so a pattern that matches only the account segment (a look-behind on ``/home/``) keeps
the path around it. A text the encoder wrote as ``{"$utf16": ...}`` (lone surrogates, C.11.3) is decoded, rewritten
and encoded again. The BF-21 rule of D-476 (an observed string follows into ``ext.lex`` pointers and member names, the
``evf``/``unk`` keys and the scoped citations) has nothing to follow here: a part's text is a value, never a member
name or a pointer token, so no copy of it exists in those places (``ext.lex`` names pointers and member orders only),
and ``ext.lex`` is left as it is, since rewriting a member name there would no longer match the object it orders.

A replacement is literal text plus two placeholders:

``{span12}``
    the first 12 hex digits of SHA-256 over ``<salt> NUL <span>``, where the span is the pattern's named group ``span``
    when it has one, else the whole match. The salt is the profile id. Distinct spans stay distinct, the same span gets
    the same label in every run of the profile, and the label cannot be reversed alone.
``{leaf}``
    the pattern's named group ``leaf`` when it has one; else the match's last path segment when it matches the rule's
    ``leaf`` pattern; else ``?``.

Each redacted pointer is tagged ``D`` (never above its record's class) and cites :data:`RULE`;
``ext.openhands.redacted`` lists ``{p, rule: "<profile id>@<version>#<rule id>"}``. The original and its full digest
are never recorded; source locators keep pointing at the raw field, and raw bytes are never touched (invariant 3). Two
different spans producing one label in a run is a profile defect (:class:`~agentprov.errors.ProfileError`).
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Final

from agentprov.errors import ProfileError

__all__ = ["RULE", "SCOPES", "RedactRule", "Redactor", "parse_redact_rules"]

RULE: Final = "openhands.value_redacted@1"
SCOPES: Final = frozenset({"tool_output"})
NAMESPACE: Final = "openhands"
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")
_ID: Final = re.compile(r"[a-z][a-z0-9_]*")
_KEYS: Final = frozenset({"id", "scope", "pattern", "replacement", "leaf", "note"})


@dataclass(frozen=True, slots=True)
class RedactRule:
    """One ``[[family.openhands.redact]]`` rule."""

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
        if compiled.fullmatch("") is not None or compiled.search("") is not None:
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


class Redactor:
    """The redaction of one run (module docstring)."""

    def __init__(self, profile_id: str, profile_version: int, rules: Sequence[RedactRule]) -> None:
        self.profile = f"{profile_id}@{profile_version}"
        self.salt = profile_id
        self.rules = tuple(r for r in rules if r.scope == "tool_output")
        self._labels: dict[str, str] = {}  # label -> span (in memory only: the collision check)

    @property
    def active(self) -> bool:
        return bool(self.rules)

    def _render(self, rule: RedactRule, match: re.Match[str]) -> str:
        span = match.group("span") if "span" in rule.pattern.groupindex and match.group("span") is not None else match.group(0)
        digest = hashlib.sha256(f"{self.salt}\0{span}".encode("utf-8", "surrogatepass")).hexdigest()[:12]
        if "leaf" in rule.pattern.groupindex:
            leaf = match.group("leaf") or "?"
        else:
            leaf = match.group(0).rstrip("/").rsplit("/", 1)[-1]
            if rule.leaf is None or rule.leaf.fullmatch(leaf) is None:
                leaf = "?"
        label = rule.replacement.replace("{span12}", digest).replace("{leaf}", leaf)
        prior = self._labels.setdefault(label, span)
        if prior != span:
            raise ProfileError(f"redaction rule {rule.id!r} gives one label to two different spans (D-606)")
        return label

    def text(self, value: str) -> tuple[str, str | None]:
        """``value`` with every rule applied in order, and the id of the first rule that changed it (else ``None``)."""
        first: str | None = None
        for rule in self.rules:
            new = rule.pattern.sub(partial(self._render, rule), value)
            if new != value:
                value = new
                first = first or rule.id
        return value, first

    def _encoded(self, value: Any) -> tuple[Any, str | None]:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict) and set(value) == {"$utf16"} and isinstance(value["$utf16"], str):
            raw = base64.b64decode(value["$utf16"]).decode("utf-16-be", "surrogatepass")
            new, rid = self.text(raw)
            if rid is None:
                return value, None
            try:
                new.encode("utf-8")
            except UnicodeEncodeError:
                return {"$utf16": base64.b64encode(new.encode("utf-16-be", "surrogatepass")).decode("ascii")}, rid
            return new, rid
        return value, None

    def apply(self, record: dict[str, Any], cite: Callable[[str], str]) -> list[tuple[str, str]]:
        """Redact one finished record in place; return ``(pointer, rule id)`` per redacted text. ``cite(pointer)`` is the
        mapper's scoped citation of :data:`RULE`. Records other than tool messages are returned unchanged."""
        if not self.active or record.get("k") != "message" or record.get("role") != "tool":
            return []
        done: list[tuple[str, str]] = []
        parts = record.get("parts")
        for i, part in enumerate(parts if isinstance(parts, list) else []):
            if not isinstance(part, dict) or "text" not in part:
                continue
            new, rid = self._encoded(part["text"])
            if rid is not None:
                part["text"] = new
                done.append((f"/parts/{i}/text", rid))
        if not done:
            return []
        evf = record.setdefault("evf", {})
        refs = record.setdefault("rule", [])
        floor = "I" if record.get("ev") == "I" else "D"
        for pointer, _rid in done:
            evf[pointer] = "I" if evf.get(pointer) == "I" else floor
            ref = cite(pointer)
            if ref not in refs:
                refs.append(ref)
        record["evf"] = dict(sorted(evf.items()))
        listing = [{"p": pointer, "rule": f"{self.profile}#{rid}"} for pointer, rid in done]
        ext = record.setdefault("ext", {}).setdefault(NAMESPACE, {})
        ext["redacted"] = [*ext.get("redacted", []), *listing]
        return done
