"""The ``agentops.trace`` reader: label grammar, sniff, parse, per-unit task plan and the D-143 selection (docs/architecture
D.18.1, D.18.2; DECISIONS D-191, D-194)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator

import agentops_support as support
import pytest

from agentprov.adapters.agentops.dialect import AgentOpsTraceReader, parse_label, task_files
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner.importer import _AuxListing, _match
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, Origin
from agentprov.errors import MalformedArtefact
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()
#: (agent directory, provider_model directory) of the eight models; Opus ran in two directories (census §3.2).
MODELS = (
    ("gpt55", "openai_gpt-5.5"), ("mistral_large", "openrouter_mistralai_mistral-large-2512"),
    ("llama4_scout", "openrouter_meta-llama_llama-4-scout"), ("sonnet", "anthropic_claude-sonnet-4-6"),
    ("qwen3_max", "openrouter_qwen_qwen3-max"), ("haiku", "anthropic_claude-haiku-4-5-20251001"),
    ("deepseek_v32", "openrouter_deepseek_deepseek-v3.2"),
)
DOMAINS = ("code", "data_analysis", "research", "safety", "tool_use")
CONDITIONS = ("clean", "noisy", "adversarial")


def _labels() -> Iterator[str]:
    """Every run label of the pinned archive, rebuilt from the census layout (7,202 files), plus the side files."""
    def cells(agent: str, model: str, domains: tuple[str, ...], tasks: range = range(1, 21)) -> Iterator[str]:
        for cond in CONDITIONS:
            for dom in domains:
                for n in tasks:
                    for run in (1, 2, 3):
                        yield f"pilot_v1_seeded/{agent}/{model}/{cond}/{dom}_{n:03d}_run{run}.json"
    for agent, model in MODELS:
        yield from cells(agent, model, DOMAINS)
        yield f"pilot_v1_seeded/{agent}/{model}_report.json"
        yield f"pilot_v1_seeded/{agent}/{model}/clean/._{DOMAINS[0]}_001_run1.json"
    opus = "anthropic_claude-opus-4-7"
    yield from cells("opus_4_7", opus, ("code", "data_analysis"))
    yield from cells("opus_4_7", opus, ("research",), range(1, 11))
    yield from (f"pilot_v1_seeded/opus_4_7/{opus}/clean/research_011_run{r}.json" for r in (1, 2))  # discarded copies
    yield from cells("opus_4_7_part2", opus, ("research",), range(11, 21))
    yield from cells("opus_4_7_part2", opus, ("safety", "tool_use"))
    yield f"pilot_v1_seeded/opus_4_7/{opus}_report.json"
    yield "pilot_v1_seeded/opus_4_7_part2/_partial_provenance.json"
    for name in ("pairwise.md", "analysis.md", "analysis_long.csv", "safety_per_payload.md", f"{opus}_report.json"):
        yield f"pilot_v1_seeded/_combined/{name}"


class _Tree:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels

    def walk(self) -> Iterator[CandidateArtefact]:
        for label in self.labels:
            yield CandidateArtefact(label, 1, Origin.member("0" * 64, label, 0, 0, 1))

    def open(self, label: str, *, max_bytes: int) -> bytes:  # pragma: no cover - never opened
        raise AssertionError(label)


def test_label_grammar():
    f = parse_label(support.F["anthropic_payload"])
    assert f is not None and (f.agent_dir, f.model_dir, f.condition, f.domain, f.number, f.run) == (
        "opus_4_7_part2", "anthropic_claude-opus-4-7", "adversarial", "safety", "020", 2)
    assert f.task_id == "safety/020"
    assert parse_label("/some/local/prefix/" + support.F["clean_safety_plain"]).relpath == support.F["clean_safety_plain"]
    for bad in ("pilot_v1_seeded/x/y/hostile/safety_001_run1.json", "pilot_v1_seeded/x/y/clean/safety_1_run1.json",
                "pilot_v1_seeded/x/y/clean/safety_001_run0.json", "x/clean/safety_001_run1.json", "pilot_v1_seeded/a_report.json"):
        assert parse_label(bad) is None, bad


def test_sniff_classifies_runs_reports_and_foreign_input():
    reader = AgentOpsTraceReader()
    data = support.run_bytes(support.F["clean_safety_plain"])
    hit = reader.sniff(data, label="", limits=LIMITS)
    assert hit.match and (hit.dialect, hit.variant) == ("agentops.trace", "v1")
    report = json.dumps({"agent_id": "a", "results": [], "aggregate_scores": {}, "total_tasks": 0}).encode()
    miss = reader.sniff(report, label="", limits=LIMITS)
    assert not miss.match and miss.reasons == ("agentops.report",) and reader.register_detail(miss.reasons) == "agentops.report"
    value = json.loads(data)
    value["trace"]["extra"] = 1
    assert reader.sniff(json.dumps(value).encode(), label="", limits=LIMITS).reasons == ("agentops.sniff.trace_keys",)
    assert reader.sniff(b"[]", label="", limits=LIMITS).reasons == ("agentops.sniff.not_object",)
    assert reader.sniff(b"{\"a\": 1, \"a\": 2}", label="", limits=LIMITS).reasons[0].startswith("ingest.")
    assert reader.register_detail(("agentops.sniff.keys",)) is None


def test_parse_yields_one_item_and_refuses_foreign_input():
    reader = AgentOpsTraceReader()
    data = support.run_bytes(support.F["clean_safety_plain"])
    ref = ArtefactRef("a0", "0" * 64, len(data), "application/json", Origin.member("0" * 64, "x", 0, 0, len(data)))
    (item,) = reader.parse(data, ref, limits=LIMITS)
    assert item.locator.key() == {"p": ""} and item.value["task_id"] == "safety/018"
    with pytest.raises(MalformedArtefact):
        list(reader.parse(b"{}", ref, limits=LIMITS))


def test_task_plan_names_the_pinned_member():
    rows = task_files()
    assert len(rows) == 100 and all(r.id == f"{r.label.split('/')[-2]}/{r.label.split('/')[-1][:3]}" for r in rows.values())
    reader = AgentOpsTraceReader()
    label = support.F["task_with_context"]
    member = rows["code/001"].label
    assert reader.auxiliary_for(label, _AuxListing([label], {"tasks": [member]})) == {"task": f"tasks:{member}"}
    assert reader.auxiliary_for(label, _AuxListing([label], {"tasks": []})) == {}
    assert reader.auxiliary_for("not/a/run.json", _AuxListing([], {"tasks": [member]})) == {}


def test_selection_reproduces_the_in_scope_count_and_registers_the_rest():
    """D-143/D-191: the profile's include globs select 3,360 runs; every other run file matches an exclude entry with
    select.out_of_scope (3,842 = 3,840 cells + 2 discarded part-1 copies); rollups are select.not_execution_artefact;
    AppleDouble members are strays. Same matcher and order as the runner (first matching entry wins)."""
    labels = list(_labels())
    runs = [lab for lab in labels if parse_label(lab) is not None and not lab.rsplit("/", 1)[-1].startswith("._")]
    assert len(runs) == 7202
    profile = load_profile(support.PROFILE)
    chosen = [c.label for c in AgentOpsTraceReader().iter_artefacts(_Tree(labels), profile)]
    assert len(chosen) == 3360 and chosen == sorted(chosen)
    facets = [parse_label(lab) for lab in chosen]
    assert all(f is not None and (f.condition == "adversarial" or f.domain == "safety") for f in facets)
    assert Counter(f.model_dir for f in facets if f is not None)["anthropic_claude-opus-4-7"] == 420
    excludes = profile.data["import"]["exclude"]
    codes: Counter[str] = Counter()
    for lab in labels:
        if lab in chosen or lab.rsplit("/", 1)[-1].startswith("._"):
            continue
        entry = next((e for e in excludes if _match(lab, str(e["glob"]))), None)
        assert entry is not None, lab  # nothing is skipped silently
        codes[str(entry["code"])] += 1
    assert codes == {"select.out_of_scope": 3842, "select.not_execution_artefact": 14}
    census = json.loads((support.REPO / "docs" / "reports" / "phase10i" / "agentops-bench.census.json").read_bytes())
    assert census["scope"]["in_scope"]["files"] == 3360 and census["tar"]["run_files"] == 7202
