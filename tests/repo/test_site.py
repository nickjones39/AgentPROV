"""The project website's landing page (``site/``; D-1000).

* Its copy passes the shared claims lint (``agentprov.adapters.registry.claims.lint_text``), as the README and the
  datasheets do, plus the O.1.2 phrases the lint does not cover.
* It is self-hosted: no script, stylesheet, image, font or request from another host; no cookie or analytics code.
* The brand files are the brand sources byte for byte; every screenshot has a light and a dark twin and is used.
* The download links are GitHub's stable ``releases/latest/download/<asset>`` URLs for the v0.1.0 plan's asset names.
* The release-day placeholders are listed, so filling them is a deliberate change.
"""

from __future__ import annotations

import importlib.util
import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path

from agentprov.adapters.registry import claims

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
RELEASES = "https://github.com/nickjones39/AgentPROV/releases/latest/download/"
#: The release assets (docs/reports/release/v0.1.0-plan.md: the five bundles, F-5's source archive, the signed sums).
ASSETS = {
    "AgentPROV-macos-arm64.dmg",
    "AgentPROV-windows-x64.zip",
    "AgentPROV-windows-arm64.zip",
    "AgentPROV-linux-x86_64.tar.gz",
    "AgentPROV-linux-aarch64.tar.gz",
    "AgentPROV-0.1.0-source.tar.gz",
    "SHA256SUMS",
    "SHA256SUMS.sig",
}
PLACEHOLDERS = {"paper", "paper-link"}  # software-doi filled 2026-10-30 (release step 5); umbrella-doi, zenodo-link 2026-10-31 (step 9)
BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "div", "section", "article", "figcaption", "pre", "code", "span", "button",
         "title", "desc", "text", "a", "b", "small", "i", "strong", "header", "footer", "nav"}


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.lines: list[str] = []
        self.headings: list[str] = []
        self._skip = 0
        self._heading: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag in ("script", "style"):
            self._skip += 1
        if tag in ("h1", "h2", "h3", "h4"):
            self._heading = []
        if tag in BLOCK:
            self.lines.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip -= 1
        if tag in ("h1", "h2", "h3", "h4") and self._heading is not None:
            self.headings.append(" ".join("".join(self._heading).split()))
            self._heading = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self.lines.append(data)
        if self._heading is not None:
            self._heading.append(data)


def _page() -> _Page:
    page = _Page()
    page.feed(INDEX.read_text(encoding="utf-8"))
    return page


def _text() -> str:
    """The visible text, one line per block element, whitespace inside a line collapsed."""
    return "\n".join(" ".join(line.split()) for line in "".join(_page().lines).split("\n") if line.strip())


def test_the_copy_passes_the_claims_lint() -> None:
    assert claims.lint_text("site/index.html", _text()) == []


def test_the_copy_avoids_the_phrases_o12_bans() -> None:
    text = _text().lower()
    for phrase in ("ground truth", "independently verifiable", "lossless", "prov-o conformant", "prov-constraints valid",
                   "detection", "detects"):
        assert phrase not in text, phrase
    assert not re.search(r"\bfirst (?:public|open|framework|corpus|corpora|provenance|tool)", text)  # O.1.2
    assert "derivation-reproducible" in text  # the scoped wording (AR-12)
    for heading in _page().headings:
        assert "live capture" not in heading.lower(), heading  # NC-LIVE-02: no "Live Capture" title


def test_the_coverage_phrase_is_the_registry_generated_one() -> None:
    phrase = claims.coverage_phrase()
    assert phrase is not None and phrase in _text()


def test_live_runs_are_worded_as_a_tested_capability() -> None:
    text = _text()
    assert "Live capture works and is tested in v0.1. No live results are claimed" in text  # D-991, U-18


