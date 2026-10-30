Revision: 2026-10-08 r2.1 — review resolutions and Addendum B applied (2026-10-07); r2-sweep residuals SW-K1…SW-K14 applied (2026-10-08).

# K. Testing strategy

Section of the AgentPROV v0.1 architecture and implementation specification.
Status: DRAFT-FOR-REVIEW, 2026-10-07 (r2). Binding brief: `investigation/DECISIONS.md` with the precedence
**Addendum B > Addendum A > D0–D12**, and `investigation/spec/review/RESOLUTIONS.md` (§3 canonical naming table,
mandatory except where Addendum B deviates). K owns `tests/` (RESOLUTIONS §0); paths and the CLI follow MN, the AER
contract follows C, the PROV mapping follows EF, and limits and security controls follow G.
The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in RFC 2119 / RFC 8174.

### Changes after review (2026-10-07)

Applied: RESOLUTIONS §4.10 edits 1–20, and the K content of R-01…R-45 and R-47…R-63 (R-46 and R-64 have no K
content), as ruled in Addendum B. Where Addendum B deviates from a RESOLUTIONS recommendation, the ruling is applied:

- **AD-10 (deviation).** A minimal, generic `agentprov stats` (`src/agentprov/stats/`) and `agentprov render` (the
  ported baseline renderer, `render` extra: pydot + graphviz) stay in v0.1. K tests both (K.5.11, K.5.12, K.15). The
  `render` marker therefore stays; the `analysis` marker and extra are gone.
- **AD-15 (deviation).** `aer/0.1` has **13 record kinds**, including the generic `activity` and `artefact` (B-1). EF
  maps them through G-ACT, G-USE, G-GEN and G-ASSOC, which take part in the Inference-6 closure. K tests the kinds
  (K.5.1), the rules (K.5.10, K.10.2) and the future-framework walkthrough (K.6.4).
- **AD-16 (deviation (c)).** Core declares `requires-python = ">=3.14"` and `.python-version` `3.14`. Archive and
  compressed-stream ingestion **refuses below 3.14.8 in release mode**, and warns and records in dev mode. CI pins the
  latest 3.14 patch. K tests the guard (K.12.12, SEC-26), which is therefore kept (R-60's deletion of SEC-26 assumed
  option (a), which was not adopted).
- **AD-15 also supersedes R-35's "keep the 11 kinds".** The future-framework test asserts named PROV statements for
  the planner step, memory write and read, screenshot, hand-off and human approval (K.6.4).
- **AD-08 (nuance).** The claims lint (K.16) allows "benchmark-agnostic" only as an architectural design goal.

r2 consistency sweep (2026-10-08). The residuals SW-K1…SW-K14 of `spec/review/SWEEP_r2.md` §7 are applied, under the
architect defaults AD-SW2 (release surface and exit codes), AD-SW4 (`foobench`, D.12 binds K.6.4), AD-SW9
(`corpus-0.1` `$defs`), AD-SW19 (baseline requirements file), AD-SW20 (three added test files) and AD-SW26 (validator
codes), and with the evidence EV-1 (the 26,645 / 23,449 pair), EV-2 (KATs 1–4) and EV-3 (Inspect log sizes).

The upstream clones moved out of the session working directory to
`~/Desktop/PhD/Labs/AgentPROV-upstream/` (B-2, U-08). No test depends on them. Tests read only
committed fixtures and pinned, digest-verified fetches; the one `--input` route, of the local `full_corpus` gate for
the six survey AgentHarm logs (K.7.4), accepts a clone outside the workspace only after verifying its commit and every
blob id against the pin.

---

## K.0 Scope, evidence base and conventions

### K.0.1 Scope

This section specifies every test layer of AgentPROV v0.1:

- unit tests;
- adapter tests;
- golden regression tests;
- integration tests;
- differential tests;
- property-based tests;
- fuzz tests;
- security tests;
- reproducibility tests;
- import-boundary tests;
- CLI and documentation tests;
- tests of the minimal `stats` and `render` commands (Addendum B, AD-10);
- tests of the three repository-root projects that live outside core: `capture/` (`agentprov-capture`),
  `backends/shared/` (`agentprov-backend`) and the backend projects `backends/agentdojo/` and `backends/autodojo/`
  (A1, AD-01).

It also gives the fixture licence policy, the test markers, the split between CI and local runs, the coverage targets and the GitHub Actions workflow outline.

The test suite is the executable form of the decisions:

- D8 tiers 1–7 (validation);
- D2 invariants (AER), as frozen by Addendum B (13 record kinds);
- D7 never-emit rules (EF NE-1…NE-20), the Inference-6 closure and the compatibility gate;
- D9 recompute rule;
- D10 import boundary, as amended by A1, AD-01 and AD-17;
- A1/AD-16 interpreter guard;
- the migration release gates of AD-07 (K.20).

### K.0.2 Code under test

The code under test is named by the module paths of MN M.1.2, which RESOLUTIONS §3.2 amends. There is no `core`
package. The core layers are `io/`, `ingest/`, `raw/`, `aer/`, `sem/`, `prov/`, `views/`, `validate/`, `corpus/`,
`release/`, `adapters/` (with the registry package `adapters/registry/`), `stats/`, `render/`, `cli/`, `api.py`,
`errors.py`, `worker.py` and `testing/`, all under `src/agentprov/`. The schemas are `aer-0.1`, `capture-0.1` and
`corpus-0.1` (AD-10 row 13). The extras are `live`, `shacl`, `render` and `dev` (RESOLUTIONS §3.1, Addendum B AD-10).
Outside core:

- `capture/` → `agentprov_capture` (event model, writer, hash-chain verifier, `redact`, envstate digests,
  `cap.rules.toml`);
- `backends/shared/` → `agentprov_backend` (gateway, pass recorder, executor mirror, recording transport, runner,
  attacks, worker, `testing.ScriptedTransport`);
- `backends/agentdojo/` and `backends/autodojo/` (backend projects that never install `agentprov`).

The migration tables of the audits [audit/capture.md §10; audit/validation.md §9; audit/legacy_replay.md §13;
audit/provenance.md §15] give the baseline origin of each tested behaviour; their destination paths are superseded by
MN M.1.2 (B.1.1 header note).

Test modules MUST follow that layout one-to-one. The test module *names* and *contents* given here are normative.

### K.0.3 Evidence base

The evidence base is:

- `baseline/BASELINE.md`;
- `audit/*.md`;
- `landscape/trace_formats.md` (§6, especially §6.16);
- `landscape/prov_semantics.md` (§3.18–3.19, §7–§11);
- `sources/*.md` and `verify/*.md`;
- the baseline code at `~/Desktop/PhD/Labs/AgentDojo-PROV-framework` @ `579a908`, cited as `file:line`;
- `landscape/secure_ingestion.md` and section G, whose G.10 catalogue (SEC-01…SEC-26) K implements in K.12;
- `spec/review/RESOLUTIONS.md` and DECISIONS Addendum B.

The first draft of this section was written before `landscape/secure_ingestion.md` existed. That statement is
stale: the study exists (RESOLUTIONS consolidator check 3), and the default limits are fixed in G.3.2
(`agentprov.ingest.limits.IngestLimits`). The tier-1 (ingest-safety) tests in K.5.6 and K.12 remain parametrised over
the limit object: they read every value from `IngestLimits()` and **hard-code no limit value** (R-63).

### K.0.4 Observations made while writing this section ([obs-K])

These are read-only probes run 2026-10-07:

- They used the baseline venv (`agentdojo_prov` 1.0.0, CPython 3.12.14) and a scratch venv holding `rfc8785` 0.1.4.
- `PYTHONDONTWRITEBYTECODE=1` was set.
- They ran against the frozen corpora in the baseline checkout, which was not modified.
- Section B independently reproduced obs-K1 and the graph-side count behind obs-K3 [spec/B_audit_evidence/README.txt, full_bytes_result.json].

| id | Observation |
|---|---|
| obs-K1 | All **35,691/35,691** stored graphs (17,664 released, 18,027 converted) are byte-identical to `json.dumps(build_prov(transcript), indent=2).encode()` with default flags. This is the serialisation the baseline writer uses (`agentdojo_prov/generate.py:468`). Wall time was 5.4 s with 10 processes on the M2 Max (BASELINE §1.2). The baseline's own recompute compared only parsed-JSON dicts [audit/corpus.md §3.3 R2], so this is the first byte-level confirmation. |
| obs-K2 | All 35,691 stored transcripts are byte-identical to `json.dumps(json.loads(bytes), indent=2)`. This matches the writer (`agentdojo_prov/transcript.py:283`). |
| obs-K3 | **Member order.** Multi-key tool-call `args` objects whose top-level member order is not lexicographic: 12,485 of 16,052 released (7,956 traces) and 12,856 of 16,873 converted (8,167 traces). **Integral floats** (e.g. `100.0`) inside tool `args`: 313 released (270 traces) and 1,681 converted (1,288 traces). Integral floats anywhere in transcripts: 15,369 (14,837 traces) and 3,381 (1,301 traces). **Graph side** [spec/B_audit_evidence]: `adprov:args` strings affected by order or integral floats in 8,037 released and 8,341 converted graphs. |
| obs-K4 | `rfc8785` 0.1.4 behaviour. `{"b":1,"a":100.0,"c":[1.5,2.0]}` is serialised as `{"a":100,"b":1,"c":[1.5,2]}`, so members are sorted and `100.0` becomes `100`. `2**60` raises `IntegerDomainError`. `nan` raises `FloatDomainError`. A lone surrogate raises `CanonicalizationError`. |
| obs-K5 | None of the 35,691 stored transcripts contains an integer beyond ±2^53, a non-finite number, a lone surrogate or a duplicate object key. Tests for these hazards therefore need synthetic fixtures. |
| obs-K6 | The two readings of the D2 execution-id rule are `base32(sha256(…))[:26]` and `base32(sha256(…)[:16])` unpadded, the latter per [landscape/trace_formats.md §6.4]. They differ in the 26th character for **7,438 of 10,000** random inputs. Letter case is unspecified in D2; trace_formats says lower case, while Python's `base64.b32encode` emits upper case. *Resolved by AD-04: C's `[0:26]` of the full digest, lower case (K.5.2).* |
| obs-K7 | The baseline `pyproject.toml` declares `pyyaml>=6.0` with the comment "build_prov: parsed fallback of the injection-marker match". `agentdojo_prov/build_prov.py:251` does `import yaml`. D10's core dependencies (`prov`, `rdflib`, `rfc8785`) do not include PyYAML. *Resolved by AD-17: `pyyaml` is a core dependency imported only by `ingest/yamlsafe.py` (K.14).* |
| obs-K8 | (r2, 2026-10-07, stdlib `hashlib`/`base64` only.) The AD-04 known-answer vector reproduces: preimage `aer-ex/1\nagentdojo.tracelogger/agentdojo-upstream\n99e641af97e56971dd67308beec96ac08fdca7063141f3714389733ba845cc8a\n{"p":""}`, SHA-256 `fd33a7625df9e869ca8445f0b613855f77c7c31ca3c300e3caab17a25e781345`, id `ex_7uz2oys57hugtsueixylme4fl5`. Under the superseded mapping id `agentdojo.tracelogger` the same artefact gives `ex_xa3om2zkco3ai5e7lo6lwdc4z2` (SHA-256 `b836e66b…561f`), matching the consolidator's check 1. |

---

## K.1 Principles (normative)

1. **Invariants are executable.**
   - Every invariant stated in this specification MUST have at least one test tagged `@pytest.mark.invariant("<ID>")`. This includes the AER invariants [landscape/trace_formats.md §6.16], the D7 never-emit rules, the D8 tiers and the D9 recompute rule.
   - `tests/invariants.toml` is the registry: id, statement, spec reference.
   - `tests/docs/test_traceability.py` (K.16) fails on any registry entry without a test, and on any marker that names an unknown id.
2. **Offline and keyless by default.**
   - No test may reach the network or read a credential unless it carries the `network` marker.
   - An autouse guard (K.3.4) blocks sockets. It also removes `*_API_KEY`, `*_TOKEN`, `OPENAI_BASE_URL` and related variables from the environment.
   - Live-backend tests use `agentprov_backend.testing.ScriptedTransport` as the HTTP transport *below* the recording transport of the stock LLM element (K.8.1; AD-01(e), AD-09). Real model runs are never part of the test suite (D5); they need the user's keys and consent (U-10).
3. **Skipped is not passed (D8).**
   - In CI every job declares the gates it enables.
   - A skip inside an enabled gate is a failure under `AGENTPROV_STRICT_SKIPS=1` (K.3.4).
   - The baseline pattern `skipif(not _has("prov"))` (`tests/test_conformance_provo.py:51-55, 65`) silently hides a missing core dependency. It MUST NOT be used for core dependencies.
4. **Untrusted data stays data.**
   - Fixtures contain prompt-injection payloads addressed to AI agents [BASELINE §8(9); sources/rope.md §4.4; sources/autodojo.md §8]. They are stored byte-identically, never edited or sanitised, and never interpreted.
   - K.12.6 tests that no AgentPROV component turns artefact content into instructions, commands, paths or terminal control sequences.
   - The repository is itself an injection channel for coding agents (R-42). Fixtures are `binary` in `.gitattributes` and listed in `.ignore`/`.rgignore`; `.claude/settings.json` denies `Read(./tests/fixtures/**)`. Golden helpers and assertion messages never print fixture content unescaped (K.3.2, K.3.4). Synthetic injection sentences are assembled at run time from fragments, so no test source or synthetic fixture holds a complete instruction sentence (K.12.6, K.12.13).
5. **Assert codes, not prose.**
   - Validators and readers MUST return typed results with stable `code` strings. Tests MUST assert codes.
   - The baseline coupled its checks by error-message prefix [audit/validation.md §7 V10]. AgentPROV MUST NOT repeat that.
6. **Unknown is a first-class expected value.**
   - Adapter and engine tests assert the declared `unk` reasons and seal issues as positively as they assert values.
   - A test MUST fail if a field that the source cannot provide is filled. This covers sentinels, fallbacks and invented times [landscape/prov_semantics.md §9.3(5)].
7. **The baseline is a frozen oracle.**
   - The baseline is pinned at `579a908354b93361efe0905ffb7623256aa96a06` (tag `agentprov-baseline-2026-10-07`, which exists locally) and its corpora are frozen [BASELINE §0].
   - Tests read the baseline's outputs, either as committed golden copies or from a local corpus path (`AGENTPROV_BASELINE_CORPUS`, lock `migration/baseline.lock.json`). They never write to the baseline checkout.
   - The old package is only ever executed in a separate environment (K.9.2).
8. **Tests are deterministic.**
   - Hypothesis runs `derandomize=True` in PR CI. Random exploration happens only in the on-demand `thorough` profile (K.3.4), run locally or by manual dispatch (K.19.1), with an example database kept locally.
   - Every failing generated example MUST be promoted to an explicit `@example(...)` or a fixture before the fix is merged.
   - Test order MUST NOT matter. PR CI uses the default collection order. A reversed-order run (`AGENTPROV_REVERSE_ORDER=1`, K.3.4) MAY be run locally; a hosted reverse-order run is deferred (AD-10 row 18).
9. **Bytes or JCS, never `==`.** Round-trip and regression assertions compare bytes or JCS (RFC 8785) serialisations, never Python `==` on decoded values, because `==` ignores member order and treats `True == 1` and `1 == 1.0` as equal (R-04; baseline R2 [audit/corpus.md §3.3]). A test helper that compares decoded values MUST say so in its name and MUST NOT be used for a gate.
10. **Core and backend projects are tested apart (A1, AD-01).** Core `tests/` runs on Python 3.14 and imports no benchmark, no `agentprov_backend` and no `httpx`/`openai`. Every test that imports `agentdojo` lives in a backend project (`backends/<b>/tests/`) and runs on that project's Python 3.12 environment. Core tests consume live outputs only as committed `capture/0.1` fixtures or as artefacts produced by a backend job (K.8.5).

---

## K.2 Baseline test inventory and port map

The baseline result is **362 passed, 1 skipped** (693 warnings) in 18.71 s across 19 modules and 5,243 lines [BASELINE §2]. The skipped test is opt-in slow (`tests/test_scripts.py:56-59`, `ADPROV_SLOW_TESTS=1`).

The function counts below are `def test_` counts at `579a908` (343 functions; parametrisation brings this to 363 collected items). Each baseline module MUST be ported or retired as follows. The audit-listed gaps MUST be added as new tests in the destination module.

| Baseline module (functions) | Decision | Destination (this section) | Gaps to add (source) |
|---|---|---|---|
| `test_attempts.py` (38) | RETAIN/ADAPT: the scripted-client harness becomes the standard backend harness [audit/capture.md §4.9]. Accounting moves to the AER side (computed once, R-13) | `backends/agentdojo/tests/test_passes_and_retries.py`, `test_resume.py`; core `tests/unit/aer/test_accounting.py` | `AbortAgentError` passes; native (non-OpenAI-compatible) providers through the recording transport; refusal mismatch recorded; `get_transcript_doc` fallback replaced by a sealed-with-issues execution [audit/capture.md §4.9] |
| `test_capture.py` (30) | SPLIT: mapping tests go to the core capture mapper (run on frozen `capture/0.1` fixtures); live-side tests go to the backend project; time, marker and graph tests go to the compat port [audit/capture.md §4.9] | `tests/adapters/agentdojo/test_capture_mapping.py`; `backends/agentdojo/tests/test_live_capture.py`; `tests/prov/compat/adprov_v2_3/test_builder_*.py` | Differential of `TimingToolsExecutor` against stock `ToolsExecutor` (K.9.4) |
| `test_reasoning.py` (14) | ADAPT | `backends/shared/tests/test_gateway.py`; `backends/agentdojo/tests/test_reasoning_capture.py` | Configured vs transmitted parameters recorded separately [audit/capture.md §9.3] |
| `test_envstate.py` (7) | RETAIN → `agentprov_capture.envstate` | `capture/tests/test_envstate.py` | `sha256:` prefix on digests [audit/capture.md §8 D15] |
| `test_generate.py` (1) | RETAIN (write gate) | `tests/unit/validate/test_write_gate.py` | Gate on AER and SEM writes, not only PROV |
| `test_convert_runs.py` (42) | RETAIN/ADAPT [audit/legacy_replay.md §13] | `tests/adapters/agentdojo/test_tracelogger_v0_k11.py`, `tests/integration/test_offline_import_e2e.py` | Content-block (`v1.k14`) logs; `pipeline_name` ≠ folder; logs lacking `utility`/`security`/`duration`; `placeholder_args` present; injection-task-as-user-task typing; schema `format` asserted; source identity recorded [audit/legacy_replay.md §10] |
| `test_replay.py` (19) | DEFERRED (AD-10 row 2): outcome replay, historical checkers and the confound probe stay in the frozen baseline environment at `579a908` (J.5: `removed (deferred; baseline env)`). If replay is reinstated, it is a T1-restricted job in `backends/agentdojo` (R-34) | — (stays in the baseline) | Recorded for reinstatement in `docs/roadmap.md`: `benchmark_of` vs `meta.benchmark_version`; DoS rows; `None == None` is not a reproduction; checker exception → `None`, not `False` [audit/legacy_replay.md §10, §1(10)] |
| `test_scoring.py` (9) | REFACTOR: the outcome rules become catalogue rules (`agentdojo.benign_security_constant`, `agentdojo.dos_security_rule`, `agentdojo.run_error_imposed_outcome`; R-09). Tests that import `agentdojo` move to the backend project | `tests/adapters/agentdojo/test_outcomes.py` | DoS + `injection_check_winnable False` [audit/legacy_replay.md §10] |
| `test_prov_builder.py` (42) | RETAIN as compat-port regression; tests that import agentdojo move to the backend project [audit/provenance.md §15] | `tests/prov/compat/adprov_v2_3/test_builder.py`, `test_marker_yaml_styles.py`; `backends/agentdojo/tests/test_builder_agentdojo.py` | Unknown-tool labelling; `#`/`%`/`[`/`]` ids; `Z` and millisecond timestamps; split-batch layout; `_shared_starts` directly; `get_endorsers`, `check_suite_coverage` [audit/provenance.md §11]. In the compat port these pin the *legacy* behaviour. In agentprov-prov/0.1 they assert the corrected behaviour. |
| `test_communication.py` (42) | RETAIN as compat-port regression | `tests/prov/compat/adprov_v2_3/test_communication.py` | — |
| `test_prov_conformance.py` (4), `test_conformance_provo.py` (14) | RETAIN + EXTEND [audit/validation.md §9] | `tests/unit/validate/test_prov_structure.py`, `test_serialisation_fidelity.py`, `test_prov_constraints.py`, `test_time_flags.py` | Constraints 33/34/35/53/54/55 direct; a negative control showing `round_trip` can fail; null/number/boolean relation sections (V1); unknown sections and foreign prefixes (V2); enriched-relation shape; builder-independent PROV-JSON fixtures [audit/validation.md §3.10] |
| `test_recompute.py` (11) | RETAIN, generalised [audit/corpus.md §3.10] | `tests/reproducibility/test_recompute.py` | Type-only changes (`true`→`1`); validation failure mid-run; dry-run validates [audit/corpus.md §3.3 R2–R4] |
| `test_package.py` (11) | RETAIN, generalised | `tests/unit/corpus/test_manifest.py`, `test_datasheet.py` | Datasheet *content* per source; DoS counting; mixed versions; manifest reproducibility [audit/corpus.md §3.10, §9 P1–P3] |
| `test_stats.py` (17) | The baseline `stats.py` is AgentDojo-specific and pandas-based; it stays in the baseline (AD-10). The AgentDojo facts it checks that the AER mapper now owns (requested calls that never ran; a null final reply ⇒ re-run; `record_complete`) are adapter assertions in K.6.2. The new generic `agentprov stats` (Addendum B, AD-10) gets new tests | `tests/unit/stats/` (K.5.11) | Counts per source and status; statement counts by class, bundle and rule; unknown-reason proportions; information-loss table |
| `test_ml_export.py` (28), `test_baselines.py` (12) | DEFERRED (AD-10 row 1): `export/ml` and the flow/argument baselines stay in the frozen baseline environment (J.5) | — (stays in the baseline) | Recorded in `docs/roadmap.md`: `EXPORT_VERSION` bump; conformance of sanitised graphs; `flow_predicates`, `score` [audit/corpus.md §3.10] |
| `test_scripts.py` (2) | RETIRE the launcher test (`run_full_corpus.sh` is replaced by a declarative run plan [audit/capture.md §10]). The confound check is DEFERRED with replay (AD-10 row 2) | — | — |

The baseline has no test of `visualize.render_prov_graph`. The port behind `agentprov render` (Addendum B, AD-10) gets new tests (K.5.12).

In the baseline, tests that need `agentdojo` relied on `importorskip("agentdojo")` (`tests/test_replay.py:30`, `tests/test_prov_builder.py:357`). In AgentPROV every such test (at least 73 of the 343 functions, R-01) lives in `backends/agentdojo/tests/` or `backends/autodojo/tests/`, carries the `agentdojo` or `autodojo` marker (meaning "backend project", not "core extra"), and never uses `importorskip`.

---

## K.3 Layout, configuration, markers and shared infrastructure

### K.3.1 Directory layout (normative)

This layout is the authority for test and fixture paths (R-48). Core tests live in `tests/`. The projects outside
core carry their own `tests/` directories and are run with their own interpreters (K.1(10)).

```
tests/                           # core; Python 3.14; imports no benchmark, no agentprov_backend, no httpx/openai
  conftest.py                    # gates, strict skips, network guard, env scrubbing, Hypothesis profiles,
                                 # pytest_assertrepr_compare escaping hook (K.3.4)
  invariants.toml                # invariant registry (K.1.1)
  strategies/                    # Hypothesis strategies (helpers, not collected)
    json_values.py  aer.py  truth.py  render_dialects.py  mutations.py  raw_bytes.py
  fixtures/                      # `binary` in .gitattributes; listed in .ignore/.rgignore (R-42)
    FIXTURES.json                # generated index: path, sha256, source id, licence class, origin (K.4)
    LICENSES/                    # verbatim licence texts, notices and use clauses of every third-party fixture source
    agentdojo/{v0.k11,v1.k14}/  agentdojo_prov_v1/golden/  rope/  agentdyn/  drift/  mandate/
    survey/  agentdojo_inspect/  autodojo_via_rope/  inspect/  stac/  capture/  foobench/  synthetic/
    expected/                    # golden expected outputs: <fixture>.aer.jsonl, .sem.jsonl, .prov.json, .trig
  unit/
    aer/        test_envelope.py test_records.py test_generic_kinds.py test_ids.py test_jcs.py
                test_lex_hints.py test_locators.py test_refs.py test_order.py test_unknowns.py
                test_seal.py test_blobs.py test_accounting.py test_schema_file.py
    ingest/     test_limits.py test_json_loader.py test_jsonl_loader.py test_archives.py test_encoding.py
                test_yamlsafe.py test_quote.py
    raw/        test_store.py test_origin.py test_members.py test_references.py test_purge.py
    sem/        test_annotations.py test_integrity.py test_roles.py test_injection_marker.py test_outcomes.py
    prov/       test_decomposed_model.py test_edge_rules.py test_generic_rules.py test_bundles.py
                test_evidence_attributes.py test_never_emit.py test_unknown_status.py
                test_conversion_provenance.py test_iris.py test_serialise_provjson.py
                test_serialise_trig.py test_semantic_diff.py
    validate/   test_aer_validator.py test_sem_validator.py test_prov_structure.py test_prov_constraints.py
                test_time_flags.py test_serialisation_fidelity.py test_profile_rules.py
                test_evidence_linkage.py test_corpus_validator.py test_report.py test_write_gate.py
    corpus/     test_manifest.py test_index.py test_register.py test_checksums.py test_dedup.py
                test_layout.py test_datasheet.py test_seal_guard.py test_licence_grouping.py
    stats/      test_stats.py                                   # K.5.11 (Addendum B, AD-10)
    views/      test_transcript_v1_view.py test_render_converted.py test_fields_table.py
  render/       test_render.py                                  # K.5.12; `render` gate
  prov/
    compat/adprov_v2_3/          # ported baseline builder/communication/marker tests (legacy behaviour pinned)
    spec_agentprov_prov_0_1/     # catalogue-level rules of the new specification
  adapters/
    test_profile_schema.py test_rule_catalogues.py test_dialect_detection.py
    registry/   test_registry.py test_status.py test_claims.py test_render_tables.py
    agentdojo/  test_tracelogger_v0_k11.py test_tracelogger_v1_k14.py
                test_identity.py test_outcomes.py test_quirks.py test_semantics_profile.py
                test_capture_reader.py test_capture_mapping.py
                test_scoring_rules.py                           # rule sets agentdojo.scoring@1 / @2 (B TST-12; J.5)
                profiles/ test_rope.py test_agentdyn.py test_drift.py test_mandate.py test_survey.py
                          test_agentdojo_inspect_dedup.py test_autodojo_via_rope.py
    adprov/     test_reader.py test_mapping.py
    inspect/    test_reader.py test_mapping.py test_resolution.py test_judges.py
    stac/       test_design_note.py                             # STAC planned (design-note fixture)
    foobench/   test_dialect.py test_mapper.py test_rules.py test_fuzz.py   # added with the adapter (D.12.1 row 9)
                test_future_framework.py                        # K.6.4 (D.12; DoD Q.3)
  golden/       test_compat_bytes.py test_v1_round_trip.py test_golden_outputs.py test_golden_index.py
  integration/  test_offline_import_e2e.py test_live_mapping.py test_run_spawn.py
  differential/ test_live_vs_native.py test_native_vs_v1.py test_old_vs_new_package.py
                test_schema_vs_validator.py test_prov_library_parity.py
  property/     test_ids_props.py test_jcs_props.py test_refs_props.py test_determinism_props.py
                test_never_emit_props.py test_evidence_props.py test_order_props.py
                test_validator_props.py test_mapper_props.py
  fuzz/         test_reader_fuzz.py test_jsonl_fuzz.py test_locator_fuzz.py test_capture_log_fuzz.py
  security/     test_archives.py test_json_limits.py test_jsonl_framing.py test_encoding.py test_names.py
                test_decompression.py test_links_special_files.py test_locator_traversal.py
                test_tamper.py test_reordering.py test_inband_claims.py test_time_claims.py
                test_identity_spoofing.py test_metadata_poisoning.py test_untrusted_content.py
                test_quote_untrusted.py test_yaml_bombs.py test_static_dangerous_calls.py
                test_worker_isolation.py test_secrets.py test_fetch_hardening.py test_deposits.py
                test_supply_chain.py test_interpreter_guard.py test_agent_channels.py
  reproducibility/ test_recompute.py test_cross_process.py test_parallel.py test_environment_independence.py
  migration/    test_test_map.py                                # J.5 per-function map: each of the 363 frozen
                                                                # baseline test ids once in migration/test_map.json
  boundary/     test_import_boundary.py test_optional_extras.py
  cli/          test_cli_contract.py test_cli_import.py test_cli_validate.py test_cli_package_verify.py
                test_cli_recompute.py test_cli_stats.py test_cli_render.py test_cli_purge.py
                test_cli_output_safety.py
  docs/         test_doc_examples.py test_rule_docs.py test_ontology.py test_links.py test_traceability.py
                test_status_docs.py test_claims_lint.py
  repo/         test_repository_hygiene.py test_unicode_controls.py
  perf/         test_perf_smoke.py
  full_corpus/  test_baseline_corpora.py test_upstream_pinned_import.py test_inspect_survey.py

capture/tests/                   # agentprov-capture; Python 3.12 and 3.14; stdlib + rfc8785 only
  test_event_model.py test_writer.py test_chain_verifier.py test_redact.py test_envstate.py

backends/shared/tests/           # agentprov-backend; Python 3.12
  test_gateway.py test_recording_transport.py test_scripted_transport.py test_worker_protocol.py
  test_netguard.py

backends/agentdojo/tests/        # backend project; Python 3.12; agentdojo==0.1.35; marker `agentdojo`
  test_live_capture.py test_passes_and_retries.py test_resume.py test_reasoning_capture.py
  test_executor_mirror.py test_defended_pipelines.py test_builder_agentdojo.py test_c6_old_vs_new.py
  test_hostile_worker.py         # hostile scripted T2 worker (G.10 SEC-14, SEC-25; K.8.4(7), K.12.16)

backends/autodojo/tests/         # backend project; Python 3.12; fork @ aa458794…; marker `autodojo`
  test_worker_fake_client.py test_executor_mirror.py
```

