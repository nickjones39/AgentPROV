"""The single v1 <-> AER field table ``views/transcript_v1_fields.toml`` (docs/architecture C.15.3, D.7.3, J.3.2; R-30).

The importer and the view both read the table; these tests check that it is complete for the J.3.2 layout, that every
handler it names exists, that every AER source names a field of its record kind (``aer/0.1`` closed field sets), and that
C.15.3's field mapping names the same v1 members.
"""

from __future__ import annotations

from pathlib import Path

from agentprov.aer._structure import KIND_FIELDS
from agentprov.views.transcript_v1 import field_table, handler_names, layout, layout_members, usage_map

REPO = Path(__file__).resolve().parents[3]
KIND_OF = {"exec": "execution", "actor": "actor", "scope": "scope", "judgement": "judgement"}


def test_every_meta_member_of_the_layout_has_exactly_one_entry():
    keys = [e["key"] for e in field_table()["meta"]]
    assert sorted(keys) == sorted(layout_members("meta")) and len(keys) == len(set(keys))


def test_model_config_and_usage_entries_name_known_slots():
    assert {e["key"] for e in field_table()["model_config"]} == {"temperature", "usage", "finish_reasons"}
    usage_fields = {"input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cache_read_tokens",
                    "cache_write_tokens", "calls"}  # C.3.12 Usage (closed)
    assert set(usage_map().values()) <= usage_fields and len(set(usage_map().values())) == len(usage_map())


def test_every_source_is_a_handler_or_a_field_of_its_record_kind():
    handlers = set()
    for section in ("meta", "model_config"):
        for entry in field_table()[section]:
            for source in entry["sources"]:
                head, _, rest = source.partition(":")
                if head == "handler":
                    handlers.add(rest)
                    continue
                pointer = rest if head == "exec" else rest.partition(":")[2]
                first = pointer.split("/")[1]
                assert first in KIND_FIELDS[KIND_OF[head]] or first == "ext", source
    assert handlers == set(handler_names())


def test_layout_templates_are_well_formed():
    for name, members in field_table()["layout"].items():
        names = [m.removeprefix("?") for m in members]
        assert len(names) == len(set(names)), name
        assert layout(name)[0][1] is False or name == "discarded_attempt", name


def test_c15_3_names_the_same_meta_members():
    text = (REPO / "docs" / "architecture" / "C_data_model.md").read_text(encoding="utf-8")
    section = text.split("### C.15.3", 1)[1].split("### C.15.4", 1)[0]
    for key in layout_members("meta"):
        if key in ("reasoning_alignment", "n_attempts", "capture"):
            assert key in section, key  # named among the synthetic-only fields
        else:
            assert f"meta.{key}" in section or f".{key}`" in section or f"`{key}`" in section, key
