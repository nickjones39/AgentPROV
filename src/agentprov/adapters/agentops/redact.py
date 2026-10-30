"""Redaction of third-party account paths in the tool output of agentops AERs (DECISIONS D-608, applying principle
D-604; a family copy of the D-476 grammar of :mod:`agentprov.adapters.agentdojo.redact`).

A source profile declares a closed table ``[[family.agentops.redact]]`` of rules ``{id, scope, pattern, replacement,
leaf?, note?}``. One scope exists:

``scope = "tool_output"``
    the values of the tool messages (``role = "tool"``): each part's ``text`` (a ``run_python`` result string) and
    ``value`` (a structured result, e.g. its ``stdout`` and ``stderr``), strings and object keys at any depth. Model
    text (assistant messages, tool-call arguments, ``final_output``), fixtures, judgements and the harness's run error
    are never touched (D-604: model-authored text stays verbatim; an execution whose derived record still holds the path
    is withheld at sealing, D-235).

Every match of a rule's pattern inside such a string is replaced by the rule's label. A replacement is literal text plus
two placeholders:

``{span12}``
    the first 12 hex digits of SHA-256 over ``<salt> NUL <span>``, where the span is the pattern's named group ``span``
    when it has one, else the whole match. The salt is the profile id: distinct spans stay distinct, the same span gets
    the same label in every run of the profile, and the label cannot be reversed alone.
``{leaf}``
    the pattern's named group ``leaf`` when it has one; else the match's last path segment when it matches the rule's
    ``leaf`` pattern; else ``?``.

The value is decoded first (:func:`agentprov.aer.canon.decode_value` with the record's ``ext.lex`` hints), so a
``$utf16`` or ``$lit`` form is redacted like any other string, and it is encoded again at the same pointer: the
``ext.lex`` entries under that value (member order, integral floats) are rebuilt from the redacted value, so no lexical
copy keeps an original key. Pointers that name a renamed key (``evf`` and ``unk`` keys, scoped rule citations) follow it.
Where the mapper recorded an injected payload at the end of a result (``keep``), only the text before the payload is
redacted, so the payload stays byte-identical to its fixture and its offset is recomputed by the mapper.

Each redacted pointer is tagged ``D`` (never above its record's class) and cites :data:`RULE`; ``ext.agentops.redacted``
lists ``{p, rule: "<profile id>@<version>#<rule id>"}``. The original and its full digest are never recorded; source
locators keep pointing at the raw field, and raw bytes are never touched (invariant 3; the raw objects holding the path
are withheld at object scope by the profile's ``[withhold]`` rule, D-608). Two different spans producing one label is a
profile defect (:class:`~agentprov.errors.ProfileError`).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Final

from agentprov.aer.canon import LexHints, decode_value, encode_value, pointer_escape, pointer_unescape
from agentprov.errors import ProfileError

__all__ = ["NAMESPACE", "RULE", "SCOPES", "RedactRule", "Redactor", "parse_redact_rules"]

RULE: Final = "agentops.value_redacted@1"
NAMESPACE: Final = "agentops"
SCOPES: Final = frozenset({"tool_output"})
#: The part members of a tool message whose values are tool output.
FIELDS: Final = ("text", "value")
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")
_ID: Final = re.compile(r"[a-z][a-z0-9_]*")
_KEYS: Final = frozenset({"id", "scope", "pattern", "replacement", "leaf", "note"})


@dataclass(frozen=True, slots=True)
class RedactRule:
    """One ``[[family.agentops.redact]]`` rule."""

    id: str
    scope: str
    pattern: re.Pattern[str]
    replacement: str
    leaf: re.Pattern[str] | None


def parse_redact_rules(entries: Iterable[Any], where: str) -> tuple[RedactRule, ...]:
    """The profile's redaction rules; :class:`ProfileError` for an unknown key or scope, a pattern that does not compile
    or can match the empty string, a duplicate id, or a replacement with a placeholder other than ``{span12}``/``{leaf}``
    (``{leaf}`` needs a ``leaf`` pattern or a ``(?P<leaf>...)`` group)."""
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


def _tokens(pointer: str) -> list[str]:
    return [pointer_unescape(t) for t in pointer.split("/")[1:]]


def _pointer(tokens: Iterable[str]) -> str:
    return "".join("/" + pointer_escape(t) for t in tokens)


class Redactor:
    """The redaction of one unit's tool output (module docstring)."""

    def __init__(self, profile_id: str, profile_version: int, rules: Sequence[RedactRule]) -> None:
        self.profile = f"{profile_id}@{profile_version}"
        self.salt = profile_id
        self.rules = tuple(r for r in rules if r.scope == "tool_output")
        self._labels: dict[str, str] = {}  # label -> span (in memory only: the collision check)

    @property
    def active(self) -> bool:
        return bool(self.rules)

    def _render(self, rule: RedactRule, match: re.Match[str]) -> str:
        has_span = "span" in rule.pattern.groupindex and match.group("span") is not None
        span = match.group("span") if has_span else match.group(0)
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
            raise ProfileError(f"redaction rule {rule.id!r} gives one label to two different spans (D-608)")
        return label

    def sub(self, text: str) -> tuple[str, str | None]:
        """``text`` with every rule applied in order; the first rule id that changed it, else ``None``."""
        first: str | None = None
        for rule in self.rules:
            new = rule.pattern.sub(partial(self._render, rule), text)
            if new != text:
                text = new
                first = first or rule.id
        return text, first

    def _value(self, value: object, tokens: tuple[str, ...], done: list[tuple[str, str]], keep: int | None) -> object:
        """The decoded ``value`` redacted; ``done`` collects ``(pointer, rule id)`` in encoded coordinates."""
        if isinstance(value, str):
            head, tail = (value[:keep], value[keep:]) if keep is not None else (value, "")
            new, rid = self.sub(head)
            if rid is not None:
                done.append((_pointer(tokens), rid))
            return new + tail
        if isinstance(value, list):
            return [self._value(item, (*tokens, str(i)), done, None) for i, item in enumerate(value)]
        if isinstance(value, dict):
            wrapped = any(isinstance(k, str) and k.startswith("$") for k in value)
            base = (*tokens, "$lit") if wrapped else tokens
            out: dict[str, object] = {}
            for key, item in value.items():
                new_key, rid = self.sub(key) if isinstance(key, str) else (key, None)
                if rid is not None:
                    done.append((_pointer((*base, new_key)), rid))
                if new_key in out:
                    raise ProfileError("a redaction label equals another key of the same tool-output object (D-608)")
                out[new_key] = self._value(item, (*base, new_key), done, None)
            return out
        return value

    def _rename(self, pointer: str, roots: Sequence[str]) -> str:
        """``pointer`` with the tokens below a redacted root redacted as keys are (renamed keys followed)."""
        for root in roots:
            if pointer == root or pointer.startswith(root + "/"):
                head, below = _tokens(root), _tokens(pointer)[len(_tokens(root)):]
                return _pointer([*head, *(self.sub(t)[0] for t in below)])
        return pointer

    def apply(self, record: dict[str, Any], cite: Callable[[str], str], keep: Mapping[str, int] | None = None,
              ) -> list[tuple[str, str]]:
        """Redact one finished tool message in place; return ``(pointer, rule id)`` per redacted string or key.
        ``cite(pointer)`` is the mapper's scoped citation of :data:`RULE`; ``keep`` maps a part's ``text`` pointer to the
        offset where a recorded injected payload begins (only the text before it is redacted)."""
        if not self.active or record.get("k") != "message" or record.get("role") != "tool":
            return []
        parts = record.get("parts")
        if not isinstance(parts, list):
            return []
        ext = record.get("ext")
        hints_in = ext.get("lex") if isinstance(ext, dict) else None
        lex = LexHints.from_dict(hints_in if isinstance(hints_in, dict) else None)
        done: list[tuple[str, str]] = []
        roots: list[str] = []
        for n, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            for field in FIELDS:
                if field not in part:
                    continue
                root = _pointer(("parts", str(n), field))
                found: list[tuple[str, str]] = []
                decoded = decode_value(part[field], at=root, lex=lex)
                redacted = self._value(decoded, ("parts", str(n), field), found, (keep or {}).get(root))
                if not found:
                    continue
                fresh = LexHints()
                part[field] = encode_value(redacted, at=root, lex=fresh)
                lex.ord = {p: k for p, k in lex.ord.items() if not (p == root or p.startswith(root + "/"))}
                lex.flt = {p for p in lex.flt if not (p == root or p.startswith(root + "/"))}
                lex.merge(fresh)
                done += found
                roots.append(root)
        if not done:
            return []
        hints = lex.as_dict()
        if hints:
            record.setdefault("ext", {})["lex"] = hints
        elif isinstance(record.get("ext"), dict):
            record["ext"].pop("lex", None)
        for name in ("evf", "unk"):
            if isinstance(record.get(name), dict):
                record[name] = {self._rename(k, roots) if isinstance(k, str) else k: v for k, v in record[name].items()}
        if isinstance(record.get("rule"), list):
            renamed = []
            for ref in record["rule"]:
                if isinstance(ref, str) and "#" in ref:
                    rid, _, pointer = ref.partition("#")
                    ref = f"{rid}#{self._rename(pointer, roots)}"
                renamed.append(ref)
            record["rule"] = renamed
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
        own = record.setdefault("ext", {}).setdefault(NAMESPACE, {})
        own["redacted"] = [*own.get("redacted", []), *listing]
        return done
