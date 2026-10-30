"""``tools/scan_origins.py`` (D-810): where an address first appears in each execution's AER, by digest.

Corpora here are synthetic trees of AER-shaped lines (the tool reads the records' fields, not their schema). No address
is written in this repository: they are assembled at run time, and no output may hold one.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from agentprov.corpus import personas as pe

TOOLS = Path(__file__).resolve().parents[3] / "tools"
sys.path.insert(0, str(TOOLS))
_spec = importlib.util.spec_from_file_location("scan_origins_tool", TOOLS / "scan_origins.py")
assert _spec is not None and _spec.loader is not None
so = importlib.util.module_from_spec(_spec)
sys.modules["scan_origins_tool"] = so
_spec.loader.exec_module(so)


def addr(local: str, domain: str) -> str:
    return "@".join((local, domain))


PERSONA = addr("benchmark.person", "bench-co.com")   # supplied by the benchmark's user message
MODEL = addr("model.invented", "invented-co.com")      # only in the agent's output
FREE_MODEL = addr("someone.real", "gmail.com")         # only in the agent's tool-call arguments, a public mail domain
COPIED = addr("copied.person", "bench-co.com")         # in a tool result, later repeated by the agent
UPSTREAM = addr("in.the.suite", "bench-co.com")
RAW_ONLY = addr("raw.only", "bench-co.com")


def digest(a: str) -> str:
    return pe.address_digest(a.encode())


def aer(ex: str, suite: str, task: str, *, user: str = "", agent: str = "", call_args: dict | None = None,
        tool_result: str = "", agent_late: str = "") -> list[dict]:
    """One execution: header, actors, user message m1, agent message m2 (with a tool call), tool result m3, agent reply m4."""
    rows = [
        {"k": "execution", "id": "exec", "ex": ex, "task": {"suite": suite, "task_id": task}},
        {"k": "actor", "id": "user", "kind": "simulated_user"}, {"k": "actor", "id": "agent", "kind": "llm_agent"},
        {"k": "actor", "id": "env", "kind": "tool_runtime"},
        {"k": "message", "id": "m1", "actor": "user", "parts": [{"t": "text", "text": f"please write to {user}"}]},
        {"k": "message", "id": "m2", "actor": "agent", "parts": [{"t": "text", "text": f"ok {agent}"},
                                                                  {"t": "tool_call", "args": call_args or {}}]},
        {"k": "tool_execution", "id": "te0", "actor": "env", "call": "m2#1", "args": call_args or {}, "status": "ok"},
        {"k": "message", "id": "m3", "actor": "env", "parts": [{"t": "tool_result", "text": f"sent {tool_result}"}]},
        {"k": "message", "id": "m4", "actor": "agent", "parts": [{"t": "text", "text": f"done {agent_late}"}]},
    ]
    return rows


def write_corpus(root: Path, executions: list[tuple[str, list[dict]]], raw_text: dict[str, str] | None = None) -> Path:
    corpus = root / "corp.partial"
    (corpus / "aer" / "aa").mkdir(parents=True)
    (corpus / "raw" / "objects" / "00").mkdir(parents=True)
    index = []
    for n, (ex, rows) in enumerate(executions):
        (corpus / "aer" / "aa" / f"{ex}.aer.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        sha = f"{n:064x}"
        text = (raw_text or {}).get(ex, json.dumps(rows))
        (corpus / "raw" / "objects" / "00" / f"{sha}.json").write_text(text)
        index.append({"ex": ex, "raw": [{"sha256": "sha256:" + sha, "role": "primary", "included": True},
                                        {"sha256": "sha256:" + "f" * 64, "role": "supporting", "included": True}]})
    (corpus / "executions.jsonl").write_text("\n".join(json.dumps(r) for r in index) + "\n")
    return corpus


EX = [("ex_" + c * 26) for c in "abcd"]


@pytest.fixture
def corpus(tmp_path):
    return write_corpus(tmp_path, [
        (EX[0], aer(EX[0], "workspace", "user_task_1", user=PERSONA, agent=f"{PERSONA} {MODEL}",
                    call_args={"to": FREE_MODEL}, tool_result=COPIED, agent_late=COPIED)),
        (EX[1], aer(EX[1], "banking", "user_task_2", agent=MODEL, call_args={"to": FREE_MODEL})),
        (EX[2], aer(EX[2], "banking", "user_task_3", agent=UPSTREAM)),
        (EX[3], aer(EX[3], "slack", "user_task_4", agent="nothing")),
    ], raw_text={EX[3]: f'{{"author": "{RAW_ONLY}"}}'})


def run(corpus: Path, tmp_path: Path, *extra: str, capsys=None):
    return so.main(["--corpus", str(corpus), "--workers", "1", *extra])


def test_first_appearance_is_by_position_and_a_copy_does_not_make_an_address_model_generated(corpus):
    _ex, found = so.first_appearances(corpus / "aer" / "aa" / f"{EX[0]}.aer.jsonl",
                                      frozenset(map(digest, (PERSONA, MODEL, FREE_MODEL, COPIED))))
    assert found[digest(PERSONA)][1:] == ("bench", "m1", "/parts/0/text", "simulated_user")
    assert found[digest(MODEL)][1:] == ("model", "m2", "/parts/0/text", "llm_agent")
    assert found[digest(FREE_MODEL)][1] == "model" and found[digest(FREE_MODEL)][4] == "llm_agent"  # a tool call's arguments
    assert found[digest(COPIED)][1] == "bench"  # first in a tool result (m3), repeated by the agent at m4


def test_the_origin_classes_and_the_withholding_numbers(corpus, tmp_path, capsys):
    upstream = {digest(UPSTREAM): "x"}
    result = so.analyse(corpus, upstream, frozenset(), workers=1)
    classes = result["_classes"]
    assert classes[digest(PERSONA)] == "benchmark-input" and classes[digest(COPIED)] == "benchmark-input"
    assert classes[digest(MODEL)] == "model-generated" and classes[digest(FREE_MODEL)] == "withhold"
    assert digest(UPSTREAM) not in classes  # found in upstream data: set aside
    rows = result["by_origin_and_class"]
    assert rows["benchmark-input|other"]["addresses"] == 2
    assert rows["model-generated|other"]["addresses"] == 1 and rows["model-generated|public-freemail"]["addresses"] == 1
    assert rows["not-in-aer|raw-only|other"]["addresses"] == 1  # the one only in a (cited) raw object: D-962
    withheld = result["withhold_model_generated_freemail"]
    assert withheld == {"addresses": 1, "executions": 2, "raw_objects": 2, "executions_via_shared_objects": 2,
                        "by_suite": {"banking": 1, "workspace": 1}, "distinct_tasks": 2}  # the shared supporting object is not counted
    assert result["not_found"] == 5 and result["mixed"] == 0


def test_an_address_only_in_a_raw_object_no_execution_cites_is_withhold_object(corpus, tmp_path):
    """Path-scan 6 (D-810): an object the import stores but no execution indexes; sealing withholds the object."""
    UNCITED = addr("uncited.person", "bench-co.com")
    (corpus / "raw" / "objects" / "00" / f"{'e' * 64}.json").write_text(f'{{"to": "{UNCITED}"}}')
    result = so.analyse(corpus, {digest(UPSTREAM): "x"}, frozenset(), workers=1)
    assert result["_classes"][digest(UNCITED)] == "withhold-object" and result["_evidence"][digest(UNCITED)] == (
        "sha256:" + "e" * 64,)
    assert result["_classes"][digest(RAW_ONLY)] == "withhold-object"  # only in a cited object: withheld alone (D-962)
    assert result["withhold_object"] == {"addresses": 2, "raw_objects": 2} and result["not_in_aer_other"] == 0
    out = tmp_path / "o.personas.toml"
    so.write_observed_file(out, "o", "bench", "corp", ("https://example.org/o/r", "a" * 40), result["_classes"],
                           result["_evidence"])
    parsed = pe.parse_persona_file(out.read_bytes())
    assert parsed.by_class["withhold-object"] == frozenset({digest(UNCITED), digest(RAW_ONLY)}) and "@" not in out.read_text()


def test_an_address_benchmark_supplied_in_one_execution_and_model_made_in_another_is_mixed_benchmark_input(tmp_path):
    root = write_corpus(tmp_path, [
        (EX[0], aer(EX[0], "workspace", "t1", user=PERSONA)),
        (EX[1], aer(EX[1], "workspace", "t2", agent=PERSONA)),
    ])
    result = so.analyse(root, {}, frozenset(), workers=1)
    assert result["_classes"][digest(PERSONA)] == "benchmark-input" and result["mixed"] == 1
    ex, (_pos, origin, record, pointer, actor) = result["_evidence"][digest(PERSONA)]
    assert (ex, origin, record, actor) == (EX[0], "bench", "m1", "simulated_user")


def test_an_address_used_as_an_object_key_is_found_and_its_evidence_pointer_carries_no_address(tmp_path):
    key_address = addr("shared.with", "bench-co.com")
    rows = aer(EX[0], "workspace", "t1")
    rows.append({"k": "state_change", "id": "sc0", "cause": "te0", "patch": {"files": {"f1": {"shared_with": {key_address: "r"}}}}})
    root = write_corpus(tmp_path, [(EX[0], rows)])
    result = so.analyse(root, {}, frozenset(), workers=1)
    assert result["_classes"][digest(key_address)] == "benchmark-input"  # an environment state change
    _ex, (_pos, _origin, record, pointer, actor) = result["_evidence"][digest(key_address)]
    assert (record, pointer, actor) == ("sc0", "/patch/files/f1/shared_with/*", "tool_runtime")
    assert "@" not in pointer and not result["by_origin_and_class"].get("not-in-aer|other")
    nested = addr("outer.key", "bench-co.com")
    rows2 = aer(EX[1], "workspace", "t2")
    rows2.append({"k": "fixture", "id": "fx", "content": {nested: {"inner": f"x {key_address}"}}})
    root2 = write_corpus(tmp_path / "two", [(EX[1], rows2)])
    result2 = so.analyse(root2, {}, frozenset(), workers=1)
    pointers = {e[1][3] for e in result2["_evidence"].values()}
    assert pointers == {"/content/*", "/content/*/inner"}  # a key above an address is written *, never the address


def test_set_aside_addresses_are_not_classified(corpus):
    result = so.analyse(corpus, {digest(PERSONA): "f"}, frozenset({digest(MODEL)}), workers=1)
    assert digest(PERSONA) not in result["_classes"] and digest(MODEL) not in result["_classes"]


def test_the_output_line_has_no_address_and_the_persona_file_is_digests_with_evidence(corpus, tmp_path, capsys):
    out = tmp_path / "corp.observed.personas.toml"
    assert run(corpus, tmp_path, "--pin", "https://github.com/o/r", "a" * 40, "--source-id", "bench", "--corpus-id", "corp",
               "--id", "corp-observed", "--out", str(out)) == 0
    printed = capsys.readouterr()
    text = out.read_text()
    for blob in (printed.out, printed.err, text):
        assert "@" not in blob.replace("sha256:", "") and "bench-co" not in blob and "gmail" not in blob
    parsed = pe.parse_persona_file(out.read_bytes())
    assert parsed.by_class["benchmark-input"] == {digest(PERSONA), digest(COPIED)}
    assert parsed.by_class["model-generated"] == {digest(MODEL), digest(UPSTREAM)}  # no upstream given
    assert parsed.by_class["withhold"] == {digest(FREE_MODEL)}  # model output only, at a public mail provider
    entry = next(e for g in parsed.groups for e in g["entries"] if e["address"] == digest(PERSONA))
    assert (entry["ex"], entry["record"], entry["pointer"], entry["actor_kind"]) == (EX[0], "m1", "/parts/0/text",
                                                                                      "simulated_user")
    assert json.loads(printed.out.splitlines()[0])["corpus"] == "corp"


def test_out_needs_its_evidence_arguments(corpus, tmp_path):
    assert run(corpus, tmp_path, "--out", str(tmp_path / "x.personas.toml")) == 2


def test_the_reserved_and_file_name_addresses_are_set_aside_by_the_tool(tmp_path):
    root = write_corpus(tmp_path, [(EX[0], aer(EX[0], "s", "t", agent=addr("x", "example.com") + " " + addr("icon", "2x.png")))])
    names = tmp_path / "n.personas.toml"
    names.write_text('format = "agentprov-personas/0.1"\nid = "n"\n[[group]]\nclass = "file-name"\nsource_id = "s"\n'
                     f'repo = "https://example.org/o/r"\ncommit = "{"a" * 40}"\nfile = "x.json"\n'
                     f'addresses = ["{digest(addr("icon", "2x.png"))}"]\n')
    result = so.analyse(root, {}, pe.parse_persona_file(names.read_bytes()).file_names, workers=1)
    assert result["not_found"] == 0 and result["by_origin_and_class"] == {}


def test_an_address_the_bytes_hold_but_the_decoded_text_does_not_takes_its_records_origin_d962(tmp_path):
    """D-962: the release scan reads stored bytes. A string with one literal backslash before ``b...`` is stored with two;
    after an even run of backslashes the byte reader does not take ``b`` for an escape and finds the whole address, while
    the decoded text (one backslash: ``\\b`` is an escape there) yields it without its ``b``. The byte reader's digest is
    in no decoded string, so it is the record's: here the agent's, at a public mail provider, ``withhold``, with the whole
    record (pointer ``""``) as evidence."""
    full = addr("bora.cut", "gmail.com")
    rows = aer(EX[0], "workspace", "user_task_1", agent="path C:\\" + full)
    corpus = write_corpus(tmp_path, [(EX[0], rows)], raw_text={EX[0]: "{}"})
    line = (corpus / "aer" / "aa" / f"{EX[0]}.aer.jsonl").read_bytes()
    assert digest(full) in {pe.address_digest(r) for _s, r in pe.find_addresses(line)}  # the byte reader's address
    text = rows[5]["parts"][0]["text"].encode()
    assert digest(full) not in {pe.address_digest(r) for _s, r in pe.find_addresses(text)}  # not the decoded text's
    result = so.analyse(corpus, {}, frozenset(), workers=1)
    assert result["_classes"][digest(full)] == "withhold"
    assert result["_evidence"][digest(full)][1][1:4] == ("model", "m2", "")
    assert result["not_in_aer_other"] == 0
