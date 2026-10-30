"""K.11.1 fuzzing of the ``dtap.trajectory`` reader (``agentprov.adapters.dtap.dialect``; D.16.1, D.16.2). Reader only:
the mapper is fuzzed by ``tests/adapters/dtap/test_fuzz.py`` (phase 10b), which also fuzzes ``sniff``/``parse`` on short
arbitrary bytes.

* F-1 totality: ``sniff`` never raises; ``parse`` yields exactly one item when ``sniff`` matched and otherwise raises
  ``MalformedArtefact`` or an ``IngestError`` with a G.3.9 code. Seeds are the committed licence-cleared DTap fixtures
  (trajectories of the four harnesses, a judge file, an LFS pointer, a synthetic run), byte-mutated; fixture text is
  never printed (Hypothesis reports draw indices, not values).
* A differential oracle for the D.16.2 sniff table over generated key sets, independent of the reader's code.
* The sniff-then-parse cache: interleaving two inputs never makes ``parse`` return the other input's value.
* The path grammar on hostile labels: ``parse_path``, ``config_path`` and ``file_class`` are total; a label that passes
  the names guard (``ingest.names.logical_name``) gives facets and a configuration path without ``.``/``..`` segments;
  only ASCII digits make a timestamp, re-run or copy class.
* ``state_form`` is total on arbitrary JSON values and hostile strings (lone surrogates, deep or broken brackets) and
  evaluates nothing.
* Discovery: ``iter_artefacts`` and ``auxiliary_for`` are total and deterministic on hostile listings and keep the D.16.8
  rule (a judge file is primary only where its directory holds no trajectory-bearing file).
* F-5 determinism: a fresh reader gives the same results.

Budgets come from ``fuzz_support`` (``AGENTPROV_FUZZ=thorough`` multiplies them for the manual job). ``src/agentprov/
adapters/dtap/`` is not edited by this phase; a defect found here is a finding for the orchestrator.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import sys
from pathlib import Path
from typing import Any

import pytest
from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given
from hypothesis import strategies as st

_DTAP_TESTS = Path(__file__).resolve().parents[1] / "adapters" / "dtap"
if str(_DTAP_TESTS) not in sys.path:
    sys.path.insert(0, str(_DTAP_TESTS))

import dtap_support as support  # noqa: E402

from agentprov.adapters.dtap.dialect import (  # noqa: E402
    FLAG_DEBUG,
    FLAG_JUDGE_ONLY,
    FRAMEWORKS,
    JUDGE_KEYS,
    LFS_HEADER,
    SPLITS,
    THREATS,
    TRAJECTORY_CLASSES,
    TRAJECTORY_KEYS,
    DtapTrajectoryReader,
    config_path,
    file_class,
    parse_path,
    state_form,
)
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, Origin  # noqa: E402
from agentprov.errors import INGEST_CODES, IngestError, MalformedArtefact  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402

LIMITS = IngestLimits()
CLASSES = frozenset({"timestamp", "rerun", "copy", "trajectory", "partial", "judge", "judge_copy", "red_teaming",
                     "other_json", "other"})
STATE_FORMS = frozenset({"object", "array", "text", "json_text", "python_repr", "brace_text", "integer", "number",
                         "boolean", "null", "other"})


def _seeds() -> list[bytes]:
    if not (support.FIXTURES / "SOURCE.json").is_file():
        return []
    return [data for _label, data in sorted(support.runs_files().items())]


SEEDS = _seeds()
needs_fixtures = pytest.mark.skipif(not SEEDS, reason="the committed DTap fixtures are absent")


def _ref(data: bytes) -> ArtefactRef:
    return ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), "application/json", Origin.local("fuzz"))


def _check_total(reader: DtapTrajectoryReader, data: bytes) -> tuple[Any, ...]:
    """F-1 for one input; returns a comparable result (match, reasons, flags, value or error)."""
    sniff = reader.sniff(data, label="x.json", limits=LIMITS)
    assert isinstance(sniff.match, bool) and all(isinstance(r, str) for r in sniff.reasons)
    result = outcome(lambda: list(reader.parse(data, _ref(data), limits=LIMITS)), MalformedArtefact)
    if sniff.match:
        assert result[0] == "ok" and len(result[1]) == 1, result[0]
        (item,) = result[1]
        assert item.locator.p == "" and item.flags == sniff.flags
        return (True, sniff.reasons, sniff.flags, json.dumps(item.value, sort_keys=True))
    assert result[0] in ("ingest", "MalformedArtefact"), result
    if result[0] == "ingest":
        assert result[1] in INGEST_CODES
    return (False, sniff.reasons, sniff.flags, result)


# ------------------------------------------------------------------------------------------------ F-1, F-5 on seeds
@needs_fixtures
def test_every_seed_is_classified_and_the_executions_parse():
    reader = DtapTrajectoryReader()
    matched = [_check_total(reader, data)[0] for data in SEEDS]
    assert any(matched) and not all(matched)  # the LFS pointer and the synthetic run are seeds that do not match


@needs_fixtures
@budget(150)
@given(st.integers(0, 10_000), st.data())
def test_sniff_and_parse_are_total_and_deterministic_on_mutated_seeds(index, data):
    seed = SEEDS[index % len(SEEDS)]
    mutated = data.draw(byte_mutations(seed))
    first = _check_total(DtapTrajectoryReader(), mutated)
    assert _check_total(DtapTrajectoryReader(), mutated) == first  # F-5


@needs_fixtures
@budget(80)
@given(st.integers(0, 10_000), st.integers(0, 10_000), st.data())
def test_the_sniff_cache_never_lets_parse_return_another_inputs_value(i, j, data):
    """The reader keeps the last sniffed bytes and value (the runner sniffs, then parses the same object). Sniffing A,
    then parsing B (equal or not), must give B's own result."""
    a = data.draw(byte_mutations(SEEDS[i % len(SEEDS)]))
    b = data.draw(byte_mutations(SEEDS[j % len(SEEDS)]))
    expected = _check_total(DtapTrajectoryReader(), b)
    reader = DtapTrajectoryReader()
    reader.sniff(a, label="a.json", limits=LIMITS)
    assert _check_total(reader, bytes(bytearray(b))) == expected  # an equal but distinct object
    reader.sniff(b, label="b.json", limits=LIMITS)
    reader.sniff(a, label="a.json", limits=LIMITS)
    assert _check_total(reader, b) == expected


