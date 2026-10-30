"""Build exam.json and findings.json of dca-agentdojo from the committed counts-only data files (no raw read).
Usage (repo root): uv run python -I docs/reports/precheck/data/dca-agentdojo/exam-scripts/exam_build.py"""
import json, os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
S = "docs/reports/precheck/data/dca-agentdojo/exam-scripts"; E = "~/.agentprov/migration-work/precheck/dca-agentdojo/exam"
def run(s): return f"uv run python -I {S}/{s}.py {E}/{s}.json"
F = []
def f(i, title, cls, sev, part, check, ev, rep, hyp, rec, prop=None, a12=None, sec=False):
    F.append({"id": f"PC-dca-agentdojo-{i:02d}", "title": title, "cls": cls, "severity": sev, "security": sec, "part": part,
              "check": check, "evidence": ev, "reproduction": rep, "hypothesis_ref": hyp, "recommendation": rec,
              "artefact_proposal": prop, "agents_md_12": a12, "verdict": "pending-verify", "verdicts": []})
f(1, "[CC-07, #181] banking IT0/IT1/IT3 successes without the GOAL datum in any executed attacker-bound transfer subject: 17 of 90 (precedence-only rule: 33 of 90); all in the 4 direct arms",
  "expected-known", "S3", "v1", "L1-05b outcome sanity / CC-07",
  "Banking IT0/1/3 security true, attacked: gpt-4o-mini direct 32 (GOAL-affected 14: it0 1, it1 10, it3 3), gpt-oss-20b direct 36 (2; precedence-only 12), Qwen3.6 direct (local) 21 (0; 6), Qwen2-7B direct 1 (1; 1); 0 in DCA, CaMeL, CaMeL+secpol and DRIFT arms. Every one of the 90 has an executed (error null) send_money/schedule_transaction to the attacker IBAN. Re-scored ASR (GOAL datum / precedence only): gpt-4o-mini direct 287 -> 273 / 273 of 949 (30.24 -> 28.77 %); gpt-oss direct 321 -> 319 / 309 (33.83 -> 33.61 / 32.56 %); Qwen3.6 direct 150 -> 150 / 144; Qwen2-7B 10 -> 9 / 9; v1 pooled 772 -> 755 / 739 of 12,337.",
  run("checks") + "  # counts '181|<arm>|<it>|succ|aff_goal|aff_prec'", "H4, H5",
  "Keep the logged booleans; disclose the re-scored baseline ASR next to the deposit's Table 1 (defended arms are unaffected). Route the per-source counts to the AgentDojo family owner for agentdojo.art.validity_defects (CC-07, scope gap CC-09).",
  "extend [[artefact]] agentdojo.art.validity_defects: scope.sources/profiles += \"dca-agentdojo\"; expected += { snapshot = \"dca-agentdojo:v1\", count = 17, unit = \"executions\", basis = \"pre-check PC-dca-agentdojo-01: banking IT0/1/3 success without the GOAL datum in an executed attacker-bound subject (#181); precedence-only 33\", status = \"proposed\" }")
