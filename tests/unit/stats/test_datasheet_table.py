"""The datasheet's field-group table (HL H.9; R-57): the rows of ``agentprov stats --tables field_groups``, as Markdown."""

from __future__ import annotations

import pytest

from agentprov.stats import open_corpus
from agentprov.stats.datasheet import COLUMNS, DatasheetFailuresError, datasheet_field_groups, render_rows, renderer
from agentprov.stats.exclusions import declared_exclusions
from agentprov.stats.tables import compute_corpus
from agentprov.testing.fs_guard import unchanged
from stats_support import Execution, agent_records, build_corpus, ex_id, standard_corpus


def test_the_table_has_one_line_per_stats_row(tmp_path):
    built = standard_corpus(tmp_path / "c.partial")
    with unchanged(built["root"]):
        text = datasheet_field_groups(built["root"])
    rows = compute_corpus(open_corpus(built["root"], verify="none"), tables=("field_groups",),
                          exclusions=declared_exclusions()).tables["field_groups"]
    lines = text.splitlines()
    assert lines[0] == "| " + " | ".join(COLUMNS) + " |"
    assert len(lines) == 2 + len(rows)
    assert sum(1 for line in lines if "| all |" in line) == sum(1 for r in rows if r["group"] == "all") >= 1


def test_the_renderer_is_deterministic_and_ignores_the_manifest(tmp_path):
    built = standard_corpus(tmp_path / "c.partial")
    render = renderer(built["root"])
    assert render({}) == render({"corpus_id": "other"}) == datasheet_field_groups(built["root"])


def test_an_execution_that_cannot_be_evaluated_refuses_the_table(tmp_path):
    # one of two agent executions carries an invalid evidence tag: compute_corpus counts it as a failure
    # (stats.aer.tag) and its cells are missing, so a rendered row would claim 2 executions over 1 execution's cells
    good = agent_records(ex_id(0))
    bad = agent_records(ex_id(0))
    for record in bad:
        if record.get("id") == "mc0":
            record["evf"]["/input"] = "Z"
    built = build_corpus(tmp_path / "c.partial", [Execution(records=bad), Execution(records=good)])
    with unchanged(built["root"]), pytest.raises(DatasheetFailuresError) as caught:
        renderer(built["root"])({})
    assert caught.value.code == "stats.datasheet.failures"
    assert caught.value.exit_code == 1
    assert "stats.aer.tag=1" in str(caught.value)


@pytest.mark.parametrize(("o", "d", "denominator", "coverage", "observed"), [
    (72, 0, 109, "0.6606", "0.6606"),  # 72/109 = 0.660550...: share() gives 0.66055, which :.4f printed as 0.6605
    (1, 0, 113, "0.0088", "0.0088"),  # 1/113 = 0.0088495...: share() gives 0.00885, printed as 0.0089
    (36, 36, 109, "0.6606", "0.3303"),
    (1, 0, 32, "0.0312", "0.0312"),  # an exact tie (0.03125) rounds half to even
    (0, 0, 0, "-", "-"),  # an empty denominator
])  # fmt: skip
def test_shares_are_rounded_once_from_the_counts(o, d, denominator, coverage, observed):
    """AU-MSR-2: the coverage cells were rounded twice (six decimals in ``share()``, then four in the cell), so about
    0.5 % of them showed a wrong fourth decimal. The cells are now computed from the integer columns, rounded once."""
    row = {"source_id": "s", "profile": "p@1", "group": "g", "n_executions": 1, "cells": denominator + 2,
           "not_applicable": 2, "O": o, "D": d, "I": denominator - o - d,
           "coverage": None if denominator == 0 else round((o + d) / denominator, 6),
           "observed_share": None if denominator == 0 else round(o / denominator, 6)}
    (line,) = render_rows([row]).splitlines()[2:]
    cells = dict(zip(COLUMNS, (c.strip() for c in line.strip("|").split("|")), strict=True))
    assert (cells["coverage"], cells["observed_share"]) == (coverage, observed)
