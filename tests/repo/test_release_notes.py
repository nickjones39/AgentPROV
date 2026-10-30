"""The GitHub Release notes (``docs/release-notes/v<version>.md``; v0.1.0-plan.md section 5, D-944).

* They pass the shared claims lint and the O.1.2 phrases it does not cover, as the landing page does; the coverage
  phrase is the registry-generated one, and live capture is worded as a tested capability (D-991).
* They name the version of ``pyproject.toml``, and every release asset the landing page links to.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from agentprov.adapters.registry import claims

ROOT = Path(__file__).resolve().parents[2]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
NOTES = ROOT / "docs" / "release-notes" / f"v{VERSION}.md"
RELEASES = "https://github.com/nickjones39/AgentPROV/releases/latest/download/"


def _text() -> str:
    return NOTES.read_text(encoding="utf-8")


def _prose() -> str:
    """The text a reader sees: no HTML comment (the fill-in instructions), no fenced command."""
    return re.sub(r"```.*?```", "", re.sub(r"<!--.*?-->", "", _text(), flags=re.S), flags=re.S)


def test_the_notes_pass_the_claims_lint() -> None:
    assert claims.lint_text(NOTES.relative_to(ROOT), _prose()) == []


def test_the_notes_avoid_the_phrases_o12_bans() -> None:
    text = " ".join(_prose().lower().split())
    for phrase in ("ground truth", "independently verifiable", "lossless", "prov-o conformant", "prov-constraints valid",
                   "detection", "detects"):
        assert phrase not in text, phrase
    assert not re.search(r"\bfirst (?:public|open|framework|corpus|corpora|provenance|tool|release)", text)  # O.1.2


def test_coverage_and_live_wording() -> None:
    text = " ".join(_prose().split())
    phrase = claims.coverage_phrase()
    assert phrase is not None and phrase in text
    assert "Live capture works and is tested in v0.1. No live results are claimed" in text  # D-991, U-18


def test_the_notes_name_the_version_and_every_asset_the_site_links_to() -> None:
    text = _text()
    assert next(line for line in text.splitlines() if line.startswith("# ")) == f"# AgentPROV v{VERSION}"
    site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assets = set(re.findall(re.escape(RELEASES) + r"([^\"'#?]+)", site))
    assert f"AgentPROV-{VERSION}-source.tar.gz" in assets  # F-5: never the sdist's case-folded twin
    missing = sorted(a for a in assets if f"`{a}`" not in text)
    assert missing == []
