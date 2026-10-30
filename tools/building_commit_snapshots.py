"""Building-commit source snapshots for the Zenodo software record (D-911, D-940).

Usage::

    python -I tools/building_commit_snapshots.py plan  --corpus DIR [--corpus DIR ...] [--repo .] [--attribute DIR=COMMIT]
        [--no-sealing]
    python -I tools/building_commit_snapshots.py build --corpus DIR [--corpus DIR ...] --out DIR [--repo .]
        [--attribute DIR=COMMIT] [--no-sealing] [--exclude PATH] [--exclude-list TOML] [--python PATH]
        [--scrub-commit COMMIT|none]
    python -I tools/building_commit_snapshots.py verify --manifest OUT/BUILDING-COMMITS.json [--corpus DIR ...]
        [--python PATH]

Every sealed corpus records the AgentPROV commits that built it, and recompute and verify reproduce a corpus at that
commit (F-8). The public repository starts from a fresh history (D-911), so those commits stay checkable through
source snapshots deposited with the software record: one ``git archive`` per distinct commit, and a manifest
``BUILDING-COMMITS.json`` (``agentprov-building-commits/0.1``) that ties each snapshot to its commit, its git tree and
the stage code digests the corpora record.

* **Which commits** (``plan``). Per corpus (sealed or working; read-only): each ``producer.build_steps`` entry with a
  ``git_commit`` (D-780; its ``stages`` name the stages that step wrote, all stages when absent); else the datasheet
  statement ``building-commit-by-digest-<abbrev>`` of a corpus built before D-780 (the abbreviation is resolved in the
  repository and, for a sealed corpus, must appear in full in ``DATASHEET.md``); else an explicit ``--attribute
  DIR=COMMIT`` from the operator (recorded as such). A corpus with none of these is refused: a commit is never guessed.
  A sealed corpus's ``producer.git_commit`` is the **sealing** commit and is snapshotted too (role ``sealing``, no stage
  checks), unless ``--no-sealing``.
* **The snapshot** (``build``). ``git archive --format=tar --prefix=agentprov-<commit12>/`` of the commit, minus the
  fixtures that stay private, found in that commit's own ``SOURCE.json`` files (any depth under ``tests/fixtures/``):
  the copyleft fixtures approved for the private repository only (every ``tests/fixtures/<dir>/`` whose ``SOURCE.json``
  marks a sample ``licence_class: restricted``, with the licence texts ``tests/fixtures/LICENSES/<dir>-*``; D-911), and,
  by U-06 as decided (D-943), every other non-synthetic entry whose class is not ``permissive`` (``restricted_use``,
  ``noncommercial``, or none yet): its ``sample_file``, or its whole directory when it names no file. Plus any
  ``--exclude`` path (it must match at every commit), plus every ``[[exclude]]`` table (``path``, ``reason``) of an
  ``--exclude-list`` file, the format of ``docs/reports/release/public-export.toml``: such a path may be absent at
  some commits but must match at one, and its reason is recorded with each path it leaves out. The tar is gzipped with
  a zero mtime and no file name, so equal inputs give equal bytes. Each excluded path is listed with its blob id.
* **Tree check.** Every member of the archive is read back; its git blob id and mode must equal the commit's
  ``ls-tree`` entry, and the member set must equal the tree minus the excluded paths (a missing, extra or changed file
  refuses the build). The archive's pax comment must name the commit. ``listing_sha256`` (``sha256`` of the sorted
  ``<mode> <blob> <path>\\n`` lines) lets anyone holding the commit, or only the snapshot, recompute the same value.
* **Stage digests.** The snapshot's ``src/agentprov`` is extracted to a temporary directory and the snapshot's **own**
  code computes the digests (``stage_definitions.code_sha256`` over ``stage_scopes``; ``raw.members`` for ``expand``)
  in a child ``python -I -B`` whose ``agentprov`` is the snapshot's. Each value is compared with every corpus entry of
  ``derivation.json`` the commit is attributed to: ``expand``, ``aer`` (``engine_code_sha256``,
  ``adapter_code_sha256``), ``sem`` (``engine_code_sha256`` and each semantics profile's digest, by the snapshot's
  ``sem.profiles.profile_digest`` over the profile directory), ``prov``, ``validation``, ``views`` and ``compat``. The
  files the ``aer`` and ``prov`` entries name by digest (the source profile and the rule catalogues) must be present in
  the snapshot with that sha256 (the source profile also gives the adapter family), and ``derivation.json``'s
  ``lockfile_sha256`` must equal the snapshot's ``uv.lock`` when one commit built the corpus. Any inequality refuses the
  build, and so does a known stage that cannot be recomputed; a stage the tool does not know is listed as unchecked.
* **Scrub ancestry.** Each snapshot commit must descend from the history scrub ``42a85025`` (account paths and secrets
  masked before it are not in the tree), unless ``--scrub-commit none``.
* ``verify`` needs no repository: it re-reads each archive, checks its size, sha256 and md5, its pax comment and
  listing digest, recomputes the stage digests with the snapshot's own code and compares them with the manifest (and,
  with ``--corpus``, with those corpora again). It runs code from the snapshots, which is the point of the check.

Standard library only; the tool never imports ``agentprov`` itself. Writes only into ``--out`` (a new or empty
directory), never inside a corpus. Nothing is pushed, uploaded or published.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMAT = "agentprov-building-commits/0.1"
MANIFEST = "BUILDING-COMMITS.json"
#: the commit that masked the account paths and secrets earlier commits carry (pre-check PC-07, D-911)
SCRUB_COMMIT = "42a85025b2bae5ddc3527ae561cb203878c7aabb"
STATEMENT = re.compile(r"^building-commit-by-digest-([0-9a-f]{7,40})$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
#: stage -> the digest fields the snapshot's code recomputes
CODE_FIELDS = {
    "expand": ("engine_code_sha256",),
    "aer": ("adapter_code_sha256", "engine_code_sha256"),
    "sem": ("engine_code_sha256", "profiles"),
    "prov": ("engine_code_sha256",),
    "validation": ("engine_code_sha256",),
    "views": ("engine_code_sha256",),
    "compat": ("engine_code_sha256",),
}
#: fixture classes a snapshot may hold (U-06 as decided, D-943): permissive, and synthetic fixtures of any class
PUBLIC_CLASSES = frozenset({"permissive"})
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_SOURCE_JSON_BYTES = 4 * 1024 * 1024


class Refused(Exception):
    """A refusal: printed as one line, exit 4; nothing more is written."""


# =============================================================================================== git plumbing
def _git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # a caller's GIT_DIR names another repo
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def git(repo: Path, *args: str, binary: bool = False) -> Any:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=_git_env(), check=False)
    if proc.returncode != 0:
        raise Refused(f"git {args[0]} failed (exit {proc.returncode}): "
                      f"{proc.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return proc.stdout if binary else proc.stdout.decode("utf-8")


def resolve_commit(repo: Path, ref: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{7,40}", ref):
        raise Refused(f"not a commit id: {ref!r} (7 to 40 lower-case hex digits)")
    out = git(repo, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}").strip()
    if not HEX40.match(out):
        raise Refused(f"commit {ref} is not in the repository")
    return out


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    kind: str
    oid: str
    path: str


def ls_tree(repo: Path, commit: str) -> dict[str, TreeEntry]:
    raw = git(repo, "ls-tree", "-r", "-z", "--full-tree", commit, binary=True)
    out: dict[str, TreeEntry] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        out[path.decode("utf-8")] = TreeEntry(mode, kind, oid, path.decode("utf-8"))
    return out


def cat_blob(repo: Path, oid: str) -> bytes:
    return git(repo, "cat-file", "blob", oid, binary=True)


# =============================================================================================== corpora
def _read_json(path: Path) -> Any:
    with open(path, "rb") as handle:
        data = handle.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise Refused(f"{path.name} of {path.parent.name} is larger than {MAX_JSON_BYTES} bytes")
    return json.loads(data)


@dataclass
class Corpus:
    dir: Path
    corpus_id: str
    sealed: bool
    derivation: Mapping[str, Any]
    #: commit -> {"basis": ..., "stages": set of stage names, or None for all}
    builds: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: (commit, stages or None for all) per build step, in build order; a commit may recur (import, import, recompute)
    steps: list[tuple[str, frozenset[str] | None]] = field(default_factory=list)
    sealing: str | None = None

    @property
    def label(self) -> str:
        return self.dir.name


def load_corpus(path: Path, repo: Path, attributed: Mapping[str, str]) -> Corpus:
    if not (path / "corpus.json").is_file() or not (path / "derivation.json").is_file():
        raise Refused(f"{path.name}: not a corpus (corpus.json and derivation.json are required)")
    manifest = _read_json(path / "corpus.json")
    corpus = Corpus(path, str(manifest.get("corpus_id")), bool(manifest.get("sealed")), _read_json(path / "derivation.json"))
    producer = manifest.get("producer") or {}
    steps = producer.get("build_steps") or []
    for step in steps:
        commit = step.get("git_commit")
        if not commit:
            continue
        if step.get("git_tree_clean") is False:
            raise Refused(f"{corpus.label}: build step {step.get('command')} at {commit[:12]} ran from a dirty tree; "
                          "a snapshot of the commit would not be the code that ran")
        full = resolve_commit(repo, commit)
        stages = step.get("stages")
        entry = corpus.builds.setdefault(full, {"basis": "producer.build_steps", "stages": set()})
        corpus.steps.append((full, None if stages is None else frozenset(stages)))
        if stages is None or entry["stages"] is None:
            entry["stages"] = None
        else:
            entry["stages"].update(stages)
    if not corpus.builds:
        statements = ((manifest.get("datasheet") or {}).get("statements")) or []
        found = [m.group(1) for s in statements if isinstance(s, str) and (m := STATEMENT.match(s))]
        if len(found) > 1:
            raise Refused(f"{corpus.label}: more than one building-commit statement")
        if found:
            full = resolve_commit(repo, found[0])
            if corpus.sealed:
                sheet = path / "DATASHEET.md"
                if not sheet.is_file() or full.encode("ascii") not in sheet.read_bytes():
                    raise Refused(f"{corpus.label}: DATASHEET.md does not name commit {full} of its statement")
            corpus.builds[full] = {"basis": f"datasheet statement building-commit-by-digest-{found[0]}", "stages": None}
    key = next((k for k in (path.name, str(path), str(path.resolve())) if k in attributed), None)
    if key is not None:
        if corpus.builds:
            raise Refused(f"{corpus.label}: --attribute given, but the corpus records its building commit")
        corpus.builds[resolve_commit(repo, attributed[key])] = {"basis": "operator attribution (--attribute)",
                                                                "stages": None}
    if not corpus.builds:
        raise Refused(f"{corpus.label}: no building commit is recorded (no build step, no building-commit statement); "
                      "name one with --attribute DIR=COMMIT")
    if corpus.sealed and producer.get("git_commit"):
        corpus.sealing = resolve_commit(repo, str(producer["git_commit"]))
    return corpus


def stage_owner(corpus: Corpus, stage: str) -> str | None:
    """The commit that wrote ``stage``: the commit of the last build step naming it, else the single all-stage
    attribution. Steps, not commits, give the order: a commit that recurs (import, import at another commit,
    recompute at the first) owns what its last step wrote."""
    owner = None
    steps = corpus.steps or [(commit, info["stages"]) for commit, info in corpus.builds.items()]
    for commit, stages in steps:  # build order
        if stages is None or stage in stages:
            owner = commit
    return owner


def plan(corpora: Sequence[Corpus], sealing: bool) -> dict[str, list[dict[str, Any]]]:
    roles: dict[str, list[dict[str, Any]]] = {}
    for corpus in corpora:
        for commit, info in corpus.builds.items():
            roles.setdefault(commit, []).append({
                "corpus_id": corpus.corpus_id, "corpus_dir": corpus.label, "role": "build", "basis": info["basis"],
                "stages": None if info["stages"] is None else sorted(info["stages"])})
        if sealing and corpus.sealing:
            roles.setdefault(corpus.sealing, []).append({
                "corpus_id": corpus.corpus_id, "corpus_dir": corpus.label, "role": "sealing",
                "basis": "producer.git_commit (sealed manifest)", "stages": []})
    return dict(sorted(roles.items()))


# =============================================================================================== exclusions
def _source_records(repo: Path, path: str, oid: str) -> list[Mapping[str, Any]]:
    data = cat_blob(repo, oid)
    if len(data) > MAX_SOURCE_JSON_BYTES:
        raise Refused(f"{path} is larger than {MAX_SOURCE_JSON_BYTES} bytes")
    records = json.loads(data)
    return [r for r in (records if isinstance(records, list) else [records]) if isinstance(r, Mapping)]


def fixture_exclusions(repo: Path, tree: Mapping[str, TreeEntry]) -> dict[str, str]:
    """path -> reason, for the fixtures of this commit's tree that stay private (see the module docstring)."""
    out: dict[str, str] = {}
    sources = sorted(p for p in tree if p.startswith("tests/fixtures/") and p.endswith("/SOURCE.json"))
    restricted: list[str] = []
    for path in sources:
        scope = path.rsplit("/", 1)[0]
        for record in _source_records(repo, path, tree[path].oid):
            cls = record.get("licence_class")
            if record.get("synthetic") is True or cls in PUBLIC_CLASSES:
                continue
            if cls == "restricted" and scope.count("/") == 2:
                restricted.append(scope.split("/")[2])
                continue
            reason = (f"{cls} fixture (U-06, D-943)" if cls else "fixture with no licence_class (U-06, D-943)")
            sample = record.get("sample_file")
            target = posixpath.normpath(f"{scope}/{sample}") if isinstance(sample, str) and sample else None
            if target is not None and not target.startswith("tests/fixtures/"):  # ../LICENSES/<text> is a sibling
                raise Refused(f"{path}: a sample_file outside tests/fixtures/")
            if target is not None and target in tree:
                out.setdefault(target, reason)
            else:  # an entry that names no file of the tree: its whole directory stays private
                for other in tree:
                    if other.startswith(scope + "/") and other != path:
                        out.setdefault(other, reason + ", whole directory")
    for name in restricted:
        prefix = f"tests/fixtures/{name}/"
        for path in tree:
            if path.startswith(prefix):
                out[path] = f"copyleft fixture {name} (licence_class restricted; private repository only)"
            base = path.rsplit("/", 1)[-1]
            if path.startswith("tests/fixtures/LICENSES/") and base.lower().startswith(name.lower() + "-"):
                out[path] = f"licence text of copyleft fixture {name}"
    return out


