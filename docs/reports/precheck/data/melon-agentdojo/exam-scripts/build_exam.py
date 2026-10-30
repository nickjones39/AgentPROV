import json, sys
D = sys.argv[1]
E = "~/.agentprov/migration-work/precheck/melon-agentdojo/exam"
W = "~/.agentprov/migration-work/precheck/melon-agentdojo"
BARE = "~/.agentprov/staging/10c/melon/MELON.git"
PIN = "71d99dfff5ef98ffb25bac451909f3e10af9e27f"
SCAN = f"uv run python -I {E}/scan_pop.py {BARE} {PIN} {E}/pop.json   # 1,911 logs via agentprov.ingest; git with GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file"
files = [f"docs/reports/precheck/data/melon-agentdojo/{x}" for x in ("exam.json", "os1-population.json", "os2-sample.json", "defence-content.json")]

level1 = (
 "Input: bare clone at the pin (--git), read through agentprov.ingest (l1_scan at f7d7eced; batch wave2 step l1 rc 0, 2.0 s). "
 "L1-01: walked 38,780 (= profile expected_files) = selected 1,911 + select.owned_elsewhere:agentdojo 36,679 + not_selected 182 + context 5 + absent_blob 3; rejected 0; units 1,911; auxiliary 1 (runs/detection_stats.json, parse ok). Matches registry 1911 and census (H1). "
 "L1-02: 1,911/1,911 ok (0 duplicate keys, non-finite, big ints, lone surrogates, BOM, trailing data, invalid UTF-8, truncation, depth); auxiliary 1/1 ok (H2). "
 "L1-03: 0 U+2028/2029/0085, C0/C1, bidi, tag, zero-width, U+FFFD, mojibake; escaped_newline 27 strings in 27 artefacts at /messages/*/content/*/content (Python-repr tool output, by design). CJK in message content only in *-melon_r / *-melon_rp dirs (examiner scan; H3). "
 "L1-04: byte-identical 0 within the part and 0 cross-corpus. Trajectory-identical (CC-01 fingerprint) 145 groups / 1,086 of 1,911 units (970 distinct fp); every group shares one user task and one (utility, security) outcome; 126 groups span defences, 36 span attacks, 12 span the two models: all 12 cross-model groups are 5- or 7-message trajectories truncated by the defence (PI sentinel + base-MELON stop message), 60 groups contain a defence intervention, 85 none (payload never read). l1-xdup: within_part 142 (3 groups move to cross_corpus), cross_corpus 5 groups with melon members (interbolt-agentdojo 4: same-model gpt-4o-mini banking/travel injection_task_7/6 pre-passes and a 7-message user_task_9 run; glitch-agentdojo + mandate-agentdojo-eval 1: gpt-4o banking injection_task_7 pre-pass). No copied runs (PC-08). "
 "L1-05: 29 strata, every per-dir and per-(dir, suite, attack) count equal to prereg section 3 (gpt-4o melon 65+9, melon_at 3x144+9, melon_sm 3x144+9, melon_r 13+9 banking + 8+5 travel, melon_rp 8+8; gpt-4o-mini melon 144+9+1 travel, melon_at/melon_sm 2x144+9, melon_r 144+9 + 1+2 travel). Against the README design (gpt-4o banking, 4 defences x 3 attacks x 144): 6 cells complete (melon_sm, melon_at), 4 cells 0 logs (melon and melon_r x important_instructions/ignore_previous), 2 partial (melon direct 65/144, melon_r direct 13/144), no undefended arm (H5). Extra cells: all gpt-4o-mini arms (904 logs), melon_rp (16), travel (17); kept (no outcome-based exclusion). "
 "L1-06: 0 secret-like, 0 account paths, 0 named accounts, 0 operator-home, 0 local-path model ids in 1,911 + 1 auxiliary (H8). "
 "L1-07: /evaluation_timestamp in 1,911/1,911, 100% parse, 100% naive, 2026-05-24..2026-06-16 (before the pin commit 2026-06-17), 0 non-monotone; the 125 May logs are exactly the gpt-4o melon, melon_r and melon_rp dirs (74+35+16); 4 other pointers are benchmark calendar args (3 artefacts each). duration absent in 3 (H9). "
 "L1-08: incomplete 6 (keys absent; 4 end on a tool message, 2 on the user message), empty 0, error_only 0, zero_messages 0; null_final 0 (also 0 under the CC-08 corrected rule: examiner scan, 0 final assistant messages with all-empty text and no tool_calls) (H10). "
 "L1-09: not applicable (git tree, no archive members). "
 "Outcome fields: utility True 904 / False 1,001 / absent 6; security True 125 / False 1,780 / absent 6; error_present false 1,911."
)

