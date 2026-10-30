"""The user guide's website builds and publishes only the guide (``mkdocs.yml``).

* ``mkdocs build --strict`` succeeds into a temporary directory. Skipped when the ``docs`` dependency group is not
  installed (``uv sync --group docs``).
* The site holds only the guide's pages (one per chapter in the nav), its images, the search index, the sitemap and
  the theme's own assets: nothing else from ``docs/``, and no ``_``-prefixed working file.
* No page, image or index of the site matches the screenshot leak guard's patterns (account paths, e-mail addresses,
  key shapes; ``gui/tools/screenshots.py`` ``LEAKS``). One exemption, by construction: the guide's own absolute links
  to ``https://github.com/nickjones39/AgentPROV/...`` contain 40-character runs that the AWS-secret shape matches. The
  theme's ``assets/`` are third-party code (a licence e-mail in lunr, CSS class names such as ``task-list-control``)
  and are not scanned.
* The configuration keeps the privacy rules: no Google Fonts, no plugin other than search, docs_dir is the guide.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "user-guide"
REPO_URL = "https://github.com/nickjones39/AgentPROV/"


def _config() -> dict:
    return yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))


def _leaks():
    spec = importlib.util.spec_from_file_location("agentprov_screenshot_guard", ROOT / "gui" / "tools" / "screenshots.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.LEAKS


_STOP = set(" \t\r\n\"'<>()[]{}")


def _url_token(text: str, start: int, end: int) -> str:
    """The whitespace-, quote- and bracket-delimited token that contains text[start:end]."""
    left, right = start, end
    while left > 0 and text[left - 1] not in _STOP:
        left -= 1
    while right < len(text) and text[right] not in _STOP:
        right += 1
    return text[left:right]


def test_the_configuration_keeps_the_privacy_and_scope_rules() -> None:
    cfg = _config()
    assert cfg["docs_dir"] == "docs/user-guide" and cfg["site_dir"] == "_site/docs" and cfg["strict"] is True
    assert cfg["site_url"] == "https://w3id.org/agentprov/docs/"  # the landing page is the root (D-1000)
    assert cfg["theme"]["name"] == "material" and cfg["theme"]["font"] is False
    assert cfg["plugins"] == ["search"]
    assert cfg["dev_addr"].startswith("127.0.0.1:")
    assert "_*.md" in cfg["exclude_docs"]
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/_site/" in ignored and "/site/" not in ignored  # site/ is the landing page's tracked source


def test_the_nav_lists_every_chapter_once() -> None:
    nav = [next(iter(item.values())) for item in _config()["nav"]]
    pages = sorted(p.name for p in GUIDE.glob("*.md") if not p.name.startswith("_"))
    assert sorted(nav) == pages and len(nav) == len(set(nav))


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if importlib.util.find_spec("mkdocs") is None or importlib.util.find_spec("material") is None:
        pytest.skip("the docs dependency group is not installed (uv sync --group docs)")
    out = tmp_path_factory.mktemp("site")
    proc = subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict", "--config-file",
                           str(ROOT / "mkdocs.yml"), "--site-dir", str(out)],
                          cwd=ROOT, capture_output=True, text=True, check=False, timeout=600)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    return out


def test_the_site_holds_only_the_guide(site: Path) -> None:
    nav = [next(iter(item.values())) for item in _config()["nav"]]
    pages = {"index.html" if p == "README.md" else f"{p.removesuffix('.md')}/index.html" for p in nav}
    images = {p.relative_to(GUIDE).as_posix() for p in (GUIDE / "images").rglob("*") if p.is_file()}
    allowed = pages | images | {"404.html", "search/search_index.json", "sitemap.xml", "sitemap.xml.gz"}
    built = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    extra = sorted(f for f in built - allowed if not f.startswith("assets/"))
    assert not extra, extra
    assert pages <= built and images <= built


def test_the_site_matches_no_leak_pattern(site: Path) -> None:
    leaks = _leaks()
    hits = []
    for path in sorted(site.rglob("*")):
        rel = path.relative_to(site).as_posix()
        if not path.is_file() or rel.startswith("assets/") or path.suffix not in (".html", ".json", ".xml", ".svg"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in leaks.finditer(text):
            if _url_token(text, m.start(), m.end()).startswith(REPO_URL):
                continue  # inside one of the guide's own absolute repository links (the AWS-shape exemption)
            hits.append(f"{rel}: {m.group(0)[:12]}…")
    assert not hits, hits


def test_the_url_exemption_is_narrow() -> None:
    text = f'<a href="{REPO_URL}blob/main/docs/architecture/G_security.md">x</a> mail someone@example.org here'
    leaks = _leaks()
    kinds = [(m.group(0), _url_token(text, m.start(), m.end()).startswith(REPO_URL)) for m in leaks.finditer(text)]
    assert ("someone@example.org", False) in kinds
    assert any(exempt for _, exempt in kinds)
    other = "https://example.com/" + "com/nickjones39/AgentPROV/blob/main/docs"
    assert not _url_token(other, 20, len(other)).startswith(REPO_URL)
