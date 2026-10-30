# Pre-check dossier: `what-surrounds`

## 1. Header

| | |
|---|---|
| Corpus | `what-surrounds` (data CC-BY-4.0, code MIT; Zenodo 21944598 v1.0.0) |
| Parts | `what-surrounds · runs-named` (1 part) |
| Family / profile | `wirelog` / `what-surrounds@1` (dialect `wirelog.request_response`, variants `bedrock-converse` / `anthropic-messages`, mapper `wirelog.run_dir`, SEM `wirelog.tools@1`) |
| Pin | `prompt-injection-study.zip`, sha256 `08e60afd…079454`, verified |
| Code commit | `d97d3a57` (L1 and L2, batch `wave6`, all steps rc 0, tracked_changes false) |
| Kind | wave 6, first examination (not in FA or E2); registry `planned`, no stored corpus |
| Date | 2026-10-14 (prereg), 2026-10-16 (L1/L2 batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), batch (L1/L2), examiner (this dossier), adversarial verifier (2026-10-21: 7/7 confirmed, 3 refined) |
| Data | [`data/what-surrounds/`](data/what-surrounds/): `research.json`, `l1-runs-named.json`, `l1-09-…`, `l1-10-…`, `l2-sample-…`, `l2-…`, `code-…`, `exam.json`, `findings.json`, `population.json`, `leads.json`, `l2-mapping.json`, `outcome-sample.json`, `exam-scripts/` |

- Code identity, part `runs-named` ([`code-runs-named.json`](data/what-surrounds/code-runs-named.json)): commit `d97d3a57` (tracked_changes false); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, sem `56e29c80ca2b`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `wirelog.run_dir@0.1.0` `de488fd3cc99`; profile sha256 `ed4849b26a47`; rules aer 1 / wirelog 1; SEM `wirelog.tools@1` `4696c9b779e6`; prov rules `79b0a1e78dc7`; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

