"""D-1062: the estimate's priors builder (``agentprov.estimate.localpriors``), local priors from the user's sealed
corpora (``agentprov priors build|show``), their precedence in ``agentprov estimate`` and the ``quote`` object.

The corpora are synthetic: slices of the committed golden AgentDojo logs, imported and sealed in temporary directories
(``local_priors_support``). Nothing reads ``$AGENTPROV_HOME`` outside the test's own temporary home."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import shutil
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_priors_support as lp  # noqa: E402

from agentprov.cli import priors_read as R  # noqa: E402
from agentprov.estimate import localpriors as L  # noqa: E402
from agentprov.estimate.cost import CellStats, PlanCell, Quantiles, estimate  # noqa: E402
from agentprov.estimate.prices import Price, plain  # noqa: E402
from agentprov.estimate.priors import PRIORS, PRIORS_FORMAT, StatsSource, load_priors  # noqa: E402
from agentprov.estimate.usage import ExecutionUsage, KeyStats, aggregate  # noqa: E402
from agentprov.testing import fs_guard  # noqa: E402

TOOL = Path(__file__).resolve().parents[2] / "tools" / "estimate" / "gen_estimate_priors.py"
TODAY = dt.date(2026, 11, 5)


# ------------------------------------------------------------------------------ the code path before D-1062, frozen
def _old_build_rows(usages: list[ExecutionUsage], min_executions: int) -> dict[tuple[str, ...], dict[str, Any]]:
    """``build_rows`` as ``tools/estimate/gen_estimate_priors.py`` had it at 2e86f1d2 (with the AU-TRG-6 fix)."""
    rows: dict[tuple[str, ...], dict[str, Any]] = {}
    for with_model in (True, False):
        for with_backend in (True, False):
            for (bench, suite, attack, family, backend), stats in sorted(aggregate(
                    usages, with_model=with_model, with_backend=with_backend,
                    min_executions=min_executions).items()):
                if (with_model and not family) or (with_backend and not backend):
                    continue
                key = (bench, suite, attack, family, backend)
                if key in rows:
                    raise RuntimeError(f"estimate priors: two rows for {key}")
                rows[key] = {"benchmark": bench, "suite": suite, "attack": attack or None, "family": family or None,
                             "backend": backend or None, **stats.to_json()}
    return rows


def _old_document(built_from: dict[str, Any], rows: dict[tuple[str, ...], dict[str, Any]]) -> bytes:
    """The tool's serialisation at 2e86f1d2 (``main``'s last lines; ``write_text`` of an ASCII string)."""
    doc = {"format": PRIORS_FORMAT, "built_from": built_from}
    head = json.dumps(doc, sort_keys=True, separators=(",", ":"))[:-1]
    lines = [json.dumps(rows[k], sort_keys=True, separators=(",", ":")) for k in sorted(rows)]
    return (head + ',"rows":[\n' + ",\n".join(lines) + "\n]}\n").encode("utf-8")


def _u(model: str | None, suite: str, calls: int, *, attack: str | None = None, backend: str | None = None,
       basis: str = "usage", judges: int = 0, seconds: float | None = 1.5, cached: int = 0) -> ExecutionUsage:
    return ExecutionUsage("agentdojo" if not judges else "agentharm", suite, attack, model, calls,
                          tuple(100 + i for i in range(calls)), (cached,) * calls, tuple(10 + i for i in range(calls)),
                          seconds, basis, (0,) * calls, backend=backend,
                          judge_tokens_in=(300,) * judges, judge_tokens_out=(20,) * judges)


def _synthetic() -> list[ExecutionUsage]:
    out: list[ExecutionUsage] = []
    for i in range(7):
        out += [_u("openai/gpt-4o-2024-05-13", "banking", 3 + i, backend="agentdojo" if i % 2 else None),
                _u("claude-sonnet-5-5", "banking", 2 + i, attack="important_instructions", basis="chars/4"),
                _u("llama3:8b", "slack", 1 + i, seconds=None, cached=i),  # no plain family: the any-model row only
                _u("deepseek-chat", "inspect_evals/agentharm", 1 + i % 3, judges=1 + i % 2, backend="agentharm"),
                _u(None, "travel", 4, basis="mixed")]
    return out + [_u("gpt-x", "workspace", 1)] * 3  # below min_executions


@pytest.mark.parametrize("min_executions", [1, 5])
def test_the_new_builder_writes_the_old_bytes(min_executions: int) -> None:
    """The shipped table regenerates byte for byte: same inputs, same document (the old and new code paths)."""
    usages = _synthetic()
    built_from = {"commit": "0" * 40, "tool": "tools/estimate/gen_estimate_priors.py", "chars_per_token": 4,
                  "min_executions": min_executions, "corpora": [{"name": "x-rg1.partial", "corpus_id": "x"}]}
    new = L.document_bytes(built_from, L.build_rows(usages, min_executions))
    assert new == _old_document(built_from, _old_build_rows(usages, min_executions))
    assert json.loads(new)["rows"]


def test_the_shipped_table_reserialises_to_its_committed_bytes() -> None:
    """The committed ``estimate_priors.json`` is exactly what ``document_bytes`` writes for its own header and rows."""
    raw = PRIORS.read_bytes()
    doc = json.loads(raw)
    rows = {(r["benchmark"], r["suite"], r["attack"] or "", r["family"] or "", r["backend"] or ""): r for r in doc["rows"]}
    assert L.document_bytes(doc["built_from"], rows) == raw


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_estimate_priors_d1062", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _InProcess:
    """The tool's process pool, in this process (a module loaded from a file path cannot be pickled to a worker)."""

    def __init__(self, max_workers: int) -> None:
        del max_workers

    def __enter__(self) -> _InProcess:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def map(self, fn: Callable[[Any], Any], items: Any, chunksize: int = 1) -> Any:
        del chunksize
        return map(fn, items)


