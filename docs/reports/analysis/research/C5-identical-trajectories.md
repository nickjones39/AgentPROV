# C5: cross-model identical trajectories (AgentDojo-HEAD 13 groups, AgentDyn 10 groups)

Read-only investigation, phase-10 analysis. Corpora: `agentdojo-upstream-head-p10.partial`, `agentdyn-a-p10.partial`.
Method: groups recomputed from the raw source JSON (message list with tool-call ids ignored, roles, contents, tool
names and arguments); this reproduces exactly 13 head and 10 AgentDyn cross-model groups, and every reported pair of
ex ids is inside a recomputed group. Model label = the `runs/<dir>` name with the defence suffix removed. Source text
was only inspected as lengths and a few words; none of it is reproduced here. No network, no fetch, no `.env`.

## Verdict

**(a) Coincidence of short, near-deterministic runs. No evidence of copied files.** Confidence: high for AgentDojo-HEAD
(full file diff plus commit history), high-to-moderate for AgentDyn (file diff plus timestamps; no commit history
available, but the evidence does not depend on it).

## Evidence common to both corpora

1. No two source files are byte-identical anywhere (`dup_source_sha = 0` in all five corpora), and no two git blob ids
   in any group are equal.
2. Inside every group, the files differ in fields that a copy would carry over unchanged:
   - head: `duration` differs in all 13 groups (e.g. 66.59 s vs 1.50 s, 106.26 s vs 2.59 s, 14.15 s vs 3.53 s) and
     `pipeline_name` (the model label). Nothing else differs, apart from one pair (below).
   - AgentDyn: `evaluation_timestamp` (distinct per file; range 2026-01-22 to 2026-01-26, 40 distinct timestamps in the
     40-member group), `duration`, `pipeline_name`, and often the injection fields.
   A copy under a new model directory would keep `duration` and `evaluation_timestamp`; a forger would have to change
   them to different plausible values.
3. The identity is rare and confined to short runs. Base rate over matched cells (same suite, user task, attack and
   injection task; 753 cells per model in head, 648 in AgentDyn):

   | model pair (head) | shared cells | identical message lists |
   |---|---:|---:|
   | gemini-2.0-flash-001 / -exp (same commit) | 753 | 3 (5, 5, 7 messages) |
   | gemini-1.5-pro-002 / gemini-2.0-flash-exp | 753 | 5 (3, 5, 5, 5, 5) |
   | gemini-1.5-flash-001 / gemini-1.5-pro-001 | 753 | 3 (5, 5, 7) |
   | gemini-1.5-pro-001 / -002 | 753 | 1 (5) |
   | gpt-4-0125-preview / gpt-4-turbo-2024-04-09 | 753 | 1 (3) |

   In AgentDyn, different-model pairs are identical in 1 to 11 of 648 cells, always 3 messages (see below). A bulk copy
   of one model directory onto another would give hundreds of identical cells, as happens for the same model under
   different defences (llama vs llama+defence: about 70 of 648, all empty replies; gemini-2.5-flash piguard vs
   prompt_guard_2: 425 of 648, which is a different phenomenon, see "Side observation").

## AgentDojo-HEAD (13 groups, each exactly 2 files)

What the runs are: all are benign (no attack, 6 groups) or attacked runs of workspace/slack/banking/travel in which the
agent answered a simple factual or single-action request, with the same tool call and arguments and the same final
sentence. None is a refusal. Shapes (S system, U user, A assistant, T tool result): 2 groups S U A (3 msgs, no tool,
one-sentence answer), 9 groups S U A(1 tool call) T A (5 msgs), 2 groups with two tool calls (7 msgs).

Introducing commits (from `origins.jsonl`, checked with `git log`/`diff-tree` in the history store, no fetch):

| commit | author, date, message | what it added |
|---|---|---|
| 6bbd9ca4 | Max Buckley, 2025-02-17, "Add the Flash 2 Exp and 001" | whole dirs gemini-2.0-flash-exp (753) and -001 (1081) |
| 650bc7ea | Max Buckley, 2024-11-19, "JSON ONLY" | whole dirs gemini-1.5-pro-002, gemini-1.5-flash-002, claude-3-5-sonnet-20241022 (753 each) |
| 19b4656d | E. Debenedetti, 2024-06-04, "Add missing message tasks" | gpt-4-0125-preview (628), gemini-1.5-pro-001 (602), claude-3-sonnet (533) |
| abe06764 | E. Debenedetti, 2024-06-03, "Add attack results for gemini flash, command r, llama" | gemini-1.5-flash-001 (656), command-r, llama-3-70b (656 each) |
| 2913b2d8 | E. Debenedetti, 2024-06-02, "Add Gemini Pro" | gemini-1.5-pro-001 (63) |
| 02bc7e41 | E. Debenedetti, 2024-06-03, "Add gpt-4 results under attack" | gpt-4-0125-preview (656) |
| 97b76722 | E. Debenedetti, 2024-07-17, "Update Llama results" | meta-llama_Llama-3-70b-chat-hf (753) and gpt-4-turbo-2024-04-09 (167) |