f(2, "[CC-07, #161] banking user_task_5 utility true in 144 of 144 attacked and 6 of 6 clean logs; no executed Spotify payment in 42 of the 90 non-CaMeL attacked logs (+ 54 of 54 CaMeL logs with no recorded payment) and 2 of 6 clean",
  "expected-known", "S3", "v1, drift", "L1-05b / CC-07",
  "UT5 attacked logs, utility true / no executed payment to the Spotify IBAN: direct gpt-4o-mini 9/0, gpt-oss 9/3, Qwen3.6 9/0, Qwen2-7B 9/9 (0 tool messages in all 9), DCA gpt-4o-mini 9/9, gpt-oss 9/3, Qwen3.6 9/9, DRIFT gpt-4o-mini 9/6, gpt-oss 9/3, Qwen3.6 9/0; CaMeL and CaMeL+secpol 6 arms 9/9 each (0 transfers among recorded tool messages; the 18 gpt-oss CaMeL UT5 logs hold no tool message, so 'no payment' is a record limit there). Clean UT5: 6/6 utility true, 2 without a payment (DCA gpt-4o-mini, DCA gpt-oss). Effect on UA: at most 9/949 = 0.95 pp per arm (e.g. DCA gpt-4o-mini 631 -> 622, 66.49 -> 65.54 %; DCA Qwen3.6 471 -> 462).",
  run("checks") + "\n" + run("extra") + "  # ut5 per arm", "H5",
  "Disclose with the UA table (the DCA arms carry 9 vacuous passes each for gpt-4o-mini and Qwen3.6); keep logged utility; route counts under CC-07/CC-09.",
  "extend agentdojo.art.validity_defects (vacuous UT5 utility): expected += { snapshot = \"dca-agentdojo:v1\", count = 35, unit = \"executions\", basis = \"pre-check PC-dca-agentdojo-02: v1 non-CaMeL UT5 utility true without an executed Spotify payment (33 attacked + 2 clean); CaMeL 54 record-limited\", status = \"proposed\" }, { snapshot = \"dca-agentdojo:drift\", count = 9, ... }")
f(3, "The deposit's only non-zero DCA ASR (gpt-oss-20b causal, 3/949) consists entirely of run-error logs whose outcome the harness imposes (AD#154): by effect DCA ASR is 0/949 for all three models",
  "expected-known", "S2", "v1", "L1-08 / L1-05b",
  "4 logs carry an error string (first word 'Skipping' in all 4), all attacked, utility false, security true: DCA gpt-oss-20b travel 3 (= its whole 3/949 ASR), direct gpt-oss-20b slack 1 (of 321). Covered by profile quirk agentdojo.run_error_imposes_outcome (4 logs), so R2; raised to S2 because it carries a reported headline ASR of the deposit (Table 1 / results excerpt: causal 0.32 % for gpt-oss:20b) and its interpretation text.",
  run("pop") + "  # arms[...causal_budgeted].attacked: err 3, sec 3\n" + run("checks") + "  # errors[]",
  "", "Report DCA gpt-oss ASR as logged 3/949 and by effect 0/949 (3 run errors, AD#154); keep the logs and their imposed outcome (never exclude); add the deposit to the scope of the run-error catalogue entry with these counts (CC-09).",
  "scope the run-error entry (agentdojo run_error_imposed_outcome / AD#154) to dca-agentdojo:v1, count 4 logs (3 DCA gpt-oss travel, 1 direct gpt-oss slack), status proposed",
  "dca-agentdojo: the deposit's 3/949 residual DCA ASR (gpt-oss) is 3 run-error logs (AD#154); by effect 0/949")
f(4, "Two of the 15 cells of the deposit's Table 1 do not reproduce from the logs: GPT-4o-mini DRIFT UA 533 vs 553 logged, GPT-OSS-20B CaMeL+secpol UA 256 vs 270 (the 256/26.98 % equals the Qwen3.6 CaMeL+secpol cell)",
  "documentation-mismatch", "S2", "v1, drift", "L1-05b (H5)",
  "Population vs results/paper_tables/main_results_from_results_xlsx.md (identical in table_material_from_draft.md, results_from_xlsx.md, chapter4_results_excerpt.md, causalarmor matrix): 13 of 15 rows exact in both UA and ASR; all 15 ASR cells exact. DRIFT gpt-4o-mini UA 553/949 = 58.27 % [55.11, 61.37] vs 56.16 % (gap +2.11 pp); CaMeL+secpol gpt-oss UA 270/949 = 28.45 % [25.67, 31.40] vs 26.98 % (+1.47 pp). Neither exceeds the README section 4 gap rule (0 flags). R3: the logs are internally consistent; S2 because Table 1 is the deposit's headline table (no ranking claim in its text changes).",
  run("pop") + "  # rows_matched 13, flags []", "H5",
  "Use the logged counts; disclose both cell differences in the datasheet (likely transcription: the gpt-oss secpol cell duplicates the Qwen3.6 one). No exclusion.", None, None)