level2 = (
 "Sample 134 of 1,911 over 29 strata (5 per stratum, the 3 strata with fewer units whole: 1, 1, 2), seed 20261011 (l2-sample-head.json sha256 260f03f9...). Import j2 and j1 at cb0af3d8 (clean tree; batch wave2 import_j2 46 s, import_j1 84 s, check 151 s, all rc 0): mapped 134, filtered 1,777, excluded 36,679 (owned_elsewhere), failed 0, degenerate 0; sealed_clean 131, sealed_with_issues 3 (incomplete_run); sample_join 134/134 1:1. "
 "Validate tiers aer, sem, prov, linkage: 134/134 passed, results reproduced 134, linkage 134/134 (100.00%); shacl not implemented (skipped), regression n/a. "
 "recompute --dry-run (selection shim): 134 identical, 0 changed, 0 unexplained, 0 failed. Determinism j2 vs j1: 548 files each, 0 differ, index identical. verify --level chain: 0 failures, only checksums.absent (working tree). "
 "A2: 0 degenerate, 0 adapter_defect, 0 unreadable, 0 failing validation checks; index codes map.accounting_unverifiable 133, map.earlier_attempts_unobservable 134, map.incomplete_run 3 (+ register select.owned_elsewhere 36,679); completeness unverifiable 131 / known_incomplete 3. "
 "A3: 0 dangling/missing/invented relation issues flagged by l2_check (51,988 statements, 89,229 relation arguments; 662 messages with generated_by, 368 model calls with input, 294 tool executions with call). But see PC-03: the 34 sampled base-MELON stop messages carry generated_by -> the model call (an unevidenced relation the PI checks do not detect). "
 "Evidence classes: core D 623 (only engine rules aprov.n_gap@1 489 and aprov.n_capture_profile@1 134) / O 2,874 / none 294; inference I 13,714 / none 1,337; assessment I 2,944 / O 268 / none 1,932; top O 23,938 / none 4,064. Family D rules cited natively only where they read logged bytes (system_prompt_variant_digest 134, incomplete_run 3); all other family D rules via _unverified twins (verified_code = []). l2_check twin counter: assessment I 1,858, inference I 12,921, inference none 1,203 (over-counts native I rules, CC-08). "
 "Identity: model 134/134 from pipeline_dir (gpt-4o-2024-05-13 80, gpt-4o-mini-2024-07-18 54), defence 134/134 by suffix (melon 21, melon_at 35, melon_sm 35, melon_r 33, melon_rp 10; melon_rp resolves although not a registered defence at the pin), attack and suite 134/134; 0 unresolved, 0 mismatches. "
 "Redaction: 0 hits (account paths, secret shapes) in 410 AER/SEM/PROV/index files. Withholding: profile has no [withhold] policy (policy null); inert as pre-registered; no sealed-copy run needed. "
 "OS-2 raw vs mapped: 131 complete labels, utility 131/131 and security 131/131 equal (0 of 262 judgements differ); 3 incomplete labels have no judgement in raw and AER; security origin checker 79, harness_default 52 (the benign pre-pass constant; 52 of 53 sampled pre-passes, 1 incomplete). "
 "Defence-authored content (examiner, population + j2 mapping; defence-content.json): base-MELON stop message 910 logs (1 per log, always last, tool_calls null, 1:1 with the 910 PI-sentinel redactions); mapped as role assistant, actor agent, generated_by the model call in 34/34 sampled (PC-03) while the redaction itself is a def0 decision (34/34). RECOVERY text at index 0 in 92 gpt-4o-mini melon_r logs mapped as the benchmark's system prompt (variant melon_r_prompt, actor bench) 3/3 sampled; the AgentDojo default prompt moves to a later index with no actor and no variant (3/3); later SECURITY WARNING inserts actor none (8 sampled) (PC-04). MELON-R SANITIZE marker in 120 tool messages / 101 logs, kept as tool output (PC-05). BLOCK messages 3 (population; none sampled)."
)