Notes on the layout:

- Test modules MAY share basenames across directories. The configuration uses `--import-mode=importlib`.
- The baseline's `testpaths = ["tests"]` exists because "bare `pytest` must not collect the vendored *-main/ directories" (baseline `pyproject.toml`). AgentPROV MUST keep `testpaths = ["tests"]` in core. Each other project sets `testpaths` to its own `tests/`.
- The canonical paths named by RESOLUTIONS R-48 are `tests/boundary/test_import_boundary.py`, `tests/unit/corpus/test_dedup.py`, the registry tests under `tests/adapters/registry/`, and the golden fixtures under `tests/fixtures/agentdojo_prov_v1/golden/`.
- Coverage-guided fuzzing (`fuzz_atheris/`) is deferred (AD-10 row 18; K.11.3).

### K.3.2 Test-support packages `agentprov.testing` and `agentprov_backend.testing`

There are two test-support packages, one per side of the A1 process split (AD-01(e)). Neither is installed where it
does not belong: backend projects never install `agentprov` (so they never see `agentprov.testing`), and core never
imports `agentprov_backend`.

**`agentprov.testing`** (`src/agentprov/testing/`, core only). It MUST import nothing beyond core dependencies.

| Module | Contents |
|---|---|
| `agentprov.testing.netguard` | `install()` and `uninstall()` patch `socket.socket.connect`, `socket.create_connection` and `socket.getaddrinfo` to raise `NetworkBlocked`. T1 import workers call `install()` when `AGENTPROV_BLOCK_NETWORK=1`. |
| `agentprov.testing.fs_guard` | Snapshot or diff of a directory tree (paths, sizes, sha256). Used for "dry run writes nothing" and "nothing written outside tmp". |
| `agentprov.testing.projections` | `common_projection(aer_records) -> dict`: the comparable view used by the differential tests (K.9.1, K.9.2). |
| `agentprov.testing.golden` | Loader for `tests/fixtures/expected/` and the golden index. Byte-comparison helpers report the line number, the JSON Pointer and **both sha256 values** of the first difference. Any excerpt goes through `escape_untrusted` and is truncated, so helper output never holds a fixture substring longer than 40 characters (R-42; SEC-12/SEC-13). |
| `agentprov.testing.inference6` | The port of the stdlib scan `landscape/prov_semantics_evidence/inference6_scan.py`, used as the reference implementation of the Inference-6 closure (K.10.2). |

**`agentprov_backend.testing`** (`backends/shared/`, Python ≥ 3.12; it may import `httpx`).

| Module | Contents |
|---|---|
| `agentprov_backend.testing.ScriptedTransport` | `ScriptedTransport(script: Script)` built on `httpx.MockTransport`. `Script` is a list of steps: `Reply.tool_calls([...])`, `Reply.text(str)`, `Reply.null()`, `Reply.refusal(str)`, `Reply.reasoning(...)`, `Fail.http(status)`, `Fail.malformed_args(raw: str)`, `Fail.no_choices()`. Each step MAY carry a request predicate (`expect=lambda req: ...`) that is checked against the *wire* request. Exhausting the script raises `ScriptExhausted`; the test then fails, it does not hang. `ScriptedTransport.requests` keeps every request verbatim. The worker loads a script from a file passed by path (K.8.4). |
| `agentprov_backend.testing.netguard` | The same socket guard for the T2 worker. The worker entry calls `install()` when `AGENTPROV_BLOCK_NETWORK=1`. The core and backend guards share one test table (`backends/shared/tests/test_netguard.py` mirrors `tests/security/test_worker_isolation.py`). |

### K.3.3 Pytest configuration (normative excerpt of `pyproject.toml`)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-markers", "--strict-config", "-ra", "--import-mode=importlib", "-p", "no:cacheprovider"]
xfail_strict = true
filterwarnings = [
  "error",
  # rdflib 7.x emits this from its own serialiser (693 occurrences in the baseline run, BASELINE §2);
  # scoped narrowly so that any new deprecation fails the suite.
  "ignore:Dataset.default_context is deprecated:DeprecationWarning:rdflib.graph",
]
markers = [
  "slow: more than ~5 s per test, or long Hypothesis/fuzz budgets; gate",
  "network: needs outbound network; gate",
  "live_artefacts: consumes capture/0.1 and native logs produced by a backend job (K.8.5); gate",
  "full_corpus: needs the frozen baseline corpora / full pinned upstream logs on disk; gate",
  "old_package: needs agentdojo-prov 1.0.0 @ 579a908 in a separate interpreter; gate",
  "shacl: needs the shacl extra; gate",
  "render: needs the render extra (pydot) and the graphviz dot binary; gate",
  "invariant(id): traceability tag (not a gate)",
  "allow_skip(reason): permits a runtime skip under AGENTPROV_STRICT_SKIPS=1 (not a gate)",
]

