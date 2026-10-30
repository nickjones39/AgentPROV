"""``tools/spec_labels.py``: every "D.x.y item N" citation names an item that exists (D-422, design §2.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import spec_labels as sl
from wf_support import commit, write

SPEC = """# D

### D.2.9 Notes

1. **Placement.** a
2. **Layering.** b
3. **Third.** c

### D.6.6 Mapping

**D.6.6.1 Call-to-result linking.** Rules:
1. By id.
2. Positional.

### D.9.5 Resolutions

1. **One.** x
2. **Two.** y

Deviations:

1. **Dev one.** z

### D.15.7 Tests

- a bullet, not a numbered item.
"""


@pytest.fixture
def spec_repo(repo: Path) -> Path:
    write(repo, sl.SPEC, SPEC)
    return repo


def _problems(repo: Path, text: str) -> list[tuple[str, str]]:
    write(repo, "src/cites.py", text)
    commit(repo, "cites")
    return [(p["citation"], p["problem"]) for p in sl.scan(repo, sl.lists_of(SPEC))]


def test_forms_that_resolve(spec_repo: Path) -> None:
    text = ('"""D.2.9 item 3; §D.2.9 items 1–3; D.2.9 items 1 and 2; D.2.9 note item 2; D.6.6.1 item 2;\n'
            'D.2.9(1); D.9.5b item 1; D.2.9 items 1, 2 or 3."""\n')
    assert _problems(spec_repo, text) == []


def test_unresolved_and_ambiguous(spec_repo: Path) -> None:
    text = "# D.2.9 item 4, D.15.7 item 1, D.77 item 1, D.9.5 item 1, D.9.5 item 2\n"
    assert _problems(spec_repo, text) == [
        ("D.2.9 item 4", "the list has no item 4"),
        ("D.15.7 item 1", "no numbered list in that section"),
        ("D.77 item 1", "no numbered list in that section"),
        ("D.9.5 item 1", "ambiguous: D.9.5b also has an item 1"),
    ]


def test_duplicates_cannot_resolve(spec_repo: Path) -> None:
    lists = sl.lists_of(SPEC.replace("3. **Third.** c", "3. **Third.** c\n3. **Other third.** d"))
    assert sl.resolve(lists, "D.2.9", 3) == "duplicate: the list holds this number twice"


def test_fixtures_are_not_scanned(spec_repo: Path) -> None:
    write(spec_repo, "tests/fixtures/x/log.json", '"D.99 item 9"\n')
    assert _problems(spec_repo, "# fine\n") == []


def test_cli_check_and_write(spec_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(spec_repo, "src/cites.py", "# D.2.9 item 9\n")
    commit(spec_repo, "a bad citation")
    assert sl.main(["-C", str(spec_repo), "--check"]) == 1
    assert "src/cites.py:1: D.2.9 item 9: the list has no item 9" in capsys.readouterr().out
    write(spec_repo, "src/cites.py", "# D.2.9 item 2\n")
    commit(spec_repo, "fixed")
    assert sl.main(["-C", str(spec_repo), "--check"]) == 0
    assert sl.main(["-C", str(spec_repo), "--write"]) == 0
    labels = json.loads((spec_repo / sl.LABELS).read_text(encoding="utf-8"))
    assert labels["D.6.6.1 item 2"] == {"list": "D.6.6.1", "section": "D.6.6.1", "line": 13, "title": "positional."}
    assert labels["D.9.5b item 1"]["section"] == "D.9.5"
    assert sl.main(["-C", str(spec_repo), "--check"]) == 0
    write(spec_repo, sl.SPEC, SPEC.replace("3. **Third.** c", "3. **Third, renamed.** c"))
    assert sl.main(["-C", str(spec_repo), "--check"]) == 1
    assert "item-labels.json is stale" in capsys.readouterr().out


def test_expand() -> None:
    assert sl.expand("8–12") == [8, 9, 10, 11, 12]
    assert sl.expand("1, 3 and 5") == [1, 3, 5]
    assert sl.expand("2 to 4 or 7") == [2, 3, 4, 7]
