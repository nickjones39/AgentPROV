"""Build the DTap test fixtures tests/fixtures/dtap/ from the pinned staging trees (docs/architecture D.16.14; K.4.1).

    uv run python -I tools/dtap/build_fixtures.py --runs RUNS_TREE --tasks TASKS_TREE [--out tests/fixtures/dtap]

Copies, byte-identical, the trajectory, judge and configuration files of the census fixtures F01-F21
(census/c23_fixtures_final.json) and of the step-3 additions (X01 re-judged result, X02 judge-only directory, X03 a
``_N`` attempt, X04 byte-identical ``(1)`` copies), each at its dataset path below ``runs/`` or ``tasks/``. A
configuration with sandbox ``env_vars`` is never copied: its derived copy (``tools/dtap/derive_fixture_config.py``,
transformation ``drop_env_vars``) goes below ``derived/tasks/`` with ``derived_from`` in SOURCE.json. Every copied file
is scanned with the census secret patterns and the attacker-token marker; a hit refuses the build. Prints counts only.

The committed F16 trajectory was edited afterwards (fixture scrub 2026-10-21): one third-party host-like account token
replaced by ``user``, recorded in SOURCE.json (``modified``, ``derived_from``). A rebuild copies the original bytes again,
so the scrub must then be repeated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RUNS_REPO = "https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories"
RUNS_COMMIT = "836caf2fdd78b888ddd14fb62dc038e932e17898"
TASKS_REPO = "https://huggingface.co/datasets/AI-Secure/DecodingTrust-Agent-Platform"
TASKS_COMMIT = "a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04"
LICENCE_SHA256 = "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
ATTRIBUTION = """DTap-Bench test fixtures (tests/fixtures/dtap/): attribution and modification notice (Apache-2.0 section 4)

Source datasets
  AI-Secure/DTap-Bench-Agent-Trajectories, Hugging Face dataset, revision 836caf2fdd78b888ddd14fb62dc038e932e17898
  AI-Secure/DecodingTrust-Agent-Platform, Hugging Face dataset, revision a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04
Authors
  Chen et al., "DecodingTrust-Agent Platform (DTap)", arXiv:2605.04808 (2026); dataset committers Zhaorun Chen and
  Yuzhou Nie.
Licence
  Apache License 2.0, per both dataset cards, which refer to the LICENSE of the upstream repository
  AI-secure/DecodingTrust-Agent (commit e0e38455); its text is DTap-Bench-Apache-2.0.txt beside this file
  (sha256 c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4). Neither dataset contains a LICENSE or
  NOTICE file, so there is no NOTICE text to reproduce.
Modifications
  Trajectory and judge files are byte-identical copies, except one trajectory (F16,
  runs/googleadk/gemini-3-pro-preview/workflow/benign/53/trajectory.json): on 2026-10-21, a third-party account name
  in it was replaced by `user` (1 file; the original digest is in SOURCE.json under derived_from). Task configurations that hold sandbox env_vars are not copied:
  derived copies below tests/fixtures/dtap/derived/ have every env_vars block deleted (tools/dtap/derive_fixture_config.py,
  transformation drop_env_vars; the original digest is in SOURCE.json under derived_from). Nothing else was changed.
Content warning
  The files contain prompt-injection payloads and jailbreak text by design. They are test data, never instructions.
