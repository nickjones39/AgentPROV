# AgentPROV roadmap: what v0.1 defers, and why

This file records every scope cut of **AD-10** ("Scope cuts for v0.1", RESOLUTIONS R-34, R-45, R-19, accepted as a
block in Addendum B with one deviation) together with its reason, what v0.1 keeps instead, and what would bring the
item back. It is the `docs/roadmap.md` that the specification points to (B.1 status `DEFERRED`, PQ phase 12).

The normative wording of each cut lives in the specification section named in the "Spec" column. When a deferred
item returns, its row here moves to "Reinstated" with the version and the decision that brought it back. Nothing in
this file is a commitment to a date.

**Addendum B's deviation.** Row 1 originally deferred `stats` and `render` too. The architect kept both in v0.1
(Addendum B, AD-10 as ruled): a minimal, generic `agentprov stats` (counts per source and status, PROV statements by
evidence class, bundle and rule, unknown-reason proportions, the per-source information-loss table the paper needs)
and `agentprov render` (the baseline `render_prov_graph` ported to `agentprov-prov/0.1` bundles, core bundle by
default, optional `render` extra). Everything else in AD-10 stands.

**Where deferred analyses run meanwhile.** The frozen AgentDojo-PROV baseline (`579a908`, tag
`agentprov-baseline-2026-10-07`) stays the home of every analysis listed below until it is ported. The old
manuscript stays pinned to that commit (D12).

## AD-10 deferrals

