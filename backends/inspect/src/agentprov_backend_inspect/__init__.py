"""AgentPROV live Inspect harness (docs/reports/inspect-harness/design.md; DECISIONS D-660..D-669).

Runs inside a per-benchmark backend environment (``backends/inspect/envs/<benchmark>``). Imports ``inspect_ai`` and the
benchmark package only there, lazily; never imports ``agentprov`` (invariant 7, D.13.3).
"""

__version__ = "0.1.0"
