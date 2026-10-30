"""The ``v0.k11`` system-prompt code states of AgentDojo, from the full history (deferrals part B; D.6.12 item 6, D.6.11 item 9).

    uv run python tools/agentdojo/system_prompt_states.py --report FILE [--store DIR] [--index FILE]

Offline (``GIT_NO_LAZY_FETCH=1``, isolated git configuration). Reads the full-history store and the full-history index of
``tools/agentdojo/full_history_index.py``:

1. **Code states.** For every commit of the head pin's history, the blob of the harness's default system message
   (``<package>/data/system_messages.yaml``; the package was ``function_calling_pi``, then ``agentgym``, then ``agentdojo``)
   and the SHA-256 of its ``default`` value read with the strict safe YAML loader. A code state is one digest; the report
   lists, per state, its first commit (by committer date), the number of commits that carry it, and the YAML blobs.
2. **Logs.** Every run log held by a pin is sniffed by the product reader; for each ``v0.k11`` log the SHA-256 of
   message 0's text, computed by the mapper's rule (a string, or the texts of text blocks joined by a newline;
   ``mapper._prompt_variant``), is compared with the state **in force at the log's introducing commit** (the newest code
   before the log was committed, an upper bound of the producing code; D.6.16) and with every state of the history.

Output: counts and digests only, never log or prompt text. The proposed ``system_prompt_variants`` entries for the
``v0.k11`` code states are written into the report for the mapper owner (regen-batch session); this tool changes no
profile.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from agentprov.adapters.agentdojo.dialect import classify
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.yamlsafe import safe_load

HEAD = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
STORE = HOME / "upstream" / "github.com" / "ethz-spylab" / "agentdojo.git"
INDEX = STORE.parent / "agentdojo.index" / f"full-{HEAD}.jsonl"
YAMLS = tuple(f"src/{pkg}/data/system_messages.yaml" for pkg in ("function_calling_pi", "agentgym", "agentdojo"))
_ENV = {"PATH": os.environ.get("PATH", ""), "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
LIMITS = IngestLimits()


def git(store: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", "--git-dir", str(store), *args], input=data, capture_output=True, check=True, env=_ENV,
                          timeout=1800).stdout


def read_blobs(store: Path, oids: list[str]) -> dict[str, bytes]:
    """``git cat-file --batch`` for ``oids``; each blob is checked against its git blob SHA-1."""
    out: dict[str, bytes] = {}
    stream = git(store, "cat-file", "--batch", data="".join(f"{o}\n" for o in oids).encode())
    pos = 0
    for oid in oids:
        end = stream.index(b"\n", pos)
        head = stream[pos:end].split()
        size = int(head[2])
        body = stream[end + 1 : end + 1 + size]
        pos = end + 2 + size
        if head[0].decode() != oid or hashlib.sha1(b"blob %d\0" % size + body, usedforsecurity=False).hexdigest() != oid:
            raise SystemExit(f"blob {oid} does not hash to its id")
        out[oid] = body
    return out


def prompt_digest(content: object) -> str | None:
    """The mapper's rule (``mapper._prompt_variant``)."""
    text: str | None = content if isinstance(content, str) else None
    if isinstance(content, list) and content and all(
            isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("content"), str) for b in content):
        text = "\n".join(str(b["content"]) for b in content)
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


