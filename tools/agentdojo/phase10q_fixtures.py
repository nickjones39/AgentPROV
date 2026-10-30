"""Build the phase-10q real fixtures, byte-identical, never read back or printed (D-478).

    uv run python tools/agentdojo/phase10q_fixtures.py [--cache DIR]

Copies two results containers of memo-ozdincer/agentdojo at the profile's pin from the bare, extraction-free fetch cache
(``git cat-file``; each blob checked against its id) to ``tests/fixtures/memo-ozdincer/<path>``, with the pin's
``LICENSE`` (MIT, the upstream text) and ``SOURCE.json`` (path, sha256, git blob id, size, CRC-32, commit, licence class,
what each file covers):

- ``results/api_evals/together_test.json``: 9 ``rc.k7`` rows on a provider model id (Together), attack recorded;
- ``results/comprehensive_eval/smoke_mse4.json``: 8 ``rc.k12`` smoke rows (row-level ``suite``) on the LoRA adapter
  ``mse4``, attack absent.

Neither holds a workstation account path (D-476 keeps such files out of Git, D-185) nor a secret-like string (the
phase-10d patterns); the tool refuses a file that does. Only paths, sizes and counts are printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase10d_fixtures import SECRET_PATTERNS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "tests" / "fixtures" / "memo-ozdincer"
PROFILE = "memo-ozdincer-agentdojo"
FILES = {
    "results/api_evals/together_test.json": "rc.k7 rows, provider model id, recorded attack (training_format)",
    "results/comprehensive_eval/smoke_mse4.json": "rc.k12 smoke rows with a row-level suite, LoRA adapter mse4, no attack key",
}
_ACCOUNT_PATH = re.compile(rb"/(?:home|Users|scratch|mfs1/u)/[^/\s\"']+/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", default=None)
    args = parser.parse_args(argv)
    from agentprov.adapters.profiles import load_profile
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(PROFILE)
    source = profile.data["source"]
    pin = next(dict(p) for p in source["pins"] if p.get("primary") is True)
    recipe = Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo"))
    fetcher = Fetcher(resolve_cache_dir(args.cache))
    entries, _ = fetcher.git_tree(recipe)
    wanted = [e for e in entries if e.is_blob and e.path in (*FILES, "LICENSE")]
    rows = []
    for blob in fetcher.iter_git_blobs(recipe, wanted):
        data, path = blob.data, blob.entry.path
        if path != "LICENSE":
            secrets = sum(len(p.findall(data)) for p in SECRET_PATTERNS)
            # /home/user/ is the AgentDojo world's fictional path; a workstation account path is any other segment
            accounts = [m for m in _ACCOUNT_PATH.findall(data) if m != b"/home/user/"]
            if secrets or accounts:
                print(f"refused {path}: {secrets} secret-like, {len(accounts)} account-path matches")
                return 1
        target = OUT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "git_blob": blob.entry.oid,
                     "size": len(data), "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", "commit": recipe.commit,
                     "repo": recipe.repo, "licence": "MIT (LICENSE at the pin, upstream text)",
                     "covers": FILES.get(path, "the pin's licence text"),
                     "licence_class": "permissive", "synthetic": False})  # K.4.2; D-946
        print(f"wrote {path} ({len(data)} B)")
    rows.sort(key=lambda r: r["path"])
    (OUT / "SOURCE.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} files, {sum(r['size'] for r in rows)} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
