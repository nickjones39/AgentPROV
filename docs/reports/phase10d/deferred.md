# Phase 10d: sources not profiled in this phase, and why

Status 2026-10-12. Sources of the phase-10c shortlist that are in phase 10d's scope ("medium, if time allows") but get no
profile here. Each has a blocker that a profile cannot honestly work around. None was imported; nothing below changes
an existing corpus. The out-of-scope sources (both Zenodo deposits, the rest of Figshare, DRIFT-format runs, saber) are
listed at the end for completeness.

## llm-lock (Wakeful-Cloud/llm-lock @ 7bb9915b, GPL-3.0, 53,307 logs): profiled after R4

No longer deferred: `llm-lock-agentdojo` (D-114; `routing.md` R4, R10).

## EnvironmentOptim (omseeth/EnvironmentOptim @ febf82d8, MIT, 6,120 v1.k14 + 620 DRIFT): needs design decisions

- **Model identity.** The logged name is a munged local path (`_ceph_ssd_students_<account>`, `-2B`, `-4B`): RL
  checkpoints of a Qwen3.5 base at training steps (`checkpoint_N/{256,320,512}`), not a published model. A row would
  have to say "a fine-tuned checkpoint of <base>, step N", and the base size of the unsuffixed path is not stated in the
  logs. This needs the user's ruling on how training checkpoints are identified (model id, `ext` fields for checkpoint
  and arm).
- **Interpretation.** The runs are training rollouts and controls of an RL study; the datasheet must say so.
- **Layout.** Run directories nest at irregular depths (and once twice: `checkpoint_4/256/_ceph.../workspace/...`).
- **Ownership.** 83,740 of its 90,480 TraceLogger files are byte-identical copies of upstream `runs/` (36,679) and
  AgentDyn variant A (47,061), to be registered `select.owned_elsewhere` with two owners; 620 runs are `drift.k18.messages`
  (`select.dialect_planned` until D-96). 111 files outside the runs hold secret-like strings (count only).

## Kavach (Ishani018/Kavach, MIT; three branch pins, 2,625 byte-distinct, about 957 distinct trajectories)

- `main` (223 logs) is contained in both other branches; `nav-fixer2` and `rearch-forcedformat-fix` re-serialise the same
  experiment (883 trajectories shared by content in different bytes). One corpus holds one snapshot today (D-108); a
  corpus of all three pins needs phase 11's multi-snapshot support, and the content repeats need a declared policy
  (`content_dedup` stays `never`; the repeats must be disclosed per execution or in the datasheet).
- Identity: `local` model from the path (`agentdojo_slack_gemma_dell`, `banking_qwen25_7b`): directory labels, class I.

## Figshare 32657856 (DCA artefact v1, MIT): not importable through the product path today

- The deposit is a zip. `agentprov import` refuses a `.zip --input` and a non-git `--fetch` (exit 5, deferred), so not
  even its 11,406 plain v1.k14 runs can be trial-imported. 1,968 further v1.k14 runs sit behind the `:` name gate (D-91)
  and 2,847 are DRIFT (D-96). Waits for phase 12's ingest decisions (D-90, D-91) and archive inputs.

## Out of scope for phase 10d (for completeness)

- Zenodo 22973265 and 22011266: nested tar.gz (D-90), phase 12.
- DRIFT-format runs anywhere (Figshare 2,847, EnvironmentOptim 620, drift-1 626): the DRIFT mapper (D-96).
- saber: EX-NOLOG (outcome-only files).
