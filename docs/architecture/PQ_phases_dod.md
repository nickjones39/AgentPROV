Revision: 2026-10-07 r2 — review resolutions and Addendum B applied.

# P. Implementation phases

Binding precedence: `investigation/DECISIONS.md` Addendum B > Addendum A > D0–D12. The consolidated review is
`spec/review/RESOLUTIONS.md`: §4.13 lists the edits for this section, and §3 is the naming authority. In the new
repository this section becomes one file of `docs/architecture/` (Addendum B-3).

**Changes after review (2026-10-07).**
- **Applied:** R-01, R-04, R-07, R-12, R-14, R-15, R-17, R-21, R-22, R-25, R-27, R-28, R-29, R-32, R-34 (as ruled),
  R-35 (as ruled), R-42, R-45, R-46, R-48, R-50, R-55, R-59, R-60 (as ruled), and the RESOLUTIONS §5 variant list.
  Paths are canonical: there is no `core/` package, and the old names for the provenance, validation and semantics
  packages, the v1, TraceLogger, capture and Inspect adapters and the ontology file are replaced.
- **Phase plan.** The table below is the re-ordered plan of RESOLUTIONS §4.13, adopted with AD-06. It is adjusted
  for the Addendum B deviations:
  - **AD-10 as ruled.** `stats/` and `render/` stay in v0.1, with the `stats` and `render` commands (phase 11; DoD
    Q.32–Q.33). The rest of the old "CLI + analysis" phase (the analysis frames, the ML export, outcome replay) is
    deferred.
  - **AD-15 as ruled.** `aer/0.1` has 13 record kinds, including the generic `activity` and `artefact` (B-1). EF's
    generic rules G-ACT, G-USE, G-GEN and G-ASSOC are built in phase 5. The future-framework adapter `foobench`
    (D.12) at the phase-6 freeze must produce named PROV statements and named, disclosed gaps (DoD Q.3).
  - **AD-16 as ruled.** `requires-python = ">=3.14"` and `.python-version` `3.14`. Release mode refuses archive and
    compressed-stream ingestion below 3.14.8 (phase 2; DoD Q.15a).
- **DoD.** The DoD carries the RESOLUTIONS §4.13 item edits, the AD-08 nuance in the claims lint (Q.11b), the B-2
  defaults (local tags; no deposit; consent for downloads and real-model runs) and B-3 (`docs/architecture/`, Q.21).
- **Challenge boxes.** This section has none to resolve.

The order below departs from the prompt's suggested sequence in three places, and it makes no parallelism claim.

- **The compat oracle comes first.** The transcript/v1 importer and the `adprov-v2.3-compat` profile are built
  *before* the new provenance engine. From day one, every later change is checked against a byte-identical baseline
  (migration gates A1, A2 and B; AD-07).
- **`aer/0.1` and `capture/0.1` freeze at a two-format gate (phase 6; AD-06).** Three importers must map without an
  AER change before SEM, live capture and TraceLogger breadth are built on the schema:
  - the Inspect importer (survey AgentHarm, a structurally different format);
  - the AgentDojo TraceLogger `v0.k11` importer;
  - the future-framework adapter `foobench` (D.12; a self-authored toy format).
- **Live capture moves after the freeze.** The isolated live backends write `capture/0.1` raw evidence, and the
  importer path must already be able to consume it.
- **No parallelism claim (R-46).** The phases are built in order. Phases 8–10 do not depend on one another, but each
  depends on the phase-6 freeze, the phase-5 engine and the phase-3 corpus writer. They are not presented as parallel
  work.

