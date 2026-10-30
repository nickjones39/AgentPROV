"""Post-check of the regenerated stored corpora (after the regeneration round): read-only measures over a stored working
corpus ``~/.agentprov/corpora/<id>-rg1.partial`` and its renamed predecessor ``<id>-p10.pre-regen.partial``
(``docs/reports/postcheck/README.md``; CORPUS-CHECK-PROTOCOL section 8.3).

    uv run python tools/precheck/post_check.py l2 --corpus C --out O [--sample S --l1-units U --scope full|sample]
    uv run python tools/precheck/post_check.py raw --old A --new B --out O
    uv run python tools/precheck/post_check.py ids --old A --new B --out O
    uv run python tools/precheck/post_check.py tie --scratch S --stored C --out O
    uv run python tools/precheck/post_check.py scan --corpus C --out O [--gitleaks PATH] [--threads N]
    uv run python tools/precheck/post_check.py seal-forecast --corpus C --spec corpora/<id>/corpus-spec.toml --out O

* ``l2``: the pre-check's Level-2 census (``l2_check.check``, ``redaction_scan``, ``withholding``) over the stored corpus,
  with no command run (validate, verify and recompute run separately through the queue). ``--scope sample`` restricts it
  to the executions of the frozen pre-check sample's labels, so it compares with the committed ``l2-<part>.json``.
* ``raw``: the raw store of two corpora: object digests and sizes, and the ``raw/origins.jsonl`` and
  ``raw/members.jsonl`` row multisets (protocol 8.3.1: the round does not change raw bytes).
* ``ids``: the index of two corpora: execution ids, per-execution status, completeness and unit transitions, issue codes
  (net), raw references, and the stage digests that changed.
* ``tie``: a fresh scratch import of the frozen sample against the stored corpus: every scratch execution has the same id
  and the same AER, SEM, PROV and validation digests in the stored corpus.
* ``scan``: a forecast of the release scan (``tools/release_scan.py``; G.9.4) over the working tree: the native path
  scan (home path, host name, D-457 account paths, D-600 secret shapes, archives decoded) and, with ``--gitleaks``, the
  pinned gitleaks with the release configuration. Counts by area and rule; distinct accounts as per-corpus ordinals
  (never a name or a digest of one); raw objects with an account-path hit by their content digest (12 hex).
* ``seal-forecast``: the checks ``package`` makes before sealing, evaluated without sealing: no filter or partial
  selection, the spec's profile and snapshot origins against the corpus (D-33, the product's own helpers), the card's
  mode and lint (H.9(3), H.9(5)), the datasheet statements that apply, and the withholding policy.

Every input corpus is opened read-only and must be a stored working corpus (``$AGENTPROV_HOME/corpora/*.partial``) or a
pre-check scratch corpus; outputs never go inside ``$AGENTPROV_HOME/corpora``. Counts, digests and statuses only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l2_check  # noqa: E402
from l2_common import agentprov_home, guard_output, inside, precheck_root, tilde, write_json  # noqa: E402

REPO: Final = Path(__file__).resolve().parents[2]
FORMAT: Final = "agentprov-postcheck/0.1"
_HEX12: Final = re.compile(r"^[0-9a-f]{12}")


# ================================================================================================ guards
def guard_input(path: Path) -> Path:
    """A stored working corpus (``$AGENTPROV_HOME/corpora/*.partial``) or a pre-check scratch corpus; opened read-only."""
    path = Path(os.path.abspath(path))
    if inside(path, agentprov_home() / "corpora"):
        if not path.name.endswith(".partial") or path.parent != agentprov_home() / "corpora":
            raise SystemExit(f"refused: {tilde(path)} is not a stored working corpus (corpora/<id>.partial)")
    elif not inside(path, precheck_root()):
        raise SystemExit(f"refused: {tilde(path)} is neither a stored working corpus nor a pre-check scratch corpus")
    if not (path / "corpus.json").is_file():
        raise SystemExit(f"refused: {tilde(path)} has no corpus.json")
    return path


def guard_out(path: Path) -> Path:
    if inside(Path(os.path.abspath(path)), agentprov_home() / "corpora"):
        raise SystemExit("refused: post-check outputs never go inside $AGENTPROV_HOME/corpora")
    return guard_output(path)


def _code() -> dict[str, Any]:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                           text=True, check=False)
    return {"commit": head.stdout.strip(), "tracked_changes": bool(dirty.stdout.strip())}


def _write(out: Path, check: str, body: Mapping[str, Any], started: float) -> None:
    write_json(guard_out(out), {"format": FORMAT, "check": check, "code": _code(),
                                "elapsed_s": round(time.perf_counter() - started, 1), **body})


def _rows(root: Path) -> list[dict[str, Any]]:
    """The index rows as JSON (``executions.jsonl``: a product file of the corpus)."""
    with (root / "executions.jsonl").open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _jsonl_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]


# ================================================================================================ l2
def l2(corpus: Path, sample: Path | None, l1_units: Path | None, scope: str) -> dict[str, Any]:
    if scope == "sample" and sample is None:
        raise SystemExit("--scope sample needs --sample")
    root = guard_input(corpus)
    info = l2_check.SampleInfo(sample, l1_units)
    labels = info.labels
    keep = (lambda label: label in labels) if scope == "sample" else None
    result = l2_check.check(root, info, keep=keep)
    reader, rows = result.pop("_reader"), result.pop("_rows")
    result["sem_census"] = sem_census(reader, rows)
    result["redaction"] = l2_check.redaction_scan(root, info, only={r.ex for r in rows} if scope == "sample" else None)
    source = (result["manifest"]["sources"] or [{}])[0]
    profile = source.get("profile") or {}
    try:
        result["withholding"] = l2_check.withholding(reader, root, str(profile.get("id")), int(profile.get("version") or 0),
                                                     rows)
    except Exception as exc:  # noqa: BLE001 - a refused policy or plan is a result, recorded
        result["withholding"] = {"error": f"{getattr(exc, 'code', type(exc).__name__)}: {l2_check.scrub(str(exc), 300)}"}
    return {"corpus": tilde(root), "scope": scope,
            "sample": None if sample is None else {"file": tilde(sample), "sha256": l2_check.sha256_file(sample),
                                                   "n": len(labels)},
            "l1_units": None if l1_units is None else tilde(l1_units), **result}


def sem_census(reader: Any, rows: Sequence[Any]) -> dict[str, Any]:
    """SEM annotations by ``profile | type | evidence class | log variant`` (the AER header's dialect variant), so an
    evidence-class move can be attributed to a log generation (e.g. the D-83 propagation on ``v1.k14``)."""
    counts: Counter[str] = Counter()
    unreadable: Counter[str] = Counter()
    for row in rows:
        try:
            variant = str((reader.read_aer(row).header.get("dialect") or {}).get("variant"))
        except Exception as exc:  # noqa: BLE001 - counted, never raised
            unreadable[f"aer:{getattr(exc, 'code', type(exc).__name__)}"] += 1
            continue
        for profile, out in sorted((row.sem or {}).items()):
            if out.state != "ok":
                continue
            try:
                doc = reader.read_sem(row, profile)
            except Exception as exc:  # noqa: BLE001
                unreadable[f"sem:{getattr(exc, 'code', type(exc).__name__)}"] += 1
                continue
            for ann in doc.annotations:
                counts[f"{profile}|{ann.get('type')}|{ann.get('ev')}|{variant}"] += 1
    return {"by_profile_type_class_variant": dict(sorted(counts.items())), "unreadable": dict(sorted(unreadable.items()))}


# ================================================================================================ residue
def residue(corpus: Path) -> dict[str, Any]:
    """What a seal would still release of the accounts it withholds: the product's withholding plan for the corpus
    (``l2_check.withholding_plan``, as ``package`` plans it, nothing written); the account names of the D-457 matches
    inside the withheld raw objects (in memory only); then, over every other file of the tree, the count of each name as
    a bare word and as a ``/home/<name>`` or ``/Users/<name>`` path, and the archives outside the withheld set (whose
    members only a decoded scan would see). Counts and digests only."""
    from agentprov.corpus.reader import CorpusReader

    sys.path.insert(0, str(REPO / "tools"))
    import release_scan as rs  # type: ignore[import-not-found]

    root = guard_input(corpus)
    reader = CorpusReader.open(root)
    manifest = reader.manifest() or {}
    prof = ((manifest.get("sources") or [{}])[0].get("profile") or {})
    got = l2_check.withholding_plan(reader, root, str(prof.get("id")), int(prof.get("version") or 0), reader.index())
    if got is None:
        return {"corpus": tilde(root), "policy": None}
    _policy, plan = got
    withheld = {str(getattr(o, "sha256", o)).removeprefix("sha256:") for o in plan.objects}
    objects = {p.name.split(".", 1)[0]: p for p in (root / "raw" / "objects").rglob("*") if p.is_file()}
    search = rs.Accounts.excluding(rs.personal_needles().get("home-path", ()))
    names: set[bytes] = set()
    for digest in withheld:
        path = objects.get(digest)
        if path is None:
            continue
        data = path.read_bytes()
        for start in search.offsets(data, 0):
            m = rs._ACCOUNT_PATH.match(data, start)
            if m is not None:
                names.add(next((g for g in m.groups() if g and g not in (b"Users", b"home")), b"").rstrip(b"."))
    pats = {n: (re.compile(rb"(?<![A-Za-z0-9._-])" + re.escape(n) + rb"(?![A-Za-z0-9_-])"),
                re.compile(rb"/(?:home|Users)/" + re.escape(n) + rb"(?![A-Za-z0-9._-])")) for n in names}
    bare: Counter[str] = Counter()
    paths: Counter[str] = Counter()
    files_scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith("raw/objects/") and path.name.split(".", 1)[0] in withheld:
            continue
        files_scanned += 1
        data = path.read_bytes()
        for word, home in pats.values():
            if word.search(data):
                bare[_area(rel)] += len(word.findall(data))
            if home.search(data):
                paths[_area(rel)] += len(home.findall(data))
    containers = {str(r.container).removeprefix("sha256:") for r in reader.members()} if reader.exists("raw/members.jsonl") else set()
    return {"corpus": tilde(root), "policy": True, "objects_withheld": len(withheld),
            "withheld_first12": sorted(d[:12] for d in withheld), "executions_withheld": len(plan.executions),
            "accounts_in_withheld_objects": len(names), "files_scanned_outside": files_scanned,
            "bare_name_hits_outside": dict(sorted(bare.items())), "home_path_hits_outside": dict(sorted(paths.items())),
            "archives_outside_withheld": len(containers - withheld), "archives_total": len(containers)}


# ================================================================================================ oracle
def oracle(corpus: Path, release: Path, spec: str = "adprov-v2.3-compat") -> dict[str, Any]:
    """The regression-oracle PROV of a corpus against the AgentDojo-PROV release graphs (invariant 8; gate B's B1 as
    stored bytes): a release transcript ``<stem>.transcript.json`` pairs with its graph ``<stem>.json`` (gate B's
    pairing); an execution's primary raw object is its transcript, so its ``spec`` document must be byte-identical to that
    graph. Counts only."""
    import hashlib

    from agentprov.corpus.reader import CorpusReader

    root = guard_input(corpus)
    graph_of: dict[str, str] = {}
    pairs = transcripts = 0
    for path in sorted(Path(release).rglob("*.transcript.json")):
        transcripts += 1
        graph = path.with_name(path.name[: -len(".transcript.json")] + ".json")
        if graph.is_file():
            pairs += 1
            graph_of[hashlib.sha256(path.read_bytes()).hexdigest()] = hashlib.sha256(graph.read_bytes()).hexdigest()
    reader = CorpusReader.open(root)
    result: Counter[str] = Counter()
    for row in reader.index():
        primary = next((r.sha256 for r in row.raw if r.role == "primary"), None)
        if spec not in (row.prov or {}):
            result["no_oracle_document"] += 1
            continue
        want = graph_of.get(str(primary))
        if want is None:
            result["no_release_graph"] += 1
            continue
        got = hashlib.sha256(reader.prov_bytes(row, spec)).hexdigest()
        result["byte_identical" if got == want else "differs"] += 1
    return {"corpus": tilde(root), "release": tilde(release), "spec": spec,
            "release_tree": {"transcripts": transcripts, "pairs": pairs}, "executions": len(reader.index()),
            "result": dict(sorted(result.items()))}


# ================================================================================================ dispatch
def dispatch(corpus: Path) -> dict[str, Any]:
    """Per execution with an ``unexecuted_tool_call`` seal issue: the issue's parts and the ``apv:dispatchStatus``
    statements of its PROV document by bundle type (core, inf, assess) and value. D-80 addendum (d) (regeneration-batch
    item 103) moves ``apv:NotDispatched`` from the core bundle to an inference-bundle mention where the unexecuted rule is
    the ``_unverified`` twin (unverified harness code), which ``l2_check``'s A3 ``unexecuted`` class reported as
    ``unexecuted_missing`` (R5) while it read only the core element; since POST-tool-01 it reads both bundles."""
    from agentprov.corpus.reader import CorpusReader

    root = guard_input(corpus)
    reader = CorpusReader.open(root)
    where: Counter[str] = Counter()
    executions = parts = 0
    for row in reader.index():
        aer = reader.read_aer(row)
        ids = [p for i in aer.seal.get("issues", ()) if isinstance(i, Mapping) and i.get("code") == "unexecuted_tool_call"
               for p in i.get("ids", ())]
        if not ids:
            continue
        executions += 1
        parts += len(ids)
        for spec_id, out in sorted((row.prov or {}).items()):
            if out.state != "ok":
                continue
            doc = json.loads(reader.prov_bytes(row, spec_id))

            def walk(d: Mapping[str, Any], bundle: str) -> None:
                for kind in ("entity", "activity"):
                    for attrs in (d.get(kind) or {}).values():
                        value = attrs.get("apv:dispatchStatus") if isinstance(attrs, Mapping) else None
                        if value is not None:
                            v = value.get("$") if isinstance(value, Mapping) else value
                            where[f"{bundle}|{kind}|{v}"] += 1
                for bid, sub in (d.get("bundle") or {}).items():
                    walk(sub, str(bid).split(".", 2)[1] if str(bid).count(".") >= 1 else str(bid))

            walk(doc, "top")
    return {"corpus": tilde(root), "executions_with_unexecuted_issue": executions, "unexecuted_parts": parts,
            "dispatch_status_by_bundle_kind_value": dict(sorted(where.items()))}


# ================================================================================================ raw
def raw_objects(root: Path) -> dict[str, int]:
    """Raw object hex digest -> size, from the corpus layout (``iter_tree``: role ``raw_object``)."""
    from agentprov.corpus.layout import iter_tree

    out = {}
    for label, role, size in iter_tree(root).files:
        if role == "raw_object":
            out[Path(label).name.split(".", 1)[0]] = int(size)
    return out


def _multiset_diff(old: Sequence[str], new: Sequence[str]) -> dict[str, Any]:
    a, b = Counter(old), Counter(new)
    return {"old": len(old), "new": len(new), "equal": a == b, "only_old": sum((a - b).values()),
            "only_new": sum((b - a).values())}


def _changed_fields(old: Sequence[str], new: Sequence[str], key: Sequence[str]) -> dict[str, Any]:
    """Rows matched by ``key`` (JSON of those fields): how many match, and per field how many matched rows differ in it
    (e.g. only the expand ``fn_digest`` of the member rows, D-451/BF-39)."""
    def index(lines: Sequence[str]) -> dict[str, dict[str, Any]]:
        out = {}
        for line in lines:
            row = json.loads(line)
            out[json.dumps([row.get(k) for k in key], sort_keys=True)] = row
        return out

    a, b = index(old), index(new)
    common = set(a) & set(b)
    fields: Counter[str] = Counter()
    for k in common:
        for f in set(a[k]) | set(b[k]):
            fields[f] += a[k].get(f) != b[k].get(f)
    return {"matched": len(common), "unmatched_old": len(set(a) - common), "unmatched_new": len(set(b) - common),
            "by_field": {f: n for f, n in sorted(fields.items()) if n}}


def _origin_kinds(lines: Iterable[str]) -> Counter[str]:
    kinds: Counter[str] = Counter()
    for line in lines:
        row = json.loads(line)
        origin = row.get("origin") if isinstance(row.get("origin"), Mapping) else row
        kinds[str(origin.get("kind"))] += 1
    return kinds


def raw(old: Path, new: Path) -> dict[str, Any]:
    a_root, b_root = guard_input(old), guard_input(new)
    a, b = raw_objects(a_root), raw_objects(b_root)
    common = set(a) & set(b)
    out: dict[str, Any] = {"old": tilde(a_root), "new": tilde(b_root),
                           "objects": {"old": len(a), "new": len(b), "common": len(common), "only_old": len(set(a) - set(b)),
                                       "only_new": len(set(b) - set(a)),
                                       "size_mismatch": sum(1 for h in common if a[h] != b[h]),
                                       "bytes_old": sum(a.values()), "bytes_new": sum(b.values()),
                                       "only_old_first": sorted(h[:12] for h in set(a) - set(b))[:10],
                                       "only_new_first": sorted(h[:12] for h in set(b) - set(a))[:10]}}  # fmt: skip
    for name in ("origins", "members"):
        la, lb = _jsonl_lines(a_root / "raw" / f"{name}.jsonl"), _jsonl_lines(b_root / "raw" / f"{name}.jsonl")
        entry = _multiset_diff(la, lb)
        entry["changed_fields"] = _changed_fields(la, lb, ("container", "label", "sha256") if name == "members"
                                                  else ("sha256", "origin"))
        if name == "origins":
            ka, kb = _origin_kinds(la), _origin_kinds(lb)
            entry["kinds_old"], entry["kinds_new"] = dict(sorted(ka.items())), dict(sorted(kb.items()))
            # the same (object, origin) pairs under another row shape (a field added or renamed) count as a shape change
            pa = Counter(json.dumps([json.loads(x).get("sha256"), json.loads(x).get("origin")], sort_keys=True) for x in la)
            pb = Counter(json.dumps([json.loads(x).get("sha256"), json.loads(x).get("origin")], sort_keys=True) for x in lb)
            entry["object_origin_pairs_equal"] = pa == pb
        out[name] = entry
    return out


# ================================================================================================ ids
def _stage_digests(row: Mapping[str, Any]) -> dict[str, str]:
    d = row.get("digests") or {}
    out = {"aer": str(d.get("aer")), "validation": str(d.get("validation"))}
    for kind in ("sem", "prov"):
        out[kind] = json.dumps(d.get(kind) or {}, sort_keys=True)
    return out


def ids(old: Path, new: Path) -> dict[str, Any]:
    a_root, b_root = guard_input(old), guard_input(new)
    a = {r["ex"]: r for r in _rows(a_root)}
    b = {r["ex"]: r for r in _rows(b_root)}
    common = sorted(set(a) & set(b))
    transitions: dict[str, Counter[str]] = {k: Counter() for k in ("status", "completeness", "unit", "execution_observed",
                                                                    "source_key", "profile", "adapter", "mode")}
    changed: Counter[str] = Counter()
    raw_refs = issues_old = issues_new = 0
    net: Counter[str] = Counter()
    sem_profiles: Counter[str] = Counter()
    for ex in common:
        ra, rb = a[ex], b[ex]
        for key, counter in transitions.items():
            counter[f"{ra.get(key)}->{rb.get(key)}" if key in ("status", "completeness", "unit", "execution_observed")
                    else ("same" if ra.get(key) == rb.get(key) else "changed")] += 1  # fmt: skip
        da, db = _stage_digests(ra), _stage_digests(rb)
        for stage in da:
            changed[stage] += da[stage] != db[stage]
        refs = lambda r: sorted((x.get("role"), x.get("sha256")) for x in r.get("raw") or ())  # noqa: E731
        raw_refs += refs(ra) != refs(rb)
        net.update(rb.get("issues") or ())
        net.subtract(ra.get("issues") or ())
        issues_old += len(ra.get("issues") or ())
        issues_new += len(rb.get("issues") or ())
        sem_profiles[f"{sorted((ra.get('digests') or {}).get('sem') or {})}->{sorted((rb.get('digests') or {}).get('sem') or {})}"] += 1
    return {"old": tilde(a_root), "new": tilde(b_root),
            "executions": {"old": len(a), "new": len(b), "common": len(common), "only_old": len(set(a) - set(b)),
                           "only_new": len(set(b) - set(a))},
            "transitions": {k: dict(sorted(v.items())) for k, v in transitions.items()},
            "stage_digests_changed": dict(sorted(changed.items())), "raw_refs_changed": raw_refs,
            "issues": {"old": issues_old, "new": issues_new,
                       "net": {k: v for k, v in sorted(net.items()) if v}}, "sem_profiles": dict(sem_profiles)}  # fmt: skip


# ================================================================================================ tie
def tie(scratch: Path, stored: Path) -> dict[str, Any]:
    s_root, c_root = guard_input(scratch), guard_input(stored)
    s = {r["ex"]: r for r in _rows(s_root)}
    c = {r["ex"]: r for r in _rows(c_root)}
    missing = sorted(set(s) - set(c))
    differ: Counter[str] = Counter()
    equal = 0
    for ex in sorted(set(s) & set(c)):
        ds, dc = _stage_digests(s[ex]), _stage_digests(c[ex])
        bad = [k for k in ds if ds[k] != dc[k]]
        differ.update(bad)
        equal += not bad
    sm = json.loads((s_root / "derivation.json").read_text(encoding="utf-8"))
    cm = json.loads((c_root / "derivation.json").read_text(encoding="utf-8"))
    keep = ("stage", "engine_code_sha256", "adapter_code_sha256", "fn_digest", "profile_sha256", "rules_sha256",
            "limits_sha256", "catalogue_sha256")

    def stages(doc: Mapping[str, Any]) -> dict[str, Any]:
        return {str(st.get("stage")): {k: st.get(k) for k in keep if k in st} for st in doc.get("stages", ())
                if isinstance(st, Mapping)}

    ss, cs = stages(sm), stages(cm)
    code_keys = ("engine_code_sha256", "adapter_code_sha256", "profile_sha256", "rules_sha256", "limits_sha256",
                 "catalogue_sha256")

    def code(st: Mapping[str, Any] | None) -> dict[str, Any]:
        return {k: (st or {}).get(k) for k in code_keys}

    def mode(doc: Mapping[str, Any]) -> dict[str, Any]:
        return {str(st.get("stage")): st.get("mode") for st in doc.get("stages", ()) if isinstance(st, Mapping)}

    return {"scratch": tilde(s_root), "stored": tilde(c_root),
            "executions": {"scratch": len(s), "in_stored": len(s) - len(missing), "missing_in_stored": len(missing),
                           "all_digests_equal": equal, "differ_by_stage": dict(sorted(differ.items()))},
            # the code a stage ran (engine, adapter, profile, rules, limits, catalogue digests): PC0
            "stage_code_equal": {k: code(ss.get(k)) == code(cs.get(k)) for k in sorted(set(ss) | set(cs))},
            # fn_digest also covers the stage's options, the import mode among them (dev or release)
            "fn_digest_equal": {k: (ss.get(k) or {}).get("fn_digest") == (cs.get(k) or {}).get("fn_digest")
                                for k in sorted(set(ss) | set(cs))},
            "modes": {"scratch": mode(sm), "stored": mode(cm)},
            "lockfile_equal": sm.get("lockfile_sha256") == cm.get("lockfile_sha256")}


# ================================================================================================ scan
def _area(label: str) -> str:
    head = label.split("/", 1)[0]
    if label.startswith("raw/objects/"):
        return "raw-object"
    return head if head in ("aer", "sem", "prov", "views", "validation", "raw") else "top-level"


def _account_ordinals(root: Path, findings: Sequence[Any]) -> dict[str, Any]:
    """Distinct account names of the ``account-path`` findings, as per-corpus ordinals in order of first appearance
    (file label order). Names are held in memory only; neither a name nor a digest of one is returned."""
    sys.path.insert(0, str(REPO / "tools"))
    import release_scan as rs

    search = rs.Accounts.excluding(rs.personal_needles().get("home-path", ()))
    order: dict[bytes, int] = {}
    per: Counter[int] = Counter()
    areas: dict[int, Counter[str]] = {}
    # an archive member's finding is ``<path>#<member>``: its bytes are also a stored raw object (a member origin), so the
    # plain-file pass sees them; a hashed label (``#sha256:``) is not a corpus file name either
    for label in sorted({f.path for f in findings if f.rule == rs.ACCOUNT_RULE and "#" not in f.path}):
        data = (root / label).read_bytes()
        for start in sorted(search.offsets(data, 0)):
            for pattern in (rs._ACCOUNT_PATH,):
                match = pattern.match(data, start)
                if match is None:
                    continue
                name = next((g for g in match.groups() if g and g not in (b"Users", b"home")), b"")
                n = order.setdefault(name.rstrip(b"."), len(order) + 1)
                per[n] += 1
                areas.setdefault(n, Counter())[_area(label)] += 1
    return {"distinct": len(order), "ordinals": [{"ordinal": f"#{n}", "matches": per[n], "areas": dict(sorted(areas[n].items()))}
                                                 for n in sorted(per)]}  # fmt: skip


def scan(corpus: Path, gitleaks: str | None, threads: int) -> dict[str, Any]:
    root = guard_input(corpus)
    sys.path.insert(0, str(REPO / "tools"))
    import release_scan as rs

    needles = rs.personal_needles()
    native = rs.path_scan(root, needles, workers=threads)
    by: Counter[str] = Counter()
    files: dict[str, set[str]] = {}
    raw_hits: Counter[str] = Counter()
    members: Counter[str] = Counter()
    for f in native:
        key = f"{_area(f.path)}:{f.rule}"
        by[key] += 1
        files.setdefault(key, set()).add(f.path.split("#", 1)[0])
        if "#" in f.path and not f.path.startswith("#"):
            members[key] += 1
        if f.rule == rs.ACCOUNT_RULE and f.path.startswith("raw/objects/"):
            raw_hits[Path(f.path.split("#", 1)[0]).name[:12]] += 1
    out: dict[str, Any] = {"corpus": tilde(root),
                           "native": {"findings": len(native), "by_area_rule": dict(sorted(by.items())),
                                      "files_by_area_rule": {k: len(v) for k, v in sorted(files.items())},
                                      "in_archive_members_by_area_rule": dict(sorted(members.items())),
                                      "raw_objects_with_account_path": dict(sorted(raw_hits.items())),
                                      "accounts": _account_ordinals(root, native)}}
    if gitleaks:
        version = rs.gitleaks_version(gitleaks)

        def run(argv: Sequence[str], env: Mapping[str, str], timeout: float | None) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(list(argv), env={**env, "GOMAXPROCS": str(threads)}, capture_output=True, timeout=timeout,
                                  check=False)

        found, cuts = rs.run_gitleaks(gitleaks, root, run=run)
        gl: Counter[str] = Counter(f"{_area(f.path)}:{f.rule}" for f in found)
        out["gitleaks"] = {"version": version, "findings": len(found), "key_cuts_resolved": cuts,
                           "by_area_rule": dict(sorted(gl.items()))}
    return out


# ================================================================================================ triage
def _suite_blob(dirs: Sequence[Path]) -> bytes:
    """The benchmark suite data (environment YAML, task code, fixtures) under ``dirs``, concatenated: the reference a
    finding's value is looked up in (in memory only)."""
    parts = []
    for d in dirs:
        for path in sorted(Path(d).rglob("*")):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 32 << 20:
                parts.append(path.read_bytes())
    return b"\n".join(parts)


_TOKEN: Final = re.compile(rb"[A-Za-z0-9+/=_-]{16,}")
_KEY_BEFORE: Final = re.compile(rb'"([A-Za-z_][A-Za-z0-9_]{0,39})"\s*:\s*(?:\[\s*)?"?[^"]*$')
_TOOLCHAIN: Final = (b"site-packages", b"conda", b"venv", b".cache", b"lib/python", b"node_modules", b".local/", b"pyenv",
                     b".pyenv", b"homebrew", b".rustup", b".cargo")
_USER_DIRS: Final = (b"Desktop", b"Documents", b"Downloads", b"Library/", b"Projects", b"projects", b"code/", b"repos",
                     b"git/", b"workspace", b"work/")


def _json_key(data: bytes, start: int) -> str:
    """The JSON member name a match sits under (the last ``"key":`` before it on the same string), a schema label."""
    m = _KEY_BEFORE.search(data[max(0, start - 400): start])
    return m.group(1).decode("ascii") if m else "(none)"


def _tail_class(tail: bytes) -> str:
    """What follows the account segment: a toolchain/environment directory (a harness or workstation path), a user
    folder, or other (benchmark or model content); the tail itself is not returned."""
    if any(t in tail for t in _TOOLCHAIN):
        return "toolchain"
    if any(t in tail for t in _USER_DIRS):
        return "user_dirs"
    return "other"


def _line(root: Path, label: str, number: int) -> bytes:
    with (root / label).open("rb") as handle:
        for n, line in enumerate(handle, 1):
            if n == number:
                return line
    return b""


def triage(corpus: Path, suites: Sequence[Path], gitleaks: str | None, threads: int) -> dict[str, Any]:
    """The release-scan forecast's findings checked against the benchmark suite data (``--suites``), in memory:

    * ``account-path``: per account ordinal (the scan's order), whether ``/home/<name>``, ``/Users/<name>`` or the
      bare name (word-bounded) occurs in the suite data (benchmark fiction), the name's length, and the areas;
    * every other rule (gitleaks, D-600 shapes): whether the finding's line shares a token of 16 or more characters
      with the suite data (a ``private-key`` header line: whether the same header occurs there).

    Archive-member findings are counted only (their stored copies are triaged as plain files). Nothing but counts,
    ordinals, lengths and booleans is returned."""
    root = guard_input(corpus)
    sys.path.insert(0, str(REPO / "tools"))
    import release_scan as rs

    blob = _suite_blob(suites)
    native = rs.path_scan(root, rs.personal_needles(), workers=threads)
    found = list(native)
    if gitleaks:
        def run(argv: Sequence[str], env: Mapping[str, str], timeout: float | None) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(list(argv), env={**env, "GOMAXPROCS": str(threads)}, capture_output=True, timeout=timeout,
                                  check=False)

        found += rs.run_gitleaks(gitleaks, root, run=run)[0]
    search = rs.Accounts.excluding(rs.personal_needles().get("home-path", ()))
    order: dict[bytes, int] = {}
    per: dict[int, Counter[str]] = {}
    keys: dict[int, Counter[str]] = {}
    tails: dict[int, Counter[str]] = {}
    for label in sorted({f.path for f in found if f.rule == rs.ACCOUNT_RULE and "#" not in f.path}):
        data = (root / label).read_bytes()
        for start in sorted(search.offsets(data, 0)):
            match = rs._ACCOUNT_PATH.match(data, start)
            if match is None:
                continue
            name = next((g for g in match.groups() if g and g not in (b"Users", b"home")), b"").rstrip(b".")
            n = order.setdefault(name, len(order) + 1)
            per.setdefault(n, Counter())[_area(label)] += 1
            keys.setdefault(n, Counter())[_json_key(data, start)] += 1
            tails.setdefault(n, Counter())[_tail_class(data[match.end(): match.end() + 120])] += 1
    ordinals = []
    for name, n in sorted(order.items(), key=lambda kv: kv[1]):
        word = re.compile(rb"(?<![A-Za-z0-9])" + re.escape(name) + rb"(?![A-Za-z0-9])")
        ordinals.append({"ordinal": f"#{n}", "length": len(name), "areas": dict(sorted(per[n].items())),
                         "json_keys": dict(keys[n].most_common(6)), "path_tail": dict(sorted(tails[n].items())),
                         "path_in_suite_data": (b"/home/" + name in blob) or (b"/Users/" + name in blob),
                         "name_in_suite_data": bool(word.search(blob))})
    other: Counter[str] = Counter()
    members: Counter[str] = Counter()
    for f in found:
        if f.rule == rs.ACCOUNT_RULE:
            continue
        key = f"{_area(f.path)}:{f.rule}"
        if "#" in f.path:
            members[key] += 1
            continue
        line = _line(root, f.path, f.line)
        if f.rule == "private-key":
            head = re.search(rb"-----BEGIN[A-Z ]*PRIVATE KEY-----", line)
            hit = head is not None and head.group(0) in blob
        else:
            hit = any(tok in blob for tok in _TOKEN.findall(line))
        other[f"{key}:{'in_suite_data' if hit else 'not_in_suite_data'}"] += 1
    return {"corpus": tilde(root), "suites": [tilde(d) for d in suites], "suite_bytes": len(blob),
            "accounts": {"distinct": len(order), "ordinals": ordinals},
            "other_rules": dict(sorted(other.items())), "archive_members_not_triaged": dict(sorted(members.items()))}


# ================================================================================================ seal forecast
def _step(steps: list[dict[str, Any]], name: str, fn: Any) -> Any:
    """Run one of ``package``'s pre-seal checks; a ``PackageRefusedError`` is recorded (code, scrubbed message)."""
    from agentprov.corpus.package import PackageRefusedError

    try:
        value = fn()
    except PackageRefusedError as exc:
        steps.append({"check": name, "result": "refused", "code": exc.code, "message": l2_check.scrub(str(exc), 300)})
        return None
    steps.append({"check": name, "result": "pass" if value is not False else "fail"})
    return value


def seal_forecast(corpus: Path, spec_path: Path) -> dict[str, Any]:
    """``package``'s own pre-seal checks on the working corpus, in its order, without sealing (nothing is written):
    ``_check_working``, shard depth, ``CHANGES.toml``, the source profile's digest, ``_check_context``, ``_check_stages``,
    ``_licences``, the D-33 snapshot origin (``l2_check.pin_origins``), the card (mode, lint) and the withholding policy.
    The producer commit and tree (H.2.7), the licence files and the catalogue and semantics-profile digests are the
    seal's, at seal time, and are not forecast."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry.claims import lint_card
    from agentprov.cli.package import _profile_bytes
    from agentprov.corpus import package as pkg
    from agentprov.corpus.datasheet import card_mode, load_statements
    from agentprov.corpus.manifest import format_for_aer
    from agentprov.corpus.reader import WORKING, CorpusReader
    from agentprov.corpus.spec import parse_spec
    from agentprov.corpus.withhold import load_policy

    root = guard_input(corpus)
    steps: list[dict[str, Any]] = []
    spec_bytes = spec_path.read_bytes()
    spec = parse_spec(spec_bytes, source=spec_path.name)
    reader = CorpusReader(root, state=WORKING, used_partial=True)
    manifest = reader.manifest()
    source = _step(steps, "working", lambda: pkg._check_working(manifest, spec, spec.corpus_version))
    _step(steps, "shard_depth", lambda: reader.shard_depth == spec.shard_depth)
    changes = pkg.parse_changes((spec_path.parent / "CHANGES.toml").read_bytes())
    _step(steps, "changelog", lambda: any(e["version"] == spec.corpus_version for e in changes))
    profile = load_profile(spec.source.profile_id)
    data = _profile_bytes(profile)
    working_profile = ((manifest or {}).get("sources") or [{}])[0].get("profile") or {}
    _step(steps, "profile_version", lambda: profile.version == spec.source.profile_version)
    _step(steps, "profile_digest", lambda: "sha256:" + pkg.sha256_hex(data) == working_profile.get("sha256"))
    derivation = reader.derivation()
    corpus_format = format_for_aer(str((pkg._stage(derivation, "aer") or {}).get("format") or ""))
    if source is not None:
        _step(steps, "context", lambda: pkg._check_context(source, corpus_format))
    rows = reader.index()
    _step(steps, "stages", lambda: pkg._check_stages(spec, derivation, rows))
    profile_doc = pkg._parse_profile(data)
    policies = {s.raw_policy for s in spec.source.snapshots if s.raw_policy != "withhold"}
    from agentprov.adapters.registry import REGISTRY_DATE

    _step(steps, "licences", lambda: pkg._licences(spec, profile_doc, next(iter(policies), "withhold"), REGISTRY_DATE))
    pins = l2_check.pin_origins(root, manifest or {})
    for snap in spec.source.snapshots:
        sid = snap.snapshot_id
        _step(steps, f"origin:{sid}", lambda sid=sid, snap=snap: sid in pins and dict(snap.origin) == pins[sid])
    card = (spec_path.parent / "CARD.md").read_text(encoding="utf-8")
    source_ids = [str(s.get("source_id")) for s in (manifest or {}).get("sources", ())]
    _step(steps, "card_mode", lambda: card_mode(card) == (manifest or {}).get("mode"))
    lint = lint_card(card, source_ids=source_ids)
    _step(steps, "card_lint", lambda: not lint)
    statements = load_statements((spec_path.parent.parent / "datasheet-statements.toml").read_bytes())
    policy = load_policy(data, profile_id=profile.id, profile_version=profile.version,
                         catalogues=pkg._catalogue_versions(derivation))
    modes = Counter(str(getattr(r, "mode", None)) for r in rows)
    refused = [s for s in steps if s["result"] != "pass"]
    return {"corpus": tilde(root), "spec_file": tilde(spec_path) if not inside(spec_path.resolve(), REPO)
            else str(spec_path.resolve().relative_to(REPO)), "corpus_id": (manifest or {}).get("corpus_id"),
            "corpus_version": spec.corpus_version, "steps": steps, "refused": len(refused),
            "row_modes": dict(sorted(modes.items())),
            "card_lint": sorted({f"{v.nc_id}" for v in lint}),
            # the spec's corpus id, as package renders the datasheet (the working manifest's id is the source-level one)
            "statements": sorted(st.id for st in statements.for_corpus(str(spec.corpus_id))),
            "withholding_policy": policy is not None, "licence_files": len(spec.licence_files)}


# ================================================================================================ main
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("l2")
    p.add_argument("--corpus", required=True, type=Path)
    p.add_argument("--sample", type=Path)
    p.add_argument("--l1-units", type=Path)
    p.add_argument("--scope", choices=("full", "sample"), default="full")
    for name in ("raw", "ids"):
        p = sub.add_parser(name)
        p.add_argument("--old", required=True, type=Path)
        p.add_argument("--new", required=True, type=Path)
    p = sub.add_parser("tie")
    p.add_argument("--scratch", required=True, type=Path)
    p.add_argument("--stored", required=True, type=Path)
    p = sub.add_parser("triage")
    p.add_argument("--corpus", required=True, type=Path)
    p.add_argument("--suites", required=True, type=Path, action="append")
    p.add_argument("--gitleaks")
    p.add_argument("--threads", type=int, default=4)
    p = sub.add_parser("residue")
    p.add_argument("--corpus", required=True, type=Path)
    p = sub.add_parser("oracle")
    p.add_argument("--corpus", required=True, type=Path)
    p.add_argument("--release", required=True, type=Path)
    p = sub.add_parser("dispatch")
    p.add_argument("--corpus", required=True, type=Path)
    p = sub.add_parser("scan")
    p.add_argument("--corpus", required=True, type=Path)
    p.add_argument("--gitleaks")
    p.add_argument("--threads", type=int, default=4)
    p = sub.add_parser("seal-forecast")
    p.add_argument("--corpus", required=True, type=Path)
    p.add_argument("--spec", required=True, type=Path)
    for p in sub.choices.values():
        p.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    started = time.perf_counter()
    if a.cmd == "l2":
        body = l2(a.corpus, a.sample, a.l1_units, a.scope)
    elif a.cmd == "raw":
        body = raw(a.old, a.new)
    elif a.cmd == "ids":
        body = ids(a.old, a.new)
    elif a.cmd == "tie":
        body = tie(a.scratch, a.stored)
    elif a.cmd == "triage":
        body = triage(a.corpus, a.suites, a.gitleaks, a.threads)
    elif a.cmd == "residue":
        body = residue(a.corpus)
    elif a.cmd == "oracle":
        body = oracle(a.corpus, a.release)
    elif a.cmd == "dispatch":
        body = dispatch(a.corpus)
    elif a.cmd == "scan":
        body = scan(a.corpus, a.gitleaks, a.threads)
    else:
        body = seal_forecast(a.corpus, a.spec)
    _write(a.out, a.cmd, body, started)
    print(json.dumps({"check": a.cmd, "out": tilde(a.out), "elapsed_s": round(time.perf_counter() - started, 1)}))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("AGENTPROV_PROGRESS", "off")
    raise SystemExit(main())
