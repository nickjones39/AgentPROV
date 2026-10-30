"""L0 tier-1 input safety: safe parsing of **untrusted** bytes, before anything else sees them (docs/architecture G.3).

Stdlib only (PyYAML solely in :mod:`agentprov.ingest.yamlsafe`). Nothing is ever extracted to the filesystem, and member
and file names are labels, never paths. Every violation is an :class:`agentprov.errors.IngestError` with a closed
``ingest.<area>.<kind>`` code (G.3.9).

========================  =====================================================================================
module                    purpose
========================  =====================================================================================
``limits``                :class:`IngestLimits` and its defaults (G.3.2)
``loaders``               :func:`strict_json_loads`, :func:`iter_jsonl` (G.3.3)
``archives``              zip, split zip and compressed tar without extraction: pre-check, member gate (G.3.5)
``parts``                 an archive stored as byte parts, read in the declared order (D-243)
``jsonstream``            JSON documents above ``max_json_bytes``, read by streaming declared arrays (D-242)
``streams``               container and codec sniffing; bounded gzip and zstd decoders for tars (G.3.4; D-240)
``names``                 :func:`logical_name`, :func:`collision_key` (G.3.6)
``paths``                 :func:`discover`, :func:`open_evidence`: no-follow local trees (G.3.6)
``quote``                 :func:`quote_untrusted`, :func:`escape_untrusted` (G.8.2)
``yamlsafe``              bounded, alias-free ``safe_load`` (G.3.7; AD-17)
========================  =====================================================================================
"""

from agentprov.ingest.archives import (
    OpenedTar,
    OpenedZip,
    ZipMember,
    ZipPrecheck,
    iter_zip_members,
    open_archive,
    open_split_zip,
    open_zip,
    zip_precheck,
)
from agentprov.ingest.jsonstream import JsonStream, JsonStreamItem, open_json_stream
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import NO_VALUE, iter_jsonl, scan_jsonl, strict_json_loads
from agentprov.ingest.names import collision_key, logical_name
from agentprov.ingest.paths import (
    Discovery,
    DiscoveredFile,
    PathRejection,
    RootHandle,
    discover,
    open_evidence,
    open_root,
)
from agentprov.ingest.quote import escape_untrusted, quote_untrusted
from agentprov.ingest.streams import sniff_codec, sniff_container

__all__ = [
    "NO_VALUE",
    "DiscoveredFile",
    "Discovery",
    "IngestLimits",
    "JsonStream",
    "JsonStreamItem",
    "OpenedTar",
    "OpenedZip",
    "PathRejection",
    "RootHandle",
    "ZipMember",
    "ZipPrecheck",
    "collision_key",
    "discover",
    "escape_untrusted",
    "iter_jsonl",
    "iter_zip_members",
    "logical_name",
    "open_archive",
    "open_evidence",
    "open_json_stream",
    "open_root",
    "open_split_zip",
    "open_zip",
    "quote_untrusted",
    "scan_jsonl",
    "sniff_codec",
    "sniff_container",
    "strict_json_loads",
    "zip_precheck",
]
