"""Gate C2 (J.3.4 row C2): the frozen baseline's validators against AgentPROV's, on sampled graphs and their mutations.

    uv run --extra shacl python tools/migration/gate_c2.py --report docs/reports/migration/C2.json [--baseline DIR]

(the ``shacl`` extra: the compat ``shacl`` check needs ``pyshacl``, as the baseline environment has it; without it the
check is ``skipped`` and every compat ``shacl`` verdict differs).

Local, no network. Inputs: the 35,691 v2.3 graphs of the baseline checkout (``$AGENTPROV_BASELINE_CORPUS``,
``corpus/{corpus-prov,corpus-og-agentdojo-runs-prov}``), read as data and never printed.

**Sample** (J.3.4): ``SampleSpec(seed=20261007, per_tree=300, strata=("model_folder", "attack"))``: within a stratum items
are ordered by ``sha256(f"{seed}\\n{relpath}")`` and taken from the front, proportionally to stratum size (largest
remainder). Edge strata added in full or by their stated count: the golden pairs; every trace with ``meta.run_error``;
20 traces per tree with duplicated tool-call ids; 20 zero-tool traces per tree; 20 per defended pipeline; 4 per DoS
attack family (each in sample order).

**Per graph**, the original and each of the 13 mutations of ``c2_mutations.MUTATIONS`` that applies; plus the audit's
3-call fixture with its mutations and the constraint probes a, b, c, e.

* **old**: ``baseline_probe.py c2`` in the baseline interpreter: ``validate_prov_document`` and the five
  ``ProvValidator`` checks (``schema``, ``round_trip``, ``completeness``, ``shacl``, ``constraints``);
* **compat**: the same two functions of the frozen port ``prov/compat/adprov_v2_3`` in the AgentPROV environment. The
  verdicts must be identical per check (port fidelity across interpreters and library versions); a difference is the
  observation ``compat:<mutation>:<check>`` and no register entry may absorb it;
* **generic**: the tier-4 structure checks (``validate.prov_structure``) and constraint checks (``validate.constraints``)
  on the same document (two structure checks are AgentPROV's own format, not PROV-JSON, and are left out:
  ``pv.prov_structure.bundles``, which requires the ``core`` bundle, and ``pv.prov_structure.identifiers``, which checks
  AgentPROV node names; no v2.3 graph is meant to satisfy them), compared with the old ``schema`` and ``constraints`` verdicts; a difference is the observation
  ``generic:<mutation>:<check>:<old>-><new>``, absorbed only by a ``C2`` register entry (J.3.4).

The report holds counts, mutation names, check names and register entry ids; never graph text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = REPO_ROOT / "tools" / "migration" / "baseline_probe.py"
MUTATIONS_FILE = REPO_ROOT / "tools" / "migration" / "c2_mutations.py"
HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
DEFAULT_PYTHON = HOME / "baseline" / "venv-579a908" / "bin" / "python3.12"
SEED = 20261007
PER_TREE = 300
TREES = {"release": "corpus-prov", "converted": "corpus-og-agentdojo-runs-prov"}
DEFENCES = ("tool_filter", "transformers_pi_detector", "spotlighting_with_delimiting", "repeat_user_prompt")
CHUNK = 400
#: Structure checks of AgentPROV's own format (the core bundle, node names): not applicable to a v2.3 graph.
AGENTPROV_FORMAT_CHECKS = frozenset({"pv.prov_structure.bundles", "pv.prov_structure.identifiers"})

sys.path.insert(0, str(REPO_ROOT / "tools" / "migration"))
import c2_mutations as mutations  # noqa: E402


def _order(relpath: str) -> str:
    return hashlib.sha256(f"{SEED}\n{relpath}".encode()).hexdigest()


def _transcripts(root: Path) -> list[str]:
    out = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".transcript.json") and not name.startswith("._"):
                out.append(Path(base, name).relative_to(root).as_posix())
    return sorted(out)


def sample(baseline: Path) -> dict[str, dict[str, Any]]:
    """``item -> {tree, graph}``: the stratified sample plus the edge strata (see the module docstring)."""
    from agentprov.testing import golden

    chosen: dict[str, dict[str, Any]] = {}

    def take(tree: str, rel: str, why: str) -> None:
        item = f"{TREES[tree]}/{rel}"
        chosen.setdefault(item, {"tree": tree, "graph": str(baseline / "corpus" / TREES[tree] / (rel[: -len(".transcript.json")] + ".json")),
                                 "why": why})

    for tree, directory in TREES.items():
        root = baseline / "corpus" / directory
        rels = _transcripts(root)
        strata: dict[tuple[str, str], list[str]] = defaultdict(list)
        for rel in rels:
            parts = rel.split("/")
            strata[(parts[0], parts[2] if len(parts) > 3 else "")].append(rel)
        quotas = {k: PER_TREE * len(v) / len(rels) for k, v in strata.items()}
        floors = {k: math.floor(q) for k, q in quotas.items()}
        rest = PER_TREE - sum(floors.values())
        for k in sorted(quotas, key=lambda k: (-(quotas[k] - floors[k]), k))[:rest]:
            floors[k] += 1
        for key, members in sorted(strata.items()):
            for rel in sorted(members, key=_order)[: floors[key]]:
                take(tree, rel, "stratum")
        dup = zero = 0
        per_defence: Counter[str] = Counter()
        per_dos: Counter[str] = Counter()
        for rel in sorted(rels, key=_order):
            doc = json.loads((root / rel).read_text(encoding="utf-8"))
            meta, turns = doc.get("meta") or {}, doc.get("turns") or []
            if meta.get("run_error"):
                take(tree, rel, "run_error")
            ids = [c.get("id") for t in turns if isinstance(t, dict) for c in (t.get("tool_calls") or []) if isinstance(c, dict)]
            if len(ids) != len(set(ids)) and dup < 20:
                dup += 1
                take(tree, rel, "duplicated_tool_call_ids")
            if not ids and zero < 20:
                zero += 1
                take(tree, rel, "zero_tool")
            folder, attack = rel.split("/")[0], rel.split("/")[2] if rel.count("/") >= 3 else ""
            defence = next((d for d in DEFENCES if folder.endswith(d)), None)
            if defence is not None and per_defence[defence] < 20:
                per_defence[defence] += 1
                take(tree, rel, f"defence:{defence}")
            if "dos" in attack and per_dos[attack] < 4:
                per_dos[attack] += 1
                take(tree, rel, f"dos:{attack}")
    for entry in golden.v1_pairs():
        rel = f"{entry.origin['corpus_relpath']}.transcript.json"
        tree = "release" if entry.tree == "release" else "converted"
        if (baseline / "corpus" / TREES[tree] / rel).is_file():
            take(tree, rel, "golden")
    return chosen


def golden_sample() -> dict[str, dict[str, Any]]:
    """``--scope golden``: the 19 golden v1 pairs' graphs (committed fixtures), for CI, where the baseline corpora are
    not available (they are not in the baseline repository)."""
    from agentprov.testing import golden
    from agentprov.testing.golden import ROLE_COMPAT_GRAPH

    return {f"golden:{e.id}": {"tree": e.tree, "graph": str(e.path_of(ROLE_COMPAT_GRAPH)), "why": "golden"}
            for e in golden.v1_pairs()}


def old_verdicts(items: dict[str, dict[str, Any]], python: Path, work: Path) -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    listed = sorted(items)
    chunks = [listed[i : i + CHUNK] for i in range(0, len(listed), CHUNK)] or [[]]
    for n, chunk in enumerate(chunks):
        directory = work / f"chunk-{n:03d}"
        directory.mkdir(parents=True, exist_ok=True)
        graphs = directory / "graphs.json"
        graphs.write_text(json.dumps([[item, items[item]["graph"]] for item in chunk]), encoding="utf-8")
        subprocess.run([str(python), "-I", "-B", str(PROBE), "c2", "--graphs", str(graphs), "--mutations", str(MUTATIONS_FILE),
                        "--out", str(directory)], cwd=directory, check=True, capture_output=True, timeout=7200,
                       env={"PATH": os.environ.get("PATH", ""), "HOME": str(directory)})
        for line in (directory / "verdicts.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            out[(row["item"], row["mutation"])] = row["verdicts"]
    return out


def compat_verdicts(doc: Any) -> dict[str, str]:
    from agentprov.prov.compat.adprov_v2_3.conformance import ProvValidator
    from agentprov.prov.compat.adprov_v2_3.validate import validate_prov_document

    out: dict[str, str] = {}
    try:
        out["validate"] = "pass" if validate_prov_document(doc).ok else "fail"
    except Exception as exc:  # noqa: BLE001 - the verdict records what the ported code does
        out["validate"] = f"raised:{type(exc).__name__}"
    try:
        for check in ProvValidator(ProvValidator.ALL_CHECKS).validate(doc).checks:
            out[check.name] = str(check.status)
    except Exception as exc:  # noqa: BLE001
        out["conformance"] = f"raised:{type(exc).__name__}"
    return out


def generic_verdicts(doc: Any) -> dict[str, str]:
    from agentprov.validate import constraints, prov_structure
    from agentprov.validate._provdoc import ProvView

    out: dict[str, str] = {}
    try:
        outcomes = [o for o in prov_structure.check(doc) if o.id not in AGENTPROV_FORMAT_CHECKS]
        out["schema"] = "fail" if any(o.status == "fail" for o in outcomes) else "pass"
    except Exception as exc:  # noqa: BLE001 - a raise is a finding of this gate
        out["schema"] = f"raised:{type(exc).__name__}"
    try:
        checks, _diagnostics = constraints.check(ProvView.parse(doc))
        out["constraints"] = "fail" if any(o.status == "fail" for o in checks) else "pass"
    except Exception as exc:  # noqa: BLE001
        out["constraints"] = f"raised:{type(exc).__name__}"
    return out


def _documents(items: dict[str, dict[str, Any]]) -> Any:
    from agentprov.prov.compat.adprov_v2_3.build_prov import build_prov

    fixture = build_prov(mutations.three())
    for item in ["fixture:three", *sorted(items)]:
        doc = fixture if item == "fixture:three" else json.loads(Path(items[item]["graph"]).read_text(encoding="utf-8"))
        yield item, "original", doc
        for name, mutate in mutations.MUTATIONS.items():
            mutated = mutate(doc)
            if mutated is not None:
                yield item, name, mutated
        if item == "fixture:three":
            for name, probe in mutations.PROBES.items():
                yield item, name, probe(doc)


def main() -> int:
    from agentprov.migration.xd import Observation, check, load_register

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=os.environ.get("AGENTPROV_BASELINE_CORPUS"))
    parser.add_argument("--baseline-python", type=Path,
                        default=Path(os.environ["AGENTPROV_BASELINE_PYTHON"]) if os.environ.get("AGENTPROV_BASELINE_PYTHON")
                        else DEFAULT_PYTHON)
    parser.add_argument("--work", type=Path, default=HOME / "migration-work" / "c2")
    parser.add_argument("--register", type=Path, default=REPO_ROOT / "migration" / "expected_differences.toml")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="development: the first N sampled items only")
    parser.add_argument("--scope", choices=("sample", "golden"), default="sample",
                        help="sample: the J.3.4 sample of the baseline corpora; golden: the golden graphs only (CI)")
    args = parser.parse_args()
    if args.scope == "golden":
        items = golden_sample()
    elif args.baseline is None:
        parser.error("--baseline or $AGENTPROV_BASELINE_CORPUS is required for --scope sample")
    else:
        items = sample(Path(args.baseline))
    if args.limit is not None:
        items = {k: items[k] for k in sorted(items)[: args.limit]}
    old = old_verdicts(items, args.baseline_python, args.work)
    observations: list[Any] = []
    rows = 0
    why = Counter(v["why"] for v in items.values())
    verdict_table: Counter[tuple[str, str, str, str, str]] = Counter()
    for item, mutation, doc in _documents(items):
        rows += 1
        before = old.get((item, mutation))
        if before is None:
            observations.append(Observation("C2", f"item:{item}", f"compat:{mutation}:missing_old_row"))
            continue
        compat = compat_verdicts(doc)
        for name in sorted(set(before) | set(compat)):
            if before.get(name) != compat.get(name):
                observations.append(Observation("C2", f"item:{item}", f"compat:{mutation}:{name}"))
        generic = generic_verdicts(doc)
        for name, new in sorted(generic.items()):
            was = before.get(name, before.get("conformance", "absent"))
            verdict_table[(mutation, name, was, new, "same" if was == new else "differs")] += 1
            if was != new:
                observations.append(Observation("C2", f"item:{item}", f"generic:{mutation}:{name}:{was}->{new}"))
    register = load_register(args.register)
    result = check(observations, register)
    report = {
        "format": "agentprov-migration-gate/0.1", "gate": "C2", "scope": args.scope, "ok": result.ok, "sampled_items": len(items),
        "sample_reasons": dict(sorted(why.items())), "documents_validated": rows,
        "compat_differences": sum(1 for o in observations if o.key.startswith("compat:")),
        "generic_verdicts": [{"mutation": m, "check": c, "old": o, "new": n, "count": k}
                             for (m, c, o, n, _s), k in sorted(verdict_table.items())],
        "failures": result.failures()[:200], "absorbed_by_entry": result.counts_by_entry(),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"C2: {len(items)} items, {rows} documents, ok={result.ok}, compat differences {report['compat_differences']}, "
          f"{len(result.failures())} failure(s)")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