[tool.coverage.run]
branch = true
source = ["agentprov"]
parallel = true
concurrency = ["multiprocessing"]
```

The core configuration registers **no** `agentdojo` or `autodojo` marker. With `--strict-markers`, a core test that
carries either marker fails at collection, which keeps benchmark tests out of core (K.1(10)). The backend projects
register them in their own `pyproject.toml`: `agentdojo` ("backend project `backends/agentdojo`, agentdojo==0.1.35")
and `autodojo` ("backend project `backends/autodojo`, fork at `aa458794b7eb7f082e94daeac4c0f55bfc0c90cc`"). The
`analysis` marker is gone with the `analysis` extra (AD-10 row 1).

Dev tooling: the `dev` extra is `pytest`, `hypothesis`, `ruff`, `mypy` and `jsonschema` (RESOLUTIONS §3.1), plus the
test-only additions `pytest-xdist`, `pytest-timeout` and `coverage[toml]`. These are never core runtime dependencies.
The type checker is mypy (`python_version = "3.14"`); ruff uses `target-version = "py314"`. Atheris and mutmut are
deferred (AD-10 row 18).

### K.3.4 `tests/conftest.py` responsibilities (normative)

1. **Gates.**
   - Option `--gates=<comma list>` enables gate markers. The environment variable `AGENTPROV_GATES` has the same effect.
   - Items carrying a gate marker that is not enabled are **deselected**, not skipped, in `pytest_collection_modifyitems`. They are reported through `config.hook.pytest_deselected`.
   - Locally, with `AGENTPROV_STRICT_SKIPS` unset, the gates `shacl` and `render` are auto-enabled when the extra is importable (and, for `render`, when `dot` is on `PATH`). The backend projects auto-enable `agentdojo` or `autodojo` in their own conftest only when the installed distribution identity equals the pinned one (version `0.1.35` for `agentdojo`; the PEP 610 `direct_url.json` commit for the AutoDojo fork).
   - In CI auto-enabling is off and gates are explicit.
2. **Strict skips.** A `pytest_runtest_makereport` hookwrapper turns a `skipped` report into `failed` when two conditions hold: `AGENTPROV_STRICT_SKIPS=1`, and the test lacks `allow_skip`. This is how "skipped never counts as passed" (D8) is enforced at the test-runner level.
3. **Network guard.** An autouse fixture calls `agentprov.testing.netguard.install()` unless the test has the `network` marker. It also sets `AGENTPROV_BLOCK_NETWORK=1` for subprocesses.
4. **Environment scrubbing.** An autouse fixture deletes every variable matching `(?i)(api_key|token|secret|base_url|openrouter|anthropic|openai|gemini|hf_)`. It also sets `TZ=UTC` and `LC_ALL=C.UTF-8`, except in K.13 tests, which vary them on purpose.
5. **Hypothesis profiles.** Selected by `HYPOTHESIS_PROFILE`:

   | Profile | max_examples | deadline | derandomize | database |
   |---|---|---|---|---|
   | `ci` | 200 | 2 s | true | off |
   | `dev` | 100 | 5 s | false | local `.hypothesis/` |
   | `thorough` | 5,000 | none | false | local `.hypothesis/`, kept between runs (cached in a dispatched run) |
   | `debug` | 10 | — | — | — (`verbosity=verbose`) |

6. **Timeouts.** `pytest-timeout` defaults to 120 s per test. Fuzz tests set their own budgets.
7. **Order independence.** With `AGENTPROV_REVERSE_ORDER=1`, a hook reverses the collection order. It is a local option; a hosted reverse-order run is deferred (AD-10 row 18).
8. **Escaped assertion output (R-42).** A `pytest_assertrepr_compare` hook routes every string operand of a failed comparison through `escape_untrusted` and truncates it, as the golden helpers do (K.3.2). Exception arguments shown in tracebacks are escaped the same way (MN N.1.3). Test output is therefore never a channel for fixture text to reach a coding agent unescaped.

### K.3.5 Markers, gates and where they run

| Marker | Project | Requires | Default (local) | PR CI | Manual CI (dispatch) | Local only |
|---|---|---|---|---|---|---|
| (none) | core | core deps + `dev` | run | run (`core` job, Python 3.14) | run | — |
| (none) | `capture/` | stdlib + `rfc8785` + `dev` | run | run (`capture` job, 3.12 and 3.14) | run | — |
| (none) | `backends/shared/` | the project lock | run | run (`backend-shared` job, 3.12) | run | — |
| `agentdojo` | `backends/agentdojo/` | `uv sync --locked` in the project (3.12) | auto (identity check) | run (`backend-agentdojo` job) | run | — |
| `autodojo` | `backends/autodojo/` | env built by `agentprov backends build autodojo` | deselected | no | run (`backend-autodojo` job) | on demand |
| `live_artefacts` | core | outputs of the `backend-agentdojo` job (K.8.5) | deselected (frozen fixtures run instead) | run (`live-map` job) | run | — |
| `shacl`, `render` | core | the extra (+ `dot` for `render`) | auto | run (`extras` job) | run | — |
| `slow` | core | — | deselected | no | run | on demand |
| `network` | core | outbound network | deselected | no | run (`network` job) | on demand |
| `old_package` | core | `AGENTPROV_BASELINE_PYTHON` | deselected | no | run (`old-vs-new` job) | on demand |
| `full_corpus` | core | `AGENTPROV_BASELINE_CORPUS`, `AGENTPROV_UPSTREAM_CACHE` | deselected | no | no (corpora are not in Git, D9) | **release gate** (K.20) |

---

## K.4 Fixtures and fixture licence policy

### K.4.1 Fixture provenance (MUST)

1. **`SOURCE.json`.**
   - Every third-party fixture file MUST have an entry in its directory's `SOURCE.json`.
   - The entry copies the schema already used by `investigation/samples/*/SOURCE.json`: `sample_file`, `url`, `repository`, `commit_or_revision`, `original_path`, `sha256`, `git_blob_sha1` (when from git), `size_bytes`, `record_locator` (for byte slices), `licence`, `retrieved_at` and `note`.
   - Two fields are added: `licence_class` (K.4.2) and `synthetic: false`.
   - Every entry, at any depth of the tree, records a boolean `synthetic`, and every real entry a `licence_class` from
     the closed set; `tests/golden/test_fixture_licence_classes.py` enforces this (D-946).
2. **Byte-identical copies.**
   - Fixtures are byte-identical copies of pinned upstream blobs (D3: pinned commits/DOIs, never "latest").
   - The investigation samples are already pinned and verified. One example is `samples/agentdojo/gpt-4o-2024-05-13__banking__user_task_7__important_instructions__injection_task_7.json` at `ethz-spylab/agentdojo@089ed468…`, sha256 `6faf6900…111a` [landscape/trace_formats.md §6.13]. These samples SHOULD seed the fixture set.
3. **Synthetic fixtures** (hand-written edge cases, hazards and invalid inputs) live under `fixtures/synthetic/`. They carry `synthetic: true` and the licence of the AgentPROV repository. Synthetic prompt-injection sentences are **not** stored whole: the fixture holds fragments, and the test assembles the sentence at run time (R-42). Real third-party payloads stay byte-identical, as item 2 requires.
   - **Amendment (D-945).** Synthetic fixtures that replace a source's real fixtures (the five copyleft phase-10d sources: gate, SENTRY, aiAuthZ, bookkeeper, llm-lock) live in that source's directory, at the paths of the logs they replace, and are written by `tests/adapters/agentdojo/phase10d_synthetic.py`; the committed files are checked byte for byte against it. A template holds a placeholder (`@@assemble:<name>@@`) where the log has an injection sentence (joined from fragments) or AgentDojo's default system prompt (read by its pinned digest from the permissive `agentdojo/head/` fixtures); the test support fills it when the test runs. Their `SOURCE.json` entries add `layout_of` (the pin whose layout they follow) and `assembled_at_run_time`.
4. **Agent hygiene (R-42).** `.gitattributes` marks `tests/fixtures/** binary`; `.ignore` and `.rgignore` list `tests/fixtures/`; `.claude/settings.json` denies `Read(./tests/fixtures/**)` and `Read(./.env)`. `tests/repo/test_repository_hygiene.py` asserts all four (K.12.13, K.17).
5. **The index test.** `tests/golden/test_golden_index.py::test_fixture_index` re-hashes every fixture. It fails when any of the following holds:
   - a sha256 mismatch;
   - a file without an index entry;
   - an entry without a file;
   - a `licence_class` outside the allow-list;
   - a cap of `tests/FIXTURES.json` is broken (D-360, user decision 2026-10-13). The caps file sits beside the tree, not
     in it, because `tests/fixtures/**` is closed to agents' reads (item 4); it is checked by
     `agentprov.testing.fixture_caps` (`tests/repo/test_fixture_caps.py` and this index test):
     - the whole tree MUST stay within **16 MiB** (`caps.total_bytes`; it was 8 MiB until D-360);
     - a file over **1 MiB** MUST be listed in `oversize_files` with a reason; it still counts towards the total;
     - a **source** (a top-level directory of the tree) over **512 KiB** MUST be listed in `source_exceptions` with its
       own `budget_bytes` and a reason; it may not grow past that budget;
     - an entry without a reason, an exception for a source that is absent or within 512 KiB, and an oversize entry for a
       file that is absent or within 1 MiB are failures too, so the file stays a true account.
     The complete Inspect `.eval` logs are measured (SWEEP_r2 EV-3): the six survey AgentHarm logs at git
     `89c4db2c949797fbb38c5bfed85dc82780ddbfe3` are 1,388,361 B (`gptoss_harmful`) to 2,385,846 B (`qwen14_benign`),
     11,825,414 B in total. **One** complete log is committed and listed in `oversize_files` with that reason; all six are
     read only by the `full_corpus` gate (K.4.3, K.7.4).

   The largest expected fixture is the R08 golden graph at 590,922 B. The whole golden set is 1.1 MB on disk [BASELINE §7].
6. **Derived fixtures** (amendment, phase 10b, D.16.14). A third-party file that must not be committed byte-identical (a configuration holding sandbox credentials) MAY be committed as a derived test input under `fixtures/<source>/derived/`, with `derived_from {sha256, git_blob_sha1, path, revision}`, the transformation and `modified: true` in `SOURCE.json`; it is never corpus raw, and a `full_corpus` test checks it against the pinned blob.

### K.4.2 Licence classes

The classes are the closed set of RESOLUTIONS §3.8: `permissive | noncommercial | restricted | restricted_use`. The
first draft's separate `own` class is folded into `permissive`; `SOURCE.json` keeps `synthetic` and the origin, so own
work stays distinguishable.

**Repository scope (Addendum B-2; U-06 decided 2026-10-29, D-943).** Every fixture that holds third-party model outputs
is **never in the sdist or wheel**; the package build test asserts the exclusion for every class except synthetic
fixtures. Real fixtures of class `permissive` may be in the **public** repository and in the building-commit snapshots
(D-942), each with its `SOURCE.json` entry and licence text. Fixtures of class `restricted_use`, `noncommercial` or
`restricted`, and entries with no class, stay in the private development repository: the public export
(`docs/reports/release/public-export.toml`) and `tools/building_commit_snapshots.py` leave out each such entry's
`sample_file`, or its whole directory when it names none.

| `licence_class` | Policy | Sources (evidence) |
|---|---|---|
| `permissive` | MAY be committed, and MAY be public (U-06, D-943). The licence text and copyright line MUST be copied to `tests/fixtures/LICENSES/<source>.txt`. | AgentDojo `runs/` (MIT, repository-wide, no separate data licence; basis recorded as "MIT by repository; data licence not separately stated", U-03) [sources/agentdojo.md §1, line 379]; ROPE (MIT) [sources/rope.md §1, §9]; AutoDojo-attack runs hosted in ROPE (MIT) [sources/autodojo.md §9]; AgentDyn (MIT, with AgentDojo's copyright line; "MIT as declared; not legally settled") [sources/agentdyn.md §10; verify/drift.md §1]; DRIFT HEAD blobs (MIT from `6fd3df4`) [sources/drift.md §11]; Mandate-AgentDojo-Eval (MIT; publisher unverified) [sources/mandate-agentdojo-eval.md §12]; MiDojo (Apache-2.0) and ADI (MIT), non-execution samples only [sources/midojo.md; sources/adi.md]; Agent Security Tools Survey AgentDojo runs (CC-BY-4.0; primary origin git `89c4db2c…`, cited with the concept DOI 10.5281/zenodo.22135956 and the version DOI fetched, R-62) [sources/agent-security-tools-survey.md l.391]; AgentDojo-Inspect (NIST notice + AgentDojo MIT; the scoping is a README claim) [verify/agentdojo-inspect.md §2]; and, classed by D-946 (U-06), AgentOps-Bench (Apache-2.0, record and LICENSE), AutoGen guard placement (data CC-BY-4.0, code MIT, third-party parts MIT), MCPHunt agent traces (CC-BY-4.0; record slices), memo-ozdincer/agentdojo (MIT at the pin) and What-Surrounds (CC-BY-4.0, LICENSE-DATA) [docs/reports/release/u06-fixture-classes.md]. **Own work:** AgentDojo-PROV golden pairs and native logs [BASELINE §7] (release data declared CC-BY-4.0, code MIT [BASELINE §4.5]; the converted pairs derive from AgentDojo MIT logs, and the licence of that converted data is the user's decision U-03 [audit/corpus.md §9 item 16]); synthetic fixtures (`synthetic: true`, repository licence). |
| `noncommercial` | MAY be committed to the private repository, with attribution and an `NC` flag. MUST be excluded from the sdist and wheel. MUST NOT be copied into any corpus release unless the release is a `-nc` corpus (licence policy `nc_partition`). | STAC records (CC BY-NC 4.0; policy `nc_partition`; STAC import is `planned`, so no NC corpus is built in v0.1) [sources/multiturn-agent-attack.md §9]. Only the five verified byte slices (59,472 B) are committed, as a design-note fixture (K.6.2). The full 4,962,431-byte file is fetched by pinned recipe under `network` [sources/multiturn-agent-attack.md l.12, §7.1]. |
| `restricted_use` | MAY be committed to the private repository only; never in the sdist or wheel. The use clause is copied verbatim to `tests/fixtures/LICENSES/<source>.txt` and propagates to `licences.restrictions` of any corpus built from it. A corpus with this class is a separate corpus; the builder refuses mixed licence classes (AD-20; K.8.3). | Survey AgentHarm Inspect logs (CC-BY-4.0 deposit; AgentHarm task data "MIT License with an additional clause" restricting use to improving AI safety and security; corpus `ast-survey-agentharm`, U-05) [I card 11 C03; R-07, R-14] |
| `restricted` | MUST NOT be committed. Kept outside Git in `$AGENTPROV_RESTRICTED_FIXTURES`. Tests that need it carry `network` or `full_corpus`. | CIAware-Bench (no licence; gated HF; "do not include … without the authors' permission"; training-use prohibition and canary GUIDs carried in `licences.restrictions`; `ciabench` is `reference` unless the user accepts the card-metadata MIT basis, U-04, AD-21) [sources/ciaware-bench.md §0, l.374]; the AgentDyn HF dataset (no licence) [sources/agentdyn.md §10]; DRIFT history-only blobs that pre-date its licence ("prefer to cite and link rather than re-host") [sources/drift.md §11] |

Model-provider terms for redistributing model outputs inside fixtures were **not assessed** [sources/agentdojo.md:378]. Committing a fixture does not settle them. U-06 (D-943) admits `permissive` fixtures to the public repository on the same footing as the corpora that publish the same data, and the datasheets keep saying that these terms were not assessed.

Fixture trees MUST NOT contain files addressed to AI coding agents (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, …). Several upstream checkouts contain such files [landscape/trace_formats.md §8]. `tests/repo/test_repository_hygiene.py` enforces this rule (SEC-13).

### K.4.3 Required fixture set (minimum, v0.1)

| Fixture group | Content | Origin |
|---|---|---|
| `agentdojo_prov_v1/golden/` | The 15 golden transcript+graph pairs R01–R08 and C01–C07, with `golden_index.json`. **Added (MUST, R-59):** the four MIG-10 pairs as byte copies — release `meta-llama_llama-3.3-70b-instruct/prov/important_instructions/workspace_user_task_10_x_injectiontask7_injection` (3,572 B, nested order) and `google_gemini-2.5-flash/prov/injecagent/workspace_user_task_7_x_injectiontask9_injection` (2,216 B, integral `wall_clock_s`); converted `gpt-4o-2024-05-13-transformers_pi_detector/prov/benign/workspace_user_task_33_benign` (6,761 B, nested order) and `gpt-4o-2024-05-13/prov/important_instructions_no_model_name/banking_user_task_11_x_injectiontask2_injection` (2,092 B, integral `wall_clock_s`) — plus the pinned native logs of the converted ones. Committing them follows U-06 (private repository only). | `investigation/baseline/golden/` [BASELINE §7]; RESOLUTIONS R-59 |
| `agentdojo/v0.k11/` | The 7 native June-2024 logs behind C01–C07, including the 2 baseline fixtures [BASELINE §7; `tests/fixtures/*` sha256 in BASELINE §1.1]. Old-format samples from `samples/agentdojo/`. **Added (MUST):** one empty-`messages` log (207 such logs, claude-3-opus/workspace; `unit: outcome_only`) [BASELINE §4.7]; one injection-task-run-as-user-task log (432 such logs) [audit/legacy_replay.md §1(6)]; one log whose final assistant content is `null` (82 such logs, where two unlogged earlier passes follow from code) [verify/agentdojo.md l.98]; one of the 7 Mixtral logs that the converted tree lacks (R-32). All fetched from `ethz-spylab/agentdojo@c274885610efaaafec38b6d3eb07152ba7ff3f94:runs/` [audit/legacy_replay.md §1(2)]. | upstream (pinned) |
| `agentdojo/v1.k14/` | 14-key content-block logs from `samples/agentdojo/` (`Meta-SecAlign-70B…`, `gemini-2.0-flash-001…`). **Added (MUST):** one `pipeline_name: "local"` log [audit/legacy_replay.md §1(4)] and one log lacking `utility`/`security` (variant `v1.k14.incomplete`) | upstream @ `089ed468…` |
| `rope/`, `autodojo_via_rope/` | `samples/rope/` (6) and `samples/autodojo/rope-runs__*` (4). These include `qwen3-235b/…/autodojo` with `pipeline_name` `gpt-4o-mini-2024-07-18-openrouter-…` (observed while writing this section) and an empty-messages log with no outcome (`vllm_parsed`, 0 messages) [sources/rope.md §4.4] | `xhOwenMa/ROPE@64495e16…` |
| `agentdyn/` | `samples/agentdyn/` (6), covering variants A, B and C and a PI detector [sources/agentdyn.md §3.1, §11]. Variant C files are re-keyed copies of AgentDyn's own history blobs, not of DRIFT history (R-62). B and C are `partial` (stretch, AD-10 row 21) | `SaFo-Lab/AgentDyn@5353cf7…` |
| `drift/` | `samples/drift/` HEAD files. The `history-53dbc6c…` file is `restricted` and excluded. DRIFT is a stretch dialect (AD-10 row 21); its fixtures are committed now so that its tests land with the dialect. | `SaFo-Lab/DRIFT@6fd3df4…` |
| `mandate/`, `survey/`, `agentdojo_inspect/` | the respective `samples/` sets. `survey/` includes outputs in Python `repr` form (2,385 of the survey's outputs are Python repr, not YAML; A6) | as recorded in each `SOURCE.json` |
| `inspect/` (new, `restricted_use`) | The survey AgentHarm members already sampled under `samples/agent-security-tools-survey/` (`agentharm_inspect__gptoss_benign__header.json`, `…__sample_42-1_epoch_1.json`), plus one complete `.eval` log (a zip whose members use method 93, zstd) from the pinned survey origin, covering `input_refs`/`events_data`/`attachment://` references, judge (score) events and a `StoreEvent`/`StateEvent` patch. Synthetic variants add a cached call, an error call, a compaction, an `ApprovalEvent`, a sub-agent span, a `BranchEvent` and a truncated `ToolEvent` where the real logs lack them (R-07). Exactly one complete log is committed (the logs measure 1,388,361–2,385,846 B, 11,825,414 B for all six; SWEEP_r2 EV-3); it is whitelisted in `FIXTURES.json` with that reason, and the fixture tree stays within the caps of `tests/FIXTURES.json` (K.4.1(5)). The six logs (1,056 samples) are imported in full by the local `full_corpus` gate (K.7.4) from the pinned git origin: `--input` on a survey clone outside the workspace, or the bare fetch into `$AGENTPROV_HOME/cache`, both verified against `89c4db2c…` and the blob ids. U-07 (consent for large downloads) applies only to the Zenodo archive of the survey, not to this git origin. | survey git `89c4db2c…` (primary); DOIs per R-62 |
| `stac/` | the 5 byte slices, including id 139 (real agent responses) and id 65 (`ValueError`). STAC import is `planned` (A6): these slices and C.16.3 form a design-note fixture (K.6.2) | `amazon-science/MultiTurnAgentAttack@ddeede7a…` |
| `capture/` | frozen `capture/0.1` sessions produced by the fake-client runs of the `agentdojo` backend project (K.8.1), each with its paired native TraceLogger log, plus corrupted variants. Core tests use these committed sessions, never the transport (AD-01(e)). Regenerated only together with a `capture/` format or version bump (K.7.3). | own work (`permissive`) |
| `foobench/` (new) | The self-authored FooBench JSONL format of D.12 (K.6.4), `*.jsonl` + `SOURCE.json` (D.12.1 row 8): one primary file and the hand-off's second file (`sub-*.jsonl`), containing every D.12 event type — `llm_request`, `llm_response`, `tool_start`, `tool_end`, `guard_verdict`, `plan_update`, `memory_write`, `memory_read`, `screenshot`, `handoff`, `approval` (one `approve`, one `edit`), `text_action`, `checkpoint_restore` and the unknown type `telemetry` (R-17, Addendum B AD-15) | own work (`permissive`, `synthetic: true`) |
| `synthetic/` | Hazard and invalid inputs for K.11–K.12; generic-kind records (`activity`, `artefact`) for K.5.1 and K.5.10; and v1 transcripts exercising fields absent from both corpora: `discarded_attempts`, `meta.n_attempts`, `meta.capture`, structured `reasoning`, `refusal` [BASELINE §0, §5.1]. The v1 transcripts are produced by the ported baseline capture tests and labelled synthetic; they are inside the A1 and A2 byte gates (R-32, MIG-5). | own work (`permissive`, `synthetic: true`) |

---

## K.5 Unit tests

The unit tests cover the AER core, ids, JCS, locators, validators, the evidence model and the engine. Every unit module MUST be runnable with only the core dependencies and `dev` installed.

### K.5.1 AER records and envelope — `tests/unit/aer/test_envelope.py`, `test_records.py`, `test_generic_kinds.py`, `test_unknowns.py`, `test_blobs.py`

C.3 and `schemas/aer-0.1.schema.json` are the only AER contract (R-02). These tests cite C and do not restate it; the
validator codes named below are the test expectations, and their final spelling is C.17's.

1. **Record kinds (Addendum B-1).** All 13 kinds are constructible and serialisable: `execution`, `actor`, `scope`, `message`, `model_call`, `tool_execution`, `decision`, `state_change`, `fixture`, `judgement`, `activity`, `artefact`, `seal`. Every message part type is too: `text`, `reasoning`, `tool_call`, `tool_result`, `blob`, `file`, `uri`, `refusal`, `other`. A 14th kind gives `aer.schema.kind`.
2. Closed core fields (`additionalProperties: false`):
   - an unknown core key gives `aer.schema.additional`;
   - framework data is accepted only under `ext.<declared ns>`; otherwise the result is `aer.ext.undeclared` [trace_formats §6.10];
   - the removed or rejected members are each an `aer.schema.additional` case: `as_sent_of`, `transform`, the forward references `output`, `result`, `replacement` and `spawns`, `judgement.valid`, `judgement.meaning`, `args_requested`, `result_raw`, `args_src`, `tool_result.sha256`, `Time.clock`, `Time.res`, `adapter.code_sha256`, `task.benchmark_version`, and the delta form `{base, plus}` of `model_call.input` (R-02, R-06, AD-03, AD-10 row 14).
3. Envelope:
   - `ev` ∈ {O, D, I} is the record's **existence class** and the default for its fields; a weaker field is tagged through `evf` and never lowers `ev` (R-22). A fixture with an agent actor whose `/model` is inferred keeps the actor's existence class and carries `evf {"/model": "I"}`;
   - `evf` resolution is longest-prefix on `/` boundaries, and `evf` values may be `O:<party>` (C CH-3);
   - `by` ∈ {capture, source, provider, benchmark, config, replay} (D2);
   - every D or I assertion, at record level or through an `evf` JSON Pointer, MUST cite at least one `rule` that matches C's scoped `RuleRef` grammar `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+@[1-9][0-9]*(#/.*)?$`; otherwise `aer.rule.missing`. The rule id is the reference without `#…` (R-09).
4. **Header members (AD-03).**
   - `unit` ∈ {`agent_execution`, `outcome_only`, `scenario`} is required (R-28);
   - `profile` is `{id, version: int, sha256}` and `rules` is `{<ns>: <int>}` (AD-18);
   - each `instrumentation[]` item has the merged shape `{id: "<ns>.<name>@<n>", kind, recorded, params?, detail?, code_ref?}`, with `kind` ∈ {behaviour_preserving, request_modifying, harness_policy, attack_parameter, test_only} and `recorded` ∈ {full, summary, none}; `changes_behaviour` is rejected;
   - every `artifacts[]` entry has `role` ∈ {primary, capture_log, native_log, supporting} and `prov_primary` ∈ {native, byte_derived, secondary, unknown} (default `unknown`, R-22); origin kinds include `member {container, label, method, crc32, size}` (AD-12).
5. **New members of the freeze (R-02).** One positive and one negative case each:
   - `model_call.input` items are `Id<message>` or `{id, sent: [Transform], sent_sha256?}` with `Transform` ∈ {error_substitution, role_rewrite, reasoning_passback, formatting, truncation, other}; `defence` is rejected (a defence rewrite is a `decision`, A5);
   - `model_call.status` ∈ {kept, discarded, error, cached}; retries are expressed through `retry_of`, and `retried` is rejected;
   - `tool_execution.status` ∈ {ok, error, invalid}; `denied`, `not_dispatched`, `unknown` and `validation_error` are rejected, and a denied call is a `decision` with **no** `tool_execution`;
   - `tool_execution` has exactly one of `call`, `requested_by` or `unk {"/call": "ambiguous"}`, and an optional `authorised_by: Id<decision>`;
   - `judgement` has `origin` ∈ {checker, harness_default, harness_rule, recomputed} and optional `generated_by: Id<model_call>|Id<scope>` and `inputs: [Id|PartId]`;
   - `state_change.cause` may be a `model_call`; `state_change.target` ∈ {environment, agent_store, sandbox, other};
   - fixture kinds are `injection_payload`, `attack_plan`, `task_prompt`, `system_prompt`, `tool_definitions`, `environment_seed`, `ground_truth`, `other`.
6. **Enum escape (AD-15).** `actor.kind`, `scope.kind`, `state_change.target`, `decision.verdict` and `fixture.kind` accept `other` only with a `subtype: "<ns>.<name>"` that a family catalogue declares; `other` without it, or with an undeclared subtype, gives `aer.subtype.missing` / `aer.subtype.undeclared`. The pruned values (`workflow`, `step` and `branch` as scope kinds; actor kinds `planner` and `generator`; `target: "memory"`) are rejected; planners, generators and context fabricators are `role` values.
7. **Generic kinds (Addendum B, AD-15)** — `tests/unit/aer/test_generic_kinds.py`, fixtures under `fixtures/synthetic/generic/`:
   - `activity` has `type` (namespaced `<ns>:<name>` with `<ns>` declared in the header `ns`), `actor`, `scope`, `inputs` (backward references to entity-like records only), `t`, `status` and `label`. An undeclared namespace gives `aer.ext.undeclared`; a malformed `type` gives `aer.schema.pattern`;
   - `artefact` has `type` (`<ns>:<name>`), exactly one of `content` or `content_ref` (a `{"$blob": …}` reference), `sha256`, `media` and `generated_by` (a backward reference to an `activity`, `model_call` or `tool_execution`). Both or neither of `content`/`content_ref` gives `aer.schema.oneof`; a `sha256` that does not match the content or the referenced blob gives `aer.blob.digest`;
   - an `activity.inputs` entry that names an activity (or any non-entity-like record) gives `aer.ref.kind`, because a `used` object is never an activity (R-21, NE-19);
   - **specialised kinds first.** An `activity` whose `type` name is the name of a specialised kind (`message`, `model_call`, `tool_execution`, `decision`, `state_change`, `fixture`, `judgement`) gives `aer.activity.shadows_kind`. The future-framework test (K.6.4, adapter `foobench`) asserts that model, tool, guard and approval events map to their specialised kinds, never to `activity`;
   - the `artefact` record kind is distinct from the header's `artifacts[]` entries (raw source artefacts, ids `a<n>`): the id grammars of C.4.2 keep the two disjoint, and a test asserts that no `artefact` record id can equal a header artefact id;
   - local ids of both kinds use the prefixes C.4.2 fixes for them; the test reads the prefixes from the grammar table rather than hard-coding them.
8. Unknowns:
   - `unk` reasons come only from the closed set of seven {`not_recorded`, `lost`, `overwritten`, `withheld`, `ambiguous`, `not_captured`, `not_applicable`}; otherwise `aer.unk.reason` (R-08). In-place redaction (PI detector, AgentDyn detectors, DRIFT isolation) is `overwritten`;
   - an `unk` pointer MUST NOT also carry a value; otherwise `aer.unk.conflict`.
9. Sentinels are forbidden in **typed** fields (D2). Each of the following MUST yield `aer.sentinel`:
   - `"0"` or `""` in a typed time field (`t.start`, `t.end`, …);
   - `""` standing in for a null text;
   - `0` standing in for unknown usage.

   The cases are parametrised from the baseline's actual sentinel: the `"0"` timing stub plus `meta.timing_stubbed` [audit/legacy_replay.md §1(7), §4]. The verbatim stub in `t.raw = {"start": "0", "end": "0"}`, with `unk not_recorded` on `t.start` and `t.end`, is valid: the deny-list applies to typed fields only, and `t.raw` is verbatim (C.7.3; R-30).
10. A source-recorded `null` is kept as `null` with `ev: O`, never coerced [trace_formats §6.2]. A test pins the null-vs-`""` distinction: release `""` vs converted `null` [audit/capture.md §7.2].
11. Blobs:
   - `{"$blob":"sha256:<64 hex>"}` resolves to a stored blob whose digest matches;
   - a malformed reference gives `aer.blob.ref`; a missing blob gives `aer.blob.missing`; a digest mismatch gives `aer.blob.digest`.
12. **C.17 invariants** each have a test: `unit` present; `prov_primary` present; `ext.lex` present when the dialect declares a byte-exact view (K.5.3); `other` requires a declared `subtype`; no `as_sent_of`; no delta form; a `verified` assumption names a framework identity (commit or wheel hash) equal to the one recorded in the AER (F.1.5 item 4; R-05).

### K.5.2 Identifiers — `tests/unit/aer/test_ids.py`

The rule under test is the one function `agentprov.aer.ids.import_execution_id` (AD-04; RESOLUTIONS §3.4):

```
ex = "ex_" + lower(base32_nopad(sha256(b"aer-ex/1\n" + mapping_id + b"\n" + sha256_lower_hex + b"\n" + JCS(loc))))[0:26]
mapping_id = "<adapter id>/<profile id>"          # e.g. agentdojo.tracelogger/agentdojo-upstream
```

1. **Known-answer tests (KAT).** The vectors are generated by `spec/examples/C/gen_examples.py` from the same function and are shared with C.4.1; C.4.1 and K.5.2 MUST carry identical vectors (RESOLUTIONS §5). They pin the byte encoding of each component, the base32 alphabet, lower case, no padding and the `[0:26]` truncation of the full digest. The four vectors of C.4.1, verbatim (all four recomputed with `hashlib`/`base64` in SWEEP_r2 EV-2):

   | # | Mapping id | Artefact SHA-256 | `JCS(loc)` | Preimage SHA-256 | `ex` |
   |---|---|---|---|---|---|
   | 1 | `agentdojo.tracelogger/agentdojo-upstream` | `99e641af97e56971dd67308beec96ac08fdca7063141f3714389733ba845cc8a` (C.16.1) | `{"p":""}` | `fd33a7625df9e869ca8445f0b613855f77c7c31ca3c300e3caab17a25e781345` | **`ex_7uz2oys57hugtsueixylme4fl5`** (obs-K8) |
   | 2 | same | same | `{}` | `5670e59816893573d45e1704128116fe2d5b5666b2201ef91368960e338b404a` | `ex_kzyolgawre2xhvc6c4cbfaiw7y` |
   | 3 | same | same | `{"line":0}` | `06dead820644bf297f8b13a1f92e9ed880a51049b10d51793fa6c6a83dbdc1c2` | `ex_a3pk3aqgis7ss74lcoq7slu63c` |
   | 4 | `inspect.eval/survey-agentharm` | `3a04cbc50dee2ec447a4796004a4800e68d3ceb30a3f886a52db88b184fad35d` (member object `samples/42-1_epoch_1.json` of the survey AgentHarm log, `investigation/samples/agent-security-tools-survey/`) | `{"p":""}` | `4c4c6ae10744f755cae97a1d0ce302dc9577db0826da20bfb9c53e1e79aadf75` | `ex_jrggvyihit3vlsxjpioqzyyc3s` |

   Vectors 2 and 3 are function vectors for the locator canon (whole artefact without parse; a JSONL line, 0-based); vector 4 is a member object stored by `expand` (AD-12) and changes if the profile id `survey-agentharm` changes (C.4.1). A JSON array element (`{"p":"/<i>"}`) and non-ASCII in a pointer are further cases of the same function (checked for the preimage bytes, not as numeric KATs, because C.4.1 carries none for them; ID-1, ID-2).

   A negative vector asserts that the superseded mapping id `agentdojo.tracelogger` gives `ex_xa3om2zkco3ai5e7lo6lwdc4z2`, which MUST NOT equal the id under the canonical mapping id. The first draft's 16-byte truncation (`ex_xa3om2zkco3ai5e7lo6lwdc4zy` for the old mapping id) is rejected and has no vector.
2. **Locator canon in the key.** `bytes` is omitted from the key when `line` or `p` is present; `{}` addresses the whole artefact; `line` is 0-based; there is no archive-member form `m` (AD-12). Adding a byte span to a `p` locator leaves the id unchanged.
3. The adapter *version* is excluded from the id; the adapter *id* and the *profile id* are included [trace_formats §6.4; AD-04(b)]. Changing `adapter.version` leaves the id unchanged. Changing `adapter.id` or `profile.id` changes it: the same bytes mapped under two profiles get two ids, and `source_key` ownership prevents double counting (K.5.8, `test_dedup.py`).
4. Live ids match `^ex_[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (UUIDv7, lower case, hyphenated). They are read from the capture log and never minted at mapping time: mapping the same capture twice yields the same id.
5. Local ids:
   - they match C.4.2's grammar `^[a-z][a-z0-9_]{0,31}$`, with parts `<id>#<k>` and the positional prefixes `m<n>`, `mc<n>`, `te<n>`, `dc<n>`, `st<n>`, `fx<n>`, `j<n>`, `run`, `att<n>`, `thr<n>`, `sc<n>`, `p<n>`, the C.4.2 prefixes of `activity` and `artefact`, and the actor ids `agent`, `user`, `env`, `bench`, `harness`, `att`, `def<n>` or `def_<name>`, `judge<n>`. `def.<name>` and `s<n>` are rejected;
   - they never contain a provider call id, a substring of a content hash, or any substring of record content longer than 3 characters (D2).
6. Instance IRIs follow `https://w3id.org/agentprov/exec/<ex>#<L(id)>`, where `L` maps `#` → `-` (EF E.4.2; AD-04). Injectivity: local ids never contain `-`, so `L` is injective; a property test (ID-5) checks it. `%23` never appears. Ids that are IRI-illegal in the baseline (`#`, `%`, `[`, `]`) [audit/provenance.md §1(8), §14 D11] cannot occur, because local ids are positional.

> **Resolved (AD-04 / R-03):** C's rule stands — `[0:26]` of the lower-case unpadded base32 of the full SHA-256, over
> the preimage `aer-ex/1\n` + `"<adapter id>/<profile id>"` + `\n` + lower-hex sha256 + `\n` + `JCS(loc)` with the
> §3.4 locator canon. K's 16-byte proposal is rejected. The KAT is `ex_7uz2oys57hugtsueixylme4fl5` (obs-K8), identical
> in C.4.1 and K.5.2.

### K.5.3 JCS, lexical hints and deterministic serialisation — `tests/unit/aer/test_jcs.py`, `test_lex_hints.py`, `test_seal.py`

1. Every line equals `rfc8785.dumps(record) + b"\n"`. A record that is valid but non-canonical gives `aer.jcs.noncanonical`. Non-canonical means extra whitespace, unsorted members, `1.0` for `1`, escaped non-ASCII, or a missing final `\n`.
2. The library's behaviour is pinned [obs-K4]:
   - integral floats serialise as integers;
   - integers beyond ±2^53 are not passed to the canonicaliser but encoded as `{"$int":"<decimal>"}` with an `evf` note [trace_formats §6.11];
   - NaN and ±Infinity are rejected at ingest (`ingest.number.nonfinite`), except under the declared `python-json` profile, which maps them to `{"$float": …}` (C.11.3) and records a finding (G.3.3 rule 5);
   - an **escaped** lone surrogate is a finding `ingest.json.lone_surrogate` (severity `info`), not a rejection, and the AER writer encodes the string as `$utf16` (C.11.2; G.3.3 rule 8). The test asserts that the outcome is typed and deterministic, that the original code units are recoverable, and that nothing is silently replaced with U+FFFD. Invalid UTF-8, including UTF-8-encoded surrogates, gives `ingest.json.encoding` (G.3.3 rule 3).
3. **Lexical hints (AD-02; C.11.4).** `aer.canon.lex_hints()` is the only writer of `ext.lex {ord: {ptr: [members]}, flt: [ptr]}`:
   - the hints cover **every** object and number copied from a source, in any field, including typed fields (`t.dur_s`, `params.*`, `usage.*`) — not only tool `args`;
   - they are sparse: an object already in lexicographic order and a number that is not an integral float produce no hint;
   - they are mandatory for adapters that declare a byte-exact view (`adprov.transcript_v1`; `agentdojo.tracelogger` while `render_converted` is a gate), and a missing hint there gives a C.17 validator error; they are optional elsewhere;
   - the flag `flt` suffices: decoding the JCS number to a float and re-dumping it with `json.dumps` reproduces the source numeral for every v1 file (consolidator check 4). A Hypothesis test checks the round trip over finite floats;
   - `ext.lex.num`, `fmt` and `args_src` are rejected (RESOLUTIONS §3.3).
4. Seal:
   - `n_records` counts all lines including the seal;
   - `records_sha256` is the sha256 over the bytes of all preceding lines;
   - `accounting {status, checks}` and `issues[] {code, ids, rule, detail?}` use C.12.3's single closed issue list; `accounting_mismatch` and `model_identity_conflict` are rejected in favour of `accounting_inconsistent` (check `aer.acc.reported_counts@1`) and `identity_conflict` (R-13);
   - a single flipped byte anywhere before the seal gives `aer.seal.digest`;
   - a dropped line gives `aer.seal.count` (or `aer.ref.dangling`).
5. `execution` is the first line and `seal` the last; otherwise `aer.order.envelope`.
6. The `rfc8785` version is recorded in reports. An upgrade that changes bytes MUST fail `test_golden_outputs.py` (K.7.3).

### K.5.4 Locators — `tests/unit/aer/test_locators.py`

The locator members are C.9's: `a` (artefact id; a member object under AD-12), `p` (JSON Pointer), `line` (0-based),
`bytes [s, e]`, `o` (origin pointer) and `blob`, plus `{}` for the whole artefact. Every form is covered, resolved
against the digest-checked stored object:

1. **JSON Pointer (RFC 6901).**
   - `~1` and `~0` decoding, with `~1` decoded first;
   - array indices without leading zeros;
   - `-` rejected for resolution;
   - a pointer into a scalar gives `aer.locator.dangling`;
   - the empty pointer `""` addresses the whole document.
2. **Member object + pointer (AD-12).** An archive member is a derived object produced by the `expand` stage and stored by sha256; the locator names it by its own `a`, and there is no archive-member form `m`. Resolution reads the stored member object, after checking its size and CRC32 against its `raw/members.jsonl` row; nothing is ever extracted to the filesystem (K.12.1).
3. **Byte range `[start, end)`.**
   - Bounds are checked.
   - With `p`, the slice MUST parse equal to the addressed element. STAC slices satisfy this: "json.loads(slice) == source_array[index]" [samples/multiturn-agent-attack/SOURCE.json].
   - STAC's file is `json.dumps(records, indent=2, ensure_ascii=False)` [sources/multiturn-agent-attack.md l.86], so spans are reproducible. In the id key, a STAC element is `{"p":"/<i>"}` and its span is omitted (K.5.2(2)).
4. **`line` (+ `p`)** for JSONL artefacts (capture logs). **0-based** indexing is pinned (RESOLUTIONS §3.4); out-of-range gives `aer.locator.dangling`.
5. **`row`/`col`/`inner`** for CSV and Python-literal cells are deferred with those parsers (AD-10 row 16). A v0.1 locator that uses them gives `aer.schema.additional`. When they return, `ast.literal_eval` semantics only, never `eval` (K.12.6).
6. **Git blob locator.** `sha1(b"blob %d\0" % len(bytes) + bytes)` MUST equal the recorded blob id; otherwise `raw.origin.blob_mismatch`.
7. Every locator in every expected AER under `fixtures/expected/` resolves. This is AER invariant 3 [trace_formats §6.16].

### K.5.5 References and order — `tests/unit/aer/test_refs.py`, `test_order.py`

1. Every typed reference resolves **backward** to a record of the kind its field name fixes (C.5.1–C.5.2). The typed fields are `generated_by` (message, judgement, artefact), `responds_to`, `call`, `requested_by`, `input` (each entry of `model_call.input`), `inputs` (judgement, activity), `scope`, `parent`, `actor`, `subject`, `spawned_by`, `retry_of`, `revises`, `authorised_by` (→ decision), `cause` (→ tool_execution, scope, decision or model_call) and `after[].id`. There are no forward references: `output`, `result`, `replacement` and `spawns` do not exist (K.5.1(2)).
   - forward → `aer.ref.forward`;
   - wrong kind → `aer.ref.kind` (for example `artefact.generated_by` naming a `message`, or an `activity.inputs` entry naming an activity);
   - missing → `aer.ref.dangling`;
   - duplicate id → `aer.id.duplicate` [trace_formats §6.5, §6.16(1)].
2. Cross-execution references `{"ex":…,"id":…}` are accepted only in the fields the AER section allows. They are never resolved inside the single-file validator.
3. Tool-result ↔ call linking records how the link was established (D2):
   - `D` + `*.call_id_unique_match@1` for a unique id match;
   - `I` + `*.positional_match@1` for `""`, null or duplicated ids;
   - `O` for a structural link in the source;
   - a `tool_result` part carries `responds_to` or an `unk` for it; a `tool_execution` carries exactly one of `call`, `requested_by` or `unk {"/call": "ambiguous"}` (AD-03 R-7);
   - the v1 importer checks `tool_call_id == paired call id` and raises `adprov.tool_call_id_mismatch` otherwise (R-30).

   Parametrised over the real id quirks:
   - Cohere null ids (C06);
   - Gemini empty ids (C07);
   - the GLM-4.6 duplicate `call_3275` (R07);
   - 189 legacy OpenAI traces with duplicate ids [BASELINE §5.1, §7].
4. `after` edges carry `b` ∈ {causal, time, pos, proto} and are acyclic (`aer.order.cycle`).
5. **Order semantics.** The absence of an edge means *unknown* (D2). The canonical line order MUST equal the specified deterministic topological order, with ties broken by source position. A valid record set serialised in any other order gives `aer.order.noncanonical`.
6. Accounting (`tests/unit/aer/test_accounting.py`) [trace_formats §6.16(7); audit/capture.md §9.4]. Accounting is computed **once**, by the AER mapper and validator (`agentprov.aer.accounting`); the capture side only seals its hash chain, and the live runner reads the seal verdict to decide re-attempts (R-13):
   - each `tool_call` part has 0 or 1 `tool_execution`, and 0 only with a denying `decision` on it or the issue `unexecuted_tool_call`;
   - each `tool_result` has exactly one `responds_to`, or an `unk` plus an issue;
   - each assistant message has `generated_by`, or an `unk` plus an issue;
   - the verdict is `consistent`, `inconsistent` (issue `accounting_inconsistent`) or `unverifiable` (issue `accounting_unverifiable`); a reported-count mismatch is `accounting_inconsistent` with check `aer.acc.reported_counts@1`.

   Inconsistent executions are **sealed with issues and kept**, never rejected silently (D5).

### K.5.6 Ingest safety (tier 1) — `tests/unit/ingest/*`

These are the functional tests of the loaders; hostile inputs are covered in K.12. They are parametrised over `agentprov.ingest.limits.IngestLimits()`, whose defaults G.3.2 fixes (closing the first draft's open question, R-63). Tests MUST read the limits from that object, MUST NOT hard-code values, and MUST probe `limit-1`, `limit` and `limit+1`. Codes are G.3.9's closed `ingest.*` list.

1. The JSON loader `agentprov.ingest.loaders.strict_json_loads(data: bytes, limits)`:
   - accepts UTF-8 only, decoded strictly from bytes (`ingest.json.encoding` with the byte offset); a UTF-8 BOM gives `ingest.json.bom`;
   - rejects duplicate keys through an `object_pairs_hook` (`ingest.json.duplicate_key`), because `json.loads` collapses them silently [audit/validation.md §7 V14];
   - enforces the depth limit (`ingest.json.depth`, 256 by A2), maps `RecursionError` to it, and runs the iterative depth check;
   - enforces size limits (`ingest.size.file`, `ingest.size.record`);
   - rejects integer strings whose digit count exceeds `max_int_digits` (`ingest.number.digits`) *before* Python's int-conversion limit raises an untyped `ValueError`;
   - rejects NaN and Infinity literals and overflowing floats (`ingest.number.nonfinite`), except under the `python-json` profile (K.5.3(2)).
2. The JSONL iterator `iter_jsonl(fp, limits)`:
   - reads in binary mode, splits on LF (0x0A) only, and yields `(line_no, byte_offset, value)` with 0-based `line_no`;
   - keeps U+2028, U+2029, U+0085 and bare CR inside a record on one line (`str.splitlines()` is forbidden, SEC-03, SEC-11);
   - reports a missing final newline as `ingest.jsonl.no_final_newline`, not as silent acceptance;
   - gives distinct codes for CRLF (`ingest.jsonl.crlf`), blank lines (`ingest.jsonl.blank`), a BOM, NUL bytes (`ingest.jsonl.nul`) and over-long lines (`ingest.jsonl.line_too_long`). Under the strict profile, a malformed line is recorded with its locator and the remaining lines are still mapped.
3. Loaders run **before** parsing on raw bytes, and never on a decoded string first (D8 tier 1). Raw bytes are stored before parsing; a policy or parse violation on bytes within limits yields a degenerate AER with the issue, and raw is kept (G.3.9).
4. `ingest.yamlsafe` (`tests/unit/ingest/test_yamlsafe.py`) is the only YAML entry point. It caps the input at `max_yaml_bytes`, rejects aliases (marker status `ambiguous`, issue `ingest.yaml.alias`), and never constructs Python objects beyond the safe types (AD-17).

### K.5.7 Raw store, capture log and live harness units — `tests/unit/raw/*`, `capture/tests/*`, `backends/shared/tests/*`

1. Raw store (`agentprov.raw.store`):
   - every byte string (artefacts, blobs, capture logs, native logs, archive members) is one content-addressed object `raw/objects/<h0h1>/<sha256>.<ext>`, stored mode 0444 without exec bits (SEC-11);
   - `put(bytes)` is idempotent;
   - stored bytes are byte-identical (sha256 of stored == sha256 of input);
   - a write never overwrites an existing digest with different bytes (`raw.digest.collision`);
   - the origin record in `raw/origins.jsonl` is mandatory.
2. Origins of kind git or HF MUST carry a pinned commit or revision; `latest`, a branch name or an empty value gives `raw.origin.unpinned` (D3). URL origins carry a retrieval date. A `member` origin carries `{container, label, method, crc32, size}` (AD-12).
3. **`expand` stage** (`agentprov.raw.members`, AD-12; `tests/unit/raw/test_members.py`): container sha256 + `fn_digest` map to an ordered list of `(label, method, crc32, size, member sha256)` in `raw/members.jsonl` and `derivation.json`; members not matching the profile's include or nested-archive patterns get a row with disposition `not_selected` (R-40); `verify --level chain` checks each member's CRC32; `rederive` re-runs `expand` and requires identical member digests; nested archives expand recursively up to `max_archive_depth`.
4. `REFERENCES.json` entries carry a hash and an origin, and **no stored command string** (R-43; the fetch command is generated at display time). A reference resolves only if it matches an in-package profile origin (kind, repo/dataset/DOI, pinned revision and sha256); otherwise `raw.reference.unpinned_origin`. Fetched bytes that hash differently give `raw.reference.digest` (tested offline with a stub fetcher).
5. **Purge** (`agentprov.raw.purge`, R-51; `tests/unit/raw/test_purge.py`): `agentprov purge sha256:<hex> --reason secret` removes the object and writes a tombstone (digest, reason, date); `verify` reports the tombstone, never a silent missing object.
6. **Capture log `capture/0.1`** (`capture/tests/`, run on Python 3.12 and 3.14, because both the backends and core install `agentprov-capture`). Event names, envelope and values are C.13's (R-16):
   - the envelope is `seq`, `type`, `ts`, `mono_ns`, `pass`, `actor`, `prev`, `data`, with occurrence ids `occ = o<n>`; `pass_no`, `monotonic_ns` and `p<pass>.t<n>` are rejected;
   - the event types are `session.start`, `instrumentation`, `identity`, `fixture`, `pass.start`, `llm.request`, `llm.response`, `tool.dispatch`, `tool.result`, `decision`, `state`, `pass.end`, `outcome`, `native.log`, `note`, `error`, `session.end`; `llm.exchange`, `llm.span`, `exception` and `artefact` are rejected;
   - `llm.request` carries `input_at` (positions in the pass's native message list) and `n_messages`; `tool.dispatch.at` is optional, and dispatch links by `occ` or `provider_call_id`;
   - `session.end.status` ∈ {complete, incomplete, errored, aborted}, and a terminal event appended by the parent carries `appended_by` ∈ {worker, parent} (`completed` and `by` are rejected);
   - the hash chain verifies (`agentprov_capture` verifier, used by core for reading);
   - append-only behaviour holds (a test opens the log twice and checks that the writer refuses to truncate);
   - `agentprov_capture.redact` applies the G.6.4 header allowlist and hard denylist; benchmark content is never pattern-redacted.
7. **Accounting** is an AER-side unit (K.5.5(6)). The capture-side tests assert only that the writer seals the chain and that `pass.start`/`pass.end` pairs (aborted passes included) are present for the mapper to account.
8. **Live harness units** (`backends/shared/tests/`, Python 3.12):
   - the default LLM element is `native`: stock behaviour, recorded by the recording httpx transport plus LLM-span brackets; the transport never modifies a request (byte-compare the request the SDK built with the one sent), and the brackets record `input_at`/`n_messages` (AD-09);
   - `gateway_compat` (the D5 port of `_CompatLLM`) is opt-in and declared in the header as `request_modifying`/`harness_policy` instrumentation;
   - configured and transmitted parameters are recorded separately (e.g. temperature);
   - discarded and retried replies are kept with a reason, and the per-execution counts of resampled and retried replies are recorded (R-25);
   - the served model id is recorded `by: provider` next to the requested one [audit/capture.md §9.3; audit/capture.md §8 D6];
   - the worker speaks protocol `agentprov-backend/0.1` (`test_worker_protocol.py`).

### K.5.8 Validators — `tests/unit/validate/*`

There is one module per D8 tier. Every rule has at least one **builder-independent** hand-written fixture, valid and invalid, under `fixtures/synthetic/validate/`. The baseline built every validator test document with `build_prov`, so validator and builder were never tested independently [audit/validation.md §3.10].

| Module | What it MUST pin |
|---|---|
| `test_aer_validator.py` | AER invariants 1–8 [trace_formats §6.16] and the C.17 invariants (K.5.1(12)). Single pass, streaming, memory bounded by record size × open references. |
| `test_sem_validator.py` | Targets exist in the referenced AER (by digest); rule ids are declared; three-valued integrity ∈ {trusted, untrusted, unknown}, with unknown tools **fail-closed** to `unknown`. The 49 released and 12 converted hallucinated tool names [audit/provenance.md §1(5)] are fixtures. The annotation shape is C.14's (R-18): `type` ∈ {integrity, channel, role, injection_marker, outcome, author} or a namespaced `<ns>.<name>`; `span [start, end]` in Unicode scalar values; `role` an array over EF's security roles including `unknown`; marker `status` ∈ {present, absent, ambiguous, gap}; outcome `{claim, holds?, score?, scale?}`; `integrity` allowed on every content part kind, on fixtures and on `artefact` records. `prop`, `{start, end}`, `present: bool` and the type names `security_role`, `source_channel`, `contains_payload`, `outcome_meaning` are rejected. |
| `test_prov_structure.py` | **Totality:** relation sections that are `null`, numbers or booleans give FAIL with errors, never an exception (baseline V1) [audit/validation.md §6.3]. Unknown or typo sections (`wasGeneratedby`) and attributes under undeclared or foreign prefixes are reported, never passed unexamined (V2). The `prov` prefix is never declared. **R-21 checks:** no `used` object is an activity; every `mentionOf` supra is declared as an entity; the core declares every node it references. |
| `test_prov_constraints.py` | Faithful PROV-CONSTRAINTS checks, separated from profile rules. Constraint 24 is keyed on (entity, activity); simultaneous multi-generation passes under 39. Constraint 42 is implemented through the event graph of the ordering constraints (regeneration-batch item 10: `pv.constraints.ordering`, with C51, C26 and the cycle lints), tested with a derivation cycle and with a strict edge closed through C37/C44 edges [audit/validation.md §6.3, §7 V6–V7]. 53/54/55 use the Recommendation's relation sets. Direct tests exist for 24, 26, 42, 51, 52 (reflexive and through a cycle), 53, 54 and 55; 33/34/35 enter only as edges of the event graph. Checks run per bundle; the union core ∪ inference bundles is checked as an application view [prov_semantics §7.2(5)]. |
| `test_time_flags.py` | Time-consistency results are **flags**, reported separately and never validity failures (D8). A missing time is not a violation [audit/validation.md §8(6); prov_semantics §3.19]. |
| `test_serialisation_fidelity.py` | Round trip: the PROV-JSON → PROV-O (N-Quads, one named graph per bundle; TriG before D-89 step 2) → PROV-JSON model is equal, and each named graph is isomorphic [prov_semantics §7.4(1)]; comparing N-Quads line sets gives the findings of comparing parsed triple sets, blank nodes included. TriG is produced on demand (`derive --trig DIR`, outside the sealed tree; AD-10 row 3); the round trip stays a validation check. A **negative control** shows `round_trip` failing. Completeness covers every section and prefix and compares *typed* literals: `"3"` vs `3` fails (V3). The reverse direction checks that every triple is explained by the JSON. The check drops implied unqualified triples before comparing: materialising them made `prov` 3.2.2 re-import 48 records instead of 37 [prov_semantics §7.4(4)]. `evq_sample.json` from `landscape/prov_semantics_evidence/` is a fixture. |
| `test_profile_rules.py` | Shape rules live per specification (`agentprov-prov/0.1`, `adprov-v2.3-compat`), never in the generic validator [audit/validation.md §7 V8]. The compat rules I1–I11 are pinned by the ported tests. VAL-05…VAL-12 are *new* generic validators in `validate/`, beside the verbatim `conformance.py` of the compat port (R-31). SHACL shapes live in `validate/shapes/` (`shacl` gate). |
| `test_evidence_linkage.py` | Every core statement's `apv:sourcePointer` resolves to an existing AER field that justifies it. The resolved field's evidence class must not be weaker than the statement's (K.10 EV-5). **Existence rule (R-22):** a statement's class is at most the existence class of every endpoint. Corrupting one pointer gives `prov.link.unresolved`. A pointer that resolves to a record that does not justify the statement gives `pv.linkage.pointer_unbound`; a class above the rule's ceiling or the node record's existence class gives `pv.linkage.ceiling` / `pv.linkage.existence`; a document validated against another AER gives `pv.linkage.aer_binding` (D-621; `tests/unit/prov/test_tier4_bindings.py`). |
| `test_corpus_validator.py` | The corpus tree is RESOLUTIONS §3.6's, with the required AD-20 additions `register.jsonl`, `validation/`, `derivation.json`, `schemas/`, `raw/origins.jsonl`, `raw/members.jsonl` and `CHANGELOG.md`; `views/` is optional. The manifest digest chain raw → AER → SEM → PROV holds; checksums cover every shipped file, *including manifests* [audit/corpus.md §9 P3; BASELINE §8(6)]. Duplicates are detected by `source_key` with one owner per key. Lineage is declared once, in the owner profile's `[lineage]`, and mirrors appear in `raw/origins.jsonl`. Compat outputs are flagged `apv:status apv:RegressionOracle` (profile `adprov-v2.3-compat`) in the manifest and the index (R-55). Instance IRIs are unique across executions (V13). The corpus `rules/` copies are compared by digest (`rules.mismatch`); they are a record, not an authority (AD-14). |
| `test_report.py` | A skipped check is reported as `skipped`, never `pass`. Release mode fails on any skip (D8; baseline V11). Library versions (`prov`, `rdflib`, `pyshacl`, `rfc8785`) and the interpreter version are recorded (V19; K.20). |
| `test_write_gate.py` | No AER, SEM or PROV file is persisted unless its validator passes. The canonical record is written before derived artefacts, and writes are atomic (port of `test_generate.py`, `agentdojo_prov/generate.py:441-468`). A failing gate leaves the target tree byte-identical (`fs_guard`). |

### K.5.9 Semantics (SEM) — `tests/unit/sem/*`

1. Every annotation carries an evidence class and a rule id (D6). SEM is hashed separately, and its digest links to the AER digest. The SEM file is `sem/<sem_profile_dir>/<ss>/<ex>.sem.jsonl`; the AgentDojo semantics profile id is `agentdojo.suites` (version `1`, directory `agentdojo.suites-1`).
2. Injection marker:
   - the YAML/repr normaliser is ported byte-exactly with the baseline's YAML-style cases (`tests/test_prov_builder.py` marker tests [audit/provenance.md §11]); YAML is parsed only through `ingest.yamlsafe`, and the survey's Python-repr outputs go through the marker normaliser registry (A6);
   - its error model is explicit: ambiguous readings are flagged with an assumption [prov_semantics §8.2 R-INJ-QUOTE], and R-INJ-QUOTE is an assessment, not a PROV relation (AD-19(d));
   - the four-valued marker status `present | absent | ambiguous | gap`, with `gap` distinct from `absent`, is preserved [audit/corpus.md §8(9)]; a rejected YAML document is `ambiguous` (R-18).
3. Outcome interpretation:
   - polarity is explicit in the SEM `outcome` annotation `{claim, holds?, score?, scale?}`, never in the AER `judgement` (R-18, R-24); a graded judge score is carried as `score` with its `scale`;
   - benign `security` is never an attack success;
   - DoS families are untargeted, so `security = not utility` is a harness rule [audit/legacy_replay.md §1(5)]. This fixes the 178 DoS successes miscounted in the converted manifests [audit/corpus.md §1(3b)];
   - `judgement.origin` ∈ {checker, harness_default, harness_rule, recomputed} (C's enum, R-13). The first draft's finer cases are rule ids under it [audit/legacy_replay.md §12.2]: benign constant → `harness_default` + `agentdojo.benign_security_constant`; run error → `harness_default` + `agentdojo.run_error_imposed_outcome`; DoS → `harness_rule` + `agentdojo.dos_security_rule`. Source-released recomputations (ROPE corrections) are `recomputed`, `by: source`.

### K.5.10 Provenance engine — `tests/unit/prov/*`

Regenerated from EF's rule catalogue (`prov/catalogue/agentprov-prov-0.1.toml`) per R-24: **one hand-built AER
fixture per rule branch**, and each test asserts statements by EF rule id. The engine reads evidence classes from the
AER only (static model, AD-05): a test that changes a profile's assumption status without changing the AER asserts
byte-identical PROV output.

1. **Decomposed model (D7).** Fixed AER inputs MUST produce exactly:
   - one `ModelInvocation` per `model_call` (`aprov.n_model_call@1`); `status: cached` gives `apv:CacheRead` with no `used(model)` and no provider association; `status: error` gives a `ModelInvocation` with no output (R-07);
   - one `ToolExecution` per `tool_execution` (`aprov.n_tool_execution@1`) with status `ok|error|invalid`; `invalid` gives `apv:execStatus apv:Invalid` and generates the error message (R-21); a denied call has no activity (NE-12);
   - `used(mc, m_i)` per input position with `prov:role apv:ContextMessage` and `apv:contextIndex i` (`aprov.use_context@1`), qualified by `apv:sentTransform` and `apv:asSentSha256` when the input item declares `sent` (R-06). One fixture per transform, including `error_substitution` (the case whose communication the first draft lost); no `as_sent_of` copies exist;
   - `used(te, req)` (`aprov.use_request@1`), guarded by NE-18: no `used(te, p)` when a `modify` decision on `p` exists (R-36);
   - generation of messages, request parts and tool results (`aprov.gen_message@1`, `aprov.gen_part@1`, `aprov.gen_result@1`, the last via `message.generated_by` and including the decision class where the target depends on it, R-22);
   - tool-call requests as **members** of the assistant message: `hadMember(msg, req)` with the message typed `prov:Collection` (A5; AD-19(a)); `apv:partOf` for requests is absent. G1 caveat: a test asserts that no `used(x, req)` is derived from `used(x, msg)`;
   - agents and associations (`aprov.assoc_model_call@1`, `aprov.assoc_tool@1`, including `requested_by` delegation when there is no part); actor classes from `kind` + `role`, and `other` → the generic class plus `apv:subtype`; structured author fields become the attribute `apv:declaredSender`, never `wasAttributedTo` (A5); `model_call.served_model` is used when present.
2. **`aprov.use_context@1` evidence class (AD-05).** The class is the one the adapter emitted at map time:
   - OBSERVED when the wire request was captured (`by: capture`) with recorded `input_at`, or the source records per-call input (Inspect `ModelEvent.input`);
   - DERIVED when `/input` is D under an assumption whose verification names a framework identity equal to the one recorded in the AER; capture completeness is **not** a condition (AD-19(d));
   - otherwise INFERRED, emitted in an inference bundle; not emitted when `/input` is `unk` (`apv:contextStatus` instead).

   The released AgentDojo-PROV v1 transcripts are the INFERRED case: their context usages go to the inference bundle `inf.adprov-context_is_prefix-v1` with assumption status `asserted` (unless a digest-pinned harness is supplied, U-01). For reasoning-returning OpenRouter models, the passed-back reasoning context is `not_captured` or `ambiguous` (§13 G2). One fixture per branch.
3. **Communications (AD-19(c); R-53).** `wasInformedBy` is asserted for **exactly** the Inference-6 closure over named activities (`aprov.comm@1`), taken over the core ∪ the bundles of the method set, each statement with `apv:premise` listing only witnesses within its scope and of class ≥ its own class. The closure includes the generic activities of item 9. The reference implementation is `agentprov.testing.inference6` (K.10.2).
4. **Bundles.**
   - the core bundle holds only O and D statements; INFERRED `after` attributes are routed to mentions in the inference bundle (R-53);
   - one inference bundle per method; method responsibility is expressed by the method's plan or a qualified association of `derive` with the method agent, never by `wasAttributedTo(bundle, adapter)` (R-56);
   - the assessment bundle holds integrity, roles, exposure, taint and marker. Mentions apply only to entities: each mention entity occurs in exactly one `mentionOf`, and there is one mention per (subject, annotation) (AD-19(b)). Activities and relations get `apv:Assessment` with `apv:subject` (R-21). Exposure's subject is the request part, else the `tool_execution` via `apv:Assessment`. R-ATTR-AUTHOR is an INFERRED authorship assessment. Nothing in it is `used`/`wasDerivedFrom`/`wasInfluencedBy` [prov_semantics §7.2];
   - configuration ground truth (attack, target and defence ids, payload fixtures, attacker attribution, outcome values) is in the core (AD-11); SEM-dependent interpretations are not.
5. **Conversion provenance (top level).**
   - `wasDerivedFrom(bundle, raw)` is always stated; `hadPrimarySource` only for artefacts with `prov_primary` ∈ {`native`, `byte_derived`} (`aprov.t_primary@1`, failing closed; NE-20; R-22);
   - `wasDerivedFrom(canonical, raw, normalise, g, u)`;
   - engine and adapter agents; the rule catalogue as `prov:Plan`; code identity from the corpus manifest, not the AER (`aprov.t_agents@1`);
   - version-specific bundle IRIs; **no** `wasRevisionOf` in the per-execution document (per-execution lineage documents are deferred, AD-10 row 5);
   - hashes outside the bundle they cover [prov_semantics §10.1–§10.2].
6. **Unknown-status vocabulary (R-08).** Statuses are one-to-one with the seven reasons — `apv:NotRecorded`, `apv:Lost`, `apv:Overwritten`, `apv:Withheld`, `apv:Ambiguous`, `apv:NotCaptured`, `apv:NotApplicable` — plus `apv:RecordedNull` and `apv:NotObservable`; any other pointer becomes `apv:Gap` (`aprov.status@1`, `aprov.n_gap@1`). `apv:Unknown` never appears. An invocation known to have happened but not held (N-LLM-LOST) is emitted with status `apv:Lost`, never dropped and never invented [prov_semantics §9.2–§9.3].
7. **Context encoding.** `members` is the only v0.1 encoding; `collection` is deferred (AD-10 row 14). If it is reinstated, its test asserts "collection core = members core minus the context usages and their Inference-6 communications" (R-24).
8. **Semantic diff (D7; R-33).** `test_semantic_diff.py` checks, on every golden execution, that every v2.3 relation in the compat graph is accounted for by `prov/compat/semdiff-map.toml` (EF's rule ids; J's closed 7-value disposition vocabulary), that counts reconcile exactly, that `defence_omitted` is Overwritten, and that unexecuted requests number 153 (positional). R5 is evaluated under the full closure; R1/R3 classes follow AD-05.
9. **Generic kinds (Addendum B, AD-15)** — `tests/unit/prov/test_generic_rules.py`. One fixture per rule and class:
   - **G-ACT:** each `activity` gives one `prov:Activity` typed with its namespaced `type`, with its `t` and `status`;
   - **G-USE:** one `used(act, e)` per `inputs` entry, at the class of the input link's `evf` (O and D in the core, I in an inference bundle); an input whose link is `unk` gives no statement;
   - **G-GEN:** `wasGeneratedBy(art, a)` from `artefact.generated_by`, where `a` is an `activity`, `model_call` or `tool_execution`; an artefact without `generated_by` gives the entity only;
   - **G-ASSOC:** `wasAssociatedWith(act, actor)` from `activity.actor`;
   - **closure:** a fixture in which tool execution `te1` generates artefact `X` (G-GEN) and activity `act2` uses `X` (G-USE) MUST yield `wasInformedBy(act2, te1)` with both premises; two generic activities chained through an artefact likewise; and a chain whose usage is INFERRED yields the communication only in the inference bundle;
   - the never-emit checks apply to the generic rules: no `used` of an activity (NE-19), no statement on an `unk` input (NE-12), no relation from `after` or `t` (NE-1).
10. **Further rules from the review.**
    - `aprov.spawn@1`: `wasStartedBy(x:sub, -, x:spawner)` from `scope.spawned_by`, at the class of `/spawned_by` (R-36);
    - `aprov.state_patch@1`: each patched `state_change` generates a new state entity, `prov:Revision`-derived from the previous state of the same target along `after` edges (never file order); with no such path, a fresh entity (R-35; also Inspect `StoreEvent`);
    - `aprov.env_pass@1`: the predecessor environment is chosen along `after` edges under `apv:EnvironmentCarriedOver`, never by digest equality alone; without the assumption, a new `before` entity with no link (R-54);
    - `aprov.decision@1`: a decision on a tool execution's output maps to the output entity (`x:L(te).out`, EF E.4.2) or the part's `.pre`, never to the activity (R-21); a defence rewrite is a decision activity, and the later invocation is informed by the defence, not by the tool (A5);
    - `aprov.outcome@1` and the judgement origin map (R-21): `checker` → a checker activity that uses the output text, E_pre and E_post when present, and every request part of the scored attempt with `prov:role apv:CheckedCallTrace` (R-20); `harness_default` → the value attributed to the harness, with no checker activity; `harness_rule` → `wasDerivedFrom(j_sec, j_util)` through a runner activity; `recomputed` → `wasDerivedFrom(j_new, j_old, [prov:type prov:Revision])`, attributed to the correcting party. No replay check is ever invented. With `judgement.generated_by`, `wasGeneratedBy(j, mc_judge)` replaces the synthetic `.check`, and `judgement.inputs` become `used` statements at their own class (R-37);
    - `aprov.deleg_user@1` is per scope actor; a fixture with `tool_execution.authorised_by` naming an `allow` decision asserts `wasStartedBy(x:L(te), -, x:L(dc))` (`aprov.authorise@1`, EF E.1.4), which replaces `aprov.start_tool@1` for that execution (AD-SW7).

### K.5.11 Statistics (`agentprov stats`) — `tests/unit/stats/test_stats.py`, `tests/cli/test_cli_stats.py`

`src/agentprov/stats/` is the minimal, generic statistics module that Addendum B keeps in v0.1 (AD-10 deviation). It
is core, it reads a sealed corpus read-only, and it imports nothing outside core dependencies (no `pandas`, `numpy`
or `pyarrow`; K.14). The tests run on the K.8.3 mixed corpus and on a hand-built corpus whose counts are known.

1. **Counts per source and status.** Executions per `source_id`, per index `status` (`ok | ok_with_issues | failed`) and per `unit`. `outcome_only` and `scenario` records are reported separately from executions; `n_executions` counts only `unit == agent_execution ∧ execution_observed` (R-28; NC-ALL-13).
2. **PROV statements** by evidence class, by bundle (core, inference, assessment) and by rule id. The class totals equal the statement total; every rule id is in a shipped catalogue; the counts equal an independent recount from the stored PROV-JSON.
3. **Unknown reasons.** Per field pointer, the proportions of the seven reasons (and of known values) sum to 1; `not_applicable` appears only for groups that cannot exist for the source (R-57).
4. **Information-loss table** per source: field-group coverage, i.e. the share of executions per field group that are O or D, against the fixed capability list (R-57, the RQ2 headline metric). The observed share is reported only as composition. The table is generic: no AgentDojo-specific column.
5. **Determinism and safety.** `--json` output validates against its committed schema and is byte-stable across runs and worker counts; `stats` writes nothing into the corpus (`fs_guard`); it prints no artefact content.

### K.5.12 Rendering (`agentprov render`) — `tests/render/test_render.py`, `tests/cli/test_cli_render.py` (`render` gate)

`src/agentprov/render/` is the baseline `visualize.render_prov_graph` (`agentdojo_prov/visualize.py:115`) ported to
read `agentprov-prov/0.1` bundles (Addendum B, AD-10 deviation). It needs the `render` extra (`pydot`) and the
graphviz `dot` binary.

1. **Validated input.** The input is parsed and validated as PROV-JSON before rendering, as the baseline does (`visualize.py:136`). An invalid document gives exit 1 with a typed code, never a traceback.
2. **Core only by default.** The default output contains exactly the nodes and edges of the core bundle; an explicit option (MN N.2) adds the inference or assessment bundles, and their elements are visually distinguished. A golden test compares the **DOT text** byte for byte for R01 and one generic-kind fixture; image bytes are library behaviour and are not compared.
3. **Subprocess discipline.** `dot` is the only subprocess. It is invoked as `["dot", "-T<fmt>"]` with the graph on stdin, a timeout and an atomic write, as in the baseline (`visualize.py:187-205`); no artefact text reaches argv (K.12.6(a)).
4. **Escaping.** Labels built from attribute values escape DOT and HTML-like label syntax (backslash, quote, newline, `<`, `>`, `&`), as the baseline does for titles (`visualize.py:149`). A label holding a synthetic payload with control and bidi characters renders without breaking the DOT parse and without raw control bytes in the DOT text.
5. **Extras and boundary.** Importing `agentprov.render` without `pydot` works; `agentprov render` without the extra or without `dot` exits 3 with a typed "extra not installed" or "missing binary" error (MN N.1.3). `pydot` and `prov.dot` are imported only inside functions (K.14).
6. **No writes into corpora.** Output goes to the path given; writing into a sealed corpus is refused (exit 4).

> **As built.** `tests/render/test_render.py` and `tests/cli/test_cli_render.py` build their corpora in a temporary directory
> from a synthetic generic-kind execution derived by the real engine (`tests/render/render_support.py`); no committed
> fixture is read. Items 1, 2, 4, 5 and 6 are covered, plus DOT determinism across runs, processes with different hash
> seeds and `--jobs`, the absence of `URL`, `href`, `tooltip`, `image` and `shapefile` attributes, an SVG without script
> or link, the `dot` argv, environment and timeout (shell-script stand-ins), and a static scan that `pydot` is imported
> only inside functions and its `create` and `write_*` are never called. The byte-for-byte DOT golden for R01 is not
> committed (the corpora are not in the repository); determinism is asserted by comparison of runs. Tests needing `pydot`
> or `dot` skip with the reason when absent (marker `render`).

---

## K.6 Adapter tests (per reader, dialect and source profile, with real fixtures)

### K.6.1 Registry, profiles and rule catalogues — `tests/adapters/registry/test_registry.py`, `test_status.py`, `test_claims.py`, `test_render_tables.py`; `tests/adapters/test_profile_schema.py`, `test_rule_catalogues.py`

1. The registry is the package `agentprov.adapters.registry` (`__init__.py` with data, factories and `EXTERNAL_OWNERS`; `claims.py`, the one claims/lint library; `render.py`). It is explicit:
   - no entry-point plugin loading (D4);
   - a test asserts that `importlib.metadata.entry_points(group=…)` is never consulted (monkeypatched to raise);
   - registry factories are `agentprov.`-namespaced (SEC-23).
2. **Profiles.** Every shipped profile is TOML and validates against the generic profile schema `[profile] [source] [licence] [lineage] [import]`. Family facts live in `[family.<ns>]` and validate against the schema the family ships; quirk ids and retry semantics are namespaced (`<ns>.<id>`). Profiles carry no status (the registry is the only status store) and no assumptions (they live on catalogue entries). `version` is an integer (AD-18). Commits are 40-hex. Lineage is declared once, in the owner profile's `[lineage]` (R-38, R-45).
3. **Catalogues (R-09).** Each catalogue is `<ns>.rules.toml` with `[catalogue] id = "<ns>"` and an integer `version`, at its home: `aer` in `src/agentprov/aer/rules/`, `aprov` in `src/agentprov/prov/catalogue/agentprov-prov-0.1.toml`, `cap` in `capture/agentprov_capture/rules/`, `corpus` in `src/agentprov/corpus/rules/`, adapter catalogues in `src/agentprov/adapters/<family>/rules/`. A built corpus holds byte-identical copies under `rules/`. Rule references match C's `RuleRef` `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+@[1-9][0-9]*(#/.*)?$`; the rule id is the reference without `#…`. Retired aliases (`agentdojo.log_holds_last_attempt`, `agentdojo.pi_detector_placeholder`, `rope.model_from_directory`, `agentdojo.evaluation_timestamp_is_start`, `agentdojo.blob_introducing_commit`, `agentdojo.defence_from_pipeline_suffix`, `adprov.compat_args_from_raw`) appear in no catalogue and no code. The package ships every released catalogue version (AD-14).
4. **Assumptions (AD-05).** A catalogue entry names core `apv:` assumptions or adapter-declared `<ns>:<Name>` ones. A `verified` assumption carries `{framework_identity, code_ref, test}`, and the AER validator rejects it when the framework identity differs from the one recorded in the AER (F.1.5 item 4). A change of verification status is a new rule id or catalogue version (static model).
5. Rule-catalogue closure:
   - **statically**, every rule-id literal in mapper and semantics code is in the catalogue;
   - **dynamically**, the union of rule ids emitted over all fixtures is a subset of the catalogue;
   - catalogue rules never emitted by any fixture are listed in the test report as uncovered. This is a warning in PR CI and a failure in the release gate unless the rule is whitelisted with a reason.
6. **Honest status (R-15).**
   - Each registry part declares `status` ∈ {supported, partial, planned, not_possible} with a non-empty `caveat`, an evidence availability ∈ {yes, partial, no}, and a part role ∈ {source, mirror, owned_elsewhere, compat_oracle, context, not_executions}.
   - The spec values are v0.1 **targets**: the test asserts equality with I.1.1 as amended (not D11's table), and that the registry value is computed from the D.3.2 gates — a part whose gate fails renders `planned` or `partial`, and `supported` additionally requires that the part's full pinned snapshot imported with zero crashes, every file sealed, and the counts recorded in `docs/reports/` (HON-10).
   - There is no best-case aggregation: a one-status rendering is per part, or worst-case with a `mixed` marker.
   - A source with status `not_possible` (MiDojo, ADI) MUST have no reader that accepts its files [sources/midojo.md; sources/adi.md].
   - `docs/` status tables, `info --matrix|--must-not-claim` output, MN N.3 texts, HL H.4.2 and A.5 are generated from the same data (K.16).
7. **Claims library** (`test_claims.py`; AD-08 as ruled). The registry-generated phrase "adapter-based core; demonstrated on N sources in K formats (single-agent, tool-calling traces)" is produced from the registry, and only after the Inspect DoD item (Q.11a) is recorded as passed. The bare term "benchmark-agnostic" is accepted only in passages the library recognises as statements of the core's architectural design goal; in any empirical coverage claim it is a lint failure. "Live Capture" in a title requires an approved, sealed, non-`test_only` live corpus (U-18). The I.4 must-not-claim items, including NC-LIVE-01, NC-PROV-01 and NC-ALL-13 (outcome-only and scenario records are not agent executions), are lint rules; NC-ALL-09 (redistribution) is enforced by `package`, not by the lint (K.8.3(6)).

### K.6.2 Per-dialect and per-profile matrix (MUST)

Every row MUST check five things:

- (a) dialect detection: positive on its fixtures and negative on every other fixture group;
- (b) mapping to the committed expected AER, byte-equal (K.7.3);
- (c) the emitted rule ids;
- (d) the declared unknowns and seal issues;
- (e) the listed quirks.

Every row also asserts the header members of K.5.1(4): `unit`, `prov_primary` (`native` for TraceLogger logs from a
pinned upstream commit), `profile {id, version, sha256}` and integer `rules`. Rule names are D.5.4's.

| Reader / profile (D4) | Test module | Fixtures | Quirks and unknowns that MUST be asserted |
|---|---|---|---|
| AgentDojo TraceLogger `v0.k11` (June-2024, 11-key), profile `agentdojo-upstream` | `agentdojo/test_tracelogger_v0_k11.py`, `test_quirks.py`, `test_outcomes.py` | `agentdojo/v0.k11/`, the C01–C07 natives | String content, not blocks. Tool timing `unk: not_recorded` with **no** `"0"` [audit/legacy_replay.md §4]. Run start/end `not_recorded` and `dur_s` observed. Inline `<thinking>` kept verbatim in text, with any extraction only as a SEM annotation (C01/C03) [audit/legacy_replay.md §4]. Spotlighting delimiters preserved (C02). PI-detector redaction gives `decision{verdict:"redact"}` with `ev:I`, rule `agentdojo.pi_detector_sentinel` and `unk {"/original": "overwritten"}` (C05) [trace_formats §6.6; R-08]. DoS polarity (C04): origin `harness_rule` with `agentdojo.dos_security_rule`. The benign `security` constant gives origin `harness_default` with `agentdojo.benign_security_constant`. `run_error` gives origin `harness_default` with `agentdojo.run_error_imposed_outcome` (C06). Null ids (C06) and empty ids (C07) give positional linking `I`. Empty `messages` gives `unit: outcome_only`, an `execution` + `judgement` with seal issue `no_execution_observed`, kept and not dropped [trace_formats §6.7]. Injection-task-as-user-task is typed, not labelled benign [audit/legacy_replay.md §1(6)]. A null final content yields derived earlier attempts (two unlogged passes, D from code) [verify/agentdojo.md l.98]. Otherwise the attempt index is `unk lost` with issue `earlier_attempts_unobservable` [trace_formats §6.7]. The log holds the last pass only (`agentdojo.log_holds_last_pass`, `apv:LastPassOnlyLogging`). Model identity comes from D's directory + table rule `agentdojo.pipeline_dir_is_model_identity` (class I), with `unk /model/served` [trace_formats §6.6]; the defence id from `agentdojo.defence_suffix` is class I, because June-2024 logs have `code_identity = "unpinned"` (R-09). `ext.lex` is present (byte-exact view while `render_converted` is a gate). The 7 Mixtral logs map like any other (R-32). |
| AgentDojo TraceLogger `v1.k14` (2025+, 14-key) | `agentdojo/test_tracelogger_v1_k14.py` | `agentdojo/v1.k14/`, `mandate/`, `survey/` | Content blocks. `evaluation_timestamp` (naive local, set in `TraceLogger.__init__`) goes to `t.raw` with `unk … ambiguous` (timezone) under `agentdojo.naive_local_timestamp`, and is never coerced to UTC [verify/agentdojo.md; trace_formats §6.7]. `agentdojo_package_version`/`benchmark_version` are recorded `O` but do not establish distribution identity (D9); the label goes on the `bench` actor's `version`. `pipeline_name: "local"` gives seal issue `identity_conflict`, flagged, not resolved [audit/legacy_replay.md §14(9)]. `placeholder_args` passes through when present. A missing `utility`/`security` gives variant `v1.k14.incomplete` and issue `incomplete_run`. Two key orders in Mandate logs are both detected [sources/mandate-agentdojo-eval.md §4.2]. |
| DRIFT-extended (`drift.k18.messages`, `drift.k18.conversations`) — **stretch** (AD-10 row 21; registry `partial`) | `agentdojo/profiles/test_drift.py` | `drift/` | Required when the dialect lands. `initial_checklist` is JSON inside a string: the raw string is kept and decoding is a `D` step. DRIFT tags in assistant content are preserved. No `injections` map gives `fixture` `unk`. The `conversations` key is detected as its own variant. DRIFT isolation of tool outputs is `overwritten`. **Timestamps embedded in tool outputs (371 HEAD runs) MUST NOT become `t` values** [verify/drift.md l.20]. |
| AgentDyn variants A/B/C (A `supported`; B and C `partial`, stretch) | `agentdojo/profiles/test_agentdyn.py` | `agentdyn/` | Variant detection by key set (A 14-key, B 11-key Progent 0.1.29, C DRIFT-shaped) [sources/agentdyn.md §3.1]. Variant C executions are re-keyed copies of AgentDyn's own history blobs; lineage edge E11 targets `agentdyn` `history`, owner `agentdyn` (R-62). Directory names are publisher-asserted labels. Bare-model `pipeline_name`, with the defence visible only in the directory: inferred identity with rule [sources/agentdyn.md §3.6]. `user`-role messages authored by the defence (tool_filter prompt, DRIFT refusal, `error` key) are attributed to a defence actor (`def<n>` or `def_<name>`) with `ev:I` [sources/agentdyn.md §3.7]. The PI-detector placeholder gives a redact decision with `unk overwritten`. The system-prompt line differs by variant (profile quirk) [sources/agentdyn.md §4.4]. Runner-assigned outcomes on JSON-decode errors give origin `harness_default` with `agentdojo.run_error_imposed_outcome` [sources/agentdyn.md §4.4]. |
| ROPE profile | `agentdojo/profiles/test_rope.py` | `rope/` | The ROPE system-prompt line (D4 quirk). A denial gives `decision{deny}` with `ev:I` and the rule citing the error pattern, and **no** `tool_execution` [trace_formats §6.6; RF-3]. Unexecuted trailing tool calls give an `unexecuted_tool_call` issue. Empty-messages logs with no outcome are recorded as `unit: outcome_only`, not dropped [sources/rope.md §4.4]. Model identity from the directory uses `rope.model_dir_identity`. **The `qwen3-235b/…/autodojo` log whose `pipeline_name` names gpt-4o-mini MUST NOT be filed as, or collide with, the gpt-4o-mini log of the same cell.** Its `source_key` is distinct and `identity_conflict` is flagged [sources/rope.md §8.4]. ROPE-corrected outcomes are `judgement` records with `origin: recomputed`, `by: source`, kept apart from `security_raw` (A6). Literal `<agent_model_name>` tokens and ChatML/forged `<think>` payload text survive byte-identically [sources/rope.md §4.4]. |
| AutoDojo-attack (via ROPE) | `agentdojo/profiles/test_autodojo_via_rope.py` | `autodojo_via_rope/` | Attributed once, to ROPE, and deduplicated by `source_key` + ownership [sources/autodojo.md §4]. The cache link is `I`, with its ambiguity set recorded [sources/autodojo.md §3.3]. |
| Mandate-AgentDojo-Eval | `agentdojo/profiles/test_mandate.py` | `mandate/` | The gate's decisions map to `decision` records per the profile. Injection-task-as-user-task cells (`…mandate_intent__banking__injection_task_0__none__none.json`) are typed. |
| Survey AgentDojo runs (part `agentdojo-runs`) | `agentdojo/profiles/test_survey.py` | `survey/` | Verified (the "pending verification" status of the first draft is stale, R-63). The model appears nowhere in the records and is path-derived. Python-repr tool outputs go through the marker normaliser registry (A6). The 11 gpt-oss runs with outcomes imposed by local patch carry `harness_default`. CC-BY attribution is present in `execution.artifacts[].origin`, whose primary origin is git `89c4db2c…` with the version DOIs as alternatives (R-62). |
| AgentDojo-Inspect | `agentdojo/profiles/test_agentdojo_inspect_dedup.py` | `agentdojo_inspect/` | Files byte-identical to AgentDojo runs share a `source_key`. A corpus build keeps one execution (part role `mirror`, owner `agentdojo-upstream`) and records the mirror as a second origin in `raw/origins.jsonl`, not as a second corpus (D4). |
| transcript/v1 (`adprov.transcript_v1`) | `adprov/test_reader.py`, `test_mapping.py` | golden 19 (incl. MIG-10); `synthetic/v1/` | Release vs converted variants [BASELINE §5.1]. The `"0"` stub with `timing_stubbed` is kept verbatim in `t.raw = {"start": "0", "end": "0"}` with `unk not_recorded` on `t.start` and `t.end` (C.7.3; R-30). `tool_call_id` must equal the paired call id, else `adprov.tool_call_id_mismatch`. `discarded_attempts` give `scope att<i>`. `meta.capture.passes[].environment` gives `state_change` digests. `reasoning` gives `I` by default [trace_formats §6.14]. Context membership is INFERRED (K.5.10(2)). `ext.lex` is present on every source-copied object and number. The documented null-vs-`""` rule for release text is pinned. No benchmark import (K.14). |
| capture/0.1 (`agentprov.capture/0.1`) | `agentdojo/test_capture_reader.py`, `test_capture_mapping.py` | `capture/` | Hash-chain verification. Every C.13 event type is mapped. `llm.request.input_at` gives context membership O; without it, D under a named alignment rule with an accounting check (R-16). Discarded and retried replies become `model_call{status, retry_of}`. Configured vs transmitted parameters. Aux-role calls become separate actors. Aborted passes. A truncated tail gives a sealed-incomplete execution with `capture_unsealed`/`incomplete_run` issues. The live `source_key` is `{sha256: <capture log>, loc: {}}`, and the live `ex` is the UUIDv7 id. |
| Inspect `.eval` (`inspect.eval`, variant `v2`; producer band `inspect_ai 0.3.247.dev69`) — **normative v0.1 importer** (AD-06) | `inspect/test_reader.py`, `test_mapping.py`, `test_resolution.py`, `test_judges.py` | `inspect/` (`restricted_use`) | Zip methods {0, 8, 93} accepted; members are derived objects (AD-12). `input_refs`, `events_data` and `attachment://` references resolve without fabrication; an unresolvable reference gives `unk` plus an `inspect.*` issue, never an invented value. Cached calls give `model_call.status: cached` (→ `apv:CacheRead`). Error calls give an invocation with no output. Compaction gives a `model_call` generating the summary message, else `ext` plus an issue. `ApprovalEvent` gives a `decision` (and `authorised_by` on the execution it approves). Judge spans give a `judge` actor and `judgement.generated_by`, with `inputs`; the score and its scale go to the SEM `outcome`. Sub-agent spans give a `subagent` scope with `spawned_by`. `BranchEvent` gives seal issue `inspect.branch_unsupported`, with no linearisation. `ToolEvent.truncated` gives a `truncation` sent transform or a `decision`. `StoreEvent`/`StateEvent` JSON patches give `state_change` with `patch` (→ `aprov.state_patch@1`). Model identity `ollama/<tag>` is in-record. The AgentHarm use clause propagates to `licences.restrictions`. Every mapping cites its D.9 rule id and class. Versions outside the band give register code `select.dialect_planned` (and `import` exits 5 for them), never a misparse by another reader. The importer landed with zero core changes, or the changes are listed (HON-09(3); K.6.4). |
| STAC JSON array (`stac.json_array`) — **planned** (A6); design-note fixture | `stac/test_design_note.py` | `stac/`; full file under `network` | v0.1 asserts only that `import` of the STAC file gives `select.dialect_planned` (exit 5) and that the C.16.3 example AER validates. When the importer lands, it MUST assert: `unit: scenario` under `stac.case_is_one_scenario@1`; the target agent `unk`, never an asserted `llm_agent`; element locators `{"p":"/<i>"}` whose byte spans re-parse equal; `arguments` kept as the raw string *and* a repeatedly decoded object with `encoding_depth` [sources/multiturn-agent-attack.md §7.2]; at most one call per assistant message, and id 139 has 3 text-only assistant messages [verify/multiturn-agent-attack.md §3.2]; tool outputs opaque strings; the scripted 32-hex call ids attributed to an `attacker` actor with `role: context_fabricator` and `ev:I`, never to an LLM (NE-13); the ASB id link flagged broken; **no `after` edge from array position** — the generation order inside a turn is call, then execution, then prompt-writing, so ordering edges are `I` from code with basis `causal`/`proto` [verify/multiturn-agent-attack.md §3.1]; `planner_history[k>0]` agent responses `unk withheld/not_recorded`; the final user turn `wasQuotedFrom` the planner output (R-56); licence policy `nc_partition`. |

### K.6.3 Ground-truth-driven mapper properties — `tests/property/test_mapper_props.py`

For each reader with a renderer in `tests/strategies/render_dialects.py`, the test works as follows:

1. Hypothesis draws an abstract **ground-truth execution** (`tests/strategies/truth.py`, K.10.1).
2. The truth is rendered into the dialect's raw bytes, losing exactly what the dialect cannot express. For example, TraceLogger keeps only the last pass and has no timestamps.
3. The rendered bytes are mapped.

The test then asserts:

- **M-1 (no invention).** Every non-`unk` field of the mapped AER is either present in the rendered raw bytes (via its `src` locator) or produced by a cited D or I rule.
- **M-2 (declared loss).** Every truth fact the dialect cannot express appears as `unk` with the expected reason, or as a seal issue.
- **M-3 (faithfulness).** Facts the dialect expresses are equal to truth: content, names, argument values, outcome values. For dialects with a byte-exact view, source member order and integral-float lexemes are recoverable from `ext.lex` (K.5.3(3)).
- **M-4 (specialised kinds first).** Truth events that a specialised kind represents never map to `activity` (Addendum B, AD-15).

### K.6.4 Future-framework conformance — `tests/adapters/foobench/test_future_framework.py` (D.12; DoD Q.3)

This test is the executable form of D.12 and of DoD Q.3, as amended by R-17 and Addendum B (AD-15). D.12 binds it:
the adapter, fixture, encodings and gap list below are D.12.1–D.12.3's (architect default AD-SW4). It runs the
self-authored adapter `foobench.jsonl` (`src/agentprov/adapters/foobench/`, namespace `foobench:` declared in
`execution.ns`, every `activity.type` and `artefact.type` declared in the catalogue's `types`) on the fixture
`tests/fixtures/foobench/` (the primary file and the hand-off's second file, K.4.3). Actor and local ids are D.12.2's;
PROV terms use EF's instance IRIs `x:<local id>` with `#` → `-` for parts (E.4.2).

1. **Protected set (D.12.3).** The test computes the diff of the commit that adds the `foobench` adapter. A file
   changed outside the list of D.12.1 (`src/agentprov/adapters/foobench/`, `tests/fixtures/foobench/`,
   `tests/adapters/foobench/`, the one registry entry and generated docs) is a failure: the protected set is all of
   `src/agentprov/` except `adapters/foobench/`, the registry entries and generated docs (R-17). The AER schema and
   validator, the provenance engine, the SEM engine, the corpus layer and the CLI are untouched. The fixture uses only
   `aer/0.1` values.
2. **Specialised kinds first (A-9; K.5.1(7)).** `llm_request`/`llm_response` map to `model_call` + message,
   `tool_start`/`tool_end`, the memory write, the hand-off, both approvals' executions and the text action to
   `tool_execution`, and `guard_verdict` and the approvals to `decision`. The AER holds exactly three `activity`
   records (`ac0`, `ac1`, `ac2`) and four `artefact` records (`af0`–`af3`), and `aer.activity.shadows_kind` never
   fires.
3. **Named PROV statements (D.12.2).** Each row MUST produce its named statements, asserted by rule id. Rows marked
   (phase 7) are asserted from phase 7 only (item 6).

   | FooBench event | AER encoding (D.12.2) | PROV statements asserted |
   |---|---|---|
   | `llm_request` + `llm_response` | `model_call mc<n>` (actor `agent`, `role: "agent"`, `input` = the referenced message ids, O) + output `message` with `generated_by: mc<n>` | `used(x:mc<n>, x:m<i>)` per input (`aprov.use_context@1`, O); `wasGeneratedBy(x:m, x:mc<n>)` (`aprov.gen_message@1`); `wasAssociatedWith(x:mc<n>, x:agent)` (`aprov.assoc_model_call@1`) |
   | `tool_start` + `tool_end` | `tool_execution te<n>` (`call` = the `tool_call` part) + `tool_result` message `generated_by: te<n>` | `used(x:te<n>, x:m<a>-<k>)` (`aprov.use_request@1`); `wasGeneratedBy(<result>, x:te<n>)` (`aprov.gen_result@1`); `wasAssociatedWith(x:te<n>, x:env)` (`aprov.assoc_tool@1`) |
   | `guard_verdict` | `decision dc<n>` (actor `def0`, verdict from the profile's closed table, subject = the `tool_call` part); a `deny` has **no** `tool_execution` | `wasAssociatedWith(x:dc<n>, x:def0)` and `used(x:dc<n>, x:m<a>-<k>)` (`aprov.decision@1`); no activity for the denied call (NE-12) |
   | **Planner step**: the planner's `llm_request`/`llm_response` in thread `thr0`, then `plan_update` | `model_call mc0` (actor `planner`, `kind: llm_agent`, `role: "planner"`; call `role: "auxiliary"`, scope `thr0`) generating message `p0`; `activity ac0 {type: "foobench:plan_step", actor: "harness", scope: "thr0", inputs: ["p0"]}`; `artefact af0 {type: "foobench:plan", media: "application/json", generated_by: "ac0"}` | `wasGeneratedBy(x:p0, x:mc0)` (`aprov.gen_message@1`); `wasAssociatedWith(x:mc0, x:planner)` (`aprov.assoc_model_call@1`); `x:ac0` typed `foobench:plan_step` (`aprov.g_act@1`); `used(x:ac0, x:p0)` (`aprov.g_use@1`); `wasGeneratedBy(x:af0, x:ac0)` (`aprov.g_gen@1`); `wasAssociatedWith(x:ac0, x:harness)` (`aprov.g_assoc@1`); `wasInformedBy(x:ac0, x:mc0)` (`aprov.comm@1`, Inference-6 closure, with premises) |
   | **Memory write**: `memory_write {key, value}` from the agent's `save_memory` tool call | `tool_execution te1` + `artefact af1 {type: "foobench:memory_item", content: {key, value}, generated_by: "te1"}`; when the fixture logs the store patch, also `state_change st0 {target: "agent_store", cause: "te1", patch}` | `wasGeneratedBy(x:af1, x:te1)` (`aprov.g_gen@1`); with the patch, the store-state chain of `aprov.state_patch@1` (a new store state generated by `x:te1`, revision-derived from the previous store state along `after` edges, or a fresh entity) |
   | **Memory read**: `memory_read {key}` by the harness before the next agent call (not a tool) | `activity ac1 {type: "foobench:memory_read", actor: "harness", scope: "att0", inputs: ["af1"]}` + `artefact af2 {type: "foobench:memory_snippet", generated_by: "ac1"}`; the injected snippet is message `m5` (gap, item 4) | `used(x:ac1, x:af1)` (`aprov.g_use@1`); `wasGeneratedBy(x:af2, x:ac1)` (`aprov.g_gen@1`); `wasAssociatedWith(x:ac1, x:harness)` (`aprov.g_assoc@1`); **`wasInformedBy(x:ac1, x:te1)`** (`aprov.comm@1`, Inference-6 closure) with both premises |
   | **Screenshot**: the environment captures the screen after a browser action (no tool call) | `activity ac2 {type: "foobench:observe", actor: "env", scope: "att0", inputs: []}` + `artefact af3 {type: "foobench:screenshot", content_ref: {"$blob": "sha256:…", …}, sha256 (= the blob digest), media: "image/png", generated_by: "ac2"}`; the observation message `m6` (part `blob`, same digest) is a gap (item 4) | `x:ac2` typed `foobench:observe` (`aprov.g_act@1`); `wasGeneratedBy(x:af3, x:ac2)` (`aprov.g_gen@1`); `wasAssociatedWith(x:ac2, x:env)` (`aprov.g_assoc@1`); a `sha256` that differs from the blob gives `aer.blob.digest` |
   | **Hand-off**: `handoff {to: "researcher", call_id}` from the agent's `transfer_to_researcher` tool call; the sub-agent's events are in the second file | `tool_execution te2` (`call` = the part); `scope sc0 {kind: "subagent", parent: "run", actor: "researcher", spawned_by: "te2"}` holding the sub-agent's records, mapped from the auxiliary file (raw artefact role `supporting`); the sub-agent's answer is the `tool_result` of `te2` | `wasStartedBy(x:sc0, -, x:te2)` (`aprov.spawn@1`); `wasAssociatedWith(x:mc<sub>, x:researcher)` (`aprov.assoc_model_call@1`); `used(x:te2, x:m<a>-<k>)` (`aprov.use_request@1`) |
   | **Human approval, approve** | `decision dc1 {actor: "user", subject: "m7#1", verdict: "allow"}`; `tool_execution te3 {call: "m7#1", authorised_by: "dc1"}` | `wasAssociatedWith(x:dc1, x:user)` and `used(x:dc1, x:m7-1)` (`aprov.decision@1`); **`wasStartedBy(x:te3, -, x:dc1)` (`aprov.authorise@1`)**, which replaces `aprov.start_tool@1` for `te3` (no `apv:AutoExecution` premise; EF E.1.4, AD-SW7) |
   | **Human approval, edit** | `decision dc2 {actor: "user", subject: "m9#1", verdict: "modify", original: "m9#1"}`; `tool_execution te4 {call: "m9#1", authorised_by: "dc2", args: <edited args as dispatched>}` | `wasAssociatedWith(x:dc2, x:user)` and `used(x:dc2, x:m9-1)` (`aprov.decision@1`); NE-18 suppresses `used(x:te4, x:m9-1)` (gap, item 4) |
   | **Text-parsed action**: `text_action {raw}` | `tool_execution te5 {requested_by: "agent", name, args (evf I, `foobench.text_action_parse@1`), status, t}` + result message `generated_by: "te5"` | `wasAssociatedWith(x:te5, x:env)` and `actedOnBehalfOf(x:env, x:agent, x:te5)` (`aprov.assoc_tool@1`, `requested_by` delegation); (phase 7) the role and integrity labels of `x:te5` in the assessment bundle, and **no** exposure or taint assessment for it: a request-less execution has no generating invocation (EF E.7.3; DECISIONS D-16), a named gap counted in the derivation report |

4. **Named, disclosed gaps (D.12.3(2)).** The test asserts each gap by name and that **no** PROV statement is emitted
   for it:
   - **NE-18 on the edited request:** no `used(x:te4, x:m9-1)`; the gap is recorded as a status until `aer/0.2` models
     the replacement (`decision.replacement`, `apv:ApproverModification`);
   - **the text action has no request part**, so there is no `used(x:te5, …)`;
   - **restore:** `checkpoint_restore` is kept verbatim in `ext.foobench.events[]` of the nearest preceding host record,
     with its own `src` and `after`, plus the issue `foobench.restore_unmodelled`; the events after it are mapped in
     source order, without linearising the restore into a state claim;
   - **telemetry:** the unknown event type is kept verbatim in `ext.foobench.events[]` of the nearest preceding host
     record as `{type, value, src: {"line": n}, after}`, plus the issue `foobench.unmapped_event_type` (info); it is
     never dropped, and there is no host-less `unmapped[]` list;
   - **observation messages `m5` and `m6`:** each carries `unk {"/generated_by": "not_recorded"}` and the issue
     `foobench.observation_unlinked`; no relation of `m5` to `af2` or of `m6` to `af3` is asserted, because an activity
     never generates a message in aer/0.1 (C.3.15; AD-SW5, AD-SW6).
5. **Validation (D.12.3(3)).** The AER validates (tier 2) and the PROV bundles validate (tier 4), with no core change.
6. **Phase split (AD-SW4; PQ phases 6 and 7).** In phase 6 (the freeze gate, before `sem/` exists) the test runs
   map → PROV → validate and asserts items 1–5 on the core and inference bundles; it asserts no SEM or assessment
   statement. Phase 7 extends it to map → SEM → PROV → validate: the SEM file validates, and the rows marked
   (phase 7) are asserted in the assessment bundle. The phase-7 assertions are added in phase 7; they are never
   present-and-skipped in phase 6 (K.1(3)).
7. **Inspect as the external case.** The same protected-set diff is computed for the commit range that adds
   `adapters/inspect/`. Any core change it needed is listed in the test report and in the paper (HON-09(3)).
8. **Claim wording.** The test report states the result in the A.6 wording: "tested on a self-authored toy format and
   on the Inspect importer (changes listed)".

---

## K.7 Golden regression

### K.7.1 Compatibility byte-identity — `tests/golden/test_compat_bytes.py`

This is migration gate **B** (J.3.3). For each golden pair R01–R08 and C01–C07, and for the four MIG-10 pairs (R-59):

1. Import the stored transcript with the v1 importer, giving raw → AER (with `ext.lex`).
2. Regenerate the transcript/v1 view **from the AER alone**: `views.transcript_v1.render(aer) -> dict`, then `serialise(dict) -> bytes`. The view reads nothing from raw: the test runs it with the raw store's open function patched to raise, and it MUST still succeed (AD-02).
3. Run `adprov-v2.3-compat` (the verbatim port `prov/compat/adprov_v2_3/`: the five files `build_prov`, `prov_emit`, `labeling`, `validate` and `conformance`, AST-equal, with only import statements changed and the `yaml` import routed to the `ingest.yamlsafe` shim recorded in `PORT_MANIFEST.json`; R-31), with default flags.
4. Serialise with `json.dumps(doc, indent=2).encode()`, with no trailing newline (`agentdojo_prov/generate.py:468`; spec/B_audit_evidence).
5. Assert that the bytes equal the stored graph bytes, whose sha256 is in `golden_index.json`.

This oracle is exact. The baseline builder reproduces **35,691/35,691** stored graphs byte-for-byte [obs-K1]. The full-corpus version of this test (`tests/full_corpus/test_baseline_corpora.py::test_compat_bytes_all`, `full_corpus`) is part of the release gate (K.20). The golden pairs run in PR CI (D7). A port-fidelity test asserts the AST equality of the five files against `579a908` and that `PORT_MANIFEST.json` lists every changed import. Compat outputs are flagged `apv:RegressionOracle` (K.5.8), and the CLI prints a notice whenever compat output is written or loaded (R-55).

### K.7.2 v1 round trip — `tests/golden/test_v1_round_trip.py`, `tests/unit/views/*`

These are migration gates **A1** and **A2** (J.3.2), plus gate **R1/R2** for converted pairs. Both directions run on
every golden transcript (including the MIG-10 pairs) and every `synthetic/v1/` transcript; the synthetic multi-pass,
capture-block and reasoning fields are inside both gates (R-32, MIG-5).

- **A1 (JCS value identity).** `rfc8785.dumps(render(aer)) == rfc8785.dumps(original)`. This equality is type-strict for booleans versus numbers, which closes baseline R2's `True == 1` gap [audit/corpus.md §3.3].
- **A2 (bytes).** `serialise(render(aer)) == stored bytes`. Every stored transcript is exactly `json.dumps(json.loads(bytes), indent=2)` [obs-K2], and the member order and integral-float lexemes that JCS loses are restored from `ext.lex` (K.5.3(3)). A2 is bytes, not JCS (R-32).
- **R1/R2 (`render_converted`).** For the converted pairs C01–C07 and the two MIG-10 converted pairs, the native June-2024 log is imported and `views.transcript_v1.render_converted(aer)` reproduces the stored converted transcript in bytes, and its compat graph in bytes. The `"0"` stub is the converter's field rule, re-applied inside `render_converted` (a native AER has no `t.raw`; erratum E8, J.4.3, D.7.4), so no declared difference table is needed. These run in PR CI as release gates (AD-07).
- **Field table.** `tests/unit/views/test_fields_table.py` asserts that `views/transcript_v1_fields.toml` is the single v1 ↔ AER field table, that C.15.3 and D.7.3 are generated from it, and that every view field maps to an AER pointer that exists in the schema (R-30).

No assertion in this section uses Python `==` on decoded values (K.1(9)).

> **Resolved (AD-02 / R-04):** the source lexical form lives in C's sparse `ext.lex {ord, flt}`, written only by
> `aer.canon.lex_hints()` for every source-copied object and number. The transcript/v1 view reads nothing from raw,
> so gate B exercises AER values and "regenerated from the AER alone through a deterministic view" is true. This
> section's raw re-read proposal and the rule `adprov.compat_args_from_raw@1` are rejected and deleted. The
> measurement that motivated the challenge stands: 12,485/16,052 released and 12,856/16,873 converted multi-key
> `args` objects are not in lexicographic order, 313 released and 1,681 converted `args` hold integral floats, and
> 8,037 released and 8,341 converted stored graphs depend on that form [obs-K3; spec/B_audit_evidence/README.txt].

### K.7.3 Golden expected outputs — `tests/golden/test_golden_outputs.py`

1. For every fixture in K.4.3, `fixtures/expected/<name>.aer.jsonl`, `.sem.jsonl`, `.prov.json` (agentprov-prov/0.1, bundled) and `.trig` are committed.
2. The test re-derives each one and compares:
   - AER, SEM and PROV-JSON as **bytes**;
   - TriG as **RDF isomorphism per named graph**, because TriG bytes are library behaviour [audit/validation.md §3.5].
3. **Change control (D9: "an intended change is a visible rule/spec version bump").**
   - `golden_index.json` records, per expected file, the adapter version, the rule-catalogue version and digest, the engine and spec versions, the `rfc8785` version and the interpreter version that produced it.
   - If the bytes differ while all recorded versions are unchanged, the test FAILS with "unversioned semantic change".
   - Regeneration is a maintenance script, `uv run python tools/regen_golden.py --reason "<text>"` (not part of the package; RESOLUTIONS §3.2). It refuses to run unless at least one recorded version differs from the index, and it writes the reason into the index.
4. The `.trig` expectations are test oracles produced by `derive --trig`; corpora store no TriG (AD-10 row 3).

### K.7.4 Full-corpus regression (`full_corpus`, local) — `tests/full_corpus/test_baseline_corpora.py`

The inputs are the frozen corpora under `$AGENTPROV_BASELINE_CORPUS` (`corpus-prov/`, 17,664 records; `corpus-og-agentdojo-runs-prov/`, 18,027) [BASELINE §4], verified first against `migration/baseline.lock.json` (gate G0). The local `runs/` copy is used only for G0's digest cross-check.

1. `test_g0_baseline`: the corpora and the lock agree (G0).
2. `test_compat_bytes_all`: 35,691/35,691 byte-identical, as in K.7.1 (B).
3. `test_v1_round_trip_all`: 35,691/35,691 A1 (JCS) and A2 (bytes), as in K.7.2.
4. `test_validation_all`: every AER, SEM and PROV passes strict validation with no skips (D).
5. `test_semdiff_all`: the gate-E report is generated from `prov/compat/semdiff-map.toml`, and every count reconciles (E).
6. `test_recompute_all`: re-map and re-derive give identical digests (D9).
7. `test_legacy_inference6_gap`: under Inference 6, the compat graphs entail communications that they do not assert [prov_semantics §0(4)]. The test pins **entailed-not-asserted = 26,645 (released) and 23,449 (converted)**, with asserted-not-entailed = 0 [`landscape/prov_semantics_evidence/inference6_scan.json`]. These equal the R6 taint-only `used` edges of the same graphs, 26,645 and 23,449 [`audit/provenance_evidence/evidence_stats.json`, `sink_taint_only_used_edges`]: each R6 taint-only `used(a_k, e_j)` edge entails exactly one `wasInformedBy(a_k, a_j)` that the builder (which asserts only the previous-turn R5 edges) does not assert, so the two readings count one set twice (99,278 − 72,633 = 26,645; 91,661 − 68,212 = 23,449; SWEEP_r2 EV-1). The pair is not contested and needs no re-derivation before it is pinned; both readings may be cited, each with its evidence file. This is a pinned *legacy* fact. The agentprov-prov/0.1 core bundles of the same executions assert **exactly** the Inference-6 closure over named activities, so they entail 0 unasserted communications (K.10, closure property).

`tests/full_corpus/test_upstream_pinned_import.py` imports the **18,241** June-2024 logs (including the 7 Mixtral logs, enumerated by path) from `$AGENTPROV_UPSTREAM_CACHE`. That cache is filled from the pinned blobs of `ethz-spylab/agentdojo@c274885610ef…:runs/` by the pinned fetch (`network`, with the user's consent, U-07), and every blob sha1 is verified [audit/legacy_replay.md §1(2)]. The test asserts:

- zero crashes, every file sealed (with or without issues), and the counts written to `docs/reports/` — the full-snapshot condition for `supported` (HON-10);
- the 207 empty-message logs are `unit: outcome_only` with issue `no_execution_observed`;
- every other log maps to AER that validates;
- the C01–C07 subset equals the committed expected AER;
- **gate R, full run (claim gate, AD-07).** Gate R runs over the 18,241 pinned blobs. For the logs behind the 18,027 converted records, `render_converted` reproduces those records in bytes (R1) and their compat graphs in bytes (R2). The logs with no converted counterpart (the 7 Mixtral logs and the outcome-only logs) are enumerated in the report. Only a pass with 0 mismatches licenses "the native re-import supersedes the converted tree" and the replacement of the converted corpus (J.4.5, HL H.4.2); otherwise the converted tree stays a `compat_oracle` part and the mismatch report is published. R3–R5 are reported, not gated.

`tests/full_corpus/test_inspect_survey.py` imports, derives and validates all 6 survey AgentHarm logs (1,056 samples) end to end (DoD Q.11a; R-07). It reads them from the pinned git origin `89c4db2c…` — `--input` on a survey clone outside the workspace, or the bare fetch cache under `$AGENTPROV_HOME/cache` — and verifies each blob id and sha256 first; only one of the six is a committed fixture (K.4.1(5), K.4.3; SWEEP_r2 EV-3). The Zenodo archive is not needed, so U-07 does not apply.

---

## K.8 Integration tests

### K.8.1 Live AgentDojo with a scripted fake LLM (`agentdojo`) — `backends/agentdojo/tests/*`

These tests live in the backend project `backends/agentdojo/` and run on its Python 3.12 environment (A1, AD-01);
they never import `agentprov`. Their core-side half — mapping the produced evidence to AER and deriving SEM and
PROV — runs in core on the produced artefacts (K.8.5).

The harness is the baseline's scripted-client pattern (`tests/test_attempts.py:1-7, 40-57`; `tests/test_reasoning.py:38-47`). One change is normative. The baseline replaced `openai.OpenAI` wholesale (`monkeypatch.setattr(openai, "OpenAI", lambda **kw: holder)`). AgentPROV MUST instead inject `agentprov_backend.testing.ScriptedTransport` as the **HTTP transport** under the recording transport of the real SDK client that the stock LLM element uses (`native`, the default; AD-09). The recorded `capture/0.1` wire request and response evidence is then genuine output of the unmodified element [audit/capture.md §9.2, §9.5]. `gateway_compat` scenarios run only where a row says so.

Real suite tasks run through `run_task_with_pipeline` of `agentdojo==0.1.35`. No network and no keys are used. The tests MUST cover the following; the assertions marked (core) are checked by K.8.5:

| Scenario | Assertion |
|---|---|
| One benign cell per v1.2.2 suite (workspace, banking, travel, slack); the baseline used banking `user_task_1` (`tests/test_attempts.py:50-57`) | capture/0.1 written and hash chain valid; every `llm.request` carries `input_at` and `n_messages`; (core) mapped AER validates; SEM and PROV derive; accounting `consistent`; context membership OBSERVED |
| An injection cell with `important_instructions` and an explicit, recorded model display name | No mutation of `agentdojo.models.MODEL_NAMES` (asserted by snapshotting the dict) [audit/capture.md §1(7), §10]; the display name is declared as `attack.model_display_name` instrumentation of kind `attack_parameter` (D.10.7); the payload is recorded as a `fixture` of kind `injection_payload` |
| A DoS-family attack | (core) Outcome origin `harness_rule` with `agentdojo.dos_security_rule`; polarity in the SEM `outcome` |
| Empty final reply, giving AgentDojo's 3-pass silent re-run | All passes kept as `scope att<i>`; logs and passback reset per pass; cross-pass reuse of tool-call ids handled (port of `test_attempts.py:61`) |
| Malformed tool-call JSON, upstream 5xx, deterministic 5xx, 4xx, no `choices` | Retries recorded as discarded `model_call`s with reasons and `retry_of`; 4xx not retried; never accepted as the reply; per-execution resample and retry counts recorded (ports of `test_attempts.py:132-145, 277-289, 335-365, 447-466`; R-25) |
| Refusal in every pass; reasoning content; provider without usage | Ports of `test_attempts.py:240-262, 482-498`; `test_reasoning.py` |
| `max_iters` cut with pending tool calls | (core) `unexecuted_tool_call` issues (48 such calls in the release) [audit/capture.md §7.6] |
| Tool error (`ValueError`, `ValidationError`) and an invalid tool name | Rendered *model-visible* text (the error string) recorded separately from `content` [audit/capture.md §8 D7]; (core) the invalid name maps to `status: invalid` |
| `AbortAgentError` pass | `pass.end` recorded as aborted [audit/capture.md §8 D11] |
| Gate negative cases (simulated missed pass, lossy counter) | (core) Execution **sealed with issues and kept** (`accounting_inconsistent` or `accounting_unverifiable`); attempt index recorded; nothing deleted (D5; replaces the baseline's discard-and-retry [audit/capture.md §1(5)]). The runner reads the seal verdict to decide a re-attempt (R-13) |
| Resume | Resume from sealed raw evidence only; a truncated or foreign stored capture is not trusted (ports of `test_attempts.py:310-430`) |
| Instrumentation declaration, `native` default | Header `instrumentation[]` items in the merged shape (K.5.1(4)); "temperature not transmitted" (0.1.35) declared; **no** `developer→system` rewrite and no resampling, because the element is stock (D5, AD-09) |
| Instrumentation declaration, `gateway_compat` opt-in | The `developer→system` rewrite and up to 8 resamples are declared as `request_modifying`/`harness_policy` items, so NC-LIVE-01 applies to the session |
| Defended pipeline (`tool_filter`) | Refused with a typed error in v0.1 (baseline behaviour, `test_attempts.py:517`; K.22 Q3 closed). Auxiliary roles are accounted in AER only for imports |
| Payload fidelity (SEC-14) | Payload bytes identical in the wire request, the capture log, the native log and (core) the AER; no subprocess; nothing written outside the staging directory |
| Provider `anthropic` (D-656; `backends/agentdojo/tests/test_live_capture_anthropic.py`) | The port of `AnthropicLLM` on a real `AsyncAnthropic` client over `ScriptedTransport` in Messages mode (synthetic SSE and JSON replies): one benign cell per suite with `input_at` verified against the stock rendering; thinking blocks sent back with their signature; tool results merged into one turn; 429/500/529 retried and recorded, 400 not retried; a 2xx stream error is `error`; refusal; `max_tokens` with a partial tool call (the stock element drops it); invalid tool names filtered; payload fidelity; the key only in `x-api-key`; the port equal to the stock source by AST except the `temperature` keyword |

### K.8.2 Executor mirror (`agentdojo`) — `backends/agentdojo/tests/test_executor_mirror.py`

See K.9.4.

### K.8.3 Offline import, end to end — `tests/integration/test_offline_import_e2e.py` (core, no benchmark import)

The input is a mixed mini-corpus built from fixture groups: AgentDojo `v0.k11` and `v1.k14`, transcript/v1, ROPE, AgentDyn variant A, survey AgentDojo runs, AgentDojo-Inspect, and Inspect `.eval` (in its own corpus, item 6). The STAC slices are included to check the planned path. The pipeline under test is: CLI `import` → raw store → `expand` → AER → SEM → PROV → `validate --strict` → `package` → `verify` (all three levels: `checksums`, `chain`, `rederive`) → `recompute --dry-run`.

The test asserts:

1. Every execution validates. The empty-messages logs are present as `unit: outcome_only` with issue `no_execution_observed`, and `register.jsonl` records their logged outcomes [audit/legacy_replay.md §14(5)]. The STAC file yields the register code `select.dialect_planned`.
2. AgentDojo-Inspect mirrors are deduplicated by `source_key`, with one owner per key (D4).
3. The manifest digest chain verifies. `checksums.sha256` covers every file including `corpus.json`, and the corpus root digest is recorded. The tree contains the required AD-20 files (K.5.8).
4. `recompute --dry-run` reports 0 changed **and** validates (fixes baseline R3).
5. Re-running `import` is idempotent: no new executions and byte-identical outputs.
6. **Licence classes (AD-20).** Packaging the AgentHarm (`restricted_use`) part together with permissive parts is refused (exit 4: mixed licence classes). Built as the separate corpus `ast-survey-agentharm`, it packages, and its use clause appears in `licences.restrictions` and verbatim in `DATASHEET.md`, which renders every `licences.raw[].basis` verbatim (R-14).
7. `agentdojo` is not importable in the core environment, and is not in `sys.modules` at any point. A fresh interpreter is used, as in K.14.
8. `agentprov stats` on the sealed corpus gives the counts the test computes independently (K.5.11).

### K.8.4 AutoDojo worker in an isolated environment (`autodojo`) — `backends/autodojo/tests/test_worker_fake_client.py`

AutoDojo has the same distribution name and version as PyPI agentdojo (`agentdojo` 0.1.35), so it cannot share an environment with it (D5) [sources/autodojo.md §7]. Under A1 it is a backend project of its own; core never installs it.

**Setup (session scope; R-39, R-49).**

1. The environment is built by `agentprov backends build autodojo`: `uv sync --locked --no-config` on `backends/autodojo` with `UV_PROJECT_ENVIRONMENT=$AGENTPROV_HOME/envs/autodojo-<commit8>/`, outside the repository. The fork is a pinned git dependency in the lock (`aa458794b7eb7f082e94daeac4c0f55bfc0c90cc`), resolved by uv into its cache. There is no upstream working tree and no editable fork.
2. The environment holds `agentprov-capture` and `agentprov-backend` (path dependencies) and never `agentprov`.
3. The fixture refuses to run unless the fork's identity read from PEP 610 `direct_url.json` equals the profile's pinned commit.

**Execution.**

- The worker is launched as `<env>/bin/python -I -B -m agentprov_backend.worker` (protocol `agentprov-backend/0.1`), with no `uv` at run time, `AGENTPROV_BLOCK_NETWORK=1`, `HOME=$AGENTPROV_HOME/t2home/<session>`, the staging directory as working directory, and the explicit environment allowlist of G.6.3 (no `UV_*` wildcard, no real `HOME`). Its entry installs `agentprov_backend.testing.netguard` and a `ScriptedTransport` loaded from a script file passed by path.
- It runs one banking task through AutoDojo's pipeline, with transport-level recording around the fork's unmodified LLM element (AD-09; D.11.4), and writes capture/0.1 into staging. The parent (core) ingests staging like `--input`, then maps, validates and derives.

**Assertions.**

1. The execution header records the AutoDojo **commit** as the distribution identity, not just the version string `agentdojo 0.1.35` (D9) [sources/autodojo.md §4]. T0 computed the lock, RECORD and guarded-source digests before spawn and cross-checked them against `hello_ok` and the capture `identity` event; a mismatch aborts the session.
2. The fork's semantic deltas are declared as instrumentation facts: temperature 0.0 transmitted, the JSON-retry path, and `security=False` on error-skipped tasks [sources/autodojo.md §4, §7].
3. `max_input_tokens` is recorded and asserted `None` for the stock-equivalent loop [verify/autodojo.md l.140].
4. No socket was opened. AutoDojo's `suite_gen_utils.py` calls `nltk.download("punkt_tab")` at import [sources/autodojo.md §7]. The worker MUST NOT import that module, and the guard turns any attempt into a test failure.
5. Core has no in-process live path: `agentprov run autodojo` without a built environment exits 3 (environment), and with an environment whose identity does not match the pin exits 3; it never imports `agentdojo` into the core process (`tests/integration/test_run_spawn.py`).
6. A forced kill of the worker leaves a session sealed `aborted` with `appended_by: parent` (PQ phase 9 exit gate).
7. **Hostile T2 worker (R-39; SEC-14/SEC-25).** A scripted worker that tries to read `$HOME`, write outside staging, report a `../x` path, or report a symlinked artefact is contained: the reads find the redirected T2 home, nothing outside staging changes (`fs_guard`), and staging ingestion rejects the reported path or link (no-follow, `S_ISREG`, `st_nlink == 1`).

### K.8.5 Core side of live runs — `tests/integration/test_live_mapping.py`, `tests/differential/test_live_vs_native.py` (`live_artefacts`)

Core consumes live evidence only as files (K.1(10)). In PR CI without the `live-map` job, these tests run on the
frozen sessions under `tests/fixtures/capture/`; with it, they also run on the sessions the `backend-agentdojo` job just
produced. For each K.8.1 scenario they assert the rows marked (core): the AER validates, SEM and PROV derive,
accounting has the expected verdict, context membership is OBSERVED where `input_at` is recorded, and the K.9.1
differential holds.

---

## K.9 Differential tests

### K.9.1 Live capture vs native log of the same execution (`live_artefacts`) — `tests/differential/test_live_vs_native.py`

D3 requires the live backend to write both `capture/0.1` and the native TraceLogger JSON. In the baseline, generation installed no `TraceLogger` [audit/capture.md §6], so the backend MUST run each cell inside a TraceLogger context. In 0.1.35 the native file is the 14-key dialect (`v1.k14`), because the version fields were added 2025-03-03 [verify/agentdojo.md]. The backend project produces the pairs (K.8.1); this core test maps and compares them (K.8.5).

For each K.8.1 scenario, map both artefacts and compare `common_projection(aer_capture)` with `common_projection(aer_native)` as JCS bytes (K.1(9)):

1. On the last pass, the following are equal: message roles and parts (text, tool_call name, args, tool_result text), tool executions and their statuses where the native log expresses them, judgements and fixtures. TraceLogger keeps only the last pass, because `self.messages = messages` precedes `save()` [verify/agentdojo.md].
2. **No contradiction.** Every `O` fact in native AER equals the corresponding capture fact or is `unk` there.
3. **Capture is at least as informative.** Every field that is `unk` in capture AER is `unk` in native AER, and the converse does not hold. Expected native-only unknowns are wire requests, earlier passes, per-call time and served model.
4. Times differ by design: native `evaluation_timestamp` is naive local time, capture is UTC plus monotonic. Times are excluded from the projection and asserted separately to be consistent within the declared clock resolution. This consistency is a *flag* check, never a relation.

### K.9.2 Old vs new package

| Test | Gate | Method |
|---|---|---|
| `test_old_vs_new_package.py::test_frozen_outputs` | core | The new compat port against the **stored** baseline outputs: K.7.1 on goldens. The new AgentDojo native importer → `render_converted` against the stored *converted* transcripts C01–C07 and the MIG-10 converted pairs, **in bytes** (R1/R2, AD-07). No declared difference table is needed: the `"0"` stub is re-applied inside `render_converted` (erratum E8; J.4.3). |
| `test_old_vs_new_package.py::test_live_old_builder` | `old_package` | `$AGENTPROV_BASELINE_PYTHON` points at a separate venv with `agentdojo-prov` @ `579a908` installed from a hash-locked export of `baseline/pip_freeze.txt` with `--require-hashes`, or from a mirrored wheel (R-49) [BASELINE §1.1]. For every non-AgentDojo-PROV fixture (ROPE, AgentDyn, DRIFT, Mandate, survey) and for Hypothesis-generated v1 views (`thorough` profile), it runs the old `build_prov` in a subprocess and the ported compat module in-process, and asserts byte equality. This shows that the port is verbatim beyond the corpus distribution (R-31: this test stays). The legacy latent defects (dropped `Z` timestamps, IRI-illegal ids, split-batch `wasInformedBy`) [audit/provenance.md §1(8)] are *expected to be reproduced* by compat, and that is asserted. |
| `backends/agentdojo/tests/test_c6_old_vs_new.py` (gate C6, split per AD-07) | `agentdojo` + `old_package` | The same scripted scenario runs through the baseline's live capture (old package) and the new backend. **(a)** Scenarios with no D5 deviation: the v1-view bytes are equal after the time mask. **(b)** Deviation scenarios: `common_projection` equality, plus exactly one registered XD entry per deviation that cites its B.9 id (F-02, F-05, F-13) and D.7.3. Gate C1 is an optional job, run by manual dispatch only (K.19.1); C4 (replay) is deferred (AD-10 row 2). |

### K.9.3 JSON Schema vs in-code validator — `tests/differential/test_schema_vs_validator.py`

The three published schemas — `schemas/aer-0.1.schema.json`, `capture-0.1` and `corpus-0.1` (AD-10 row 13) — are each checked with `jsonschema` (`dev` extra), and **with format assertion enabled**, against their in-code validators. The `corpus-0.1` check covers the schema's `$defs` as well as `corpus.json`: the execution-index row, the register entry, the derivation document and the `raw/members.jsonl` row (HL H.2.1, H.3, H.6; architect default AD-SW9), each validated against its `$def` and against the in-code validator of that file. The baseline schema test passed `"0"` date-times only because `format` was not asserted [audit/legacy_replay.md §3.6 D4]. A further check (EXT-01, R-02) asserts that every AER pointer named in an EF rule's "Required AER evidence" column, including those of G-ACT/G-USE/G-GEN/G-ASSOC, exists in the AER schema.

Every validator error code is classified as either `schema_expressible` or `schema_inexpressible`. The inexpressible group is backward references, kind-typed references, locators, the seal, JCS form, catalogue membership, `after` acyclicity and accounting. For every record produced by `strategies.aer` and by `strategies.mutations`:

- (a) schema-invalid ⇒ validator-invalid;
- (b) validator-invalid with a `schema_expressible` code ⇒ schema-invalid;
- (c) every code is classified, and a new code without a classification fails the test.

The in-code validator stays authoritative (D2). This test only guarantees that consumers who use the published schema are not misled.

### K.9.4 Stock `ToolsExecutor` vs the capture mirror (`agentdojo`) — `backends/agentdojo/tests/test_executor_mirror.py`

The same inputs (valid call, empty name, invalid tool, argument-validation error, exception, YAML-formatted output) go through stock `agentdojo.agent_pipeline.ToolsExecutor` and through the mirror in `agentprov_backend.executor_mirror`. The resulting message lists and environment dumps MUST be equal (compared as JCS bytes). A version assertion pins `agentdojo==0.1.35` [audit/capture.md §4.2.2]. AutoDojo's `ToolsExecutor` class is AST-identical to PyPI 0.1.35 [verify/autodojo.md item 18], so the same test runs in the AutoDojo backend project (`backends/autodojo/tests/test_executor_mirror.py`, `autodojo`).

### K.9.5 PROV library parity — `tests/differential/test_prov_library_parity.py`

AgentPROV's deterministic PROV-JSON serialiser is checked against the `prov` 3.2.2 parse and re-serialise for every expected PROV document: the parse is model-equal and the TriG is isomorphic per graph. An optional ProvToolbox cross-check MAY be added under `network`/`slow`; its behaviour was not verified [prov_semantics §3.19; audit/validation.md §11].

---

## K.10 Property-based tests (Hypothesis)

### K.10.1 Strategies — `tests/strategies/`

| Strategy | Produces |
|---|---|
| `json_values.ijson(max_depth=4, hazards=False)` | I-JSON values: integers within ±2^53, finite floats, strings without lone surrogates. With `hazards=True` it adds big integers, integral floats, lone surrogates, NaN-like literals at byte level, and deep nesting. |
| `truth.executions(passes=st.integers(1,3), max_model_calls=6, max_tools_per_call=4, aux_roles=st.booleans(), decisions=…, fixtures=…, id_quirks=st.sampled_from(["unique","null","empty","duplicate","reused_across_passes"]))` | An abstract ground-truth execution: model calls with exact contexts, tool calls and results, aux calls, defence decisions, environment digests, judgements, and times on a declared clock. It is the oracle for K.6.3. |
| `aer.executions(mode=st.sampled_from(["import","live"]), unit=st.sampled_from(["agent_execution","outcome_only","scenario"]), with_unknowns=True, with_after=True, generic_kinds=True)` | A valid AER record stream over all 13 kinds (via the reference renderer in the strategy), with its raw artefact bytes and the expected facts. With `generic_kinds`, it adds `activity` records with typed inputs and `artefact` records generated by activities, model calls or tool executions |
| `mutations.invalidating()` | Pairs (mutated stream, expected code): `drop_record`; `swap_to_forward_ref`; `add_forward_ref_field` (`output`, `result`, `replacement`, `spawns`); `corrupt_seal`; `inject_sentinel`; `undeclared_ext_ns`; `unknown_rule_id`; `cycle_after`; `dangling_locator`; `non_jcs_line`; `duplicate_id`; `wrong_kind_ref`; `activity_input_is_activity`; `artefact_content_and_ref`; `evf_without_rule`; `bad_unk_reason`; `value_and_unk`; `missing_unit`; `other_without_subtype`; `as_sent_of_present`; `delta_form_input`; `missing_lex_hint` (byte-exact-view dialects) |
| `mutations.semantics_preserving()` | Re-serialisation permutations that keep references valid; whitespace-only changes to raw JSON (for readers); provider-id renaming |
| `raw_bytes.dialect_seeds()` | Seed fixtures per dialect, for fuzzing (K.11) |

### K.10.2 Invariants (each is a test function tagged with its id)

**Identifiers** — `test_ids_props.py`

- **ID-1:** `agentprov.aer.ids.import_execution_id` is a pure function, matches the KAT rule (K.5.2) and is 26 characters of `[a-z2-7]` after `ex_`.
- **ID-2:** it is invariant under a change of adapter version, and varies with the mapping id (adapter id and profile id) and with the locator key, but not with a byte span added beside `p` or `line`.
- **ID-3:** local ids are invariant under any renaming, nulling, emptying or duplication of provider call ids. Only the `provider_call_id` fields and the link evidence class change (D → I).
- **ID-4:** no local id contains a provider id or a content-hash substring.
- **ID-5:** instance IRIs of distinct executions are disjoint: merging two PROV-O graphs shares no instance IRI (fixes V13). Within an execution, `L` (`#` → `-`) is injective over the local-id grammar.

**References and serialisation** — `test_refs_props.py`, `test_jcs_props.py`

- **REF-1:** every generated valid stream validates.
- **REF-2:** every `invalidating()` mutation yields at least its expected code, and never an exception.
- **REF-3:** the JCS bytes of `canonical_order(permute(records))` equal those of `records` for any permutation. The canonical order is a function of the record set.
- **REF-4:** every typed reference points backward; no generated stream needs a forward reference to express any of the 13 kinds.
- **JCS-1:** `rfc8785.dumps(json.loads(rfc8785.dumps(x))) == rfc8785.dumps(x)` for I-JSON `x`.
- **JCS-2:** each AER line round-trips byte-identically.
- **JCS-3:** any single-byte change before the seal is detected.

**Derivation determinism** — `test_determinism_props.py`

- **DET-1:** `map`, `semantics` and `provenance` are pure. The same inputs give identical bytes on two calls, also after `importlib.reload` of the engine modules.
- **DET-2:** outputs do not depend on dict insertion order of inputs that the specification calls unordered, for example the `injections` map. The order of `injections` is shuffled; marker results and every output byte are unchanged (the baseline already iterates over values only, `agentdojo_prov/build_prov.py:348`).
- **DET-3:** PROV-JSON key order is deterministic, and TriG is isomorphic across runs.

**Never-emit rules (D7; EF E.2 NE-1…NE-20)** — `test_never_emit_props.py`

These run over the derived PROV of every generated execution, including executions with generic kinds. Each property
carries EF's never-emit id, which replaces the first draft's K-local numbering (R-24).

- **NE-1:** every `used` and `wasInformedBy` carries an `apv:rule` from the allowed edge-rule set, which includes G-USE [prov_semantics §8.2]. No rule in the catalogue derives an edge from `after`, `t` or file order.
- **NE-2:** a `ToolExecution` activity `used` only its request entity (`aprov.use_request@1`) and the state it read (`aprov.env_call@1`). A generic activity `used` only its declared `inputs` (G-USE).
- **NE-3, NE-11:** the core bundle has no `wasDerivedFrom` inferred from context membership or co-occurrence, no statement of class I, and no statement with an INFERRED premise.
- **NE-4:** there is no `wasAttributedTo` of a composite output (a whole tool result or message) to a channel agent.
- **NE-5:** there is no `wasInfluencedBy` anywhere.
- **NE-6:** every PROV time value equals an AER `t` value that has `ev:O` and a `src` locator. There is no `end := start`, no run-start fallback, no time taken from content (DRIFT case), and no relation time.
- **NE-7 and the closure (AD-19(c)).** The bundles are **Inference-6-closed and Inference-6-exact over named activities**: every communication entailed by the `used` + `wasGeneratedBy` statements of the core ∪ the method-set bundles — the generic G-USE and G-GEN statements included — is asserted with `apv:premise`, at the class E.1.6 assigns (ceiling D; the best witness) and in the bundle that class implies; every asserted one is entailed; nothing composite or transitive is asserted. The reference implementation is the stdlib scan `landscape/prov_semantics_evidence/inference6_scan.py`, ported as `agentprov.testing.inference6`.
- **NE-9:** no negative fact is derived from absence ("did not use", "concurrent").
- **NE-10:** integrity, role, exposure, taint, payload containment, marker and authorship never appear as PROV relations, only in the assessment bundle.
- **NE-12:** no statement rests on a required AER field in `unk`, and no activity is emitted for a call that was not dispatched, was denied or has unknown status; a G-USE input whose link is `unk` gives no `used`.
- **NE-13:** scripted or synthetic turns are never attributed to an LLM agent or a model invocation.
- **NE-14:** no activity stands for two occurrences.
- **NE-15:** no instance IRI falls in the vocabulary namespace, and no provider id or content hash is node identity.
- **NE-16:** neither the converse of Inference 13 nor any other non-PROV inference is applied.
- **NE-17 (as reworded under AD-11):** SEM-dependent interpretations (payload containment, attack success interpreted for security, label census) are not in the core; configuration ground truth is (K.5.10(4)).
- **NE-18:** no `used(te, p)` when a `modify` decision on `p` exists.
- **NE-19:** no `used` whose object is an activity, and no `mentionOf` of an activity.
- **NE-20:** no `hadPrimarySource` unless the artefact's `prov_primary` ∈ {`native`, `byte_derived`}.
- **NE-8** (usage of a member inferred from usage of a collection) is vacuous in v0.1, because collection mode is deferred; the property is kept and asserts that no `members`-mode output contains such a statement.

**Evidence propagation** — `test_evidence_props.py`

- **EV-1:** every D or I assertion cites at least one catalogued rule.
- **EV-2 (monotonicity).** With the order O > D > I, each statement's class is at most the weakest premise class and at most the rule's ceiling. A non-observation rule yields at most D [prov_semantics §7.2; trace_formats §6.2].
- **EV-3:** the core bundle holds only O and D statements. I statements appear only in inference bundles. Non-PROV claims appear only in the assessment bundle.
- **EV-4 (propagation).** Overriding any single premise field to I through `evf` demotes every transitive dependant to I and removes it from the core bundle. The class of no other statement changes.
- **EV-5:** every `apv:sourcePointer` resolves, and the resolved field's class is not weaker than the statement's.
- **EV-6:** no sentinel appears. Unknowns appear only as `unk` (AER) or as status attributes or `apv:Gap` (PROV).
- **EV-7 (existence, R-22):** a statement's class is at most the existence class (`ev`) of every endpoint record.
- **EV-8 (generic usage):** each G-USE statement has exactly the class of its input link's `evf` (or the record default), and each G-GEN statement at most the class of `/generated_by`.
- **EV-9 (static model, AD-05):** changing only a profile's or catalogue's assumption status, with the AER bytes unchanged, changes no derived byte.

**Order-unknown semantics** — `test_order_props.py`

- **ORD-1:** `after` is acyclic. Generated streams with cycles are rejected.
- **ORD-2 (order is never causality).** The set of PROV relations, excluding order *attributes*, is invariant under three changes: (a) deleting every `after` edge; (b) applying any monotone or non-monotone perturbation to every `t` value; (c) any semantics-preserving re-serialisation. Only `apv:` order attributes and time attributes may change.
- **ORD-3:** for two records with no `after` path, no output statement asserts precedence or concurrency between them.
- **ORD-4:** time-consistency findings are flags and never change validity (D8).

**Validator totality** — `test_validator_props.py`

- **VAL-1:** for arbitrary JSON (`ijson(hazards=True)`) the validators return a result and never raise. The baseline raised `TypeError` on scalar sections [audit/validation.md §7 V1].
- **VAL-2:** errors are reported per record and per activity. Compensating errors never cancel [audit/validation.md §8(3)].

---

## K.11 Fuzz tests

### K.11.1 Hypothesis-driven reader fuzzing — `tests/fuzz/test_reader_fuzz.py`, `test_jsonl_fuzz.py`, `test_locator_fuzz.py`, `test_capture_log_fuzz.py`

Inputs:

- `st.binary(max_size=64 KiB)`;
- structure-aware mutations of the seed fixtures: delete or duplicate a key, change a type, deepen nesting, insert unicode or controls, truncate at random offsets, splice two seeds;
- JSONL-specific mutations: split or merge lines, truncate the tail, CRLF, BOM, NUL, oversize lines;
- locator strings: random JSON Pointers with `~` escapes, `..`, absolute paths, and huge or negative byte ranges.

Every reader (including the Inspect `.eval` reader and its reference resolution), the `expand` stage, the dialect detector, the capture-log verifier and the locator resolver MUST satisfy:

- **F-1:** the outcome is success or an exception that is a subclass of `agentprov.errors.IngestError` (adapter layer: `IngestSafetyError`) carrying a G.3.9 code. Any other exception fails. Exception arguments that echo input are escaped (`escape_untrusted`).
- **F-2:** a per-input time budget (Hypothesis `deadline`) and a memory budget (`resource.setrlimit` in a subprocess for the `thorough` profile).
- **F-3:** nothing is written outside `tmp_path` (`fs_guard`).
- **F-4:** success implies that the mapped AER passes the AER validator. Readers either reject an input or produce valid AER.
- **F-5:** determinism. The same bytes give the same outcome and the same code.

PR CI uses the `ci` profile, and the manually dispatched `thorough` job uses `thorough` (`slow`).

### K.11.2 Malformed JSONL corpus

`fixtures/synthetic/jsonl/` holds a fixed regression set. It is grown from every fuzz failure, minimised by Hypothesis and committed with the expected code.

### K.11.3 Coverage-guided fuzzing (atheris) — deferred

Deferred to v0.2 (AD-10 row 18; K.22 Q5). The intended shape is kept for then: `fuzz_atheris/fuzz_<reader>.py`
harnesses outside `tests/`, run locally or in a manual job, seeded by the fixture files, with crashes converted into
`fixtures/synthetic/` regression cases. Atheris is not locked and not required; its availability on CPython 3.14 and
macOS arm64 was not verified. In v0.1, the Hypothesis fuzzing of K.11.1 is the fuzz layer.

---

## K.12 Security tests

All of these run in PR CI (core) unless marked otherwise. They are parametrised over `IngestLimits()` (K.5.6) and
probe `limit − 1`, `limit` and `limit + 1`. K.12 implements G.10's catalogue SEC-01…SEC-26, including the additions
of RESOLUTIONS §4.6 edit 18 (R-39, R-40, R-42, R-43, R-44). Test function names start with `test_sec<NN>_`, so every
SEC id is traceable (K.16). The map is:

| K subsection | SEC ids |
|---|---|
| K.12.1 Archives | SEC-05 (nested), SEC-07, SEC-08, SEC-09 |
| K.12.2 JSON limits and numbers | SEC-01, SEC-02, SEC-04 |
| K.12.3 Encoding; JSONL framing | SEC-01, SEC-03 |
| K.12.4 Traversal and metadata poisoning | SEC-08, SEC-21 |
| K.12.5 Tampering and reordering | SEC-15, SEC-16, SEC-17, SEC-18, SEC-19 |
| K.12.6 Prompt injection and dangerous sinks | SEC-05 (YAML), SEC-11, SEC-12, SEC-14 |
| K.12.7 Spoofed identity | SEC-20 |
| K.12.8 Decompression | SEC-06 |
| K.12.9 Links and special files | SEC-10 |
| K.12.10 Worker isolation | SEC-22 |
| K.12.11 Secrets | SEC-25 |
| K.12.12 Interpreter guard | SEC-26 |
| K.12.13 Agent channels | SEC-12, SEC-13 |
| K.12.14 Fetch hardening and references | SEC-24 |
| K.12.15 Downloaded deposits | SEC-15 |
| K.12.16 Live tier T2 | SEC-14, SEC-25 |
| K.14 Supply chain | SEC-23 |

### K.12.1 Archives — `tests/security/test_archives.py`, `test_names.py`

Inputs are zip archives (`.eval` and other deposits). Tar is refused (`ingest.archive.format`), and the cases of
obs-G1 are kept for a future tar enablement (SEC-07). Archives are **never extracted** (A2): members are streamed,
metadata-validated and stored by sha256 as derived objects of the `expand` stage (AD-12). Member names are labels,
never paths. Each member is accepted or rejected with a code, and `fs_guard` shows that nothing was created outside
the raw store's staging and `tmp_path`.

| Hazard | Code |
|---|---|
| A member name with `../`, an absolute path, a drive letter or backslashes | `ingest.archive.traversal`; the label is never opened as a path |
| Symlink members (zip external attributes) and hardlinks | `ingest.archive.link` |
| Duplicate member names; NFC/NFD or case collisions (all colliding members rejected); names with controls, ANSI or bidi; reserved names; trailing dots; over-long names, checked before NFC (SEC-09) | `ingest.archive.duplicate` / `ingest.name.invalid` |
| Member count over the limit; 200,000 entries rejected before `ZipFile()` by the EOCD/ZIP64 size check; lying EOCD counts; a prefix; trailing data recorded | `ingest.archive.members` / `ingest.archive.cd` / `ingest.archive.prefix` / `ingest.archive.trailing` |
| Total uncompressed size over the limit; compression ratio over the limit (zip bomb, including nested archives); full and partial member overlap | `ingest.archive.size` / `ingest.archive.ratio` / `ingest.archive.overlap` |
| Nested archive depth over `max_archive_depth` (a depth-3 nesting); an undeclared nested archive is stored but not opened (SEC-05) | `ingest.archive.depth` |
| Encrypted members; a method outside {0, 8, 93}; a CRC mismatch | `ingest.archive.encrypted` / `ingest.archive.method` / `ingest.archive.crc` |
| **More than 256 MiB of members (R-40)** | accepted: `DATA` frames of at most 16 MiB, bounded by `max_member_bytes` and `max_total_bytes`, not by the per-job output cap, which applies to `JSON` frames only; wall and CPU limits scale with the declared total |
| Members not matching the profile's include or nested-archive patterns | not streamed; a `raw/members.jsonl` row with disposition `not_selected` |

Whole-archive and per-member dispositions are distinguished (SEC-07). Method 93 (zstd) is accepted, because the
Inspect `.eval` logs use it (AD-06).

### K.12.2 JSON limits and numbers — `tests/security/test_json_limits.py`

- Deep nesting at depth 257 and at depth 100,000 (`[` repeated 100,000 times in a 200 KB file): `ingest.json.depth` without `RecursionError` (SEC-02).
- Huge numbers:
  - `1e400` gives `ingest.number.nonfinite`;
  - a 10^6-digit integer gives `ingest.number.digits`, before Python's int-string limit fires (obs-G4);
  - integers beyond ±2^53 that are accepted are encoded `{"$int":…}` in AER [trace_formats §6.11].
- Duplicate keys at every depth: `ingest.json.duplicate_key`.
- Oversized records and lines: `ingest.size.record` (`ingest.jsonl.line_too_long` for JSONL). Oversized files and streams: `ingest.size.file` / `ingest.stream.size`, decided before reading the whole input into memory. A resource violation stores no bytes and writes a `rejected_unsafe` register entry; a policy violation on bytes within limits stores them and yields a degenerate AER (G.3.9; SEC-04).

### K.12.3 Encoding and JSONL framing — `tests/security/test_encoding.py`, `test_jsonl_framing.py`

The following each give a distinct code, and the bytes are never silently replaced:

- invalid UTF-8 (overlong, truncated, `0xC0`/`0xFF`), including UTF-8-encoded surrogates (`ingest.json.encoding`);
- UTF-16/32 input, with or without BOM;
- a UTF-8 BOM (`ingest.json.bom`);
- NUL bytes (`ingest.jsonl.nul` in JSONL);
- an **escaped** lone surrogate `"\ud800"` is the exception: a finding `ingest.json.lone_surrogate` (severity `info`), not a rejection, and the AER encodes it as `$utf16` (G.3.3 rule 8; K.5.3).

JSONL framing (SEC-03): U+2028 and U+0085 inside a record stay one line; CR, CRLF, blank lines, NUL, BOM, a missing final LF and over-long lines give distinct codes, each as a per-line issue with a locator, while the other lines are still mapped.

Valid but unusual content passes through byte-identically: right-to-left override, zero-width characters, combining marks and ANSI escapes inside JSON strings. Their sha256 in AER equals the source's.

### K.12.4 Path traversal and metadata poisoning — `tests/security/test_locator_traversal.py`, `test_metadata_poisoning.py`

- Member labels such as `../../x`, `/etc/passwd` and `C:\x` are labels: they are never opened as paths, and a locator addresses a member only through its member object `a` (AD-12). A locator that names no stored object fails with `aer.locator.dangling`.
- JSON Pointers cannot escape the artefact.
- Byte ranges are bounded.
- Corpus paths are derived **only** from execution ids and digests. Ids, suite, task, pipeline and version values containing `/`, `..`, NUL, ANSI or 10 KB strings never alter a filesystem path or an identity (SEC-21). The test asserts every written path is under the corpus root and matches the sharded-id pattern `aer/<ss>/<ex>.aer.jsonl` with `ss = sha256(ex)[:2]` (D9). Unknown tools fail closed in SEM.
- Origin `path` fields are data and never opened relative to the working directory.

### K.12.5 Tampering, forged manifests and reordered events — `tests/security/test_tamper.py`, `test_reordering.py`

| Attack | Expected detection |
|---|---|
| One byte changed in a raw artefact | `raw.digest.mismatch` at verify and before any re-derivation (baseline R5 [audit/corpus.md §3.3]) |
| `corpus.json` or `executions.jsonl` edited | Root digest mismatch. Manifests are covered (baseline P3) [audit/corpus.md §9] |
| `checksums.sha256` regenerated by the attacker to match tampered files | Detected through the recorded root digest and the AER seal → SEM → PROV digest chain, which do not match |
| A forged AER seal (correct count, wrong hash) | `aer.seal.digest` |
| A forged raw origin (git blob sha1 that does not match the bytes) | `raw.origin.blob_mismatch` |
| A forged derived file that `checksums.sha256` and the root digest were regenerated to cover | `verify --level rederive` re-derives from raw with package catalogues and detects the difference (SEC-15) |
| An archive member object altered | `verify --level chain` fails the member's CRC32 check; `rederive` re-runs `expand` and requires identical member digests (AD-12) |
| `REFERENCES.json` entry pointing to a different commit, or to an origin no in-package profile pins | `raw.reference.digest` / `raw.reference.unpinned_origin` (R-43) |
| capture/0.1 events reordered, deleted, duplicated or inserted, or the tail truncated | Distinct hash-chain codes (`capture.chain.order`, `.gap`, `.duplicate`, `.truncated`). A truncated tail is sealed *incomplete with issues*, never silently repaired (SEC-16). |
| AER lines reordered with references still valid | `aer.order.noncanonical` (and `aer.seal.digest`) |
| AER lines reordered so a reference becomes forward | `aer.ref.forward` |
| An artefact with embedded PROV, a claimed `sha256` and claimed producer versions | No core PROV statement and no identity come from those fields; they appear only as `O` data `by: source` (SEC-17) |
| Claimed times that would imply an order | No `after` edge and no PROV dependency; an implausible time gives `time.implausible` and the value is unchanged (SEC-18) |
| The same bytes at two origins; one `source_key` claimed by two corpora | One execution with two origins; the second owner is refused (SEC-19; `tests/unit/corpus/test_dedup.py`) |
| A sealed corpus targeted by `import`, `recompute` or `package` | Refused by the manifest seal check (exit 4). This replaces the baseline's name-based release guard [audit/legacy_replay.md §3.6 D9] |

> **As built (phase 11):** the tamper and verify cases of K.12.5 are tested in `tests/corpus/` (`test_tamper.py` and
> neighbours), not in `tests/security/`, because `tests/security/` belonged to phase 12 during phase 11. The SEC-15
> placement in `tests/security/test_tamper.py` and `test_deposits.py` is pending phase 12b. U4's tests:
> `tests/corpus/test_tamper.py` (every K.12.5 row at the level that detects it), `test_deposit_verify.py`,
> `test_verify.py`, `test_validate_corpus.py`.

### K.12.6 Prompt injection in data and dangerous sinks — `tests/security/test_untrusted_content.py`, `test_static_dangerous_calls.py`, `test_yaml_bombs.py`

**Dynamic test.** Fixtures are augmented with synthetic payload strings: `$(touch /tmp/pwned)`, backticks, `; rm -rf ~`, `{{7*7}}`, `${jndi:…}`, `../../`, `\x1b]0;title\x07`, `\x1b[2J`, ChatML `<|im_start|>system`, forged `<think>` blocks, and an imperative sentence addressed to an AI agent that asks it to delete the corpus. The sentence is assembled at run time from fragments, so no test source or fixture file holds it whole (R-42). Running the full CLI pipeline (import → package → verify → stats → render where the extra is installed) on them MUST show:

- (a) no subprocess launched other than the declared `dot` renderer, which receives data only on stdin and never by argv (checked by monkeypatching `subprocess.Popen`; K.5.12);
- (b) no file created outside the corpus root and tmp;
- (c) stdout and stderr contain no raw C0/C1 control bytes or ESC sequences: content snippets go through `quote_untrusted` (fenced, with locator and hash) and exception arguments through `escape_untrusted` (SEC-12);
- (d) the payload bytes survive byte-identically in raw and AER;
- (e) `DATASHEET.md` and generated Markdown contain no unescaped payload text that could inject Markdown or HTML, and the datasheet has its untrusted-content section;
- (f) `inspect` shows content only with `--show-content`, and then only through `quote_untrusted` (R-42; MN N.2.8 as amended).

`tests/security/test_quote_untrusted.py` covers `quote_untrusted` itself: the Cc/Cf/Cs/Zl/Zp categories, fence integrity and the round trip (obs-G10 as a test).

**Static test** (SEC-11). An AST scan of `src/agentprov/**`, `capture/agentprov_capture/**` and `backends/shared/agentprov_backend/**` MUST find none of:

- `eval`, `exec`, `compile` on non-literals;
- `pickle.load(s)`, `marshal.loads`;
- `yaml.load` / `yaml.unsafe_load` / `yaml.full_load`, and any `import yaml` outside `ingest/yamlsafe.py` and the compat shim;
- `subprocess.*(…, shell=True)`, `os.system`, `os.popen`;
- `shutil.unpack_archive`, `tarfile.extractall`, `zipfile.ZipFile.extractall`;
- `importlib.metadata.entry_points`, `dotenv.load_dotenv` (only `dotenv_values` in the live CLI entry), and `str.splitlines` in loaders.

The allow-list is empty in v0.1. Python literal parsing, when it returns with its dialects, uses `ast.literal_eval` only. Store objects are mode 0444 without exec bits, and a sniffed pickle stays inert.

**Live backend** (SEC-14). AgentPROV's own recording transport and recorders MUST NOT alter payload text that the benchmark deliberately places in the model's context. A backend-project test compares the payload in the wire request with the benchmark's fixture text; K.8.1 extends the comparison to the capture log, the native log and the AER.

**YAML bombs** (SEC-05). Marker normalisation parses untrusted tool output through `ingest.yamlsafe` only [audit/provenance.md §14 D19]. An alias-expansion "billion laughs" document or a self-referencing alias in a tool output MUST complete within the time and memory budget: aliases are rejected, the input is capped at `max_yaml_bytes`, and the marker status is `ambiguous` with issue `ingest.yaml.alias`, never a crash.

**Hygiene.** No fixture tree contains files addressed to coding agents (K.4.2; K.12.13).

### K.12.7 Spoofed identity — `tests/security/test_identity_spoofing.py`

1. A live fake-client response reports `model: "gpt-4o"` for a request that asked for `gpt-5-nano`. Both values are recorded, `requested` (`by: config`) and `served` (`by: provider`), and an issue makes the mismatch visible. Neither value is overwritten. (The fake-client half runs in `backends/shared/tests/`; the mapping half runs on the frozen capture fixture.)
2. Import with `pipeline_name` versus directory disagreements (ROPE qwen→gpt-4o-mini; AgentDojo HEAD `local`; AgentDyn bare model names) gives seal issue `identity_conflict`, flagged and not resolved, and the two executions never collide.
3. Logs claiming `agentdojo_package_version: "0.1.35"` do not establish distribution identity. AgentDyn and AutoDojo both report it (D9). The benchmark identity in AER comes from the profile's pinned commit (the `bench` actor's `code`), with the claimed version recorded as `O` data (its `version`).
4. A capture log whose `identity` event claims a different capture-code commit than the one T0 computed before spawn is recorded as claimed and flagged, never trusted for identity; for a live session the mismatch aborts the run (K.8.4(1)).

### K.12.8 Decompression — `tests/security/test_decompression.py` (SEC-06)

v0.1 decompresses only zip members with method 8 (deflate) and 93 (zstd); the gzip, bzip2 and xz stream codecs are
deferred (AD-10 row 16), and such a stream gives `ingest.stream.codec`. The tests cover: a zstd member bomb stopped
at the cap (`ingest.archive.ratio`/`ingest.archive.size`); a zstd frame whose declared window exceeds
`zstd_window_log_max` (`ingest.stream.memory`); a truncated frame (`ingest.stream.truncated`); and decompression
inside a T1 worker, so an exhaustion kills the worker and never the parent. The gzip, bzip2 and xz cases of SEC-06 land
with those codecs.

### K.12.9 Links and special files — `tests/security/test_links_special_files.py` (SEC-10)

A zip symlink attribute is refused (`ingest.archive.link`); a git mode 120000 entry is stored as data; an `--input`
tree with a symlink in any path component is refused (`ingest.path.symlink`; `O_NOFOLLOW_ANY` on macOS); a hardlink is
refused unless `--allow-hardlinks` is given (`ingest.path.hardlink`, recorded); a FIFO is rejected without hanging
(`ingest.path.special`). The macOS-specific case runs on the maintainer's macOS machine and is recorded in the release
report, because a hosted macOS run of this case is deferred (AD-10 row 18).

### K.12.10 Worker isolation — `tests/security/test_worker_isolation.py` (SEC-22)

T1 workers run as `python -I -B -m agentprov.worker` (protocol `agentprov-job/0.1`). A CPU loop is killed
(`SIGXCPU`); a memory hog is killed by the RSS watchdog; the wall timeout fires; writes past `RLIMIT_FSIZE` give
`EFBIG` while the pipe keeps working (obs-G5); the audit hook — reduced to network and subprocess events (R-45) —
blocks sockets and `Popen`; no secret is in the worker environment; no `FORBIDDEN` module is in `sys.modules` after a
job. Each failure becomes a degenerate AER with `adapter_defect` or `worker.limit.<cpu|rss|wall|output>`, and the raw
bytes are kept. The parent rejects a frame over 16 MiB, an unknown tag, a `DATA` frame without an open member, and
`JSON` output over the per-job cap. `--release` together with `--in-process` is refused (exit 4), and an
`--in-process` run records `producer.isolation = "in-process"`. Linux adds `RLIMIT_AS`.

### K.12.11 Secrets — `tests/security/test_secrets.py` (SEC-25; R-51)

- `.env` is read only by the live CLI entry, from `--env-file` or the repository root, with `dotenv_values` only; `os.environ` is unchanged (A4).
- The sentinel-secret test of G.6.5: a sentinel key value never appears in any capture log, AER, register row, report or log file; the header allowlist and the hard denylist (never `authorization`, API keys or `key=` query values) apply to recorded wire requests.
- T0 runs the literal-value scan over **every** staged file before `put_stream`, using the values it read from `.env`; a hit quarantines the session, and a scan failure in the worker ends the capture log `errored` with the constant `capture.redact` error, which T0 also quarantines (D-290; tested end to end through the real worker and with the fake worker, where no staged file holds a value T0 knows).
- `$HOME` is replaced by `<home>`, and the host name is redacted, on non-content surfaces (tracebacks, worker logs, `file` origins).
- A base URL that is not https (loopback excepted), that carries a query, or whose host does not match `endpoints.toml` is refused unless `--allow-custom-endpoint` is given, which is recorded.
- `agentprov purge sha256:<hex> --reason secret` removes a leaked object and writes a tombstone (K.5.7(5)).
- The CI `secrets` job runs gitleaks over the full history (K.19).

### K.12.12 Interpreter guard — `tests/security/test_interpreter_guard.py` (SEC-26; Addendum B, AD-16)

Core declares `requires-python = ">=3.14"`. The guard concerns archive and compressed-stream ingestion below 3.14.8,
where the 3.14.8-only fixes (CVE-2026-15310, CVE-2026-19672) are missing (G.3.8). The tests monkeypatch the version
the guard reads:

1. **Dev mode, below 3.14.8:** a WARNING with code `ingest.interpreter.unpatched` naming both CVEs; `python_version` and `interpreter_advisory` are recorded in `corpus.json` and in the register; ingestion continues.
2. **Release mode, below 3.14.8:** every release-mode entry point that ingests an archive or a compressed stream — the `--release` flag of the commands that take it (MN N.2), and the deposit builder `agentprov.release.builder`, reached through `package --deposit` (the "`release`" of AD-16 is this builder, not a command; AD-SW2) — **refuses** archive and compressed-stream ingestion before any byte is parsed, with exit 3 (environment; Addendum C-1) and the same code. `package` in seal mode opens no archive or compressed stream, so it has nothing to refuse; the test proves that it opens none (D-62, user decision 2026-10-12; phase 12c observation O-2). There is no override flag: `--allow-unpatched-interpreter` does not exist (K.15).
3. **Advisory corpus (AD-SW2; G.3.8(3)).** `package`, and the builder through `package --deposit`, refuse a corpus whose `corpus.json` `producer` block records an `interpreter_advisory` (a corpus built in dev mode below 3.14.8), with exit 4 (refused; MN N.1.3), whatever interpreter runs `package`: the test builds the corpus with the version patched below 3.14.8, then runs `package` with the version patched to 3.14.8 and expects exit 4.
4. **At or above 3.14.8:** no warning, no refusal, and nothing recorded beyond the interpreter version.
5. Plain JSON and JSONL ingestion is unaffected in both modes.
6. A packaging test asserts `requires-python = ">=3.14"` in `pyproject.toml` and `3.14` in `.python-version`; the CI core job pins the latest 3.14 patch (K.19).

### K.12.13 The repository as an injection channel — `tests/security/test_agent_channels.py`, `tests/repo/*` (SEC-12, SEC-13; R-42)

- `.gitattributes` marks `tests/fixtures/** binary`; `.ignore` and `.rgignore` list `tests/fixtures/`; `.claude/settings.json` denies `Read(./tests/fixtures/**)` and `Read(./.env)`; `AGENTS.md` and `CLAUDE.md` (pointing to `AGENTS.md`) exist at the repository root, and no agent-instruction file exists under `tests/fixtures/`.
- Golden-helper and assertion output holds no fixture substring longer than 40 characters (K.3.2, K.3.4); a test feeds a mismatching golden with a payload fixture and inspects the captured report.
- Tracebacks print frames, and exception arguments are escaped.
- `tools/check_unicode.py` rejects each listed control category and accepts allowlisted fixtures; ruff PLE2502 is enabled (`tests/repo/test_unicode_controls.py`).

### K.12.14 Fetch hardening and references — `tests/security/test_fetch_hardening.py` (SEC-24; R-43)

On a synthetic local repository (the file protocol is allowed in this test only): no working tree is created; blob
SHA-1 is checked; symlinks are data; a gitlink is not fetched; a branch or tag is refused (`raw.origin.unpinned`); a
hook in the source never runs. For references: a reference resolves only against an in-package profile origin
(`raw.reference.unpinned_origin` otherwise); a token is attached with `add_unredirected_header` and only to the host
the profile declares; a cross-host redirect drops credentials, a downgrade to http is refused, and an unlisted host is
refused; `REFERENCES.json` holds no command or instruction text.

### K.12.15 Downloaded deposits — `tests/security/test_deposits.py` (SEC-15; R-44, AD-14)

- **Archive mode.** `verify` reads deposit archives directly in T1, extraction-free (G.3.5), and checks member labels against the closed-world `checksums.sha256`.
- **Tree mode.** Every relpath is validated with `logical_name` and the H.1.3 grammar before it is opened; a symlinked object and a `../` relpath are refused.
- **Swapped `rules/`.** `rederive` loads profiles and catalogues only from package resources, at the recorded version; a corpus whose `rules/` copies differ gives `rules.mismatch`, and a version the package does not ship gives `rules.unavailable`. A forged corpus cannot make `rederive` reproduce its forged derived files.

### K.12.16 Live tier T2 — `backends/agentdojo/tests/*`, `backends/autodojo/tests/*`, `tests/integration/test_run_spawn.py` (SEC-14, SEC-25; R-39, AD-13)

A T2 compromise is a compromise of the user account (G.1.2), so these tests check the v0.1 controls, not a
sandbox: `HOME` redirected to `$AGENTPROV_HOME/t2home/<session>`; the staging directory as working directory; the
venv interpreter launched directly, with no `uv` at run time; the environment built with `UV_PROJECT_ENVIRONMENT`
outside the repository and `--no-config`; the identity cross-check of K.8.4(1); staging ingested like `--input`
(reported paths are labels resolved only under the session directory; no-follow, `S_ISREG`, `st_nlink == 1`); and
the hostile-worker cases of K.8.4(7). Real-model runs additionally require the macOS `sandbox-exec` profile, after its
feasibility probe, or a documented dedicated macOS user or VM (AD-13(b)); they are never part of the test suite.

---

## K.13 Reproducibility tests — `tests/reproducibility/*`

| Id | Test | Assertion |
|---|---|---|
| RPR-1 | `test_recompute.py::test_zero_diff` | On the K.8.3 corpus (CI) and the full baselines (`full_corpus`): `recompute --dry-run` gives 0 changed, compared as **JCS bytes**, plus a semantic diff report (the baseline's `diff_documents` method is retained) [audit/corpus.md §3.3] |
| RPR-2 | `test_recompute.py::test_type_only_change_detected` | Changing a stored PROV attribute `true`→`1` or `3`→`3.0` in a copy is reported as changed (baseline R2) |
| RPR-3 | `test_recompute.py::test_transactional` | A failure injected after N writes leaves the corpus byte-identical: staging plus atomic swap (baseline R4) |
| RPR-4 | `test_recompute.py::test_inputs_verified_first` | Tampered raw bytes make recompute refuse before deriving (baseline R5) |
| RPR-5 | `test_recompute.py::test_derivation_versions_recorded` | The manifest and `derivation.json` record adapter (dotted id + SemVer), profile and catalogue (integer versions and digests, `rules: {"<ns>": <int>}`), engine, spec, `rfc8785` and interpreter versions, plus the digests of the core `uv.lock` and of each `backends/<b>/uv.lock` used (baseline R6; HL L.2.2). An intended change is a version bump (D9). |
| RPR-6 | `test_cross_process.py` | `-I` ignores `PYTHONHASHSEED`, so string hashing is randomised in every T1 worker (G.4.8, obs-G6). The test therefore compares at least three independent pool runs (each with fresh random seeds) and one `--in-process` run under each of `PYTHONHASHSEED` ∈ {0, 1, 4294967295}. All outputs are byte-identical. |
| RPR-7 | `test_environment_independence.py` | Byte-identical outputs under `TZ` ∈ {UTC, Pacific/Auckland}, `LC_ALL` ∈ {C, C.UTF-8}, two different working directories and corpus roots (no absolute path appears in any output), and two frozen clock instants. No derived artefact contains a wall-clock time. The baseline's `generated_utc` broke manifest reproducibility [audit/corpus.md §1(3c)]. |
| RPR-8 | `test_parallel.py` | `--jobs 1` vs `4` vs `8`, and worker recycling after every job vs after 64: identical `executions.jsonl`, `corpus.json`, `checksums.sha256` and every artefact. The index order is a function of execution ids (G.4.7). |
| RPR-9 | `test_parallel.py::test_filesystem_order` | `os.scandir` and `Path.iterdir` are monkeypatched to return reversed or shuffled entries. Outputs are unchanged. |
| RPR-10 | `test_recompute.py::test_live_raw_rederive` | Re-mapping a frozen `capture/` fixture twice yields the same AER digest. (Backend project) a second fake-client run of the same scenario yields different raw (ids and times) but the same `common_projection` (K.8.5). |
| RPR-11 | `test_recompute.py::test_rederive_members` | `verify --level rederive` re-runs `expand` on every container and obtains identical member digests (AD-12). |

---

## K.14 Import boundary and dependency tests — `tests/boundary/*`

`tests/boundary/test_import_boundary.py` and `test_optional_extras.py` (R-01, R-47; A1, AD-01, AD-17):

1. **No benchmark or backend imports in core.**
   - For **every** module under `agentprov` (there are no exceptions: live code is not in core), a fresh subprocess runs `python -c "import sys, <module>; print(sorted(k for k in sys.modules if k.split('.')[0] in FORBIDDEN))"` and MUST print `[]`.
   - `FORBIDDEN` = {`agentdojo`, `agentprov_backend`, `inspect_ai`, `openai`, `anthropic`, `google`, `cohere`, `httpx`, `pandas`, `pyarrow`, `numpy`, `networkx`, `pydot`, `pyshacl`, `dotenv`}. The extras' packages (`pydot` for `agentprov.render`, `pyshacl` for SHACL validation, `dotenv` for the live CLI entry) are imported only inside the functions that need them, so module import never loads them.
   - This also catches the baseline defect where offline `recompute` imported `agentdojo` through `generate` → `observer` [audit/corpus.md §3.3 R1; audit/legacy_replay.md §3.6 D8].
2. **A static AST check** forbids `import agentdojo`, `from agentdojo` and any import of `agentprov_backend` anywhere under `src/agentprov/`. It catches lazy imports the dynamic test cannot reach. The same check over `backends/` asserts that no backend project imports `agentprov`, and each backend `pyproject.toml` is checked to have no `agentprov` dependency.
3. **YAML (AD-17).** `pyyaml` is a core dependency. `yaml` is imported only by `src/agentprov/ingest/yamlsafe.py`; the compat port's `import yaml` is routed to the `safe_load` shim over `ingest.yamlsafe` and recorded in `PORT_MANIFEST.json` (R-31). Readers and loaders never use YAML, which keeps A1's "stdlib-only for parsing untrusted bytes" (G.11 #17).
4. **`agentprov_capture` purity.** A fresh interpreter that imports every `agentprov_capture` module has only stdlib modules and `rfc8785` in `sys.modules`, on Python 3.12 and 3.14.
5. **The CI `core` job asserts that `agentdojo`, `agentprov_backend`, `openai`, `httpx` and `inspect_ai` are not installed.** Offline import, SEM, PROV, validation, `stats`, package, verify and recompute must therefore pass without them.
6. **Optional extras** (`test_optional_extras.py`): importing `agentprov` with `shacl`, `render` or `live` absent works. Commands needing them (`validate` with SHACL shapes, `render`, and `run` when it reads `.env`) fail with a typed "extra not installed" error and exit 3, never an `ImportError` traceback. There is no `agentdojo`, `analysis` or `all` extra.
7. **No RDF plugin injection.** No distribution in the core lock declares `rdf.plugins.*` entry points (rdflib would load them).
8. **Supply chain (SEC-23).** Each `uv.lock` (core, `capture/`, `backends/shared/`, `backends/agentdojo/`, `backends/autodojo/`) passes `uv lock --check`; installs are wheel-only except an allowlist; a fixed `exclude-newer` is present; no code uses `entry_points`; registry factories are `agentprov.`-namespaced; profile files from outside the package are refused in release mode. osv-scanner runs over every lock in the CI `supply-chain` job (K.19).

> **Resolved (AD-17 / R-47):** PyYAML is a core runtime dependency, locked at 6.0.3 and imported only by
> `ingest/yamlsafe.py`, which the SEM marker normaliser and the compat shim use. The `import` extra proposed here is
> not adopted. The evidence for the challenge stands [obs-K7; `agentdojo_prov/build_prov.py:251`].

---

## K.15 CLI tests — `tests/cli/*`

The tests drive the `agentprov` console entry point through `subprocess` (real exit codes, real stdout and stderr), and through the in-process main function for coverage. Subcommand names and flags follow MN N.2. The tests apply to every registered subcommand.

1. **Contract** (`test_cli_contract.py`):
   - the registered command set is **exactly** the 15 commands of MN N.2 — RESOLUTIONS §3.7's 13 (`run`, `import` with alias `convert`, `fetch`, `derive`, `recompute`, `validate`, `verify`, `inspect`, `info` with alias `sources`, `backends`, `package`, `migrate`, `purge`) plus `stats` and `render`, which Addendum B keeps (AD-10). `diff` is deferred; the HL groups (`corpus build`, `raw fetch`, `release build`, `collection build`), `compat verify`, `corpus package` and `verify-profile` do not exist;
   - the flags of §3.7 exist: `verify --profile-counts SOURCE --raw DIR`, `verify --against-pins`, `--in-process`, `--show-content`, `--allow-hardlinks`, `--env-file`, `--allow-custom-endpoint`, `info --matrix|--must-not-claim`, `--format` and `derive --trig DIR`; `--allow-unpatched-interpreter`, `derive --outcome-replay` and `info --card` do not;
   - `--help` for every subcommand exits 0;
   - exit codes are MN N.1.3's: 0 ok, 1 failures, 2 usage, 3 environment (missing extra, missing binary, isolated environment absent or identity mismatch, unpinned origin, interpreter below 3.14.8 in release mode), 4 refused, 5 unsupported (a `planned` or `not_possible` source or dialect), 70 internal (including a `ProfileError`), 130 interrupted. Each code has at least one test that triggers it;
   - `--json` output validates against a committed JSON Schema (`agentprov-cli-summary/0.1`) and is byte-stable across runs;
   - no subcommand opens a socket unless it is a declared fetch command run with `network`.
2. **Dry run.** `import --dry-run`, `recompute --dry-run` and `package --dry-run` write nothing (`fs_guard` over the corpus root and `$HOME`), and they still *validate* (baseline R3).
3. **`validate --strict` / `--release`.** Any skipped check fails with exit 1. The report lists library and interpreter versions.
4. **`verify`.** Every K.12.5 tamper case gives exit 1 with the matching code in `--json`, at the level that detects it (`checksums`, `chain` or `rederive`).
5. **Output safety** (`test_cli_output_safety.py`): K.12.6(c) and (f). `inspect` content views require `--show-content`. Paths in messages are relative to the corpus root, and `$HOME` is shown as `<home>`.
6. **Sealed corpora.** Writers refuse to write into them (exit 4; K.12.5).
7. **Idempotence.** Repeating `import` and `package` produces byte-identical trees.
8. **Generic commands.** `stats` (`test_cli_stats.py`) and `render` (`test_cli_render.py`, `render` gate) per K.5.11 and K.5.12; `purge` (`test_cli_purge.py`) per K.5.7(5); `import inspect` is supported for the producer band and exits 5 with a "planned" text for other versions (MN N.3); compat output prints its regression-oracle notice (R-55).

---

## K.16 Documentation tests — `tests/docs/*`

1. **`test_doc_examples.py`.**
   - Every fenced block tagged `aer-example`, `sem-example` or `prov-example` in `docs/` (including the specification files `docs/architecture/*.md`; Addendum C-2, B-3) validates with the in-code validator and the JSON Schema. The examples of `spec/examples/C/` are generated by the scripts there and never hand-edited.
   - Every `python` block tagged `doctest` runs through `pytest --doctest-glob="docs/**/*.md"`.
   - Console examples tagged `console-test` run against fixtures and compare their output. They write corpora under `$AGENTPROV_HOME` and use `agentprov fetch` or `--input` outside the workspace, never a working-tree clone.
