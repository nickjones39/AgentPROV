"""D-701: ``agentprov estimate`` against the fake backend environment of ``live_fake`` (no benchmark package, no
network, no key). Its plan is the dry run's (the totals agree), a real model is planned with the scripted stand-in
when no key source is given (and says so), the price comes from ``agentprov prices``, and nothing is written."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_fake import make_fake_env, repo_root  # noqa: E402

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aphome"
    path.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(path))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.chdir(repo_root())
    make_fake_env(path, "ok")
    return path


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], home: Path) -> Callable[..., Run]:
    from agentprov.cli.main import main

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main(list(argv))
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def _estimate(cli: Callable[..., Run], *extra: str) -> Run:
    return cli("estimate", "agentdojo", "--suite", "banking", "--progress", "off", "--format", "json", *extra)


def test_a_scripted_estimate_costs_nothing_and_matches_the_dry_plan(cli: Callable[..., Run], home: Path,
                                                                    tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text("[]")
    run = _estimate(cli, "--llm-script", str(script), "--repeats", "3")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["format"] == "agentprov-estimate/0.1" and doc["transport"] == "scripted"
    assert doc["planned_with"] == "model" and doc["plan"]["repeats"] == 3
    assert doc["units"] == doc["plan"]["units"] == doc["plan"]["cells"] * 3
    assert doc["cost_p50"] == doc["cost_p90"] == "0" and doc["price"]["provider"] == "local"
    assert {g["label"] for g in doc["by_suite"]} == {"banking"}
    assert not any("stand-in" in w for w in doc["warnings"])
    assert not (home / "corpora").exists()  # a dry run writes nothing


def test_a_real_model_without_a_key_is_planned_with_the_stand_in(cli: Callable[..., Run], home: Path) -> None:
    run = _estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["transport"] == "http" and doc["planned_with"] == "stand-in"
    assert (doc["endpoint"], doc["model"]) == ("openrouter", "openai/gpt-4o")
    assert doc["price"]["model"] == "openai/gpt-4o" and Decimal(doc["cost_p90"]) >= Decimal(doc["cost_p50"]) > 0
    assert Decimal(doc["cost_worst"]) >= Decimal(doc["cost_p90"])
    assert any("stand-in" in w for w in doc["warnings"])
    assert doc["calls_p50"] >= doc["units"]  # at least one call per cell, plus the preflight probe


def test_an_override_prices_the_estimate(cli: Callable[..., Run]) -> None:
    assert cli("prices", "set", "openrouter", "vendor/mine", "--input", "1000", "--output", "0",
               "--progress", "off").code == 0
    doc = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "vendor/mine").out)
    assert doc["price"]["provider"] == "override" and Decimal(doc["cost_p50"]) > 0


def test_no_model_id_or_no_price_is_a_warning_not_a_guess(cli: Callable[..., Run]) -> None:
    doc = json.loads(_estimate(cli, "--model", "openrouter").out)
    assert doc["cost_p50"] is None and any("--model-id" in w for w in doc["warnings"])
    doc = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "vendor/unpriced").out)
    assert doc["price"] is None and doc["cost_p50"] is None and "no price" in doc["headline"]


def test_the_text_form_and_usage_errors(cli: Callable[..., Run], tmp_path: Path) -> None:
    text = cli("estimate", "agentdojo", "--suite", "banking", "--model", "openrouter", "--model-id", "openai/gpt-4o",
               "--progress", "off")
    assert text.code == 0 and "By suite:" in text.err and "Cost: p50 $" in text.err
    assert _estimate(cli).code == 2  # no model
    assert _estimate(cli, "--model", "openrouter", "--json").code == 2  # stdout is taken
    assert _estimate(cli, "--model", "openrouter", "--stats-corpus", str(tmp_path)).code == 2  # not a corpus
    assert cli("estimate", "agentdojo", "--dry-run", "--progress", "off").code == 2  # run-only options are absent


def _local_priors(home: Path) -> None:
    """A local priors file (D-1062) with this model family's banking row, as ``agentprov priors build`` writes it."""
    from agentprov.estimate.localpriors import document_bytes, local_priors_path
    from agentprov.estimate.usage import KeyStats

    stats = KeyStats(40, 400, 10.0, 14.0, 900.0, 1500.0, 0.0, 0.0, 80.0, 150.0, 20.0, 45.0, "chars/4")
    rows = {("agentdojo", "banking", "", "gpt-4o", ""): {"benchmark": "agentdojo", "suite": "banking", "attack": None,
                                                         "family": "gpt-4o", "backend": None, **stats.to_json()}}
    built_from = {"tool": "agentprov priors build", "corpora": [{"corpus_id": "mine-test", "executions_read": 40,
                                                                 "manifest_sha256": "0" * 64}]}
    path = local_priors_path(home)
    path.parent.mkdir(parents=True)
    path.write_bytes(document_bytes(built_from, rows))


