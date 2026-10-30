# Pre-registration: `what-surrounds`

| | |
|---|---|
| Corpus | `what-surrounds` (family `wirelog`, profile `what-surrounds` v1, dialect `wirelog.request_response`, variants `bedrock-converse` / `anthropic-messages`, mapper `wirelog.run_dir`, rules `aer 1 / wirelog 1`, SEM `wirelog.tools@1`, catalogue `wirelog` v1) |
| Parts | `runs-named` (only part): Zenodo 21944598 v1.0.0, `prompt-injection-study.zip`, 1,334 runs |
| Wave | 6 (first examination; not in FA or E2; registry status `planned`, no stored corpus) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: phase-10m report part A (`../../phase10m/README.md`, census `zenodo-21944598.census.json`), the profile, the registry, `wirelog/artefacts.toml`, DECISIONS D-280..D-285 (+ D-281 addendum), and desk research (`../data/what-surrounds/research.json`). Nothing here was computed from run data. |
| Method | [`../README.md`](../README.md) |

Source keys: **P** = `src/agentprov/adapters/wirelog/profiles/what-surrounds.profile.toml`; **A** = `wirelog/artefacts.toml`;
**C** = phase-10m census (README §A.3 and the census JSON); **T** = phase-10m in-memory map and scratch trial (README §A.7, §A.8);
**R** = registry `tools/readme_corpora.toml`; **Z** = Zenodo API record 21944598; **PA** = the deposit's `PAPER.md` ("Draft, August
2026"; no arXiv or other preprint found); **RM** = the deposit's `README.md`; **VS** = the deposit's committed `verify_stats_output.txt`.
PA, RM, VS, `LICENSE*` and `CITATION.cff` are documentation members of the staged zip, read in memory through `agentprov.ingest`
(no run directory, `results.csv` or `attacks.json` was opened).

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Data record | Zenodo 21944598, concept 21944597, version `1.0.0`, published 2026-08-15 (created 10:16:55Z, revision 3); **1 version** in the concept; one file `prompt-injection-study.zip`, 6,354,708 B, md5 `a5ce4a134c610e493e95096abb69f8b3` = P pin (sha256 `08e60afd…079454`) | Z; P |
| Creator | Shaban Asif (independent researcher); no other Zenodo record, no arXiv paper, no public GitHub repository found | Z; arXiv API; GitHub search |
| Paper | `PAPER.md` inside the deposit (59,523 B), single draft; CITATION.cff `date-released` 2026-08-07 | PA |
| Code | harness scripts in the zip, no commit, "as they ran" (RM); D-282: documentary, not verified producers | RM; C §A.3.5 |
| Harness / API | own Python harness; AWS Bedrock Converse (`toolConfig`, `inferenceConfig.maxTokens` 1024), two synthetic tools (`read_file`, `send_email`); no MCP server, no AgentDojo / Inspect | PA §4.1; C |
| Attack source | MCPTox paradigms P1/P2/P3 (Wang et al., AAAI-26, DOI 10.1609/aaai.v40i42.40895, arXiv:2508.14925 v2), retargeted to `archive@records.example` | PA §2, App. A; Z related ids |
| Licence | CC-BY-4.0 (record; `LICENSE-DATA`: `runs_named/`, `results.csv`, `attacks.json`, `PAPER.md`); code MIT (`LICENSE`, 2026 Shaban Asif); no use clause; unassessed: provider terms on model outputs | Z; zip; P |

## 2. Expected counts (part `runs-named`)