| Phase | Content | Exit gate |
|---|---|---|
| 0. Freeze baseline (**done**) | Tag `agentprov-baseline-2026-10-07` on `579a908` (an annotated local tag; it exists, RESOLUTIONS consolidator check 2). `investigation/baseline/` holds the test results, recompute output, checksums, provenance statistics and 15 golden traces. | 362 passed. Recompute: 0 changed on 17,664 + 18,027. 107,112 checksums OK. Pushing the tag is the user's decision (U-16). |
| 1. Architecture (**Addendum B ratified 2026-10-07**) | Investigation, decision brief (D0–D12, Addenda A and B), spec sections A–Q, adversarial review, `spec/review/RESOLUTIONS.md`, and the r2 fixes applied to every section. | The blocking findings R-01…R-07 are resolved in every section. Addendum B is ratified. The RESOLUTIONS §5 post-edit greps are clean outside quoted history and variant columns. U-01…U-18 are forwarded to the user, and the B-2 defaults apply until the user rules. |
| 2. Bootstrap (A1, AD-01, AD-16) | `AgentPROV-framework/` with git, holding five uv projects. **(1)** Core `agentprov` on Python ≥ 3.14 (the exact pins are in Q.15a and Q.21); extras `live` (`python-dotenv>=1.2.2`), `shacl`, `render` and `dev`. **(2)** `capture/`: `agentprov-capture`, ≥ 3.12, stdlib + `rfc8785`. **(3)** `backends/shared/`: `agentprov-backend`. **(4–5)** Skeletons of `backends/agentdojo/` and `backends/autodojo/`, each with its own `pyproject.toml`, `uv.lock` and Python 3.12 pin; no backend depends on `agentprov`. Repository files: `.gitignore`, `.gitattributes` (`tests/fixtures/** binary`), `.ignore` and `.rgignore`, `.env.example`, a local `.env` that is never committed, LICENSE (MIT) + `THIRD_PARTY_NOTICES.md`, `AGENTS.md`, `CLAUDE.md` (points to `AGENTS.md`), `.claude/settings.json` deny rules, README, and `docs/architecture/` (this specification, B-3). CI: one core job on the latest 3.14 patch and one job per backend project on 3.12. Pre-commit: gitleaks, ruff, `tools/check_unicode.py`. The interpreter guard (`envinfo.py`): below 3.14.8, release mode refuses archive and compressed-stream ingestion, and dev mode warns and records `python_version` and `interpreter_advisory`. Private GitHub repository `AgentPROV`. Pre-push checks: secrets, ignores, large files. uv ≥ 0.12.22 is recommended because it installs 3.14.8. The local uv 0.12.18 cannot, so development proceeds on the newest 3.14 patch it can install (AD-16). | `uv sync --locked` succeeds in all five projects, and `uv run pytest` runs. `prov`, `rdflib` and `pyshacl` import on 3.14. The first push contains no secrets or corpora. The reach of the deny rules is verified (G open question 10). |
| 3. Core | `ingest/`: limits, strict JSON/JSONL loaders, bounded streams, extraction-free archive streaming, names, paths, `quote_untrusted`, `yamlsafe`; archive and compressed-stream ingestion goes through the interpreter guard. `raw/`: store, origins, and `members` (the `expand` stage, AD-12). `aer/`: types for the 13 record kinds, including the generic `activity` and `artefact` (B-1); `canon` + `lex_hints()`; `ids` with the KAT `ex_7uz2oys57hugtsueixylme4fl5`; writer, reader, validator, and the `aer-0.1` JSON Schema. `aer/rules.py` and `aer/rules/aer.rules.toml`. `io/workers.py` + `worker.py` (the rlimited spawn pool, A3). A minimal corpus writer (objects, origins, members, index, register). A CLI skeleton (`import`, `validate`, `info`). | Unit, property and security tests pass. They include the generic-kind checks (backward references only; `aer.activity.shadows_kind`, K.5.1) and the interpreter-guard tests (K.12.12). The schema and the in-code validator agree on generated cases. |
| 4. Baseline bridge | `adapters/adprov/`: transcript/v1 reader + mapper, writing `ext.lex`. `views/transcript_v1.py`: `render(aer) -> dict` and `serialise(dict) -> bytes`; it reads nothing from raw. `views/transcript_v1_fields.toml`. `prov/compat/adprov_v2_3/`: a strict port of `build_prov`, `prov_emit`, `labeling`, `validate` and `conformance`, AST-equal with only import changes, plus the `yamlsafe` shim and `PORT_MANIFEST.json` (R-31). `src/agentprov/migration/`: the lock `migration/baseline.lock.json` and gate G0. | Golden gates pass in CI on all 19 golden pairs from the AER alone: A1 (JCS), A2 (bytes) and B (compat graph bytes). The 19 include the four R-59 (MIG-10) hazard pairs. No test compares with Python `==`. Locally, the same holds on all 35,691. |
| 5. PROV engine, part 1 | `prov/`: engine, evidence, specs, iri, vocab; rules `nodes`, `edges`, `top`; `serialise/provjson`. It derives core and inference bundles, including the Inference-6 closure over named activities. The generic rules G-ACT, G-USE, G-GEN and G-ASSOC (`aprov.g_act@1`, `aprov.g_use@1`, `aprov.g_gen@1`, `aprov.g_assoc@1`; AD-15) supply premises to that closure. Canonical PROV-JSON. `prov/catalogue/agentprov-prov-0.1.toml`. `validate/` tier-4 checks: PROV structure, per-bundle constraints, evidence linkage, the existence-class rule, no `used` of an activity, and mentions only of entities. Never-emit properties NE-1…NE-21; NE-21 covers the generic rules. `vocab/apv-0.1.ttl` (`apv` 0.1.0), copied to `docs/ns/apv-0.1.ttl`. | Every golden v1 AER derives and validates. Synthetic generic-kind fixtures derive their named statements. Gate D passes on the golden set (core and inference bundles). |
| 6. **Freeze gate (AD-06)** | **Inspect importer** `adapters/inspect/` (dialect `inspect.eval`): producer band `inspect_ai 0.3.247.dev69`; zip methods 0, 8 and 93 (93 through stdlib `compression.zstd`); `events_data`, `input_refs` and `attachment://` resolved without fabrication; the D.9 mapping table. **`agentdojo-upstream` `v0.k11` importer** `adapters/agentdojo/` (`dialect.py`, `mapper.py`, profile, `rules/agentdojo.rules.toml`), writing `ext.lex`, plus `render_converted`. Pinned-fetch recipes (`raw/fetch.py`, `agentprov fetch`). **Future-framework adapter** `adapters/foobench/` (FooBench, a self-authored toy format; D.12; DoD Q.3). **`aer/0.1` (13 kinds) and `capture/0.1` (C.13, with `input_at` and `n_messages`) freeze here, with their schemas.** The AER name is settled first (AD-22; U-15). | The 6 survey AgentHarm logs (1,056 samples; git origin `89c4db2c…`) and the TraceLogger fixtures import, derive and validate with no AER change. The six logs need no download: they are held at git `89c4db2c…` (SWEEP_r2 EV-3), and U-07 covers only the Zenodo archives. The D.9 status table (`ToolCallError.type` → `tool_execution.status`, `inspect.tool_error_status@1`) is verified against the `inspect_ai 0.3.247.dev69` wheel. The 18,241 pinned logs at `c274885`, including the 7 Mixtral logs, import with zero crashes. Fetching `c274885` needs the user's consent (U-07); the local AgentDojo clone (`089ed468`) lacks that commit (SWEEP_r2 EV-3). Without U-07 consent this import is recorded `unverified` (never passed), and part `agentdojo` · `2024-06` renders `partial` (R-15; SWEEP_r2 AD-SW22). R1/R2 pass in CI on the golden converted pairs (C01–C09). `tests/adapters/foobench/test_future_framework.py` (K.6.4) asserts the named PROV statements of Q.3 in the core and inference bundles and the named, disclosed gaps of D.12.3(2), with zero changes to the protected set. Any core change the Inspect importer needed is listed. CIABench is used only if the user accepts its licence basis (AD-21; U-04). |
| 7. SEM and assessment | `sem/` (engine, types, validate). The AgentDojo semantics profile `agentdojo.suites`: tool tables per suite version, and a marker normaliser registry for YAML (via `ingest.yamlsafe`), repr and JSON. The assessment bundle (`prov/rules/assess.py`). `prov/compat/semdiff-map.toml` (R-33). | Assessment bundles validate, and the allowed-forms check passes. Gate D is complete on the golden set. Gate E passes on the golden set (the v2.3 → 0.1 semantic diff, generated from `semdiff-map.toml`). The future-framework test (K.6.4) passes end to end, including SEM. |
| 8. Live AgentDojo | `backends/agentdojo/` (pins `agentdojo==0.1.35`) on `agentprov_backend`: the `native` LLM element by default, i.e. stock behaviour recorded by the recording httpx transport plus LLM-span brackets (AD-09); `gateway_compat` (the port of `_CompatLLM`) as an opt-in declared as instrumentation; the pass recorder, executor mirror, runner and worker; `ScriptedTransport`. The `agentprov_capture` writer, hash-chain verifier and redactor. The capture mapper (`adapters/agentdojo/capture_reader.py`, `capture_mapper.py`). `agentprov backends build agentdojo` and `agentprov run agentdojo`: the parent spawns `<env>/bin/python -I -B -m agentprov_backend.worker`, with the environment under `$AGENTPROV_HOME/envs/`, under the T2 controls of AD-13(a). | Scripted cells of real suite tasks are sealed. Live and native-log AER agree on shared fields. The executor-mirror differential passes. Gate C6 passes in the `old-vs-new` job. Real-model runs need the user's keys and consent (U-10) and the AD-13(b) containment. Before any real-model run, the `sandbox-exec` feasibility probe of G.4.10 (G.11.3 open question 12) is run and its result recorded by `agentprov backends build`; if the probe fails, only a dedicated macOS user or a VM is allowed. |
| 9. Live AutoDojo | `backends/autodojo/`, pinned to AutoDojo `aa458794b7eb7f082e94daeac4c0f55bfc0c90cc` and installed in isolation by `agentprov backends build autodojo`. Suite and attack registry; `AUTODOJO_CACHE` handling; transport-level recording around the fork's unmodified LLM element (AD-09). `agentprov run autodojo`. | A scripted (fake-client) cell, one banking task under the `autodojo` attack, is sealed and produces valid AER/PROV. A forced kill leaves the session sealed `aborted` (`appended_by: parent`). A real pilot runs only with the user's keys and consent (U-10), and only after the `sandbox-exec` feasibility probe of G.4.10 has been run and recorded for this backend, as in phase 8. |
| 10. TraceLogger breadth | The `v1.k14` dialect. Profiles for the `agentdojo-upstream` HEAD snapshot (`089ed468`), `rope` (including the AutoDojo-attack slice, `autodojo-via-rope`), `agentdyn` (variant A), `mandate` and `survey-runs`; pinned-fetch recipes. Stretch (AD-10 row 21): DRIFT, AgentDyn B/C. | Per-profile fixtures pass. The `rope` profile applies `rope.security_correction@1`: the corrected `security` values are `recomputed` judgements beside the recorded ones, never in their place, and reproduce the observed counts of D.4.4 (Q.8). Full-snapshot imports are recorded in `docs/reports/` (HON-10); a part without one stays `partial` (R-15). |
| 11. Corpus sealing, statistics and rendering | `corpus/`: layout, `corpus.json`, `executions.jsonl`, `register.jsonl`, `derivation.json`, `validation/`, `checksums.sha256` + root digest, the generated `DATASHEET.md`, and compat outputs flagged `apv:RegressionOracle`. `verify` at three levels (`checksums`, `chain`, `rederive`), including deposit archives verified without extraction (AD-14). `recompute`. Deterministic `package`. `release/`: the deposit draft grouped by licence class (spdx, sorted restrictions) and the Zenodo metadata draft; nothing is uploaded. **AD-10 as ruled:** `stats/` (counts per source and status; PROV statements by evidence class, bundle and rule; unknown-reason proportions; the per-source information-loss table) and `render/` (the baseline `visualize.render_prov_graph` ported to `agentprov-prov/0.1` bundles, core bundle by default; `render` extra). The remaining commands of N.2, 15 in all, including `stats`, `render` and `purge`. | Tamper tests pass. Recompute reports 0 diffs. Two `package` runs give byte-identical archives. The builder refuses mixed licence classes. K.5.11 (stats) and K.5.12 (render) pass, and the CLI tests (K.15) pass. The provisional expand-job CPU and wall budgets of G.4.3 are calibrated with the SEC-07 case of more than 256 MiB of selected members (G.11.3 open question 13). SEC-07 confirms that the post-open ZIP prefix check (`ingest.archive.prefix`, G.3.5) rejects the obs-G8 archive. |
| 12. Hardening | Hypothesis fuzz and security suites (including the G.10 additions); the import-boundary and optional-extras tests; docs: `docs/adapter-guide.md` with the future-framework walkthrough, `docs/threat-model.md`, and `docs/roadmap.md` with every AD-10 deferral and its reason. | DoD Q.15, Q.15a, Q.16, Q.17 and Q.31. |
| 13. Full-corpus regression | Run locally: gates A1, A2 and B over all 35,691; D; E (semantic diff); R1/R2 in full (the claim gate) and R3–R5 (reported). Full-snapshot imports: the pinned `c274885` tree, ROPE, AgentDyn A, Mandate and the survey runs. Per-source evidence-class proportions and information-loss tables from `agentprov stats`. Every figure marked "recompute (phase 13)" is re-derived. | Reports are written to `docs/reports/` (numbers only, no corpora). |
| 14. Manuscript | `3. AgentPROV paper/` (local git): `paper/agentprov_paper.tex`, evolved from `adprov_paper.tex`, with the inherited preamble, references and macro emitter. Figures, tables and macros come from the paper's `agentprov_paper` pipeline (O.3.5): data via `agentprov.api` and `agentprov stats` → values → render → macros. A new compatibility-matrix table and a pipeline figure. The paper environment needs Python `>=3.14` if it imports `agentprov.api`. | DoD Q.24–Q.26 and the claims lint (Q.11b). |
| 15. v0.1.0 release | Update CHANGELOG, AGENTS.md and README. Release-mode steps run on Python ≥ 3.14.8 (AD-16); the user upgrades uv to ≥ 0.12.22 first. Tag `v0.1.0`; the tag stays local until the user decides (B-2). Draft the Zenodo deposit (archives + metadata + DATASHEET), unpublished. A private GitHub release is created only once the user allows the tag to be pushed. | Definition of Done (Q) satisfied. |

