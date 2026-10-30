"""Redaction of listed third-party workstation account paths in the dtap family's AERs (DECISIONS D-607, user decision
2026-10-21: a labels allowlist; the agentdojo family's D-476 grammar, applied over every AER string).

A source profile declares a closed table ``[[family.dtap.redact]]`` of rules ``{id, scope, pattern, replacement, labels,
note?}``:

``scope = "all_strings"``
    the only scope: every string of every record the mapper writes (values, object keys, ``ext`` copies and the
    ``ext.lex`` member-order copies), whoever authored it (tool output, harness state, agent text and the final
    response alike; an exception to D-604 recorded in D-607);
``pattern``
    a structural pattern with a named group ``span``: the account segment of an account path (``host_account``), or a
    whole token in any context (``host_account_token``, ``host_account_dotted``: ``ls -l`` owner columns, munged
    directory names, deeper paths; the D-607 census). It names no account;
``labels``
    the allowlist: 12-hex labels (``{span12}`` below) of the accounts to redact. A match whose label is not listed is left
    as it is, so benchmark and model content with other account names is never touched. Git holds only these labels,
    which an AER would carry anyway, never a name;
``replacement``
    literal text plus the placeholder ``{span12}``: the first 12 hex digits of SHA-256 over ``<salt> NUL <span>``, the
    salt being the profile id (the construction of D-476's ``{span12}``, :func:`span_label`). It takes the place of the
    ``span`` group only; the rest of the match (``/home/``, ``C:\\Users\\``) and whatever follows stay.

Pointers are redacted token by token (each JSON-Pointer token unescaped, redacted as a string, escaped again), so a
renamed object key and the ``evf``/``unk`` keys, scoped rule citations and ``ext.lex`` pointers that name it stay in step;
a pointer's own ``/`` never joins two tokens into a path. Source locators (``src``) keep pointing at the raw field, and the
raw bytes are never touched (invariant 3; D-186 (c)); the generated members (``k``, ``id``, ``ev``, ``by``, ``after``)
hold no copied value.

Each redacted pointer is tagged ``D`` (never above its record's class) and cites :data:`RULE`; ``ext.dtap.redacted``
lists ``{p, rule: "<profile id>@<version>#<rule id>"}``. The original and its full digest are never recorded. Two
different spans giving one listed label is a profile defect (:class:`~agentprov.errors.ProfileError`).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Final

from agentprov.aer.canon import pointer_escape
from agentprov.errors import ProfileError

__all__ = ["ISSUE", "NAMESPACE", "RULE", "SCOPES", "RedactRule", "Redactor", "parse_redact_rules", "span_label"]

RULE: Final = "dtap.value_redacted@1"
ISSUE: Final = "dtap.value_redacted"
NAMESPACE: Final = "dtap"
SCOPES: Final = frozenset({"all_strings"})
_PLACEHOLDER: Final = re.compile(r"\{([^{}]*)\}")
_ID: Final = re.compile(r"[a-z][a-z0-9_]*")
_LABEL: Final = re.compile(r"[0-9a-f]{12}")
_KEYS: Final = frozenset({"id", "scope", "pattern", "replacement", "labels", "note"})
#: Record members that hold no copied value (generated ids, classes and edges) or point at the raw field (``src``).
_SKIP: Final = frozenset({"k", "id", "ev", "by", "after", "src"})
#: Record members whose keys (``evf``, ``unk``) or entries (``rule``) are pointers into the record.
_POINTERS: Final = frozenset({"evf", "unk", "rule"})


def span_label(span: str, *, salt: str) -> str:
    """The ``{span12}`` label of one account segment: SHA-256 over ``<salt> NUL <span>``, first 12 hex digits (D-476)."""
    return hashlib.sha256(f"{salt}\0{span}".encode("utf-8", "surrogatepass")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class RedactRule:
    """One ``[[family.dtap.redact]]`` rule."""

    id: str
    scope: str
    pattern: re.Pattern[str]
    replacement: str
    labels: frozenset[str]


def parse_redact_rules(entries: Iterable[Any], where: str) -> tuple[RedactRule, ...]:
    """The profile's redaction rules; :class:`ProfileError` for an unknown key or scope, a pattern that does not compile,
    has no ``span`` group or can match the empty string, a duplicate id, a replacement with a placeholder other than
    ``{span12}`` (or none), or a label that is not 12 lower-case hex digits or is listed twice."""
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
        except (re.error, TypeError) as exc:
            raise ProfileError(f"{at}: the pattern does not compile ({exc})") from None
        if "span" not in compiled.groupindex:
            raise ProfileError(f"{at}: the pattern has no (?P<span>...) group")
        if compiled.fullmatch("") is not None:
            raise ProfileError(f"{at}: the pattern matches the empty string")
        names = _PLACEHOLDER.findall(replacement)
        if not names or any(n != "span12" for n in names):
            raise ProfileError(f"{at}: the replacement is literal text with the placeholder {{span12}}")
        if "{" in _PLACEHOLDER.sub("", replacement) or "}" in _PLACEHOLDER.sub("", replacement):
            raise ProfileError(f"{at}: an unbalanced brace in the replacement")
        labels = entry.get("labels")
        if not isinstance(labels, (list, tuple)) or not all(isinstance(x, str) and _LABEL.fullmatch(x) for x in labels) \
                or len(set(labels)) != len(labels):
            raise ProfileError(f"{at}: labels is a list of distinct 12-hex labels")
        out.append(RedactRule(rid, str(scope), compiled, replacement, frozenset(labels)))
    return tuple(out)


class Redactor:
    """The redaction of one unit's records (module docstring)."""

    def __init__(self, profile_id: str, profile_version: int, rules: Sequence[RedactRule]) -> None:
        self.profile = f"{profile_id}@{profile_version}"
        self.salt = profile_id
        self.rules = tuple(r for r in rules if r.labels)
        self._spans: dict[str, str] = {}  # label -> span (in memory only: the collision check)
        self._labels: dict[str, str] = {}  # span -> label (a word rule meets the same tokens many times)

    @property
    def active(self) -> bool:
        return bool(self.rules)

    def _sub(self, rule: RedactRule, match: re.Match[str]) -> str:
        span = match.group("span")
        if span is None:
            return match.group(0)
        label = self._labels.get(span)
        if label is None:
            label = self._labels[span] = span_label(span, salt=self.salt)
        if label not in rule.labels:
            return match.group(0)
        prior = self._spans.setdefault(label, span)
        if prior != span:
            raise ProfileError(f"redaction rule {rule.id!r} gives one label to two different strings (D-607)")
        start, end = match.start("span") - match.start(), match.end("span") - match.start()
        whole = match.group(0)
        return whole[:start] + rule.replacement.replace("{span12}", label) + whole[end:]

    def text(self, value: str) -> tuple[str, str | None]:
        """``(redacted value, id of the first rule that changed it)``; ``(value, None)`` when nothing is listed."""
        first: str | None = None
        for rule in self.rules:
            new = rule.pattern.sub(partial(self._sub, rule), value)
            if new != value and first is None:
                first = rule.id
            value = new
        return value, first

    def label(self, value: str) -> str:
        """The redacted form of one string as a record would hold it."""
        return self.text(value)[0]

    def pointer(self, value: str) -> str:
        """A JSON Pointer redacted token by token."""
        if not value.startswith("/"):
            return value
        tokens = [t.replace("~1", "/").replace("~0", "~") for t in value[1:].split("/")]
        return "".join("/" + pointer_escape(self.text(t)[0]) for t in tokens)

    def citation(self, value: str) -> str:
        """A scoped rule citation ``<rule>#<pointer>``: the pointer part redacted token by token."""
        rule, sep, ptr = value.partition("#")
        return rule + sep + self.pointer(ptr) if sep else value

    def apply(self, record: dict[str, Any], cite: Callable[[str], str]) -> list[tuple[str, str]]:
        """Redact one finished record in place; return ``(pointer, rule id)`` per redacted value or key. ``cite(pointer)``
        is the mapper's scoped citation of :data:`RULE`."""
        if not self.active:
            return []
        done: list[tuple[str, str]] = []

        def here(tokens: tuple[str, ...]) -> str:
            return "".join("/" + pointer_escape(t) for t in tokens)

        def walk(node: Any, tokens: tuple[str, ...]) -> Any:
            if isinstance(node, str):
                text, rid = self.text(node)
                if rid is not None:
                    done.append((here(tokens), rid))
                return text
            if isinstance(node, dict):
                out: dict[str, Any] = {}
                for key, item in node.items():
                    new_key = key
                    if isinstance(key, str):
                        new_key, rid = self.text(key)
                        if rid is not None:
                            done.append((here((*tokens, new_key)), rid))
                    out[new_key] = walk(item, (*tokens, new_key))
                return out
            if isinstance(node, list):
                return [walk(item, (*tokens, str(i))) for i, item in enumerate(node)]
            return node

        for key in [k for k in record if k not in _SKIP and k not in _POINTERS]:
            if key == "ext" and isinstance(record[key], dict):
                record[key] = self._ext(record[key], walk)
            else:
                record[key] = walk(record[key], (key,))
        for name in ("evf", "unk"):
            if isinstance(record.get(name), dict):
                record[name] = {self.pointer(k) if isinstance(k, str) else k: v for k, v in record[name].items()}
        if isinstance(record.get("rule"), list):
            record["rule"] = [self.citation(r) if isinstance(r, str) else r for r in record["rule"]]
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
            order = record["ext"].get("lex", {}).get("ord", {}).get(f"/ext/{NAMESPACE}")
            if isinstance(order, list) and "redacted" not in order:  # a recorded member order stays a permutation
                order.append("redacted")
        return done

    def _ext(self, ext: dict[str, Any], walk: Callable[[Any, tuple[str, ...]], Any]) -> dict[str, Any]:
        """``ext``: every namespace walked as values, except ``ext.lex``, whose ``ord`` keys and ``flt`` entries are
        pointers (token by token) and whose ``ord`` lists are member names (strings, as the keys they copy)."""
        out: dict[str, Any] = {}
        for ns, value in ext.items():
            if ns != "lex" or not isinstance(value, dict):
                out[ns] = walk(value, ("ext", ns))
                continue
            lex: dict[str, Any] = {}
            for name, item in value.items():
                if name == "ord" and isinstance(item, dict):
                    lex[name] = {self.pointer(p): [self.label(k) if isinstance(k, str) else k for k in keys]
                                 if isinstance(keys, list) else keys for p, keys in item.items()}
                elif name == "flt" and isinstance(item, list):
                    lex[name] = sorted(self.pointer(p) for p in item if isinstance(p, str))
                else:
                    lex[name] = item
            out[ns] = lex
        return out
