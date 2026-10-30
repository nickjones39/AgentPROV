"""Cache provenance of ``--autodojo-cache`` (docs/architecture D.11.3 rule 5; MN-r12): ``agentprov.cli.live.autodojo_cache``.

A synthetic local repository stands in for the fork: the recipe still names the fork's https URL and the commit is the
synthetic repository's own (the module's ``commit`` test seam); the fetcher's ``remote_urls`` and ``file_protocol`` seam
points at the local repository, exactly as ``tests/unit/raw`` does. No test touches the network.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from agentprov.cli.common import CliUsageError
from agentprov.cli.live.autodojo_cache import (
    AUTODOJO_COMMIT,
    AUTODOJO_REPO,
    AutodojoCacheNotCachedError,
    AutodojoCacheUnverifiedError,
    AutodojoCacheUsageError,
    check_variant,
    git_blob_sha1,
    parse_variant,
    validate_cache_shape,
    verify_autodojo_cache,
)
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.fetch import Fetcher
from agentprov.raw.origins import Origin

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}  # fmt: skip


def cache_bytes(**changes: object) -> bytes:
    """A valid cache document (two tasks, three vectors; variant lists of length 3, 2 and 1)."""
    document: dict[str, object] = {
        "optimiser": "synthetic",
        "injection_tasks": {
            "injection_task_0": {
                "v_a": {"variants": ["a0", "a1", "a2"], "original": "goal a"},
                "v_b": {"variants": ["b0", "b1"]},
            },
            "injection_task_1": {"v_a": {"variants": ["c0"], "original": "goal c"}},
        },
    }
    document.update(changes)
    return json.dumps(document, sort_keys=True).encode()


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env={**os.environ, **_ENV})
    return done.stdout.strip()


@dataclass
class Fork:
    path: Path
    commit: str

    def fetcher(self, cache: Path, *, allow_network: bool) -> Fetcher:
        return Fetcher(cache, allow_network=allow_network, remote_urls={AUTODOJO_REPO: f"file://{self.path}"}, file_protocol=True)

    def verify(self, file: Path, cache: Path, *, allow_network: bool, **kwargs: object):
        return verify_autodojo_cache(
            file, cache_dir=cache, allow_network=allow_network, commit=self.commit,
            fetcher=self.fetcher(cache, allow_network=allow_network), **kwargs,  # type: ignore[arg-type]
        )  # fmt: skip

    def warm(self, cache: Path) -> None:
        """Fill the bare fetch cache the way an earlier ``--allow-network`` run would."""
        from agentprov.raw.fetch import Recipe

        self.fetcher(cache, allow_network=True).fetch(Recipe(kind="git", repo=AUTODOJO_REPO, commit=self.commit))


@pytest.fixture
def fork(tmp_path: Path) -> Fork:
    repo = tmp_path / "fork"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    files = {
        "README.md": b"readme\n",
        "caches/main.json": cache_bytes(),
        "caches/other.json": cache_bytes(optimiser="another"),
        "m/dup.json": cache_bytes(optimiser="twice"),
        "a/dup.json": cache_bytes(optimiser="twice"),
        "Z/dup.json": cache_bytes(optimiser="twice"),
    }
    for rel, data in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(data)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "synthetic fork")
    return Fork(repo, git(repo, "rev-parse", "HEAD"))


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "fetch-cache"


def user_file(tmp_path: Path, data: bytes, name: str = "copied.json") -> Path:
    path = tmp_path / "user" / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------------------------------- the match


def test_a_cached_commit_matches_without_the_network(fork, cache_dir, tmp_path):
    fork.warm(cache_dir)
    data = cache_bytes()
    verified = fork.verify(user_file(tmp_path, data), cache_dir, allow_network=False)
    assert verified.path == "caches/main.json" and verified.matching_paths == ("caches/main.json",)
    assert verified.size == len(data) and verified.blob_sha1 == git_blob_sha1(data)
    assert verified.blob_sha1 == git(fork.path, "rev-parse", f"{fork.commit}:caches/main.json")
    import hashlib

    assert verified.sha256 == hashlib.sha256(data).hexdigest() and verified.data == data
    assert verified.origin == Origin.git(AUTODOJO_REPO, fork.commit, "caches/main.json", verified.blob_sha1)
    assert verified.repo == AUTODOJO_REPO and verified.commit == fork.commit and verified.fetched is False
    assert (verified.shape.tasks, verified.shape.cells, verified.shape.variants) == (2, 3, 6)
    assert (verified.shape.min_variants, verified.shape.max_variants) == (1, 3)


def test_allow_network_fetches_the_commit_once(fork, cache_dir, tmp_path):
    file = user_file(tmp_path, cache_bytes())
    first = fork.verify(file, cache_dir, allow_network=True)
    assert first.fetched is True and first.path == "caches/main.json"
    again = fork.verify(file, cache_dir, allow_network=False)  # now cached: no network needed
    assert again.fetched is False and again.origin == first.origin


def test_default_fetcher_is_built_for_the_cache_and_network_flag(fork, cache_dir, tmp_path):
    fork.warm(cache_dir)  # warm cache: a default fetcher reads it with no network and no seam
    verified = verify_autodojo_cache(user_file(tmp_path, cache_bytes()), cache_dir=cache_dir, allow_network=False, commit=fork.commit)
    assert verified.path == "caches/main.json"


def test_several_paths_with_the_same_blob_give_the_bytewise_smallest(fork, cache_dir, tmp_path):
    fork.warm(cache_dir)
    verified = fork.verify(user_file(tmp_path, cache_bytes(optimiser="twice")), cache_dir, allow_network=False)
    assert verified.matching_paths == ("Z/dup.json", "a/dup.json", "m/dup.json")  # 'Z' < 'a' < 'm' by bytes
    assert verified.path == "Z/dup.json" and verified.origin.data["path"] == "Z/dup.json"


# ---------------------------------------------------------------------------------------------------- refusals (exit 3)


def test_a_file_that_is_not_in_the_pinned_tree_exits_3_and_runs_nothing(fork, cache_dir, tmp_path):
    fork.warm(cache_dir)
    edited = cache_bytes(optimiser="edited by the user")
    with pytest.raises(AutodojoCacheUnverifiedError) as info:
        fork.verify(user_file(tmp_path, edited), cache_dir, allow_network=False)
    assert info.value.exit_code == 3 and info.value.code == "cli.environment.autodojo_cache_blob"
    assert git_blob_sha1(edited) in str(info.value)


def test_a_cache_with_a_trailing_newline_is_a_different_blob(fork, cache_dir, tmp_path):
    fork.warm(cache_dir)
    with pytest.raises(AutodojoCacheUnverifiedError):
        fork.verify(user_file(tmp_path, cache_bytes() + b"\n"), cache_dir, allow_network=False)


def test_an_uncached_commit_without_the_network_is_refused_with_exit_3(fork, cache_dir, tmp_path):
    with pytest.raises(AutodojoCacheNotCachedError) as info:
        fork.verify(user_file(tmp_path, cache_bytes()), cache_dir, allow_network=False)
    assert info.value.exit_code == 3 and info.value.code == "cli.environment.autodojo_cache_commit"
    assert "--allow-network" in str(info.value)
    assert not (cache_dir / "git").exists() and not (cache_dir / "acquisitions.jsonl").exists()  # nothing was fetched


def test_a_commit_the_remote_lacks_is_a_fetch_error_not_a_match(fork, cache_dir, tmp_path):
    with pytest.raises(AgentProvError):
        verify_autodojo_cache(
            user_file(tmp_path, cache_bytes()), cache_dir=cache_dir, allow_network=True, commit="0" * 40,
            fetcher=fork.fetcher(cache_dir, allow_network=True),
        )  # fmt: skip


def test_the_error_classes_are_stable():
    assert AutodojoCacheNotCachedError.exit_code == 3 and AutodojoCacheUnverifiedError.exit_code == 3
    assert AutodojoCacheUsageError.exit_code == 2 and issubclass(AutodojoCacheUsageError, CliUsageError)
    codes = {c.code for c in (AutodojoCacheNotCachedError, AutodojoCacheUnverifiedError, AutodojoCacheUsageError)}
    assert len(codes) == 3


def test_a_mismatched_fetcher_is_a_programming_error(fork, cache_dir, tmp_path):
    with pytest.raises(ValueError):
        verify_autodojo_cache(
            user_file(tmp_path, cache_bytes()), cache_dir=cache_dir / "other", allow_network=False, commit=fork.commit,
            fetcher=fork.fetcher(cache_dir, allow_network=False),
        )  # fmt: skip


# ---------------------------------------------------------------------------------------------------- the file


def test_an_oversized_file_is_refused_before_anything_is_fetched(fork, cache_dir, tmp_path):
    data = cache_bytes()
    limits = IngestLimits(max_json_bytes=len(data) - 1)
    with pytest.raises(AutodojoCacheUsageError) as info:
        fork.verify(user_file(tmp_path, data), cache_dir, allow_network=True, limits=limits)
    assert info.value.exit_code == 2 and "ingest.size.file" in str(info.value)
    assert not (cache_dir / "git").exists()
    ok = fork.verify(user_file(tmp_path, data), cache_dir, allow_network=True, limits=IngestLimits(max_json_bytes=len(data)))
    assert ok.size == len(data)  # exactly at the limit is allowed


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        (b"not json", "ingest.json.syntax"),
        (b'{"injection_tasks": {"t": {"v": {"variants": ["x"]}}}, "injection_tasks": {}}', "ingest.json.duplicate_key"),
        (b"[" * 300 + b"]" * 300, "ingest.json.depth"),
        (b'{"injection_tasks": NaN}', "ingest.number.nonfinite"),
        (b"\xef\xbb\xbf{}", "ingest.json.bom"),
        (b"\xff\xfe", "ingest.json.encoding"),
    ],
)
def test_malformed_json_is_a_usage_error_naming_the_ingest_code(fork, cache_dir, tmp_path, data, fragment):
    with pytest.raises(AutodojoCacheUsageError) as info:
        fork.verify(user_file(tmp_path, data), cache_dir, allow_network=True)
    assert fragment in str(info.value) and info.value.exit_code == 2
    assert not (cache_dir / "git").exists()


def test_a_missing_file_a_directory_and_a_symlink_are_usage_errors(fork, cache_dir, tmp_path):
    real = user_file(tmp_path, cache_bytes())
    link = tmp_path / "user" / "link.json"
    link.symlink_to(real)
    for target in (tmp_path / "user" / "absent.json", tmp_path / "user", link):
        with pytest.raises(AutodojoCacheUsageError):
            fork.verify(target, cache_dir, allow_network=True)


# ---------------------------------------------------------------------------------------------------- shape


GOOD = json.loads(cache_bytes())


@pytest.mark.parametrize(
    "document",
    [
        [],
        {},
        {"injection_tasks": []},
        {"injection_tasks": {}},
        {"injection_tasks": {"t": {}}},
        {"injection_tasks": {"t": []}},
        {"injection_tasks": {"t": {"v": []}}},
        {"injection_tasks": {"t": {"v": {}}}},
        {"injection_tasks": {"t": {"v": {"variants": "x"}}}},
        {"injection_tasks": {"t": {"v": {"variants": ["x", 1]}}}},
        {"injection_tasks": {"t": {"v": {"variants": ["x"], "original": 1}}}},
        {"injection_tasks": {"t": {"v": {"variants": ["x"], "original": None}}}},
        {"injection_tasks": {"": {"v": {"variants": ["x"]}}}},
        {"injection_tasks": {"t": {"": {"variants": ["x"]}}}},
    ],
)
def test_shape_violations_are_usage_errors(document):
    with pytest.raises(AutodojoCacheUsageError) as info:
        validate_cache_shape(document)
    assert info.value.exit_code == 2 and "--autodojo-cache" in str(info.value)


def test_shape_messages_escape_untrusted_identifiers():
    document = {"injection_tasks": {"t\x1b[31mevil": {"v": {"variants": [1]}}}}
    with pytest.raises(AutodojoCacheUsageError) as info:
        validate_cache_shape(document)
    assert "\x1b" not in str(info.value) and "<U+001B>" in str(info.value)


def test_a_valid_shape_tolerates_extra_keys_and_empty_variant_lists():
    shape = validate_cache_shape({"meta": 1, "injection_tasks": {"t": {"v": {"variants": [], "extra": True}}}})
    assert (shape.tasks, shape.cells, shape.variants, shape.min_variants, shape.max_variants) == (1, 1, 0, 0, 0)


def test_shape_failure_is_reported_before_the_git_lookup(fork, cache_dir, tmp_path):
    with pytest.raises(AutodojoCacheUsageError):
        fork.verify(user_file(tmp_path, b'{"injection_tasks": {"t": {"v": {"variants": "x"}}}}'), cache_dir, allow_network=True)
    assert not (cache_dir / "git").exists()


# ---------------------------------------------------------------------------------------------------- the variant


@pytest.mark.parametrize("text", ["", "-1", "+1", " 1", "1 ", "1.0", "0x1", "one", "١", "1" * 10, "1\n"])
def test_variant_text_must_be_plain_ascii_digits(text):
    with pytest.raises(AutodojoCacheUsageError) as info:
        parse_variant(text)
    assert info.value.exit_code == 2


def test_variant_text_parses():
    assert (parse_variant("0"), parse_variant("007"), parse_variant("999999999")) == (0, 7, 999999999)


def test_variant_must_be_servable_and_the_fallback_is_counted():
    shape = validate_cache_shape(GOOD)  # lengths 3, 2, 1
    assert check_variant(0, shape) == 0
    assert check_variant(1, shape) == 1  # only the length-1 cell falls back
    assert check_variant(2, shape) == 2
    for bad in (3, 100):
        with pytest.raises(AutodojoCacheUsageError) as info:
            check_variant(bad, shape)
        assert "falls back" in str(info.value) or "fall back" in str(info.value)
    for bad in (-1, True):
        with pytest.raises(AutodojoCacheUsageError):
            check_variant(bad, shape)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------------- the pin


def test_the_pinned_fork_constants_equal_the_profile_and_the_spec():
    from agentprov.adapters.profiles import load_profile

    (pin,) = load_profile("autodojo-live").data["source"]["pins"]
    assert (pin["repo"], pin["commit"]) == (AUTODOJO_REPO, AUTODOJO_COMMIT)
    assert AUTODOJO_REPO == "https://github.com/xhOwenMa/AutoDojo" and AUTODOJO_COMMIT == "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"


def test_git_blob_sha1_matches_git():
    assert git_blob_sha1(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert git_blob_sha1(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