2. **`test_rule_docs.py`.** Every rule id in every shipped catalogue has a documentation entry: statement, evidence class ceiling, cited code or source, version history. No documented rule is missing from a catalogue.
3. **`test_ontology.py`.**
   - `vocab/apv-0.2.ttl` parses with rdflib, `owl:versionInfo` equals `0.2.0`, `owl:versionIRI` ends in `/ns/0.2.0`, and `owl:priorVersion` names `/ns/0.1.0`; `docs/ns/apv-0.2.ttl` is a byte copy, and every term of the published `docs/ns/apv-0.1.ttl` (0.1.0) is still declared in 0.2.0 with the same types and ranges. The w3id IRIs are placeholders until U-02.
   - Every `apv:` term emitted by the engine on the fixture set is declared, including `apv:CacheRead`, `apv:RegressionOracle`, `apv:Overwritten`, `apv:RecordedNull`, `apv:NotObservable`, `apv:subtype`, `apv:declaredSender`, `apv:sentTransform`, `apv:LastPassOnlyLogging`, `apv:EnvironmentCarriedOver` and the generic-kind classes. `apv:Unknown` and `apv:CheckerReadsFinalState` are not declared. The baseline held the same property for `adprov:` [audit/validation.md §6.2].
   - Instance IRIs never fall in the vocabulary namespace (D7; V13).
   - The frozen `adprov.ttl` is byte-identical to the baseline copy (sha256 `4a9dcf4a…dca3`) [BASELINE §1.1].
