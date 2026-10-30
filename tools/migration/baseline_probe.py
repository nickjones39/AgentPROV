"""The only door to the frozen baseline package for the differential gates (docs/architecture J.1.6 step 3; J.3.4).

Run by the **baseline interpreter** (``$AGENTPROV_BASELINE_PYTHON``, built by ``build_baseline_env.py``), never by an
AgentPROV environment, as a subprocess with ``-I -B`` and the gate work directory as its working directory. It reads
input paths and writes JSON results into the given output directory only; it never writes elsewhere (the baseline's
own outputs go to ``--out``; its renderer is replaced by a no-op, so no graphviz call happens).

    <baseline python> -I -B tools/migration/baseline_probe.py identity --out DIR
    <baseline python> -I -B tools/migration/baseline_probe.py c6 --scenario SCENARIO.json --out DIR
    <baseline python> -I -B tools/migration/baseline_probe.py c5 --log LOG.json --pipeline NAME --out DIR
    <baseline python> -I -B tools/migration/baseline_probe.py c2 --graphs LIST.json --mutations c2_mutations.py --out DIR
    <baseline python> -I -B tools/migration/baseline_probe.py c3 --corpus BASELINE_CORPUS_DIR --out DIR

``identity`` writes ``probe.json`` with what J.1.6 step 4 requires of every result: ``agentdojo_prov.__file__``, the
``importlib.metadata`` versions and the installed distribution's ``direct_url.json`` (absent for a wheel install).

``c6`` runs one gate-C6 scenario through the **baseline generator itself**: ``generate._run_one_benign`` or
``generate._run_one_injection`` (``make_instrumented_pipeline`` + ``_CompatLLM`` via ``build_llm``, the
``MODEL_NAMES`` registration, the ``_trace_meta``/``_model_config_from_llm`` meta, the transcript and graph writers),
exactly as a v2.3 generation cell ran. The scripted responses of ``tests/test_attempts.py`` are served at the **wire**
level: ``openai.OpenAI`` is wrapped so that the SDK client the baseline builds gets an ``httpx2.MockTransport`` that
returns, for the n-th request, the exact status, headers and body bytes in the scenario file (rendered by the
backend's ``agentprov_backend.testing.transport.render_response``, the bytes the new side's ``ScriptedTransport``
serves). The baseline's ``_FakeClient`` returned parsed SDK objects and raised a generic ``APIStatusError`` for HTTP
errors (D.10.10 item 18: its 400 case counted three attempts that a real ``BadRequestError`` never makes); serving
wire bytes makes the SDK raise what it raises for a real provider. ``time.sleep`` is a no-op (as in the baseline test
fixture); nothing else is patched.

Outputs in ``--out``: ``transcript.json`` and ``graph.json`` (the generator's files, bytes unchanged) when it wrote
them; ``requests/<n>.json`` (every wire request body); ``probe.json`` (identity, the generation-log row with its
``error``, the ``MODEL_NAMES`` keys the cell added, the number of requests served and whether the script ran out).
Scenario text is data; this script prints none of it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROBE_FORMAT = "agentprov-baseline-probe/1"
_SCRUB = ("REASONING_EFFORT", "REASONING_PASSBACK", "LLM_TIMEOUT_S", "ADPROV_ALLOW_MIXED_CONFIG")


def identity() -> dict[str, Any]:
    import importlib.metadata as md

    import agentdojo_prov

    dist = md.distribution("agentdojo-prov")
    direct = dist.read_text("direct_url.json")
    return {
        "agentdojo_prov_file": str(Path(agentdojo_prov.__file__).resolve()),
        "python": sys.version.split()[0],
        "versions": {name: md.version(name) for name in ("agentdojo-prov", "agentdojo", "openai", "httpx2", "pydantic")},
        "direct_url": json.loads(direct) if direct else None,
    }


def _plain(value: Any) -> Any:
    """The generator's row as JSON (``pd.NA`` -> null; numpy scalars -> Python)."""
    try:
        import pandas as pd

        if value is pd.NA:
            return None
    except ImportError:  # pragma: no cover - pandas is in the frozen environment
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return value.item()
    return value


