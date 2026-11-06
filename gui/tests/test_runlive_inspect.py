"""Run Live with an Inspect backend (D-1120): the Inspect catalogue (``agentprov-inspect-catalogue/0.1``) is parsed
strictly, AgentHarm's task, parameters, samples, limits and judges are rows of the form, the AgentDojo-only rows are
hidden, and the command card, the estimate and Start carry exactly the argv the CLI accepts (checked by the CLI's own
parser and Inspect plan builder in a subprocess: the GUI never imports ``agentprov.cli``). The AgentDojo path is
unchanged."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.live.plan import PlanError, parse_any_catalogue, parse_inspect_catalogue
from test_g3_live import CATALOGUE, wait
from test_runlive_form import QUOTE, _dialog, quoting_run

REPO = Path(__file__).resolve().parents[2]
_PARAMS = [
    {"choices": ["test_public", "val"], "default": "test_public", "name": "split", "type": "str"},
    {"choices": ["default", "refusal"], "default": "default", "name": "agent", "type": "str"},
    {"default": None, "name": "detailed_behaviors", "type": "bool|null"},
    {"default": None, "name": "hint_included", "type": "bool|null"},
    {"default": 0, "maximum": 64, "minimum": 0, "name": "n_irrelevant_tools", "type": "int"},
    {"choices": ["auto", "forced_first", "none"], "default": "auto", "maps_to": "agent_kwargs.tool_choice",
     "name": "tool_choice", "type": "str"},
    {"choices": ["standard", "cot", "react", "refusal"], "default": "standard",
     "maps_to": "agent_kwargs.prompt_technique", "name": "prompt_technique", "type": "str"},
]
_TASK = {"default_solver": "default", "fixed": {"max_messages": 20, "max_retries": 3, "max_tokens": 4096, "seed": 0,
                                                "temperature": 0},
         "name": "inspect_evals/agentharm", "params": _PARAMS,
         "scorers": [{"judge_roles": [{"calls_per_sample": "varies", "default_model": "openai/gpt-4o-2024-08-06",
                                       "role": "refusal_judge"},
                                      {"calls_per_sample": "varies", "default_model": "openai/gpt-4o-2024-08-06",
                                       "role": "semantic_judge"}], "name": "combined_scorer"}],
         "solvers": ["default", "refusal"],
         "splits": [{"name": "test_public", "samples": 176, "tool_definition_chars": {"max": 3286, "mean": 1321}},
                    {"name": "val", "samples": 32, "tool_definition_chars": {"max": 1439, "mean": 953}}]}
#: ``agentprov run agentharm --catalogue`` as the CLI printed it on 2026-11-06 (inspect-agentharm-f698b6d1)
INSPECT_CATALOGUE: dict[str, Any] = {
    "backend": "inspect-agentharm", "benchmark": "agentharm",
    "dataset": {"repo": "ai-safety-institute/AgentHarm", "revision": "e23b3fe60a0da9037314b88e5ee3a0c054970dad"},
    "format": "agentprov-inspect-catalogue/0.1", "inspect_ai": "0.3.263",
    "tasks": [_TASK, {**copy.deepcopy(_TASK), "name": "inspect_evals/agentharm_benign"}]}


def inspect_run(calls: list[list[str]], catalogue: Any = None, quote: dict[str, Any] | None = None) -> Any:
    """The Run Live fake, with ``agentharm`` answering an Inspect catalogue and an Inspect estimate."""
    base = quoting_run(calls, quote)
    doc = INSPECT_CATALOGUE if catalogue is None else catalogue

    def run(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if argv[-1] == "agentharm" and "--catalogue" in argv:
            calls.append(list(argv))
            return 0, (doc if isinstance(doc, bytes) else json.dumps(doc).encode()), b""
        if argv[0] == "estimate" and argv[-1] == "agentharm":
            calls.append(list(argv))
            scripted = "--llm-script" in argv
            est = {"format": "agentprov-estimate/0.1", "units": 2, "attempts_due": 6,
                   "cost_p50": "0" if scripted else "0.0017", "cost_p90": "0" if scripted else "0.0102",
                   "cost_worst": "0" if scripted else "0.0343", "seconds_p50": 60.0, "seconds_p90": 180.0,
                   "price": None, "planned_with": "model", "plan": {"plan_sha256": "0" * 64}, "warnings": [],
                   "text": ["2 cell run(s); scripted transport: no cost." if scripted else "≈ $0.0017 (p90 $0.0102)",
                            "Plan 0000…: 2 cells", "Inspect inspect_evals/agentharm: 2 sample(s) × 1 epoch(s)"]}
            if quote is not None and not scripted:
                est["quote"] = quote
            return 0, json.dumps(est).encode(), b""
        return base(manager, argv, **kw)

    return run


def _inspect_dialog(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, scripted: bool = True,
                    catalogue: Any = None, quote: dict[str, Any] | None = None) -> Any:
    calls: list[list[str]] = []
    dlg = _dialog(tmp_path, monkeypatch, scripted=scripted, run=inspect_run(calls, catalogue, quote))
    dlg.calls = calls
    dlg.source.setCurrentIndex(dlg.source.findData("agentharm"))
    wait(qapp, lambda: "agentharm" in dlg.catalogues and "agentharm" in dlg.live_status and dlg.prices is not None)
    qapp.processEvents()
    return dlg


def _fill(dlg: Any, *, samples: int = 2) -> None:
    dlg.sample_count.setValue(samples)
    dlg.limit_inputs["message_limit"].setValue(10)
    dlg.limit_inputs["token_limit"].setValue(20000)
    dlg.limit_inputs["time_limit"].setValue(600)


def _param(dlg: Any, name: str) -> Any:
    return dlg.param_inputs[name][1]


def _choose(box: Any, text: str) -> None:
    index = next(i for i in range(box.count()) if box.itemText(i).split(" (")[0] == text)
    box.setCurrentIndex(index)


def _cli_plan(argv: list[str]) -> dict[str, Any]:
    """The CLI's own reading of a ``run`` argv: its parser, then its Inspect plan builder (``_inspect_document``),
    in a child interpreter (``-I``), as test_cli_parity reads the CLI's tree."""
    code = (
        "import json, sys\n"
        "from agentprov.cli.main import build_parser\n"
        "from agentprov.cli import run\n"
        "args = build_parser().parse_args(json.loads(sys.argv[1]))\n"
        "agent = {'model_requested': args.model_id or 'scripted-fake', 'endpoint': 'scripted'}\n"
        "print(json.dumps(run._inspect_document(args, agent, 'inspect-agentharm')))\n")
    done = subprocess.run([sys.executable, "-I", "-c", code, json.dumps(argv)], capture_output=True, text=True,
                          check=False, cwd=REPO)
    assert done.returncode == 0, done.stderr[-2000:]
    plan: dict[str, Any] = json.loads(done.stdout)
    return plan