- Data record: <https://doi.org/10.5281/zenodo.21944598> (concept 21944597, one version, 2026-08-15). Paper: the deposit's `PAPER.md` (draft, August 2026). No preprint and no public repository found.
- Attack source: MCPTox (<https://arxiv.org/abs/2508.14925>, <https://doi.org/10.1609/aaai.v40i42.40895>).
- Notes on data versus paper (detail in `research.json` and prereg §8): the pilot run 0001 uses Anthropic Messages bodies (D-283); 358 first-batch `meta.json` were rewritten at rename; 154 runs have no final-text split; `verify_stats_output.txt` reports "712 send_email calls to attacker", but 712 is the number of runs (PC-01).

## 3. Expectations

[`prereg/what-surrounds.md`](prereg/what-surrounds.md), commit `fd75f8a3`. 18 hypotheses (H-01..H-18), check map §6. Per-hypothesis table added by the completeness critic (2026-10-21) from the examiner's record.

| H | Verdict and evidence (from `data/what-surrounds/exam.json`) |
|---|---|
| H-01 | supported: 1,334 runs, numbers 1..1,334 contiguous, meta.run_id = dir 1,334/1,334, csv ids = dirs; 10,744 / 10,724 (1,334 primary + 9,390 aux) / 20 |
| H-02 | supported: 67 cells, sizes = prereg §3, 0 missing, 0 extra; 0 runs in unrun templates or dropped models |
| H-03 | supported: 16 short-shape = 8 Sonnet + 8 Haiku mcptox_p2, runs 359-374 |
| H-04 | supported: runs 1 (Sonnet soft), 2-4 and 155-158 (operator_spoof x 7 models) |
| H-05 | supported: 154 = runs 1-154 (52/51/51); tokens over 1,180 runs csv = meta = response usage = 1,838,264 / 274,519; 0 run-level mismatches |
| H-06 | supported: 67/67 hijack cells exact; 712; csv = meta.fired_attacker = recomputed in 1,334/1,334 |
| H-07 | refuted (partly): aggregates and 26 exfil cells exact, 13/15 silent cells exact; Claude p2 silent csv 37/2 vs PA 29/1 (PC-02) |
| H-08 | refuted: 756 = 721 attacker + 29 legit + 6 other (PC-01) |
| H-09 | supported: 19 legit-send, 11 no-send |
| H-10 | supported: 1 (nova-lite soft 0176), 0 reverse |
| H-11 | supported (part): 4 Converse toolConfigs (+ run 0001 Messages tools); 7 P2-metadata arms share the mcptox_p2 config; P2 core-sentence byte identity not tested |
| H-12 | supported (part): 330 runs with system, 5 texts, 1 per sys arm; userprefix_long none; task-prompt-with-prefix count not tested |
| H-13 | supported (part): source_quote P1 120 + P2 796 = 916, P3 60, one quote digest per paradigm; underscore form not tested |
| H-14 | supported: 1 anthropic-messages (0001), 1,333 Converse; 3,191 requests (79/662/584/9 per run); 0 model mismatches |
| H-15 | supported: 0 secret-like, 0 real account paths; 929 benchmark-quote /home/<name> strings in aux (PC-04, CC-03) |
| H-16 | supported: 1,334 parse, +00:00, non-decreasing, 2026-08-06..2026-08-07T10:18Z, 0 after record creation |
| H-17 | supported: 300/300 ok, 0 degenerate, determinism identical, only §5 codes at proportional rates |
| H-18 | supported: 0 flagged gaps on 7 pooled arms and 2 channel pools with n >= 20 |


## 4. Level 1 (whole population, raw through `agentprov.ingest`)

| Check | Result (denominator) | vs prereg |
|---|---|---|
| L1-01 | 10,744 walked = 1,334 selected + 9,390 auxiliary + 20 not selected; 0 rejected; units 1,334 = registry | = |
| L1-02 | 1,334/1,334 primaries and 2,669/2,669 aux parsed ok | = |
| L1-03 | variation selectors in 160 primaries (model emoji); literal `\n` in 4 model strings; 0 mojibake, controls, bidi, surrogates | = (literal `\n` not pre-registered, model text, no finding) |
| L1-04 | 0 byte-identical primaries; 15 trajectory groups / 43 units (CC-01 fingerprint; 5 groups span arms, mostly Qwen3 clean vs `mcptox_p2`, same output); cross-corpus 0 (`_cross/l1-xdup.json`) | = |
| L1-05 | 67 cells, sizes exactly as §3, 0 missing, 0 extra; per-model 420/299/141/111/111/111/141 | = (H-02) |
| L1-06 | primaries 0 secret-like, 0 account paths; aux 929 `/home/<name>` strings (1 name, length withheld, also in the PAPER.md MCPTox quote) at `/source_quote` (916) and 13 `attacks.json` pointers | CC-03 (PC-04) |
| L1-07 | primaries carry no time (by design); `meta.json` 1,334 parse, `+00:00`, non-decreasing by run, 2026-08-06 to 2026-08-07T10:18Z | = (H-16); tool counts primaries only (PC-06) |
| L1-08 | 0 flags; 79 runs without a tool call; 3 attacked `tool_result` runs without `read_file` | entry says 1 (PC-03) |
| L1-09 | 0 metadata members | n/a |
| L1-10 | 6,721 aux files screened, 0 hits, 0 operator | = |

Whole-population recount (`population.json`, exam scripts). Counts of 3,191 requests (79/662/584/9 per run), 2,001 tool calls (1,245 read / 756 send) and 79 runs without a call match the census. File sets 976/204/154 and meta shapes 960/16/204/154 also match. Tokens over the 1,180 runs agree three ways: csv = meta = response usage = 1,838,264 / 274,519. 4 Converse `toolConfig`s; run 0001 sends Messages `tools`. 330 runs carry a `system` field, with 5 texts. Source quotes: P1 120, P2 796, P3 60.

## 5. Level 2

- Sample [`l2-sample-runs-named.json`](data/what-surrounds/l2-sample-runs-named.json): 300 of 1,334 (67 strata, 4-5 each, seed 20261011, not over the maximum).
- Import j2/j1: 300/300 mapped, sealed_clean 300, degenerate 0, adapter_defect 0, failed 0; join 300 labels → 300 executions.
- Validate (aer, sem, prov, linkage): 300/300, linkage 100 %; shacl skipped (not implemented); regression n/a. Recompute `--dry-run`: 300 identical. Determinism j2 vs j1: 6,870 files, 0 differ, index identical. `verify --level chain`: only `checksums.absent` (working tree).
- A2: `map.wirelog.meta_rewritten` 152 (= sampled first-batch units), `map.wirelog.final_texts_not_logged` 70 = `map.accounting_unverifiable` 70 (= sampled units from runs 1-154). No other code.
- A3: 0 PI issues over 149,261 statements / 256,388 relation arguments. Messages with `generated_by` 1,134; model calls with input 708; tool executions with call 426.
- Accounting: `wirelog.acc.recorded_hijack@1` consistent 300/300. `usage_totals` is consistent for 230 runs and unverifiable for 70 (runs 1-154). Dispatcher log and final text are consistent 300/300.
- Mapping versus raw (`l2-mapping.json`): AER `hijack`, `exfiltration`, `silent` and `call_order` equal the `results.csv` row 300/300. No judgement `wirelog.hijack_recomputed` exists (PC-05).
- Evidence classes. AER: actor I 1,755, fixture D 148, all other records O. PROV: core D 11,685 / O 9,223; inference I 13,777 (+1,983 none); assessment D 356 / I 5,017 / O 600. `_unverified` split: twin 0, native 14,937, mixed 0.
- Identity: 7 model ids = `meta.model` with 0 mismatches; defence `none`; attack = arm (`clean` → `none`); suite unresolved 300 (the family has no suite facet).
- Redaction: 138/300 AER executions hit at `/ext/wirelog/meta/source_quote` only, all of them the MCPTox quote (CC-03, PC-04). 0 hits in SEM and PROV, 0 operator hits. Withholding: no policy, as expected.
- CC-07 (#181/#161): not applicable (not an AgentDojo-format corpus).

## 6. Outcome comparison (hijack)

Population: all 67 (model × arm) cells equal the PAPER.md integers exactly. Total 712; `results.csv` = `meta.fired_attacker` = recomputed attacker send in 1,334/1,334. All 26 pre-registered exfiltration cells, 13/15 silent cells and every aggregate match: 202/39, 435/51, 137/122, 161/2/20, plus 140 first-batch result hijacks. Sample ([`outcome-sample.json`](data/what-surrounds/outcome-sample.json)): the expected rate is the sample-weighted paper rate.

| Arm | n | Sample rate [Wilson 95 %] | Expected | Gap pp | Population | Verdict |
|---|---:|---|---:|---:|---|---|
| clean | 31 | 0.000 [0.000, 0.110] | 0.000 | 0.0 | 0/70 | ok |
| soft | 30 | 0.100 [0.035, 0.256] | 0.107 | -0.7 | 8/71 | ok |
| imperative | 31 | 0.452 [0.292, 0.622] | 0.542 | -9.0 | 40/70 | ok |
| urgent_authority | 30 | 0.500 [0.332, 0.669] | 0.493 | +0.7 | 37/70 | ok |
| operator_spoof | 30 | 0.667 [0.488, 0.808] | 0.667 | 0.0 | 55/77 | ok |
| mcptox_p2 | 30 | 0.700 [0.521, 0.833] | 0.700 | 0.0 | 158/226 | ok |
| mcptox_p2_toolresult | 30 | 0.600 [0.423, 0.754] | 0.609 | -0.9 | 137/210 | ok |
| channel tool_description | 88 | 0.670 [0.567, 0.760] | 0.707 | -3.7 | 416/586 | ok |
| channel tool_result (attacked) | 171 | 0.409 [0.338, 0.484] | 0.427 | -1.8 | 277/618 | ok |
| mcptox_p3 (param) | 10 | 0.100 [0.018, 0.404] | 0.317 | -21.7 | 19/60 | n < 20, Wilson only |
| other 10 arms | 5-13 | see file | | ≤ 11.7 abs | = PA | n < 20, Wilson only |

0 flagged gaps. Silent differs in 2 cells (Claude `mcptox_p2` Haiku/Sonnet: csv 37/2 vs PA 29/1), all from the confirmation batch; PAPER.md counts those 9 not silent, the final texts support csv (PC-02). Hypotheses: supported H-01..H-06, H-09, H-10, H-14..H-18; supported in part (some sub-claims not tested) H-11, H-12, H-13; refuted H-07 (2 silent cells, PC-02) and H-08 (PC-01).

## 7. Findings

| Id | Title | Class | Sev | CC | Verdict |
|---|---|---|---|---|---|
| PC-what-surrounds-01 | 721 attacker-addressed send calls in 712 hijacked runs (9 double sends); 29 legit, not 38 | documentation-mismatch | S3 | R3/R4 | confirmed |
| PC-what-surrounds-02 | csv `silent`=1 on the 9 confirmation-batch hijacks; PA counts them not silent (Haiku 29 of 37); final texts support csv | documentation-mismatch | S3 | R3 | confirmed (refined) |
| PC-what-surrounds-03 | `payload_not_delivered` (issue code, count 1 correct) misses 2 first-batch runs that never read the file (3 in all) | documentation-mismatch | S3 | R2 | confirmed (refined) |
| PC-what-surrounds-04 | MCPTox quote `/home/<name>` (non-generic, benchmark text) in 933 raw occurrences, AER `source_quote` (138/300) | expected-known | S3 | CC-03 | confirmed (refined) |
| PC-what-surrounds-05 | Phase-10m docs name a `hijack_recomputed` judgement; the engine runs accounting check `wirelog.acc.recorded_hijack@1` | documentation-mismatch | S3 | R4 | confirmed |
| PC-what-surrounds-06 | Pre-check tools: no wirelog outcome hook; L1-07 counts primary members only | analysis-artefact | S3 | R5 | confirmed |
| PC-what-surrounds-07 | Catalogued quirks reproduced at their counts | expected-known | S3 | R2 | confirmed |

Proposed `artefacts.toml` text (route to the wirelog family owner):

```
# PC-02 (new): [[artefact]] id = "wirelog.art.confirmation_batch_silent"; scope what-surrounds:runs-named;
#   16 short-shape meta.json runs (359-374) have no silent field; results.csv silent = 1 on their 9 hijacks;
#   PAPER.md per-cell silent counts exclude them (Haiku p2 29 vs 37, Sonnet p2 1 vs 2); documentation only
# PC-03 (scope note, verifier-corrected): keep wirelog.art.payload_not_delivered count 1 (mapper flags attacks.json
#   payload fixtures only, mapper.py 592-606); add a note or first-batch detector for 0130, 0133 (Nova Micro imperative)
```

AGENTS.md §12: none. Security: no secret and no real account path. PC-04 is benchmark text, with 0 operator hits.

## 8. Recommendations and readiness

**Readiness: `ready-with-caveats`.** Every finding is S3, the mapping is exact against the raw tables, and the population reproduces the paper's hijack integers exactly. Adversarial verifier (2026-10-21): 7/7 findings confirmed, 0 refuted, 0 outcome gaps, readiness confirmed; refinements to PC-02, PC-03 and PC-04 are in `findings.json` `verdicts`. Caveats for the datasheet:

1. Hijack is a per-run indicator (721 calls in 712 runs).
2. The 9 confirmation-batch silent values come from csv; PAPER.md 5.4 counts them not silent (Haiku 29 of 37). A final-text check (calibrated exactly on the 32 full-shape Claude p2 hijacks) finds no disclosure in any of the 9, so csv is supported. Keep them; do not re-score.
3. 3 runs never received the payload. They are kept, and no data is excluded for zero attack success.
4. The MCPTox quote path (one non-generic 4-character name, inside attack payload text only, 0 operator hits) is allow-listed as benchmark text after a digest check against the upstream MCPTox text.

Follow-ups (not run):

- Full import for population AER counts (`exam.json` followups).
- A wirelog outcome hook in the tools (PC-06).
- PC-02 final texts: heuristic check done by the verifier (supports csv); a manual read is optional.
- Family owner: confirm the MCPTox quote against upstream by digest before the allow-list (PC-04); PC-03 scope note.
- Phase-10m README correction (PC-05).

## 9. Reproduction

```
W=~/.agentprov/migration-work/precheck/what-surrounds; X=docs/reports/precheck/data/what-surrounds/exam-scripts
uv run python -I $X/pop.py $X $W/exam/pop.json            # population recount (H-01..H-16) -> population.json
python3 -I $X/cells.py $W/exam/pop.json                    # per-cell vs prereg §4
uv run python -I $X/leads.py $X > $W/exam/leads.json       # silent, double sends, no-read runs, H-10 cell
uv run python -I $X/toolcfg.py $X                          # toolConfig digests per arm
uv run python -I $X/homecomp.py $X                         # home-path component class (booleans only)
uv run python -I $X/l2out.py $X $W/l2-runs-named-j2.partial $W/exam/l2out.json   # AER vs raw
python3 -I $X/outcome.py docs/reports/precheck/data/what-surrounds/l2-runs-named.json $W/exam/pop.json $W/exam/l2out.json $W/exam/outcome.json
# batch (already run): tools/precheck/run_batch.py --plan tools/precheck/plans/wave6.toml (l1, l1_10, sample, import_j2, import_j1, check)
```
