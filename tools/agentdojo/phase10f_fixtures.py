"""Build the phase-10f real fixtures, byte-identical, chosen by structure, never read back or printed (D-150, D-151).

    uv run python tools/agentdojo/phase10f_fixtures.py seagent --zip SEAGENT.zip
    uv run python tools/agentdojo/phase10f_fixtures.py whistlebench --tree TREE --licence-json PHASE10E_RAW_LICENSE_RESPONSE

``seagent`` reads the pinned deposit zip through :func:`agentprov.ingest.archives.open_archive` (the G.3.5 gate; nothing is
extracted), and for each criterion copies the **smallest** matching member (ties by label) to
``tests/fixtures/seagent/<label below raw_data/agentdojo/>``, with ``SOURCE.json`` (label, sha256, size, CRC-32, the zip's
DOI, file and sha256, licence class, criteria). Criteria: one ``attacked`` log per arm, ``benign``, ``prepass``,
``trailing_calls`` (the phase-10d criteria, ``phase10d_fixtures._criteria``), ``guard_warning`` (a user-role message right
after a tool result, the SEAgent guard warning) and ``no_tool_calls_key`` (an assistant message without the key, the
PVAgent shape). The deposit's ``LICENSE-CC-BY-4.0.txt`` is copied verbatim to ``tests/fixtures/LICENSES/``.

``whistlebench`` copies the smallest ``.eval`` log of the pinned ``final_runs/`` checkout to
``tests/fixtures/inspect/whistlebench/`` with ``SOURCE.json`` (path, sha256, git blob id, size, commit). The licence text is
decoded from phase 10e's saved GitHub API response for ``LICENSE`` at the same commit (no new download) and checked
against the sha256 phase 10e recorded.

A file with a secret-like string is never chosen (the phase-10d patterns; only the count is printed), nor a label with
whitespace. Only paths, sizes and criteria are printed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase10d_fixtures import SECRET_PATTERNS, _criteria  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
SEAGENT_PREFIX = "seagent-ae/artifact/results/raw_data/agentdojo/"
WHISTLEBENCH_COMMIT = "9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc"
WHISTLEBENCH_LICENCE_SHA256 = "a435c9f380834aa5"  # prefix recorded in phase 10e (pass 1)


def _secret(data: bytes) -> bool:
    return any(p.search(data) for p in SECRET_PATTERNS)


def _seagent_criteria(doc: dict[str, Any], label: str) -> set[str]:
    out = _criteria(doc, label, ())
    arm = label[len(SEAGENT_PREFIX):].split("/")[1]
    if "attacked" in out:
        out.discard("attacked")
        out.add(f"attacked:{arm}")
    messages = [m for m in doc.get("messages") or [] if isinstance(m, dict)]
    if any(m.get("role") == "user" and k > 0 and messages[k - 1].get("role") == "tool" for k, m in enumerate(messages)):
        out.add("guard_warning")
    if any(m.get("role") == "assistant" and "tool_calls" not in m for m in messages):
        out.add("no_tool_calls_key")
    return out


def seagent(zip_path: Path) -> list[dict[str, Any]]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.ingest.archives import iter_zip_members, open_archive

    profile = load_profile("seagent-agentdojo")
    pin = next(p for p in profile.data["source"]["pins"] if p.get("primary") is True)
    container = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if container != pin["sha256"]:
        raise SystemExit("the zip is not the pinned deposit file")
    best: dict[str, tuple[int, str, bytes, Any]] = {}
    secrets = 0
    with zip_path.open("rb") as fh, open_archive(fh, release=True) as archive:
        for member in iter_zip_members(archive, lambda label: label.startswith(SEAGENT_PREFIX) and label.endswith(".json")
                                       and label.count("/") == 12):
            if member.disposition != "selected" or member.label is None or " " in member.label:
                continue
            data = archive.read_member(member)
            if _secret(data):
                secrets += 1
                continue
            for criterion in _seagent_criteria(json.loads(data), member.label):
                key = (member.file_size, member.label)
                if criterion not in best or key < best[criterion][:2]:
                    best[criterion] = (member.file_size, member.label, data, member)
        licence = next(m for m in iter_zip_members(archive, lambda label: label == "seagent-ae/LICENSE-CC-BY-4.0.txt")
                       if m.disposition == "selected")
        licence_bytes = archive.read_member(licence)
    root = FIXTURES / "seagent"
    if root.exists():
        for old in sorted(root.rglob("*"), reverse=True):
            old.unlink() if old.is_file() else old.rmdir()
    rows: dict[str, dict[str, Any]] = {}
    for criterion, (size, label, data, _member) in sorted(best.items()):
        rel = label[len(SEAGENT_PREFIX):]
        row = rows.setdefault(rel, {"label": label, "path": rel, "size": size, "sha256": hashlib.sha256(data).hexdigest(),
                                    "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", "doi": pin["doi"], "file": pin["file"],
                                    "container_sha256": container, "licence_class": "permissive", "synthetic": False,
                                    "criteria": []})
        row["criteria"].append(criterion)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (root / "SOURCE.json").write_text(json.dumps(sorted(rows.values(), key=lambda r: r["path"]), indent=2, sort_keys=True)
                                      + "\n", encoding="utf-8")
    (FIXTURES / "LICENSES").mkdir(exist_ok=True)
    (FIXTURES / "LICENSES" / "SEAgent-CC-BY-4.0.txt").write_bytes(licence_bytes)
    print(json.dumps({"secret_like_members_skipped": secrets, "fixtures": [
        {"path": r["path"], "size": r["size"], "criteria": r["criteria"]} for r in sorted(rows.values(), key=lambda r: r["path"])]},
        indent=1))
    return list(rows.values())


def whistlebench(tree: Path, licence_json: Path) -> dict[str, Any]:
    logs = sorted((p.stat().st_size, p.relative_to(tree).as_posix()) for p in tree.rglob("*.eval"))
    clean = ((n, r, (tree / r).read_bytes()) for n, r in logs if " " not in r)
    chosen = next(((n, r, d) for n, r, d in clean if not _secret(d)), None)
    if chosen is None:
        raise SystemExit("no clean log")
    size, rel, data = chosen
    blob = subprocess.run(["git", "hash-object", "--stdin"], input=data, capture_output=True, check=True).stdout.decode().strip()
    root = FIXTURES / "inspect" / "whistlebench"
    if root.exists():
        for old in sorted(root.rglob("*"), reverse=True):
            old.unlink() if old.is_file() else old.rmdir()
    root.mkdir(parents=True)
    name = rel.rsplit("/", 1)[-1]
    (root / name).write_bytes(data)
    row = {"path": rel, "file": name, "size": size, "sha256": hashlib.sha256(data).hexdigest(), "git_blob": blob,
           "commit": WHISTLEBENCH_COMMIT, "repo": "https://github.com/legobridge/whistlebench", "licence_class": "permissive",
           "synthetic": False,
           "criteria": ["smallest_complete_log"]}
    (root / "SOURCE.json").write_text(json.dumps([row], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    response = json.loads(licence_json.read_bytes())
    text = base64.b64decode(response["content"])
    if not hashlib.sha256(text).hexdigest().startswith(WHISTLEBENCH_LICENCE_SHA256) or response.get("path") != "LICENSE":
        raise SystemExit("the saved licence response does not match phase 10e's record")
    (FIXTURES / "LICENSES" / "whistlebench-MIT.txt").write_bytes(text)
    print(json.dumps({"path": rel, "size": size, "git_blob": blob}, indent=1))
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seagent")
    s.add_argument("--zip", type=Path, required=True)
    w = sub.add_parser("whistlebench")
    w.add_argument("--tree", type=Path, required=True)
    w.add_argument("--licence-json", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.cmd == "seagent":
        seagent(args.zip)
    else:
        whistlebench(args.tree, args.licence_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