# ------------------------------------------------------------------------------------------------- parsing
def test_the_inspect_catalogue_parses_with_its_tasks_params_and_judges() -> None:
    cat = parse_inspect_catalogue(json.dumps(INSPECT_CATALOGUE).encode())
    assert cat.backend == "inspect-agentharm" and cat.benchmark == "agentharm" and cat.inspect_ai == "0.3.263"
    assert cat.dataset_repo == "ai-safety-institute/AgentHarm" and cat.dataset_revision.startswith("e23b3fe6")
    assert [t.name for t in cat.tasks] == ["inspect_evals/agentharm", "inspect_evals/agentharm_benign"]
    task = cat.task("inspect_evals/agentharm")
    assert task is not None and task.default_solver == "default" and task.solvers == ("default", "refusal")
    assert [p.name for p in task.params] == [p["name"] for p in _PARAMS]
    n = task.param("n_irrelevant_tools")
    assert n is not None and (n.type, n.default, n.minimum, n.maximum) == ("int", 0, 0, 64)
    hint = task.param("hint_included")
    assert hint is not None and hint.type == "bool|null" and hint.default is None and hint.choices == ()
    assert task.param("tool_choice").choices == ("auto", "forced_first", "none")  # type: ignore[union-attr]
    assert [(s.name, s.samples) for s in task.splits] == [("test_public", 176), ("val", 32)]
    assert [(j.role, j.calls_per_sample) for j in task.judges] == [("refusal_judge", None), ("semantic_judge", None)]
    assert dict(task.fixed) == {"max_messages": 20, "max_retries": 3, "max_tokens": 4096, "seed": 0, "temperature": 0}
    assert parse_any_catalogue(json.dumps(INSPECT_CATALOGUE).encode()) == cat
    assert parse_any_catalogue(json.dumps(CATALOGUE).encode()).suites[0].name == "banking"  # AgentDojo as before


