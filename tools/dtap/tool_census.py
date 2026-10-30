"""Census of the tools DTap agents call, and the coverage of the semantics profile ``dtap.tools@1`` (D.16.9).

    uv run python -I tools/dtap/tool_census.py --runs RUNS_TREE --tasks TASKS_TREE [--out FILE] [--jobs N]

Reads every trajectory of the pinned runs tree as data (strict JSON through ``agentprov.ingest``; nothing is executed)
and counts the agent call steps per ``(harness, domain, server, tool_name)``, plus the meta-steps (``List MCP Tools``,
``send_message_to_user``, OpenClaw ``error``). For each logged ``(server, tool_name)`` it records whether a description is
logged for it (OpenClaw ``traj_info.metadata.mcp_tools``, ``debug.tool_descriptions``; a yes/no, never the text). From the
task configurations it counts the ``injected_tool`` and ``injection_mcp_tool`` values (``env_vars`` are never read).

The shipped profile then resolves every pair exactly as SEM does (``DtapToolsProfile.tool_label``): the coverage is the
share of tool calls and of distinct tools whose role is not ``["unknown"]``, split by harness, with the role and output
integrity counts and the evidence basis of the labels. ``List MCP Tools`` meta-steps are harness activities (D.16.3) and
are not tool calls. Prints counts only; ``--out`` writes the full count tables as JSON.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import tomllib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

META_CALL = "List MCP Tools"


def _scan(item: tuple[str, str]) -> dict[str, Any]:
    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    path, rel = item
    out: dict[str, Any] = {"ok": 0, "calls": Counter(), "meta": Counter(), "described": set()}
    try:
        with open(path, "rb") as handle:
            value = strict_json_loads(handle.read())
    except (IngestError, OSError):
        return out
    if not isinstance(value, dict) or not isinstance(value.get("trajectory"), list):
        return out
    out["ok"] = 1
    parts = rel.split("/")
    harness, domain = parts[0], parts[2] if len(parts) > 2 else "?"
    for step in value["trajectory"]:
        if not isinstance(step, dict) or step.get("role") != "agent":
            continue
        meta = step.get("metadata") if isinstance(step.get("metadata"), dict) else {}
        if "tool_name" not in meta and step.get("action") in ("send_message_to_user", "error"):
            out["meta"][(harness, str(step["action"]))] += 1
            continue
        name, server = str(meta.get("tool_name")), str(meta.get("server"))
        if name == META_CALL:
            out["meta"][(harness, META_CALL)] += 1
            continue
        out["calls"][(harness, domain, server, name)] += 1
    tools = ((value.get("traj_info") or {}).get("metadata") or {}).get("mcp_tools")
    if isinstance(tools, dict):
        for server, entries in tools.items():
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry.get("description"):
                    out["described"].add((str(server), entry["name"]))
    debug = value.get("debug")
    if isinstance(debug, dict) and isinstance(debug.get("tool_descriptions"), dict):
        for key, text in debug["tool_descriptions"].items():
            if isinstance(key, str) and ":" in key and text:
                out["described"].add(tuple(key.split(":", 1)))
    return out


def _configs(tasks: Path) -> dict[str, Counter[str]]:
    from agentprov.ingest import yamlsafe

    found: dict[str, Counter[str]] = {"injected_tool": Counter(), "injection_mcp_tool": Counter(), "mcp_servers": Counter()}
    for dirpath, dirs, files in os.walk(tasks):
        dirs[:] = [d for d in dirs if d != ".git"]
        if "config.yaml" not in files:
            continue
        try:
            doc = yamlsafe.safe_load((Path(dirpath) / "config.yaml").read_bytes())
        except Exception:  # noqa: BLE001 - an unparseable configuration contributes nothing
            continue
        if not isinstance(doc, dict):
            continue
        agent = doc.get("Agent") if isinstance(doc.get("Agent"), dict) else {}
        for server in agent.get("mcp_servers") or []:
            if isinstance(server, dict) and isinstance(server.get("name"), str):  # only the name; never env_vars
                found["mcp_servers"][server["name"]] += 1
        attack = doc.get("Attack") if isinstance(doc.get("Attack"), dict) else {}
        for turn in attack.get("attack_turns") or []:
            for step in (turn.get("attack_steps") or []) if isinstance(turn, dict) else []:
                if isinstance(step, dict):
                    for key in ("injected_tool", "injection_mcp_tool"):
                        if isinstance(step.get(key), str):
                            found[key][step[key]] += 1
    return found


def coverage(calls: Counter[tuple[str, str, str, str]]) -> dict[str, Any]:
    """Resolve every observed pair through the shipped ``dtap.tools@2`` and count what is labelled."""
    from importlib import resources

    from agentprov.adapters.semantics_profiles import load_semantics_profile

    profile: Any = load_semantics_profile("dtap.tools", 1)
    data = resources.files("agentprov").joinpath("adapters", "dtap", "semantics", "dtap.tools-2")
    evidence: dict[tuple[str, str], str] = {}
    for entry in tomllib.loads(data.joinpath("labels.toml").read_text(encoding="utf-8")).get("label", []):
        evidence[(entry["server"], entry["tool"])] = entry["evidence"][0]
    for entry in tomllib.loads(data.joinpath("builtins.toml").read_text(encoding="utf-8")).get("builtin", []):
        evidence[("unknown", entry["name"])] = entry["evidence"][0]
    pairs: Counter[tuple[str, str]] = Counter()
    labelled_pairs: set[tuple[str, str]] = set()
    by_harness: dict[str, Counter[str]] = defaultdict(Counter)
    out: dict[str, Any] = {"tool_calls": 0, "labelled_calls": 0, "roles_by_tools": Counter(), "roles_by_calls": Counter(),
                           "integrity_by_calls": Counter(), "evidence_by_tools": Counter(), "rules_by_calls": Counter()}
    sources: dict[tuple[str, str], tuple[tuple[str, str], tuple[str, ...]]] = {}  # pair -> (label key, roles)
    for (harness, domain, server, name), n in calls.items():
        roles, integrity, rules = profile.tool_label(name, server, domain)
        pairs[(server, name)] += n
        by_harness[harness]["calls"] += n
        out["tool_calls"] += n
        out["integrity_by_calls"][integrity] += n
        out["rules_by_calls"]["+".join(rules)] += n
        for role in roles:
            out["roles_by_calls"][role] += n
        if tuple(roles) == ("unknown",):
            continue
        out["labelled_calls"] += n
        by_harness[harness]["labelled"] += n
        labelled_pairs.add((server, name))
        key = (server, name)
        if server == "openclaw":
            split = max((s for s in profile.tables.servers if name.startswith(s + "_")), key=len, default=None)
            key = (split, name[len(split) + 1:]) if split else key
        elif server == "unknown" and ("unknown", name) not in evidence:
            key = next((s, name) for s in sorted(profile.tables.domains.get(domain, ())) if name in profile.tables.servers.get(s, ()))
        sources.setdefault((server, name), (key, tuple(roles)))
    for pair in sorted(pairs):
        if pair in labelled_pairs:  # a pair counts as labelled when any of its calls is (domain-dependent for server unknown)
            out["evidence_by_tools"][evidence.get(sources[pair][0], "?")] += 1
        for role in sources[pair][1] if pair in labelled_pairs else ("unknown",):
            out["roles_by_tools"][role] += 1
    out["tools"] = len(pairs)
    out["labelled_tools"] = len(labelled_pairs)
    unknown = [(n, s, t) for (s, t), n in pairs.items() if (s, t) not in labelled_pairs]
    out["by_harness"] = {h: dict(c) for h, c in sorted(by_harness.items())}
    out["unknown_top"] = [f"{n} {server}:{name}" for n, server, name in sorted(unknown, reverse=True)[:40]]
    out["unknown_calls"] = sum(n for n, *_ in unknown)
    for key in ("roles_by_tools", "roles_by_calls", "integrity_by_calls", "evidence_by_tools", "rules_by_calls"):
        out[key] = dict(sorted(out[key].items()))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args(argv)
    items = []
    for dirpath, dirs, files in os.walk(args.runs):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            if name.endswith(".json") and not name.startswith(("judge_result", "red_teaming_agent_")):
                full = os.path.join(dirpath, name)
                items.append((full, os.path.relpath(full, args.runs)))
    calls: Counter[tuple[str, str, str, str]] = Counter()
    meta: Counter[tuple[str, str]] = Counter()
    described: set[tuple[str, str]] = set()
    parsed = 0
    with mp.get_context("fork").Pool(args.jobs) as pool:
        for result in pool.imap_unordered(_scan, items, chunksize=32):
            parsed += result["ok"]
            calls.update(result["calls"])
            meta.update(result["meta"])
            described |= result["described"]
    report = {"files": len(items), "parsed": parsed, "meta_steps": {f"{h}|{a}": n for (h, a), n in sorted(meta.items())},
              "coverage": coverage(calls)}
    print(json.dumps(report, indent=1, sort_keys=True))
    if args.out is not None:
        configs = _configs(args.tasks)
        tools: dict[str, Any] = defaultdict(lambda: {"calls": 0, "by_harness": Counter(), "by_domain": Counter()})
        for (harness, domain, server, name), n in calls.items():
            row = tools[f"{server}\t{name}"]
            row["calls"] += n
            row["by_harness"][harness] += n
            row["by_domain"][domain] += n
        for key, row in tools.items():
            row["description_logged"] = tuple(key.split("\t", 1)) in described
        payload = {"report": report, "tools": dict(sorted(tools.items())),
                   "configs": {k: dict(sorted(v.items())) for k, v in configs.items()}}
        args.out.write_text(json.dumps(payload, indent=1, sort_keys=True, default=dict) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
