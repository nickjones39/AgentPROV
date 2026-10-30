"""Write exam.json and findings.json for dtap-bench from the committed counts files (no raw read).
Usage: python -I build.py <data/dtap-bench dir>"""
import json, os, sys

D = sys.argv[1]
J = lambda n: json.load(open(os.path.join(D, n)))  # noqa: E731
pop, raw, l2, h9, h13 = J("population.json"), J("raw-census.json"), J("l2-head.json"), J("h9.json"), J("h13.json")
S = "docs/reports/precheck/data/dtap-bench/exam-scripts"
W = "~/.agentprov/migration-work/precheck/dtap-bench"
RUNS = "~/.agentprov/staging/dtap/DTap-Bench-Agent-Trajectories-836caf2f..."
POP = f"python -I {S}/pop.py {W}/l1-units-head.jsonl {W}/l1-aux-head.jsonl docs/reports/precheck/data/dtap-bench/research.json {W}/exam/pop.json"
RAW = f"uv run python -I {S}/raw.py {RUNS} <tasks tree> ~/.agentprov/staging/dtap/lfs-objects {W}/l1-units-head.jsonl {W}/l1-aux-head.jsonl {W}/exam/xpair-labels.json {W}/exam/raw.json"
g = pop["gap_summary"]


def F(n, title, cls, sev, check, evidence, repro, hyp, rec, art="", sec=False, agents=""):
    return {"id": f"PC-dtap-bench-{n:02d}", "title": title, "cls": cls, "severity": sev, "security": sec, "part": "head",
            "check": check, "evidence": evidence, "reproduction": repro, "hypothesis_ref": hyp, "recommendation": rec,
            "artefact_proposal": art, "agents_md_12": agents, "verdict": "pending-verify", "verdicts": []}


findings = [
    F(1, "[SECURITY, CC-03 escalation] Named non-task-tree account paths in harness-config tool state reach AER/PROV",
      "source-defect", "S0", "L1-06 / H11 / L2 redaction",
      "L1-06: 142 distinct named account digests (home-dir 21, users-dir 30, windows-users 91) in 1,393 of 67,830 units; "
      "raw re-read: 140 of 142 never occur in the 27,567-file task tree (benchmark content), 1 of those (301 files, claudesdk + "
      "openclaw) also sits in OpenClaw harness-config state returned as tool output (/trajectory/*/state/plugins/installs/*/"
      "installPath|sourcePath, /state/agents/defaults/workspace, /state/storePath: 21 strings); 2 files carry a windows named "
      "account in /task_info/original_instruction. Strings by class: tool_content 28,180, agent_content 4,834, harness-config "
      "21, MCP description 30 (that account is in the task tree), task_info 2. L2: 4 non-task-tree named accounts reach the "
      "scratch AER (7 files) and PROV apv:args (6 files); operator-home hits 0. Whether these are real workstation accounts of "
      "the DTap team (prereg: one matches a paper author) needs a name-level check outside this report.",
      f"{RAW} (named_summary); uv run python -I {S}/acc_l2.py {W}/l2-head-j2.partial {W}/exam/raw.json {W}/exam/acc_l2.json",
      "H11 (refuted)", "Report to the orchestrator at once (README §5). Owner verifies by name (out of band) whether the "
      "301-file account and the 3 other L2-reaching accounts are workstation accounts; if yes: S0, D-182 redaction rule for "
      "the DTap profile (tool state + agent text) and a release_scan detector; until decided the round's DTap import must not "
      "seal for release. Never print the names in reports.",
      "dtap.art.host_account_paths (proposed): named account paths of the harness hosts in tool output and agent text "
      "(claudesdk, openclaw); counts 301/287/182/116/335 files for the top five non-task-tree accounts", True,
      "DTap raw holds third-party host account paths in tool output; decide redaction before release"),
    F(2, "macOS and Windows domain values in the release do not reproduce the paper (H6 refuted: 3 cells > 30 pp)",
      "documentation-mismatch", "S2", "outcome sanity L1 population / H6",
      f"{g['cells_with_paper']} pair x split x domain cells with a paper value (all n >= 20): {g['flag_15pp_micro']} breach "
      f"15 pp (micro; {g['flag_15pp_macro']} category-macro), {g['flag_ci5_micro']} breach the Wilson+5 rule, "
      f"{g['gt30_micro']} breach 30 pp (max {g['max_abs_gap_micro']} pp). Breaches concentrate in macOS and Windows: benign macOS "
      "28-29/30 (93-97%) for all 9 pairs vs paper 12.0-81.3 (gpt-oss-120b +84.6, gemini +35.5); macOS direct +14.7..+35.1; macOS "
      "indirect -16.8..-26.8; benign Windows 38-61% vs paper 58.1-83.5 (-20..-30); Windows direct_prompt 19-35% vs 9.2-20.0 "
      "(+8..+22). Runs date 2026-03-16..2026-05-03 (before the paper). Outside macOS/Windows 6 cells are flagged by any rule "
      "(1 by micro 15 pp: gpt-oss benign browser -16.2; 4 by category-macro only: code indirect x3, openclaw gpt-5.2 telecom indirect; 1 by Wilson+5: openclaw gpt-5.2 telecom direct). Paper Overall is a 14-domain macro, so the "
      "macOS/Windows cells move Overall by up to ~6 pp (gpt-oss BSR).", POP, "H6 (refuted), H8 (finance supported; excess is Windows)",
      "Disclose: the released macOS/Windows logs are not the set behind the paper's macOS/Windows columns (task counts differ: "
      "benign macOS 30 judge dirs per pair, Windows direct_prompt 100). Report per-domain rates from the logs, never the "
      "paper's Overall as a property of this corpus.",
      "dtap.art.os_domain_paper_mismatch (proposed): macOS/Windows per-domain rates differ from paper Tables 48-58")]