def _broken(**changes: Any) -> bytes:
    doc = copy.deepcopy(INSPECT_CATALOGUE)
    task = doc["tasks"][0]
    for path, value in changes.items():
        target: Any = task
        *head, last = path.split(".")
        for part in head:
            target = target[int(part)] if part.isdigit() else target[part]
        target[int(last) if last.isdigit() else last] = value
    return json.dumps(doc).encode()


@pytest.mark.parametrize("data", [
    _broken(name="../../etc/passwd"),  # a path, not a registry name
    _broken(name="inspect_evals/<b>x</b>"),  # markup
    _broken(**{"params.0.name": "split/x"}),  # a parameter name with a slash
    _broken(**{"params.0.name": "agent"}),  # a duplicate parameter
    _broken(**{"params.2.type": "float"}),  # a type the CLI never declares
    _broken(**{"params.2.minimum": 0}),  # bounds on a bool|null
    _broken(**{"params.4.default": 99}),  # a default outside its bounds
    _broken(**{"params.4.default": True}),  # a bool for an int
    _broken(**{"params.0.choices": ["a"] * 65}),  # too many choices
    _broken(**{"params.0.choices": ["val", "val"]}),  # duplicate choices
    _broken(**{"splits.0.samples": -1}),
    _broken(**{"scorers.0.judge_roles.0.role": "Refusal Judge"}),  # not a role --judge takes
    _broken(**{"scorers.0.judge_roles.0.default_model": "a\nb"}),
    json.dumps({**INSPECT_CATALOGUE, "tasks": None}).encode(),
    json.dumps({**INSPECT_CATALOGUE, "tasks": [_TASK] * 2}).encode(),  # duplicate tasks
    json.dumps({**INSPECT_CATALOGUE, "tasks": "x"}).encode(),
    json.dumps({**INSPECT_CATALOGUE, "format": "agentprov-inspect-catalogue/9"}).encode(),
    b'{"format": "agentprov-inspect-catalogue/0.1", "backend": "x", "backend": "y"}',  # duplicate keys
    b"[]", b"\xff\xfe", b'{"format": NaN}',
], ids=lambda _d: "case")
def test_a_hostile_inspect_catalogue_is_refused(data: bytes) -> None:
    with pytest.raises(PlanError):
        parse_any_catalogue(data)


def test_unknown_members_are_dropped_and_odd_facts_ignored() -> None:
    doc = copy.deepcopy(INSPECT_CATALOGUE)
    doc["tasks"][0]["fixed"] = {"max_messages": 20, "note": "<script>", "flag": True, "huge": 1e300}
    doc["tasks"][0]["extra"] = {"anything": 1}
    doc["inspect_ai"] = "<b>"
    task = parse_inspect_catalogue(json.dumps(doc).encode()).tasks[0]
    assert task.fixed == (("max_messages", 20),)
    assert parse_inspect_catalogue(json.dumps(doc).encode()).inspect_ai == ""


