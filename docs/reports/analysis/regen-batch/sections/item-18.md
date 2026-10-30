## Item 18 (implemented, 2026-10-12; phase 10f F2, D-156 part 2; user-approved): the TraceLogger layout locator for archive members

- **Change:** for a primary artefact with a `member` origin (an archive member: container sha256, `label` = the member's
  full name, method, crc32, size; the interface agreed with the deferrals session, their D-204), the identity's layout
  locator reads the origin's `/label`. It read `/path` before, which a member origin does not have, so the AER failed
  `aer.locator.dangling` (AER-V21).
- **Why it is enough:** `path_facets` already fell back to the label. The layout templates match the member label
  exactly as they match a git origin's path.
- **Code:** `adapters/agentdojo/mapper.py` (`_identity_src`).
- **Test:** `tests/adapters/agentdojo/test_phase10f_seagent.py::test_member_origins_seal_and_validate_in_release_mode_d156`,
  which replaces the gap test. Every real SEAgent fixture under a `member` origin seals and validates in release mode,
  with the same mapping as under the scratch `local` origin apart from that locator. The runner's archive-input trial
  import is the deferrals session's part A. Their scratch run with this change mapped, derived and validated
  5,342/5,342 SEAgent logs, 0 degenerate.

**Digest prediction:**
- No stored AER moves: no stored AgentDojo-family corpus has a member-origin log (scan of the six stored
  AgentDojo-family corpora: 0 member-origin AERs).
- The `agentdojo` adapter code digest in stored manifests moves at the next regeneration.