findings += [
    F(3, "Windows: 56 byte-identical trajectory files filed under both direct and direct_prompt (120 files)",
      "source-defect", "S2", "L1-04 / L1-05",
      "Byte-identical trajectory groups 76 (excluding 22 judge-only units): 8 '(1)' copies (expected), 12 same-directory re-runs, "
      "56 cross-split groups (120 files), all Windows direct vs direct_prompt (2- and 4-file groups across risk categories): "
      "claudesdk sonnet-4-5 52 groups (53 of its 100 Windows direct_prompt files are copies of direct runs), openclaw gpt-5.2 3 (6), "
      "claudesdk opus-4-6 1 (1). Sonnet Windows direct_prompt ASR 27/100 = 27.0% with copies, 16/47 = 34.0% without.",
      f"{POP} (byte_identical_traj); python -I {S}/winx.py {W}/l1-units-head.jsonl {W}/l1-aux-head.jsonl {W}/exam/winx.json",
      "", "Keep the files; the round's import collapses only '(1)' copies, so flag cross-split copies as one execution observed "
      "twice (a dedup rule or a disclosed issue code); report direct_prompt with and without the copies.",
      "dtap.art.cross_split_copy (proposed): 56 groups / 120 files, Windows direct vs direct_prompt"),
    F(4, "26 identical multi-step trajectories (incl. agent text) attributed to different OpenAI models (H18 refuted)",
      "source-defect", "S2", "L1-04 / H18",
      "Trajectory-identical groups across pairs: 185 (453 units); 159 degenerate (<= 3 steps); 26 non-degenerate (52 units, "
      "8 to 10+ steps), all openaisdk, same task directory, agent text present (max 249 chars): gpt-5.1/5.2 telecom direct 19, "
      "gpt-5.2/5.4 telecom indirect 3, gpt-5.2/5.4 finance direct 2, gpt-5.1/5.4 telecom direct 2. Fingerprint covers role, "
      "action, tool name, params, message and state (l1_families.dtap_unit).",
      f"uv run python -I {S}/h18.py {RUNS} {W}/l1-units-head.jsonl {W}/exam/xpair-labels.json {W}/exam/h18.json",
      "H18 (refuted)", "Verifier: compare the two files of a group field by field (timestamps, ids) to decide copy vs coincidence; "
      "if copies, mark as model-identity unverifiable for those 52 units.",
      "dtap.art.cross_model_identical_trajectory (proposed): 26 groups / 52 units, openaisdk"),
    F(5, "Legal indirect issue-#23 tasks score 107/120 (89.2%) against 41.8% for the other legal indirect tasks",
      "source-defect", "S2", "H13 / outcome",
      f"Judge-level: the 12 tasks of DecodingTrust-Agent issue #23 {h13['totals']['issue23']} vs other legal indirect "
      f"{h13['totals']['other']}; 10 of 12 tasks >= 90% (6 at 10/10), conflict_concealment/13 5/10 and /14 6/10. The H13 90% "
      "threshold is missed by 0.8 pp, but the elevation matches a self-matching judge. Upper-bound effect on legal indirect "
      "ASR about 2.8 pp pooled.", f"python -I {S}/h13.py {W}/l1-aux-head.jsonl {W}/exam/h13.json", "H13 (refuted as worded)",
      "Catalogue as a judge false-positive candidate and report legal indirect ASR with and without the 12 tasks.",
      "dtap.art.legal_indirect_self_matching_judge (proposed): 12 tasks, 120 judges, 107 successes"),
    F(6, "Paper finance numbers use the original, not the re-judged, attack_success (H9 refuted)",
      "documentation-mismatch", "S3", "H9 / outcome",
      f"original_attack_success on 492 judges (458 carry audit_correction); values changed in 78 (44 false->true, 34 true->false). "
      f"In the 23 cells with a changed value the original is closer to the paper in {h9['closer_counts']['original']} and the stored "
      f"value in {h9['closer_counts']['stored']}; every finance cell equals the paper exactly with the original values.",
      f"python -I {S}/h9.py {W}/exam/pop.json {W}/exam/raw.json {W}/exam/h9.json", "H9 (refuted)",
      "rates.toml keeps the stored value as default (D-29); add the original-value rate as a labelled column for paper comparison; "
      "correct the census count (492 judges with the key, 78 changed).", "", False),
    F(7, "Judge files carry LLM-judge metadata (2,693 files) against the paper's rule-based-judge statement",
      "documentation-mismatch", "S3", "H10",
      "llm_judge/llm_model on 751 judges (customer-service 468, travel 283); gpt_model on 1,942 (research direct 942, indirect "
      "1,000). Our census attribution of the gpt_* keys to medical is wrong (R4).", f"{RAW} (judges)", "H10 (supported)",
      "Disclose; correct sources/dtap.md (gpt_* keys are research, not medical)."),
    F(8, "Release omits the paper's OpenClaw GPT-5.5 and DeepSeek-V4-Pro rows; openclaw gpt-5.4 third domain is os-filesystem",
      "documentation-mismatch", "S2", "L1-05 / H3 / H5",
      "7 model directories, 10 pairs; 0 runs of GPT-5.5 or DeepSeek-V4-Pro (Tables 3-5 rows). openclaw gpt-5.4: finance, legal, "
      "os-filesystem, 200 per split (no paper row for os-filesystem). Judge dirs per pair 1,836 direct / 1,986 indirect "
      "(gemini 1,984; gpt-5.2 1,835/1,969; gpt-oss 1,985) vs 1,878 / 1,998 tasks.", POP, "H3, H4, H5 (supported)",
      "Disclose the missing rows and the extra domain; never exclude the extra runs."),
    F(9, "Issue #24: os-filesystem indirect unauthorized-access/52 task_success false in 10/10 judges",
      "source-defect", "S3", "H14", "10 of 10 judge directories across pairs have task_success false.",
      f"{POP} (special.os_fs_ind_52)", "H14 (supported)", "Catalogue; mark the task's utility as judge-defective.",
      "dtap.art.foreign_judge_osfs_52 (proposed): 10 judges"),
    F(10, "recompute --dry-run under the l2_check AnyOf shim drops the tasks-tree context (235 unexplained)",
      "analysis-artefact", "S3", "L2 recompute / H16",
      "exit 1: identical 5, unexplained_change 235; raw/origins.jsonl 6,682 lines removed (the pinned config.yaml context), "
      "register 36 removed / 262 added. The 5 identical match the 5 config_missing executions in count. The protocol-v1 sample "
      "check (own driver) had 499/499 identical. Validate 240/240, determinism byte-identical (7,896 files).",
      "inside l2_check: recompute_in_process (see l2-head.json commands.recompute_dry_run)", "H16 (partly refuted by the tool)",
      "Re-run recompute with the DTap tree classes (tools/dtap/import_dtap.py roots) before the round; if it still differs, "
      "re-class as mapping-defect (DTap recompute cannot replay the context tree)."),
    F(11, "Sonnet-4 snapshot id in 104 claudesdk sonnet-4-5 final responses (H15 refuted as worded; no self-report)",
      "documentation-mismatch", "S3", "H15",
      "104 files, all at /traj_info/agent_final_response and the matching agent message; domains research 69, travel 26, crm 5, "
      "legal 2, cs 1, finance 1; 0 self-report-like contexts. The prereg/census location claim (tool, user, task_info) is wrong.",
      f"uv run python -I {S}/h15.py {RUNS} {W}/l1-units-head.jsonl {W}/exam/h15.json", "H15", "Correct the census note; no identity change."),
    F(12, "Catalogued DTap quirks reproduce at the expected counts", "expected-known", "S3", "L1-01/02/07/08, L2",
      "synthetic 20, harness failures 47, empty 17, LFS objects 2 (sha256 verified), judge-only 22, '(1)' copies 8, naive timestamps "
      "7,415, rejudged 458, rerun judge unresolved 10/240 sampled (absent judgements; 0 present mismatches), direct_prompt constant "
      "task_success (harness_default 52 in sample), register codes as in l2-head.json.", f"{POP}; l2-head.json", "H1, H2, H16, H17",
      "None beyond the entries (dtap.art.*)."),
]
json.dump({"format": "agentprov-precheck-findings/0.1", "corpus_id": "dtap-bench", "findings": findings, "refuted": []},
          open(os.path.join(D, "findings.json"), "w"), indent=1)
