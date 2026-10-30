# B. Existing AgentDojo-PROV audit

Revision: 2026-10-07 r2 — review resolutions and Addendum B applied.

Status: normative for the AgentPROV v0.1 port. Date: 2026-10-07.
Baseline under audit: `~/Desktop/PhD/Labs/AgentDojo-PROV-framework` at
`579a908354b93361efe0905ffb7623256aa96a06` (`master`, working tree clean, 57 tracked files; the annotated tag
`agentprov-baseline-2026-10-07` already points at it) [baseline/BASELINE.md §0, §1.1; RESOLUTIONS consolidator
check 2]. Binding brief: `investigation/DECISIONS.md` D0–D12, Addendum A and Addendum B, with the precedence
Addendum B > Addendum A > main text. Review: `investigation/spec/review/RESOLUTIONS.md` (cited below as
"RESOLUTIONS"); its §3 naming table is mandatory in this section except where Addendum B deviates from it.

This section says, for every artefact of the baseline repository, what AgentPROV does with it, where the
result lives, and why. It also fixes the invariants the port must keep, the audited defects the port must
fix, and the things that must not be ported. It does not define the AER, SEM, capture or PROV formats. Those
belong to their own sections; this section names the modules that implement them only so that every baseline
component has a destination.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in RFC 2119.

**Changes after review (2026-10-07, r2).** RESOLUTIONS findings applied: R-01, R-02 (closed AER fields), R-03
(ids and IRIs), R-04, R-05, R-06, R-09 (rule names), R-13 (seal and register codes), R-16 (capture names), R-17,
R-18, R-20, R-28 (`unit`), R-30, R-31, R-32, R-33, R-34, R-39, R-42, R-47, R-48, R-50, R-52, R-57, R-59, R-63,
R-64, plus the §1.3 dispositions for B and the §3 canonical names. Addendum B rulings applied: AD-01, AD-02,
AD-04, AD-05, AD-07, AD-08 (with its nuance), AD-09, AD-10 (as ruled: a minimal generic `stats` and a ported
`render` are kept), AD-11, AD-12, AD-16 (as ruled: `requires-python = ">=3.14"` with a release-mode refusal below
3.14.8), AD-17, AD-19 and AD-20. In short:
- B.1.1 is no longer the path authority. MN M.1.2 and RESOLUTIONS §3.2 are; the destination columns of B.2–B.5
  are regenerated against them.
- Live code leaves core. It goes to `agentprov_capture` (`capture/`), `agentprov_backend` (`backends/shared/`) and
  the backend projects `backends/agentdojo/` and `backends/autodojo/`. There is no `agentdojo` extra.
- The compat oracle is the five baseline files `build_prov`, `prov_emit`, `labeling`, `validate` and `conformance`,
  ported verbatim (AST-equal) to `prov/compat/adprov_v2_3/`. VAL-05…VAL-12 become new generic validators.
- Replay, historical checkers, the confound probe, `ml_export`, the AgentDojo statistics frame, flow and argument
  baselines, heuristics and the labelling audit are DEFERRED to v0.2 (AD-10). The frozen baseline environment at
  `579a908` serves the old corpus until they are ported.
- The two B.7 challenges are resolved (AD-02, AD-17), and the open questions are dispositioned in B.12.
- No baseline component needs the generic `activity` or `artefact` record kinds that Addendum B adds (AD-15): each
  AgentDojo-PROV concept maps to a specialised kind, and AD-15 requires adapters to prefer those.

---

## B.0 Scope, evidence and conventions

### B.0.1 Evidence base

- The five code audits: `audit/capture.md`, `audit/provenance.md`, `audit/validation.md`,
  `audit/legacy_replay.md` and `audit/corpus.md`. They are cited as [capture §n], [provenance §n],
  [validation §n], [legacy §n] and [corpus §n].
- The frozen baseline: [baseline/BASELINE.md §n]. At that commit the suite gives 362 passed and 1 skipped,
  `recompute --dry-run` reports 0 changed on 17,664 + 18,027 traces, and every graph passes all five
  conformance checks.
- Landscape reports, where a destination depends on them: [landscape/trace_formats.md §n] and
  [landscape/prov_semantics.md §n].
- Code citations use the form `file.py:L1-L2` and refer to commit `579a908`.

**Additional checks made for this section.** All were read-only against the baseline; `git status --porcelain`
was empty afterwards. Scripts and outputs are in `investigation/spec/B_audit_evidence/`.

| Id | Check | Result |
|---|---|---|
| E1 | Re-derive every stored graph with the baseline `build_prov` and compare `json.dumps(doc, indent=2).encode("utf-8")` with the stored bytes (`full_bytes.py`, `golden_bytes.py`) | **Byte-identical: 17,664/17,664 released, 18,027/18,027 converted, 15/15 golden.** No stored graph ends in a newline. Importing `agentdojo_prov.build_prov` does not load the `agentdojo` package. |
| E2 | Scan every stored graph's `adprov:args` string, which is `json.dumps(args, default=str)` (`prov_emit.py:124-127`) (`args_order.py`) | Released: 12,676 of 64,781 activities have args whose key order is not lexicographic, and 313 contain an integral float such as `100.0`. Converted: 12,862 of 68,620, and 1,681. Graphs affected: 8,037 released, 8,341 converted. |
| E3 | `placeholder_args` and message shape in two post-June-2024 upstream samples: `investigation/samples/agentdojo/Meta-SecAlign-70B__slack__user_task_2__important_instructions__injection_task_1.json` and `…/gemini-2.0-flash-001__workspace__user_task_36__important_instructions__injection_task_10.json` | In both, the key is present on tool calls with value `null`. The Meta-SecAlign log has the 14-key header and content-block messages. The Gemini-2.0 log has the **11-key** header but **string** content, and still carries `placeholder_args`. The top-level key set therefore does not determine the message-level shape. June-2024 logs never carry the key [legacy §2.4]. |

E1 strengthens the corpus audit's finding that the recompute check uses dict equality only [corpus §3.3 R2]:
byte identity in fact holds today. E2 bears on D7 (see B.7.1).

### B.0.2 Decision vocabulary

Every row in B.2–B.5 carries exactly one decision. A compound such as `EXTRACT + ADAPT` means the component is
split and the row names one destination per part.

| Decision | Meaning | What it obliges |
|---|---|---|
| **RETAIN** | Port the behaviour unchanged. Code may move and be renamed, and comments may be corrected, but observable behaviour stays the same. | The baseline tests for it MUST pass unchanged in substance at the destination. |
| **REFACTOR** | Keep the behaviour but restructure its boundaries: split, merge, or change inputs and outputs to AER/SEM. | The listed invariants (B.8) MUST be preserved. Changed outputs MUST be covered by new tests. |
| **EXTRACT** | Lift the benchmark-neutral part into a core module or into `agentprov_capture`. Provider-client code that needs `openai` or `httpx` goes to `agentprov_backend` instead, which is not core (AD-01). | A core or `agentprov_capture` module MUST NOT import a benchmark package (B.1.2). |
| **GENERALISE** | Make the component parameterised by profile, vocabulary, adapter or role, beyond its AgentDojo-only form. | AgentDojo becomes one configuration of it, and the old behaviour MUST be reproducible under that configuration. |
| **ADAPT** | Move into an adapter family, a profile or the live harness (or reshape it there) because it is benchmark-specific. | It MUST live under `agentprov.adapters.<family>`, in profile or catalogue data, or in `agentprov_backend` or a backend project (`backends/`), never in core. |
| **DEPRECATE** | Not developed further. Either kept frozen for compatibility or regression only, or superseded by a named successor. | It MUST NOT be used to produce new AgentPROV artefacts except through the compatibility profile. |
| **REMOVE** | Not ported, with no successor (the capability is dropped). | Listed in B.10. |
| **REPLACE** | A new implementation with a different design. Only the invariants listed in B.8 carry over. | The successor MUST be named. |
| **DEFERRED** | Not ported in v0.1 (AD-10). The frozen baseline environment at `579a908` keeps serving the old corpus. | Recorded in `docs/roadmap.md` with its reason, and in `docs/port/baseline-map.json` with status `deferred`. The row's rationale, invariants and defects bind the port when it is reinstated. |

### B.0.3 Identifiers used in this section

| Prefix | Refers to |
|---|---|
| `CAP-`, `PRV-`, `VAL-`, `LEG-`, `COR-` | rows for package modules (B.2) |
| `DOC-` | rows for `docs/` (B.3) |
| `TST-` | rows for tests (B.4) |
| `PRJ-` | rows for scripts and project files (B.5) |
| `EXT-` | rows for untracked material (B.5) |
| `R-nn` | reconciliations (B.6) |
| `I-nn` | invariants (B.8) |
| `F-nn` | defects to fix (B.9) |
| `N-nn` | things that must not be ported (B.10) |

The bare `R-nn` ids are this section's reconciliations. Review findings are cited as "RESOLUTIONS R-nn" and
architect rulings as `AD-nn` (Addendum B).

---

## B.1 Destination layout and dependency boundaries

### B.1.1 Destination layout (superseded as path authority)

> **Superseded by MN M.1.2 and RESOLUTIONS §3.2; destinations below are mapped there.** (RESOLUTIONS R-17, R-01;
> AD-01; AD-10 as ruled.) MN M.1.2, amended by RESOLUTIONS §3.2 and Addendum B, is the only path authority. This
> subsection lists only the destinations that B.2–B.5 name, so that every baseline component has a home. Where it
> disagrees with MN M.1.2 or §3.2, they govern, and the B.2–B.5 rows and `docs/port/baseline-map.json` are
> regenerated from them.

```
<repository root>
  capture/agentprov_capture/          # dist agentprov-capture; Python >=3.12; stdlib + rfc8785 only (AD-01(a))
                                      #   event model, writer, hash-chain verifier, redact (+ redact_allowlist.toml),
                                      #   envstate digests, rules/cap.rules.toml
  backends/shared/agentprov_backend/  # dist agentprov-backend; AgentDojo-family live harness (AD-01(b));
                                      #   imports agentdojo (from the backend project), openai, httpx
                                      #   gateway, pass_recorder, executor_mirror, runtime, transport, runner,
                                      #   attacks, worker, testing (ScriptedTransport)
  backends/agentdojo/                 # uv project on Python 3.12 (own uv.lock); pins agentdojo==0.1.35; tests/
  backends/autodojo/                  # uv project on Python 3.12 (own uv.lock); pins the fork at aa458794…
                                      # neither backend project ever installs agentprov (AD-01)
  src/agentprov/                      # core; requires-python ">=3.14" (AD-16 as ruled); .python-version 3.14
    io/{atomic,canonical,workers}.py   worker.py   errors.py   api.py   _version.py
    ingest/{limits,loaders,archives,streams,names,paths,quote,yamlsafe}.py
    raw/{store,origins,members,fetch,references,purge}.py
    aer/{types,canon,ids,evidence,rules,writer,reader,locators,accounting,validate}.py   aer/rules/aer.rules.toml
    sem/{engine,types,validate}.py
    prov/{engine,evidence,specs,iri,vocab,diff}.py   prov/rules/   prov/serialise/{provjson,trig,time}.py
    prov/catalogue/agentprov-prov-0.1.toml
    prov/compat/adprov_v2_3/          # build_prov, prov_emit, labeling, validate, conformance: verbatim, AST-equal;
                                      #   PORT_MANIFEST.json; byte copy of adprov.ttl (RESOLUTIONS R-31)
    prov/compat/semdiff-map.toml
    views/{transcript,transcript_v1}.py   views/transcript_v1_fields.toml
    validate/{tiers,prov_structure,constraints,roundtrip,linkage,profiles}.py   validate/shapes/
    vocab/{apv-0.1,apv-adprov-map-0.1}.ttl
    corpus/{spec,layout,manifest,index,register,derive,integrity,datasheet,package,dedup}.py
    release/{builder,metadata}.py
    adapters/{types,protocols,profiles,runner}.py   adapters/registry/{__init__,claims,render}.py
    adapters/agentdojo/{dialect,mapper,capture_reader,capture_mapper}.py
    adapters/agentdojo/{semantics,profiles,rules}/      # SEM profile agentdojo.suites; agentdojo.rules.toml
    adapters/adprov/                  # AgentDojo-PROV transcript/v1 importer, legacy layout reader
    adapters/inspect/   adapters/stac/ (design note; planned)
    stats/                            # AD-10 as ruled: minimal generic statistics; core dependencies only
    render/{dot,style}.py             # AD-10 as ruled: ported render_prov_graph; extra `render` (pydot + Graphviz)
    migration/                        # J gates (agentprov.migration.gates)
    testing/   cli/   schemas/{aer-0.1,capture-0.1,corpus-0.1}.schema.json
```

**Mapping of the r1 destinations.** Earlier drafts of this section named the paths in the left column. The right
column is where each now lives.

| r1 destination | Canonical destination |
|---|---|
| `io/ingest.py` | `ingest/{limits,loaders,archives}.py` (`IngestLimits`, `strict_json_loads`, `iter_jsonl`; `agentprov.errors.IngestError`) |
| `raw/origin.py` | `raw/origins.py` |
| `aer/model.py` | `aer/types.py` |
| `sem/model.py`, `sem/policy.py` | `sem/types.py`, `sem/engine.py` |
| `capture/events.py`, `capture/session.py` | `agentprov_capture` (event model, writer, hash-chain verifier) |
| `capture/accounting.py` | `aer/accounting.py`: accounting is computed once, on the AER side (RESOLUTIONS R-13) |
| `capture/envstate.py` | `agentprov_capture.envstate` |
| `capture/gateway.py`, `capture/providers/openai_compat.py` | `agentprov_backend.transport` (recording transport around the default `native` element) and `agentprov_backend.gateway` (opt-in `gateway_compat`) (AD-09) |
| `capture/providers/endpoints.toml` | `endpoints.toml` (location per MN M.1.2; env-var names and hosts only) |
| `backends/{base,plan,runner,scheduler,worker}.py` | `agentprov_backend.{runner,worker}`, which hold `CellSpec`, `BenchmarkIdentity`, `AgentConfig.llm_element`, `ExecutionBackend` and `CaptureHooks`; the parent side (spawn, lock, teardown) is `agentprov.cli.run` |
| `adapters/registry.py` | `adapters/registry/` package |
| `adapters/base.py` | `adapters/{types,protocols,profiles}.py` |
| `adapters/importer.py` | `adapters/runner.py` |
| `adapters/agentdojo/dialects/tracelogger.py`, `mapping/{messages,tracelogger,identity,outcomes}.py` | `adapters/agentdojo/{dialect,mapper}.py` |
| `adapters/agentdojo/dialects/transcript_v1.py` (+ schema) | `adapters/adprov/` (v1 reader and mapper; corrected `transcript_v1.schema.json`) |
| `adapters/agentdojo/dialects/capture.py`, `mapping/live.py` | `adapters/agentdojo/{capture_reader,capture_mapper}.py` (core) |
| `adapters/agentdojo/views/transcript_v1.py` | `views/transcript_v1.py` |
| `adapters/agentdojo/legacy_layout.py` | `adapters/adprov/layout.py` |
| `adapters/agentdojo/profiles/rules/*.toml`, `profiles/tables/*.json` | `adapters/agentdojo/rules/agentdojo.rules.toml`; SEM tables under `adapters/agentdojo/semantics/` |
| `adapters/agentdojo/live/*` | `backends/shared/agentprov_backend/*` |
| `adapters/agentdojo/verify/*` | DEFERRED (AD-10); if reinstated, a T1-restricted job in `backends/agentdojo` |
| `adapters/agentdojo/semantics/ml_tasks.py` | DEFERRED with `export/ml` (AD-10) |
| `prov/spec/`, `prov/emit.py` | `prov/{engine,specs,iri,evidence,vocab}.py`, `prov/rules/` |
| `prov/serialise/prov_json.py`, `prov_o.py` | `prov/serialise/provjson.py`, `trig.py` (TriG on demand, `derive --trig DIR`) |
| `compat/adprov_v2_3/` | `prov/compat/adprov_v2_3/` (the five baseline files verbatim) |
| `vocab/apv.ttl`, `vocab/adprov-to-apv.ttl` | `vocab/apv-0.1.ttl`, `vocab/apv-adprov-map-0.1.ttl` |
| `validate/{registry,gate,report}.py` | `validate/tiers.py` |
| `validate/{prov_constraints,time_flags}.py` | `validate/constraints.py` |
| `validate/fidelity.py` | `validate/roundtrip.py` |
| `validate/coverage.py`, `validate/profiles/assessment.py` | `validate/profiles.py` |
| `validate/shacl.py`, `validate/shapes/prov-o-core.ttl` | `validate/shapes/` (extra `shacl`) |
| `validate/corpus.py` | `corpus/integrity.py` (MN M.1.10 row 15) |
| `corpus/{store,rederive}.py` | `corpus/derive.py`; the sealed-corpus guard is in `corpus/layout.py` |
| `corpus/release.py` | `release/builder.py` |
| `analysis/stats.py` | `stats/` (generic part only; AD-10 as ruled) |
| `analysis/{graph,heuristics,flow,argflow,labelling_audit,cache}.py`, `export/ml/` | DEFERRED (AD-10) |
| `render/{dot,style}.py` | `render/{dot,style}.py` (AD-10 as ruled) |
| `cli/*` | `cli/` per MN N.2. Commands: `run`, `import` (alias `convert`), `fetch`, `derive`, `recompute`, `validate`, `verify`, `inspect`, `info` (alias `sources`), `backends`, `package`, `migrate`, `purge`, `stats`, `render` (AD-10 as ruled). `diff` is deferred |
| `schemas/{aer-0.1,sem-0.1,capture-0.1,corpus-manifest-0.1,run-plan-0.1}.schema.json` | published schemas `aer-0.1`, `capture-0.1` and `corpus-0.1` only (AD-10 row 13) |
| `tests/core/…`, `tests/adapters/agentdojo/{live,verify}/…`, `tests/compat/…`, `tests/analysis/…`, `tests/export/…`, `tests/render/…`, `tests/golden/…` | the K.3.1 layout. Tests that import `agentdojo` go to `backends/agentdojo/tests/` |
| `docs/{spec,sources,compat,ns,port}/` | unchanged (MN M.1.5). `docs/export/` is deferred with the export; `docs/roadmap.md` lists the deferrals |

### B.1.2 Dependency extras and import boundaries