4. **`test_links.py`.** Internal links and anchors resolve offline. External links are checked under `network`. w3id is never contacted outside `network`.
5. **`test_status_docs.py`.** The support-status tables in `README.md` and `docs/`, the `info --matrix|--must-not-claim` output, MN N.3 texts and the datasheet placeholders are generated from the registry (K.6.1) and are up to date. Every deferral of AD-10 is listed, with its reason, in `docs/roadmap.md`.
6. **`test_claims_lint.py`** (DoD Q.11b). The one claims/lint library (`adapters/registry/claims.py`) passes over `README.md`, `AGENTS.md`, `docs/`, the datasheet templates and the paper sources: registry status phrases only; the I.4 must-not-claim items; the scoped-term rules of O.3.7, including the AD-08 rule on "benchmark-agnostic" (K.6.1(7)); "derivation-reproducible", "integrity-verifiable" and "traceable statement by statement" instead of the unqualified forms; "AER" always expanded as "AgentPROV Execution Record" at first use (AD-22).
7. **`test_traceability.py`.** K.1(1), plus every SEC id of G.10 maps to at least one `test_sec<NN>_` function (K.12). It also asserts B.11 check 1: `docs/port/baseline-map.json` has an entry for every row of B.2–B.5, no entry names a row that B.2–B.5 lack, and every row deferred by AD-10 has status `deferred`.

