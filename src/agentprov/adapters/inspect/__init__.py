"""The Inspect AI ``.eval`` adapter family (docs/architecture D.9; MN M.1.2; layer L4).

* :mod:`~agentprov.adapters.inspect.dialect`: :class:`InspectEvalReader` (dialect ``inspect.eval``, variant ``v2``;
  container sniffing, member-object parsing and the per-container unit plan, D.9.1);
* :mod:`~agentprov.adapters.inspect.mapper`: :class:`InspectEvalMapper` (adapter ``inspect.eval``, D.9.2);
* ``profiles/survey-agentharm.profile.toml``, ``rules/inspect.rules.toml``, ``artefacts.toml``, ``ext.schema.json`` and
  ``family.schema.json`` (data).

This package imports no other adapter family and no ``inspect_ai`` code (M.5.2(2), D.13.1).
"""
