# AgentDojo-format candidate sources: ranked shortlist (phase 10c)

Status: **verification only** (2026-10-11). Nothing has been imported and no profile was written. **The user approved
all recommendations of section 4 (D-90 to D-96) on 2026-10-11.** This shortlist ranks
every licensed candidate of the systematic search whose run logs are in the AgentDojo TraceLogger format and that has
at least 100 runs (EX-SIZE-1, `../eligibility-criteria.md`, D-25). It also covers Zenodo 22973265, Zenodo 22011266 and
Figshare 32657856.

**Evidence.**
- Source report: `AgentPROV/investigation/sources/agentdojo-format-candidates.md`, with pins, licences, census and
  notes per candidate.
- Verification record: `AgentPROV/investigation/verify/agentdojo-format-candidates.md`, with corrections to the
  search records.
- Scripts and census JSON: `~/.agentprov/migration-work/phase10c/`.

All counts come from a census of the bytes at each pin (SHA-256, strict JSON, the adapter's own D.6.2 classifier). The
user approved every download in chat on 2026-10-11, including the follow-up fetch of the Kavach and Menelaus29
branches (D-95, done).

## 1. Summary

- **158,705 distinct new runs** across 26 candidates: 100,110 permissive, 53,877 GPL-3.0, 4,718 AGPL-3.0. "Distinct"
  means byte-distinct and absent from every converted source and from the DRIFT and agentdojo-inspect references.
- **No byte overlap between candidates** once the two Linyxus branches (`tacit-exp` ⊂ `lacuna-exp`) and the two
  Zenodo 22973265 versions (v1.0 ⊂ v2.1.0) are merged.
- **128,745 are readable and mappable by today's code** with only a profile and a pin. The rest are blocked as follows:

  | Blocker | Runs | Owner |
  |---|---:|---|
  | Nested `.tar.gz` inside a zip | 19,137 | core ingest |
  | `:` in member names | 1,968 | core ingest |
  | Unmapped `drift.k18` variant | 4,093 | adapter |
  | Outcome-only files (no trajectory) | 4,762 | — |

- **No candidate needs a new dialect or any change to `aer/`, `prov/`, `validate/` or `corpus/`** (invariant 5).
  Two of the blockers are in `ingest/` (core, phase-12-owned) and need a user decision (section 4).
- **Harness code.** No candidate has verified harness code. Every profile gets `code_identity` `range` or `unpinned`
  and therefore the class-I twins (D-24).

## 2. Ranked shortlist

Ranking:
1. Runs readable today.
2. What is new for the corpus: models, attacks and defences not in the converted sources.
3. Risk: identity, blockers, licence.
4. Profile effort.

Profile effort:
- **Low:** a standard layout and `pipeline_name` identity; quirks already in the vocabulary.
- **Medium:** an extra layout component, an identity table or a new semantics table.
- **High:** a blocker outside the profile.

| # | Candidate (pin) | New distinct (readable today) | Licence → corpus | What is new | Profile effort | Risks |
|---|---|---:|---|---|---|---|
| 1 | **ceferisbarov/agentdojo** (`2273e1c`, main) | 18,442 (18,442) | MIT → own permissive corpus | 61 re-run arms of optimised injection strings (`llama_k_*`, `mistral_k_*`, `qwen_k_*`, `optim_str`, `1_parallel_*`) on gpt-4o and gemini-2.5-pro; Qwen2.5, command-r-plus variants; slack- and banking-heavy | **Medium**: ROPE-like `{arm}` layout component; attack variant from the arm, because the label is always `important_instructions` | Vendored fork, code changed after the runs (`range`); 65 run errors; 2 files with secret-like patterns |
| 2 | **Wakeful-Cloud/llm-lock** (`7bb9915`) | 53,307 (53,307) | GPL-3.0 → own GPL-3.0 corpus | 9 detector-defence arms: embedding, LLM, multiclass, data-delimiter, two HF classifiers × transformer/hybrid; 6 attacks incl. `system_message`, `injecagent`, `tool_knowledge`, plus `dos`; all 4 suites at full task coverage | **Medium**: `{defence}/{classifier?}` path; detector-output extra keys; defence-denial quirk (88,197 tool errors) | **The model is not recorded** (`local`); only the code default (Llama-4-Scout GGUF via Ollama, env-overridable) names one. Partly abandoned attacks left in; AgentDojo from a git-pinned fork (`Wakeful-Cloud/agentdojo@6ebf27e`) not yet verified |
| 3 | **Figshare 32657856** (v1) | 16,221 (11,406) | MIT → own permissive corpus | CaMeL and CaMeL+secpol; the DCA defence (`causal_budgeted`); DRIFT runs; gpt-oss-20b, qwen3.6:27b, gpt-4o-mini | **Medium**: `+camel`/`-causal_budgeted` suffixes; CaMeL quirks (no system message, null finals) | 1,968 v1.k14 runs behind the `:` name gate; 2,847 DRIFT runs unmapped; 1,025 content repeats |
| 4 | **Linyxus/agentdojo** (`698d7ff`, lacuna-exp) | 9,068 (9,068) | MIT → own permissive corpus | Tacit defence on OpenRouter o4-mini-high, gemini-2.5-pro, gpt-5.4-nano, claude-sonnet-4, deepseek-v4-flash; 5 to 7 repeated run sets | **Medium**: 24 defence-generated system prompts (3k to 17k characters); extra keys `backend_tool_traces` etc.; provider route in the name | Code changed after the runs (`range`); 359 null finals |
| 5 | **Zenodo 22973265** (v2.1.0 `23138310`) | 18,739 (2,813) | CC-BY-4.0 → own permissive corpus | GPT-6 Luna, GPT-6 Sol, Claude Haiku 4.5; delegated-authority caps A3/A4, no-egress, auto-confirm; new `authority_notice` attack plus 8 templates; gpt-3.5-turbo and gpt-4o-mini re-executions | **Low** for the plain part (`-capA3`/`-capA4`/`-noegress`/`-autoconfirm`/`-rep3` suffixes) | 15,926 runs only inside nested tar.gz (section 4); 3,269 content repeats; harness scripts are in the deposit, but AgentDojo 0.1.35 itself is unverified |
| 6 | **omseeth/EnvironmentOptim** (`febf82d`) | 6,740 (6,120) | MIT → own permissive corpus | Qwen3.5 RL checkpoints (2B, 4B, base) over training; AgentDyn suites dailylife, github, shopping; gpt-5.4 | **Medium**: identity table for checkpoint paths; AgentDyn suite semantics | Training rollouts (interpretation); 620 DRIFT runs unmapped; 576 content repeats; 111 files with secret-like patterns outside the runs |
| 7 | **dafarusd/gate** (`925b992`) | 3,870 (3,870) | AGPL-3.0 → own AGPL-3.0 corpus | Gate defence on/off on local Qwen3 models (coder-480b, 235b, 3.5-9b, 3.6-35b); new hold-out attacks (base64, split payload, Spanish, markdown-image exfiltration, urgency, ...) | **Low/Medium**: `-gate-all/-off` suffix; 12 attack labels | Unpinned harness; 383 content repeats; 2 path/field mismatches |
| 8 | **mohameduk/agentdojo** (`3f9d69a`, ubag-gateway-defense) | 3,630 (3,630) | MIT → own permissive corpus | UBAG and UBAG-behavioural gateway defence on gemini-2.5-flash and gpt-4o-mini | **Low**: `-ubag[_behavioral]` suffix; `version_when_absent` | `benchmark_version` null in all attacked runs; 763 content repeats (21%) to understand before import |
| 9 | **luiacuaniello/geryon** (`905aae0`) | 3,179 (3,179) | Apache-2.0 → own permissive corpus | gpt-oss-120b and qwen3-235b via Bedrock; three repetitions; Geryon attack | **Low**: `v0.k11` (mapped since phase 6); repetition and arm in the path | No timestamps (never filled in); Progent AgentDojo cloned at HEAD (unpinned) |
| 10 | **Ishani018/Kavach** (`53df954` main + `f2dd7ef` nav-fixer2 + `6b31a55` rearch-forcedformat-fix) | 2,625 (2,625) | MIT → own permissive corpus | Kavach defence on local Gemma and Qwen2.5-7B; three branch states of the same experiment | **Medium**: `local` identity from path; custom system prompt; three pins in one profile | Only about 957 distinct trajectories by content: the branches re-serialise the same runs (main 223 ⊂ both; 883 shared by content between the two branches). Each byte-distinct file counts under the size rule, but an import should declare the repeats |
| 11 | **CSSLab/Tacit** (`995692d`) | 2,076 (2,076) | Apache-2.0 → own permissive corpus | Llama-3.1-8B and Qwen3-4B, local and vLLM | **Low**: `model_dir` identity | No harness in the repository; 3,750 null call ids |
| 12 | **deconvolute-labs/interbolt-agentdojo** (`43e2b5f`) | 2,016 (2,016) | Apache-2.0 → own permissive corpus | Interbolt defence with three policies, gpt-4o-mini, two repeats | **Low** | Best-documented harness (PyPI 0.1.35 locked in `uv.lock`), still `range` |
| 13 | **xwsdid/MELON** (`71d99df`) | 1,911 (1,911) | MIT → own permissive corpus | MELON defence variants (`melon`, `_at`, `_sm`, `_r`, `_rp`) on gpt-4o and gpt-4o-mini; `ignore_previous` and `direct` attacks | **Low** | Banking almost only |
| 14 | **zanethomas1430-code/Glitch** (`713bb29`) | 1,844 (1,844) | MIT → own permissive corpus | Glitch defence on gpt-4o and claude-haiku-4-5 | **Low** | Very recent (2026-10-07); unpinned harness |
| 15 | **AthaSSiN/CrAIBench** (`e41eac1`) | 1,163 (1,163) | MIT → own permissive corpus | **New suites** `crypto_trading` and `chain`; memory-injection variant; spotlighting on gpt-4o and gpt-4o-mini | **Medium**: suite registration, a SEM semantics table for the new tools, a file-name rule for `*_memory_injection.json` (688) | `v0.k11` from vendored 0.1.15; no timestamps |
| 16 | **HilaryTorn/in-context-trajectory-poisoning** (`d71ab8b`) | 990 (990) | MIT → own permissive corpus | Trajectory-poisoning attacks (TAP, seeded pairs, persona), 22 labels, gpt-4o | **Low** | `requirements.txt` (0.1.29) contradicts the logs (0.1.35) |
| 17 | **Menelaus29/ipi-multidomain-agent-study** (`ec9c928` main + `7c354f9` + `c560139`) | 965 (965) | MIT → own permissive corpus | Gemma-4-26B and Gemini 3.5/3.6 flash(-lite); 197-payload attack corpus; spotlighting | **Medium**: bracketed `model [alias]` identity; 197 attack labels; three pins | 107 runs exist only on branches `phase-6a-attack-calibration` and `phase-8-defense-spotlighting` |
| 18 | **kongminOS/jspace-agentdojo-950** (`f341af6`) | 950 (950) | MIT → own permissive corpus | DeepSeek V4-Flash (README only), `tool_knowledge` | **Low/Medium**: identity row from the README (class I) | Model not in the logs |
| 19 | **vinhqdang/SENTRY** (`938e8be`) | 674 (674) | AGPL-3.0 → own AGPL-3.0 corpus | deepseek-v4-flash, gpt-4o-mini; `injecagent` | **Low** | 72 runs via an OpenRouter free router (model unknowable) |
| 20 | **ShreeyaVarma/llm_safety** (`78d22e4`) | 672 (672) | MIT → own permissive corpus | gpt-4o `tool_knowledge`; local Qwen | **Low** | Small; mixed `local` labels |
| 21 | **sricursion/bookkeeper** (`0fe09bb`) | 570 (570) | GPL-3.0-or-later → own GPL-3.0 corpus | MUNIM defence on glm-5.3-flash and gpt-oss-120b | **Low** | `benchmark_version` null |
| 22 | **yockcheng/prompt-injection-harness** (`5f9137f`) | 280 (280) | Apache-2.0 → own permissive corpus | Claude Haiku 4.5, Sonnet 4.5, 3.7 Sonnet, 3 Haiku | **Low** | Small |
| 23 | **Sports-Vision-Inc/aiAuthZ** (`6eaac86`) | 174 (174) | AGPL-3.0 → own AGPL-3.0 corpus | aiAuthZ defence on claude-fable-5 and gemini-3-flash-preview via OpenRouter | **Low/Medium**: `model_dir` identity; `pipeline_name_policy = config_tag_never_model` (the logged names are deliberate registry tags) | Small |

### Held or proposed for exclusion

| Candidate | New distinct | Proposed outcome | Why |
|---|---:|---|---|
| **Zenodo 22011266** (v4.0.0) | 3,211 (0 readable) | **Hold** for the nested-tar decision; otherwise EX-FMT | Every trajectory is in nested tar.gz. Content would be valuable: gpt-5.4-mini, gpt-5.4, claude-sonnet-4-6 under five AgentDojo defences |
| **CGboom-git/drift-1** (`0e28729`) | 626 (0 readable) | **Hold** for the DRIFT mapper (D-96); licence recommended as MIT by README statement (D-93), otherwise EX-LIC-1 | No LICENSE file; a README badge points to a missing file. All runs are DRIFT-format (unmapped). 1,569 of its files are DRIFT copies (EX-DUP for those) |
| **sssr-lab/saber** (`f34f886`) | 4,762 | **EX-NOLOG** for its AgentDojo part | All 4,762 files have empty `messages`: outcome records, not run logs (IN-1). SABER's own benchmark logs (about 25,000 JSON, different format) are a separate lead for a new adapter, out of this phase's scope |

### Sensitivity (for the appendix)

The threshold applies to distinct new runs, as the size rule does, over the 23 ranked candidates (Kavach and Menelaus29
including their branches).

| Threshold | Candidates | Distinct new runs | Readable today |
|---|---:|---:|---:|
| none / 100 | 23 | 150,106 | 128,745 |
| 1,000 | 15 | 144,831 | 123,470 |
| 5,000 | 6 | 122,517 | 101,156 |

### Late additions from the literature search (S2), verified 2026-10-11

The merged screening table (`../included-excluded.md`) lists 28 phase-10c candidates. Two of them came from S2 after
this phase's scope was set. Both were settled from metadata alone, with no download.

| Candidate | Proposed outcome | Evidence |
|---|---|---|
| `gh:qiang-yu/agentdojo` (MIT; arXiv:2601.04795, tool-result parsing defence) | **EX-DUP** of AgentDojo upstream: 0 new runs | Both branches were checked. `main` (`96046ab`) and `tool-result-extract` (`245bed6`) each hold 36,679 `runs/` blobs, all byte-identical (git blob id) to upstream `runs/`. Against upstream `main`, `tool-result-extract` is 76 ahead and 14 behind, and its diff touches 15 files, all code or docs (`tool_result_extract.py`, `benchmark_lmstudio.py`, ...) and none a run file. The defence's own runs are not published |
| `hf:changdae/agentdojo-trajectories-qwen35-gemma4` | **EX-ACCESS** | The dataset page and the API return HTTP 401 without a login, and the dataset is absent from the author's public dataset list (7 other datasets): private, gated or removed. Nothing can be pinned (IN-5) or licence-checked. If it reappears, check it against the unlicensed `sungjuncho/agentdojo-trajectories` (EX-LIC-1) first |

Zenodo 20731176, the screening table's 28th row, is the concept DOI of Zenodo 22011266 (v4.0.0), covered above.
Scripts: `m03_qiangyu.py`, plus the GitHub compare API (`meta/m03_qiangyu.json`).

## 3. Corpora (D-25)

- **Permissive:** 18 own corpora (MIT, Apache-2.0, CC-BY-4.0), one per source, as for the converted sources.
- **GPL-3.0:** llm-lock and bookkeeper, each its own corpus under its licence. bookkeeper is GPL-3.0-or-later;
  llm-lock's LICENSE is GPL-3.0 and does not say "only".
- **AGPL-3.0:** gate, SENTRY and aiAuthZ, each its own corpus. gate states AGPL-3.0-only; the commercial-licence offers
  of gate and aiAuthZ do not restrict the AGPL grant.

Three AGPL corpora of 3,870, 674 and 174 runs, and a GPL corpus of 570, are small. Whether same-licence sources may
share one corpus is a question for the user (D-94 below); D-25 currently says one corpus per source.

## 4. Decisions, with recommendations (all approved by the user, 2026-10-11)

Numbers are reserved for this phase. The user approved every recommendation below on 2026-10-11; they are not yet
entered in DECISIONS.md (a shared file this phase was asked not to edit). D-95 is done: the user approved the fetch,
and the counts above include it. D-90 and D-91 are approved as requests to phase 12, which owns `ingest/`.

### D-90. Nested `.tar.gz` inside deposits (19,137 runs)

Zenodo 22973265 has 15,926 runs in nested tar.gz; Zenodo 22011266 has 3,211.

- **Options.**
  - (a) Phase 12 adds read-only support for a gzip-compressed tar **nested inside a zip** to `ingest/`: streaming, the
    G.3.5 framing pre-scanner, the existing size, ratio, count and depth limits, regular files only, member names
    through `logical_name`.
  - (b) Exclude these runs as EX-FMT.
- **Recommendation: (a)**, scoped to exactly that case. No top-level tar and no other codecs.
- **Why.**
  - These are the only runs in the set with GPT-6 Luna/Sol, gpt-5.4(-mini) and claude-sonnet-4-6 under AgentDojo
    defences.
  - Both deposits are pinned by DOI and MD5.
  - The census streamed every member in memory without trouble.
  - G.3.5 already anticipates tar behind a framing pre-scanner, and invariant 3 holds (no extraction).
- **Cost.** New ingest codes, fuzz and security tests (phase 12b); no change to any existing corpus.
- **Until then.** Import neither Zenodo deposit. Importing only the 2,813 plain-JSON runs now would create a corpus
  version that has to be superseded.
- **Fallback.** If phase 12 declines, take (b) and import 22973265's 2,813 plain runs only.

### D-91. `:` in archive member labels (3,866 Figshare members: 1,968 v1.k14 and 1,898 drift.k18)

- **Options.**
  - (a) A narrow ingest change: archive members may contain `:` inside a component (not as a drive-letter prefix),
    recorded as an info finding.
  - (b) Exclude these members with a disclosed code.
- **Recommendation: (a)**, implemented by phase 12.
- **Why.**
  - Labels are never paths: the raw store is content-addressed (`raw/members.py`: "Nothing here builds a filesystem
    path from a member name"; `raw/store.py`: the label "is never used as a path").
  - `logical_name(portable=False)` already accepts `a:b` for local `--input` trees.
  - So the Windows-portability rule protects nothing for archive labels. Keeping the drive-letter, traversal,
    backslash and reserved-device checks keeps the security rules intact.
- **Check before implementing.** Corpus layout, the register and the deposit builder may turn labels into file names;
  the H.1.3 grammar must reject or escape them there. Phase 12 should confirm this.
- **Fallback.** (b).

### D-92. Model identity when no log names the model

- **Recommendation: assert a model only where a document states which model produced these runs; never from a code
  default.**
  - **kongminOS (950).** The README says the runs are DeepSeek V4-Flash. Use an identity-table row under a class-I rule
    with basis "README statement". This follows the AgentDyn pipeline-directory registry precedent.
  - **llm-lock (53,307).** Only `agentdojo/main.py`'s default (`hf.co/unsloth/Llama-4-Scout-17B-16E-Instruct-GGUF:Q3_K_XL`)
    names a model, and it is overridable by `LLM_API_MODEL`. Seal the agent with `unk {"/model": "not_recorded"}`
    (A-3) and record the code default only as a note in `ext`, not as an assertion.
  - If a later paper or README by the llm-lock authors names the model, switch to a class-I row.
- **Why.** A default that the run environment may have overridden is a guess (invariant 2, rule 5 for agents). A
  corpus of 53,307 runs with a wrong model would distort every per-model figure.
- **Consequence.** llm-lock is still worth importing for its defence and attack comparisons, which do not depend on
  the model. Model-level analyses must leave it out; the datasheet says so.
- The same rule covers SENTRY's 72 OpenRouter free-router runs: `not_recorded`.

### D-93. saber and drift-1

- **saber: exclude its AgentDojo files as EX-NOLOG.** All 4,762 have empty message lists (outcome records only).
  - Record SABER's own logs (about 25,000 JSON, an agent-safety benchmark for coding agents) as a lead for the search's
    "new adapter" track. They are not screened here.
- **drift-1: include with the licence recorded as "MIT, README badge only; LICENSE file missing"**, under LIC rule 1
  (a README statement counts).
  - Defer the import to D-96, because all 626 new runs are `drift.k18`.
  - Its 1,569 DRIFT copies are EX-DUP.
  - If you read the badge as too weak to be a grant, the alternative is EX-LIC-1.
  - Either way it changes nothing now, because nothing can be mapped before the DRIFT mapper exists.

### D-94. Copyleft corpora

- **Recommendation: keep one corpus per source**, as D-25 says.
- **Why.**
  - Each source has its own pin, profile version, attribution and copyright holder. Pooling would mix provenance
    units in one corpus manifest and version line.
  - The licences differ in detail: gate is AGPL-3.0-only, bookkeeper GPL-3.0-or-later, and llm-lock GPL-3.0 without
    "only" or "or later". A pooled corpus would have to choose one licence expression for all.
  - Small corpora cost nothing extra in the pipeline.
- **What changes.** Nothing beyond what D-25 already says.

### D-96. Priority of the DRIFT (`drift.k18`) mapper

- **Scope.** One mapper in `adapters/agentdojo/` serves:
  - the known DRIFT source (1,569 head and 1,046 history runs);
  - AgentDyn C and D (4,258 and 949);
  - Figshare (2,847);
  - EnvironmentOptim (620);
  - drift-1 (626).

  That is about 11,900 runs.
- **Recommendation:** schedule it after the low-effort v1.k14 profiles below and after phase 11 is merged. It is
  adapter work, not core.
- **Constraint.** Its quirks are already listed (D.6.4 `drift_*`, `verify/drift.md`); none needs a core change.

### Recommended import order (no decision needed; for planning)

1. **Low-effort v1.k14 and v0.k11 profiles:**
   - interbolt, MELON, Glitch, mohameduk (needs `version_when_absent`), Tacit, geryon (v0.k11), HilaryTorn, yockcheng,
     ShreeyaVarma;
   - the copyleft corpora gate, SENTRY, bookkeeper and aiAuthZ.
2. **Medium:**
   - ceferisbarov (`{arm}`), Linyxus (system-prompt digests, extra keys), Figshare (11,406 readable), kongminOS
     (D-92), Menelaus29, Kavach (three pins, content repeats), CrAIBench (suites, SEM table), EnvironmentOptim
     (identity table), llm-lock (D-92).
3. **After the D-90 and D-91 ingest changes:** both Zenodo deposits and the rest of Figshare.
4. **After D-96:** the DRIFT-format runs.

Every import uses the class-I twins (D-24). Each new corpus is checked with `CORPUS-CHECK-PROTOCOL.md` before any
figure.

## 5. What importing would change elsewhere (CLAUDE.md rule 10)

Each source would add, in the adapter only:
- a new profile, pin and registry row;
- possibly an identity table (llm-lock, EnvironmentOptim);
- possibly a semantics table (CrAIBench suites).

Nothing would change in:
- existing corpora, AER or PROV digests;
- the compat gate;
- `aer/`, `prov/`, `validate/` or `corpus/`.

Manuscript numbers that would change:
- the source table;
- the PRISMA flow and the included/excluded table (corrected run counts, section 1 of the verification record);
- the corpus totals.

The ingest options D-90 and D-91 are the only core changes, and only if chosen.
