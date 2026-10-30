"""``agentprov render`` (MN N.2.13; K.5.12; K.15): selection, output guard, exit codes, determinism, hostile content.

Corpora are built in a temporary directory by ``tests/render/render_support.py`` (a synthetic execution derived by the
real engine); nothing here reads a committed fixture, the user's corpora or the network.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

_RENDER_TESTS = Path(__file__).resolve().parents[1] / "render"
if str(_RENDER_TESTS) not in sys.path:
    sys.path.insert(0, str(_RENDER_TESTS))

import render_support as rs  # noqa: E402

pytestmark = pytest.mark.render

HAVE_PYDOT = importlib.util.find_spec("pydot") is not None
needs_pydot = pytest.mark.skipif(not HAVE_PYDOT, reason="the render extra (pydot) is not installed")
needs_dot = pytest.mark.skipif(not HAVE_PYDOT or shutil.which("dot") is None, reason="needs pydot and the Graphviz dot binary")


def _build(tmp_path_factory: pytest.TempPathFactory, name: str, **kw: Any) -> dict[str, Any]:
    base = tmp_path_factory.mktemp(name)
    (base / "scratch").mkdir()
    return rs.build_corpus(base / "corpus", base / "scratch", **kw)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    return _build(tmp_path_factory, "plain")


@pytest.fixture(scope="module")
def sealed(tmp_path_factory):
    return _build(tmp_path_factory, "sealed", sealed=True, executions=1)


@pytest.fixture(scope="module")
def broken(tmp_path_factory):
    return _build(tmp_path_factory, "broken", broken_prov=True)


@pytest.fixture(scope="module")
def noprov(tmp_path_factory):
    return _build(tmp_path_factory, "noprov", no_prov_last=True)


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def dots(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.rglob("*.dot"))}


# ------------------------------------------------------------------------------------------------ usage
def test_help_names_the_synopsis(cli):
    run = cli("render", "--help")
    assert run.code == 0
    for text in ("--corpus", "--ex", "--select", "--bundle", "--format", "--direction", "--out", "--limit", "--jobs", "--dry-run", "evidence class"):
        assert text in run.out


def test_nothing_selected_is_a_usage_error(cli, corpus):
    run = cli("render", "--corpus", str(corpus["root"]))
    assert run.code == 2 and "nothing selected" in run.err


@pytest.mark.parametrize(
    "extra",
    [("--ex", "ex_bad"), ("--select", "nokey"), ("--select", "bogus=1"), ("--format", "gif"), ("--bundle", "inference"),
     ("--limit", "-1"), ("--limit", "x")],
)
def test_bad_options_are_usage_errors(cli, corpus, extra):
    assert cli("render", "--corpus", str(corpus["root"]), "--limit", "1", *extra).code == 2


def test_there_is_no_render_all_option(cli, corpus):
    """D-45: renders are on demand; `--all` is not an option (nor an abbreviation of anything)."""
    run = cli("render", "--corpus", str(corpus["root"]), "--all")
    assert run.code == 2 and "--all" in run.err
    assert cli("render", "--corpus", str(corpus["root"]), "--limit", "1", "--all").code == 2
    assert "--all" not in cli("render", "--help").out


def test_select_without_limit_is_a_usage_error(cli, corpus, tmp_path):
    """D-45: a filter alone could still match every execution, so `--select` needs `--limit`."""
    run = cli("render", "--corpus", str(corpus["root"]), "--select", "task=t1", "--out", str(tmp_path / "o"))
    assert run.code == 2 and "--select needs --limit" in run.err
    assert not (tmp_path / "o").exists()


@needs_pydot  # without the extra, the extras check (exit 3) precedes resolving --ex
def test_missing_corpus_and_unknown_execution_are_usage_errors(cli, corpus, tmp_path):
    assert cli("render", "--corpus", str(tmp_path / "nope"), "--limit", "10").code == 2
    unknown = "ex_" + "a" * 26
    run = cli("render", "--corpus", str(corpus["root"]), "--ex", unknown, "--format", "dot", "--out", str(tmp_path / "o"))
    assert run.code == 2 and unknown in run.err


# ------------------------------------------------------------------------------------------------ output location
@needs_pydot
def test_default_output_is_beside_the_corpus_and_nothing_is_written_inside_it(cli, tmp_path):
    c = rs.build_corpus(tmp_path / "work" / "corp", tmp_path)
    before = tree(c["root"])
    run = cli("render", "--corpus", str(c["root"]), "--limit", "10", "--format", "dot")
    assert run.code == 0, run.err
    out = tmp_path / "work" / "corp-rendered" / "agentprov-prov-0.1"
    assert sorted(p.name for p in out.rglob("*.dot")) == sorted(f"{ex}.dot" for ex in c["exs"])
    assert tree(c["root"]) == before  # byte-identical: a render never writes into a corpus
    assert cli("render", "--corpus", str(c["root"]), "--limit", "10", "--format", "dot").code == 0  # re-running overwrites in place


def test_the_default_output_of_a_dot_or_dotdot_corpus_path_is_beside_the_corpus(cli, corpus, monkeypatch):
    """`--corpus .` was an internal error (exit 70) and `--corpus C/aer/..` a refusal (exit 4) without any --out.

    The output guard precedes the extras check, so without pydot the run still gets past it (exit 3)."""
    monkeypatch.chdir(corpus["root"])
    for path in (".", str(corpus["root"] / "aer" / "..")):
        run = cli("render", "--corpus", path, "--limit", "1", "--format", "dot", "--dry-run")
        assert run.code == (0 if HAVE_PYDOT else 3), run.err


def test_jobs_0_is_the_host_default(cli, corpus, monkeypatch, tmp_path):
    """``--jobs 0`` (the default) runs the host default worker count of ``dot`` processes; it was min(4, CPUs). The
    extras check is stubbed and the run stops at the pool, so this holds without pydot."""
    import agentprov.cli.render as render_cli
    import agentprov.io.workers as io_workers
    import agentprov.render.dot as dotmod

    seen: list[int] = []

    def executor(max_workers: int):
        seen.append(max_workers)
        raise KeyboardInterrupt  # stop here: nothing is rendered (the CLI turns it into an exit code)

    monkeypatch.setattr(dotmod, "require_pydot", lambda: None)
    monkeypatch.setattr(io_workers, "resolve_worker_count", lambda requested: 11 if requested == 0 else requested)
    monkeypatch.setattr(render_cli, "ThreadPoolExecutor", executor)
    for jobs, expected in (("0", 11), ("2", 2)):
        run = cli("render", "--corpus", str(corpus["root"]), "--limit", "1", "--format", "dot", "--dry-run", "--jobs",
                  jobs, "--out", str(tmp_path / f"out-{jobs}"))
        assert run.code != 0 and seen.pop() == expected  # the CLI reports the interrupt


def test_output_inside_the_corpus_is_refused_before_anything_else(cli, corpus):
    before = tree(corpus["root"])
    for inside in (corpus["root"], corpus["root"] / "prov", corpus["root"] / "renders"):
        run = cli("render", "--corpus", str(corpus["root"]), "--limit", "10", "--out", str(inside))
        assert run.code == 4, run.err
    assert tree(corpus["root"]) == before and not (corpus["root"] / "renders").exists()


def test_output_inside_a_sealed_corpus_is_refused(cli, sealed):
    run = cli("render", "--corpus", str(sealed["root"]), "--limit", "10", "--out", str(sealed["root"] / "r"), "--json")
    assert run.code == 4 and "sealed" in run.err.lower()
    assert not (sealed["root"] / "r").exists()


@needs_pydot
def test_a_sealed_corpus_can_be_rendered_to_an_outside_directory(cli, sealed, tmp_path, check_summary):
    run = cli("render", "--corpus", str(sealed["root"]), "--limit", "10", "--format", "dot", "--out", str(tmp_path / "o"), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["corpus"]["state"] == "sealed" and summary["corpus"]["corpus_id"] == "tst-corpus"
    assert summary["counters"]["rendered"] == 1 and not any("not sealed" in n for n in summary["notices"])


@needs_pydot
def test_a_working_tree_is_found_by_its_final_name(cli, tmp_path):
    c = rs.build_corpus(tmp_path / "w" / "corp.partial", tmp_path)
    run = cli("render", "--corpus", str(tmp_path / "w" / "corp"), "--limit", "10", "--format", "dot", "--json")
    assert run.code == 0, run.err
    assert any("not sealed" in n for n in run.json()["notices"])
    assert len(dots(tmp_path / "w" / "corp-rendered")) == len(c["exs"])


# ------------------------------------------------------------------------------------------------ selection
@needs_pydot
def test_ex_select_and_limit(cli, corpus, tmp_path):
    first, second = corpus["exs"]
    one = tmp_path / "one"
    assert cli("render", "--corpus", str(corpus["root"]), "--ex", second, "--format", "dot", "--out", str(one)).code == 0
    assert list(dots(one)) == [f"{second}.dot"]
    by_task = tmp_path / "task"
    run = cli("render", "--corpus", str(corpus["root"]), "--select", "task=t1", "--limit", "5", "--format", "dot", "--out", str(by_task), "--json")
    assert run.code == 0 and run.json()["counters"]["selected"] == 1 and len(dots(by_task)) == 1
    none = cli("render", "--corpus", str(corpus["root"]), "--select", "task=nothing", "--limit", "5", "--format", "dot", "--out", str(tmp_path / "n"), "--json")
    assert none.code == 0 and none.json()["counters"]["selected"] == 0 and "no execution matched the selection" in none.json()["notices"]
    limited = tmp_path / "lim"
    assert cli("render", "--corpus", str(corpus["root"]), "--limit", "1", "--format", "dot", "--out", str(limited)).code == 0
    assert list(dots(limited)) == [f"{first}.dot"]  # index order
    zero = cli("render", "--corpus", str(corpus["root"]), "--limit", "0", "--format", "dot", "--out", str(tmp_path / "z"), "--json")
    assert zero.code == 0 and zero.json()["counters"]["rendered"] == 0


@needs_pydot
def test_an_invalid_prov_document_fails_only_its_execution(cli, broken, tmp_path):
    out = tmp_path / "o"
    run = cli("render", "--corpus", str(broken["root"]), "--limit", "10", "--format", "dot", "--out", str(out), "--json")
    assert run.code == 1
    summary = run.json()
    assert summary["counters"]["rendered"] == 1 and summary["counters"]["failed"] == 1
    assert [f["code"] for f in summary["failures"]] == ["render.invalid_prov"] and "Traceback" not in run.err
    assert len(dots(out)) == 1


@needs_pydot
def test_an_execution_without_prov_is_skipped_unless_named(cli, noprov, tmp_path):
    run = cli("render", "--corpus", str(noprov["root"]), "--limit", "10", "--format", "dot", "--out", str(tmp_path / "a"), "--json")
    assert run.code == 0 and run.json()["counters"]["skipped_no_prov"] == 1 and run.json()["counters"]["rendered"] == 1
    named = cli("render", "--corpus", str(noprov["root"]), "--ex", noprov["no_prov"][0], "--format", "dot", "--out", str(tmp_path / "b"), "--json")
    assert named.code == 1 and named.json()["failures"][0]["code"] == "render.no_prov"


# ------------------------------------------------------------------------------------------------ environment (exit 3)
def test_a_missing_extra_exits_3_with_the_hint(cli, corpus, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pydot", None)
    run = cli("render", "--corpus", str(corpus["root"]), "--limit", "10", "--out", str(tmp_path / "o"))
    assert run.code == 3 and "uv sync --frozen --group docs --extra render" in run.err
    assert not (tmp_path / "o").exists()


@needs_pydot
def test_a_missing_dot_binary_exits_3_but_dot_text_needs_none(cli, corpus, tmp_path, monkeypatch):
    from agentprov.render import dot as dotmod

    monkeypatch.setattr(dotmod.shutil, "which", lambda *_a, **_k: None)
    run = cli("render", "--corpus", str(corpus["root"]), "--limit", "10", "--format", "svg", "--out", str(tmp_path / "o"))
    assert run.code == 3 and "graphviz" in run.err.lower() and not (tmp_path / "o").exists()
    assert cli("render", "--corpus", str(corpus["root"]), "--limit", "10", "--format", "dot", "--out", str(tmp_path / "d")).code == 0


# ------------------------------------------------------------------------------------------------ dry run, determinism
@needs_pydot
def test_dry_run_builds_everything_and_writes_nothing(cli, corpus, tmp_path):
    out = tmp_path / "o"
    run = cli("render", "--corpus", str(corpus["root"]), "--limit", "10", "--format", "svg,dot", "--out", str(out), "--dry-run", "--json")
    assert run.code == 0 and run.json()["dry_run"] is True and run.json()["counters"]["rendered"] == 2
    assert run.json()["counters"]["files"] == 0 and not out.exists()


@needs_pydot
def test_dot_and_summary_are_byte_identical_across_runs_and_jobs(cli, corpus, tmp_path):
    outs, summaries = [], []
    for jobs in ("1", "3", "1"):
        out = tmp_path / f"o{len(outs)}"
        run = cli("render", "--corpus", str(corpus["root"]), "--limit", "10", "--bundle", "all", "--format", "dot", "--jobs", jobs, "--out", str(out), "--json")
        assert run.code == 0, run.err
        summary = run.json()
        summary["options"].pop("jobs"), summary["options"].pop("out")
        outs.append(dots(out))
        summaries.append(summary)
    assert outs[0] == outs[1] == outs[2] and len(outs[0]) == 2
    assert summaries[0] == summaries[1] == summaries[2]


@needs_pydot
def test_core_and_all_differ_and_all_marks_the_bundles(cli, corpus, tmp_path):
    for mode in ("core", "all"):
        assert cli("render", "--corpus", str(corpus["root"]), "--limit", "1", "--bundle", mode, "--format", "dot", "--out", str(tmp_path / mode)).code == 0
    core, everything = (next(iter(dots(tmp_path / m).values())).decode() for m in ("core", "all"))
    assert "assessment bundle" not in core and "cluster_" not in core and "fillcolor=\"#FFAAAA\"" not in core
    assert "assessment bundle" in everything and "subgraph cluster_" in everything and "integrity: untrusted" in everything


# ------------------------------------------------------------------------------------------------ images
@needs_dot
def test_svg_end_to_end_with_the_summary(cli, corpus, tmp_path, check_summary):
    out = tmp_path / "o"
    run = cli("render", "--corpus", str(corpus["root"]), "--limit", "1", "--format", "svg,png", "--out", str(out), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["counters"]["files"] == 3 and any(n.startswith("graphviz dot ") for n in summary["notices"])
    files = sorted(p.suffix for p in out.rglob("*.*") if p.is_file())
    assert files == [".dot", ".png", ".svg"]
    assert b"<svg" in next(out.rglob("*.svg")).read_bytes() and not list(out.rglob("*.tmp-*"))


# ------------------------------------------------------------------------------------------------ hostile content
@needs_pydot
def test_hostile_content_never_reaches_the_terminal_and_is_data_in_the_dot(cli, corpus, tmp_path):
    out = tmp_path / "o"
    run = cli("render", "--corpus", str(corpus["root"]), "--ex", corpus["exs"][0], "--bundle", "all", "--show-content", "--format", "dot", "--out", str(out), "--json")
    assert run.code == 0, run.err
    assert not rs.CONTROL.search(run.out) and not rs.CONTROL.search(run.err) and "\x1b" not in run.err + run.out
    text = next(iter(dots(out).values())).decode()
    assert not rs.CONTROL.search(text) and "<U+001B>" in text
    default = tmp_path / "d"
    assert cli("render", "--corpus", str(corpus["root"]), "--ex", corpus["exs"][0], "--format", "dot", "--out", str(default)).code == 0
    plain = next(iter(dots(default).values())).decode()
    assert not any(part in plain for part in rs.PAYLOAD_PARTS) and json.dumps(rs.payload())[1:20] not in plain


# ------------------------------------------------------------------------------------------------ layout limit
@needs_pydot
def test_a_graph_over_the_layout_limit_gets_its_dot_text_and_a_clear_failure_without_running_dot(
    cli, corpus, tmp_path, monkeypatch
):
    """CLI robustness item 6: a large ``--bundle all`` graph ran into dot's 120 s timeout; it now fails at once with
    ``render.graph_too_large``, keeps the .dot text and names the remedies. ``dot`` is never started."""
    from agentprov.render import dot as dotmod

    def no_dot(*args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("dot was started for a graph over the limit")

    monkeypatch.setattr(dotmod, "run_dot", no_dot)
    monkeypatch.setattr(dotmod, "find_dot", lambda: "/usr/bin/false")
    monkeypatch.setattr(dotmod, "graphviz_version", lambda exe: None)
    out = tmp_path / "o"
    run = cli("render", "--corpus", str(corpus["root"]), "--limit", "2", "--bundle", "all", "--format", "svg",
              "--max-edges", "1", "--out", str(out), "--json")
    assert run.code == 1, run.err
    summary = run.json()
    assert summary["issues_by_code"] == {"render.graph_too_large": 2} and summary["counters"]["rendered"] == 0
    assert "too large to lay out as an image (limit 1 edges" in run.err and "--bundle core" in run.err
    assert len(dots(out)) == 2 and not list(out.rglob("*.svg"))
    dry = cli("render", "--corpus", str(corpus["root"]), "--limit", "2", "--bundle", "all", "--max-edges", "1",
              "--out", str(tmp_path / "dry"), "--dry-run", "--json")
    assert dry.code == 1 and dry.json()["issues_by_code"] == {"render.graph_too_large": 2}
    assert not (tmp_path / "dry").exists()
    text_only = cli("render", "--corpus", str(corpus["root"]), "--limit", "2", "--bundle", "all", "--format", "dot",
                    "--max-edges", "1", "--out", str(tmp_path / "t"))
    assert text_only.code == 0, text_only.err  # no image, no layout: the limit does not apply


def test_the_default_layout_limit_keeps_dot_inside_its_timeout():
    from agentprov.render import dot as dotmod

    assert dotmod.MAX_LAYOUT_EDGES == 800 and dotmod.DOT_TIMEOUT_S == 120.0  # research §M7b: 983 edges took 114 s