| # | ex ids | model labels | suite / user task / injection task | msgs | blob ids equal | differing fields | introducing commits | verdict |
|---|---|---|---|---:|---|---|---|---|
| 1 | ex_4pcp5kbb... / ex_gd7h6ygj... | gpt-4-turbo-2024-04-09 / gpt-4-0125-preview | travel / injection_task_6 as user task / none | 3 | no | duration, pipeline_name | 97b76722 / 02bc7e41 | coincidence |
| 2 | ex_5dzyffe7... / ex_pqy63l4p... | gemini-1.5-pro-001 / -002 | slack / user_task_0 / none | 5 | no | duration (3.5 vs 14.1 s), pipeline_name, plus `placeholder_args` field present in one file only (message 2 and 3) | 2913b2d8 / 650bc7ea | coincidence; the schema difference shows the two files come from different harness versions |
| 3 | ex_k4j6i723... / ex_ek77khiu... | gemini-2.0-flash-001 / -exp | banking / injection_task_7 as user task / none | 5 | no | duration (1.5 vs 66.6 s), pipeline_name | 6bbd9ca4 both | coincidence (same bulk commit, but durations differ) |
| 4 | ex_rpfbqchm... / ex_es3zmwqv... | gemini-1.5-flash-001 / -pro-001 | workspace / user_task_14 / injection_task_1 | 5 | no | duration, pipeline_name | abe06764 / 19b4656d | coincidence |
| 5 | ex_ov7h5kob... / ex_ewlaafjw... | gemini-1.5-pro-002 / 2.0-flash-exp | banking / injection_task_4 as user task / none | 3 | no | duration, pipeline_name | 650bc7ea / 6bbd9ca4 | coincidence |
| 6 | ex_kuosqgcu... / ex_jd5jaj2c... | gemini-1.5-flash-001 / -pro-001 | workspace / user_task_7 / injection_task_2 | 7 | no | duration, pipeline_name | abe06764 / 19b4656d | coincidence |
| 7 | ex_p6psaha4... / ex_jd7ftjnk... | gemini-1.5-pro-002 / 2.0-flash-exp | workspace / user_task_2 / injection_task_3 | 5 | no | duration, pipeline_name | 650bc7ea / 6bbd9ca4 | coincidence |
| 8 | ex_kv5k5ssn... / ex_xlak2gpg... | gemini-2.0-flash-001 / -exp | slack / user_task_2 / none | 7 | no | duration, pipeline_name | 6bbd9ca4 both | coincidence |
| 9 | ex_xqyiovzm... / ex_oexs7meq... | gemini-1.5-pro-002 / 2.0-flash-exp | workspace / user_task_2 / injection_task_4 | 5 | no | duration, pipeline_name | 650bc7ea / 6bbd9ca4 | coincidence |
| 10 | ex_oezo4js3... / ex_rufjn2t7... | gemini-1.5-pro-002 / 2.0-flash-exp | workspace / user_task_2 / injection_task_2 | 5 | no | duration, pipeline_name | 650bc7ea / 6bbd9ca4 | coincidence |
| 11 | ex_zr6ll6ir... / ex_ozzmdhz3... | gemini-1.5-flash-001 / -pro-001 | workspace / user_task_14 / injection_task_4 | 5 | no | duration, pipeline_name | abe06764 / 19b4656d | coincidence |
| 12 | ex_s3s3o24z... / ex_rv47xcyg... | gemini-2.0-flash-001 / -exp | workspace / user_task_2 / none | 5 | no | duration (2.6 vs 106.3 s), pipeline_name | 6bbd9ca4 both | coincidence |
| 13 | ex_zdltshfj... / ex_yfro2tc2... | gemini-1.5-pro-002 / 2.0-flash-exp | workspace / user_task_2 / injection_task_0 | 5 | no | duration (6.4 vs 50.0 s), pipeline_name | 650bc7ea / 6bbd9ca4 | coincidence |

Notes: (i) Only 3 of the 13 pairs (3, 8, 12) have both files introduced in one commit; in none is the whole
directory duplicated (3 of 753 matched cells are identical for that pair). (ii) The commit-pair is the bulk add of the
whole model directory by the benchmark's maintainers; none of these commits touches a model directory by copying
another. (iii) Utility/security are identical inside each group, as expected for identical message lists (G7, G9, G10,
G13 are all the same user task 2 answered with the same sentence and scored utility=false, security=false in both files).

## AgentDyn (10 groups, 2 to 47 members each; single pinned commit 5353cf76, shallow clone, no history)

What the runs are: 9 of 10 groups are S U A with an **empty assistant message** (a single text part of length 0,
`tool_calls` either `[]` or `null`, no tool called, utility false): a degenerate no-op completion, not a refusal text.
The remaining group (#2, github, 3 messages, 7 members: gemini-2.5-flash and -pro) is a short clarification question to
the user without a tool call. Group #8 is the 5-message variant (S U U A A, both assistant messages empty, shopping,
tool_filter defence). The groups pool several models, defences and, where the injection was not read (the agent did
nothing), several injection tasks, hence the large membership.