Every rule below MUST be enforced by `tests/boundary/test_import_boundary.py` (K.3.1). The test imports each module
in a fresh subprocess with a `sys.meta_path` finder that raises on a forbidden top-level package.

| Distribution or module prefix | May import (beyond stdlib) | Installed where |
|---|---|---|
| `agentprov_capture` | `rfc8785` only | core and both backend projects (Python ≥ 3.12) |
| `agentprov_backend` | `agentprov_capture`, `agentdojo` (supplied by the backend project), `openai`, `httpx`, `pydantic` | backend projects only (Python 3.12); they never install `agentprov` |
| `agentprov.render.*` | `pydot`, Graphviz `dot` as a subprocess | core extra `render` (AD-10 as ruled) |
| SHACL checks in `agentprov.validate` | `pyshacl`, imported lazily | core extra `shacl` |
| the live CLI entry (`agentprov run`, `.env`) | `python-dotenv`, imported lazily | core extra `live` (`python-dotenv>=1.2.2`) |
| `agentprov.ingest.yamlsafe` | `yaml` | core (AD-17) |
| every other `agentprov.*` module, including `agentprov.stats` | `prov`, `rdflib`, `rfc8785`, `agentprov_capture` | core (`requires-python = ">=3.14"`, AD-16 as ruled) |

- No core module MAY import `agentdojo`, `agentprov_backend`, `openai` or `httpx`, directly or transitively.
  Benchmark imports exist only under `backends/`. The baseline violated this through `recompute → generate →
  observer` [corpus §3.3 R1] and `convert_runs → generate` [legacy §3.6 D8].
- There is no `agentdojo`, `analysis` or `all` extra in v0.1 (AD-01, AD-10). `agentprov.stats` has no extra and uses
  core dependencies only.
- PyYAML is a core runtime dependency (`pyyaml`, locked at 6.0.3), imported only by `ingest/yamlsafe.py` (AD-17).
  Readers and loaders never parse YAML.
- `python-dotenv` (outside the `live` extra), `tenacity`, `matplotlib` and the `numpy` pin are NOT core
  dependencies. The baseline listed them for the live runtime and for the manuscript [corpus §3.9].
- The compat port `agentprov.prov.compat.adprov_v2_3` imports only its own ported files and a `safe_load` shim over
  `ingest.yamlsafe`, recorded in `PORT_MANIFEST.json` (RESOLUTIONS R-31). The r1 exception that let it import
  `agentprov.adapters.agentdojo.semantics.marker` is withdrawn: the port keeps its own verbatim `payload_marker`
  (MN M.1.10 row 6). No core module other than the spec resolver (`prov/specs.py`, which loads it lazily) MAY import
  `agentprov.prov.compat`.

### B.1.3 Port traceability

- The port MUST maintain `docs/port/baseline-map.json`. Each entry is
  `{row_id, baseline_path, baseline_lines, decision, destinations[], tests[], status}` with
  `status ∈ {"todo","ported","verified","not_ported","deferred"}`. `deferred` marks AD-10 deferrals.
- The destinations are those of B.2–B.5 as regenerated in r2. They are expressed in the canonical paths of MN M.1.2
  and RESOLUTIONS §3.2, including the repository-root projects `capture/` and `backends/`.
- A traceability test under `tests/docs/` (K.3.1; K owns the exact name) SHOULD assert two things:
  - every one of the 57 tracked baseline files at `579a908` appears in at least one entry;
  - every destination module named by an entry with status `ported` or `verified` exists.

---

## B.2 Component table: `agentdojo_prov/` (22 modules)

### B.2.1 Live capture and generation (`runtime.py`, `observer.py`, `transcript.py`, `envstate.py`, `generate.py`, `__init__.py`)

| Id | Existing component (file:lines) | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| CAP-01 | `runtime.py:121-393` `_build_openai_compat_llm` / `_CompatLLM`: per-call logs, retry loop, passback | REFACTOR (EXTRACT + ADAPT) | (a) `agentprov_backend.transport`: recording httpx transport around the stock agentdojo LLM element, which is the default (`llm_element = "native"`), plus LLM-span brackets that record `input_at` and `n_messages` without modifying requests; (b) `agentprov_backend.gateway`: `gateway_compat`, the port of `_CompatLLM`, opt-in and declared as `request_modifying`/`harness_policy` instrumentation (AD-09) | Every released model ran through it, and RT-1…RT-6 are tested. But discarded replies, wire requests, per-call usage, endpoint and SDK version are not recorded [capture §4.1, §8 D2]. D5 asks for recording into `capture/0.1`. AD-09 makes the stock element the default, so that new live corpora stay comparable with stock AgentDojo; the port is kept for v2.3 comparability. Resample and retry counts are recorded per execution. | `OpenAILLM` subclass and `query` signature; private `_function_to_openai`, `_message_to_openai`, `_openai_to_assistant_message`, `chat_completion_request` (`runtime.py:148-154`); passback reset keyed on "request has no assistant message" (`:251-252`) |
| CAP-02 | `runtime.py:49-118` effort parsing, `_message_extras`, `_reasoning_text`, `_upstream_failure` | EXTRACT | `agentprov_backend.gateway` (`reasoning_text(message) -> Optional[str]`, `upstream_failure(completion) -> Optional[str]`) | Provider-client concerns, independent of any benchmark [capture §4.1 "Generic"]. They need the `openai` response types, so they live with the gateway, outside core (AD-01). | none |
| CAP-03 | `runtime.py:396-536` builders, `_LLM_BUILDERS`, `_OPENROUTER_MODEL_ENV`, `build_llm`, `resolved_model_id`; env vars `*_API_KEY`, `*_BASE_URL`, `*_MODEL`, `REASONING_*`, `LLM_TIMEOUT_S` | GENERALISE | `AgentConfig` in `agentprov_backend` (D.10.1; `llm_element ∈ native\|gateway_compat`) + `endpoints.toml` (env-var names and default hosts only). The parent (T0) checks that base URLs are https (loopback excepted) and that the host matches `endpoints.toml` unless `--allow-custom-endpoint` is given, which is recorded (RESOLUTIONS R-39) | Defaults are duplicated. Base URL, timeout, retry constants and SDK version reach no trace [capture §4.1]. `AgentConfig` MUST be recorded in the `capture/0.1` `session.start` event and the AER header; secrets appear only as env-var names. An explicit model id is required: there are no silent defaults (RESOLUTIONS §1.3, MN Q5). | none |
| CAP-04 | `runtime.py:37-42, 579-585` `BENCHMARK_VERSION="v1.2.2"`, defaults, `load_suite` | ADAPT | `agentprov_backend` (`BenchmarkIdentity`; `load_suite(name)` in `agentprov_backend.runtime`); the worker reports its identity in `hello_ok` (distribution, commit from PEP 610 `direct_url.json`, lock digest), and T0 cross-checks it against digests computed before spawn (RESOLUTIONS R-39) | Version strings do not identify the distribution: AgentDyn and AutoDojo also report `agentdojo 0.1.35` [capture §9.6; D9]. | entirely |
| CAP-05 | `runtime.py:543-659` `build_pipeline`, `run_benign`, `run_injection`, `main` (uninstrumented smoke CLI) | DEPRECATE | successor: `agentprov run --dry-run`, executed by the spawned backend worker (`agentprov_backend.worker`) | Uninstrumented, so a run leaves no evidence [capture §4.1 defect 5] | entirely |
| CAP-06 | `observer.py:70-169` `EnvironmentRecorder`, `TranscriptCapture` (`begin_pass`, `_usage_len`, swap-and-reset) | ADAPT + EXTRACT | `agentprov_backend.pass_recorder.PassRecorder` (wraps the whole `AgentPipeline`), which writes `pass.start`/`pass.end` events through `agentprov_capture`; per-pass accounting → `agentprov.aer.accounting`, computed once on the AER side (RESOLUTIONS R-13) | OB-1…OB-5 are correct. Aborted passes bypass the last element, and messages are serialised only after the run [capture §4.2.1, §8 D11]. | `BasePipelineElement.query`; the ≤3-pass silent re-run; pydantic `TaskEnvironment` |
| CAP-07 | `observer.py:172-231` `TimingToolsExecutor` | ADAPT | `agentprov_backend.executor_mirror` (version-guarded mirror of `TimingToolsExecutor`) + `agentprov_backend.runtime` (`RecordingFunctionsRuntime`, passed through `run_task_with_pipeline(runtime_class=…)`) | A behaviour-preserving mirror of the 0.1.35 `ToolsExecutor`; AgentDyn's copy is byte-identical. It records no dispatch status or effective args, and no timing when `id is None` [capture §4.2.2]. D5 requires a differential test against the stock executor (B.11 check 5). | mirror of `tool_execution.py` L58-115; `FunctionsRuntime.run_function`; YAML `tool_result_to_str` |
| CAP-08 | `observer.py:234-461` (excluding L272-313) in-loop `ProvObserver` projection, `get_prov_document`, `save_prov_document` | REMOVE | none: provenance is derived offline by `agentprov.prov.engine` | A second PROV implementation, reached only from tests. Its timestamps are observation time (`startTime == endTime == now`, L351, L389-398) and its hashes are 16 hex characters [capture §4.2.3; provenance §7.5; D5] | `BasePipelineElement` API |
| CAP-09 | `observer.py:61-67, 272-305` `get_transcript_doc`, `CaptureIncomplete` gate | REFACTOR + GENERALISE | accounting → `agentprov.aer.accounting` (verdict `consistent\|inconsistent\|unverifiable`, computed by the AER mapper and validator); the capture side (`agentprov_capture`) only seals its hash chain; `agentprov_backend.runner` reads the seal verdict to decide a re-attempt (RESOLUTIONS R-13) | The gate compares two in-process counters and is inert for native providers. It assumes one LLM and one agent, has an ungated fallback (L301-305), and failing cells are discarded [capture §4.2.4, §8 D4-D5]. D5 asks for kept failures. | single-agent, one-message-per-call assumption; `_CompatLLM.n_calls` |
| CAP-10 | `observer.py:307-313` `derive_prov` | REMOVE (from capture) | derivation stage `agentprov.prov.engine`, driven by `agentprov.corpus.derive` | Builds the transcript a second time instead of reading the persisted bytes [capture §4.2.4 defect 6]; D0 | none |
| CAP-11 | `observer.py:468-526` `make_instrumented_pipeline` | ADAPT (v0.1); GENERALISE later | `agentprov_backend.runner` (`instrument(config, llm, session) -> AgentPipeline`, using `pass_recorder`, `executor_mirror` and `runtime`) | OB-8 (refuse `defense is not None` or non-YAML output, L484-487) MUST hold as a typed refusal in v0.1 (RESOLUTIONS §1.3; I-08) until a generalised gate covers auxiliary LLM calls [capture §4.2.5] | entirely |
| CAP-12 | `observer.py:1-24` module docstring ("FLINT Layer-2 PROV observer") | REMOVE | none | Stale [capture §4.8 item 5; provenance §12] | none |
| CAP-13 | `transcript.py:27-145` `message_to_turn`, `_split_blocks`, `_serialize_function_call`, `_build_turns` (alignment, timings) | ADAPT | message mapping in `adapters/agentdojo/` (`to_aer_messages(native_messages, *, reasoning_log=None, refusal_log=None, timings=None) -> list[Record]`), shared by `mapper.py` (TraceLogger) and `capture_mapper.py` (live); the v1 importer (`adapters/adprov/`) applies the same TR rules to v1 turns | TR-1…TR-8 are correct but lossy: non-text blocks dropped, block order lost, I presented as O [capture §4.3]. Evidence qualifiers (`ev` as the existence class, `evf`, `rule`; C.6.3) MUST be added. | block types `text`/`thinking`/`redacted_thinking`; `FunctionCall`; tool message `tool_call`/`tool_call_id`/`error` |
| CAP-14 | `transcript.py:148-185` `capture_record` | GENERALISE | `agentprov.aer.accounting` | The tri-state precedence is generic once accounting is partitioned by role [capture §4.3 TR-9, §9.4] | per-pass `llm_calls` from `_CompatLLM` |
| CAP-15 | `transcript.py:188-264` `build_transcript` | REFACTOR | raw side: the `agentprov_capture` hash-chained log, with native pass dumps and wire blobs staged under `$AGENTPROV_HOME/staging/<session>/` and ingested into `raw/objects/`; canonical side: `adapters/agentdojo/capture_mapper.py`; v1 shape: `views/transcript_v1.py` | Raw evidence and the canonical record are the same object today [capture §1 item 2]. D0 and D3 separate them. | `meta` layout of `generate._trace_meta` |
| CAP-16 | `transcript.py:267-287` `suffixed`, `atomic_write_text`, `save_transcript` | EXTRACT | `agentprov.io.atomic` (`atomic_write_bytes(path: Path, data: bytes) -> None`, `atomic_write_text(path, text) -> None`, `suffixed(path, suffix) -> Path`) | Generic; TR-10 [capture §4.3] | none |
| CAP-17 | `transcript.py:20` `TRANSCRIPT_SCHEMA = "transcript/v1"` and the v1 record shape | DEPRECATE (as canonical) / RETAIN (as import dialect and view) | `adapters/adprov/` (dialect `adprov.transcript_v1`), `views/transcript_v1.py` | The id stayed frozen through field additions and one semantic change (null versus `""`) [capture §7, §8 D3]. D1 keeps v1 as an import format and as a derived view. | entirely |
| CAP-18 | `envstate.py:1-95` `dump_state`, `_canon`, `digest`, `diff`, `pass_record`, `VALUE_CAP`, `ENTRY_CAP` | EXTRACT | `agentprov_capture.envstate` (`digest(state) -> str`, `diff(before, after) -> dict`, `pass_record(before, after) -> dict`) + optional full snapshots as raw blobs | No AgentDojo import, and E-1…E-5 are tested. It keeps only a truncated diff, and `truncated` ignores value cuts [capture §4.4, §8 D15]. | none (pydantic `model_dump` duck-typed) |
| CAP-19 | `generate.py:311-468, 638-902` orchestration: early save, resume, write gate, CLI, exit codes, stagger | REFACTOR (EXTRACT generic part) | worker side: `agentprov_backend.runner` (resume from sealed raw evidence, attempts, `config_digest` guard); parent side: `agentprov.cli.run` (spawns `<env>/bin/python -I -B -m agentprov_backend.worker`, per-plan lock, signal-safe teardown; AD-01(c)); write gate → `agentprov.validate.tiers` + `agentprov.corpus.derive` | G-1…G-6 are generic and correct. Capture, derivation, validation and rendering run in one process, and resume keys on the derived graph [capture §4.5]. D5 resumes from sealed raw evidence, and A1 makes every live run a spawned worker. | cell key fields only |
| CAP-20 | `generate.py:238-275, 475-631` `_resolve_inj_task_ids`, `_without_json`, `_benign_json_path`, `_injection_json_path`, `_run_one_benign`, `_run_one_injection` | ADAPT | `agentprov_backend.runner` (`enumerate_cells(plan) -> Iterator[CellSpec]`, `run_cell(cell, agent, hooks) -> CellOutcome`) + `agentprov_backend.attacks` (`load_attack`) | AgentDojo task and attack semantics [capture §4.5] | suites, `injection_task_N` parsing, `load_attack`, `run_task_with_pipeline`, path layout |
| CAP-21 | `generate.py:127-224` `_agentdojo_version`, `_trace_meta`, `_model_config_from_llm` | ADAPT | `adapters/agentdojo/capture_mapper.py`: the execution header `task`, the agent actor's model, `model_call.params{configured, transmitted}` and `judgement` (with `origin`, C) | `response` is reduced to sorted sets and usage is aggregated. Temperature is recorded but not transmitted [capture §4.1 defect 3, §5.2]. | `utility`/`security` polarity; benign `security` (G-7) |
| CAP-22 | `generate.py:276-302` `_make_pipeline`, including `MODEL_NAMES[model_id] = …title()` (L299-302) | ADAPT (naming) + REMOVE (mutation) | `agentprov_backend.attacks`; the display name is the declared instrumentation item `attack.model_display_name` (kind `attack_parameter`, D.10.7), copied into the AER header; stock behaviour otherwise (RESOLUTIONS §1.3) | The mutation determines the `important_instructions` text ("Gpt 5 Nano", …) where stock AgentDojo raises [capture §4.5 defect 3, §8 D10] | `MODEL_NAMES`, `get_model_name_from_pipeline` |
| CAP-23 | `generate.py:328-357` `_config_differs`, `_refuse_mixed_configuration` | GENERALISE | `agentprov_backend.runner.config_digest(agent: AgentConfig, identity: BenchmarkIdentity, cell: CellSpec) -> str` | Checks only `reasoning_effort`, and only in the first transcript found [capture §4.5 defect 2, §8 D16] | none |
| CAP-24 | `generate.py:71-124` `_LEGACY_MODEL_FOLDERS`, `_model_folder`, `_render_title`, `_render_dir_for` | ADAPT | `adapters/adprov/layout.py` (read-only legacy layout reader; render-dir rule); title → `agentprov.render.style` (AD-10 as ruled) | G-10 is needed only to read the released folders [capture §4.5]. The render rule MUST stay single-sourced [legacy §5; corpus §2.2]. | `prov-` folder prefixes |
| CAP-25 | `generate.py:391-420, 733-799` parquet run log (`_selection_tag`, `_write_log`, `_merge_log`); error rows `generate.py:603-607` | REPLACE | `agentprov_backend.runner`: every attempt is its own sealed capture session (`capture {session, log, attempt}`), failures are kept with session end status `errored` or `aborted`, and the full exception is an `error` event; T0 lists failed attempts in `register.jsonl` (stage `capture`) | The log is the only trace of failed attempts and truncates errors to 120 characters. Error rows carry placeholder `utility=False, security=False` [capture §4.5 defects 4, 6]. | none |
| CAP-26 | `generate.py:680-691` call to `check_suite_coverage` | ADAPT | `agentprov.validate.profiles` (policy-coverage guard), run at semantics time with the SEM profile `agentdojo.suites` | An interpretation concern inside the capture CLI [capture §4.5] | `labeling.py` tables |
| CAP-27 | `__init__.py:1-26` docstring module map; `__version__ = "1.0.0"` | REPLACE | `src/agentprov/__init__.py`, `_version.py` | The version was never bumped across data-affecting changes [corpus §0]; the docstring is stale [capture §4.7] | the namespace IRI in the docstring |

### B.2.2 Provenance derivation (`build_prov.py`, `prov_emit.py`, `labeling.py`, `graph.py`)