---

## K.17 Repository hygiene and performance smoke

1. **`tests/repo/test_repository_hygiene.py`** (runs on `git ls-files`). It fails on:
   - tracked corpora (`corpus/`, `runs/`, `*.aer.jsonl` outside `tests/fixtures/expected/`), and upstream clones or working-tree checkouts inside the repository;
   - `.env`, `*.log` and `CLAUDE.local.md` (they are in `.gitignore`);
   - files over 1 MiB outside the fixture whitelist;
   - strings matching common secret patterns (`sk-[A-Za-z0-9]{20,}`, `AKIA[0-9A-Z]{16}`, `hf_[A-Za-z0-9]{30,}`); the gitleaks pre-commit hook and the CI `secrets` job cover the full history (K.12.11);
   - fixture files without an index entry;
   - AI-agent instruction files inside `tests/fixtures/`, and a missing `.gitattributes` binary rule, `.ignore`/`.rgignore` entry or `.claude/settings.json` deny rule (K.12.13);
   - fixture files of any class but synthetic inside the sdist or wheel (K.4.2; U-06).

   These enforce the user's no-secrets / no-corpora-in-Git rule and D9.
2. **`tests/perf/test_perf_smoke.py`** (`slow`). This test records timings and does not gate on them, except with a ceiling 10× the recorded baseline. It covers:
   - deriving and validating the largest golden execution, R08 (164 tool calls, 2,222 v2.3 relations) [BASELINE §7];
   - a synthetic 1,000-call execution, generated as in the investigation's `scale_synthetic.py`.

   The baseline's taint rule grew `used` edges O(n²), and its `round_trip` took 104 s at 1,000 calls [audit/validation.md §6.5]. The test records the agentprov-prov/0.1 edge count of the `members` encoding (D7); the `collection` encoding is deferred (AD-10 row 14), and these counts are the evidence for reinstating it.

