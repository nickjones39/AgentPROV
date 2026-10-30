# Item-22 re-measure: home-directory paths after regeneration (plan §7b, obligation 5)

Datasheet item 22 and the statement `benchmark-and-model-home-paths` cite
[`docs/reports/bugpass/home-paths-classification.md`](../../bugpass/home-paths-classification.md), which was measured
on the **stored** corpora. The plan asks for the same check on the regenerated `ast-survey-agentharm` and `agentdyn-a`.

**Method.** `tools/regen/homepath_remeasure.py` (counts and opaque ordinals only; no name or path is printed or written)
reads every AER and PROV file of a stored corpus and of its regenerated copy:
- It finds the D-457 account-path names, using `tools/release_scan.py`'s own patterns, allowlist and D-604 labels.
- For each name it records:
  - the executions that hold it;
  - the PROV files that hold it;
  - the kind of the first AER record that holds it in each execution;
  - the executions whose earlier records hold the bare token;
  - the hits under harness-derived pointers.
- It then compares the two corpora name by name, in memory.

The 2026-10-22 classification's own script was not kept, so this does not recount its labels. It checks instead that
what that classification read has not changed.

| Corpus (stored → regenerated) | Executions | Names (stored / new) | Same names | Per-name feature differences | Harness-field hits |
|---|---|---|---|---|---|
| `ast-survey-agentharm-p10` → `-rg2` (5fc39c16) | 1,056 | 23 / 23 | yes | 0 | 0 |
| `agentdyn-a-p10` → `-rg1` (5b1f6fdf), `task.suite == "github"` | 12,444 | 14 / 14 | yes | 0 | 0 |

- **agentdyn-a:** the 14 names and the 12,444 github-suite executions are the classification's N1–N14 and its count.
  Every name first appears in a message record, as it says.
- **ast-survey-agentharm:** the D-457 shapes find 23 distinct names. The classification lists 18, S1–S18, of the
  `/home/<name>/` shape that the pre-round redaction proof reported. The difference comes from the shape: D-457 also
  counts a bare home with no trailing path. It does not come from the regeneration, because the stored and
  regenerated corpora hold the same 23 names with the same features.

**Verdict.** Equal: the regenerated corpora hold exactly the names and occurrences the classification was made from, so
its counts, its labels and the item-22 statement stand unchanged. Records: `ast-survey-agentharm.json`,
`agentdyn-a-github.json`.
