"""The ``autogen-guard-placement`` profile and its registry part (docs/architecture D.19.10; DECISIONS D-300, D-303)."""

from __future__ import annotations

import json
import tomllib

import autogen_support as support
import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source

PROFILE_FILE = support.REPO / "src/agentprov/adapters/autogen/profiles/autogen-guard-placement.profile.toml"


def _toml() -> dict:
    return tomllib.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def test_profile_pin_licence_and_import_table():
    profile = load_profile(support.PROFILE)
    data = _toml()
    (pin,) = [p for p in data["source"]["pins"] if p.get("primary") is True]
    assert pin["kind"] == "zenodo" and pin["doi"] == "10.5281/zenodo.23025259" and pin["sha256"] == support.ZIP_SHA256
    assert (pin["size"], pin["md5"], pin["version"]) == (4978620, "800a67afee7bef77cdbea9df9920b33c", "v1.0")
    assert data["licence"]["spdx"] == data["licence"]["data_licence"] == "CC-BY-4.0" and data["licence"]["policy"] == "include"
    imp = data["import"]
    assert imp["dialect"] == imp["mapper"] == "autogen.runs" and imp["variants"] == ["condition", "defense", "injecagent", "team"]
    assert "exclude" not in imp  # D-300 with D-321: phases 7-9 are registered row by row by the reader, not as files
    assert profile.version == 2 and profile.parts == ("v1.0",)  # D-603: [withhold] added; v1 archived (D-31)
    assert load_profile(support.PROFILE, 1).sha256.startswith("1a7573f4e88a")  # the scratch corpora's recorded bytes


def test_family_table_conforms_to_the_closed_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((support.REPO / "src/agentprov/adapters/autogen/family.schema.json").read_bytes())
    jsonschema.validate(_toml()["family"]["autogen"], schema)


def test_verified_code_is_the_autogen_tag():
    (entry,) = _toml()["family"]["autogen"]["verified_code"]
    assert entry["commit"] == "83afbf5857aac683340d4c692194e548b1e8edda"


def test_registry_part_is_supported_with_its_own_corpus_and_semantics():
    registration = get_source("autogen-guard-placement")
    (part,) = registration.capabilities
    assert part.profile == "autogen-guard-placement" and part.corpus_id == "autogen-guard-placement" and part.part == "v1.0"
    assert part.import_status == "supported" and part.target_import_status == "supported"
    assert part.semantics == ("autogen.tools@1",) and registration.family == "autogen"
    assert registration.licence.spdx == "CC-BY-4.0"


def test_the_fixtures_are_pinned_members_with_their_licences():
    import hashlib
    import zlib

    rows = json.loads((support.FIXTURES / "SOURCE.json").read_text(encoding="utf-8"))
    assert len(rows) == 9 and {r["container"] for r in rows} == {support.ZIP_SHA256}
    for r in rows:
        data = (support.FIXTURES / r["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == r["sha256"] and len(data) == r["size"]
        assert f"{zlib.crc32(data):08x}" == r["crc32"]
    labels = {r["label"].split("/", 1)[1] for r in rows}
    assert {"LICENSE", "LICENSE-DATA", "LICENSE-THIRD-PARTY"} <= labels
