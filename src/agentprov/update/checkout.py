"""The checkout shortcut (D-1130, amending D-1065): ``git pull --ff-only`` and ``uv sync --frozen --group docs``, only
for a clean checkout of ``main`` whose remote is the project's.

An editable install (``agentprov`` run from a checkout's ``.venv``) is the checkout's own code; nothing is downloaded
from a release. ``agentprov update install --checkout --confirm --allow-network`` updates it the way its maintainer
does, and only when every condition of :func:`inspect_checkout` holds:

* the editable install's source folder is a git checkout of this project (``pyproject.toml`` names ``agentprov``,
  ``src/agentprov`` is there);
* the current branch is ``main`` and its upstream is ``origin/main``;
* ``origin``'s URL is one of the project's GitHub repositories (:data:`REMOTES`: the public ``nickjones39/AgentPROV``
  and the development repository ``nickjones39/agentprov-framework``), over https or ssh;
* the tree is clean: ``git status --porcelain`` (untracked files included) prints nothing;
* local ``main`` has no commit that ``origin/main`` lacks (``git rev-list --count origin/main..HEAD`` is 0: unpushed
  work is never put at risk), checked against the last fetch and again after this one.

* the program doing it runs from the checkout's own ``.venv`` (when the caller names its environment): ``uv sync``
  updates ``ROOT/.venv``, so an agentprov in another environment (``UV_PROJECT_ENVIRONMENT``) would be left behind.

Otherwise it changes nothing and the reason is reported with the commands, for the user to run. The steps (the effect
of ``git pull --ff-only origin main``, split so the ahead check sees the fetched state): ``git -C ROOT fetch origin
main``, the ahead check, the ignored-file check, ``git -C ROOT merge --ff-only FETCH_HEAD`` (a fast-forward or
nothing: a diverged branch is refused by git itself), then ``uv sync --frozen --group docs [--extra X …] --project
ROOT``. The ignored-file check (D-1130 review): git overwrites an ignored file without asking when the merge adds a
tracked file at its path (a clean ``git status`` does not show ignored files), so a commit that adds a path existing
on disk refuses the update. The extras (D-1130 review): ``uv sync`` is exact and removes every extra it is not given,
so each extra of ``agentprov`` whose requirements are installed (:func:`installed_extras`: ``live``, ``render``,
``shacl``, …) is named again. Nothing is ever discarded: no ``reset``,
no ``stash``, no switch to another branch. git and uv run with this environment minus every ``GIT_*``,
``UV_*`` and ``PYTHON*`` variable (so nothing redirects the repository, the index or the interpreter) and
``GIT_TERMINAL_PROMPT=0`` (no password prompt). The previous commit is reported, and ``git -C ROOT reset --keep OLD``
followed by the same ``uv sync`` goes back to it (the old commit stays in git's history).

Outside every stage closure (class 0).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote, urlsplit

from agentprov.update.releases import UpdateError

__all__ = ["REMOTES", "checkout_root", "commands", "inspect_checkout", "installed_extras", "update_checkout"]

#: the project's repositories (owner/name, compared case-insensitively) that the shortcut pulls from
REMOTES: Final = frozenset({"nickjones39/agentprov", "nickjones39/agentprov-framework"})
BRANCH: Final = "main"
GIT_TIMEOUT_S: Final = 60
PULL_TIMEOUT_S: Final = 600
SYNC_TIMEOUT_S: Final = 1800
_REMOTE: Final = re.compile(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)"
                            r"([A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?")
_DROP_ENV: Final = ("GIT_", "UV_", "PYTHON", "VIRTUAL_ENV")
_EXTRA_MARKER: Final = re.compile(r"""extra\s*==\s*["']([A-Za-z0-9._-]+)["']""")
_REQ_NAME: Final = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
#: the ignored paths an incoming commit adds that are named in a refusal
MAX_NAMED: Final = 5

Run = Callable[..., Any]


def checkout_root(direct_url: str | None = None) -> Path | None:
    """The source folder of this editable ``agentprov`` (its ``direct_url.json``), when it is a project checkout."""
    if direct_url is None:
        try:
            direct_url = metadata.distribution("agentprov").read_text("direct_url.json")
        except metadata.PackageNotFoundError:
            return None
    try:
        doc = json.loads(direct_url or "")
    except ValueError:
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("dir_info"), dict) or doc["dir_info"].get(
            "editable") is not True or not isinstance(doc.get("url"), str):
        return None
    url = urlsplit(doc["url"])
    if url.scheme != "file" or url.netloc not in ("", "localhost"):
        return None
    path = unquote(url.path)
    if os.name == "nt" and re.match(r"/[A-Za-z]:", path):
        path = path[1:]
    root = Path(path)
    return root if (root / "pyproject.toml").is_file() and (root / "src" / "agentprov").is_dir() else None


