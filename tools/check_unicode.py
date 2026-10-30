"""Reject invisible / control Unicode in tracked text files (security spec G.8).

Agent tool layers and pasted corpus text can silently insert format characters (Unicode category Cf:
zero-width, bidi overrides), tag characters (U+E0000-U+E007F) or C0/C1 controls. These can hide
instructions from human reviewers while remaining visible to LLM coding agents. Fixtures under
tests/fixtures/ and tests/golden/ are exempt: they are third-party data, kept byte-identical, and only
ever displayed through agentprov.ingest.quote.
"""

from __future__ import annotations

import subprocess
import sys
import unicodedata

EXEMPT_PREFIXES = ("tests/fixtures/", "tests/golden/")
ALLOWED_CONTROLS = {"\t", "\n", "\r"}
TEXT_SUFFIXES = (".py", ".md", ".toml", ".txt", ".json", ".yaml", ".yml", ".ttl", ".cfg", ".ini", ".sh", ".tex", ".bib")


def bad_chars(text: str) -> list[tuple[int, int, str]]:
    out = []
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        for col, ch in enumerate(line, 1):
            cp = ord(ch)
            cat = unicodedata.category(ch)
            if ch in ALLOWED_CONTROLS:
                continue
            if cat in ("Cc", "Cf", "Cs", "Co") or 0xE0000 <= cp <= 0xE007F or cp in (0x2028, 0x2029):
                out.append((lineno, col, f"U+{cp:04X} {unicodedata.name(ch, cat)}"))
    return out


def main(argv: list[str]) -> int:
    # -z: NUL-separated and unquoted, so tracked paths with spaces or non-ASCII characters are listed exactly.
    files = argv or [p for p in subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                                               check=True).stdout.split("\0") if p]
    status = 0
    for path in files:
        if path.startswith(EXEMPT_PREFIXES) or not path.endswith(TEXT_SUFFIXES):
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{path}: unreadable as UTF-8 ({exc})")
            status = 1
            continue
        for lineno, col, desc in bad_chars(text):
            print(f"{path}:{lineno}:{col}: forbidden character {desc}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