# =============================================================================================== archive
def build_archive(repo: Path, commit: str, excluded: Iterable[str]) -> tuple[bytes, bytes]:
    prefix = f"agentprov-{commit[:12]}/"
    specs = [f":(exclude,literal){p}" for p in sorted(excluded)]
    tar = git(repo, "-c", "tar.umask=0022", "archive", "--format=tar", f"--prefix={prefix}", commit, "--", ".", *specs,
              binary=True)
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as gz:
        gz.write(tar)
    return tar, buf.getvalue()


@dataclass
class ArchiveRead:
    comment: str | None
    entries: dict[str, TreeEntry]
    files: dict[str, bytes]  # every regular file, by path without the prefix
    prefix: str


def read_archive(gz_bytes: bytes) -> ArchiveRead:
    tar_bytes = gzip.decompress(gz_bytes)
    entries: dict[str, TreeEntry] = {}
    files: dict[str, bytes] = {}
    prefix: str | None = None
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        comment = tar.pax_headers.get("comment")
        for member in tar:
            name = member.name
            top, _, rest = name.partition("/")
            if prefix is None:
                prefix = top + "/"
            if member.isdir() and name.rstrip("/") + "/" == prefix:
                continue
            if not name.startswith(prefix) or ".." in name.split("/") or name.startswith("/"):
                raise Refused(f"archive member outside the prefix: {name!r}")
            if member.isdir():
                continue
            if member.issym():
                data = member.linkname.encode("utf-8")
                mode = "120000"
            elif member.isfile():
                handle = tar.extractfile(member)
                assert handle is not None
                data = handle.read()
                mode = "100755" if member.mode & 0o111 else "100644"
                files[rest] = data
            else:
                raise Refused(f"archive member of an unexpected type: {name!r}")
            oid = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            entries[rest] = TreeEntry(mode, "blob", oid, rest)
    return ArchiveRead(comment, entries, files, prefix or "")


