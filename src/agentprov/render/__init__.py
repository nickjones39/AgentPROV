"""PROV graph renders (layer L7; MN N.2.13; AD-10 as ruled; docs/architecture K.5.12).

``agentprov render`` draws selected executions' ``agentprov-prov/0.1`` bundles on demand; nothing is rendered during import
and a render is never written into a corpus. This package is the port of the baseline's ``render_prov_graph``:

* :mod:`~agentprov.render.graph` validates a PROV-JSON document and builds the drawable model, and
  :func:`~agentprov.render.graph.render_prov_graph` writes the DOT text and the images;
* :mod:`~agentprov.render.dot` builds the DOT text with ``pydot`` and runs ``dot -T<fmt>`` (the only process);
* :mod:`~agentprov.render.style` holds the notation, the label grammars and the escaping of untrusted text;
* :mod:`~agentprov.render.source` reads a corpus (index, PROV-JSON) strictly and read-only, and
  :mod:`~agentprov.render.output` keeps the output outside every corpus.

Importing this package needs neither the ``render`` extra nor Graphviz: ``pydot`` is imported inside functions, and a
missing ``pydot`` or ``dot`` is a typed error with exit code 3 (:mod:`~agentprov.render.errors`).
"""

from __future__ import annotations

from agentprov.render.errors import (
    EXTRA_HINT,
    RenderCorpusError,
    RenderEnvironmentError,
    RenderError,
    RenderInputError,
    RenderOutputRefusedError,
    RenderProcessError,
)

__all__ = [
    "EXTRA_HINT",
    "RenderCorpusError",
    "RenderEnvironmentError",
    "RenderError",
    "RenderInputError",
    "RenderOutputRefusedError",
    "RenderProcessError",
]