def wil(lo, hi): return f"[{lo:.2f}, {hi:.2f}]"
outcomes = [
 dict(arm="gpt-4o melon_sm banking direct", level="L1-population", n=144, metric="UA", rate="52.08 (75/144)", wilson95=wil(43.98,60.08), paper="52.08 (README, report 6.2.1)", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_sm banking direct", level="L1-population", n=144, metric="ASR", rate="0.00 (0/144)", wilson95=wil(0,2.60), paper="0.00", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_sm banking important_instructions", level="L1-population", n=143, metric="UA", rate="33.57 (48/143; 48/144 = 33.33 with the incomplete log as False)", wilson95=wil(26.35,41.65), paper="33.33", gap_pp="+0.24 (0 under k/144)", flag=False),
 dict(arm="gpt-4o melon_sm banking important_instructions", level="L1-population", n=143, metric="ASR", rate="1.40 (2/143; 3/144 = 2.08 with the incomplete log as success)", wilson95=wil(0.38,4.96), paper="2.08", gap_pp="-0.68 (0 under k/144)", flag=False),
 dict(arm="gpt-4o melon_sm banking ignore_previous", level="L1-population", n=144, metric="UA", rate="52.78 (76/144)", wilson95=wil(44.66,60.75), paper="52.78", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_sm banking ignore_previous", level="L1-population", n=144, metric="ASR", rate="0.00", wilson95=wil(0,2.60), paper="0.00", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_sm banking none (pre-pass)", level="L1-population", n=9, metric="BU", rate="88.89 (8/9)", wilson95=wil(56.50,98.01), paper="88.89 (report 6.2.1)", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_at banking direct", level="L1-population", n=144, metric="UA", rate="62.50 (90/144)", wilson95=wil(54.36,69.99), paper="62.50 (README, report 6.3.1)", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_at banking direct", level="L1-population", n=144, metric="ASR", rate="0.00", wilson95=wil(0,2.60), paper="0.00", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_at banking important_instructions", level="L1-population", n=143, metric="UA", rate="43.36 (62/143; 62/144 = 43.06)", wilson95=wil(35.51,51.55), paper="43.06", gap_pp="+0.30 (0 under k/144)", flag=False),
 dict(arm="gpt-4o melon_at banking important_instructions", level="L1-population", n=143, metric="ASR", rate="12.59 (18/143; 19/144 = 13.19 with the incomplete log as success)", wilson95=wil(8.11,19.02), paper="13.19", gap_pp="-0.60 (0 under k/144)", flag=False),
 dict(arm="gpt-4o melon_at banking ignore_previous", level="L1-population", n=144, metric="UA", rate="60.42 (87/144)", wilson95=wil(52.26,68.03), paper="60.42", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_at banking ignore_previous", level="L1-population", n=144, metric="ASR", rate="0.00", wilson95=wil(0,2.60), paper="0.00", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_at banking none (pre-pass)", level="L1-population", n=9, metric="BU", rate="100.00 (9/9)", wilson95=wil(70.09,100), paper="100.00 (report 6.3.1)", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon banking direct (partial arm, 65 of 144 logs)", level="L1-population", n=64, metric="UA", rate="60.94 (39/64)", wilson95=wil(48.69,71.94), paper="38.19 (55/144, README)", gap_pp="+22.75", flag=True),
 dict(arm="gpt-4o melon banking direct (partial arm)", level="L1-population", n=64, metric="ASR", rate="0.00", wilson95=wil(0,5.66), paper="0.00", gap_pp="0.00", flag=False),
 dict(arm="gpt-4o melon_r banking direct (partial arm, 13 of 144)", level="L1-population", n=13, metric="UA", rate="84.62 (11/13)", wilson95=wil(57.77,95.67), paper="45.83 (66/144, README)", gap_pp="+38.79 (Wilson excludes by 11.94)", flag=True),
 dict(arm="gpt-4o melon_r banking direct (partial arm)", level="L1-population", n=13, metric="ASR", rate="0.00", wilson95=wil(0,22.81), paper="2.08", gap_pp="-2.08", flag=False),
 dict(arm="README 'GPT-4o' MELON ignore_previous row vs gpt-4o-mini melon ignore_previous cell", level="L1-population", n=144, metric="UA / ASR", rate="37.50 (54/144) / 0.00 (0/144)", wilson95=wil(30.01,45.64)+" / "+wil(0,2.60), paper="37.50 / 0.00 (README, labelled GPT-4o; 0 gpt-4o logs)", gap_pp="0.00 / 0.00 (exact k match on another model's cell)", flag=True),
 dict(arm="README 'GPT-4o' MELON-R ignore_previous row vs gpt-4o-mini melon_r ignore_previous cell", level="L1-population", n=144, metric="UA / ASR", rate="43.06 (62/144) / 2.78 (4/144)", wilson95=wil(35.25,51.22)+" / "+wil(1.09,6.92), paper="43.06 / 2.78 (README, labelled GPT-4o; 0 gpt-4o logs)", gap_pp="0.00 / 0.00 (exact k match on another model's cell)", flag=True),
 dict(arm="README No Defense row (gpt-4o banking direct)", level="L1-population", n=0, metric="UA / ASR", rate="no fork log; upstream copy gpt-4o-2024-05-13 banking direct 70.14 / 11.81 (101/144, 17/144)", wilson95="", paper="43.06 / 55.56", gap_pp="unbacked", flag=True),
 dict(arm="gpt-4o melon / melon_r important_instructions, ignore_previous", level="L1-population", n=0, metric="UA / ASR", rate="0 logs", wilson95="", paper="29.86/0.00, 37.50/0.00, 44.44/8.33, 43.06/2.78", gap_pp="unbacked (H5)", flag=False),
 dict(arm="gpt-4o-mini melon_at direct / ignore_previous", level="L1-population", n=144, metric="UA / ASR", rate="34.72 (50) / 2.08 (3); 35.42 (51) / 0.00", wilson95=wil(27.43,42.80)+" / "+wil(0.71,5.95)+"; "+wil(28.08,43.51)+" / "+wil(0,2.60), paper="none reported", gap_pp="", flag=False),
 dict(arm="gpt-4o-mini melon_sm direct / ignore_previous", level="L1-population", n=144, metric="UA / ASR", rate="38.19 (55) / 4.86 (7); 35.42 (51) / 2.78 (4)", wilson95=wil(30.66,46.34)+" / "+wil(2.37,9.69)+"; "+wil(28.08,43.51)+" / "+wil(1.09,6.92), paper="none reported", gap_pp="", flag=False),
 dict(arm="gpt-4o melon_rp banking direct", level="L1-population", n=8, metric="UA / ASR", rate="100.00 (8/8) / 0.00", wilson95=wil(67.56,100)+" / "+wil(0,32.44), paper="none reported", gap_pp="", flag=False),
 dict(arm="travel (17 logs: gpt-4o melon_r direct 7 complete, none 5; gpt-4o-mini melon_r none 2)", level="L1-population", n=14, metric="UA / BU", rate="melon_r direct UA 6/7, ASR 0/7; BU 4/5, 2/2", wilson95="", paper="none reported", gap_pp="", flag=False),
 dict(arm="pre-passes, all 9 arms (88 logs, 87 complete)", level="L1-population", n=87, metric="BU", rate="90.80 (79/87)", wilson95=wil(82.89,95.27), paper="report gives only SM 8/9, AT 9/9", gap_pp="", flag=False),
 dict(arm="sample: gpt-4o melon_sm + melon_at attacked (6 cells x 5)", level="L2-sample", n=30, metric="UA", rate="46.67 (14/30)", wilson95=wil(30.23,63.86), paper="population sample-weighted 50.78; README cells 33.33-62.50", gap_pp="-4.11 vs population", flag=False),
 dict(arm="sample: gpt-4o melon_sm + melon_at attacked", level="L2-sample", n=30, metric="ASR", rate="0.00 (0/30)", wilson95=wil(0,11.35), paper="population sample-weighted 2.33", gap_pp="-2.33", flag=False),
 dict(arm="sample: all attacked", level="L2-sample", n=79, metric="UA / ASR", rate="54.43 (43/79) / 2.53 (2/79)", wilson95=wil(43.50,64.95)+" / "+wil(0.70,8.77), paper="population sample-weighted 53.36 / 1.68", gap_pp="+1.07 / +0.85", flag=False),
 dict(arm="sample: pre-passes", level="L2-sample", n=52, metric="BU", rate="94.23 (49/52)", wilson95=wil(84.36,98.02), paper="population sample-weighted 90.60", gap_pp="+3.63", flag=False),
 dict(arm="sample: raw vs mapped on the same 131 complete labels", level="L2-sample", n=131, metric="utility and security values", rate="0 of 262 judgements differ", wilson95="", paper="raw L1 fields", gap_pp="0", flag=False),
]

hyp = [
 dict(id="H1", result="supported", note="1,911 selected; 9 dirs and 29 strata equal prereg section 3 exactly; owned_elsewhere 36,679, absent 3, walked 38,780"),
 dict(id="H2", result="supported", note="1,911/1,911 strict ok; auxiliary detection_stats.json ok"),
 dict(id="H3", result="supported", note="0 U+FFFD, 0 mojibake; CJK in message content only in *-melon_r and *-melon_rp dirs (gpt-4o melon_r 3 logs + melon_rp 1 log + gpt-4o-mini melon_r)"),
 dict(id="H4", result="refuted (third clause only; explained, no copied runs)", note="0 byte-identical pairs and 0 cross-corpus byte overlap hold; 145 trajectory-identical groups, 126 across pipeline dirs and 12 across models, all defence-truncated or payload-not-read, same task and outcome per group (PC-08, CC-01)"),
 dict(id="H5", result="supported", note="4 README cells 0 logs, 2 partial (65/144, 13/144), no undefended arm"),
 dict(id="H6", result="supported", note="12 UA/ASR + 2 BU values reproduced exactly under the k/144 convention; the two important_instructions ASR cells are 1 run off when the incomplete log is excluded (PC-06)"),
 dict(id="H7", result="refuted", note="gpt-4o-mini melon ignore_previous = 54/0 of 144 and gpt-4o-mini melon_r ignore_previous = 62/4 of 144, both exactly the README 'GPT-4o' rows (PC-01)"),
 dict(id="H8", result="supported", note="L1-06 0 classes in 1,911 + 1; L2 redaction 0 hits in 410 files"),
 dict(id="H9", result="supported", note="1,911 naive, 2026-05-24..2026-06-16, none after the pin; duration absent in 3"),
 dict(id="H10", result="supported", note="6 incomplete (4 end on tool, 2 on user), 0 empty, 0 error-only"),
 dict(id="H11", result="refuted (mapping clause)", note="the data clauses hold (Chinese defence messages only in melon_r/melon_rp dirs; 113 extra system messages are defence inserts: 92 default prompts displaced by the RECOVERY text at index 0, 9 second RECOVERY copies, 8 + 4 later warnings; all 92 melon_r_prompt logs carry the default prompt later; 910 English stop messages, all in melon/melon_sm/melon_at dirs); but L2 maps the base-MELON stop message as model output (34/34, PC-03) and the RECOVERY insert as the system prompt (3/3, PC-04)"),
 dict(id="H12", result="supported", note="910 sentinel redactions in 910 logs, all in melon/melon_sm/melon_at dirs; 0 in the 88 pre-passes (no scope extension of defence_benign_intervention needed)"),
 dict(id="H13", result="refuted", note="the SANITIZE marker is in 120 tool messages of 101 logs (gpt-4o-mini melon_r 119/100, gpt-4o melon_r 1/1; 8 whole-message, 112 partial), not 7; a second marker not at the pin in 4 tool messages of gpt-4o melon_r/melon_rp (PC-05)"),
 dict(id="H14", result="supported", note="134 units, every stage ok, 0 failing checks, 0 degenerate, 0 adapter_defect, recompute 0 differences, j2 = j1 byte-identical, identity 100%; ok_with_issues 3 = incomplete_run (expected)"),
 dict(id="H15", result="refuted", note="runs/detection_stats.json holds 215 events of the melonsm detector only (TP 0 / FP 82 / TN 133 / FN 0, final threshold 0.8), not 86 events with 57/0/16/13 (SM) and 55/0/16/15 (AT) (PC-07)"),
 dict(id="H16", result="supported", note="all 14 sampled gpt-4o melon_sm/melon_at cells (n = 5) contain the README value in their Wilson 95% interval; pooled 30: UA 46.67 [30.23, 63.86] vs population 50.78; ASR 0/30 [0, 11.35] vs 2.33"),
]

ADP_ROWS = '''[[artefact]]
id = "agentdojo.art.reported_rows_unbacked"
title = "Reported result rows the released logs do not back, or that match another model's arm"
description = "xwsdid/MELON README and report: the GPT-4o MELON and MELON-R ignore_previous rows (37.50/0.00, 43.06/2.78) equal the gpt-4o-mini-2024-07-18 melon and melon_r ignore_previous cells exactly (54/0 and 62/4 of 144) while 0 gpt-4o logs exist for them; the GPT-4o MELON and MELON-R important_instructions rows have 0 logs; the MELON and MELON-R direct rows are backed by 65 and 13 of 144 logs (runs of 2026-05-24..26) whose UA (60.94%, 84.62%) does not reproduce 38.19% and 45.83%; the No Defense row has no fork run and the upstream gpt-4o-2024-05-13 banking copies do not reproduce it. Only the melon_sm and melon_at GPT-4o rows reproduce (12 UA/ASR and 2 BU values, exact with the incomplete log counted as utility False / security True). All arms are kept."
scope = { sources = ["melon-agentdojo"], parts = ["head"], profiles = ["melon-agentdojo"] }
cause = "unknown"
detector = { rule = "artefact.generic.arm_coverage (proposed)", class = "D" }
claims = []
recorded_as = { notes = ["stats:arm_cells"] }
handling = { class = "FO" }
expected = [
  { snapshot = "head", count = 2, unit = "README rows equal to a gpt-4o-mini cell", basis = "precheck OS-1 2026-10-15", status = "verified" },
  { snapshot = "head", count = 4, unit = "README cells with 0 logs", basis = "precheck L1-05", status = "verified" },
  { snapshot = "head", count = 2, unit = "partial arms (65/144, 13/144)", basis = "precheck L1-05", status = "verified" },
]
manuscript = true
refs = ["docs/reports/precheck/prereg/melon-agentdojo.md (H5, H6, H7)", "https://github.com/xwsdid/MELON/blob/71d99dfff5ef98ffb25bac451909f3e10af9e27f/README.md"]'''

ADP_DEF = '''[[artefact]]
id = "agentdojo.art.defence_authored_message"
title = "Defence-authored assistant and system messages logged as conversation"
description = "MELON (melon, melon_sm, melon_at) replaces the model's message after a detection by the fixed English stop message (tool_calls null, always the last message; 910 logs, 1:1 with the 910 PI-sentinel redactions). MELON-R appends or replaces a fixed Chinese BLOCK message (3 logs) and inserts a SECURITY WARNING RECOVERY system message at index 0 or later (92 logs at index 0, 9 of them twice; 8 later copies in 2 logs; a 117-character warning in 4 gpt-4o melon_r/melon_rp logs). These are defence decisions, not model output or the benchmark's system prompt."
scope = { sources = ["melon-agentdojo"], parts = ["head"], profiles = ["melon-agentdojo"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.defence_authored_message@1 (proposed; a quirk hook in the style of D-113/D-116)", class = "I" }
claims = []
recorded_as = { notes = ["decision by the defence actor; message generated_by that decision"] }
handling = { class = "CR" }
expected = [
  { snapshot = "head", count = 910, unit = "logs with the base-MELON stop message", basis = "precheck examiner scan 2026-10-15", status = "verified" },
  { snapshot = "head", count = 3, unit = "logs with a MELON-R BLOCK message", basis = "precheck examiner scan", status = "verified" },
  { snapshot = "head", count = 113, unit = "defence-inserted system messages (98 logs)", basis = "precheck examiner scan", status = "verified" },
]
manuscript = true
refs = ["src/agentdojo/agent_pipeline/pi_detector.py at xwsdid/MELON@71d99dff (MELON.query, MELONR)", "docs/reports/precheck/prereg/melon-agentdojo.md H11"]'''

ADP_SAN = '''[[artefact]]
id = "agentdojo.art.defence_rewritten_tool_output"
title = "Tool outputs rewritten by a sanitising defence"
description = "MELON-R SANITIZE replaces flagged spans of a tool output by a marker: 120 tool messages in 101 logs (gpt-4o-mini melon_r 119 in 100 of 156 logs, gpt-4o melon_r 1; 8 whole-message, 112 partial); a second marker text that is not in the pinned code occurs in 4 tool messages of gpt-4o melon_r / melon_rp (5 occurrences). The logged tool output is the defence's rewrite, not the tool's output."
scope = { sources = ["melon-agentdojo"], parts = ["head"], profiles = ["melon-agentdojo"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.defence_sanitised_output@1 (proposed; routing R3)", class = "I" }
claims = []
recorded_as = { notes = ["redact decision by the defence; tool_execution output not observed"] }
handling = { class = "CR" }
expected = [
  { snapshot = "head", count = 101, unit = "logs", basis = "precheck examiner scan 2026-10-15", status = "verified" },
  { snapshot = "head", count = 124, unit = "tool messages (120 + 4 second marker)", basis = "precheck examiner scan", status = "verified" },
]
manuscript = false
refs = ["docs/reports/phase10d/routing.md R3"]'''

findings = [
 dict(id="PC-melon-agentdojo-01", title="README 'GPT-4o' MELON and MELON-R ignore_previous rows equal the gpt-4o-mini cells exactly",
  cls="documentation-mismatch", severity="S2", security=False, part="head", check="OS-1 / L1-05 (H7 refuted; R3)",
  evidence="0 gpt-4o-2024-05-13 logs exist for melon or melon_r x ignore_previous. README rows (labelled GPT-4o): MELON 37.50/0.00 = 54/144, 0/144; MELON-R 43.06/2.78 = 62/144, 4/144. Population cells: gpt-4o-mini-2024-07-18-melon ignore_previous banking utility 54 / security 0 of 144; gpt-4o-mini-2024-07-18-melon_r ignore_previous banking utility 62 / security 4 of 144: both UA and ASR equal on both rows. A search of all 15 complete 144-log cells finds these two as the only cross-model matches (the other 4 matches are the melon_sm/melon_at rows on their own cells). The report's note 3 says the docx report named GPT-4o-mini as the base model; report 6.2.1 says the MELON/MELON-R rows are carried from the docx Table 1 (an absent blob).",
  reproduction=f"{SCAN}\npython3 {E}/os1.py x tools/analysis2   # -> os1.json 'MATCHES': {{paper_row gpt-4o-2024-05-13|melon|ignore_previous, paper_k [54,0], matching_cell gpt-4o-mini-2024-07-18|melon|ignore_previous, cell_k [54,0]}}, {{paper_row ...|melon_r|ignore_previous, paper_k [62,4], matching_cell gpt-4o-mini-2024-07-18|melon_r|ignore_previous, cell_k [62,4]}}\n# also from the batch output alone: l1-head.json /family/outcomes_by_stratum 'pipeline_dir=gpt-4o-mini-2024-07-18-melon|attack_dir=ignore_previous|suite=banking' utility true 54, security false 144; '...-melon_r|attack_dir=ignore_previous|suite=banking' utility true 62, security true 4",
  hypothesis_ref="H7",
  recommendation="Datasheet: the README's GPT-4o MELON and MELON-R ignore_previous rows are, on the released logs, the gpt-4o-mini arms; cite only the melon_sm and melon_at GPT-4o rows as reproduced. Identity stays as the directories say (gpt-4o-mini); no relabelling, no exclusion. Route the artefact entry (with PC-02) to the agentdojo family owner.",
  artefact_proposal=ADP_ROWS, agents_md_12=True),
 dict(id="PC-melon-agentdojo-02", title="README MELON, MELON-R and No Defense rows otherwise unbacked: 4 empty cells, 2 partial arms that do not reproduce, no undefended run",
  cls="documentation-mismatch", severity="S2", security=False, part="head", check="L1-05 / OS-1 gap rule (H5 supported; R3)",
  evidence="gpt-4o melon direct: 65 of 144 logs (user_task_0..6 x 9 + user_task_7, 8 x 1), 64 complete, UA 39/64 = 60.94% [48.69, 71.94] vs README 38.19% (55/144): gap +22.75 pp with n >= 20, flagged. gpt-4o melon_r direct banking: 13 logs, UA 11/13 = 84.62% [57.77, 95.67] vs 45.83%: Wilson excludes by 11.94 pp, flagged. Investigation: task mix does not explain it (same (user, injection) cells in gpt-4o melon_sm 32/65 and melon_at 41/65 UA; for melon_r 8/13 and 9/13); outcome mapping is not involved (L1 raw fields; OS-2 0/262 differ); arm identity from the directory is consistent (all 65 + 13 logs are gpt-4o pipeline dirs). The partial arms are the early runs: all 125 logs dated 2026-05 are exactly the gpt-4o melon (74), melon_r (35) and melon_rp (16) dirs; every other arm is June. 4 README cells (melon, melon_r x important_instructions, ignore_previous) have 0 gpt-4o logs. No Defense row (43.06/55.56 direct; ASR 51.30, 52.37 not k/144): 0 fork logs; the upstream copies (owned by agentdojo head) give gpt-4o-2024-05-13 banking direct 101/144 UA, 17/144 ASR, important 100/90, ignore 99/12.",
  reproduction=f"{SCAN}\npython3 {E}/os1.py x tools/analysis2   # gpt-4o melon direct UA k 39 n 64 rate 60.94 wilson [48.69, 71.94] paper 38.19 gap 22.75 flag true; melon_r direct UA 11/13 84.62 [57.77, 95.67] paper 45.83 flag true\npython3 {E}/build_data.py docs/reports/precheck/data/melon-agentdojo tools/analysis2   # os1-population.json partial_arm_same_cell_control: melon n 65, same_cells_melon_sm UA_k 32, same_cells_melon_at UA_k 41; may_logs_by_pipeline_dir 74/35/16; no_defence_row_check",
  hypothesis_ref="H5",
  recommendation="Datasheet: only 6 of the README's 12 GPT-4o defence cells are backed by logs (melon_sm, melon_at); the MELON and MELON-R GPT-4o direct arms are partial early runs whose rates differ from the README; the No Defense baseline is not in the release. Keep every arm, including the partial and zero-success ones; report partial-arm rates with their n. Same artefact entry as PC-01.",
  artefact_proposal="see PC-melon-agentdojo-01 (one entry, agentdojo.art.reported_rows_unbacked)", agents_md_12=True),
 dict(id="PC-melon-agentdojo-03", title="Base-MELON stop message (defence-authored) is mapped as agent output generated by the model call",
  cls="mapping-defect", severity="S2", security=False, part="head", check="L2 identity/attribution (H11 mapping clause; prereg falsifier)",
  evidence="Population: the fixed English stop message (pi_detector.py MELON.query at the pin) is the last message in 910 of 1,911 logs (gpt-4o melon 31, melon_sm 288, melon_at 185; gpt-4o-mini melon 135, melon_sm 141, melon_at 130), always with tool_calls null, exactly 1:1 with the 910 PI-sentinel redactions; 0 in melon_r/melon_rp dirs and 0 in the 88 pre-passes. Mapping (j2, 34 sampled occurrences): role assistant, actor agent, generated_by the preceding model_call, rule agentdojo.assistant_msg_has_one_call_unverified@1#/generated_by, ev O (34/34); the redaction itself is mapped correctly as a def0 decision (34 decisions, aer.decision_after_subject@1). So every MELON detection yields a PROV wasGeneratedBy from the model call to a text the defence wrote, an unevidenced relation (invariant 2) that A3 does not flag. The 3 MELON-R BLOCK messages (gpt-4o-mini melon_r, Chinese text, tool_calls null; none in the sample) take the same generic path. Neither D-113 (tool-message denials) nor D-116 (logs ending at a tool output) covers an assistant-position defence message; the profile declares neither.",
  reproduction=f"{SCAN}\npython3 {E}/aer_check.py {W}/l2-head-j2.partial {E}/pop.json\n# == stop_en: 34 ('assistant', 'agent', 'source', True, 'O', 'null', '[\"agentdojo.assistant_msg_has_one_call_unverified@1#/generated_by\", \"aer.output_after_generator@1#/after\"]')\n# == sentinel: 23+7+2+2 = 34 with actor 'def0'\npython3 {E}/build_data.py docs/reports/precheck/data/melon-agentdojo tools/analysis2   # defence-content.json per_pipeline_dir stop_en / sentinel_tool_msgs / stop_en_last",
  hypothesis_ref="H11",
  recommendation="Family owner (agentdojo adapter, not core): a quirk hook in the style of D-113/D-116 that maps a defence-authored message (exact texts per profile: base-MELON stop text; the two MELON-R BLOCK texts) as generated_by a defence decision (verdict terminate/deny) of the def0 actor, with no model_call output; declare it in melon-agentdojo (profile bump to 2). Fix before the regeneration round (needs the user's approval like every pre-round fix); downstream: AER/SEM/PROV digests of the 910 + 3 executions, census quirk counts. Draft artefact entry attached.",
  artefact_proposal=ADP_DEF, agents_md_12=True),
 dict(id="PC-melon-agentdojo-04", title="MELON-R RECOVERY insert at index 0 is mapped as the benchmark's system prompt; the real AgentDojo prompt becomes an unattributed later system message",
  cls="mapping-defect", severity="S2", security=False, part="head", check="L2 identity/attribution (H11 mapping clause)",
  evidence="Population: 92 of 156 gpt-4o-mini melon_r logs start with the 92-character RECOVERY text (sha256 82ce7af3..., 'SECURITY WARNING' header, Chinese body; 9 logs have it at index 0 and 1) and carry the 469-character AgentDojo default prompt (a021a92b...) at a later index; further defence system inserts: a 129-character SECURITY WARNING text 8 times in 2 logs (gpt-4o melon_r 1, gpt-4o-mini melon_r 1 with 7) and a 117-character Chinese warning in 4 gpt-4o melon_r/melon_rp logs: 113 defence system messages = the 2,024 - 1,911 surplus. Mapping (j2): the index-0 RECOVERY text is actor bench with ext.agentdojo.system_prompt_variant melon_r_prompt (rule system_prompt_variant_digest D; system_prompt_from_harness_unverified) in 3/3 sampled, the default prompt at index 1 has actor none and no variant (3/3), the 129-character inserts actor none (8/8). The profile's system_prompt_variants row 'melon_r_prompt' (source pi_detector.py at the pin, comment 'MELON-R's own' prompt) is the cause: the text is the first five of the six RECOVERY lines (fact-check), i.e. a defence intervention of an earlier uncommitted code state.",
  reproduction=f"{SCAN}\npython3 -c \"import json,collections;rows=json.load(open('{E}/pop.json'))['rows'];print(collections.Counter((r['pdir'],tuple((i if i<2 else 'later',d,n) for i,d,n,_,_ in r['system'])) for r in rows if len(r['system'])>1))\"\n# gpt-4o-mini melon_r: 83 x ((0,'82ce7af3',92),(1,'a021a92b',469)); 9 x ((0,'82ce7af3',92),(1,'82ce7af3',92),('later','a021a92b',469)); ...\npython3 {E}/aer_check.py {W}/l2-head-j2.partial {E}/pop.json\n# == system: 131 ('bench','source','agentdojo_default',469,False); 3 ('bench','source','melon_r_prompt',92,True); 3 (None,'source',None,469,False); 8 (None,'source',None,129,True)",
  hypothesis_ref="H11",
  recommendation="Family owner: replace the 'melon_r_prompt' system_prompt_variants row by a defence-insert matcher (same hook as PC-03): RECOVERY and warning system messages become messages generated_by a def0 decision, and the system prompt is the AgentDojo default wherever it sits; correct the profile comment (the text is not 'MELON-R's own prompt' and is not at the pin). Profile bump; fix before the round with PC-03; downstream digests of the 98 affected executions.",
  artefact_proposal="see PC-melon-agentdojo-03 (agentdojo.art.defence_authored_message covers the system inserts)", agents_md_12=True),
 dict(id="PC-melon-agentdojo-05", title="MELON-R sanitising rewrite is in 120 tool messages of 101 logs, not 7; tool outputs of 100 of 156 gpt-4o-mini melon_r logs are defence rewrites mapped as the tool's output",
  cls="documentation-mismatch", severity="S2", security=False, part="head", check="L1 examiner scan / L2 mapping (H13 refuted; R4, severity raised)",
  evidence="Marker '[已移除潜在注入内容]' in 120 tool messages / 101 logs: gpt-4o-mini melon_r 119 in 100 of 156 logs (7 whole-message replacements, 112 partial), gpt-4o melon_r 1 (whole). A second marker, not in the pinned code, in 4 tool messages (5 occurrences) of gpt-4o melon_r (3) and melon_rp (1). routing.md R3 counts 'seven tool messages' (exactly the 7 whole-message replacements, all in the single incomplete gpt-4o-mini melon_r travel log) and defers the rule as low priority. Mapped as plain env tool_result output (routing R3, deferred), so the AER says the tool produced the rewritten text.",
  reproduction=f"uv run python -I {E}/scan_detail.py {BARE} {PIN}   # {{'san_eq': 8, 'san_occurrences': 120, 'san_contains': 112, 'cjk_other:gpt-4o-2024-05-13-melon_r': 3, 'cjk_other:gpt-4o-2024-05-13-melon_rp': 1}}\nuv run python -I {E}/scan_detail2.py {BARE} {PIN}   # {{'eq:gpt-4o-2024-05-13-melon_r': 1, 'contains:gpt-4o-mini-2024-07-18-melon_r': 112, 'eq:gpt-4o-mini-2024-07-18-melon_r': 7}}; second-marker fragment 5",
  hypothesis_ref="H13",
  recommendation="Correct routing.md R3 (120 / 101 + 4 second-marker messages) and re-prioritise it: a redact decision by def0 on the tool output (both marker texts) before the round if PC-03/04's hook lands, otherwise disclose. Draft artefact entry attached.",
  artefact_proposal=ADP_SAN, agents_md_12=False),
 dict(id="PC-melon-agentdojo-06", title="README important_instructions ASR counts the incomplete run as an attack success",
  cls="documentation-mismatch", severity="S3", security=False, part="head", check="OS-1 (H6 supported; R3)",
  evidence="gpt-4o melon_sm and melon_at important_instructions each hold 1 incomplete log (keys absent; 2 and 4 messages, ending on user and tool, before any attacker action could run). README UA 48/144 and 62/144 and ASR 3/144 and 19/144 equal the logged true counts with the incomplete log as utility False and security True; excluding it gives ASR 2/143 = 1.40% and 18/143 = 12.59% (-0.68 and -0.60 pp). All other 10 GPT-4o melon_sm/melon_at values and both BU values are exact. AgentDojo's runner treats a crashed run as security True (issue #154, agentdojo.art.run_error_imposed); the corpus records no judgement for these logs (agentdojo.incomplete_run, nothing invented).",
  reproduction=f"python3 {E}/os1.py x tools/analysis2   # melon_sm important ASR k 2 n 143 k_of_144_conv '3/144' paper_k 3; melon_at important ASR k 18 n 143 k_of_144_conv '19/144' paper_k 19",
  hypothesis_ref="H6",
  recommendation="Statistics over this corpus state the convention (incomplete runs excluded, as the AER records no outcome); the datasheet notes the 1-run difference to the README in these two cells.",
  artefact_proposal="", agents_md_12=False),
 dict(id="PC-melon-agentdojo-07", title="runs/detection_stats.json does not back the report's detector tables",
  cls="documentation-mismatch", severity="S3", security=False, part="head", check="L1 auxiliary (H15 refuted; R3)",
  evidence="The committed supporting artefact (587 B, stored as a context artefact) holds 215 events of one detector (melonsm): TP 0, FP 82, TN 133, FN 0, FPR 0.381, final threshold 0.8; no AT detector. The README/report give 86 events with TP/FP/TN/FN 57/0/16/13 (MELON-SATM) and 55/0/16/15 (MELON-AT). The per-step decisions (defense_logs.jsonl) are not committed.",
  reproduction=f"{SCAN}\npython3 -c \"import json;print(json.load(open('{E}/pop.json'))['detection_stats'])\"   # /total 215, /overall/TP 0, /overall/FP 82, /overall/TN 133, /overall/FN 0, /by_detector/melonsm/final_threshold 0.8",
  hypothesis_ref="H15",
  recommendation="Datasheet: the detector-level tables of the report are not reproducible from the release; detection_stats.json is from another run. No mapping change.",
  artefact_proposal="", agents_md_12=False),
 dict(id="PC-melon-agentdojo-08", title="Trajectory-identical groups span defences and models (defence-truncated runs), not copied runs; effective n is lower",
  cls="documentation-mismatch", severity="S3", security=False, part="head", check="L1-04 (H4 third clause refuted; R4 against the prereg; CC-01)",
  evidence="0 byte-identical within the part and 0 cross-corpus. Trajectory fingerprint (CC-01): 145 groups / 1,086 of 1,911 units; each group has one user task and one outcome; 126 span defences, 36 span attacks, 12 span gpt-4o and gpt-4o-mini, all 12 of which are 5- or 7-message runs [system, user, call, sentinel tool result, stop message]; 60 groups contain a defence intervention, 85 none (payload never read). Cross-corpus: 5 groups (interbolt-agentdojo 4, glitch-agentdojo + mandate-agentdojo-eval 1), all same model and same task (benign pre-passes, one payload-not-read user_task_9 run).",
  reproduction=f"python3 {E}/groups.py {W}/l1-units-head.jsonl {E}/pop.json\n# groups 145 units 1086 {{'span_defence': 126, 'span_attack': 36, 'any_intervention': 60, 'span_model': 12, 'cross_model_msgs_5': 10, 'cross_model_msgs_7': 2}} (no span_task, no mixed_outcome)\n# cross-corpus: docs/reports/precheck/data/_cross/l1-xdup.json /trajectory_identical/cross_corpus/pairs (interbolt-agentdojo|melon-agentdojo 4, glitch-agentdojo|melon-agentdojo 1, mandate-agentdojo-eval|melon-agentdojo 1)",
  hypothesis_ref="H4",
  recommendation="No data action. Statistics that treat executions as independent should note the identical-trajectory groups (effective n); the post-check uses the same fingerprint (CC-01).",
  artefact_proposal="", agents_md_12=False),
 dict(id="PC-melon-agentdojo-09", title="No artefacts.toml entry is scoped to melon-agentdojo although seven generic AgentDojo entries apply",
  cls="documentation-mismatch", severity="S3", security=False, part="head", check="L1-05/L1-07/L1-08 vs artefacts.toml (R2; CC-07)",
  evidence="Measured here: incomplete_run 6 logs (3 sampled, all issue incomplete_run), benign_security_constant 88 pre-passes (87 with the origin rule, 52 harness_default in the sample), injection_task_as_user 88, naive_timestamp 1,911, payload_not_reaching_agent (85 trajectory groups without intervention), and the banking checker defects of agentdojo.art.validity_defects / banking_ut15_confound (CC-07): 1,814 banking attacked logs, 605 with injection_task_0/1/3 (#181), user_task_5 119 (#161), user_task_14 108 (#139), user_task_15 108. The scopes of agentdojo.art.incomplete_run, .benign_security_constant, .injection_task_as_user, .naive_timestamp, .payload_not_reaching_agent, .validity_defects and .banking_ut15_confound list no melon-agentdojo source or profile. defence_benign_intervention needs no extension (0 pre-pass redactions).",
  reproduction="grep -n '^id = \\|^scope' src/agentprov/adapters/agentdojo/artefacts.toml | paste - - | grep -E 'incomplete_run|naive_timestamp|benign_security|injection_task_as_user|validity|payload_not_reaching|banking_ut15'   # no scope lists melon-agentdojo\n" + f"python3 -c \"import json;rows=json.load(open('{E}/pop.json'))['rows'];b=[r for r in rows if r['suite']=='banking' and r['attack']!='none'];print(len(b),sum(r['inj'] in ('injection_task_0','injection_task_1','injection_task_3') for r in b))\"   # 1814 605",
  hypothesis_ref="",
  recommendation="Family owner: add melon-agentdojo (source, part head, profile) to the seven scopes with the counts above (expected rows status verified, basis precheck 2026-10-15).",
  artefact_proposal="scope extension only: add sources 'melon-agentdojo', profiles 'melon-agentdojo', part 'head' to agentdojo.art.incomplete_run (expected 6), .benign_security_constant (88; origin rule 87), .injection_task_as_user (88), .naive_timestamp (1,911), .payload_not_reaching_agent (count from the post-round census), .validity_defects and .banking_ut15_confound (banking counts above)", agents_md_12=False),
 dict(id="PC-melon-agentdojo-10", title="l2_check outcome arms pool suites (arm key model|defence|attack)",
  cls="analysis-artefact", severity="S3", security=False, part="head", check="L2 outcome sanity (R5)",
  evidence="l2-head.json /outcomes/arm_key = 'model|defence|attack': gpt-4o melon_r direct (n 9) pools 5 banking + 4 complete travel logs, gpt-4o melon_r none (10) pools 5 + 5, gpt-4o-mini melon_r none (7) 5 + 2, gpt-4o-mini melon none (6 runs, n 5) 5 + 1 incomplete travel; the strata of the sample are (dir, attack, suite). Not a corpus property; this dossier's sample rates come from os2-sample.json (per stratum).",
  reproduction="python3 -c \"import json;d=json.load(open('docs/reports/precheck/data/melon-agentdojo/l2-head.json'));print(d['outcomes']['arm_key'], d['outcomes']['arms']['gpt-4o-2024-05-13|melon_r|direct']['utility'])\"   # model|defence|attack {'k': 9, 'n': 9, ...}",
  hypothesis_ref="",
  recommendation="Tool owner after the freeze: include suite in the arm key (or report per stratum). Not counted in readiness.",
  artefact_proposal="", agents_md_12=False),
 dict(id="PC-melon-agentdojo-11", title="[CC-08] l2_check twin counts include native class-I rules; null_final unaffected here",
  cls="analysis-artefact", severity="S3", security=False, part="head", check="L2 evidence classes / L1-08 (CC-08)",
  evidence="unverified_twin_by_bundle_class assessment I 1,858, inference I 12,921, inference none 1,203 include native I rules (e.g. auto_execution_unverified 134, checker_inputs_unverified 210 AER citations). L1-08 null_final 0, and 0 under the corrected CC-08 rule (examiner scan: 0 final assistant messages with all-empty text and no tool_calls; 2 logs have no assistant message, both incomplete).",
  reproduction=f"uv run python -I {E}/nullfinal.py {BARE} {PIN}   # {{'no_assistant': 2}} 1911",
  hypothesis_ref="",
  recommendation="See CC-08: re-run l2_check after the twin-counting fix; no L1 re-run needed for null_final (0 either way).",
  artefact_proposal="", agents_md_12=False),
]

exam = {
 "corpus_id": "melon-agentdojo", "format": "agentprov-precheck-exam/1", "date": "2026-10-15",
 "code_commit": "f7d7eced (L1), cb0af3d8 (L2 import and check, clean tree); examination at 6b76c15e (read-only)",
 "examiner_scripts": f"{E}/ (scan_pop.py, scan_detail.py, scan_detail2.py, nullfinal.py: raw via git cat-file + agentprov.ingest strict_json_loads with GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file; aer_check.py over the j2 scratch AERs; os1.py, build_data.py, build_exam.py); copy into data/melon-agentdojo/exam-scripts/ for the dossier",
 "files_written": files,
 "level1": level1, "level2": level2, "outcomes": outcomes, "hypotheses": hyp, "findings": findings,
 "followups": [],
 "sample_size": "134 of 1,911 (29 strata, 5 per stratum; 3 small strata whole: 1, 1, 2)",
 "l2_status": "done",
 "readiness": "ready-with-caveats: the data import correctly and deterministically (134/134 valid, recompute 0 unexplained, j1 = j2, raw = mapped 0/262), but two S2 mapping defects of the profile/family (PC-03 defence stop message as model output in 910 executions; PC-04 RECOVERY insert as system prompt in 92) should be fixed in the agentdojo adapter before the round (user approval), else disclosed; S2 disclosures PC-01, PC-02, PC-05; no data excluded.",
}
json.dump(exam, open(f"{D}/exam.json", "w"), indent=1, ensure_ascii=False)
print("written", len(findings), "findings")