def test_the_tool_is_a_thin_wrapper_over_the_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``gen_estimate_priors.py`` over a corpus folder gives the old code path's bytes for the same executions."""
    from agentprov.estimate.usage import execution_usage

    g = _tool()
    monkeypatch.setattr(g, "ProcessPoolExecutor", _InProcess)
    assert g.build_rows is L.build_rows and g.document_bytes is L.document_bytes
    root = tmp_path / "corpora"
    root.mkdir()
    lp.working(root / "x-rg1", 0, 3)
    out = tmp_path / "priors.json"
    sha = "1" * 40
    assert g.main(["--corpora-root", str(root), "--workers", "1", "--min-executions", "1", "--out", str(out),
                   "--corpus-commit", f"x-rg1.partial={sha}"]) == 0
    written = out.read_bytes()
    files = sorted(str(p) for p in (root / "x-rg1.partial" / "aer").rglob("*.aer.jsonl"))
    usages = [u for u in (execution_usage(f) for f in files) if u is not None]
    built_from = json.loads(written)["built_from"]
    assert built_from["corpora"][0]["building_commit"] == sha and usages
    assert written == _old_document(built_from, _old_build_rows(usages, 1))


# ------------------------------------------------------------------------------------------ local priors, built
@pytest.fixture(scope="module")
def corpora(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Under one corpora folder: two sealed corpora (one withholding an execution), a working one, and an older sealed
    version of the second corpus."""
    base = tmp_path_factory.mktemp("local-priors")
    root = base / "corpora"
    root.mkdir()
    alpha = lp.sealed(root / "alpha", 0, 3, corpus_id="alpha-test", withhold=0)
    beta = lp.sealed(root / "beta", 3, 3, corpus_id="beta-test", version="0.2.0")
    lp.sealed(root / "beta-old", 3, 2, corpus_id="beta-test", version="0.1.0")
    lp.working(root / "gamma", 6, 3)
    return {"root": root, "alpha": alpha, "beta": beta}


def test_local_priors_count_sealed_corpora_only_and_never_withheld_executions(corpora: dict[str, Any]) -> None:
    root = corpora["root"]
    with fs_guard.unchanged(root):  # nothing is written into a corpus (or anywhere under the folder)
        paths, skipped = R.discover(root)
        data, built = R.build_local(paths, jobs=1, min_executions=1, skipped=skipped)
    assert [p.name for p in paths] == ["alpha", "beta"]
    # the sealed corpus's private sidecar alpha.withheld is never opened, so it is not listed either
    assert {s["name"]: s["reason"] for s in skipped} == {
        "beta-old": "an older version of a corpus read", "gamma.partial": "working (not sealed)"}
    by_id = {c["corpus_id"]: c for c in built["corpora"]}
    assert set(by_id) == {"alpha-test", "beta-test"} and by_id["beta-test"]["corpus_version"] == "0.2.0"
    assert by_id["alpha-test"]["withheld"] == 1 and by_id["alpha-test"]["executions_read"] == 2
    assert by_id["beta-test"]["executions_read"] == 3 and built["executions"] == 5
    assert all(len(c["manifest_sha256"]) == 64 for c in built["corpora"])
    doc = json.loads(data)
    assert doc["format"] == PRIORS_FORMAT and doc["built_from"] == json.loads(json.dumps(built))
    assert doc["rows"] and all(r["executions"] >= 1 for r in doc["rows"])
    # the withheld execution is in no row: every any-model, any-backend row together counts the five read
    assert sum(r["executions"] for r in doc["rows"] if r["family"] is None and r["backend"] is None) == 5


def test_local_priors_are_deterministic_whatever_the_worker_count(corpora: dict[str, Any]) -> None:
    paths, skipped = R.discover(corpora["root"])
    one, _ = R.build_local(paths, jobs=1, min_executions=1, skipped=skipped)
    again, _ = R.build_local(paths, jobs=1, min_executions=1, skipped=skipped)
    two, _ = R.build_local(paths, jobs=2, min_executions=1, skipped=skipped)
    assert one == again == two


def test_an_execution_in_two_corpora_counts_once(tmp_path: Path, corpora: dict[str, Any]) -> None:
    copy = tmp_path / "beta-copy"
    shutil.copytree(corpora["root"] / "beta", copy, symlinks=True)
    _, built = R.build_local([corpora["root"] / "beta", copy], jobs=1, min_executions=1)
    first, second = built["corpora"]
    assert first["executions_read"] == 3 and second["executions_read"] == 0 and second["duplicates"] == 3


def _damage_aers(corpus: Path) -> None:
    for f in sorted((corpus / "aer").rglob("*.aer.jsonl")):
        f.chmod(0o644)
        data = f.read_bytes()
        f.write_bytes(data[:-2] + b"X\n")


def test_an_unreadable_copy_never_hides_a_readable_one_in_either_order(tmp_path: Path,
                                                                       corpora: dict[str, Any]) -> None:
    """AU-NC-103: an execution is marked counted only once its AER was read, so a damaged copy read first does not turn
    the readable original into duplicates; the rows do not depend on the corpora's order."""
    beta = corpora["root"] / "beta"
    copy = tmp_path / "beta-damaged"
    shutil.copytree(beta, copy, symlinks=True)
    _damage_aers(copy)
    first, built = R.build_local([copy, beta], jobs=1, min_executions=1)
    damaged, original = built["corpora"]
    assert damaged["unreadable"] == 3 and damaged["executions_read"] == 0
    assert original["executions_read"] == 3 and original["duplicates"] == 0 and built["executions"] == 3
    second, built = R.build_local([beta, copy], jobs=2, min_executions=1)
    original, damaged = built["corpora"]
    assert original["executions_read"] == 3 and damaged["duplicates"] == 3 and built["executions"] == 3
    assert json.loads(first)["rows"] == json.loads(second)["rows"]


def test_a_damaged_corpus_is_skipped_by_name_unless_it_was_named(tmp_path: Path, corpora: dict[str, Any]) -> None:
    """AU-NC-102: a discovered sealed corpus whose index is damaged adds nothing and is named in ``built_from.skipped``
    (the others are still read); a ``--corpus`` one refuses the build, naming its number."""
    root = tmp_path / "corpora"
    root.mkdir()
    for name in ("alpha", "beta"):
        shutil.copytree(corpora["root"] / name, root / name, symlinks=True)
    index = root / "alpha" / "executions.jsonl"
    index.chmod(0o644)
    index.write_bytes(index.read_bytes() + b"{}\n")
    paths, skipped = R.discover(root)
    assert [p.name for p in paths] == ["alpha", "beta"] and skipped == []
    _, built = R.build_local(paths, jobs=1, min_executions=1, skipped=skipped)
    assert [c["corpus_id"] for c in built["corpora"]] == ["beta-test"] and built["executions"] == 3
    assert [s["name"] for s in built["skipped"]] == ["alpha"]
    assert built["skipped"][0]["reason"].startswith("unreadable (corpus.")
    with pytest.raises(L.PriorsBuildError, match=r"--corpus number 1 \(alpha\) is not readable"):
        R.build_local(paths, jobs=1, min_executions=1, given=True)


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
        ) -> Callable[..., Run]:
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main([*argv, "--progress", "off"])
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def test_priors_build_and_show(cli: Callable[..., Run], tmp_path: Path, corpora: dict[str, Any]) -> None:
    home = tmp_path / "home"
    shown = json.loads(cli("priors", "show", "--format", "json").out)
    assert shown["format"] == "agentprov-priors-show/0.1" and shown["local"]["exists"] is False
    assert shown["shipped"]["exists"] and shown["shipped"]["rows"] > 0
    empty = cli("priors", "build", "--format", "json")  # no corpora folder in this home: nothing is written
    assert empty.code == 0 and json.loads(empty.out)["written"] is False
    assert not (home / "estimate").exists()
    shutil.copytree(corpora["root"], home / "corpora", symlinks=True)
    run = cli("priors", "build", "--jobs", "1", "--min-executions", "1", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    path = home / "estimate" / "priors-local.json"
    assert doc["format"] == "agentprov-priors-build/0.1" and doc["written"] and doc["path"] == str(path)
    assert doc["executions"] == 5 and [c["corpus_id"] for c in doc["corpora"]] == ["alpha-test", "beta-test"]
    header, rows = load_priors(path)
    assert rows and header["built_from"]["tool"] == "agentprov priors build"
    shown = json.loads(cli("priors", "show", "--format", "json").out)["local"]
    assert shown["exists"] and shown["rows"] == len(rows) and shown["executions"] == 5
    assert shown["benchmarks"] == {"agentdojo": len(rows)}
    named = cli("priors", "build", "--corpus", str(home / "corpora" / "beta"), "--min-executions", "1", "--jobs", "1",
                "--format", "json")
    assert named.code == 0 and [c["corpus_id"] for c in json.loads(named.out)["corpora"]] == ["beta-test"]
    assert cli("priors", "build", "--corpus", str(home / "corpora" / "gamma")).code == 2  # working: refused
    twice = cli("priors", "build", "--corpus", str(home / "corpora" / "beta"), "--corpus",
                str(home / "corpora" / "beta-old"))
    assert twice.code == 2 and "count twice" in twice.err
    damaged = tmp_path / "damaged"  # AU-NC-102: a named corpus that cannot be read refuses the build, by its number
    shutil.copytree(home / "corpora" / "beta", damaged, symlinks=True)
    (damaged / "executions.jsonl").chmod(0o644)
    (damaged / "executions.jsonl").write_bytes((damaged / "executions.jsonl").read_bytes() + b"{}\n")
    refused = cli("priors", "build", "--corpus", str(damaged), "--jobs", "1")
    assert refused.code == 2 and "--corpus number 1 (damaged) is not readable" in refused.err
    assert cli("priors", "show").code == 0


# ------------------------------------------------------------------------------------------ precedence and basis
def _ks(executions: int, calls: float, basis: str = "chars/4", cached: float = 0.0) -> KeyStats:
    return KeyStats(executions, int(executions * calls), calls, calls * 2, 1000.0, 2000.0, cached, cached, 100.0,
                    200.0, 30.0, 60.0, basis)


def _key(family: str = "", suite: str = "banking", benchmark: str = "agentdojo") -> tuple[str, str, str, str, str]:
    return (benchmark, suite, "", family, "")


def test_local_rows_come_first_and_family_rows_before_any_model_rows() -> None:
    shipped = {_key("gpt-4o"): _ks(500, 7), _key(): _ks(900, 8), _key(suite="slack"): _ks(400, 9)}
    local = {_key("gpt-4o"): _ks(12, 3), _key(suite="slack"): _ks(20, 4), _key(suite="travel"): _ks(30, 5)}
    s = StatsSource(benchmark="agentdojo", model="openai/gpt-4o-2024-05-13", priors=shipped, local=local,
                    local_corpora=("alpha-test",))
    assert (s("banking", None, "user_task").calls.p50, s("banking", None, "user_task").source) == (3, "priors-local")
    assert s.basis() == {"priors": "local", "family_specific": True, "family": "gpt-4o", "executions": 12,
                         "corpora": ["alpha-test"], "token_basis": "chars/4", "cached_input": False,
                         "groups_by_source": {"priors-local": 1}}
    # a family row (shipped) wins over an any-model row (local); local any-model wins over shipped any-model
    only_any = StatsSource(benchmark="agentdojo", model="gpt-4o", priors=shipped, local={_key(): _ks(10, 2)})
    assert only_any("banking", None, "user_task").source == "priors"
    assert only_any("banking", None, "user_task").calls.p50 == 7
    s2 = StatsSource(benchmark="agentdojo", model="claude-sonnet-5-5", priors=shipped, local=local)
    assert s2("slack", None, "user_task").source == "priors-local" and s2("slack", None, "user_task").calls.p50 == 4
    s2("banking", None, "user_task")
    s2("nowhere", None, "user_task")
    b = s2.basis()
    assert b["priors"] == "mixed" and b["family_specific"] is False and b["family"] is None
    assert b["executions"] == 20 + 900 and b["corpora"] == [] and b["groups_by_source"] == {
        "default": 1, "priors": 1, "priors-local": 1}
    # without local priors the shipped order is the one before D-1062
    plain = StatsSource(benchmark="agentdojo", model="gpt-4o", priors=shipped)
    assert plain("banking", None, "user_task").calls.p50 == 7 and plain.basis()["priors"] == "shipped"


def test_estimate_without_local_priors_is_unchanged() -> None:
    """The cell statistics without a local file match the lookup before D-1062 for every shipped key."""
    from agentprov.estimate.usage import lookup

    _, shipped = load_priors(PRIORS)
    for model in ("gpt-4o-2024-05-13", "claude-3-5-sonnet-20241022", None):
        s = StatsSource(benchmark="agentdojo", model=model, backend="agentdojo", priors=shipped)
        for suite in sorted({k[1] for k in shipped})[:12]:
            hit = None
            for benchmark in ("agentdojo", "agentdyn"):
                hit = lookup(shipped, benchmark, suite, None, s.family, "agentdojo")
                if hit is not None:
                    break
            got = s(suite, None, "user_task")
            assert (got.source == "priors") == (hit is not None)
            if hit is not None:
                assert got.calls.p50 == hit[0].calls_p50 and hit[1] in got.basis


def test_the_estimate_sums_tokens_as_it_sums_the_cost() -> None:
    stats = CellStats(Quantiles(10, 20), Quantiles(1000, 2000), Quantiles(0, 0), Quantiles(100, 200),
                      Quantiles(60, 120), "priors")
    price = Price("openai", "m", Decimal(1), Decimal(10), None, "s", TODAY)
    cells = [PlanCell("banking", None, "user_task", 0), PlanCell("slack", "ii", "attacked", 0)]
    e = estimate(cells, repeats=2, attempts_due=4, jobs=2, price=price, stats_for=lambda *_: stats, today=TODAY)
    assert (e.tokens_in_p50, e.tokens_in_p90) == (4 * 10 * 1000 + 1000, 4 * 20 * 2000 + 2000)  # + the probe
    assert (e.tokens_out_p50, e.tokens_out_p90) == (4 * 10 * 100 + 100, 4 * 20 * 200 + 200)
    assert (e.seconds_serial_p50, e.seconds_serial_p90) == (4 * 60, 4 * 120)
    assert (e.seconds_p50, e.seconds_p90) == (2 * 60, 2 * 120)  # ceil(4 / 2) rounds at --jobs 2
    per_call_90 = (Decimal(2000) * 1 + Decimal(200) * 10) / 10**6
    assert e.cost_p90 == Decimal(80) * per_call_90 + per_call_90  # the sum of per-cell 90th percentiles


def test_the_quote_object() -> None:
    from agentprov.cli.estimate import estimate_only_line, quote

    stats = CellStats(Quantiles(10, 20), Quantiles(1000, 2000), Quantiles(0, 0), Quantiles(100, 200),
                      Quantiles(60, 120), "priors-local")
    price = Price("anthropic", "claude-sonnet-5-5", Decimal(3), Decimal(15), Decimal("0.3"), "s", TODAY)
    e = estimate([PlanCell("banking", None, "user_task", 0)], repeats=3, attempts_due=9, jobs=3, price=price,
                 stats_for=lambda *_: stats, today=TODAY)
    basis = {"priors": "local", "family_specific": True, "family": "claude-sonnet-5-5", "executions": 40,
             "corpora": ["alpha-test"], "token_basis": "chars/4", "cached_input": False, "groups_by_source": {}}
    q = quote(e, basis, price, 3)
    assert set(q) == {"usd_p50", "usd_p90", "calls_p50", "calls_p90", "tokens_in_p50", "tokens_in_p90",
                      "tokens_out_p50", "tokens_out_p90", "seconds_p50", "seconds_p90", "seconds_serial_p50",
                      "seconds_serial_p90", "jobs", "cells", "p50_aggregation", "p90_aggregation", "basis"}
    assert e.cost_p50 is not None and e.cost_p90 is not None
    assert (q["usd_p50"], q["usd_p90"]) == (plain(e.cost_p50), plain(e.cost_p90))
    assert q["cells"] == 3 and q["jobs"] == 3 and q["calls_p50"] == 31 and q["tokens_in_p50"] == 31000
    assert q["p90_aggregation"] == "upper (sum of per-cell 90th percentiles)"
    assert q["basis"] == {"priors": "local", "family_specific": True, "family": "claude-sonnet-5-5",
                          "executions": 40, "corpora": ["alpha-test"], "token_basis": "chars/4",
                          "price_source": "direct", "price_as_of": "2026-11-05", "discounts_assumed": False,
                          "estimate_only": True}
    assert estimate_only_line(q) == ("Estimate only: actual cost can differ (token counts are approximated as "
                                     "characters / 4; batch and cache discounts are not assumed).")
    cached = quote(e, {**basis, "cached_input": True, "token_basis": "usage"}, price, 3)
    assert cached["basis"]["discounts_assumed"] is True and "recorded usage" not in estimate_only_line(cached)
    assert "cache rate" in estimate_only_line(cached) and "usage recorded" in estimate_only_line(cached)
    unpriced = quote(estimate([PlanCell("b", None, "user_task", 0)], repeats=1, attempts_due=1, jobs=1, price=None,
                              stats_for=lambda *_: stats), basis, None, 1)
    assert unpriced["usd_p50"] is None and unpriced["basis"]["price_source"] is None
