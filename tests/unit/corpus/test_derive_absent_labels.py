"""The labels a re-map accounts for executions that need an object absent on purpose (RC-2; RC-14, RC-16).

``Derivation._labels_of_executions`` returns the input labels whose register, origin and member rows the corpus-file
comparison does not hold against the re-map. RC-14: an input that a verified execution also uses (a task's
configuration) is never among them, so a real change to it is reported. RC-16: each label is its JCS string, the bytes the
corpus rows hold (raw UTF-8), so a non-ASCII label matches its rows.
"""

from __future__ import annotations

from types import SimpleNamespace

from agentprov.corpus.derive import Derivation
from agentprov.io.canonical import jcs_bytes
from agentprov.raw.origins import Origin, OriginRow

REPO, COMMIT = "https://example.invalid/runs", "a" * 40
JUDGE, CONFIG, ACCENTED = "x/32/judge_result.json", "tasks/t1/config.yaml", "x/é/judge_result.json"


def _sha(n: int) -> str:
    return f"{n:064x}"


def _derivation() -> SimpleNamespace:
    ref = lambda n, role="auxiliary": SimpleNamespace(sha256=_sha(n), role=role)  # noqa: E731
    rows = [
        SimpleNamespace(ex="ex_absent", raw=[ref(1, "primary"), ref(2), ref(3)]),   # needs the absent object 1
        SimpleNamespace(ex="ex_absent2", raw=[ref(4, "primary"), ref(5)]),          # needs the absent object 4
        SimpleNamespace(ex="ex_verified", raw=[ref(6, "primary"), ref(3)]),         # shares the configuration 3
    ]
    origins = [
        OriginRow(_sha(2), Origin.git(REPO, COMMIT, JUDGE, "b" * 40)),
        OriginRow(_sha(3), Origin.git(REPO, COMMIT, CONFIG, "c" * 40)),
        OriginRow(_sha(5), Origin.git(REPO, COMMIT, ACCENTED, "d" * 40)),
        OriginRow(_sha(6), Origin.git(REPO, COMMIT, "y/1/trajectory.json", "e" * 40)),
    ]
    stub = SimpleNamespace(src_rows=rows, src=SimpleNamespace(origins=lambda: origins))
    stub._inputs_of = lambda executions: Derivation._inputs_of(stub, executions)  # type: ignore[arg-type]
    return stub


def test_only_labels_used_exclusively_by_absent_dependent_executions_are_accounted_rc14():
    labels = Derivation._labels_of_executions(_derivation(), {"ex_absent", "ex_absent2"})  # type: ignore[arg-type]
    assert jcs_bytes(JUDGE).decode() in labels
    assert jcs_bytes(CONFIG).decode() not in labels  # a verified execution uses it: a change there must be reported
    assert jcs_bytes("y/1/trajectory.json").decode() not in labels
    assert Derivation._labels_of_executions(_derivation(), set()) == set()  # type: ignore[arg-type]


def _reader(files: dict[str, bytes]) -> SimpleNamespace:
    return SimpleNamespace(exists=lambda label: label in files, read_bytes=lambda label: files[label])


def test_the_corpus_file_comparison_counts_a_duplicated_row_and_ignores_order_rc13():
    """RC-13: the comparison used line sets, so a row written twice by the re-map was not a difference. It is now a
    multiset comparison; the order stays uncompared (a re-map writes carried rows before re-derived ones)."""
    rows = b'{"code":"a"}\n{"code":"b"}\n'
    stub = SimpleNamespace(src=_reader({"register.jsonl": rows}), absent={}, absent_ex=set(), withheld_ex=set(),
                           absent_labels=set())
    report = SimpleNamespace(corpus_changes=[])
    duplicated = _reader({"register.jsonl": rows + b'{"code":"b"}\n'})
    assert Derivation._compare_corpus_files(stub, duplicated, report, {}) == 1  # type: ignore[arg-type]
    assert report.corpus_changes == [{"file": "register.jsonl", "explained": False, "removed": 0, "added": 1}]
    report.corpus_changes.clear()
    reordered = _reader({"register.jsonl": b'{"code":"b"}\n{"code":"a"}\n'})
    assert Derivation._compare_corpus_files(stub, reordered, report, {}) == 0  # type: ignore[arg-type]
    assert report.corpus_changes == []


def test_a_non_ascii_label_matches_its_jcs_rows_rc16():
    labels = Derivation._labels_of_executions(_derivation(), {"ex_absent", "ex_absent2"})  # type: ignore[arg-type]
    (token,) = [t for t in labels if "judge_result" in t and "32" not in t]
    row = jcs_bytes({"code": "select.not_execution_artefact", "subject": {"path": ACCENTED, "snapshot_id": "head"}})
    assert token.encode() in row  # the comparison's test: ``t.encode() in line``
    assert "\\u00e9" not in token
