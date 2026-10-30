"""``agentprov.raw.fetch``: recipes, the verified git cache, the HTTPS downloader and the acquisitions log (G.7.5; MN N.1.11).

All git work uses a local repository fetched through ``file://`` with the Fetcher's test seam; all HTTP work uses a fake
transport. A guard makes any socket use fail the test, so no test can reach the network.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fetch_support import FILES, GITLINK_SHA, REPO_URL, SYMLINK_TARGET, FakeTransport, git, make_upstream, needs_git, sha256

from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.raw import fetch as fetch_mod
from agentprov.raw.fetch import (
    ACQUISITIONS_NAME,
    AbsentBlobError,
    BlobMismatchError,
    DigestMismatchError,
    FetchEnvironmentError,
    FetchError,
    Fetcher,
    LargeDownloadRefusedError,
    NetworkRefusedError,
    NotCachedError,
    RedirectRefusedError,
    Recipe,
    SafeRedirectHandler,
    TreeEntry,
    check_git_version,
    parse_ls_tree,
    recipes_from_source,
    resolve_cache_dir,
)
from agentprov.raw.origins import OriginLog, OriginUnpinnedError
from agentprov.raw.store import RawObjectStore

NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any socket use in these tests is a bug: fail loudly instead of reaching the network."""

    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("a test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ---------------------------------------------------------------------------------------------------- recipes


def test_a_git_pin_becomes_a_recipe_with_the_profile_defaults():
    pin = {"role": "head", "kind": "git", "commit": "a" * 40, "tree": "runs/", "expected_files": 3, "expected_bytes": 9,
           "date": "2026-06-02", "note": "ignored", "primary": True}  # fmt: skip
    recipe = Recipe.from_pin(pin, canonical_repo="https://github.com/ethz-spylab/agentdojo")
    assert (recipe.kind, recipe.repo, recipe.commit, recipe.paths) == ("git", "https://github.com/ethz-spylab/agentdojo", "a" * 40, ("runs/",))
    assert (recipe.expected_files, recipe.expected_bytes, recipe.role) == (3, 9, "head")
    assert Recipe.from_pin(pin, canonical_repo="https://github.com/o/r", paths=["x/", "y"]).paths == ("x/", "y")


def test_a_pin_repo_overrides_the_canonical_repo():
    recipe = Recipe.from_pin({"kind": "git", "repo": "https://github.com/a/b", "commit": "b" * 40}, canonical_repo="https://github.com/c/d")
    assert recipe.repo == "https://github.com/a/b" and recipe.paths == ()


@pytest.mark.parametrize("commit", ["main", "v1.0", "", "HEAD", "abc1234", "A" * 40, "a" * 39, "a" * 41, None])
def test_git_commits_must_be_full_lower_case_hex(commit):
    with pytest.raises(OriginUnpinnedError) as err:
        Recipe(kind="git", repo=REPO_URL, commit=commit)
    assert err.value.exit_code == 3 and err.value.code == "raw.origin.unpinned"


@pytest.mark.parametrize(
    "repo",
    [
        "http://github.com/a/b", "ssh://git@github.com/a/b", "git@github.com:a/b.git", "file:///tmp/x", "/tmp/x",
        "https://user:pw@github.com/a/b", "https://github.com:8443/a/b", "https://github.com/a/b?x=1", "https://github.com/a/b#f",
        "https://github.com/a", "https://github.com/a/b/c", "https://github.com/-a/b", "https://github.com/a/b c",
        "https://github.com/../b", "", None,
        # Hugging Face: only datasets, exactly /datasets/<owner>/<name> (D.16.18 item 13)
        "https://huggingface.co/datasets/o", "https://huggingface.co/datasets/o/n/x", "https://huggingface.co/spaces/o/n",
        "https://huggingface.co/models/o/n", "https://huggingface.co/datasets/../n", "https://huggingface.co/datasets/-o/n",
        "https://huggingface.co/Datasets/o/n", "http://huggingface.co/datasets/o/n", "https://huggingface.co/datasets//n",
        # a two-part path whose owner is a namespace name would share the dataset cache directory
        "https://huggingface.co/datasets/n", "https://huggingface.co/Datasets/n", "https://huggingface.co/spaces/n",
    ],
)  # fmt: skip
def test_git_repository_urls_have_one_safe_shape(repo):
    with pytest.raises(FetchError):
        Recipe(kind="git", repo=repo, commit="a" * 40)


@pytest.mark.parametrize("path", ["/abs", "../up", "a/../b", "a//b", "-flag", "a\\b", "a\nb", "a\x00b", "", "./x"])
def test_path_prefixes_are_plain_relative_paths(path):
    with pytest.raises(FetchError):
        Recipe(kind="git", repo=REPO_URL, commit="a" * 40, paths=(path,))


HF_REPO = "https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories"


@pytest.mark.parametrize("repo", [HF_REPO, HF_REPO + ".git", HF_REPO + "/", "https://HuggingFace.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories"])
def test_a_hugging_face_dataset_repository_is_a_git_pin_with_its_own_cache_namespace(tmp_path, repo):
    recipe = Recipe(kind="git", repo=repo, commit="c" * 40)
    assert recipe.host == "huggingface.co" and "huggingface.co" in recipe.allowed_hosts
    expected = ("huggingface.co", "datasets", "AI-Secure")
    assert recipe.cache_path(tmp_path) == tmp_path.joinpath("git", *expected, "DTap-Bench-Agent-Trajectories.git")
    fetcher = Fetcher(tmp_path)
    assert fetcher.history_store(recipe) == tmp_path.joinpath("git-history", *expected, "DTap-Bench-Agent-Trajectories.git")
    assert fetcher.history_index_path(recipe) == tmp_path.joinpath(
        "git-history", *expected, "DTap-Bench-Agent-Trajectories.index", f"{'c' * 40}.jsonl"
    )


def test_a_hugging_face_model_path_keeps_the_generic_shape_and_cannot_meet_a_dataset(tmp_path):
    model = Recipe(kind="git", repo="https://huggingface.co/acme/runs", commit="c" * 40)
    dataset = Recipe(kind="git", repo="https://huggingface.co/datasets/acme/runs", commit="c" * 40)
    assert model.cache_path(tmp_path) == tmp_path / "git" / "huggingface.co" / "acme" / "runs.git"
    assert dataset.cache_path(tmp_path) == tmp_path / "git" / "huggingface.co" / "datasets" / "acme" / "runs.git"
    # the generic shape on other hosts is unchanged, including an owner called "datasets"
    other = Recipe(kind="git", repo="https://github.com/datasets/runs", commit="c" * 40)
    assert other.cache_path(tmp_path) == tmp_path / "git" / "github.com" / "datasets" / "runs.git"


def test_the_shipped_dtap_profile_pins_are_git_recipes():
    from agentprov.adapters.profiles import load_profile

    source = load_profile("dtap-bench").data["source"]
    recipes, _skipped = recipes_from_source(source)
    git_recipes = {r.role: r for r in recipes if r.kind == "git"}
    assert {r.repo for r in git_recipes.values()} == {
        HF_REPO, "https://huggingface.co/datasets/AI-Secure/DecodingTrust-Agent-Platform",
    }  # fmt: skip
    assert all(r.host == "huggingface.co" for r in git_recipes.values())


def test_path_prefixes_may_end_in_a_slash():
    assert Recipe(kind="git", repo=REPO_URL, commit="a" * 40, paths=("runs/", "a/b.json")).paths == ("runs/", "a/b.json")


ZENODO = {"kind": "zenodo", "doi": "10.5281/zenodo.12528189", "file": "agentdojo-v0.1.7.zip", "sha256": "a" * 64, "md5": "b" * 32, "bytes": 5}


def test_a_zenodo_pin_builds_the_download_url_and_cache_path(tmp_path):
    recipe = Recipe.from_pin(ZENODO)
    assert recipe.download_url == "https://zenodo.org/records/12528189/files/agentdojo-v0.1.7.zip?download=1"
    assert recipe.cache_path(tmp_path) == tmp_path / "zenodo" / "12528189" / "agentdojo-v0.1.7.zip"
    assert recipe.host == "zenodo.org" and "zenodo.org" in recipe.allowed_hosts


@pytest.mark.parametrize(
    "changes",
    [
        {"doi": "10.1234/other"}, {"doi": "10.5281/zenodo.abc"}, {"doi": None}, {"file": None}, {"file": "../x.zip"},
        {"sha256": "z" * 64}, {"md5": "short"}, {"sha256": None, "md5": None}, {"bytes": -1}, {"bytes": True},
    ],
)  # fmt: skip
def test_download_recipes_need_a_clean_doi_file_and_a_digest(changes):
    with pytest.raises(FetchError):
        Recipe.from_pin({**ZENODO, **changes})


@pytest.mark.parametrize(
    "file",
    ["../x.zip", "a/../b.zip", "a/./b.zip", "./a.zip", "/abs.zip", "a//b.zip", "dir/", "", "a\\b.zip", "a\x00b.zip",
     "a\nb.zip", "-x.zip"],
)  # fmt: skip
def test_a_zenodo_file_key_with_slashes_is_a_clean_relative_path(file):
    """D-530 item 4: a key may hold '/', but never '..', '.', an empty segment, a leading '/' or '-', a trailing '/', a
    backslash or a control character (NUL included)."""
    with pytest.raises(FetchError):
        Recipe.from_pin({**ZENODO, "file": file})


def test_a_zenodo_file_key_with_slashes_builds_a_segment_encoded_url_and_a_nested_cache_path(tmp_path):
    recipe = Recipe.from_pin({**ZENODO, "file": "owner/repo-v1.0.zip"})
    assert recipe.download_url == "https://zenodo.org/records/12528189/files/owner/repo-v1.0.zip?download=1"
    assert recipe.cache_path(tmp_path) == tmp_path / "zenodo" / "12528189" / "owner" / "repo-v1.0.zip"
    odd = Recipe.from_pin({**ZENODO, "file": "a b/c#d?%.zip"})  # each segment percent-encoded; the separators kept
    assert odd.download_url == "https://zenodo.org/records/12528189/files/a%20b/c%23d%3F%25.zip?download=1"


def test_the_agentops_zip_key_builds_a_recipe_and_verifies_by_its_last_segment():
    """The pin that found the gap: AgentOps-Bench's code snapshot on Zenodo 19875693, key
    ``kunwarshivam/agentops-bench-v1.0.zip`` (a GitHub-integration snapshot)."""
    import io

    from agentprov.raw.fetch import verify_download

    pin = {"kind": "zenodo", "doi": "10.5281/zenodo.19875693", "file": "kunwarshivam/agentops-bench-v1.0.zip",
           "sha256": "852a372da1d797adc5a60a95ea8f5194d8b652d4d5c19738eab152f7a57c1fed",
           "md5": "71ad345da90595fe85456d0a9a1e47f2", "size": 2449857}  # fmt: skip
    recipe = Recipe.from_pin(pin)
    assert recipe.file == "kunwarshivam/agentops-bench-v1.0.zip"
    assert recipe.download_url == "https://zenodo.org/records/19875693/files/kunwarshivam/agentops-bench-v1.0.zip?download=1"
    body = b"not the pinned bytes"
    small = Recipe.from_pin({**pin, "sha256": sha256(body), "md5": None, "size": len(body)})
    assert verify_download(io.BytesIO(body), "agentops-bench-v1.0.zip", small)[0] == sha256(body)
    with pytest.raises(FetchError):
        verify_download(io.BytesIO(body), "other.zip", small)


def test_a_url_recipe_needs_a_sha256_pin_and_https():
    ok = Recipe.from_pin({"kind": "url", "url": "https://example.invalid/data.json", "sha256": "c" * 64})
    assert ok.cache_path(Path("/c")) == Path("/c/url/" + "c" * 64)
    for bad in ({"url": "http://example.invalid/x"}, {"url": "https://u:p@example.invalid/x"}, {"sha256": None, "md5": "d" * 32}):
        with pytest.raises(FetchError):
            Recipe.from_pin({"kind": "url", "url": "https://example.invalid/data.json", "sha256": "c" * 64, **bad})


def test_an_hf_recipe_needs_a_pinned_revision():
    pin = {"kind": "hf", "dataset": "owner/name", "revision": "e" * 40, "file": "data/x.json", "sha256": "f" * 64}
    recipe = Recipe.from_pin(pin)
    assert recipe.download_url == f"https://huggingface.co/datasets/owner/name/resolve/{'e' * 40}/data/x.json"
    assert "cdn-lfs.huggingface.co" in recipe.allowed_hosts
    assert "us.aws.cdn.hf.co" in recipe.allowed_hosts  # D-831
    with pytest.raises(OriginUnpinnedError):
        Recipe.from_pin({**pin, "revision": "main"})


def test_token_settings_must_be_well_formed():
    pin = {**ZENODO, "token_env": "ZENODO_TOKEN", "token_host": "zenodo.org"}
    assert Recipe.from_pin(pin).token_env == "ZENODO_TOKEN"
    for bad in ({"token_env": "lower"}, {"token_env": "X Y"}, {"token_host": None}):
        with pytest.raises(FetchError):
            Recipe.from_pin({**pin, **bad})


def test_profile_sources_give_recipes_and_report_the_pins_that_are_not_fetchable():
    source = {
        "canonical_repo": "https://github.com/ethz-spylab/agentdojo",
        "pins": [
            {"role": "head", "kind": "git", "commit": "a" * 40, "tree": "runs/"},
            {"role": "zenodo_head", "kind": "zenodo", "doi": "10.5281/zenodo.17458493"},
            {"role": "note", "kind": "other"},
        ],
    }
    recipes, skipped = recipes_from_source(source)
    assert [r.role for r in recipes] == ["head"]
    assert [role for role, _ in skipped] == ["zenodo_head"]


def test_an_unpinned_git_pin_in_a_profile_is_loud():
    with pytest.raises(OriginUnpinnedError):
        recipes_from_source({"canonical_repo": REPO_URL, "pins": [{"role": "x", "kind": "git", "commit": "main"}]})


def test_the_shipped_adprov_profile_yields_its_two_git_recipes():
    from agentprov.adapters.profiles import load_profile

    profile = load_profile("adprov-v1")
    recipes, skipped = recipes_from_source(profile.data["source"])
    assert [r.role for r in recipes] == ["release", "converted-legacy"] and skipped == []
    assert all(r.commit == "579a908354b93361efe0905ffb7623256aa96a06" for r in recipes)
    assert [r.expected_files for r in recipes] == [17664, 18027]


# ---------------------------------------------------------------------------------------------------- cache directory


def test_cache_dir_precedence(tmp_path):
    env = {"AGENTPROV_UPSTREAM_CACHE": str(tmp_path / "up"), "AGENTPROV_HOME": str(tmp_path / "home")}
    assert resolve_cache_dir(tmp_path / "explicit", env) == tmp_path / "explicit"
    assert resolve_cache_dir(None, env) == tmp_path / "up"
    assert resolve_cache_dir(None, {"AGENTPROV_HOME": str(tmp_path / "home")}) == tmp_path / "home" / "cache"
    assert resolve_cache_dir(None, {}) == Path.home().absolute() / ".agentprov" / "cache"


def test_cache_dir_inside_a_repository_is_refused(tmp_path):
    (tmp_path / "work" / ".git").mkdir(parents=True)
    with pytest.raises(FetchEnvironmentError) as err:
        resolve_cache_dir(tmp_path / "work" / "cache", {})
    assert err.value.exit_code == 3


# ---------------------------------------------------------------------------------------------------- parsing helpers


def test_ls_tree_output_is_parsed_and_sorted_bytewise():
    out = b"100644 blob " + b"a" * 40 + b"       3\tz.json\0" + b"160000 commit " + b"b" * 40 + b"       -\tsub\0" + b"120000 blob " + b"c" * 40 + b"      5\ta b.json\0"
    entries, skipped = parse_ls_tree(out)
    assert [e.path for e in entries] == ["a b.json", "sub", "z.json"] and skipped == 0
    assert entries[1].is_gitlink and not entries[1].is_blob and entries[1].size is None
    assert entries[0].is_symlink and entries[0].is_blob and entries[2].size == 3


def test_ls_tree_skips_undecodable_paths_and_rejects_garbage():
    entries, skipped = parse_ls_tree(b"100644 blob " + b"a" * 40 + b"       3\tbad\xff.json\0")
    assert entries == [] and skipped == 1
    for garbage in (b"nonsense\0", b"100644 blob xyz       3\tp\0", b"100644 blob " + b"a" * 40 + b" 3 no tab\0"):
        with pytest.raises(FetchError):
            parse_ls_tree(garbage)


def test_ls_tree_refuses_absent_blobs_with_a_typed_code_and_names_them():
    """``git ls-tree -l`` prints ``BAD`` as the size of a blob a partial clone lacks (routing R2): a typed refusal, never a
    ``ValueError`` from ``int("BAD")``, and never a half-read tree."""
    out = (b"100644 blob " + b"a" * 40 + b"       3\tok.json\0" + b"100644 blob " + b"b" * 40 + b"     BAD\tz.json\0"
           + b"100644 blob " + b"c" * 40 + b"     BAD\tbad\xff.json\0")  # fmt: skip
    with pytest.raises(AbsentBlobError) as err:
        parse_ls_tree(out)
    assert err.value.code == "raw.fetch.blob_absent" and isinstance(err.value, FetchError)
    assert err.value.paths == ("bad\\xff.json", "z.json") and "2 object(s)" in str(err.value)
    assert "z.json" not in str(err.value)  # paths are labels for the caller, not message text


@pytest.mark.parametrize("size", [b"bad", b"-1", b"3.0", b"\xd9\xa3", b"1" * 20, b"0x10"])
def test_ls_tree_rejects_a_size_that_is_not_a_decimal_count(size):
    with pytest.raises(FetchError) as err:
        parse_ls_tree(b"100644 blob " + b"a" * 40 + b" " + size + b"\tp.json\0")
    assert err.value.code == "raw.fetch.git" and not isinstance(err.value, AbsentBlobError)


def test_every_git_call_of_the_fetcher_refuses_lazy_fetch(tmp_path):
    assert Fetcher(tmp_path)._git_env()["GIT_NO_LAZY_FETCH"] == "1"
    assert Fetcher(tmp_path, env={"GIT_NO_LAZY_FETCH": "0", "PATH": os.environ.get("PATH", "")})._git_env()["GIT_NO_LAZY_FETCH"] == "1"


@pytest.mark.parametrize(("text", "ok"), [("git version 2.54.0 (Apple Git-157)", True), ("git version 2.50.1", True), ("git version 2.50.0", False),
                                          ("git version 2.40.1", False), ("git version 3.0.0", True), ("garbage", False)])  # fmt: skip
def test_git_version_floor(text, ok):
    if ok:
        assert check_git_version(text)[0] >= 2
    else:
        with pytest.raises(FetchEnvironmentError):
            check_git_version(text)


def test_an_old_git_executable_is_refused(tmp_path):
    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\necho 'git version 2.40.0'\n")
    fake.chmod(0o755)
    fetcher = Fetcher(tmp_path / "cache", allow_network=True, git=str(fake))
    with pytest.raises(FetchEnvironmentError):
        fetcher.fetch(Recipe(kind="git", repo=REPO_URL, commit="a" * 40))


# ---------------------------------------------------------------------------------------------------- git: network policy


@needs_git
def test_a_git_fetch_without_allow_network_is_refused_before_anything_happens(tmp_path):
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    fetcher = up.fetcher(cache)  # allow_network defaults to False
    with pytest.raises(NetworkRefusedError) as err:
        fetcher.fetch(up.recipe())
    assert err.value.exit_code == 4 and "--allow-network" in str(err.value)
    assert not cache.exists()


@needs_git
def test_plan_has_no_side_effects_and_says_whether_the_network_is_needed(tmp_path):
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    plan = up.fetcher(cache).plan(up.recipe())
    assert (plan.cached, plan.needs_network, plan.host) == (False, True, "example.invalid")
    assert plan.target == cache / "git" / "example.invalid" / "acme" / "runs.git" and not cache.exists()
    up.fetcher(cache, allow_network=True).fetch(up.recipe())
    again = up.fetcher(cache).plan(up.recipe())
    assert (again.cached, again.needs_network) == (True, False)


# ---------------------------------------------------------------------------------------------------- git: fetch and read


@needs_git
def test_fetch_creates_a_bare_cache_with_no_working_tree_and_logs_the_acquisition(tmp_path):
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    fetcher = up.fetcher(cache, allow_network=True, consent="--allow-network", now=lambda: NOW)
    result = fetcher.fetch(up.recipe(expected_files=4))
    bare = cache / "git" / "example.invalid" / "acme" / "runs.git"
    assert result.path == bare and result.network_used and (bare / "objects").is_dir() and (bare / "HEAD").is_file()
    # extraction-free: nothing but the bare repository exists in the cache, and no checkout of any file
    on_disk = {p.name for p in cache.rglob("*") if p.is_file()}
    assert not on_disk & {"one.json", "two.json", "three.json", "README.md", "skip.txt", "link.json"}
    assert not (cache / ".git").exists() and not (bare / ".git").exists()
    # runs/ holds 3 json blobs + the symlink blob in the first commit (the gitlink is not a file)
    assert (result.files, result.gitlinks) == (4, 1)
    assert result.tree == git(up.path, "rev-parse", f"{up.commit}^{{tree}}")
    assert result.problems == ()
    (row,) = fetcher.log.rows()
    assert row["kind"] == "git" and row["repo"] == REPO_URL and row["commit"] == up.commit and row["tree"] == result.tree
    assert row["retrieved_at"] == "2026-10-08T12:00:00Z" and row["consent"] == "--allow-network" and row["files"] == 4
    assert (cache / ACQUISITIONS_NAME).read_bytes().endswith(b"\n")


@needs_git
def test_a_hugging_face_dataset_pin_is_fetched_from_a_local_bare_repository(tmp_path):
    up = make_upstream(tmp_path)
    bare = tmp_path / "upstream-bare.git"
    git(tmp_path, "clone", "-q", "--bare", str(up.path), str(bare))
    cache = tmp_path / "cache"
    recipe = up.recipe(repo=HF_REPO)
    fetcher = Fetcher(cache, allow_network=True, remote_urls={HF_REPO: bare.as_uri()}, file_protocol=True)
    result = fetcher.fetch(recipe)
    target = cache / "git" / "huggingface.co" / "datasets" / "AI-Secure" / "DTap-Bench-Agent-Trajectories.git"
    assert result.path == target and (target / "objects").is_dir() and result.network_used
    assert result.tree == git(up.path, "rev-parse", f"{up.commit}^{{tree}}") and result.problems == ()
    blobs = {b.entry.path: b.data for b in fetcher.iter_git_blobs(recipe)}
    assert {k: v for k, v in blobs.items() if k.endswith(".json") and k != "runs/link.json"} == {
        k: v for k, v in FILES.items() if k.startswith("runs/")
    }
    (row,) = fetcher.log.rows()
    assert row["repo"] == HF_REPO and row["commit"] == up.commit
    # cached: the second fetch needs no network
    assert not Fetcher(cache, remote_urls={HF_REPO: bare.as_uri()}, file_protocol=True).fetch(recipe).network_used


def _partial_clone(up, tmp_path: Path, *, bare: bool) -> Path:
    """A ``blob:none`` clone of the upstream (its promisor remote is the upstream, through the file protocol)."""
    git(up.path, "config", "uploadpack.allowFilter", "true")
    dest = tmp_path / ("partial.git" if bare else "partial")
    git(tmp_path, "-c", "protocol.file.allow=always", "clone", "-q", "--filter=blob:none", "--no-checkout",
        *(["--bare"] if bare else []), up.url, str(dest))  # fmt: skip
    return dest


def _has_blob(repo: Path, oid: str) -> bool:
    import subprocess

    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", oid], env=env, capture_output=True).returncode == 0


@needs_git
def test_seeding_from_a_partial_clone_never_fetches_its_absent_blobs_from_upstream(tmp_path, monkeypatch):
    """Routing R2: the partial clone's upload-pack must not lazily fetch the blobs it lacks from its promisor remote (on a
    real clone that is GitHub: network use without consent). The fetch fails with a typed code and the clone gains nothing.
    """
    up = make_upstream(tmp_path)
    partial = _partial_clone(up, tmp_path, bare=False)
    oid = up.blob_ids["runs/a/one.json"]
    assert not _has_blob(partial, oid)
    fetcher = Fetcher(tmp_path / "cache", allow_network=True, remote_urls={REPO_URL: partial.as_uri()}, file_protocol=True)
    with pytest.raises(FetchError) as err:
        fetcher.fetch(up.recipe())
    assert err.value.code in ("raw.fetch.git", "raw.fetch.blob_absent")
    assert not _has_blob(partial, oid), "the partial clone fetched an absent blob from its promisor remote"
    assert fetcher.log.rows() == []


@needs_git
def test_the_lazy_fetch_guard_is_what_keeps_the_partial_clone_from_its_upstream(tmp_path, monkeypatch):
    """Control for the test above. git >= 2.45.1 already disables lazy fetching inside ``upload-pack``, but only by default:
    ``GIT_NO_LAZY_FETCH=0`` turns it back on, and then the same seeding does reach the promisor remote. The Fetcher pins 1."""
    up = make_upstream(tmp_path)
    partial = _partial_clone(up, tmp_path, bare=False)
    oid = up.blob_ids["runs/a/one.json"]
    monkeypatch.setattr(fetch_mod, "_GIT_ENV", {**fetch_mod._GIT_ENV, "GIT_NO_LAZY_FETCH": "0"})
    fetcher = Fetcher(tmp_path / "cache", allow_network=True, remote_urls={REPO_URL: partial.as_uri()}, file_protocol=True)
    fetcher.fetch(up.recipe())
    assert _has_blob(partial, oid)


@needs_git
def test_a_cached_store_with_absent_blobs_is_refused_with_a_typed_code_and_stays_offline(tmp_path):
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    store = up.recipe().cache_path(cache)
    store.parent.mkdir(parents=True)
    _partial_clone(up, tmp_path, bare=True).rename(store)
    fetcher = Fetcher(cache)  # no network; the store's promisor remote is the upstream
    # as a fetch would have recorded it (ultra raw-withhold #7: a cached commit without its row is not cached)
    fetcher.log.append({"kind": "git", "repo": REPO_URL, "commit": up.commit, "store": str(store.relative_to(cache))})
    assert fetcher.plan(up.recipe()).cached
    with pytest.raises(AbsentBlobError) as err:
        fetcher.git_tree(up.recipe())
    assert set(err.value.paths) == {"runs/a/one.json", "runs/a/two.json", "runs/b/three.json", "runs/link.json"}
    assert not _has_blob(store, up.blob_ids["runs/a/one.json"])


@needs_git
def test_without_the_guard_reading_a_partial_store_fetches_from_its_upstream(tmp_path, monkeypatch):
    """Control for the test above, and the defect it fixes: before, the depth-1 store's reads ran without
    ``GIT_NO_LAZY_FETCH`` (only the history store had it), so ``ls-tree -l`` on a store with a promisor remote lazily
    fetched every blob it sized from that remote; upload-pack's default does not apply to local reads."""
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    store = up.recipe().cache_path(cache)
    store.parent.mkdir(parents=True)
    _partial_clone(up, tmp_path, bare=True).rename(store)
    monkeypatch.setattr(fetch_mod, "_GIT_ENV", {k: v for k, v in fetch_mod._GIT_ENV.items() if k != "GIT_NO_LAZY_FETCH"})
    monkeypatch.delenv("GIT_NO_LAZY_FETCH", raising=False)
    entries, _ = Fetcher(cache, file_protocol=True).git_tree(up.recipe())
    assert len(entries) == 5 and _has_blob(store, up.blob_ids["runs/a/one.json"])


@needs_git
def test_a_second_fetch_uses_the_cache_without_the_network_and_logs_nothing(tmp_path):
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    up.fetcher(cache, allow_network=True).fetch(up.recipe())
    offline = up.fetcher(cache)
    result = offline.fetch(up.recipe())
    assert not result.network_used and result.verified == "cached"
    assert len(offline.log.rows()) == 1


@needs_git
def test_expectations_of_the_profile_are_reported_not_hidden(tmp_path):
    up = make_upstream(tmp_path)
    result = up.fetcher(tmp_path / "c", allow_network=True).fetch(up.recipe(expected_files=99, expected_bytes=1))
    assert len(result.problems) == 2 and "expected 99 files" in result.problems[0]


@needs_git
def test_every_blob_is_read_with_its_sha1_recomputed_and_symlinks_are_data(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    recipe = up.recipe()
    fetcher.fetch(recipe)
    blobs = {b.entry.path: b for b in fetcher.iter_git_blobs(recipe)}
    assert sorted(blobs) == ["runs/a/one.json", "runs/a/two.json", "runs/b/three.json", "runs/link.json"]  # no gitlink
    for path in ("runs/a/one.json", "runs/a/two.json", "runs/b/three.json"):
        assert blobs[path].data == FILES[path] and blobs[path].sha256 == sha256(FILES[path])
        assert blobs[path].entry.oid == up.blob_ids[path]
    link = blobs["runs/link.json"]
    assert link.entry.is_symlink and link.data == SYMLINK_TARGET.encode()  # the target text, never resolved


@needs_git
def test_the_gitlink_is_listed_and_not_fetched(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    fetcher.fetch(up.recipe())
    entries, _ = fetcher.git_tree(up.recipe())
    (sub,) = [e for e in entries if e.path == "runs/sub"]
    assert sub.is_gitlink and sub.oid == GITLINK_SHA
    assert all(b.entry.path != "runs/sub" for b in fetcher.iter_git_blobs(up.recipe()))


@needs_git
def test_paths_select_a_subtree_and_the_whole_tree_is_the_default(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    fetcher.fetch(up.recipe())
    assert [e.path for e in fetcher.git_tree(up.recipe(paths=("runs/b/",)))[0]] == ["runs/b/three.json"]
    assert len(fetcher.git_tree(up.recipe(paths=()))[0]) == len(FILES) + 2  # + symlink + gitlink
    assert [e.path for e in fetcher.git_tree(up.recipe(paths=("runs/a/one.json",)))[0]] == ["runs/a/one.json"]


@needs_git
def test_reading_an_uncached_commit_never_uses_the_network(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    with pytest.raises(NotCachedError):
        fetcher.git_tree(up.recipe())
    with pytest.raises(NotCachedError):
        list(fetcher.iter_git_blobs(up.recipe(), [TreeEntry("100644", "blob", "a" * 40, 1, "x")]))


@needs_git
def test_a_commit_the_remote_does_not_have_fails_without_a_cache_entry(tmp_path):
    up = make_upstream(tmp_path)
    cache = tmp_path / "c"
    with pytest.raises(FetchError) as err:
        up.fetcher(cache, allow_network=True).fetch(up.recipe(commit="9" * 40))
    assert err.value.code == "raw.fetch.git"
    assert not up.fetcher(cache).plan(up.recipe(commit="9" * 40)).cached


@needs_git
def test_a_tampered_blob_is_caught_by_the_sha1_check(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    recipe = up.recipe()
    result = fetcher.fetch(recipe)
    victim = up.blob_ids["runs/a/one.json"]
    loose = result.path / "objects" / victim[:2] / victim[2:]
    if not loose.is_file():  # a shallow fetch keeps a pack: unpack it so the object is a file we can swap
        import subprocess

        for pack in sorted((result.path / "objects" / "pack").glob("*.pack")):
            data = pack.read_bytes()
            for done in (pack.with_suffix(".idx"), pack):
                done.chmod(0o644)  # git writes packs read-only; Windows cannot unlink a read-only file
                done.unlink()
            subprocess.run(["git", "-C", str(result.path), "unpack-objects", "-q"], input=data, check=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull})
    assert loose.is_file()
    import zlib

    loose.chmod(0o644)
    loose.write_bytes(zlib.compress(b"blob 4\0evil"))  # a different, perfectly valid blob under the same name
    with pytest.raises(BlobMismatchError) as err:
        list(fetcher.iter_git_blobs(recipe))
    assert err.value.code == "raw.fetch.blob_sha1"


@needs_git
def test_a_wrong_tree_entry_size_is_caught(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    recipe = up.recipe()
    fetcher.fetch(recipe)
    entry = next(e for e in fetcher.git_tree(recipe)[0] if e.path == "runs/a/one.json")
    with pytest.raises(BlobMismatchError):
        list(fetcher.iter_git_blobs(recipe, [TreeEntry(entry.mode, entry.type, entry.oid, 999, entry.path)]))


@needs_git
def test_oversized_blobs_are_refused(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True, limits=IngestLimits().replace(max_artefact_bytes=3))
    recipe = up.recipe()
    fetcher.fetch(recipe)
    with pytest.raises(FetchError) as err:
        list(fetcher.iter_git_blobs(recipe))
    assert err.value.code == "ingest.size.file"


@needs_git
def test_blobs_go_into_the_raw_store_with_git_origins(tmp_path):
    up = make_upstream(tmp_path)
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    recipe = up.recipe()
    fetcher.fetch(recipe)
    store = RawObjectStore(tmp_path / "raw")
    origins = OriginLog()
    stored = fetcher.store_git(recipe, store, origins)
    assert [s.path for s in stored] == ["runs/a/one.json", "runs/a/two.json", "runs/b/three.json", "runs/link.json"]
    assert all(s.created for s in stored) and all(store.has(s.sha256) for s in stored)
    one = next(s for s in stored if s.path == "runs/a/one.json")
    assert one.sha256 == sha256(FILES["runs/a/one.json"]) and store.read_bytes(one.sha256) == FILES["runs/a/one.json"]
    (origin,) = origins.origins_of(one.sha256)
    assert origin.to_json() == {"kind": "git", "repo": REPO_URL, "commit": up.commit, "path": "runs/a/one.json", "blob_sha1": up.blob_ids["runs/a/one.json"]}
    assert not any(s.created for s in fetcher.store_git(recipe, store, origins))  # idempotent
    assert len(origins) == 4


@needs_git
def test_the_git_argv_is_hardened_and_the_environment_is_scrubbed(tmp_path):
    fetcher = Fetcher(tmp_path, env={"PATH": "/usr/bin", "HOME": "/home/me", "ZENODO_TOKEN": "secret", "GIT_DIR": "/elsewhere"})
    args = fetcher._hardening()
    assert f"core.hooksPath={os.devnull}" in args and "protocol.file.allow=never" in args and "transfer.fsckObjects=true" in args
    assert "core.symlinks=false" in args and "protocol.ext.allow=never" in args
    # https only (no downgrade to http, git:// or ssh) and no redirect to another host (CB-25)
    assert "protocol.allow=never" in args and "protocol.https.allow=always" in args and "http.followRedirects=false" in args
    assert "protocol.file.allow=always" in Fetcher(tmp_path, file_protocol=True)._hardening()  # the test seam only
    env = fetcher._git_env()
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert "ZENODO_TOKEN" not in env and "HOME" not in env and "GIT_DIR" not in env


# ---------------------------------------------------------------------------------------------------- https downloads

BODY = b"zip bytes " * 10
URL = "https://zenodo.org/records/12528189/files/agentdojo-v0.1.7.zip?download=1"


def zenodo_recipe(**changes: object) -> Recipe:
    pin = {**ZENODO, "sha256": sha256(BODY), "md5": __import__("hashlib").md5(BODY, usedforsecurity=False).hexdigest(), "bytes": len(BODY)}
    pin.update(changes)
    return Recipe.from_pin(pin)


def test_a_download_without_allow_network_is_refused_and_the_transport_is_never_used(tmp_path):
    transport = FakeTransport({URL: BODY})
    with pytest.raises(NetworkRefusedError) as err:
        Fetcher(tmp_path / "c", transport=transport).fetch(zenodo_recipe())
    assert err.value.exit_code == 4 and transport.calls == []
    assert not (tmp_path / "c").exists()


def _purged(cache: Path, digest: str) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "tombstones.jsonl").write_text(f'{{"date":"2026-10-12","reason":"secret","sha256":"sha256:{digest}"}}\n')


def test_a_purged_pinned_download_is_refused_before_the_network(tmp_path):
    """G.9.6 / D-46 / D-61: ``purge --cache`` leaves a tombstone; the same pin is never downloaded again."""
    transport = FakeTransport({URL: BODY})
    cache = tmp_path / "c"
    _purged(cache, sha256(BODY))
    with pytest.raises(fetch_mod.TombstonedDownloadError) as err:
        Fetcher(cache, allow_network=True, transport=transport).fetch(zenodo_recipe())
    assert err.value.code == "raw.fetch.tombstoned" and transport.calls == []


def test_a_purged_md5_only_download_is_not_kept(tmp_path):
    transport = FakeTransport({URL: BODY})
    cache = tmp_path / "c"
    _purged(cache, sha256(BODY))
    with pytest.raises(fetch_mod.TombstonedDownloadError):
        Fetcher(cache, allow_network=True, transport=transport).fetch(zenodo_recipe(sha256=None))
    assert not (cache / "zenodo" / "12528189").exists() or list((cache / "zenodo" / "12528189").iterdir()) == []


@pytest.mark.parametrize("pinned", [True, False])
def test_a_purge_that_lands_before_the_fetch_takes_the_lock_is_honoured(tmp_path, pinned):
    """Ultra raw-withhold #8: the tombstones are read again under the fetch-cache write lock, so a ``purge --cache`` that
    finishes between the first read and the lock is not undone by downloading the purged file again (D-46)."""
    transport = FakeTransport({URL: BODY})
    cache = tmp_path / "c"
    cache.mkdir()
    fetcher = Fetcher(cache, allow_network=True, transport=transport)
    taken = fetcher._write_lock

    def purge_then_lock():
        _purged(cache, sha256(BODY))  # the concurrent purge's locked apply, just before this fetch gets the lock
        return taken()

    fetcher._write_lock = purge_then_lock  # type: ignore[method-assign]
    with pytest.raises(fetch_mod.TombstonedDownloadError) as err:
        fetcher.fetch(zenodo_recipe() if pinned else zenodo_recipe(sha256=None))
    # a pinned digest is refused before the network; an MD5-only one is known only once downloaded, and is not kept
    assert err.value.code == "raw.fetch.tombstoned" and len(transport.calls) == (0 if pinned else 1)
    assert not (cache / "zenodo" / "12528189" / "agentdojo-v0.1.7.zip").exists()
    assert not (cache / ACQUISITIONS_NAME).exists()


def test_a_download_is_verified_stored_read_only_and_logged(tmp_path):
    transport = FakeTransport({URL: BODY})
    cache = tmp_path / "c"
    fetcher = Fetcher(cache, allow_network=True, transport=transport, consent="--allow-network", now=lambda: NOW)
    result = fetcher.fetch(zenodo_recipe())
    target = cache / "zenodo" / "12528189" / "agentdojo-v0.1.7.zip"
    assert result.path == target and target.read_bytes() == BODY and result.network_used
    assert (result.sha256, result.bytes, result.verified) == (sha256(BODY), len(BODY), "size+md5+sha256")
    assert stat.S_IMODE(target.stat().st_mode) == 0o444
    assert [p.name for p in target.parent.iterdir()] == [target.name]  # no .part file left
    (call,) = transport.calls
    assert call.url == URL and call.allowed_hosts == {"zenodo.org"} and call.unredirected == {} and call.timeout == 60.0
    assert transport.responses[0].closed
    (row,) = fetcher.log.rows()
    assert set(row) >= {"bytes", "consent", "doi", "file", "kind", "md5", "md5_published", "record", "retrieved_at", "sha256", "url", "verified"}
    assert row["record"] == "zenodo/12528189/agentdojo-v0.1.7.zip" and row["kind"] == "zenodo" and row["retrieved_at"] == "2026-10-08T12:00:00Z"


def test_a_cached_download_needs_no_network_and_is_rechecked(tmp_path):
    cache = tmp_path / "c"
    Fetcher(cache, allow_network=True, transport=FakeTransport({URL: BODY})).fetch(zenodo_recipe())
    transport = FakeTransport({})
    offline = Fetcher(cache, transport=transport)
    result = offline.fetch(zenodo_recipe())
    assert not result.network_used and transport.calls == [] and len(offline.log.rows()) == 1
    target = cache / "zenodo" / "12528189" / "agentdojo-v0.1.7.zip"
    target.chmod(0o644)
    target.write_bytes(b"corrupted")
    with pytest.raises(DigestMismatchError):
        offline.fetch(zenodo_recipe())
    assert target.read_bytes() == b"corrupted"  # never overwritten behind the caller's back


@pytest.mark.parametrize("what", ["sha256", "md5", "bytes"])
def test_a_download_that_does_not_match_its_pin_stores_nothing(tmp_path, what):
    bad = {"sha256": "0" * 64, "md5": "0" * 32, "bytes": len(BODY) + 1}[what]
    cache = tmp_path / "c"
    fetcher = Fetcher(cache, allow_network=True, transport=FakeTransport({URL: BODY}))
    with pytest.raises(DigestMismatchError) as err:
        fetcher.fetch(zenodo_recipe(**{what if what != "bytes" else "bytes": bad}))
    assert err.value.code == "raw.fetch.digest"
    assert not [p for p in cache.rglob("*") if p.is_file()]
    assert fetcher.log.rows() == []


def test_an_oversized_body_is_cut_off(tmp_path):
    fetcher = Fetcher(tmp_path / "c", allow_network=True, transport=FakeTransport({URL: BODY * 5}))
    with pytest.raises(FetchError) as err:
        fetcher.fetch(zenodo_recipe())  # the recipe says len(BODY) bytes
    assert err.value.code == "ingest.size.file"
    assert not [p for p in (tmp_path / "c").rglob("*") if p.is_file()]


def test_an_announced_size_over_the_cap_is_refused_before_reading(tmp_path):
    transport = FakeTransport({URL: (BODY, 200, {"Content-Length": "99999999999"})})
    with pytest.raises(FetchError) as err:
        Fetcher(tmp_path / "c", allow_network=True, transport=transport).fetch(zenodo_recipe())
    assert err.value.code == "ingest.size.file"
    assert transport.responses[0]._pos == 0


@pytest.mark.parametrize("status", [403, 404, 500])
def test_http_errors_leave_nothing_behind(tmp_path, status):
    fetcher = Fetcher(tmp_path / "c", allow_network=True, transport=FakeTransport({URL: (b"nope", status, {})}))
    with pytest.raises(FetchError) as err:
        fetcher.fetch(zenodo_recipe())
    assert err.value.code == "raw.fetch.http_status"
    assert not [p for p in (tmp_path / "c").rglob("*") if p.is_file()]


def test_a_large_download_needs_the_explicit_consent_of_u07(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod, "LARGE_DOWNLOAD_BYTES", 5)
    transport = FakeTransport({URL: BODY})
    with pytest.raises(LargeDownloadRefusedError) as err:
        Fetcher(tmp_path / "c", allow_network=True, transport=transport).fetch(zenodo_recipe())
    assert err.value.exit_code == 4 and "agentdojo-v0.1.7.zip" in str(err.value) and "zenodo.org" in str(err.value)
    assert transport.calls == []
    result = Fetcher(tmp_path / "c", allow_network=True, large_download_consent=True, transport=transport).fetch(zenodo_recipe())
    assert result.network_used


def test_a_large_announced_length_without_a_declared_size_is_also_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod, "LARGE_DOWNLOAD_BYTES", 5)
    transport = FakeTransport({URL: (BODY, 200, {"Content-Length": str(len(BODY))})})
    with pytest.raises(LargeDownloadRefusedError):
        Fetcher(tmp_path / "c", allow_network=True, transport=transport).fetch(zenodo_recipe(bytes=None))
    assert not [p for p in (tmp_path / "c").rglob("*") if p.is_file()]


def test_an_unsized_download_without_an_announced_length_is_refused_once_it_is_large(tmp_path, monkeypatch):
    """U-07 / D-249: with no pinned size and no Content-Length, the stream itself is measured against the threshold."""
    monkeypatch.setattr(fetch_mod, "LARGE_DOWNLOAD_BYTES", 5)
    transport = FakeTransport({URL: (BODY, 200, {})})
    fetcher = Fetcher(tmp_path / "c", allow_network=True, transport=transport)
    with pytest.raises(LargeDownloadRefusedError) as err:
        fetcher.fetch(zenodo_recipe(bytes=None))
    assert err.value.code == "raw.fetch.consent_required" and err.value.exit_code == 4
    assert not [p for p in (tmp_path / "c").rglob("*") if p.is_file()] and fetcher.log.rows() == []
    assert transport.responses[0].closed
    consented = Fetcher(tmp_path / "c", allow_network=True, large_download_consent=True, transport=FakeTransport({URL: (BODY, 200, {})}))
    assert consented.fetch(zenodo_recipe(bytes=None)).bytes == len(BODY)


def test_an_unsized_download_below_the_threshold_needs_no_consent(tmp_path):
    result = Fetcher(tmp_path / "c", allow_network=True, transport=FakeTransport({URL: (BODY, 200, {})})).fetch(zenodo_recipe(bytes=None))
    assert result.network_used and result.bytes == len(BODY)


def test_plan_flags_a_large_download(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod, "LARGE_DOWNLOAD_BYTES", 5)
    plan = Fetcher(tmp_path / "c").plan(zenodo_recipe())
    assert plan.large and plan.needs_network and not plan.cached and plan.expected_bytes == len(BODY)


def test_plan_flags_an_unsized_download_as_large(tmp_path):
    """As for a split part (D-249), a download pin with no size may need U-07 consent, so the plan says so."""
    plan = Fetcher(tmp_path / "c").plan(zenodo_recipe(bytes=None))
    assert plan.large and plan.expected_bytes is None


def test_an_unpinned_sha256_is_flagged_for_the_profile(tmp_path):
    result = Fetcher(tmp_path / "c", allow_network=True, transport=FakeTransport({URL: BODY})).fetch(zenodo_recipe(sha256=None))
    assert result.verified == "size+md5" and "no sha256 is pinned" in result.problems[0]


def test_a_token_is_sent_unredirected_to_its_host_only_and_never_stored(tmp_path):
    transport = FakeTransport({URL: BODY})
    recipe = zenodo_recipe(token_env="ZENODO_TOKEN", token_host="zenodo.org")
    fetcher = Fetcher(tmp_path / "c", allow_network=True, transport=transport, env={"ZENODO_TOKEN": "s3cret-value"})
    fetcher.fetch(recipe)
    (call,) = transport.calls
    assert call.unredirected == {"Authorization": "Bearer s3cret-value"} and "Authorization" not in call.headers
    text = (tmp_path / "c" / ACQUISITIONS_NAME).read_text()
    assert "s3cret-value" not in text
    # a token declared for another host is never sent
    other = FakeTransport({URL: BODY})
    elsewhere = zenodo_recipe(token_env="ZENODO_TOKEN", token_host="other.example")
    Fetcher(tmp_path / "d", allow_network=True, transport=other, env={"ZENODO_TOKEN": "s3cret-value"}).fetch(elsewhere)
    assert other.calls[0].unredirected == {}


def test_acquisition_rows_never_carry_credentials(tmp_path):
    from agentprov.raw.fetch import AcquisitionLog

    log = AcquisitionLog(tmp_path / "a.jsonl")
    for key in ("token", "Authorization", "password"):
        with pytest.raises(FetchError):
            log.append({"kind": "x", key: "v"})
    log.append({"kind": "x", "b": 1, "a": 2})
    assert (tmp_path / "a.jsonl").read_bytes() == b'{"a":2,"b":1,"kind":"x"}\n'  # JCS: sorted, compact


@pytest.mark.parametrize("damage", [b'{"kind":"zen', b"\xff\xfe\n", b'{"a":1,"a":2}\n'])
def test_a_torn_or_corrupt_acquisitions_line_is_a_typed_fetch_error(tmp_path, damage):
    """Ultra raw-withhold #9: the log is read through the bounded strict loader; a torn line (an append cut short) or a
    corrupt one is ``raw.fetch.log``, never a bare ``JSONDecodeError`` from every cached download."""
    cache = tmp_path / "c"
    Fetcher(cache, allow_network=True, transport=FakeTransport({URL: BODY})).fetch(zenodo_recipe())
    with (cache / ACQUISITIONS_NAME).open("ab") as log:
        log.write(damage)
    offline = Fetcher(cache)
    with pytest.raises(FetchError) as err:
        offline.log.rows()
    assert err.value.code == "raw.fetch.log" and err.value.exit_code == 1
    with pytest.raises(FetchError) as err:
        offline.fetch(zenodo_recipe())  # a cached download reads the log for its retrieval time
    assert err.value.code == "raw.fetch.log"


def test_the_acquisitions_log_is_append_only(tmp_path):
    up_cache = tmp_path / "c"
    f1 = Fetcher(up_cache, allow_network=True, transport=FakeTransport({URL: BODY}))
    f1.fetch(zenodo_recipe())
    first = (up_cache / ACQUISITIONS_NAME).read_bytes()
    f2 = Fetcher(up_cache, allow_network=True, transport=FakeTransport({"https://example.invalid/d.json": b"{}"}))
    f2.fetch(Recipe.from_pin({"kind": "url", "url": "https://example.invalid/d.json", "sha256": sha256(b"{}")}))
    assert (up_cache / ACQUISITIONS_NAME).read_bytes().startswith(first) and len(f2.log.rows()) == 2


# ---------------------------------------------------------------------------------------------------- redirects


def _redirect(handler: SafeRedirectHandler, url: str, new: str, headers: dict[str, str] | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    return handler.redirect_request(req, None, 302, "Found", {}, new)


def test_redirects_must_stay_on_https_and_the_allow_list():
    handler = SafeRedirectHandler(frozenset({"zenodo.org", "cdn.zenodo.org"}))
    with pytest.raises(RedirectRefusedError):
        _redirect(handler, "https://zenodo.org/a", "http://zenodo.org/b")  # downgrade
    with pytest.raises(RedirectRefusedError):
        _redirect(handler, "https://zenodo.org/a", "https://evil.example/b")  # unlisted host
    with pytest.raises(RedirectRefusedError):
        _redirect(handler, "https://zenodo.org/a", "https://user:pw@zenodo.org/b")  # credentials in the URL
    with pytest.raises(RedirectRefusedError):
        _redirect(handler, "https://zenodo.org/a", "ftp://zenodo.org/b")
    ok = _redirect(handler, "https://zenodo.org/a", "https://cdn.zenodo.org/b")
    assert ok is not None and ok.full_url == "https://cdn.zenodo.org/b"


def test_credentials_are_dropped_on_any_host_change_and_kept_on_the_same_host():
    handler = SafeRedirectHandler(frozenset({"zenodo.org", "cdn.zenodo.org"}))
    headers = {"Authorization": "Bearer x", "Cookie": "c=1", "Proxy-Authorization": "p", "User-Agent": "ua"}
    moved = _redirect(handler, "https://zenodo.org/a", "https://cdn.zenodo.org/b", headers)
    assert moved is not None and {k.lower() for k in moved.headers} == {"user-agent"}
    same = _redirect(handler, "https://zenodo.org/a", "https://zenodo.org/b", headers)
    assert same is not None and "authorization" in {k.lower() for k in same.headers}


def test_unredirected_headers_are_not_copied_by_urllib():
    req = urllib.request.Request("https://zenodo.org/a")
    req.add_unredirected_header("Authorization", "Bearer x")
    new = SafeRedirectHandler(frozenset({"zenodo.org"})).redirect_request(req, None, 302, "Found", {}, "https://zenodo.org/b")
    assert new is not None and not new.unredirected_hdrs


def test_the_production_transport_is_not_built_unless_a_download_needs_it(tmp_path):
    fetcher = Fetcher(tmp_path / "c")
    assert fetcher._transport is None
    with pytest.raises(NetworkRefusedError):
        fetcher.fetch(zenodo_recipe())
    assert fetcher._transport is None


def test_errors_are_agentprov_errors_with_stable_codes():
    codes = {
        fetch_mod.FetchError: ("raw.fetch.error", 1), NetworkRefusedError: ("raw.fetch.network_refused", 4),
        LargeDownloadRefusedError: ("raw.fetch.consent_required", 4), FetchEnvironmentError: ("raw.fetch.environment", 3),
        NotCachedError: ("raw.fetch.not_cached", 1), DigestMismatchError: ("raw.fetch.digest", 1),
        BlobMismatchError: ("raw.fetch.blob_sha1", 1), RedirectRefusedError: ("raw.fetch.redirect", 1),
    }  # fmt: skip
    for cls, (code, exit_code) in codes.items():
        assert issubclass(cls, AgentProvError) and (cls.code, cls.exit_code) == (code, exit_code)
    assert json.dumps(sorted(c[0] for c in codes.values()))


# ---------------------------------------------------------------------------------------------------- the row and the cache
def _enospc(self: object, row: object) -> None:
    raise OSError(28, "No space left on device")


def test_a_download_whose_acquisitions_row_fails_publishes_nothing_and_the_next_fetch_records_it(tmp_path, monkeypatch):
    """Ultra raw-withhold #7: the row is appended before the file is published, so a failed append leaves no cached file
    that every later run would take as recorded (a url pin then had no ``retrieved_at`` for good)."""
    cache = tmp_path / "c"
    target = cache / "zenodo" / "12528189" / "agentdojo-v0.1.7.zip"
    original = fetch_mod.AcquisitionLog.append
    monkeypatch.setattr(fetch_mod.AcquisitionLog, "append", _enospc)
    with pytest.raises(OSError):
        Fetcher(cache, allow_network=True, transport=FakeTransport({URL: BODY})).fetch(zenodo_recipe())
    assert not target.exists() and list(target.parent.iterdir()) == []  # no published file, no .part file
    monkeypatch.setattr(fetch_mod.AcquisitionLog, "append", original)
    result = Fetcher(cache, allow_network=True, transport=FakeTransport({URL: BODY}), now=lambda: NOW).fetch(zenodo_recipe())
    assert result.network_used and target.read_bytes() == BODY
    (row,) = Fetcher(cache).log.rows()
    assert row["sha256"] == sha256(BODY) and row["record"] == "zenodo/12528189/agentdojo-v0.1.7.zip"
    assert Fetcher(cache).recorded_retrieval(target, sha256(BODY)) == "2026-10-08T12:00:00Z"


def test_an_unwritable_acquisitions_log_is_a_typed_refusal_that_publishes_nothing(tmp_path):
    cache = tmp_path / "c"
    (cache / ACQUISITIONS_NAME).mkdir(parents=True)  # os.open of the log fails (EISDIR), as a 0644 log of another user would
    with pytest.raises(FetchError) as err:
        Fetcher(cache, allow_network=True, transport=FakeTransport({URL: BODY})).fetch(zenodo_recipe())
    assert err.value.code == "raw.fetch.log" and err.value.exit_code == 1
    assert not (cache / "zenodo" / "12528189" / "agentdojo-v0.1.7.zip").exists()


@needs_git
def test_a_cached_commit_whose_acquisitions_row_was_lost_is_fetched_again_and_recorded(tmp_path, monkeypatch):
    """Ultra raw-withhold #7, git site: a fetched commit cannot be unpublished from the bare store, so a commit that has no
    acquisitions row counts as not cached: an offline fetch refuses, and a fetch with the network records the row."""
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    original = fetch_mod.AcquisitionLog.append
    monkeypatch.setattr(fetch_mod.AcquisitionLog, "append", _enospc)
    with pytest.raises(OSError):
        up.fetcher(cache, allow_network=True).fetch(up.recipe())
    monkeypatch.setattr(fetch_mod.AcquisitionLog, "append", original)
    plan = up.fetcher(cache).plan(up.recipe())
    assert not plan.cached and plan.needs_network
    with pytest.raises(NetworkRefusedError):
        up.fetcher(cache).fetch(up.recipe())
    result = up.fetcher(cache, allow_network=True, now=lambda: NOW).fetch(up.recipe())
    assert result.network_used
    (row,) = up.fetcher(cache).log.rows()
    assert row["commit"] == up.commit and row["retrieved_at"] == "2026-10-08T12:00:00Z"
    again = up.fetcher(cache).fetch(up.recipe())  # recorded now: offline from the cache, nothing new logged
    assert not again.network_used and len(up.fetcher(cache).log.rows()) == 1


@needs_git
def test_an_acquisitions_row_with_an_absolute_store_under_the_cache_still_counts(tmp_path):
    """Pre-round verification V-1: rows written on 2026-10-08 record the bare store as an absolute path. The
    raw-withhold #7 check compared the cache-relative path only, so those commits (the agentdojo-upstream and inspect
    pins) counted as not cached and an offline ``import --fetch`` was refused. An absolute store that resolves to the
    same bare store under the cache root counts; one outside the cache root never does (fail closed)."""
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    up.fetcher(cache, allow_network=True).fetch(up.recipe())
    log = cache / ACQUISITIONS_NAME
    (row,) = [json.loads(line) for line in log.read_text().splitlines()]
    store = up.recipe().cache_path(cache)
    log.write_text(json.dumps({**row, "store": str(store.resolve())}) + "\n")  # as the 2026-10-08 rows are
    assert up.fetcher(cache).plan(up.recipe()).cached  # before: not cached, and offline fetch refused
    assert not up.fetcher(cache).fetch(up.recipe()).network_used
    outside = tmp_path / "elsewhere" / store.name  # the same bare-store name, outside the cache root
    log.write_text(json.dumps({**row, "store": str(outside)}) + "\n")
    assert not up.fetcher(cache).plan(up.recipe()).cached
    log.write_text(json.dumps({**row, "store": str(store.parent)}) + "\n")  # inside the cache, but not this store
    assert not up.fetcher(cache).plan(up.recipe()).cached