| # | members | model labels in group | suite / user task | msgs | final assistant | blob ids equal | differing fields (across members) | verdict |
|---|---:|---|---|---:|---|---|---|---|
| 1 (contains ex_2axjhzsh... / ex_2bjpx6nv...) | 40 | llama-3.3-70b (plain and 4 defences), qwen3-235b | github / user_task_3 | 3 | empty | no | evaluation_timestamp (40 distinct), duration, pipeline_name, injection fields, some `tool_calls` `[]` vs `null`, security flag | coincidence (shared degenerate output) |
| 2 | 7 | gemini-2.5-flash, gemini-2.5-pro (+defences) | github / user_task_18 | 3 | short clarifying question | no | timestamps (7 distinct), duration, pipeline_name | coincidence |
| 3 | 23 | gemini-2.5-pro, llama-3.3 (+defences) | dailylife / user_task_4 | 3 | empty | no | as above | coincidence |
| 4 | 47 | gemini-2.5-pro, llama-3.3, qwen3 (+defences) | github / user_task_16 | 3 | empty | no | as above (46 distinct ts; the only shared timestamp is two files of one model in parallel workers) | coincidence |
| 5 | 9 | llama-3.3, qwen3 | github / user_task_10 | 3 | empty | no | as above | coincidence |
| 6 | 5 | llama-3.3, qwen3 | dailylife / user_task_5 | 3 | empty | no | as above | coincidence |
| 7 | 3 | llama-3.3, qwen3 | dailylife / user_task_13 | 3 | empty | no | as above | coincidence |
| 8 | 6 | gemini-2.5-flash/-pro, qwen3 (tool_filter) | shopping / user_task_1 | 5 | empty x2 | no | as above | coincidence |
| 9 | 7 | llama-3.3, qwen3 (spotlighting) | dailylife / user_task_16 | 3 | empty | no | as above | coincidence |
| 10 | 2 | gemini-2.5-pro, llama-3.3 | github / user_task_11 | 3 | empty | no | timestamps, duration, pipeline_name, `tool_calls` type, security | coincidence |

Base rate: across 648 matched cells, different-model pairs coincide in 1 to 11 cells and only ever as the 3-message
empty reply; same-model pairs under different defences coincide in 67 to 87 cells (llama), all 3 messages. Empty
completions are a recurrent failure mode of the llama/qwen/gemini API endpoints used, so many unrelated runs produce
the same (empty) transcript. Distinct `evaluation_timestamp` values and different durations rule out a file copy.

## Side observation (not part of C5, worth a line in the analysis)

In AgentDyn, `gemini-2.5-flash` with `piguard_detector` and with `prompt_guard_2_detector` have 425 of 648 cells with
identical message lists, and with `transformers_pi_detector` 357 and 275 (3 to 13-message trajectories, up to 23). If
those were copies, `evaluation_timestamp` would be shared. I did not examine this further (outside the question); it is
a candidate for the same timestamp/duration test, because multi-call identical trajectories are less obviously
explained by empty output. One may reasonably expect this for a deterministic model with a detector that never fires,
but it should be checked before it is described as coincidence.

## Conclusion and recommended disclosure wording

Conclusion: the 23 groups are independent runs that happened to produce the same transcript, mostly because the
transcript is trivial (an empty completion, a one-sentence answer, one canonical tool call) and the tool outputs are
deterministic. Per file, they differ in recorded duration and (AgentDyn) evaluation timestamp; they were introduced in
separate model-directory bulk commits (head) and no blob is shared. Treating them as distinct executions (`content_dedup
= never`) is therefore correct.

Suggested manuscript / datasheet text:

> "Some short runs are identical across model labels in the source logs (AgentDojo-HEAD: 13 pairs of 3 to 7 messages;
> AgentDyn: 10 groups, mostly 3-message runs whose single assistant reply is empty). We checked the source files: none
> is byte-identical, their blob identifiers differ, recorded durations (and, in AgentDyn, evaluation timestamps) differ,
> and in AgentDojo the files were introduced by separate model-directory commits (three pairs, flash-001 and flash-exp,
> share one bulk commit but are 3 of 753 matched cells). We therefore regard them as independent executions whose
> transcripts coincide because the runs are short and deterministic, not as duplicated files. They are retained as
> separate executions; analyses that treat runs as independent samples should be aware that trajectory identity across
> models is possible for short runs, and that identical transcripts do not show identical decoding."

Caveats: AgentDyn history unavailable (shallow clone), so introducing commits are unverified there; the argument rests on
file contents. A forged copy that also rewrote durations and timestamps cannot be excluded in principle, but nothing
suggests it and the base-rate profile is inconsistent with bulk copying.

Scratch scripts (not in the repository): /private/tmp/claude-501/-Users-professional-Desktop-PhD-Labs-AgentPROV-framework/9434a108-33e9-46fa-846b-ba9851ddd0d0/scratchpad/c5*.py
