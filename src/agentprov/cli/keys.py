"""``agentprov keys``: endpoint keys in the OS keychain (D-702; D-395, D-655; reverse CLI parity D-700).

    agentprov keys status [--format text|json]
    agentprov keys list [--format text|json]          # names and presence only, never values
    agentprov keys set NAME [--stdin]                 # the value from a no-echo prompt, or one line on stdin
    agentprov keys delete NAME [--yes]

NAME is a key variable that ``endpoints.toml`` declares (``api_key_env``) or one of :data:`RELEASE_KEY_NAMES`, the
Zenodo tokens of the draft-only uploader (``agentprov-zenodo --keychain``, D-880), so the keychain holds nothing else. A value
never comes from argv, never reaches a log (it is registered with the redaction before anything else) and is never
printed. ``run --keychain`` reads the selected endpoint's key the same way the GUI does. Every operation goes through
the keychain helper process (:mod:`agentprov.keys.helper`), the only importer of ``keyring``; without an allowed
back-end (macOS Keychain, Windows Credential Locker, Secret Service, KWallet) the command exits 4.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, Refusal, register_secret

MAX_VALUE = 16 * 1024
#: D-880: the tokens of the draft-only Zenodo uploader (``agentprov_zenodo``, outside this package), sandbox and production.
RELEASE_KEY_NAMES = ("ZENODO_SANDBOX_TOKEN", "ZENODO_TOKEN")


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("keys", parents=[shared], help="endpoint keys in the OS keychain (names only are ever shown)",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="keys", handler=run_keys, feedback=False)
    actions = p.add_subparsers(dest="keys_action", metavar="ACTION", required=True)
    for name, help_text in (("status", "whether a secure keychain is available"),
                            ("list", "the endpoints' key variables and whether each is stored")):
        a = actions.add_parser(name, parents=[shared], help=help_text, allow_abbrev=False)
        a.add_argument("--format", choices=["text", "json"], default="text")
    s = actions.add_parser("set", parents=[shared], help="store a key (prompted without echo, or one line on stdin)",
                           allow_abbrev=False)
    s.add_argument("name", metavar="NAME", help="a key variable of endpoints.toml, e.g. OPENROUTER_API_KEY, or "
                   "ZENODO_SANDBOX_TOKEN / ZENODO_TOKEN")
    s.add_argument("--stdin", action="store_true", help="read the value as one line from stdin (never from argv)")
    d = actions.add_parser("delete", parents=[shared], help="remove a stored key", allow_abbrev=False)
    d.add_argument("name", metavar="NAME")
    d.add_argument("--yes", action="store_true", help="confirm without asking (needed when not interactive)")


def key_names() -> list[str]:
    from agentprov_capture.endpoints import load_endpoints

    return sorted({e.api_key_env for e in load_endpoints().values() if e.api_key_env} | set(RELEASE_KEY_NAMES))


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _interactive() -> bool:
    """Whether a person can answer: stdin and stderr are terminals. A seam for the tests."""
    try:
        return sys.stdin.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _read_value(from_stdin: bool) -> str:
    if from_stdin:
        raw = sys.stdin.buffer.readline(MAX_VALUE + 1) if hasattr(sys.stdin, "buffer") else sys.stdin.readline().encode()
        text = raw.decode("utf-8", "strict").rstrip("\r\n") if isinstance(raw, bytes) else str(raw).rstrip("\r\n")
    elif _interactive():
        text = getpass.getpass("value (not echoed): ")
    else:
        raise CliUsageError("agentprov keys set: give the value on a terminal prompt or with --stdin (never in argv)")
    if not text or len(text) > MAX_VALUE or any(c in text for c in "\r\n\x00"):
        raise CliUsageError("agentprov keys set: the value must be one non-empty line of at most 16 KiB")
    return text


def run_keys(ctx: Context) -> CommandResult:
    from agentprov import keys

    args = ctx.args
    result = CommandResult()
    try:
        if args.keys_action == "status":
            st = keys.status()
            doc: dict[str, object] = {"allowed": st.allowed, "backend": st.backend}
            if not st.allowed:
                doc["reason"] = keys.unavailable_reason()  # G5 P-1: why, per OS, and where keys come from instead
            if args.format == "json":
                result.payload = _payload(doc)
            else:
                result.payload = (f"keychain: {st.backend} (allowed)\n" if st.allowed else
                                  f"no secure keychain: keys cannot be stored: {doc['reason']}\n").encode()
            if not st.allowed:
                result.exit_code = 4
        elif args.keys_action == "list":
            names = key_names()
            found = keys.present(names) if names else {}
            if args.format == "json":
                result.payload = _payload({"keys": [{"name": n, "stored": found.get(n, False)} for n in names]})
            else:
                result.payload = "".join(f"{n}  {'stored' if found.get(n) else 'not stored'}\n" for n in names).encode()
        else:
            name = str(args.name)
            if name not in key_names():
                raise CliUsageError(f"agentprov keys: {name[:64]!r} is not a key variable of endpoints.toml or a "
                                    f"Zenodo token (known: {', '.join(key_names())})")
            if args.keys_action == "set":
                value = _read_value(bool(args.stdin))
                register_secret(value)  # before anything could log it
                keys.store(name, value)
                del value
                result.info(f"keys: {name} stored in the keychain")
            else:
                if not args.yes:
                    if not _interactive():
                        result.exit_code = 4
                        result.refusal = Refusal(id=name, mode="keys", status="not confirmed",
                                                 lines=("Deleting a key needs --yes when not interactive.",))
                        return result
                    answer = input(f"Delete {name} from the keychain? [y/N] ").strip().lower()
                    if answer not in ("y", "yes"):
                        result.info("keys: not deleted")
                        return result
                keys.delete(name)
                result.info(f"keys: {name} deleted")
    except keys.KeychainError as exc:
        result.exit_code = exc.exit_code
        result.error(f"agentprov keys: {exc.code}")
    return result