**Artefact catalogues (DECISIONS D-12; D.15).** Each importer phase ships its adapter's `artefacts.toml`, the
bespoke handlers and their tests:
- phase 4: `adprov`, both trees;
- phase 6: Inspect, AgentDojo `v0.k11` and `foobench`;
- phases 8–9: the live instance, D.10.9;
- phase 10: the TraceLogger profiles.

The thin shared layer (`agentprov.artefacts`: catalogue schema, safety net, `import --dry-run --artefacts`) lands in
phase 6. `stats --artefacts` lands in phase 11. The per-source reports under `docs/reports/artefacts/` are written in
phase 13 and feed the manuscript (phase 14).

**Deferred from v0.1** (AD-10 as ruled; recorded in `docs/roadmap.md`):
- the analysis frames (`analysis/`) and the ML export (`export/ml/`);
- outcome replay, the historical checkers and the confound probe (gate C4 goes with them);
- `diff`, collections, flattened core documents, stored TriG and lineage documents;
- execution fingerprints;
- DRIFT and AgentDyn B/C beyond the stretch, and the STAC importer.

Until these are ported, the frozen baseline at `579a908` remains the home of the deferred analyses. No feature work
that changes AER, SEM or PROV output may merge while the golden gates fail: A1, A2 and B from phase 4, and R1/R2 from
phase 6 (J.3.7).

