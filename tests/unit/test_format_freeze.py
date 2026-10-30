"""``aer/0.1`` and ``capture/0.1`` are frozen (phase-6 gate, AD-06, 2026-10-08; docs/architecture C.20); ``aer/0.2`` and
``agentprov-corpus/0.2`` are frozen with their approval (D-210..D-212, 2026-10-12), beside the unchanged 0.1 files.

The published schemas, the AER record kinds and the closed enums of ``agentprov.aer.types`` are pinned by digest. If a
test here fails, the change is a **format change**: it needs a new format version (``aer/0.2`` or ``capture/0.2``, with
its own schema file, D.12.4), a DECISIONS entry and an AGENTS.md record. Do not update a pin to make the test pass.
``CORE_ISSUE_CODES`` is not pinned: seal issue codes are validator vocabulary, not record grammar (C.12.3).
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources

import pytest

from agentprov import versions
from agentprov.aer import RECORD_KINDS
from agentprov.aer import types as T

SCHEMA_PINS = {
    "aer-0.1.schema.json": "a0c3b248122122716c9cfe590f492758b5a1bad9626acec2afb7f71ca324ad6e",
    "capture-0.1.schema.json": "a191667820d309c90a15db4691f5b323f2acf6988f142c2e410ad9eb8017ade5",
    # D-224 (deferrals ultra fixes) + pre-round verification V-7 (#28 reserved forms, #31 header task unk); no 0.2 corpus stored
    "aer-0.2.schema.json": "42e7046c9c76b26c037cc9bcfd13257bbb4b505d95ddefa33d20ff593bbb9639",
    # D-623: aer.mode + D-224 + D-640: optional prov rules + V-7: the validation stage's optional `skipped`; none stored
    # + D-780: the optional producer.build_steps (no corpus is sealed in 0.2, so nothing sealed carries the older bytes)
    "corpus-0.2.schema.json": "f6e54b2f59674e8b3dce2936886ac393cb52889d2b6538f6ae411410840a2d11",
}
ENUM_SURFACE_PIN = "968e852105285704349141dc43dbf216cbd4f9698eb977b74e7b33c0bda2d722"
UNPINNED = {"CORE_ISSUE_CODES"}


def test_frozen_formats_are_declared() -> None:
    assert versions.FROZEN == {"aer", "capture"}
    assert versions.VERSIONS["aer"] == "aer/0.2" and versions.VERSIONS["capture"] == "capture/0.1"
    assert versions.VERSIONS["corpus_format"] == "agentprov-corpus/0.2"


@pytest.mark.parametrize("name", sorted(SCHEMA_PINS))
def test_published_schema_is_frozen(name: str) -> None:
    data = resources.files("agentprov").joinpath("schemas", name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == SCHEMA_PINS[name], (
        f"{name} changed after the phase-6 freeze: a format change needs a new version (D.12.4), not an edit"
    )


def _enum_surface() -> bytes:
    names = sorted(
        n for n in dir(T) if n.isupper() and isinstance(getattr(T, n), (frozenset, tuple)) and n not in UNPINNED
    )
    surface = {n: sorted(getattr(T, n), key=lambda v: (str(type(v)), v)) for n in names}
    surface["RECORD_KINDS"] = sorted(RECORD_KINDS)
    return json.dumps(surface, sort_keys=True, separators=(",", ":")).encode()


def test_record_kinds_and_closed_enums_are_frozen() -> None:
    assert len(RECORD_KINDS) == 13
    assert hashlib.sha256(_enum_surface()).hexdigest() == ENUM_SURFACE_PIN, (
        "an AER record kind or closed enum changed after the phase-6 freeze: that is aer/0.2 (D.12.4)"
    )
