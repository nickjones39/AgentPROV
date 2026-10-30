
**Not in the batch (no corpus change):** datasheet statements (C4, c1, c2, c5 and the artefact wording; checklist in `datasheet-items.md`, applied by phase 11); B2/B4/B5 and the escaping
fixes F-02…F-07, F-09, F-14 (applied directly); F-08 (glob matcher) only if its selection semantics stay identical
for every shipped pattern, otherwise it joins this list; F-12 depending on whether TriG is stored in a corpus. From examination 2: E2-b4 (= F-04) and E2-b7 (= F-02) are already applied; E2-b5
(catalogue entries for 156 unclassified safety-net findings) changes no corpus bytes; E2-b6 (`$utf16` in typed text)
is **rejected** by D-23 (the adapter-layer replacement, item 7, is the fix).

**Phase 12a (2026-10-11; `docs/reports/hardening/sec-coverage.md` §5).** Applied directly, none changes an AER, SEM or
PROV byte (golden and gate-D digests unchanged): the validator and `pointer_get` robustness fixes, `io/atomic.py`,
`prov/serialise/time.py` (`re.ASCII`; output-identical), and the importer's `worker.limit.*` register row for a stopped
job whose degenerate AER cannot be sealed (a `register.jsonl` row that was missing; only corpora that had such a stopped
job would gain it at regeneration). **Proposed at the time, not applied then; status since:**
- F-08 compiler hardening in `raw/members.py` (refuse multi-`*` segments): selection is unchanged for every shipped
  pattern (pinned by `tests/security/test_selection_patterns.py`), but `raw/members.py` is an `EXPAND_MODULES` file, so
  the `expand` stage's `fn_digest` in `raw/members.jsonl` (and a resumed import's identity check) would change. Suggest
  bundling it with the regeneration. *Since applied as D-59 (phase 12b expand bundle).*
- A mapper fallback (or `aer/0.2`) for a degenerate header that cannot name its task (`task.task_id` is required with no
  `unk` escape), shown for both the AgentDojo and adprov families; AER bytes change only for units that are today
  registered `map.adapter_defect` without an AER. *Since resolved: the mapper keeps a usable task id (`eb8c377`), and
  aer/0.2 lets a degenerate header declare its task id not captured (D-219, item 151).*
- F-13: escaping C0/C1/bidi in TriG literals belongs to phase 11's `derive --trig` (TriG is not stored, AD-10 row 3).
  *Not a regeneration item.*

