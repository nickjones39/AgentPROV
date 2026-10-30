"""The golden index: schema, completeness and digests (J.2.2; K.4.1(5), K.7). Runs before any other golden test needs it.

Skips with the reason when neither ``tests/fixtures/agentdojo_prov_v1/golden`` nor ``AGENTPROV_GOLDEN_DIR`` exists. Prints
digests, sizes and ids only, never fixture text (R-42).
"""

from __future__ import annotations

import json

import pytest

from agentprov.testing import fixture_caps, golden

pytestmark = pytest.mark.usefixtures("golden_index")

PAIR_IDS = [f"R{i:02d}" for i in range(1, 11)] + [f"C{i:02d}" for i in range(1, 10)]
NATIVE_IDS = [f"N-C{i:02d}" for i in range(1, 10)]
AGENT_FILES = {"agents.md", "claude.md", "skill.md", ".cursorrules", "gemini.md", "copilot-instructions.md"}

#: J.2.1: the four MIG-10 pairs of R-59: (transcript bytes, transcript sha256 prefix, graph bytes, graph prefix, hazard).
MIG10 = {
    "R09": (3572, "5ff4202511e75ab6", 2226, "ae41e9d0d91c8b17", "nested_order"),
    "R10": (2216, "b9f1f0a257db09cf", 496, "49be42e5615aed2c", "wall_clock_integral"),
    "C08": (6761, "982b2700fb1a5b43", 3432, "85fbe0ec24c6ca29", "nested_order"),
    "C09": (2092, "8423069c006e2a9d", 497, "b6bd29f1cf8f0d16", "wall_clock_integral"),
}
#: J.2.3: native-log pins (git blob SHA-1, bytes, sha256 prefix).
NATIVE_PINS = {
    "N-C01": ("f94053615f024afe6e67b4d39e13647ff34f77c5", 4572, "c96a325a0aab7df5"),
    "N-C02": ("59855f48cffdd3a293a401073126ad6fe71259d4", 3008, "294d9d585c9dbb37"),
    "N-C03": ("1dc18df723d3b1ad5931f49748d59b8d79b04a28", 10176, "333c34951a22dad2"),
    "N-C04": ("721b2cd79206bdadcf1bc391c520acab79fcf7de", 3932, "17fa30e47eb511d9"),
    "N-C05": ("2fd0c7553005a05043655f19d8b6384d341aa0ae", 5438, "72ec7896af000430"),
    "N-C06": ("23cf1da26fa67f67437723e0cdbd4c231362d25f", 5109, "82960f51b7643415"),
    "N-C07": ("a2de257e594996decca633b302418afd37e78fe6", 4201, "57973365e4cac8a1"),
    "N-C08": ("0d72cd3cbe96da2f30cf3610501d2e99243b0a7c", 7060, "c0b1df733e19fcb3"),
    "N-C09": ("feb67bcb83d853e4039a1186d3677ae5d39b0d9b", 1930, "d45f36b597d131f4"),
}


@pytest.fixture(scope="module")
def entries(golden_index):
    return {e.id: e for e in golden_index}


def test_the_index_is_well_formed_and_lists_exactly_the_19_pairs_and_9_native_logs(entries):
    raw = json.loads(golden.index_path().read_bytes())
    assert golden.validate_index(raw) == []
    assert sorted(entries) == sorted(PAIR_IDS + NATIVE_IDS)
    assert [e.id for e in golden.v1_pairs()] == PAIR_IDS
    assert [e.id for e in golden.native_logs()] == NATIVE_IDS


def test_every_listed_file_is_present_with_the_indexed_size_sha256_and_blob_id(entries):
    problems = [p for e in entries.values() for p in golden.verify_entry_files(e)]
    assert problems == []


def test_no_unlisted_file_and_every_file_has_a_source_record():
    """Each file under the golden dir and the native-log dir is in the index or in SOURCE.json (K.4.1(5))."""
    root = golden.fixtures_root()
    indexed = {f.path for e in golden.entries() for f in e.files}
    for directory in (golden.golden_dir(), root / "agentdojo" / "v0.k11", root / "agentdojo" / "head"):
        source = json.loads((directory / "SOURCE.json").read_bytes())
        recorded = {(directory / item["sample_file"]).relative_to(root).as_posix(): item for item in source}
        on_disk = {p.relative_to(root).as_posix(): p for p in directory.rglob("*") if p.is_file() and p.name != "SOURCE.json"}
        assert set(on_disk) == set(recorded), "files without a SOURCE.json entry, or entries without a file"
        for rel, item in recorded.items():
            data = on_disk[rel].read_bytes()
            assert golden.sha256_hex(data) == item["sha256"] and len(data) == item["size_bytes"], rel
            assert item["licence_class"] in golden.LICENCE_CLASSES and item["synthetic"] is False
            if item.get("git_blob_sha1"):
                assert golden.git_blob_sha1(data) == item["git_blob_sha1"], rel
    assert {f for f in indexed if f.startswith("agentdojo_prov_v1/golden/")} <= {
        p.relative_to(root).as_posix() for p in golden.golden_dir().rglob("*") if p.is_file()
    }


