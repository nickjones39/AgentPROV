"""Redaction of third-party account paths in the tool output the credleak family copies into AERs (DECISIONS D-605,
applying principle D-604, user decision 2026-10-21; the grammar of D-476, ``agentprov.adapters.agentdojo.redact``,
copied here: families never import each other).

A source profile declares a closed table ``[[family.credleak.redact]]`` of rules ``{id, scope, pattern, replacement,
leaf?, labels?, note?}``. One scope exists:

``scope = "tool_output"``
    the ``output`` of a ``toolCalls[]`` entry, which the mapper copies into the tool result message (``/parts/0/text``
    when it is a string, else ``/parts/0/value``): every string in it and every member name of an object in it. This is
    environment output (D-604): the tool runtime wrote it, not the model.

Model-authored text (the agent's tool-call input, its assistant text) and the scripted user message are never
rewritten: D-604 keeps them verbatim, and the profile's ``[withhold]`` policy decides about an execution that still
holds a path there (D-235).

The pattern is applied to the **source value before it is encoded** (C.11), so every copy the AER holds is the redacted
one: the value itself, a member name, the ``ext.lex`` source-order lists and pointers that name a member, and a string
the encoder wraps as ``$utf16``. Every match is replaced by the rule's replacement, literal text plus two placeholders:

``{span12}``
    the first 12 hex digits of SHA-256 over ``<salt> NUL <span>``, where the span is the pattern's named group ``span``
    when it has one, else the whole match. The salt is the profile id: distinct spans stay distinct, the same span gets
    the same label in every run of the profile, and the label cannot be reversed alone.
``{leaf}``
    the pattern's named group ``leaf`` when it has one; else the match's last path segment when it matches the rule's
    ``leaf`` pattern; else ``?``.

A **labelled** rule (``labels``, a list of 12-hex ``{span12}`` values; the D-607 approach) is structural: its pattern
must have a ``span`` group, only that group is replaced (the rest of the match stays), and only when the span's
``{span12}`` is listed. So a structural pattern (the owner and group columns of an ``ls -l`` line) redacts the listed
accounts only, and the profile names no account: the labels are computed out of band from the data. Any other match is
left as it is and is not counted.

Each redacted pointer is tagged ``D`` and cites :data:`RULE` scoped to it; ``ext.credleak.redacted`` lists
``{p, rule: "<profile id>@<version>#<rule id>"}``; one info issue ``credleak.value_redacted`` per run counts them. The
original and its full digest are never recorded; the source locators keep pointing at the raw field, and raw bytes are
never touched (invariant 3). Two different spans producing one label, or two member names of one object becoming one,
is a profile defect (:class:`~agentprov.errors.ProfileError`).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Final

from agentprov.aer.canon import pointer_escape
from agentprov.errors import ProfileError

__all__ = ["ISSUE", "RULE", "SCOPES", "RedactRule", "Redactor", "parse_redact_rules"]

RULE: Final = "credleak.value_redacted@1"
ISSUE: Final = "credleak.value_redacted"
SCOPES: Final = frozenset({"tool_output"})
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")
_ID: Final = re.compile(r"[a-z][a-z0-9_]*")
_KEYS: Final = frozenset({"id", "scope", "pattern", "replacement", "leaf", "labels", "note"})
_LABEL: Final = re.compile(r"[0-9a-f]{12}")


@dataclass(frozen=True, slots=True)
class RedactRule:
    """One ``[[family.credleak.redact]]`` rule."""

    id: str
    scope: str
    pattern: re.Pattern[str]
    replacement: str
    leaf: re.Pattern[str] | None
    labels: frozenset[str] | None = None


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
        labels = entry.get("labels")
        if labels is not None:
            if (not isinstance(labels, (list, tuple)) or not labels or len(set(labels)) != len(labels)
                    or not all(isinstance(x, str) and _LABEL.fullmatch(x) for x in labels)):
                raise ProfileError(f"{at}: labels is a non-empty list of distinct 12-hex labels")
            if "span" not in compiled.groupindex:
                raise ProfileError(f"{at}: a labelled rule's pattern has a (?P<span>...) group")
        out.append(RedactRule(rid, str(scope), compiled, replacement, leaf,
                              frozenset(labels) if labels is not None else None))
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

    def ref(self, rule_id: str) -> str:
        """The ``ext.credleak.redacted`` rule name: ``<profile id>@<version>#<rule id>``."""
        return f"{self.profile}#{rule_id}"

    def _render(self, rule: RedactRule, match: re.Match[str]) -> str:
        span = match.group("span") if "span" in rule.pattern.groupindex and match.group("span") is not None else match.group(0)
        digest = hashlib.sha256(f"{self.salt}\0{span}".encode("utf-8", "surrogatepass")).hexdigest()[:12]
        if rule.labels is not None and digest not in rule.labels:
            return match.group(0)  # a labelled rule leaves an unlisted account as it is
        if "leaf" in rule.pattern.groupindex:
            leaf = match.group("leaf") or "?"
        else:
            leaf = match.group(0).rstrip("/").rsplit("/", 1)[-1]
            if rule.leaf is None or rule.leaf.fullmatch(leaf) is None:
                leaf = "?"
        label = rule.replacement.replace("{span12}", digest).replace("{leaf}", leaf)
        prior = self._labels.setdefault(label, span)
        if prior != span:
            raise ProfileError(f"redaction rule {rule.id!r} gives one label to two different spans (D-605)")
        if rule.labels is not None:  # only the span is replaced
            start, end = match.start("span") - match.start(), match.end("span") - match.start()
            return match.group(0)[:start] + label + match.group(0)[end:]
        return label

    def text(self, value: str) -> tuple[str, str | None]:
        """``value`` with every rule applied in order, and the first rule that changed it (``None``: unchanged)."""
        first: str | None = None
        for rule in self.rules:
            new = rule.pattern.sub(partial(self._render, rule), value)
            if new != value:
                value = new
                first = first or rule.id
        return value, first

    def tool_output(self, value: object, at: str) -> tuple[object, list[tuple[str, str]]]:
        """The source ``value`` of one tool output with every string and member name redacted, and ``(pointer, rule id)``
        per redacted string or name. ``at`` is the record pointer the encoded value will sit at; pointers follow the
        encoder (C.11.2: an object with a ``$``-prefixed member name is wrapped as ``$lit``). Pure but for the
        collision check."""
        done: list[tuple[str, str]] = []
        if not self.active:
            return value, done

        def walk(node: object, pointer: str) -> object:
            if isinstance(node, str):
                new, rid = self.text(node)
                if rid is not None:
                    done.append((pointer, rid))
                return new
            if isinstance(node, list):
                return [walk(item, f"{pointer}/{i}") for i, item in enumerate(node)]
            if isinstance(node, dict):
                renamed = [(*self.text(key), item) if isinstance(key, str) else (key, None, item)
                           for key, item in node.items()]
                keys = [key for key, _rid, _item in renamed]
                if len(set(keys)) != len(keys):
                    raise ProfileError("a redaction rule turns two member names of one object into one (D-605)")
                base = f"{pointer}/$lit" if any(isinstance(k, str) and k.startswith("$") for k in keys) else pointer
                done.extend((f"{base}/{pointer_escape(key)}", rid) for key, rid, _item in renamed if rid is not None)
                return {key: walk(item, f"{base}/{pointer_escape(key)}") for key, _rid, item in renamed}
            return node

        return walk(value, at), done
