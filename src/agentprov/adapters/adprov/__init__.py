"""The AgentDojo-PROV ``transcript/v1`` adapter family (docs/architecture D.7; MN M.1.2; layer L4).

* :mod:`~agentprov.adapters.adprov.dialect`: :class:`TranscriptV1Reader` (dialect ``adprov.transcript_v1``, variant
  ``v1``, D.7.2 flags);
* :mod:`~agentprov.adapters.adprov.mapper`: :class:`TranscriptV1Mapper` (adapter ``adprov.transcript_v1``, D.7.3);
* ``profiles/adprov-v1.profile.toml`` and ``rules/adprov.rules.toml`` (data).

The inverse is the view :mod:`agentprov.views.transcript_v1`. This package imports no other adapter family (M.5.2(2)).
"""
