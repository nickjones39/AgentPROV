- **D-621 amendment (2026-10-22, the area-E minors of the pre-round review; scope extension and user decisions of
  2026-10-22, relayed by the orchestrator session; D-31 owner ruling of 2026-10-22).**
  - **Validator.**
    - #23: `pv.linkage.existence` checks class ≤ the rule's ceiling, and an AER node's class ≤ its record's `ev`.
    - #24: the premise routing scope covers assessment bundles.
    - #25: a reflexive `mentionOf` is a Constraint 52 finding.
    - #26 (plausible): the new check `pv.linkage.aer_binding` binds the AER entity and every bundle dk to the AER
      validated against. It recomputes with the document's own recorded `aprov` digest, since catalogue drift is
      D-460's to report.
  - **Engine.**
    - #16: an item declared `unk` fires no usage.
    - #15, user decision (a): unknown is not absent for negative rule conditions, so the dead guard is replaced. Class
      2: the attributions (and AutoExecution starts and delegations) that rested on an unknown generator or
      authorisation are no longer emitted, as in the foobench trace and live captures with `missing_generated_by`.
    - #17, user decision (a): message nodes state `apv:partOf` / `apv:thread` from `/scope` under the new rule
      `aprov.n_message@2`; `@1` stays for the documents that cite it. Class 2: every message node.
    - #18, user decision (a): one raw entity per content digest. Per-artifact attributes are multi-valued and
      sorted, and t_* statements are made once per digest. Only AERs that refused before are affected.
  - **Catalogue.** `aprov` goes to version 2 (D-31 owner ruling): stored corpora record v1, so a content change at an
    unchanged integer is refused. v1 = `79b0a1e78dc7…` (main's bytes) is archived byte-exact and answered by
    `corpus.authority`. The 3 older corpora that record `000598fdb9a2…` (pre-D-31 in-place edits) stay drift-window.
  - **Rejected.**
    - #15 (b), unknown as absent: it states an attribution the AER marks unknown.
    - #17 (b), amending the spec instead: thread membership would stay lost.
    - #18 (b), per-artifact raw names: they break the content-addressed scheme.
    - #18 (c), refusing duplicate digests at tier 2: identical auxiliary files would make a source unimportable.
    - Changing `aprov.n_message@1` in place: it would change what stored citations mean.
  - **Not done here, routed.** Recording `rules: {aprov: <n>}` in the prov stage definition, so that recompute can
    print the D-430 drift line instead of `rules.mismatch` (D-31 owner's recommendation; it moves the prov fn_digest).
    It goes to the EF owner as a pre-round sibling item.