def installed_extras(*, requires: Sequence[str] | None = None,
                     installed: Callable[[str], bool] | None = None) -> list[str]:
    """The extras of this ``agentprov`` whose every requirement is installed here (sorted): what ``uv sync`` must be
    given again, or it removes them. ``requires`` (the ``Requires-Dist`` lines) and ``installed`` are seams."""
    if requires is None:
        try:
            requires = metadata.distribution("agentprov").metadata.get_all("Requires-Dist") or []
        except metadata.PackageNotFoundError:
            return []
    if installed is None:
        def installed(name: str) -> bool:
            try:
                metadata.distribution(name)
            except metadata.PackageNotFoundError:
                return False
            return True
    needs: dict[str, list[str]] = {}
    for line in requires:
        requirement, _, marker = str(line).partition(";")
        extra = _EXTRA_MARKER.search(marker)
        name = _REQ_NAME.match(requirement)
        if extra and name:
            needs.setdefault(extra.group(1), []).append(name.group(1))
    return sorted(extra for extra, names in needs.items() if all(installed(n) for n in names))


def _same(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if environ is None else environ
    env = {k: v for k, v in source.items() if not k.upper().startswith(_DROP_ENV)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(git: str, root: Path, args: list[str], run: Run, timeout: float = GIT_TIMEOUT_S) -> tuple[int, str]:
    try:
        done = run([git, "-C", str(root), *args], capture_output=True, timeout=timeout, check=False, env=_env(),
                   stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    out = done.stdout.decode("utf-8", "replace") if isinstance(done.stdout, bytes) else str(done.stdout or "")
    return done.returncode, out


def _project(url: str) -> str | None:
    m = _REMOTE.fullmatch(url.strip())
    return m.group(1).lower() if m else None


def _named_agentprov(root: Path) -> bool:
    try:
        with open(root / "pyproject.toml", "rb") as fh:
            head = fh.read(4096).decode("utf-8", "replace")
    except OSError:
        return False
    return re.search(r'(?m)^name\s*=\s*"agentprov"\s*$', head) is not None


def inspect_checkout(root: Path, *, run: Run = subprocess.run, which: Callable[[str], str | None] = shutil.which,
                     prefix: str | Path | None = None) -> dict[str, Any]:
    """Whether the shortcut may update ``root`` (``ok``), and the facts it read (no network: local git only).
    ``prefix``: the environment the program doing it runs from (``sys.prefix``), which must be ``ROOT/.venv``."""
    git, uv = which("git"), which("uv")
    facts: dict[str, Any] = {"root": str(root), "branch": None, "upstream": None, "remote": None, "clean": None,
                             "head": None, "ok": False, "why": None}

    def no(why: str) -> dict[str, Any]:
        return {**facts, "why": why}

    if not _named_agentprov(root) or not (root / "src" / "agentprov").is_dir():
        return no("the folder is not an AgentPROV checkout")
    if git is None:
        return no("git is not on PATH")
    if uv is None:
        return no("uv is not on PATH (uv sync --frozen --group docs needs it)")
    if prefix is not None and not _same(prefix, root / ".venv"):
        return no(f"this agentprov runs from {str(prefix)[:200]}, not the checkout's .venv: uv sync would update "
                  "another environment (UV_PROJECT_ENVIRONMENT?) and leave this one behind")
    code, out = _git(git, root, ["symbolic-ref", "--quiet", "--short", "HEAD"], run)
    facts["branch"] = out.strip() if code == 0 else None
    code, out = _git(git, root, ["rev-parse", "HEAD"], run)
    facts["head"] = out.strip() if code == 0 and re.fullmatch(r"[0-9a-f]{40,64}", out.strip()) else None
    if facts["branch"] != BRANCH:
        return no(f"the checkout is not on {BRANCH} (it is on {facts['branch'] or 'a detached HEAD'}): another "
                  "branch is never changed")
    code, out = _git(git, root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], run)
    facts["upstream"] = out.strip() if code == 0 else None
    if facts["upstream"] != f"origin/{BRANCH}":
        return no(f"{BRANCH}'s upstream is not origin/{BRANCH}")
    code, out = _git(git, root, ["remote", "get-url", "origin"], run)
    facts["remote"] = out.strip()[:300] if code == 0 else None
    if code != 0 or _project(out) not in REMOTES:
        return no("origin is not one of the project's GitHub repositories (nickjones39/AgentPROV, "
                  "nickjones39/agentprov-framework)")
    code, out = _git(git, root, ["status", "--porcelain=v1", "--untracked-files=normal"], run)
    facts["clean"] = code == 0 and not out.strip()
    if code != 0:
        return no("git status failed in the checkout")
    if not facts["clean"]:
        return no("the checkout has changes or untracked files: a tree with work in it is never touched")
    ahead = _ahead(git, root, run)
    facts["ahead"] = ahead
    if ahead is None:
        return no(f"git cannot compare {BRANCH} with origin/{BRANCH}")
    if ahead:
        return no(f"local {BRANCH} has {ahead} commit{'s' if ahead != 1 else ''} that origin/{BRANCH} lacks: unpushed "
                  "work is never put at risk")
    return {**facts, "ok": True, "git": git, "uv": uv}


def _ahead(git: str, root: Path, run: Run) -> int | None:
    code, out = _git(git, root, ["rev-list", "--count", f"origin/{BRANCH}..HEAD"], run)
    return int(out.strip()) if code == 0 and out.strip().isdigit() else None


def sync_argv(root: Path, extras: Sequence[str] = (), *, uv: str = "uv") -> list[str]:
    """``uv sync --frozen --group docs [--extra X …] --project ROOT``."""
    return [uv, "sync", "--frozen", "--group", "docs", *(a for x in extras for a in ("--extra", x)), "--project",
            str(root)]


def commands(root: Path, extras: Sequence[str] = ()) -> list[list[str]]:
    """What the user runs instead (and what the shortcut runs): the fast-forward and the frozen sync."""
    return [["git", "-C", str(root), "pull", "--ff-only", "origin", BRANCH], sync_argv(root, extras)]


def _ignored_in_the_way(git: str, root: Path, run: Run) -> list[str] | None:
    """The paths the fetched commits add that already exist on disk (ignored files, the tree being clean), which the
    merge would overwrite; ``None`` when git cannot say. ``--no-renames``: git's diff detects renames by default (and
    copies under ``diff.renames=copies``), and a path a fetched rename or copy creates would show as R or C, not A."""
    try:
        done = run([git, "-C", str(root), "diff", "--no-renames", "--name-only", "--diff-filter=A", "-z", "HEAD",
                    "FETCH_HEAD"],
                   capture_output=True, timeout=GIT_TIMEOUT_S, check=False, env=_env(), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    out = done.stdout if isinstance(done.stdout, bytes) else str(done.stdout or "").encode()
    names = [n.decode("utf-8", "replace") for n in out.split(b"\0") if n]
    return [n for n in names if os.path.lexists(root / n)]


def update_checkout(root: Path, *, run: Run = subprocess.run, which: Callable[[str], str | None] = shutil.which,
                    version: Callable[[], str | None] | None = None, extras: Sequence[str] = (),
                    prefix: str | Path | None = None) -> dict[str, Any]:
    """Check the conditions again, fast-forward ``main`` and sync the environment (naming ``extras`` again); the
    outcome."""
    facts = inspect_checkout(root, run=run, which=which, prefix=prefix)
    if not facts["ok"]:
        raise UpdateError(f"the checkout is not updated: {facts['why']}", code="update.checkout.refused", exit_code=4)
    git, uv, old = facts["git"], facts["uv"], facts["head"]
    code, _out = _git(git, root, ["fetch", "origin", BRANCH], run, PULL_TIMEOUT_S)
    if code != 0:
        raise UpdateError("git fetch origin main failed (offline, or the remote refused); nothing was changed",
                          code="update.checkout.pull")
    ahead = _ahead(git, root, run)
    if ahead:
        raise UpdateError(f"local {BRANCH} has {ahead} commit(s) that origin/{BRANCH} lacks: the checkout is not "
                          "updated (unpushed work is never put at risk)", code="update.checkout.refused", exit_code=4)
    in_the_way = _ignored_in_the_way(git, root, run)
    if in_the_way is None:
        raise UpdateError("git cannot list what the fetched commits add; nothing was changed",
                          code="update.checkout.pull")
    if in_the_way:
        from agentprov.ingest.quote import escape_untrusted_line

        named = ", ".join(escape_untrusted_line(n, max_chars=120) for n in in_the_way[:MAX_NAMED])
        more = f" and {len(in_the_way) - MAX_NAMED} more" if len(in_the_way) > MAX_NAMED else ""
        raise UpdateError(f"origin/{BRANCH} adds {named}{more}, which already exist{'s' if len(in_the_way) == 1 else ''}"
                          " here as ignored local files: the merge would overwrite them. Move them aside, then update "
                          "again; nothing was changed", code="update.checkout.refused", exit_code=4)
    code, _out = _git(git, root, ["merge", "--ff-only", "FETCH_HEAD"], run, PULL_TIMEOUT_S)
    if code != 0:
        raise UpdateError("main cannot be fast-forwarded to origin/main (they have diverged); nothing was changed",
                          code="update.checkout.pull")
    code, out = _git(git, root, ["rev-parse", "HEAD"], run)
    new = out.strip() if code == 0 else None
    try:
        done = run(sync_argv(root, extras, uv=uv), cwd=str(root), capture_output=True, timeout=SYNC_TIMEOUT_S,
                   check=False, env=_env(), stdin=subprocess.DEVNULL)
        synced = done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        synced = False
    return {"root": str(root), "from_commit": old, "to_commit": new, "changed": old != new, "synced": synced,
            "extras": list(extras), "to_version": version() if version is not None and synced else None,
            "restore": None if not old or old == new else
            [["git", "-C", str(root), "reset", "--keep", old], commands(root, extras)[1]]}
