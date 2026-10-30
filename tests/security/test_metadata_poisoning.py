"""SEC-21 (K.12.4, K.12.7; T-19): hostile benchmark metadata never alters paths, identity or the code that runs.

Suite, task, pipeline, attack and version values are data from the log. They may end up as recorded values (``O`` data
``by: source``) or as issues; they must never become a path component, an execution id component or a selector of
code. Generic ``activity``/``artefact`` ``type`` labels must be declared in the family catalogue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import agentdojo_support as ad
import pytest
from aer_support import codes_of, example_records, insert_after, validate_example
from import_harness import ALLOWED_PATHS, EX, run_import

ESC, NUL, RLO = chr(0x1B), chr(0x00), chr(0x202E)
HOSTILE = {
    "dotdot": "a/../../b",
    "absolute": "/etc/passwd",
    "backslash": "..\\..\\x",
    "nul": f"x{NUL}y",
    "ansi": f"{ESC}[31mred{ESC}[0m",
    "bidi": f"safe{RLO}txt.exe",
    "long": "L" * 10_000,
}
FIELDS = ("suite_name", "user_task_id", "injection_task_id", "pipeline_name", "attack_type")


def _clean_path(n: int) -> str:
    return f"runs/gpt-4o-2024-05-13/banking/user_task_{n}/important_instructions/injection_task_2.json"


@pytest.fixture(scope="module")
def poisoned(tmp_path_factory: pytest.TempPathFactory) -> Any:
    files: dict[str, bytes] = {}
    cases: list[tuple[str, str]] = []
    for field in FIELDS:
        for label, value in HOSTILE.items():
            n = len(cases)
            files[_clean_path(n)] = ad.log_bytes(ad.base_log(**{field: value}, user_task_id=f"user_task_{n}")
                                                 if field != "user_task_id" else ad.base_log(user_task_id=value))
            cases.append((field, label))
    return run_import(tmp_path_factory.mktemp("poison"), files), cases


def test_sec21_hostile_metadata_values_never_reach_a_written_path(poisoned: Any) -> None:
    imported, cases = poisoned
    files = imported.files()
    assert files and all(ALLOWED_PATHS.fullmatch(f) for f in files), [f for f in files if not ALLOWED_PATHS.fullmatch(f)]
    joined = "\n".join(files)
    for value in HOSTILE.values():
        assert value[:12] not in joined


def test_sec21_every_unit_seals_and_execution_ids_keep_their_grammar(poisoned: Any) -> None:
    import re

    imported, cases = poisoned
    report = imported.report
    assert report.counters["seen"] == len(cases)
    assert report.counters["failed"] == 0, report.failures  # a hostile value is data: sealed (with issues), never lost
    rows = imported.rows("executions.jsonl")
    assert len(rows) == len(cases) and all(re.fullmatch(EX, r["ex"]) for r in rows)
    assert len({r["ex"] for r in rows}) == len(rows)


def test_sec21_identity_comes_from_the_path_not_from_a_hostile_pipeline_name(poisoned: Any) -> None:
    import json

    imported, _ = poisoned
    models = set()
    for data in imported.aers().values():
        for line in data.splitlines():
            rec = json.loads(line)
            if rec.get("k") == "actor" and rec.get("kind") == "llm_agent":
                models.add(json.dumps(rec.get("model"), sort_keys=True))
    assert models and all("etc/passwd" not in m and "../" not in m and ESC not in m for m in models)


def test_sec21_a_hostile_directory_name_is_a_rejected_label_not_a_path(tmp_path: Path) -> None:
    doc = ad.base_log()
    hostile_dirs = {"ansi": f"runs/gpt-4o-2024-05-13/bank{ESC}[2Jing/user_task_1/none/none.json",
                    "bidi": f"runs/gpt-4o-2024-05-13/banking/user_task_1/none/no{RLO}ne.json"}
    imported = run_import(tmp_path, {path: ad.log_bytes(doc) for path in hostile_dirs.values()})
    assert all(ALLOWED_PATHS.fullmatch(f) for f in imported.files())
    joined = "\n".join(imported.files())
    assert ESC not in joined and RLO not in joined


# --------------------------------------------------------------------------------- generic kinds (AD-15)
def _activity(**kw: Any) -> dict[str, Any]:
    rec = {"k": "activity", "id": "ac0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:plan", "actor": "agent",
           "scope": "att0", "inputs": ["m0"], "status": "ok", "label": "plan"}
    rec.update(kw)
    return rec


def _artefact(**kw: Any) -> dict[str, Any]:
    rec = {"k": "artefact", "id": "af0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:note", "content": {"steps": ["a"]},
           "generated_by": "ac0", "media": "application/json"}
    rec.update(kw)
    return rec


def _codes(*extra: dict[str, Any]) -> list[str]:
    recs, anchor = example_records(), "m0"
    for rec in extra:
        recs = insert_after(recs, anchor, rec)
        anchor = rec["id"]
    return codes_of(validate_example(recs))


@pytest.mark.parametrize("value", ["tst:undeclared", "tst:../x", f"tst:a{NUL}b", f"tst:{ESC}[31m", "tst:" + "x" * 10_000,
                                   f"tst:pl{RLO}an", "../tst:plan", "tst:plan/../note"])
def test_sec21_undeclared_or_hostile_generic_types_are_rejected_for_both_kinds(value: str) -> None:
    rejected = {"aer.subtype.undeclared", "aer.schema.pattern", "aer.ext.undeclared"}
    assert rejected & set(_codes(_activity(type=value)))
    assert rejected & set(_codes(_activity(), _artefact(type=value)))


def test_sec21_declared_generic_types_validate_for_both_kinds() -> None:
    assert _codes(_activity(), _artefact()) == []
