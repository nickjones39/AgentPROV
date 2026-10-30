"""The AgentDojo adapter family (docs/architecture D.6, D.10.4, D.6.12; MN M.1.2).

The TraceLogger importer: the reader ``dialect`` (every D.6.2 variant is recognised), the mapper ``mapper`` (adapter id
``agentdojo.tracelogger``; ``v0.k11`` since phase 6, ``v1.k14`` and ``v1.k14.incomplete`` since phase 10), the pure
identity resolution ``identity``, the layout templates ``layout``, the family-schema check ``profile``, the quirk-hook
extension point ``quirks`` (source-specific hooks live in ``hooks/``), the profile census ``census``, the source
profiles ``profiles/*.profile.toml``, the closed schemas ``family.schema.json`` and ``ext.schema.json``, the rule
catalogue ``rules/agentdojo.rules.toml`` and the artefact catalogue ``artefacts.toml`` (D.15.5). The capture mapping
(phase 8) is ``capture_reader`` and ``capture_mapper``.

Importing this package imports none of its modules; the registry reaches them through lazy factory strings (D.3.1).
"""
