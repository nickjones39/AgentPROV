"""``python -m agentprov``: the same entry point as the ``agentprov`` console script (MN M.1.2)."""

from __future__ import annotations

from agentprov.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