---

## K.18 Execution matrix and coverage

### K.18.1 What runs where

| Layer | PR/push CI | Manual CI (dispatch) | Local only |
|---|---|---|---|
| Core: unit, adapter (incl. Inspect and the `foobench` future-framework test), golden (19 pairs incl. MIG-10, R1/R2 converted pairs, expected outputs), offline e2e, stats, security, boundary, CLI, docs, hygiene | ✓ (`core`, Python 3.14 latest patch, Ubuntu) | ✓ | macOS-specific security cases (SEC-10, SEC-22) on the maintainer's machine; a hosted macOS run is deferred (AD-10 row 18) |
| `agentprov-capture` unit tests | ✓ (`capture`, Python 3.12 and 3.14) | ✓ | — |
| `agentprov-backend` unit tests | ✓ (`backend-shared`, Python 3.12) | ✓ | — |
| Live AgentDojo integration, executor mirror, payload fidelity | ✓ (`backend-agentdojo`, Python 3.12 backend project) | ✓ | — |
| Core mapping of fresh live outputs; live-vs-native differential | ✓ (`live-map`, Python 3.14; frozen fixtures in `core` otherwise) | ✓ | — |
| SHACL, render | ✓ (`extras`) | ✓ | — |
| Property tests, `ci` profile | ✓ | — | — |
| Property tests `thorough` profile; Hypothesis fuzz `thorough`; perf smoke | — | ✓ (`thorough`, `slow`) | on demand |
| Pinned upstream fetch and verification; STAC full file; external links | — | ✓ (`network`) | on demand |
| Old-vs-new package (incl. C6) | — | ✓ (`old-vs-new`) | on demand |
| AutoDojo worker | — | ✓ (`backend-autodojo`; the environment is built by `agentprov backends build autodojo` from the lock; tests run network-blocked) | on demand |
| Dependency and secret scanning | on lock changes (`supply-chain`); every push (`secrets`) | ✓ (`supply-chain` has its own dispatch trigger) | — |
| Full 35,691 A1/A2/B, validation (D), semantic diff (E) and recompute; full June-2024 import (18,241) and full R claim gate; all 6 survey AgentHarm logs | — | — | ✓ (`full_corpus`, release gate). The on-disk corpus is v2.3, deposited on Zenodo on 2026-10-10 (`10.5281/zenodo.23276620`, D-900; byte equality unverified, U-07) [BASELINE §8(1)]. Corpora are never in Git (D9). |

