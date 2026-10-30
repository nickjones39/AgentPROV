"""The corpus pre-check's Level-1 scanner (``tools/precheck/l1_scan.py``, ``l1_families.py``, ``l1_xdup.py``).

Synthetic data only, built in memory or under ``tmp_path`` (never ``tests/fixtures`` nor ``~/.agentprov``): one test per
parse-failure class and per string-hazard class, secret and account-path counting without the value reaching any output,
timestamp monotonicity, fingerprint stability under key reordering, and end-to-end scans through the AgentDojo
TraceLogger and Inspect ``.eval`` hooks with real source profiles. Invisible characters are built with ``chr`` so this
file holds none.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "precheck"


@pytest.fixture(scope="module")
def l1() -> Any:
    sys.path.insert(0, str(TOOLS))
    try:
        import l1_scan

        yield l1_scan
    finally:
        sys.path.remove(str(TOOLS))


@pytest.fixture(scope="module")
def fam(l1: Any) -> Any:
    import l1_families

    return l1_families


BS = "\\"  # one backslash, kept out of literal escape sequences


# ================================================================================================ L1-02 parse classes
@pytest.mark.parametrize(
    ("data", "cls"),
    [
        (b'{"a": 1, "a": 2}', "duplicate_key"),
        (b'{"a": NaN}', "non_finite"),
        (b'{"a": 1' + b"0" * 1200 + b"}", "big_int"),
        (b"\xef\xbb\xbf{}", "bom"),
        (b'{"a": 1} {"b": 2}', "trailing_data"),
        (b'{"a": "\xff"}', "invalid_utf8"),
        (b'{"a": [1, 2', "truncated"),
        (b"[" * 300 + b"]" * 300, "too_deep"),
        (b'{"a": 1,, "b": 2}', "other"),
    ],
)
def test_parse_failure_class(l1: Any, data: bytes, cls: str) -> None:
    parsed = l1.parse_json(data, l1.IngestLimits(), lenient=True)
    assert parsed.primary != "ok"
    assert cls in parsed.classes


def test_parse_lone_surrogate_escaped_and_decoded(l1: Any) -> None:
    escaped = b'{"a": "' + BS.encode() + b'ud800"}'
    parsed = l1.parse_json(escaped, l1.IngestLimits(), lenient=True)
    assert parsed.primary == "ok" and "lone_surrogate" in parsed.classes  # strict accepts it, with a finding
    decoded = b'{"a": "\xed\xa0\x80"}'  # a UTF-8-encoded surrogate: invalid UTF-8 for the strict loader
    parsed = l1.parse_json(decoded, l1.IngestLimits(), lenient=True)
    assert {"lone_surrogate", "invalid_utf8"} <= parsed.classes


def test_parse_too_large(l1: Any) -> None:
    limits = l1.IngestLimits().replace(max_json_bytes=16)
    parsed = l1.parse_json(b'{"a": "' + b"x" * 64 + b'"}', limits, lenient=True)
    assert parsed.primary == "too_large" and "too_large" in parsed.classes


def test_one_document_reports_several_classes(l1: Any) -> None:
    parsed = l1.parse_json(b'{"a": NaN, "a": 1, "b": 99999999999999999999}', l1.IngestLimits(), lenient=True)
    assert {"duplicate_key", "non_finite", "big_int"} <= parsed.classes
    assert parsed.value is not l1.NO_VALUE  # the lenient value is kept for the walk


def test_i_json_integer_counted_by_the_walk(l1: Any) -> None:
    walker = l1.Walker([], [])
    walker.walk({"n": [2**53, 5]})
    assert walker.ptr["L1-02\tbig_int\t/n/*"] == 1


# ================================================================================================ L1-03 hazards
@pytest.mark.parametrize(
    ("text", "cls"),
    [
        ("a" + chr(0x2028) + "b", "line_sep"),
        ("a" + chr(0x85) + "b", "nel"),
        ("a" + chr(0x01) + "b", "c0"),
        ("a" + chr(0x0D) + "b", "cr"),
        ("a" + chr(0x90) + "b", "c1"),
        ("x" + chr(0x1B) + "[31mred", "ansi"),
        ("x" + chr(0x1B) + "y", "esc"),
        ("a" + chr(0x202E) + "b", "bidi"),
        ("a" + chr(0xE0041) + "b", "tag"),
        ("a" + chr(0x200B) + "b", "zero_width"),
        ("a" + chr(0xFE0F) + "b", "variation_selector"),
        ("a" + chr(0xE000) + "b", "pua"),
        ("a" + chr(0xFFFD) + "b", "fffd"),
        ("caf" + chr(0xC3) + chr(0xA9), "mojibake"),
        ("line" + BS + "nnext", "escaped_newline"),
        ("x" + BS + "u00e9", "escaped_unicode"),
        ('{"k": [1, 2]}', "json_in_string"),
        ("a" + chr(0xD800) + "b", "lone_surrogate"),
    ],
)
def test_string_hazard_class(l1: Any, text: str, cls: str) -> None:
    walker = l1.Walker([], [])
    walker.walk({"msgs": [{"content": text}]})
    assert walker.ptr[f"L1-03\t{cls}\t/msgs/*/content"] == 1


def test_clean_ascii_string_has_no_hazard(l1: Any) -> None:
    walker = l1.Walker([], [])
    walker.walk({"a": "plain text, nothing odd", "b": ["x", 1, None, True]})
    assert not [k for k in walker.ptr if k.startswith("L1-03")]


def test_pointer_masks_dynamic_keys(l1: Any) -> None:
    walker = l1.Walker([], [])
    walker.walk({"model_usage": {"openai/gpt-4o": {"note": "a" + chr(0x2028)}}, "attachments": {"a" * 32: "b" + chr(0x2028)}})
    keys = {k.split("\t")[2] for k in walker.ptr}
    assert keys == {"/model_usage/<key>/note", "/attachments/<key>"}


# ================================================================================================ L1-06 secrets and paths
FAKE_KEY = "AKIA" + "QX7Z" * 4  # an AWS-key-shaped synthetic string, not a credential
FAKE_ACCOUNT = "zyxprecheckuser"


def test_secret_and_account_counted_by_pointer_only(l1: Any) -> None:
    walker = l1.Walker([], [])
    walker.walk({"out": f"key={FAKE_KEY}", "path": f"/Users/{FAKE_ACCOUNT}/work/x.txt", "fiction": "/home/ubuntu/app/run.sh"})
    assert walker.ptr["L1-06\tsecret:aws-access-key-id\t/out"] == 1
    assert walker.ptr["L1-06\taccount:users-dir:named\t/path"] == 1
    assert walker.ptr["L1-06\taccount:home-dir:generic\t/fiction"] == 1
    dumped = json.dumps({"ptr": dict(walker.ptr), "acc": {k: sorted(v) for k, v in walker.accounts.items()}})
    assert FAKE_KEY not in dumped and FAKE_ACCOUNT not in dumped
    assert len(walker.accounts["users-dir"]) == 1  # a distinct-count digest, never the name


def test_local_path_model_id(l1: Any) -> None:
    walker = l1.Walker([], [])
    walker.walk({"model": "vllm//workspace/" + FAKE_ACCOUNT + "/ckpt"})
    assert walker.ptr["L1-06\taccount:local-path-model\t/model"] == 1


# ================================================================================================ L1-07 timestamps
def test_timestamp_forms_and_monotonicity(l1: Any) -> None:
    walker = l1.Walker([], [])
    walker.begin_unit()
    walker.walk({"events": [{"timestamp": "2026-01-02T10:00:00Z"}, {"timestamp": "2026-01-02T09:00:00Z"}]})
    assert walker.end_unit() is False
    walker.begin_unit()
    walker.walk({"events": [{"timestamp": "2026-01-02T10:00:00+02:00"}, {"timestamp": "2026-01-02T10:00:01+02:00"},
                            {"t": 1767340800.5}]})  # fmt: skip
    assert walker.end_unit() is True
    stat = walker.ts["/events/*/timestamp"]
    assert stat.count == 4 and stat.units_non_monotone == 1 and stat.units_with == 2
    assert stat.forms == {"Z": 2, "offset": 2}
    assert stat.min_date == "2026-01-02" and stat.max_date == "2026-01-02"
    assert walker.ts["/events/*/t"].forms == {"epoch_s": 1}


def test_timestamp_naive_and_parse_failure(l1: Any) -> None:
    walker = l1.Walker([], [])
    walker.walk({"evaluation_timestamp": "2026-02-30 10:00:00", "ok": "2026-02-01 10:00:00.123"})
    assert walker.ts["/evaluation_timestamp"].fail == 1
    assert walker.ts["/ok"].forms == {"naive": 1}


# ================================================================================================ L1-04 fingerprints
def test_fingerprint_stable_under_key_reordering(l1: Any, fam: Any) -> None:
    a = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": None,
         "tool_calls": [{"function": "f", "args": {"x": 1, "y": [1, 2]}, "id": "c1"}]}]  # fmt: skip
    b = [{"content": "hi", "role": "user"}, {"tool_calls": [{"id": "c1", "args": {"y": [1, 2], "x": 1}, "function": "f"}],
         "content": None, "role": "assistant"}]  # fmt: skip
    ctx = fam.Ctx(profile_id="glitch-agentdojo", part="head")
    head = {"suite_name": "s", "user_task_id": "user_task_0", "pipeline_name": "p", "injection_task_id": None,
            "attack_type": None, "injections": {}, "error": None, "utility": True, "security": True, "duration": 1.0}  # fmt: skip
    va = fam.agentdojo_unit({**head, "messages": a}, "runs/p/s/user_task_0/none/none.json", ctx)
    vb = fam.agentdojo_unit({**head, "messages": b}, "runs/p/s/user_task_0/none/none.json", ctx)
    assert l1.fingerprint(va.steps) == l1.fingerprint(vb.steps)
    assert l1.fingerprint(va.steps)[0] is not None
    assert l1.fingerprint(None) == (None, False)
    _fp, fallback = l1.fingerprint([["x", chr(0xD800)]])
    assert fallback  # JCS refuses a lone surrogate: the documented fallback is used


# ================================================================================================ hooks
def test_layout_facets(fam: Any) -> None:
    facets, flags = fam.layout_facets("runs/{model_dir?}/{suite}/{task_dir}/{attack_dir}/{file}.json",
                                      "runs/router/gemini-3-flash/banking/user_task_1/autodojo/injection_task_2.json")  # fmt: skip
    assert facets["model_dir"] == "router/gemini-3-flash" and facets["file"] == "injection_task_2" and not flags
    facets, _ = fam.layout_facets("runs/{model_dir?}/{suite}/{task_dir}/{attack_dir}/{file}.json",
                                  "runs/banking/user_task_1/none/none.json")  # fmt: skip
    assert facets["model_dir"] == "<none>"
    facets, flags = fam.layout_facets("runs/{pipeline_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json",
                                      "clone/runs/gpt/slack/user_task_3/direct/injection_task_1.json")  # fmt: skip
    assert facets["pipeline_dir"] == "gpt" and facets["_prefix"] == "clone" and not flags
    _facets, flags = fam.layout_facets("results/{a}/{b}/x.json", "other/1/2/x.json")
    assert flags == ["layout_mismatch"]


def test_agentdojo_variant_by_key_set(fam: Any) -> None:
    base = {"suite_name": "s", "user_task_id": "u", "pipeline_name": "p", "injection_task_id": None, "attack_type": None,
            "injections": {}, "messages": [], "error": None, "utility": True, "security": True, "duration": 1.0}  # fmt: skip
    assert fam.agentdojo_variant(base) == "v0.k11"
    v1 = {**base, "benchmark_version": "v1", "evaluation_timestamp": "t", "agentdojo_package_version": "0.1.35"}
    assert fam.agentdojo_variant(v1) == "v1.k14"
    assert fam.agentdojo_variant({k: v for k, v in v1.items() if k != "utility"}) == "v1.k14.incomplete"
    assert fam.agentdojo_variant({**base, "build_constraints": True}) == "drift.k18.messages"
    assert fam.agentdojo_variant({"suite_name": "s"}) == "not_tracelogger"


def test_consumes_context_table_matches_the_mappers(l1: Any) -> None:
    from agentprov.adapters.registry import MAPPERS, READERS
    from agentprov.adapters.runner import resolve_factory

    declared = set()
    for dialect in READERS:
        mapper = MAPPERS.get(dialect) or MAPPERS.get(dialect.rsplit(".", 1)[0] + ".trace")
        if mapper and getattr(resolve_factory(mapper), "consumes_context", False):
            declared.add(dialect)
    assert declared == set(l1.CONSUMES_CONTEXT)


# ================================================================================================ end to end
def _tracelogger(user_task: str, attack: str | None, messages: list[dict[str, Any]], **extra: Any) -> bytes:
    log = {"suite_name": "banking", "pipeline_name": "gpt-x-glitch", "user_task_id": user_task,
           "injection_task_id": "injection_task_1" if attack else None, "attack_type": attack,
           "injections": {"v": "payload"} if attack else {}, "messages": messages, "error": None, "utility": False,
           "security": bool(attack), "duration": 2.5, "benchmark_version": "v1",
           "evaluation_timestamp": "2026-10-05 12:20:00", "agentdojo_package_version": "0.1.35", **extra}  # fmt: skip
    return json.dumps(log).encode()


def _run(l1: Any, tmp_path: Path, argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    out = tmp_path / "summary.json"
    l1.run(l1.parser().parse_args([*argv, "--summary-out", str(out), "--jobs", "1", "--emit-fp", "--lenient-classes"]))
    summary = json.loads(out.read_text())
    home = l1.precheck_root()
    corpus = summary["corpus_id"]
    rows = [json.loads(x) for x in (home / corpus / f"l1-units-{summary['part']}.jsonl").read_text().splitlines()]
    everything = "".join(p.read_text(encoding="utf-8") for p in home.rglob("*.jsonl")) + out.read_text()
    return summary, rows, everything


def test_agentdojo_tracelogger_end_to_end(l1: Any, tmp_path: Path) -> None:
    root = tmp_path / "raw"
    base = root / "17_agentdojo" / "runs" / "gpt-x-glitch" / "banking"
    msgs = [{"role": "system", "content": [{"type": "text", "content": "sys"}]},
            {"role": "user", "content": [{"type": "text", "content": f"see /Users/{FAKE_ACCOUNT}/notes and {FAKE_KEY}"}]},
            {"role": "assistant", "content": None, "tool_calls": [{"function": "read", "args": {"p": 1}, "id": None,
                                                                    "placeholder_args": None}]},
            {"role": "tool", "content": "ok" + chr(0x2028), "tool_call_id": None, "error": None,
             "tool_call": {"function": "read", "args": {"p": 1}, "id": None, "placeholder_args": None}},
            {"role": "assistant", "content": [{"type": "text", "content": "done"}], "tool_calls": None}]  # fmt: skip
    files = {
        base / "user_task_0" / "important_instructions" / "injection_task_1.json": _tracelogger("user_task_0", "important_instructions", msgs),
        base / "user_task_1" / "important_instructions" / "injection_task_1.json": _tracelogger("user_task_1", "important_instructions", msgs),
        base / "user_task_0" / "none" / "none.json": _tracelogger("user_task_0", None, []),
        base / "user_task_2" / "none" / "none.json": b'{"suite_name": "banking", "a": 1, "a": 2} tail',
        root / "README.md": b"# readme",
        root / "17_agentdojo" / "runs" / ".DS_Store": b"junk",
    }  # fmt: skip
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    summary, rows, everything = _run(l1, tmp_path, ["--source", "glitch-agentdojo", "--part", "head", "--input", str(root)])
    assert FAKE_KEY not in everything and FAKE_ACCOUNT not in everything
    assert summary["L1-01"]["dispositions"]["selected"] == 4 and summary["L1-01"]["units"] == 4
    by_label = {r["label"]: r for r in rows}
    ok = by_label["17_agentdojo/runs/gpt-x-glitch/banking/user_task_0/important_instructions/injection_task_1.json"]
    assert ok["facets"]["pipeline_dir"] == "gpt-x-glitch" and ok["facets"]["variant"] == "v1.k14"
    assert ok["stratum"] == "pipeline_dir=gpt-x-glitch|suite=banking|attack_dir=important_instructions"
    assert ok["outcomes"] == {"utility": False, "security": True, "error_present": False}
    assert ok["ts"] == {"present": True, "tz": ["naive"], "monotone": None}
    empty = by_label["17_agentdojo/runs/gpt-x-glitch/banking/user_task_0/none/none.json"]
    assert "zero_messages" in empty["flags"] and empty["fp"] is None
    broken = by_label["17_agentdojo/runs/gpt-x-glitch/banking/user_task_2/none/none.json"]
    assert broken["parse"] == "duplicate_key"
    assert {"parse:duplicate_key", "parse:trailing_data", "strict_parse_failed", "not_tracelogger"} <= set(broken["flags"])
    assert summary["L1-02"]["artefacts_with_class"] == {"duplicate_key": 1, "trailing_data": 1}
    assert summary["L1-03"]["classes"]["line_sep"]["pointers"] == {"/messages/*/content": 2}
    assert summary["L1-06"]["artefacts_with"]["secret:aws-access-key-id"] == 2
    assert summary["L1-06"]["named_accounts_distinct"] == {"users-dir": 1}
    # two byte-different logs (user_task differs) with the same messages: one trajectory group of 2
    assert summary["L1-04"]["trajectory_identical"]["groups"] == 1
    assert summary["L1-04"]["trajectory_identical"]["facets_differing_in_groups"]["task_dir"] == 1


def _eval_zip(path: Path, model: str, samples: list[dict[str, Any]]) -> None:
    header = {"version": 2, "status": "success",
              "eval": {"task": "agentharm", "model": model, "packages": {"inspect_ai": "0.3.247.dev69+g53c1fa98b"},
                       "created": "2026-08-01T10:00:00+00:00"},
              "stats": {"started_at": "2026-08-01T10:00:00+00:00", "completed_at": "2026-08-01T10:05:00+00:00"}}  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("header.json", json.dumps(header))
        for i, sample in enumerate(samples, 1):
            z.writestr(f"samples/{i}_epoch_1.json", json.dumps(sample))
        z.writestr("summaries.json", json.dumps([{"id": 1}]))


def _sample(i: int, category: str, value: float) -> dict[str, Any]:
    return {"id": i, "epoch": 1, "input": "do x", "metadata": {"category": category},
            "messages": [{"role": "user", "content": "do x"},
                         {"role": "assistant", "content": [{"type": "text", "text": "no"}],
                          "tool_calls": [{"id": "t", "function": "send", "arguments": {"to": "a"}}]}],
            "events": [{"event": "model", "timestamp": "2026-08-01T10:00:02+00:00"},
                       {"event": "tool", "timestamp": "2026-08-01T10:00:01+00:00"}],
            "scores": {"combined_scorer": {"value": {"score": value, "refusal": 1.0}}}}  # fmt: skip


def test_inspect_eval_end_to_end(l1: Any, tmp_path: Path) -> None:
    root = tmp_path / "survey"
    results = root / "agentharm" / "results"
    _eval_zip(results / "qwen14_harmful" / "2026-08-01_agentharm_a.eval", "ollama/qwen3:14b",
              [_sample(1, "Fraud", 0.0), _sample(2, "Cybercrime", 1.0)])  # fmt: skip
    _eval_zip(results / "gptoss_benign" / "2026-08-01_agentharm_b.eval", "ollama/gpt-oss:120b", [_sample(3, "Fraud", 1.0)])
    (results / "broken_benign").mkdir(parents=True)
    (results / "broken_benign" / "x.eval").write_bytes(b"PK\x03\x04 not a zip")
    summary, rows, _everything = _run(l1, tmp_path, ["--source", "agent-security-tools-survey", "--part", "agentharm",
                                                     "--input", str(root)])  # fmt: skip
    assert summary["L1-01"]["units"] == 3 and summary["L1-01"]["dispositions"]["selected"] == 3
    by_dir = {r["facets"]["results_dir"]: r for r in rows}
    harmful = by_dir["qwen14_harmful"]
    assert harmful["n_units"] == 2 and harmful["kind"] == "eval"
    assert harmful["facets"]["model"] == "ollama/qwen3:14b" and harmful["stratum"] == "results_dir=qwen14_harmful"
    assert harmful["unit_facets"] == {"category": {"Cybercrime": 1, "Fraud": 1}}
    assert harmful["outcomes"]["score.combined_scorer.score"] == {"0.0": 1, "1.0": 1}
    assert harmful["ts"]["monotone"] is False  # event list order is not time order: counted, not hidden
    assert by_dir["broken_benign"]["parse"].startswith("archive:") and by_dir["broken_benign"]["n_units"] == 0
    assert summary["L1-07"]["pointers"]["samples:/events/*/timestamp"]["units_non_monotone"] == 3
    fp_file = l1.precheck_root() / "_fp" / "agent-security-tools-survey.agentharm.jsonl"
    fps = [json.loads(x) for x in fp_file.read_text().splitlines()]
    assert sum(1 for r in fps if r.get("unit")) == 3  # one fingerprint row per sample
    # the three samples share the same message list: one trajectory group across two logs
    assert summary["L1-04"]["trajectory_identical"]["groups"] == 1
    assert summary["L1-04"]["trajectory_identical"]["units_in_groups"] == 3


def test_xdup_scopes(l1: Any, tmp_path: Path) -> None:
    import l1_xdup

    fp_dir = tmp_path / "_fp"
    fp_dir.mkdir()
    rows = {
        "a.p1.jsonl": [{"fp": "f1", "sha256": "s1", "label": "x", "source": "a", "part": "p1", "corpus_id": "A"},
                       {"fp": "f1", "sha256": "s2", "label": "y", "source": "a", "part": "p1", "corpus_id": "A"}],
        "a.p2.jsonl": [{"fp": "f2", "sha256": "s3", "label": "x", "source": "a", "part": "p2", "corpus_id": "A"}],
        "b.h.jsonl": [{"fp": "f2", "sha256": "s3", "label": "z", "source": "b", "part": "h", "corpus_id": "B"},
                      {"fp": None, "sha256": "s4", "label": "w", "source": "b", "part": "h", "corpus_id": "B"}],
        "b.h.limit5.jsonl": [{"fp": "f1", "sha256": "s1", "label": "q", "source": "b", "part": "h", "corpus_id": "B"}],
    }  # fmt: skip
    for name, items in rows.items():
        (fp_dir / name).write_text("".join(json.dumps(r) + "\n" for r in items))
    out = l1_xdup.run(fp_dir, tmp_path / "x.json", with_limit=False)
    assert out["trajectory_identical"]["within_part"]["groups"] == 1
    assert out["trajectory_identical"]["cross_corpus"]["groups"] == 1
    assert out["trajectory_identical"]["cross_corpus"]["pairs"] == {"A|B": 1}
    assert out["byte_identical"]["cross_corpus"]["groups"] == 1
    assert out["byte_identical"]["within_part"]["groups"] == 0
    assert out["totals"]["units_without_fp"] == 1


# ================================================================================================ other families (synthetic)
def _scanner(l1: Any, profile_id: str, tmp_path: Path) -> Any:
    return l1.Scanner({"profile_id": profile_id, "part": "head", "source": {"kind": "local", "root": str(tmp_path)}})


def test_geminicli_stream_file_unit(l1: Any, tmp_path: Path) -> None:
    lines = [{"type": "init", "timestamp": "2026-05-01T10:00:00.000Z", "model": "gemini-2.5-pro"},
             {"type": "message", "timestamp": "2026-05-01T10:00:01.000Z", "role": "assistant", "content": "x", "delta": True},
             {"type": "tool_use", "timestamp": "2026-05-01T10:00:02.000Z", "tool_name": "run", "tool_id": "run-1", "parameters": {}},
             {"type": "tool_result", "timestamp": "2026-05-01T10:00:01.500Z", "tool_id": "run-1", "status": "success"}]  # fmt: skip
    data = b"".join(json.dumps(x).encode() + b"\n" for x in lines) + b'{"type": "message",\r\n'
    label = "RESULTS_build/cells/gemini_cli__glm-4.7-probe/SK-ABC__m03/gemini_stream.jsonl"
    res = _scanner(l1, "code-agent-misalignment-geminicli", tmp_path).scan(label, len(data), data, None, False)
    row = res["row"]
    assert row["kind"] == "jsonl" and row["n_units"] == 1
    assert row["facets"] == {"scaffold": "gemini_cli", "model": "glm-4.7-probe", "skeleton": "SK-ABC", "mutation": "m03"}
    assert "unterminated" in row["flags"] and "parse:crlf" in row["flags"] and row["ts"]["monotone"] is False


def test_autogen_rows_units_and_non_run_rows(l1: Any, tmp_path: Path) -> None:
    run = {"run_id": "r1", "entry": "tool", "modes": {"model": "observe", "bus": "block", "tool": "observe"},
           "messages": [{"type": "TextMessage", "source": "user", "text": "task", "raw": {"created_at": "2026-01-01T00:00:00Z"}}],
           "stop_reason": "MaxMessageTermination", "error": None}  # fmt: skip
    data = (json.dumps(run) + "\n" + json.dumps({**run, "run_id": "r2", "entry": "user"}) + "\n"
            + json.dumps({"probe_id": "p", "response": "x"}) + "\n").encode()  # fmt: skip
    label = "autogen-guard-placement/results/phase6/bus/runs.jsonl"
    res = _scanner(l1, "autogen-guard-placement", tmp_path).scan(label, len(data), data, None, False)
    row = res["row"]
    assert row["n_units"] == 2 and row["non_run_rows"] == 1
    assert row["facets"] == {"phase": "6", "arm": "bus"} and row["stratum"] == "phase=6|arm=bus"
    assert row["unit_facets"]["entry"] == {"tool": 1, "user": 1}


def test_credleak_cell_runs_and_withhold_rule(l1: Any, tmp_path: Path) -> None:
    turn = {"turnNumber": 1, "userMessage": "go", "assistantResponse": "done", "timestamp": "2026-06-10T10:00:00.000Z",
            "toolCalls": [{"tool": "read_file", "input": {"path": "a"}, "output": "token CANARYX-123"}]}  # fmt: skip
    cell = {"model": "m1", "technique": "T1", "scenario": "T1.1", "defence": "C4-baseline", "runId": "x", "config": {},
            "summary": {}, "timestamp": "2026-06-10T10:00:00.000Z",
            "runs": [{"repetition": 1, "turns": [turn], "hijackSucceeded": True},
                     {"repetition": 2, "turns": [], "hijackSucceeded": False}]}  # fmt: skip
    data = json.dumps(cell).encode()
    label = "p15b-run-data/01-injection-map/T-FILE/m1/run__a.json"
    res = _scanner(l1, "credleak-p15b", tmp_path).scan(label, len(data), data, None, False)
    row = res["row"]
    assert row["n_units"] == 2 and row["facets"]["layout_class"] == "roster" and row["facets"]["batch"] == "run"
    assert row["outcomes"]["hijackSucceeded"] == {"false": 1, "true": 1}
    assert row["unit_flags"] == {"zero_messages": 1}
    assert res["walk"]["ptr"]["L1-06\twithhold:canary-tag\t/runs/*/turns/*/toolCalls/*/output"] == 1


def test_mcphunt_streamed_traces(l1: Any, tmp_path: Path) -> None:
    trace = {"task_id": "t", "model": "m", "defense": "none", "mitigation_level": "none", "env_type": "benign",
             "risk_mechanism": "r", "messages": [{"role": "user", "content": "x"}],
             "events": [{"timestamp": 1767225600.0, "canary_in_result": True}], "outcome": "safe_success"}  # fmt: skip
    doc = {"schema_version": "2.0.0", "pipeline_git_commit": "abc1234", "task_taxonomy_version": "1",
           "labeling_rules_version": "1", "traces": [trace, {**trace, "model": "n"}]}  # fmt: skip
    data = json.dumps(doc).encode()
    res = _scanner(l1, "mcphunt", tmp_path).scan("main/m.json", len(data), data, None, False)
    row = res["row"]
    assert row["kind"] == "jsonstream" and row["n_units"] == 2 and row["stratum"] == "split=main|document=m"
    assert row["unit_facets"]["model"] == {"m": 1, "n": 1} and row["unit_flags"] == {"canary_flagged": 2}


def test_dtap_lfs_pointer_and_judge_only(l1: Any, tmp_path: Path) -> None:
    scanner = _scanner(l1, "dtap-bench", tmp_path)
    pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 12\n"
    label = "claudesdk/claude-sonnet-4-5/windows/benign/32/20260401_095722.json"
    row = scanner.scan(label, len(pointer), pointer, None, False)["row"]
    assert row["parse"] == "lfs_pointer" and row["facets"]["framework"] == "claudesdk" and row["n_units"] == 0
    judge = json.dumps({"task_success": True, "attack_success": False}).encode()
    jlabel = "openaisdk/gpt-5.1/crm/malicious/indirect/data-exfil/7/judge_result.json"
    row = scanner.scan(jlabel, len(judge), judge, None, False)["row"]
    assert row["facets"]["split_label"] == "indirect" and "judge_only_unit" in row["flags"]
    assert row["outcomes"] == {"task_success": True, "attack_success": False}


def test_parse_json_default_is_strict_only(l1: Any) -> None:
    """Without --lenient-classes nothing is re-parsed outside agentprov.ingest: the strict class alone, no value."""
    parsed = l1.parse_json(b'{"a": NaN, "a": 1}', l1.IngestLimits())
    assert parsed.primary != "ok"
    assert parsed.classes == {parsed.primary}
    assert parsed.value is l1.NO_VALUE


@pytest.mark.parametrize(("content", "empty"), [
    (None, True), ("", True), ([], True), ([["text", ""]], True), ([["text", ""], ["text", None]], True),
    ([["text", "hi"]], False), ([["text", ""], ["image", {"url": "x"}]], False), ("x", False),
])  # fmt: skip
def test_empty_content_cc08(l1: Any, content: object, empty: bool) -> None:
    """CC-08: a final assistant turn of only empty text blocks counts as empty (E2 A03), as None/"" do."""
    assert l1.fam.empty_content(content) is empty


def test_guard_output_refuses_real_roots_under_pytest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-10-15 incident: under pytest no tool may write into the real ~/.agentprov or the repo's precheck docs."""
    import l2_common

    real_home = Path.home() / ".agentprov" / "migration-work" / "precheck" / "x" / "l1-units-head.jsonl"
    docs = Path(l2_common.REPO) / "docs" / "reports" / "precheck" / "data" / "x" / "l1-head.json"
    for path in (real_home, docs):
        with pytest.raises(SystemExit, match="refused under pytest"):
            l2_common.guard_output(path)
    assert l2_common.guard_output(tmp_path / "ok.json") == tmp_path / "ok.json"
    monkeypatch.setenv("AGENTPROV_PRECHECK_ROOT", str(tmp_path / "root"))
    assert l2_common.precheck_root() == tmp_path / "root"
    monkeypatch.delenv("AGENTPROV_PRECHECK_ROOT")
    monkeypatch.delenv("AGENTPROV_HOME", raising=False)  # as outside the repo conftest: the default is the real root
    with pytest.raises(SystemExit, match="refused under pytest"):
        l2_common.precheck_root()


