"""``agentprov settings``: the user settings the CLI and the GUI share (D-703; reverse CLI parity D-700).

    agentprov settings list [--prefix P] [--schema] [--format text|json]
    agentprov settings get KEY [--format text|json]
    agentprov settings set KEY VALUE
    agentprov settings unset KEY

The store is ``$AGENTPROV_HOME/settings.json`` (:mod:`agentprov.settings`: a closed schema, strict reads, atomic
writes under a lock). Keys are never secrets (``agentprov keys``) and never corpus text. ``get`` of an unset key prints
nothing and exits 0 (``--format json``: ``null``); an unknown key or a refused value exits 2.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("settings", parents=[shared], help="list, get, set or unset the shared user settings",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="settings", handler=run_settings, feedback=False)
    actions = p.add_subparsers(dest="settings_action", metavar="ACTION", required=True)
    ls = actions.add_parser("list", parents=[shared], help="the stored settings (or the schema)", allow_abbrev=False)
    ls.add_argument("--prefix", default="", metavar="P", help="only keys starting with P")
    ls.add_argument("--schema", action="store_true", help="list the key patterns, types and bounds instead")
    ls.add_argument("--format", choices=["text", "json"], default="text")
    g = actions.add_parser("get", parents=[shared], help="one setting (nothing when unset)", allow_abbrev=False)
    g.add_argument("key", metavar="KEY")
    g.add_argument("--format", choices=["text", "json"], default="text")
    s = actions.add_parser("set", parents=[shared], help="store one setting (checked against the schema)",
                           allow_abbrev=False)
    s.add_argument("key", metavar="KEY")
    s.add_argument("value", metavar="VALUE", help="lists: comma or space separated; booleans: true or false")
    u = actions.add_parser("unset", parents=[shared], help="remove one setting", allow_abbrev=False)
    u.add_argument("key", metavar="KEY")


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def run_settings(ctx: Context) -> CommandResult:
    from agentprov import settings as S

    args = ctx.args
    result = CommandResult()
    home = None  # $AGENTPROV_HOME, as every command
    try:
        if args.settings_action == "list":
            if args.schema:
                rows = [{"pattern": k.pattern, "type": k.kind, "help": k.help, "min": k.lo, "max": k.hi,
                         "choices": list(k.choices) or None} for k in S.SCHEMA]
                if args.format == "json":
                    result.payload = _payload({"format": "agentprov-settings-schema/0.1", "keys": rows})
                else:
                    result.payload = "".join(f"{r['pattern']}  ({r['type']})  {r['help']}\n" for r in rows).encode()
                return result
            values = S.items(args.prefix, home=home)
            for problem in S.problems(home=home):
                result.notices.append(f"ignored stored value: {safe_text(problem, 200)}")
            if args.format == "json":
                result.payload = _payload({"format": S.SETTINGS_FORMAT, "values": values})
            else:
                result.payload = "".join(f"{key} = {safe_text(json.dumps(value), 300)}\n"
                                         for key, value in values.items()).encode("utf-8")
            result.counters = {"settings": len(values)}
        elif args.settings_action == "get":
            value = S.get(args.key, home=home)
            if args.format == "json":
                result.payload = _payload(value)
            elif value is not None:
                text = value if isinstance(value, str) else json.dumps(value)
                result.payload = (safe_text(text, 600) + "\n").encode("utf-8")
        elif args.settings_action == "set":
            stored = S.set(args.key, args.value, home=home)
            result.info(f"settings: {args.key} = {safe_text(json.dumps(stored), 300)}")
        elif args.settings_action == "unset":
            removed = S.unset(args.key, home=home)
            result.info(f"settings: {args.key} " + ("removed" if removed else "was not set"))
    except S.SettingsError as exc:
        raise CliUsageError(f"agentprov settings: {exc}") from None
    return result
