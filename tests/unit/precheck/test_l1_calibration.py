"""Calibration of the pre-check's Level 1 scanner (protocol C00 analogue; docs/reports/precheck/README.md section 3).

Every L1 class is fault-injected into an in-memory copy of a clean synthetic document; the mutated copy is scanned end to
end (``l1_scan.run`` over a ``tmp_path`` tree under a real AgentDojo profile, or ``Scanner.scan`` for the JSONL and
Inspect ``.eval`` paths) and the class must fire. The unmutated documents must give **no** finding at all, and no injected
secret-like value or account name may appear in any output the scanner writes (rows, auxiliary rows, fingerprints,
summary) or prints. Synthetic data only (never ``tests/fixtures`` nor ``~/.agentprov``: the conftest isolates
``$AGENTPROV_HOME``). Secret-shaped strings and invisible characters are assembled at run time, so this file holds
neither.
"""

from __future__ import annotations

import copy
import io
import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "precheck"

BS = "\\"
ACCOUNT = "zyxcalibacct"  # a named account (not in GENERIC_ACCOUNTS)
#: Secret-like synthetic strings, one per pattern family, built from pieces so no literal key shape sits in the source.
SECRETS: dict[str, str] = {
    "aws-access-key-id": "AK" + "IA" + "QZ7X" * 4,
    "openai-api-key": "sk" + "-proj-" + "Zq9" * 10,
    "anthropic-api-key": "sk" + "-ant-" + "api03-" + "Wv8" * 10,
    "github-token": "gh" + "p_" + "Rt5" * 12,
    "slack-token": "xo" + "xb-" + "1234567890-" + "abcdef",
    "google-api-key": "AI" + "za" + "Sy" + "Q" * 33,
    "hf-token": "hf" + "_" + "Lm3" * 12,
    "stripe-key": "sk" + "_live_" + "Pq4" * 8,
    "private-key-block": "-----BEGIN RSA PRIV" + "ATE KEY-----",
    "jwt": "ey" + "J" + "hbGciOiJIUzI1NiJ9" + ".ey" + "J" + "zdWIiOiIxMjM0NTY3ODkwIn0" + ".c2lnbmF0dXJlX3Rlc3Q",
}
LAYOUT = "17_agentdojo/runs/gpt-x-glitch/banking"
CLEAN_A = f"{LAYOUT}/user_task_0/none/none.json"
CLEAN_B = f"{LAYOUT}/user_task_1/important_instructions/injection_task_1.json"


@pytest.fixture(scope="module")
def l1() -> Any:
    sys.path.insert(0, str(TOOLS))
    try:
        import l1_scan

        yield l1_scan
    finally:
        sys.path.remove(str(TOOLS))


# ================================================================================================ clean documents
def _messages(words: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": [{"type": "text", "content": "You are a bank agent."}],
                                  "timestamp": "2026-10-05T12:20:00Z"}]  # fmt: skip
    for i, word in enumerate(words, 1):
        out.append({"role": "user", "content": [{"type": "text", "content": f"hello {word} please"}],
                    "timestamp": f"2026-10-05T12:2{i}:00Z"})  # fmt: skip
        out.append({"role": "assistant", "content": None, "timestamp": f"2026-10-05T12:2{i}:10Z",
                    "tool_calls": [{"function": "get_balance", "args": {"account": word}, "id": f"c{i}",
                                    "placeholder_args": None}]})  # fmt: skip
        out.append({"role": "tool", "content": f"balance of {word}: 10", "error": None, "tool_call_id": f"c{i}",
                    "timestamp": f"2026-10-05T12:2{i}:20Z",
                    "tool_call": {"function": "get_balance", "args": {"account": word}, "id": f"c{i}",
                                  "placeholder_args": None}})  # fmt: skip
    out.append({"role": "assistant", "content": [{"type": "text", "content": "done"}], "tool_calls": None,
                "timestamp": "2026-10-05T12:29:00Z"})  # fmt: skip
    return out


