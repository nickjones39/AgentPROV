"""Local names, IRIs, statement ids and derivation keys of ``agentprov-prov/0.1`` (EF E.1.2, E.3.4, E.4.1, E.4.2).

Node names are ``L(id)`` (``#`` -> ``-``), derived nodes ``L(id).<q>``; statement names ``<rule-name>.<h16>``; bundle
IRIs carry the derivation key ``dk``. Every hash input is UTF-8 and every function is pure.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, Final

from agentprov.io.canonical import base32_lower_nopad, jcs_bytes

__all__ = [
    "BASE",
    "PREFIXES",
    "derivation_key",
    "h",
    "local",
    "method_slug",
    "prefixes_for",
    "profile_slug",
    "rule_name",
    "rule_slug",
    "statement_name",
]

BASE: Final = "https://w3id.org/agentprov/"
APV_NS: Final = BASE + "ns#"
#: Document-level prefixes (E.4.1). ``x`` and ``xd`` depend on the execution id; ``prov`` and ``xsd`` are never declared.
PREFIXES: Final[Mapping[str, str]] = {
    "apv": APV_NS,
    "raw": BASE + "raw/",
    "sw": BASE + "sw/",
    "rules": BASE + "rules/",
}
#: Derived-node qualifiers (E.1.2): a closed set.
QUALIFIERS: Final = frozenset({"model", "svc", "check", "rule", "out", "pre", "before", "after", "ctx"})


def prefixes_for(ex: str) -> dict[str, str]:
    """The document's ``prefix`` member for execution ``ex``."""
    out = dict(PREFIXES)
    out["x"] = f"{BASE}exec/{ex}#"
    out["xd"] = f"{BASE}exec/{ex}/"
    return out


def local(aer_id: str) -> str:
    """``L(id)``: the AER local id with ``#`` replaced by ``-`` (injective, E.4.2)."""
    return aer_id.replace("#", "-")


def h(text: str, n: int) -> str:
    """First ``n`` characters of lower-case unpadded base32 of SHA-256 over the UTF-8 bytes of ``text``."""
    return base32_lower_nopad(hashlib.sha256(text.encode("utf-8")).digest())[:n]


def rule_name(rule_id: str) -> str:
    """``aprov.use_context@1`` -> ``use_context`` (the statement-name stem, E.1.2)."""
    head = rule_id.split("@", 1)[0]
    return head.split(".", 1)[1] if "." in head else head


def rule_slug(rule_id: str) -> str:
    """``.`` -> ``-`` and ``@`` -> ``-v`` (E.4.2 item 1): ``adprov.context_is_prefix@1`` -> ``adprov-context_is_prefix-v1``."""
    return rule_id.replace(".", "-").replace("@", "-v")


def method_slug(methods: Iterable[str]) -> str:
    """The slug of a method set: the sorted rule slugs joined with ``--``."""
    return "--".join(sorted(rule_slug(m) for m in methods))


def profile_slug(profile_id: str, version: int) -> str:
    """The slug of a semantics profile at a version (E.4.2 item 1): ``agentdojo.suites``, 1 -> ``agentdojo-suites-v1``."""
    return rule_slug(f"{profile_id}@{version}")


def statement_name(dk: str, rule_id: str, args: Iterable[str], discriminator: str = "") -> str:
    """``<rule-name>.<h16>`` with ``h16`` over ``aprov-stmt/1``, ``dk``, the rule id, the argument QNames in PROV
    argument order (absent arguments as ``-``) and the discriminator (E.4.2)."""
    text = "aprov-stmt/1\n" + dk + "\n" + rule_id + "\n" + "\n".join(args) + "\n" + discriminator
    return f"{rule_name(rule_id)}.{h(text, 16)}"


def derivation_key(
    *,
    spec_id: str,
    catalogue_sha256: str,
    aer_digest: str,
    sem_digest: str | None,
    kind: str,
    key: str | None,
    options: Mapping[str, Any],
) -> str:
    """The bundle derivation key ``dk`` (E.3.4): 26 base32 characters."""
    text = (
        "aprov-bundle/1\n"
        + spec_id
        + "\n"
        + catalogue_sha256
        + "\n"
        + aer_digest
        + "\n"
        + (sem_digest or "-")
        + "\n"
        + kind
        + "\n"
        + (key or "-")
        + "\n"
        + jcs_bytes(dict(options)).decode("utf-8")
    )
    return h(text, 26)
