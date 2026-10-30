"""S7 and D-395: the GUI never reads ``.env``, never passes ``--env-file`` and does not use ``dotenv``. The one allowed
mention is the refusal table entry marked ``# S7: refused`` (the GUI rejects the option when a user types it)."""

from __future__ import annotations

import re

from _ast_support import SRC

PATTERN = re.compile(r"""(['"/\\])\.env\b|dotenv|--env-file""")


def test_no_dotenv_anywhere_in_gui_sources() -> None:
    bad = []
    for path in sorted(SRC.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PATTERN.search(line) and "# S7: refused" not in line:
                bad.append(f"{path.relative_to(SRC)}:{number}")
    assert not bad, "\n".join(bad)