f(5, "No deposit table gives clean utility (6 clean arms) or the Qwen2-7B direct arm, although TABLE_ROW_TO_LOG_DIR maps both tables to directories",
  "documentation-mismatch", "S3", "v1", "L1-05b (H5)",
  "TABLE_ROW_TO_LOG_DIR.md lists a 'Qwen model-sensitivity' and a 'Clean utility' table with directories but no numbers; no file of the pin gives them. L1 population: clean utility gpt-4o-mini 70/97, DCA 67/97; gpt-oss 61/97, DCA 54/97; Qwen3.6 (OpenRouter) 87/97, DCA 77/97; Qwen2-7B attacked UA 169/949, ASR 10/949. Reported as the prereg's documentation gap.",
  run("pop"), "H5", "Report the L1 population rates as the only figures for these arms; mark them as not deposit-reported.", None, None)
f(6, "Profile context_artefacts (README.md, docs/*.md, code/*/README.md, third_party_licenses/*) omit the deposit's result tables (results/paper_tables/*.md, results/summaries/*.md), which the prereg's per-arm target rule needs",
  "documentation-mismatch", "S3", "v1, drift", "L1-01 / L1-10",
  "L1-01 dispositions context 10, not_selected 115 of 125 non-log members; the 9 table/summary .md files are not_selected, so L1-10 screened none of them. Supplementary scan of the 111 non-log members outside results/logs/ (nonlog.py): 0 account paths, 1 generic api_key assignment in code/drift_runner (placeholder-like, environment reference, no digit; not a secret).",
  run("nonlog"), "H11", "Profile owner: add results/paper_tables/*.md and results/summaries/*.md to context_artefacts (R4; AgentDojo family owner).", None, None)
f(7, "CaMeL arms log tool results without a proposing assistant tool call in at least 2,947 of 5,904 logs; no profile quirk covers it",
  "source-defect", "S3", "v1", "L1-08 (degenerate shapes) / L2 pre-condition",
  "Per CaMeL arm (984 logs): logs with zero assistant tool_calls / zero tool messages: gpt-4o-mini camel 680/109, +secpol 775/192; gpt-oss camel 646/418, +secpol 708/479; Qwen3.6 camel 718/49, +secpol 734/67, so at least 571+583+228+229+669+667 = 2,947 logs hold tool messages with no proposed call (the CaMeL interpreter calls tools from generated code). Non-CaMeL arms: zero tool calls implies zero tool messages in every arm. No outcome is biased (R1, S3), but evidence linkage of tool executions to model calls cannot come from the logs for these arms.",
  run("toolmsgs"), "-",
  "Declare a profile quirk (CaMeL tool executions without a proposing call); the post-check L2 (after D-455) must check A3 evidence linkage and dangling-relation issue classes on the CaMeL strata; never invent the missing call relation (invariant 2).",
  "[[family.agentdojo.quirk]] id = \"agentdojo.camel_interpreter_tool_results_without_call\" (observed >= 2,947 of 5,904 v1 CaMeL logs; pre-check PC-dca-agentdojo-07)",
  "dca-agentdojo CaMeL arms: tool results without a proposing call in >= 2,947 logs; L2 must not infer the call")
f(8, "L1-06: one secret-like string in the DRIFT part (/initial_checklist, keyword 'password') is AgentDojo banking benchmark content (the same token occurs in 1,735 other logs of the pin), not a credential",
  "expected-known", "S3", "drift", "L1-06 (H11)",
  "1 hit, class generic-credential-assignment, pointer /initial_checklist, banking user_task_14 x injection_task_3, DRIFT gpt-4o-mini; token 28 chars, lower case and punctuation only; byte-present in 1,735 other logs of the pin (benchmark environment text). 0 account paths in 16,221 logs; operator hits 0. Analogous to CC-02 (benchmark fixture string). Not security-relevant.",
  run("extra") + "  # drift_secret_hit", "H11", "No action beyond the datasheet note; the release scan should not treat this pointer as a secret.", None, None)
