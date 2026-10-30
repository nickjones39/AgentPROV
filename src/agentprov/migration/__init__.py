"""Baseline -> AgentPROV migration support (docs/architecture J; MN M.1.2; layer L7).

``lock``   the frozen baseline lock ``migration/baseline.lock.json`` (J.1.5) and the tree-listing digest (J.1.4)
``gates``  the common gate contract and gates G0, A, B and E (J.3.0-J.3.3, J.3.6); gate D arrives with its CLI
``pipeline`` the v1 -> AER -> view -> compat pipeline behind gates A, B and E
``semdiff`` the semantic-diff map ``prov/compat/semdiff-map.toml``, the edge classifier and the report of gate E (R-33)
``xd``     the expected-differences register ``migration/expected_differences.toml`` of gate C and its checker (J.3.4)
``c6``     the comparer half of gate C6 (old versus new live capture; the producer is the backend project's test)

Nothing here imports a benchmark package or the old ``agentdojo_prov`` package; the old repository is only ever read.
"""