def listing_sha256(entries: Mapping[str, TreeEntry]) -> str:
    lines = "".join(f"{e.mode} {e.oid} {p}\n" for p, e in sorted(entries.items(), key=lambda kv: kv[0].encode("utf-8")))
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


def tree_check(tree: Mapping[str, TreeEntry], excluded: Mapping[str, str], read: ArchiveRead) -> None:
    expected = {p: e for p, e in tree.items() if p not in excluded and e.kind == "blob"}
    missing = sorted(set(expected) - set(read.entries))
    extra = sorted(set(read.entries) - set(expected))
    changed = sorted(p for p in set(expected) & set(read.entries)
                     if (expected[p].mode, expected[p].oid) != (read.entries[p].mode, read.entries[p].oid))
    if missing or extra or changed:
        raise Refused(f"the archive differs from the commit's tree minus the exclusions: {len(missing)} missing, "
                      f"{len(extra)} extra, {len(changed)} changed (first: {(missing + extra + changed)[0]})")
    left = [p for p in read.entries if p in excluded]
    if left:
        raise Refused(f"an excluded path is in the archive: {left[0]}")


# =============================================================================================== stage digests
HELPER = r'''
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
import agentprov
if not Path(agentprov.__file__).resolve().is_relative_to(root):
    raise SystemExit("the snapshot's agentprov was not the one imported")
from agentprov.stage_definitions import code_sha256
try:
    from agentprov import stage_scopes as ss
except ImportError:
    ss = None
requests = json.loads(sys.stdin.read())
out = {}
for key, r in requests.items():
    stage = r["stage"]
    if stage == "expand":
        from agentprov.raw.members import engine_code_sha256
        out[key] = {"engine_code_sha256": "sha256:" + engine_code_sha256()}
        continue
    if ss is None:
        out[key] = None
        continue
    if stage == "aer":
        fam = r["family"]
        out[key] = {"adapter_code_sha256": "sha256:" + code_sha256([f"adapters/{fam}"]),
                    "engine_code_sha256": "sha256:" + code_sha256(ss.aer_scope(fam))}
    elif stage == "sem":
        from importlib import resources
        from agentprov.adapters.semantics_profiles import _collect, semantics_families
        from agentprov.sem.profiles import profile_digest
        from agentprov.sem.types import sem_profile_dir
        adapters = resources.files("agentprov").joinpath("adapters")
        digests, families = {}, set()
        for pid, version in r["profiles"]:
            name = sem_profile_dir(pid, version)
            found = [f for f in semantics_families() if adapters.joinpath(f, "semantics", name).is_dir()]
            if len(found) != 1:
                digests[f"{pid}@{version}"] = None
                continue
            files = {}
            _collect(adapters.joinpath(found[0], "semantics", name), "", files)
            digests[f"{pid}@{version}"] = "sha256:" + profile_digest(files)
            families.add(f"adapters/{found[0]}/semantics")
        out[key] = {"engine_code_sha256": "sha256:" + code_sha256(ss.sem_scope(sorted(families))), "profiles": digests}
    elif stage == "prov":
        out[key] = {"engine_code_sha256": "sha256:" + code_sha256(ss.prov_scope(), exclude=ss.PROV_EXCLUDE)}
    elif stage == "validation":
        out[key] = {"engine_code_sha256": "sha256:" + code_sha256(ss.validation_scope())}
    elif stage == "views":
        out[key] = {"engine_code_sha256": "sha256:" + code_sha256(["views"])}
    elif stage == "compat":
        out[key] = {"engine_code_sha256": "sha256:" + code_sha256(["prov/compat", "views"])}
    else:
        out[key] = None
sys.stdout.write(json.dumps(out, sort_keys=True))
'''