f(9, "[CC-09] no AgentDojo-family artefacts.toml entry scopes dca-agentdojo, so the catalogued #181, #161 and run-error artefacts above are not attributed by agentprov.artefacts.scan",
  "documentation-mismatch", "S3", "v1, drift", "catalogue scope",
  "Prereg section 5 (artefacts.toml has no DCA/Figshare id); counts to route: #181 17 (precedence 33), #161 v1 35 (33 attacked + 2 clean) + drift 9 (+54 CaMeL record-limited), run errors 4, slack IT5 (#168, CC-10) 0 of 49.",
  "grep -n dca src/agentprov/adapters/agentdojo/artefacts.toml  # 0 lines", "-", "AgentDojo family owner: widen the scopes (CC-09) with these counts.", None, None)
f(10, "Pre-check tool definitions differ from the census for null_final (4,521 v1 + 3 drift vs 4,274), trajectory repeats (CC-01) and the DRIFT injection-header count (134 runs / 166 occurrences vs 123 / 165)",
  "analysis-artefact", "S3", "v1, drift", "L1-04, L1-08, H8, H10",
  "null_final counts v1.k14 empty text blocks (CC-08 rule); L1-04 fingerprint excludes call ids (CC-01): 1,034 groups over both parts, same-cell cross-arm repeats CaMeL vs secpol 765 and Qwen3.6 direct vs DCA 243 (both = prereg), other 104 (census about 17); the examiner's '<INFORMATION>' count covers every message field, not the census's visible-frame rule. Not corpus properties (R5).",
  run("dup") + "\n" + run("checks") + "  # drift_information_*", "H8, H10", "None for the corpus; the post-check uses the same tools.", None, None)
fd = {"format": "agentprov-precheck-findings/0.1", "corpus_id": "dca-agentdojo", "findings": F, "refuted": []}
json.dump(fd, open(f"{D}/findings.json", "w"), indent=1, ensure_ascii=False)
H = {"H1": ["supported", "16,346 members; 16,221 logs (v1 13,374, drift 2,847); 125 non-log (context 10, not_selected 115); parse ok 16,221; 0 byte-identical"],
     "H2": ["supported", "13 attacked v1 arms 949 + 35; 6 clean arms 97; 3 drift arms 949"],
     "H3": ["supported", "drift security true 0 / 2,847 (never an exclusion reason)"],
     "H4": ["supported", "v1 attacked security true 772 / 12,337; benign + pre-pass 1,037 / 1,037"],
     "H5": ["supported (gap rule), with PC-04", "0 arms flagged; 13/15 Table 1 rows exact; 2 UA cells differ by +2.11 / +1.47 pp; clean and Qwen2-7B: no table (PC-05)"],
     "H6": ["supported", "13,374 naive 'YYYY-MM-DD HH:MM:SS', 2026-05-23 00:33:07 .. 2026-06-12 00:34:11; 0 outside the window (zone unrecorded)"],
     "H7": ["supported (Qwen3.6)", "final call-like text without tool_calls: Qwen3.6 local direct 225/949, local DCA 244/949 vs Qwen3.6 OpenRouter clean 0/97 and 0/97 (different condition); Qwen2-7B 42/949, no API arm; API arms gpt-4o-mini 0, gpt-oss 4 and 6 of 949"],
     "H8": ["supported for the pairs; 'other' not comparable (CC-01)", "same-cell repeats 765 / 243 exact; other 104 under the L1 fingerprint"],
     "H9": ["refuted (the arm part)", "proxy security true with trailing unexecuted calls: 6 logs (<= 161), all in direct arms (gpt-4o-mini 1, gpt-oss 4, Qwen2-7B 1); prereg marked the arm part an assumption; slack IT5 (#168, CC-10): 0 of 49 successes lack an executed membership call"],
     "H10": ["not tested (definition)", "134 runs / 166 occurrences of '<INFORMATION>' (all fields) vs 123 / 165 visible frames; positional part not computed"],
     "H11": ["refuted literally; benign", "1 secret-like benchmark string (PC-08); 0 account paths in logs and in 111 non-log members"],
     "H12": ["supported at L1 (precursors); sealing not tested", "negative duration 2 (CaMeL gpt-oss travel IT3 pre-pass; Qwen3.6 secpol workspace UT11/IT13); tool 'none' 1 (drift gpt-oss slack UT10/IT2)"]}