def test_the_gui_mirrors_of_cli_rules_are_pinned() -> None:
    """D-391: the GUI copies these CLI and backend constants instead of importing them; a change there fails here."""
    from agentprov_gui.live import inspectplan, plan

    cat_src = (REPO / "src/agentprov/cli/live/inspect_catalogue.py").read_text(encoding="utf-8")
    assert f're.compile(r"{plan._TASK.pattern}")' in cat_src and f're.compile(r"{plan._ILABEL.pattern}")' in cat_src
    assert 'frozenset({"str", "int", "bool|null"})' in cat_src
    run_src = (REPO / "src/agentprov/cli/run.py").read_text(encoding="utf-8")
    assert f'"model_requested": args.model_id or "{inspectplan.SCRIPTED_MODEL}"' in run_src
    assert 'backend.startswith("inspect-")' in run_src
    assert 're.fullmatch(r"[a-z][a-z0-9_]{0,63}", role)' in run_src  # --judge ROLE=MODEL
    assert "tomllib.loads(f\"v = {raw}\")" in run_src  # --task-param reads a TOML scalar, else the text
    assert '"defence",\n)' in run_src  # the last of _CELL_OPTIONS
    plan_src = (REPO / "backends/inspect/src/agentprov_backend_inspect/plan.py").read_text(encoding="utf-8")
    assert 'MAX_LIMITS = {"message_limit": 500, "token_limit": 10_000_000, "time_limit_s": 86_400}' in plan_src
    assert "1 <= epochs <= 10" in plan_src and "1 <= max_connections <= 64" in plan_src
    assert "1 <= cell_size <= 500" in plan_src and 'ins.get("cell_size", 25)' in plan_src
    assert 'ins.get("max_connections", 4)' in plan_src
    assert inspectplan.LIMIT_BOUNDS["message_limit"] == (1, 500) and inspectplan.LIMIT_BOUNDS["cell_size"] == (1, 500)
    assert f'_ID = re.compile(r"{inspectplan._SAMPLE_ID.pattern}")' in plan_src


def test_the_inspect_dev_script_is_a_combined_script_of_its_size() -> None:
    from agentprov_gui.live.inspectplan import DEV_SAMPLES, INSPECT_DEV_SCRIPT

    doc = json.loads(INSPECT_DEV_SCRIPT.read_text(encoding="utf-8"))
    assert len(doc["agent"]) == DEV_SAMPLES
    roles = {j["role"] for j in _TASK["scorers"][0]["judge_roles"]}  # type: ignore[index]
    assert set(doc["judges"]) == roles and all(len(v) == 4 * DEV_SAMPLES for v in doc["judges"].values())
    assert all(step["reply"] == "text" for step in doc["agent"])


def test_task_params_are_written_as_the_cli_reads_them() -> None:
    from agentprov_gui.live.inspectplan import param_arg

    assert param_arg("split", "val") == "split=val"
    assert param_arg("tool_choice", "none") == "tool_choice=none"
    assert param_arg("x", "true") == 'x="true"' and param_arg("x", "12") == 'x="12"'  # would read as bool / int
    assert param_arg("x", "1979-05-27") == 'x="1979-05-27"'  # a TOML date
    assert param_arg("detailed_behaviors", True) == "detailed_behaviors=true"
    assert param_arg("n_irrelevant_tools", 3) == "n_irrelevant_tools=3"


