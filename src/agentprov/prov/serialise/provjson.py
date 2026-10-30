"""Canonical bundled PROV-JSON (EF E.5.3): RFC 8785 JCS bytes, UTF-8, no BOM, no trailing newline.

The document is never written through ``prov.ProvDocument.serialize``; JCS fixes key order, whitespace and number
form, so the bytes and their SHA-256 are a function of the document's values alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agentprov.io.canonical import jcs_bytes, sha256_hex

__all__ = ["digest", "dumps"]


def dumps(document: Mapping[str, Any]) -> bytes:
    """The canonical bytes of a PROV-JSON document."""
    return jcs_bytes(dict(document))


def digest(data: bytes) -> str:
    """``sha256:<hex>`` of the canonical bytes."""
    return "sha256:" + sha256_hex(data)
