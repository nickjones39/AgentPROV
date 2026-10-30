"""Identifiers of AER: execution ids, local ids, part ids and instance IRIs (C.4).

The execution id of an import is one pure function, :func:`import_execution_id` (AD-04, C.4.1)::

    mapping_id = adapter.id + "/" + profile.id
    preimage   = b"aer-ex/1\\n" + mapping_id + b"\\n" + artefact_sha256_hex + b"\\n" + JCS(loc)
    ex         = "ex_" + lower(base32_nopad(SHA-256(preimage)))[0:26]

(26 characters of the full 32-byte digest; the "first 16 bytes" variant of the trace-format sketch differs in the
last character and is not used.)
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from agentprov.io.canonical import base32_lower_nopad, is_sha256_hex, jcs_bytes, sha256_hex

__all__ = [
    "EXECUTION_ID_RE",
    "FIXED_IDS",
    "IRI_BASE",
    "LOCAL_ID_PREFIXES",
    "LOCAL_ID_RE",
    "PART_ID_RE",
    "RESERVED_LOCAL_NAMES",
    "UUID7_RE",
    "canonical_key_loc",
    "import_execution_id",
    "instance_iri",
    "is_local_id",
    "is_part_id",
    "is_ref_id",
    "live_execution_id",
    "mapping_id",
    "part_id",
    "shard",
    "split_part_id",
]

#: Local id grammar (C.4.2). ``a<n>`` is reserved for the raw-artefact ids of ``execution.artifacts`` and
#: ``as`` is reserved by EF E.4.2, so neither is a record id (keeps header-artefact and ``artefact``-record ids
#: disjoint, K.5.1 item 7).
LOCAL_ID_RE: Final = re.compile(r"(?!a(?:0|[1-9][0-9]*)$)(?!as$)[a-z][a-z0-9_]{0,31}")
PART_ID_RE: Final = re.compile(r"([a-z][a-z0-9_]{0,31})#(0|[1-9][0-9]*)")
#: Syntax of a reference to a record or part (kind and existence are checked by the validator).
_REF_ID_RE: Final = re.compile(r"[a-z][a-z0-9_]{0,31}(?:#(?:0|[1-9][0-9]*))?")
EXECUTION_ID_RE: Final = re.compile(
    r"ex_(?:[a-z2-7]{26}|[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
)
UUID7_RE: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
#: Names that may be used as local ids only by their own record (C.4.2); ``as`` is never an id.
FIXED_IDS: Final = {"execution": "exec", "seal": "seal"}
RESERVED_LOCAL_NAMES: Final = frozenset({"exec", "as"})
IRI_BASE: Final = "https://w3id.org/agentprov/exec/"

#: Prefix grammar per record kind (C.4.2 table), as regular-expression sources. The table is read by the tests;
#: the validator enforces only the two rows that keep id spaces disjoint (``activity`` and ``artefact``) because
#: actors, scopes and secondary message threads use profile-defined names.
LOCAL_ID_PREFIXES: Final[Mapping[str, str]] = {
    "message": "m",
    "model_call": "mc",
    "tool_execution": "te",
    "decision": "dc",
    "state_change": "st",
    "fixture": "fx",
    "judgement": "j",
    "activity": "ac",
    "artefact": "af",
}


def is_local_id(value: object) -> bool:
    return isinstance(value, str) and LOCAL_ID_RE.fullmatch(value) is not None


def is_part_id(value: object) -> bool:
    return isinstance(value, str) and PART_ID_RE.fullmatch(value) is not None


def is_ref_id(value: object) -> bool:
    """Syntax of a reference target: a local id, ``exec``/``seal``-style fixed names, or a part id."""
    return isinstance(value, str) and _REF_ID_RE.fullmatch(value) is not None


def part_id(message_id: str, k: int) -> str:
    """``<message id>#<k>`` (C.4.2); ``k`` is the 0-based part index."""
    if k < 0:
        raise ValueError("part index must be >= 0")
    return f"{message_id}#{k}"


def split_part_id(value: str) -> tuple[str, int]:
    """``("m2", 1)`` for ``"m2#1"``; ``ValueError`` when ``value`` is not a part id.

    An ordinal of more than 18 digits is out of range (no message has that many parts, and past 4300 digits ``int()``
    itself refuses): it raises the same error, so callers treat the reference as dangling.
    """
    match = PART_ID_RE.fullmatch(value)
    if match is None or len(match.group(2)) > 18:
        raise ValueError("not a part id")
    return match.group(1), int(match.group(2))


