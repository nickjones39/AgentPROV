"""``agentprov fetch`` (MN N.2.2, N.1.11): usage errors exit 2, a missing ``--allow-network`` exits 4, plans never touch the network.

The real network is never reached. End-to-end runs replace the CLI's ``Fetcher`` by one that fetches from a local
repository through ``file://`` (the Fetcher's test seam) and replace the profile lookup by a source table naming it.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

_RAW_TESTS = Path(__file__).resolve().parents[1] / "unit" / "raw"
if str(_RAW_TESTS) not in sys.path:
    sys.path.insert(0, str(_RAW_TESTS))

from fetch_support import FILES, REPO_URL, make_upstream, needs_git  # noqa: E402

from agentprov.cli import fetch as fetch_cmd  # noqa: E402
from agentprov.raw.fetch import Fetcher  # noqa: E402

FETCH_OPTIONS = {
    "--corpus", "--profile", "--only", "--pin", "--path", "--cache-dir", "--allow-network", "--i-consent-to-large-download",
    "--dry-run",
}  # fmt: skip


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("a test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    return tmp_path / "cache"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_upstream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **pin: Any) -> Any:
    """Make the CLI fetch from a local repository: a profile whose pin names it and a Fetcher with the test seam."""
    up = make_upstream(tmp_path)
    source = {
        "canonical_repo": REPO_URL,
        "pins": [{"role": "head", "kind": "git", "commit": up.commit, "tree": "runs/", "primary": True, **pin}],
    }
    monkeypatch.setattr(fetch_cmd, "_source_table", lambda profile_id: source)
    monkeypatch.setattr(fetch_cmd, "_shipped_profile_ids", lambda: ["whatever"])  # the one profile whose pins a reference may match

    def seamed(cache_dir: Path, **kwargs: Any) -> Fetcher:
        return Fetcher(cache_dir, remote_urls={REPO_URL: up.url}, file_protocol=True, **kwargs)

    monkeypatch.setattr(fetch_cmd, "Fetcher", seamed)
    return up


# ---------------------------------------------------------------------------------------------------- contract


def test_every_shipped_profile_pin_loads_for_the_references_mode():
    """D.16.18 item 13: the dtap-bench git pins (Hugging Face datasets) used to make ``fetch --references`` raise."""
    recipes = fetch_cmd._all_recipes()
    assert {"https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories",
            "https://huggingface.co/datasets/AI-Secure/DecodingTrust-Agent-Platform"} <= {r.repo for r in recipes}


def test_fetch_is_registered_with_its_documented_options():
    from agentprov.cli.main import COMMANDS, build_parser

    assert "fetch" in COMMANDS
    sub = next(a for a in build_parser()._actions if a.__class__.__name__ == "_SubParsersAction")
    options = {o for action in sub.choices["fetch"]._actions for o in action.option_strings}
    assert FETCH_OPTIONS <= options


def test_help_exits_zero(cli):
    run = cli("fetch", "--help")
    assert run.code == 0 and "usage:" in run.out and "--allow-network" in run.out


@pytest.mark.parametrize(
    "argv",
    [
        ("fetch",),
        ("fetch", "--corpus", ".", "--profile", "adprov-v1"),
        ("fetch", "--profile", "adprov-v1", "--only", "sha256:" + "a" * 64),
        ("fetch", "--corpus", ".", "--pin", "release"),
        ("fetch", "--corpus", ".", "--path", "runs/"),
        ("fetch", "--corpus", ".", "--only", "sha256:xyz"),
        ("fetch", "--corpus", ".", "--only", "abc"),
        ("fetch", "--profile", "../etc/passwd"),
        ("fetch", "--profile", "Bad Id"),
        ("fetch", "--corpus", "/nonexistent-corpus-dir-xyz"),
        ("fetch", "--profile", "adprov-v1", "--allow-networ"),  # abbreviations are errors
        ("fetch", "--profile", "adprov-v1", "--no-such-option"),
    ],
)
def test_usage_errors_exit_2(cli, argv):
    assert cli(*argv, "--dry-run").code == 2


def test_an_unknown_profile_is_a_usage_error(cli, cache):
    run = cli("fetch", "--profile", "no-such-profile", "--dry-run", "--cache-dir", str(cache))
    assert run.code == 2 and "no profile" in run.err


def test_an_unknown_pin_role_is_a_usage_error(cli, cache):
    run = cli("fetch", "--profile", "adprov-v1", "--pin", "nonesuch", "--dry-run", "--cache-dir", str(cache))
    assert run.code == 2 and "nonesuch" in run.err


# ---------------------------------------------------------------------------------------------------- network refusal


def test_without_allow_network_the_command_exits_4_and_does_nothing(cli, cache, check_summary):
    run = cli("fetch", "--profile", "adprov-v1", "--cache-dir", str(cache), "--json")
    assert run.code == 4
    summary = run.json()
    check_summary(summary)
    assert summary["outcome"] == "refused" and "--allow-network" in run.err
    assert not cache.exists()


def test_the_references_mode_also_needs_allow_network(cli, tmp_path, cache):
    (tmp_path / "corpus" / "raw").mkdir(parents=True)
    run = cli("fetch", "--corpus", str(tmp_path / "corpus"), "--cache-dir", str(cache))
    assert run.code == 4


# ---------------------------------------------------------------------------------------------------- dry run


def test_dry_run_prints_the_plan_for_the_primary_pins_and_writes_nothing(cli, cache, check_summary):
    run = cli("fetch", "--profile", "adprov-v1", "--cache-dir", str(cache), "--dry-run", "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["dry_run"] is True and summary["counters"]["recipes"] == 1  # only the primary pin
    assert "would fetch from github.com" in run.err
    assert not cache.exists()


def test_dry_run_with_a_named_pin(cli, cache):
    run = cli("fetch", "--profile", "adprov-v1", "--pin", "converted-legacy", "--cache-dir", str(cache), "--dry-run")
    assert run.code == 0 and "would fetch" in run.err and "579a908354b9" in run.err


# ---------------------------------------------------------------------------------------------------- acquisition mode


@needs_git
def test_profile_fetch_end_to_end_then_cached(cli, tmp_path, cache, monkeypatch, check_summary):
    local_upstream(tmp_path, monkeypatch, expected_files=4)
    run = cli("fetch", "--profile", "whatever", "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["counters"] == {"bytes_verified": sum(len(FILES[p]) for p in FILES if p.startswith("runs/")) + len("../../etc/passwd"),
                                   "cached": 0, "failed": 0, "files_verified": 4, "fetched": 1, "recipes": 1}  # fmt: skip
    assert "verified by git blob id" in run.err and "1 gitlink(s) not fetched" in run.err
    rows = [json.loads(line) for line in (cache / "acquisitions.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "git" and rows[0]["consent"] == "--allow-network"
    again = cli("fetch", "--profile", "whatever", "--allow-network", "--cache-dir", str(cache), "--json")
    assert again.code == 0 and again.json()["counters"]["cached"] == 1 and again.json()["counters"]["fetched"] == 0
    assert len((cache / "acquisitions.jsonl").read_text().splitlines()) == 1  # nothing new was acquired


@needs_git
def test_a_file_count_that_differs_from_the_profile_exits_1(cli, tmp_path, cache, monkeypatch, check_summary):
    local_upstream(tmp_path, monkeypatch, expected_files=99)
    run = cli("fetch", "--profile", "whatever", "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 1
    summary = run.json()
    check_summary(summary)
    assert summary["issues_by_code"] == {"raw.fetch.expectation": 1} and "expected 99 files" in run.err


@needs_git
def test_path_prefixes_narrow_the_read(cli, tmp_path, cache, monkeypatch):
    local_upstream(tmp_path, monkeypatch)
    run = cli("fetch", "--profile", "whatever", "--path", "runs/b/", "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 0 and run.json()["counters"]["files_verified"] == 1


@needs_git
def test_a_failure_for_one_recipe_is_reported_with_its_code_and_exit(cli, tmp_path, cache, monkeypatch, check_summary):
    local_upstream(tmp_path, monkeypatch, commit="9" * 40)  # a commit the remote does not have
    run = cli("fetch", "--profile", "whatever", "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 1
    summary = run.json()
    check_summary(summary)
    assert summary["failures"][0]["code"] == "raw.fetch.git" and summary["counters"]["failed"] == 1


def test_a_cache_inside_a_repository_exits_3(cli, tmp_path):
    (tmp_path / "work" / ".git").mkdir(parents=True)
    run = cli("fetch", "--profile", "adprov-v1", "--dry-run", "--cache-dir", str(tmp_path / "work" / "cache"))
    assert run.code == 3


def test_a_cache_inside_a_sealed_corpus_or_the_fetched_corpus_exits_4(cli, tmp_path, monkeypatch):
    """CC-8: the fetch cache is written by every fetch, so it may not lie inside a sealed corpus (G1), nor inside the
    corpus whose references are fetched (N.2.2: the corpus is never written; G2). Refused before a fetcher exists."""
    import agentprov.cli.fetch as fetch_cmd

    def no_fetcher(*args, **kwargs):
        raise AssertionError("a fetcher was built")

    monkeypatch.setattr(fetch_cmd, "Fetcher", no_fetcher)
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "corpus.json").write_text('{"sealed": true}')
    for mode in ("--dry-run", "--allow-network"):
        run = cli("fetch", "--profile", "adprov-v1", mode, "--cache-dir", str(sealed / "cache"))
        assert run.code == 4 and not (sealed / "cache").exists()
    (tmp_path / "corpus" / "raw").mkdir(parents=True)
    run = cli("fetch", "--corpus", str(tmp_path / "corpus"), "--allow-network", "--cache-dir", str(tmp_path / "corpus" / "c"))
    assert run.code == 4 and not (tmp_path / "corpus" / "c").exists()


# ---------------------------------------------------------------------------------------------------- references mode


def corpus_with(tmp_path: Path, objects: list[dict[str, Any]], *, extra: dict[str, Any] | None = None) -> Path:
    root = tmp_path / "corpus"
    (root / "raw").mkdir(parents=True)
    doc = {"format": "agentprov-raw-references/0.1", "objects": objects, **(extra or {})}
    (root / "raw" / "REFERENCES.json").write_text(json.dumps(doc))
    return root


def reference_for(up: Any, path: str, *, digest: str | None = None, **changes: Any) -> dict[str, Any]:
    data = FILES[path]
    return {
        "sha256": "sha256:" + (digest or sha256(data)), "bytes": len(data), "reason": "licence-unclear", "requires": ["network"],
        "origins": [{"kind": "git", "repo": REPO_URL, "commit": up.commit, "path": path, "blob_sha1": up.blob_ids[path]}],
        **changes,
    }  # fmt: skip


def tree_state(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@needs_git
def test_references_resolve_against_pins_fetch_and_verify_without_writing_the_corpus(cli, tmp_path, cache, monkeypatch, check_summary):
    up = local_upstream(tmp_path, monkeypatch)
    corpus = corpus_with(tmp_path, [reference_for(up, "runs/a/one.json"), reference_for(up, "runs/b/three.json")])
    before = tree_state(corpus)
    run = cli("fetch", "--corpus", str(corpus), "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["counters"] == {"failed": 0, "references": 2, "unpinned": 0, "unverified": 0, "verified": 2}
    assert tree_state(corpus) == before


@needs_git
def test_only_selects_one_object(cli, tmp_path, cache, monkeypatch):
    up = local_upstream(tmp_path, monkeypatch)
    corpus = corpus_with(tmp_path, [reference_for(up, "runs/a/one.json"), reference_for(up, "runs/b/three.json")])
    run = cli("fetch", "--corpus", str(corpus), "--only", "sha256:" + sha256(FILES["runs/b/three.json"]), "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 0 and run.json()["counters"]["references"] == 1
    missing = cli("fetch", "--corpus", str(corpus), "--only", "sha256:" + "0" * 64, "--allow-network", "--cache-dir", str(cache))
    assert missing.code == 2


@needs_git
def test_an_origin_that_matches_no_in_package_pin_is_never_contacted(cli, tmp_path, cache, monkeypatch, check_summary):
    up = local_upstream(tmp_path, monkeypatch)
    foreign = reference_for(up, "runs/a/one.json")
    foreign["origins"][0]["repo"] = "https://evil.invalid/acme/runs"  # not a pinned repository
    other_commit = reference_for(up, "runs/a/two.json")
    other_commit["origins"][0]["commit"] = up.later_commit  # a commit no pin names
    outside = reference_for(up, "other/skip.txt")  # inside the repo and commit but outside the pin's runs/ prefix
    corpus = corpus_with(tmp_path, [foreign, other_commit, outside])
    run = cli("fetch", "--corpus", str(corpus), "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 1
    summary = run.json()
    check_summary(summary)
    assert summary["counters"]["unpinned"] == 3 and summary["counters"]["verified"] == 0
    assert summary["issues_by_code"] == {"raw.reference.unpinned_origin": 3}
    assert not cache.exists()  # nothing was contacted or created


@needs_git
def test_a_wrong_digest_gives_raw_reference_digest(cli, tmp_path, cache, monkeypatch, check_summary):
    up = local_upstream(tmp_path, monkeypatch)
    corpus = corpus_with(tmp_path, [reference_for(up, "runs/a/one.json", digest="0" * 64)])
    run = cli("fetch", "--corpus", str(corpus), "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 1
    summary = run.json()
    check_summary(summary)
    assert summary["failures"][0]["code"] == "raw.reference.digest"
    assert "agentprov fetch --corpus" in run.err  # the hint is generated at display time


@needs_git
def test_gated_references_are_reported_unverified_and_never_attempted(cli, tmp_path, cache, monkeypatch):
    up = local_upstream(tmp_path, monkeypatch)
    gated = reference_for(up, "runs/a/one.json", requires=["network", "hf-gate-acceptance"], reason="gated")
    corpus = corpus_with(tmp_path, [gated])
    run = cli("fetch", "--corpus", str(corpus), "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 1 and run.json()["counters"]["unverified"] == 1 and "never accepts" in " ".join(run.json()["notices"])
    assert not cache.exists()


def test_references_that_store_instructions_are_refused_as_malformed(cli, tmp_path, cache):
    corpus = corpus_with(tmp_path, [], extra={"fetch": {"instructions": "run this command"}})
    run = cli("fetch", "--corpus", str(corpus), "--allow-network", "--cache-dir", str(cache))
    assert run.code == 2 and "no instructions or commands" in run.err


def test_a_corpus_without_references_is_a_usage_error(cli, tmp_path, cache):
    (tmp_path / "corpus" / "raw").mkdir(parents=True)
    assert cli("fetch", "--corpus", str(tmp_path / "corpus"), "--allow-network", "--cache-dir", str(cache)).code == 2


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_a_symlinked_references_file_is_not_followed(cli, tmp_path, cache):
    root = tmp_path / "corpus"
    (root / "raw").mkdir(parents=True)
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps({"format": "agentprov-raw-references/0.1", "objects": []}))
    (root / "raw" / "REFERENCES.json").symlink_to(real)
    run = cli("fetch", "--corpus", str(root), "--allow-network", "--cache-dir", str(cache))
    assert run.code == 2 and "cannot be read safely" in run.err


@needs_git
def test_dry_run_in_references_mode_resolves_without_fetching(cli, tmp_path, cache, monkeypatch):
    up = local_upstream(tmp_path, monkeypatch)
    corpus = corpus_with(tmp_path, [reference_for(up, "runs/a/one.json")])
    run = cli("fetch", "--corpus", str(corpus), "--dry-run", "--cache-dir", str(cache), "--json")
    assert run.code == 0 and "would fetch" in run.err and not cache.exists()
