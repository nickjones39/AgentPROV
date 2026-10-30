"""The source registry: the only status store (docs/architecture D.3; I.0.2, I.1.1; DoD Q.2; layer L6).

Content: the ``adprov-v1`` source (I.1.1 rows 2 and 3, phase 4); ``agentdyn`` (phase 10; D.6.14: ``a`` the ``v1.k14`` import,
``b``/``c`` stretch parts ``planned``, ``d`` owned by ``drift``, ``history`` ``planned``); ``agentdojo`` · ``head``
(``v0.k11`` + ``v1.k14``, phase 10; D.6.12) and ``agentdojo`` · ``2024-06`` (the ``v0.k11``
importer, phase 6; D.6); ``agentdojo`` · ``live`` (the capture mapper, phase 8; D.10.4), ``autodojo`` · ``live`` (phase 9;
D.11) and ``agentdyn`` · ``live`` (D.11.10), all three ``partial`` (D-720: real-model runs for a declared subset of
configurations, D-721/D-725) and ``autodojo`` · ``rope-slice`` (phase 10, served by ``rope``);
``rope`` · ``head`` (phase 10; D.4.4, D.6.13); the survey's ``agentharm`` part (row 11, phase 6; D.9) and ``agentdojo-runs``
part (phase 10; D.6.15); ``mandate-agentdojo-eval`` (phase 10; D.6.15); and ``foobench``, the self-authored
toy format of the future-framework test (D.12; no support claim, status ``None``). Phase 10d adds 18 AgentDojo-format
sources of the systematic search, each one ``head`` part (``_phase10d``; D.6.17, D-100). Every other source of D.3.3
joins with its importer. Statuses are the **gated** values (D.3.2 rule 1; R-15): a part shows ``planned`` until its importer
exists, ``partial`` with the caveat "full snapshot not yet imported" once the reader, mapper, profile and the product
ingestion path (``agentprov import``, phase 6) exist and its golden fixtures pass in CI, and ``supported`` only after the
full pinned snapshot is imported through that path with zero crashes and the counts are recorded in ``docs/reports/``
(HON-10; D.3.2 rule 4). Round 1 and wave 2 (2026-10-29) imported and sealed every part whose v0.1 target allows it;
``Capability.sealed`` names the sealed corpus that holds a part's executions, for display only (``corpus_id`` keeps the
registry's grouping, which imports key on).

Reader and mapper factories are ``agentprov.``-namespaced ``"module:Class"`` strings resolved lazily
(:func:`agentprov.adapters.runner.resolve_factory`): importing this package imports no adapter family (D.2.1, D.3.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

__all__ = [
    "BACKENDS",
    "EXTERNAL_OWNERS",
    "MAPPERS",
    "READERS",
    "REGISTRY",
    "REGISTRY_DATE",
    "BackendDescriptor",
    "Capability",
    "LicencePolicy",
    "SealedCorpus",
    "SourceRegistration",
    "get_source",
]

Status = Literal["supported", "partial", "planned", "not_possible"]
Role = Literal["source", "mirror", "owned_elsewhere", "compat_oracle", "context", "not_executions"]
#: ``n/a``: a live part releases no evidence of its own; it produces it (D.3.3 row ``agentdojo`` · ``live``).
Evidence = Literal["yes", "partial", "no", "n/a"]

REGISTRY_DATE: Final = "2026-10-30"


@dataclass(frozen=True)
class LicencePolicy:
    spdx: str | None
    licence_ref: str | None = None
    holders: tuple[str, ...] = ()
    data_licence: str | None = None
    policy: Literal["include", "reference", "nc_partition", "forbidden"] = "reference"
    restrictions: tuple[str, ...] = ()
    basis: str = ""
    attribution: tuple[str, ...] = ()
    unassessed: tuple[str, ...] = ()


@dataclass(frozen=True)
class SealedCorpus:
    """A sealed corpus that holds a part's executions, for display only: the README, the user guide and ``agentprov
    info`` show it. Imports never read it; they key on ``Capability.corpus_id`` (owner rows, the default ``--corpus-id``),
    which keeps the registry's grouping."""

    corpus_id: str
    version: str

    @property
    def tag(self) -> str:
        """The annotated tag on the corpus's sealing commit (CLAUDE.md: ``corpus/<corpus_id>/vX.Y.Z``)."""
        return f"corpus/{self.corpus_id}/v{self.version}"


@dataclass(frozen=True)
class Capability:
    part: str
    role: Role = "source"
    evidence: Evidence = "yes"
    import_status: Status | None = None
    live_status: Status | None = None
    caveat: str | None = None
    verification: Literal["verified"] = "verified"
    dialects: tuple[str, ...] = ()
    variants: tuple[str, ...] = ()
    reader: str | None = None
    mapper: str | None = None
    backend: str | None = None
    profile: str | None = None
    via: str | None = None
    mirror_of: str | None = None
    owner: str | None = None
    corpus_id: str | None = None
    #: The sealed corpora holding this part's executions (display only; see :class:`SealedCorpus`).
    sealed: tuple[SealedCorpus, ...] = ()
    requires: tuple[str, ...] = ()
    target_import_status: Status | None = None  # the v0.1 target of I.1.1 (shown beside the gated value, never instead)
    #: Semantics profiles (``<id>@<version>``) the import applies to this part's AERs (C.14; HL H.2.5 ``profiles.semantics``).
    semantics: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceRegistration:
    source_id: str
    name: str
    family: str | None
    capabilities: tuple[Capability, ...]
    licence: LicencePolicy
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BackendDescriptor:
    project: str
    protocol: str = "agentprov-backend/0.1"
    worker_module: str = "agentprov_backend.worker"
    capture_mapper: str = "agentdojo.capture"
    profile: str = "agentdojo-live"
    #: D-666: the session's mapped artefact is the backend's native log (an Inspect ``.eval``), expanded and mapped by
    #: the profile's reader and mapper; the capture log is stored beside it and not mapped (D-665 (b)).
    native_log: bool = False


def _sealed(corpus_id: str, version: str = "0.1.0") -> tuple[SealedCorpus, ...]:
    return (SealedCorpus(corpus_id, version),)


#: Round 1 (sealed 2026-10-29): the eight corpora of the regeneration round.
_ROUND1_SEAL: Final = "; sealed in round 1 as {0} 0.1.0 (tag corpus/{0}/v0.1.0; docs/reports/release/pre-release-checks.md)"
#: Wave 2 (2026-10-29): the gate evidence of a part imported in full and sealed (D.3.2, HON-10).
_WAVE2_SEAL: Final = (
    "full pinned snapshot imported through agentprov import in wave 2 and sealed as {0} 0.1.0 (tag corpus/{0}/v0.1.0; "
    "docs/reports/wave-2-corpora/README.md; seal: docs/reports/release/wave-2-pre-release-checks.md)"
)


def _wave2(corpus_id: str, caveat: str = "") -> str:
    return _WAVE2_SEAL.format(corpus_id) + (f": {caveat}" if caveat else "")


_ADPROV_RELEASE_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --release on 2026-10-08 (docs/reports/adprov/"
    "import-cli-release.json): 17,664 of 17,664 released transcripts verified by the pin's listing digest and sealed, "
    "0 degenerate, every AER valid and every derivation passing tier 4; gates A1, A2 and B pass on the same tree "
    "(docs/reports/migration/, dev mode)"
)

_FOOBENCH_CAVEAT: Final = (
    "self-authored toy format for the future-framework test (D.12); not a real source: it makes no support claim and "
    "has no pinned snapshot"
)

_DTAP_CAVEAT: Final = (
    "implemented in phase 10b step 3 (reader, mapper, profile dtap-bench, catalogue dtap v3, semantics dtap.tools@3 (D-934), "
    "runner items R1-R3); one registered failed execution, ex_dwfig (778 calls), whose PROV is over the worker's output "
    "limit (the size limits of the D-935 addendum): its AER is kept, it has no PROV"
)

_OPENHANDS_CAVEAT: Final = (
    "implemented in phase 10g (reader openhands.events with variants oas-0.28 and oh-1.5, mapper, profiles "
    "openagentsafety and redcode-exec-openhands, catalogue openhands v2, semantics openhands.tools@2); RedCode's "
    "trajectories are deposit-zip members, imported as archive inputs (D-200, member origins D-204)"
)

_CREDLEAK_CAVEAT: Final = (
    "phase 10k (D-260..D-268): census of Zenodo 22737462 v3 (docs/reports/phase10k/census.md); the profile declares "
    "the [withhold] policy of D-265 (planted canary credentials), applied at the seal; a cell holds up to 160 runs, "
    "mapped one execution per run by the runner's multi-execution support (R-10k-1, D-320)"
)

_INSPECT_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --release on 2026-10-08 (docs/reports/inspect/"
    "import-cli-agentharm.json): 6 of 6 logs, 1,056 samples sealed, 0 degenerate, every AER valid and every derivation "
    "passing tier 4; band inspect_ai 0.3.247.dev69 only (other producers are select.dialect_planned); restricted-use "
    "corpus ast-survey-agentharm (AgentHarm use clause)"
)

_GEMINICLI_CAVEAT: Final = (
    "phase 10o (D-330..D-337): reader geminicli.stream_json, mapper, profile code-agent-misalignment-geminicli, catalogue "
    "geminicli v1, semantics geminicli.tools@1; the 2,182 non-empty gemini_cli streams of D-143 are counted; the claude_code, codex_cli and openhands cells are select.out_of_scope; one "
    "execution holding a credential-shaped value is withheld from release by the profile's [withhold] rule (D-336)"
)

_QWENCODE_CAVEAT: Final = (
    "phase 10o part C (D-570..D-578): reader qwencode.json, mapper, profile redcode-exec-qwencode, catalogue qwencode v2, "
    "semantics qwencode.tools@2; 3,300 Qwen Code runs of RedCode-Exec (Zenodo 23168099); the score records and requests "
    "are read from the deposit's supplementary zip, the context pin supp (D-530); 4 outputs cut at 64 KiB are salvaged "
    "(D-577)"
)

_AGENTOPS_CAVEAT: Final = (
    "phase 10i (D-190..D-199): reader, mapper, profile agentops-bench-pilot, catalogue agentops v2, semantics "
    "agentops.tools@2; the 3,360 in-scope runs of D-143, members of the deposit's top-level tar.gz, an archive input "
    "(D-192, D-200), with the tasks/ tree at tag v1.0 as the context pin tasks (runner item R2); the other 3,840 cells "
    "are select.out_of_scope (D-191)"
)

_AUTOGEN_CAVEAT: Final = (
    "phase 10n (D-300..D-306): reader autogen.runs, mapper, profile autogen-guard-placement, catalogue autogen v1, "
    "semantics autogen.tools@1; the 1,080 run rows, one execution per JSONL line (D-301); the 190 non-run rows are "
    "registered by file (phase 7 select.not_execution_artefact, phases 8-9 select.out_of_scope)"
)

_WIRELOG_CAVEAT: Final = (
    "phase 10m (D-280..D-285): reader wirelog.request_response (variants bedrock-converse and anthropic-messages), mapper "
    "wirelog.run_dir, profile what-surrounds, catalogue wirelog v1, semantics wirelog.tools@1; the tools are synthetic "
    "by design (read_file answers from the harness, send_email sends nothing, D-284)"
)

_MCPHUNT_CAVEAT: Final = (
    "phase 10m (D-286..D-289): reader mcphunt.traces (streamed /traces, D-242), mapper mcphunt.trace, profile mcphunt, "
    "catalogue mcphunt v2, semantics mcphunt.tools@2; one execution per streamed trace (D-323), the 64 MiB element "
    "limit in [import] limits, tool results over 1 MiB carved by the trace's byte range (D-218); canary-flagged traces "
    "are withheld by the profile's issue rule (D-289, D-311); a recompute of the sealed corpus rebuilds its ingest-limit "
    "overrides from the recorded profile (D-1001)"
)

READERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "adprov.transcript_v1": "agentprov.adapters.adprov.dialect:TranscriptV1Reader",
        "agentdojo.tracelogger": "agentprov.adapters.agentdojo.dialect:TraceLoggerReader",
        "agentdojo.results_container": "agentprov.adapters.agentdojo.results_reader:ResultsContainerReader",
        "agentops.trace": "agentprov.adapters.agentops.dialect:AgentOpsTraceReader",
        "autogen.runs": "agentprov.adapters.autogen.dialect:AutoGenRunsReader",
        "agentprov.capture": "agentprov.adapters.agentdojo.capture_reader:CaptureLogReader",
        "credleak.cell": "agentprov.adapters.credleak.dialect:CredleakCellReader",
        "dtap.trajectory": "agentprov.adapters.dtap.dialect:DtapTrajectoryReader",
        "foobench.jsonl": "agentprov.adapters.foobench.dialect:FooJsonlReader",
        "geminicli.stream_json": "agentprov.adapters.geminicli.dialect:GeminiStreamReader",
        "inspect.eval": "agentprov.adapters.inspect.dialect:InspectEvalReader",
        "mcphunt.traces": "agentprov.adapters.mcphunt.dialect:McpHuntReader",
        "openhands.events": "agentprov.adapters.openhands.dialect:OpenHandsEventsReader",
        "qwencode.json": "agentprov.adapters.qwencode.dialect:QwenJsonReader",
        "wirelog.request_response": "agentprov.adapters.wirelog.dialect:WireLogReader",
    }
)
MAPPERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "adprov.transcript_v1": "agentprov.adapters.adprov.mapper:TranscriptV1Mapper",
        "agentdojo.tracelogger": "agentprov.adapters.agentdojo.mapper:TraceLoggerMapper",
        "agentdojo.capture": "agentprov.adapters.agentdojo.capture_mapper:AgentDojoCaptureMapper",
        "agentops.trace": "agentprov.adapters.agentops.mapper:AgentOpsMapper",
        "autogen.runs": "agentprov.adapters.autogen.mapper:AutoGenMapper",
        "credleak.cell": "agentprov.adapters.credleak.mapper:CredleakMapper",
        "dtap.trajectory": "agentprov.adapters.dtap.mapper:DtapMapper",
        "foobench.jsonl": "agentprov.adapters.foobench.mapper:FooMapper",
        "geminicli.stream_json": "agentprov.adapters.geminicli.mapper:GeminiStreamMapper",
        "inspect.eval": "agentprov.adapters.inspect.mapper:InspectEvalMapper",
        "mcphunt.trace": "agentprov.adapters.mcphunt.mapper:McpHuntMapper",
        "openhands.events": "agentprov.adapters.openhands.mapper:OpenHandsMapper",
        "qwencode.json": "agentprov.adapters.qwencode.mapper:QwenJsonMapper",
        "wirelog.run_dir": "agentprov.adapters.wirelog.mapper:WireLogMapper",
    }
)
#: Backends are separate uv projects addressed by id, never import targets (D.3.1); the descriptor names the capture
#: mapper and the live profile of the sessions they write.
BACKENDS: Final[Mapping[str, BackendDescriptor]] = MappingProxyType(
    {
        "agentdojo": BackendDescriptor(project="backends/agentdojo", capture_mapper="agentdojo.capture", profile="agentdojo-live"),
        "autodojo": BackendDescriptor(project="backends/autodojo", capture_mapper="agentdojo.capture", profile="autodojo-live"),
        "agentdyn": BackendDescriptor(project="backends/agentdyn", capture_mapper="agentdojo.capture", profile="agentdyn-live"),
        # D-662: the Inspect harness, one environment per benchmark (backends/inspect/envs/<benchmark>)
        "inspect-agentharm": BackendDescriptor(project="backends/inspect/envs/agentharm",
                                               worker_module="agentprov_backend_inspect.worker",
                                               capture_mapper="inspect.eval", profile="agentharm-live", native_log=True),
    }
)

#: D-720: the declared subset of a ``partial`` live part; every live part says the same.
_LIVE_SUBSET: Final = (
    "partial: real-model runs are admitted for local model servers (endpoints.toml local = true, loopback only) with "
    "consent, and for API endpoints only with consent, a call cap and a USD cost cap (--max-calls, --max-cost-usd), "
    "under --containment with the D-664 egress allowlist (D-721, D-725, D-726), with the native LLM element only"
)
#: D-722 step 2 (user approval of the pilot, D-729): the pilot's record, naming only the endpoint classes the part ran.
_PILOT: Final = (
    "real-model pilot 2026-10-22, approved by the user (D-722, D-729): {runs} through agentprov run "
    "(docs/reports/live-pilot/); working corpora, not sealed"
)
_LIVE_UNSEALED: Final = (
    "Live corpora cannot be sealed in this build, so no live corpus supports a \"Live Capture\" claim (U-18)"
)

_AGENTDOJO_LIVE_CAVEAT: Final = (
    _LIVE_SUBSET + ", or gateway_compat for a local model server (D-829, the user's decision 2026-10-28, for preset runs "
    "and the --tune-jobs sweep; the pilot ran native only). "
    + _PILOT.format(runs="local qwen3-8b-abliterated-v2 (8 cells), OpenRouter openai/gpt-4o-mini (4 cells), Anthropic "
                    "claude-haiku-5-5 (4 cells)")
    + " (--defence none only). " + _LIVE_UNSEALED + ". The backend backends/agentdojo runs stock agentdojo 0.1.35 "
    "(capture mapper agentdojo.capture, profile agentdojo-live; the live-versus-native check on every session); a "
    "defence runs only if the live profile allows it (D-670, D-677)"
)

_AGENTHARM_LIVE_CAVEAT: Final = (
    "partial (D-741, pilot-style like D-720): real-model runs are admitted for OpenAI-chat endpoints only: a local model "
    "server (loopback) with consent, or an API endpoint with consent, a call cap and a USD cost cap (--max-calls, "
    "--max-cost-usd), under --containment with the D-664 egress allowlist (D-721, D-725, D-726). Under the caps an "
    "Inspect cell is bounded by D-740: --message-limit is required, every judge uses the agent's model, --cell-size "
    "defaults to 1, and the worker allows one retry per model call. The backend inspect-agentharm (inspect_ai 0.3.263, "
    "inspect_evals 0.20.0, the pinned AgentHarm dataset) runs cells through Inspect's eval(); the cell's .eval log is "
    "mapped by the unchanged inspect.eval reader and mapper (AER mode import, evidence by source: Inspect's own record "
    "of the run), and its capture/0.1 wire log is stored, not mapped. Real-model probe 2026-10-23, approved by the "
    "user (D-667, D-722, D-744): API endpoint class, OpenRouter openai/gpt-4o-mini as agent and both judges, 4 samples "
    "of the harmful split through agentprov run (docs/reports/inspect-harness/probe-d667.md); working corpora, not "
    "sealed. Live corpora cannot be sealed in this build (U-18). Restricted-use corpus, private (D-668)"
)

_AUTODOJO_LIVE_CAVEAT: Final = (
    _LIVE_SUBSET + "; --defence none only. " + _PILOT.format(runs="local qwen3-8b-abliterated-v2 (2 cells)") + ". "
    + _LIVE_UNSEALED + ". Isolated environment backends/autodojo (fork @ aa458794; profile autodojo-live; the capture mapper "
    "agentdojo.capture is shared with agentdojo · live); the autodojo attack replays a verified fork cache. ROPE-hosted "
    "AutoDojo runs cannot be reproduced (unreleased harness revision, D.11.6); live runs are new executions, and the "
    "ROPE import part (autodojo-via-rope) is a separate phase-10 part"
)
#: Owners that are not registry sources (D.3.1): their bytes are registered ``select.owned_elsewhere`` and never imported.
EXTERNAL_OWNERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "ext:agentlab": "AgentLAB (TanqiuJiang/AgentLAB @ 36f58e60c36bbd6d5b8e61d50d7db7d9ea7258d7, arXiv:2602.16901, MIT): "
        "its long-horizon attack artefacts and victim traces, vendored byte-identically in ROPE agentlab/res/**",
    }
)

_ROPE_HEAD_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --verify-against-pin --release on 2026-10-10 (docs/reports/"
    "rope/import-cli-rope.json): 10,791 of 10,791 logs at 64495e16 sealed (10,789 agent_execution, 2 outcome-only; 9,366 "
    "clean, 1,425 with issues), 0 degenerate, every AER valid and every derivation passing tier 4; every observed count of "
    "the profile reproduced, and the released security corrections recomputed beside the recorded values, never over them "
    "(198 slack IT5, 260 dailylife IT7, 220 github IT1 logs; docs/reports/rope/rope-q8.json); agentlab/res/** is "
    "AgentLAB's (select.owned_elsewhere, owner ext:agentlab); no second import of this snapshot was run, so determinism "
    "across --jobs is not shown for it"
)

_AUTODOJO_ROPE_SLICE_CAVEAT: Final = (
    "served by source rope (via): the 2,847 ROPE-hosted AutoDojo-attack logs (3 models x 949 cells, ROPE-defended only) "
    "are imported, owned and counted under rope (full import recorded in docs/reports/rope/import-cli-rope.json; the slice "
    "figures are in docs/reports/rope/rope-q8.json); the payload of each slot is linked to the optimiser caches by content "
    "(autodojo.payload_cache_link@1, class I) with its ambiguity set, since neither the cache nor the variant is logged; "
    "the AutoDojo paper's other defences and models are unreleased, so the part stays partial; the slice is sealed in round 1 "
    "within rope 0.1.0 (tag corpus/rope/v0.1.0; docs/reports/release/pre-release-checks.md)"
)

_AGENTDOJO_HEAD_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --verify-against-pin --release on 2026-10-11 (docs/reports/"
    "agentdojo/import-cli-head.json): 36,679 of 36,679 089ed468 logs sealed (24,914 v0.k11, 11,764 v1.k14, 1 "
    "v1.k14.incomplete; 207 outcome-only), 0 degenerate, every AER valid and every derivation passing tier 4; every "
    "observed count of the profile reproduced (census-head.json); ext.agentdojo.committed_no_later_than (all 36,679) and "
    "benchmark_era (the 24,914 v0.k11 logs) are written because the history index was cached for that import "
    "(agentprov fetch --history, user consent; D.6.16): without the index neither field is written"
)

_MANDATE_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --verify-against-pin --release on 2026-10-11 (docs/reports/"
    "mandate/import-cli-mandate.json): 396 of 396 logs at fa62a977 sealed clean, 0 degenerate, every AER valid and every "
    "derivation passing tier 4; the census (240 declines, 27 solvability pre-pass files) and the investigation's outcome "
    "table reproduce; the allows are inferred from the absence of a decline (class I); the publisher of the repository is "
    "unverified (licence basis recorded verbatim) and the corpus is narrow (one model, one suite, 396 runs)"
)

_SURVEY_RUNS_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --verify-against-pin --release on 2026-10-11 (docs/reports/"
    "survey/import-cli-agentdojo-runs.json): 3,243 of 3,243 logs at 89c4db2c sealed (59 with issues), 0 degenerate, every "
    "AER valid and every derivation passing tier 4; the census (11 run-error outcomes, 48 iteration-capped traces, 105 "
    "solvability pre-pass files) and the investigation's aggregates reproduce; the model id is read from the results "
    "directory (it is in no record) and the code that wrote the logs is the pinned submodule plus three patches that are "
    "not in the pinned tree (structural rules cited as class-I twins)"
)

_AGENTDYN_A_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --verify-against-pin --release on 2026-10-11 (docs/reports/"
    "agentdyn/import-cli-agentdyn.json): the 38,281 variant-A (v1.k14) logs of the 47,723 runs/ files at 5353cf76 sealed "
    "(2,377 with issues), 0 degenerate, every AER valid and every derivation passing tier 4; the other 9,442 files are "
    "variants B and C and are registered select.dialect_planned (not mapped), the 949 DRIFT copies select.owned_elsewhere; "
    "directory names are publisher-asserted curation labels (class I), the model, defence and provider come from them; "
    "SEM fails closed on the three new suites (agentdojo.suites@1 has no tool tables for them; counts in docs/reports/"
    "agentdyn/sem-unknown-tools.json); no second import of this snapshot was run, so determinism across --jobs is not "
    "shown for it; from 2026-10-13 the part reads agentdojo.suites@3, whose reviewed tables label AgentDyn's tools "
    "(regeneration-batch item 27 (b)); the stored derivation keeps @1 until the next re-derive"
)
_AGENTDYN_LIVE_CAVEAT: Final = (
    _LIVE_SUBSET + ". " + _PILOT.format(runs="local qwen3-8b-abliterated-v2 (2 cells)") + ". " + _LIVE_UNSEALED
    + ". The backend backends/agentdyn runs AgentDyn from its own pinned code (SaFo-Lab/AgentDyn @ "
    "5353cf76; D.11.10, D-680..D-688), capture mapper agentdojo.capture with profile agentdyn-live; every defence and "
    "the gateway_compat element are refused. AgentDyn's tools read the clock and the random generator, so a re-run is "
    "not a reproduction (agentdyn.art.nondeterministic_tools)"
)