def mapping_id(adapter_id: str, profile_id: str) -> str:
    """The mapping identity ``"<adapter id>/<profile id>"`` (C.4.1, AD-04); versions are excluded."""
    if not adapter_id or not profile_id or "/" in adapter_id or "\n" in adapter_id + profile_id:
        raise ValueError("adapter and profile ids must be non-empty, without newline; adapter id without '/'")
    return f"{adapter_id}/{profile_id}"


def canonical_key_loc(loc: Mapping[str, object]) -> dict[str, object]:
    """Validate and return the canonical key form of ``source_key.loc`` (C.4.1).

    The key form has no ``a``: ``{}`` (whole artefact), ``{"p": <pointer>}`` (``""`` is the JSON root,
    ``"/<i>"`` an array element), ``{"line": <n>}`` (0-based JSONL line, optional ``p``) or ``{"bytes": [s, e]}``
    when neither ``p`` nor ``line`` is present. ``ValueError`` otherwise.
    """
    allowed = {"p", "line", "bytes"}
    if not set(loc) <= allowed:
        raise ValueError("source_key.loc has members outside {p, line, bytes}")
    if "bytes" in loc and ("p" in loc or "line" in loc):
        raise ValueError("bytes never enters the key when p or line is present")
    if "p" in loc and (not isinstance(loc["p"], str) or (loc["p"] and not loc["p"].startswith("/"))):
        raise ValueError("source_key.loc.p must be a JSON Pointer")
    if "line" in loc and (not isinstance(loc["line"], int) or isinstance(loc["line"], bool) or loc["line"] < 0):
        raise ValueError("source_key.loc.line must be a non-negative integer")
    if "bytes" in loc:
        pair = loc["bytes"]
        ok = (
            isinstance(pair, list)
            and len(pair) == 2
            and all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in pair)
            and pair[0] < pair[1]
        )
        if not ok:
            raise ValueError("source_key.loc.bytes must be [start, end_exclusive] with start < end")
    return dict(loc)


def import_execution_id(mapping_id: str, artefact_sha256: str, loc: Mapping[str, object]) -> str:
    """``ex_`` + the first 26 characters of lower-case unpadded base32 of the preimage digest (C.4.1, AD-04).

    ``mapping_id`` is ``"<adapter id>/<profile id>"``; ``artefact_sha256`` the 64-hex digest of the primary
    artefact (for an archive member, of the member object produced by ``expand``); ``loc`` the canonical key
    form of the locator. The preimage components are UTF-8 and the locator is its JCS serialisation.
    """
    if not is_sha256_hex(artefact_sha256):
        raise ValueError("artefact digest must be 64 lower-case hex digits")
    key = canonical_key_loc(loc)
    preimage = (
        b"aer-ex/1\n"
        + mapping_id.encode("utf-8")
        + b"\n"
        + artefact_sha256.encode("ascii")
        + b"\n"
        + jcs_bytes(key)
    )
    digest = bytes.fromhex(sha256_hex(preimage))
    return "ex_" + base32_lower_nopad(digest)[:26]


def live_execution_id(session_uuid7: str) -> str:
    """``"ex_" + session`` for a live execution; the session is a canonical lower-case hyphenated UUIDv7."""
    if UUID7_RE.fullmatch(session_uuid7) is None:
        raise ValueError("session must be a lower-case hyphenated UUIDv7")
    return "ex_" + session_uuid7


def shard(ex: str) -> str:
    """The two-hex-digit shard of an execution id: the first two digits of ``sha256(utf8(ex))`` (C.2.1)."""
    return sha256_hex(ex.encode("utf-8"))[:2]


def instance_iri(ex: str, local_id: str) -> str:
    """``https://w3id.org/agentprov/exec/<ex>#<L(local)>`` with ``#`` mapped to ``-`` (C.4.3).

    ``L`` is injective because local ids never contain ``-``. The ``w3id.org`` base is a placeholder until the
    registration is merged (U-02, Addendum D-3).
    """
    if EXECUTION_ID_RE.fullmatch(ex) is None:
        raise ValueError("not an execution id")
    if not is_ref_id(local_id) and local_id not in {"exec", "seal", "run"}:
        raise ValueError("not a local or part id")
    return f"{IRI_BASE}{ex}#{local_id.replace('#', '-')}"