# ------------------------------------------------------------------------------------------------- the form
def test_an_inspect_backend_shows_its_task_rows_and_hides_the_agentdojo_ones(
        qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch)
    dlg.show()
    qapp.processEvents()
    from agentprov_gui.ui.forms import IntField

    assert dlg.inspect_mode() and dlg.inspect_catalogue is not None
    assert not dlg.cells_section.isVisible() and not dlg.version_row.isVisible()
    assert not dlg.more_rows["defence"].isVisible()
    for w in (dlg.inspect_section, dlg.params_section, dlg.samples_section, dlg.inspect_more):
        assert w.isVisible()
    assert not dlg.judges_section.isVisible()  # scripted: the script answers for the judges
    assert [dlg.task.itemText(i) for i in range(dlg.task.count())] == [t["name"] for t in INSPECT_CATALOGUE["tasks"]]
    assert "2 tasks" in dlg.inspect_cat_label.text() and "inspect_ai 0.3.263" in dlg.inspect_cat_label.text()
    assert "max_messages 20" in dlg.fixed_label.text() and "solver default" in dlg.fixed_label.text()
    assert list(dlg.param_inputs) == [p["name"] for p in _PARAMS]
    split = _param(dlg, "split")
    assert [split.itemText(i) for i in range(split.count())] == ["test_public (default)", "val"]
    hint = _param(dlg, "hint_included")
    assert [hint.itemText(i) for i in range(hint.count())] == ["not set (default)", "true", "false"]
    n = _param(dlg, "n_irrelevant_tools")
    assert isinstance(n, IntField) and n.number() is None and n.maximum() == 64 and n.minimum() == -1
    assert "176 samples" in dlg.samples_row.caption.text()
    _choose(split, "val")
    assert "val has 32 samples" in dlg.samples_row.caption.text()
    assert dlg.script.text().endswith("scripted-dev-inspect.json")  # the combined dev script follows the backend
    assert "three per-sample limits" in dlg.error.text() or "samples" in dlg.error.text()
    assert not dlg.start_btn.isEnabled()
    dlg.mode.setCurrentIndex(1)  # Real model: one judge row per role
    qapp.processEvents()
    assert dlg.judges_section.isVisible() and list(dlg.judge_inputs) == ["refusal_judge", "semantic_judge"]
    dlg.close()


def test_the_scripted_argv_is_what_the_cli_reads_as_the_plan(qapp: Any, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import runlive

    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch)
    _fill(dlg)
    _choose(_param(dlg, "split"), "val")
    _choose(_param(dlg, "detailed_behaviors"), "true")
    _choose(_param(dlg, "tool_choice"), "none")
    _param(dlg, "n_irrelevant_tools").setValue(3)
    dlg.cell_inputs["cell_size"].setValue(1)
    wait(qapp, lambda: dlg.current_estimate() is not None)
    argv = list(dlg.run_spec().argv)
    corpus = str(tmp_path / "home" / "corpora" / "agentharm-live-t")
    assert argv == ["run", "--corpus", corpus, "--campaign", "t", "--task", "inspect_evals/agentharm",
                    "--task-param", "detailed_behaviors=true", "--task-param", "n_irrelevant_tools=3",
                    "--task-param", "split=val", "--task-param", "tool_choice=none", "--samples", "limit:2",
                    "--message-limit", "10", "--token-limit", "20000", "--time-limit", "600", "--cell-size", "1",
                    "--judge", "refusal_judge=scripted-fake", "--judge", "semantic_judge=scripted-fake",
                    "--llm-script", str(runlive.INSPECT_DEV_SCRIPT), "agentharm"]
    for banned in ("--suite", "--attack", "--benign", "--user-tasks", "--injection-tasks", "--benchmark-version",
                   "--defence"):
        assert banned not in argv
    plan = _cli_plan(argv)
    assert plan["inspect"] == {"task": "inspect_evals/agentharm", "samples": {"limit": 2}, "cell_size": 1,
                               "params": {"split": "val", "detailed_behaviors": True, "n_irrelevant_tools": 3,
                                          "tool_choice": "none"},
                               "limits": {"message_limit": 10, "token_limit": 20000, "time_limit_s": 600}}
    assert set(plan["judges"]) == {"refusal_judge", "semantic_judge"}
    estimate = [c for c in dlg.calls if c[0] == "estimate"][-1]
    assert estimate[estimate.index("--task") + 1] == "inspect_evals/agentharm"
    assert [estimate[i + 1] for i, x in enumerate(estimate) if x == "--task-param"] == [
        "detailed_behaviors=true", "n_irrelevant_tools=3", "split=val", "tool_choice=none"]
    ((comment, shown),) = dlg.command_card.commands
    assert comment == "" and list(shown) == argv  # a scripted run: the run's command alone
    assert "inspect_evals/agentharm · val · first 2 samples" in dlg.sub.text()
    assert dlg.start_btn.isEnabled(), dlg.error.text()
    monkeypatch.setattr(runlive, "confirm", lambda _p, spec, _a: spec)
    dlg._start(preflight=False)
    assert dlg.start is not None and list(dlg.start.spec.argv) == argv
    assert dlg.start.backend == "inspect-agentharm"


