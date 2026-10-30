- **D-31 addendum (2026-10-14, bug pass regen items 33-41: the agentops and mcphunt bumps; reviewed by the D-31 owner,
  user-approved with the items 2026-10-14, held for the regeneration round).** Items 37 and 40 add catalogue issue codes,
  so each family is bumped once (one bump per catalogue per round):
  - catalogues `agentops` and `mcphunt` 1 -> 2; the `mcphunt` v2 catalogue also carries `mcphunt.lfs_pointer@1` (phase
    10m regen item 114, taken into `bugpass-regen-mcphunt` at 4db05b90 so that one v2 byte set exists; v2 sha256
    `081a6291…`);
  - profiles `agentops-bench-pilot` and `mcphunt` 1 -> 2, with `[source]`/`[import] rules` declaring version 2;
  - new semantics versions `agentops.tools@2` and `mcphunt.tools@2` (version 1's tables, reading catalogue 2; H.2.5:
    one catalogue version per corpus), with `tools.py` following the profile version (`CATALOGUE_OF`, as in
    `agentdojo.suites`);
  - registry parts on `@2`;
  - version 1 of each catalogue and profile ships under `archive/`, byte-identical to main before the bump (digests
    pinned in each family's `test_d31_bump.py`), and `tools@1` is unchanged and reads the archived catalogue, so stored
    corpora stay recomputable at their recorded versions (D-430: at main, recompute reports the drift and refuses
    `--out`; the round re-imports).
  The held work is one branch per family (`bugpass-regen-{core,agentops,credleak,mcphunt,openhands}`), because each
  family's new-family guard admits only that family's files.