def test_the_quote_says_what_it_rests_on(cli: Callable[..., Run], home: Path) -> None:
    """D-1062: ``quote`` (additive) from the shipped priors, then from local priors of this model family."""
    shipped = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o").out)
    q = shipped["quote"]
    assert q["usd_p50"] == shipped["cost_p50"] and q["usd_p90"] == shipped["cost_p90"]
    assert q["cells"] == shipped["units"] and q["calls_p90"] == shipped["calls_p90"] and q["jobs"] == 1
    assert q["tokens_in_p90"] >= q["tokens_in_p50"] > 0 and q["seconds_serial_p50"] == q["seconds_p50"]
    assert q["p90_aggregation"] == "upper (sum of per-cell 90th percentiles)"
    b = q["basis"]
    assert b["priors"] == "shipped" and b["corpora"] == [] and b["estimate_only"] is True
    assert b["price_source"] == "openrouter" and b["price_as_of"] == shipped["price"]["as_of"]
    assert b["discounts_assumed"] is False and b["executions"] > 0
    _local_priors(home)
    local = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o", "--jobs", "2").out)
    b = local["quote"]["basis"]
    assert (b["priors"], b["family_specific"], b["family"], b["executions"], b["corpora"], b["token_basis"]) == (
        "local", True, "gpt-4o", 40, ["mine-test"], "chars/4")
    assert local["sources"] == {"priors-local": local["units"]} and local["quote"]["jobs"] == 2
    assert local["quote"]["seconds_serial_p50"] >= local["quote"]["seconds_p50"]
    other = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "deepseek/deepseek-chat").out)
    assert other["quote"]["basis"]["priors"] == "shipped"  # no local row for this family or any model
    text = cli("estimate", "agentdojo", "--suite", "banking", "--model", "openrouter", "--model-id", "openai/gpt-4o",
               "--progress", "off")
    assert ("Estimate only: actual cost can differ (token counts are approximated as characters / 4; batch and "
            "cache discounts are not assumed).") in text.err


def test_the_quote_suggests_caps_with_room_for_the_reserved_cells(cli: Callable[..., Run], home: Path) -> None:
    """D-1090: ``quote.caps`` from the dry plan's own cell bound (the campaign's), the margin setting and the price;
    the text form prints the suggestion; a scripted estimate suggests none."""
    from agentprov import settings

    doc = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o").out)
    q, c = doc["quote"], doc["quote"]["caps"]
    assert c["available"] is True and (c["margin_pct"], c["margin_from"]) == ("20", "default")
    assert (c["reserved_cells"], c["cell_calls"], c["probe_calls"]) == (1, 48, 1)
    assert c["max_calls"] >= q["calls_p90"] * 1.2 + 49 and c["max_calls"] < q["calls_p90"] * 1.2 + 50
    assert Decimal(c["max_cost_usd"]) >= Decimal(q["usd_p90"]) * Decimal("1.2") + Decimal(c["cell_usd"])
    assert (c["price_in"], c["price_out"]) == (doc["price"]["input"], doc["price"]["output"])
    wide = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o", "--jobs", "4",
                                "--llm-element", "gateway_compat").out)["quote"]["caps"]
    assert (wide["reserved_cells"], wide["cell_calls"], wide["probe_calls"]) == (min(4, doc["units"]), 384, 8)
    settings.set("estimate.caps_margin_pct", "50")
    loose = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o").out)["quote"]["caps"]
    assert (loose["margin_pct"], loose["margin_from"]) == ("50", "setting") and loose["max_calls"] > c["max_calls"]
    text = cli("estimate", "agentdojo", "--suite", "banking", "--model", "openrouter", "--model-id", "openai/gpt-4o",
               "--progress", "off")
    assert f"Suggested caps: --max-calls {loose['max_calls']} --max-cost-usd {loose['max_cost_usd']}" in text.err
    unpriced = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "vendor/unpriced-model").out)
    assert unpriced["quote"]["caps"]["available"] is False and "no price" in unpriced["quote"]["caps"]["reason"]


def test_caps_pass_through_and_a_cap_below_the_p90_is_a_warning(cli: Callable[..., Run]) -> None:
    """D-725 caps are estimate options (a keyed API plan needs them, D-721); a cap below the p90 is said, not hidden."""
    doc = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o", "--max-calls", "1",
                               "--max-cost-usd", "0.0001", "--price-in", "2.5", "--price-out", "10").out)
    warnings = " ".join(doc["warnings"])
    assert "above --max-calls 1" in warnings and "above --max-cost-usd $0.0001" in warnings
    roomy = json.loads(_estimate(cli, "--model", "openrouter", "--model-id", "openai/gpt-4o", "--max-calls", "100000",
                                 "--max-cost-usd", "1000", "--price-in", "2.5", "--price-out", "10").out)
    assert not any("--max-c" in w for w in roomy["warnings"])
    assert _estimate(cli, "--llm-script", "/nonexistent", "--i-consent-to-local-run").code == 2  # not an estimate option