def test_sample_ids_and_defaults_left_out(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch)
    _fill(dlg)
    _choose(dlg.task, "inspect_evals/agentharm_benign")
    dlg.sample_mode.setCurrentIndex(1)
    dlg.sample_ids.setText("1-1, 2-3")
    argv = list(dlg.run_spec().argv)
    assert "--task-param" not in argv  # every parameter at its default
    assert argv[argv.index("--samples") + 1] == "1-1,2-3" and argv[argv.index("--task") + 1].endswith("_benign")
    assert _cli_plan(argv)["inspect"]["samples"] == {"ids": ["1-1", "2-3"]}
    dlg.sample_ids.setText("1-1, ../x")
    assert "Not sample ids" in dlg.error.text() and not dlg.start_btn.isEnabled()
    dlg.sample_mode.setCurrentIndex(0)
    dlg.sample_count.setValue(200)  # test_public has 176
    assert "at most that many" in dlg.error.text()
    dlg.close()


def test_a_real_model_run_has_judges_caps_and_the_consent(qapp: Any, tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch, scripted=False, quote=QUOTE)
    _fill(dlg)
    wait(qapp, lambda: dlg.current_estimate() is not None)
    argv = list(dlg.run_spec(consent=True).argv)
    assert [argv[i + 1] for i, x in enumerate(argv) if x == "--judge"] == ["refusal_judge=vendor/m",
                                                                           "semantic_judge=vendor/m"]
    assert "--keychain" in argv and "--i-consent-to-api-costs" in argv and "--llm-script" not in argv
    assert argv[argv.index("--model-id") + 1] == "vendor/m" and argv[argv.index("--containment") + 1] == "vm"
    estimate = [c for c in dlg.calls if c[0] == "estimate"][-1]
    assert "--judge" in estimate and "--message-limit" in estimate
    dlg.judge_inputs["semantic_judge"].setCurrentText("openai/gpt-4o-2024-08-06")
    qapp.processEvents()
    assert "every judge must use the agent's model" in dlg.error.text() and not dlg.start_btn.isEnabled()
    dlg.judge_inputs["semantic_judge"].setCurrentText("")
    dlg.max_calls.setValue(100)
    dlg.max_cost.setValue(1.0)
    wait(qapp, lambda: dlg.current_estimate() is not None)
    assert dlg.start_btn.isEnabled(), dlg.error.text()
    dlg.close()


def test_the_dev_script_capacity_is_checked(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch)
    _fill(dlg, samples=150)
    assert "answers 100 samples" not in dlg.error.text()  # the default cells of 25 fit
    dlg.cell_inputs["cell_size"].setValue(150)
    assert "answers 100 samples" in dlg.error.text() and not dlg.start_btn.isEnabled()
    dlg.cell_inputs["cell_size"].setValue(50)
    dlg.cell_inputs["epochs"].setValue(2)
    assert "answers 100 samples" not in dlg.error.text()
    dlg.close()


