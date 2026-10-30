# Systematic source search (manuscript appendix)

This search finds benchmarks, forks, derivative projects and deposits that release LLM-agent run logs which AgentPROV
can convert to W3C PROV. It also justifies the sources already converted. **Everything here is kept for the
manuscript.** Nothing in this folder may be deleted. Superseded files are renamed, never removed.

| File | Content |
|---|---|
| `eligibility-criteria.md` | Inclusion and exclusion criteria, including the licence rules (D-25), fixed before screening |
| `protocol.md` | The search protocol as run: questions, strands, query logs, dates, screening stages, how the criteria were applied, de-duplication, limitations |
| `prisma.md` | PRISMA-style flow: counts per stage per strand and merged, with a flow diagram |
| `included-excluded.md` | Appendix table of every distinct source (licence, runs, decision, code, corpus); good sources excluded only by licence; large sets; strand conflicts; phase-10c and phase-10e verification outcomes |
| `sensitivity.md` | Included sources and distinct runs under no size threshold, 100, 1,000 and 5,000 runs (current corpora and candidates separately) |
| `justification.md` | Why each source AgentPROV already converts meets the criteria |
| `records-merged.jsonl`, `records-merged.csv` | One row per distinct source after cross-strand de-duplication, with strand calls, licence source and notes |
| `scripts/merge_screen.py` | De-duplication and screening decisions; regenerates the records, `prisma.md`, `included-excluded.md` and `sensitivity.md` (stdlib, no network) |
| `excluded-by-licence-preliminary.superseded.md` | Preliminary licence-excluded list from S1 and S3, superseded by `included-excluded.md` |
| `candidates/dtap-bench.md` | DTap-Bench sample read, convertibility, and the injection-observability **limitation** |
| `candidates/agentdojo-format-shortlist.md` | Phase 10c: verification of the 28 AgentDojo-format candidates (licence, pins, census, overlap, profile needs) |
| `candidates/phase10e-candidates.md` | Phase 10e: verification of the other 66 pending sources: cards of the 15 newly included sources, ranked recommendation, decisions D-140..D-148 (user-approved 2026-10-12) |
| `data/V10e-verification/` | Phase 10e log, every query and call (metadata and downloads), raw-response manifest, hashes of the staged files |
| `records-merged.pre-10e.superseded.jsonl`, `.csv` | The merged records as they stood before phase 10e (superseded, kept) |
| `data/S1-code/` | Code-platform search: query log (279 queries), 248 screened records with licences, forks, dependents, CSV |
| `data/S3-data/` | Research-data repository search: search log, 156 screened records, scripts |
| `data/S2-literature/` | Literature search: search log (27 database queries, 13 site-restricted web searches), 3,904 records with screening decisions and licences, summary, scripts |
| `data/raw-manifest.sha256` | sha256 of every raw API response kept outside the repository |

**Searches.**
- S1 covers code platforms: GitHub, GitLab, Codeberg and Hugging Face.
- S2 covers the literature: Semantic Scholar (keyword and AgentDojo forward citations), OpenAlex, arXiv, and
  site-restricted web searches for DBLP, ACL Anthology and Papers with Code.
- S3 covers research-data repositories: Zenodo, Hugging Face, DataCite, Figshare, Dryad, OSF, Software Heritage and
  Kaggle.

**Raw responses.** The raw responses and API caches (about 60 MB) stay in `~/.agentprov/migration-work/syssearch/` and are verified
by `data/raw-manifest.sha256`. They belong in the manuscript's data deposit, not in Git.

**Status (2026-10-12).** Final screening done on 2026-10-11: 756 distinct sources, 8 included at screening (the six
converted sources, DTap-Bench and DRIFT), 94 pending verification, 654 excluded. **Phase 10c then verified the 28
AgentDojo-format candidates from their bytes** (`candidates/agentdojo-format-shortlist.md`, decisions D-90..D-96): 25
are included with census counts and 3 excluded. **Phase 10e verified the other 66 pending sources on 2026-10-12**
(`candidates/phase10e-candidates.md`, log in `data/V10e-verification/`, decisions D-140..D-148 approved by the user): 15 are
included (78,001 counted runs) and 51 excluded. The tables now show **48 included, 0 pending, 708 excluded**. New
convertible sources are reported to the user before any is added to the framework.
