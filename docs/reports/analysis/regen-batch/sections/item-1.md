## Item 1 implemented (2026-10-12; D-86 and its addendum, with D-110–D-112) — digest prediction

Item 1 extends `agentdojo.suites@2` (phase 10d's R8 version, D-110). Version 1, which every stored corpus reads, is
unchanged, so item 1 changes SEM and PROV bytes only for a corpus derived with version 2. Today that is CrAIBench's
trial alone; the other profiles move in R9. The user's answers on 2026-10-12: verify, then extend; the normalisers are
harness-independent; B1 is gated on the AutoDojo link.

| Effect | Where | Count (stored phase-10 corpora; scripts in the session scratchpad) |
|---|---|---|
| AER: `dos_security_rule` / `injection_task_as_user_task` cited at D again, not through item 3's twins (the passages are checked at `089ed468` and the 0.1.35 wheel) | head `v1.k14`, Mandate | head 140, Mandate 27 executions (of the 1,289 head and 27 Mandate executions citing either rule). Fixtures: 1 head and 2 Mandate AER pins regenerated |
| PROV of every corpus: the `agentdojo` catalogue digest (5 code lists extended, 4 twins, 1 new rule) | all corpora | every execution, catalogue digest only; golden pins: 19 PROV, 28 gate-D PROV, 0 SEM |
| SEM/PROV under version 2, B1: markers on AutoDojo-linked fixtures become `present` with the escape undone | ROPE AutoDojo arm (2,847 executions) | 3,344 markers in 1,877 executions (absent → present 2,739, ambiguous → present 605). 1,840 of the 3,344 are verbatim, matching examination 2's census exactly; 1,504 are found through the YAML readings every marker uses. Executions with a `present` marker: 1,118 → 2,528. The 10 long-horizon `ambiguous` markers have no link and stay |
| SEM/PROV under version 2, D-86 twins: outcome and marker annotations cite twins (ev I) | ROPE 10,791, AgentDyn 38,281, survey 3,243 executions, the phase-10d forks | every execution with an outcome or marker annotation; 2024-06 and Mandate stay D. *Corrected 2026-10-15 (corpus pre-check PC-agentdojo-upstream-04, CC-04):* head does not stay D. After the round, the outcome and marker annotations of head-only logs are class I (the D-84 and D-86 twins), and D-83 propagates I to 47 `v1.k14` security outcomes. *Corrected 2026-10-23 (regeneration round, D-359, user option A):* Mandate does not stay D either. Its 369 security outcomes, and 11,236 head `v1.k14` security outcomes (not 47), are class I: their rule `security_polarity@1` stays D, but their judgement's `/origin` cites `agentdojo.checker_outcome_unverified@1` (item 3), and D-83 propagates the weakest premise. Utility outcomes stay D |
| SEM/PROV under version 2: the profile digest | every corpus moved to version 2 | every execution |

**adprov-v1 (user decision 2026-10-12, verified; D-86 addendum).** `a75aba7` (agentdojo 0.1.35, which the writer
`579a908` pins exactly) is added to `adprov-v1`'s `verified_code` for released transcripts. Its task-suite checks and
`tool_result_to_str` are what scored and rendered those runs, and the cited files are byte-identical to `089ed468`'s.
Under version 2, the 17,664 released executions therefore keep D outcomes. Regeneration effect: every adprov-v1 AER
changes through the profile digest (17,664 executions; no rule citation changes), and so do its SEM and PROV. Fixture
pins regenerated: golden and gate-D PROV.

**Round outcome (2026-10-22, regeneration round; measured, `docs/reports/regeneration/round/`: `injection_markers_net_by_status_class`,
`sem_annotations_net_by_kind_class`).**
- **B1:** ROPE has +3,344 `present` markers, from 2,739 `absent` and 605 `ambiguous`, as predicted. In every other
  corpus no marker changes status.
- **D-86 twins** (outcome and marker annotations D → I):
  - ROPE: 21,508 outcomes, 183,896 markers;
  - AgentDyn: 71,352 outcomes, 441,750 markers;
  - survey: 6,069 outcomes, 18,368 markers;
  - head: 31,207 outcomes, 100,688 markers. This is the 2026-10-15 correction: head-only logs go to I.
  2024-06 and adprov-v1 stay D.
- **Propagation, not a twin (D-359):**
  - In Mandate, 369 security outcomes move D → I, one per execution with an injection.
  - In head, 11,236 `v1.k14` security outcomes do too. These are part of head's 31,207 above; the rest are the
    twinned outcomes: security 9,232, DoS 60, utility 10,323 and injection task as user task 356.
  - Their rule stays `security_polarity@1` (D). The judgement's `/origin` premise cites
    `agentdojo.checker_outcome_unverified@1`, whose code list is `c2748856` only.
  - The corpus pre-check found the Mandate case (PC-mandate-agentdojo-eval-04).
  - The user chose to correct the text (option A, 2026-10-23); the corpora stay as they are. The table row above is
    corrected.

