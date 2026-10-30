## Item 17 (implemented, 2026-10-12; deferrals part B, D-207; user-approved): the `v0.k11` system prompt labelled by its digest

Owner's write-up of the table row above (this session owns the `agentdojo-upstream` profile). Evidence: the full
history of `ethz-spylab/agentdojo` (deferrals part B, `docs/reports/deferrals/part-b/` on branch `deferrals-b`; the
store at `$AGENTPROV_HOME/upstream/github.com/ethz-spylab/agentdojo.git`, read only).

- **The default text.** One code state over the whole history: the `default` key of `system_messages.yaml` has
  `a021a92b…` at all 547 commits that carry the file (part B §3). The `v0.k11` logs carrying it equal the code state at
  their own introducing commit.
- **The spotlighting texts (owner's choice: label them, neither of the two offered options).** The 900 distinct
  `runs/gpt-4o-2024-05-13-spotlighting_with_delimiting/` logs carry two texts. Each is reproduced exactly from the code,
  as the default text plus the defence's sentence:
  - `d9524c73…` (606 head logs, the same 753 in 2024-06): the sentence at `c274885`
    (`src/function_calling_pi/agent_pipeline/make_pipeline.py` l. 185-191), written with a typographic apostrophe
    ("I’ll"). All 753 are in the 2024-06 pin (introduced at or before `c274885`, 2024-06-05); the 606 still at head
    were introduced at `a73028f` (509) and `6158e62` (97), both 2024-06-04, and the other 147 were replaced at head.
  - `2954962b…` (147 head-only logs, all introduced at `52df3bc`, 2024-07-16): the same sentence with an ASCII
    apostrophe, after `40085c0` (2024-06-18) rewrote it; the text of the head pin's `agent_pipeline.py` l. 267-273,
    already the label `agentdojo_default_spotlighting` in the AIAuthz and menelaus29 profiles.

  So no `v0.k11` log is left `system_prompt_unrecognised`, and no selector has to hide a defence.
- **Change (profile only; no code, no rule change).** In `agentdojo-upstream.profile.toml`
  `[harness] system_prompt_variants`:
  - `agentdojo_default` gains `v0.k11` in its `applies` variants;
  - new `agentdojo_default_spotlighting` (`2954962b…`, source the head pin's `agent_pipeline.py`), and new
    `agentdojo_default_spotlighting_2024_06` (`d9524c73…`, source `c274885`'s `make_pipeline.py`), both
    `applies = { variant = ["v0.k11"], pipeline_dir = ["*-spotlighting_with_delimiting"] }`;
  - the phase-10 comment above the list is rewritten to say why, citing D-207.

  The rule `agentdojo.system_prompt_variant_digest@1` is code-independent (`INDEPENDENT` in
  `adapters/agentdojo/citation.py`: a digest comparison against pinned bytes), so the labels are D whatever D-84 says
  about the producing code. The profile's `version` stays 1 (AD-18: nothing is released yet; item 13 kept it too).
- **Also in the same profile change (orchestrator, part B §2): the `history` part's note.** It says "11,173 superseded
  blob versions". Reconciled on the full index: 11,173 is the number of distinct `runs/` blobs absent from the head pin
  (47,852 distinct blobs in the history, 36,679 at head); 4,059 of them are held by the 2024-06 pin, which the `2024-06`
  part already imports. What the `history` part would add is the versions held by neither pin: 7,867 `(path, blob)`
  versions (7,114 distinct blobs). The note becomes that, with the 11,173 explained. `D_adapters.md` quotes the note
  and changes with it; `I_matrix.md`'s "11,173 no longer at head" is correct as worded and stays.

**Digest prediction** (read-only scan of every stored AER of the two corpora, digest of the system row's text by the
mapper's rule; it reproduces part B's counts exactly):

| Corpus | `v0.k11` executions | `agentdojo_default` | `…_spotlighting_2024_06` | `…_spotlighting` | no system row (unchanged) |
|---|---|---|---|---|---|
| `agentdojo-upstream-2024-06` | 18,241 | 17,281 | 753 | 0 | 207 |
| `agentdojo-upstream-head` | 24,914 | 23,954 | 606 | 147 | 207 |

- **AER content:** those 18,034 and 24,707 AERs gain `ext.agentdojo.system_prompt_variant` on the system row, with
  `evf` D and the rule citation. No `system_prompt_unrecognised` issue is added. The head `v1.k14` logs (11,765) keep
  their label.
- **AER bytes:** every AER of both corpora (the profile digest is in each header, as for items 3 and 13).
- **SEM and PROV:** they change only through the AER and profile digests they carry. The engine does not map `ext`,
  so no PROV statement is added or removed; to be confirmed by the full-derive sample check after implementation.
- **No other corpus moves.** Geryon and AgentDyn already label their `v0.k11` logs from their own profiles; no other
  profile changes.
- Needs a re-map from stored raw (recompute), as for item 13.

**Implemented (2026-10-12, branch `claude/item-17-d207`).** The profile change above, with the note; D.6.11 item 9 marked
superseded and D.6.12 item 6 rewritten. Tests: `test_v1_import.py` (`test_system_prompt_variant_label` now expects the
v0.k11 label; `test_spotlighting_variants_apply_to_their_run_directory_only` for both spotlighting texts and their
selector; the head-fixture test requires a pinned variant on every v0.k11 system message and no
`system_prompt_unrecognised`). Pins regenerated: C.16.1 vector (its system message gains `agentdojo_default`; records
digest `a8635c14…`), agentdojo AER digests (2024-06 and head fixtures), gate D.

**Full-derive sample check (2026-10-12).** 300 stored executions per corpus (every stratum of items 13/14's check, plus
66 and 60 spotlighting logs and the no-system-row logs), re-mapped from the raw store with the old code (`c88af67`) and
the new (item 17), then SEM (`suites@1`, `@2`), PROV and tier 4:
- tier 4 passes 600/600 for both SEM versions under both codes; 0 errors;
- labels as predicted: 2024-06 `agentdojo_default` 200, `…_spotlighting_2024_06` 66, none 34 (no system row);
  head `agentdojo_default` 218 (82 of them `v1.k14`, already labelled), `…_spotlighting_2024_06` 50, `…_spotlighting`
  10, none 22; `system_prompt_unrecognised` 0 under both codes;
- AER: only the label (with its `evf` and rule) and the digests differ; SEM identical with digests masked (574/574);
- PROV: for 60 relabelled `v0.k11` executions (30 spotlighting, 30 default) and both SEM versions, the statement
  multisets are identical with digests and digest-derived identifiers masked (120/120). The engine does not map `ext`,
  so the label adds no PROV statement, as predicted.

**Rejected:**
- `system_prompt_unrecognised` on the spotlighting logs: both texts are reproduced from pinned code, so the issue would
  be false.
- An `applies` selector that skips the defence: it would hide 900 logs that can be labelled on the same evidence.
- One label for both spotlighting texts: they differ by a character; a label names one pinned text.

**Round outcome (2026-10-22, regeneration round; measured, `docs/reports/regeneration/round/`).** `agentdojo.system_prompt_variant_digest@1`
is newly cited in 18,034 executions of 2024-06 and 24,707 of head, as predicted. No other corpus cites it.

