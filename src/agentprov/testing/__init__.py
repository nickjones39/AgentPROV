"""Core-only test support (docs/architecture K.3.2; MN M.1.2): the side layer of M.5.1.

``agentprov.testing`` may import L0-L6 only and may be imported only by ``tests/`` and ``tools/`` (enforced by
``tests/boundary/test_import_boundary.py``). It is never installed in a backend environment and never imported by
runtime code. Modules are imported explicitly (``from agentprov.testing import golden``); this package imports nothing
eagerly.

========================  =====================================================================================
module                    purpose
========================  =====================================================================================
``golden``                golden index loader and byte-comparison helpers with the R-42 output rules (K.3.2)
``sem_v23``               per-element comparison of SEM labels with the frozen v2.3 compat graph (gate D, EF E.8.4)
``projections``           ``common_projection(aer_records)``: the comparable view of the differential tests (K.9.1)
``fs_guard``              snapshot a tree (kinds, modes, inodes, mtimes, sizes, sha256) and fail if it changed (K.3.2)
========================  =====================================================================================

The other K.3.2 modules (``netguard``, ``inference6``) arrive with their features.
"""
