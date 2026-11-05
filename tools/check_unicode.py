"""Reject invisible / control Unicode in tracked text files (security spec G.8.3).

Agent tool layers and pasted corpus text can silently insert format characters (Unicode category Cf:
zero-width, bidi overrides), tag characters (U+E0000-U+E007F), variation selectors (which can smuggle hidden bytes),
invisible fillers or C0/C1 controls (a lone CR hides the text before it when the file is printed). These can hide
instructions from human reviewers while remaining visible to LLM coding agents. G.8.3(1) is the rule set: invalid
UTF-8; C0 and C1 controls except TAB and LF; categories Cf, Zl, Zp, Co and Cn; variation selectors; the listed
fillers. Every tracked file is checked unless it is binary (it holds a NUL byte), whatever its suffix.

Files are read as bytes, so CR is never translated away before the check. Exceptions: fixtures under tests/fixtures/
and tests/golden/ are exempt (third-party data, kept byte-identical, only ever displayed through
agentprov.ingest.quote), and tools/unicode_allowlist.toml lists single files by path and sha256 with a reason
(G.8.3(2)); an entry whose digest no longer matches the file exempts nothing.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tomllib
import unicodedata
from pathlib import Path

EXEMPT_PREFIXES = ("tests/fixtures/", "tests/golden/")
ALLOWLIST = Path(__file__).resolve().with_name("unicode_allowlist.toml")
ALLOWED_CONTROLS = {"\t", "\n"}
REJECTED_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
#: G.8.3(1): variation selectors and the invisible fillers (Hangul fillers, Braille blank, combining grapheme joiner).
EXTRA_REJECTED = frozenset({*range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0),
                            0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800, 0x034F})


def bad_chars(text: str) -> list[tuple[int, int, str]]:
    out = []
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        for col, ch in enumerate(line, 1):
            cp = ord(ch)
            cat = unicodedata.category(ch)
            if ch in ALLOWED_CONTROLS:
                continue
            if cat in REJECTED_CATEGORIES or cp in EXTRA_REJECTED or 0xE0000 <= cp <= 0xE007F:
                out.append((lineno, col, f"U+{cp:04X} {unicodedata.name(ch, cat)}"))
    return out


def load_allowlist(path: Path = ALLOWLIST) -> dict[str, str]:
    """``{path: sha256}`` from the allowlist; every entry needs a path, a sha256 and a non-empty reason."""
    if not path.exists():
        return {}
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("file", [])
    allowed = {}
    for entry in entries:
        if not (isinstance(entry.get("path"), str) and isinstance(entry.get("sha256"), str)
                and isinstance(entry.get("reason"), str) and entry["reason"].strip()):
            raise ValueError(f"{path}: every [[file]] entry needs path, sha256 and reason: {entry!r}")
        allowed[entry["path"]] = entry["sha256"]
    return allowed


def main(argv: list[str]) -> int:
    # -z: NUL-separated and unquoted, so tracked paths with spaces or non-ASCII characters are listed exactly.
    files = argv or [p for p in subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                                               check=True).stdout.split("\0") if p]
    allowlist = load_allowlist(ALLOWLIST)
    status = 0
    for path in files:
        if path.startswith(EXEMPT_PREFIXES):
            continue
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            print(f"{path}: unreadable ({exc})")
            status = 1
            continue
        if b"\0" in data:  # binary (images, icons); git's own text heuristic
            continue
        if allowlist.get(path) == hashlib.sha256(data).hexdigest():
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            print(f"{path}: unreadable as UTF-8 ({exc})")
            status = 1
            continue
        for lineno, col, desc in bad_chars(text):
            print(f"{path}:{lineno}:{col}: forbidden character {desc}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