# Q. Definition of Done (v0.1.0)

Each criterion is objective and checkable. Results are recorded in `docs/reports/v0.1.0-acceptance.md`. Item numbers
are stable identifiers that other sections cite. Items added after the review carry new numbers (11a, 11b, 15a,
30–33) and sit in their category.

**Architecture**
- **Q.1.** The core packages import no benchmark package, and `tests/boundary/test_import_boundary.py` passes. The
  test also checks three further rules:
  - `agentprov_capture` imports only stdlib + `rfc8785`;
  - benchmark imports exist only under `backends/`;
  - `pyyaml` is imported only by `ingest/yamlsafe.py` (AD-17), and `pydot` only inside `render/` (AD-10 as ruled).
- **Q.2.** `agentprov info` lists every source in section I with evidence availability and implementation status.
  The listing has two axes, gives one row per part, and carries the caveat. The output is generated from the
  registry, which is the only status store, and the README table is generated from the same source. Spec statuses
  are v0.1 targets: the registry shows the gated value, for example `planned` until a part's gates pass (R-15).
- **Q.3.** The future-framework walkthrough (D.12) is implemented as the adapter `src/agentprov/adapters/foobench/`
  (FooBench, a self-authored toy format), tested by `tests/adapters/foobench/test_future_framework.py` (K.6.4). It
  reads a self-authored JSONL format with unseen event types. D.12.2's encodings and D.12.3's gap list bind this item
  (SWEEP_r2 AD-SW4).
  - **Protected set.** The format is imported, derived and validated with **zero** changes to the protected set:
    all of `src/agentprov/` except `adapters/foobench/`, registry entries and generated docs (R-17).
  - **Fixture.** The fixture uses only `aer/0.1` values, including the generic `activity` and `artefact` kinds
    (AD-15). It contains the R-17 event list plus the Addendum B events:
    - a hand-off to a sub-agent recorded in a second file;
    - a planner step that is not an LLM;
    - two human approvals, one `approve` and one `edit`;
    - a memory write and a later read;
    - a screenshot (an image observation);
    - a text-parsed action;
    - a restore/branch;
    - one unknown event (`telemetry`).
  - **Named PROV statements.** The test asserts these by rule id, as D.12.2 encodes them:
    - planner step: G-ACT, G-USE, G-ASSOC;
    - memory write and read: G-GEN and G-USE, plus the Inference-6 `wasInformedBy(read, write)` with `apv:premise`
      (`aprov.comm@1`);
    - screenshot: G-GEN, with the blob digest bound;
    - hand-off: `aprov.spawn@1` `wasStartedBy`;
    - human approval: `aprov.decision@1` for both decisions, and `aprov.authorise@1` (`wasStartedBy(te, -, dc)` from
      `tool_execution.authorised_by`, replacing `aprov.start_tool@1`) for the approved execution.
  - **Named, disclosed gaps.** The test asserts the named, disclosed gaps of D.12.3(2), and that no PROV statement is
    emitted for any of them:
    - the approval with `edit`: NE-18 suppresses `used` of the edited request, and its status is recorded;
    - the text-parsed action: it has no request part, so there is no `used` of a request;
    - the restore/branch: kept in `ext.foobench` of the nearest preceding host record, issue
      `foobench.restore_unmodelled`;
    - the unknown `telemetry` event: kept in `ext.foobench` of the nearest preceding host record, issue
      `foobench.unmapped_event_type`;
    - the observation messages `m5` (the memory snippet) and `m6` (the screenshot): each carries
      `unk {"/generated_by": "not_recorded"}` and the issue `foobench.observation_unlinked` (C.3.15: an activity
      cannot generate a message in aer/0.1).
  - **Specialised kinds first.** Model and tool events never map to `activity`.
  - **Inspect.** The Inspect importer lands with zero core changes, or its core changes are listed and reported in
    the paper. The result is stated as "tested on a self-authored toy format and on the Inspect importer (changes
    listed)".

