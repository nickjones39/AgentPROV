"""Record the code identity of each Level-2 scratch import (orchestrator request 2026-10-15): which commit and which stage
code produced it, so a difference between waves (old base vs merged main) can be attributed.

    uv run python tools/precheck/code_ident.py --corpus-id C --part P     # one part
    uv run python tools/precheck/code_ident.py --all                        # every part with an l2-<part>.json

Reads ``docs/reports/precheck/data/C/l2-P.json`` (``code``: the git commit l2_check ran at) and the scratch corpus's
``derivation.json`` and ``corpus.json`` (``~/.agentprov/migration-work/precheck/C/l2-P-j2.partial``) and writes
``docs/reports/precheck/data/C/code-P.json``: commit, tracked changes, lockfile digest, Python version, and per stage
(aer, sem, prov, validation, ...) the engine and adapter code digests, the function digest, profile and rule-catalogue
digests and limits digest, exactly as the derivation records them. Digests only; no path is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO: Final = Path(__file__).resolve().parents[2]
DATA: Final = REPO / "docs" / "reports" / "precheck" / "data"
KEEP: Final = ("stage", "fn", "format", "engine", "engine_code_sha256", "adapter", "adapter_code_sha256", "fn_digest",
               "profile", "profile_sha256", "profiles", "rules", "rules_sha256", "limits_sha256", "catalogue",
               "catalogue_sha256", "spec", "options")  # fmt: skip


def scratch_root() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from l2_common import precheck_root

    return precheck_root()


def ident(corpus_id: str, part: str) -> dict[str, Any]:
    l2 = json.loads((DATA / corpus_id / f"l2-{part}.json").read_text(encoding="utf-8"))
    corpus = scratch_root() / corpus_id / f"l2-{part}-j2.partial"
    derivation = json.loads((corpus / "derivation.json").read_text(encoding="utf-8"))
    manifest = json.loads((corpus / "corpus.json").read_text(encoding="utf-8"))
    stages = [{k: s[k] for k in KEEP if k in s} for s in derivation.get("stages", []) if isinstance(s, Mapping)]
    return {
        "format": "agentprov-precheck-code/0.1",
        "corpus_id": corpus_id,
        "part": part,
        "commit": (l2.get("code") or {}).get("commit"),
        "tracked_changes": (l2.get("code") or {}).get("tracked_changes"),
        "lockfile_sha256": derivation.get("lockfile_sha256"),
        "python": derivation.get("python"),
        "agentprov_version": (manifest.get("producer") or {}).get("agentprov_version"),
        "adapters": [{k: a.get(k) for k in ("id", "version", "code_sha256")} for a in manifest.get("adapters", [])],
        "stages": stages,
    }


def write(corpus_id: str, part: str) -> Path:
    out = DATA / corpus_id / f"code-{part}.json"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from l2_common import guard_output

    guard_output(out).write_text(json.dumps(ident(corpus_id, part), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--corpus-id")
    ap.add_argument("--part")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    todo: list[tuple[str, str]] = []
    if a.all:
        for path in sorted(DATA.glob("*/l2-*.json")):
            if path.name.startswith("l2-sample-"):
                continue
            part = path.stem[len("l2-"):]
            if (scratch_root() / path.parent.name / f"l2-{part}-j2.partial" / "derivation.json").is_file():
                todo.append((path.parent.name, part))
    elif a.corpus_id and a.part:
        todo.append((a.corpus_id, a.part))
    else:
        ap.error("name --corpus-id and --part, or --all")
    for corpus_id, part in todo:
        print(write(corpus_id, part).relative_to(REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
