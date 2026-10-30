"""Referenced raw: ``raw/REFERENCES.json`` and its resolution against in-package pins (docs/architecture HL H.4.3, G.7.5; R-43).

A corpus may reference raw bytes it does not include (licence, size or gate). Its ``REFERENCES.json`` is corpus-supplied and
therefore **untrusted**:

* it is parsed strictly (:func:`parse_references`): a fixed set of keys, closed ``reason`` and ``requires`` vocabularies,
  validated origins, and no member that could carry a command or instruction text (an extra key such as ``fetch`` or
  ``instructions`` is a ``raw.reference.invalid`` error);
* a reference resolves only against a :class:`~agentprov.raw.fetch.Recipe` built from an **in-package** profile pin: same
  kind, repository (or DOI, or dataset), pinned commit or revision, a path inside the pin's paths, and, for downloads, the
  pinned sha256. Anything else is ``raw.reference.unpinned_origin`` and is never contacted;
* fetched bytes are verified by SHA-256 against the reference before they count (``raw.reference.digest``);
* a reference that needs ``hf-gate-acceptance`` or ``authors-permission`` is reported ``unverified``: a gate, licence or
  terms are never accepted on the user's behalf.

The command that obtains a reference is generated at display time by the CLI (:func:`fetch_command_hint`); the file stores
none.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.raw.fetch import FetchError, Fetcher, Recipe
from agentprov.raw.origins import Origin, OriginError

__all__ = [
    "REFERENCES_FORMAT",
    "Reference",
    "ReferencesError",
    "Resolution",
    "fetch_command_hint",
    "parse_references",
    "resolve_reference",
    "select",
    "verify_reference",
]

REFERENCES_FORMAT: Final = "agentprov-raw-references/0.1"
REASONS: Final = frozenset({"licence-no-redistribution", "licence-unclear", "gated", "size"})
REQUIRES: Final = frozenset({"network", "hf-gate-acceptance", "authors-permission", "credentials"})
#: ``requires`` values that mean a human must act first: the reference is reported ``unverified`` and never attempted.
BLOCKING: Final = frozenset({"hf-gate-acceptance", "authors-permission"})
_SHA256_REF: Final = re.compile(r"sha256:[0-9a-f]{64}")
_TOP: Final = frozenset({"format", "objects"})
_OBJECT: Final = frozenset({"sha256", "bytes", "media_type", "origins", "reason", "requires"})


class ReferencesError(AgentProvError):
    """``REFERENCES.json`` is malformed (``raw.reference.invalid``; exit 1)."""

    code = "raw.reference.invalid"
    exit_code = 1


@dataclass(frozen=True, slots=True)
class Reference:
    """One referenced object: its digest and size, the origins that can supply it, and why it is not included."""

    sha256: str  # 64 hex
    bytes: int
    media_type: str | None
    origins: tuple[Origin, ...]
    reason: str
    requires: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return bool(BLOCKING & set(self.requires))


def parse_references(data: bytes, limits: IngestLimits | None = None) -> list[Reference]:
    """Parse ``REFERENCES.json`` from untrusted bytes. Sorted by digest; duplicates are an error."""
    try:
        doc = strict_json_loads(data, limits)
    except IngestError as exc:
        raise ReferencesError(f"REFERENCES.json is not strict JSON ({exc.code})") from None
    if not isinstance(doc, dict) or set(doc) != _TOP or doc.get("format") != REFERENCES_FORMAT:
        raise ReferencesError("REFERENCES.json has exactly 'format' and 'objects' (no instructions or commands are stored)")
    objects = doc["objects"]
    if not isinstance(objects, list):
        raise ReferencesError("'objects' must be an array")
    out: dict[str, Reference] = {}
    for item in objects:
        if not isinstance(item, dict) or not {"sha256", "bytes", "origins", "reason"} <= set(item) or set(item) - _OBJECT:
            raise ReferencesError("a reference has sha256, bytes, origins, reason (and optionally media_type, requires) and nothing else")
        ref = item["sha256"]
        size = item["bytes"]
        if not isinstance(ref, str) or _SHA256_REF.fullmatch(ref) is None:
            raise ReferencesError("a reference sha256 is 'sha256:<64 hex>'")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ReferencesError("a reference size is a non-negative integer")
        media = item.get("media_type")
        if media is not None and (not isinstance(media, str) or not media or len(media) > 255):
            raise ReferencesError("media_type must be a short string")
        reason = item["reason"]
        if not isinstance(reason, str) or reason not in REASONS:  # a str first: [] or {} is unhashable (#10)
            raise ReferencesError("reason is not in the closed list")
        requires = item.get("requires", [])
        if not isinstance(requires, list) or not all(isinstance(r, str) and r in REQUIRES for r in requires):
            raise ReferencesError("requires is not a subset of the closed list")
        raw_origins = item["origins"]
        if not isinstance(raw_origins, list) or not raw_origins:
            raise ReferencesError("a reference needs at least one origin")
        try:
            origins = tuple(Origin.from_json(o) for o in raw_origins)
        except OriginError:
            raise ReferencesError("a reference origin is malformed") from None
        digest = ref[7:]
        if digest in out:
            raise ReferencesError("a digest is referenced twice")
        out[digest] = Reference(digest, size, media, origins, reason, tuple(sorted(set(requires))))
    return [out[k] for k in sorted(out)]


@dataclass(frozen=True, slots=True)
class Resolution:
    """How a reference resolves: ``resolved`` (a recipe and the origin that matched), ``unpinned`` or ``blocked``."""

    reference: Reference
    status: str  # "resolved" | "unpinned" | "blocked"
    recipe: Recipe | None = None
    origin: Origin | None = None

    @property
    def code(self) -> str | None:
        if self.status == "unpinned":
            return "raw.reference.unpinned_origin"
        return None


def _git_match(recipe: Recipe, origin: Origin) -> bool:
    d = origin.data
    if recipe.kind != "git" or recipe.repo != d["repo"] or recipe.commit != d["commit"]:
        return False
    path = str(d["path"])
    # A pin path is a git pathspec (``Fetcher.git_tree``): the path itself or anything below it as a directory, with or
    # without a trailing slash. Sibling lookalikes ("logsX/..." under "logs") stay unpinned.
    return not recipe.paths or any(path == p or path.startswith(p.rstrip("/") + "/") for p in recipe.paths)


def _match(recipe: Recipe, origin: Origin, ref: Reference) -> bool:
    d = origin.data
    if origin.kind == "git":
        return _git_match(recipe, origin)
    if recipe.sha256 is not None and recipe.sha256 != ref.sha256:
        return False
    if origin.kind == "zenodo":
        return recipe.kind == "zenodo" and recipe.doi == d["doi"] and recipe.file == d["file"]
    if origin.kind == "hf":
        return recipe.kind == "hf" and recipe.repo == d["repo"] and recipe.revision == d["revision"] and recipe.file == d["path"]
    if origin.kind == "url":
        return recipe.kind == "url" and recipe.url == d["url"] and recipe.sha256 == ref.sha256
    return False


def resolve_reference(ref: Reference, recipes: Iterable[Recipe]) -> Resolution:
    """Match ``ref`` against the in-package recipes. Nothing is contacted. First matching (recipe, origin) in order wins."""
    if ref.blocked:
        return Resolution(ref, "blocked")
    pool = list(recipes)
    for origin in ref.origins:
        for recipe in pool:
            if _match(recipe, origin, ref):
                return Resolution(ref, "resolved", recipe, origin)
    return Resolution(ref, "unpinned")


def verify_reference(fetcher: Fetcher, resolution: Resolution) -> bool:
    """Fetch what the resolution names (the network only if the fetcher allows it) and check SHA-256 and size.

    Returns ``True`` when the bytes match the reference. A digest or size difference raises ``raw.reference.digest``; an
    unresolved or blocked resolution raises ``ValueError`` (the caller reports it instead).
    """
    if resolution.status != "resolved" or resolution.recipe is None or resolution.origin is None:
        raise ValueError("only a resolved reference can be verified")
    ref, recipe, origin = resolution.reference, resolution.recipe, resolution.origin
    if recipe.kind == "git":
        narrowed = Recipe(
            kind="git", role=recipe.role, repo=recipe.repo, commit=recipe.commit, paths=(str(origin.data["path"]),)
        )
        fetcher.fetch(narrowed)
        entries, _ = fetcher.git_tree(narrowed)
        match = [e for e in entries if e.path == origin.data["path"] and e.oid == origin.data["blob_sha1"] and e.is_blob]
        if len(match) != 1:
            raise FetchError("the referenced path is not that blob in the pinned tree", code="raw.reference.digest")
        (blob,) = fetcher.iter_git_blobs(narrowed, match)
        if blob.sha256 != ref.sha256 or len(blob.data) != ref.bytes:
            raise FetchError("the fetched blob does not match the reference digest", code="raw.reference.digest")
        return True
    result = fetcher.fetch(recipe)
    if result.sha256 != ref.sha256 or result.bytes != ref.bytes:
        raise FetchError("the fetched file does not match the reference digest", code="raw.reference.digest")
    return True


def fetch_command_hint(corpus_root: str, digest: str) -> str:
    """The help text for obtaining one referenced object, generated at display time and never stored (R-43)."""
    return f"agentprov fetch --corpus {corpus_root} --only sha256:{digest}"


def select(references: Sequence[Reference], only: Iterable[str] | None) -> list[Reference]:
    """The references named by ``--only sha256:HEX`` values (all when ``only`` is empty)."""
    wanted = {o.removeprefix("sha256:") for o in (only or ())}
    return [r for r in references if not wanted or r.sha256 in wanted]