| Id | Existing component (file:lines) | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| PRV-01 | `build_prov.py:328-495` `build_prov(transcript, *, emit_content=False, emit_source_agents=False, emit_derived_edges=False)` | RETAIN (verbatim, compat) + REPLACE (core) | `agentprov.prov.compat.adprov_v2_3.build_prov` (verbatim, AST-equal; only import statements change; RESOLUTIONS R-31); core: `agentprov.prov.engine` under `agentprov-prov/0.1` | Correct, pure, and byte-identical on 35,691/35,691 (E1). But one activity stands for both the LLM decision and the tool execution [provenance §1, §14 D1]. D7 requires the decomposed model and keeps this builder as the oracle. | reads `transcript/v1`; YAML marker; tool tables |
| PRV-02 | `build_prov.py:342-346, 371-421` pass/batch/turn/step walk | EXTRACT | AER structure built by the mappers from request membership: `scope` attempt records, the assistant `message` `generated_by` its `model_call`, that message's `tool_call` parts, and `tool_execution.call` pointing at a part. References are backward only (C). Compat keeps the walk verbatim | Batches come from message adjacency. A split layout recreates same-request `wasInformedBy` (demonstrated) [provenance §7.1.6, §14 D4]. | sequential AgentDojo tool loop |
| PRV-03 | `build_prov.py:460-469` R3/R4/R5: first-turn `used(e_user_query)`, exchange `used`, `wasInformedBy` | REFACTOR | `agentprov.prov.engine` under `agentprov-prov/0.1`: the ModelInvocation uses its `model_call.input` messages, with per-input sent transforms (`apv:sentTransform`); the ToolExecution uses only its request part; `wasInformedBy` is exactly the Inference-6 closure over named activities, each with `apv:premise` (AD-19). For the released v1 transcripts, context membership is INFERRED and goes to the inference bundle (AD-05) | The evidence is context availability. Only 28.8% of released `wasInformedBy` edges have literal argument support [provenance §4.3, §5.3; landscape/prov_semantics.md §5.2; D7]. The prefix-context assumption rests on unversioned client code, not on a version string (AD-05). | prefix-context assumption (`OpenAILLM.query` sends the full history) |
| PRV-04 | `build_prov.py:371-372, 412, 471-474` R6 context-taint `used` for sinks | EXTRACT | taint policy of the SEM profile `agentdojo.suites` (`adapters/agentdojo/semantics/profile.py`). EF emits it only in the assessment bundle, as `apv:Assessment` (`aprov.a_exposure@1` + `aprov.a_taint@1`), never as `prov:used` | A policy rather than provenance; 28.2% literal support [provenance §5.4; D7 "never emit"]. The turn-aware visibility rule MUST be kept exactly (I-26). | sink and ⊥ tables |
| PRV-05 | `build_prov.py:475-477` (+ `prov_emit.py:199-209`) R7 `wasDerivedFrom` under `emit_derived_edges` | DEPRECATE | compat only. The flag stays in the verbatim port, with no CLI exposure (N-05; RESOLUTIONS §1.3) | The strongest PROV claim on the weakest evidence, and it passes every validator [provenance §5.5; validation V7] | none |
| PRV-06 | `build_prov.py:396, 483-490` (+ `prov_emit.py:211-221`) R8 source agents under `emit_source_agents` | REPLACE | SEM `author` annotation. Structured-content author fields become `apv:declaredSender` (a parse fact); any authorship claim is INFERRED and lives in the assessment bundle (A5; RESOLUTIONS R-20) | Misattributes agent-authored mutation outputs: 66 in a 150-trace sample [provenance §5.6] | `_CHANNEL_OF` |
| PRV-07 | `build_prov.py:79-114, 307-325, 389-395, 430-437` `_timestamp`, `_shared_starts`, run-start fallback, `end:=start` | GENERALISE | predicate → `agentprov.prov.serialise.time.prov_timestamp(value: object) -> Optional[str]` (verbatim semantics); normalisation, `t.raw` retention and shared-start conflicts → AER mappers (`unk`, seal issue); fallbacks → compat only | The predicate is a property of `prov` 3.2.2 serialisation and rejects `Z`/millisecond forms; the fallbacks fabricate times [provenance §7.1.2, §14 D9-D10; validation §3.2] | none |
| PRV-08 | `build_prov.py:116-141` `_IRI_ILLEGAL`, `RESERVED_LOCS`, `unique_loc`, `tc_step{n}` | RETAIN (compat) / REPLACE (core) | compat verbatim; core: local ids in C's grammar (`^[a-z][a-z0-9_]{0,31}$`; D2) and IRIs `https://w3id.org/agentprov/exec/<ex>#<L(id)>` with `L` mapping `#` → `-`, minted by `agentprov.prov.iri` (AD-04; EF E.4.2) | The collision loop is required for released data (GLM-4.6 reuse; null and empty legacy ids). The IRI-legality gap misses `#`, `%`, `[` and `]` [provenance §7.1.3] | provider id formats |
| PRV-09 | `build_prov.py:144-304` marker: `_ESCAPE`, `_SIMPLE_ESCAPES`, `_unescape`, `_content_forms`, `_decoded_forms`, `_norm_payload`, `_norm_match`, `payload_marker`, `_first_user_text` | EXTRACT | `adapters/agentdojo/semantics/marker.py`: `payload_marker_v1(content: str, norm_payloads: Sequence[str]) -> Optional[bool]`, `norm_payload_v1`, `norm_match_v1`, `content_forms_v1`, imported by the SEM profile. YAML goes through `ingest/yamlsafe.py` (AD-17). The compat port keeps its own verbatim copy (RESOLUTIONS R-31; MN M.1.10 row 6), and a differential test pins the two to the same results (I-21) | Hard-won: released numbers moved with each fix. In the baseline it is shared by builder, stats and baselines [provenance §7.1.4; corpus §3.4.2 rule 4]. Configuration ground truth (attack, payload fixtures) stays in the core bundle as configuration provenance; SEM-dependent interpretations such as marker results stay out of it (AD-11). | `yaml.safe_dump` escaping; Python repr nesting; `meta.injections` |
| PRV-10 | `build_prov.py:498-524` `injection_reaches_untrusted` | RETAIN | `agentprov.validate.profiles.injection_reaches_untrusted(sem) -> Optional[bool]` (over SEM annotations); compat copy verbatim | A generic tri-state guard, given integrity and marker [provenance §7.1.5] | none |
| PRV-11 | `build_prov.py:40-69` `_CHANNEL_OF`, `PI_DETECTOR_PLACEHOLDER` | ADAPT | data of the SEM profile `agentdojo.suites`: `adapters/agentdojo/semantics/tables/{channels,defences}.json`, loader `semantics/tables.py`; the PI-detector sentinel is cited by the catalogue rule `agentdojo.pi_detector_sentinel` (D.5.4) | Pure AgentDojo tables, hashed into the profile digest [provenance §7.1.1] | entirely |
| PRV-12 | `prov_emit.py:17` `ADPROV_NS` (imported by conformance, validate, package, ml_export, visualize) | RETAIN (frozen, compat) | `agentprov.prov.compat.adprov_v2_3.prov_emit.ADPROV_NS` (verbatim) | Baked into 35,691 graphs [provenance §9-10; D7] | none |
| PRV-13 | `prov_emit.py:35-253` `ProvDocumentBuilder` | GENERALISE (core) + RETAIN (compat, verbatim) | core statement assembly in `agentprov.prov.engine` with the writer `prov/serialise/provjson.py`: namespaces as parameters, `prov:type`, qualified relations, bundles, an error on a duplicate id; compat: `prov/compat/adprov_v2_3/prov_emit.py` verbatim | Hard-coded prefix; a duplicate id silently overwrites (`prov_emit.py:162`) [provenance §7.2, §14 D15] | adprov attribute lists |
| PRV-14 | `prov_emit.py:21-27` `_now_iso`, `_content_hash` (16 hex) | REMOVE | none; clocks live in the `capture/0.1` event envelope (`ts`, `mono_ns`), written by `agentprov_capture` | Used only by the in-loop path and `generate` [provenance §7.2] | none |
| PRV-15 | `prov_emit.py:30-32` `_sha256` (`"sha256:"+hex`) | EXTRACT | `agentprov.io.canonical.sha256_hex(data: bytes) -> str` | Generic; notation is unified per R-12 | none |
| PRV-16 | `labeling.py:6-14, 128-145` `Label`, `NodeRole`, `classify_activity`, `entity_integrity` | GENERALISE (core) + RETAIN (compat) | `sem/types.py` (`integrity ∈ trusted\|untrusted\|unknown`; security roles including `unknown`) + fail-closed lookup in `sem/engine.py`; compat keeps the fail-open defaults verbatim | Fail-open: 49 released and 12 converted hallucinated-tool turns are labelled ⊤. Labels are static per tool [provenance §7.3; D6]. | none |
| PRV-17 | `labeling.py:19-125` `SINK_TOOLS` (24), `EXTERNAL_CONTENT_TOOLS` (28), `ENDORSER_TOOLS` (empty) | ADAPT | data of the SEM profile `agentdojo.suites`: `adapters/agentdojo/semantics/tables/tools-v1.2.2.json`, keyed by (suite, tool) | AgentDojo v1.2.2 tool names; `download_file` is in no suite; endorser is never emitted [provenance §7.3] | entirely |
| PRV-18 | `labeling.py:148-175` `check_suite_coverage`, `check_external_content_coverage` | RETAIN | `agentprov.validate.profiles` (policy-coverage guards), fed by an adapter-supplied injection-vector → reader-tool map | Generic guards; the current static test is tautological [provenance §7.3, §14 D20] | the maps |
| PRV-19 | `graph.py:1-114` `load_prov_graph`, `get_untrusted_sources`, `get_sinks`, `get_endorsers` | DEFERRED (AD-10) | `analysis/graph` is deferred to v0.2; the baseline environment at `579a908` serves the old corpus. When ported: `load_flow_graph(doc, *, vocab, evidence=None) -> nx.MultiDiGraph`, reading the assessment bundle (RESOLUTIONS R-34) | Edge orientation is correct. A `DiGraph` collapses parallel edges, and the loader keys on literal `adprov:` strings [provenance §7.4] | `adprov:` attribute names |

### B.2.3 Validation (`validate.py`, `conformance.py`)

Both files are part of the compat oracle and are ported verbatim, AST-equal, to `prov/compat/adprov_v2_3/`
(RESOLUTIONS R-31). VAL-05…VAL-12 therefore describe *new* generic validators in `src/agentprov/validate/` that sit
beside the verbatim `conformance.py`; they do not modify it.

| Id | Existing component (file:lines) | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| VAL-01 | `validate.py:18-59, 277-394, 435-453` generic structural layer (S1, S3–S7, S9), `ValidationResult` | EXTRACT | new generic validator `agentprov.validate.prov_structure.check_structure(doc, *, profile) -> CheckResult`; the compat port keeps `validate.py` verbatim | Dependency-free (0.05–0.08 ms/graph) and gates every write. Has a totality bug and closed-world gaps [validation §3.1, V1, V2]. | none except the S2 pin |
| VAL-02 | `validate.py:62-274, 396-433` shape invariants I1–I11; S2 namespace pin (`:286-291`); S8 enumerations (`:386-394`) | RETAIN (verbatim, compat) | `prov/compat/adprov_v2_3/validate.py`, verbatim; results reported under the ids `adprov-v2.3.I1` … `I11`, `S2`, `S8` | The exact regression oracle for one builder policy. It must not gate other sources [validation §3.2, V8; D8 "profile rules separate from generic checks"]. | single LLM; user query identified by label; tool-call-only activities; AgentDojo passes; tool tables |
| VAL-03 | `validate.py:217-221` sink-taint part of I9 | ADAPT | compat (verbatim); new assessment-bundle rules (allowed statement forms, EF E.7.2) in `agentprov.validate.profiles` | Detection policy, not provenance [validation §3.2, V9] | sink and ⊥ tables |
| VAL-04 | `validate.py:261-274` I11, which imports `build_prov._timestamp` (`:263`) | EXTRACT | `agentprov.prov.serialise.time`, shared by the new emitter and the new validators; the compat port keeps its verbatim import | Removes the validator → builder dependency in new code [validation V10] | none |
| VAL-05 | `conformance.py:92-156, 244-253` `ProvValidator`, `CheckOutcome`, `ValidationResult`, `_missing` | GENERALISE | new generic check registry in `agentprov.validate.tiers` (`Check` protocol; `CheckResult{rule_id, severity, status, focus, message}` with status `pass\|fail\|skipped\|not_applicable` and severity `info\|warning\|error`; `run_checks(doc, checks, *, strict: bool) -> Report`); the compat port keeps `conformance.py` verbatim | The plug-in idea is sound. But "skipped = ok", the RDF graph is rebuilt 4×, and errors are plain strings [validation §3.3, V11, V15] | none |
| VAL-06 | `conformance.py:160-242` `_check_schema` | REFACTOR | new structure checks in `agentprov.validate.prov_structure`; compat verbatim | Filters `validate.py` errors by message text, and the two gates disagree in both directions [validation §3.4, V10] | namespace pin, enumerations |
| VAL-07 | `conformance.py:257-280` `round_trip` | RETAIN | `agentprov.validate.roundtrip.round_trip(doc, cache) -> CheckResult` | Catches library-incompatible input. The claim is relabelled "prov library round-trip stability" [validation §3.5, V4] | none |
| VAL-08 | `conformance.py:344-447` `completeness`, `_QUALIFIED`, `_NODE_CLASS`, `_NODE_PROV_ATTR`, `_lexical` | RETAIN + GENERALISE | `agentprov.validate.roundtrip.completeness`, extended to all PROV-DM relations, bundles, every declared prefix, typed literals, and the reverse direction | Found the `"0"` stub in 17,265 converted graphs. It is lexical, one-way, and blind to unknown sections and prefixes [validation §3.6, V2, V3] | `adprov:` key handling |
| VAL-09 | `conformance.py:450-562` `constraints_errors`, `_dt`, `_comparable` | REFACTOR | `agentprov.validate.constraints`: faithful 24 per (entity, activity); 39; 42; 53 with the Rec. relation set; 54; 55 with typing inference. The time checks (30/33/34/35/37) are MAY-flags reported apart from validity. The closed-world rules stay in the verbatim compat `conformance.py` | The labels misstate PROV-CONSTRAINTS, and 42 is missing [validation §3.7, V5-V7; landscape/prov_semantics.md §5.6] | none |
| VAL-10 | `conformance.py:577-607, 309-332` `_SHACL_SHAPES_TTL` (`adprov:ActivityShape`, `adprov:AssociationShape`), `_check_shacl` | GENERALISE | `src/agentprov/validate/shapes/` (generic PROV-O shapes; extra `shacl`, `pyshacl` imported lazily; results read from the `sh:ValidationReport` graph); the compat shapes stay verbatim inside the ported `conformance.py` | Shapes live in a Python string and are undeclared in `adprov.ttl`; results are parsed from text [validation §3.8, V16] | none |
| VAL-11 | `conformance.py:335-341, 565-574` `to_prov_o`, `_to_rdf_graph` | EXTRACT | `agentprov.prov.serialise.trig` (TriG, one named graph per bundle), produced on demand by `derive --trig DIR`; the PROV-JSON → PROV-O → PROV-JSON round trip stays a check in `agentprov.validate.roundtrip` (AD-10 row 3) | Belongs to serialisation. Instance IRIs collide across traces [validation §3.9, V13, V20] | none |
| VAL-12 | `conformance.py:52-89` `RELATION_KINDS`, `RELATION_ENDPOINTS`, `_ENDPOINT_BUCKET` | EXTRACT + GENERALISE | `agentprov.validate.prov_structure`, with tables covering every PROV-DM relation | Knows only seven relation kinds [validation V2] | none |

### B.2.4 Legacy import, replay and scoring (`convert_runs.py`, `replay.py`, `legacy_checkers.py`, `scoring.py`)

