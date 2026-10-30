"""The ``prov``-library PROV-O image of a ``ProvDocument`` as N-Quads, and its parse (EF E.5.4, E.5.5; D-89 step 2,
D-131).

One path, shared by the two readers of the image: the tier-4 round trip (:mod:`agentprov.validate.roundtrip`) checks
it per execution, and the on-demand canonical TriG (:func:`agentprov.prov.serialise.trig.to_trig`) reads its triple
set through it, so the path TriG is produced from is the path tier 4 validates.

:func:`encode_nquads` encodes with ``ProvRDFSerializer.encode_document`` (what ``serialize(format="rdf")`` does) and
writes rdflib's N-Quads; :func:`parse_nquads` parses that text with rdflib's N-Quads parser and re-applies the
encoding's namespace bindings, which N-Quads does not carry. The result depends on the ``prov`` and ``rdflib``
versions (E.5.4(5)). Pure: nothing is read or written here.
"""

from __future__ import annotations

import io
import warnings
from typing import Any

__all__ = ["encode_nquads", "parse_nquads"]


def encode_nquads(document: Any) -> tuple[bytes, list[tuple[str, Any]]]:
    """The document's PROV-O as UTF-8 N-Quads (what ``serialize(format="rdf", rdf_format="nquads")`` writes; bytes, not
    text, so a large image costs one byte per ASCII character) and the namespace bindings of the encoding."""
    from prov.serializers.provrdf import ProvRDFSerializer

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # caveat C4: rdflib DeprecationWarnings on xsd:int
        encoded = ProvRDFSerializer(document).encode_document(document)
        buffer = io.BytesIO()
        encoded.serialize(buffer, format="nquads")
        return buffer.getvalue(), list(encoded.namespaces())


def parse_nquads(nquads: bytes, bindings: list[tuple[str, Any]]) -> Any:
    """The parsed image (an ``rdflib.Dataset``), with the encoding's namespace bindings: N-Quads carries no prefixes, and
    the ``prov`` decoder names each IRI by the graph's bindings, so a decoded model gets the qualified names a TriG
    text would have given it."""
    import rdflib

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ds = rdflib.Dataset()
        ds.parse(data=nquads, format="nquads")
        for prefix, uri in bindings:
            ds.bind(prefix, uri, override=False)
    return ds
