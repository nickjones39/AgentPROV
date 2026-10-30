"""Writes findings.json (CC-06 format) and exam.json for code-agent-misalignment from the committed counts files.
    python3 -I S/build_findings.py D"""
import json, sys
from pathlib import Path
D = Path(sys.argv[1]); C = "code-agent-misalignment"; P = "results-raw"
S = "docs/reports/precheck/data/code-agent-misalignment/exam-scripts"
cen = json.loads((D / "exam-census.json").read_text()); ctx = json.loads((D / "exam-context.json").read_text())["by"]
oc = json.loads((D / "exam-outcomes.json").read_text())
def f(n, title, cls, sev, sec, check, ev, rep, hyp, rec, art=None, a12=None):
    return {"id": f"PC-{C}-{n:02d}", "title": title, "cls": cls, "severity": sev, "security": sec, "part": P, "check": check,
            "evidence": ev, "reproduction": rep, "hypothesis_ref": hyp, "recommendation": rec, "artefact_proposal": art,
            "agents_md_12": a12, "verdict": "pending-verify", "verdicts": []}
host = "home-dir:<account-B>"
F = [
 f(1, "Host work-root path with a named third-party account in 272 raw-store final_diff.patch files (CC-11)", "source-defect", "S2", True,
   "L1-10, H-17",
   {"files": ctx[f"{host}:files"]["n"], "matches": sum(ctx[f"{host}:role"].values()), "role": ctx[f"{host}:role"],
    "line_class": ctx[f"{host}:line"], "next_segment": "jss_agent_work (836/836)", "by_model_matches": ctx[f"{host}:model"],
    "distinct_named_accounts": 1, "account_digest12": "<account-B>", "operator_home_hits": 0,
    "in_raw_store": "all 2,500 final_diff.patch are raw-store members of the scratch import (raw/members.jsonl, selected, object present)",
    "in_aer_sem_prov": 0, "aer_home_paths_sample": "10 executions, all generic (/home/ubuntu-class)",
    "also": {"second_named_digest_<account-A>": {"files": 11, "matches": 21, "lines": "+ (agent-written)", "model": "gemini-2.5-pro", "with_jss_agent_work": 0, "status": "undetermined"},
             "windows_users_digest_<account-C>": {"files": 12, "matches": 24, "note": "digest = sha256('foo')[:12], a placeholder"},
             "pem_header_lines": 4, "jwt_lines": 4, "pem_jwt_where": "2 gemini-2.5-pro SK-DEPDOWN patches, + lines"}},
   f"uv run python -I {S}/patches.py ~/.agentprov/migration-work/precheck/{C}/exam/patches.json",
   "H-17 refuted (prereg: 0 jss_agent_work or other host work root)",
   "Report to the orchestrator at once (security, CC-11). Decision for the user: withhold the 272 patches at seal with digests kept (D-345/CC-11 precedent) or a profile redaction; extend [withhold] scope (today executions-only, pattern AIza) to context artefacts; the release_scan third-party home-path detector (CC-11) must cover final_diff.patch. Verifier: inspect the <account-A> lines with quote_untrusted (fiction vs a real account).",
   "geminicli.art.host_path_in_diff: 272 final_diff.patch (gemini_cli) carry /home/<account>/jss_agent_work/ in diff header lines; 1 named account; context artefacts only; handling withhold-at-seal (proposed)",
   "code-agent-misalignment: 272 raw-store final_diff.patch hold a third-party host work-root path (1 named account); withhold/redact before seal (CC-11)"),
 f(2, "Live-prefixed Stripe key shape (1 distinct value, SK-SECRETLOG fixture) reaches AER and PROV apv:args; uncatalogued", "source-defect", "S2", True,
   "L1-06, L2 redaction",
   {"streams": 14, "matches_streams": 35, "matches_events_jsonl": 35, "distinct_values": cen["secrets"]["stripe_distinct_n"],
    "prefix_class": cen["secrets"]["stripe_prefix"], "skeletons": cen["secrets"]["stripe_by_skeleton"],
    "pointers": {"/parameters/new_string": 16, "/parameters/old_string": 16, "/parameters/content": 3},
    "sample_hits": {"aer": 10, "prov_apv_args": 5}, "withhold_scan_rules": ["gcp-api-key"], "artefacts_toml_entry": "none"},
   f"uv run python -I {S}/census.py ~/.agentprov/migration-work/precheck/{C}/exam/census.json; grep -c stripe src/agentprov/adapters/geminicli/artefacts.toml",
   "prereg section 5 secret list (stripe not listed)",
   "Benchmark fixture value (present in old_string, one value, one skeleton): treat as CC-02-class content. Family owner: add an artefacts.toml entry with the count and decide a [withhold] or a release_scan allowlist by digest before the release scan; widen CC-02 to this corpus.",
   "geminicli.art.fixture_secret_shapes: 1 sk_live_-prefixed value in 14 SK-SECRETLOG streams (35 matches) and their events.jsonl; benchmark fixture; reaches AER/PROV args",
   None),
 f(3, "MiniMax-M2 cell: 351/384 streams end in a CLI error result (meta exit 244); no args-stripping signature (H-11 refuted)", "expected-known", "S2", False,
   "L1-08, H-11, H-12",
   {"minimax": {"result_error": 351, "success": 33, "meta_exit_244": 351, "tool_use": 975, "tool_use_params_empty": 0},
    "other_cells_error_or_zero_tool_share": {"claude-sonnet-4-6": "4/460", "gemini-2.5-pro": "89/420", "glm-4.7-probe": "33/457", "gpt-5.3-codex": "21/461"},
    "params_empty_all_cells": 0, "cli_error_result_total": 495, "other_nonzero_meta_exit": {"gpt-5.3-codex": {"244": 14, "246": 2, "147": 4}, "glm-4.7-probe": {"147": 31}}},
   f"uv run python -I {S}/census.py ...; per_model.result_status / tool_use.params_empty",
   "H-11 refuted, H-12 supported",
   "Disclose with geminicli.art.cli_error_result (351 of its 495 are this cell): the MiniMax-M2 rate (22/384) measures a mostly failed CLI run. Keep every run (no outcome-based exclusion). Research: the bridge args-stripping explanation is not visible in the stream (0 empty parameters).",
   "geminicli.art.cli_error_result: add per-cell split MiniMax-M2 351, gemini-2.5-pro 88, glm-4.7-probe 33, gpt-5.3-codex 20, claude-sonnet-4-6 3 (meta exit 244 for all 351 MiniMax)",
   "code-agent-misalignment MiniMax-M2: 351/384 streams end in CLI error; cell rate is a degraded-run rate (disclose)"),
 f(4, "subagent_internals: 76 codebase_investigator calls sit in 72 streams, not 29 (artefacts.toml description, prereg H-18)", "documentation-mismatch", "S3", False,
   "H-18, H-20",
   {"calls": 76, "streams": 72, "by_model_streams": {m: cen["per_model"][m].get("investigator", {}).get("streams", 0) for m in cen["per_model"]},
    "stats_tool_calls_differs": 20, "differs_all_glm_with_tool": True, "sample_issue_subagent_internals_unobserved": "7/251 executions (index)"},
   f"uv run python -I {S}/census.py ...; per_model.investigator", "H-18 partly refuted (calls 76 and counter 20 confirmed)",
   "Correct the description of geminicli.art.subagent_internals and C section 9 to 72 streams (R4, geminicli family owner); the expected count (73 tool executions) is not affected.", None, None),
 f(5, "Corpus denominators differ from the paper's by design: 318 stream-less rollouts (19 elicited: MiniMax-M2 6, gemini-2.5-pro 13) are outside the corpus", "expected-known", "S3", False,
   "L1-01, outcome sanity",
   {"selected_units": 2500, "executions": 2182, "empty_stream": 175, "no_stream": 143, "elicited_streams": 363, "elicited_no_stream": 19,
    "elicited_empty": 0, "paper": "382/2500", "corpus": "363/2182"},
   "l1-results-raw.json family.outcomes; exam-census.json rollout_join", "H-07 supported",
   "Disclose with geminicli.art.rollouts_without_stream; corpus rates are per mapped stream, paper rates per rollout. Exclusion is by format, never by outcome.", None, None),
 f(6, "L1-04 trajectory-identical groups among non-empty streams: 27 groups / 86 units (prereg expected 0)", "analysis-artefact", "S3", False,
   "L1-04 (CC-01)",
   {"groups": 27, "units": 86, "within_model": 23, "cross_model": 4, "median_size_bytes": 1135, "elicited_in_groups": 0},
   "python over l1-units-results-raw.jsonl fp groups (dossier section 9)", "L1-04 expectation",
   "The fingerprint drops call ids and timestamps (CC-01); the groups are short runs with the same prompt per skeleton. Not a corpus duplicate; no action.", None, None),
 f(7, "Pre-check tool properties: sample remainder allocation in sorted stratum order (MiniMax-M2 96/300 labels) and verdict-only/empty units in the frame (49 labels without execution); 'foo' missing from GENERIC_ACCOUNTS", "analysis-artefact", "S3", False,
   "L2 sample, L1-10",
   {"labels_by_model": {"MiniMax-M2": 96, "claude-sonnet-4-6": 51, "gemini-2.5-pro": 51, "glm-4.7-probe": 51, "gpt-5.3-codex": 51},
    "sampled_without_execution": {"no_stream_verdict_only": 25, "empty_stream": 24}, "executions": 251,
    "post_stratified_sample_rate": oc["all"]["sample_post_stratified_by_model"], "windows_named_placeholder_files": 12},
   "l2-sample-results-raw.json quotas; l2-results-raw.json sample_join", "README section 4 / amendment 2",
   "R5/R6: report post-stratified rates (done). Tool owner (after the round, no change now): spread the remainder across the first facet; add 'foo' to GENERIC_ACCOUNTS.", None, None),
 f(8, "Desk documentation mismatches of the deposit (H-22), not re-tested", "documentation-mismatch", "S3", False,
   "H-22", {"items": ["50 seeds vs 51 skeletons", "'in-house probe' vs claude_code", "transcripts on request vs open deposit", "RESULTS_build/ vs RESULTS_raw/", "~1.6 GB vs 1.46 GB"]},
   "prereg section 1, research.json", "H-22", "Record in the datasheet (R3, S3).", None, None),
]
out = {"format": "agentprov-precheck-findings/0.1", "corpus_id": C, "findings": F, "refuted": []}
(D / "findings.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(F))