| Id | Existing component (file:lines) | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| LEG-01 | `convert_runs.py:211-408, 411-461` driver: `_is_log_json` (`:232-239`), filters, `--limit`, dry-run, counters, collision guard (`:377-382`), complete-pair resume (`:389-392`), `_update_excluded` (`:211-229`), `_reject_release_root` (`:242-260`), exit status | EXTRACT + GENERALISE | `agentprov.adapters.runner.import_source(…)` (D.2.9; D owns the signature), with parse/map in T1 workers (`agentprov.io.workers`) and writes through the corpus writer; resume keyed on `source_key` plus versions (B.6 R-09) | The control logic is correct and benchmark-independent. But resume and collision checks are per run and not keyed on source bytes, and the release guard is name-based [legacy §3.3, §3.6 D1/D9/D10, §5] | naming only |
| LEG-02 | `convert_runs.py:74-84, 133-208` constants, `_pipeline_folder`, `run_to_meta`, `_output_relpath`, `convert_run` | ADAPT | dialect `adapters/agentdojo/dialect.py` (`agentdojo.tracelogger`, variants `v0.k11` and `v1.k14` among D's names; string or content-block messages; optional `placeholder_args`; message-level features detected per B.6 R-01) + `adapters/agentdojo/mapper.py` (identity and outcomes), citing the catalogue `agentdojo.rules.toml` | The field map is AgentDojo-specific and lacks raw anchoring, schema dispatch, identity evidence, outcome origin and task-kind typing [legacy §3.4, §3.7, §12.2] | entirely |
| LEG-03 | `convert_runs.py:75-78, 166, 202-205` `TIMING_STUB = "0"`, `meta.timing_stubbed` | REPLACE | AER `unk` (`not_recorded`) on the typed time fields of `tool_execution` and `scope`; the verbatim stub stays in `t.raw` (`{"start": "0", "end": "0"}`, C.7.3), and the v1 view renders it from there (RESOLUTIONS R-30) | A sentinel in a `format: date-time` field. The schema check passes only because `format` is not asserted [legacy §3.6 D4, §4; D2 "sentinel values are forbidden" in typed fields] | none |
| LEG-04 | `convert_runs.py:80-84, 331-358` empty-message exclusion, `EXCLUDED.json` | GENERALISE | an AER with `unit: outcome_only` (only `execution` + `judgement` records) and seal issue `no_execution_observed`; index row with `unit` and `execution_observed: false` in `executions.jsonl` (RESOLUTIONS R-28; D9 as amended by AD-20) | The policy is right, but it needs hashes, reason codes, rule versions and stale-entry handling [legacy §4, §13; landscape/trace_formats.md §6.7] | AgentDojo empty `messages` (207 Opus logs; 2 more in ROPE) |
| LEG-05 | `convert_runs.py:87-130` `_README` caveats | ADAPT | a datasheet section generated from the corpus card and source profile (`agentprov.corpus.datasheet`, generated placeholders only; AD-10 row 9) | The text is June-2024 specific [legacy §13] | entirely |
| LEG-06 | `convert_runs.py:69` `from agentdojo_prov.generate import …` | REMOVE | none | Drags in `agentdojo`; an offline import must not need it [legacy §3.6 D8; D10] | none |
| LEG-07 | `replay.py:85-249` `REPLAY_FILE`, `NATIVE_SOURCE`, regexes `_IDS`/`_NAMES`/`_DRIFT`/`_STATE`/`_PROMPT_IDS`, `benchmark_of`, `_suite`, `_task`, `_cell_env`, `_check_injection`, `_cell_key`, `replay_trace` | DEFERRED (AD-10) | outcome replay is deferred to v0.2. If reinstated: a T1-restricted job in `backends/agentdojo` with no keys and no network, inputs named by digest, outputs over the pipe, a T-27 threat row and a specified protocol (RESOLUTIONS R-34) | Irreducibly AgentDojo. Version selection ignores `meta.benchmark_version` (R2) [legacy §7] | entirely (suite loading, private `_check_task_result`, `_get_next_id`, `ground_truth`) |
| LEG-08 | `replay.py:258-452` `_run`, `_winnable`, `_winnable_after_user_task`, `_utility_without_action`, `lost_task_values` and helpers | DEFERRED (AD-10) | with LEG-07. When reinstated, results are verification annotations with `ev: "I"` and rule ids | Heuristics presented as fields. An exception maps to `False`, conflating "cannot determine" with "cannot win" (R3) [legacy §7.5] | entirely |
| LEG-09 | `replay.py:455-497` `_one`, `replay_corpus`, `load_replay(required=)` | DEFERRED (AD-10) | with LEG-07. The contract (verification plugin, soft failure, per-cell cache, parallel driver, rows under `sem/` rather than in `outcome_replay.json`) is recorded in `docs/roadmap.md` | The row schema, soft failure, per-cell cache and parallel driver generalise [legacy §7.6, §12.3] | none |
| LEG-10 | `replay.py:500-530` `_untargeted`, `rerun_outcome_reproduced`, `outcome_disputed` | REMOVE | single implementation in `adapters/agentdojo/semantics/scoring.py` | Divergent copies; `None == None` counted as reproduced (R1) [legacy §7.5, §9 S3] | none |
| LEG-11 | `legacy_checkers.py:1-81` June-2024 workspace IT4/IT5 bodies (`:40-64`), `_LOGGING_ERA`, `LOGGED_VERSION`, `logging_era_checker` | DEFERRED (AD-10) | with LEG-07. When reinstated: in `backends/agentdojo` (T1-restricted), keyed by `(benchmark, era, suite, task)`; the era comes from source evidence (upstream commits `d32829e157…c274885610`), with repo, commit and blob `8ca9fef0…` recorded beside each body, and the AgentDojo MIT notice in `THIRD_PARTY_NOTICES.md` (U-12) | Verified identical to the upstream June blob [legacy §8] | entirely |
| LEG-12 | `scoring.py:1-98` `MARKER_ON_UNTRUSTED`, `untargeted`, `score_trace` | REFACTOR | `adapters/agentdojo/semantics/scoring.py`: `score(rec, row, *, run_error: bool, rule_set: Literal["agentdojo.scoring@1","agentdojo.scoring@2"]) -> Verdict` | Keeps the v2.3 rules reproducible under `@1` and fixes DoS gating (S1) under `@2`, with one implementation [legacy §9]. Replay is deferred (AD-10), so until it returns the replay-dependent inputs of `score` (`row`) exist only in the baseline environment. | DoS suffix, benign convention, `run_error` semantics, account rules |

### B.2.5 Corpus, statistics, export, analysis and rendering (`package.py`, `stats.py`, `ml_export.py`, `baselines.py`, `recompute.py`, `visualize.py`)

| Id | Existing component (file:lines) | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| COR-01 | `package.py:45-64, 115-190, 242-262` `_clean`, `_stem`, `build_manifest`, `write_manifests` | REFACTOR | `agentprov.corpus.manifest` + `agentprov.corpus.index` (`corpus.json`, `executions.jsonl`; schema `schemas/corpus-0.1.schema.json`) + AgentDojo facets from SEM (`adapters/agentdojo/semantics/manifest_ext.py`) | AgentDojo-shaped. No trace id, digests or derivation versions, and it uses pandas [corpus §3.1; D9]. The core corpus code MUST NOT import pandas (B.1.2). | task coordinates, outcomes, marker status, rerun, split |
| COR-02 | `package.py:80-112, 193-209` `_recorded_version`, `_tristate_counts`, `_rerun_counts`, `_record_counts`, `_render_base_for` | RETAIN | `agentprov.corpus.manifest` (recorded-version rule, tri-state tallies); render-base rule → `adapters/adprov/layout.py` | Correct and tested [corpus §3.1.2 rules 1, 2, 8] | release layout names |
| COR-03 | `package.py:471-497` `write_checksums` | GENERALISE | `agentprov.corpus.integrity` (`write_checksums(root: Path) -> Path`, `root_digest(root: Path) -> str`) | Manifests, datasheets and `EXCLUDED.json` are not hashed, and there is no root digest [corpus P3; BASELINE §8.6] | none |
| COR-04 | `package.py:263-470` `write_datasheet`; constants `package.py:31-42` (`NS_PREFIX`, `AGENTDOJO_VERSION`, `BENCHMARK_VERSION`, `TRANSCRIPT_SCHEMA`, `CORPUS_VERSION`) | REPLACE | `agentprov.corpus.datasheet.render(manifest, card: SourceCard) -> str`; constants dropped in favour of recorded values; wording checked by the shared claims library (`adapters/registry/claims.py`) | The converted datasheet makes false provenance claims through build constants and release-only prose [corpus P1, P7] | prose |
| COR-05 | `package.py:65-77` `_split_for` | DEFERRED (AD-10 row 1, with `export/ml`) | frozen baseline only. The legacy md5 split is not a corpus property and is not a v0.1 facet (HL H.1.7); its frozen definition stays in the baseline, which the old manuscript stays pinned to (D12). It is not part of the verbatim compat port, which holds only the five builder and validator files. Splits for new corpora are defined by an export view when `export/ml` returns | A published field read by the manuscript [corpus §3.1.2 rule 5] | entirely |
| COR-06 | `package.py:212-239` `with_replay_evidence` | ADAPT | `adapters/agentdojo/semantics/coordinates.py` (rule `agentdojo.record_complete_with_replay@1`: reserved; deferred with outcome replay, AD-10 row 2; not in the D.5.4 catalogue), applied only when verification rows exist, and recorded as applied. Replay is deferred (AD-10), so v0.1 does not apply it; the headline is 47 (RESOLUTIONS §1.3) | An optional input silently changes published counts (47 versus 52) [corpus P4; BASELINE §8.3] | replay evidence |
| COR-07 | `package.py:500-531` `main`, datasheet location rule (`:519-520`) | REPLACE | `agentprov package` (`agentprov.cli`; `agentprov.corpus.package`) | Superseded by the D9 layout | tree names |
| COR-08 | `stats.py:327-440, 449-531` `transcript_stats`, `prov_stats`, `trace_record`, `iter_transcripts`, `corpus_dataframe` | REPLACE (generic counts) + DEFERRED (AgentDojo frame) | generic counts → `agentprov.stats` and the `agentprov stats` command (AD-10 as ruled): counts per source and status; PROV statements by evidence class, bundle and rule; unknown-reason proportions; the per-source information-loss table (field-group coverage, RESOLUTIONS R-57). The AgentDojo-shaped `corpus_dataframe` and its column providers are DEFERRED; the paper owns its frames through `agentprov.api` | Mixes generic counts, AgentDojo semantics and heuristics; counts the last pass only (S1) [corpus §3.4]. The paper needs the generic counts and the information-loss table (Addendum B, AD-10). | column semantics |
| COR-09 | `stats.py:67-130, 252-306` `rerun_detected`, `record_complete`, `record_complete_with_replay`, `_ACCOUNT`, `user_prompt_names_attack_account`, `CHECK_MET_BY_USER_TASK`, `user_task_meets_injection_check` | EXTRACT | `adapters/agentdojo/semantics/coordinates.py` (SEM annotations with `ev` and rule ids); `CHECK_MET_BY_USER_TASK` becomes a data table of the SEM profile `agentdojo.suites` (PRJ-02) | AgentDojo ≤3-pass semantics and the banking confound [corpus §3.4.1] | entirely |
| COR-10 | `stats.py:140-233` `unexecuted_tool_call`, `narrated_tool_call` and their regexes | DEFERRED (AD-10) | `analysis/heuristics` is deferred. When ported: parameterised by the adapter tool catalogue, outputs `ev: "I"` | Calibrated on this corpus; specific to English and to this output format [corpus S7] | AgentDojo tool-name shape |
| COR-11 | `stats.py:236-247, 309-324` `pending_tool_calls`, `abnormal_finish` | GENERALISE | the facts are in AER: a request with no `tool_execution` carries the seal issue `unexecuted_tool_call` (RESOLUTIONS R-13), and `model_call.finish_reason` is the verbatim provider value (C). `agentprov.stats` counts seal issues per source | Generic once the canonical record carries the facts [corpus §3.4.3 (d)] | OpenAI finish-reason vocabulary |
| COR-12 | `stats.py:466-503` `write_cache`, `read_cache`, `CACHE_VERSION` | DEFERRED (AD-10) | `analysis/cache` and the derivation-keyed build cache are deferred (AD-10 rows 1, 11); `agentprov stats` computes without a cache. When ported: keyed on `(corpus root digest, engine/mapping versions, stats version)` | Bound to a version number, not to the corpus (S2) [corpus §3.4.3] | none |
| COR-13 | `stats.py:623-648` `conformance_summary` | ADAPT | `agentprov.validate.tiers`: the corpus validation report `validation/results.jsonl` + `validation/summary.json`, over every execution (required in the layout, AD-20); any sample is seeded and the seed recorded | The "first N" sample is biased (S3) [corpus §3.4.3; validation §9] | none |
| COR-14 | `stats.py:537-581` `entity_records`, `entity_dataframe` | DEFERRED (AD-10) | `analysis/labelling_audit` is deferred | The integrity × marker labelling audit [corpus §3.4.1] | marker normalisation |
| COR-15 | `stats.py:42-64` marker-status constants, `_iso`, `_tool_latency_s` | RETAIN (constants) / GENERALISE (`_iso` → AER time) | constants in `adapters/agentdojo/semantics/coordinates.py` (single definition, imported by `scoring`) | `MARKER_ON_UNTRUSTED` is duplicated in `scoring.py:31` (S4) [corpus §3.4.3] | marker-status vocabulary |
| COR-16 | `ml_export.py:1-833` sanitiser, `NODE_FEATURES`/`RELATIONS`/`FORBIDDEN`, `feature_errors`, `check_features`, `sanitize_graph`, splits, metrics, floors, `Dataset`, atomic build | DEFERRED (AD-10) | `export/ml` is deferred to v0.2, together with the normative blind view and its leakage test (AD-11). When ported: `sanitise`, `features`, `splits`, `metrics`, `dataset`, `build` | The strongest code analysed. Its couplings: the tool vocabulary comes from `agentdojo` at run time (`:164-171`), tree names are hard-coded (`:821`), instance ids sit in the vocabulary namespace, and `EXPORT_VERSION` was never bumped (`:51`) [corpus §3.5] | `TASKS`/`NON_TASKS`, scoring, replay requirement, README |
| COR-17 | `ml_export.py:91-111, 164-171, 603-710, 819-823` task definitions, `_tool_names`, README text, tree names | DEFERRED (AD-10) | with COR-16. When ported: `adapters/agentdojo/semantics/ml_tasks.py`, tool catalogue from profile data | No benchmark import; vocabulary comes from the adapter [corpus M2] | entirely |
| COR-18 | `baselines.py:52-184` `_reachable_from`, `flow_predicates`, `iter_prov_files`, `flow_baseline_dataframe`, `score` | DEFERRED (AD-10) | `analysis/flow` is deferred. When ported: evidence-class edge filter, labels and normaliser from the adapter, reading the assessment bundle (RESOLUTIONS R-34) | The deployable/oracle split and `score`'s refusals are correct. Reachability rests on visibility-inferred `used` edges (B1) [corpus §3.6] | tool tables, `adprov:` attributes |
| COR-19 | `baselines.py:194-353` `ARG_MIN_LEN(S)`, `_arg_leaves`, `_arg_evidence`, `argument_flow_predicates`, `argument_baseline_dataframe` | DEFERRED (AD-10) | `analysis/argflow` is deferred | Turn-aware visibility identical to the builder; `_norm_match` is applied to arguments (B4) [corpus §3.6] | YAML normaliser; `discarded_attempts` |
| COR-20 | `recompute.py:88-247` `recompute_corpus`, `main` | REFACTOR | `agentprov.corpus.derive.rederive(corpus: Path, *, dry_run: bool = True, staging: Optional[Path] = None) -> RederiveReport`, run by `agentprov recompute` (MN M.1.10 row 16) | The invariant is real, but it is checked as dict equality, dry-run skips validation, writes are non-transactional, and the module imports `agentdojo` (`:41`) [corpus §3.3]. D9 requires a content-addressed check. | import chain only |
| COR-21 | `recompute.py:48-85` `diff_documents` | RETAIN | `agentprov.prov.diff.diff_documents(old: dict, new: dict) -> list[str]`, used for the diagnostics of `agentprov recompute` (K RPR-1); the `diff` command is deferred (AD-10) | Generic, order-insensitive semantic diff [corpus §3.3] | none |
| COR-22 | `visualize.py:47-103, 115-205` colours, `_url_to_qid`, `_apply_flint_colors`, `render_prov_graph`, `DOT_TIMEOUT_S`, `_write_with_dot` | REFACTOR | `agentprov.render` and the `agentprov render` command (AD-10 as ruled): `render_prov_graph` ported to read `agentprov-prov/0.1` bundles, the core bundle only by default; extra `render` (pydot + Graphviz). `agentprov.render.dot.render(doc, out: Path, *, style: StylePolicy, bundles=("core",), formats=("svg",), direction="LR", show_element_attributes=True, simplify_labels=False, label_fontsize=None) -> list[Path]`; `agentprov.render.style` | Absent integrity is drawn as trusted (V1); node mapping is namespace-coupled; versions are not recorded [corpus §3.7] | colour keys on `adprov:integrity`/`adprov:role` |
| COR-23 | `visualize.py:106-112` `validate_prov_json` | REMOVE (renamed) | `agentprov.render.dot.parse_prov_json(doc) -> ProvDocument` | Misnamed: it parses and validates nothing [validation §9; corpus §3.7] | none |
| COR-24 | `visualize.py:208-230` `_write_pdf`; `visualize.py:234-240` `render_prov_json` alias | REFACTOR (`_write_pdf`: timeout + atomic) / REMOVE (alias) | `agentprov.render.dot` | No timeout and non-atomic (V3). The alias refers to the missing `live_run.py` [corpus §3.7] | none |

---

## B.3 Component table: `docs/`

| Id | Existing component | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| DOC-01 | `docs/capture_spec.md` title and §1–§3 (L1-59) | ADAPT | `docs/architecture/C_data_model.md` (C.13, `capture/0.1`; Addendum C-2) | The principle and AgentDojo source surfaces stay valid. The title ("FLINT") and status line ("139 tests") are stale [capture §4.8] | §3 entirely |
| DOC-02 | `capture_spec.md` §4–§4.3 (L60-243): transcript, reasoning, passes, completeness | ADAPT | `docs/architecture/C_data_model.md` (C.13, `capture/0.1`; Addendum C-2) + `docs/sources/agentdojo.md` (TR rules, pass semantics) | Corrections are needed: `placeholder_args` (F-01); "raw content" is the YAML-rendered, model-visible string; timing is keyed by (id, occurrence); losslessness has a stated scope [capture §4.8] | passes, YAML |
| DOC-03 | `capture_spec.md` §5–§7 (L244-497): derived PROV, ids, emission conditions, edge cases, decisions, marker guard | RETAIN (frozen; normative for compat only) | `docs/compat/adprov-v2.3.md`: a verbatim copy plus an errata list (§5.1 IRI-legality claim; dangling "§6.1" in §5.2; "live_run" in §7; the `build_prov.py:468` comment of F-78) | Matches the code line by line apart from the listed drift [provenance §12]. Superseded for new data by `agentprov-prov/0.1` (D7) | tables |
| DOC-04 | `capture_spec.md` §8–§9 (L498-557): conformance, implementation | REPLACE | the validator sections of `docs/architecture/` (D8 tiers; Addendum C-2): C.17 in `C_data_model.md` (tier 2), E.2 and E.5.5 in `EF_provenance.md` (tier 4), H.5 and H.8 in `HL_corpus_versioning.md` (tier 5) | Overclaims ("a real PROV-O guarantee"); stale check lists [validation V4, V17] | none |
| DOC-05 | `capture_spec.md` §10 (L558-563): re-run policy | ADAPT | `docs/architecture/HL_corpus_versioning.md`, H.8 (re-derivation; Addendum C-2) | The principle stays, generalised to content-addressed derivation (D9) | none |
| DOC-06 | `docs/transcript.schema.json` (232 lines; `$id` on github.io) | DEPRECATE (as canonical) / RETAIN (corrected import schema) | `src/agentprov/adapters/adprov/transcript_v1.schema.json` (pinned by digest, MN M.1.3) | Permissive (`additionalProperties: true`), with a four-suite enum and a wrong `placeholder_args` description (L168-171); `format` is not asserted [capture §4.8; legacy §3.6 D4]. The corrected copy MUST still validate all 35,691 stored transcripts. | suite enum |
| DOC-07 | `docs/ns/adprov.ttl` (158 lines, `owl:versionInfo "1.0"`, sha256 `4a9dcf4a…dca3`) | DEPRECATE (frozen; the hosted copy is untouched) + REPLACE (new vocabulary) | frozen byte copy `src/agentprov/prov/compat/adprov_v2_3/adprov.ttl`; new `src/agentprov/vocab/apv-0.1.ttl` (`owl:versionInfo "0.1.0"`) + `vocab/apv-adprov-map-0.1.ttl`; checked copy `docs/ns/apv-0.1.ttl` | Instance IRIs in the vocabulary namespace, no versioning or classes, ML-only terms mixed in, SHACL terms undeclared [provenance §9; D7] | integrity, role, channel, marker and defence terms |
| DOC-08 | `docs/ns/HOSTING.md` (41 lines) | ADAPT | `docs/ns/HOSTING.md` for `https://w3id.org/agentprov/`: prepared registration text, not submitted without the user's consent (D7; U-02) | Resolvability constraint; the legacy site must stay frozen [provenance §10] | none |
| DOC-09 | `docs/ns/index.html` (44 lines) | DEPRECATE | stays in the baseline repository, served by Pages (U-17); new HTML is generated from `apv-0.1.ttl` | Part of the frozen legacy namespace [provenance §10] | none |
| DOC-10 | `docs/ml_export.md` (133 lines) | DEFERRED (AD-10) | with the ML export (COR-16). When ported: §3–§5 as the AgentDojo export card (`docs/sources/agentdojo-ml-export.md`) and §1–§2 generalised (`docs/export/ml.md`) | Its numbers match the observed `REPORT.json` [corpus §3.9] | §3 task definitions |
| DOC-11 | gitignored local reports: `docs/convert_runs_plan.md` (623), `docs/convert_runs_report.tex` (1137) and its build artefacts (`.aux`, `.fdb_latexmk`, `.fls`, `.log`, `.out`, `.pdf`, `.toc`), `docs/corpus_differences.md` (325), `docs/framework_versions.md` (390) + `.tex`/`.pdf` | DEPRECATE | not copied; verified facts are restated with evidence in `docs/sources/agentdojo.md` | Unversioned and partly stale: eight inconsistencies listed [legacy §11, §13] | none |
| DOC-12 | `docs/stats.md` (640) + `.tex`/`.pdf`; `docs/fig_legacy_marker_status.{pdf,png}` | DEPRECATE | not copied (research notes) | Stale against v2.3 [corpus §3.9] | none |

---

## B.4 Component table: `tests/`

Function counts are `def test_` definitions; parametrisation brings the suite to 363 collected tests
[baseline/pytest.txt]. K owns test paths (K.2, K.3.1); the destinations below follow them. Every baseline test that
imports `agentdojo` (at least 73 of the 343 functions) moves to `backends/agentdojo/tests/`, where the pytest marker
`agentdojo` means "backend project", not "core extra" (RESOLUTIONS R-01).

| Id | Existing test file (lines; functions) | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| TST-01 | `tests/test_attempts.py` (669; 38): a scripted `_FakeClient` drives banking `user_task_1` through `make_instrumented_pipeline`. It covers passes, passback, failures, the gate, env diffs, resume, atomic writes, log merge, config refusal, schema, defended refusal, and the dot timeout (L590-604) | ADAPT | `backends/agentdojo/tests/` (D.10.8): the K.8.1 live-capture tests (passes and retries, accounting, resume, defended refusal), with `agentprov_backend.testing.ScriptedTransport` in place of `_FakeClient`; core-side assertions on `capture/0.1` and AER run on committed capture fixtures (`tests/adapters/agentdojo/test_capture_reader.py`, `test_capture_mapping.py`); L590-604 → the render tests (AD-10 as ruled) | The key integration harness. Its scripted-client pattern becomes the standard backend harness (D5). Assertions move from transcript fields to `capture/0.1` events and AER [capture §4.9] | a real AgentDojo task |
| TST-02 | `tests/test_reasoning.py` (212; 14) | ADAPT | `backends/agentdojo/tests/` (gateway and LLM-element tests, K.2 `test_model_gateway.py`, `test_reasoning_capture.py`), because they import `agentprov_backend` | Effort placement; reasoning kept out of the scored content [capture §4.9] | passback |
| TST-03 | `tests/test_capture.py` (528; 30) | ADAPT (split) | mapping → `tests/integration/test_live_mapping.py` (fixtures only); executor timing → `backends/agentdojo/tests/` (executor mirror, K.9.4); marker, time and graph tests → `tests/prov/compat/adprov_v2_3/` and `tests/unit/sem/test_injection_marker.py` | Mixes concerns [capture §4.9; provenance §11]. `test_turn_without_a_timestamp_falls_back_to_the_run_start` (L436) is compat-only. `test_external_content_coverage_has_no_gaps` (L307) is tautological and is replaced by a vector→reader-map test | none |
| TST-04 | `tests/test_envstate.py` (53; 7) | RETAIN | `capture/tests/test_envstate.py`, exercising `agentprov_capture.envstate` | Generic [capture §4.9] | none |
| TST-05 | `tests/test_generate.py` (17; 1) | RETAIN | `tests/unit/validate/test_write_gate.py` | Checks that the gate refuses a malformed graph before any write [capture §4.9] | none |
| TST-06 | `tests/test_prov_builder.py` (556; 42) | RETAIN (port, split) | builder, marker and id tests → `tests/prov/compat/adprov_v2_3/test_builder.py`, `test_marker_yaml_styles.py`; labelling basics → `tests/unit/sem/`; `TestProvObserver` (L150-330) → removed with CAP-08; tests that import `agentdojo` (placeholder string, suite-table names) → `backends/agentdojo/tests/` | A strong regression oracle [provenance §11] | ten `agentdojo` imports |
| TST-07 | `tests/test_communication.py` (471; 42) | RETAIN (port) | `tests/prov/compat/adprov_v2_3/test_communication.py`; in-loop parity tests (L196-212, L287-312, L396-413) are removed | Holds most of the I7–I9 negative controls [validation §3.10] | three `agentdojo`-importing tests |
| TST-08 | `tests/test_prov_conformance.py` (79; 4) | RETAIN | `tests/unit/validate/test_prov_structure.py`, plus builder-independent fixtures | [validation §3.10] | none |
| TST-09 | `tests/test_conformance_provo.py` (212; 14) | RETAIN + EXTEND | `tests/unit/validate/test_serialisation_fidelity.py`, `test_prov_constraints.py`, `test_time_flags.py` (K.2) | Add a negative control for `round_trip`, unknown sections, foreign prefixes and datatypes [validation §3.10] | none |
| TST-10 | `tests/test_convert_runs.py` (785; 42) | ADAPT | writer semantics → `tests/integration/test_offline_import_e2e.py`; mapping → `tests/adapters/agentdojo/test_tracelogger_v0_k11.py`; recompute no-op and the `"0"` completeness regression → `tests/reproducibility/test_recompute.py` and `tests/adapters/adprov/` | Strong. Missing cases: the 2025 dialect, pipeline ≠ folder, `placeholder_args`, task-kind typing [legacy §10] | fixtures |
| TST-11 | `tests/test_replay.py` (278; 19) | DEFERRED (AD-10) | with replay (LEG-07). When reinstated: `backends/agentdojo/tests/`, adding `benchmark_of` against the recorded version, DoS rows, and exception → `None` [legacy §10] | Replay executes benchmark code and is deferred to v0.2 (RESOLUTIONS R-34) | most tests use `importorskip("agentdojo")` |
| TST-12 | `tests/test_scoring.py` (78; 9) | RETAIN | `tests/adapters/agentdojo/test_scoring_rules.py`, run under both rule sets | Add DoS with `injection_check_winnable False` [legacy §10] | none |
| TST-13 | `tests/test_package.py` (185; 11) | ADAPT | `tests/unit/corpus/test_manifest.py`, `test_checksums.py`, `test_datasheet.py`; render-base tests → `tests/adapters/adprov/` (legacy layout reader) | No tests of datasheet content, DoS counting or reproducibility [corpus §3.10] | none |
| TST-14 | `tests/test_stats.py` (215; 17) | ADAPT (split) + DEFERRED | generic counts → the `agentprov.stats` tests (K adds the module, AD-10 as ruled); coordinates → `tests/adapters/agentdojo/test_semantics_profile.py`; tests of the AgentDojo frame are deferred with it (COR-08) | [corpus §3.10] | none |
| TST-15 | `tests/test_ml_export.py` (477; 28) | DEFERRED (AD-10) | with the ML export (COR-16); adds export versioning and validation of sanitised graphs when ported [corpus §3.10] | The export is deferred to v0.2 | none |
| TST-16 | `tests/test_baselines.py` (138; 12) | DEFERRED (AD-10) | with `analysis/flow` and `analysis/argflow` (COR-18, COR-19); adds `flow_predicates` and `score` when ported [corpus B5] | The baselines are deferred to v0.2 | none |
| TST-17 | `tests/test_recompute.py` (228; 11) | ADAPT | `tests/reproducibility/test_recompute.py` | Add a type-only change (`True` → `1`), a mid-run gate failure, and dry-run validation [corpus §3.10] | none |
| TST-18 | `tests/test_scripts.py` (62; 2) | REPLACE (launcher test) + DEFERRED (slow confound test) | launcher → `tests/cli/` run-contract tests (spawned worker, per-plan lock, signal-safe teardown, non-zero exit on any failure; I-14); confound probe → deferred with PRJ-02 | [corpus §3.8, §3.10] | confound probe |
| TST-19 | `tests/__init__.py` (empty) | REMOVE | none; `tests/conftest.py` provides shared fixtures | Not needed with `testpaths` | none |
| TST-20 | `tests/fixtures/native_benign_claude-3-haiku_bank_user_task_9.json` (sha256 `c96a325a…`), `tests/fixtures/native_injection_gpt4o_spotlighting_workspace_user_task_25.json` (`294d9d58…`) | RETAIN | `tests/fixtures/agentdojo/2024/`, with an origin record (repo `ethz-spylab/agentdojo`, commit `c274885610efaaafec38b6d3eb07152ba7ff3f94`, path, blob SHA-1) and the licence basis "MIT by repository; data licence not separately stated" (U-03). Committed to the private repository only, never in the sdist (U-06; Addendum B, B-2), and marked `binary` in `.gitattributes` (RESOLUTIONS R-42) | Byte-identical to the upstream June logs [legacy §10; BASELINE §7 C01/C02]. The data licence is not separately stated [legacy §15] | none |

---

## B.5 Component table: scripts, project files and untracked material

| Id | Existing component | Decision | Destination | Rationale (evidence) | AgentDojo-specific parts |
|---|---|---|---|---|---|
| PRJ-01 | `scripts/run_full_corpus.sh` (198) | REPLACE | `agentprov run --plan <plan.toml>`: the parent (`agentprov.cli.run`) spawns `<env>/bin/python -I -B -m agentprov_backend.worker` per cell, with the backend environment built by `agentprov backends build` outside the repository (AD-01(c)); release plan `plans/agentdojo-v1.2.2-release.toml` reproduces the 18-worker matrix | The matrix is hard-coded, and the benign traces depend on the `direct` batch [capture §4.6]. The per-model lock, signal-safe teardown and non-zero exit on any worker failure (L38-60, L177-198) MUST be preserved (I-14) | suites, attacks, id format |
| PRJ-02 | `scripts/check_task_confounds.py` (82) | DEFERRED (AD-10) | the confound probe is deferred. `adapters/agentdojo/semantics/coordinates.py` reads a confound table of the SEM profile `agentdojo.suites`, ported as data from `CHECK_MET_BY_USER_TASK` (COR-09); re-verifying it with the probe waits for v0.2 | The expected set is hard-coded twice, which makes that check circular; the two empirical checks are real [corpus §3.8] | entirely |
| PRJ-03 | `pyproject.toml` (53) | REPLACE | new `pyproject.toml` per MN M.2: `requires-python = ">=3.14"` and `.python-version` `3.14` (AD-16 as ruled: archive and compressed-stream ingestion refuses to run below 3.14.8 in release mode (`--release`, `package`, `release`), and in dev mode warns and records `python_version` and `interpreter_advisory`); core deps `prov`, `rdflib`, `rfc8785`, `pyyaml`, `agentprov-capture`; extras `live`, `shacl`, `render`, `dev`; src layout; `uv.lock` committed | One dependency set that includes the manuscript's dependencies; RDF libraries unpinned [corpus §3.9; validation V19] | the `agentdojo==0.1.35` pin moves to the backend project `backends/agentdojo/` (AD-01) |
| PRJ-04 | `.gitignore` (57) | ADAPT | new `.gitignore`: keep `corpus/`, `runs/`, `.env` and raw stores; add `*.log` and `CLAUDE.local.md` (RESOLUTIONS R-52); drop the vendored-directory entries; version the agent guidance. `.gitattributes` marks `tests/fixtures/**` as `binary` (R-42) | [corpus §3.9] | none |
| PRJ-05 | `CHANGELOG.md` (711) | RETAIN (historical, in the baseline repository) | not copied. A new `CHANGELOG.md` keeps separate streams (software, `aer`, `sem`, `capture`, `agentprov-prov`, `apv`, adapters, corpora; D9) | It mixes code and data changes under one corpus version [corpus §3.9] | none |
| PRJ-06 | `DATASHEET.md` (145; v2.3 release) | REPLACE (template) / RETAIN (historical record) | a `DATASHEET.md` generated per corpus (`agentprov.corpus.datasheet`) + the corpus card `docs/sources/agentdojo.md` | Release-specific prose; "lossless transcript" claim [corpus §3.2] | prose |
| PRJ-07 | `README.md` (399) | ADAPT | new README, whose coverage wording is checked by the shared claims library (AD-08); AgentDojo content → `docs/sources/agentdojo.md` | An accurate overview with an incomplete API list [corpus §3.9] | none |
| PRJ-08 | `LICENSE` (MIT, sha256 `026dc92c…`) | RETAIN | `LICENSE` (code, MIT) + `THIRD_PARTY_NOTICES.md` (U-12); data licences per corpus under `LICENSES/` (D9) | GitHub detects NOASSERTION although the text is MIT [BASELINE §1.1]. The data licence of upstream-derived logs is not separately stated [corpus §9 item 16; legacy §15] | none |
| EXT-01 | `CLAUDE.md` (gitignored, 107 lines) | DEPRECATE | versioned successors in the new repository: `AGENTS.md`, and `CLAUDE.md` pointing to it (RESOLUTIONS R-50) | Stale: "exactly `max(n-1,0)` wasInformedBy" (L85); lists only 5 of the 18 public symbols [validation §4, V17; BASELINE §8.5; corpus §4] | none |
| EXT-02 | `code-review.md`, `code-review-repo.md` (gitignored) | REMOVE | none | Local working notes dated 2026-09-29. Read on 2026-10-07 (read-only, B.12): their fixes are already in `579a908`, and their findings map to existing rows; nothing in them needs porting | none |
| EXT-03 | vendored `AgentDyn-main/`, `ROPE-main/`, `agentdojo-inspect-main/` | REMOVE | pinned upstream fetch through `agentprov fetch` (`raw/fetch.py`; D3) | No `.git`, so the commit is unknown [capture §0.3] | none |
| EXT-04 | `.claude/worktrees/intelligent-haibt-1cc805/` (HEAD `77b0152`) | REMOVE | none | Holds an older `validate.py` and shape: "do not port from it" [validation §0] | none |
| EXT-05 | `runs/` (18,234 June-2024 logs, gitignored) | REMOVE (from the repository) | raw store, fetched by blob from `ethz-spylab/agentdojo@c274885610efaaafec38b6d3eb07152ba7ff3f94:runs/`. The import uses the 18,241 pinned blobs (including 7 Mixtral logs); the local copy is used only for gate G0 (RESOLUTIONS R-32) | All 18,234 local files are byte-identical to the upstream blobs [legacy §2.1; D3] | none |
| EXT-06 | `corpus/corpus-prov/`, `corpus/corpus-og-agentdojo-runs-prov/`, `corpus/corpus-ml/` | REPLACE | AgentPROV corpora (D9): the v2.3 release re-imported through the v1 importer (`adapters/adprov/`); the June-2024 logs re-imported through the TraceLogger dialect (`agentdojo-upstream`); the converted tree kept as a `compat_oracle` part (B.6 R-05); the ML export deferred (AD-10) | No source anchors; converted transcripts were regenerated in place [legacy §3.6 D1, §13] | none |
| EXT-07 | `investigation/baseline/golden/` (15 pairs, 7 native logs, `golden_index.json`) | RETAIN | `tests/fixtures/agentdojo_prov_v1/golden/` plus the four MIG-10 pairs (RESOLUTIONS R-59); the native logs under `tests/fixtures/agentdojo/2024/`. Committed to the private repository only (U-06) | The CI gate for D7 byte identity (E1) [BASELINE §7] | none |
| EXT-08 | `agentdojo_prov.egg-info/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.DS_Store` | REMOVE | none | Build and OS artefacts | none |

---

## B.6 Reconciliation of audit disagreements

**R-01. `placeholder_args`.**
- The capture audit says it never appears on model calls: 0 of 133,602 calls in both trees, and it is a
  ground-truth-only field in 0.1.35 [capture §3, §8 D1].
- The legacy audit says newer upstream logs carry it on tool calls (10 pipelines) [legacy §2.1, §4].
- Both are right. In post-June-2024 logs the key is serialised with value `null` (E3), which is a dump
  artefact of the `FunctionCall` model, not pre-injection arguments.
- Ruling: the TraceLogger dialect MUST pass the key through verbatim into `ext.agentdojo` and MUST NOT turn it
  into a core field. No mapping rule MAY interpret it (F-01).
- E3 also refines the legacy audit's two-schema picture (11 June keys versus 14 keys) [legacy §2.1]. An 11-key
  log can still carry `placeholder_args`. So the dialect reader MUST detect message-level features (string
  versus content-block `content`, presence of `placeholder_args`, null tool-call ids) independently of the
  top-level key set. The header variant goes in the AER header `dialect {id: "agentdojo.tracelogger", variant}`
  (D's names, e.g. `v0.k11`, `v1.k14`), and the detected message-level features go in `ext.agentdojo`.

**R-02. Where `validate.py` goes.**
- The provenance audit says: split into generic validity, a vocabulary contract and policy conformance
  [provenance §7.6].
- The validation audit adds: GENERALISE I2–I8 into a reusable "turn-structured tool-call profile"
  [validation §3.2, §9].
- Ruling:
  - generic checks → new validators in `agentprov.validate.prov_structure` (VAL-01);
  - I1–I11, S2 and S8 → the verbatim compat port `prov/compat/adprov_v2_3/validate.py` (VAL-02; RESOLUTIONS
    R-31).
- The I2–I8 generalisation is **not** done in v0.1. Under D7, `agentprov-prov/0.1` has ModelInvocation and
  ToolExecution activities, and its `wasInformedBy` statements are exactly the Inference-6 closure over named
  activities (AD-19), so I7's previous-turn bipartite rule has no consumer. The new specification's profile rules
  are defined by EF.

**R-03. How the compat oracle works.**
- The provenance audit and prov_semantics §11 obtain v2.3 as a projection of the decomposed core
  [provenance §5.3, §16.4; landscape/prov_semantics.md §11].
- The validation audit keeps I1–I11 bit for bit [validation §3.2].
- D7 decides: the baseline `build_prov` is ported verbatim and run on a v1 view regenerated from AER.
- Ruling: D7 governs. The oracle is the five baseline files ported verbatim, AST-equal (RESOLUTIONS R-31). The
  projection is kept only as the documented semantic diff (D7 "semantic-diff"), whose single machine-readable form
  is `prov/compat/semdiff-map.toml`, owned by EF (RESOLUTIONS R-33). What "regenerated from AER" means is settled
  by AD-02 (B.7.1): the view is regenerated from the AER alone through a deterministic view.

**R-04. A compatibility shim for the manuscript.**
- The corpus audit recommends an `agentdojo_prov` shim that re-exports 18 symbols [corpus §4].
- D12 pins the old manuscript to `579a908` with no shim.
- Ruling: D12 governs, and no shim is built. The AgentDojo analysis frame is deferred (AD-10), and the paper owns
  its frames through `agentprov.api`, with names that follow MN M.6 (RESOLUTIONS R-64). Column names SHOULD stay
  the same where the meaning is unchanged, so that the new figure pipeline can reuse code, but nothing obliges
  this.

**R-05. The converted legacy tree.**
- The legacy audit says REPLACE it by re-importing from the pinned upstream commit [legacy §13].
- D11 supports the v1 importer for transcript/v1, and D7 needs the 18,027 converted graphs as an oracle.
- Ruling, which uses both routes:
  1. The authoritative AgentPROV corpus for the June-2024 logs is the TraceLogger re-import, with raw
     evidence = upstream blobs.
  2. The converted tree `corpus-og-agentdojo-runs-prov` is a `compat_oracle` part. Its v1 import feeds the compat
     regression gates (gate B, and the R1/R2 `render_converted` byte gates on the golden converted pairs) and is
     not packaged as a corpus. Its lineage to the native log is recorded as `ev: "I"`, matched on path, because
     the converted transcripts carry no source anchor (F-45). Only a 0-mismatch pass of the full gate R over the
     18,027 converted graphs licenses the statement that the native re-import supersedes the converted tree;
     otherwise the mismatch report is published (AD-07).
  3. The v2.3 release (17,664) has no rawer evidence, so the v1 import of the released transcripts is
     authoritative for it.

**R-06. Where re-derivation lives.**
- The corpus audit proposes `agentprov.engine.rederive` [corpus §3.3].
- D9 frames recompute as a corpus-level, content-addressed check.
- Ruling: the driver lives in `agentprov.corpus.derive` (`rederive()`, run by `agentprov recompute`; MN M.1.10
  row 16). The pure functions it calls (map, semantics, provenance) stay in their own packages. Archive members are
  re-expanded by the `expand` stage and must reproduce identical member digests (AD-12).

**R-07. `stats.conformance_summary`.**
- The validation audit says ADAPT to the validation report [validation §9]. The corpus audit says RETAIN in
  the validation layer [corpus §7].
- Ruling: ADAPT (COR-13). Fixing the biased sample changes the behaviour.

**R-08. Strength of the recompute invariant.**
- The corpus audit observes that recompute checks dict equality, not bytes [corpus §3.3 R2].
- D7 demands byte identity.
- E1 shows byte identity actually holds on all 35,691 pairs, with serialisation `json.dumps(doc, indent=2)`:
  insertion order, `ensure_ascii=True`, no trailing newline (`generate.py:468`).
- Ruling: the compat gate compares bytes (I-19). Any compat serialiser MUST reproduce that exact call.

**R-09. Resume key.**
- The capture audit says: a sealed raw-evidence manifest [capture §4.5].
- The legacy audit says: complete pair, plus source sha256 and adapter/mapping versions [legacy §5].
- The baseline uses the existence of the derived graph (G-3).
- Ruling: the resume unit is one execution. Its key, written in the corpus layer's `<id>@<version>` form
  (RESOLUTIONS §3.5), is
  `(source_key or capture session id, adapter@version, catalogue versions {<ns>: <int>}, semantics@version, spec@version)`.
  - Sealed raw evidence is never re-executed.
  - A derived artefact whose key differs is re-derived.
  - A cell whose raw capture is unsealed is re-attempted under a new attempt index (`capture.attempt`); the
    earlier attempt is kept (F-05).

**R-10. Empty executions.**
- The legacy audit says: exclude and register them [legacy §14.5].
- landscape/trace_formats.md §6.7 and D5 say: keep them as records.
- Ruling: an AER with `unit: outcome_only`, only `execution` + `judgement` records and the seal issue
  `no_execution_observed`, indexed with `unit` and `execution_observed: false` (RESOLUTIONS R-28). This covers
  the 207 AgentDojo and 2 ROPE logs with `messages: []`. No trajectory is fabricated (LEG-04).

**R-11. `record_complete`: 47 or 52 converted.**
- The figure is 47 from the stats rule and 52 when replay evidence is merged [BASELINE §8.3; corpus P4].
- Ruling: these are two fields with different evidence:
  - `record_complete` (observed from capture, or derived by `agentdojo.null_final_implies_three_passes@1`, D.5.4);
  - `earlier_pass_evidence` (inferred by the replay plugin).
- They MUST NOT be merged silently. The rule `agentdojo.record_complete_with_replay@1` (reserved; deferred with
  outcome replay, AD-10 row 2; not in the D.5.4 catalogue) would reproduce the published 52 when verification rows
  exist, and the manifest would record that it was applied.
- Disposition (RESOLUTIONS §1.3): the headline is **47** (structural). The 52 stays a separate,
  evidence-qualified field. Replay is deferred (AD-10), so v0.1 does not recompute it.

**R-12. Hash notation.**
- `envstate` digests are bare hex [capture §4.4 E-2]. Transcript and graph hashes are `"sha256:"+hex`
  [provenance §6].
- Ruling, unless the AER section states otherwise:
  - fields whose name ends in `sha256` carry 64 lower-case hex characters without a prefix;
  - blob references use the form `{"$blob": "sha256:<hex>"}` (D2);
  - compat output keeps `adprov:content_hash` = `"sha256:"+hex` verbatim.

**R-13. Unexecuted tool calls in the converted tree: 153 or 141.**
- The legacy audit gives 68,773 requested versus 68,620 executed = 153 [legacy §2.4].
- The provenance audit gives 141 calls with no matching tool turn, matched by id [provenance §2].
- Ids are null, empty or duplicated in 2,175 converted traces [BASELINE §5.1], so id matching under-counts.
- Ruling: AER mappers MUST pair requested and executed calls positionally within a batch (valid for 68,620 of
  68,620 June calls [legacy §2.4]), recorded as `ev: "I"` with the rule `agentdojo.positional_match@1`
  (D.5.4; the v1 importer applies the same pairing under its own catalogue). They MUST report **153**
  unexecuted requests for that tree: request parts with no `tool_execution`, flagged by the seal issue
  `unexecuted_tool_call` (RESOLUTIONS R-13; there is no `tool_execution` status for them). In the release both
  methods agree on 48 [capture §7.6].
- Confirmed by RESOLUTIONS R-33: 153 (positional) is the reported count of unexecuted requests, and EF's 141 is
  corrected in `prov/compat/semdiff-map.toml`.

**R-14. Where `check_suite_coverage` runs.**
- The capture audit says it is an interpretation concern inside capture [capture §4.5].
- The provenance audit says RETAIN as a validator [provenance §7.3].
- Ruling: `agentprov.validate.profiles` (policy-coverage guards), invoked at semantics time and never during
  live capture (CAP-26, PRV-18).

**R-15. Splitting `test_capture.py`.**
- The capture audit sends its mapping tests to the adapter [capture §4.9]. The provenance audit claims its
  run-start fallback test for compat [provenance §11].
- Ruling: split as in TST-03. The fallback test is compat-only, because the fallback is removed from the
  engine (F-24).

**R-16. Tool-free converted graphs.**
- `corpus_differences.md` says 832. The baseline says 762.
- Ruling: 762 is correct (832 is the count before exclusion) [legacy §11 item 1; BASELINE §5]. The golden and
  regression gates use 762.

---

## B.7 Challenges to the decision brief (resolved)

### B.7.1 What the compat view must reproduce

**Finding (still valid).** D7 makes the regression gate "byte-identical graphs for the frozen baseline … run on a
transcript/v1 *view regenerated from AER*". D2 serialises every AER line in RFC 8785 (JCS) form, which re-orders
object members lexicographically and rewrites numbers in shortest ECMAScript form (`100.0` → `100`). The compat
graph embeds tool arguments as `adprov:args = json.dumps(args, default=str)` (`prov_emit.py:124-127`), which
preserves source key order and the float lexical form. E2 shows that 12,676 of 64,781 released activities have
non-lexicographic argument key order and 313 contain integral floats (converted tree: 12,862 and 1,681), so that
8,037 released and 8,341 converted graphs, roughly 46% of the corpus, are affected. A view built only from
JCS-normalised values cannot pass the byte gate, and Python dict equality would hide this, because key order is
ignored and `100.0 == 100` [corpus §3.3 R2].

> **Resolved (AD-02 / RESOLUTIONS R-04):** One mechanism, C's sparse `ext.lex {ord, flt}`, written by the shared
> helper `agentprov.aer.canon.lex_hints()`. It covers every object and number copied from a source, typed fields
> included, and is mandatory for dialects with a byte-exact view (`adprov.transcript_v1`, and
> `agentdojo.tracelogger` while `render_converted` is a gate). The transcript/v1 view
> (`views/transcript_v1.py`: `render(aer) -> dict`, `serialise(dict) -> bytes`) reads **nothing** from raw, so the
> claim is "regenerated from the AER alone through a deterministic view". Gates are A1 (JCS value identity), A2
> (bytes) and B (compat graph bytes), and no gate or round-trip test uses Python `==`. The raw-side re-read
> proposed in r1 is rejected. `args_raw` keeps its own meaning: the verbatim transmitted text.

### B.7.2 PyYAML as a core dependency

> **Resolved (AD-17 / RESOLUTIONS R-47):** Accepted. `pyyaml` (locked at 6.0.3) is a core runtime dependency,
> imported only by `ingest/yamlsafe.py`, which the SEM marker and the compat port's `safe_load` shim use; the
> import-boundary test enforces this (B.1.2). The bounded loader refuses input above the tier-1 size limit, and a
> refused document gives the SEM marker status `ambiguous` (RESOLUTIONS R-18). The bound cannot alter any stored
> graph: E1 re-derived all 35,691 graphs with unbounded `safe_load`, the shim changes no frozen byte and is
> recorded in `PORT_MANIFEST.json` (RESOLUTIONS R-31), and the bound MUST be set above the largest tool output in
> the frozen corpora. Readers and loaders never parse YAML, which keeps A1's "stdlib-only for parsing untrusted
> bytes" [provenance §14 D19].

---

## B.8 Invariants the port MUST preserve

Each invariant names its source. "Compat" means it binds the `adprov-v2.3-compat` profile only. Every other
invariant binds the new code paths too. Invariants of components deferred by AD-10 bind their port when it
returns.

**Live capture** (in `agentprov_backend` and the backend projects, AD-01)

Under AD-09 the default LLM element is the stock agentdojo element (`native`), recorded at the transport level.
I-02 to I-05 describe the baseline `_CompatLLM` and therefore bind the opt-in `gateway_compat` element only;
whichever element runs, every model response is recorded and the resample and retry counts are recorded per
execution.

- **I-01.** Instrumentation never alters what the benchmark scores. In particular, reasoning never enters the
  scored assistant message (RT-1) [capture §4.1; `runtime.py:356-370`].
- **I-02.** (`gateway_compat`.) Every kept model reply is recorded exactly once per per-call log, and the call
  counter increments unconditionally. A failure in reasoning extraction yields `None`, never a skipped entry
  (RT-2) [`runtime.py:358-370`].
- **I-03.** (`gateway_compat`.) Request parity with the release, unless the run plan says otherwise, recorded as
  declared `request_modifying`/`harness_policy` instrumentation (D5; AD-09) [`runtime.py:57-68, 239-243,
  277-295`]:
  - no reasoning parameter unless configured;
  - temperature sent as `temperature or NOT_GIVEN`;
  - OpenRouter effort in `extra_body`;
  - `developer` → `system` rewrite.
- **I-04.** (`gateway_compat`.) The retry taxonomy RT-4 (429 backoff; connection/timeout; at most 3 5xx; other
  4xx raise; malformed tool-call JSON resampled up to 8; upstream failure retried up to 8) is kept as its default
  `RetryPolicy`. Every attempt is recorded [`runtime.py:267-351`].
- **I-05.** (`gateway_compat`.) `reasoning_details` passback is reset at an AgentDojo pass boundary (RT-5)
  [`runtime.py:251-252`; `tests/test_attempts.py:90-92`].
- **I-06.** Pass recording follows OB-1…OB-5 [`observer.py:70-169, 283-289`; CHANGELOG L196-201]:
  - the recorder is placed around the whole pipeline;
  - logs are reset per pass;
  - an unknown call count is `None`, never `0`;
  - environment recording errors never kill a run;
  - every completed pass is kept in order, and the last pass is the scored one.
- **I-07.** Tool timing is keyed by call occurrence, never by provider id alone. Undispatched (empty or
  invalid) calls are timed too (OB-6) [`observer.py:216-221`].
- **I-08.** Defended or non-YAML AgentDojo pipelines are refused with a typed error in v0.1, until a
  generalised gate covers auxiliary LLM calls (OB-8; RESOLUTIONS §1.3). Auxiliary roles are accounted in AER
  only for imports [`observer.py:484-487`; capture §4.2.5].
- **I-09.** An assistant text is `null` iff the native content is `None` (TR-1). Positional reasoning and
  refusal alignment happens only when counts are equal and never overrides native reasoning (TR-3, TR-4), and
  it carries `ev: "I"` (F-10). An absent pass count means unknown (TR-8)
  [`transcript.py:80-86, 115-130, 240-251`].
- **I-10.** Writes are atomic: a temporary file beside the target, then `os.replace` (TR-10)
  [`transcript.py:273-279`].
- **I-11.** Environment digests follow E-1…E-5, and pass chaining holds: `before` of pass p+1 equals `after`
  of pass p [`envstate.py`; `tests/test_attempts.py:207`].
- **I-12.** Evidence is persisted before derivation. A derived artefact is written last and atomically.
  Rendering never runs in the backend worker (N-23), so a render failure cannot kill one (G-1, G-2)
  [`generate.py:311-325, 441-468`].
- **I-13.** A fresh pipeline, LLM element and capture session for every cell (G-8)
  [`generate.py:496-502, 571-578`].
- **I-14.** A run reports success only when every cell succeeded, and error rows are excluded from printed
  rates (G-6). The parent keeps a per-plan lock, signal-safe teardown and a non-zero exit when any worker fails
  [`generate.py:896-902`; `scripts/run_full_corpus.sh:38-60, 177-198`]. The codes are MN N.1.3's: 0 when all
  succeeded, 1 when any failed. The baseline's 2 ("some failed") maps to 1, because 2 is a usage error in
  AgentPROV (RESOLUTIONS §3.7).

**Provenance derivation (compat unless stated)**

- **I-15.** Purity, for both compat and core: a graph is a function only of its inputs (record and flags today;
  AER, SEM and spec under D7). No clock, randomness, network or environment
  [provenance §13.1; landscape/trace_formats.md §6.11].
- **I-16.** Stream rules [provenance §13.2]:
  - `discarded_attempts[*].turns` oldest first, then `turns`;
  - one activity and one output entity per tool turn;
  - exactly one `e_user_query`, taken from the first user turn of the final pass;
  - exactly one `ag_llm`, even with zero tool turns.
- **I-17.** The id rule [provenance §13.3, §7.1.7]:
  - `unique_loc`, with `RESERVED_LOCS = {"user_query"}` and the `tc_step{n}` fallback;
  - relation ids `adprov:<prefix>_<5-digit shared counter>`;
  - emission order: activity, entity, `wasGeneratedBy`, informants/query `used`, sink taint, `wasAssociatedWith`,
    then ⊥ bookkeeping.
- **I-18.** The rules for generation, association, communication, usage, passes and times hold exactly as in
  [provenance §13.4–13.8]. This includes the shared-start withholding and the two fallbacks (compat only).
- **I-19.** Compat serialisation is `json.dumps(doc, indent=2)`, UTF-8, no trailing newline. Only the `adprov`
  prefix is declared, `prov` never; empty sections are omitted; `adprov:args` is a JSON string; the namespace
  IRI is exact [provenance §13.10; E1; `generate.py:468`].
- **I-20.** Flags default to off and only add [provenance §13.11].
- **I-21.** `payload_marker` has a single definition per version in new code
  (`adapters/agentdojo/semantics/marker.py`, `payload_marker_v1`). The compat port keeps the baseline definition
  verbatim (RESOLUTIONS R-31), and a differential test pins `payload_marker_v1` to it on the frozen corpora; any
  behavioural change is a new version. It is YAML-aware and keeps all six readings plus the parsed fallback. The
  marker is absent when no payload is registered, and the user query never carries one [provenance §7.1.4,
  §13.9; legacy §14.12].
- **I-22.** Order is attribute data (`adprov:step`, `turn`, `attempt` in compat; `apv:` order attributes in
  core), never a PROV relation. No relation is asserted from temporal adjacency
  [corpus §8.17; validation §8.10; D7].
- **I-23.** A time appears in a graph only where a true timestamp was recorded, and an absent time is omitted,
  never written as `""`, `"0"` or a fallback in core [validation §8.5; legacy §14.3].
- **I-24.** `defence_omitted` is emitted only on exact equality with `PI_DETECTOR_PLACEHOLDER`, and integrity is
  unchanged (compat) [provenance §13.9].
- **I-25.** Compat labels λ and ρ are functions of the tool name through the three sets, with an unknown default
  of ⊤/neutral (compat only; core is fail-closed, F-21) [provenance §13.9].
- **I-26.** The turn-aware visibility rule is kept exactly wherever it is evaluated (compat builder; the taint
  policy of the SEM profile `agentdojo.suites`, emitted through `aprov.a_exposure@1` and `aprov.a_taint@1`; and
  `analysis.argflow` when it is ported, AD-10): a tool output becomes visible only at the next assistant turn of
  the same pass, and pools reset per pass [provenance §15 row 4; corpus §8.14].

**Validation**

- **I-27.** Fail-closed write gate: no PROV document, AER or SEM file is persisted unless its validator passes
  [validation §8.1; D8].
- **I-28.** Totality: malformed input yields FAIL with errors, never an exception (after F-36)
  [validation §8.2].
- **I-29.** Cardinality checks are per element, never global totals [validation §8.3].
- **I-30.** Completeness is fail-closed: a key with no mapping rule is an error, extended to every section and
  prefix [validation §8.4].
- **I-31.** Time-consistency flags apply only where both times exist; a missing time is not a violation
  [validation §8.6].
- **I-32.** The namespace IRI of a profile is part of its identity. The compat profile keeps the exact
  `adprov` IRI check [validation §8.8].
- **I-33.** Compat I1–I11 hold on all 35,691 stored graphs and on every compat re-derivation [validation §8.9].
- **I-34.** Skipped checks never count as passed in release mode (D8).

**Import, replay and scoring**

- **I-35.** No fabricated value in any typed field; unknown is `unk` with a reason [legacy §14.1; D2].
- **I-36.** Logged outcomes are preserved verbatim at the source-preserving layer (`judgement.value`). Their
  origin (`judgement.origin ∈ checker|harness_default|harness_rule|recomputed`) and their interpretation (SEM
  `outcome`, scoring) are separate; the AER has no validity field on judgements (RESOLUTIONS R-02) [legacy §14.4].
- **I-37.** Importer semantics [legacy §14.7–14.8; §3.3 rules 7–15]:
  - a stem or execution-id collision is a named failure; the first writer wins; nothing is half-written;
  - an importer never writes into a sealed corpus;
  - dry-run writes and deletes nothing;
  - `limit=0` converts nothing, and `None` is the only "no limit";
  - filesystem strays are not logs;
  - any failure gives a non-zero exit.
- **I-38.** Imported identities come from the source's own fields and are recorded alongside the curator's
  label. Conflicts are flagged, never silently resolved [legacy §14.9].
- **I-39.** (Deferred with replay, AD-10.) Replay uses the benchmark version and checker era that produced the
  trace. Earlier passes are applied before the recorded one. Extras fail soft (`None`) and never lose the core
  outcome [legacy §14.10].
- **I-40.** Scoring:
  - `None == None` is not a reproduction;
  - reasons fire in the order abandoned > unwinnable > rerun_not_reproduced > account;
  - unscored traces keep their graphs;
  - under `agentdojo.scoring@1` the published v2.3 verdicts are reproduced exactly; this is checked only in the
    frozen baseline environment until outcome replay returns (AD-10 row 2) [legacy §14.11, §9].

**Corpus, analysis and export**

- **I-41.** No derivation step rewrites raw evidence or an imported record [corpus §8.1].
- **I-42.** Enriched or experimental derivations never land in a released or sealed tree [corpus §8.4].
- **I-43.** Manifest versions are the versions the records carry, `null` when unrecorded, never build
  constants [corpus §8.6].
- **I-44.** Unknown is never coerced to false: tri-states stay tri-state, and `score` refuses NaN, non-boolean
  dtypes and misaligned indexes [corpus §8.8; `baselines.py:155-169`].
- **I-45.** Marker status is four-valued, and `gap` (payload only on ⊤) is distinct from `absent`
  [corpus §8.9].
- **I-46.** Benign `security` is never an attack success (and neither, after F-62, are untargeted DoS outcomes)
  [corpus §8.10].
- **I-47.** For AgentDojo-PROV v2.3 records (COR-05), the legacy manifest split is `md5("suite/user_task") % 10`
  → buckets 0–7/8/9 (frozen baseline only; not a v0.1 facet, HL H.1.7) [corpus §8.11].
- **I-48.** Checksum files keep the `sha256sum` format (`<64 hex>␠␠<posix relpath>`), and dotfiles are skipped
  [corpus §8.12].
- **I-49.** (Deferred with the ML export, AD-10.) ML export leakage rules [corpus §8.13, §3.5.1]:
  - whitelist-only attributes; relations keep endpoints only;
  - the `FORBIDDEN` set with its reasons;
  - ids rebuilt from execution order;
  - deterministic sha256 key shuffle;
  - unknown tools become `unknown_tool`;
  - labels appear only in `labels.jsonl`;
  - the loader refuses anything else;
  - incomplete records are held back by default;
  - tied scores form one threshold; 95% recall uses `ceil`;
  - atomic export swap.
- **I-50.** (Deferred with the cache, AD-10; the v0.1 `agentprov stats` keeps no cache.) Stats caches are
  whole-corpus only, versioned, narrowed per model, and refused on missing columns [corpus §8.15].
- **I-51.** The render location rule (`corpus-prov` → `corpus-rendered`, any other root → `<root>-rendered`,
  flat → `rendered`) is single-sourced and independent of whether renders exist. It binds the legacy layout
  reader `adapters/adprov/layout.py` only [corpus §8.5; legacy §5].

---

## B.9 Defects the port MUST fix

Each fix MUST have a regression test named `test_fix_F<nn>_<slug>` at the stated destination. Fixes whose
destination is deferred (AD-10) get their test when the component is ported.

No defect is fixed inside the compat port. `prov/compat/adprov_v2_3/` holds the five baseline files verbatim and
AST-equal, and only its import statements change (RESOLUTIONS R-31). A defect of baseline behaviour is fixed in the
new code paths; where it also affects the frozen files, it is recorded as an erratum in
`docs/compat/adprov-v2.3.md`, and every compat-side test re-runs the E1 gate.

Fixes that deliberately change behaviour relative to the baseline (F-02, F-05, F-13) are registered as XD entries
under J gate C6(b), each citing its F id (AD-07; RESOLUTIONS R-32).

| # | Defect (source) | Location | Required fix | Destination |
|---|---|---|---|---|
| F-01 | `placeholder_args` specified as pre-injection arguments [capture §8 D1] | `docs/capture_spec.md` §2–§4; `docs/transcript.schema.json:168-171`; `transcript.py:57-69` | Pass through verbatim in `ext.agentdojo`; no core field; correct the docs (R-01) | `adapters/agentdojo/mapper.py`; DOC-02, DOC-06 |
| F-02 | Content of discarded and retried replies is lost [capture §4.1 defect 1, §8 D5] | `runtime.py:331-351` | Record every response, with its reason, as an `llm.response` event (`status ∈ kept\|discarded\|error\|cached`); in AER a retry is a `model_call` with `retry_of` (C). A deliberate deviation from the baseline: registered as an XD entry under J gate C6(b) (AD-07) | `agentprov_backend.transport`, `agentprov_backend.gateway` |
| F-03 | `finish_reasons` can misalign because of a broad `except` [capture §4.1 defect 2] | `runtime.py:373-387` | One record per call; fields that fail to parse are declared in `unk`, never skipped | `agentprov_backend.transport`, `agentprov_backend.gateway`; `adapters/agentdojo/capture_mapper.py` |
| F-04 | Served model, provider and usage reduced to sets or aggregates [capture §4.1 defect 3] | `generate.py:165-224` | One `model_call` per call, with `params{configured, transmitted}`, usage, finish reason and served model | `adapters/agentdojo/capture_mapper.py` |
| F-05 | Narrow gate; failing cells discarded and re-attempted without evidence [capture §8 D4–D5] | `observer.py:290-299`; `generate.py:600-607` | Generalised accounting (role-partitioned; dispatch ↔ result 1:1; pending calls; `pass.end` for every `pass.start`), giving `consistent\|inconsistent\|unverifiable` with reasons, computed once on the AER side (RESOLUTIONS R-13). Inconsistent or errored runs are sealed and kept with their `capture.attempt` index (D5). A deliberate deviation from the baseline: registered as an XD entry under J gate C6(b) (AD-07) | `aer/accounting.py`; `agentprov_capture` (hash-chain seal); `agentprov_backend.runner` (reads the seal verdict) |
| F-06 | Ungated fallback when no pass was recorded [capture §8 D11] | `observer.py:301-305` | Accounting always runs; a session with no recorded pass is sealed with the issue `no_execution_observed` and its accounting verdict | `adapters/agentdojo/capture_mapper.py`, `aer/accounting.py` |
| F-07 | Aborted passes invisible [capture §4.2.1] | `observer.py:88-169` | `PassRecorder` catches `AbortAgentError`, records `e.messages` and `e.task_environment` for the aborted pass, and re-raises | `agentprov_backend.pass_recorder` |
| F-08 | No timing when `tool_call.id is None`; wall clock only [capture §8 D13] | `observer.py:215-221` | Harness occurrence id per call (`occ`); wall clock (`ts`) plus monotonic time (`mono_ns`) in the capture envelope, mapped to `t.mono_start_ns`/`t.mono_end_ns` in AER | `agentprov_backend.executor_mirror`, `agentprov_capture` |
| F-09 | Refusal mismatch recorded silently [capture §8 D12] | `transcript.py:117-122` | On mismatch: `unk` with reason `ambiguous` plus a seal issue | `adapters/agentdojo/` message mapping (CAP-13) |
| F-10 | Position-aligned reasoning and refusal presented as observed [capture §8 D6] | `transcript.py:115-130` | `evf` `"I"` with rule `adprov.reasoning_log_alignment@1` [landscape/trace_formats.md §6.6] | `adapters/adprov/` mapper; `adapters/agentdojo/capture_mapper.py` |
| F-11 | The source of truth is not validated at write [capture §4.3] | `transcript.py:282-283` (`save_transcript`) | The AER validator gates every write (D8 tier 2) | `aer/validate.py`, `validate/tiers.py` (write gate) |
| F-12 | `truncated` ignores value cuts; digest notation inconsistent [capture §4.4] | `envstate.py:24-25, 39-46, 81-86` | `truncated` is true if any entry or value was cut; notation per R-12 | `agentprov_capture.envstate` |
| F-13 | `MODEL_NAMES` mutation decides the attack text [capture §8 D10] | `generate.py:299-302` | Declared instrumentation `attack.model_display_name` (kind `attack_parameter`, D.10.7), recorded in the AER header; stock behaviour otherwise. The v2.3 release plan MAY set the v2.3 strings to stay comparable, declared as a deviation and registered as an XD entry under J gate C6(b) (AD-07) | `agentprov_backend.attacks` |
| F-14 | Mixed-config guard checks one field in one file [capture §8 D16] | `generate.py:328-357` | Guard on `config_digest` over the full `AgentConfig`, `BenchmarkIdentity` and cell parameters | `agentprov_backend.runner` |
| F-15 | Error rows carry placeholder `utility=False, security=False` [capture §4.5 defect 4] | `generate.py:603-607` | Outcome `null`, session end status `errored`, full exception in an `error` event | `agentprov_backend.runner` |
| F-16 | `started_at` and `wall_clock_s` include environment loading and scoring [capture §8 D13] | `generate.py:132-162` | Separate `scope` records for run, passes and scoring, each with its own interval | `adapters/agentdojo/capture_mapper.py` |
| F-17 | For a failed tool call the model saw `error` while the record holds `content == ""` (6,920 released turns) [capture §8 D7; landscape/prov_semantics.md §5.6 item 7] | `transcript.py:91-102`; `build_prov.py:447-457` | AER records the model-visible text (`tool_result` part, with `error?`) separately from the dispatch outcome (`tool_execution.status ∈ ok\|error\|invalid`, `exception`, `returned`); a model-visible substitution is a sent transform `error_substitution` on the model input (RESOLUTIONS R-06) | `adapters/agentdojo/mapper.py`, `capture_mapper.py`; `agentprov_backend.runtime` |
| F-18 | Endpoint, timeout and SDK version not recorded [capture §4.1] | `runtime.py:121-212, 396-536` | Recorded in the `capture/0.1` `session.start` event (`AgentConfig` without secrets) and copied into the AER header | `agentprov_backend` (`AgentConfig`), `agentprov_capture` |
| F-19 | One activity stands for both the LLM decision and the tool execution [provenance §14 D1] | `build_prov.py:419-479` | Decomposed engine (D7); compat unchanged | `prov/engine.py` |
| F-20 | Context-taint usage indistinguishable from other `used` [provenance §14 D2] | `build_prov.py:471-474`; `validate.py:188-231` | Assessment bundle only (D7) | `prov/engine.py`, `validate/profiles.py` |
| F-21 | Fail-open labels (61 turns) [provenance §14 D5] | `labeling.py:128-145` | Three-valued, fail-closed `unknown` (D6) | `sem/engine.py`, `sem/types.py` |
| F-22 | Instance IRIs in the vocabulary namespace, repeated across graphs [provenance §14 D7; validation V13; corpus M3] | `prov_emit.py:17, 61-63`; `build_prov.py:116-141`; `ml_export.py:194-240` | `https://w3id.org/agentprov/exec/<ex>#<L(id)>` with `#` → `-` (D7; AD-04); the per-graph instance namespace in exports is deferred with the export (AD-10) | `prov/iri.py` |
| F-23 | Graphs are not self-describing [provenance §14 D8] | `build_prov.py:328-495` | Top-level conversion provenance and bundle identity (D7) | `prov/engine.py` |
| F-24 | Time fabrication: the run start is copied to untimed calls, and `end := start` [provenance §14 D9] | `build_prov.py:389-395, 436-437` | Removed from the engine and kept in compat only | `prov/engine.py` |
| F-25 | The timestamp predicate rejects `Z` and millisecond forms [provenance §14 D10] | `build_prov.py:79-114` | AER normalises to RFC 3339 and keeps `t.raw`; the predicate applies only at the `prov`-library boundary | mappers in `adapters/<family>/`, `prov/serialise/time.py` |
| F-26 | `_IRI_ILLEGAL` misses `#`, `%`, `[` and `]`, and invalid IRIs pass the checks [provenance §14 D11] | `build_prov.py:118` | Restricted to the new engine's IRI minting: positional local ids in C's grammar, with fragments minted by `prov/iri.py` (injective, AD-04), and the validator rejects invalid IRIs. The compat port reproduces the baseline behaviour verbatim (D7; RESOLUTIONS R-31); no stored graph has such an id | `prov/iri.py`, `validate/prov_structure.py` |
| F-27 | A duplicate node id silently overwrites [provenance §14 D15] | `prov_emit.py:162` | The core statement builder raises `DuplicateIdError` | `prov/engine.py`, `prov/serialise/provjson.py` |
| F-28 | Batches inferred from adjacency [provenance §14 D4] | `build_prov.py:371-420` | Request membership recorded in AER with backward references only: the assistant message is `generated_by` its `model_call`, its `tool_call` parts are the requests, and `tool_execution.call` points at a part (PRV-02) | `adapters/agentdojo/mapper.py`, `capture_mapper.py` |
| F-29 | Failed sinks still receive taint; attempted and effected sinks are not distinguished [provenance §14 D14] | `build_prov.py:471-474` | SEM sink annotation carries `tool_execution.status` | `adapters/agentdojo/semantics/profile.py` |
| F-30 | Unexecuted calls, later user turns and auxiliary LLM calls are absent from the graph [provenance §14 D16] | `build_prov.py:411-420` | AER records them (request parts with no `tool_execution`, flagged `unexecuted_tool_call`; `message`; `model_call` with an auxiliary actor), and the core engine emits them | mappers, `prov/engine.py` |
| F-31 | `adprov` vocabulary hygiene [provenance §14 D17] | `docs/ns/adprov.ttl` | `apv-0.1.ttl` with `owl:versionInfo "0.1.0"`, `owl:versionIRI`, classes and declared shapes; ML-only terms in a separate export vocabulary (deferred with the export) | `vocab/apv-0.1.ttl` |
| F-32 | Totality bug: `TypeError` on scalar relation sections [validation V1] | `validate.py:439-444`; `conformance.py:224` | Type-check sections, return FAIL, keep errors (new validators; the compat port stays verbatim) | `validate/prov_structure.py` |
| F-33 | Unknown sections and prefixes go unexamined, and a typo section passes the write gate [validation V2] | `validate.py:18-26`; `conformance.py:344-447` | Known-section whitelist (flag or reject), all prefixes examined, duplicate keys rejected at load | `validate/prov_structure.py`, `validate/roundtrip.py`, `ingest/loaders.py` |
| F-34 | Completeness is lexical and one-way [validation V3] | `conformance.py:375-379` | Typed literals plus the reverse direction | `validate/roundtrip.py` |
| F-35 | Constraint numbers attached to profile rules; 42 missing [validation V5–V7] | `conformance.py:466-562` | Faithful constraints (24 per (entity, activity), 39, 42, 53 with the Rec. set, 54, 55 with typing inference); time checks as MAY-flags; closed-world rules in compat | `validate/constraints.py` |
| F-36 | Coupling through message text; validator imports the builder [validation V10] | `conformance.py:235-241`; `validate.py:263` | Registry with typed results; a shared time module | `validate/tiers.py`, `prov/serialise/time.py` |
| F-37 | "Skipped" counts as ok [validation V11] | `conformance.py:99-101` | Strict mode: skipped = fail in release (D8) | `validate/tiers.py` |
| F-38 | No corpus-level validation [validation V13] | none | IRI scoping, manifest hash linkage, record ↔ graph linkage (D8 tiers 4–5) | `validate/linkage.py`, `corpus/integrity.py` |
| F-39 | RDF rebuilt 4× per document [validation V15] | `conformance.py:257-447` | One cached `(ProvDocument, rdflib.Graph)` per document | `validate/tiers.py` |
| F-40 | SHACL results parsed from text [validation V16] | `conformance.py:322-324` | Query the `sh:ValidationReport` graph | `validate/shapes/` (extra `shacl`) |
| F-41 | Unpinned RDF libraries; versions not in reports [validation V19] | `pyproject.toml` | `uv.lock`; library versions in every validation report | PRJ-03, `validate/tiers.py` |
| F-42 | `skipped` SHACL counted valid in tests [validation V11] | `tests/test_convert_runs.py:380-381` | Tests run in strict mode | TST-10 |
| F-43 | Overclaiming docstrings ("real W3C PROV-O conformance guarantee", "nothing goes unexamined") [validation V4, V2] | `conformance.py:11-12, 394-395`; `stats.py` docstring | Claims restated as what each check establishes (new code; the compat port keeps its docstrings verbatim, and `docs/compat/adprov-v2.3.md` lists them as errata) | `validate/*`, `stats/` |
| F-44 | Duplicate JSON keys silently collapsed [validation V14] | every `json.loads` | Tier-1 strict loader that rejects duplicates (`strict_json_loads`) | `ingest/loaders.py` |
| F-45 | No source anchor on converted transcripts [legacy §3.6 D1] | `convert_runs.py:138-208` | Raw store with origin `git {repo, commit, path, blob_sha1}` and sha256 (D3) | `raw/origins.py`, `adapters/agentdojo/dialect.py` |
| F-46 | Identity rule specific to one snapshot (pipeline field over folder; 11,765 `local*` upstream logs) [legacy §3.6 D2] | `convert_runs.py:310-317` | Keep the field and folder verbatim; derive the identity with a rule id (e.g. `agentdojo.pipeline_dir_is_model_identity`, class I); flag disagreement (`identity_conflict`) | `adapters/agentdojo/mapper.py` + profile tables |
| F-47 | Model and defence conflated [legacy §3.6 D3] | `convert_runs.py:138-172` | The requested model (`ev: "I"`) and the defence id (`ev: "I"`, rule `agentdojo.defence_suffix`, class I unless verified over the producing code range) through catalogue rules | same |
| F-48 | `"0"` sentinel in a date-time field [legacy §3.6 D4] | `convert_runs.py:78, 202-205` | `unk` `not_recorded` on the typed time fields; the verbatim stub stays in `t.raw` (C.7.3; RESOLUTIONS R-30). The TraceLogger mapper never emits it | `adapters/adprov/` mapper |
| F-49 | Runner defaults indistinguishable from checker outcomes [legacy §3.6 D5] | `convert_runs.py:157-158` | `judgement.origin ∈ checker\|harness_default\|harness_rule\|recomputed` (C); the finer cases are rule ids (`agentdojo.benign_security_constant`, `agentdojo.dos_security_rule`, `agentdojo.run_error_imposed_outcome`); no `valid` field (RESOLUTIONS R-02, R-13) | `adapters/agentdojo/mapper.py` |
| F-50 | 432 injection-task-as-user-task logs labelled `benign` [legacy §3.6 D6] | `convert_runs.py:145, 175-183` | Task kind `injection_task_as_user_task` | `adapters/agentdojo/mapper.py` |
| F-51 | `duration` rounded, scope unstated [legacy §3.6 D7] | `convert_runs.py:161` | Keep the raw float (with its lexical form in `ext.lex`); declare the scope (all passes plus checkers) | same |
| F-52 | Release guard is name-based [legacy §3.6 D9] | `convert_runs.py:242-260` | A sealed `corpus.json` checked by every writer | `corpus/layout.py` |
| F-53 | Exclusion register hygiene [legacy §3.6 D10] | `convert_runs.py:211-229` | Index and register rows keyed by `source_key` (`"sha256:<hex>#" + JCS(loc)`); stale entries reported | `corpus/index.py`, `corpus/register.py` |
| F-54 | `None == None` counted as reproduced [legacy §7.5 R1] | `replay.py:507-519` | Removed; single rule in `scoring` | LEG-10 |
| F-55 | `benchmark_of` ignores the recorded benchmark version [legacy §7.5 R2] | `replay.py:104-105` | Version from the AER identity and evidence | deferred with replay (LEG-07, AD-10) |
| F-56 | Checker exception → `False` ("unwinnable") [legacy §7.5 R3] | `replay.py:281-284, 317-321` | `None` plus an error note | deferred with replay |
| F-57 | Replayed `security` of DoS rows is the placeholder task's check [legacy §7.5 R4] | `replay.py:215-217` | Untargeted rows declare `security` as not applicable | deferred with replay |
| F-58 | Logging-era checks not applied to injection tasks run as user tasks [legacy §7.5 R5] | `replay.py:215` | Era-aware utility | deferred with replay |
| F-59 | `outcome_replay.json` written non-atomically [legacy §7.5] | `replay.py:479` | Atomic write through `io.atomic` | deferred with replay (LEG-09) |
| F-60 | `unwinnable` and `rerun_not_reproduced` apply to DoS [legacy §9 S1] | `scoring.py:59-60, 79-80` | Fixed in `agentdojo.scoring@2`; `@1` stays verbatim | `adapters/agentdojo/semantics/scoring.py` |
| F-61 | Converted datasheet states false collection provenance [corpus P1] | `package.py:335-342, 390-396, 413-438` | Datasheet numbers computed and prose supplied by the source card | `corpus/datasheet.py` |
| F-62 | DoS traces counted as attack successes (178) [corpus P2] | `package.py:180` | Exclude untargeted attacks via the scoring rule set | `adapters/agentdojo/semantics/manifest_ext.py` |
| F-63 | Manifests and datasheets unhashed; `generated_utc` breaks reproducibility [corpus P3] | `package.py:169, 471-497` | Hash every shipped file and add a root digest. Wall-clock timestamps go outside the digested content, or are recorded as release metadata | `corpus/integrity.py`, `corpus/manifest.py` |
| F-64 | Optional replay silently changes counts [corpus P4] | `package.py:229-231` | Override recorded as applied or not (R-11) | COR-06 |
| F-65 | First non-null version and `model_id` taken without a uniqueness check [corpus P5] | `package.py:93-94, 159-164` | Distinct values listed; a mixture is flagged | `corpus/manifest.py` |
| F-66 | Manifest row written for a missing graph [corpus P6] | `package.py:132-158` | Referential check before sealing | `corpus/integrity.py`, `corpus/package.py` |
| F-67 | Offline recompute imports `agentdojo` [corpus R1] | `recompute.py:41` | Import-boundary test (B.1.2) | `corpus/derive.py` |
| F-68 | Recompute: dict equality, no validation in dry-run, non-transactional, no input integrity, no derivation provenance [corpus R2–R6] | `recompute.py:133-181` | Compare JCS digests (core) or `indent=2` bytes (compat); validate in dry-run; staging plus atomic swap; verify raw digests first; record versions | `corpus/derive.py` |
| F-69 | Stats count the last pass only [corpus S1] | `stats.py:330-335` | Counts over all attempt scopes, with last-pass counts named as such | `stats/` (AD-10 as ruled) |
| F-70 | Caches not bound to the corpus [corpus S2] | `stats.py:466-503` | Key on the root digest | deferred with the cache (COR-12, AD-10) |
| F-71 | Biased conformance sample [corpus S3] | `stats.py:645-647` | Validate every execution (`validation/results.jsonl`); any sample is seeded and the seed recorded | `validate/tiers.py` |
| F-72 | `marker_status = "n/a"` for an unknown attack type [corpus S5] | `stats.py:438` | `unknown`, distinct from `n/a` | `adapters/agentdojo/semantics/coordinates.py` |
| F-73 | `EXPORT_VERSION` never bumped [corpus M1] | `ml_export.py:51` | Version by content digest plus a semantic version | deferred with the export (COR-16, AD-10) |
| F-74 | Export imports `agentdojo` for the tool vocabulary [corpus M2] | `ml_export.py:164-171` | Tool catalogue from profile data | deferred with the export (COR-17) |
| F-75 | Sanitised graphs never validated [corpus M4] | `ml_export.py:194-240` | Run the structural validator on every exported graph | deferred with the export |
| F-76 | Missing integrity drawn as trusted; missing role as neutral [corpus V1, B2] | `visualize.py:86, 93` | A distinct style for `unknown`; evidence class shown | `render/style.py` (AD-10 as ruled) |
| F-77 | PDF rendering without timeout, non-atomic [corpus V3] | `visualize.py:208-230` | Timeout and atomic write | `render/dot.py` (AD-10 as ruled) |
| F-78 | Inaccurate comment "chose these calls from the user query alone" [provenance §12] | `build_prov.py:468` | Recorded as an erratum; the compat port stays verbatim (RESOLUTIONS R-31) | `docs/compat/adprov-v2.3.md` (DOC-03) |

---

## B.10 Things that MUST NOT be ported

- **N-01.** The in-loop `ProvObserver` projection, `get_prov_document` and `save_prov_document`
  (`observer.py:234-461`) (CAP-08; D5).
- **N-02.** `prov_emit._now_iso` and the 16-hex `_content_hash` (PRV-14).
- **N-03.** Mutation of `agentdojo.models.MODEL_NAMES` or any other upstream module global (CAP-22, F-13).
- **N-04.** The `"0"` timing sentinel in typed time fields, and `meta.timing_stubbed` as a core field. The
  verbatim stub MAY be kept in `t.raw` with `unk` on the typed fields (C.7.3), and the v1 view renders it from
  there only to reproduce v1 records (LEG-03; RESOLUTIONS R-30).
- **N-05.** `emit_source_agents` and `emit_derived_edges` semantics in the new engine. In the compat port the
  flags remain verbatim, but MUST NOT be reachable from any CLI command or corpus packaging step (PRV-05, PRV-06;
  RESOLUTIONS §1.3).
- **N-06.** Time fabrication (run-start copy, `end := start`) and fail-open labelling outside compat (F-24,
  F-21).
- **N-07.** The `adprov:` namespace, or the `nickjones39.github.io` host, for any new data or instance IRI.
  `adprov.ttl` MUST NOT be edited, and the hosted site MUST NOT be renamed or unpublished (DOC-07; D7).
- **N-08.** Silent discard-and-rerun of failing cells; placeholder outcomes on error rows (F-05, F-15).
- **N-09.** Build constants as manifest or datasheet facts (`CORPUS_VERSION`, `dataset`, licence literals,
  `AGENTDOJO_VERSION`, `BENCHMARK_VERSION`) and hard-coded release prose (COR-04).
- **N-10.** Duplicate rule implementations: `replay.rerun_outcome_reproduced`, `outcome_disputed`,
  `_untargeted`, the duplicated `MARKER_ON_UNTRUSTED`, and the manuscript's pandas re-implementation of
  scoring (LEG-10, COR-15).
- **N-11.** `visualize.validate_prov_json` under that name; `render_prov_json`; every reference to `live_run`
  (COR-23, COR-24).
- **N-12.** The uninstrumented smoke runners in `runtime.py:543-659` (CAP-05).
- **N-13.** Any import of `agentdojo` outside `backends/` (`agentprov_backend` and the backend projects
  `backends/agentdojo/`, `backends/autodojo/`). This includes the `recompute → generate → observer` chain and
  `ml_export._tool_names` (B.1.2; AD-01).
- **N-14.** `transcript/v1` or `docs/transcript.schema.json` as a canonical format, and the four-suite enum
  anywhere in core (CAP-17, DOC-06).
- **N-15.** The stale worktree `.claude/worktrees/intelligent-haibt-1cc805`, the vendored `*-main/`
  directories, `code-review*.md`, and build or OS artefacts (EXT-02…EXT-04, EXT-08).
- **N-16.** `runs/` and `corpus/` contents into Git (D9), and the converted v1 transcripts as the
  authoritative source for the June-2024 logs (R-05).
- **N-17.** The invariants stated in `CLAUDE.md` where they contradict code. In particular "exactly
  `max(n-1,0)` wasInformedBy" (EXT-01).
- **N-18.** Over-claiming wording: "lossless" without a scope; "real W3C PROV-O conformance guarantee";
  "nothing in the JSON goes unexamined"; "historical detector graph EXACTLY"; `wasInformedBy` "only where
  that happened"; the "FLINT" naming [capture §4.8; provenance §8, §12; validation V4, V17; corpus §3.2].
- **N-19.** The gitignored local reports and research notes as documentation (DOC-11, DOC-12).
- **N-20.** `matplotlib`, `numpy` and `tenacity` as core dependencies; `python-dotenv` outside the `live` extra;
  automatic `.env` loading. `.env` is read only by the live CLI entry, from `--env-file` or the repository root
  (A4; PRJ-03).
- **N-21.** `adprov:placeholder_mismatch`, `adprov:len_bucket` and `adprov:has_error` in the provenance
  vocabulary. The last two belong to the export vocabulary only (F-31).
- **N-22.** The md5 `split` for new corpora (COR-05), and hard-coded tree names (`generated`, `converted`,
  `corpus-prov`) or path arithmetic (`tpath.parents[2]`, `.transcript.json` → `.json`) outside
  `adapters/adprov/layout.py` [corpus §2.2].
- **N-23.** Rendering, derivation or validation inside the live-capture process (CAP-10, CAP-19).
- **N-24.** Running a ported analysis on `agentprov-prov/0.1` core graphs without the assessment bundle
  (RESOLUTIONS R-34). Rendering is not an analysis in this sense: `agentprov render` draws the core bundle by
  default (AD-10 as ruled; COR-22).

---

## B.11 Acceptance checks for this section

The port of the baseline is complete for v0.1 when all of the following hold. Gate names are J's (AD-07); test
paths are K's.

1. **Coverage.** `docs/port/baseline-map.json` has an entry for every row of B.2–B.5, with status `deferred` for the
   AD-10 deferrals, and the traceability test of B.1.3 passes.
2. **Import boundaries.** `tests/boundary/test_import_boundary.py` passes (B.1.2). `agentprov_capture` imports only
   the stdlib and `rfc8785`; benchmark imports exist only under `backends/`.
3. **Compat byte identity (D7, I-19).**
   - `tests/golden/test_compat_bytes.py` (K.7.1) re-derives the 15 golden graphs, plus the MIG-10 pairs
     (RESOLUTIONS R-59), from the v1 view regenerated from the AER alone (`ext.lex`, B.7.1) and compares bytes.
     This is gate B, run in CI after gates A1 (JCS) and A2 (bytes).
   - `agentprov migrate` runs gate B locally over all 35,691 pairs (`full_corpus`) and MUST report 35,691/35,691,
     matching E1.
4. **v1 round trip (D8 tier 6).** For every golden transcript, v1 → AER → v1 passes gate A1 (JCS value identity)
   and gate A2 (`serialise(render(aer))` equals the source bytes), from the AER alone. No round-trip test uses
   Python `==` (AD-02). The full 35,691 run is local (phase 13). For the converted tree, R1/R2 run on the golden
   converted pairs in CI, and the full 18,027 run is the claim gate of B.6 R-05.
5. **Executor differential (D5).** The executor-mirror test in `backends/agentdojo/tests/` (K.9.4) runs the stock
   0.1.35 `ToolsExecutor` and the mirror on identical inputs (valid, empty-name, unknown-tool, string-encoded-list
   and raising calls) and asserts equal message lists. It also asserts `agentdojo.__version__ == "0.1.35"`.
6. **Behavioural ports.** The ported tests of B.4 pass at their destinations. Removed tests (TST-06 observer
   section, TST-07 parity tests, TST-19) are listed as `not_ported`, and deferred ones (TST-11, TST-15, TST-16,
   the confound part of TST-18, the frame part of TST-14) as `deferred`.
7. **Defects.** Every F-nn with a v0.1 destination has its `test_fix_F<nn>_*` regression test, and every
   compat-side test leaves check 3 green.
8. **Recompute baseline.** `agentprov recompute --dry-run` over the re-imported v2.3 release and the June-2024
   re-import reports 0 changed digests. This is the first AgentDojo regression gate [corpus §3.3; D9].
9. **Retained reports (AD-10 as ruled).** `agentprov stats` produces the generic counts and the per-source
   information-loss table of COR-08 over the re-imported corpora, counting all attempt scopes (F-69).
   `agentprov render` renders the core bundle of a re-imported execution, draws unknown integrity distinctly
   (F-76), and writes PDFs with a timeout and atomically (F-77). Both are covered by K's tests.

---

## B.12 Open questions and their dispositions

RESOLUTIONS §1.3 dispositions the open questions of r1:

| Open question (r1) | Disposition |
|---|---|
| Data licence of the upstream AgentDojo run logs; may golden converted fixtures and the June-2024 raw logs be redistributed? | U-03, forwarded to the user. Record the basis "MIT by repository; data licence not separately stated". Until the user decides, fixtures with third-party model outputs stay in the private repository and never enter the sdist (Addendum B, B-2; U-06) |
| Compat view method: `src` locators into raw, or `args_raw` in AER? | Neither as proposed: AD-02 (`ext.lex`; the view reads nothing from raw). `args_raw` keeps its own meaning (B.7.1) |
| `model_display_name` for comparability with v2.3 | Closed: declared instrumentation `attack.model_display_name` (kind `attack_parameter`, D.10.7); stock behaviour otherwise (CAP-22, F-13) |
| Keep `emit_source_agents` / `emit_derived_edges`? | Closed: kept verbatim in the oracle, with no CLI exposure (RESOLUTIONS R-31; N-05) |
| Defended pipelines in live v0.1 | Closed: the OB-8 typed refusal stays for v0.1; auxiliary roles are accounted in AER only for imports (I-08) |
| `record_complete` headline: 47 or 52? | Closed: headline 47 (structural); 52 stays a separate, evidence-qualified field (B.6 R-11) |
| `code-review.md` and `code-review-repo.md` unread | Done on 2026-10-07, read-only, as the fixer action that §1.3 asks for before B.9 is frozen. Both are local notes dated 2026-09-29, written before the v2.3 release; their fixes are part of `579a908`. Their findings map to existing rows: the render-directory rule and render base (I-51, COR-02, CAP-24), recorded versions instead of build constants (I-43, COR-02), the release-root guard, `--limit 0` and complete-pair resume (I-37, LEG-01, F-52), the YAML line-fold and `\uXXXX` marker fixes (I-21, PRV-09), the collision re-check (PRV-08, I-17), timing keyed by id and occurrence (I-07), `score` refusing unknown ground truth (I-44), the fabricated-outcome exit path (I-14, F-15), the relabelling of content-bearing mutation tools as ⊥ (the v2.3 tables of PRV-17), the historical `prov-` model folders (CAP-24), and checksums that do not cover renders (F-63). Two residuals need no new F-row: the untested renderer is covered by the render tests of the AD-10 port (B.11 check 9), and the latent `bool()` coercion of logged outcomes cannot recur because outcomes are copied verbatim (I-36). No new defect is added to B.9 |