# ------------------------------------------------------------------------------------------------ the D.16.2 table
JSON_LEAF = st.one_of(st.none(), st.booleans(), st.integers(-(2**53), 2**53), st.text(max_size=12))
JSON_VALUE = st.recursive(JSON_LEAF, lambda inner: st.one_of(st.lists(inner, max_size=3),
                                                            st.dictionaries(st.text(max_size=6), inner, max_size=3)),
                          max_leaves=8)
KEYS = sorted(TRAJECTORY_KEYS | JUDGE_KEYS | {"debug", "attack_trajectory", "extra", "metadata"})


def _oracle(value: Any) -> tuple[bool, str, frozenset[str]]:
    """D.16.2, written from the specification table (not from the reader)."""
    if not isinstance(value, dict):
        return False, "dtap.sniff.not_object", frozenset()
    keys = set(value)
    if {"task_info", "traj_info", "trajectory"} <= keys and keys <= {"task_info", "traj_info", "trajectory", "debug"}:
        task_info, traj_info = value["task_info"], value["traj_info"]
        metadata = traj_info.get("metadata") if isinstance(traj_info, dict) else None
        if (isinstance(task_info, dict) and task_info.get("synthetic") is True) or (
                isinstance(metadata, dict) and metadata.get("synthetic") is True):
            return False, "dtap.synthetic", frozenset()
        return True, "dtap.sniff.trajectory_keys", frozenset({FLAG_DEBUG}) if "debug" in keys else frozenset()
    if {"task_success", "attack_success"} <= keys and keys <= JUDGE_KEYS:
        return True, "dtap.sniff.judge_keys", frozenset({FLAG_JUDGE_ONLY})
    if {"task_info", "attack_trajectory"} <= keys:
        return False, "dtap.red_teaming_log", frozenset()
    return False, "dtap.sniff.keys", frozenset()