def code_states(store: Path) -> tuple[dict[str, str | None], dict[str, dict[str, Any]]]:
    """``commit -> default-prompt digest`` (None: no YAML in the tree) and ``digest -> state facts``."""
    commits = [line.split() for line in git(store, "log", "--format=%H %ct", HEAD).decode().splitlines()]
    yaml_blob: dict[str, str | None] = {}
    for commit, _epoch in commits:
        listing = git(store, "ls-tree", commit, "--", *YAMLS).decode().split("\n")
        blobs = [line.split()[2] for line in listing if line.strip()]
        yaml_blob[commit] = blobs[0] if len(blobs) == 1 else None
    blobs = sorted({b for b in yaml_blob.values() if b})
    text = read_blobs(store, blobs)
    digest_of_blob: dict[str, str | None] = {}
    for blob in blobs:
        try:
            value = safe_load(text[blob], LIMITS)
        except AgentProvError:
            value = None
        default = value.get("default") if isinstance(value, dict) else None
        digest_of_blob[blob] = hashlib.sha256(default.encode("utf-8")).hexdigest() if isinstance(default, str) else None
    state_of = {c: (digest_of_blob.get(b) if b else None) for c, b in yaml_blob.items()}
    epoch = {c: int(e) for c, e in commits}
    states: dict[str, dict[str, Any]] = {}
    for commit, digest in state_of.items():
        if digest is None:
            continue
        entry = states.setdefault(digest, {"commits": 0, "first_commit": commit, "first_epoch": epoch[commit],
                                           "yaml_blobs": set()})
        entry["commits"] += 1
        entry["yaml_blobs"].add(yaml_blob[commit])
        if (epoch[commit], commit) < (entry["first_epoch"], entry["first_commit"]):
            entry["first_commit"], entry["first_epoch"] = commit, epoch[commit]
    return state_of, states


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    state_of, states = code_states(args.store)
    lines = args.index.read_bytes().splitlines()
    header = json.loads(lines[0])
    rows = [json.loads(line) for line in lines[1:]]
    pinned = [r for r in rows if r["pins"]]
    blobs = read_blobs(args.store, sorted({r["b"] for r in pinned}))
    tallies: Counter[tuple[str, ...]] = Counter()
    by_state: Counter[str] = Counter()
    variants: Counter[str] = Counter()
    other_by_dir: Counter[str] = Counter()  # run directory (a model-pipeline label) of the logs with another prompt
    for row in pinned:
        try:
            obj = strict_json_loads(blobs[row["b"]], LIMITS)
        except AgentProvError:
            variants["unparseable"] += 1
            continue
        sniff = classify(obj)
        variant = str(sniff.variant) if sniff.match else "not_tracelogger"
        variants[variant] += 1
        if variant != "v0.k11":
            continue
        messages = obj.get("messages") if isinstance(obj, dict) else None
        first = messages[0] if isinstance(messages, list) and messages and isinstance(messages[0], dict) else {}
        digest = prompt_digest(first.get("content")) if first.get("role") == "system" else None
        at_intro = state_of.get(row["c"])
        under = "2024-06" if "2024-06" in row["pins"] else "head-only"
        if digest is None:
            kind = "no_system_text"
        elif digest == at_intro:
            kind = "equals_state_at_introducing_commit"
        elif digest in states:
            kind = "equals_an_earlier_or_other_state"
        else:
            kind = "equals_no_state"
            other_by_dir[row["p"].split("/")[1] if row["p"].count("/") > 1 else "?"] += 1
        tallies[(under, kind)] += 1
        if digest is not None:
            by_state[digest if digest in states else "unknown"] += 1
    report: dict[str, Any] = {
        "format": "agentprov-system-prompt-states/1", "head": HEAD, "index_sha256": header.get("rows_sha256"),
        "yaml_paths": list(YAMLS),
        "code_states": [{"sha256": d, "commits": s["commits"], "first_commit": s["first_commit"],
                         "yaml_blobs": sorted(s["yaml_blobs"]), "v0k11_logs": by_state.get(d, 0)}
                        for d, s in sorted(states.items(), key=lambda kv: (kv[1]["first_epoch"], kv[0]))],
        "commits_without_yaml": sum(1 for v in state_of.values() if v is None),
        "pinned_logs_by_variant": dict(sorted(variants.items())),
        "v0k11_logs": {f"{u}/{k}": n for (u, k), n in sorted(tallies.items())},
        "v0k11_logs_with_an_unknown_prompt": by_state.get("unknown", 0),
        "v0k11_unknown_prompt_by_run_directory": dict(sorted(other_by_dir.items())),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"states": len(states), "v0k11": report["v0k11_logs"], "variants": report["pinned_logs_by_variant"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
