"""D-217 (agentprov-corpus/0.2): a snapshot imported from an archive stored as byte parts (D-249) seals with its
``parts``, so a Zenodo split deposit can be sealed; the frozen corpus-0.1 behaviour is pinned in
``tests/adapters/runner/test_ingest_formats_2.py``.

Not covered here: sealing a whole imported corpus. The only family with a split-deposit fixture (FooBench, a toy whose
row maps with issues by design) cannot be sealed; ``package.seal`` takes the origin from
:func:`snapshot_origin_from_pin` and compares it with the spec's (:func:`check_origin`), both tested below."""

from __future__ import annotations

import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters"))  # import_support
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "runner"))

from test_ingest_formats_2 import _split_deposit  # noqa: E402

from agentprov.corpus import manifest as m  # noqa: E402
from agentprov.corpus.manifest import ManifestError, snapshot_origin_from_pin  # noqa: E402
from agentprov.corpus.spec import CorpusSpecError, check_origin  # noqa: E402
from agentprov.raw.fetch import split_pin_record  # noqa: E402

V02 = {"corpus_format": "agentprov-corpus/0.2"}


def _origin_validator(fmt: str) -> jsonschema.Draft202012Validator:
    schema = m.corpus_schema(fmt)
    origin = schema["properties"]["sources"]["items"]["properties"]["snapshots"]["items"]["properties"]["origin"]
    return jsonschema.Draft202012Validator({"$schema": schema["$schema"], "$defs": schema.get("$defs", {}), **origin})


def test_a_zenodo_split_snapshot_seals_with_its_parts_in_corpus_0_2(tmp_path):
    pin, _ = _split_deposit(tmp_path / "zen")
    record = split_pin_record(pin)
    descriptor = {"kind": "split", "archive": "zip", "label": "deposit.zip", "parts": [p["sha256"] for p in pin["parts"]]}
    origin = snapshot_origin_from_pin(record, [descriptor], **V02)
    assert (origin["kind"], origin["doi"], origin["file"]) == ("zenodo", pin["doi"], record["file"])
    assert [p["file"] for p in origin["parts"]] == [p["file"] for p in pin["parts"]]  # the pin's order
    assert all(p["sha256"].startswith("sha256:") and isinstance(p["bytes"], int) for p in origin["parts"])
    assert not list(_origin_validator("agentprov-corpus/0.2").iter_errors(origin))
    assert list(_origin_validator("agentprov-corpus/0.1").iter_errors(origin))  # 0.1 has no parts
    assert check_origin(origin) == origin  # a corpus spec can name it
    with pytest.raises(ManifestError):  # the descriptor must list the pin's parts in order
        snapshot_origin_from_pin(record, [{**descriptor, "parts": descriptor["parts"][::-1]}], **V02)


def test_an_hf_split_snapshot_lists_its_parts_in_corpus_0_2(tmp_path):
    pin, _ = _split_deposit(tmp_path / "hf", kind="hf")
    descriptor = {"kind": "split", "archive": "zip", "label": "deposit.zip", "parts": [p["sha256"] for p in pin["parts"]]}
    origin = snapshot_origin_from_pin(split_pin_record(pin), [descriptor], **V02)
    assert {k: origin[k] for k in ("dataset", "gated", "kind", "path", "revision")} == {
        "dataset": "owner/name", "gated": False, "kind": "hf", "path": "logs", "revision": "c" * 40}
    assert len(origin["parts"]) == len(pin["parts"])
    assert not list(_origin_validator("agentprov-corpus/0.2").iter_errors(origin))


def test_a_spec_origin_with_malformed_parts_is_refused():
    base = {"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "a.zip"}
    for parts in ([], [{"file": "a.z01", "bytes": 1, "sha256": "sha256:" + "0" * 64}],
                  [{"file": "a.z01", "bytes": 1, "sha256": "0" * 64}] * 2,
                  [{"file": "a.z01", "bytes": -1, "sha256": "sha256:" + "0" * 64}] * 2):
        with pytest.raises(CorpusSpecError):
            check_origin({**base, "parts": parts})