"""
CENSUS = Path.home() / ".agentprov" / "migration-work" / "phase10b" / "census" / "c23_fixtures_final.json"
EXTRA = {
    "X01": ("openclaw/gpt-5.2/customer-service/malicious/direct/policy_misrepresentation/pol-1_002", "re-judged result (audit_correction)"),
    "X02": ("openaisdk/gpt-5.2/research/malicious/direct/Biosecurity_Risks/42", "judge-only directory"),
    "X03": ("openaisdk/gpt-5.1/finance/malicious/direct/pig_butchering/5", "a <TS>_<N>.json attempt"),
    "X04": ("openaisdk/gpt-5.1/legal/malicious/direct_prompt/fabricated_evidence/20", "byte-identical (1) copies of a trajectory and its judge"),
}
#: The census secret patterns (c13_secrets.py classes); a hit refuses the build (values are never printed).
SECRET_PATTERNS = {
    "openai_sk": re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    "aws_akia": re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "private_key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "stripe_live": re.compile(rb"[sr]k_live_[0-9A-Za-z]{10,}"),
    "bearer": re.compile(rb"[Bb]earer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "github_pat": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "google_api": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "slack_token": re.compile(rb"xox[abprs]-[0-9A-Za-z-]{10,}"),
    "token_marker": re.compile(rb"\(token:"),
}


def git_blob_sha1(data: bytes) -> str:
    h = hashlib.sha1(b"blob %d\0" % len(data), usedforsecurity=False)
    h.update(data)
    return h.hexdigest()


def scan(data: bytes) -> list[str]:
    return [name for name, rx in SECRET_PATTERNS.items() if rx.search(data)]


def main(argv: list[str] | None = None) -> int:
    from agentprov.adapters.dtap.dialect import config_path, file_class, parse_path
    from agentprov.ingest import yamlsafe

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from derive_fixture_config import _without, drop_env_vars

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--licence", type=Path, default=None, help="the upstream Apache-2.0 LICENSE (sha256 pinned)")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "dtap")
    args = parser.parse_args(argv)
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    dirs: dict[str, tuple[str, str]] = {}
    for row in census:
        dirs.setdefault(row["path"].rsplit("/", 1)[0], (row["id"].rstrip("ab"), str(row["purpose"])))
    for fid, (directory, purpose) in EXTRA.items():
        dirs[directory] = (fid, purpose)
    entries: list[dict[str, object]] = []
    hits: dict[str, int] = {}
    env_configs = 0

    def record(sample: str, data: bytes, repo: str, commit: str, original: str, fid: str, purpose: str, **extra: object) -> None:
        for name in scan(data):
            hits[name] = hits.get(name, 0) + 1
        target = args.out / sample
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entry: dict[str, object] = {
            "sample_file": sample, "url": f"{repo}/blob/{commit}/{original}", "repository": repo,
            "commit_or_revision": commit, "original_path": original, "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob_sha1": git_blob_sha1(data), "size_bytes": len(data), "record_locator": None, "licence": "Apache-2.0",
            "licence_class": "permissive", "retrieved_at": "2026-10-11", "note": f"{fid}: {purpose}", "synthetic": False,
        }
        entry.update(extra)
        entries.append(entry)

    for directory, (fid, purpose) in sorted(dirs.items()):
        src = args.runs / directory
        names = sorted(p.name for p in src.iterdir() if p.is_file())
        for name in names:
            cls = file_class(name)
            if cls == "red_teaming" or not name.endswith(".json"):
                continue
            data = (src / name).read_bytes()
            record(f"runs/{directory}/{name}", data, RUNS_REPO, RUNS_COMMIT, f"{directory}/{name}", fid, purpose)
        trajectories = [n for n in names if file_class(n) not in ("judge", "judge_copy", "red_teaming", "other")]
        if not trajectories:
            continue
        facets = parse_path(f"{directory}/{trajectories[0]}")
        assert facets is not None
        cfg_rel = config_path(facets)
        cfg = args.tasks / cfg_rel
        if not cfg.is_file():
            continue
        raw = cfg.read_bytes()
        document = yamlsafe.safe_load(raw)
        has_env = "env_vars" in json.dumps(document, default=str)
        if not has_env:
            if f"tasks/{cfg_rel}" not in {e["sample_file"] for e in entries}:
                record(f"tasks/{cfg_rel}", raw, TASKS_REPO, TASKS_COMMIT, cfg_rel, fid, purpose)
            continue
        env_configs += 1
        derived, removed = drop_env_vars(raw.decode("utf-8"))
        if _without(document) != yamlsafe.safe_load(derived.encode("utf-8")):
            print("refused: a derived configuration is not the source minus env_vars", file=sys.stderr)
            return 1
        if f"derived/tasks/{cfg_rel}" in {e["sample_file"] for e in entries}:
            continue
        record(f"derived/tasks/{cfg_rel}", derived.encode("utf-8"), TASKS_REPO, TASKS_COMMIT, cfg_rel, fid, purpose,
               derived_from={"sha256": hashlib.sha256(raw).hexdigest(), "git_blob_sha1": git_blob_sha1(raw), "path": cfg_rel,
                             "revision": TASKS_COMMIT},
               transformation="drop_env_vars (tools/dtap/derive_fixture_config.py)", modified=True,
               note_derived=f"{removed} env_vars block(s) deleted; values never copied")
    if hits:
        print(json.dumps({"refused_secret_pattern_hits": hits}), file=sys.stderr)
        return 1
    licences = args.out.parent / "LICENSES"
    licences.mkdir(parents=True, exist_ok=True)
    if args.licence is not None:
        text = args.licence.read_bytes()
        if hashlib.sha256(text).hexdigest() != LICENCE_SHA256:
            print("refused: the licence text is not the pinned upstream LICENSE", file=sys.stderr)
            return 1
        (licences / "DTap-Bench-Apache-2.0.txt").write_bytes(text)
    (licences / "DTap-Bench-ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    entries.sort(key=lambda e: str(e["sample_file"]))
    (args.out / "SOURCE.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(entries), "bytes": sum(int(str(e["size_bytes"])) for e in entries),
                      "derived_configs": env_configs, "secret_hits": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