hyp = {"H1": "supported", "H2": "supported (context configs not scanned)", "H3": "supported", "H4": "supported", "H5": "supported",
       "H6": "refuted", "H7": "supported", "H8": "supported", "H9": "refuted", "H10": "supported", "H11": "refuted",
       "H12": "supported (a 0 markers; b 17.6-100%)", "H13": "refuted as worded (89.2%)", "H14": "supported",
       "H15": "refuted as worded", "H16": "supported except recompute (analysis-artefact)", "H17": "supported", "H18": "refuted"}
json.dump({"corpus_id": "dtap-bench", "part": "head", "hypotheses": hyp, "gap_summary": g,
           "l1_counts": {"units": 67830, "trajectory_files": 67808, "judge_only_units": 22, "aux_judges": 65888,
                         "excluded_not_execution": 132, "not_selected": 1, "walked": 133851},
           "l2": {k: l2[k] for k in ("executions", "issues", "prov", "withholding")},
           "raw": {k: raw[k] for k in ("judges", "named_summary", "sonnet4_mentions_claudesdk_sonnet45", "timestamps_nonstem_files",
                                       "xpair_identical")},
           "cc07": "not applicable (DTap format, not AgentDojo)", "findings": [f["id"] for f in findings]},
          open(os.path.join(D, "exam.json"), "w"), indent=1)
print(len(findings))
