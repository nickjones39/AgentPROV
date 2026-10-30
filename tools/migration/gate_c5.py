"""Gate C5 (J.3.4 row C5): the frozen baseline's converter against the native importer on the upstream samples.

    uv run python tools/migration/gate_c5.py --report docs/reports/migration/C5.json [--baseline-python PY] [--work DIR]

Local, no network. Samples: the nine golden June-2024 native logs (N-C01..N-C09, ``tests/fixtures/agentdojo_prov_v1``) and
the seven head fixtures (``tests/fixtures/agentdojo/head``, every TraceLogger variant), loaded programmatically and never
printed. Per sample:

* **old**: ``tools/migration/baseline_probe.py c5`` run by the baseline interpreter (``$AGENTPROV_BASELINE_PYTHON``,
  default ``$AGENTPROV_HOME/baseline/venv-579a908/bin/python3.12``; ``-I -B``, the network blocked) calls
  ``convert_runs.convert_run(log, pipeline)`` with the pipeline the converter itself used, the log's run directory;
* **new**: the product mapper (profile ``agentdojo-upstream``, the pinned ``git`` origin) and the legacy converted view
  ``views.transcript_v1.render_converted`` (J.4.3);
* the two transcripts are compared as decoded JSON (``migration.c6.json_differences``: member presence, member order,
  type and value); each difference is an observation ``v1:<pointer>`` that the register
  ``migration/expected_differences.toml`` must absorb (``comparison = "C5"``; J.3.4). A converter refusal on the old side
  is the observation ``old:refused:<error type>``.

The report holds sample ids, pointers, register entry ids and counts; never log text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = "https://github.com/ethz-spylab/agentdojo"
PINS = {"2024": "c274885610efaaafec38b6d3eb07152ba7ff3f94", "head": "089ed468cf3ed0322acc66b0211f26d9d90dbf60"}
HEAD_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "agentdojo" / "head"
PROBE = REPO_ROOT / "tools" / "migration" / "baseline_probe.py"
HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
DEFAULT_PYTHON = HOME / "baseline" / "venv-579a908" / "bin" / "python3.12"


def samples() -> list[dict[str, Any]]:
    """``{id, path, blob, commit, data}`` of every sample (the golden native logs, then the head fixtures)."""
    from agentprov.testing import golden

    out = []
    for entry in golden.native_logs():
        out.append({"id": entry.id, "path": str(entry.origin["path"]), "blob": str(entry.origin["git_blob_sha1"]),
                    "commit": PINS["2024"], "data": entry.native_bytes()})
    for entry in json.loads((HEAD_FIXTURES / "SOURCE.json").read_bytes()):
        data = (HEAD_FIXTURES / entry["sample_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SystemExit(f"head fixture {entry['sample_file']} does not match its recorded digest")
        out.append({"id": f"head:{entry['original_path']}", "path": entry["original_path"], "blob": entry["git_blob_sha1"],
                    "commit": PINS["head"], "data": data})
    return out


def new_view(sample: dict[str, Any]) -> dict[str, Any]:
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.adapters.types import Origin
    from agentprov.aer.reader import load_aer
    from agentprov.views.transcript_v1 import render_converted

    origin = Origin.git(UPSTREAM, sample["commit"], sample["path"], sample["blob"])
    data, _info = aer_bytes(map_artefact(sample["data"], origin, profile_id="agentdojo-upstream")[0])
    with tempfile.TemporaryDirectory(prefix="agentprov-c5-") as tmp:
        path = Path(tmp) / "a.aer.jsonl"
        path.write_bytes(data)
        return render_converted(load_aer(path))


def old_transcript(sample: dict[str, Any], python: Path, work: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    out = work / hashlib.sha256(sample["id"].encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    log = out / "log.json"
    log.write_bytes(sample["data"])
    pipeline = sample["path"].split("/")[1]  # the converter's own pipeline argument: the run directory
    subprocess.run([str(python), "-I", "-B", str(PROBE), "c5", "--log", str(log), "--pipeline", pipeline, "--out", str(out)],
                   cwd=out, check=True, capture_output=True, timeout=600,
                   env={"PATH": os.environ.get("PATH", ""), "HOME": str(out)})
    probe = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    if probe.get("error"):
        return None, probe
    return json.loads((out / "transcript.json").read_text(encoding="utf-8")), probe


def main() -> int:
    from agentprov.migration.c6 import json_differences
    from agentprov.migration.xd import Observation, check, load_register

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline-python", type=Path,
                        default=Path(os.environ["AGENTPROV_BASELINE_PYTHON"]) if os.environ.get("AGENTPROV_BASELINE_PYTHON")
                        else DEFAULT_PYTHON)
    parser.add_argument("--work", type=Path, default=HOME / "migration-work" / "c5")
    parser.add_argument("--register", type=Path, default=REPO_ROOT / "migration" / "expected_differences.toml")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    observations: list[Any] = []
    items: dict[str, dict[str, Any]] = {}
    identity: Any = None
    for sample in samples():
        old, probe = old_transcript(sample, args.baseline_python, args.work)
        identity = identity or probe.get("identity")
        keys = [f"old:refused:{probe['error']}"] if old is None else [f"v1:{p}" for p in json_differences(old, new_view(sample))]
        items[sample["id"]] = {"differences": len(keys)}
        observations.extend(Observation("C5", sample["id"], key) for key in keys)
    register = load_register(args.register)
    result = check(observations, register)
    report = {
        "format": "agentprov-migration-gate/0.1", "gate": "C5", "ok": result.ok, "samples": len(items), "items": items,
        "failures": result.failures(), "absorbed_by_entry": result.counts_by_entry(),
        "observations": sorted({o.key for o in observations}),
        "baseline": {"python": str(args.baseline_python).replace(str(Path.home()), "<home>"), "identity": identity},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"C5: {len(items)} samples, ok={result.ok}, {len(observations)} observation(s), "
          f"{len(result.failures())} failure(s)")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
