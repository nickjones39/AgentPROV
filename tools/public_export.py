"""The public repository's fresh history (D-943; ``docs/reports/release/public-repo-plan.md`` Phase B): local only.

    uv run python tools/public_export.py export --commit R --out DIR --email NOREPLY [--sign]
    uv run python tools/public_export.py export --commit R --onto CLONE --email NOREPLY --version v0.1.1 [--sign]
    uv run python tools/public_export.py fingerprint --dir DIR --report GITLEAKS.json --tag v0.1.0 [--accept] [--sign]

Never pushes, never creates a remote, never touches the network.

* **export** (steps 7–10). ``EXCL`` is R's own ``docs/reports/release/public-export.toml`` (its ``[[exclude]]`` paths; a
  trailing ``/`` names a directory) plus the fixtures R's ``SOURCE.json`` files keep private (D-943, the rule of
  ``tools/building_commit_snapshots.py``). ``git archive`` of R minus ``EXCL`` is unpacked into ``DIR`` (new or empty),
  ``git init -b main``, ``git add --force -A`` (a tracked file may match ``.gitignore``: rehearsal F-1) and **one root
  commit**: author and committer ``--name``/``--email`` (the GitHub no-reply address), dated at R's commit time, message
  ``AgentPROV v0.1.0, exported from agentprov-framework <R>``. The export list's ``[gitignore]`` lines (D-1004, P-3a:
  the coding-agent files, ignored in the public repository only) are appended to the public tree's ``.gitignore`` under
  a comment naming their reason; an appended line that matches a file the public tree keeps is refused. The root
  commit's ``listing_sha256`` must equal R's minus ``EXCL``, with ``.gitignore`` as that exact blob (the equality
  proof), or the export is refused. The proof, which records both ``.gitignore`` blobs and the appended lines, is
  written beside ``DIR`` (``DIR.export-proof.json``), never into the tree. Hooks are off in the new repository;
  ``--sign`` signs the commit with your own git signing configuration.
* **export --onto** (a later release, P-10; D-1011 for v0.1.1). ``CLONE`` is a clean clone of the public repository
  on ``main``: no untracked or ignored file either (``add --force -A`` would commit it), and a history with exactly one
  root commit, an export's (never the development repository). Hooks are off for the commit, as with ``--out``. The
  equality proof runs on the index before the commit; a refusal resets the clone, so a refused tree is never committed
  (review UC-1, UC-7). Its tracked files are replaced by R minus ``EXCL`` (the same ``.gitignore`` rule) and **one commit** goes
  on top of its ``HEAD``, with the same identity, date and message rules, so the public history stays one commit per
  release. The public ``.gitleaksignore`` is kept as it is: its fingerprints name public commits, and R's names
  development ones. The equality proof is R minus ``EXCL`` with the public ``.gitignore`` and the kept
  ``.gitleaksignore`` (``CLONE.export-proof.json``, beside the clone, records the parent). Run ``gitleaks git
  --log-opts=PARENT..HEAD`` on the new commit: a finding there needs a new decision before the tag.
* **fingerprint** (the second commit, rehearsal F-3). ``.gitleaksignore`` pins findings to commits (D-462), so R's file
  names development commits, and a file naming the root commit cannot be part of it. Run ``gitleaks git DIR --redact
  --report-format json --report-path GITLEAKS.json`` on the root commit; each finding is matched to R's entry with the
  same path and rule (the nearest line). Any other finding or a finding of another commit is refused: it needs a new
  decision. An entry with no finding in the root commit is dropped and reported (D-1004): it names a file of the
  development history only, such as ``DECISIONS.md`` before the D-1003 split, and a fresh history cannot hold it;
  dropping an accepted fingerprint hides nothing. Without ``--accept`` the candidate file is printed and nothing is
  committed. With
  ``--accept`` (the user's yes to the same findings again) the file is rewritten (comment blocks kept), committed with
  the root commit's identity and date as the only change, and the annotated tag (``--sign``: signed) goes on it. The
  commit is signed when the export was (``--sign`` there sets the repository's ``commit.gpgsign``).

Prints paths, counts and digests only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tarfile
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_spec = importlib.util.spec_from_file_location("building_commit_snapshots",
                                               Path(__file__).resolve().parent / "building_commit_snapshots.py")
assert _spec is not None and _spec.loader is not None
bcs = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("building_commit_snapshots", bcs)
_spec.loader.exec_module(bcs)
Refused = bcs.Refused

EXPORT_LIST = "docs/reports/release/public-export.toml"
EXPORT_FORMAT = "agentprov-public-export/0.1"
PROOF_FORMAT = "agentprov-public-export-proof/0.1"
GITLEAKSIGNORE = ".gitleaksignore"
GITIGNORE = ".gitignore"


def export_list(repo: Path, commit: str) -> dict[str, Any]:
    doc = tomllib.loads(bcs.git(repo, "show", f"{commit}:{EXPORT_LIST}"))
    if doc.get("format") != EXPORT_FORMAT:
        raise Refused(f"{EXPORT_LIST}: format is not {EXPORT_FORMAT}")
    return doc


def exclusions(repo: Path, commit: str, tree: Mapping[str, Any], doc: Mapping[str, Any] | None = None) -> dict[str, str]:
    """path -> reason: the export list of ``commit`` plus the fixtures its ``SOURCE.json`` files keep private."""
    doc = export_list(repo, commit) if doc is None else doc
    out: dict[str, str] = {}
    for entry in doc.get("exclude", []):
        path, reason = entry["path"], entry["reason"]
        hits = [p for p in tree if (p.startswith(path) if path.endswith("/") else p == path)]
        if not hits:
            raise Refused(f"{EXPORT_LIST}: {path} matches no file of {commit[:12]}")
        out.update(dict.fromkeys(hits, reason))
    for path, reason in bcs.fixture_exclusions(repo, tree).items():
        out.setdefault(path, reason)
    return out


def gitignore_lines(doc: Mapping[str, Any]) -> list[str]:
    """The ``[gitignore]`` lines of the export list (D-1004): plain patterns, one per line, never a comment."""
    table = doc.get("gitignore") or {}
    lines = table.get("append", [])
    if not isinstance(lines, list) or any(not isinstance(x, str) or x != x.strip() or not x or "\n" in x
                                          or x.startswith(("#", "!")) for x in lines):
        raise Refused(f"{EXPORT_LIST}: [gitignore] append must list plain patterns")
    if lines and not str(table.get("reason", "")).strip():
        raise Refused(f"{EXPORT_LIST}: [gitignore] needs a reason")
    return list(lines)


def public_gitignore(base: bytes, doc: Mapping[str, Any]) -> bytes:
    """R's ``.gitignore`` with the export list's ``[gitignore]`` lines appended under their reason; unchanged without."""
    lines = gitignore_lines(doc)
    if not lines:
        return base
    head = base if not base or base.endswith(b"\n") else base + b"\n"
    block = f"\n# Public repository only ({EXPORT_LIST}): {doc['gitignore']['reason']}\n" + "".join(f"{x}\n" for x in lines)
    return head + block.encode("utf-8")


def _excl_sha256(excl: Mapping[str, str]) -> str:
    lines = "".join(f"{p}\t{excl[p]}\n" for p in sorted(excl, key=lambda s: s.encode("utf-8")))
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _identity_env(name: str, email: str, date: str) -> dict[str, str]:
    env = bcs._git_env()
    env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=date, GIT_COMMITTER_NAME=name,
               GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=date)
    return env


#: Per-command configuration of the commands that write the new tree and commit: no hooks of the target clone run and
#: no line endings are converted, in both modes (``_init`` also stores them in a fresh repository).
_HARDEN = ("-c", f"core.hooksPath={os.devnull}", "-c", "core.autocrlf=false")
#: The root commit message of an export (``--onto`` accepts only a clone whose single root commit has it).
ROOT_MESSAGE = re.compile(r"AgentPROV v[0-9][0-9A-Za-z.+-]*, exported from agentprov-framework [0-9a-f]{40}")


def _run(cwd: Path, env: Mapping[str, str], *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=dict(env), check=False)
    if proc.returncode != 0:
        name = next((a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or args[i - 1] != "-c")), "?")
        raise Refused(f"git {name} failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
    return proc.stdout


def _hash_object(cwd: Path, env: Mapping[str, str], data: bytes) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), "hash-object", "--stdin"], input=data, capture_output=True,
                          env=dict(env), check=False)
    if proc.returncode != 0:
        raise Refused(f"git hash-object failed (exit {proc.returncode})")
    return proc.stdout.decode("ascii").strip()


def _init(out: Path, env: Mapping[str, str], sign: bool) -> None:
    _run(out, env, "init", "-q", "-b", "main")
    for key, value in (("core.hooksPath", os.devnull), ("core.autocrlf", "false"),
                       ("commit.gpgsign", "true" if sign else "false"), ("tag.gpgsign", "true" if sign else "false")):
        _run(out, env, "config", key, value)


def _public_history(out: Path, env: Mapping[str, str]) -> None:
    """``--onto`` only goes on a public history: exactly one root commit, made by an export (never the development
    repository, whose history must not reach the public remote)."""
    roots = _run(out, env, "rev-list", "--max-parents=0", "HEAD").split()
    if len(roots) != 1:
        raise Refused(f"{out} has {len(roots)} root commits: not a clone of the public repository")
    if not ROOT_MESSAGE.fullmatch(_run(out, env, "log", "-1", "--format=%s", roots[0]).strip()):
        raise Refused(f"{out}'s root commit is not an export's root commit: not a clone of the public repository")


def _equal(expected: Mapping[str, Any], got: Mapping[str, Any]) -> None:
    if bcs.listing_sha256(expected) != bcs.listing_sha256(got):
        missing, extra = sorted(set(expected) - set(got)), sorted(set(got) - set(expected))
        changed = sorted(p for p in set(expected) & set(got) if (expected[p].mode, expected[p].oid) != (got[p].mode, got[p].oid))
        raise Refused(f"the new commit's tree is not R minus EXCL (with the public .gitignore): {len(missing)} missing, {len(extra)} extra, "
                      f"{len(changed)} changed (first: {(missing + extra + changed)[:3]})")


def _clear_tracked(out: Path, env: Mapping[str, str]) -> None:
    """Remove every tracked file of the clone (``--onto``): the new tree is written in their place."""
    for rel in _run(out, env, "ls-files", "-z").split("\0"):
        if rel:
            (out / rel).unlink(missing_ok=True)
    for path in sorted(out.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        if path.is_dir() and ".git" not in path.relative_to(out).parts[:1] and not any(path.iterdir()):
            path.rmdir()


def cmd_export(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    onto = args.onto is not None
    if onto == (args.out is not None):
        raise Refused("give exactly one of --out (a fresh history) and --onto (a later release)")
    out = Path(args.onto if onto else args.out).resolve()
    env0 = bcs._git_env()
    parent: str | None = None
    kept_leaks: bytes | None = None
    if onto:
        if not (out / ".git").exists():
            raise Refused(f"{out} is not a clone of the public repository")
        # --ignored and --untracked-files=all: an ignored file (.env, .venv/) would otherwise be staged by `add --force -A`
        if _run(out, env0, "status", "--porcelain", "--ignored", "--untracked-files=all").strip():
            raise Refused(f"{out} has uncommitted, untracked or ignored files: use a fresh clone of the public repository")
        if _run(out, env0, "rev-parse", "--abbrev-ref", "HEAD").strip() != "main":
            raise Refused(f"{out} is not on main")
        _public_history(out, env0)
        parent = _run(out, env0, "rev-parse", "HEAD").strip()
        tracked = _run(out, env0, "ls-tree", "--name-only", "HEAD", "--", GITLEAKSIGNORE).strip()
        if tracked:
            kept_leaks = subprocess.run(["git", "-C", str(out), "show", f"HEAD:{GITLEAKSIGNORE}"], capture_output=True,
                                        env=dict(env0), check=True).stdout
    elif out.exists() and any(out.iterdir()):
        raise Refused(f"{out} is not empty")
    commit = bcs.resolve_commit(repo, args.commit)
    tree = bcs.ls_tree(repo, commit)
    doc = export_list(repo, commit)
    excl = exclusions(repo, commit, tree, doc)
    appended = gitignore_lines(doc)
    tar = bcs.git(repo, "-c", "tar.umask=0022", "archive", "--format=tar", commit, "--", ".",
                  *(f":(exclude,literal){p}" for p in sorted(excl)), binary=True)
    out.mkdir(parents=True, exist_ok=True)
    date = bcs.git(repo, "log", "-1", "--format=%cI", commit).strip()
    env = _identity_env(args.name, args.email, date)
    base = bcs.cat_blob(repo, tree[GITIGNORE].oid) if GITIGNORE in tree else b""
    ignore = public_gitignore(base, doc)
    try:
        if onto:
            _clear_tracked(out, env0)
        tar_path = out.parent / f"{out.name}.tar"
        tar_path.write_bytes(tar)
        with tarfile.open(tar_path, mode="r:") as archive:
            archive.extractall(out, filter="data")
        tar_path.unlink()
        if appended:
            (out / GITIGNORE).write_bytes(ignore)
        if kept_leaks is not None:
            (out / GITLEAKSIGNORE).write_bytes(kept_leaks)
        if onto:
            _run(out, env, "config", "commit.gpgsign", "true" if args.sign else "false")
        else:
            _init(out, env, args.sign)
        _run(out, env, *_HARDEN, "add", "--force", "-A")
        if appended:
            patterns = out.parent / f"{out.name}.gitignore-appended"
            patterns.write_text("".join(f"{x}\n" for x in appended), encoding="utf-8")
            try:
                kept = _run(out, env, "ls-files", "--cached", "--ignored", f"--exclude-from={patterns}").split("\n")
            finally:
                patterns.unlink()
            if any(kept):
                raise Refused(f"[gitignore] lines match {len([k for k in kept if k])} file(s) the public tree keeps "
                              f"(first: {[k for k in kept if k][:3]})")
        expected = {p: e for p, e in tree.items() if p not in excl and e.kind == "blob"}
        ignore_oid = _hash_object(out, env, ignore)
        if appended:
            mode = tree[GITIGNORE].mode if GITIGNORE in tree else "100644"
            expected[GITIGNORE] = bcs.TreeEntry(mode, "blob", ignore_oid, GITIGNORE)
        leaks_oid = None
        if kept_leaks is not None:
            leaks_oid = _hash_object(out, env, kept_leaks)
            expected[GITLEAKSIGNORE] = bcs.TreeEntry("100644", "blob", leaks_oid, GITLEAKSIGNORE)
        # the equality proof runs on the index before anything is committed: a refused tree never becomes a commit
        _equal(expected, bcs.ls_tree(out, _run(out, env, "write-tree").strip()))
    except Refused:
        if onto:  # leave the clone as it was: nothing was committed, and it held no untracked or ignored file
            _run(out, env0, "reset", "-q", "--hard", "HEAD")
            _run(out, env0, "clean", "-q", "-f", "-d", "-x")
        raise
    _run(out, env, *_HARDEN, "commit", "-q", "-m", f"AgentPROV {args.version}, exported from agentprov-framework {commit}")
    root = _run(out, env, "rev-parse", "HEAD").strip()
    got = bcs.ls_tree(out, root)
    _equal(expected, got)
    have = bcs.listing_sha256(got)
    proof = {"format": PROOF_FORMAT, "development_commit": commit,
             "development_tree": bcs.git(repo, "rev-parse", f"{commit}^{{tree}}").strip(),
             "root_commit": root, "root_tree": _run(out, env, "rev-parse", "HEAD^{tree}").strip(),
             "listing_sha256": have, "excluded": dict(sorted(excl.items())), "excluded_sha256": _excl_sha256(excl),
             "export_list_sha256": "sha256:" + hashlib.sha256(bcs.cat_blob(repo, tree[EXPORT_LIST].oid)).hexdigest(),
             "gitignore": {"development_blob": tree[GITIGNORE].oid if GITIGNORE in tree else None,
                           "public_blob": ignore_oid, "appended": appended},
             "files": len(got), "identity": f"{args.name} <{args.email}>", "date": date}
    if onto:
        proof["parent_commit"] = parent
        proof["gitleaksignore_kept"] = leaks_oid
    proof_path = out.parent / f"{out.name}.export-proof.json"
    proof_path.write_text(json.dumps(proof, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: proof[k] for k in ("development_commit", "root_commit", "listing_sha256", "files")}
                     | {"excluded": len(excl), "gitignore_appended": len(appended), "proof": str(proof_path)}, indent=1))
    return 0


def refingerprint(ignore_text: str, findings: Sequence[Mapping[str, Any]], root: str,
                  dropped: list[str] | None = None) -> str:
    """R's ``.gitleaksignore`` with each entry replaced by the finding of the same path and rule (nearest line); an entry
    with no such finding (development history only) is left out and appended to ``dropped``."""
    if any(f.get("Commit") != root for f in findings):
        raise Refused("a finding names another commit than the root commit")
    left = [f["Fingerprint"] for f in findings]
    out = []
    for line in ignore_text.splitlines():
        if not line or line.startswith("#"):
            out.append(line)
            continue
        _commit, path, rule, number = line.rsplit(":", 3)
        same = [fp for fp in left if fp.rsplit(":", 3)[1:3] == [path, rule]]
        if not same:
            if dropped is not None:
                dropped.append(f"{path} ({rule})")
            continue
        best = min(same, key=lambda fp: abs(int(fp.rsplit(":", 1)[1]) - int(number)))
        left.remove(best)
        out.append(best)
    if left:
        raise Refused(f"{len(left)} finding(s) of the root commit are not accepted ones: a new decision is needed")
    if not any(line and not line.startswith("#") for line in out):
        raise Refused("no accepted entry has a finding in the root commit: delete the file instead")
    return "\n".join(out) + "\n"


def cmd_fingerprint(args: argparse.Namespace) -> int:
    out = Path(args.dir).resolve()
    env0 = bcs._git_env()
    log = _run(out, env0, "log", "--format=%H %P").split("\n")
    commits = [line.split() for line in log if line.strip()]
    if len(commits) != 1 or len(commits[0]) != 1:
        raise Refused("the repository must hold exactly the root commit of an export")
    root = commits[0][0]
    findings = json.loads(Path(args.report).read_bytes())
    dropped: list[str] = []
    text = refingerprint(_run(out, env0, "show", f"{root}:{GITLEAKSIGNORE}"), findings, root, dropped)
    for entry in dropped:
        print(f"dropped: {entry}: no finding in the root commit (development history only)", file=sys.stderr)
    if not args.accept:
        sys.stdout.write(text)
        print(f"candidate only ({len(findings)} findings): nothing committed; --accept records your yes", file=sys.stderr)
        return 0
    who = _run(out, env0, "log", "-1", "--format=%an%x00%ae%x00%cI", root).strip().split("\0")
    env = _identity_env(who[0], who[1], who[2])
    (out / GITLEAKSIGNORE).write_text(text, encoding="utf-8")
    _run(out, env, "add", "--", GITLEAKSIGNORE)
    _run(out, env, "commit", "-q", "-m", f"{GITLEAKSIGNORE}: the {len(findings)} accepted gitleaks findings, fingerprinted "
                                        "for this history (D-462)")
    changed = _run(out, env, "diff", "--name-only", root, "HEAD").split()
    if changed != [GITLEAKSIGNORE]:
        raise Refused(f"the second commit changes more than {GITLEAKSIGNORE}: {changed[:5]}")
    _run(out, env, "tag", "-s" if args.sign else "-a", args.tag, "-m", f"AgentPROV {args.tag}")
    head = _run(out, env, "rev-parse", "HEAD").strip()
    print(json.dumps({"root_commit": root, "tag": args.tag, "tag_commit": head, "fingerprints": len(findings),
                      "dropped": dropped}, indent=1))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--repo", default=".", help="the development repository (default: here)")
    export.add_argument("--commit", required=True, help="the release commit R (full or abbreviated id)")
    export.add_argument("--out", help="a new or empty directory for the public repository (a fresh history)")
    export.add_argument("--onto", help="a clean clone of the public repository on main: one commit on top (P-10)")
    export.add_argument("--email", required=True, help="the GitHub no-reply address (P-7)")
    export.add_argument("--name", default="Nicholas Jones")
    export.add_argument("--version", default="v0.1.0")
    export.add_argument("--sign", action="store_true", help="sign the root commit (your git signing configuration)")
    fingerprint = sub.add_parser("fingerprint")
    fingerprint.add_argument("--dir", required=True, help="the export directory (holding only the root commit)")
    fingerprint.add_argument("--report", required=True, help="gitleaks git --report-format json output for that commit")
    fingerprint.add_argument("--tag", default="v0.1.0")
    fingerprint.add_argument("--accept", action="store_true", help="commit the rewritten file and tag (your yes)")
    fingerprint.add_argument("--sign", action="store_true", help="sign the commit and the tag")
    args = parser.parse_args(argv)
    try:
        return {"export": cmd_export, "fingerprint": cmd_fingerprint}[args.command](args)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
