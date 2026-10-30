- **D-621 amendment 2 (2026-10-22, pre-round verification `verify-66513065.md` V-2, V-3, V-6; assigned by the
  orchestrator; branch `integration-fix-verify-tier4` from `8af8adc3`; regen item 164).**
  - **V-2.** PV-NE-20 compares the set of `prov_primary` values of the artifacts that share a digest with the raw
    entity's (multi-valued) `apv:provPrimary`, and a raw entity is a primary source when any of them is native or
    byte_derived, as #18 (a) emits. The last-wins scalar map failed the engine's correct output for identical-byte
    twins that differ in `prov_primary` (latent: no stored AER has duplicate digests).
  - **V-3.** The one-hop link of E-3 (a record that names an anchor in any top-level field, or is named by one) is
    replaced by per-rule premise links (`linkage.PREMISE_LINKS`): the record kind, the linking field and, where the
    engine's citations are closed, the pointers the link binds. `assoc_tool`: the message the execution's `call`
    names (`/generated_by`, `/actor`) and its generator (`/actor`); `start_tool`: the execution's actor (its
    AutoExecution citation); `decision`: a decision whose `subject` names the statement's entity; `gen_result`: that
    decision (`/subject`) and a message it generated (`/generated_by`); `outcome`: the scope of a checked message
    (`/scored`); `n_model`: a model call of the service's actor (`/served_model`); `n_part`: the decision
    (`/subject`, `/verdict`) or seal issue (`ids`) about that part (part ids now match exactly). Scope, run and actor
    records no longer pass as evidence: the measured residual (assoc_tool 17/27, decision 12/29, n_model 12/29,
    gen_result 7/29, n_part 4/29 wrong records accepted) drops to the statement's anchors only.
    - **Residual (recorded, not tightened).** `n_model` is one rule for an actor's model node and its service node,
      so a model call's `/served_model` of the same actor also binds on the actor's model node; both name the
      actor's model. A decision's other fields (for example `/original`) stay open under `aprov.decision@1`, since
      the engine may cite them on that rule's nodes (a split attribute).
    - **Rejected.** Excluding only `/scope`, `/parent` and actor references from the one-hop relation (the
      verification's first option): `outcome` rests on exactly a scope's `/scored`, and any other field would still
      bind any record that names an anchor.
  - **V-6.** Tests for the other branch of #15 (an unk `/authorised_by` fires neither start_tool nor the AutoExecution
    delegation, cited by the execution or its runtime; an unk request-message generator names no requester) and of
    #24 (another assessment bundle and an unknown bundle are out of scope; core, inference and the own bundle are in
    it). Each new test fails on the unfixed or mutated code.
  - **Class 1:** the validation `engine_code_sha256` moves (`validate/`); prov, SEM, AER and compat do not. No
    validation row changes: 480 documents from the 8 stored corpora, stored and fresh, pass with no finding, and a
    coverage run (64 fresh documents) binds through every link kind except the seal issue's.
