"""D-706: the ``cell.<member>``, ``outcome.<claim>`` and ``issue`` selectors (the Viewer's filters, D-700), on a derived
corpus of three golden AgentDojo executions:

* ``workspace``, attacked (``important_instructions``), security false: ``attack_succeeded`` does not hold;
* ``banking``, attacked, security true: ``attack_succeeded`` holds;
* ``banking``, benign (``attack_id`` null), security true by the raw judgement, but SEM gives no ``attack_succeeded``
  claim on a benign cell: it is ``none`` (not judged), never ``true``.

Working rows (the corpus before ``derive``) have no cell or facets and match none of these keys.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov import api
from agentprov.cli.main import main
from agentprov.stats.source import SelectionError, normalise_select, outcome_states

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "corpus"))
import seal_support  # noqa: E402


@pytest.fixture(scope="module")
def corpora(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    working = Path(seal_support.working_corpus(tmp_path_factory, tmp_path_factory.mktemp("w") / "mini"))
    derived = tmp_path_factory.mktemp("d") / "derived"
    assert main(["derive", "--corpus", str(working), "--out", str(derived), "--progress", "off"]) == 0
    return working, derived


def _suites(root: Path, **select: Any) -> list[str]:
    corpus = api.open_corpus(root)
    return sorted(str(row.facet_members.cell.get("suite")) if row.facet_members else "-"
                  for row in api.iter_executions(corpus, select=select))


def test_cell_members_select(corpora: tuple[Path, Path]) -> None:
    _working, derived = corpora
    assert _suites(derived, **{"cell.suite": "banking"}) == ["banking", "banking"]
    assert _suites(derived, **{"cell.attack_id": "important_instructions"}) == ["banking", "workspace"]
    assert _suites(derived, **{"cell.defense_id": "spotlighting_with_delimiting"}) == ["workspace"]
    assert _suites(derived, **{"cell.suite_set": "not_recorded"}) == []  # an unknown member never matches


def test_outcome_claims_select(corpora: tuple[Path, Path]) -> None:
    _working, derived = corpora
    assert _suites(derived, **{"outcome.attack_succeeded": "true"}) == ["banking"]
    assert _suites(derived, **{"outcome.attack_succeeded": "false"}) == ["workspace"]
    assert _suites(derived, **{"outcome.attack_succeeded": "none"}) == ["banking"]  # the benign cell
    assert _suites(derived, **{"outcome.user_task_solved": ["true", "false"]}) == ["banking", "banking", "workspace"]
    both = {"outcome.attack_succeeded": "true", "cell.suite": "workspace"}
    assert _suites(derived, **both) == []


def test_working_rows_match_no_cell_or_outcome_key(corpora: tuple[Path, Path]) -> None:
    working, _derived = corpora
    assert _suites(working, **{"cell.suite": "banking"}) == []
    assert _suites(working, **{"outcome.attack_succeeded": "none"}) == []  # nothing is known about them


def test_issue_selects_rows_with_that_code(corpora: tuple[Path, Path]) -> None:
    _working, derived = corpora
    corpus = api.open_corpus(derived)
    codes = sorted({c for row in api.iter_executions(corpus) for c in row.issues})
    if codes:
        with_code = [r for r in api.iter_executions(corpus) if codes[0] in r.issues]
        assert len(list(api.iter_executions(corpus, select={"issue": codes[0]}))) == len(with_code)
    assert list(api.iter_executions(corpus, select={"issue": "no.such.code"})) == []


@pytest.mark.parametrize("select", [{"outcome.attack_succeeded": "yes"}, {"cell.": "x"}, {"outcome.": "true"},
                                    {"nosuch": "x"}])
def test_bad_selectors_are_refused(select: dict[str, str]) -> None:
    with pytest.raises(SelectionError):
        normalise_select(select)


def test_outcome_states_reads_holds_only() -> None:
    outcome = [{"claim": "attack_succeeded", "holds": True}, {"claim": "attack_succeeded", "holds": None},
               {"claim": "user_task_solved", "holds": False}, "not an element"]
    assert outcome_states(outcome, "attack_succeeded") == ["true"]
    assert outcome_states(outcome, "user_task_solved") == ["false"]
    assert outcome_states(outcome, "attack_goal_progress") == ["none"]
    assert outcome_states(None, "attack_succeeded") == ["none"]


def test_the_cli_takes_the_new_keys(corpora: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    import json

    _working, derived = corpora
    capsys.readouterr()
    assert main(["stats", "--corpus", str(derived), "--tables", "counts", "--select", "outcome.attack_succeeded=true",
                 "--select", "cell.suite=banking", "--format", "json", "--progress", "off"]) == 0
    assert json.loads(capsys.readouterr().out)["corpora"][0]["population"]["selected"] == 1
    assert main(["stats", "--corpus", str(derived), "--select", "outcome.attack_succeeded=maybe", "--progress",
                 "off"]) == 2