The PR CI target is under 12 minutes wall time per job. A reversed-order run is a local option (K.3.4). Atheris and a hosted reverse-order run are deferred (AD-10 row 18).

### K.18.2 Coverage (branch coverage on; ratchet from the first measured value)

Under AD-10 row 18, the fixed floors of the first draft (98 %/95 % for the AER core down to 92 %/85 % combined) are
deferred. Coverage is measured per area from the first CI run that has the area's code, and the recorded value is a
**ratchet**: it MUST NOT be lowered without a `CHANGELOG.md` entry. The areas are kept so that the ratchet is
per area:

| Area (package) | Measured in |
|---|---|
| AER model, ids, JCS, lexical hints, locators, seal, accounting; ingest safety; validators (all tiers) | `core` |
| Provenance engine (incl. generic rules), SEM, raw store and `expand`, corpus/manifest, stats | `core` |
| Import readers and mappers (TraceLogger, adprov, Inspect, capture); profiles loader; registry and claims | `core` |
| Compat port (verbatim) | `core` (golden + ported baseline tests) |
| Render | `extras` |
| `agentprov_capture` | `capture` |
| `agentprov_backend` and the backend projects | `backend-shared`, `agentdojo` |
| CLI | `core` |
| Whole core package (combined) | `coverage` job |

`# pragma: no cover` requires an inline reason. `tests/repo/test_repository_hygiene.py` fails if more than 25 pragmas exist without the agreed `# pragma: no cover — <reason>` form.

Mutation testing (`mutmut`) is deferred (AD-10 row 18).

---

## K.19 GitHub Actions workflow outline (private repository, uv-based)

Normative properties:

- every third-party action is pinned to a full commit SHA, with the version in a comment;
- `permissions: contents: read`;
- no secrets are used by any job;
- every job installs only from a lock: `uv sync --locked` in the project it tests, and `uv lock --check` for every lock in `lint`;
- the core job runs **Python 3.14 at the latest patch**, pinned by the workflow (Addendum B, AD-16), and replaces the first draft's 3.12/3.13 matrix (A1);
- backend jobs run **Python 3.12** inside their own project (`backends/<b>`), and the markers `agentdojo` and `autodojo` mean "backend project", not "core extra" (R-01);
- the `backend-autodojo` job builds its environment with `agentprov backends build autodojo` from the lock; it checks out no upstream repository and installs no editable fork (R-49);
- the `old-vs-new` job installs the baseline as J.1.6 does: the dependencies from `migration/baseline-requirements.txt` (the hash-locked export of `baseline/pip_freeze.txt`) with `--require-hashes --no-deps`, and the old package as a non-editable wheel built from `579a908` or taken from a private mirror (R-49);
- JUnit XML and coverage data are uploaded as artefacts; fuzz crashers and live outputs are uploaded, and may contain untrusted payload text (the repository is private);
- one dependency scanner (osv-scanner, with `uv lock --check`) and one secret scanner (gitleaks) run in CI (R-45); `tools/check_unicode.py` runs in `lint`.

```yaml
# .github/workflows/ci.yml  (outline)
name: ci
on:
  push: {branches: [main]}
  pull_request:
  # no schedule: the manual-dispatch jobs run at the points of K.19.1
  workflow_dispatch:
    inputs:
      gates: {description: "extra gates (comma list)", required: false, default: ""}
permissions: {contents: read}
concurrency: {group: "ci-${{ github.ref }}", cancel-in-progress: true}
env:
  AGENTPROV_STRICT_SKIPS: "1"
  AGENTPROV_BLOCK_NETWORK: "1"
  HYPOTHESIS_PROFILE: ci
  CORE_PY: "3.14.x"            # pinned to the latest 3.14 patch by the workflow (AD-16)

jobs:
  lint:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>        # vX
      - uses: astral-sh/setup-uv@<sha>      # vY
        with: {enable-cache: true}
      - run: |                              # every lock, every project
          for p in . capture backends/shared backends/agentdojo backends/autodojo; do
            (cd "$p" && uv lock --check); done
      - run: uv sync --locked --extra dev --python "$CORE_PY"
      - run: uv run --locked ruff check .                   # target-version py314; PLE2502 enabled
      - run: uv run --locked ruff format --check .
      - run: uv run --locked mypy src/agentprov             # python_version 3.14
      - run: uv run --locked python tools/check_unicode.py

  core:
    needs: lint
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
        with: {enable-cache: true}
      - run: uv sync --locked --extra dev --python "$CORE_PY"
      - name: benchmark and backend packages must be absent
        run: uv run --locked python -c "import importlib.util as u,sys; sys.exit(any(u.find_spec(m) for m in ('agentdojo','agentprov_backend','openai','httpx','inspect_ai')))"
      - run: uv run --locked coverage run -m pytest -n auto --gates= --junitxml=junit-core.xml
      - uses: actions/upload-artifact@<sha>
        with: {name: cov-core, path: ".coverage.*", include-hidden-files: true}

  capture:
    needs: lint
    strategy: {fail-fast: false, matrix: {python: ["3.12", "3.14.x"]}}
    runs-on: ubuntu-24.04
    defaults: {run: {working-directory: capture}}
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - run: uv sync --locked --python ${{ matrix.python }}
      - run: uv run --locked pytest --junitxml=junit-capture-${{ matrix.python }}.xml

  backend-shared:
    needs: lint
    runs-on: ubuntu-24.04
    defaults: {run: {working-directory: backends/shared}}
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - run: uv sync --locked --python 3.12
      - run: uv run --locked pytest --junitxml=junit-backend-shared.xml

  backend-agentdojo:
    needs: lint
    runs-on: ubuntu-24.04
    defaults: {run: {working-directory: backends/agentdojo}}
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - run: uv sync --locked --python 3.12
      - run: uv run --locked python -c "import importlib.metadata as m; assert m.version('agentdojo') == '0.1.35'"
      - run: uv run --locked pytest -m agentdojo --junitxml=junit-agentdojo.xml   # writes live outputs to $RUNNER_TEMP/live
      - uses: actions/upload-artifact@<sha>
        with: {name: live-outputs, path: "${{ runner.temp }}/live"}

  live-map:                                   # core side of the live runs (K.8.5)
    needs: [backend-agentdojo]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - uses: actions/download-artifact@<sha>
        with: {name: live-outputs, path: live}
      - run: uv sync --locked --extra dev --python "$CORE_PY"
      - run: AGENTPROV_LIVE_ARTEFACTS=$PWD/live uv run --locked pytest -m live_artefacts --gates=live_artefacts

  extras:
    needs: lint
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - run: sudo apt-get update && sudo apt-get install -y graphviz
      - run: uv sync --locked --extra dev --extra shacl --extra render --python "$CORE_PY"
      - run: uv run --locked coverage run -m pytest -m "shacl or render" --gates=shacl,render
      - uses: actions/upload-artifact@<sha>
        with: {name: cov-extras, path: ".coverage.*", include-hidden-files: true}

  coverage:
    needs: [core, extras]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - uses: actions/download-artifact@<sha>
        with: {pattern: "cov-*", merge-multiple: true}
      - run: uv sync --locked --extra dev --python "$CORE_PY"
      - run: uv run --locked coverage combine
      - run: uv run --locked python tools/coverage_ratchet.py   # per-area ratchet of K.18.2

  secrets:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>
        with: {fetch-depth: 0}
      - run: tools/ci/install-gitleaks.sh   # pinned release, verified by sha256; no licence secret needed
      - run: gitleaks detect --redact --config .gitleaks.toml --baseline-path .gitleaks-baseline.json --log-opts=--all

  # supply-chain: a separate workflow, .github/workflows/supply-chain.yml, triggered on pushes that change any
  # **/uv.lock and by manual dispatch; it runs osv-scanner over every uv.lock (SEC-23; R-45).

  thorough:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-24.04
    env: {HYPOTHESIS_PROFILE: thorough}
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - uses: actions/cache@<sha>
        with: {path: .hypothesis, key: "hypothesis-${{ github.run_id }}", restore-keys: "hypothesis-"}
      - run: uv sync --locked --extra dev --python "$CORE_PY"
      - run: uv run --locked pytest --gates=slow

  network:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-24.04
    env: {AGENTPROV_BLOCK_NETWORK: "0"}
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - run: uv sync --locked --extra dev --python "$CORE_PY"
      - run: uv run --locked pytest -m network --gates=network   # pinned fetches verified by digest

  old-vs-new:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - run: uv venv /tmp/baseline --python 3.12.14                 # the baseline interpreter (J.1.6)
      - run: uv pip install --python /tmp/baseline/bin/python --require-hashes --no-deps -r migration/baseline-requirements.txt  # J.1.6: pip_freeze.txt minus its -e line, hashed
      - run: uv pip install --python /tmp/baseline/bin/python --no-deps "$BASELINE_WHEEL"  # agentdojo_prov 1.0.0, non-editable, built from 579a908 or a private mirror; sha256 per the lock (J.1.6)
      - run: uv sync --locked --extra dev --python "$CORE_PY"
      - run: AGENTPROV_BASELINE_PYTHON=/tmp/baseline/bin/python uv run --locked pytest -m old_package --gates=old_package
      # C6 (K.9.2) runs in the agentdojo backend project with the same baseline interpreter

  backend-autodojo:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-24.04
    env: {AGENTPROV_HOME: "${{ runner.temp }}/agentprov-home"}
    steps:
      - uses: actions/checkout@<sha>
      - uses: astral-sh/setup-uv@<sha>
      - run: uv sync --locked --python "$CORE_PY"                   # core CLI only
      - run: uv run --locked agentprov backends build autodojo      # uv sync --locked --no-config on backends/autodojo;
                                                                    # env under $AGENTPROV_HOME/envs/autodojo-<commit8>
      - run: "$AGENTPROV_HOME"/envs/autodojo-*/bin/python -I -m pytest backends/autodojo/tests -m autodojo
```

Local equivalents. The release gate (K.20) runs `uv run python tools/gates.py --all` (a maintenance script, not part
of the package; RESOLUTIONS §3.2), which sets the environment variables and runs every gate including `full_corpus`.
The run writes a signed-off report JSON: versions (including the interpreter and every lock digest), counts, digests,
and zero skips.

### K.19.1 Manual CI runs (no scheduled CI)

AgentPROV has no scheduled CI of any kind (DECISIONS D-22). The merge gate is local (D-431 as updated by D-462):
`tools/ci_local.py`, whose `core` job is the full suite through `tools/suite_queue.py` (AGENTS.md §8). GitHub CI is
optional: its push and pull-request runs happen only while the repository variable `CI_ON_PUSH` is `true` (every job
is skipped otherwise), and `CI_RUNNER` can move the jobs to a self-hosted runner. Dispatch runs every job, including
the offline ones. At each point below, also run `uv run python tools/ci_local.py --strict --with-dispatch-jobs
--allow-network` (with the user's yes for the network) and record its report. The jobs
that rebuild pinned environments from the network, or run the slow gates, are **manual dispatch only**:
`backend-autodojo`, `old-vs-new`, `network` and `thorough`. They check things outside the repository (GitHub, PyPI,
nltk_data, the baseline wheel), so a repository that does not change can still stop rebuilding. `network` and
`thorough` are built when their gates have tests; AGENTS.md §8 "Manual CI runs" names the jobs that exist.

Dispatch the workflow (`gh workflow run ci.yml --ref main`, or "Run workflow" on GitHub; a dispatch runs every job) and
check that the jobs above pass on the commit concerned, at each of these points:

1. before tagging a software release (`vX.Y.Z`);
2. before building or depositing a corpus release (`corpus/<id>/vX.Y.Z`; Zenodo), where depositing also needs the
   user's explicit instruction (D-5);
3. before submitting a thesis chapter or paper that reports live-backend or migration results;
4. after changing anything the jobs exercise: `backends/**`, `capture/**`, a backend `uv.lock`, the baseline lock in
   `migration/`, the gate-C6 register, or the `agentdojo` capture mapping.

The run id and result are recorded in the release notes or the relevant `docs/reports/` file (K.20 item 1). A failure
caused by an external pin that vanished or changed (fork rewritten, wheel yanked, file moved) is a finding: it is
reported, and the pin is never changed silently.

---

## K.20 Release gates

A software release (`agentprov` x.y.z) or a corpus release MUST NOT be tagged unless all of the following hold for the release commit:

1. Every PR job is green, and the manually dispatched jobs (K.19.1) have passed on the release commit, with zero skips under strict mode.
2. **Migration release gates (AD-07; J.3.0), verbatim and in this order: G0, A1, A2, B, D, E.**
   - **G0** — the baseline corpora match `migration/baseline.lock.json` (K.7.4(1));
   - **A1** — v1 → AER → v1 view, JCS value identity, 35,691/35,691 (K.7.2);
   - **A2** — the same in **bytes**, 35,691/35,691 (K.7.2);
   - **B** — `adprov-v2.3-compat` graphs byte-identical, 35,691/35,691 (K.7.1);
   - **D** — `agentprov-prov/0.1` derivation validated on all, with no skips (K.7.4(4));
   - **E** — the semantic-diff report generated from `prov/compat/semdiff-map.toml` (K.7.4(5)).

   **R1/R2** on the golden converted pairs (C01–C07 and the MIG-10 converted pairs) are release gates in CI (K.7.2). The **full R** run over the 18,241 pinned June-2024 blobs is a **claim gate**: the report records its status (pass with 0 mismatches, or the mismatch report), and only a pass licenses "the native re-import supersedes the converted tree". R3–R5 are reported. C1 is optional; C4 is deferred.
3. The local `full_corpus` gate passes and its report is committed under `docs/reports/` (MN M.1.5; PQ phase 13; numbers only, no corpora). Besides the gates of item 2, the report covers: recompute 0 diff; the June-2024 pinned import (zero crashes, all sealed, counts); the 6 survey AgentHarm logs end to end (DoD Q.11a); the pinned legacy Inference-6 counts 26,645 / 23,449 (K.7.4(7)); and the **interpreter** (`python_version`, and `interpreter_advisory` if any) and lock digests that produced it (J.0).
4. The report's digest is recorded in the corpus manifest, or in the release notes for a software release.
5. Every committed fixture's licence class permits the release type (K.4.2). Corpus packaging refuses `restricted` raw bytes, refuses mixed licence classes in one deposit (grouping key (spdx, sorted restrictions); AD-20), carries `restricted_use` clauses in `licences.restrictions`, and allows `noncommercial` content only in a `-nc` corpus (D3, D9).
6. The rule-catalogue coverage report (K.6.1(5)) shows no unexplained uncovered rule.
7. Release mode ran on an interpreter at or above 3.14.8, or refused archive ingestion (K.12.12).
8. The claims lint (K.16(6)) passes, and every registry status equals its gated value (K.6.1(6)).

Nothing is published to Zenodo or w3id by any test or workflow (D7, D9). Tags stay local, and any deposit or w3id
registration is the user's decision (Addendum B-2; U-01, U-02, U-16).

---

## K.21 Challenges raised in this section and their dispositions

All three challenges of the first draft have been ruled (RESOLUTIONS §1.3; Addendum B).

1. **D2: execution-id encoding.** The measurement stands: `base32(sha256)[:26]` and `base32(sha256[:16])` differ for 7,438/10,000 inputs [obs-K6].
   > **Resolved (AD-04 / R-03):** C's `[0:26]` of the full digest, lower case, over the mapping id
   > `<adapter id>/<profile id>` and the §3.4 locator canon; K's 16-byte rule is rejected. KAT
   > `ex_7uz2oys57hugtsueixylme4fl5` (K.5.2; obs-K8).
2. **D2/D7: JCS-canonical AER vs compat byte-identity.** The measurement stands: 8,037 released and 8,341 converted stored graphs depend on member order or integral-float lexemes [obs-K3; spec/B_audit_evidence].
   > **Resolved (AD-02 / R-04):** `ext.lex {ord, flt}` written by `aer.canon.lex_hints()`; the view reads nothing
   > from raw; gates A1 (JCS), A2 (bytes) and B (bytes). K's raw re-read and `adprov.compat_args_from_raw@1` are
   > rejected (K.7.2).
3. **D10: PyYAML missing from core.** [obs-K7; `build_prov.py:251`]
   > **Resolved (AD-17 / R-47):** accepted — a core dependency imported only by `ingest/yamlsafe.py` (K.14).

Refinements that do not contradict a decision:

- the scripted transport sits at the HTTP transport, below the recording transport of the stock LLM element (K.8.1, D5, AD-09);
- the backend must run cells inside a TraceLogger context for the D3 differential (K.9.1);
- the schema-vs-validator differential is one-directional on schema-expressible codes (K.9.3, D2);
- test-only dev tools are added (K.3.3, D10).

---

## K.22 Open questions and their dispositions

Dispositions per RESOLUTIONS §1.3 (row "K").

1. **Ingest limits.** *Closed (R-63).* The first draft said `landscape/secure_ingestion.md` was absent; it exists, and G.3.2 fixes the `IngestLimits` defaults. K.5.6 and K.12 read every value from `IngestLimits()` and probe the boundaries.
2. **Lone surrogates and non-I-JSON values.** *Closed by G.3.3 rule 8.* An escaped lone surrogate is a finding `ingest.json.lone_surrogate` (severity `info`), and the AER writer encodes the string as `$utf16` (C.11.2). None occur in the 35,691 baseline transcripts [obs-K5], and rfc8785 0.1.4 refuses them [obs-K4], which the `$utf16` encoding avoids. K.5.3 and K.12.3 assert this.
3. **Defended pipelines.** *Closed:* a defended AgentDojo pipeline is refused with a typed error in v0.1 live scope (K.8.1); auxiliary roles are accounted in AER only for imports.
4. **Type checker.** *Closed:* mypy is the CI authority (K.3.3, K.19).
5. **Atheris.** *Deferred* (AD-10 row 18; K.11.3).
6. **Model-provider terms and the converted-tree licence.** *Forwarded to the user* (U-06 for provider terms and committing real fixtures; U-03 for the licence of the converted-tree data derived from AgentDojo's 2024 logs [sources/agentdojo.md:378; audit/corpus.md §9 item 16]). Until then: private repository only, never in the sdist (Addendum B-2; K.4.2).
7. **Full-corpus gate in hosted CI.** *Accepted as written:* it cannot run there until a corpus containing the 35,691 v2.3 records is published (v2.3 is on Zenodo since 2026-10-10, D-900, so the gate could fetch it there; not yet wired). Until then the gate is local and its report is committed (K.20).
8. **Old-vs-new install.** *Resolved by R-49:* the job installs the baseline from a hash-locked export of `baseline/pip_freeze.txt` with `--require-hashes`, or from a mirrored wheel, not from a mutable repository URL (K.9.2, K.19).
9. **AutoDojo pin.** *Closed (A6):* `aa458794b7eb7f082e94daeac4c0f55bfc0c90cc` [sources/autodojo.md §1.1, §2]. The AutoDojo profile and `backends/autodojo` record it as a full 40-hex SHA in the lock, and K.8.4 enforces it through PEP 610 `direct_url.json`. If a later commit is inspected, the profile, the lock and the test move together.

New items found while revising (r2), with their dispositions after the r2 consistency sweep (SWEEP_r2, 2026-10-08):

10. **Generic-kind id prefixes and validator codes.** *Closed.* C.4.2 fixes the local-id prefixes `ac<n>` (`activity`) and `af<n>` (`artefact`); K still reads them from C's grammar table. The AER validator error codes are C.17's, and C.17 adopts K's spellings (`aer.schema.kind`, `aer.schema.oneof`, `aer.activity.shadows_kind`, `aer.subtype.missing`, `aer.subtype.undeclared` and the rest of K.5's codes), each mapped to its AER-V invariant (architect default AD-SW26; the closed list is added to C.17 by residual SW-C4).
11. **The 26,645 / 23,449 pair.** *Closed (SWEEP_r2 EV-1).* The pair is not contested: entailed-not-asserted communications (`landscape/prov_semantics_evidence/inference6_scan.json`) and R6 taint-only `used` edges (`audit/provenance_evidence/evidence_stats.json`) are the same set counted two ways, 26,645 (released) and 23,449 (converted). K.7.4(7) pins the values with both citations; no re-derivation is needed before pinning.
12. **uv floor vs AD-16.** *Closed by Addendum C-1.* The committed uv floor is `required-version = ">=0.12.18"` (the local uv), CI uses uv ≥ 0.12.22, and the release-mode interpreter refusal exits 3. K.19 pins the CI interpreter; MN commits the floor (M.2).
13. **macOS cases.** *Closed.* G.10 no longer assigns SEC-10 or SEC-22 to a hosted macOS job: SEC-10's macOS branch runs on the developer's machine, and hosted macOS runs are deferred (AD-10 row 18). K runs the macOS cases on the maintainer's machine and records them in the release report (K.12.9, K.18.1).
14. **Paths K introduces for MN.** *Closed.* The maintenance scripts under `tools/` (RESOLUTIONS §3.2) are MN's to list (M.1.6): `tools/regen_golden.py`, `tools/gates.py`, `tools/coverage_ratchet.py` and `tools/ci/install-gitleaks.sh` (K.7.3, K.19); MN's alignment of `coverage_gates.py` and the gitleaks installer is residual SW-MN5. The baseline requirements file is J's `migration/baseline-requirements.txt` (J.1.6; AD-SW19), which K.19 uses (the r2 draft's lock file under `tools/` is withdrawn). The release-mode entry points are the `--release` flag, `package`, and the deposit builder `agentprov.release.builder` reached through `package --deposit`; there is no `release` command (AD-SW2). Release-mode ingestion refusal exits 3, and `package` refusing a corpus that records an `interpreter_advisory` exits 4 (K.12.12(2)–(3)).
15. **G.10 SEC-23 scanner set.** *Closed.* G.10 SEC-23 now names osv-scanner only; pip-audit is no longer used (G.7.2, G.9.4). K follows R-45: one dependency scanner (osv-scanner, with `uv lock --check`).
