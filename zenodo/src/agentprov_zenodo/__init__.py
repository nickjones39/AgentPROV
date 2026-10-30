"""AgentPROV's draft-only Zenodo uploader (D-790, D-870, D-880), a distribution of its own (``agentprov-zenodo``).

It lives outside the ``agentprov`` package because HL H.10.1(1) keeps every network library and every upload call out
of ``agentprov.release``, and D-790 keeps the uploader out of the ``agentprov`` command. ``agentprov`` never imports it
(``tests/boundary/test_import_boundary.py``). The tool is :mod:`agentprov_zenodo.draft`; run it as
``python -I -m agentprov_zenodo``, ``agentprov-zenodo-draft`` or, in a checkout, ``tools/zenodo_draft.py``.
"""
