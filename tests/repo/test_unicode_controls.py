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

#: One code point per rejected class: C0 (CR included), DEL, C1 (Cc); bidi override, isolate, ZWSP, BOM, soft hyphen
#: (Cf); a private-use point (Co); a tag character; the line and paragraph separators (Zl, Zp); unassigned points and
#: noncharacters (Cn); variation selectors and their supplement; the G.8.3(1) fillers (AU-TWF-1).
REJECTED = [0x00, 0x07, 0x0D, 0x1B, 0x7F, 0x85, 0x9B, 0x202E, 0x2066, 0x200B, 0xFEFF, 0x00AD, 0xE000, 0xF8FF, 0xE0041,
            0xE007F, 0x2028, 0x2029, 0x0378, 0xFFFE, 0xFF00, 0x10FFFF, 0xFE00, 0xFE0F, 0xE0100, 0xE01EF, 0x115F, 0x1160,
            0x3164, 0xFFA0, 0x2800, 0x034F]


@pytest.mark.parametrize("cp", REJECTED, ids=[f"U+{cp:04X}" for cp in REJECTED])
def test_sec13_each_listed_category_is_reported(cp: int) -> None:
    text = f"x = 1  # a{chr(cp)}b\n"
    found = TOOL.bad_chars(text)
    assert [(line, col) for line, col, _ in found] == [(1, 11)]
    assert f"U+{cp:04X}" in found[0][2]


def test_sec13_the_rejected_set_covers_every_listed_category_except_tab_and_newline() -> None:
    sample = [cp for cp in range(0x10000) if unicodedata.category(chr(cp)) in ("Cc", "Cf", "Co", "Cn", "Zl", "Zp")
              and not 0xD800 <= cp <= 0xDFFF]
    sample += [*range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0), 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800, 0x034F]
    allowed = {0x09, 0x0A}
    assert all(TOOL.bad_chars(chr(cp)) for cp in sample if cp not in allowed)
    assert all(TOOL.bad_chars(chr(cp)) == [] for cp in allowed)


def test_sec13_ordinary_unicode_text_passes() -> None:
    assert TOOL.bad_chars("caf\u00e9, na\u00efve, \u2192, \u00d7, \u2264, \u65e5\u672c, \u2764, \uff21\n\ttab\n") == []


def test_sec13_main_fails_on_a_hostile_file_and_exempts_only_fixtures_and_goldens(tmp_path: Path,
                                                                                    monkeypatch: pytest.MonkeyPatch,
                                                                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    hostile = f"print('a{chr(0x202E)}b')\n"
    for rel in ("src/a.py", "tests/fixtures/x/a.py", "tests/golden/a.md", "tests/fixturesX/a.py", "docs/a.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(hostile, encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/a.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\r" + hostile.encode())
    assert TOOL.main(["tests/fixtures/x/a.py", "tests/golden/a.md", "data/a.png"]) == 0  # exempt, or binary (NUL)
    for rel in ("src/a.py", "tests/fixturesX/a.py", "docs/a.md"):
        assert TOOL.main([rel]) == 1
    out = capsys.readouterr().out
    assert chr(0x202E) not in out and "U+202E" in out  # the report names the code point, never prints it


@pytest.mark.parametrize("rel", ["a.ps1", "gui/a.spec", "site/a.js", "site/index.html", "site/a.css", "docs/a.patch",
                                 "CITATION.cff", ".gitignore", ".env.example", "a.jsonl", "a.svg", "Makefile", "LICENSE"])
def test_sec13_main_checks_every_text_file_whatever_its_suffix(rel: str, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-TWF-2: a text file is checked by its content, not a suffix allowlist."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"x a{chr(0x202E)}b\n", encoding="utf-8")
    assert TOOL.main([rel]) == 1


@pytest.mark.parametrize("raw", [b"x = 1\r\n", b"x = 'rm -rf ~'\r# harmless\n", b"x = 1\r"], ids=["crlf", "lone-cr", "cr-eof"])
def test_sec13_main_rejects_cr_read_without_newline_translation(raw: bytes, tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    """AU-TWF-1: the file is read as bytes, so a CR is not turned into LF before the check."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_bytes(raw)
    assert TOOL.main(["a.py"]) == 1
    assert "U+000D" in capsys.readouterr().out


def test_sec13_the_allowlist_exempts_only_the_listed_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """G.8.3(2): an entry names a path and the sha256 of its bytes; once the file changes, it is checked again."""
    import hashlib

    monkeypatch.chdir(tmp_path)
    raw = b"a,b\r\n1,2\r\n"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/record.csv").write_bytes(raw)
    allowlist = tmp_path / "allow.toml"
    allowlist.write_text(f'[[file]]\npath = "docs/record.csv"\nsha256 = "{hashlib.sha256(raw).hexdigest()}"\n'
                         'reason = "a research record kept as exported"\n', encoding="utf-8")
    monkeypatch.setattr(TOOL, "ALLOWLIST", allowlist)
    assert TOOL.main(["docs/record.csv"]) == 0
    (tmp_path / "docs/record.csv").write_bytes(raw + b"3,4\r\n")
    assert TOOL.main(["docs/record.csv"]) == 1
    allowlist.write_text('[[file]]\npath = "docs/record.csv"\nsha256 = "00"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="reason"):
        TOOL.main(["docs/record.csv"])


def test_sec13_the_committed_allowlist_is_well_formed() -> None:
    entries = TOOL.load_allowlist(TOOL.ALLOWLIST)
    assert all(len(digest) == 64 and not path.startswith(TOOL.EXEMPT_PREFIXES) for path, digest in entries.items())


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