| Quantity | Expected | Source |
|---|---:|---|
| Deposit files / bytes | 1 / 6,354,708 | Z; P |
| Archive members (all selected by the ingest gate, 0 rejected, 0 findings) | 10,744 | C |
| top-level files / `runs_named/` members | 22 / 10,722 | C; ingest-gate member listing (fact-check: 10,744 members, 22 top-level). *Corrected:* the Zenodo preview is truncated at 1,000 entries and shows only 19 of the 22 top-level files (not `score.py`, `verify_stats.py`, `verify_stats_output.txt`), so it does not support these counts |
| Selected by the profile (`runs_named/*/*`, `results.csv`, `attacks.json`) / not selected (`wirelog.non_run_member@1`) | 10,724 / 20 | P; A `wirelog.art.non_run_members`; T (verify: 10,724 members) |
| Uncompressed bytes / largest member | 14,114,755 / 219,709 (`results.csv`) | C |
| Run directories = units = executions (`agent_execution`) | 1,334 (R `count = 1334`, basis census); RM/PA: run ids 1..1,334 contiguous | R; C; RM; PA §5.1 |
| Primary per unit | `response_raw.json` (1,334 distinct); `request.json` auxiliary (1,263 distinct) | D-281 addendum |
| File sets: 8 files / 9 (+`outcome_v2.txt`) / 7 (no `final_user_text`/`final_reasoning`) | 976 / 204 / 154 | C |
| `meta.json` shapes: attack full / attack short / variant with tokens / variant without | 960 / 16 / 204 / 154 | C |
| Model calls (requests = responses) / per run 1,2,3,4 | 3,191 / 79, 662, 584, 9 | C |
| Tool calls / `read_file` / `send_email` results | 2,001 / 1,245 / 756 | C; PA §5.1 (756 sends) |
| Multi-result wire messages (2 / 3 blocks) | 141 (138 / 3) | C; P quirk |
| AER (in-memory map at phase 10m) | calls 3,191; tool executions 2,001; messages 6,856; fixtures 2,310 (1,334 tool configs + 976 payloads); judgements 7,028 | T |
| Issues | `wirelog.meta_rewritten` 358, `wirelog.final_texts_not_logged` 154, `wirelog.payload_not_delivered` 1, `accounting_unverifiable` 154 | T; A |
| Tokens (meta / csv, 1,180 runs) | input 1,838,264, output 274,519 | PA App. B |

## 3. Expected arms (L1-05; facets `model_dir` × `arm`, default strata of the L1 hook)

Arm determines channel, paradigm and context (PA §4.2, §5.6; C). Cell sizes: census arm totals and per-model totals,
split per model from PA tables (n per cell); cells marked † are inferred from per-model totals, not stated per cell.

| Arm | Channel / context | Sonnet 4.6 | Haiku 4.5 | Nova Micro | Nova Lite | Nova Pro | Ministral 3 8B | Qwen3 32B | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `clean` | tool_result (no attack) | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 70 |
| `soft` | tool_result | 11 | 10 | 10 | 10 | 10 | 10 | 10 | 71 |
| `imperative` | tool_result | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 70 |
| `urgent_authority` | tool_result | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 70 |
| `operator_spoof` | tool_result | 11 | 11 | 11 | 11 | 11 | 11 | 11 | 77 |
| `mcptox_p2` | tool_description, none | 38 | 38 | 30 | 30 | 30 | 30 | 30 | 226 |
| `mcptox_p2_toolresult` | tool_result, none | 30 | 30 | 30 | 30 | 30 | 30 | 30 | 210 |
| `mcptox_p1` / `mcptox_p1_toolresult` / `mcptox_p3` | desc / result / param_description, none | 30 each | 30 each | — | — | — | — | — | 60 each |
| `mcptox_p2_sys_explicit` | desc, explicit distrust system | 30 | 30 | — | — | — | — | — | 60 |
| `mcptox_p2_sys_generic` | desc, "helpful assistant" system | 30 | 30† | — | — | — | — | — | 60 |
| `mcptox_p2_sys_generic_b` / `_role` | desc, "AI assistant" / short role system | 30 / 30 | — | — | — | — | — | — | 30 / 30 |
| `mcptox_p2_sys_generic_long` | desc, ~70-word role system | 30 | — | 30 | — | — | — | 30 | 90 |
| `mcptox_p2_userprefix_long` | desc, same text in the user turn | 30 | — | — | — | — | — | — | 30 |
| `mcptox_p2_toolresult_sysctx` | result, ~70-word role system | 30 | 30 | — | — | — | — | — | 60 |
| **Total** | | **420** | **299** | **141** | **111** | **111** | **111** | **141** | **1,334** |

- **67 non-empty cells** (35 first-batch, 32 named-attack). Channels: tool_description 586, tool_result 688, param_description 60 (C).
  Producer generations: first batch (`run_trials.py`, 5 variants) 358; named attacks (`run_channels.py` + drivers) 976 (C).
