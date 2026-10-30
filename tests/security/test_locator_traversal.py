"""SEC-08 (K.12.4): locators resolve only inside the digest-checked artefact, and every failure is a typed error.

A locator is AER data, and AER read back from a corpus or a downloaded deposit is untrusted (G.1.3). Path-like
strings in it are labels or JSON Pointer tokens, never filesystem paths; numbers in it are bounded before use.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest
from aer_support import ARTEFACT_BYTES, MemoryStore, example_records, example_store, make_registry

from agentprov.aer.locators import LocatorError, LocatorResolver, pointer_exists, pointer_get, resolve
from agentprov.aer.validate import validate_records

HEADER = example_records()[0]
HUGE = "9" * 5000  # beyond CPython's 4,300-digit int() limit


def _resolve(loc: dict[str, Any], store: MemoryStore | None = None) -> Any:
    return resolve(loc, header=HEADER, store=store or example_store())


# ------------------------------------------------------------------------------------------- pointer forms
@pytest.mark.parametrize(
    "pointer",
    ["/..", "/../..", "/messages/../meta", "/etc/passwd", "../../x", "messages/0", "//", "/messages/-1", "/messages/+1",
     "/messages/1e3", "/messages/ 1", "/messages/\u0661", "/messages/" + HUGE, "/messages/0" + HUGE],
)
def test_sec08_path_like_pointers_are_member_names_and_fail_typed(pointer: str) -> None:
    with pytest.raises(LocatorError) as exc:
        _resolve({"a": "a0", "p": pointer})
    assert exc.value.code == "aer.locator.dangling"


def test_sec08_a_huge_array_index_is_out_of_range_not_an_untyped_error() -> None:
    """Regression: ``int()`` of a 4,301+ digit token raised ``ValueError`` and escaped every caller."""
    assert not pointer_exists([1, 2], "/" + HUGE)
    with pytest.raises(KeyError):
        pointer_get({"a": [0]}, "/a/" + HUGE)
    with pytest.raises(LocatorError):
        _resolve({"a": "a0", "o": "/x/" + HUGE})
    # the longest index that can still be valid is accepted
    assert pointer_get(list(range(10)), "/9") == 9 and not pointer_exists(list(range(10)), "/10")


def test_sec08_the_validator_survives_a_hostile_unk_pointer_into_a_list() -> None:
    """Regression: the tier-2 validator crashed on ``unk`` keys such as ``/rule/99...9`` (an AER from a deposit)."""
    records = copy.deepcopy(example_records())
    target = next(i for i, r in enumerate(records) if r["k"] != "execution" and isinstance(r.get("rule"), list))
    records[target]["unk"] = dict(records[target].get("unk") or {}, **{f"/rule/{HUGE}": "not_recorded"})
    report = validate_records(records, store=example_store(), catalogues=make_registry(), mode="release")
    assert report.findings, "a pointer that does not exist must be reported"


def test_sec08_invalid_tilde_escapes_never_reach_beyond_existing_members() -> None:
    # RFC 6901 forbids "~2"; the reader treats it as a literal member name, so it can only name a member that exists
    assert pointer_get({"~2": 1}, "/~2") == 1
    with pytest.raises(LocatorError):
        _resolve({"a": "a0", "p": "/~2"})


# ------------------------------------------------------------------------------------------- numeric forms
@pytest.mark.parametrize(
    "bad", [True, False, -1, 10**30, int(HUGE[:400]), 1.0, "0", None, [0], {"n": 0}]
)
def test_sec08_line_numbers_are_bounded_and_typed(bad: object) -> None:
    with pytest.raises(LocatorError):
        _resolve({"a": "a0", "line": bad})


@pytest.mark.parametrize(
    "bad",
    [[True, 5], [0, True], [0, 10**30], [-(10**30), 4], [0, 1.5], [0, len(ARTEFACT_BYTES) + 1], [3, 3], [5, 2], [0, 1, 2],
     [], "0-5", None],
)
def test_sec08_byte_ranges_are_inside_the_artefact(bad: object) -> None:
    with pytest.raises(LocatorError):
        _resolve({"a": "a0", "bytes": bad})


@pytest.mark.parametrize(
    "loc",
    [{"a": "../a0"}, {"a": "/etc/passwd"}, {"a": "a0/../a0", "p": ""}, {"a": 0}, {"a": None}, {"a": ["a0"]},
     {"blob": "sha256:../../" + "0" * 58}, {"blob": "sha256:" + "A" * 64}, {"blob": "/etc/passwd"}, {"blob": None},
     {"a": "a0", "p": 5}, {"a": "a0", "o": None}],
)
def test_sec08_artefact_and_blob_names_are_labels_never_paths(loc: dict[str, Any], tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda path, *a, **k: opened.append(str(path)) or real_open(path, *a, **k))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(LocatorError):
        _resolve(loc)
    assert opened == [] and list(tmp_path.iterdir()) == []


def test_sec08_resolution_reads_only_the_store_by_digest() -> None:
    reads: list[str] = []

    class Spy(MemoryStore):
        def read_bytes(self, sha256: str) -> bytes:
            reads.append(sha256)
            return super().read_bytes(sha256)

    store = Spy(example_store().objects)
    header = json.loads(json.dumps(HEADER))
    header["artifacts"][0]["origin"] = {"kind": "local", "path": "../../../etc/passwd"}
    resolver = LocatorResolver(header, store)
    assert resolver.resolve({"a": "a0", "o": "/path"}) == "../../../etc/passwd"  # origin fields are returned as data
    assert reads == []
    resolver.resolve({"a": "a0", "p": "/meta/k"})
    assert reads == [header["artifacts"][0]["sha256"]]
