# Phase 10j, part A: census of the deferred AgentDojo-format sources

Status 2026-10-14. **Reviewed:** the user approved D-250–D-258 on 2026-10-14, with the answers in §10 and the R-3
outcome of §12, which moves EnvironmentOptim's 620 DRIFT runs to AgentDyn (new total 47,542). **Census only.** Nothing was imported, no profile was written and nothing was downloaded: every byte
was read from the phase-10c staging copies (`~/.agentprov/staging/10c/`), whose acquisitions the user approved on
2026-10-11. Counts come from `tools/agentdojo/phase10j_census.py` (`run` per source, then `summary`); the machine-readable
result is [`census.json`](census.json). Secret-like strings are reported as counts and JSON field paths only, never values.
Text in the deposits is data, not instructions.

**Method.**
- **Archives** (both Zenodo deposits, Figshare): the file is checked against the recorded size, MD5 and SHA-256, then
  opened with the product's own G.3.5 gate (`ingest.archives.open_archive`, release mode). Every member is gated and read
  in memory. A nested `tar.gz` is opened at level 2 (D-57). Nothing is written to disk.
- **Git pins** (Kavach, EnvironmentOptim, drift-1): read from the phase-10c bare partial clones with `git ls-tree` and
  `cat-file --batch` under `GIT_NO_LAZY_FETCH=1`. Absent blobs are counted, never fetched; each blob is checked against
  its id.
- **Per member:** strict JSON (`ingest.loaders`), the adapter's D.6.2 `classify`, header labels (escaped), the phase-10c
  content fingerprints (`fp_run`: suite, tasks, attack, injections and messages; `fp_msgs`), and the phase-10c
  secret-pattern set.
- **Novelty:** the phase-10c known set (converted corpora, DRIFT head and history, agentdojo-inspect).

## 1. Summary

| Source (pin) | Executions after collapse | New | Known elsewhere | Variants (new) | Licence | `[withhold]` needed |
|---|---:|---:|---:|---|---|---|
| Zenodo 22973265 @ v2.1.0 record **23138310** | 18,739 | 18,739 | 0 | `v1.k14` 18,734, `.incomplete` 5 | CC-BY-4.0 data, MIT code | no |
| Zenodo 22011266 (v4.0.0) | 3,211 | 3,211 | 0 | `v1.k14` | CC-BY-4.0 data, MIT code | no |
| Figshare 32657856 (v1) | 16,221 | 16,221 | 0 | `v1.k14` 13,374; `drift.k18.conversations` 2,847 | MIT (+ third-party notices) | no |
| Kavach (three branch pins) | 2,625 | 2,625 | 0 | `v1.k14` 2,620, `.incomplete` 5 | MIT | no |
| EnvironmentOptim @ `febf82d8` | 6,120 | 6,120 | 84,360 (not imported) | `v1.k14` 6,120 (6,016 held, D-255) | MIT | no (see §8) |
| drift-1 @ `0e28729b` | 626 | 626 | 1,569 (not imported) | `drift.k18.conversations` 626 | MIT, README badge only (D-93) | no |
| **Total new** | | **47,542** | | | | |

- Every count in the brief is reproduced: 18,739; 3,211; 11,406 + 1,968 + 2,847; 2,625 (about 957 by content); 620 new
  DRIFT runs plus 4,258 copies (and 6,120 new `v1.k14`); 626 (616 + 10 PACT).
- **The product reads all of it today.** The gate selects every member of the three archives in release mode, with 0
  rejections, and no limit is reached:
  - the 3,866 Figshare labels with `:` pass (D-56);
  - the six nested `tar.gz` containers open at level 2 (D-57): three in 23138310 and three in 22011266. This is the
    first check of 23138310's containers, which D-57 recorded as unverified. They hold 19,212 members, with no pax
    header refused;
  - Git: every log blob is present. The absent blobs (drift-1 44, Kavach 8, EnvironmentOptim 1,722) are figures and
    documents, never logs.
- **No new download is needed** for any part of this phase.

## 2. Zenodo 22973265 (concept): one corpus at record 23138310 (v2.1.0)