def test_trailing_calls_flag(l1: Any) -> None:
    """A log ending on an assistant turn with tool calls (no results after it) is flagged trailing_calls."""
    base = {"suite_name": "banking", "pipeline_name": "m", "user_task_id": "user_task_0", "injection_task_id": None,
            "attack_type": None, "injections": {}, "utility": True, "security": True, "duration": 1.0, "error": None}
    msgs = [{"role": "user", "content": "x"},
            {"role": "assistant", "content": None, "tool_calls": [{"function": "f", "args": {}}]}]  # fmt: skip
    ctx = l1.fam.Ctx(profile_id="glitch-agentdojo", part="head", layout=None, variant_labels={}, producer_band=())
    view = l1.fam.agentdojo_unit({**base, "messages": msgs}, "runs/m/banking/user_task_0/none/none.json", ctx)
    assert "trailing_calls" in view.flags and "null_final" not in view.flags
    done = [*msgs, {"role": "tool", "content": "ok", "tool_call": {"function": "f", "args": {}}},
            {"role": "assistant", "content": "done", "tool_calls": []}]  # fmt: skip
    view = l1.fam.agentdojo_unit({**base, "messages": done}, "runs/m/banking/user_task_0/none/none.json", ctx)
    assert "trailing_calls" not in view.flags