def test_everything_is_self_hosted() -> None:
    for tag, attrs in _page().tags:
        for key in ("src", "srcset", "data", "poster"):
            value = attrs.get(key)
            assert value is None or not re.match(r"(?:[a-z][a-z0-9+.-]*:|//)", value), (tag, key, value)
        if tag == "link":
            href = attrs.get("href") or ""
            assert not re.match(r"(?:[a-z][a-z0-9+.-]*:|//)", href), href
        assert not any(k.startswith("on") for k in attrs), (tag, attrs)  # no inline handlers (the page's CSP)
    for path in SITE.rglob("*"):
        if path.suffix in (".css", ".js"):
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"https?://|//[a-z0-9-]+\.[a-z]", text, re.IGNORECASE), path
            assert "@import" not in text and "@font-face" not in text, path
            for word in ("document.cookie", "fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "gtag", "analytics"):
                assert word not in text, (path, word)


def test_every_image_has_alt_text_and_every_file_is_used() -> None:
    tags = _page().tags
    images = [attrs for tag, attrs in tags if tag == "img"]
    assert images and all("alt" in attrs for attrs in images)
    shots = [attrs for attrs in images if (attrs.get("src") or "").startswith("assets/img/gui/")]
    assert all((attrs.get("alt") or "").strip() or (attrs.get("src") or "").endswith("runs-jobs.webp") for attrs in shots)
    referenced = {attrs.get("src") or attrs.get("href") for _, attrs in tags} - {None}
    referenced |= {"assets/img/brand/favicon.png"}
    files = {p.relative_to(SITE).as_posix() for p in SITE.rglob("*") if p.is_file() and p.name != ".DS_Store"}
    assert files - {"index.html"} <= referenced, sorted(files - {"index.html"} - referenced)
    light = {p.name for p in (SITE / "assets/img/gui/light").iterdir()}
    dark = {p.name for p in (SITE / "assets/img/gui/dark").iterdir()}
    assert light == dark and light


def test_the_brand_files_are_the_brand_sources() -> None:
    brand = ROOT / "docs" / "images" / "brand"
    copies = sorted((SITE / "assets/img/brand").glob("*.svg"))
    assert [p.name for p in copies] == ["agentprov-icon.svg", "agentprov-wordmark-on-dark.svg", "agentprov-wordmark.svg"]
    for copy in copies:
        assert copy.read_bytes() == (brand / copy.name).read_bytes(), copy.name
    favicon = ROOT / "docs" / "user-guide" / "images" / "brand" / "favicon.png"
    assert (SITE / "assets/img/brand/favicon.png").read_bytes() == favicon.read_bytes()


def test_the_downloads_are_the_release_assets() -> None:
    plan = (ROOT / "docs" / "reports" / "release" / "v0.1.0-plan.md").read_text(encoding="utf-8")
    links = {attrs["data-asset"]: attrs.get("href") for _, attrs in _page().tags if attrs.get("data-asset")}
    assert set(links) == ASSETS
    for asset, href in links.items():
        assert href == RELEASES + asset, (asset, href)
        assert asset in plan, asset


def test_the_release_day_placeholders_are_listed() -> None:
    found = {attrs["data-placeholder"] for _, attrs in _page().tags if attrs.get("data-placeholder")}
    assert found == PLACEHOLDERS


def test_the_site_matches_no_leak_pattern() -> None:
    spec = importlib.util.spec_from_file_location("agentprov_screenshot_guard", ROOT / "gui" / "tools" / "screenshots.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hits = []
    for path in sorted(SITE.rglob("*")):
        if path.is_file() and path.suffix in (".html", ".css", ".js", ".svg"):
            hits += [f"{path.relative_to(ROOT)}: {h[:12]}…" for h in module.leak_hits(path.read_text(encoding="utf-8"))]
    assert not hits, hits


def test_the_site_is_part_of_the_public_export() -> None:
    """D-943: the public tree is the release commit minus public-export.toml's paths; the website must not be one."""
    export = tomllib.loads((ROOT / "docs" / "reports" / "release" / "public-export.toml").read_text(encoding="utf-8"))
    for entry in export.get("exclude", []):
        path = entry["path"]
        assert not ("site/".startswith(path) or path.startswith("site/")), path
        assert not (".github/workflows/pages.yml".startswith(path)), path
