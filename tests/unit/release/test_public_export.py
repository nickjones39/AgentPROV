"""``tools/public_export.py`` (D-943; public-repo-plan.md Phase B; rehearsal F-1 and F-3): the fresh public history.

Synthetic data only: each test builds a small git repository with the export list, the development-only files it
names, a ``restricted_use`` and a ``permissive`` fixture, a tracked file that ``.gitignore`` matches, and a commit-pinned
``.gitleaksignore``. Checked: the root commit equals R minus EXCL (listing digest, identity, date, message), the
proof file sits outside the tree, refusals (a non-empty ``--out``, an export-list path that matches nothing), and the
second commit: candidate only without ``--accept``, the rewritten ``.gitleaksignore`` as its only change and the tag on
it, and refusals for an unaccepted finding or a repository with more than the root commit.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _load(name: str):
    path = Path(__file__).resolve().parents[3] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pe = _load("public_export")
EMAIL = "12345+example@users.noreply.github.com"
EXPORT_TOML = '''format = "agentprov-public-export/0.1"
[[exclude]]
path = "CLAUDE.md"
reason = "agent notes"
[[exclude]]
path = ".claude/"
reason = "agent settings"
'''


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    base = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    base.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", **(env or {})})
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=base).stdout


def _write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def dev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "dev"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    files = {
        "README.md": "readme\n", "CLAUDE.md": "notes\n", ".claude/settings.json": "{}\n",
        "docs/reports/release/public-export.toml": EXPORT_TOML, ".gitignore": "*.aer.jsonl\n",
        "tests/fixtures/harm/SOURCE.json": json.dumps([{"sample_file": "h.json", "synthetic": False,
                                                        "licence_class": "restricted_use"}]),
        "tests/fixtures/harm/h.json": "{}\n",
        "tests/fixtures/mit/SOURCE.json": json.dumps([{"sample_file": "m.json", "synthetic": False,
                                                       "licence_class": "permissive"}]),
        "tests/fixtures/mit/m.json": "{}\n",
        "src/tool.sh": "#!/bin/sh\n",
    }
    for rel, text in files.items():
        _write(repo, rel, text)
    os.chmod(repo / "src/tool.sh", 0o755)
    _write(repo, "golden/trace.aer.jsonl", "{}\n")
    _git(repo, "add", "-A")
    _git(repo, "add", "--force", "golden/trace.aer.jsonl")
    env = {"GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.invalid", "GIT_COMMITTER_NAME": "dev",
           "GIT_COMMITTER_EMAIL": "dev@example.invalid", "GIT_AUTHOR_DATE": "2026-10-29T16:55:24+13:00",
           "GIT_COMMITTER_DATE": "2026-10-29T16:55:24+13:00"}
    _git(repo, "commit", "-q", "-m", "first", env=env)
    first = _git(repo, "rev-parse", "HEAD").strip()
    _write(repo, ".gitleaksignore", f"# accepted\n{first}:docs/a.md:generic-api-key:3\n{first}:src/b.py:generic-api-key:9\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second", env=env)
    return repo, _git(repo, "rev-parse", "HEAD").strip()


def _export(repo: Path, commit: str, out: Path) -> int:
    return pe.main(["export", "--repo", str(repo), "--commit", commit, "--out", str(out), "--email", EMAIL])


def test_the_root_commit_is_r_minus_excl_with_the_no_reply_identity(dev, tmp_path, capsys):
    repo, commit = dev
    out = tmp_path / "public"
    assert _export(repo, commit, out) == 0
    files = set(_git(out, "ls-files").split())
    assert "golden/trace.aer.jsonl" in files  # F-1: tracked although .gitignore matches it
    assert not {"CLAUDE.md", ".claude/settings.json", "tests/fixtures/harm/h.json"} & files
    assert {"tests/fixtures/mit/m.json", "tests/fixtures/harm/SOURCE.json", ".gitleaksignore"} <= files
    assert _git(out, "log", "--format=%an <%ae>|%cn <%ce>|%cI|%P|%s").strip() == (
        f"Nicholas Jones <{EMAIL}>|Nicholas Jones <{EMAIL}>|2026-10-29T16:55:24+13:00||"
        f"AgentPROV v0.1.0, exported from agentprov-framework {commit}")
    assert _git(out, "ls-files", "-s", "src/tool.sh").startswith("100755")
    proof = json.loads((tmp_path / "public.export-proof.json").read_bytes())
    assert proof["development_commit"] == commit and proof["root_commit"] == _git(out, "rev-parse", "HEAD").strip()
    tree = pe.bcs.ls_tree(repo, commit)
    expected = {p: e for p, e in tree.items() if p not in proof["excluded"]}
    assert proof["listing_sha256"] == pe.bcs.listing_sha256(expected)
    assert set(proof["excluded"]) == {"CLAUDE.md", ".claude/settings.json", "tests/fixtures/harm/h.json"}
    assert not (out / "public.export-proof.json").exists() and _git(out, "status", "--porcelain") == ""


def test_export_refusals(dev, tmp_path):
    repo, commit = dev
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x", encoding="utf-8")
    assert _export(repo, commit, full) == 4
    _write(repo, "docs/reports/release/public-export.toml", EXPORT_TOML + '[[exclude]]\npath = "gone.md"\nreason = "r"\n')
    _git(repo, "commit", "-q", "-am", "list a path that is not there",
         env={"GIT_AUTHOR_NAME": "d", "GIT_AUTHOR_EMAIL": "d@x.invalid", "GIT_COMMITTER_NAME": "d",
              "GIT_COMMITTER_EMAIL": "d@x.invalid"})
    assert _export(repo, _git(repo, "rev-parse", "HEAD").strip(), tmp_path / "p2") == 4


def _report(out: Path, root: str, lines=(("docs/a.md", 4), ("src/b.py", 9))) -> Path:
    findings = [{"Commit": root, "File": f, "RuleID": "generic-api-key", "StartLine": n,
                 "Fingerprint": f"{root}:{f}:generic-api-key:{n}"} for f, n in lines]
    path = out.parent / "gitleaks.json"
    path.write_text(json.dumps(findings), encoding="utf-8")
    return path


def test_the_second_commit_rewrites_only_the_fingerprints_and_carries_the_tag(dev, tmp_path, capsys):
    repo, commit = dev
    out = tmp_path / "public"
    assert _export(repo, commit, out) == 0
    root = _git(out, "rev-parse", "HEAD").strip()
    report = _report(out, root)
    assert pe.main(["fingerprint", "--dir", str(out), "--report", str(report)]) == 0  # candidate only
    assert _git(out, "rev-list", "--count", "HEAD").strip() == "1"
    assert f"{root}:docs/a.md:generic-api-key:4" in capsys.readouterr().out
    assert pe.main(["fingerprint", "--dir", str(out), "--report", str(report), "--accept"]) == 0
    head = _git(out, "rev-parse", "HEAD").strip()
    assert _git(out, "diff", "--name-only", root, head).split() == [".gitleaksignore"]
    assert _git(out, "rev-parse", "v0.1.0^{commit}").strip() == head and _git(out, "cat-file", "-t", "v0.1.0").strip() == "tag"
    assert (out / ".gitleaksignore").read_text(encoding="utf-8") == (
        f"# accepted\n{root}:docs/a.md:generic-api-key:4\n{root}:src/b.py:generic-api-key:9\n")
    assert _git(out, "log", "-1", "--format=%ae|%cI").strip() == f"{EMAIL}|2026-10-29T16:55:24+13:00"
    assert pe.main(["fingerprint", "--dir", str(out), "--report", str(report), "--accept"]) == 4  # not the root alone


def test_an_unaccepted_finding_is_refused(dev, tmp_path):
    repo, commit = dev
    out = tmp_path / "public"
    assert _export(repo, commit, out) == 0
    root = _git(out, "rev-parse", "HEAD").strip()
    extra = _report(out, root, (("docs/a.md", 3), ("src/b.py", 9), ("src/new.py", 1)))
    assert pe.main(["fingerprint", "--dir", str(out), "--report", str(extra), "--accept"]) == 4
    other = [{"Commit": "0" * 40, "File": "docs/a.md", "RuleID": "generic-api-key", "StartLine": 3,
              "Fingerprint": f"{'0' * 40}:docs/a.md:generic-api-key:3"}]
    (out.parent / "other.json").write_text(json.dumps(other), encoding="utf-8")
    assert pe.main(["fingerprint", "--dir", str(out), "--report", str(out.parent / "other.json"), "--accept"]) == 4
    none = _report(out, root, ())
    assert pe.main(["fingerprint", "--dir", str(out), "--report", str(none), "--accept"]) == 4  # nothing left to keep
    assert _git(out, "rev-list", "--count", "HEAD").strip() == "1"


def test_an_entry_of_the_development_history_only_is_dropped_and_reported(dev, tmp_path, capsys):
    """D-1004: the D-1003 split moved a finding's text out of DECISIONS.md, so the entry pinned to the old file has no
    finding in a fresh history; it is left out (an accepted fingerprint fewer hides nothing) and named on stderr."""
    repo, commit = dev
    out = tmp_path / "public"
    assert _export(repo, commit, out) == 0
    root = _git(out, "rev-parse", "HEAD").strip()
    capsys.readouterr()
    short = _report(out, root, (("docs/a.md", 3),))
    assert pe.main(["fingerprint", "--dir", str(out), "--report", str(short), "--accept"]) == 0
    assert (out / ".gitleaksignore").read_text(encoding="utf-8") == f"# accepted\n{root}:docs/a.md:generic-api-key:3\n"
    captured = capsys.readouterr()
    assert "dropped: src/b.py (generic-api-key)" in captured.err
    assert json.loads(captured.out)["dropped"] == ["src/b.py (generic-api-key)"]


GITIGNORE_TOML = EXPORT_TOML + '''[gitignore]
reason = "coding-agent files"
append = ["CLAUDE.md", ".claude/", "/docs/agents/"]
'''


def _commit_export_list(repo: Path, text: str) -> str:
    _write(repo, "docs/reports/release/public-export.toml", text)
    _git(repo, "commit", "-q", "-am", "export list",
         env={"GIT_AUTHOR_NAME": "d", "GIT_AUTHOR_EMAIL": "d@x.invalid", "GIT_COMMITTER_NAME": "d",
              "GIT_COMMITTER_EMAIL": "d@x.invalid", "GIT_AUTHOR_DATE": "2026-10-30T09:00:00+13:00",
              "GIT_COMMITTER_DATE": "2026-10-30T09:00:00+13:00"})
    return _git(repo, "rev-parse", "HEAD").strip()


def test_the_public_gitignore_gains_the_listed_lines_in_the_root_commit_only(dev, tmp_path):
    """D-1004 (P-3a): the agent files are ignored in the public repository only; the proof records both blobs."""
    repo, _ = dev
    commit = _commit_export_list(repo, GITIGNORE_TOML)
    out = tmp_path / "public"
    assert _export(repo, commit, out) == 0
    text = (out / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("*.aer.jsonl\n\n# Public repository only (")
    assert text.endswith("coding-agent files\nCLAUDE.md\n.claude/\n/docs/agents/\n")
    assert _git(repo, "show", f"{commit}:.gitignore") == "*.aer.jsonl\n"  # the development repository is unchanged
    assert _git(out, "check-ignore", "CLAUDE.md", ".claude/settings.json", "docs/agents/x.md").split() == [
        "CLAUDE.md", ".claude/settings.json", "docs/agents/x.md"]
    assert _git(out, "status", "--porcelain") == "" and _git(out, "rev-list", "--count", "HEAD").strip() == "1"
    proof = json.loads((tmp_path / "public.export-proof.json").read_bytes())
    assert proof["gitignore"] == {"development_blob": pe.bcs.ls_tree(repo, commit)[".gitignore"].oid,
                                  "public_blob": _git(out, "rev-parse", "HEAD:.gitignore").strip(),
                                  "appended": ["CLAUDE.md", ".claude/", "/docs/agents/"]}
    expected = {p: e for p, e in pe.bcs.ls_tree(repo, commit).items() if p not in proof["excluded"]}
    expected[".gitignore"] = pe.bcs.ls_tree(out, proof["root_commit"])[".gitignore"]
    assert proof["listing_sha256"] == pe.bcs.listing_sha256(expected)
    assert not list(tmp_path.glob("*.gitignore-appended"))


def test_gitignore_lines_that_hide_a_kept_file_or_carry_a_comment_are_refused(dev, tmp_path):
    repo, _ = dev
    commit = _commit_export_list(repo, GITIGNORE_TOML.replace('"/docs/agents/"]', '"/docs/agents/", "README.md"]'))
    assert _export(repo, commit, tmp_path / "p1") == 4  # README.md is kept: an ignore line must not match it
    commit = _commit_export_list(repo, GITIGNORE_TOML.replace('"/docs/agents/"]', '"# note"]'))
    assert _export(repo, commit, tmp_path / "p2") == 4
    commit = _commit_export_list(repo, GITIGNORE_TOML.replace('reason = "coding-agent files"\n', ""))
    assert _export(repo, commit, tmp_path / "p3") == 4
