"""D-654: every option of every ``agentprov`` command is reachable in the GUI.

A subprocess (this interpreter, ``-I``; the GUI never imports ``agentprov.cli``) walks the CLI's argparse tree and
prints, per command path, each option's long name, its ``choices`` and the positionals. Each option must be a form
field (:data:`FORMS`), a job-wide global (:data:`GLOBAL_FIELDS`), set by the GUI itself (:data:`MANAGED_OPTIONS`) or
excluded with a reason (:data:`EXCLUDED_OPTIONS`). An alias (:data:`ALIASES`) is reached under its other name. A form
field's choices must be the CLI's (plus "" for "not given"), and a form must have as many positional fields as the
command has positionals. A GUI option the CLI does not have fails too.
"""

from __future__ import annotations

import json
import subprocess
import sys

from agentprov_gui.jobs.commands import (
    ALIASES,
    EXCLUDED_OPTIONS,
    FORMS,
    GLOBAL_FIELDS,
    MANAGED_OPTIONS,
    PENDING_MANAGED,
    option_table,
)

_DUMP = r"""
import argparse, json
from agentprov.cli.main import build_parser
out = {}
def walk(p, words):
    opts, positionals, subs = {}, [], None
    for a in p._actions:
        if isinstance(a, argparse._SubParsersAction):
            subs = a
            continue
        if isinstance(a, argparse._HelpAction):
            continue
        longs = [s for s in a.option_strings if s.startswith("--")]
        if a.option_strings:
            opts[longs[0] if longs else a.option_strings[0]] = sorted(map(str, a.choices)) if a.choices else None
        else:
            positionals.append(a.dest)
    out[" ".join(words)] = {"options": opts, "positionals": positionals, "leaf": subs is None}
    if subs:
        for name, sp in subs.choices.items():
            walk(sp, words + [name])
walk(build_parser(), [])
print(json.dumps(out))
"""


def cli_tree() -> dict[str, dict[str, object]]:
    done = subprocess.run([sys.executable, "-I", "-c", _DUMP], capture_output=True, text=True, check=True, timeout=120)
    return json.loads(done.stdout)


def _excluded(command: str) -> dict[str, str]:
    return {**EXCLUDED_OPTIONS.get("*", {}), **EXCLUDED_OPTIONS.get(command, {})}


def test_every_cli_option_is_reachable_or_excluded_with_a_reason() -> None:
    tree, table = cli_tree(), option_table()
    root = set(tree[""]["options"])  # type: ignore[arg-type]
    missing: list[str] = []
    for command, node in tree.items():
        if not command or not node["leaf"] or command in ALIASES:
            continue
        reached = table.get(command)
        if reached is None:
            missing.append(f"{command}: no GUI form")
            continue
        excluded = _excluded(command)
        for option in node["options"]:  # type: ignore[union-attr]
            if option not in reached and option not in excluded:
                missing.append(f"{command} {option}{' (global)' if option in root else ''}")
    assert not missing, "CLI options the GUI cannot reach (add a field, or exclude with a reason):\n" + "\n".join(missing)


def test_exclusions_and_managed_options_name_real_options_and_give_reasons() -> None:
    tree = cli_tree()
    root = set(tree[""]["options"])  # type: ignore[arg-type]
    for table in (EXCLUDED_OPTIONS, MANAGED_OPTIONS):
        for command, rows in table.items():
            known = root if command == "*" else set(tree[command]["options"])  # type: ignore[arg-type]
            for option, reason in rows.items():
                assert option in known, (command, option)
                assert len(reason) > 10, (command, option)
    for command, rows in PENDING_MANAGED.items():  # may wait for its CLI option; named with a reason
        for option, reason in rows.items():
            assert option.startswith("--") and len(reason) > 10, (command, option)


def test_aliases_are_the_same_command() -> None:
    tree = cli_tree()
    for alias, target in ALIASES.items():
        assert tree[alias]["options"] == tree[target]["options"], alias


def test_gui_options_exist_with_the_cli_choices_and_positionals() -> None:
    tree = cli_tree()
    bad: list[str] = []
    for form in FORMS.values():
        if form.tool is not None:
            continue
        command = " ".join(form.words)
        node = tree[command]
        options: dict[str, list[str] | None] = node["options"]  # type: ignore[assignment]
        for f in (*form.fields, *GLOBAL_FIELDS):
            if f.option is None:
                continue
            if f.option not in options:
                if not f.pending:  # a pending field (e.g. D-656's --max-tokens) may wait for its CLI option
                    bad.append(f"{form.name}: {f.option} is not a CLI option")
            elif f.kind == "choice":
                cli = options[f.option]
                # a pending choice (D-656's anthropic) may be absent until its CLI lands, then must match
                gui = sorted(c for c in f.choices if c and (c not in f.pending_choices or c in (cli or ())))
                if cli is not None and gui != sorted(cli):
                    bad.append(f"{form.name}: {f.option} choices {gui} != {cli}")
        positional = [f for f in form.fields if f.option is None]
        if len(positional) != len(node["positionals"]):  # type: ignore[arg-type]
            bad.append(f"{form.name}: {len(positional)} positional fields, the CLI has {node['positionals']}")
    assert not bad, "\n".join(bad)