def _doc(user_task: str, attack: str | None, words: list[str]) -> dict[str, Any]:
    return {"suite_name": "banking", "pipeline_name": "gpt-x-glitch", "user_task_id": user_task,
            "injection_task_id": "injection_task_1" if attack else None, "attack_type": attack,
            "injections": {"v": "payload"} if attack else {}, "messages": _messages(words), "error": None,
            "utility": True, "security": bool(attack), "duration": 2.5, "benchmark_version": "v1",
            "evaluation_timestamp": "2026-10-05 12:20:00", "agentdojo_package_version": "0.1.35"}  # fmt: skip


def _clean() -> tuple[dict[str, Any], dict[str, Any]]:
    return _doc("user_task_0", None, ["alpha", "beta"]), _doc("user_task_1", "important_instructions", ["gamma", "delta"])


def _enc(doc: Any) -> bytes:
    return json.dumps(doc).encode("utf-8")


# ================================================================================================ mutations
def _content(doc: dict[str, Any], text: str) -> bytes:
    """Doc B with its second user message's text set to ``text``."""
    doc = copy.deepcopy(doc)
    doc["messages"][4]["content"][0]["content"] = text
    return _enc(doc)


def _set(key: str, value: Any) -> Callable[[dict[str, Any]], bytes]:
    def mutate(doc: dict[str, Any]) -> bytes:
        return _enc({**doc, key: value})

    return mutate


def _bytes(fn: Callable[[bytes], bytes]) -> Callable[[dict[str, Any]], bytes]:
    return lambda doc: fn(_enc(doc))


def _with_text(text: str) -> Callable[[dict[str, Any]], bytes]:
    return lambda doc: _content(doc, text)


def _reorder_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _reorder_keys(value[k]) for k in reversed(list(value))}
    if isinstance(value, list):
        return [_reorder_keys(v) for v in value]
    return value


def _same_trajectory_reordered(doc: dict[str, Any]) -> bytes:
    a, _b = _clean()
    return _enc({**doc, "messages": _reorder_keys(a["messages"]), "duration": 9.75})


def _non_monotone(doc: dict[str, Any]) -> bytes:
    doc = copy.deepcopy(doc)
    msgs = doc["messages"]
    msgs[1]["timestamp"], msgs[5]["timestamp"] = msgs[5]["timestamp"], msgs[1]["timestamp"]
    return _enc(doc)


def _deep(doc: dict[str, Any]) -> bytes:
    nested: Any = "x"
    for _ in range(300):
        nested = [nested]
    doc = copy.deepcopy(doc)
    doc["messages"][4]["content"] = nested
    return _enc(doc)


def _secret_key(doc: dict[str, Any]) -> bytes:
    doc = copy.deepcopy(doc)
    doc["messages"][3]["tool_call"]["args"] = {SECRETS["github-token"]: "x"}
    return _enc(doc)