SYNTHETIC = st.one_of(JSON_VALUE, st.fixed_dictionaries({"synthetic": st.sampled_from([True, False, 1, "true", None])}),
                      st.fixed_dictionaries({"metadata": st.fixed_dictionaries(
                          {"synthetic": st.sampled_from([True, False, 1, None])})}))


@budget(300)
@given(st.one_of(st.dictionaries(st.sampled_from(KEYS), SYNTHETIC, max_size=9), JSON_VALUE))
def test_the_sniff_follows_the_d16_2_table(value):
    data = json.dumps(value).encode("utf-8")
    sniff = DtapTrajectoryReader().sniff(data, label="x.json", limits=LIMITS)
    match, reason, flags = _oracle(value)
    assert (sniff.match, sniff.reasons, sniff.flags) == (match, (reason,), flags)
    assert DtapTrajectoryReader.register_detail(sniff.reasons) == (reason if reason in (
        "dtap.synthetic", "dtap.red_teaming_log") else None)


@budget(100)
@given(st.binary(max_size=200))
def test_an_lfs_pointer_is_never_parsed(tail):
    data = LFS_HEADER + tail
    reader = DtapTrajectoryReader()
    sniff = reader.sniff(data, label="x.json", limits=LIMITS)
    assert not sniff.match and sniff.reasons == ("dtap.lfs_pointer",)
    assert DtapTrajectoryReader.register_detail(sniff.reasons) == "dtap.lfs_pointer"
    with pytest.raises(MalformedArtefact):
        list(reader.parse(data, _ref(data), limits=LIMITS))


# ------------------------------------------------------------------------------------------------ path grammar
SEGMENT = st.one_of(
    st.sampled_from(sorted(FRAMEWORKS | SPLITS | THREATS)),
    st.sampled_from(["..", ".", "", "a\\b", "x" * 300, "judge_result.json", "20260220_133459.json",
                     "20260220_133459(1).json", "20260220_133459_2.json", "trajectory.json", "con", "a b", "~"]),
    st.text(min_size=1, max_size=12),
)


@budget(400)
@given(st.lists(SEGMENT, max_size=11), st.sampled_from(["/", "\\"]))
def test_parse_path_and_config_path_are_total_and_keep_the_grammar(segments, separator):
    from agentprov.ingest.names import logical_name

    label = separator.join(segments)
    facets = parse_path(label)
    assert facets == parse_path(label)  # F-5
    if facets is None:
        return
    assert facets.framework in FRAMEWORKS and facets.split in SPLITS
    assert (facets.threat in THREATS) if facets.split == "malicious" else facets.threat is None
    fields = [facets.framework, facets.model, facets.domain, facets.task_dir, facets.file,
              *(f for f in (facets.threat, facets.risk_category, facets.subcategory) if f is not None)]
    assert all(f and "/" not in f and "\\" not in f for f in fields)
    config = config_path(facets)
    assert config.endswith("/config.yaml") and config.startswith(facets.domain + "/")
    try:
        name = logical_name(label)
    except IngestError:
        return  # the walk never hands the reader a label the names guard refuses (G.3.6, SEC-09)
    guarded = parse_path(name)
    if guarded is not None:
        assert not {".", ".."} & set(guarded.relpath.split("/"))
        assert posixpath.normpath(config_path(guarded)) == config_path(guarded)


DIGITS = st.text(alphabet=st.characters(categories=["Nd"]), min_size=1, max_size=8)


@budget(400)
@given(st.one_of(st.text(max_size=40), st.builds(lambda d, e: f"{d}_{e}.json", DIGITS, DIGITS),
                 st.builds(lambda d, e, r: f"{d}_{e}_{r}.json", DIGITS, DIGITS, DIGITS)))
def test_file_class_is_total_and_only_ascii_digits_make_a_time_named_class(name):
    cls = file_class(name)
    assert cls in CLASSES and cls == file_class(name)
    if cls in ("timestamp", "copy", "rerun"):
        stem = name[:-len(".json")]
        assert stem[:15].isascii() and stem[:8].isdigit() and stem[9:15].isdigit()
        assert all(c.isascii() for c in stem.removesuffix("(1)"))


