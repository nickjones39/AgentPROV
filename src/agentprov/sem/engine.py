"""The SEM engine: runs a semantics profile over one AER and seals the annotations (C.14.1-C.14.2; D6).

::

    doc = annotate(aer, profile)          # SemDocument: header, a0 … a<n-1>, seal
    data = dumps_sem(doc)                 # the bytes of sem/<sem_profile_dir>/<ss>/<ex>.sem.jsonl

The caller supplies the profile object (discovery and loading belong to the adapter layer, which may import families;
this module may not). :func:`annotate` numbers the profile's annotations ``a0, a1, …`` in yield order and writes:

* the header (C.14.1) ``{k: "sem", id: "sem", sem: "0.1", ex, aer_digest: "sha256:<AER execution digest>",
  profile: {id, version}, rules: profile.rules, ns: profile.ns, canon: "jcs-rfc8785", hash: "sha256"}``;
* the seal ``{k, id: "seal", n_records, records_sha256}`` with the AER's digest definition (C.11.6): ``n_records``
  counts every line including the seal, ``records_sha256`` is the SHA-256 over every line before it (the SEM digest).

A profile defect raises :class:`SemAnnotationError` with a ``sem.*`` code and never yields a document: something that
is not an :class:`~agentprov.sem.types.Annotation`, a record that fails the validator's record-local checks
(:func:`agentprov.sem.validate.annotation_problems`; a namespaced type must be declared in ``profile.ns``), a value JSON
cannot carry, or a target or premise naming the annotation itself or a later one. The output is a pure function of the
AER and the profile (C.11.7): no time, host, path or package version is written. The full tier-3 check against the AER
and the catalogues is :func:`agentprov.sem.validate.validate_sem_document`, which the write gate runs (K.5.8).

Paths: the corpus layout owns them (:meth:`agentprov.corpus.layout.CorpusLayout.sem_relpath`), sharded with the AER's
shard function; this layer only names the profile directory (:func:`~agentprov.sem.types.sem_profile_dir`).
"""

from __future__ import annotations

import hashlib
from typing import Any, Final

from agentprov.aer.canon import CanonError, dumps_line
from agentprov.aer.reader import AerDocument
from agentprov.errors import AgentProvError
from agentprov.sem.types import SEM_VERSION, Annotation, SemanticsProfile, SemDocument
from agentprov.sem.validate import ANN_ID_RE, annotation_problems

__all__ = ["SemAnnotationError", "annotate", "dumps_sem", "sem_header"]

CANON: Final = "jcs-rfc8785"
HASH: Final = "sha256"


class SemAnnotationError(AgentProvError):
    """A semantics profile yielded an annotation the engine cannot write (a profile defect: exit 70).

    ``code`` is the ``sem.*`` code of the first problem; ``index`` the annotation's position. The message carries codes,
    pointers and the index only, never AER or profile text.
    """

    code = "sem.schema"

    def __init__(self, message: str, *, code: str, index: int) -> None:
        super().__init__(message, code=code)
        self.index = index


def sem_header(aer: AerDocument, profile: SemanticsProfile) -> dict[str, Any]:
    """The ``k: "sem"`` header (line 0) for ``profile`` over ``aer`` (C.14.1)."""
    return {
        "k": "sem",
        "id": "sem",
        "sem": SEM_VERSION,
        "ex": aer.ex,
        "aer_digest": f"sha256:{aer.execution_digest}",
        "profile": {"id": profile.id, "version": profile.version},
        "rules": dict(profile.rules),
        "ns": dict(profile.ns),
        "canon": CANON,
        "hash": HASH,
    }


def _forward_refs(annotation: Annotation, index: int) -> list[str]:
    """Pointers of the target and premises that name this annotation or a later one.

    An ``a<n>`` id has no leading zeros, so more digits than ``index`` means a larger number; comparing lengths first
    keeps ``int()`` away from a digit string past its conversion limit.
    """
    refs = [("/target", annotation.target)] + [(f"/premises/{i}/id", p.id) for i, p in enumerate(annotation.premises)]
    digits = len(str(index))
    return [where for where, ref in refs if ANN_ID_RE.fullmatch(ref) is not None
            and (len(ref) - 1 > digits or int(ref[1:]) >= index)]


def annotate(aer: AerDocument, profile: SemanticsProfile) -> SemDocument:
    """Run ``profile`` over ``aer`` and return the sealed document (module docstring)."""
    header = sem_header(aer, profile)
    declared = frozenset(profile.ns)
    try:
        lines = [dumps_line(header)]
    except CanonError as exc:
        raise SemAnnotationError("the profile's rules or ns cannot be canonicalised", code="sem.header", index=-1) from exc
    records: list[dict[str, Any]] = [header]
    for index, annotation in enumerate(profile.annotate(aer)):
        if not isinstance(annotation, Annotation):
            raise SemAnnotationError(f"annotation {index}: not an Annotation", code="sem.schema", index=index)
        if not isinstance(annotation.premises, tuple) or not isinstance(annotation.rule, tuple) or not (
                annotation.span is None or (isinstance(annotation.span, tuple) and len(annotation.span) == 2)):
            raise SemAnnotationError(f"annotation {index}: premises, rule or span has the wrong shape", code="sem.schema",
                                     index=index)
        if not isinstance(annotation.target, str) or not all(isinstance(getattr(p, "id", None), str)
                                                              for p in annotation.premises):
            raise SemAnnotationError(f"annotation {index}: target or premise id is not a string", code="sem.schema",
                                     index=index)
        forward = _forward_refs(annotation, index)
        if forward:
            code = "sem.target.forward" if forward[0] == "/target" else "sem.premise.forward"
            raise SemAnnotationError(f"annotation {index}: {forward[0]} names this or a later annotation", code=code,
                                     index=index)
        try:
            record = annotation.to_record(f"a{index}")
            line = dumps_line(record)
        except (CanonError, AttributeError, TypeError, IndexError, ValueError) as exc:
            raise SemAnnotationError(f"annotation {index}: not representable in JCS", code="sem.value", index=index) from exc
        problems = annotation_problems(record, declared_types=declared)
        if problems:
            code, pointer, detail = problems[0]
            raise SemAnnotationError(f"annotation {index}: {code} at {pointer or '/'} ({detail})", code=code, index=index)
        records.append(record)
        lines.append(line)
    body = b"".join(lines)
    digest = hashlib.sha256(body).hexdigest()
    seal: dict[str, Any] = {"k": "seal", "id": "seal", "n_records": len(records) + 1, "records_sha256": digest}
    return SemDocument(
        header=header,
        records=records,
        seal=seal,
        digest=digest,
        file_sha256=hashlib.sha256(body + dumps_line(seal)).hexdigest(),
    )


def dumps_sem(doc: SemDocument) -> bytes:
    """The bytes of the ``.sem.jsonl`` file of ``doc``: one JCS line per record, then the seal (C.14.1, C.11.1)."""
    return b"".join(dumps_line(record) for record in doc.records) + dumps_line(doc.seal)
