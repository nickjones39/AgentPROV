"""D-1065: the releases answer (untrusted), the version order, this platform's bundle and the cached check."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import update_support as us  # noqa: E402

from agentprov.raw.fetch import FetchError  # noqa: E402
from agentprov.update import releases as R  # noqa: E402

DMG = "AgentPROV-macos-arm64.dmg"


@pytest.mark.parametrize("ordered", [
    ["0.1.1", "0.1.2", "0.2.0.dev1", "0.2.0a1", "0.2.0a2", "0.2.0b1", "0.2.0rc1", "0.2.0", "0.2.0.post1", "0.10.0",
     "1.0.0"],
])
def test_versions_sort_in_pep440_order(ordered: list[str]) -> None:
    keys = [R.version_key(v) for v in ordered]
    assert all(k is not None for k in keys)
    assert keys == sorted(keys) and len(set(map(str, keys))) == len(keys)  # type: ignore[type-var]
    assert R.version_key("0.1.1+local.1") == R.version_key("0.1.1")


@pytest.mark.parametrize("bad", ["", "1.2", "v0.1.1", "0.1.1-beta", "1.2.3.4", "01.2.x", None, 3])
def test_a_version_outside_the_subset_has_no_key(bad: object) -> None:
    assert R.version_key(bad) is None


@pytest.mark.parametrize(("system", "machine", "label", "asset"), [
    ("darwin", "arm64", "macos-arm64", "AgentPROV-macos-arm64.dmg"),
    ("darwin", "x86_64", "macos-x86_64", "AgentPROV-macos-x86_64.dmg"),
    ("win32", "AMD64", "windows-x64", "AgentPROV-windows-x64.zip"),
    ("win32", "ARM64", "windows-arm64", "AgentPROV-windows-arm64.zip"),
    ("linux", "x86_64", "linux-x86_64", "AgentPROV-linux-x86_64.tar.gz"),
    ("linux", "aarch64", "linux-aarch64", "AgentPROV-linux-aarch64.tar.gz"),
])
def test_the_platform_names_the_release_s_bundle(system: str, machine: str, label: str, asset: str) -> None:
    assert R.platform_label(system, machine) == label
    assert R.bundle_asset_name(label) == asset


def test_no_bundle_for_other_platforms() -> None:
    assert R.platform_label("freebsd14", "amd64") is None and R.platform_label("linux", "riscv64") is None


def test_the_newest_final_release_is_chosen_and_drafts_and_prereleases_are_ignored() -> None:
    data = us.answer(
        us.release("v0.3.0", prerelease=True), us.release("v0.4.0", draft=True), us.release("nightly"),
        us.release("v0.1.1"), us.release("v0.2.1", [(DMG, 10)]), us.release("v0.2.0"),
        {"tag_name": "v9.9.9", "assets": []},  # draft/prerelease not stated: not taken as final
    )
    found = R.parse_releases(data)
    assert sorted(r.tag for r in found) == ["v0.1.1", "v0.2.0", "v0.2.1"]
    latest = R.latest_release(found)
    assert latest is not None and latest.version == "0.2.1"
    assert latest.url == "https://github.com/nickjones39/AgentPROV/releases/tag/v0.2.1"
    assert latest.assets[0].url == f"{us.REPO_DL}/v0.2.1/{DMG}"


@pytest.mark.parametrize(("core", "gui", "available", "behind"), [
    ("0.1.1", None, True, {"core": True, "gui": None}),  # newer release
    ("0.2.1", None, False, {"core": False, "gui": None}),  # the same
    ("0.3.0", None, False, {"core": False, "gui": None}),  # older release than installed
    ("0.2.1", "0.1.1", True, {"core": False, "gui": True}),  # only the app is behind
    ("0.2.1.dev0", None, True, {"core": True, "gui": None}),  # a dev build of the release itself
    ("weird", None, None, {"core": None, "gui": None}),  # not comparable: never guessed
])
def test_update_available_compares_every_known_component(core: str, gui: str | None, available: bool | None,
                                                         behind: dict[str, bool | None]) -> None:
    rel = R.latest_release(R.parse_releases(us.answer(us.release("v0.2.1", [(DMG, 10), ("SHA256SUMS", 5)]))))
    doc = R.check_document(rel, core=core, gui=gui, label="macos-arm64", checked_at="2026-11-05T00:00:00Z",
                           fetched=True, auto_check=True, due=False)
    assert doc["update_available"] is available and doc["behind"] == behind
    assert doc["assets"] == [{"name": DMG, "size": 10, "url": f"{us.REPO_DL}/v0.2.1/{DMG}"}]
    assert doc["checksum_asset"]["name"] == "SHA256SUMS" and doc["signature_asset"] is None


def test_the_check_document_shape() -> None:
    rel = R.latest_release(R.parse_releases(us.answer(us.release("v0.2.1"))))
    doc = R.check_document(rel, core="0.1.1", gui=None, label="linux-x86_64", checked_at="2026-11-05T00:00:00Z",
                           fetched=True, auto_check=True, due=False)
    assert set(doc) == {"format", "repository", "checked_at", "fetched", "current", "latest", "tag",
                        "update_available", "behind", "published_at", "release_url", "notes", "notes_truncated",
                        "platform", "assets", "checksum_asset", "signature_asset", "auto_check", "check_due"}
    assert doc["format"] == "agentprov-update-check/0.1" and doc["published_at"] == "2026-11-04T01:02:03Z"
    assert doc["assets"] == []  # the release has no bundle for this platform
    none = R.check_document(None, core="0.1.1", gui=None, label=None, checked_at=None, fetched=False,
                            auto_check=True, due=True)
    assert none["latest"] is None and none["update_available"] is False


def test_notes_are_plain_text_escaped_and_capped() -> None:
    body = ("Fixed\r\nthe \x1b[31mviewer\x1b[0m " + chr(0x202E) + "evil" + chr(0x202C) + "\n"
            + "x" * (R.NOTES_MAX_CHARS + 50))
    rel = R.parse_releases(us.answer(us.release("v0.2.1", body=body)))[0]
    assert "\x1b" not in rel.notes and chr(0x202E) not in rel.notes and "<U+001B>" in rel.notes
    assert "\r" not in rel.notes and rel.notes.startswith("Fixed\nthe ")
    assert rel.notes_truncated and "[truncated:" in rel.notes and len(rel.notes) < R.NOTES_MAX_CHARS + 100


@pytest.mark.parametrize("data", [
    b"not json", b"{}", b'[{"tag_name": "v1.0.0", "tag_name": "v2.0.0"}]', b"[1]",
    us.answer({**us.release("v0.2.1"), "assets": {"a": 1}}),
    us.answer(us.release("v0.2.1", [(DMG, -1)])), us.answer(us.release("v0.2.1", [(DMG, 2**40)])),
    us.answer(us.release("v0.2.1", [(DMG, 1), (DMG, 1)])),
    b"[" + b"[" * 40 + b"]" * 40 + b"]",
])
def test_a_malformed_answer_is_refused(data: bytes) -> None:
    with pytest.raises(R.UpdateError) as exc:
        R.parse_releases(data)
    assert exc.value.code.startswith("update.response")


def test_an_oversized_answer_is_refused() -> None:
    big = b"[" + b" " * (R.MAX_API_BYTES + 1) + b"]"
    with pytest.raises(R.UpdateError, match="larger than"):
        R.parse_releases(big)
    t = us.FakeTransport({R.API_URL: big})
    with pytest.raises(R.UpdateError, match="larger than"):
        R.fetch_releases(t)
    announced = us.FakeTransport({R.API_URL: us.FakeResponse(b"[]", headers={"Content-Length": str(R.MAX_API_BYTES
                                                                                                    + 1)})})
    with pytest.raises(R.UpdateError, match="larger than"):
        R.fetch_releases(announced)


@pytest.mark.parametrize("url_for", [
    lambda t, n: f"https://evil.example/{t}/{n}",
    lambda t, n: f"https://github.com/someone/AgentPROV/releases/download/{t}/{n}",
    lambda t, n: f"http://github.com/nickjones39/AgentPROV/releases/download/{t}/{n}",
    lambda t, n: f"https://github.com/nickjones39/AgentPROV/releases/download/v0.0.1/{n}",
])
def test_an_asset_address_other_than_the_repository_s_release_is_refused(url_for) -> None:  # noqa: ANN001
    with pytest.raises(R.UpdateError) as exc:
        R.parse_releases(us.answer(us.release("v0.2.1", [(DMG, 10)], url_for=url_for)))
    assert exc.value.code == "update.response.host"


def test_the_api_request_goes_to_one_host_without_credentials() -> None:
    t = us.FakeTransport({R.API_URL: us.answer(us.release("v0.2.1"))})
    assert R.parse_releases(R.fetch_releases(t))[0].tag == "v0.2.1"
    assert t.calls == [(R.API_URL, frozenset({"api.github.com"}))]
    assert R.API_URL.startswith("https://api.github.com/repos/nickjones39/AgentPROV/releases")


def test_an_answer_from_another_host_or_status_is_refused() -> None:
    moved = us.FakeTransport({R.API_URL: us.FakeResponse(b"[]", url="https://evil.example/releases")})
    with pytest.raises(R.UpdateError) as exc:
        R.fetch_releases(moved)
    assert exc.value.code == "update.response.host"
    with pytest.raises(FetchError):
        R.fetch_releases(us.FakeTransport({}))  # 404


def test_the_redirect_handler_keeps_downloads_on_github_s_hosts() -> None:
    """The production transport's redirect policy (``SafeRedirectHandler``) with the download allow-list."""
    import urllib.request

    from agentprov.raw.fetch import RedirectRefusedError, SafeRedirectHandler

    handler = SafeRedirectHandler(R.DOWNLOAD_HOSTS)
    req = urllib.request.Request(f"{us.REPO_DL}/v0.2.1/{DMG}")
    ok = handler.redirect_request(req, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/x")
    assert ok is not None
    for bad in ("https://evil.example/x", "http://release-assets.githubusercontent.com/x"):
        with pytest.raises(RedirectRefusedError):
            handler.redirect_request(req, None, 302, "Found", {}, bad)
    assert "api.github.com" not in R.DOWNLOAD_HOSTS


def test_a_download_is_bounded_by_the_listed_size(tmp_path: Path) -> None:
    asset = R.Asset(DMG, 4, f"{us.REPO_DL}/v0.2.1/{DMG}")
    t = us.FakeTransport({asset.url: b"12345"})
    with pytest.raises(R.UpdateError, match="longer"):
        R.download(t, asset, tmp_path / DMG)
    assert not list(tmp_path.iterdir())  # the partial file is removed
    t = us.FakeTransport({asset.url: b"123"})
    with pytest.raises(R.UpdateError, match="shorter"):
        R.download(t, asset, tmp_path / DMG)
    t = us.FakeTransport({asset.url: b"1234"})
    assert R.download(t, asset, tmp_path / DMG) == __import__("hashlib").sha256(b"1234").hexdigest()
    assert t.calls[0][1] == R.DOWNLOAD_HOSTS


def test_the_cache_round_trips_and_a_damaged_cache_is_no_check(home: Path) -> None:
    rel = R.parse_releases(us.answer(us.release("v0.2.1", [(DMG, 10)])))[0]
    moment = dt.datetime(2026, 11, 5, 1, 0, tzinfo=dt.UTC)
    path = R.write_cache(home, rel, moment)
    assert R.read_cache(home) == ("2026-11-05T01:00:00Z", rel)
    doc = json.loads(path.read_text())
    doc["release"]["assets"][0]["url"] = "https://evil.example/x"
    path.write_text(json.dumps(doc))
    assert R.read_cache(home) is None
    path.write_text("{")
    assert R.read_cache(home) is None


@pytest.mark.skipif(not hasattr(__import__('time'), 'tzset'), reason="time.tzset is POSIX only (Windows)")
def test_once_a_day_in_local_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    __import__("time").tzset()
    try:
        # 2026-11-05 10:00 UTC is 23:00 NZDT; 11:30 UTC is 00:30 on the 6th in Auckland: a new local day
        assert not R.check_due("2026-11-05T10:00:00Z", dt.datetime(2026, 11, 5, 10, 30, tzinfo=dt.UTC))
        assert R.check_due("2026-11-05T10:00:00Z", dt.datetime(2026, 11, 5, 11, 30, tzinfo=dt.UTC))
        assert R.check_due(None) and R.check_due("garbage")
    finally:
        monkeypatch.delenv("TZ")
        __import__("time").tzset()