# ------------------------------------------------------------------------------------------------ state_form
HOSTILE_STRINGS = st.one_of(
    st.text(max_size=60),
    st.builds(lambda n: "[" * n + "]" * n, st.integers(0, 3000)),
    st.builds(lambda n: "{'a': " * n, st.integers(0, 200)),
    st.sampled_from(["{'a': 1}", "[{'a': 1}]", "{\"a\": 1}", "[1, 2", " {x}", "{" + chr(0xD800) + "}", "[" + chr(0xDFFF),
                     "__import__('os').system('true')", "{'__class__': 1}", "[NaN]", "{\"a\": 1e999}"]),
)


@budget(300)
@given(st.one_of(JSON_VALUE, HOSTILE_STRINGS, st.floats(allow_nan=True), st.binary(max_size=8)))
def test_state_form_is_total_and_evaluates_nothing(value):
    form = state_form(value)
    assert form in STATE_FORMS and state_form(value) == form


# ------------------------------------------------------------------------------------------------ discovery
class _Tree:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels

    def walk(self) -> Any:
        for label in self.labels:
            yield CandidateArtefact(label, 1, Origin.local("fuzz"))

    def open(self, label: str, *, max_bytes: int) -> bytes:
        raise AssertionError("discovery never opens a file")


class _Listing:
    def __init__(self, labels: list[str]) -> None:
        self.labels = set(labels)

    def siblings(self, label: str) -> list[str]:
        directory = label.rpartition("/")[0]
        return sorted(x for x in self.labels if x.rpartition("/")[0] == directory)

    def exists(self, ref: str) -> bool:
        return ref in self.labels


NAMES = st.one_of(st.sampled_from(["20260220_133459.json", "20260220_133459(1).json", "20260220_133459_2.json",
                                   "trajectory.json", "partial_trajectory.json", "judge_result.json",
                                   "judge_result(1).json", "red_teaming_agent_1.json", "notes.txt", ".DS_Store",
                                   "._x.json", "other.json", "config.yaml"]),
                  st.text(min_size=1, max_size=10))
DIRS = st.sampled_from(["openaisdk/m/code/benign/57", "openaisdk/m/code/benign/58", "claudesdk/m/x/malicious/direct/r/1",
                        "a", ""])


@pytest.fixture(scope="module")
def profile() -> Any:
    from agentprov.adapters.profiles import load_profile

    return load_profile("dtap-bench")


@budget(200)
@given(st.lists(st.tuples(DIRS, NAMES), max_size=14, unique=True))
def test_discovery_is_total_deterministic_and_keeps_the_judge_rule(profile, entries):
    labels = [f"{d}/{n}" if d else n for d, n in entries]
    reader = DtapTrajectoryReader()
    chosen = [c.label for c in reader.iter_artefacts(_Tree(labels), profile)]
    assert chosen == [c.label for c in DtapTrajectoryReader().iter_artefacts(_Tree(list(reversed(labels))), profile)]
    assert set(chosen) <= set(labels) and len(chosen) == len(set(chosen))
    for label in chosen:
        name = label.rsplit("/", 1)[-1]
        assert name != ".DS_Store" and not name.startswith("._")
        cls = file_class(name)
        assert cls in TRAJECTORY_CLASSES or cls == "judge"
        siblings = [x for x in labels if x.rpartition("/")[0] == label.rpartition("/")[0]]
        if cls == "judge":
            assert not any(file_class(s.rsplit("/", 1)[-1]) in TRAJECTORY_CLASSES and s in chosen for s in siblings)
    listing = _Listing(labels + [f"tasks:{config_path(f)}" for f in map(parse_path, labels) if f is not None])
    for label in chosen:
        aux = reader.auxiliary_for(label, listing)
        assert aux == DtapTrajectoryReader().auxiliary_for(label, listing)
        directory = label.rpartition("/")[0]
        for role, ref in aux.items():
            assert role in ("judge", "copy:judge", "config") or role.startswith("attempt:")
            if role == "config":
                assert ref.startswith("tasks:") and listing.exists(ref)
            else:
                assert ref != label and ref.rpartition("/")[0] == directory and ref in listing.labels
