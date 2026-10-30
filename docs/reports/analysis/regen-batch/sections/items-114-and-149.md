## Items 114 and 149 (phase 10m, MCPHunt; held on `bugpass-regen-mcphunt`, in the pre-round integration): row recorded at integration from the owner's records

Source: `docs/reports/phase10m/README.md` §items 114/149, DECISIONS D-31 addendum (regen items 33–41; mcphunt v2 at
`081a6291…`), spec D.21.2/D.21.6. Predictions per the D-451 scopes: `adapters/mcphunt/*` is outside the stage engine
scopes. So the family's `adapter_code_sha256` moves, not an engine `engine_code_sha256`.

- **114 (4db05b90): the reader registers a Git LFS pointer file** as `select.not_execution_artefact`
  (`mcphunt.lfs_pointer`, rule `mcphunt.lfs_pointer@1`), instead of sealing it as a degenerate execution beside its R3
  pinned object.
  - **Prediction:** mcphunt `adapter_code_sha256` moves. The rule is appended to the mcphunt v2 catalogue (the one v2
    byte set, `081a6291…`, so the catalogue's `apv:sha256` in PROV is v2's).
  - An import from a checkout has one degenerate AER fewer per LFS document, and the register gains rows.
  - No mapped AER changes. No kept corpus.
- **149 (b67fa858): every MCPHunt record locator is a C.9.1 byte range** over its trace's slice: `{"a", "bytes":
  [start, end], "p"}`, and the envelope members' own spans for the judge version. So documents over `max_json_bytes`
  (64 MiB) resolve.
  - **Prediction:** mcphunt `adapter_code_sha256` moves. Every MCPHunt AER's `src` locators change, and so do their
    AER, SEM and PROV digests.
  - No profile or catalogue change, no rule. No kept corpus.