**AgentDojo**
- **Q.4.** `agentprov run agentdojo` runs the spawned backend worker with a scripted fake model
  (`agentprov_backend.testing.ScriptedTransport`, the `native` LLM element). It produces sealed raw evidence →
  AER → PROV that validates at every tier. Caveat: fake-client tested in v0.1 (R-25); since D-720 the part is
  `partial`, and a real-model pilot ran on 2026-10-22 (working corpora, not sealed; D-722, D-729).
  `gateway_compat` is opt-in and declared as instrumentation (AD-09).
- **Q.5.** The v1 → AER → v1 view passes A1 (JCS) and A2 (bytes) from the AER alone, and the compat graphs are
  byte-identical (gate B; AD-02). These hold in CI on all 19 golden pairs: the 15 baseline pairs plus the four R-59
  hazard pairs (R01–R10, C01–C09). Locally, all 35,691 satisfy the same, and the result is recorded. No round-trip
  test compares with Python `==`.
  - The release gates G0, A1, A2, B, D and E pass (AD-07; J.3; K.20). R1/R2 pass on the golden converted pairs in
    CI.
  - The full R run is a claim gate. Only a 0-mismatch pass licenses "the native re-import supersedes the converted
    tree". Otherwise the converted tree stays a `compat_oracle` part, and the mismatch report is published.
