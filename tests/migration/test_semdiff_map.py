"""``prov/compat/semdiff-map.toml`` (R-33; EF E.8.4, J.3.6; K.5.6 item 8): closed schema, vocabulary, rule ids, rulings,
the generated tables, and agreement with the spec tables as they stand.

The spec keeps its prose tables (EF E.8.4, J.3.6); the map is the machine-readable source and follows the rulings J.3.6
cites where the two would differ. Every place the map deliberately goes beyond or departs from the spec text is listed
below with its reason, so a new disagreement fails here instead of slipping through.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from agentprov.aer.rules import CatalogueUnavailableError, load_catalogue
from agentprov.migration import semdiff
from agentprov.prov.specs import load_spec

REPO = Path(__file__).resolve().parents[2]
EF = REPO / "docs" / "architecture" / "EF_provenance.md"
J = REPO / "docs" / "architecture" / "J_migration.md"

#: Rule ids the map may name before the engine catalogue ships them (none since the phase-7 assessment rules merged).
PENDING_PHASE7_RULES: frozenset[str] = frozenset()
#: Rule ids the spec names for deferred engine methods (E.1.7); they appear only in ``mentions``.
DEFERRED_RULES = frozenset({"aprov.i_arg_literal_overlap@1"})

#: Map rows with no row in the E.8.4 tables, and why (reported, not silently added to the spec).
NOT_IN_EF = {
    "new_actors": "E.8.4 lists no row for the non-LLM actors (user, attacker, checker, runtime, defence) that now become agents",
    "new_gaps": "E.8.4 lists no row for declared unknowns (apv:Gap, status properties; R-08) that replace v2.3 omissions",
    "prov_label": "E.8.4's attribute table omits prov:label, which every v2.3 node carries (audit/provenance.md §6)",
    "adprov_content": "E.8.4's attribute table omits the gated adprov:content (audit/provenance.md §6)",
}

#: The evidence classes where the map (and the engine output gate E checks) differ from the E.8.4 class text. The test
#: does not parse class prose; these are pinned on the map rows instead.
CLASS_DISAGREEMENTS = {
    "R1": ({"D", "I"}, "E.8.4: OBSERVED for v1; the mapper records /generated_by as DERIVED (adprov.tool_turn_is_one_execution@1)"),
    "acted_on_behalf_of": ({"D", "I"}, "E.8.4: DERIVED; the v1 runtime delegation is INFERRED (EF E.10 item 21)"),
}

_DISPOSITION = re.compile(r"(moved-to-assessment|reclassified|replaced|dropped|moved|kept|new)\b")
_RULE_ID = re.compile(r"\b[a-z]+\.[a-z0-9_]+\*?@\d+|\baprov\.[a-z0-9_]+\*")
_PAIR = re.compile(r"(\d[\d,]*) / (\d[\d,]*)")
_NUMBER = re.compile(r"\d[\d,]*")


@pytest.fixture(scope="module")
def semdiff_map() -> semdiff.SemDiffMap:
    return semdiff.load_map()


def _num(text: str) -> int:
    return int(text.replace(",", ""))


# ------------------------------------------------------------------------------------------------ schema


def test_the_map_loads_with_its_format_and_version(semdiff_map):
    assert semdiff_map.format == "agentprov-semdiff-map/0.1" and semdiff_map.version == 1
    assert semdiff_map.source == "adprov-v2.3-compat" and semdiff_map.to == "agentprov-prov/0.1"
    assert len(semdiff_map.sha256) == 64 and semdiff_map.sha256 == semdiff.sha256_hex(semdiff.map_bytes())


def test_every_disposition_is_in_js_closed_vocabulary(semdiff_map):
    assert semdiff.DISPOSITIONS == ("kept", "reclassified", "moved", "replaced", "moved-to-assessment", "dropped", "new")
    assert {r.disposition for r in semdiff_map.rows} <= set(semdiff.DISPOSITIONS)


def test_the_map_covers_every_builder_rule_and_node_class(semdiff_map):
    assert {r.rule for r in semdiff_map.rows if r.rule} == set(semdiff.V23_RULES)
    assert {r.node for r in semdiff_map.rows if r.node} == set(semdiff.NODE_CLASSES)


def _mutate(old: str, new: str) -> bytes:
    data = semdiff.map_bytes().decode()
    assert old in data
    return data.replace(old, new, 1).encode()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('id = "R1"\n', 'id = "R1"\nsurprise = 1\n', "unknown keys"),
        ('disposition = "kept"', 'disposition = "retained"', "closed vocabulary"),
        ('rule = "R2"', 'rule = "R1"', "same rule"),
        ('rule = "R7"', 'node = "a_k"', "same node"),
        ('rule = "R8"\n', '', "exactly one matcher"),
        ('targets = ["aprov.gen_result@1", "aprov.gen_message@1"]', 'targets = ["gen_result"]', "not a rule id"),
        ('targets = ["aprov.assoc_tool@1"]', 'targets = ["agentdojo.auto_execution_unverified@1"]', "engine catalogue"),
        ('bundle = ["inference"]', 'bundle = ["inference", "none"]', "bundle"),
        ('frozen = { released = 64781, converted = 68620 }', 'frozen = { release = 64781 }', "count table"),
        ('frozen = { released = 22218, converted = 19838 }', 'frozen = { released = -1 }', "non-negative"),
        ('on = ["wasGeneratedBy"]', 'on = ["used"]', "same element"),
        ('version = 1\n', 'version = 1\nextra = 2\n', "[map] has exactly"),
        ('format = "agentprov-semdiff-map/0.1"', 'format = "agentprov-semdiff-map/0.2"', "format"),
        ('recompute = "phase 13"', 'recompute = "later"', "recompute"),
    ],
    ids=[
        "unknown-key", "disposition", "duplicate-rule", "duplicate-node", "no-matcher", "bad-rule-id", "adapter-target",
        "bundle-none", "count-key", "negative-count", "overlapping-attribute", "map-key", "format", "recompute",
    ],
)
def test_the_schema_is_closed(old, new, message):
    with pytest.raises(semdiff.SemDiffMapError, match=re.escape(message)):
        semdiff.parse_map(_mutate(old, new))


def test_a_dropped_element_has_no_counterpart():
    data = _mutate('disposition = "moved"\ntargets = ["aprov.use_context@1"]', 'disposition = "dropped"\ntargets = ["aprov.use_context@1"]')
    with pytest.raises(semdiff.SemDiffMapError, match="dropped element"):
        semdiff.parse_map(data)


def test_frozen_counts_need_a_source():
    data = _mutate('frozen_source = "audit/provenance.md §4.1; J.1.3 (wasGeneratedBy)"\n', "")
    with pytest.raises(semdiff.SemDiffMapError, match="frozen_source"):
        semdiff.parse_map(data)


# ------------------------------------------------------------------------------------------------ rule ids


def _adapter_rule_exists(ref: str) -> bool:
    namespace = ref.split(".", 1)[0]
    try:
        return load_catalogue(namespace).get(ref) is not None
    except CatalogueUnavailableError:
        return False


def test_every_target_is_a_rule_of_the_shipped_engine_catalogue(semdiff_map):
    engine = set(load_spec().rules)
    missing = {t for r in semdiff_map.rows for t in r.targets} - engine
    assert missing <= PENDING_PHASE7_RULES, f"targets missing from the aprov catalogue: {sorted(missing - PENDING_PHASE7_RULES)}"


def test_every_assumption_and_mention_resolves(semdiff_map):
    engine = set(load_spec().rules)
    unknown = []
    for row in semdiff_map.rows:
        for ref in (*row.assumptions, *row.mentions):
            if ref.startswith("aprov."):
                if ref not in engine and ref not in PENDING_PHASE7_RULES | DEFERRED_RULES:
                    unknown.append((row.id, ref))
            elif not _adapter_rule_exists(ref):
                unknown.append((row.id, ref))
    assert unknown == []


def test_deferred_rule_ids_are_only_mentioned(semdiff_map):
    for row in semdiff_map.rows:
        assert not set(row.targets) & DEFERRED_RULES and not set(row.assumptions) & DEFERRED_RULES


# ------------------------------------------------------------------------------------------------ the rulings of J.3.6


def test_defence_omitted_maps_to_an_overwritten_content_status(semdiff_map):
    row = next(r for r in semdiff_map.rows if r.attribute == "adprov:defence_omitted")
    assert row.content_status == "apv:Overwritten" and row.disposition == "reclassified"
    assert "aprov.decision@1" in row.targets and row.frozen == {"released": 0, "converted": 2154}


def test_r5_is_replaced_by_the_full_inference6_closure(semdiff_map):
    row = semdiff_map.by_rule("R5")
    assert row is not None and row.disposition == "replaced" and row.targets == ("aprov.comm@1",)
    assert "Inference-6 closure" in row.counterpart and "AD-19(c)" in row.counterpart


def test_r3_and_r4_are_inferred_context_membership_per_ad05(semdiff_map):
    for rule in ("R3", "R4"):
        row = semdiff_map.by_rule(rule)
        assert row is not None and row.disposition == "moved" and row.targets == ("aprov.use_context@1",)
        assert row.bundle == ("inference",) and row.evidence_class == ("I",)
        assert "adprov.context_is_prefix@1" in row.assumptions and row.recompute == "phase 13"


def test_sink_taint_moves_to_the_assessment_bundle(semdiff_map):
    row = semdiff_map.by_rule("R6")
    assert row is not None and row.disposition == "moved-to-assessment" and row.bundle == ("assessment",)
    assert set(row.targets) == {"aprov.a_exposure@1", "aprov.a_taint@1"}
    assert row.frozen == {"released": 26645, "converted": 23449}
    assert row.frozen_extra["taint_pairs"] == {"released": 41066, "converted": 36687}
    # the overlaps are the rest of the taint pairs (audit/provenance.md §4.1: "the rest are also R4")
    assert row.frozen_extra["overlaps"] == {"released": 41066 - 26645, "converted": 36687 - 23449}


def test_the_unexecuted_requests_are_153_positional(semdiff_map):
    row = next(r for r in semdiff_map.rows if r.measure == "unexecuted_requests")
    assert row.frozen == {"released": 48, "converted": 153} and "R-33" in (row.frozen_source or "")


def test_the_used_decomposition_reconciles_with_j13(semdiff_map):
    """J.1.3 / J.3.6: used = R3 + R4 + R6-only = 121,496 / 111,499."""
    rows = [semdiff_map.by_rule(r) for r in ("R3", "R4", "R6")]
    assert sum(r.frozen["released"] for r in rows if r) == 121496
    assert sum(r.frozen["converted"] for r in rows if r) == 111499


@pytest.mark.parametrize("row_id", sorted(CLASS_DISAGREEMENTS))
def test_classes_that_differ_from_the_ef_prose_are_pinned(semdiff_map, row_id):
    classes, reason = CLASS_DISAGREEMENTS[row_id]
    row = next(r for r in semdiff_map.rows if r.id == row_id)
    assert set(row.evidence_class) == classes, reason


# ------------------------------------------------------------------------------------------------ generated tables


def _tool():
    spec = importlib.util.spec_from_file_location("gen_semdiff_tables", REPO / "tools" / "gen_semdiff_tables.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gen_semdiff_tables", module)
    spec.loader.exec_module(module)
    return module


def test_the_generated_tables_are_current():
    tool = _tool()
    assert tool.main(["--check"]) == 0, "run: uv run python tools/gen_semdiff_tables.py"


def test_the_generated_tables_carry_every_row(semdiff_map):
    text = _tool().render(semdiff_map)
    assert "do not edit" in text and semdiff_map.sha256 in text
    for row in semdiff_map.rows:
        assert row.v23_element.replace("|", "\\|") in text


# ------------------------------------------------------------------------------------------------ the spec tables


def _section(path: Path, start: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def _tables(section: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[str] = []
    for line in [*section.splitlines(), ""]:
        if line.startswith("|"):
            current.append(line)
        elif current:
            rows = [[c.strip() for c in row.strip().strip("|").split("|")] for row in current[2:]]
            tables.append(rows)
            current = []
    return tables


def _spec_rows() -> dict[str, list[list[str]]]:
    ef = _tables(_section(EF, "### E.8.4", "### E.8.5"))
    j = _tables(_section(J, "### J.3.6", "**`SemDiffReport` fields:**"))
    assert len(ef) == 3 and len(j) == 1, "the E.8.4 / J.3.6 table layout changed"
    return {"relations": ef[0], "nodes": ef[1], "attributes": ef[2], "j": j[0]}


def _label(cell: str) -> str:
    return cell.replace("`", "")


def _match(table: list[list[str]], prefix: str) -> list[str]:
    found = [row for row in table if _label(row[0]).startswith(prefix)]
    assert len(found) == 1, f"{prefix!r} matches {len(found)} spec rows"
    return found[0]


def _groups(semdiff_map) -> dict[tuple[str, str], list[semdiff.MapRow]]:
    groups: dict[tuple[str, str], list[semdiff.MapRow]] = {}
    for row in semdiff_map.rows:
        if row.ef:
            table, prefix = row.ef.split(":", 1)
            groups.setdefault((table, prefix), []).append(row)
        if row.j:
            groups.setdefault(("j", row.j), []).append(row)
    return groups


def test_every_map_row_has_a_spec_row_or_a_recorded_reason(semdiff_map):
    assert {r.id for r in semdiff_map.rows if not r.ef} == set(NOT_IN_EF)


def test_every_spec_row_is_covered_by_the_map(semdiff_map):
    spec = _spec_rows()
    covered = {(t, id(_match(spec[t], p))) for (t, p) in _groups(semdiff_map)}
    for table, rows in spec.items():
        for row in rows:
            assert (table, id(row)) in covered, f"{table}: spec row {_label(row[0])[:40]!r} has no map row"


def _ids_in(cells: list[str]) -> set[str]:
    return {m for cell in cells for m in _RULE_ID.findall(cell)}


def _expand(ref: str, universe: set[str]) -> set[str]:
    if "*" not in ref:
        return {ref}
    prefix = ref.split("*", 1)[0]
    return {u for u in universe if u.startswith(prefix)} or {ref}


@pytest.mark.parametrize("table", ["relations", "nodes", "attributes", "j"])
def test_dispositions_rule_ids_and_counts_agree_with_the_spec(semdiff_map, table):
    spec = _spec_rows()
    universe = set(load_spec().rules) | PENDING_PHASE7_RULES
    problems = []
    for (t, prefix), rows in _groups(semdiff_map).items():
        if t != table:
            continue
        spec_row = _match(spec[table], prefix)
        disposition_col = {"relations": 3, "nodes": 3, "attributes": 3, "j": 2}[table]
        found = _DISPOSITION.match(spec_row[disposition_col])
        dispositions = {r.disposition for r in rows}
        if found is None or found.group(1) not in dispositions:
            problems.append(f"{prefix}: disposition {spec_row[disposition_col][:30]!r} vs map {sorted(dispositions)}")
        names = {ref for r in rows for ref in r.rule_ids}
        for ref in _ids_in(spec_row[1:]):
            if not _expand(ref, universe) <= names:
                problems.append(f"{prefix}: the spec names {ref}, the map rows do not")
        count = spec_row[1].split("(", 1)[0] if table == "attributes" else spec_row[1]
        pair = _PAIR.search(count)
        if table == "attributes":
            values = {v for r in rows for v in r.frozen.values()}
            for number in _NUMBER.findall(count):
                if _num(number) not in values:
                    problems.append(f"{prefix}: count {number} is not a frozen count of the map rows")
            if not _NUMBER.search(count) and not any(r.frozen_note for r in rows):
                problems.append(f"{prefix}: the spec states the count in words; the map rows carry no frozen_note")
        elif pair:
            released, converted = _num(pair.group(1)), _num(pair.group(2))
            if not any(r.frozen.get("released") == released and r.frozen.get("converted") == converted for r in rows):
                problems.append(f"{prefix}: count {released} / {converted} is not the frozen count of a map row")
    assert problems == []


def test_the_ef_node_table_states_the_153_ruling():
    nodes = _spec_rows()["nodes"]
    new_row = _match(nodes, "—")
    assert "48 / 153" in new_row[2] and "R-33" in new_row[2]