def _block_network() -> None:
    """Offline guarantee: any socket connection or name lookup fails (the wire is the mock transport)."""
    import socket

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise OSError("network blocked by the baseline probe")

    socket.socket.connect = refuse  # type: ignore[method-assign]
    socket.create_connection = refuse  # type: ignore[assignment]
    socket.getaddrinfo = refuse  # type: ignore[assignment]


def run_c6(scenario_path: Path, out: Path) -> dict[str, Any]:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    old = scenario["old"]
    for key in _SCRUB:
        os.environ.pop(key, None)
    os.environ.update({str(k): str(v) for k, v in old["env"].items()})
    time.sleep = lambda s: None  # type: ignore[assignment]  # the baseline test fixture's no-op sleep

    import httpx2
    import openai
    from agentdojo.models import MODEL_NAMES

    from agentdojo_prov import generate, runtime

    wire = scenario["wire"]
    served: list[bytes] = []
    state = {"exhausted": False}

    def handler(request: Any) -> Any:
        body = request.read()
        served.append(bytes(body))
        n = len(served) - 1
        if n >= len(wire):
            state["exhausted"] = True
            raise RuntimeError(f"C6 script exhausted after {len(wire)} steps")
        step = wire[n]
        if step.get("connect_error") is not None:
            raise httpx2.ConnectError(str(step["connect_error"]), request=request)
        return httpx2.Response(int(step["status"]), headers=dict(step["headers"]),
                               content=base64.b64decode(step["body_b64"]))

    real_openai = openai.OpenAI

    def scripted_openai(**kwargs: Any) -> Any:
        kwargs["http_client"] = openai.DefaultHttpx2Client(transport=httpx2.MockTransport(handler))
        return real_openai(**kwargs)

    openai.OpenAI = scripted_openai  # type: ignore[misc]  # the baseline's runtime builds its client through this name
    generate.render_prov_json = lambda *a, **k: None  # no graphviz; generation writes the graph after the render

    before = list(MODEL_NAMES)
    prov_dir = out / "prov"
    suite = runtime.load_suite(old["suite"])
    if old["kind"] == "benign":
        row = generate._run_one_benign(suite, old["model"], old["user_task"], prov_dir=prov_dir,
                                       suite_name=old["suite"], skip_existing=False)
        stem = prov_dir / "benign" / f"{old['suite']}_{old['user_task']}_benign"
    else:
        row = generate._run_one_injection(suite, old["model"], old["user_task"], old["injection_task"], old["attack"],
                                          prov_dir=prov_dir, suite_name=old["suite"], skip_existing=False)
        safe = old["injection_task"].replace("_", "")
        stem = prov_dir / old["attack"] / f"{old['suite']}_{old['user_task']}_x_{safe}_injection"
    added = [k for k in MODEL_NAMES if k not in before]
    added_names = {k: MODEL_NAMES[k] for k in added}

    files = {}
    for suffix, name in ((".transcript.json", "transcript.json"), (".json", "graph.json")):
        src = stem.with_name(stem.name + suffix)
        if src.is_file():
            shutil.copyfile(src, out / name)
            files[name] = hashlib.sha256(src.read_bytes()).hexdigest()
    shutil.rmtree(prov_dir, ignore_errors=True)
    req_dir = out / "requests"
    req_dir.mkdir(exist_ok=True)
    for n, body in enumerate(served):
        (req_dir / f"{n}.json").write_bytes(body)
    return {
        "probe": PROBE_FORMAT,
        "scenario": scenario["name"],
        "identity": identity(),
        "row": {str(k): _plain(v) for k, v in row.items()},
        "model_names_added": added_names,
        "n_requests": len(served),
        "n_steps": len(wire),
        "script_exhausted": state["exhausted"],
        "files": files,
    }


