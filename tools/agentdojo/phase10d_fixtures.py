"""Build the phase-10d real fixtures: a few byte-identical logs per source, chosen by shape, never read back or printed.

    uv run python tools/agentdojo/phase10d_fixtures.py --profile ID --cache DIR --name NAME --licence LICENSE-PATH \
        --licence-file Name-SPDX.txt [--denial TEXT ...] [--per-dir]

Reads the profile's pinned tree from a (scratch) fetch cache (``tools/agentdojo/phase10d_trial.py seed``), selects among the
logs the profile includes, and copies, for each criterion below, the **smallest** matching log (ties by path) to
``tests/fixtures/<NAME>/<original path>`` (the directory is rebuilt; a criterion whose smallest log is over ``--max-bytes``
is skipped and named on stderr), with ``SOURCE.json`` (path, sha256, git blob id, size, commit, licence class,
criterion). The criteria read only structure (keys, roles, ``None`` values) and, with ``--denial``, whether a tool error
starts with a given defence text; nothing is printed except paths, sizes and criteria. A log with a secret-like string
(the phase-10c census patterns) is never chosen; only their count is printed. Nor is a path with whitespace. The licence file at the pin is
copied verbatim to ``tests/fixtures/LICENSES/<licence-file>``.

Criteria: ``benign`` (no attack), ``prepass`` (an injection task run as a user task), ``attacked`` (one per pipeline
directory with ``--per-dir``, else one), ``null_final`` (last assistant content null), ``trailing_calls`` (the last
message is an assistant message with tool calls), ``null_ids`` (a call with a null id), ``incomplete`` (no outcome keys),
``denial`` (a tool error starting with one of the ``--denial`` texts), ``redaction`` (a tool output equal to the AgentDojo
PI-detector sentinel), ``extra_keys`` (a top-level key beyond the 14).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
#: Secret-like patterns (the phase-10c census set): a log matching any is never a fixture; only the count is reported.
SECRET_PATTERNS = tuple(re.compile(p) for p in (
    rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}", rb"sk-ant-[A-Za-z0-9_-]{20,}", rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|github_pat_[A-Za-z0-9_]{40,}", rb"\bAIza[0-9A-Za-z_-]{35}\b",
    rb"\bhf_[A-Za-z0-9]{30,}\b", rb"\bxox[abprs]-[A-Za-z0-9-]{10,}", rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    rb"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", rb"[Bb]earer [A-Za-z0-9._~+/-]{20,}",
))
SENTINEL = "<Data omitted because a prompt injection was detected>"
V1_KEYS = frozenset({"suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type", "injections", "messages",
                     "error", "utility", "security", "duration", "evaluation_timestamp", "benchmark_version",
                     "agentdojo_package_version"})


def _criteria(doc: dict[str, Any], label: str, denials: tuple[str, ...]) -> set[str]:
    out: set[str] = set()
    messages = doc.get("messages") or []
    task = str(doc.get("user_task_id", ""))
    if doc.get("attack_type") is None:
        out.add("prepass" if task.startswith("injection_task_") else "benign")
    else:
        out.add("attacked")
    assistants = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
    if assistants and assistants[-1].get("content") is None:
        out.add("null_final")
    if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "assistant" and messages[-1].get("tool_calls"):
        out.add("trailing_calls")
    if any(isinstance(c, dict) and c.get("id") is None for m in assistants for c in (m.get("tool_calls") or ())):
        out.add("null_ids")
    if "utility" not in doc or "security" not in doc:
        out.add("incomplete")
    if set(doc) - V1_KEYS - {"duration"} and "evaluation_timestamp" in doc:
        out.add("extra_keys")
    for m in messages:
        error = m.get("error") if isinstance(m, dict) and m.get("role") == "tool" else None
        if isinstance(error, str) and any(error.startswith(d) for d in denials):
            out.add("denial")
        content = m.get("content") if isinstance(m, dict) and m.get("role") == "tool" else None
        texts = [content] if isinstance(content, str) else [b.get("content") for b in content or () if isinstance(b, dict)] \
            if isinstance(content, list) else []
        if texts == [SENTINEL]:
            out.add("redaction")
    return out


def build(profile_id: str, cache: Path, name: str, licence: str, licence_file: str, denials: tuple[str, ...],
          per_dir: bool, max_bytes: int, licence_class: str | None = None,
          only: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phase10d_trial import _fetcher_recipe

    from agentprov.adapters.agentdojo.profile import family_table
    from agentprov.adapters.runner.importer import _match
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    profile, fetcher, recipe, _pin, _absent = _fetcher_recipe(profile_id, cache)
    layout = family_table(profile).layout
    include = tuple(profile.data["import"]["include"])
    exclude = tuple(e["glob"] for e in profile.data["import"].get("exclude", ()))
    entries, _ = fetcher.git_tree(recipe)
    logs = [e for e in entries if e.is_blob and any(_match(e.path, g) for g in include) and not any(_match(e.path, g) for g in exclude)]
    best: dict[str, tuple[int, str, Any, bytes]] = {}
    secret_like = 0
    for blob in fetcher.iter_git_blobs(recipe, logs):
        if any(c.isspace() for c in blob.entry.path):  # tools/check_unicode.py splits `git ls-files` on whitespace
            continue
        if any(p.search(blob.data) for p in SECRET_PATTERNS):
            secret_like += 1
            continue
        try:
            doc = strict_json_loads(blob.data, IngestLimits())
        except Exception:  # noqa: BLE001 - a non-JSON blob is never a fixture
            continue
        if not isinstance(doc, dict):
            continue
        facets = layout.match(blob.entry.path) if layout is not None else None
        for criterion in _criteria(doc, blob.entry.path, denials):
            key = criterion
            if criterion == "attacked" and per_dir and facets is not None:
                key = f"attacked:{facets.get('pipeline_dir') or facets.get('model_dir')}"
            candidate = (len(blob.data), blob.entry.path, blob.entry, blob.data)
            if key not in best or candidate[:2] < best[key][:2]:
                best[key] = candidate
    if secret_like:
        print(f"{secret_like} log(s) with secret-like strings never considered (count only)", file=sys.stderr)
    root = REPO / "tests" / "fixtures" / name
    if root.is_dir():  # rebuilt from scratch: a fixture no criterion selects any more is removed
        import shutil

        shutil.rmtree(root)
    if only:  # the smallest excerpt (copyleft sources): only the named criteria
        best = {k: v for k, v in best.items() if k.split(":", 1)[0] in only}
    skipped = sorted(k for k, v in best.items() if v[0] > max_bytes)
    if skipped:
        print(f"criteria skipped (smallest log over {max_bytes} bytes): {skipped}", file=sys.stderr)
    chosen: dict[str, dict[str, Any]] = {}
    for key, (size, path, entry, data) in sorted(best.items()):
        if size > max_bytes:
            continue
        row = chosen.setdefault(path, {
            "sample_file": path, "original_path": path, "sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha1": entry.oid,
            "size_bytes": size, "repo": recipe.repo, "commit_or_revision": recipe.commit,
            "licence_class": licence_class or "permissive",
            "synthetic": False, "criteria": [],
        })
        row["criteria"].append(key)
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    rows = sorted(chosen.values(), key=lambda r: r["sample_file"])
    (root / "SOURCE.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lic = next(e for e in entries if e.path == licence)
    data = next(fetcher.iter_git_blobs(recipe, [lic])).data
    (REPO / "tests" / "fixtures" / "LICENSES" / licence_file).write_bytes(data)
    return [{"path": r["sample_file"], "size": r["size_bytes"], "criteria": r["criteria"]} for r in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", required=True)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--licence", required=True, help="the licence file's path at the pin")
    parser.add_argument("--licence-file", required=True, help="the file name under tests/fixtures/LICENSES/")
    parser.add_argument("--denial", action="append", default=[])
    parser.add_argument("--per-dir", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=40_000, help="skip a criterion whose smallest log is larger")
    parser.add_argument("--criteria", default="", help="comma-separated criteria to keep (default: all)")
    parser.add_argument("--licence-class", default=None, help="SOURCE.json licence_class (default permissive; copyleft: restricted)")
    args = parser.parse_args(argv)
    rows = build(args.profile, args.cache, args.name, args.licence, args.licence_file, tuple(args.denial), args.per_dir,
                 args.max_bytes, args.licence_class, tuple(c for c in args.criteria.split(",") if c))
    print(json.dumps(rows, indent=1))
    print(f"{len(rows)} fixtures, {sum(r['size'] for r in rows)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