def test_the_fixture_tree_holds_no_agent_instruction_files_and_respects_the_size_caps():
    root = golden.fixtures_root()
    files = [p for p in root.rglob("*") if p.is_file()]
    assert files
    assert [p.name for p in files if p.name.lower() in AGENT_FILES] == []  # K.4.2
    # K.4.1(5), D-360: the caps of tests/FIXTURES.json (16 MiB total; files over 1 MiB and sources over 512 KiB only
    # with a recorded reason)
    assert fixture_caps.check_tree(root) == []


def test_pairs_have_the_release_and_converted_licences_and_the_native_link(entries):
    for ident in PAIR_IDS:
        e = entries[ident]
        assert e.kind == golden.KIND_V1_PAIR and e.licence_class == "permissive"
        assert e.origin["framework_commit"] == "579a908354b93361efe0905ffb7623256aa96a06"
        assert e.origin["corpus_relpath"].startswith("corpus/")
        if ident.startswith("R"):
            assert e.tree == "release" and e.licence == "CC-BY-4.0 AND MIT" and e.native is None
            assert "/generated/" in e.file(golden.ROLE_V1_TRANSCRIPT).path
        else:
            assert e.tree == "converted" and e.licence == "MIT" and e.native == "N-" + ident
            assert "/converted/" in e.file(golden.ROLE_V1_TRANSCRIPT).path
            assert golden.native_of(e).id == e.native
        assert e.file(golden.ROLE_V1_TRANSCRIPT).path.endswith(".transcript.json")
        assert e.file(golden.ROLE_COMPAT_GRAPH).path.endswith(".json") and not e.file(golden.ROLE_COMPAT_GRAPH).path.endswith(".transcript.json")
        for key in ("meta", "observed", "manifest_row"):
            assert key in e.expect, (ident, key)


def test_the_four_mig10_pairs_are_the_j21_paths_with_their_hazards(entries):
    tagged = sorted(i for i, e in entries.items() if "mig10" in e.hazards)
    assert tagged == sorted(MIG10)
    for ident, (t_bytes, t_prefix, g_bytes, g_prefix, hazard) in MIG10.items():
        e = entries[ident]
        t, g = e.file(golden.ROLE_V1_TRANSCRIPT), e.file(golden.ROLE_COMPAT_GRAPH)
        assert (t.size, t.sha256[:16], g.size, g.sha256[:16]) == (t_bytes, t_prefix, g_bytes, g_prefix)
        assert hazard in e.hazards
    assert entries["R09"].origin["corpus_relpath"].endswith(
        "meta-llama_llama-3.3-70b-instruct/prov/important_instructions/workspace_user_task_10_x_injectiontask7_injection"
    )
    assert entries["C09"].origin["corpus_relpath"].endswith(
        "gpt-4o-2024-05-13/prov/important_instructions_no_model_name/banking_user_task_11_x_injectiontask2_injection"
    )
    # the 15 original pairs carry neither MIG-10 hazard (J.2.1)
    original = [e for i, e in entries.items() if i in PAIR_IDS and i not in MIG10]
    assert len(original) == 15 and not any({"nested_order", "wall_clock_integral"} & set(e.hazards) for e in original)


@pytest.mark.parametrize("ident", NATIVE_IDS)
def test_native_logs_match_the_j23_pins(entries, ident):
    blob, size, prefix = NATIVE_PINS[ident]
    e = entries[ident]
    f = e.file(golden.ROLE_NATIVE_LOG)
    assert (f.git_blob_sha1, f.size, f.sha256[:16]) == (blob, size, prefix)
    assert e.origin == {
        "repo": "https://github.com/ethz-spylab/agentdojo",
        "commit": "c274885610efaaafec38b6d3eb07152ba7ff3f94",
        "path": e.origin["path"],
        "git_blob_sha1": blob,
    }
    assert e.origin["path"].startswith("runs/") and f.path == f"agentdojo/v0.k11/{e.origin['path']}"
    assert e.licence == "MIT"


def test_the_two_old_test_fixtures_are_stored_once_as_aliases(entries):
    assert list(entries["N-C01"].aliases) == ["tests/fixtures/native_benign_claude-3-haiku_bank_user_task_9.json"]
    assert list(entries["N-C02"].aliases) == ["tests/fixtures/native_injection_gpt4o_spotlighting_workspace_user_task_25.json"]
    assert all(not e.aliases for i, e in entries.items() if i not in ("N-C01", "N-C02"))


def test_the_licence_notices_are_present():
    root = golden.fixtures_root()
    assert (golden.golden_dir() / "NOTICE.md").is_file()
    text = (root / "LICENSES" / "AgentDojo-MIT.txt").read_text(encoding="utf-8")
    assert text.startswith("MIT License") and "Debenedetti" in text  # the licence's own title and copyright line
