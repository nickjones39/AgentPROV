"""Checkout entry of the draft-only Zenodo uploader: the tool is :mod:`agentprov_zenodo.draft` (``zenodo/``, D-880).

    uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox|production --check
    uv run python tools/zenodo_draft.py --help
"""

import sys

from agentprov_zenodo.draft import main

if __name__ == "__main__":
    sys.exit(main())