- **Q.6.** The legacy AgentDojo runs import from the pinned `c274885` (18,241 artefacts, including the 7 Mixtral logs)
  through the TraceLogger importer with zero crashes. Fetching `c274885` needs the user's consent (U-07): the local
  AgentDojo clone is at `089ed468` and lacks that commit (SWEEP_r2 EV-3). Without U-07 consent this import is
  recorded `unverified` (never passed), and part `agentdojo` · `2024-06` renders `partial` (R-15; SWEEP_r2 AD-SW22).
  The local `runs/` copy (18,234 files) is used only for gate G0.
  Every file yields either a sealed AER or a sealed record with issues; nothing is silently dropped. The 207 logs with
  empty `messages` are `unit: outcome_only` with the issue `no_execution_observed` (R-28).

**AutoDojo**
- **Q.7.** `agentprov run autodojo` runs in its isolated backend environment with a scripted fake model and produces
  valid AER/PROV. The environment is `backends/autodojo` with the fork pinned at `aa458794…`, built outside the
  repository by `agentprov backends build autodojo`. A forced kill leaves a session sealed `aborted`.
- **Q.8.** The ROPE-hosted AutoDojo-attack runs import and validate. `security_raw` and the ROPE-corrected outcomes
  are kept separate (A6): the `rope` profile applies `rope.security_correction@1`, so the corrected `security` values
  are `recomputed` judgements beside the recorded ones, never in their place, and reproduce the observed counts of
  D.4.4.
  *Evidence (phase 10, 2026-10-10; `docs/reports/rope/`):* all 10,791 ROPE logs import, validate and re-derive; the
  recomputed values cover 198 slack IT5, 260 dailylife IT7 and 220 github IT1 logs (recorded successes 32, 39 and 5; 0, 22
  and 0 after correction), every one beside its recorded judgement; the AutoDojo slice is 2,847 logs (88 recorded and 71
  effective successes).
