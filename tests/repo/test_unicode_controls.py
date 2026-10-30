"""SEC-13 (K.12.13, G.8.3): ``tools/check_unicode.py`` rejects every listed category and exempts only the fixtures.

Every hostile character is built with ``chr()`` at run time, so this file itself stays clean.
"""

from __future__ import annotations

import importlib.util
import unicodedata
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_unicode", ROOT / "tools" / "check_unicode.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _tool()

#: One code point per rejected class: C0, DEL, C1 (Cc); bidi override, isolate, ZWSP, BOM, soft hyphen (Cf);
#: a private-use point (Co); a tag character; the line and paragraph separators (Zl, Zp).
REJECTED = [0x00, 0x07, 0x1B, 0x7F, 0x85, 0x9B, 0x202E, 0x2066, 0x200B, 0xFEFF, 0x00AD, 0xE000, 0xF8FF, 0xE0041, 0xE007F,
            0x2028, 0x2029]


@pytest.mark.parametrize("cp", REJECTED, ids=[f"U+{cp:04X}" for cp in REJECTED])
def test_sec13_each_listed_category_is_reported(cp: int) -> None:
    text = f"x = 1  # a{chr(cp)}b\n"
    found = TOOL.bad_chars(text)
    assert [(line, col) for line, col, _ in found] == [(1, 11)]
    assert f"U+{cp:04X}" in found[0][2]


def test_sec13_the_rejected_set_covers_every_cc_cf_co_code_point_except_tab_newline_cr() -> None:
    sample = [cp for cp in range(0x10000) if unicodedata.category(chr(cp)) in ("Cc", "Cf", "Co")]
    allowed = {0x09, 0x0A, 0x0D}
    assert all(TOOL.bad_chars(chr(cp)) for cp in sample if cp not in allowed)
    assert all(TOOL.bad_chars(chr(cp)) == [] for cp in allowed)


def test_sec13_ordinary_unicode_text_passes() -> None:
    assert TOOL.bad_chars("caf\u00e9, na\u00efve, \u2192, \u00d7, \u2264, \u65e5\u672c\n\ttab\r\n") == []


def test_sec13_main_fails_on_a_hostile_file_and_exempts_only_fixtures_and_goldens(tmp_path: Path,
                                                                                    monkeypatch: pytest.MonkeyPatch,
                                                                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    hostile = f"print('a{chr(0x202E)}b')\n"
    for rel in ("src/a.py", "tests/fixtures/x/a.py", "tests/golden/a.md", "tests/fixturesX/a.py", "docs/a.md",
                "data/a.bin"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(hostile, encoding="utf-8")
    assert TOOL.main(["tests/fixtures/x/a.py", "tests/golden/a.md", "data/a.bin"]) == 0  # exempt, or not a text suffix
    for rel in ("src/a.py", "tests/fixturesX/a.py", "docs/a.md"):
        assert TOOL.main([rel]) == 1
    out = capsys.readouterr().out
    assert chr(0x202E) not in out and "U+202E" in out  # the report names the code point, never prints it


def test_sec13_a_file_that_is_not_utf8_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_bytes(b"x = '\xff'\n")
    assert TOOL.main(["a.py"]) == 1


def test_sec13_the_tracked_tree_is_clean(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The same check CI runs in ``core`` (and pre-commit runs per file): the tool's ``main`` over every tracked file,
    run in-process from the repository root (the check is about the tree, not the process; a ``uv run`` child cost
    about 13 s of start-up)."""
    import shutil

    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    monkeypatch.chdir(ROOT)
    assert TOOL.main([]) == 0, capsys.readouterr().out[-2000:]



def test_sec13_the_tracked_listing_keeps_paths_with_spaces_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                  capsys: pytest.CaptureFixture[str]) -> None:
    """``git ls-files`` is read NUL-separated, so a tracked path with a space is one path, not two (phase 10d R7)."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    hostile = tmp_path / "dir with space" / "note file.md"
    hostile.parent.mkdir()
    hostile.write_text("bidi " + chr(0x202E) + " here" + chr(10), encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    monkeypatch.chdir(tmp_path)
    assert _tool().main([]) == 1
    out = capsys.readouterr()
    assert "dir with space/note file.md:1:" in out.out + out.err  # the finding names the real path, not a fragment