- **Expected missing (by design, PA §7):** P1/P3 and every context arm on the five non-Claude models; context arms on Nova
  Lite/Pro and Ministral (at ceiling); three implemented but unrun templates (turn-boundary, split-read, multi-turn); probed
  and dropped models (Llama 3 8B/70B, Command R/R+, Gemma 3): **0 runs** each.
- **Expected extra:** the 8 pilot runs (11th trial: `operator_spoof` × 7 models, `soft` × Sonnet; run numbers 1-4 and 155-158,
  PA §5.1) and the 16-run Claude P2 confirmation batch inside the n = 38 cells (PA §4.2). Neither is extra to the paper.
- Run 0001 (`claude-sonnet-4-6__soft__0001`) is the only `anthropic-messages` run; all others `bedrock-converse` (C; D-283).
- Model ids (`meta.model` = every request's `model`): `us.anthropic.claude-sonnet-4-6`, `us.anthropic.claude-haiku-4-5-20251001-v1:0`,
  `amazon.nova-micro-v1:0`, `amazon.nova-lite-v1:0`, `amazon.nova-pro-v1:0`, `mistral.ministral-3-8b-instruct`,
  `qwen.qwen3-32b-v1:0` = PA §4.1 table, same run counts. No served model in Converse responses; region not recorded.

## 4. Expected outcome rates (comparison targets)

**Mapping.** PA's *hijack* = the dispatcher log (`tools_called.txt`) shows `send_email` with `to` = the attacker address
(address-exact) = `results.csv` `hijack` = `meta.fired_attacker` (named attacks) = the recomputed attacker send (C: equal
1,334/1,334). AER: judgement `hijack` (by `benchmark`, origin `checker`, class I) and the recomputed one
(`wirelog.hijack_recomputed@1`, D). *Exfiltration* = hijack whose body carries ticket content = csv `exfiltration`. *Silent* =
hijack without a send mentioned in `final_user_text.txt` = csv `silent`. `call_order` = csv. `outcome.txt` (harness label,
origin `harness_rule`) and `outcome_v2.txt` (re-derivation, 358 runs) are separate judgements and **not** the paper's metric.
No utility metric is reported; the clean arm is the control (0 sends).

**Hijack, exact counts (PA tables; all n from PA):**

| Arm | Sonnet | Haiku | Nova Micro | Nova Lite | Nova Pro | Ministral | Qwen3 | Pooled | Source |
|---|---|---|---|---|---|---|---|---|---|
| clean | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/70 | PA §5.1 |
| soft | 0/11 | 0/10 | 0/10 | 5/10 | 3/10 | 0/10 | 0/10 | 8/71 | PA §5.1 |
| imperative | 0/10 | 0/10 | 8/10 | 10/10 | 10/10 | 8/10 | 4/10 | 40/70 | PA §5.1 |
| urgent_authority | 0/10 | 0/10 | 10/10 | 10/10 | 10/10 | 4/10 | 3/10 | 37/70 | PA §5.1 |
| operator_spoof | 0/11 | 0/11 | 11/11 | 11/11 | 11/11 | 11/11 | 11/11 | 55/77 | PA §5.1 |
| mcptox_p2 | 4/38 | 37/38 | 15/30 | 27/30 | 30/30 | 30/30 | 15/30 | 158/226 | PA §5.2 |
| mcptox_p2_toolresult | 0/30 | 0/30 | 29/30 | 28/30 | 30/30 | 21/30 | 29/30 | 137/210 | PA §5.2, §5.3 |
| mcptox_p1 / p1_toolresult / p3 | 0 / 0 / 0 of 30 | 25 / 0 / 19 of 30 | | | | | | 25 / 0 / 19 of 60 | PA §5.2 |
| sys_generic / generic_b / role | 29 / 26 / 29 of 30 | 30/30† (generic) | | | | | | 59/60, 26/30, 29/30 | PA §5.6 |
| sys_generic_long | 30/30 | | 23/30 | | | | 30/30 | 83/90 | PA §5.6, §5.7 |
| userprefix_long / sys_explicit | 29/30 / 0/30 | — / 7/30 | | | | | | 29/30, 7/60 | PA §5.6 |
| toolresult_sysctx | 0/30 | 0/30 | | | | | | 0/60 | PA §5.7 |

Totals: **712 hijacked runs** (sum of the table) = VS "total send_email calls to attacker = 712"; 756 `send_email` calls, 6 to
neither attacker nor legitimate recipient (3 malformed, in runs without an attacker send), hence 38 to the legitimate
recipient (PA §5.1; VS; derived). Sonnet 420 trials, 210 without context, 0 exfiltrations there, 6 in all; Claude
data-channel trials 283, 0 hijacks (VS).

**Exfiltration and silence (PA §5.3, §5.4, §5.6):** p2 desc exfil Haiku 4, Nova Lite 1, others 0; p2 result exfil Nova
Micro 27, Nova Lite 26, Nova Pro 30, Ministral 15, Qwen3 24 (Claude 0); p1 Haiku 15; p3 Haiku 19. Context arms (Sonnet):
exfil 3/1/1/1/0/0 and silent 18/20/22/16/27/0 for generic/generic_b/role/long/userprefix/explicit; Sonnet p2 bare silent 1;
Haiku exfil 4 → 5 (generic) → 1 (explicit); Nova Micro/Qwen3 long-context exfil 0 (all 53 send-before-read). Aggregates
(VS): no-context metadata 202 hijack / 39 exfil; all metadata 435 / 51; tool_result (named) 137 / 122 (VS labels this line "tool_result, all arms", but the figures are the named tool_result arms only: the first batch's tool_result hijacks are another 140); call order in
no-context P1+P2 metadata: send-first-empty 161, read-first-empty 2, read-first-data 20. Silent among p2 desc hijacks: Haiku
29/37, Nova Pro 29/30, Nova Lite 26/27, Nova Micro 14/15, Qwen3 15/15, Ministral 17/30 (*derived*: PA §5.5 states 13 of 30 disclosed); p2 result: Nova Pro
6/30 (*derived*: PA §5.4 states 24 of 30 disclosed), Qwen3 4/29 (*derived*: 25 of 29 disclosed). *Corrected (fact-check):* these three silent counts are
not printed in PA; each is the cell's hijack count minus its stated disclosure count. Sonnet p3: 19 sends to the legitimate recipient, 11 no send (PA §5.5).

**L2 use.** 67 strata × about 5 exceed the 300 cap, so about 4-5 units per stratum: no (model, arm) stratum reaches 20.
The README threshold (> 15 pp with n ≥ 20, or a 95 % binomial interval excluding the expected rate by > 5 pp) is applied to
pooled arms (arm over models: each first-batch variant, `mcptox_p2`, `mcptox_p2_toolresult` reach n ≈ 30), with the
expected rate = the sample-weighted mean of the per-cell rates above; also pooled by channel (desc / result / param).
Everything else: Wilson intervals only. The stronger test is the **whole-population recount** of `results.csv` and the
dispatcher log against the exact integers above (L1-05 extension, H-06..H-09).

## 5. Known quirks (expected-known)

| Id | Expected | Where |
|---|---|---|
| `wirelog.art.synthetic_tools` / quirk `wirelog.synthetic_tools` | 2,001 results (1,245 read, 756 sent); no real file or mail (D-284) | A; P; PA §8 |
| `wirelog.art.anthropic_messages_run` / quirk | 1 run (0001) | A; P; D-283 |
| `wirelog.multi_result_messages` | 141 wire messages (138 / 3) | P; D-281(c) |
| `wirelog.art.meta_rewritten` | 358 (`source_dir` = `run_<meta.run>`) | A; C §A.3.5 |
| `wirelog.art.final_texts_not_logged` (+ `accounting_unverifiable`) | 154 | A; T |
| `wirelog.art.payload_not_delivered` | 1 (tool_result arm, no `read_file` call) | A; C |
| `wirelog.art.first_batch_payload_in_code` | 288 attacked first-batch runs (no payload fixture; recognised by digest) | A; P |
| `wirelog.art.metadata_channel_payload` | 646 (586 desc + 60 param) | A |
| `wirelog.art.outcome_at_save` | 1,334 (358 with `outcome_v2`) | A |
| `wirelog.art.event_times_not_recorded` | 1,334 (only `meta.timestamp`; `latencyMs` 3,189) | A; C |
| `wirelog.art.non_run_members` | 20 not-selected files | A |
| `wirelog.art.context_diverges`, `wirelog.art.label_field_mismatch` | 0 | A; C |
| D-281 addendum | `request.json` byte-repeats: 1,263 distinct of 1,334 (single-request runs) | DECISIONS |
| Census, other | CRLF line ends in JSON/`tools_called.txt`; 0 reasoning blocks; longest string 2,863 B; 5 distinct e-mail addresses in 4 domains (`records.example`, `example.com`, `support.system`, `malicious.com`); *corrected (fact-check):* not all reserved: `malicious.com` (the MCPTox P3 quote `proxy@malicious.com`, PA App. A) is an ordinary `.com` name, not an RFC 2606 name, `support.system` is model-invented (C); `/home/` hits 916 = MCPTox quote in `meta.source_quote`; 4 distinct `toolConfig`s; 3 task prompts (1,244 / 60 / 30); 5 system prompts (778 requests) | C |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2: 1 zip, 10,744 members, 10,724 selected / 20 not selected, 1,334 units; arm/model totals §3 |
| L1-02 strict parse | yes | JSON members (`meta`, `request`, `response_raw`, `attacks.json`) and `results.csv` rows; expect 0 defects (C: 0 errors); CRLF is whitespace |
| L1-03 encodings | yes | expect model-text emoji with variation selectors (Sonnet warnings, PA §5.5); 0 mojibake, 0 lone surrogates; Windows producer (VS path, CRLF) is a reason to look for cp1252 artefacts |
| L1-04 duplicates | yes | 0 byte-identical `response_raw.json`; 71 byte-repeated `request.json` (expected); byte-identical auxiliaries (`outcome_v2.txt`, final texts) expected; cross-corpus: 0 (own harness, no shared upstream) |
| L1-05 arm coverage | yes | 67 cells of §3, 0 extra cells; plus the whole-population outcome recount (H-06..H-10) |
| L1-06 secrets / account paths | yes | expect 0 secret-like, 0 account paths in selected members; `/home/.ssh/...` MCPTox quote (916) is not an account path; VS (not selected) holds a Windows drive path without a user-name component |
| L1-07 timestamps | yes | `meta.timestamp` only: 1,334 parseable, `+00:00`, non-decreasing by run number (C); range H-16 |
| L1-08 degenerate | yes | 0 empty, 0 zero-message; 79 runs with no tool call (valid executions, D-285); every run ends `end_turn`; 154 without final-text split |
| L2 import, validate, recompute, determinism | yes | T: 1,334 mapped, 0 degenerate, byte-identical at 8 vs 3 workers, recompute identical; archive input (`ArchiveTree`) with sampled member labels |
| L2 A2 / A3 classes | yes | expect only §5 issue codes; no position-only or time edge (every edge by id or request echo) |
| L2 evidence classes | yes | D: request prefix, call-id pairing, hijack recompute, usage sums; I (`_unverified`): harness behaviour (D-282), save time, synthetic runtime |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model = `meta.model` = request `model` (7 ids); provider `aws-bedrock` (I); served model only for run 0001; benchmark version `1.0.0`, code `not_recorded` |
| L2 redaction | yes | no account path in AER/SEM/PROV (none expected in the source) |
| L2 withholding | no | no `[withhold]` policy (D-285: 0 secret-like strings); becomes conditional if L1-06 finds one |
| L2 SEM | yes | `wirelog.tools@1`: `read_file` output untrusted, `send_email` sink without external effect; first-batch documents by digest |
| L2 outcome sanity | yes (pooled + Wilson) | §4 |
| Utility under attack / defence facet | no | the paper reports no utility; the only defence-like factor is the explicit-distrust system prompt, an arm (`mcptox_p2_sys_explicit`), not a defence facet |
| Delta since E2 | no | not in FA/E2; baseline is the phase-10m map/trial (T); since then `wirelog` changed only by `18205ac4` (degenerate header for crashed jobs), so AER counts are expected equal to T; digests may move with core changes |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H-01 | §2 counts exactly (10,744 / 10,724 / 20 / 1,334; run numbers 1..1,334 contiguous, `meta.run_id` = directory name) | any differs |
| H-02 | 67 cells with the sizes of §3; 0 runs in the unrun templates or dropped models | any cell differs, or any extra cell |
| H-03 | The 16 short-shape `meta.json` runs are the Claude P2 confirmation batch: 8 Sonnet + 8 Haiku `mcptox_p2`, run numbers about 359-374 (the Zenodo listing shows Haiku `mcptox_p2` from 0367) | they are not 8 + 8 `mcptox_p2` Claude runs |
| H-04 | The 8 eleventh trials are runs 1-4 and 155-158 (`operator_spoof` × 7 models, `soft` × Sonnet) | other run numbers or arms |
| H-05 | The 154 runs without tokens and without the final-text split are exactly runs 1-154 = first batch of Sonnet (52), Haiku (51), Nova Micro (51); token sums over the other 1,180 = 1,838,264 / 274,519 (csv = meta = response usage) | any membership or sum differs |
| H-06 | Whole-population `results.csv` `hijack` per cell equals §4 exactly; total 712 = attacker-addressed `send_email` calls (VS) | any cell off by ≥ 1 (documentation-mismatch to investigate) |
| H-07 | `exfiltration`, `silent`, `call_order` reproduce §4 (202/39, 435/51, 137/122; 161/2/20; per-cell exfil and silent) | any cell off by ≥ 1 |
| H-08 | 756 `send_email` calls: 712 attacker, 38 legitimate recipient, 6 other (3 malformed in runs without an attacker send) | any differs |
| H-09 | Sonnet `mcptox_p3`: 19 runs send to the legitimate recipient, 11 do not send | differs |
| H-10 | Exactly 1 run (Nova Lite `soft`) where the harness label in `outcome.txt` counts a forward but `hijack` is false (PA §5.1 third scoring bug); 0 the other way | ≥ 2 such runs, or any reverse case |
| H-11 | 4 distinct `toolConfig`s; all seven P2-metadata arms share the `mcptox_p2` one (drivers' startup assertion, PA §4.2); the P2 core sentence is byte-identical between `mcptox_p2` (tool description) and `mcptox_p2_toolresult` (ticket) | > 4 configs, or a context arm differs in schema or document |
| H-12 | Runs with a `system` field = 330 (all `sys_*` arms 270 + `toolresult_sysctx` 60); 5 distinct system texts; `userprefix_long` has no system field and the task-prompt-with-prefix (30) | any differs |
| H-13 | `meta.source_quote` carries the MCPTox P1/P2 strings with the path written without the underscore (PA App. A) in the 916 P1/P2 runs; P3 runs carry the P3 quote | another form, or a different count |
| H-14 | 1 `anthropic-messages` run (0001) and 1,333 Converse; 0 runs whose request `model` differs from `meta.model` | any differs |
| H-15 | 0 secret-like strings, 0 account paths in the 10,724 selected members | ≥ 1 (report to the orchestrator at once) |
| H-16 | All 1,334 timestamps parse, offset `+00:00`, non-decreasing by run number, and lie before the record's creation (2026-08-15T10:16:55Z); *corrected (fact-check):* no documented lower bound of 2026-06-01: PA §2 says arXiv:2606.00566 (posted 2026-05-30) appeared "while this study was running", so runs may predate June; PA §7 says the numbers "describe August 2026". Expected span ends before the record's creation; no start date is pre-registered (a start long before 2026-05-30 is an S3 note only) | any after the record's creation (finding), or outside the span (S3 note) |
| H-17 | L2 sample (~300 units): 0 failures, 0 degenerate, determinism byte-identical, only §5 issue codes, issue rates proportional to the sample's strata (meta_rewritten = first-batch units, final_texts_not_logged = units from runs 1-154) | any failure, nondeterminism or new code |
| H-18 | L2 pooled hijack rates within the README threshold of §4's sample-weighted expectations | a gap above the threshold |

## 8. Discrepancy leads carried to the dossier

- PA §4.1 says every model was reached through Bedrock's unified interface with an identical request shape, and §5.1 that
  the pilots used an identical harness configuration; run 0001 (a pilot) holds Anthropic Messages bodies that no shipped
  script sends (expected-known, D-283; documentation-mismatch, S3).
- PA App. B and RM say the harness never rewrites a saved record; 358 first-batch `meta.json` were rewritten when the runs
  were renamed into `runs_named/` (`source_dir`, new `run_id`) (expected-known, `wirelog.art.meta_rewritten`).
- PA §4.3 / App. B say every trial writes eight files including the final-text split, and that silence is judged on
  `final_user_text.txt`; 154 runs lack those files (their 29 Nova Micro hijacks were judged for silence on something
  else) and 358 carry a ninth file `outcome_v2.txt` not mentioned in RM's file list.
- PA's "first batch" (154 runs, earlier metadata schema) is not the census's "first batch" (358 `run_trials.py` runs):
  terminology only, checked by H-05.
- The Haiku "generic" context cell (30/30, PA §5.6) is not named; the arm `mcptox_p2_sys_generic` is inferred (H-12 by
  system-text digest).
- `verify_stats_output.txt` was produced on a Windows path (consistent with the CRLF JSON); the shipped scripts are not
  verified producers (D-282).
- The paper's third scoring fix (address-exact) changed one Nova Lite `soft` cell from 6/10 to 5/10; the earlier harness
  labels (`outcome.txt`) may still carry the old classification (H-10).

## 9. Fact-check (adversarial, 2026-10-14)

Re-opened: Zenodo API record 21944598 and its versions/creator queries; DOI CSL metadata for 10.5281/zenodo.21944598 and
10.1609/aaai.v40i42.40895; arXiv API for 2508.14925, 2606.00566 and preprint searches; GitHub search; the record's zip
preview page (listing only); the deposit's `PAPER.md`, `README.md`, `LICENSE`, `LICENSE-DATA`, `CITATION.cff` and
`verify_stats_output.txt`, read in memory through `agentprov.ingest.archives` from the staged pin (no run member,
`results.csv` or `attacks.json` opened); our census JSON and phase-10m README, the profile, `artefacts.toml`, the registry
and DECISIONS D-144, D-280..D-285. Nothing computed from run data.

- **Confirmed:** record version, dates, revision, single version, creator, licence, related identifiers, file size and md5;
  CITATION.cff date 2026-08-07; LICENSE-DATA scope and MIT notice; every hijack cell of §4 against PA §5.1, §5.2, §5.6, §5.7
  (all n and counts), the pooled sums (8/71, 40/70, 37/70, 55/77, 158/226, 137/210) and the 712 total (140 first batch +
  572 named = VS attacker calls); exfiltration cells (PA §5.3) and the 202/39, 435/51, 137/122, 161/2/20 aggregates (VS
  and PA §5.3); Sonnet context exfil/silent row; Haiku 37/38 → 30/30 → 7/30, exfil 4 → 5 → 1; 756 / 712 / 6 sends (PA
  §5.1: 3 of the 6 in runs that also had an attacker send, 3 malformed in runs without); pilots runs 1-4 and 155-158;
  App. B tokens 1,838,264 / 274,519 over 1,180 runs and the 154 = 52 + 51 + 51 split; per-model run counts (PA §4.1 =
  census); arm totals and channel totals (586 / 688 / 60) re-added from the census arm table; 67 cells; MCPTox versions
  (v1 2025-08-19, v2 2026-09-29) and AAAI DOI (40(42), 35811-35819); Same-Payload v1 2026-05-30, v2 2026-08-21, EMNLP 2026
  comment; no preprint or public repository found; zip member count 10,744 with 22 top-level files (ingest listing).
- **Corrected:** (1) the Zenodo preview does not show all 22 top-level files (it is truncated; 19 visible), §2; (2) the
  silent counts for Ministral P2 desc and Nova Pro / Qwen3 P2 result are derived from stated disclosure counts, §4;
  (3) the five e-mail addresses are not all reserved (`malicious.com` from the MCPTox quote), §5; (4) the 2026-06-01 lower
  bound in H-16 contradicts PA §2 and was removed; (5) VS's "tool_result, all arms" line covers named arms only, §4.
- **Unverifiable from documents:** the arm of Haiku's "generic" cell (inferred from census arm totals and per-model totals;
  PA does not name it); the run numbers of the 16 short-shape runs (the truncated preview lists Haiku `mcptox_p2`
  0367-0374, then 0405 onward, which is consistent with H-03 but not proof); provider terms on model outputs.