- **Q.9.** Every limitation is documented in the README and AGENTS.md: the real-model pilots of both live backends
  are pending the user's keys and consent (U-10), and some AutoDojo arms are unreleased. *Since D-720 (2026-10-22):*
  the live parts are `partial`. Real-model runs need consent, and for API endpoints both caps (D-725). The pilot
  of D-728 is pending, and live corpora cannot be sealed yet (D-724).

**External sources**
- **Q.10.** Every requested source has a row in the compatibility matrix (`docs/sources/matrix.md`, a reviewed
  document; AD-10 row 8). Each row gives evidence-based values on both axes, rendered per part or worst-case with a
  `mixed` marker (never best-case), and a justification.
- **Q.11.** Every source part marked *supported* meets four conditions:
  - it has at least one licence-cleared real fixture in `tests/fixtures/`;
  - it has an adapter test;
  - it passes an end-to-end import → derive → validate test;
  - its full pinned snapshot imports with zero crashes, every file is sealed, and the counts are recorded in
    `docs/reports/` (HON-10).

  Otherwise the registry renders the part `partial`, with the caveat "full snapshot not yet imported" (R-15).
- **Q.11a.** All 6 survey AgentHarm logs (1,056 samples) import, derive and validate end to end. They pass through
  the Inspect importer, producer band `inspect_ai 0.3.247.dev69`, from the git origin `89c4db2c…`. No download is
  needed: the six logs are held at git `89c4db2c…` (SWEEP_r2 EV-3), and U-07 covers only the Zenodo archives. They
  form the separate restricted-use corpus `ast-survey-agentharm`, with the use clause in `licences.restrictions`
  (U-05). The fixture is of class `restricted_use` (K.4.2). CIABench counts only if the user accepts its licence basis
  (AD-21).
