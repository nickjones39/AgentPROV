"""``agentprov purge``: remove a leaked object from a working store (MN N.2.15; G.9.6; R-51; D-46).

::

    agentprov purge sha256:HEX --reason {secret,personal_data} (--corpus DIR | --cache) [--cache-dir DIR] [--yes] [--dry-run]

It deletes one object from a *working* corpus's raw store (``--corpus``) or one downloaded file from the fetch cache
(``--cache``), writes a tombstone (digest, reason, date; never the value or a fragment of it) to ``raw/tombstones.jsonl`` or
``<cache>/tombstones.jsonl``, and gives the executions that cite the object the register code ``release.withheld`` (G.9.5).
The logic is :mod:`agentprov.corpus.purge`; this module is argument handling, the confirmation and the report.

* A sealed corpus is never modified: exit 4 (build a new version with the object withheld, G.9.5).
* Purging is irreversible. It asks for interactive confirmation on a terminal; a non-interactive invocation is refused
  (exit 4) unless ``--yes`` is given. ``--dry-run`` prints what would be removed and writes nothing, takes no lock and asks
  nothing.
* Exit 0; 2 for an unknown object or a malformed digest or a missing corpus; 4 for a sealed corpus or an unconfirmed purge.

Nothing printed here is taken from the purged bytes: only digests, sizes, execution ids and store-relative labels.
``--cache-dir`` is an addition to the N.2.15 synopsis (same meaning as for ``fetch``): the cache is otherwise
``$AGENTPROV_UPSTREAM_CACHE``, else ``$AGENTPROV_HOME/cache``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, redact_personal, safe_text
from agentprov.errors import AgentProvError

_LISTED = 20  # execution ids printed on stderr; the summary counters carry the totals


class PurgeNotConfirmedError(AgentProvError):
    """A purge was not confirmed: non-interactive without ``--yes``, or the answer was not the confirmation word. Exit 4."""

    code = "cli.refused.unconfirmed"
    exit_code = 4


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "purge",
        parents=[shared],
        help="remove a leaked object from a working corpus or the fetch cache, leaving a tombstone (irreversible)",
        description=(
            "Delete one object (by sha256) from a working corpus's raw store, or one downloaded file from the fetch cache, "
            "and write a tombstone beside the store's records (N.2.15; G.9.6). Executions that cite the object get the "
            "register code release.withheld. A sealed corpus is never modified (exit 4). Purging is irreversible: it asks for "
            "confirmation on a terminal, and refuses (exit 4) without --yes when not interactive."
        ),
        allow_abbrev=False,
    )
    p.set_defaults(command="purge", handler=run_purge, feedback=False)
    p.add_argument("object", metavar="sha256:HEX", help="the object to remove")
    p.add_argument("--reason", required=True, choices=["secret", "personal_data"], help="why the object is removed")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--corpus", metavar="DIR", help="the working corpus (DIR.partial) whose raw store holds the object")
    where.add_argument("--cache", action="store_true", help="remove a downloaded file from the fetch cache instead")
    p.add_argument("--cache-dir", metavar="DIR", help="with --cache: the fetch cache (default $AGENTPROV_UPSTREAM_CACHE, else $AGENTPROV_HOME/cache)")
    p.add_argument("--yes", action="store_true", help="confirm the irreversible removal without asking (needed when not interactive)")
    p.add_argument("--dry-run", action="store_true", help="print what would be removed; write nothing, take no lock")


# ------------------------------------------------------------------------------------------------ confirmation
def _interactive() -> bool:
    """Whether a person can answer: stdin and stderr are terminals. A seam for the tests."""
    try:
        return sys.stdin.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _ask(prompt: str) -> str:
    """Prompt on stderr, read one line from stdin. A seam for the tests."""
    sys.stderr.write(prompt)
    sys.stderr.flush()
    return sys.stdin.readline().strip()


def _confirm(args: argparse.Namespace, digest: str) -> None:
    if args.yes:
        return
    if not _interactive():
        raise PurgeNotConfirmedError(
            "purging is irreversible and needs confirmation: run it in a terminal and answer the prompt, or pass --yes (N.2.15)"
        )
    word = digest[:8]
    answer = _ask(f"agentprov purge: remove sha256:{digest[:12]}... permanently? Type the first 8 digits ({word}) to confirm: ")
    if answer != word:
        raise PurgeNotConfirmedError("not confirmed; nothing was removed")


# ------------------------------------------------------------------------------------------------ command
def _describe(plan: Any, result: CommandResult, dry: bool) -> None:
    where = "fetch cache" if plan.kind == "cache" else "working corpus"
    root = safe_text(redact_personal(str(plan.root)), 300)
    verb = "would remove" if dry else "removing"
    if plan.object_label is not None:
        result.output(f"{verb} sha256:{plan.digest} ({plan.size} bytes) from the {where} {root}: {safe_text(plan.object_label, 200)}")
        for label in plan.other_labels:  # further cached copies of the same bytes (another pin), removed too
            result.output(f"  and the same bytes at {safe_text(label, 200)}")
    for note in plan.notices:
        result.output(f"  {note}")
    action = "would write" if dry else "writing"
    status = "already present" if plan.already_tombstoned else f"reason {plan.reason}, date {plan.date}"
    result.output(f"  {action} the tombstone in {plan.tombstone_label} ({status})")
    if plan.kind == "corpus":
        n = len(plan.affected)
        result.output(
            f"  {n} execution(s) cite the object; {plan.new_register_entries} new register entr"
            f"{'y' if plan.new_register_entries == 1 else 'ies'} release.withheld"
        )
        for ex in plan.affected[:_LISTED]:
            result.output(f"    {safe_text(ex, 80)}")
        if n > _LISTED:
            result.output(f"    ... and {n - _LISTED} more")
        if plan.member_objects:
            result.output(
                f"  {len(plan.member_objects)} member object(s) expanded from it stay stored; purge them too if they hold the value:"
            )
            for digest in plan.member_objects[:_LISTED]:
                result.output(f"    sha256:{digest}")
        if plan.container_objects:
            result.output("  it is also a member of a stored container whose bytes still contain it; purge the container too:")
            for digest in plan.container_objects[:_LISTED]:
                result.output(f"    sha256:{digest}")
        if plan.linked_objects:
            result.output(
                f"  {len(plan.linked_objects)} linked object(s) (split archive parts or carved values, D-315) stay stored; "
                "purge them too if they hold the value:"
            )
            for digest in plan.linked_objects[:_LISTED]:
                result.output(f"    sha256:{digest}")


def run_purge(ctx: Context) -> CommandResult:
    from agentprov.corpus import purge as engine
    from agentprov.corpus.reader import CorpusReader
    from agentprov.raw.fetch import resolve_cache_dir

    args = ctx.args
    if args.cache_dir and not args.cache:
        raise CliUsageError("agentprov purge: --cache-dir goes with --cache")
    try:
        digest = engine.parse_digest(args.object)
    except engine.UsageError as exc:
        raise CliUsageError(f"agentprov purge: {exc}") from None
    result = CommandResult(dry_run=bool(args.dry_run))

    # pre-flight, in the order of N.1.3: usage (2) and the sealed-corpus refusal (4) before anything is asked
    try:
        if args.cache:
            cache = resolve_cache_dir(args.cache_dir, ctx.env)
            plan = engine.plan_cache(cache, digest, args.reason)
        else:
            working = engine.resolve_working_corpus(args.corpus)
            plan = engine.plan_corpus(working, digest, args.reason)
    except engine.PurgeError as exc:
        if not isinstance(exc, engine.UsageError) and exc.code != "purge.corpus.not_working":
            raise
        # a missing path, or a directory that is neither a sealed corpus nor beside a working tree (N.1.3: exit 2)
        raise CliUsageError(f"agentprov purge: {safe_text(str(exc), 300)}") from None

    _describe(plan, result, bool(args.dry_run))
    if plan.kind == "corpus":
        manifest = CorpusReader(plan.root, state="working", used_partial=True).manifest()
        corpus_id = manifest.get("corpus_id") if manifest else None
        result.corpus = {
            "content_digest": None,
            "corpus_id": corpus_id if isinstance(corpus_id, str) else "",
            "root": redact_personal(str(plan.root)),
            "state": "working",
        }
        result.notices.append(
            "corpus.json counts and the index rows' issues are not rewritten; they are refreshed when the corpus is derived or sealed"
        )

    counters = {
        "executions_withheld": plan.new_register_entries,
        "objects_removed": 1 if plan.object_label is not None else 0,
        "tombstones_written": 0 if plan.already_tombstoned else 1,
    }
    if args.dry_run:
        result.counters = counters
        result.info("agentprov purge: dry run; nothing was removed or written")
        return result

    _confirm(args, digest)
    if plan.kind == "cache":
        from agentprov.io.locks import fetch_cache_lock

        with fetch_cache_lock(plan.root, command="purge --cache"):  # G6a: never remove a file a fetch is writing
            done = engine.apply(plan, break_stale_lock=bool(args.break_stale_lock))
    else:
        done = engine.apply(plan, break_stale_lock=bool(args.break_stale_lock))
    result.counters = {
        "executions_withheld": done.register_entries_written,
        "objects_removed": 1 if done.removed else 0,
        "tombstones_written": 1 if done.tombstone_written else 0,
    }
    result.info(
        f"agentprov purge: removed sha256:{digest}; tombstone in {plan.tombstone_label}; "
        f"{done.register_entries_written} execution(s) newly withheld (release.withheld)"
    )
    if done.register_entries_written:
        result.issues_by_code["release.withheld"] = done.register_entries_written
    return result
