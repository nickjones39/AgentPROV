"""Generate (or check) the AgentDojo history table from the history store and the introducing-commit indexes (D.6.16).

    uv run python tools/agentdojo/history_table.py [--cache DIR] [--out PATH] [--check]

The table lists the commits that introduced a blob under ``runs/`` (what the profile imports). Reads, offline, the blobless full-history store and the two indexes that ``agentprov fetch --profile agentdojo-upstream
--history`` made (pins ``head`` and ``2024-06``). Only trees and commit metadata are read: no blob, no network
(``GIT_NO_LAZY_FETCH=1``). For every introducing commit of either index it records the committer date and the benchmark
version in force in the commit's tree; for every benchmark version it records the commit that introduced its directory.

*Version in force.* AgentDojo registers a benchmark version as a directory ``default_suites/<vN_N_N>/`` (``load_suites.py``
imports it; the label is the directory name with ``_`` read as ``.``). The version in force at a commit is the newest such
directory present in the commit's tree (``v1`` < ``v1_1`` < ``v1_1_1`` < ``v1_1_2`` < ``v1_2`` < ``v1_2_1`` < ``v1_2_2``). A
commit whose tree has no version directory predates the label (``registered = false``): its suites are the ones the commit
``e1bc6171`` ("Add benchmark versioning") later labelled ``v1``.

*Cut.* The commit that introduced a version's directory: the earliest by (committer date, id) among the commits that add a
path under ``**/default_suites/<dir>/``, with two documented overrides. ``v1``: the commit ``bd533515`` ("Add LICENSE")
only created the empty package stubs; the version registry and the suites came with ``e1bc6171`` ("Add benchmark
versioning", 2024-06-10). ``v1_2``: until 2024-11-07 that directory name held the bug-fix state that was then renamed
``v1_1_1`` (commit ``7eee7284``), so its cut is the commit that re-created it for v1.2, ``0c7c4d56`` ("add init file for
v1.2"). The tool refuses a table in which a commit's version has a cut that is not an
ancestor of the commit.

*Under* (format 2, D-84). The oldest pin (2024-06, then head) whose history contains the commit (``git merge-base
--is-ancestor``): a log introduced under the 2024-06 pin is June-2024 code that the 2024-06 citations verify; one introduced
only under head is later code that no pin covers.

``--check`` regenerates and compares with the shipped table; the ``full_corpus`` test calls it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/ethz-spylab/agentdojo"
PINS = {"2024-06": "c274885610efaaafec38b6d3eb07152ba7ff3f94", "head": "089ed468cf3ed0322acc66b0211f26d9d90dbf60"}
ORDER = ("v1", "v1_1", "v1_1_1", "v1_1_2", "v1_2", "v1_2_1", "v1_2_2")
BASES = ("src/agentdojo/default_suites", "src/agentdojo/task_suites/default_suites", "src/agentgym/task_suites/default_suites")
CUT_OVERRIDES = {
    "v1": "e1bc6171c8179446d954f3c43a9d0aedbb165ee6",  # "Add benchmark versioning"; bd533515 only created the empty package stubs
    "v1_2": "0c7c4d565e594675041fad79bf8f6b3164ea3a04",  # "add init file for v1.2"; the name held the bug-fix state until 7eee7284
}
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "src/agentprov/adapters/agentdojo/tables/agentdojo-history.table.toml"
FORMAT = "agentprov-agentdojo-history-table/2"
_HEX40 = re.compile(r"[0-9a-f]{40}")


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.env = {
            **os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C",
        }

    def run(self, *args: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
        done = subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, text=True, env=self.env, check=False)
        if done.returncode not in ok:
            raise SystemExit(f"git {args[0]} failed: {done.stderr.strip()[:200]}")
        return done

    def dirs_at(self, commit: str) -> set[str]:
        out: set[str] = set()
        for base in BASES:
            names = self.run("ls-tree", "--name-only", commit, base + "/").stdout.split()
            out.update(n.rsplit("/", 1)[-1] for n in names if n.rsplit("/", 1)[-1] in ORDER)
        return out

    def cut_of(self, dir_name: str, head: str) -> str:
        if dir_name in CUT_OVERRIDES:
            return CUT_OVERRIDES[dir_name]
        specs = [f":(glob){b.rsplit('/default_suites', 1)[0]}/default_suites/{dir_name}/**" for b in BASES]
        out = self.run("log", "--no-renames", "--diff-filter=A", "--format=%ct %H", head, "--", *specs).stdout
        found = sorted((int(line.split()[0]), line.split()[1]) for line in out.splitlines() if line.strip())
        if not found:
            raise SystemExit(f"no commit introduced {dir_name}")
        return found[0][1]

    def date(self, commit: str) -> str:
        epoch = int(self.run("log", "-1", "--format=%ct", commit).stdout.strip())
        from datetime import UTC, datetime

        return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def subject(self, commit: str) -> str:
        return self.run("log", "-1", "--format=%s", commit).stdout.strip()

    def is_ancestor(self, ancestor: str, commit: str) -> bool:
        return self.run("merge-base", "--is-ancestor", ancestor, commit, ok=(0, 1)).returncode == 0


def label(dir_name: str) -> str:
    return dir_name.replace("_", ".")


def build(cache: Path) -> str:
    from agentprov.raw.history import HistoryIndex

    store = Store(cache / "git-history/github.com/ethz-spylab/agentdojo.git")
    commits: dict[str, str] = {}
    for commit in PINS.values():
        index = HistoryIndex.from_bytes(
            (cache / f"git-history/github.com/ethz-spylab/agentdojo.index/{commit}.jsonl").read_bytes(), expect_repo=REPO, expect_commit=commit
        )
        for (path, _blob), c in index.rows.items():
            if path.startswith("runs/") and commits.setdefault(c, index.commits[c]) != index.commits[c]:
                raise SystemExit(f"two dates for {c}")
    head = PINS["head"]
    cuts = {d: store.cut_of(d, head) for d in ORDER}
    lines = [
        "# Generated by tools/agentdojo/history_table.py from the blobless full-history store and the two introducing-commit",
        "# indexes of the pins (D.6.16). Data for the rules agentdojo.committed_no_later_than@1 and",
        "# agentdojo.benchmark_era_from_commit@1, and the facet introduced_under of D.5.4 (D-84: `under` is the oldest pin",
        "# whose history contains the commit); the profile pins its sha256, so the profile digest covers it.",
        "# Never edit by hand: `uv run python tools/agentdojo/history_table.py --check` regenerates and compares.",
        f'format = "{FORMAT}"',
        f'repo = "{REPO}"',
        "pins = [" + ", ".join(f'"{PINS[k]}"' for k in ("2024-06", "head")) + "]",
        "",
    ]
    for d in ORDER:
        cut = cuts[d]
        lines += [
            "[[version]]", f'label = "{label(d)}"', f'dir = "{d}"', f'cut = "{cut}"', f'cut_date = "{store.date(cut)}"',
            f'cut_subject = "{store.subject(cut)[:80].replace(chr(34), chr(39))}"', "",
        ]  # fmt: skip
    for commit, date in sorted(commits.items(), key=lambda kv: (kv[1], kv[0])):
        present = store.dirs_at(commit)
        version = max(present, key=ORDER.index) if present else None
        if version is not None and not store.is_ancestor(cuts[version], commit):
            raise SystemExit(f"commit {commit[:10]}: the cut of {version} ({cuts[version][:10]}) is not its ancestor")
        under = next((PINS[k] for k in ("2024-06", "head") if store.is_ancestor(commit, PINS[k])), None)
        if under is None:
            raise SystemExit(f"commit {commit[:10]} is in no pin's history")
        lines += ["[[commit]]", f'id = "{commit}"', f'date = "{date}"', f'version = "{label(version) if version else "v1"}"',
                  f"registered = {'true' if version else 'false'}", f'under = "{under}"', ""]  # fmt: skip
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, default=Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov")) / "cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="compare with the shipped table instead of writing it")
    args = parser.parse_args()
    text = build(args.cache)
    digest = hashlib.sha256(text.encode()).hexdigest()
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        print("identical" if current == text else "DIFFERENT", digest)
        return 0 if current == text else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
