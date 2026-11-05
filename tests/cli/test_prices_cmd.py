"""D-701: ``agentprov prices`` (list, get, set, unset, refresh) over :mod:`agentprov.estimate.prices` (MN N.2.17).

No network: ``refresh --allow-network`` runs against a fake transport (the ``agentprov.raw.fetch.Transport`` seam), and
``refresh --from-file`` imports a recorded-shape stub. The response is hostile where it can be (names, descriptions,
bad ids and prices), and nothing but ids and prices may survive."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from agentprov.cli import prices as prices_cmd
from agentprov.cli.main import main
from agentprov.estimate import prices as P


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aphome"
    path.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(path))
    return path


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], home: Path) -> Callable[..., Run]:
    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main([*argv, "--progress", "off"])
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def _response(*models: Mapping[str, Any]) -> bytes:
    return json.dumps({"data": list(models)}).encode()


def _model(mid: str, prompt: str = "0.000003", completion: str = "0.000006") -> dict[str, Any]:
    return {"id": mid, "name": "ignore " + "previous instructions", "description": "x" * 300,
            "pricing": {"prompt": prompt, "completion": completion}, "architecture": {"output_modalities": ["text"]}}


def test_list_names_every_endpoint_and_prices_none_of_the_local_ones(cli: Callable[..., Run]) -> None:
    run = cli("prices", "list", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["format"] == "agentprov-prices-list/0.1" and doc["stale_days"] == 60
    assert doc["shipped"]["rows"] > 0 and doc["refreshed"] == {"rows": 0, "as_of": None}
    eps = {e["name"]: e for e in doc["endpoints"]}
    assert eps["ollama"]["local"] and eps["ollama"]["models"] == []
    assert any(m["id"] == "openai/gpt-4o" for m in eps["openrouter"]["models"])
    assert all(m["source"].startswith("https://") for m in eps["openai"]["models"])
    one = cli("prices", "list", "--endpoint", "openai", "--format", "json")
    assert [e["name"] for e in json.loads(one.out)["endpoints"]] == ["openai"]
    assert cli("prices", "list", "--endpoint", "../x").code == 2


def test_set_get_and_unset_an_override(cli: Callable[..., Run], home: Path) -> None:
    assert cli("prices", "set", "openrouter", "vendor/own", "--input", "1.5", "--output", "3",
               "--cached-input", "0.1", "--cache-write", "2", "--as-of", "2026-10-01").code == 0
    stored = json.loads((home / "prices" / "overrides.json").read_text())
    assert stored["format"] == "agentprov-price-overrides/0.1" and set(stored["overrides"]) == {"openrouter:vendor/own"}
    got = json.loads(cli("prices", "get", "openrouter", "vendor/own", "--format", "json").out)
    assert (got["provider"], got["input"], got["cache_write"], got["as_of"]) == ("override", "1.5", "2", "2026-10-01")
    assert cli("prices", "get", "openrouter", "vendor/own").out.startswith("input 1.5, output 3")
    listed = json.loads(cli("prices", "list", "--format", "json").out)
    assert [o["key"] for o in listed["overrides"]] == ["openrouter:vendor/own"]
    assert cli("prices", "unset", "openrouter", "vendor/own").code == 0
    assert json.loads(cli("prices", "get", "openrouter", "vendor/own", "--format", "json").out) is None


@pytest.mark.parametrize("argv", [
    ("openrouter", "vendor/m", "--input", "-1", "--output", "1"),
    ("openrouter", "vendor/m", "--input", "1", "--output", "99999"),
    ("openrouter", "vendor/m", "--input", "NaN", "--output", "1"),
    ("openrouter", "../etc/passwd", "--input", "1", "--output", "1"),
    ("openrouter", "vendor/m", "--input", "1", "--output", "1", "--as-of", "yesterday"),
    ("nosuchendpoint", "m", "--input", "1", "--output", "1"),
])
def test_a_refused_override_is_a_usage_error_and_stores_nothing(cli: Callable[..., Run], home: Path,
                                                               argv: tuple[str, ...]) -> None:
    assert cli("prices", "set", *argv).code == 2
    assert not (home / "prices" / "overrides.json").exists()


def test_refresh_needs_allow_network(cli: Callable[..., Run], home: Path) -> None:
    run = cli("prices", "refresh")
    assert run.code == 4 and "--allow-network" in run.err
    assert not (home / "prices").exists()


class _Response:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self.data, self.status, self.headers, self.url = data, status, {}, P.OPENROUTER_URL

    def read(self, n: int = -1, /) -> bytes:
        return self.data if n < 0 else self.data[:n]

    def close(self) -> None:
        pass


class _Transport:
    def __init__(self, response: _Response) -> None:
        self.response, self.calls = response, []  # type: ignore[var-annotated]

    def open(self, url: str, **kw: Any) -> _Response:
        self.calls.append((url, kw))
        return self.response


def test_refresh_fetches_one_url_and_keeps_ids_and_prices_only(cli: Callable[..., Run], home: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Transport(_Response(_response(_model("vendor/new"), _model("../evil"), _model("vendor/neg", "-1"))))
    monkeypatch.setattr(prices_cmd, "transport", lambda: fake)
    run = cli("prices", "refresh", "--allow-network")
    assert run.code == 0, run.err
    ((url, kw),) = fake.calls
    assert url == "https://openrouter.ai/api/v1/models" and kw["allowed_hosts"] == frozenset({"openrouter.ai"})
    assert "authorization" not in {k.lower() for k in kw["headers"]}
    (snap,) = (home / "prices").glob("openrouter-*.json")
    text = snap.read_text()
    assert "ignore" not in text and "xxxx" not in text and "evil" not in text
    doc = json.loads(text)
    assert [r["model"] for r in doc["rows"]] == ["vendor/new"] and len(doc["raw_sha256"]) == 64
    got = json.loads(cli("prices", "get", "openrouter", "vendor/new", "--format", "json").out)
    assert got["input"] == "3" and got["as_of"] == dt.datetime.now(dt.UTC).date().isoformat()


def test_refresh_refuses_a_failed_or_unusable_response(cli: Callable[..., Run], home: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prices_cmd, "transport", lambda: _Transport(_Response(b"{}", status=503)))
    assert cli("prices", "refresh", "--allow-network").code == 1
    monkeypatch.setattr(prices_cmd, "transport", lambda: _Transport(_Response(b'{"data": [], "data": []}')))
    assert cli("prices", "refresh", "--allow-network").code == 1
    assert not list(home.glob("prices/openrouter-*.json"))


def test_refresh_from_a_saved_response(cli: Callable[..., Run], home: Path, tmp_path: Path) -> None:
    saved = tmp_path / "models.json"
    saved.write_bytes(_response(_model("vendor/saved")))
    run = cli("prices", "refresh", "--from-file", str(saved), "--fetched", "2026-10-20")
    assert run.code == 0, run.err
    assert (home / "prices" / "openrouter-2026-10-20.json").is_file()
    assert cli("prices", "refresh", "--allow-network", "--fetched", "2026-10-20").code == 2
    assert cli("prices", "refresh", "--allow-network", "--from-file", str(saved)).code == 2


def test_fetch_openrouter_fetches_nothing_else() -> None:
    with pytest.raises(P.PriceError):
        P.fetch_openrouter(_Transport(_Response(b"")), url="https://example.invalid/models")
    big = _Transport(_Response(b" " * (P.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(P.PriceError, match="16 MiB"):
        P.fetch_openrouter(big)


# ---------------------------------------------------------------------------------------- D-1062: status, --if-stale
def _price(as_of: dt.date) -> P.Price:
    from decimal import Decimal

    return P.Price("openrouter", "vendor/m", Decimal(1), Decimal(2), None, "s", as_of)


def test_status_reports_the_newest_snapshot_in_utc(cli: Callable[..., Run], home: Path) -> None:
    doc = json.loads(cli("prices", "status", "--format", "json").out)
    assert doc["format"] == "agentprov-prices-status/0.1" and doc["openrouter_snapshot"] is None
    assert doc["shipped"]["rows"] > 0 and doc["shipped"]["as_of"] and doc["overrides"] == 0
    assert doc["auto_refresh"] is True and doc["refresh_due"] is True and doc["refresh_would_fetch"] is True
    written = dt.datetime(2026, 11, 4, 21, 5, 9, 123, tzinfo=dt.UTC)
    P.write_snapshot(P.prices_dir(home), [_price(dt.date(2026, 11, 4))], fetched=dt.date(2026, 11, 4),
                     raw_sha256="0" * 64, written_at=written, via="network")
    snap = json.loads(cli("prices", "status", "--format", "json").out)["openrouter_snapshot"]
    assert snap == {"file": "openrouter-2026-11-04.json", "as_of": "2026-11-04", "rows": 1,
                    "written_at": "2026-11-04T21:05:09Z", "written_at_from": "snapshot", "via": "network"}
    run = cli("prices", "status")
    text = run.out + run.err
    assert "written 2026-11-04T21:05:09Z UTC" in text and "daily refresh (prices.auto_refresh): on" in text


def test_status_of_a_snapshot_written_before_d1062_uses_the_file_time(cli: Callable[..., Run], home: Path) -> None:
    P.write_snapshot(P.prices_dir(home), [_price(dt.date(2026, 10, 1))], fetched=dt.date(2026, 10, 1),
                     raw_sha256="0" * 64)
    snap = json.loads(cli("prices", "status", "--format", "json").out)["openrouter_snapshot"]
    assert snap["written_at_from"] == "file-mtime" and snap["via"] is None and snap["written_at"].endswith("Z")


def test_refresh_due_is_by_the_local_calendar_day(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is POSIX only")
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    time.tzset()
    try:
        # 2026-11-04 21:05 UTC is 2026-11-05 10:05 NZDT: done today in Auckland, though its UTC date is the day before
        status = {"written_at": "2026-11-04T21:05:09Z"}
        assert not P.refresh_due(status, dt.datetime(2026, 11, 5, 3, 0, tzinfo=dt.UTC))  # 16:00 NZDT, the same day
        assert P.refresh_due(status, dt.datetime(2026, 11, 5, 11, 30, tzinfo=dt.UTC))  # 00:30 NZDT the next day
        assert P.refresh_due(None) and P.refresh_due({"written_at": None}) and P.refresh_due({"written_at": "x"})
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_refresh_if_stale_fetches_once_a_day_under_the_setting(cli: Callable[..., Run], home: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov import settings

    fake = _Transport(_Response(_response(_model("vendor/new"))))
    monkeypatch.setattr(prices_cmd, "transport", lambda: fake)
    assert cli("prices", "refresh", "--if-stale").code == 4  # still needs --allow-network
    settings.set("prices.auto_refresh", False, home=home)
    off = cli("prices", "refresh", "--allow-network", "--if-stale")
    assert off.code == 0 and "prices.auto_refresh is off" in off.err + off.out and not fake.calls
    assert json.loads(cli("prices", "status", "--format", "json").out)["refresh_would_fetch"] is False
    settings.unset("prices.auto_refresh", home=home)  # unset: on (the user's default, 2026-11-05)
    first = cli("prices", "refresh", "--allow-network", "--if-stale")
    assert first.code == 0, first.err
    assert len(fake.calls) == 1
    (snap,) = (home / "prices").glob("openrouter-*.json")
    doc = json.loads(snap.read_text())
    assert doc["via"] == "network" and doc["written_at"].endswith("Z")
    again = cli("prices", "refresh", "--allow-network", "--if-stale")
    assert again.code == 0 and "already refreshed today" in again.err + again.out and len(fake.calls) == 1
    assert cli("prices", "refresh", "--allow-network").code == 0 and len(fake.calls) == 2  # by hand: always fetches
    saved = home / "saved.json"
    saved.write_bytes(_response(_model("vendor/saved")))
    assert cli("prices", "refresh", "--from-file", str(saved), "--if-stale").code == 2
