# Phase 10k: needs routed to the orchestrator

## R-10k-1: multi-execution whole-file artefacts in the runner (blocks the full credleak import)

**Status (2026-10-13): implemented as D-320** on branch `r10k1-multi-execution`, stacked on `phase-10k-credleak`. The
user approved the runner edit, the empty-cell rule (`select.not_execution_artefact`, no AER), the per-run `{source_key}`
collapse subject and the number (first D-269, renumbered to D-320 in the orchestrator's range). The deferrals session
(runner owner) approved the design with one required change, made: a file sealed whole as one degenerate AER is
resumed whole by its document-root key, never re-mapped into items. The proposal below was followed. Two refinements:
- single-item readers keep their pre-map digest check unchanged, rather than a source key computed before parsing;
- `map_artefact_total` keeps the single-item rule, and the per-item path is `map_artefact_units`.

Downstream effects: the `aer` stage's `engine_code_sha256` moves for future imports (regen-batch entry `R-10k-1`).
Details are in D.2.9 note item 12 and D.19.14. Merge waits for the user's yes.

**Need.** A credleak cell is one JSON file holding up to 160 runs. Each run is one execution, with source key
`sha256:<cell>#{"p":"/runs/<i>"}`. HL H.7.1 lists this case ("element of a JSON array", `{"p":"/<i>"}`, planned), and
H.7.2 collapses by source key. So the identity model of `aer/`, `corpus/` and `validate/` needs no change. The
`runner/` implements only the one-execution-per-file case:

1. `adapters/runner/__init__.py` `map_artefact_total` (and `map_artefact`) refuses `len(items) != 1`. A multi-run
   cell becomes a degenerate AER (`unparseable_artefact`).
2. `adapters/runner/importer.py` `_Pipeline._seen_before` and `_known_artefacts` key resume and the D-202 cross-snapshot
   collapse on the primary artefact digest alone. With several executions per artefact, the second run of a cell would
   be skipped as "seen".
3. `container` mode (a reader with `plan`) does yield several units per member, but it needs an `expand`-able archive
   and is refused for D-200 archive inputs (`importer.py:745`). The credleak pin is an archive input whose members are
   the JSON cells.

**Proposal** (for the orchestrator; it moves no existing digest):
- `map_artefact_total` returns one outcome per located item when the reader declares it, for example with a class
  attribute `multi_execution = True` (only `CredleakCellReader` would set it).
- The `total` map job then frames each unit as `container` mode does, `{"unit": {...}}` plus its records and seal
  (`split_unit_frames` exists).
- The importer keys `known`, `_seen_before` and the register subjects by **source key** (digest plus locator) instead
  of digest. For every existing reader the locator is the constant `{"p": ""}` (or `{}`), so the keys, resume and
  collapse decisions are unchanged.
- A cell whose bytes fail the strict loader stays one degenerate AER for the whole file, as today.
- **Tests:** a two-run cell imports as two executions (pinned on the phase-10k branch as a strict expected failure,
  `tests/adapters/credleak/test_runner_multi_execution.py`; it flips to XPASS, and so fails, when the change lands); resume after a crash between them maps only the second; a
  byte-identical cell in a second snapshot collapses both runs (D-202).

**Downstream effects.**
- None for existing corpora, as long as the source-key keying reduces exactly to today's digest keying for single-item
  readers. This needs the regression suite plus a `recompute --dry-run` on one existing corpus.
- The credleak `planned` → `partial` gate, part C's full product-path trial and the import (after the regeneration round,
  with the user's approval) wait for it.

**Not done here.** `runner/` belongs to the orchestrator (the phase-10k task rules), so the family ships without it.
Its reader already yields one item per run. Its end-to-end withholding test uses single-run cells, which the current
runner maps as whole files.

## R-10k-2: derivation keys cut by gitleaks fragment boundaries escape the release-scan allowlist

**Resolved** by D-310 (user-approved 2026-10-13): commit `a4fca19` resolves each gitleaks key cut against the file,
merged to main at `0b663f3`. The text below is the need as routed.

**Found by** the part-C3 full-size scan estimate (`trials.md`). `tools/release_scan.py` allowlists AgentPROV's own
content-addressed keys (`_KEY_ALLOWLIST`, user-approved 2026-10-11), accepting a field name cut at the start down to
6 characters (`_MIN_FIELD_SUFFIX`) and a key cut at the end down to 16. On the releasable credleak PROV files, gitleaks
cut 5 matches further: four field names to 3-5 characters (`onKey":"`, `nKey":"`, `Key":"`) and one key to 12
characters. Each is reported as `generic-api-key`, and the credleak profile names that rule in `scan_rules`, so each
needs a person's `false-positive` triage before a deposit.

**Not a one-line fix.** Lowering the field minimum to 3 would also hide `apiKey":"<26 base32 characters>"`. Options
for the owner of `release_scan.py`: (a) a second pass that resolves each `generic-api-key` match back to the full JSON
member on its line and drops it only when the member is `apv:derivationKey`, `subject_key` or `logical_key`;
(b) accept per-fingerprint triage. No change was made on the phase-10k branch.

## Notes for the orchestrator (no action needed in phase 10k)

- `docs/architecture/DECISIONS.md` D-234 still says "No shipped profile declares one yet". It is a dated record, so it
  is left as written; D-265 supersedes it in practice. The stale sentence in the sec25 test docstring is corrected on
  this branch.
- Phase 10e's card 3.10 counts (654 cells; OpenAI-like 17,479, which overlaps the Anthropic-like strings) are corrected
  in `census.md` (643 cells; disjoint counts). The card in `phase10e-candidates.md` is a released report and was not
  edited.
