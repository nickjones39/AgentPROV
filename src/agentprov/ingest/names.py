"""Names are labels, never paths (docs/architecture G.3.6; A2; SEC-08, SEC-09).

:func:`logical_name` validates an archive member name or an ``--input`` tree label and returns its NFC form. The result
is a *label* recorded in manifests: it is never joined onto a filesystem path. :func:`collision_key` gives the key under
which two names collide on case-insensitive, normalisation-insensitive filesystems (APFS: NFC and NFD names open the same
file, and case is folded).

Rejections raise :class:`~agentprov.errors.IngestError` with ``ingest.archive.traversal`` for traversal forms (absolute
names, drive letters, backslashes, ``..`` components) and ``ingest.name.invalid`` for everything else. The message never
echoes the name.

Bidirectional controls, zero-width characters and other Cf code points are **not** rejected (G.3.6 lists C0/C1 controls
and lone surrogates only); a label that contains them is always shown through ``quote.escape_untrusted``.

``:`` is a label character inside a component (D-91): archive members named after a model tag (``qwen3.6:27b/run.json``)
are accepted, because a label is never joined onto a path (the raw store is content-addressed, a stored object's
extension comes from a closed suffix table, and register subjects and member origins carry the label as a JSON value).
A component that *starts* like a drive (``C:``, ``c:x``) is still a traversal form, in every position.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits

_WINDOWS_INVALID: Final = frozenset('<>"|?*')  # ':' is a label character (D-91); drive forms are refused below
# CON, PRN, AUX, NUL, COM0-9, LPT0-9 including the superscript-digit forms (U+00B9, U+00B2, U+00B3).
_RESERVED: Final = re.compile("^(CON|PRN|AUX|NUL|(COM|LPT)[0-9\u00b9\u00b2\u00b3])$")
_DRIVE: Final = re.compile(r"^[A-Za-z]:")


def _invalid(reason: str) -> IngestError:
    return IngestError("ingest.name.invalid", f"invalid name: {reason}")


def _traversal(reason: str) -> IngestError:
    return IngestError("ingest.archive.traversal", f"traversal form: {reason}")


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8", "surrogatepass"))


def logical_name(raw: str, limits: IngestLimits | None = None, *, portable: bool = True) -> str:
    """Validate ``raw`` and return its NFC logical name (G.3.6).

    ``portable=False`` skips the drive-letter, Windows-invalid-character, trailing-dot/space and reserved-device-name rules. It is for
    labels of local ``--input`` trees, where POSIX file names such as ``a:b`` are legitimate; every other rule still
    applies. In portable mode ``:`` is allowed inside a component (D-91) but no component may start with a drive form
    (``[A-Za-z]:``); :func:`has_colon` tells a caller to record the info finding ``ingest.name.colon``.
    """
    if not isinstance(raw, str):
        raise TypeError("logical_name takes str")
    limits = limits or IngestLimits()
    # Length first, before NFC normalisation (CVE-2026-3276).
    if not raw:
        raise _invalid("empty")
    if _utf8_len(raw) > limits.max_name_bytes:
        raise _invalid("longer than max_name_bytes")
    for ch in raw:
        code = ord(ch)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            raise _invalid("control character")
        if 0xD800 <= code <= 0xDFFF:
            raise _invalid("lone surrogate")
    if raw.startswith("/"):
        raise _traversal("absolute name")
    if portable and _DRIVE.match(raw):
        raise _traversal("drive letter")
    if "\\" in raw:
        raise _traversal("backslash")

    name = unicodedata.normalize("NFC", raw)
    if _utf8_len(name) > limits.max_name_bytes:
        raise _invalid("longer than max_name_bytes after NFC")
    components = name.split("/")
    for part in components:
        if part == "..":
            raise _traversal("'..' component")
    for part in components:
        if part in ("", "."):
            raise _invalid("empty or '.' component")
        if _utf8_len(part) > limits.max_component_bytes:
            raise _invalid("component longer than max_component_bytes")
        if portable:
            if _DRIVE.match(part):
                raise _traversal("drive letter")
            if not _WINDOWS_INVALID.isdisjoint(part):
                raise _invalid("character invalid on Windows")
            if part[-1] in " .":
                raise _invalid("trailing dot or space")
            if _RESERVED.match(part.split(".", 1)[0].rstrip(" ").upper()):
                raise _invalid("reserved device name")
    return name


def has_colon(name: str) -> bool:
    """Whether a validated label contains ``:`` (recorded as the info finding ``ingest.name.colon``, D-91)."""
    return ":" in name


def collision_key(name: str) -> str:
    """``NFC(NFD(casefold(NFD(name))))``: the key under which two logical names collide (G.3.6).

    This is Unicode's canonical caseless match (``NFD(casefold(NFD(x)))``, spelled in NFC). Casefolding is not closed
    under normalisation: ``NFC(casefold(name))`` gave different keys to names a case-insensitive, normalisation-
    insensitive file system (APFS) opens as one file, for example a Greek letter with ypogegrammeni followed by another
    mark (pre-round review D #9)."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", unicodedata.normalize("NFD", name).casefold()))