| # | Deferred item | Why it is deferred | Kept in v0.1 instead | Returns when | Spec |
|---|---|---|---|---|---|
| 1 | `export/ml` (ML export, the normative blind view and its leakage test, AD-11); `analysis/{flow,argflow,heuristics,labelling_audit,graph,cache,frames}`; the `diff` command; an `analysis` extra | The baseline's analyses are calibrated on one corpus and one output format, and several rest on visibility-inferred `used` edges that the new semantics no longer emits (B.3 COR-10, COR-16–COR-19, PRV-19). Porting them means re-deriving them against `agentprov-prov/0.1` and the assessment bundle, which is research work in its own right, not a port. | `agentprov stats` and `agentprov render` (Addendum B); the paper owns its frames through `agentprov.api`; `agentprov.prov.diff.diff_documents` for `recompute` diagnostics only | A study needs a deferred analysis on the new corpora; each port reads the assessment bundle (R-34) and takes its tool vocabulary from adapter data, never from a benchmark import | B.3 (COR-08, COR-10, COR-12, COR-14, COR-16–COR-21, PRV-19, DOC-10) |
| 2 | Outcome replay, the historical checkers, the confound probe, `derive --outcome-replay`, gate C4 | Replay executes benchmark code, which the core must never do (invariant 7). An exception mapped to `False` conflated "cannot determine" with "cannot win" (B.3 LEG-08). Doing it safely needs a new isolation design. | Released outcomes as recorded (`by: source`); `agentdojo.record_complete_with_replay@1` reserved, never applied; the v0.1 headline count is 47, not 52 (RESOLUTIONS §1.3) | Reinstated only as a T1-restricted job in `backends/agentdojo` with no keys and no network, inputs named by digest, outputs over the pipe, plus a new threat row T-27 and a specified protocol; results become `ev: "I"` verification annotations | B.3 LEG-07–LEG-11, COR-06; EF E.2; D.15.5 `replay_dispute` |
| 3 | TriG stored and hashed per execution (amends D7's storage, not the capability) | Storing a second serialisation of every bundle doubles corpus size and adds a second byte-determinism surface (the `prov` 3.2.2 TriG path) with no reader that needs it stored. | Canonical bundled PROV-JSON in the corpus; TriG produced on demand by `derive --trig DIR`; the PROV-JSON → PROV-O → PROV-JSON round trip stays a tier-4 check | A consumer needs RDF in the deposit itself | EF E.1, E.5; HL H.8 |
| 4 | Flattened core PROV-JSON (`<ex>.prov-core.json`) | D7 marked it optional; nothing in v0.1 consumes it, and it would be another file under the checksum chain. | Bundled PROV-JSON (core, inference, assessment) | A tool that cannot read bundles needs it | EF E.3.6 |
| 5 | Per-execution lineage documents (`lineage/<ss>/<ex>.lineage.json`) | One more derived file per execution, carrying facts already in the manifest and index. | Compat marking in the manifest and index (`oracles`, gate-report digest, R-55) | Lineage across corpora (row 6) returns | EF E.3.5; HL H.3 |
| 6 | Collection manifests, cross-corpus ownership checks, `verify --collection` | v0.1 builds one corpus per source part; nothing pools corpora yet, so a collection layer has no user. | The owner declared once in the profile's `[lineage]`; `select.owned_elsewhere` keeps a source from being imported twice | Several sealed corpora must be released or verified as one set | HL H.7.5 |
| 7 | Execution-fingerprint deduplication (`agentdojo.tracelogger_efp@1`) | A fingerprint is a heuristic identity across different bytes; it is dialect-specific and must not sit in `corpus/keys.py` (invariant 5). | `source_key` deduplication (same bytes, several origins) plus ownership | Reinstated as a dialect hook, never in the corpus layer, with its own rule and false-merge evidence | D.5 (reserved rule); HL H.7 |
| 8 | `[matrix]` card tables, `[[lineage.edge]]` as profile data, claim tags and the claim gate, matrix renderers | A second status store next to the registry would let the two disagree (R-38, R-45). | Registry status (two axes, per part, caveat) and one claims/lint library; the matrix stays a reviewed document | The matrix outgrows manual review | I.4; D.3 |
| 9 | Datasheet `CLAIMS` registry and a separate card linter | Same reason as row 8: two claim checkers would drift. | One claims/lint library (`adapters/registry/claims.py`); datasheets use generated placeholders only; `validate --card` | — (merged, not just deferred) | HL H.8; I.4 |
| 10 | Corpus SemVer checker (`diff --semver-check`) | Needs the deferred `diff` command and a machine definition of "breaking" for corpora. | Corpus versions bumped by hand and recorded in `CHANGELOG.md` (DoD Q.18) | Corpus releases become frequent enough for manual bumps to slip | HL §0 item 13; DoD Q.18 |
| 11 | Build cache keyed by the derivation key `dk` | A cache keyed on derivation inputs is an extra correctness surface (a stale hit is a silent wrong output). | Resume on the sealed-AER key (D.2.9); `recompute --check` proves derivations | Full re-derivations become too slow on the M5 Ultra corpora | HL H.8.3; D.2.9 |
| 12 | `views/stats`, views in deposits, `corpus.prov.json` (provenance of the release) | Views are derived from AER on demand and need no storage; release provenance was not specified to the level a deposit needs. | Views computed on demand; `derivation.json` records software version and code digest (D-13) | A deposit consumer needs stored views or a release-level PROV document | HL H.8.7 |
| 13 | Ten of the thirteen planned JSON Schemas | Each published schema is a compatibility promise and needs a differential test against the in-code validator. | `aer-0.1`, `capture-0.1` and `corpus-0.1` only, each differentially tested | A consumer needs another schema (SEM, run plan, index) | C.13.9, C.17; HL H.1 |
| 14 | Collection context encoding; AER delta-form `input` | Both change the meaning of pointers like `/input/3` and the edge counts; they are `aer/0.2` changes after the freeze (D-14). | `members` encoding with full input lists (the only `context_encoding`) | The perf smoke (K.17 item 2) shows the members encoding is too large; the edge counts it records are the evidence | C.5.3; EF E.6 |
| 15 | Engine-run inference methods (`aprov.i_arg_literal_overlap@1`) | An inference the engine computes itself is a heuristic inside the provenance engine; v0.1 keeps every inference rule in adapter catalogues. | Inference bundles from adapter I-rules only | A method is specified with its own evidence class, premises and validation | EF E.1.7 |
| 16 | gzip, bzip2 and xz stream codecs; CSV-cell and Python-literal locators and parsing | Each codec is a new decompression-bomb surface (the four-codec SEC-06 suite is written only when a codec is enabled), and Python literals have no safe stdlib parser bounded like `strict_json_loads`. | zip methods 0, 8 and 93 (stored, deflate, zstd) behind the member gate; since D-57 (phase 12b) also a gzip tar nested in a zip, through a bounded gzip decoder and AgentPROV's own tar header parser (never `tarfile`); every other single stream stored inert with `ingest.stream.codec`; JSON and JSONL | A source the user wants ships only as a compressed stream, CSV or Python literals (DRIFT `asb`) | G.3.4, G.3.7; C.9 |
| 17 | T1 isolation of SEM, PROV and validation; double validation | SEM, PROV and validation read only sealed AER written by the core, not untrusted bytes; isolating them costs time and buys little. | T1 for container expansion and parse/map (A3); one T0 write gate; SEM/PROV/validation MAY run in the pool or in-process | A stage starts reading untrusted bytes | G.4.1 |
| 18 | T1 `sandbox-exec`, atheris coverage-guided fuzzing, mutmut, macOS and reverse-order nightlies, 98 % / 95 % coverage floors | Each needs infrastructure v0.1 does not have (atheris on CPython 3.14 / macOS arm64 was not verified; hosted macOS minutes; a coverage baseline). CI has no schedule at all since D-22. | Hypothesis fuzzing (K.11.1) is the fuzz layer; macOS-specific cases (SEC-10, SEC-22) run on the maintainer's machine; a coverage ratchet from the first measured value | A real-model campaign or a release needs more assurance than the Hypothesis layer gives | K.11.3, K.18 |
| 19 | Audit-hook event matrix; a second dependency scanner; a second secret scanner; a struct-only central-directory walker | Each duplicates a control v0.1 already has; two scanners double the triage without a measured gap. | A network-and-subprocess audit hook; osv-scanner plus `uv lock --check`; gitleaks; an EOCD/ZIP64 size check before `ZipFile()` and the other checks after opening | A scanner misses a finding the other would have caught | G.4.4, G.7.2, G.3.5 |
| 20 | PDF byte determinism; `BUILD_PROVENANCE.prov.json` | TeX toolchains embed times and paths; making them byte-deterministic is a toolchain project. | `values.json` and `macros.tex` determinism (the numbers the paper prints) | The manuscript build must be reproducible to the byte | O.0, O.3 |
| 21 | The DRIFT dialect and profile, AgentDyn B/C/history, the STAC importer, the ASB reader | Each needs a dialect or format v0.1 does not parse (DRIFT single-pass, CSV and Python literals, STAC scenario records); the DoD set comes first. | Registry `partial` or `planned` with caveats; DRIFT and AgentDyn B/C are built only after the DoD set (stretch) | After the v0.1 DoD set passes | D.6, D.8; I |
| 22 | The NC partition and per-licence concept DOIs | Deferred with STAC, the only NC source of the original plan. **Changed by D-25 (2026-10-11):** NC sources found by the systematic search are included, each in a separate `-nc` corpus under the `nc_partition` policy; the per-licence concept DOI question remains open. | The builder refuses mixed licence classes (AD-20) | The first `-nc` corpus is packaged (phase 11 onwards) | HL H.5; DECISIONS D-25 |
| 23 | OTel, STS and ATIF exporters | Non-normative formats with no stable specification (OTel GenAI is still "Development"). | AER, SEM and PROV-JSON | A consumer needs one of these formats; exporters then read AER and never feed back into it | C.18 |

## Related deferrals recorded elsewhere

These are not AD-10 rows but follow from them, and are tracked where they were decided:

- **Fuzzing of the `dtap` reader, SEC-15 tamper/verify/deposit cases, SEC-19 corpus dedupe and the SEC-12 render
  cases** wait for phase 11 and phase 10b to merge (phase 12b; `docs/reports/hardening/sec-coverage.md`).
- **Import deferrals** (refused with typed messages: `--spec`, `--prov-spec adprov-v2.3-compat`, `--pipeline`, `.zip`
  `--input`, non-git `--fetch` pins, several snapshots per corpus, `rules/` copies, stored `$blob` payloads for
  imports): AGENTS.md §0 "Known follow-ups" and MN N.2.2.
- **`aer/0.2` and `capture/0.2` candidates** (`decision.replacement`, `scope.forked_after`, `state_change.restores`,
  `message.generated_by` → `activity`, new span and human-input events): D.12.4.

- **The Zenodo upload helper is built, draft-only (D-790, 2026-10-23; D-5, H.10.1(2)).** `tools/zenodo_draft.py` (since
  D-880 the checkout entry of the `agentprov-zenodo` distribution, also reachable from the GUI's Package page)
  creates an unpublished draft from a deposit draft directory, behind `--create-draft`, a typed confirmation and the user's
  own token; the user presses Publish in the web UI. It is a script, not an `agentprov` subcommand, and not part of the
  installed package. Still the user's to do, in their own terminal: a sandbox trial (`--target sandbox`) that confirms
  the file limits and licence ids the helper takes from Zenodo's documentation, then the production draft. Not built:
  deleting inherited files of a new-version draft (the helper never deletes), and any publish call.
- **Option B for `checker_outcome` (restoring D for Mandate's 369 and head v1.k14's 11,236 security outcomes),
  deferred** (user decision, 2026-10-23). It is reconsidered at the end of the release work, depending on the
  post-check. The plan, evidence and cost are in `docs/reports/regeneration/option-b-deferred.md`; Option A (D-359,
  docs only) stands until then.
- **Linux and Windows desktop bundles (GUI G5): built for every platform and released untested; clean-machine
  testing deferred to the Mac Studio** (user decisions, 2026-10-22). The plan is in
  `docs/reports/gui/g5-cross-platform.md` (on main since train 6, 2026-10-23).
  - **Platforms and build hosts:**
    - macOS arm64: built and tested on this Mac.
    - Linux x86_64 (`ubuntu-22.04`, glibc 2.35 floor), Linux aarch64 (`ubuntu-24.04-arm`, glibc 2.39 floor; already used by `ci.yml`)
      and Windows x86_64 (`windows-latest`): GitHub runners, through one manual-dispatch workflow.
    - Windows ARM64: a GitHub Windows ARM runner, if one is available to the repository and PySide6 publishes
      `win_arm64` wheels. Both are unchecked. Until then, the x86_64 bundle runs under Windows 11's x64 emulation.
    - The runners are free once the repository is public. Private-repository runs are blocked by the account's
      Actions billing, and none is attempted before the user fixes it or makes the repository public.
  - **What each build proves:** each bundle passes `build_bundle.py`'s build-time checks (the excluded Qt modules,
    the LGPL notices, the layout) and an automated `--smoke` start of the GUI and the preview helper on the runner, and
    nothing more.
  - **Labels:** the release notes and the guide label every non-macOS bundle **"not tested on a clean machine"**.
    Windows ships unsigned (SmartScreen: More info, then Run anyway); Linux ships as a `.tar.gz`.
  - **Before the first release** (built 2026-10-22, D-750): the fixes users would hit at once.
    - P-3: the job queue refused cleanly on Windows.
    - P-4: Run Live offers only the containment the OS has. `dedicated-user` and `vm` are labelled as declared, not
      enforced.
    - P-7: per-OS `build_bundle.py` checks.
  - **Deferred to the Mac Studio:**
    - the remaining portability fixes (P-1, P-2, P-5, P-6; work in progress kept on branch `gui-g5-held`);
    - the two-level "starts on a clean machine" test for every OS, which removes the "untested" label. The ARM guests
      run in native-speed VMs (UTM). x86_64 needs a native PC or a VM product that runs x86_64 well, since the Mac
      Studio is Apple silicon too.
  - **Downloads:** each needs the user's typed yes (UTM, the OS images, uv and Python, PySide6). The Windows licence
    and the VM product are the user's to settle.
- **Mac Studio M5 Ultra (36 CPU cores, 80-core GPU, 256 GB): tuning when it arrives** (user decision, 2026-10-23). Do
  these together with the clean-machine tests above. None changes corpus bytes: outputs are identical across worker
  counts and machines (invariant 4), and only the archive bytes depend on the recorded zlib version.
  - **Already sized from the host, no change:**
    - the import, derive and validate workers at `--jobs 0` (`host.py`: min(CPUs, 75 % of memory ÷ the per-worker
      cap); about 36 instead of 12);
    - the job queue's budget (`tools/suite_queue.py`: CPUs − 2 and 75 % of memory; about 34 CPUs and 192 GiB);
    - the memory granted to each queued job, which follows the budget.
  - **Hard-coded caps to raise** (class 0; outside every stage scope):
    - **done (tuning session, 2026-10-28):** `tools/suite_queue.py` slots scale with the CPU budget (1 suite,
      max(2, budget/5) import, max(2, budget/8) rehearsal: 1 / 6 / 4 here), `$AGENTPROV_QUEUE_SLOTS` overrides them,
      and older copies share the queue safely;
    - **done (tuning session, 2026-10-28):** `corpus/withhold_scan.py` and `cli/render.py` (`min(4, CPUs)`) and
      `migration/gate_d.py` (`min(8, CPUs)`) take the host default worker count; `tools/ci_local.py`'s gate takes
      `-n 24` here (two thirds of the CPUs, at least 10; `$AGENTPROV_SUITE_WORKERS`);
    - **done (AGENTS.md §8):** session habits rather than code: `--cpu` follows `--jobs` on queued imports instead of
      `--cpu 4`, `-n 24` for a full suite, `D358_CPU=16` for `tools/regen/d358_building_commit.sh`.
    - not yet: `withhold_scan` reads its archives one at a time (`run_one`), so its worker count does not
      change its speed (72 archives: 30.9 s at 4 workers, 29.4 s at 36); a parallel walk is a follow-up.
  - **Calibrate on the machine** (commands, not code):
    - `run --tune-jobs` with the oMLX models (built 2026-10-28, D-820..D-823; the measurements wait for the user's yes).
      Then bump the `m5ultra` preset in `src/agentprov/presets/presets.toml` (its live-cell caps 8 / 6 / 4, server
      concurrency 8 and reserves are provisional, taken from M3 Ultra benchmarks) to a new version with the measured
      values and `cell_seconds` rows for the local estimate (D-826). Corpora keep the preset version they recorded;
    - ~~the host capability probes~~ **met by the move (D-824):** they are probed live in every process, and on the
      Studio `--m5ultra` dry runs no longer warn;
    - the memory-watchdog allocation rate (D-825): it is **measured in every process** (the 4 GiB/s default is only
      the fallback). What is left is recording the Studio's figures (20 probe runs) beside the M2 Max's in the docs;
    - ~~the estimate priors~~ **no rebuild needed (D-826):** their seconds are the durations recorded in the source
      logs, not this machine's time, so a rebuild gives the same rows;
    - rebuild the backend environments (AgentDojo, AutoDojo, AgentDyn, Inspect AgentHarm) there; don't copy them.
  - **Not needed:** the pipeline is CPU-only and never uses Metal. The GPU and the memory matter only to local models
    through oMLX.
  - **Expected speed-up** (estimate, unmeasured): about 4–8× on machine-bound work, such as imports, suites, priors and
    the regeneration round. About 1.5× on steps that run one after another, such as the gate chain and corpus
    writing.

## Planned for v0.2

Recorded by the user's decision on 2026-10-29. v0.1 releases import corpora only. Live capture is supported and tested
in v0.1, but no live corpus can be sealed yet.

- **Live sealing: `agentprov-corpus/0.3` with a closed live block** (pre-release decision U-7, change C-6). Today
  `package` refuses a live corpus (`package.unsupported.live`) and every sealed manifest writes `"live": null`. The
  published `corpus-0.2` schema defines 8 live keys (`LIVE_BLOCK` in `corpus/manifest.py`), but a working live corpus
  carries about 25: the transport, the endpoint, plan and config digests, local models, served model ids, caps,
  egress (D-664), quality and attack caches. Sealing the round-1 corpora froze the `corpus-0.2` schema bytes, so the
  closed block needs a new format version. The work:
  - decide which live facts a published corpus carries (privacy versus reproducibility);
  - write the `corpus-0.3` schema;
  - let `package` seal `mode: live` and refuse `test_only` corpora;
  - add live sections to the datasheet (models, endpoint kind, containment, consent, caps);
  - make the release scan handle wire logs;
  - extend `verify`, add tests and update the spec.

  Class 0 (`corpus/` and the schema are outside the stage digests). Details: `docs/reports/release/pre-release-checks.md`
  section 6.
- **A sealed live corpus (the live capture campaign).** Real-model runs with the calibrated `m5ultra` v2 preset
  (D-823; local models through oMLX at 4 jobs), for example AgentDojo with and without the registered defences, then
  the pre-release checks and sealing as for round 1. API models only with the user's caps and consent.
- **Related live follow-ups:**
  - live AER records `mono_*_ns` but no `t.dur_s`, so `estimate --stats-corpus` gets no time from live corpora
    (calibration report section 4);
  - the live-run code drops a dead worker's reason and log (`worker_died`; seen on Windows x64 in G5);
  - the 15–40 B and > 40 B preset classes are not measured yet.
- **PROV that grows with the square of the model calls** (DTap finding F-12, 2026-10-29). Each model call `used` every
  message in its context (with Inference-6 `wasInformedBy`), and the assessment bundle states an `ExposedTo` and a
  `PotentiallyInfluencedBy` per request × untrusted context member (E.7.3). So a run's PROV grows as calls²: in DTap,
  168 calls give 68.7 MB, 210 give 103 MB and 778 give about 1 GB, from AER records of about 1–1.6 MB. Tier-4
  validation needs about 80× the PROV size in memory. v0.1 raises the limits for engine-produced PROV per source
  (D-935), which recovers all but the 778-call run. That run is recorded as a size limit in the datasheet, not
  excluded for its outcome. The v0.2 fix is a linear context representation, for example incremental context
  collections referenced by each call, with the assessment pairs stated per collection. It is a class-2 PROV semantics
  change, with a rule-catalogue version bump and its own decision. It also shrinks deposit sizes.
- **Recompute on a sealed tree reports, never crashes** (wave-2 pre-release checks, check 7, 2026-10-30; option (b) of
  the user's choice, deferred). D-358 after the wave-2 seal could not run on 10 of the 43 sealed trees. On these the
  evidence is the pre-seal recompute at the building commit plus `verify --level chain` (option (a)):
  - nine exit 70 with `adapter.archive_input` because the seal withheld their stored input archive (`autogen-guard-placement`,
    `code-agent-misalignment`, `ipi-defenses-agentdojo`, `agentops-bench`, `seagent-agentdojo`,
    `redcode-exec-openhands`, `dca-agentdojo`, `authority-caps-agentdojo`, `credleak-p15b`);
  - `controlarena-persistent`, sealed metadata-only, exits 70 with a `KeyError` on a withheld object's digest.

  The fix: an execution whose input archive or raw object is withheld is counted `unverified` (H.4.5(6)), as for a
  withheld member object, and the run goes on. The exit-70 refusal is raised in the importer
  (`adapters/runner/importer.py`, inside the AER stage scope), so the byte class depends on where the fix lands: class 0
  if `corpus/derive.py` accounts for the withheld input before the re-map. The fix needs a test on a sealed fixture with
  a withheld archive and a withheld object. (The third case, `mcphunt`'s `corpus.derive.limits_mismatch` on a sealed
  manifest with no `limits` record, is fixed in v0.1 by D-1001.)

  A related gap showed in DTap's D-358 after its seal (`dtap-bench-w2c`, 2026-10-30): a re-map of a sealed tree can
  produce units the corpus never had. `Derivation.exclude_absent` drops the withheld objects and the inputs that only
  unverified executions use (RC-13), by sha256. Two cases are left over:
  - path instances of a kept object: a judge file whose content other runs share stays, although its own run's
    trajectory was dropped;
  - the files of a withheld execution: it has no released row, and `WITHHELD.json` does not list its raw references,
    so its own supporting files stay.

  In DTap, 8 judge files were left beside a dropped file. The re-map selected each as an outcome-only unit
  (`map.no_execution_observed`), and the selection's duplicate handling changed 117 `register.jsonl` rows and 4
  `raw/origins.jsonl` rows that concern their paths. Every execution present in both trees was identical. The fix:
  `exclude_absent` also drops the path instances in a dropped file's unit directory, and a withheld execution's files.
  It belongs in `corpus/derive.py`, outside the stage scopes (class 0), with a test on a sealed DTap-shaped fixture
  (a run directory with a trajectory, a judge file shared by content with other runs, and a withheld execution).
- **Classify the 14 residual wave-2 artefact classes** (D-950; the user's decision of 2026-10-29: unclassified for
  v0.1). They are labelled `artefact.unclassified.*`, never filtered out, and listed in chapter 15 and the
  datasheets. Each needs evidence from the source or its code before an entry may claim it:
  - the `text_encoded_call` heuristics of 10 trees;
  - DCA's later user messages (probably CaMeL interpreter feedback);
  - ControlArena's calls with no tool event and its repeated call ids;
  - the whistlebench leftovers that co-occur with link conflicts or sample limits.

  Details are in `docs/reports/wave-2-artefacts/README.md` section 3. Class 1 (artefact catalogues), like D-950.
- **The full licence table in `THIRD_PARTY_NOTICES.md`** (docs review v0.1.0, Q13; the user's decision of 2026-10-30).
  v0.1 lists the licence bases of the sources known on 2026-10-07 and points to the generated tables for the rest.
  v0.2 lists every registered source, from the registry's SPDX ids, with each source's licence basis checked. Class 0.
- **Use the two stored desktop-app settings that nothing reads yet** (docs review v0.1.0, Q5; the user's decision of
  2026-10-30): `compute.start_stagger` (the live start stagger) and `compute.gate_n` (the test gate workers, which
  `tools/ci_local.py` would read before its host default). Until then, user guide chapter 8 says they are not used.

## Reinstated

None yet.