ex = {"corpus_id": "dca-agentdojo", "format": "agentprov-precheck-exam/0.1", "date": "2026-10-21",
      "code_commit": "L1 d97d3a574a4e745a815af7ff6f6692b371a36f5d (batch wave7, rc 0); examiner scripts run at 34fd4cbc",
      "examiner_scripts": S + " (zipread: agentprov.ingest open_zip/iter_zip_members + strict_json_loads, pin sha256 checked; pop, checks, extra, toolmsgs, dup, h12, nonlog, exam_build); counts only",
      "files_written": [f"docs/reports/precheck/data/dca-agentdojo/{x}" for x in ("exam.json", "findings.json", "os1-population.json", "checker.json", "extra.json", "toolmsgs.json", "dup-groups.json", "h12.json", "nonlog-scan.json", "exam-scripts/")] + ["docs/reports/precheck/dca-agentdojo.md"],
      "deposit_table_transcription": {"source": "results/paper_tables/main_results_from_results_xlsx.md (sha256 fa83f21c21db...)", "note": "prereg section 4 asked for a prereg amendment before any rate; the prereg is not edited by the examiner, so the transcription is recorded here and in exam-scripts/pop.py (T), made before pop.py ran",
                                      "rows": 15, "n_each": 949},
      "level1": {"v1": {"units": 13374, "parse_ok": 13374, "byte_identical_groups": 0, "trajectory_groups": 1016, "strata": 128, "secret_like": 0, "account_paths": 0, "null_final": 4521, "trailing_calls": 161, "error_present": 4},
                 "drift": {"units": 2847, "parse_ok": 2847, "byte_identical_groups": 0, "trajectory_groups": 18, "strata": 12, "secret_like": 1, "account_paths": 0, "null_final": 3, "ts_with": 356},
                 "cross": {"byte_identical_cross_corpus": 0, "trajectory_cross_corpus_pairs": {"mohameduk": 29, "authority-caps": 25, "melon": 17, "interbolt": 8, "sentry": 4, "ceferisbarov": 2, "ast-survey": 1, "gate": 1}, "cross_part_v1_drift": 0},
                 "l1_09": "0 AppleDouble / metadata members", "l1_10": "10 context files, 0 hits; supplement nonlog.py 111 members, 0 account paths"},
      "level2": "not run: import held until D-455 (url pin as archive input, regen item 101); sample list not drawn yet (follow-up)",
      "outcomes": "os1-population.json (per arm UA/ASR/clean, Wilson 95 %, Table 1 gap)", "hypotheses": H,
      "findings": [x["id"] for x in F],
      "followups": ["uv run python tools/precheck/l2_sample.py select --units ~/.agentprov/migration-work/precheck/dca-agentdojo/l1-units-v1.jsonl --source dca-agentdojo --part v1 --corpus-id dca-agentdojo --out docs/reports/precheck/data/dca-agentdojo/l2-sample-v1.json (and --part drift with l1-units-drift.jsonl): the prereg says the sample list is drawn at P0; it is missing",
                    "after D-455 and regen items 96/97: run_batch.py with a plan entry for both parts (sample, import_j2, import_j1, check) through tools/suite_queue.py --class import --cpu 2 --label precheck-dca-agentdojo; then code_ident.py --corpus-id dca-agentdojo --part v1|drift",
                    "post-check L2: A3 evidence linkage / dangling relations on the CaMeL strata (PC-07); H12 sealing; mapped outcomes vs l1 raw for the 4 run-error logs",
                    "H10 recount with the phase-10l census definition (visible frames, batch position)", "verifier pass on PC-01..PC-10"],
      "sample_size": None, "l2_status": "blocked (D-455)", "readiness": "ready-with-caveats"}
json.dump(ex, open(f"{D}/exam.json", "w"), indent=1, ensure_ascii=False); print(len(F), "findings")
