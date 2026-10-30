# Phase 10f: SEAgent and WhistleBench source profiles

Branch `phase-10f-profiles`, 2026-10-12. Decisions D-150–D-156 (`docs/architecture/DECISIONS.md`, user-approved 2026-10-12); spec §D.6.18
and §D.9.7. Inputs: the phase-10e verification (`docs/reports/systematic-search/candidates/phase10e-candidates.md` §3.1,
§3.2; D-144, D-145, D-147). The user approved the downloads (2026-10-12): Zenodo 23218779 `seagent-acsac2026-ae-v2.zip`
(237.7 MB) and a bare partial clone of `legobridge/whistlebench` with its `final_runs/` checked out at the pin. Staging:
`~/.agentprov/staging/10f/`; scripts and census output: `~/.agentprov/migration-work/phase10f/`. Third-party data, read in
memory or through `agentprov.ingest`; nothing in it was run or followed.

## What was done

| | `seagent-agentdojo` | `whistlebench` |
|---|---|---|
| Family, dialect | agentdojo, `agentdojo.tracelogger` `v1.k14` | inspect, `inspect.eval` `v2` |
| Pin | Zenodo 23218779, `seagent-acsac2026-ae-v2.zip` (sha256 `e15a8f0f…`, md5 matches the record) | `legobridge/whistlebench@9c27637c`, tree `final_runs/` (223 files, 523,183,391 B) |
| Licence → corpus | CC-BY-4.0 data (Apache-2.0 code; AgentDojo text MIT) → own corpus | MIT → own corpus |
| Runs | 5,342 logs, deepseek-v3 under 5 arms × 4 suites | 184 logs, 9,200 samples (all distinct by messages), 11 models |
| Identity | table by run directory (40 rows, D-152) | header model per log |
| Registry | `head` `planned` | `final-runs` `planned`, no semantics profile (SEM skipped) |
| Census | every member mapped (`phase10f_seagent.py`): 5,342 mapped, 0 crashes, 0 validation findings beyond the scratch origin; `observed` filled, 0 differences | every log and sample read (`whistlebench.census.json`): versions, models, scorers, tools, limits; 0 secret-like strings |
| Fixtures | 10 members by criterion (CC-BY-4.0 text) | the smallest complete log, 1,420,537 B (MIT text) |
| Tests | `tests/adapters/agentdojo/test_phase10f_seagent.py` (14) | `tests/adapters/inspect/test_whistlebench.py` (8) |
| Trial import | none (archive inputs, D-156) | full pinned tree, 8 workers: 9,200 mapped, derived, validated; 3-worker sample byte-identical |

Files: profiles `src/agentprov/adapters/agentdojo/profiles/seagent-agentdojo.profile.toml` and
`src/agentprov/adapters/inspect/profiles/whistlebench.profile.toml`; table
`src/agentprov/adapters/agentdojo/tables/seagent_run_dirs.toml`; registry entries appended; tools
`tools/agentdojo/phase10f_seagent.py` (census) and `tools/agentdojo/phase10f_fixtures.py`; reports here. No mapper, quirk,
catalogue, core or existing profile file changed (invariant 5).

## SEAgent

- **Arms** (deposit README and EVALUATION.md): `baseline` (AgentDojo without a guard), `agentspec` and `pvagent`
  (comparison defences), `seagent` (initial policy), `seagent-RF` / `seagent-rf` (refined policy). Security runs: the
  `important_instructions` attack plus utility pre-passes; perf runs: benign timing runs.
- **Census** (`seagent-agentdojo.census.json`): variants `v1.k14` 5,342; quirk counts: benign security constant 657,
  injection-task pre-passes 172, args mutated in place 5,135, placeholder args 15,902, unexecuted trailing calls 392 in 317
  logs. Issue codes by file: `earlier_attempts_unobservable` 5,342 (generic), `unattributed_additional_user_message` 863,
  `agentdojo.unknown_message_shape` 541 with `orphan_tool_result` 541, `unexecuted_tool_call` 317, `missing_tool_result` 94.
- **Defence-authored messages** (D-153): the 863 logs with extra user messages are the seagent arms; all 960 extra
  messages follow a tool result and open with one of 23 phrases, the most common being a guard warning ("[WARNING] Tool
  call to '<tool>' may violate the user int…", quoted as data). They stay unattributed. The 541 PVAgent logs have 740
  assistant messages without a `tool_calls` key, so the tool results after them are orphans; no call is inferred.
- **Why no trial import** (D-154, D-156): the runner imports git trees and Inspect containers, not a deposit archive whose
  members are whole run logs, and the TraceLogger mapper's layout locator points at the origin's `/path`, which a `member`
  origin lacks (`aer.locator.dangling`, pinned by `test_a_member_origin_does_not_seal_yet_d156`). The census therefore
  maps each member under a development-only `local` origin and validates in development mode (release mode refuses that
  origin by design); nothing is sealed or stored.

## WhistleBench

- **Census** (`whistlebench.census.json`): tasks `high_agency` 176 logs, `high_agency_deliberation_awareness` 8; producers
  `inspect_ai` 0.3.130 (161) and 0.3.134.dev31+geb46eef8 (23); all logs `success`, log version 2; models: gemini-2.5-pro
  and grok-4 (OpenRouter), claude-opus-4-1/4, claude-sonnet-4/4-5, gpt-4.1, gpt-5, qwen3-32b, qwen3-max, llama-4-maverick.
  Tools: write_file 10,928, send_email 6,473, write_logs 705 and a few more; 15 calls name several tools run together.
  Scorers: email_whistleblowing, refusal, test_awareness, deliberation_analysis and three snitching scorers. 12 sample
  limits. Every sample's messages are distinct (no regraded copies).
- **Trial import** (8 workers, `whistlebench.trial.json`): 184 containers, 9,200 samples mapped, derived and validated;
  0 failures, 0 degenerate, 3,179 s. Issue codes (samples): `missing_tool_result` and `dangling_source_ref` 8,416 occurrences
  in 8,401 samples (the react agent's final `submit` call is a tool event whose message was pruned);
  `call_result_link_conflict` 12,304 occurrences and `unexecuted_tool_call` in 3,452 samples (one tool-call id belongs to two
  call parts, so links are `ambiguous`); `accounting_inconsistent` 4,666; `inspect.unmapped_event` 113; sample limits 12.
  The conflicts occur under both producer versions, mostly in the `high_agency` task. Nothing false is written, but about
  37.5% of samples lose explicit call-result links: routed to the Inspect mapper owner before any full import (D-155).
- **Second import** (3 workers, every 5th log, `whistlebench.trial-sample.json`): 37 containers, 1,850 samples, 0 failures,
  609 s; every one of its 5,624 objects (AER, PROV, raw) is byte-identical in the 8-worker import (`whistlebench.compare.json`).

## Open items and routing

1. **D-156** (orchestrator): archive inputs in the runner and member-origin layout in the TraceLogger mapper (SEAgent);
   call identity for `inspect_ai` 0.3.130/0.3.134 in the Inspect mapper (WhistleBench).
2. **D-153**: a rule for defence-authored messages (SEAgent guard warnings; with phase-10d routing R1).
3. **WhistleBench semantics profile**: scorer claims and a tool table (write_file, send_email, write_logs, ...).
4. **D-150–D-156** are user-approved (2026-10-12). Full imports wait for the regeneration round and the user's approval; both registry
   parts stay `planned`.

The trial and scratch corpora (`~/.agentprov/migration-work/phase10f/corpora/`) and the staging bytes stay outside Git.