- **Q.11b.** The claims lint passes over the README, the datasheets and the paper. It is the one library
  `adapters/registry/claims.py`, and it checks the registry status phrases and the I.4 must-not-claim entries. Under
  AD-08 as ruled:
  - "benchmark-agnostic" may describe only the architectural design goal of the core, in design sections (README,
    AGENTS.md, the paper's design sections);
  - every empirical coverage claim uses the registry-generated phrase "adapter-based core; demonstrated on N sources
    in K formats (single-agent, tool-calling traces)", and only after Q.11a passes;
  - "Live Capture" appears in a title only with an approved, sealed, non-`test_only` live corpus (U-10, U-18).

**Provenance**
- **Q.12.** Every core-bundle statement carries `apv:evidenceClass` ∈ {Observed, Derived} plus `apv:rule`, and its
  `apv:sourcePointer` resolves into AER. The evidence-linkage validator passes on all fixtures. The validator also
  enforces the following:
  - the class of a statement is no higher than the existence class (record `ev`) of any of its endpoints (R-22);
  - no `used` object is an activity;
  - `mentionOf` applies only to entities, and activities and relations get `apv:Assessment`;
  - the core declares every node it references (R-21);
  - `hadPrimarySource` appears only for `prov_primary` ∈ {`native`, `byte_derived`}.
- **Q.13.** Property tests show four things:
  - no rule emits `used`, `wasInformedBy` or `wasDerivedFrom` from order alone;
  - no time attribute appears that is absent from AER, and no relation carries a time;
  - `wasInformedBy` is exactly the Inference-6 closure over named activities, each statement with `apv:premise`
    (AD-19), including the activities of generic `activity` records;
  - G-USE emits `used` only for declared `inputs`, and G-GEN emits `wasGeneratedBy` only from `generated_by` (NE-21).
- **Q.14.** Recompute over a derived corpus reports 0 differences. Derivation is byte-deterministic across two
  processes and across worker counts.

**Security**
- **Q.15.** The enumerated security categories, including the G.10 additions, pass:
  - archive traversal labels, symlinks and bombs;
  - deep or huge JSON and duplicate keys;
  - invalid UTF-8;
  - forged digests and manifests;
  - reordered records;
  - prompt-injection strings rendered only through `quote_untrusted`.

  The process controls run in CI and are documented: dependency scanning, pinned-fetch hardening and the release-mode
  interpreter guard. This replaces "every threat in G.2 has a test".
- **Q.15a.** The interpreter policy holds (AD-16 as ruled; K.12.12):
  - `pyproject.toml` declares `requires-python = ">=3.14"`, and `.python-version` is `3.14`;
  - the CI core job runs on the latest 3.14 patch;
  - below 3.14.8, release mode (`--release`, `package --deposit` and the deposit builder in `release/`; `package` in seal
    mode opens no archive, D-62) refuses archive and
    compressed-stream ingestion, and dev mode warns and records `python_version` and `interpreter_advisory`;
  - no override flag exists.
- **Q.16.** gitleaks reports no findings on the repository history. `.env` is ignored and absent from history. No
  corpus or raw store is tracked (`git ls-files` check).
- **Q.17.** `uv lock --check` passes, and osv-scanner runs in CI.
- **Q.31.** Agent hygiene is enforced (R-42):
  - `.gitattributes` marks `tests/fixtures/** binary`, and `.ignore` and `.rgignore` list `tests/fixtures/`;
  - `.claude/settings.json` denies `Read(./tests/fixtures/**)` and `Read(./.env)`;
  - `inspect` shows content only with `--show-content`, and always through `quote_untrusted`.

**Reproducibility**
- **Q.18.** `corpus.json` records every version axis of L.1. There is no SemVer checker: corpus versions are bumped
  by hand and recorded in `CHANGELOG.md` (AD-10 row 10).
- **Q.19.** `agentprov verify` detects every tampering case in the tests, at all three levels. This includes deposit
  archives verified without extraction. `rederive` loads profiles and catalogues only from package resources (AD-14).
- **Q.20.** Two independent `package` runs produce byte-identical archives.

**Repository**
- **Q.21.** These exist and are current:
  - the core uv project with `uv.lock` (`requires-python = ">=3.14"`, `.python-version` `3.14`);
  - `capture/`, `backends/shared/`, `backends/agentdojo/` and `backends/autodojo/`, each with its own
    `pyproject.toml` and `uv.lock`;
  - `.gitignore`, `.env.example`, `AGENTS.md` and `CLAUDE.md` (which points to `AGENTS.md`), `.claude/settings.json`,
    README, LICENSE (MIT) and `THIRD_PARTY_NOTICES.md`;
  - `docs/roadmap.md`;
  - the specification as `docs/architecture/`: `README.md` (index, executive architecture, decision record A + B)
    and one file per section. Addendum B-3 binds over the single `docs/architecture.md` of R-50.
- **Q.22.** The private GitHub repository `AgentPROV` exists and holds the pushed history.
- **Q.23.** Tag `v0.1.0` exists on the release commit. It stays local until the user decides to push it (B-2).

**Manuscript**
- **Q.24.** `3. AgentPROV paper/paper/agentprov_paper.tex` compiles with the inherited class, packages,
  bibliography and macro emitter.
- **Q.25.** Its figures, tables and macros come from the paper's `agentprov_paper` pipeline (O.3.5): data via
  `agentprov.api` and `agentprov stats` → values → render → macros. Prose checks fail the build on any mismatch.
- **Q.26.** Open baseline issues (v2.3 deposited 2026-10-10 per D-900, so only DeepSeek naming, reasoning sentence) are listed in its TODO.

**Corpus**
- **Q.27.** No exported corpus is in Git.
- **Q.28.** A Zenodo deposit draft (archives, metadata, DATASHEET) exists for at least one AgentPROV corpus, marked
  unpublished. The draft is grouped by licence class (spdx, sorted restrictions), and the builder refuses mixed
  classes (AD-20).
- **Q.29.** Corpus lineage (raw origins, pins, duplicates) is recorded in `raw/origins.jsonl` and `corpus.json`.
  The owner of each part is declared once, in its profile's `[lineage]`.
- **Q.30.** The manifest and the index flag compat outputs with `apv:status apv:RegressionOracle` (profile
  `adprov-v2.3-compat`). The CLI prints a notice whenever compat output is written or loaded (R-55).

**Statistics and rendering (Addendum B, AD-10 as ruled)**
- **Q.32.** `agentprov stats` produces the generic tables over a sealed corpus:
  - counts per source, status and `unit`;
  - PROV statements by evidence class, bundle and rule;
  - unknown-reason proportions;
  - the per-source information-loss table (field-group coverage, R-57).

  The output is deterministic, and `stats` writes nothing into the corpus. K.5.11 passes. The paper's
  information-loss table is generated from this output.
- **Q.33.** `agentprov render` renders `agentprov-prov/0.1` bundles, the core bundle by default, through the optional
  `render` extra (pydot + the Graphviz `dot` binary). Without the extra it exits 3 with a typed error. K.5.12 passes.
