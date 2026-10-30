"""Generate ``migration/baseline.lock.json`` once from the baseline (docs/architecture J.1.5), then freeze it.

    uv run python tools/migration/make_baseline_lock.py \\
        --baseline /path/to/AgentDojo-PROV-framework --investigation /path/to/investigation/baseline [--out FILE]

Reads ``baseline.json`` from the investigation directory, the tracked-file digests and tag objects from the old repo (git
only, read-only) and the five tree listings of J.1.4 from its gitignored ``corpus/`` and ``runs/``. The recorded results
are the J.1.2 values. The J.1.6 hashes (``requirements_lock_sha256``, ``baseline_wheel_sha256``) are taken from
``--requirements`` (``migration/baseline-requirements.txt``) and ``--wheel`` (the wheel kept by
``tools/migration/build_baseline_env.py`` in ``<venv>/wheel/``); each stays ``null`` when its option is not given.
The lock is regenerated deliberately, never edited. Refuses to overwrite an existing lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from agentprov.migration.lock import LOCK_FORMAT, PREDICATES, TREE_SPECS, parse_lock, tree_listing

FROZEN_ON = "2026-10-07"
TAG = "agentprov-baseline-2026-10-07"
RESULTS = {  # J.1.2 (investigation/baseline/baseline.json and J-M2/J-M3 byte checks)
    "pytest": {"collected": 363, "passed": 362, "failed": 0, "skipped": 1, "warnings": 693},
    "pytest_slow": {"passed": 3},
    "recompute_dry_run": {"release": {"seen": 17664, "changed": 0}, "converted": {"seen": 18027, "changed": 0}},
    "byte_rederivation": {"release": [17664, 17664], "converted": [18027, 18027]},
    "converter_bytes": {"logs": 18234, "empty": 207, "pairs_equal": 18027},
    "checksums": {"lists": 25, "entries": 107112, "failed": 0},
    "conformance": {
        "release": 17664,
        "converted": 18027,
        "checks": ["schema", "round_trip", "completeness", "constraints", "shacl"],
    },
}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "--no-pager", "--no-optional-locks", "-C", str(repo), *args], capture_output=True, check=True
    )
    return done.stdout.decode().strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--investigation", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "migration" / "baseline.lock.json")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--requirements", type=Path, default=None, help="J.1.6 hash-locked requirements export")
    ap.add_argument("--wheel", type=Path, default=None, help="J.1.6 baseline wheel")
    args = ap.parse_args()
    if args.out.exists():
        print(f"refusing to overwrite {args.out.name}: the lock is frozen", file=sys.stderr)
        return 4
    info = json.loads((args.investigation / "baseline.json").read_text(encoding="utf-8"))
    fw, env = info["framework"], info["environment"]
    commit = git(args.baseline, "rev-parse", f"{TAG}^{{commit}}")
    assert commit == fw["git_commit"], "baseline.json and the tag disagree"
    lock = {
        "lock": LOCK_FORMAT,
        "frozen_on": FROZEN_ON,
        "framework": {
            "remote": fw["remote"],
            "commit": commit,
            "describe": fw["describe"],
            "tag": {"name": TAG, "object": git(args.baseline, "rev-parse", TAG), "pushed": False},
            "existing_tags": dict(fw["tags"]),
            "package": {"name": fw["package"]["name"], "version": fw["package"]["version"]},
            "tracked_files": dict(fw["file_sha256"]),
        },
        "environment": {
            "python": env["python"].split()[1],
            "uv": env["uv"].split()[1],
            "agentdojo": env["agentdojo_version"],
            "pip_freeze_sha256": sha256(args.investigation / env["pip_freeze_file"].split("/")[-1]),
            "packages": dict(env["key_packages"]),
            "requirements_lock_sha256": sha256(args.requirements) if args.requirements else None,
            "baseline_wheel_sha256": sha256(args.wheel) if args.wheel else None,
        },
        "results": RESULTS,
        "trees": {},
        "investigation_record": {
            "BASELINE.md": sha256(args.investigation / "BASELINE.md"),
            "baseline.json": sha256(args.investigation / "baseline.json"),
            "golden_index.json": sha256(args.investigation / "golden" / "golden_index.json"),
        },
    }
    for name, (root, predicate) in TREE_SPECS.items():
        listing = tree_listing(args.baseline / root, PREDICATES[predicate], workers=args.workers)
        lock["trees"][name] = {
            "root": root, "predicate": predicate, "files": listing.files, "listing_sha256": listing.listing_sha256,
        }
        print(f"{name}: {listing.files} files, {listing.listing_sha256}")
    text = json.dumps(lock, indent=2, ensure_ascii=False) + "\n"
    parse_lock(text.encode())  # validate before writing
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out.name}: sha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
