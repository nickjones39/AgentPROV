# Systematic source search: eligibility criteria

Status: criteria fixed 2026-10-11, before screening. This file is part of the manuscript appendix on how the converted
corpora's sources were selected (decision D-25). The search protocol, search log, PRISMA flow and the included/excluded
table are added beside it after screening.

**Scope.** A record is any repository, dataset, deposit or paper artefact found by the searches of code platforms,
research-data repositories and the literature. The searches also cover the sources AgentPROV already converts, and
those sources are screened with the same criteria. The manuscript reports **every** screened record in a single
included/excluded table. Each excluded record gives the first criterion that excluded it, applying the codes in the
order listed below (licence, then the other criteria, then size).

## Inclusion criteria (all must hold)

- **IN-1 Run logs.** The record releases per-execution logs or trajectories of LLM agents (messages, tool calls, tool
  results), not only a benchmark definition, aggregate scores, detector outputs or code.
- **IN-2 Agent security relevance.** The executions come from an agent-security or agent-safety benchmark or
  evaluation (prompt injection, harmful tool use, misuse, control).
- **IN-3 Convertible format.** An AgentPROV adapter family can read the logs (AgentDojo family, Inspect `.eval`,
  AgentDojo-PROV transcripts), or a new adapter is feasible without changing `aer/`, `prov/`, `validate/` or `corpus/`
  (invariant 5).
- **IN-4 Redistributable licence.** The data is under a licence that permits redistributing derived data (see LIC).
- **IN-5 Identifiable and pinnable.** The bytes can be pinned (commit, DOI version or content digest), so the
  conversion is reproducible.

## Exclusion criteria (any one excludes)

Licence criteria (user decision, 2026-10-11):

- **EX-LIC-1 No licence.** No licence covers the data: there is no LICENSE file, no licence in the dataset card,
  deposit metadata or README, and no repository-level licence that covers the data files. Example: Hugging Face
  `sungjuncho/agentdojo-trajectories` and its byte-identical mirror `tomciotomcio/agentdojo-trajectories`, which are
  excluded despite their exact AgentDojo layout.
- **EX-LIC-2 Licence forbids redistribution.** The licence permits use but not the redistribution of the data or of data
  derived from it. This covers evaluation-only, research-only-no-redistribution and custom licences with that effect.
  Example: an evaluation-only licence, such as NVIDIA's on the Nemotron agentic-safety dataset.

Other criteria:

- **EX-NOLOG Not run logs.** The record contains code, benchmark definitions, scores, detector outputs or redacted
  prompts only (fails IN-1).
- **EX-SCOPE Out of scope.** The executions are not agent-security or agent-safety evaluations (fails IN-2).
- **EX-FMT Not convertible.** The format cannot be read faithfully: missing tool calls or results, or a new adapter
  that would require a core change (fails IN-3).
- **EX-ACCESS Inaccessible.** The data is gated behind a manual approval that is not granted, or is withdrawn or
  unreachable. A gated record whose terms are accepted is screened normally.
- **EX-DUP Duplicate.** The record is a byte-identical mirror or re-upload of an included record. It is listed with a
  pointer to the record it duplicates. If the original is excluded, the mirror takes the same exclusion code.
- **EX-PIN Not pinnable.** The bytes cannot be identified by commit, version or digest (fails IN-5).

Size criteria (user decision, 2026-10-11; two tiers):

- **EX-SIZE-1 Too small for any source.** A source with fewer than **100** distinct runs is excluded. This removes
  demonstration and toy repositories.
- **EX-SIZE-2 Too small for a new adapter.** A source that no existing AgentPROV adapter family can read, and so would
  need a new one, is excluded with fewer than **1,000** distinct runs. A new adapter costs days of implementation
  and continuing maintenance; a source readable by an existing family costs only a profile and a pin.
- **How runs are counted:** distinct executions after removing byte-identical duplicates of runs already in an
  included source. A mirror counts once (EX-DUP). Counts estimated from listings are confirmed before the final
  decision; a source within 10% of a threshold is counted exactly.
- **Disclosure:** these thresholds were set after the known sources had been identified, so they are reported as
  post-hoc screening criteria. The appendix includes a sensitivity table of the included sources and run totals
  under no threshold, 100, 1,000 and 5,000 runs.

## How the licence is determined (LIC)

1. Read the licence where the data is published. Check the repository's LICENSE file, the dataset card or deposit
   metadata, and the README, in that order. A missing licence tag on a platform is **not** enough to call a record
   unlicensed: the README or LICENSE file may still state one.
2. **A repository-level licence that covers the data counts as a licence.** Examples are MIT by repository for
   `runs/` in AgentDojo upstream, ROPE and AgentDyn. The basis is recorded verbatim, e.g. "MIT by repository; data
   licence not separately stated", as the source profiles already do.
3. **A use clause that still permits redistribution does not exclude.** One example is AgentHarm's MIT licence with
   an AI-safety use clause. Such a record is included, and the clause goes in `licences.restrictions` in a separate
   restricted-use corpus (U-05).
4. Every record states its licence as an SPDX id, `none`, `custom-restrictive` or `unknown`, and says where the
   licence was found. `unknown` is resolved before the record is included. It is never an inclusion by default.
5. **Copyleft and non-commercial licences permit redistribution, so they do not exclude** (user decision,
   2026-10-11):
   - **GPL-3.0 and AGPL-3.0** data is included. Each such source becomes its own corpus under that same licence,
     because a derived corpus must carry it. It is never mixed into a corpus under another licence.
   - **CC-BY-NC** data is included under the existing registry policy `nc_partition`, in a separate non-commercial
     `-nc` corpus (§I.0.2, R-14).
   - The table records the licence and the corpus it goes to.
6. These criteria do not assess model-provider terms on redistributing model outputs. The manuscript notes this as a
   limitation, as the source cards already do (I_matrix C03).

## Relation to the source registry

Exclusion is a screening outcome, not a registry status. If an excluded record is registered at all, it is registered
under the existing vocabulary (§I.0.2):
- EX-LIC-1 and EX-LIC-2 become licence policy `reference`: the location is recorded and nothing is imported. If the
  licence explicitly prohibits redistribution, the policy is `forbidden`.
- EX-DUP becomes role `mirror`.
- EX-NOLOG becomes role `not_executions`.
