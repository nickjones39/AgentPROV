"""The FooBench adapter: the future-framework test of docs/architecture D.12 (DoD Q.3; K.6.4).

FooBench is a **self-authored toy format** (JSONL, one event per line, a hand-off's sub-agent in a second file). It
exists to show that a framework with unseen event types lands with no change to the protected set (everything under
``src/agentprov/`` except this package and its registry entry). It proves coverage of the listed constructs, not
agnosticism (D.12, R-27). It is not a real source.

* :mod:`~agentprov.adapters.foobench.dialect`: :class:`FooJsonlReader` (dialect ``foobench.jsonl``, variant ``v1``);
* :mod:`~agentprov.adapters.foobench.mapper`: :class:`FooMapper` (adapter ``foobench.jsonl``, D.12.2);
* ``profiles/foobench.profile.toml``, ``rules/foobench.rules.toml``, ``artefacts.toml``, ``ext.schema.json`` and
  ``family.schema.json`` (data).

This package imports only the standard library and ``agentprov.{ingest,aer,adapters,errors}`` (D.2.1 boundary test).
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID"]

ADAPTER_ID: Final = "foobench.jsonl"