_AGENTDOJO_2024_06_CAVEAT: Final = (
    "full pinned snapshot imported through agentprov import --fetch --release on 2026-10-08 (docs/reports/agentdojo/"
    "import-cli-2024-06.json): 18,241 of 18,241 c274885 logs sealed (207 outcome-only, 7 Mixtral), 0 degenerate, every "
    "AER valid and every derivation passing tier 4; gate R passes (gate-r-full.json)"
)

def _phase10d(source_id: str, name: str, caveat: str, licence: LicencePolicy, *, variants: tuple[str, ...] = ("v1.k14",),
              evidence: tuple[str, ...] = ("sources/agentdojo-format-candidates.md", "verify/agentdojo-format-candidates.md",
                                           "docs/reports/systematic-search/candidates/agentdojo-format-shortlist.md"),
              semantics: tuple[str, ...] = ("agentdojo.suites@2",)) -> SourceRegistration:
    """A phase-10d AgentDojo-format source (D-100): one ``head`` part, ``supported`` since its wave-2 import and seal, mapped
    by the TraceLogger mapper with the profile and corpus of the source's own id (D-94), read with ``agentdojo.suites@2`` (R9,
    D-115: the SEM rules' twins for unverified harnesses, D-86; CrAIBench's reviewed tables, D-110)."""
    return SourceRegistration(
        source_id=source_id,
        name=name,
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2(source_id, caveat),
                dialects=("agentdojo.tracelogger",),
                variants=variants,
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile=source_id,
                corpus_id=source_id,
                sealed=_sealed(source_id),
                semantics=semantics,
            ),
        ),
        licence=licence,
        evidence_refs=evidence,
    )