def file_index(files: Mapping[str, bytes]) -> dict[str, list[str]]:
    """sha256 -> the snapshot paths under ``src/agentprov/`` with those bytes."""
    index: dict[str, list[str]] = {}
    for path, data in files.items():
        if path.startswith("src/agentprov/"):
            index.setdefault("sha256:" + hashlib.sha256(data).hexdigest(), []).append(path)
    return index


def _family_of(paths: Sequence[str], kind: str) -> str | None:
    fams = {p.split("/")[3] for p in paths
            if p.startswith("src/agentprov/adapters/") and len(p.split("/")) > 5 and p.split("/")[4] == kind}
    return fams.pop() if len(fams) == 1 else None


def stage_requests(entry: Mapping[str, Any], index: Mapping[str, list[str]]) -> tuple[dict[str, Any] | None, list[dict]]:
    """The helper request for one ``derivation.json`` stage entry, and the file-presence checks it implies."""
    stage = entry.get("stage")
    checks: list[dict[str, Any]] = []

    def present(what: str, digest: Any, kind: str | None = None) -> list[str]:
        paths = index.get(str(digest), [])
        if kind is not None:
            paths = [p for p in paths if f"/{kind}/" in p]
        checks.append({"check": f"{stage}.{what}", "recorded": digest, "present_in_snapshot": sorted(paths),
                       "equal": bool(paths)})
        return paths

    if stage == "aer":
        paths = present("profile_sha256", entry.get("profile_sha256"), "profiles")
        for ns, digest in sorted((entry.get("rules_sha256") or {}).items()):
            present(f"rules_sha256.{ns}", digest)
        family = _family_of(paths, "profiles")
        return ({"stage": "aer", "family": family} if family else None), checks
    if stage == "sem":
        refs = [ref.rpartition("@") for ref in sorted(entry.get("profiles") or {})]
        if not refs or any(not pid or not v.isdigit() for pid, _, v in refs):
            return None, checks
        return {"stage": "sem", "profiles": [[pid, int(v)] for pid, _, v in refs]}, checks
    if stage == "prov":
        if isinstance(entry.get("rules_sha256"), str):
            present("rules_sha256", entry["rules_sha256"])
        return {"stage": "prov"}, checks
    if stage in CODE_FIELDS:
        return {"stage": stage}, checks
    return None, checks


