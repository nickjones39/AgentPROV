# Phase 10q routing (R-10q-1..R-10q-4)

| Id | What | File (owner) | Status |
|---|---|---|---|
| R-10q-1 | `TraceLoggerMapper.accepts` gains `(agentdojo.results_container, rc.k7/rc.k12)`; `map` and `degenerate_header` dispatch that dialect to `results_mapper` (D-471, the D-270/RT-1 pattern) | `adapters/agentdojo/mapper.py` | **in this branch**: assigned here by the orchestrator on 2026-10-14 after regen-items-2-12 landed (origin/main 9999c41e); regen-items does not touch the dispatch |
| R-10q-2 | `citation.NAMESPACES` gains `rescont` | `adapters/agentdojo/citation.py` | in this branch |
| R-10q-3 | `CATALOGUE_HOMES["rescont"] = "agentprov.adapters.agentdojo"`, and `tests/unit/adapters/test_discovery.py` lists it | `aer/rules.py` (core) | in this branch; a one-line merge conflict with the bug pass's held item 33 (`RuleCatalogue.rules` immutability) and possibly deferrals-c |
| R-10q-4 | the regeneration-batch entry below | `docs/reports/analysis/regen-batch.md` (regen-batch owner) | text for the owner; implemented in this branch only through R-10q-1..3 |

The shared redaction (D-476) is wired into the TraceLogger build by the regen-items session after this branch lands; the
directory-name case (R-10j-1) is proposed in `d510-directory-account-paths.md` (D-510).

## R-10q-4: regeneration-batch entry (D-479)

**What moves.** Code identities only:

| Identity | origin/main 9999c41e | this branch | Moves for |
|---|---|---|---|
| `adapter_code_sha256` of `adapters/agentdojo` | `c311b5a6…` | see the final value in the README §8 | every agentdojo-family import or re-map made afterwards |
| `aer` stage `engine_code_sha256` (`adapters/runner` + `aer`) | `24df84b5…` | `0bf9409e…` | every import or re-map made afterwards, in every family (R-10q-3 edits `aer/rules.py`) |
| `sem` stage (`sem`, `semantics_profiles.py`, `adapters/agentdojo/semantics`) | `ae0ee532…` | `ae0ee532…` | none |
| `prov` stage (`prov`, `vocab`) | `d57bd291…` | `d57bd291…` | none |

**What does not move.** No AER, SEM or PROV byte of any stored corpus: the dispatch is taken only by items of the new
dialect, no existing profile declares `[[family.agentdojo.redact]]` or `container_table`, and the `rescont` catalogue is
cited by no existing record. Proof: `tests/adapters/agentdojo`, `tests/unit/adapters` and `tests/unit/aer` (every
agentdojo golden AER and digest file) pass unchanged on this branch (1,174 passed, targeted, 2026-10-14), and the gate
suite.

**Consequence for stored corpora.** A working corpus paused before the merge is refused on resume (G4, the `aer` stage
identity). `recompute --dry-run` of a stored corpus at the new main reports the moved code identities as drift (the
F-8 ruling: old corpora reproduce at their building commit), with byte-identical AERs.
