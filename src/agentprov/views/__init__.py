"""Derived views of AER (docs/architecture C.15; MN M.1.2; layer L2).

A view is a pure, versioned function of an AER (C.15.1). It reads nothing from raw artefacts (AD-02), is never canonical,
and is never stored in a corpus as evidence. Modules:

* :mod:`agentprov.views.transcript_v1`: the AgentDojo-PROV ``transcript/v1`` view (``render``, ``render_converted``,
  ``serialise``), the input of the ``adprov-v2.3-compat`` regression oracle; its field table is
  ``transcript_v1_fields.toml`` (R-30).

The generic transcript view (``transcript.py``, C.15.2) is not built yet.
"""