def run_helper(python: str, files: Mapping[str, bytes], requests: Mapping[str, Any], work: Path) -> dict[str, Any]:
    if not requests:
        return {}
    with tempfile.TemporaryDirectory(prefix="bcs-", dir=work) as tmp:
        root = Path(tmp)
        for path, data in files.items():
            if not path.startswith("src/agentprov/"):
                continue
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "GIT_"))}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run([python, "-I", "-B", "-c", HELPER, str(root)], input=json.dumps(requests).encode(),
                              capture_output=True, env=env, cwd=root, check=False, timeout=600)
        if proc.returncode != 0:
            raise Refused(f"the snapshot's digest code failed (exit {proc.returncode}): "
                          f"{proc.stderr.decode('utf-8', 'replace').strip().splitlines()[-1:] or ''}")
        return json.loads(proc.stdout)


def stage_checks(corpora: Sequence[Corpus], commit: str, files: Mapping[str, bytes], python: str,
                 work: Path) -> dict[str, Any]:
    """Recompute and compare every stage digest of the corpora attributed to ``commit``."""
    index = file_index(files)
    requests: dict[str, Any] = {}
    pending: list[tuple[Corpus, int, Mapping[str, Any], str | None]] = []
    presence: list[dict[str, Any]] = []
    unchecked: list[dict[str, Any]] = []
    for corpus in corpora:
        for n, entry in enumerate(corpus.derivation.get("stages") or []):
            stage = str(entry.get("stage"))
            if stage_owner(corpus, stage) != commit:
                continue
            request, checks = stage_requests(entry, index)
            for c in checks:
                presence.append({"corpus_id": corpus.corpus_id, "corpus_dir": corpus.label, "stage_index": n, **c})
            key = json.dumps(request, sort_keys=True) if request else None
            if request is None and stage in CODE_FIELDS:
                unchecked.append({"corpus_id": corpus.corpus_id, "stage_index": n, "stage": stage,
                                  "reason": "the files the entry names by digest are not in the snapshot"})
            elif request is None:
                unchecked.append({"corpus_id": corpus.corpus_id, "stage_index": n, "stage": stage,
                                  "reason": "a stage this tool does not know"})
            else:
                requests[key] = request
            pending.append((corpus, n, entry, key))
    computed = run_helper(python, files, requests, work)
    rows: list[dict[str, Any]] = []
    for corpus, n, entry, key in pending:
        if key is None:
            continue
        values = computed.get(key)
        stage = str(entry.get("stage"))
        if values is None:
            unchecked.append({"corpus_id": corpus.corpus_id, "stage_index": n, "stage": stage,
                              "reason": "the snapshot has no stage_scopes module (before D-451)"})
            continue
        for fld in CODE_FIELDS[stage]:
            rows.append({"corpus_id": corpus.corpus_id, "corpus_dir": corpus.label, "stage_index": n, "stage": stage,
                         "field": fld, "recorded": entry.get(fld), "computed": values.get(fld),
                         "equal": entry.get(fld) == values.get(fld)})
    lock = files.get("uv.lock")
    lock_digest = "sha256:" + hashlib.sha256(lock).hexdigest() if lock is not None else None
    lockfile = []
    for corpus in corpora:
        if len(corpus.builds) == 1 and commit in corpus.builds and "lockfile_sha256" in corpus.derivation:
            recorded = corpus.derivation.get("lockfile_sha256")
            lockfile.append({"corpus_id": corpus.corpus_id, "corpus_dir": corpus.label, "recorded": recorded,
                             "computed": lock_digest, "equal": recorded == lock_digest})
    return {"requests": {k: requests[k] for k in sorted(requests)}, "computed": {k: computed[k] for k in sorted(computed)},
            "code_digests": rows, "files_by_digest": presence, "lockfile": lockfile, "unchecked": unchecked}


