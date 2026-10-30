"""Generate the tool inventory tables of the semantics profile ``dtap.tools@2`` (docs/architecture D.16.9).

    uv run python -I tools/dtap/gen_tool_tables.py --runs RUNS_TREE --tasks TASKS_TREE [--out DIR] [--jobs N]

Reads, as data and never executing anything, (1) the MCP server names each task configuration enables
(``Agent.mcp_servers[].name``; ``env_vars`` is never read into this tool's output), (2) the ``{name, description}``
entries of OpenClaw's ``traj_info.metadata.mcp_tools`` (names only are kept) and (3) the observed ``(server, tool_name)``
pairs of agent call steps. It writes ``servers.toml`` (per server, the sorted tool names) and ``domains.toml`` (per
domain, the servers its configurations enable) into ``--out`` (default: the profile directory). The role assignments are
not generated: they are the reviewed ``labels.toml`` and ``builtins.toml``. Prints counts only.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
from collections import defaultdict
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parents[2] / "src" / "agentprov" / "adapters" / "dtap" / "semantics" / "dtap.tools-2"


def _toml_string(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def _scan_run(path: str) -> tuple[list[tuple[str, str]], dict[str, list[str]]]:
    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    pairs: list[tuple[str, str]] = []
    listed: dict[str, list[str]] = {}
    try:
        with open(path, "rb") as handle:
            value = strict_json_loads(handle.read())
    except (IngestError, OSError):
        return pairs, listed
    if not isinstance(value, dict) or not isinstance(value.get("trajectory"), list):
        return pairs, listed
    for step in value["trajectory"]:
        meta = step.get("metadata") if isinstance(step, dict) else None
        if isinstance(step, dict) and step.get("role") == "agent" and isinstance(meta, dict):
            name, server = meta.get("tool_name"), meta.get("server")
            if isinstance(name, str) and isinstance(server, str) and name != "List MCP Tools":
                pairs.append((server, name))
    tools = ((value.get("traj_info") or {}).get("metadata") or {}).get("mcp_tools")
    if isinstance(tools, dict):
        for server, entries in tools.items():
            if isinstance(entries, list):
                listed[str(server)] = [str(e["name"]) for e in entries if isinstance(e, dict) and isinstance(e.get("name"), str)]
    return pairs, listed


def main(argv: list[str] | None = None) -> int:
    from agentprov.ingest import yamlsafe

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=PROFILE_DIR)
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args(argv)
    domains: dict[str, set[str]] = defaultdict(set)
    config_servers: set[str] = set()
    n_configs = 0
    for dirpath, _dirs, files in os.walk(args.tasks):
        if "config.yaml" not in files:
            continue
        rel = Path(dirpath).relative_to(args.tasks).as_posix()
        try:
            document = yamlsafe.safe_load((Path(dirpath) / "config.yaml").read_bytes())
        except Exception:  # noqa: BLE001 - an unparseable configuration contributes nothing (counted)
            continue
        n_configs += 1
        agent = document.get("Agent") if isinstance(document, dict) else None
        servers = agent.get("mcp_servers") if isinstance(agent, dict) else None
        for server in servers if isinstance(servers, list) else []:
            if isinstance(server, dict) and isinstance(server.get("name"), str):  # only the name; never env_vars
                domains[rel.split("/", 1)[0]].add(server["name"])
                config_servers.add(server["name"])
    paths = []
    for dirpath, _dirs, files in os.walk(args.runs):
        if "/.git" in dirpath:
            continue
        for name in files:
            if name.endswith(".json") and not name.startswith(("judge_result", "red_teaming_agent_")):
                paths.append(os.path.join(dirpath, name))
    paths.sort()
    inventory: dict[str, set[str]] = defaultdict(set)
    observed: dict[tuple[str, str], int] = defaultdict(int)
    with mp.get_context("fork").Pool(args.jobs) as pool:
        for pairs, listed in pool.imap(_scan_run, paths, chunksize=64):
            for pair in pairs:
                observed[pair] += 1
            for server, names in listed.items():
                inventory[server].update(names)
    known = set(inventory) | config_servers
    openclaw_unsplit = 0
    for (server, name), _count in observed.items():
        if server == "openclaw":
            prefix = max((s for s in known if name.startswith(s + "_")), key=len, default=None)
            if prefix is None:
                openclaw_unsplit += 1
                inventory["openclaw"].add(name)
            else:
                inventory[prefix].add(name[len(prefix) + 1:])
        elif server != "unknown":
            inventory[server].add(name)
    for server in config_servers:
        inventory.setdefault(server, set())
    builtins = sorted({name for (server, name) in observed if server == "unknown"})
    args.out.mkdir(parents=True, exist_ok=True)
    lines = ["# Generated by tools/dtap/gen_tool_tables.py from the pinned DTap datasets (do not edit by hand).",
             "# Per MCP server: the tool names seen in OpenClaw mcp_tools lists and in agent call steps (OpenClaw names split",
             "# at the longest server prefix, dtap.openclaw_prefix_split@1). An inventory only: roles are in labels.toml.", ""]
    for server in sorted(inventory):
        lines.append("[[server]]")
        lines.append(f"name = {_toml_string(server)}")
        lines.append("tools = [" + ", ".join(_toml_string(t) for t in sorted(inventory[server])) + "]")
        lines.append("")
    (args.out / "servers.toml").write_text("\n".join(lines), encoding="utf-8")
    lines = ["# Generated by tools/dtap/gen_tool_tables.py: per domain, the MCP servers its task configurations enable",
             "# (Agent.mcp_servers[].name at the tasks pin; env_vars are never read).", ""]
    for domain in sorted(domains):
        lines.append("[[domain]]")
        lines.append(f"name = {_toml_string(domain)}")
        lines.append("servers = [" + ", ".join(_toml_string(s) for s in sorted(domains[domain])) + "]")
        lines.append("")
    (args.out / "domains.toml").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"configs": n_configs, "runs_scanned": len(paths), "servers": len(inventory),
                      "tools": sum(len(v) for v in inventory.values()), "observed_pairs": len(observed),
                      "claudesdk_builtins_observed": len(builtins), "openclaw_unsplit_names": openclaw_unsplit}))
    print("builtins:", ", ".join(builtins[:80]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