def run_c5(log_path: Path, pipeline: str, out: Path) -> dict[str, Any]:
    """Gate C5's old side (J.3.4 row C5): the baseline converter ``convert_runs.convert_run`` on one native AgentDojo log.

    The log is read as the converter reads it (``json.loads`` of the file's text); ``convert_run(run, pipeline)`` returns
    the transcript/v1 document and its graph, written to ``transcript.json`` and ``graph.json`` with the member order the
    converter built (``json.dumps``, no sorting). A ``KeyError``/``TypeError`` (the converter's refusal of a malformed
    log) is recorded as ``error`` (its type only). No text of the log is printed."""
    from agentdojo_prov import convert_runs

    run = json.loads(log_path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {"probe": PROBE_FORMAT, "c5": True, "identity": identity(), "pipeline_given": bool(pipeline)}
    try:
        transcript, graph = convert_runs.convert_run(run, pipeline)
    except (KeyError, TypeError) as exc:
        result["error"] = type(exc).__name__
        return result
    (out / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    result["error"] = None
    return result


def c2_verdicts(doc: Any, validate_prov_document: Any, validator: Any) -> dict[str, str]:
    """Gate C2's per-check verdicts of one document: ``validate`` (``validate_prov_document``) and the five
    ``ProvValidator`` checks; an exception is the verdict ``raised:<type>`` (the whole validator for ``conformance``)."""
    out: dict[str, str] = {}
    try:
        out["validate"] = "pass" if validate_prov_document(doc).ok else "fail"
    except Exception as exc:  # noqa: BLE001 - the verdict records what the old code does
        out["validate"] = f"raised:{type(exc).__name__}"
    try:
        for check in validator.validate(doc).checks:
            out[check.name] = str(check.status)
    except Exception as exc:  # noqa: BLE001
        out["conformance"] = f"raised:{type(exc).__name__}"
    return out


def run_c2(graphs: Path, mutations_path: Path, out: Path) -> dict[str, Any]:
    """Gate C2's old side (J.3.4 row C2): the baseline validators on every listed graph and its mutations, and on the
    audit fixture with its constraint probes. Writes ``verdicts.jsonl``: ``{item, mutation, verdicts}`` per line."""
    import importlib.util

    from agentdojo_prov.build_prov import build_prov
    from agentdojo_prov.conformance import ProvValidator
    from agentdojo_prov.validate import validate_prov_document

    spec = importlib.util.spec_from_file_location("c2_mutations", mutations_path)
    assert spec is not None and spec.loader is not None
    mutations = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mutations)
    validator = ProvValidator(ProvValidator.ALL_CHECKS)
    rows = 0
    with (out / "verdicts.jsonl").open("w", encoding="utf-8") as sink:
        def emit(item: str, mutation: str, doc: Any) -> None:
            nonlocal rows
            row = {"item": item, "mutation": mutation, "verdicts": c2_verdicts(doc, validate_prov_document, validator)}
            sink.write(json.dumps(row, sort_keys=True) + "\n")
            rows += 1

        fixture = build_prov(mutations.three())
        listed = [("fixture:three", None)] + [(str(i), Path(p)) for i, p in json.loads(graphs.read_text(encoding="utf-8"))]
        for item, path in listed:
            doc = fixture if path is None else json.loads(path.read_text(encoding="utf-8"))
            emit(item, "original", doc)
            for name, mutate in mutations.MUTATIONS.items():
                mutated = mutate(doc)
                if mutated is not None:
                    emit(item, name, mutated)
            if path is None:
                for name, probe in mutations.PROBES.items():
                    emit(item, name, probe(doc))
    return {"probe": PROBE_FORMAT, "c2": True, "identity": identity(), "rows": rows,
            "fixture_sha256": hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()}


#: The ``stats.trace_record`` fields and replay-row fields ``scoring.score_trace`` reads (579a908 scoring.py l.44-98).
C3_REC_FIELDS = ("attack_type", "security", "utility", "rerun_detected", "n_turns", "marker_status",
                 "user_prompt_names_attack_account", "user_task_meets_injection_check")
C3_ROW_FIELDS = ("replay_error", "security", "utility", "security_logging_checker", "earlier_pass_evidence",
                 "injection_check_winnable")


def run_c3(corpus: Path, out: Path) -> dict[str, Any]:
    """Gate C3's old side (J.3.4 row C3): ``stats.trace_record`` and ``scoring.score_trace`` over every trace of both
    baseline trees, with each model folder's ``outcome_replay.json`` row (``{}`` where the folder has none, as
    ``ml_export`` passes an absent row). Writes ``verdicts.jsonl``: ``{item, verdict, rec, row, run_error,
    replay_file}``, ``rec`` and ``row`` restricted to the fields ``score_trace`` reads (labels and booleans, no text)."""
    from agentdojo_prov.replay import load_replay
    from agentdojo_prov.scoring import score_trace
    from agentdojo_prov.stats import iter_transcripts, trace_record

    rows = 0
    folders: dict[str, bool] = {}
    with (out / "verdicts.jsonl").open("w", encoding="utf-8") as sink:
        for tree in ("corpus-prov", "corpus-og-agentdojo-runs-prov"):
            replay_cache: dict[str, dict[str, Any]] = {}
            for model_folder, attack_dir, tpath in iter_transcripts(corpus / tree):
                if model_folder not in replay_cache:
                    replay_cache[model_folder] = load_replay(tpath.parents[2], required=False)
                    folders[f"{tree}/{model_folder}"] = bool(replay_cache[model_folder])
                transcript = json.loads(tpath.read_text(encoding="utf-8"))
                rec = trace_record(tpath, transcript)
                stem = tpath.name.replace(".transcript.json", "")
                row = replay_cache[model_folder].get(f"{attack_dir}/{stem}") or {}
                run_error = bool((transcript.get("meta") or {}).get("run_error"))
                verdict = score_trace(rec, row, run_error=run_error)
                sink.write(json.dumps({
                    "item": f"{tree}/{model_folder}/prov/{attack_dir}/{stem}", "verdict": verdict, "run_error": run_error,
                    "rec": {k: _plain(rec.get(k)) for k in C3_REC_FIELDS},
                    "row": {k: _plain(row.get(k)) for k in C3_ROW_FIELDS if k in row},
                }, sort_keys=True) + "\n")
                rows += 1
    return {"probe": PROBE_FORMAT, "c3": True, "identity": identity(), "rows": rows,
            "replay_files": dict(sorted(folders.items()))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_id = sub.add_parser("identity")
    p_id.add_argument("--out", type=Path, required=True)
    p_c6 = sub.add_parser("c6")
    p_c6.add_argument("--scenario", type=Path, required=True)
    p_c6.add_argument("--out", type=Path, required=True)
    p_c2 = sub.add_parser("c2")
    p_c2.add_argument("--graphs", type=Path, required=True)
    p_c2.add_argument("--mutations", type=Path, required=True)
    p_c2.add_argument("--out", type=Path, required=True)
    p_c3 = sub.add_parser("c3")
    p_c3.add_argument("--corpus", type=Path, required=True, help="the baseline checkout's corpus/ directory")
    p_c3.add_argument("--out", type=Path, required=True)
    p_c5 = sub.add_parser("c5")
    p_c5.add_argument("--log", type=Path, required=True)
    p_c5.add_argument("--pipeline", required=True)
    p_c5.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    _block_network()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.cmd == "identity":
        result = identity()
    elif args.cmd == "c2":
        result = run_c2(args.graphs, args.mutations, args.out)
    elif args.cmd == "c3":
        result = run_c3(args.corpus, args.out)
    elif args.cmd == "c5":
        result = run_c5(args.log, args.pipeline, args.out)
    else:
        result = run_c6(args.scenario, args.out)
    (args.out / "probe.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