def failures(checks: Mapping[str, Any]) -> list[str]:
    bad = [f"{r['corpus_dir']} {r['stage']}.{r['field']}" for r in checks["code_digests"] if not r["equal"]]
    bad += [f"{r['corpus_dir']} {r['check']}" for r in checks["files_by_digest"] if not r["equal"]]
    bad += [f"{r['corpus_dir']} lockfile_sha256" for r in checks["lockfile"] if not r["equal"]]
    bad += [f"{r['corpus_id']} {r['stage']} not checked ({r['reason']})" for r in checks["unchecked"]
            if r["stage"] in CODE_FIELDS]
    return bad


# =============================================================================================== commands
def _digests(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            "md5": hashlib.md5(data, usedforsecurity=False).hexdigest()}


def _attributions(values: Sequence[str]) -> dict[str, str]:
    out = {}
    for value in values:
        corpus, sep, commit = value.rpartition("=")
        if not sep or not corpus or not commit:
            raise Refused(f"--attribute takes DIR=COMMIT, not {value!r}")
        out[corpus.rstrip("/")] = commit
    return out


def load_exclude_list(path: Path) -> list[tuple[str, str]]:
    """The ``[[exclude]]`` tables of a TOML file as ``(path, reason)``; other keys are ignored (public-export.toml)."""
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise Refused(f"--exclude-list {path}: {exc}") from None
    entries = doc.get("exclude")
    if not isinstance(entries, list) or not entries:
        raise Refused(f"--exclude-list {path} holds no [[exclude]] table")
    out = []
    for entry in entries:
        rel, reason = (entry.get("path"), entry.get("reason")) if isinstance(entry, dict) else (None, None)
        if not isinstance(rel, str) or not rel.strip("/") or rel.startswith("/") or ".." in rel.split("/"):
            raise Refused(f"--exclude-list {path}: an [[exclude]] path is a relative repository path, not {rel!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise Refused(f"--exclude-list {path}: {rel} needs a reason")
        out.append((rel, reason.strip()))
    return out


def _matches(tree: Mapping[str, TreeEntry], path: str) -> list[str]:
    return [p for p in tree if p == path or p.startswith(path.rstrip("/") + "/")]


def cmd_plan(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    corpora = [load_corpus(Path(c), repo, _attributions(args.attribute)) for c in args.corpus]
    roles = plan(corpora, not args.no_sealing)
    print(json.dumps({"commits": [{"commit": c, "roles": r} for c, r in roles.items()]}, indent=2, sort_keys=True))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    out = Path(args.out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise Refused(f"--out {out} exists and is not an empty directory")
    for c in args.corpus:
        if Path(c).resolve() == out.resolve() or Path(c).resolve() in out.resolve().parents:
            raise Refused("--out is inside a corpus")
    corpora = [load_corpus(Path(c), repo, _attributions(args.attribute)) for c in args.corpus]
    roles = plan(corpora, not args.no_sealing)
    scrub = None if args.scrub_commit == "none" else resolve_commit(repo, args.scrub_commit)
    listed = [entry for path in args.exclude_list for entry in load_exclude_list(Path(path))]
    trees = {commit: ls_tree(repo, commit) for commit in roles}
    for rel, _ in listed:  # refused before any archive is written: a listed path that matches no commit is a typo
        if not any(_matches(tree, rel) for tree in trees.values()):
            raise Refused(f"--exclude-list path {rel} matches nothing at any snapshot commit")
    snapshots: list[dict[str, Any]] = []
    artefacts: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="bcs-work-") as tmp:
        work = Path(tmp)
        for commit, commit_roles in roles.items():
            if scrub is not None:
                anc = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", scrub, commit],
                                     env=_git_env(), capture_output=True, check=False)
                if anc.returncode != 0:
                    raise Refused(f"commit {commit[:12]} does not descend from the history scrub {scrub[:12]}: its "
                                  "tree may hold account paths or secrets masked later")
            tree = trees[commit]
            excluded = fixture_exclusions(repo, tree)
            for path in args.exclude:
                hits = _matches(tree, path)
                if not hits:
                    raise Refused(f"--exclude {path} matches nothing at {commit[:12]}")
                for p in hits:
                    excluded.setdefault(p, "operator exclusion (--exclude)")
            for rel, reason in listed:
                for p in _matches(tree, rel):
                    excluded.setdefault(p, reason)
            tar, gz = build_archive(repo, commit, excluded)
            read = read_archive(gz)
            if read.comment != commit:
                raise Refused(f"the archive's pax comment does not name {commit[:12]}")
            tree_check(tree, excluded, read)
            checks = stage_checks(corpora, commit, read.files, args.python, work)
            bad = failures(checks)
            if bad:
                raise Refused(f"commit {commit[:12]}: {len(bad)} recorded digest(s) differ from the snapshot's: "
                              + "; ".join(bad[:5]))
            name = f"agentprov-src-{commit}.tar.gz"
            artefacts[name] = gz
            subject = git(repo, "log", "-1", "--format=%cI%x00%s", commit).rstrip("\n").split("\0", 1)
            snapshots.append({
                "commit": commit, "tree": git(repo, "rev-parse", f"{commit}^{{tree}}").strip(),
                "committed": subject[0], "subject": subject[1] if len(subject) > 1 else "",
                "roles": commit_roles, "scrub_ancestor": scrub,
                "archive": {"name": name, "prefix": read.prefix, "format": "tar (git archive) + gzip (mtime 0, level 9)",
                            "tar": _digests(tar), **_digests(gz), "members": len(read.entries),
                            "listing_sha256": listing_sha256(read.entries)},
                "excluded": [{"path": p, "blob": tree[p].oid, "mode": tree[p].mode, "reason": r}
                             for p, r in sorted(excluded.items())],
                "stage_checks": checks,
            })
            print(f"{commit[:12]}: {len(read.entries)} members, {len(excluded)} excluded, "
                  f"{len(checks['code_digests'])} code digests equal, {len(checks['unchecked'])} unchecked",
                  file=sys.stderr)
    git_version = git(repo, "--version").strip()
    manifest = {
        "format": FORMAT,
        "tool": "tools/building_commit_snapshots.py (D-940)",
        "git": git_version,
        "python": sys.version.split()[0],
        "corpora": [{"corpus_id": c.corpus_id, "corpus_dir": c.label, "sealed": c.sealed,
                     "building_commits": list(c.builds), "sealing_commit": c.sealing} for c in corpora],
        "snapshots": snapshots,
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, data in artefacts.items():
        with open(out / name, "xb") as handle:
            handle.write(data)
    with open(out / MANIFEST, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"out": str(out), "snapshots": len(snapshots),
                      "bytes": sum(len(v) for v in artefacts.values())}), file=sys.stderr)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = _read_json(manifest_path)
    if manifest.get("format") != FORMAT:
        raise Refused(f"not an {FORMAT} manifest")
    base = manifest_path.parent
    corpora_by_dir: dict[str, Corpus] = {}
    for c in args.corpus:
        path = Path(c)
        m = _read_json(path / "corpus.json")
        corpora_by_dir[path.name] = Corpus(path, str(m.get("corpus_id")), bool(m.get("sealed")),
                                           _read_json(path / "derivation.json"))
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="bcs-work-") as tmp:
        work = Path(tmp)
        for snap in manifest["snapshots"]:
            commit = snap["commit"]
            archive = snap["archive"]
            data = (base / archive["name"]).read_bytes()
            got = _digests(data)
            if any(got[k] != archive[k] for k in ("bytes", "sha256", "md5")):
                problems.append(f"{archive['name']}: size or digest differs from the manifest")
                continue
            read = read_archive(data)
            if read.comment != commit:
                problems.append(f"{archive['name']}: the pax comment does not name {commit}")
            if listing_sha256(read.entries) != archive["listing_sha256"]:
                problems.append(f"{archive['name']}: listing_sha256 differs")
            excluded = {e["path"] for e in snap["excluded"]}
            if excluded & set(read.entries):
                problems.append(f"{archive['name']}: an excluded path is present")
            requests = snap["stage_checks"]["requests"]
            computed = run_helper(args.python, read.files, requests, work)
            if computed != snap["stage_checks"]["computed"]:
                problems.append(f"{archive['name']}: the snapshot's code gives other stage digests than the manifest")
            for row in snap["stage_checks"]["code_digests"]:
                if not row["equal"]:
                    problems.append(f"{archive['name']}: the manifest records an unequal digest")
                corpus = corpora_by_dir.get(row["corpus_dir"])
                if corpus is None:
                    continue
                entries = corpus.derivation.get("stages") or []
                n = row["stage_index"]
                recorded = entries[n].get(row["field"]) if n < len(entries) else None
                if recorded != row["computed"]:
                    problems.append(f"{row['corpus_dir']} {row['stage']}.{row['field']}: the corpus records another "
                                    f"digest than snapshot {commit[:12]} gives")
            print(f"{commit[:12]}: checked", file=sys.stderr)
    for p in problems:
        print(p, file=sys.stderr)
    print(json.dumps({"snapshots": len(manifest["snapshots"]), "problems": len(problems)}))
    return 1 if problems else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        p = sub.add_parser(name)
        p.add_argument("--corpus", action="append", required=True, help="a corpus directory (repeatable; read-only)")
        p.add_argument("--repo", default=".", help="the development repository (default: here)")
        p.add_argument("--attribute", action="append", default=[], metavar="DIR=COMMIT",
                       help="the building commit of a corpus that records none (recorded as an operator attribution)")
        p.add_argument("--no-sealing", action="store_true", help="leave out the sealing commits")
    build = sub.choices["build"]
    build.add_argument("--out", required=True, help="a new or empty directory for the snapshots and the manifest")
    build.add_argument("--exclude", action="append", default=[], metavar="PATH", help="a further path to leave out")
    build.add_argument("--exclude-list", action="append", default=[], metavar="TOML",
                       help="[[exclude]] tables (path, reason), as in public-export.toml; a path may be absent at some "
                            "commits but must match at one")
    build.add_argument("--python", default=sys.executable, help="the interpreter that runs the snapshots' digest code")
    build.add_argument("--scrub-commit", default=SCRUB_COMMIT, help="each snapshot must descend from it ('none': off)")
    verify = sub.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--corpus", action="append", default=[], help="compare with these corpora again")
    verify.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    try:
        return {"plan": cmd_plan, "build": cmd_build, "verify": cmd_verify}[args.command](args)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