REGISTRY: Final[tuple[SourceRegistration, ...]] = (
    SourceRegistration(
        source_id="agentdojo",
        name="AgentDojo (ethz-spylab/agentdojo) native TraceLogger run logs",
        family="agentdojo",
        capabilities=(
            # Phase 10 (D.6.12): the head snapshot @089ed468, mixing v0.k11 and v1.k14 logs (D.6.1).
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_AGENTDOJO_HEAD_CAVEAT + _ROUND1_SEAL.format("agentdojo-upstream-head"),
                dialects=("agentdojo.tracelogger",),
                variants=("v0.k11", "v1.k14", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="agentdojo-upstream",
                semantics=("agentdojo.suites@2",),
                corpus_id="agentdojo-upstream",
                sealed=_sealed("agentdojo-upstream-head"),
            ),
            Capability(
                part="2024-06",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_AGENTDOJO_2024_06_CAVEAT + _ROUND1_SEAL.format("agentdojo-upstream-2024-06"),
                dialects=("agentdojo.tracelogger",),
                variants=("v0.k11",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="agentdojo-upstream",
                semantics=("agentdojo.suites@2",),
                corpus_id="agentdojo-upstream",
                sealed=_sealed("agentdojo-upstream-2024-06"),
            ),
            # Phase 8 (D.10.4): the live part. Gated value `partial` (D-720: the scripted D.3.2 live gate passes; real-model
            # runs are admitted for the declared subset of the caveat only); the D.3.3 target is `supported`.
            Capability(
                part="live",
                role="source",
                evidence="n/a",
                import_status=None,
                live_status="partial",
                caveat=_AGENTDOJO_LIVE_CAVEAT,
                dialects=("agentprov.capture", "agentdojo.tracelogger"),
                variants=("0.1", "v1.k14"),
                reader=READERS["agentprov.capture"],
                mapper=MAPPERS["agentdojo.capture"],
                backend="agentdojo",
                profile="agentdojo-live",
                requires=("backend:agentdojo",),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti", "Jie Zhang", "Mislav Balunovic", "Luca Beurer-Kellner", "Marc Fischer",
                     "Florian Tramèr"),
            data_licence="none",
            policy="include",
            basis="MIT by repository; data licence not separately stated",
            attribution=("LICENSE (MIT, (c) 2024 Debenedetti et al.)", "CITATION.bib: arXiv:2406.13352"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("sources/agentdojo.md", "verify/agentdojo.md", "audit/legacy_replay.md §2"),
    ),
    # Phase 10 (D.6.14): AgentDyn, variant A (`v1.k14`) mapped; B and C are stretch (AD-10 row 21), D is DRIFT's.
    SourceRegistration(
        source_id="agentdyn",
        name="AgentDyn (SaFo-Lab/AgentDyn) run logs",
        family="agentdojo",
        capabilities=(
            Capability(
                part="a",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_AGENTDYN_A_CAVEAT + _ROUND1_SEAL.format("agentdyn-a"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="agentdyn",
                semantics=("agentdojo.suites@3",),
                corpus_id="agentdyn",
                sealed=_sealed("agentdyn-a"),
            ),
            Capability(
                part="b",
                role="source",
                evidence="yes",
                import_status="partial",
                target_import_status="partial",
                caveat=_wave2("agentdyn-b", "assigned to this part by the profile's variant_labels (the importer of part a "
                "records the files as select.dialect_planned); Progent, vendored AgentDojo 0.1.29, v0.k11, 5,184 logs, "
                "mapped since D-933 (profile agentdyn v4: part b's observed counts measured over the full pinned snapshot, "
                "5,184 sealed, 0 crashes); it stays partial, the v0.1 target of this stretch part (I.1.1)"),
                dialects=("agentdojo.tracelogger",),
                variants=("v0.k11",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="agentdyn",
                semantics=("agentdojo.suites@3",),
                corpus_id="agentdyn",
                sealed=_sealed("agentdyn-b"),
            ),
            Capability(
                part="c",
                role="source",
                evidence="yes",
                import_status="partial",
                target_import_status="partial",
                caveat=_wave2("agentdyn-c", "assigned to this part by the profile's variant_labels (the importer of part a "
                "records the files as select.dialect_planned); re-keyed copies of AgentDyn's own history blobs (edge E11), "
                "drift.k18.messages, 4,258 logs, mapped by the DRIFT build (D-270, regeneration-batch item 22); it stays "
                "partial: tool outputs are DRIFT's isolated copies, edited or not (drift.tool_output_post_isolation@1)"),
                dialects=("agentdojo.tracelogger",),
                variants=("drift.k18.messages",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="agentdyn",
                semantics=("agentdojo.suites@3",),
                corpus_id="agentdyn",
                sealed=_sealed("agentdyn-c"),
            ),
            Capability(
                part="d",
                role="owned_elsewhere",
                evidence="yes",
                import_status=None,
                caveat="949 DRIFT runs vendored under src/agentdojo/defenses/drift/runs, byte-identical to the head of the drift source "
                "(edge E09); not selected here (select.owned_elsewhere, owner drift)",
                dialects=("agentdojo.tracelogger",),
                variants=("drift.k18.conversations",),
                owner="drift",
            ),
            Capability(
                part="history",
                role="source",
                evidence="yes",
                import_status="planned",
                caveat="16,795 superseded run-log blobs in git history (16,175 distinct executions, incl. Claude Haiku and "
                "Sonnet 4.5); opt-in; fingerprint deduplication is deferred (AD-10 row 7); this build: the first slice is "
                "pinned (pin history, regeneration-batch item 95, R-10j-2), the 621 logs (620 drift.k18.messages, one v1.k14.incomplete) of "
                "runs/gpt-4o-mini-2024-07-18-drift/ at 785b9127, not fetched or imported in v0.1 (deferred to v0.2 with the "
                "fingerprint deduplication, docs/reports/wave-2-corpora/README.md); the other superseded blobs stay planned",
                dialects=("agentdojo.tracelogger",),
                variants=("drift.k18.messages", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="agentdyn",
                semantics=("agentdojo.suites@3",),
                corpus_id="agentdyn",
            ),
            # D.11.10 (D-684): the live part, AgentDyn run from its own pinned code. Gated value `partial`, promoted with
            # the other two live parts (D-720).
            Capability(
                part="live",
                role="source",
                evidence="n/a",
                import_status=None,
                live_status="partial",
                caveat=_AGENTDYN_LIVE_CAVEAT,
                dialects=("agentprov.capture", "agentdojo.tracelogger"),
                variants=("0.1", "v1.k14"),
                reader=READERS["agentprov.capture"],
                mapper=MAPPERS["agentdojo.capture"],
                backend="agentdyn",
                profile="agentdyn-live",
                requires=("backend:agentdyn",),
                semantics=("agentdojo.suites@3",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti", "Jie Zhang", "Mislav Balunovic", "Luca Beurer-Kellner", "Marc Fischer",
                     "Florian Tramèr"),
            data_licence="none",
            policy="include",
            basis="MIT as declared; not legally settled",
            attribution=("arXiv:2602.03117",
                         "LICENSE (MIT; the only copyright line is the AgentDojo authors' (c) 2024; AgentDyn adds none of its own)"),
            unassessed=("the AgentDyn authors' own contributions (run logs, new suites) carry no separate licence statement",
                        "model-provider terms on redistributing model outputs"),
        ),
        evidence_refs=("sources/agentdyn.md", "verify/agentdyn.md"),
    ),
    SourceRegistration(
        source_id="autodojo",
        name="AutoDojo (xhOwenMa/AutoDojo): live capture and the ROPE-hosted attack slice",
        family="agentdojo",
        capabilities=(
            # Phase 9 (D.11): the live part. Gated value `partial` (D-720), as agentdojo · live.
            Capability(
                part="live",
                role="source",
                evidence="n/a",
                import_status=None,
                live_status="partial",
                caveat=_AUTODOJO_LIVE_CAVEAT,
                dialects=("agentprov.capture", "agentdojo.tracelogger"),
                variants=("0.1", "v1.k14"),
                reader=READERS["agentprov.capture"],
                mapper=MAPPERS["agentdojo.capture"],
                backend="autodojo",
                profile="autodojo-live",
                requires=("backend:autodojo",),
                semantics=("agentdojo.suites@3",),
            ),
            # Phase 10 (D.4.4, D.6.13): the ROPE-hosted AutoDojo-attack slice, imported through source rope (via); the
            # profile autodojo-via-rope carries the payload-cache provenance the ROPE mapping consults.
            Capability(
                part="rope-slice",
                role="source",
                evidence="partial",
                import_status="partial",
                target_import_status="partial",
                caveat=_AUTODOJO_ROPE_SLICE_CAVEAT,
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="autodojo-via-rope",
                via="rope",
                owner="rope",
                corpus_id="rope",
                sealed=_sealed("rope"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Xinhang Ma", "Taoran Li", "Chaowei Xiao", "Zhiyuan Yu", "Ning Zhang", "Yevgeniy Vorobeychik"),
            data_licence="none",
            policy="include",
            basis="MIT by repository (LICENSE line 3: Copyright (c) 2026 Ma, Li, Xiao, Yu, Zhang, Vorobeychik); data "
            "licence not separately stated; the user's own runs of the MIT-licensed fork",
            attribution=("LICENSE (MIT)",),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("sources/autodojo.md", "verify/autodojo.md"),
    ),
    # Phase 10 (D.4.4, D.6.13): ROPE's released runs/ (10,791 v1.k14 logs @ 64495e16), owner of the AutoDojo-attack slice.
    SourceRegistration(
        source_id="rope",
        name="ROPE (xhOwenMa/ROPE) defence-evaluation TraceLogger run logs",
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                live_status="planned",
                target_import_status="supported",
                caveat=_ROPE_HEAD_CAVEAT + _ROUND1_SEAL.format("rope"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="rope",
                semantics=("agentdojo.suites@2",),
                corpus_id="rope",
                sealed=_sealed("rope"),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Xinhang Ma", "Chaowei Xiao", "William Yeoh", "Ning Zhang", "Yevgeniy Vorobeychik"),
            data_licence="none",
            policy="include",
            basis="MIT by repository (LICENSE: Copyright (c) 2026 Ma, Xiao, Yeoh, Zhang, Vorobeychik); no separate data "
            "licence; runs/ falls under the repository licence",
            attribution=("LICENSE (MIT, (c) 2026 Ma et al.)", "ROPE arXiv:2608.27496", "AutoDojo payloads: arXiv:2606.15057",
                         "long-horizon payloads: AgentLAB arXiv:2602.16901"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("sources/rope.md", "verify/rope.md", "verify/autodojo.md"),
    ),
    SourceRegistration(
        source_id="adprov-v1",
        name="AgentDojo-PROV transcript/v1",
        family="adprov",
        capabilities=(
            Capability(
                part="release",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_ADPROV_RELEASE_CAVEAT + _ROUND1_SEAL.format("adprov-v1-release"),
                dialects=("adprov.transcript_v1",),
                variants=("v1",),
                reader=READERS["adprov.transcript_v1"],
                mapper=MAPPERS["adprov.transcript_v1"],
                profile="adprov-v1",
                semantics=("agentdojo.suites@2",),
                corpus_id="adprov-v1",
                sealed=_sealed("adprov-v1-release"),
            ),
            Capability(
                part="converted-legacy",
                role="compat_oracle",
                evidence="partial",
                import_status=None,
                caveat="derived data only (timing stubbed); superseded by the native import agentdojo · 2024-06 (full gate R "
                "passed 2026-10-08: R1/R2 18,027/18,027 bytes, J.4.6); kept as the compat oracle of gates A1, A2 and B and "
                "not released as a corpus; owner of the executions: agentdojo",
                dialects=("adprov.transcript_v1",),
                variants=("v1",),
                reader=READERS["adprov.transcript_v1"],
                mapper=MAPPERS["adprov.transcript_v1"],
                profile="adprov-v1",
                semantics=("agentdojo.suites@2",),
                owner="agentdojo",
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            data_licence="CC-BY-4.0",
            policy="include",
            basis="released transcripts: data CC-BY-4.0, code MIT per the AgentDojo-PROV manifests; derived licence per "
            "U-03 (default inherit), carrying AgentDojo's MIT notice for the embedded benchmark text",
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("baseline/BASELINE.md", "audit/capture.md", "audit/legacy_replay.md", "verify/agentdojo.md §2.2"),
    ),
    # Phase 6 (D.9): the Inspect .eval importer registers the `agentharm` part of the survey source; phase 10 (D.6.15) adds
    # `agentdojo-runs`. The survey's other parts (asb, zenodo-bundled-runs) join with their importers (D.3.3).
    SourceRegistration(
        source_id="agent-security-tools-survey",
        name="Agent Security Tools Survey",
        family="inspect",
        capabilities=(
            Capability(
                part="agentharm",
                role="source",
                evidence="yes",
                import_status="supported",
                                target_import_status="supported",
                caveat=_INSPECT_CAVEAT + _ROUND1_SEAL.format("ast-survey-agentharm"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="survey-agentharm",
                corpus_id="ast-survey-agentharm",
                sealed=_sealed("ast-survey-agentharm"),
                semantics=("inspect.agentharm@2",),
            ),
            # Phase 10 (D.6.15): the AgentDojo run logs of the survey, mapped by the TraceLogger mapper (family agentdojo).
            Capability(
                part="agentdojo-runs",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_SURVEY_RUNS_CAVEAT + _ROUND1_SEAL.format("ast-survey-agentdojo"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="survey-runs",
                corpus_id="ast-survey-agentdojo",
                sealed=_sealed("ast-survey-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("Jhih-Jhong Lin",),
            data_licence="CC-BY-4.0",
            policy="include",
            restrictions=("AgentHarm task data: MIT License with an additional clause (use only to improve AI safety and "
                          "security)",),
            basis="CC-BY-4.0 (repository and Zenodo); AgentHarm data per HF ai-safety-institute/AgentHarm @ e23b3fe6 card",
            attribution=("AgentHarm (c) 2024 Gray Swan AI and UK AI Safety Institute, MIT License with an additional clause",
                         "inspect_evals (MIT)"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("sources/agent-security-tools-survey.md §5", "verify/agent-security-tools-survey.md §2"),
    ),
    # Phase 10 (D.6.15): Mandate-AgentDojo-Eval, 396 AgentDojo 0.1.35 banking logs of an action-gating defence.
    SourceRegistration(
        source_id="mandate-agentdojo-eval",
        name="Mandate-AgentDojo-Eval (jwilliamsc/mandate-agentdojo-eval)",
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_MANDATE_CAVEAT + _ROUND1_SEAL.format("mandate-agentdojo-eval"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="mandate-agentdojo-eval",
                corpus_id="mandate-agentdojo-eval",
                sealed=_sealed("mandate-agentdojo-eval"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Mandate Labs (asserted; publisher unverified)",),
            data_licence="none",
            policy="include",
            basis="MIT as declared; publisher unverified",
            attribution=("LICENSE (MIT, Copyright (c) 2026 Mandate Labs)",
                         "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=(
                "publisher identity: the repository owner jwilliamsc is not verifiably the Mandate Labs of the LICENSE",
                "model-provider terms on redistributing model outputs",
            ),
        ),
        evidence_refs=("sources/mandate-agentdojo-eval.md", "verify/mandate-agentdojo-eval.md"),
    ),
    # Phase 10b (D.16; D-26, D-28, D-29): DTap-Bench, the `dtap` family; imported in full and sealed in wave 2.
    SourceRegistration(
        source_id="dtap",
        name="DTap-Bench (AI-Secure/DTap-Bench-Agent-Trajectories with AI-Secure/DecodingTrust-Agent-Platform)",
        family="dtap",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("dtap-bench", _DTAP_CAVEAT),
                dialects=("dtap.trajectory",),
                variants=("v1",),
                reader=READERS["dtap.trajectory"],
                mapper=MAPPERS["dtap.trajectory"],
                profile="dtap-bench",
                corpus_id="dtap-bench",
                sealed=_sealed("dtap-bench"),
                semantics=("dtap.tools@3",),  # D-934: dtap.tools@2 on catalogue dtap 3 (D-607 pattern)
            ),
        ),
        licence=LicencePolicy(
            spdx="Apache-2.0",
            data_licence="Apache-2.0",
            policy="include",
            basis="Apache-2.0 per both dataset cards; upstream AI-secure/DecodingTrust-Agent LICENSE (e0e38455); no LICENSE "
            "or NOTICE file in either dataset; secrets decision option A, include (D.16.13; D-29 item 10)",
            attribution=("Chen et al., DecodingTrust-Agent Platform (DTap), arXiv:2605.04808",
                         "AI-Secure/DTap-Bench-Agent-Trajectories @ 836caf2f",
                         "AI-Secure/DecodingTrust-Agent-Platform @ a3edc9b7"),
            unassessed=("model-provider terms on redistributing model outputs",
                        "vendored sandbox datasets inside tool results (Salesforce, PayPal and others)"),
        ),
        evidence_refs=("sources/dtap.md", "verify/dtap.md", "docs/reports/systematic-search/candidates/dtap-bench.md"),
    ),
    # Phase 10g (D.17; D-170-D-179): the OpenHands event-stream family, imported and sealed in wave 2.
    SourceRegistration(
        source_id="openagentsafety",
        name="OpenAgentSafety (sani903/OpenAgentSafety): OpenHands trajectories of five models on 352 safety tasks",
        family="openhands",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("openagentsafety", _OPENHANDS_CAVEAT),
                dialects=("openhands.events",),
                variants=("oas-0.28",),
                reader=READERS["openhands.events"],
                mapper=MAPPERS["openhands.events"],
                profile="openagentsafety",
                corpus_id="openagentsafety",
                sealed=_sealed("openagentsafety"),
                semantics=("openhands.tools@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            data_licence="MIT",
            policy="include",
            basis="LICENSE (MIT) at 857798ff; secret-like strings kept as published (option A, D-179)",
            attribution=("OpenAgentSafety (sani903/OpenAgentSafety @ 857798ff), MIT", "built on TheAgentCompany and Sotopia"),
            unassessed=("model-provider terms on redistributing model outputs",
                        "third-party text inside tool outputs and browser pages"),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10g/README.md"),
    ),
    SourceRegistration(
        source_id="redcode-exec-openhands",
        name="Which Orders Count? (Zenodo 23168099): OpenHands 1.5.0 runs on RedCode-Exec requests C1-C3",
        family="openhands",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("redcode-exec-openhands", "six trajectory zips, one pin role and one snapshot each (--pin "
                              "<role> --snapshot <role>, D-932); " + _OPENHANDS_CAVEAT),
                dialects=("openhands.events",),
                variants=("oh-1.5",),
                reader=READERS["openhands.events"],
                mapper=MAPPERS["openhands.events"],
                profile="redcode-exec-openhands",
                corpus_id="redcode-exec-openhands",
                sealed=_sealed("redcode-exec-openhands"),
                semantics=("openhands.tools@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            data_licence="CC-BY-4.0",
            policy="include",
            basis="Zenodo record 23168099 licence CC-BY-4.0; the vendored OpenHands keeps its MIT licence",
            attribution=("Which Orders Count? replication package, Zenodo 10.5281/zenodo.23168099 (CC-BY-4.0)",
                         "RedCode-Exec (RedCode benchmark)", "OpenHands 1.5.0 (MIT)"),
            unassessed=("model-provider terms on redistributing model outputs",
                        "RedCode-Exec dataset licence terms beyond the deposit's"),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10g/README.md"),
    ),
    SourceRegistration(
        source_id="foobench",
        name="FooBench (self-authored toy format, D.12)",
        family="foobench",
        capabilities=(
            Capability(
                part="fixture",
                role="source",
                evidence="yes",
                import_status=None,
                caveat=_FOOBENCH_CAVEAT,
                dialects=("foobench.jsonl",),
                variants=("v1",),
                reader=READERS["foobench.jsonl"],
                mapper=MAPPERS["foobench.jsonl"],
                profile="foobench",
                semantics=("foobench.toy@1",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("AgentPROV authors",),
            data_licence="MIT",
            policy="include",
            basis="self-authored synthetic fixtures; the licence of the AgentPROV repository",
        ),
        evidence_refs=("docs/architecture/D_adapters.md D.12", "docs/architecture/K_testing.md K.6.4"),
    ),
    # Phase 10d (D-100..D-109): the verified AgentDojo-format sources of the phase-10c shortlist (D-90..D-96), one corpus
    # per source (D-94). Each part is imported in full and sealed in wave 2 (D.3.2, HON-10).
    _phase10d(
        "interbolt-agentdojo", "Interbolt on AgentDojo (deconvolute-labs/interbolt-agentdojo)",
        "the 1,879 Interbolt denials (tool error 'Blocked by security policy.') are defence decisions, not executions "
        "(agentdojo.defence_denial_message@1, R1, D-113)",
        LicencePolicy(
            spdx="Apache-2.0", holders=("deconvolute-labs (repository owner; the LICENSE carries no copyright line)",),
            data_licence="none", policy="include",
            basis="Apache-2.0 LICENSE at the pin and the README licence badge; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("deconvolute-labs/interbolt-agentdojo (Apache-2.0), commit 43e2b5fa3e7b41b7e26f7c04cc8f371ab98aa875",
                         "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
    ),
    _phase10d(
        "melon-agentdojo", "MELON variants on AgentDojo (xwsdid/MELON)",
        "the 36,679 "
        "upstream run copies of the fork are select.owned_elsewhere (owner agentdojo); MELON-R's sanitising "
        "replacement text is kept as tool output (routing.md R3)",
        LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (the upstream LICENSE kept by the fork)", "xwsdid (fork owner; no own copyright line)"),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin (upstream text, (c) 2024 Debenedetti et al.); the fork adds no licence of its own",
            attribution=("xwsdid/MELON (MIT), commit 71d99dfff5ef98ffb25bac451909f3e10af9e27f", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs and the vendored code"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "glitch-agentdojo", "Glitch on AgentDojo (zanethomas1430-code/Glitch)",
        "the 531 gateway "
        "denials ('DENIED by the gateway:') are defence decisions, not executions (agentdojo.defence_denial_message@1, "
        "R1, D-113)",
        LicencePolicy(
            spdx="MIT",
            holders=("Zane Thomas",),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin, (c) 2026 Zane Thomas; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("zanethomas1430-code/Glitch (MIT, (c) 2026 Zane Thomas), commit 713bb2961fa16980ca8085d372adb200a66cad71", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
    ),
    _phase10d(
        "mohameduk-agentdojo", "UBAG gateway on AgentDojo (mohameduk/agentdojo, branch ubag-gateway-defense)",
        "the 36,679 "
        "upstream run copies are select.owned_elsewhere (owner agentdojo); benchmark_version is not recorded in the "
        "3,145 attacked logs; the 2,731 UBAG denials and holds are defence decisions (verdict deny; "
        "agentdojo.defence_denial_message@1, R1, D-113)",
        LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (the upstream LICENSE kept by the fork)", "mohameduk (fork owner; no own copyright line)"),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin (upstream text, (c) 2024 Debenedetti et al.); the fork adds no licence of its own",
            attribution=("mohameduk/agentdojo (MIT), branch ubag-gateway-defense, commit 3f9d69a1ea96b75e8695653ceee8c3ff088db9b3", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs and the forked code"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
    ),
    _phase10d(
        "tacit-agentdojo", "TACIT AgentDojo trajectories (CSSLab/Tacit)",
        "the models are the "
        "directory labels (the checkpoints are not recorded)",
        LicencePolicy(
            spdx="Apache-2.0",
            holders=("CSSLab (repository owner; the LICENSE carries no copyright line)",),
            data_licence="none",
            policy="include",
            basis="Apache-2.0 LICENSE at the pin; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("CSSLab/Tacit (Apache-2.0), commit 995692d3cd42c32e08cf0db8a5fae55fec272f1a", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "geryon-agentdojo", "Geryon (luiacuaniello/geryon)",
        "v0.k11 logs "
        "without timestamps or versions; the defence (Progent in condition B) is read from the log-set directory; "
        "Progent's 773 tool denials are defence decisions (agentdojo.defence_denial_message@1, R1, D-113); its "
        "JSON-schema argument errors stay tool errors",
        LicencePolicy(
            spdx="Apache-2.0",
            holders=("Luigi Iacuaniello (CITATION.cff; the LICENSE carries no copyright line)",),
            data_licence="none",
            policy="include",
            basis="Apache-2.0 LICENSE at the pin, README section Licence and CITATION.cff; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("luiacuaniello/geryon (Apache-2.0), commit 905aae02c4185454ffbdb64a8bae6a042f6d7047; cite per CITATION.cff", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs", "Progent (Shi et al., arXiv:2504.11703): the defence of condition B"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v0.k11",),
    ),
    _phase10d(
        "hilarytorn-trajectory-poisoning", "In-context trajectory poisoning (HilaryTorn/in-context-trajectory-poisoning)",
        "the agent monitors "
        "under attack are not in the logs",
        LicencePolicy(
            spdx="MIT",
            holders=("Hilary Torn",),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin, (c) 2026 Hilary Torn; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("HilaryTorn/in-context-trajectory-poisoning (MIT, (c) 2026 Hilary Torn), commit d71ab8bc2aa9db35ff443cc81e475e70ee8da215", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
    ),
    _phase10d(
        "yockcheng-prompt-injection-harness", "Prompt injection harness (yockcheng/prompt-injection-harness)",
        "",
        LicencePolicy(
            spdx="Apache-2.0",
            holders=("yockcheng (repository owner; the LICENSE carries no copyright line)",),
            data_licence="none",
            policy="include",
            basis="Apache-2.0 LICENSE at the pin (GitHub reports NOASSERTION; the text is Apache-2.0); the logs embed AgentDojo benchmark text (MIT)",
            attribution=("yockcheng/prompt-injection-harness (Apache-2.0), commit 5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "shreeyavarma-llm-safety", "llm_safety (ShreeyaVarma/llm_safety)",
        "the 58 local Qwen "
        "logs name no model (identity_unresolved, D-92); the 24,914 upstream run copies are select.owned_elsewhere "
        "(owner agentdojo)",
        LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (the upstream LICENSE kept by the fork)", "ShreeyaVarma (fork owner; no own copyright line)"),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin (upstream text, (c) 2024 Debenedetti et al.); the fork adds no licence of its own; the vendored nodejs/ tree carries its own licences and is not data",
            attribution=("ShreeyaVarma/llm_safety (MIT), commit 78d22e4a3daa5e76c77b75076c30ceb1faab22c1", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "gate-agentdojo", "gate (dafarusd/gate)",
        "own copyleft "
        "corpus (D-94); the 215 logs of the directory local name no model (D-92); the gate's 1,101 "
        "denials are defence decisions (agentdojo.defence_denial_message@1, R1, D-113)",
        LicencePolicy(
            spdx="AGPL-3.0-only",
            holders=("Dafarus (dafarusd)",),
            data_licence="none",
            policy="include",
            restrictions=("AGPL-3.0-only: a corpus holding these logs is conveyed under the AGPL-3.0 (corresponding source, the same licence for derived works); kept in its own corpus (D-94)",),
            basis="AGPL-3.0-only per NOTICE and README, LICENSE the AGPL v3 text, (c) 2026 Dafarus; the offer of a commercial licence does not restrict the AGPL grant; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("dafarusd/gate (AGPL-3.0-only, (c) 2026 Dafarus), commit 925b99260beec53d94bd48b587b0bdc33614e3df", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "sentry-agentdojo", "SENTRY (vinhqdang/SENTRY-Anytime-Valid-E-Process-Monitoring-of-LLM-Agent-Action-Streams)",
        "own copyleft "
        "corpus (D-94); the 72 OpenRouter free-router logs name no model (D-92); benchmark_version is not recorded",
        LicencePolicy(
            spdx="AGPL-3.0-only",
            holders=("vinhqdang (repository owner; the LICENSE carries no copyright line of its own)",),
            data_licence="none",
            policy="include",
            restrictions=("AGPL-3.0: a corpus holding these logs is conveyed under the AGPL-3.0 (corresponding source, the same licence for derived works); kept in its own corpus (D-94)",),
            basis="LICENSE is the AGPL v3 text and the README names AGPL-3.0; no 'or later' statement was found, so the stated version is recorded (-only); the logs embed AgentDojo benchmark text (MIT)",
            attribution=("vinhqdang/SENTRY-Anytime-Valid-E-Process-Monitoring-of-LLM-Agent-Action-Streams (AGPL-3.0), commit 938e8be757f4d8168bc7ee5b23f767e431df873f", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "bookkeeper-agentdojo", "Munim (sricursion/bookkeeper)",
        "own copyleft "
        "corpus (D-94); benchmark_version is not recorded; Munim's 180 refusals and holds are "
        "defence decisions (verdict deny; agentdojo.defence_denial_message@1, R1, D-113)",
        LicencePolicy(
            spdx="GPL-3.0-or-later",
            holders=("sricursion (repository owner; the LICENSE carries no copyright line of its own)",),
            data_licence="none",
            policy="include",
            restrictions=("GPL-3.0-or-later: a corpus holding these logs is conveyed under the GPL (corresponding source, the same licence for derived works); kept in its own corpus (D-94)",),
            basis="README section License: GNU General Public License v3.0 or later; LICENSE the GPL v3 text; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("sricursion/bookkeeper (GPL-3.0-or-later), commit 0fe09bb6e8c0c864cee5daa9451f2647c2c846be", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "aiauthz-agentdojo", "aiAuthZ on AgentDojo (Sports-Vision-Inc/aiAuthZ)",
        "own copyleft "
        "corpus (D-94); the logged pipeline names are registry tags, the model is the OpenRouter id of the run "
        "directory; the 9 aiAuthZ denials are defence decisions (agentdojo.defence_denial_message@1, R1, "
        "D-113)",
        LicencePolicy(
            spdx="AGPL-3.0-only",
            holders=("SportsVision AI",),
            data_licence="none",
            policy="include",
            restrictions=("AGPL-3.0: a corpus holding these logs is conveyed under the AGPL-3.0 (corresponding source, the same licence for derived works); kept in its own corpus (D-94)",),
            basis="NOTICE: Copyright (c) 2026 SportsVision AI, licensed under the GNU AGPL v3.0; LICENSE the AGPL v3 text; no 'or later' statement, so the stated version is recorded (-only); the commercial licence offered beside it does not restrict the AGPL grant; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("Sports-Vision-Inc/aiAuthZ (AGPL-3.0, (c) 2026 SportsVision AI), commit 6eaac86ae5bfd8bf7b8a65786a5c77a7c0bce673", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
    ),
    _phase10d(
        "kongminos-agentdojo", "jspace-agentdojo-950 (kongminOS/jspace-agentdojo-950)",
        "the model "
        "(DeepSeek V4-Flash) is asserted from the README's statement, class I (D-92), because no log names it",
        LicencePolicy(
            spdx="MIT",
            holders=("kongminOS",),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin, (c) 2026 kongminOS, and the README licence section (derived data released under MIT); the logs embed AgentDojo benchmark text (MIT)",
            attribution=("kongminOS/jspace-agentdojo-950 (MIT, (c) 2026 kongminOS), commit f341af69498ee36a8d1a2e69040ab70bd8e20a01", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
    ),
    _phase10d(
        "ceferisbarov-agentdojo", "ceferisbarov/agentdojo reruns (optimised injection strings)",
        "the attack arm is "
        "in the origin path only (every attacked log is labelled important_instructions; routing.md R5); the 36,679 "
        "upstream run copies are select.owned_elsewhere (owner agentdojo)",
        LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (the upstream LICENSE kept by the fork)", "ceferisbarov (fork owner; no own copyright line)"),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin (upstream text, (c) 2024 Debenedetti et al.), which covers reruns/; the fork adds no licence of its own",
            attribution=("ceferisbarov/agentdojo (MIT), commit 2273e1cd42493398d1581121c4c4439a8ecc072a", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    SourceRegistration(
        source_id="memo-ozdincer-agentdojo",
        name="memo-ozdincer/agentdojo results containers (circuit-breaker LoRRA adapters and AgentDojo defences)",
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("memo-ozdincer-agentdojo", "phase 10q, D-470..D-479: 13,070 rows of 137 results containers, mapped one execution per "
                       "row by the results-container build of the TraceLogger mapper (D-471); 1,038 exception rows are "
                       "outcome_only with imposed outcomes (D-475); model, LoRA adapter and undocumented attacks from the "
                       "container table (D-474); workstation account paths redacted in the AER (D-476)"),
                dialects=("agentdojo.results_container",),
                variants=("rc.k7", "rc.k12"),
                reader=READERS["agentdojo.results_container"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="memo-ozdincer-agentdojo",
                corpus_id="memo-ozdincer-agentdojo",
                sealed=_sealed("memo-ozdincer-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (the upstream LICENSE kept by the fork)", "memo-ozdincer (fork owner; no own copyright line)"),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin (upstream text, (c) 2024 Debenedetti et al.), which covers results/; the fork adds no licence of its own",
            attribution=("memo-ozdincer/agentdojo (MIT), commit 7c331d978acca38534a3d42951f28a25ba26901b", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the runs"),
            unassessed=("model-provider terms on redistributing model outputs (Llama 3.3 and Qwen2.5 licences; Together AI)",),
        ),
        evidence_refs=("docs/reports/phase10q/README.md", "docs/reports/systematic-search/candidates/phase10e-candidates.md"),
    ),
    _phase10d(
        "linyxus-agentdojo", "Linyxus/agentdojo lacuna-exp (Tacit defence)",
        "the Tacit system "
        "prompts are defence-generated and unrecognised; the extra top-level keys are kept verbatim in "
        "ext.agentdojo.extra",
        LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (the upstream LICENSE kept by the fork)", "Linyxus (fork owner; no own copyright line)"),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin (upstream text, (c) 2024 Debenedetti et al.); the fork adds no licence of its own",
            attribution=("Linyxus/agentdojo (MIT), branch lacuna-exp, commit 698d7ff29cac4bb5dccb5ed2d06f5e8364547a97", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "craibench-agentdojo", "CrAIBench (AthaSSiN/CrAIBench)",
        "v0.k11; the new "
        "suites crypto_trading and chain read the reviewed tool tables of agentdojo.suites@2 (routing.md R8, D-110; "
        "chain knows only the 4 tools labelled alike in both of its code states, the other 5 fail closed); the "
        "memory-injection variant is visible only in the file name",
        LicencePolicy(
            spdx="MIT",
            holders=("Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (the upstream LICENSE kept by the fork)", "AthaSSiN (fork owner; no own copyright line)"),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin (upstream text); the finetune_dataset/ card's CC-BY-4.0 covers that dataset, not the runs",
            attribution=("AthaSSiN/CrAIBench (MIT), commit e41eac1eb2fea00a31c69827bfe83f9722a25702", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v0.k11",),
    ),
    _phase10d(
        "menelaus29-ipi-multidomain", "IPI multidomain agent study (Menelaus29/ipi-multidomain-agent-study)",
        "one snapshot, the main pin; the 107 runs only on two "
        "branches wait for a second snapshot in the same corpus (D-108); the defence is read from the experiment "
        "directory",
        LicencePolicy(
            spdx="MIT",
            holders=("Khue Vu",),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin, (c) 2026 Khue Vu; the logs embed AgentDojo benchmark text (MIT)",
            attribution=("Menelaus29/ipi-multidomain-agent-study (MIT, (c) 2026 Khue Vu), commit ec9c9287889ebec339c4304f01a4a4a99500c491", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        variants=("v1.k14", "v1.k14.incomplete"),
    ),
    _phase10d(
        "llm-lock-agentdojo", "LLMLock (Wakeful-Cloud/llm-lock)",
        "own copyleft corpus "
        "(D-94); no log records the agent's model, so all 53,307 logs are identity_unresolved with the defence arm "
        "from the path (R4, D-92); its detectors abort a run (four arms: terminate decisions, R10, D-116) or redact the "
        "flagged output (three arms) and never refuse a call, so its tool errors are the tools' own",
        LicencePolicy(
            spdx="GPL-3.0",
            holders=("Wakeful-Cloud (repository owner; the LICENSE file is the GPL-3.0 text with no copyright line)",),
            data_licence="none",
            policy="include",
            basis="GPL-3.0 LICENSE at the pin (title line 'GNU GENERAL PUBLIC LICENSE Version 3'); no 'only' or 'or later' statement; own GPL-3.0 corpus (D-94)",
            attribution=("Wakeful-Cloud/llm-lock (GPL-3.0), commit 7bb9915b57e087536b6bdeae0066adb0d8999958", "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
    ),
    # Phase 10f (D-150): WhistleBench, verified in phase 10e (D-144, D-147); Inspect .eval, its own corpus. Semantics
    # profile inspect.whistlebench@2 (D-601 addenda, D.9.14): tool and scorer tables read from the pinned code.
    SourceRegistration(
        source_id="whistlebench",
        name="WhistleBench (legobridge/whistlebench)",
        family="inspect",
        capabilities=(
            Capability(
                part="final-runs",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("whistlebench", "the pinned final_runs/ tree; call links are ambiguous in 3,452 of 9,200 samples and the pruned submit "
                       "call leaves a missing result in 8,401 (routed to the Inspect mapper owner, D-155/D-156); the "
                       "semantics profile inspect.whistlebench@2 reads tools and scorers from the pinned code, "
                       "class I; the email_whistleblowing judgements get no outcome "
                       "(D-601 addendum); unsanctioned whistleblowing is in scope (D-147)"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="whistlebench",
                corpus_id="whistlebench",
                sealed=_sealed("whistlebench"),
                semantics=("inspect.whistlebench@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Kushal Agrawal and co-authors (LICENSE copyright line)",),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin; no separate data licence",
            attribution=("legobridge/whistlebench (MIT), commit 9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc",),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10f/README.md"),
    ),
    # Phase 10f (D-150): the SEAgent artefact's AgentDojo logs, verified in phase 10e (D-144); members of a Zenodo deposit
    # zip, imported as archive inputs since D-200 (member origins D-204); there is a census but no trial import yet.
    SourceRegistration(
        source_id="seagent-agentdojo",
        name="SEAgent artefact: AgentDojo episode logs (Zenodo 23218779)",
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("seagent-agentdojo", "the deposit's members import as archive inputs (D-200) and the mapper reads member origins (D-204); SEAgent guard warnings map as unattributed user messages "
                       "and PVAgent's call-less assistant messages leave orphan tool results (disclosed)"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="seagent-agentdojo",
                corpus_id="seagent-agentdojo",
                sealed=_sealed("seagent-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("the SEAgent authors (artefact record 23218779)",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="README and LICENSES.md of the deposit: SEAgent-authored data CC-BY-4.0, software Apache-2.0; AgentDojo "
                  "benchmark text and runtime code keep the MIT licence",
            attribution=("SEAgent artefact, Zenodo 10.5281/zenodo.23218779 (CC-BY-4.0 data, Apache-2.0 code)",
                         "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10f/README.md"),
    ),
    # D-666 (Inspect harness, 2026-10-22): AgentHarm run live through backends/inspect/envs/agentharm. The live part moved
    # here from agent-security-tools-survey · agentharm, whose logs are a third party's runs (its live_status is unset).
    # Restricted use, private (D-668). Gated value `partial` (D-741: the scripted live gate passes; real-model runs are
    # admitted for the caveat's declared subset only); the caveat records the user-approved D-667 probe (D-744).
    SourceRegistration(
        source_id="agentharm",
        name="AgentHarm (inspect_evals agentharm, agentharm_benign) run live through the Inspect harness",
        family="inspect",
        capabilities=(
            Capability(
                part="live",
                role="source",
                evidence="n/a",
                import_status=None,
                live_status="partial",
                caveat=_AGENTHARM_LIVE_CAVEAT,
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                backend="inspect-agentharm",
                profile="agentharm-live",
                requires=("backend:inspect-agentharm",),
                semantics=("inspect.agentharm@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("UK AI Security Institute (inspect_evals)", "Gray Swan AI and UK AI Safety Institute (AgentHarm)"),
            data_licence="MIT",
            policy="include",
            restrictions=("AgentHarm task data: MIT License with an additional clause (use only to improve AI safety and "
                          "security)",
                          "D-668: restricted-use corpus, private; no public release without a separate user decision"),
            basis="the user's own runs of inspect_evals (MIT) on the AgentHarm dataset (MIT with an AI-safety use clause, "
                  "HF ai-safety-institute/AgentHarm @ e23b3fe6 card); D-668",
            attribution=("AgentHarm (c) 2024 Gray Swan AI and UK AI Safety Institute, MIT License with an additional clause",
                         "inspect_evals (MIT, (c) 2024 UK AI Security Institute)"),
            unassessed=("model-provider terms on redistributing model outputs (agent and judge models)",),
        ),
        evidence_refs=("docs/reports/inspect-harness/design.md",),
    ),
    # Phase 10h (D-180): the two AgentHarm Inspect log sets verified in phase 10e (D-144, D-145 rank 4), each its own
    # restricted-use corpus (AgentHarm use clause), as ast-survey-agentharm. Workstation account paths in model ids,
    # dataset locations and tracebacks wait for the redaction proposal D-182 (regeneration batch).
    SourceRegistration(
        source_id="kexin-xu-01-agentharm",
        name="Kexin-xu-01/agentharm (AgentHarm Inspect logs)",
        family="inspect",
        capabilities=(
            Capability(
                part="logs",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("kexin-xu-01-agentharm", "18 logs name the agent model by a local checkpoint path, redacted in the AER (D-182, regeneration-batch item "
                       "107); 2 "
                       "unfinished logs have no header (select.dialect_planned, 28 samples); restricted-use corpus "
                       "(AgentHarm use clause)"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="kexin-xu-01-agentharm",
                corpus_id="kexin-xu-01-agentharm",
                sealed=_sealed("kexin-xu-01-agentharm"),
                semantics=("inspect.agentharm@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("UK AI Security Institute (LICENSE copyright line, inherited from inspect_evals)",),
            data_licence="MIT",
            policy="include",
            restrictions=("AgentHarm task data: MIT License with an additional clause (use only to improve AI safety and "
                          "security)",),
            basis="MIT LICENSE at the pin; AgentHarm data per HF ai-safety-institute/AgentHarm @ e23b3fe6 card",
            attribution=("Kexin-xu-01/agentharm (MIT), commit 859c34f411fdf8d6a01670da2d2460d21e739e7e",
                         "AgentHarm (c) 2024 Gray Swan AI and UK AI Safety Institute, MIT License with an additional clause",
                         "inspect_evals (MIT, (c) 2024 UK AI Security Institute)"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10h/README.md"),
    ),
    SourceRegistration(
        source_id="fragfuse-agentharm",
        name="zixin22/fragfuse_agentharm (AgentHarm Inspect logs and memory/carrier attack runs)",
        family="inspect",
        capabilities=(
            Capability(
                part="logs",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("fragfuse-agentharm", "the 4 none/none logs (12 samples) are select.not_execution_artefact "
                       "(D-183); task.attack_id is unrecorded for every sample, the memory and carrier attacks being "
                       "visible only in eval.task, the solver plan and ext (D-184); workstation account paths in error tracebacks "
                       "and one metadata field are redacted in ext (D-182, regeneration-batch item 107) and the raw objects "
                       "that name them are withheld (the profile's [withhold]); restricted-use corpus (AgentHarm use clause)"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="fragfuse-agentharm",
                corpus_id="fragfuse-agentharm",
                sealed=_sealed("fragfuse-agentharm"),
                semantics=("inspect.agentharm@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("UK AI Security Institute (LICENSE copyright line, inherited from inspect_evals)",),
            data_licence="MIT",
            policy="include",
            restrictions=("AgentHarm task data: MIT License with an additional clause (use only to improve AI safety and "
                          "security)",),
            basis="MIT LICENSE at the pin; AgentHarm data per HF ai-safety-institute/AgentHarm @ e23b3fe6 card",
            attribution=("zixin22/fragfuse_agentharm (MIT), commit 24cc8aea1b9906bee20fb585007410a5d885933a",
                         "AgentHarm (c) 2024 Gray Swan AI and UK AI Safety Institute, MIT License with an additional clause",
                         "inspect_evals (MIT, (c) 2024 UK AI Security Institute)"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10h/README.md"),
    ),
    # Phase 10i (D.18; D-190..D-199): AgentOps-Bench, the `agentops` family; the in-scope part is imported in full and
    # sealed in wave 2 (archive inputs, D-200).
    SourceRegistration(
        source_id="agentops-bench",
        name="AgentOps-Bench v1.0 pilot (Zenodo 19875693)",
        family="agentops",
        capabilities=(
            Capability(
                part="pilot-v1-seeded",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("agentops-bench", _AGENTOPS_CAVEAT),
                dialects=("agentops.trace",),
                variants=("v1",),
                reader=READERS["agentops.trace"],
                mapper=MAPPERS["agentops.trace"],
                profile="agentops-bench-pilot",
                corpus_id="agentops-bench",
                sealed=_sealed("agentops-bench"),
                semantics=("agentops.tools@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="Apache-2.0",
            holders=("Kunwar Shivam Srivastav (the record's creator)",),
            data_licence="Apache-2.0",
            policy="include",
            basis="Apache-2.0 on the Zenodo record and in the code snapshot's LICENSE; the pilot traces carry no separate licence",
            attribution=("AgentOps-Bench, Zenodo 10.5281/zenodo.19875693 (Apache-2.0)",
                         "code snapshot kunwarshivam-agentops-bench-9153772 (task definitions)"),
            unassessed=("model-provider terms on redistributing model outputs",
                        "web-search fixture content replayed inside tool results"),
        ),
        evidence_refs=("docs/reports/phase10i/README.md", "docs/reports/systematic-search/candidates/phase10e-candidates.md §3.12"),
    ),
    # Phase 10l (D.6.19; D-270..D-279): DRIFT, the `drift.k18` variants mapped by the DRIFT build of the dialect's mapper.
    # `head` is imported in full and sealed in wave 2, and stays `partial` (post-isolation tool outputs); `history` is
    # pre-licence (policy reference, D-279): census and trial only.
    SourceRegistration(
        source_id="drift",
        name="DRIFT (SaFo-Lab/DRIFT) run logs",
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="partial",
                import_status="partial",
                target_import_status="partial",
                caveat=_wave2("drift-head", "1,569 drift.k18.conversations logs at 6fd3df47 mapped through the DRIFT build; it stays partial: tool "
                       "outputs are post-isolation, DRIFT's own "
                       "LLM calls and the agent's prompt are not logged, there is no payload map and no time"),
                dialects=("agentdojo.tracelogger",),
                variants=("drift.k18.conversations",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="drift",
                corpus_id="drift",
                sealed=_sealed("drift-head"),
                semantics=("agentdojo.suites@2",),
            ),
            Capability(
                part="history",
                role="source",
                evidence="partial",
                import_status="planned",
                caveat="1,046 superseded or deleted logs at 53dbc6c5 (end-of-run plan fields), committed before any licence "
                       "statement: licence policy reference (D-279), census and scratch trial only, never released",
                dialects=("agentdojo.tracelogger",),
                variants=("drift.k18.conversations",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="drift",
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Hao Li",),
            data_licence="none",
            policy="include",
            basis="MIT by repository (LICENSE added at 6fd3df47); the history part's blobs pre-date it (policy reference there)",
            attribution=("arXiv:2506.12104 (DRIFT, NeurIPS 2025)", "LICENSE (MIT, Copyright (c) 2026 Hao Li)",
                         "AgentDojo and AgentDyn (MIT): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("sources/drift.md", "verify/drift.md", "docs/reports/phase10l/census.md"),
    ),
    # Phase 10k (D.19; D-260..D-268): Zenodo 22737462, the `credleak` family; imported in full and sealed in wave 2 (the
    # runner's multi-execution whole-file support, R-10k-1, is D-320).
    SourceRegistration(
        source_id="credleak-p15b",
        name="Run data of the credential-leak attack-surface measurement of LLM coding agents (Zenodo 22737462)",
        family="credleak",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("credleak-p15b", _CREDLEAK_CAVEAT),
                dialects=("credleak.cell",),
                variants=("v1",),
                reader=READERS["credleak.cell"],
                mapper=MAPPERS["credleak.cell"],
                profile="credleak-p15b",
                corpus_id="credleak-p15b",
                sealed=_sealed("credleak-p15b"),
                semantics=("credleak.tools@2",),  # D-605: version 2 reads the credleak catalogue version 2
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("the authors of the run-data record 22737462",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="Zenodo record 22737462 metadata: licence cc-by-4.0 (open access); the deposit holds no other licence "
                  "file; planted canary credentials withheld by the profile's [withhold] policy (D-146, D-265)",
            attribution=("Run data and analysis code for \"How Credentials Leak from 'Safe' LLM Coding Agents: An "
                         "Attack-Surface Measurement\", Zenodo 10.5281/zenodo.22737462 (v3, CC-BY-4.0)",),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10k/census.md"),
    ),
    # Phase 10p (D.9.9; D-340..D-348, user-approved 2026-10-13): the control-arena persistent-state archive, Inspect .eval
    # logs in three split zips (D-249) and two tar.zst inputs (D-240), one corpus with one snapshot per part (D-202).
    SourceRegistration(
        source_id="controlarena-persistent",
        name="Control-arena persistent-state evaluation archive (HF idacy, 2026-07-30)",
        family="inspect",
        capabilities=(
            Capability(
                part="zip-3-001",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("controlarena-persistent", "split zip 3-001 (8 parts): 132 logs / 660 samples direct, 413 logs / 1,976 samples in 4 nested zips (D-382); the workstation account "
                       "path in harness text is redacted (D-349, D-182) and the raw objects holding it are withheld (D-604; hyphenated names are left to the release scan); a metadata-only release: "
                       "every execution is withheld at the seal by the profile's [withhold] policy (D-344); no semantics "
                       "profile, so SEM is skipped"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="controlarena-persistent",
                corpus_id="controlarena-persistent",
                sealed=_sealed("controlarena-persistent"),
                semantics=(),
            ),
            Capability(
                part="zip-3-002",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("controlarena-persistent", "split zip 3-002 (8 parts): 31 logs / 153 samples direct, 515 logs / 1,499 samples in 1 nested zip (D-382); the workstation account "
                       "path in harness text is redacted (D-349, D-182) and the raw objects holding it are withheld (D-604; hyphenated names are left to the release scan); a metadata-only release: "
                       "every execution is withheld at the seal by the profile's [withhold] policy (D-344); no semantics "
                       "profile, so SEM is skipped"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="controlarena-persistent",
                corpus_id="controlarena-persistent",
                sealed=_sealed("controlarena-persistent"),
                semantics=(),
            ),
            Capability(
                part="zip-3-003",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("controlarena-persistent", "split zip 3-003 (3 parts): 162 logs / 810 samples; the workstation account "
                       "path in harness text is redacted (D-349, D-182) and the raw objects holding it are withheld (D-604; hyphenated names are left to the release scan); a metadata-only release: "
                       "every execution is withheld at the seal by the profile's [withhold] policy (D-344); no semantics "
                       "profile, so SEM is skipped"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="controlarena-persistent",
                corpus_id="controlarena-persistent",
                sealed=_sealed("controlarena-persistent"),
                semantics=(),
            ),
            Capability(
                part="batch-runs",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("controlarena-persistent", "logs_batch_runs tar.zst: 110 logs / 638 samples; the workstation account "
                       "path in harness text is redacted (D-349, D-182) and the raw objects holding it are withheld (D-604; hyphenated names are left to the release scan); a metadata-only release: "
                       "every execution is withheld at the seal by the profile's [withhold] policy (D-344); no semantics "
                       "profile, so SEM is skipped"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="controlarena-persistent",
                corpus_id="controlarena-persistent",
                sealed=_sealed("controlarena-persistent"),
                semantics=(),
            ),
            Capability(
                part="auditor",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("controlarena-persistent", "agentic_auditor_logs tar.zst: the auditor's 1 input log / 6 samples; the auditor's records are EX-FMT (D-342); the workstation account "
                       "path in harness text is redacted (D-349, D-182) and the raw objects holding it are withheld (D-604; hyphenated names are left to the release scan); a metadata-only release: "
                       "every execution is withheld at the seal by the profile's [withhold] policy (D-344); no semantics "
                       "profile, so SEM is skipped"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="controlarena-persistent",
                corpus_id="controlarena-persistent",
                sealed=_sealed("controlarena-persistent"),
                semantics=(),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("the dataset's authors (Hills, Caspary and Cooper Stickland; dataset card)",),
            data_licence="MIT",
            policy="include",
            basis="dataset card 'license: mit' at revision 84d39e0a; planted and generated credentials withheld by the "
                  "profile's [withhold] policy (D-344)",
            attribution=("idacy/control-arena-persistent-state-eval-archive-2026-07-30 (MIT), revision "
                         "84d39e0a485d7ea6ca10f4ceb2a3fbf88dab0e62",),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md", "docs/reports/phase10p/README.md"),
    ),
    # Phase 10n (D-144, D-145 rank 12): ATIA, verified in phase 10e; Inspect .eval, its own corpus. Semantics profile
    # inspect.atia@1 (D-307 addendum, D.9.15): every tool fail-closed, no scorer claims. Multimodal inputs as attachments
    # (D-308).
    SourceRegistration(
        source_id="atia-benchmark",
        name="ATIA: adversarial tool infiltration benchmark (mattngyn/atia_benchmark)",
        family="inspect",
        capabilities=(
            Capability(
                part="logs",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("atia-benchmark", "one suite (account takeover), 123 samples of google/gemini-2.0-flash "
                       "under inspect_ai 0.3.112; image, audio and video inputs as sample attachments (D-308); the "
                       "semantics profile inspect.atia@1 makes every tool fail-closed and claims no outcome "
                       "(D-307 addendum)"),
                dialects=("inspect.eval",),
                variants=("v2",),
                reader=READERS["inspect.eval"],
                mapper=MAPPERS["inspect.eval"],
                profile="atia-benchmark",
                corpus_id="atia-benchmark",
                sealed=_sealed("atia-benchmark"),
                semantics=("inspect.atia@1",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("mattngyn (repository owner; LICENSE at the pin)",),
            data_licence="none",
            policy="include",
            basis="MIT LICENSE at the pin; no separate data licence",
            attribution=("mattngyn/atia_benchmark (MIT), commit cc71caf55c6f35d7aad440a4a746f44ae39d17c4",),
            unassessed=("model-provider terms on redistributing model outputs", "provenance of the adversarial media inputs"),
        ),
        evidence_refs=("docs/reports/systematic-search/candidates/phase10e-candidates.md §3.5", "docs/reports/phase10n/README.md"),
    ),
    # Phase 10n (D.19; D-300..D-306): the AutoGen guard-placement deposit, the `autogen` family; one execution per JSONL
    # line (D-301), imported in full and sealed in wave 2.
    SourceRegistration(
        source_id="autogen-guard-placement",
        name="AutoGen guard placement (Zenodo 23025259 v1.0)",
        family="autogen",
        capabilities=(
            Capability(
                part="v1.0",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("autogen-guard-placement", _AUTOGEN_CAVEAT),
                dialects=("autogen.runs",),
                variants=("condition", "defense", "injecagent", "team"),
                reader=READERS["autogen.runs"],
                mapper=MAPPERS["autogen.runs"],
                profile="autogen-guard-placement",
                corpus_id="autogen-guard-placement",
                sealed=_sealed("autogen-guard-placement"),
                semantics=("autogen.tools@1",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("the deposit's authors (Zenodo record 23025259)",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="CC-BY-4.0 on the record and in LICENSE-DATA; code MIT (LICENSE); AgentDojo templates and InjecAgent cases MIT (LICENSE-THIRD-PARTY)",
            attribution=("AutoGen guard placement, Zenodo 10.5281/zenodo.23025259 v1.0 (data CC-BY-4.0, code MIT)",
                         "AgentDojo injection templates (MIT) inside the probe passages",
                         "InjecAgent cases (MIT) in the phase-6 runs"),
            unassessed=("model-provider terms on redistributing model outputs (local open-weight model)",),
        ),
        evidence_refs=("docs/reports/phase10n/README.md", "docs/reports/systematic-search/candidates/phase10e-candidates.md §3.15"),
    ),
    # Phase 10m (D.20; D-280..D-285): Zenodo 21944598, the `wirelog` family; imported in full and sealed in wave 2.
    SourceRegistration(
        source_id="what-surrounds",
        name="What surrounds an injection decides whether it works (Zenodo 21944598)",
        family="wirelog",
        capabilities=(
            Capability(
                part="runs-named",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("what-surrounds", _WIRELOG_CAVEAT),
                dialects=("wirelog.request_response",),
                variants=("bedrock-converse", "anthropic-messages"),
                reader=READERS["wirelog.request_response"],
                mapper=MAPPERS["wirelog.run_dir"],
                profile="what-surrounds",
                corpus_id="what-surrounds",
                sealed=_sealed("what-surrounds"),
                semantics=("wirelog.tools@1",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("Shaban Asif (the record's creator)",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="CC-BY-4.0 on the Zenodo record; LICENSE-DATA in the zip: runs_named/, results.csv, attacks.json and "
                  "PAPER.md under CC BY 4.0, code under MIT",
            attribution=("Asif, S. (2026). What surrounds an injection decides whether it works. Data and code. Zenodo. "
                         "https://doi.org/10.5281/zenodo.21944598 (CC BY 4.0)",),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/phase10m/README.md", "docs/reports/systematic-search/candidates/phase10e-candidates.md §3.14"),
    ),
    # Phase 10m (D.21; D-286..D-289): MCPHunt, the `mcphunt` family. Imported in full and sealed in wave 2 (D-323).
    SourceRegistration(
        source_id="mcphunt",
        name="MCPHunt agent traces (HF lihaonan0716/mcphunt-agent-traces)",
        family="mcphunt",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("mcphunt", _MCPHUNT_CAVEAT),
                dialects=("mcphunt.traces",),
                variants=("v2.0.0",),
                reader=READERS["mcphunt.traces"],
                mapper=MAPPERS["mcphunt.trace"],
                profile="mcphunt",
                corpus_id="mcphunt",
                sealed=_sealed("mcphunt"),
                semantics=("mcphunt.tools@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("Haonan Li, Tianjun Sun, Yongqing Wang, Qisheng Zhang (the dataset's authors)",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="CC-BY-4.0 in the dataset card at the pinned revision",
            attribution=("Li, H., Sun, T., Wang, Y., Zhang, Q. (2026). MCPHunt Agent Traces. Hugging Face "
                         "lihaonan0716/mcphunt-agent-traces (CC BY 4.0); arXiv:2604.27819",),
            unassessed=("model-provider terms on redistributing model outputs",
                        "third-party web content in fetch and browser results"),
        ),
        evidence_refs=("docs/reports/phase10m/README.md", "docs/reports/systematic-search/candidates/phase10e-candidates.md §3.11"),
    ),
    # Phase 10o (D.19; D-330..D-337): the gemini_cli part of Zenodo 20404563, the `geminicli` family; imported in full and
    # sealed in wave 2.
    SourceRegistration(
        source_id="code-agent-misalignment-geminicli",
        name="Code-agent agentic misalignment RESULTS_raw, gemini_cli streams (Zenodo 20404563)",
        family="geminicli",
        capabilities=(
            Capability(
                part="results-raw",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("code-agent-misalignment", _GEMINICLI_CAVEAT),
                dialects=("geminicli.stream_json",),
                variants=("v1",),
                reader=READERS["geminicli.stream_json"],
                mapper=MAPPERS["geminicli.stream_json"],
                profile="code-agent-misalignment-geminicli",
                corpus_id="code-agent-misalignment",
                sealed=_sealed("code-agent-misalignment"),
                semantics=("geminicli.tools@1",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("the record's creators (Zenodo 20404563)",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="CC-BY-4.0 on the Zenodo record; the code repository it supplements is MIT (not imported)",
            attribution=("RESULTS_raw, Zenodo 10.5281/zenodo.20404563 (CC-BY-4.0)",
                         "github.com/warmjademe/code_agent_agentic_misalignment @ 1dec4f17 (MIT; cited, not imported)"),
            unassessed=("model-provider terms on redistributing model outputs",
                        "web search results replayed inside tool outputs"),
        ),
        evidence_refs=("docs/reports/phase10o/README.md", "docs/reports/systematic-search/candidates/phase10e-candidates.md §3.13"),
    ),
    # Phase 10j (D-250..D-258; docs/reports/phase10j/): the AgentDojo-format sources phase 10d deferred, imported in full
    # and sealed in wave 2.
    SourceRegistration(
        source_id="authority-caps-agentdojo",
        name="agent-authority-caps: AgentDojo logs under enforced authority caps (Zenodo 23138310)",
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("authority-caps-agentdojo", "21,999 logs of the pinned v2.1.0 zip (18,739 distinct; 3,260 re-packed copies collapse), "
                       "2,813 at level 1 and 19,186 in three declared nested tar.gz (D-250); v1.0 (record 22973266) is contained; "
                       "gpt-6-luna and gpt-6-sol carry no snapshot date"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="authority-caps-agentdojo",
                corpus_id="authority-caps-agentdojo",
                sealed=_sealed("authority-caps-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("Liang-Cheng Chang (dataset creator)",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="README and original-study/LICENSE-DATA (CC-BY-4.0 data; AgentDojo-derived fields MIT); LICENSE-CODE MIT",
            attribution=("Chang, L.-C., agent-authority-caps, Zenodo 10.5281/zenodo.23138310 (v2.1.0; concept 10.5281/zenodo.22973265), CC-BY-4.0",
                         "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/phase10j/census.md §2", "docs/reports/systematic-search/candidates/agentdojo-format-shortlist.md"),
    ),
    SourceRegistration(
        source_id="ipi-defenses-agentdojo",
        name="IPI defences replication package: AgentDojo banking logs under built-in defences (Zenodo 22011266)",
        family="agentdojo",
        capabilities=(
            Capability(
                part="head",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("ipi-defenses-agentdojo", "3,211 logs in three declared nested tar.gz of v4.0.0 (D-251); the README discloses lost "
                       "first-run traces (only complete surviving cells are deposited), an unpinned PI-detector revision and runs 1 "
                       "and 2 over the same instances; benchmark_version not recorded"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="ipi-defenses-agentdojo",
                corpus_id="ipi-defenses-agentdojo",
                sealed=_sealed("ipi-defenses-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("Adil Khan", "Khaled AlKhanbashi", "Azza Mohamed"),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="README 'Licence': code MIT, data and documentation CC BY 4.0",
            attribution=("Khan, AlKhanbashi, Mohamed, replication package, Zenodo 10.5281/zenodo.22011266 (v4.0.0), CC-BY-4.0",
                         "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/phase10j/census.md §3",),
    ),
    SourceRegistration(
        source_id="dca-agentdojo",
        name="DCA AgentDojo artefact v1: logs under DCA, CaMeL and DRIFT (Figshare 32657856)",
        family="agentdojo",
        capabilities=(
            Capability(
                part="v1",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("dca-agentdojo", "13,374 v1.k14 logs of the pinned zip, 1,968 with `:` labels "
                       "(D-56); the url pin is an archive input since D-455 (R-10j-3 resolved); CaMeL tool results without a call "
                       "stay orphan results; 1,025 content repeats kept and disclosed"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="dca-agentdojo",
                corpus_id="dca-agentdojo",
                sealed=_sealed("dca-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
            Capability(
                part="drift",
                role="source",
                evidence="partial",
                import_status="partial",
                target_import_status="partial",
                caveat=_wave2("dca-agentdojo", "2,847 drift.k18.conversations logs mapped by the DRIFT build "
                       "(D-252; RT-7, D-279 addendum: included; 0 of 2,847 attacked runs succeed); imported from the pin of part "
                       "`v1` with `--snapshot drift` (`variant_labels`); it stays partial: tool outputs are post-isolation"),
                dialects=("agentdojo.tracelogger",),
                variants=("drift.k18.conversations",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="dca-agentdojo",
                corpus_id="dca-agentdojo",
                sealed=_sealed("dca-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("the DCA artefact authors (Figshare 32657856)",),
            data_licence="none",
            policy="include",
            basis="Figshare record licence MIT; third_party_licenses/ carries AgentDojo (MIT), CaMeL (Apache-2.0) and DRIFT (MIT)",
            attribution=("DCA AgentDojo artefact v1, Figshare 10.6084/m9.figshare.32657856 (MIT)",
                         "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs",
                         "CaMeL (Apache-2.0) and DRIFT (MIT): the runners of the CaMeL and DRIFT rows (third_party_licenses/)"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/phase10j/census.md §4", "docs/reports/phase10l/census.md"),
    ),
    SourceRegistration(
        source_id="kavach-agentdojo",
        name="Kavach: AgentDojo logs of a runtime tool-call defence (Ishani018/Kavach, three branches)",
        family="agentdojo",
        capabilities=(
            Capability(
                part="main",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("kavach-agentdojo", "223 logs at 53df9545, all also in both branches (D-253); `local` everywhere, model only where a run summary records it (gemma4:26b), "
                       "one directory identity_unresolved at this pin (3 logs; six across the three pins); the 220 agentdojo_slack_gemma_dell logs the authors mark invalid are "
                       "included and disclosed"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="kavach-agentdojo",
                corpus_id="kavach-agentdojo",
                sealed=_sealed("kavach-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
            Capability(
                part="nav-fixer2",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("kavach-agentdojo", "1,518 logs at f2dd7efa (1,477 distinct) (D-253); `local` everywhere, model only where a run summary records it (gemma4:26b), "
                       "six directories identity_unresolved at this pin (150 logs); the 220 agentdojo_slack_gemma_dell logs the authors mark invalid are "
                       "included and disclosed; 650 trajectories recur across the branches in other bytes"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="kavach-agentdojo",
                corpus_id="kavach-agentdojo",
                sealed=_sealed("kavach-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
            Capability(
                part="rearch-forcedformat-fix",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("kavach-agentdojo", "1,518 logs at 6b31a554 (D-253); `local` everywhere, model only where a run summary records it (gemma4:26b), "
                       "five directories identity_unresolved at this pin (66 logs; six across the three pins); the 220 agentdojo_slack_gemma_dell logs the authors mark invalid are "
                       "included and disclosed; 650 trajectories recur across the branches in other bytes"),
                dialects=("agentdojo.tracelogger",),
                variants=("v1.k14", "v1.k14.incomplete"),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="kavach-agentdojo",
                corpus_id="kavach-agentdojo",
                sealed=_sealed("kavach-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("Kavach Team, PES University",),
            data_licence="none",
            policy="include",
            basis="LICENSE (MIT, (c) 2026 Kavach Team, PES University), identical at the three pins",
            attribution=("Ishani018/Kavach (MIT, (c) 2026 Kavach Team, PES University), commits 53df9545, f2dd7efa, 6b31a554",
                         "AgentDojo (MIT, (c) 2024 Debenedetti et al.): the benchmark text embedded in the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/phase10j/census.md §5", "docs/reports/phase10d/deferred.md"),
    ),
    SourceRegistration(
        source_id="drift1-agentdojo",
        name="drift-1 (CGboom-git/drift-1): DRIFT-format logs incl. a PACT-DRIFT arm",
        family="agentdojo",
        capabilities=(
            Capability(
                part="drift",
                role="source",
                evidence="partial",
                import_status="partial",
                target_import_status="partial",
                caveat=_wave2("drift1-agentdojo", "626 new drift.k18.conversations logs (616 gpt-4o-mini, 10 PACT-DRIFT with six extra keys "
                       "and unrecognised CALL ERRORs) mapped by the DRIFT build (D-256); 1,569 DRIFT head copies owned by drift; "
                       "MIT by README badge only (D-93); it stays partial: tool outputs are post-isolation"),
                dialects=("agentdojo.tracelogger",),
                variants=("drift.k18.conversations",),
                reader=READERS["agentdojo.tracelogger"],
                mapper=MAPPERS["agentdojo.tracelogger"],
                profile="drift1-agentdojo",
                corpus_id="drift1-agentdojo",
                sealed=_sealed("drift1-agentdojo"),
                semantics=("agentdojo.suites@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="MIT",
            holders=("CGboom-git (drift-1)", "Hao Li (DRIFT)"),
            data_licence="none",
            policy="include",
            basis="MIT, README badge only; LICENSE file missing (D-93)",
            attribution=("CGboom-git/drift-1 (MIT by README badge), commit 0e28729b4d9a6f466ba4803ccdc18a842c50cd20",
                         "DRIFT (MIT, (c) 2026 Hao Li; arXiv:2506.12104), AgentDojo and AgentDyn (MIT): the code and benchmark text behind the logs"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/phase10j/census.md §7", "docs/reports/phase10l/routing.md"),
    ),
    # Phase 10o part C (D.24; D-570..D-578): the Qwen Code part of Zenodo 23168099, the `qwencode` family; imported in full
    # and sealed in wave 2, with the supplementary zip as a context pin (D-530).
    SourceRegistration(
        source_id="redcode-exec-qwencode",
        name="RedCode-Exec agent runs, Qwen Code part (Zenodo 23168099)",
        family="qwencode",
        capabilities=(
            Capability(
                part="qwen3coder",
                role="source",
                evidence="yes",
                import_status="supported",
                target_import_status="supported",
                caveat=_wave2("redcode-exec-qwencode", _QWENCODE_CAVEAT),
                dialects=("qwencode.json",),
                variants=("v0.21",),
                reader=READERS["qwencode.json"],
                mapper=MAPPERS["qwencode.json"],
                profile="redcode-exec-qwencode",
                corpus_id="redcode-exec-qwencode",
                sealed=_sealed("redcode-exec-qwencode"),
                semantics=("qwencode.tools@2",),
            ),
        ),
        licence=LicencePolicy(
            spdx="CC-BY-4.0",
            holders=("the record's creators (Zenodo 23168099)",),
            data_licence="CC-BY-4.0",
            policy="include",
            basis="CC-BY-4.0 on the Zenodo record",
            attribution=("Which Orders Count? replication package, Zenodo 10.5281/zenodo.23168099 (CC-BY-4.0)",
                         "RedCode-Exec dataset (as redistributed in the package)"),
            unassessed=("model-provider terms on redistributing model outputs",),
        ),
        evidence_refs=("docs/reports/phase10o/part-c.md",),
    ),
)


def get_source(source_id: str) -> SourceRegistration:
    """The registration of ``source_id``; ``KeyError`` when it is not registered."""
    for registration in REGISTRY:
        if registration.source_id == source_id:
            return registration
    raise KeyError(source_id)