- **Record and pin.** Record 23138310 (v2.1.0, 2026-10-04) publishes `agent-authority-caps-v2.0.0.zip`
  (40,160,657 B, MD5 `3fba8031…`, SHA-256 `1dce0380…`). This is the same file as record 22996368 (v2.0.0), plus
  supplementary PDF, DOCX, CSV and PY files that hold no runs.
- **v1.0 is contained in it.** All 2,813 v1.0 logs (record 22973266) are byte-identical members of the v2.0.0 zip, so one
  pin covers the concept; v1.0 is recorded as lineage.
- **Members.** 22,250 in all: 3,041 at level 1, 19,212 inside `original-study/experiments/reexecuted_caps/runs_exp4.tar.gz`,
  `templates_and_autoconfirm/runs_exp5.tar.gz` and `raw-additions/runs_exp7.tar.gz`.
- **Logs.** 21,999 TraceLogger members collapse to 18,739 executions (the importer's `dedup.collapsed`, H.7.2). The 3,260
  byte-identical copies are runs the authors re-packed into several experiments:
  - `gpt-4o-mini-2024-07-18` in exp4, exp5 and exp7 (1,506 copies);
  - the `current_models/runs/` arms again inside exp5 (gpt-6-luna 753, gpt-6-sol 753, two autoconfirm arms 124 + 124).
  Content repeats with different bytes: 4 groups only.
- **Arms**, one pipeline directory each (logged `pipeline_name` equals the directory everywhere):
  - models: `gpt-6-luna`, `gpt-6-sol`, `claude-haiku-4-5-20251001`, `gpt-4o-mini-2024-07-18`, `gpt-3.5-turbo-0125`;
  - suffixes: `-autoconfirm` (harness auto-confirms the agent's questions), `-capA3` and `-capA4` (enforced authority
    caps: a runtime tool filter), `-noegress` (no-egress filter), `-rep1..3` (repetitions);
  - experiments: current models, pilot, exp4 re-executed caps, exp5 templates and autoconfirm, exp7 no-egress and repeats.
- **Attacks.** `important_instructions` 9,656, `authority_notice` 1,887 (the new attack), `tool_knowledge` 1,258, and
  eight further AgentDojo attacks with 629 each; 2,164 benign.
- **Header fields.** `benchmark_version` `v1` everywhere; `agentdojo_package_version` `0.1.35`; 51 run errors; one system
  prompt, AgentDojo's default (`a021a92b…`, 469 characters).
- **Licence.** The README and `original-study/LICENSE-DATA` put the data under CC-BY-4.0 (fields derived from AgentDojo
  logs stay MIT), and the code under MIT (`LICENSE-CODE`, © 2026 Liang-Cheng Chang). The record licence is cc-by-4.0.
- **Identity.** `pipeline_name` names the model plus a condition suffix, so it needs a table keyed by pipeline
  directory (D-104), one row per directory, with the condition as defence or harness setting. (As built and recorded in
  D-250's addendum of 2026-10-21: the experiment is no key, because the re-packed copies span experiments.)
  - The deposit's `RESULTS_new_models.md` states that GPT-6 Luna and GPT-6 Sol ran with `reasoning_effort=none`
    (an `ext` note, not identity).
  - `gpt-6-luna` and `gpt-6-sol` are logged without a snapshot date and stay as logged.
- **Secret-like strings:** none in any member, including the nested ones.

## 3. Zenodo 22011266 (v4.0.0): inclusion re-checked, stays included

- **Members.** 3,234: 26 at level 1, and 3,211 logs in the three nested tars
  `traces_run1_mini_pdef`, `traces_run2_mini_rerun` and `traces_frontier_verify`.
- **Logs.** All 3,211 are byte-distinct and new; 3,171 are distinct by content. The 40 content repeats are mostly
  `tool_filter` runs that re-ran identically in runs 1 and 2.
- **Design.** Banking only. Models: `gpt-5.4-mini-2026-03-17` 1,690, `gpt-5.4-2026-03-05` 845, `claude-sonnet-4-6` 676,
  the API snapshots the README lists. Five AgentDojo defences by directory: none, `spotlighting_with_delimiting`,
  `repeat_user_prompt`, `transformers_pi_detector`, and `tool_filter` (OpenAI models only).
- **Header fields.**
  - `benchmark_version` is `null` in all 3,211 logs, so it stays `not_recorded` (D-102).
  - System prompts: AgentDojo's default, plus the spotlighting variant (`2954962b…`) in exactly the 676 spotlighting logs.
- **Re-check of the inclusion criteria.** The logs are per-run trajectories (IN-1); the data are CC-BY-4.0 (README:
  "Code: MIT. Data and documentation: CC BY 4.0"); 3,211 runs pass the size rule; the deposit is pinned by DOI and MD5;
  the product reads it today; nothing overlaps another source. **It stays included.** The README's own limitations go
  into the profile and datasheet:
  1. A runner defect overwrote some first-run cells, and the deposit ships only the per-cell traces that survived.
     Every directory here holds a complete 169-run cell.
  2. The PI detector's Hugging Face revision is not pinned.
  3. Runs 1 and 2 re-evaluate the same instances.
- **Open, optional.** Whether a version newer than v4.0.0 exists needs a Zenodo metadata query, which is network access
  and needs the user's yes. The phase-10c metadata (2026-10-11) lists v4.0.0 as the latest.
- **Secret-like strings:** none.

## 4. Figshare 32657856 (DCA artefact v1)

- **Pin.** `DCA_AgentDojo_artifact_v1_20260612.zip` (54,196,099 B, MD5 `26a3a972…`, SHA-256 `ed500ca3…`; Figshare
  file 65496114). The product has no `figshare` pin kind. A `url` pin (`url`, `sha256`, `md5`, `size`) passes
  `raw.fetch.verify_download`, but **correction (part B):** the runner takes archive inputs from `zenodo` and `hf` pins
  only (`DOWNLOAD_PIN_KINDS`), so the import needs a runner change after all (routing R-10j-3). Until it lands, the logs
  are mapped by the census under the `member` origins an import would give them.
- **Members.** 16,346, all at level 1; 16,221 logs (13,374 `v1.k14` and 2,847 `drift.k18.conversations`), all
  byte-distinct and new; 3,866 labels contain `:` (1,968 `v1.k14` and 1,898 DRIFT). Content repeats: 15,196 distinct by
  content. The 1,025 repeats are mostly CaMeL against CaMeL+secpol (765), where the policy did not intervene, and the
  direct Qwen3.6 run against DCA (243). They are separate runs with different bytes, so they are kept and disclosed
  (`content_dedup = never`).
- **Arms.**
  - Direct: gpt-4o-mini, `openai_gpt-oss-20b` (OpenRouter), and `local` twice (Qwen2-7B and Qwen3.6-27B through
    Ollama).
  - DCA: `-causal_budgeted` (three models).
  - Clean: 97 benign runs per arm.
  - CaMeL and CaMeL+secpol: three models.
  - DRIFT: gpt-4o-mini, `gpt-oss:20b` and `qwen3.6:27b`, 949 each.
- **Header fields.** `benchmark_version` `v1.2.2`; 4 run errors. 8,751 logs have no system message: all 5,904 CaMeL logs
  and all 2,847 DRIFT logs. 4,274 end with a `null` assistant content.
- **Identity (D-92).** The deposit README states every model:
  - GPT-4o-mini-2024-07-18 through the OpenAI API;
  - GPT-OSS-20B through OpenRouter (`openai/gpt-oss-20b`);
  - Qwen3.6-27B through local Ollama for the attacked rows;
  - Qwen2-7B through local Ollama for the direct model-sensitivity rows.
  So the two `local` directories (`direct_agentdojo_qwen2_7b_ollama_*`, `*_qwen36_27b_ollama_*`) get class-I rows citing
  the README. The DRIFT arm's logged `gpt-oss:20b` is an Ollama tag, while the README says OpenRouter: the row asserts
  the model and leaves the route unrecorded (question Q7).
- **DRIFT part (2,847).** It is **included** and registered for mapping by the DRIFT build (RT-7; D-279 addendum), never
  `select.dialect_planned`. The DRIFT dispatch (RT-1, regen-batch item 22) is on main. Every phase-10l count reconciles
  (2,847 files, `v1.2.2`, 949 per arm, 0 attacks succeed). The datasheet may state the 0 of 2,847 as context.
- **Licence.** The record is MIT; `third_party_licenses/` carries AgentDojo (MIT), CaMeL (Apache-2.0 text) and DRIFT/ASB
  (MIT).
- **Secret-like strings:** none.

## 5. Kavach: one corpus with three snapshots (D-95, D-202)

| Pin | Logs | Byte-distinct | Distinct by content |
|---|---:|---:|---:|
| `main` 53df9545 | 223 | 223 | 166 |
| `nav-fixer2` f2dd7efa | 1,518 | 1,477 (41 byte repeats inside the pin) | 884 |
| `rearch-forcedformat-fix` 6b31a554 | 1,518 | 1,518 | 956 |
| **union** | | **2,625** | **957** |

- **Overlap by bytes.** `main`'s 223 are in all three pins, 147 are shared by the two branches only, and 1,107 and 1,148
  are branch-only.
- **Overlap by content.** 650 groups (2,318 files) are the same trajectory in different bytes: the branches re-serialise
  one experiment.
- **Import plan.** Imported as one corpus with three snapshots in the order main, nav-fixer2, rearch-forcedformat-fix.
  Byte repeats collapse (`dedup.collapsed`, `n_origins`); content repeats stay separate executions (`content_dedup =
  never`) and are disclosed with their counts in the profile, the registry caveat and the datasheet.
- **Identity.** The logged `pipeline_name` is `local` or `local-kavach` (the Kavach defence arm) everywhere, so the model
  must come from the directory or a record. Evidence per directory:
  - `agentdojo_summary*.json` in four run directories records `model_id = gemma4:26b`: `agentdojo_slack_gemma_dell`,
    `agentdojo_workspace_forced`, `_not_forced` and `_not_forced2`.
  - `REPRODUCIBILITY.md` says "Gemma4 27B via Ollama" for the Dell. That conflicts with the summaries; the row uses the
    run record's `gemma4:26b`.
  - The run guide names `llama3.1:8b` as the laptop model but no run directory.
  - `agentdojo_dell`, `agentdojo_llama3.1`, `agentdojo_forced_llama3.1`, `agentdojo_workspace_forced2`,
    `results_v2/logs` and `agentdojo_live/banking_qwen25_7b` have no record that names the model (question Q4).
- **Source-declared invalid run.** The authors mark `benchmarks/results_v2/agentdojo_slack_gemma_dell/` invalid
  (`INVALID_README.md`; handoff of 2026-07-06): a harness defect echoed tool results back to Gemma, so neither arm
  measured anything. These are 220 logs, the whole of `main` except 3 (question Q3).
- **Other features.** A custom system prompt (`2e867516…`, 1,225 characters) in 1,515 logs, to be labelled by digest
  with the file that holds it (D-109). `benchmark_version` is `null` in 1,515 logs (D-102).
- **Licence.** MIT (© 2026 Kavach Team, PES University), the same at all three pins.
- **Secret-like strings:** none in any log. Hits exist only in non-log files the profile will not select (pattern
  corpora such as `VAULT/patterns`, and test descriptions: `private_key` headers 9-10 files, `openai_sk` shapes 2-4,
  `anthropic_sk` 2 at `main`). A git pin stores only selected blobs, so no `[withhold]` is needed.

## 6. EnvironmentOptim @ febf82d8

- **What it holds.** 93,042 blobs; 90,480 TraceLogger logs, all byte-distinct. Only 6,740 are new. The other 83,740
  are known elsewhere (`v1.k14` 49,384, `v0.k11` 30,098, DRIFT 4,258). No directory mixes new runs with copies, so the
  copies can be excluded by directory glob, `select.owned_elsewhere`, never mapped and never stored. By phase 10d's
  split, they are:
  - copies of upstream AgentDojo `runs/` (36,679, owner `agentdojo-upstream`), in `runs/dojo_*`;
  - copies of AgentDyn (47,061, owner `agentdyn`) under AgentDyn's directory names, including the 4,258 variant-C DRIFT
    copies in the seven `*-drift` directories other than `gpt-4o-mini-2024-07-18-drift`.
- **New `v1.k14`: 6,120,** all benign (`attack_type` `null`), all seven suites:
  - 104 `gpt-5.4-2026-03-05`;
  - 6,016 local Qwen3.5 runs in about 140 arm directories: baselines `qwen3_5-{2B,4B,9B}_baseline(_train)`;
    `benign_injection/…/checkpoint_N/{256,320,512}` (benign images); `soft_image_prompt/…`,
    `soft_language_prompt/…` (soft prompts, seeds, RLVR rollouts, ablations); `text_prompt/{system,user}/prompt_N`;
  - one directory nests a level deeper (`benign_injection/checkpoint_4/256/<model dir>/workspace/…`, 13 logs).
- **Not new after all: the 620 DRIFT runs** in `runs/gpt-4o-mini-2024-07-18-drift/` are AgentDyn's own superseded
  generation (§12, R-10j-2): `select.owned_elsewhere`, owner `agentdyn`. Before that check: variant C (`messages`). Phase 10l mapped them all
  (620/620 valid with a stand-in profile). They need EnvironmentOptim's own identity row (RT-8): AgentDyn's row for that
  directory is a variant-A row and raised `agentdojo.pipeline_name_mismatch` on all 620.
- **What the checkpoints are (the RT-8 ruling, question Q1).** The README states that the agent's model in all
  experiments is Qwen3.5-9B and stays frozen: the thesis optimises nudges in the environment (soft language prompts,
  soft image prompts, benign images, text prompts). So `checkpoint_N` is a checkpoint of the **trained payload**, not
  of the model. The arm (payload kind, checkpoint, image size, seed, rollout) is a condition of the run, and the agent
  model is Qwen3.5-9B by the README. The `-2B` and `-4B` baselines log a model path ending `qwen3_5-2B`/`-4B`, which no
  document states as a model.
- **Interpretation for the datasheet.** These are benign-utility runs of a thesis on environment optimisation, not attack
  runs. The intervention (a soft prompt or image embedding) reaches the model outside the logged messages, so the AER
  cannot show it; this is a disclosed limitation.
- **Account path in the logged name (question Q2).** The 6,016 local runs log `pipeline_name` as a munged cluster home
  directory path that includes an account segment (`_ceph_ssd_students_<account>_qwen3_5…`). The agentdojo mapper
  copies `pipeline_name` verbatim into `ext.agentdojo.pipeline_name`, and the family has no redaction (D-182 covers the
  Inspect family). D-186 (c) lets the raw bytes ship as they are, but D-182 redacts AER copies.
- **Licence.** MIT: the README badge and the repository `LICENSE`, whose text is AgentDojo's MIT notice. The README says
  the thesis contributions are `optimization/` and the new `runs/` subdirectories.
- **Secret-like strings.**
  - One new log (DRIFT) holds a bare `-----BEGIN … PRIVATE KEY-----` header in two strings, an assistant content and a
    tool content, with **no key body and no footer**. This is the EnvironmentOptim file of RT-10 that is not an AgentDyn
    copy.
  - The other 110 matching logs are copies owned by AgentDyn (21 `v0.k11`, 85 `v1.k14`, 4 DRIFT). They are not stored
    by this profile. Among them, 5 complete key blocks occur in 2 files each: four have bodies of 0-54 characters (no
    key material), and one is a 1,390-character OPENSSH block. RT-10's AgentDyn
    `[withhold]` decision stays with AgentDyn's profile owner.
  - Two non-log files have header matches; they are not selected.

## 7. drift-1 @ 0e28729b

- **What it holds.** 2,195 DRIFT logs (`conversations`, `benchmark_version` `v1.2`). 1,569 are byte copies of DRIFT head
  in `runs/gpt-4o-mini-2024-07-18/`: `select.owned_elsewhere`, owner `drift`.
- **New: 626.**
  - 616 in `runs/gpt-4o-mini/`, with initial-plan semantics;
  - 10 PACT-DRIFT files in `runs/pact-gpt-4o-mini-banking10/` with six extra top-level keys (`argument_validation_events`,
    `global_tool_contract_path`, `pact_drift_decision_summary`, `pact_drift_enabled`, `provenance_records`,
    `task_contract`). They carry 9 CALL ERROR texts that match neither DRIFT check (`drift.call_error_unrecognised`).
    The PACT arm stays in (RT-6 withdrawn).
- **Identity.** The logged `pipeline_name` is `gpt-4o-mini`, with no snapshot, for all 626. The PACT directory name
  differs from it, so it needs an identity row.
- **Licence.** MIT by README badge only; there is no LICENSE file (D-93).
- **Secret-like strings:** one `hf_` shape in a non-log file, not selected.

## 8. Withholding (D-230–D-237, D-450)

**No source needs a `[withhold]` table on this census.**
- **The three deposits:** 0 matches in any member, nested members included. So D-450's decoded scan has nothing to find,
  and with no byte rules it does not run.
- **Kavach and drift-1:** their matches are only in files the profiles do not select, and a git pin stores only
  selected blobs.
- **EnvironmentOptim:** its one new file has a header with no key material, the shape the release scan's private-key rule
  does not match. Recommendation: no `[withhold]`; disclose the count in the profile. Should the user prefer a
  precautionary rule, `private-key-header` (as in the controlarena profile) would withhold that one file's raw object
  at object level.

## 9. Decisions D-250–D-259 (user decision 2026-10-14: approved; see DECISIONS.md, where D-254 and D-255 carry the R-3 amendment)

- **D-250. Zenodo 22973265: one corpus `authority-caps-agentdojo` at record 23138310 (v2.1.0).**
  - Pin: kind `zenodo`, `record` 23138310, `version` "2.1.0", the v2.0.0 zip.
  - v1.0 (22973266) is recorded as contained lineage, not pinned.
  - All three nested tars are declared; 18,739 executions; 3,260 byte copies collapse.
  - Identity table keyed by pipeline directory (D-250 addendum, 2026-10-21), with the suffix conditions as defences
    (`authority_cap_a3`, `authority_cap_a4`, `no_egress`) or harness settings (`autoconfirm`, repetition).
  - **Rejected:** pinning v1.0 too (all of it is inside v2.1.0); one corpus per experiment (one deposit, one licence,
    one pin).
- **D-251. Zenodo 22011266 stays included as `ipi-defenses-agentdojo`.**
  - Defence by directory (D-104); models from the logged API snapshots; `benchmark_version` `not_recorded`.
  - The README's three limitations are disclosed.
  - **Rejected:** excluding it for the trace-loss defect (every directory holds complete cells; the loss concerns runs
    that are not in the deposit).
- **D-252. Figshare 32657856: one corpus `dca-agentdojo` with parts `v1` (13,374 `v1.k14`) and `drift` (2,847, mapped by
  the DRIFT build).**
  - Pin: kind `url` (Figshare file 65496114).
  - Identity rows from the README (D-92), the two `local` directories included; CaMeL, CaMeL+secpol, DCA and DRIFT
    arms as defences.
  - The 1,025 content repeats are disclosed.
  - **Rejected:** a new `figshare` pin kind now (a `raw/` change the import does not need); deduplicating by content
    (they are separate runs).
- **D-253. Kavach: one corpus `kavach-agentdojo` with three snapshots** (main, nav-fixer2, rearch-forcedformat-fix,
  imported in that order).
  - Byte repeats collapse; the 650 content-repeat groups are disclosed.
  - Model rows only where a run record names the model: the four `agentdojo_summary*.json` directories, as
    `gemma4:26b`. Every other directory is `identity_unresolved` with the directory label kept (D-105), unless the user
    rules otherwise (Q4).
  - The source-declared invalid directory is included and disclosed (Q3).
- **D-254. EnvironmentOptim identity (the ruling RT-8 asks for; Q1).**
  - Recommended: agent model **Qwen3.5-9B**, class I, basis the README, for the unsuffixed model path.
  - The arm path keys the identity table (D-104) and is recorded as the condition. `checkpoint_N` is a payload
    checkpoint, never a model id.
  - The `-2B`/`-4B` baselines are asserted as Qwen3.5-2B/4B from the logged model path (class I), or left unresolved
    if the user prefers D-92's strict reading.
  - The 620 DRIFT runs get their own row (gpt-4o-mini-2024-07-18, defence `drift`).
- **D-255. EnvironmentOptim's account path (Q2).**
  - Recommended: hold the 6,016 local-Qwen logs as `select.redaction_pending` (D-324) until an agentdojo-family
    redaction of the logged `pipeline_name` exists (the D-182 analogue, routed to the regen-batch session, because it
    moves the agentdojo code digest).
  - Import the 104 gpt-5.4 logs and the 620 DRIFT logs now.
  - **Rejected:** copying the account path into the AER (contradicts D-182's AER redaction); dropping the logs
    (exclusion for a fixable reason).
- **D-256. drift-1: one corpus `drift1-agentdojo`, part `drift` (626).**
  - The DRIFT head copies are `select.owned_elsewhere` (owner `drift`).
  - The PACT directory gets its own identity row (model as logged: `gpt-4o-mini`).
  - The extra keys are mapped generically and the unrecognised CALL ERRORs are reported (D-279).
- **D-257. No `[withhold]` table for any of the six profiles** (§8). EnvironmentOptim's header-only file is disclosed.
- **D-258. Fixtures (D-109; at most 512 KiB per source).**
  - Real fixtures where licence-cleared and free of account paths and secret-like strings: byte-identical pinned
    members, the smallest per criterion (variant, nested member, `:` label, DRIFT, PACT, `.incomplete`).
  - Synthetic fixtures for EnvironmentOptim's local-Qwen runs (account path).
- **D-259.** Reserved.

## 10. Questions for the user

1. **Q1 (EnvironmentOptim identity, RT-8):** model Qwen3.5-9B from the README, with checkpoints as payload conditions?
   And the `-2B`/`-4B` baselines: assert Qwen3.5-2B/4B from the logged path, or leave them unresolved?
2. **Q2 (EnvironmentOptim account path):** hold the 6,016 local-Qwen logs `select.redaction_pending` until an
   agentdojo-family redaction lands (recommended), or import them with the label as logged?
3. **Q3 (Kavach):** include the 220 logs the authors mark invalid and disclose it (recommended), or hold them?
4. **Q4 (Kavach identity):** leave the six directories without a model record unresolved (recommended, D-92/D-105), or
   accept `llama3.1:8b` from the run guide for the two `llama3.1` directories?
5. **Q5 (optional network):** a Zenodo metadata query for versions of 22011266 newer than v4.0.0? An AgentDyn history
   fetch to settle whether EnvironmentOptim's 620 DRIFT runs are AgentDyn's superseded generation (RT-8, R-3)? Neither is
   needed to build the profiles.
6. **Q7 (Figshare DRIFT `gpt-oss:20b`):** assert GPT-OSS-20B from the README with the route unrecorded (recommended),
   or leave the arm unresolved?

## 11. What part B changes elsewhere (CLAUDE.md rule 10)

- **New files:** six profiles, their identity tables, fixtures, tests, a D_adapters.md subsection, and append-only
  registry entries with status `planned`.
- **No change to** the agentdojo mapper, quirks, catalogue, hooks, existing profiles, `runner/`, `raw/`, `ingest/`,
  `corpus/` or `aer/`. No stored corpus byte, code digest or golden moves.
- **Routed** (if the user agrees):
  - the agentdojo-family redaction for EnvironmentOptim (D-255);
  - optionally a `figshare` pin kind (D-252).

## 12. Outcome of the approved network checks (user approval 2026-10-14; Q5)

Both are logged in `~/.agentprov/migration-work/phase10j/acquisitions.jsonl`.

- **(a) Zenodo 22011266.** The concept record 20731176 resolves to 22011266. The versions list has four entries:
  20731177 (2026-06-17), 21361725 (`v2`), 21418519 (`3.0.0`) and 22011266 (`4.0.0`, 2026-08-19). v4.0.0 is the latest,
  so the pin is unchanged.
- **(b) AgentDyn history (R-3).** A blob-less bare clone of `SaFo-Lab/AgentDyn` (3.7 MB, 26 commits, `main` at the
  pinned `5353cf76`; no blob contents).
  - **All 620** of EnvironmentOptim's `gpt-4o-mini-2024-07-18-drift` logs have the git blob ids of AgentDyn's files at
    the same path in every commit from `2d4ad05a` (2026-02-14) to `785b9127` (2026-04-09). AgentDyn replaced the
    directory at `6623a721` (2026-04-19).
  - All 4,878 of EnvironmentOptim's DRIFT logs are thus in AgentDyn's history; none of its 6,120 new `v1.k14` logs is.
  - **User decision:** the 620 belong to an AgentDyn `history` part (routed, `routing.md` R-10j-2), and
    EnvironmentOptim registers them `select.owned_elsewhere` (owner `agentdyn`).
  - EnvironmentOptim's new runs are therefore 6,120: 104 gpt-5.4 imported now, and 6,016 local-Qwen held for R-10j-1.