def test_a_hostile_or_mismatched_catalogue_launches_nothing(qapp: Any, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    for catalogue, words in ((_broken(name="../../x"), "catalogue unusable: malformed task name"),
                             (CATALOGUE, "catalogue unusable: not an Inspect catalogue"),
                             (b"\x00garbage", "catalogue unusable: not strict JSON")):
        dlg = _inspect_dialog(qapp, tmp_path, monkeypatch, catalogue=catalogue)
        assert words in dlg.inspect_cat_label.text() and words in dlg.error.text()
        assert dlg.task.count() == 0 and dlg.task.placeholderText().startswith("None")
        assert not dlg.start_btn.isEnabled() and "../../x" not in dlg.inspect_cat_label.text()
        dlg.close()


def test_the_agentdojo_path_is_unchanged(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Back on agentdojo after AgentHarm: no Inspect option in its argv, its rows and dev script back."""
    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch)
    _fill(dlg)
    dlg.source.setCurrentIndex(dlg.source.findData("agentdojo"))
    wait(qapp, lambda: dlg.current_estimate() is not None)
    dlg.show()
    qapp.processEvents()
    argv = list(dlg.run_spec().argv)
    assert argv[argv.index("--suite") + 1] == "banking" and argv[argv.index("--attack") + 1] == "direct"
    assert not re.search(r"--(task|task-param|samples|message-limit|token-limit|time-limit|judge|cell-size)\b",
                         " ".join(argv))
    assert dlg.cells_section.isVisible() and dlg.version_row.isVisible() and not dlg.inspect_section.isVisible()
    assert dlg.script.text().endswith("scripted-dev.json")
    dlg.close()


def test_the_plan_window_says_why_it_is_empty_and_never_shows_a_stale_plan(
        qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Show the plan before the form is complete says what is missing; once estimated it holds the CLI's breakdown;
    an estimate that fails afterwards leaves the reason, not the earlier selection's plan."""
    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch)
    dlg.refresh_estimate()
    assert dlg.details.toPlainText().startswith("No plan yet: choose the samples to run")
    dlg.show_plan()
    qapp.processEvents()
    assert dlg.details.isVisible() and dlg.details.toPlainText().startswith("No plan yet:")
    dlg.plan_dialog.reject()
    _fill(dlg)
    wait(qapp, lambda: dlg.current_estimate() is not None)
    assert "Inspect inspect_evals/agentharm: 2 sample(s)" in dlg.details.toPlainText()
    base = dlg.run

    def failing(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if argv[0] == "estimate":
            return 2, b"", b"agentprov estimate: the backend refused the plan"
        return base(manager, argv, **kw)

    dlg.run = failing
    dlg.limit_inputs["time_limit"].setValue(900)
    dlg.refresh_estimate()
    wait(qapp, lambda: "exit 2" in dlg.headline.text())
    text = dlg.details.toPlainText()
    assert text.startswith("No plan yet: agentprov estimate ended with exit 2") and "Inspect inspect_evals" not in text
    dlg.close()


def test_an_estimate_without_a_breakdown_says_so(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.live.plan import parse_estimate

    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch)
    dlg.estimate_result = parse_estimate(json.dumps({
        "format": "agentprov-estimate/0.1", "units": 1, "attempts_due": 3, "cost_p50": "0", "cost_p90": "0",
        "cost_worst": "0", "seconds_p50": 1.0, "seconds_p90": 2.0, "price": None, "planned_with": "model",
        "plan": {"plan_sha256": "0" * 64}, "warnings": [], "text": ["1 cell run(s); scripted transport: no cost."]}).encode())
    dlg.show_estimate()
    assert dlg.details.toPlainText().startswith("agentprov estimate gave no breakdown for this selection")
    dlg.close()


@pytest.mark.parametrize("scripted", [True, False], ids=["scripted", "real-model"])
def test_the_inspect_rows_have_tooltips(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                        scripted: bool) -> None:
    from test_tooltip_coverage import _report, gaps

    dlg = _inspect_dialog(qapp, tmp_path, monkeypatch, scripted=scripted, quote=QUOTE)
    _fill(dlg)
    found = gaps(dlg, minimum=60)
    dlg.close()
    assert not found, _report(found)