#: (case id, mutation of doc B, findings that must fire, the injected values that must never reach an output)
CASES: list[tuple[str, Callable[[dict[str, Any]], bytes], set[str], list[str]]] = [
    # ---- L1-02 parse classes
    ("duplicate_key", _bytes(lambda d: b'{"utility": false, ' + d[1:]), {"L1-02:duplicate_key"}, []),
    ("nan", _bytes(lambda d: d.replace(b'"duration": 2.5', b'"duration": NaN')), {"L1-02:non_finite"}, []),
    ("infinity", _bytes(lambda d: d.replace(b'"duration": 2.5', b'"duration": -Infinity')), {"L1-02:non_finite"}, []),
    ("float_overflow_1e400", _bytes(lambda d: d.replace(b'"duration": 2.5', b'"duration": 1e400')),
     {"L1-02:non_finite"}, []),
    ("big_int_digits", _bytes(lambda d: d.replace(b'"duration": 2.5', b'"duration": 1' + b"0" * 1200)),
     {"L1-02:big_int"}, []),
    ("big_int_beyond_i_json", _set("duration", 2**60), {"L1-02:big_int"}, []),
    ("escaped_lone_surrogate", lambda d: _content(d, "hello" + chr(0xD800) + "there"),
     {"L1-02:lone_surrogate", "L1-03:lone_surrogate"}, []),
    ("bom", _bytes(lambda d: b"\xef\xbb\xbf" + d), {"L1-02:bom"}, []),
    ("trailing_data", _bytes(lambda d: d + b' {"x": 1}'), {"L1-02:trailing_data"}, []),
    ("invalid_utf8", _bytes(lambda d: d.replace(b"hello gamma", b"hel\xfflo gamma")),
     {"L1-02:invalid_utf8", "L1-03:undecodable_byte"}, []),
    ("truncated", _bytes(lambda d: d[: len(d) // 2]), {"L1-02:truncated", "L1-08:unparsed"}, []),
    ("too_deep", _deep, {"L1-02:too_deep"}, []),
    ("empty_file", _bytes(lambda d: b""), {"L1-08:empty_file", "L1-02:empty"}, []),
    # ---- L1-03 encodings and escaping
    ("u2028", lambda d: _content(d, "hello" + chr(0x2028) + "there"), {"L1-03:line_sep"}, []),
    ("nel", lambda d: _content(d, "hello" + chr(0x85) + "there"), {"L1-03:nel"}, []),
    ("c0", lambda d: _content(d, "hello" + chr(0x01) + "there"), {"L1-03:c0"}, []),
    ("bidi", lambda d: _content(d, "hello" + chr(0x202E) + "there"), {"L1-03:bidi"}, []),
    ("tag_char", lambda d: _content(d, "hello" + chr(0xE0041) + "there"), {"L1-03:tag"}, []),
    ("zero_width", lambda d: _content(d, "hello" + chr(0x200B) + "there"), {"L1-03:zero_width"}, []),
    ("fffd", lambda d: _content(d, "hello" + chr(0xFFFD) + "there"), {"L1-03:fffd"}, []),
    ("mojibake", lambda d: _content(d, "hello caf" + chr(0xC3) + chr(0xA9)), {"L1-03:mojibake"}, []),
    ("literal_newline_residue", lambda d: _content(d, "line one" + BS + "nline two"), {"L1-03:escaped_newline"}, []),
    ("escaped_unicode_residue", lambda d: _content(d, "caf" + BS + "u00e9"), {"L1-03:escaped_unicode"}, []),
    ("json_in_string", lambda d: _content(d, '{"tool": "x", "args": [1, 2]}'), {"L1-03:json_in_string"}, []),
    # ---- L1-06 account paths and secret-like strings (counts and pointers only)
    ("account_path_users", lambda d: _content(d, f"see /Users/{ACCOUNT}/notes.txt"),
     {"L1-06:account:users-dir:named", "L1-08:account_path_named"}, [ACCOUNT]),
    ("account_path_home", lambda d: _content(d, f"cat /home/{ACCOUNT}/.bashrc"), {"L1-06:account:home-dir:named"}, [ACCOUNT]),
    ("account_path_windows", lambda d: _content(d, f"C:{BS}Users{BS}{ACCOUNT}{BS}x.txt"),
     {"L1-06:account:windows-users:named"}, [ACCOUNT]),
    *[(f"secret_{name}", _with_text(f"use {value} now"),
       {f"L1-06:secret:{name}", "L1-08:secret_like"}, [value]) for name, value in SECRETS.items()],
    ("secret_as_key", _secret_key, {"L1-06:secret:github-token"}, [SECRETS["github-token"]]),
    # ---- L1-07 timestamps
    ("non_monotone_timestamps", _non_monotone, {"L1-07:non_monotone"}, []),
    ("unparseable_timestamp", _set("evaluation_timestamp", "2026-02-30 10:00:00"), {"L1-07:parse_fail"}, []),
    # ---- L1-04 duplicates
    ("identical_trajectory_key_reordering", _same_trajectory_reordered, {"L1-04:trajectory_identical"}, []),
    ("byte_identical_copy", lambda d: _enc(_clean()[0]), {"L1-04:byte_identical", "L1-04:trajectory_identical"}, []),
    # ---- L1-08 degenerate
    ("zero_messages", _set("messages", []), {"L1-08:zero_messages"}, []),
]


# ================================================================================================ scan and findings
def _scan(l1: Any, tmp_path: Path, files: dict[str, bytes], capsys: pytest.CaptureFixture[str],
          lenient: bool = True) -> tuple[dict[str, Any], str]:
    root = tmp_path / "raw"
    for label, data in files.items():
        path = root / label
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    out = tmp_path / "summary.json"
    argv = ["--source", "glitch-agentdojo", "--part", "head", "--input", str(root), "--summary-out", str(out),
            "--jobs", "1", "--emit-fp", *(["--lenient-classes"] if lenient else [])]  # fmt: skip
    l1.run(l1.parser().parse_args(argv))
    summary = json.loads(out.read_text(encoding="utf-8"))
    printed = capsys.readouterr()
    written = "".join(p.read_text(encoding="utf-8") for p in l1.precheck_root().rglob("*") if p.is_file())
    return summary, written + out.read_text(encoding="utf-8") + printed.out + printed.err


def findings(summary: dict[str, Any]) -> set[str]:
    """Every finding an L1 summary reports (a clean part must give the empty set)."""
    out = {f"L1-02:{c}" for c in summary["L1-02"]["artefacts_with_class"]}
    out |= {f"L1-02:primary:{c}" for c in summary["L1-02"]["by_primary_class"] if c != "ok"}
    out |= {f"L1-03:{c}" for c in summary["L1-03"]["classes"]}
    out |= {f"L1-06:{c}" for c in summary["L1-06"]["classes"]}
    for stat in summary["L1-07"]["pointers"].values():
        if stat["units_non_monotone"]:
            out.add("L1-07:non_monotone")
        if stat["parse_fail"]:
            out.add("L1-07:parse_fail")
    out |= {f"L1-08:{f}" for f in summary["L1-08"]["flags"]}
    out |= {f"L1-08:unit:{f}" for f in summary["L1-08"]["unit_flags"]}
    for kind in ("byte_identical", "trajectory_identical"):
        if summary["L1-04"][kind]["groups"]:
            out.add(f"L1-04:{kind}")
    return out


def test_unmutated_documents_give_no_finding(l1: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a, b = _clean()
    summary, _text = _scan(l1, tmp_path, {CLEAN_A: _enc(a), CLEAN_B: _enc(b)}, capsys)
    assert summary["L1-01"]["dispositions"] == {"selected": 2} and summary["L1-01"]["units"] == 2
    assert findings(summary) == set()
    assert summary["L1-02"]["by_primary_class"] == {"ok": 2}
    assert summary["L1-07"]["artefacts"] == {"with": 2}  # timestamps present, all monotone
    assert summary["L1-04"]["trajectory_identical"]["units_with_fp"] == 2


@pytest.mark.parametrize(("case", "mutate", "expected", "never"), CASES, ids=[c[0] for c in CASES])
def test_injected_class_is_detected(l1: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str,
                                    mutate: Callable[[dict[str, Any]], bytes], expected: set[str], never: list[str]) -> None:  # fmt: skip
    a, b = _clean()
    summary, text = _scan(l1, tmp_path, {CLEAN_A: _enc(a), CLEAN_B: mutate(b)}, capsys)
    found = findings(summary)
    assert expected <= found, f"{case}: missing {sorted(expected - found)}; found {sorted(found)}"
    for value in [*never, *SECRETS.values(), ACCOUNT]:
        assert value not in text, f"{case}: an injected value reached an output"


#: Classes a case must NOT report (each one an analysis artefact found by this calibration and fixed).
NOT_EXPECTED: dict[str, set[str]] = {
    "empty_file": {"L1-02:truncated"},  # an empty file is not a truncated document
    "invalid_utf8": {"L1-03:lone_surrogate"},  # surrogateescape output of the lenient pass is not a lone surrogate
    "big_int_beyond_i_json": {"L1-02:primary:big_int"},  # the strict loader accepts it: parse stays ok
    "escaped_lone_surrogate": {"L1-02:primary:lone_surrogate"},
}


@pytest.mark.parametrize("case", sorted(NOT_EXPECTED))
def test_injected_class_is_not_misattributed(l1: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str) -> None:
    mutate = next(c[1] for c in CASES if c[0] == case)
    a, b = _clean()
    summary, _text = _scan(l1, tmp_path, {CLEAN_A: _enc(a), CLEAN_B: mutate(b)}, capsys)
    assert not NOT_EXPECTED[case] & findings(summary)


def test_every_class_of_the_task_list_is_calibrated() -> None:
    """The fault list of the calibration brief: each class has at least one case above."""
    required = {"L1-02:duplicate_key", "L1-02:non_finite", "L1-02:big_int", "L1-02:lone_surrogate", "L1-02:bom",
                "L1-02:trailing_data", "L1-02:invalid_utf8", "L1-02:truncated", "L1-03:line_sep", "L1-03:bidi",
                "L1-03:tag", "L1-03:zero_width", "L1-03:fffd", "L1-03:mojibake", "L1-03:escaped_newline",
                "L1-06:account:users-dir:named", "L1-07:non_monotone", "L1-08:empty_file",
                "L1-04:trajectory_identical"}  # fmt: skip
    covered = set().union(*(c[2] for c in CASES))
    assert required <= covered
    assert any(c[0].startswith("secret_") for c in CASES)
    names = {c[0] for c in CASES}
    assert {"nan", "infinity", "float_overflow_1e400", "big_int_digits", "big_int_beyond_i_json"} <= names


# ================================================================================================ other parse paths
def _scanner(l1: Any, profile_id: str, tmp_path: Path) -> Any:
    return l1.Scanner({"profile_id": profile_id, "part": "head", "source": {"kind": "local", "root": str(tmp_path)},
                       "lenient": True})


GEMINI_LABEL = "RESULTS_build/cells/gemini_cli__glm-4.7-probe/SK-ABC__m03/gemini_stream.jsonl"
_GEMINI_LINES = [{"type": "init", "timestamp": "2026-05-01T10:00:00.000Z", "model": "gemini-2.5-pro"},
                 {"type": "message", "timestamp": "2026-05-01T10:00:01.000Z", "role": "assistant", "content": "hello"},
                 {"type": "tool_use", "timestamp": "2026-05-01T10:00:02.000Z", "tool_name": "run", "parameters": {}},
                 {"type": "result", "timestamp": "2026-05-01T10:00:03.000Z", "status": "success"}]  # fmt: skip


def _jsonl(lines: list[bytes]) -> bytes:
    return b"".join(line + b"\n" for line in lines)


@pytest.mark.parametrize(
    ("case", "mutate", "cls"),
    [
        ("duplicate_key", lambda ls: [b'{"type": "x", "type": "y"}', *ls], "duplicate_key"),
        ("nan", lambda ls: [*ls[:-1], ls[-1].replace(b'"success"}', b'"success", "x": NaN}')], "non_finite"),
        ("truncated_line", lambda ls: [*ls, b'{"type": "message",'], "truncated"),
        ("invalid_utf8", lambda ls: [ls[1].replace(b"hello", b"he\xffllo"), *ls[2:]], "invalid_utf8"),
        ("crlf", lambda ls: [ls[0] + b"\r", *ls[1:]], "crlf"),
    ],
)
def test_jsonl_parse_classes(l1: Any, tmp_path: Path, case: str, mutate: Callable[[list[bytes]], list[bytes]],
                             cls: str) -> None:  # fmt: skip
    clean = [json.dumps(x).encode() for x in _GEMINI_LINES]
    scanner = _scanner(l1, "code-agent-misalignment-geminicli", tmp_path)
    base = scanner.scan(GEMINI_LABEL, 0, _jsonl(clean), None, False)
    assert base["classes"] == [] and base["row"]["parse"] == "ok"
    assert not [k for k in base["walk"]["ptr"] if k.startswith(("L1-02", "L1-03", "L1-06"))]
    assert base["row"]["ts"]["monotone"] is True and "unterminated" not in base["row"]["flags"]
    res = scanner.scan(GEMINI_LABEL, 0, _jsonl(mutate(clean)), None, False)
    assert cls in res["classes"], f"{case}: {res['classes']}"


def _eval_bytes(sample: bytes, header: dict[str, Any] | None = None) -> bytes:
    header = header or {"version": 2, "status": "success",
                        "eval": {"task": "agentharm", "model": "openai/gpt-4o", "packages": {"inspect_ai": "0.3.100"}}}  # fmt: skip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("header.json", json.dumps(header))
        z.writestr("samples/1_epoch_1.json", sample)
    return buf.getvalue()


_SAMPLE = {"id": 1, "epoch": 1, "metadata": {"category": "Fraud"},
           "messages": [{"role": "user", "content": "hello there"}, {"role": "assistant", "content": "no"}],
           "events": [{"event": "model", "timestamp": "2026-08-01T10:00:01+00:00"},
                      {"event": "model", "timestamp": "2026-08-01T10:00:02+00:00"}],
           "scores": {"s": {"value": 1.0}}}  # fmt: skip


def test_eval_member_classes_and_no_value_leak(l1: Any, tmp_path: Path) -> None:
    label = "agentharm/results/m_harmful/2026-08-01_agentharm_x.eval"
    scanner = _scanner(l1, "survey-agentharm", tmp_path)
    base = scanner.scan(label, 0, _eval_bytes(json.dumps(_SAMPLE).encode()), None, False)
    assert base["classes"] == [] and base["row"]["n_units"] == 1 and base["row"]["ts"]["monotone"] is True
    assert not [k for k in base["walk"]["ptr"] if k.startswith(("L1-02", "L1-03", "L1-06"))]
    dup = b'{"id": 1, "id": 2, ' + json.dumps(_SAMPLE).encode()[1:]
    assert "duplicate_key" in scanner.scan(label, 0, _eval_bytes(dup), None, False)["classes"]
    secret = SECRETS["openai-api-key"]
    leaky = {**_SAMPLE, "messages": [{"role": "user", "content": f"key {secret} at /Users/{ACCOUNT}/k"}]}
    header = {"version": 2, "status": "success",
              "eval": {"task": "agentharm", "model": f"vllm//Users/{ACCOUNT}/ckpt", "packages": {"inspect_ai": "0.3.100"}}}  # fmt: skip
    res = scanner.scan(label, 0, _eval_bytes(json.dumps(leaky).encode(), header), None, False)
    ptr = res["walk"]["ptr"]
    assert ptr["L1-06\tsecret:openai-api-key\tsamples:/messages/*/content"] == 1
    assert ptr["L1-06\taccount:local-path-model\theader.json:/eval/model"] == 1
    assert {"secret_like", "local_path_model", "account_path_named"} <= set(res["row"]["flags"])
    assert res["row"]["facets"]["model"] == "<local-path-model>"
    dumped = json.dumps({k: v for k, v in res.items()}, default=str)
    assert secret not in dumped and ACCOUNT not in dumped


# ================================================================================================ masking of the fixes
def test_secret_shaped_keys_never_become_pointer_segments(l1: Any) -> None:
    assert l1.pointer_part(SECRETS["aws-access-key-id"]) == "<key>"
    assert l1.pointer_part(SECRETS["openai-api-key"]) == "<key>"
    assert l1.pointer_part("content") == "content"
    assert l1.pointer_part("jane.doe@example.org") == "<key>" and l1.pointer_part("@context") == "@context"
    sys.path.insert(0, str(TOOLS))
    try:
        import l2_common
    finally:
        sys.path.remove(str(TOOLS))
    letters_only = "sk" + "-" + "abcdefghij" * 3  # matches the plain-key rule, still secret-shaped
    assert l2_common.norm_segment(letters_only) == "{k}"
    assert l2_common.norm_segment("content") == "content"


def test_facet_and_outcome_values_mask_secret_shapes(l1: Any) -> None:
    import l1_families as fam

    assert fam.fv(SECRETS["github-token"]) == fam.SECRET_FACET
    assert fam.outcome_value(SECRETS["aws-access-key-id"]) == "<str>"
    assert fam.fv("gpt-4o") == "gpt-4o"


def test_summary_order_does_not_depend_on_completion_order(l1: Any) -> None:
    from collections import Counter

    a = Counter({"b": 2, "a": 2, "c": 5})
    b = Counter({"c": 5, "a": 2, "b": 2})
    assert l1.ranked(a) == l1.ranked(b) == [("c", 5), ("a", 2), ("b", 2)]
    assert l1.capped(a, 2) == l1.capped(b, 2) == {"a": 2, "c": 5, "<other>": 2}


def test_sample_refuses_a_label_with_an_account_path() -> None:
    sys.path.insert(0, str(TOOLS))
    try:
        import l2_sample
    finally:
        sys.path.remove(str(TOOLS))
    units = [{"label": f"runs/u{i}.json", "stratum": "s"} for i in range(3)]
    assert l2_sample.select(units, source="s", part="p", corpus_id="c")["n"] == 3
    with pytest.raises(SystemExit):
        l2_sample.select([*units, {"label": f"/Users/{ACCOUNT}/x.json", "stratum": "s"}], source="s", part="p",
                         corpus_id="c")  # fmt: skip


def test_split_pin_parts_resolve_below_the_input_directory(l1: Any, tmp_path: Path) -> None:
    """A split download pin whose file sits in a sub-directory (control-arena ``logs_tmp_zips/``): the parts are found
    under ``--input``/<pin dir> and verified (the smoke found them looked up under ``--input`` only)."""
    import hashlib

    from agentprov.adapters.profiles import load_profile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("logs/exp/run_1/2026-06-10T00-00-00_task_x.eval", _eval_bytes(json.dumps(_SAMPLE).encode()))
    data = buf.getvalue()
    half = len(data) // 2
    sub = tmp_path / "logs_tmp_zips"
    sub.mkdir()
    parts = []
    for i, chunk in enumerate((data[:half], data[half:])):
        name = f"logs_tmp_zips/demo.zip.part-{i:04d}"
        (tmp_path / name).write_bytes(chunk)
        parts.append({"file": name, "bytes": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest()})
    pin = {"role": "zip-3-003", "part": "zip-3-003", "primary": True, "kind": "hf", "dataset": "d/x",
           "revision": "0" * 40, "file": "logs_tmp_zips/demo.zip", "archive": "split-zip", "parts": parts}  # fmt: skip
    args = l1.parser().parse_args(["--source", "controlarena-persistent", "--part", "zip-3-003", "--input", str(tmp_path)])
    profile = load_profile("controlarena-persistent")
    source, info = l1.archive_source(args, profile, [pin], tmp_path, l1.IngestLimits(), {})
    assert info["input"]["archives"] == [{"file": "demo.zip", "parts": 2, "verified": True}]
    labels = [e.label for e in source.entries() if e.disposition == "listed"]
    assert labels == ["logs/exp/run_1/2026-06-10T00-00-00_task_x.eval"]
