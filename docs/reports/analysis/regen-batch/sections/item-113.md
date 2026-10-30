## Item 113: melon defence messages (2026-10-21; D-586; user-approved; held branch `claude/artefact-catalogues-family-fixes-6451d3`)

- **What:**
  - `melon-agentdojo@2` declares `agentdojo.melon_defence_messages` (hook `hooks/melon.py`), on the new hook point
    `message_author` (`quirks.py`).
  - `mapper.py` adds two calls (the system branch of `_plain`, and `_assistant` before the message is appended) and the
    helpers `_message_author`, `_authored_system` and `_defence_reply`.
  - `agentdojo.rules.toml` v2 gains two class-I rules in place.
- **Moves:**
  - the AER of every melon execution (the profile header);
  - in 913 executions, a `terminate` decision record by the defence, with the final message's author, `generated_by`
    and `after` changed;
  - in 98 MELON-R executions, the author of 113 system messages (the defence), and the harness prompt behind them
    (`bench`, labelled);
  - then the SEM and PROV of all of them;
  - the `agentdojo` catalogue digest, which is in every PROV derivation key and therefore in every agentdojo-family
    corpus at its next re-derive (as item 103 already needs).
- **Stored corpora:** none. **Fixture pins:** the 11 melon rows of `tests/adapters/agentdojo/phase10d_aer_digests.json`.
  The golden PROV pins embed the `agentdojo` catalogue digest, so `tests/golden/prov_digests.json` and
  `gate_d_digests.json` were regenerated with `tools/regen_pins.py --write` (counts in the commit). The agentdyn, drift
  and C.16.1 pins are unchanged.
- **Census of the full snapshot:** recorded below.

