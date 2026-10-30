"""Source-specific quirk hooks of the AgentDojo TraceLogger family (docs/architecture D.6.12 item 7).

Each module here defines ``HOOKS: tuple[QuirkHook, ...]`` (:mod:`agentprov.adapters.agentdojo.quirks`); the modules are
discovered by name, in sorted order, by :func:`agentprov.adapters.agentdojo.quirks.hooks`. A module is imported only when
a TraceLogger mapping or a profile check needs the hooks; it must not import a benchmark package (the import-boundary
test covers this package like the rest of the core).

No source-specific quirk ships in phase 10 wave 1: the generic quirks of the AgentDojo harness are implemented by the
mapper itself. Wave 2 adds ``rope.py``, ``agentdyn.py``, ``mandate.py`` and ``survey.py`` here.
"""
