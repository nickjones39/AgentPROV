# Systematic source search: protocol

Status: record of the protocol as it was run on 2026-10-11, with the verification of the pending sources in phase 10c
(2026-10-11) and phase 10e (2026-10-12). It was written after the searches and describes what was done; it is not a
pre-registration. It belongs to the manuscript appendix on how the converted corpora's sources
were selected (decision D-25). Counts are in `prisma.md`, every screened source is in `included-excluded.md` and
`records-merged.jsonl`, and the criteria are in `eligibility-criteria.md`.

## 1. Questions

1. Which public releases contain per-execution logs of LLM agents from agent-security or agent-safety evaluations
   that AgentPROV can convert to W3C PROV, and under which licence?
2. Which forks, derivative projects and deposits in the AgentDojo ecosystem release runs beyond the sources already
   known?
3. Do the sources AgentPROV already converts meet the same criteria? (Answered in `justification.md`.)

## 2. Strands and sources searched

Three independent searches (strands) ran on the same day. Each strand produced its own records under `data/`.

| Strand | Sources searched | What was looked for |
|---|---|---|
| S1 code platforms | GitHub (REST, GraphQL, code search, repository search, dependency-graph page), GitLab, Codeberg, Hugging Face (datasets API), Zenodo (records mentioning AgentDojo) | (1) every fork of `ethz-spylab/agentdojo`, to depth 2, compared with upstream by commit and blob SHA; (2) dependents and repositories that import or mention AgentDojo, tree-screened for run files; (3) other agent-security benchmarks by name and topic; (4) the same on the other hosts; (5) a licence audit of every record (LICENSE, README, dataset card) |
| S2 literature | Semantic Scholar (forward citations of AgentDojo, arXiv:2406.13352, and keyword search), OpenAlex (citations, title/abstract and full-text search), arXiv export API, OpenReview, Hugging Face papers; site-restricted web searches for DBLP, ACL Anthology, Papers with Code and OpenReview; supplementary location searches on Zenodo and Hugging Face datasets | papers that release, or point to, per-run agent logs; their data or code locations; the licence of each released artefact |
| S3 research-data repositories | Zenodo, Hugging Face Hub, DataCite (cross-repository index), Figshare, Dryad, OSF, Software Heritage, Kaggle; Mendeley Data and Papers with Code were tried | deposits and datasets with per-run agent logs, and confirmation of the known deposits |

## 3. Query sets

The exact query strings, endpoints, UTC times and result counts are logged, not repeated here:

- S1: `data/S1-code/S1-search-log.md` and its machine-readable twin `data/S1-code/S1-queries.jsonl` (279 queries and
  calls, steps 1 to 5); forks in `S1-forks.jsonl` (243), dependents in `S1-dependents.jsonl` (3,192).
- S2: `data/S2-literature/S2-search-log.md` (27 database queries, 13 site-restricted web searches, 8 location
  searches) and `data/S2-literature/S2-summary.md`; the scripts under `data/S2-literature/scripts/`.
- S3: `data/S3-data/S3-search-log.md` (296 queries: Zenodo 56, Hugging Face 111, DataCite 19, Figshare, Dryad, OSF
  and Software Heritage 85, Kaggle 25) and `data/S3-data/S3-summary.md`; the scripts under `data/S3-data/scripts/`.
- The raw API responses (about 60 MB) stay outside Git in `~/.agentprov/migration-work/syssearch/` and are verified
  by `data/raw-manifest.sha256`.

## 4. Dates

All searches ran on 2026-10-11 (UTC): S1 from 07:01 to about 08:02 (the licence audit ran at 08:02), S2 from 07:01 to
about 09:00, S3 from 07:01 to about 07:50. The cross-strand de-duplication and the final screening recorded here were
done on the same day, from the recorded evidence only, with no network access. The DTap-Bench candidate card
(`candidates/dtap-bench.md`) adds a user-approved sample read and a full census from the same day. Phase 10c verified
the AgentDojo-format candidates on 2026-10-11. Phase 10e verified the other 66 pending sources on 2026-10-12 (UTC 00:32
to 01:25; `data/V10e-verification/V10e-log.md`).

## 5. Screening stages

1. **Identification** (per strand). The queries in section 3.
2. **Screening on title/abstract or listing** (per strand, with the strand's own rules, stated in its log). S1
   compared forks with upstream and tree-screened repositories for AgentDojo-shaped run files, Inspect `.eval` files
   and log-like directories, checking novelty by blob SHA against upstream and the known sources. S2 screened titles
   and abstracts, then retrieved arXiv HTML or Zenodo records and inspected the linked repositories and datasets. S3
   filtered pooled hits by keyword and read the metadata of about 200 records.
3. **Full assessment by the strand.** Each strand wrote one record per retained item, with its licence and a call
   (S1: 248 records; S2: 3,904 records, 1,474 assessed in full; S3: 156 records).
4. **Final screening (this record).** Records that point to a released artefact (a repository, dataset or deposit)
   are *source candidates*. S2 papers that released no artefact are counted, not merged. The candidates of the three
   strands were de-duplicated (section 7), and every distinct source was assessed against the criteria in their
   stated order, with one decision and the first applicable exclusion code. The calls of every strand are kept beside
   the decision (`strand_calls`), so a reader can see where the final decision departs from a strand's call. The
   decisions are encoded in `scripts/merge_screen.py`, which regenerates `records-merged.jsonl`, `records-merged.csv`,
   `prisma.md`, `included-excluded.md` and `sensitivity.md` from the strand records.
5. **Verification** (after this record). AgentDojo-format candidates were verified by the phase-10c session
   (licence, pinned clone, census, overlap; `candidates/agentdojo-format-shortlist.md`). The other 66 pending sources
   were verified by the phase-10e session (`candidates/phase10e-candidates.md`): licence read at a pin, the pin
   recorded, runs counted from file trees, zip central directories, archive manifests and container headers, and
   user-approved sample reads of one to three files per source for the format (all run files where a count needed
   them). Every call is logged in `data/V10e-verification/`. The decisions are encoded in `scripts/merge_screen.py`
   (block `phase 10e`); each verified record's note starts with `Verified in phase 10e [was pending: ...]`. No source
   remains pending. New convertible sources are reported to the user before any is added to the framework.

## 6. Criteria and how they were applied

The criteria are `eligibility-criteria.md` (IN-1 to IN-5; EX-LIC-1, EX-LIC-2, then EX-NOLOG, EX-SCOPE, EX-FMT,
EX-ACCESS, EX-DUP, EX-PIN, then EX-SIZE-1 and EX-SIZE-2), with decisions D-25 (licence) and D-26 (DTap-Bench).
Applying them needed the following readings, recorded here so that they can be checked:

- **Order.** The first applicable code is reported even when another criterion also applies; the other codes are
  kept in `other_applicable_codes` (for example a no-licence repository with fewer than 100 runs is EX-LIC-1, also
  EX-SIZE-1). A licence that could not be determined does not exclude; the next criterion is applied.
- **Licence.** A repository-level licence covers the data (LIC 2). `none` means no licence anywhere: S1 audited
  LICENSE, README and dataset cards; S2 read LICENSE files, cards and README text; for Zenodo, Figshare, OSF and
  Kaggle the licence is a metadata field. A Hugging Face dataset whose only evidence is a missing licence tag, with
  the card text not checked, is `unknown` (LIC 1), unless the strand recorded that it has no card. Hugging Face
  `other` tags are `unknown`. NoDerivatives licences, evaluation-only licences, BUSL and fair-use declarations are
  EX-LIC-2 (no redistribution of derived data). AgentHarm's MIT licence with a use clause permits redistribution
  (LIC 3). Copyleft and non-commercial licences are included in their own corpora (LIC 5).
- **Run logs (IN-1).** Synthetic or generated trajectories that are not executions of an agent fail IN-1
  (EX-NOLOG). Where the strands disagree on this, the source is pending (AgentDrift, ATBench). Detector outputs,
  monitor labels, aggregate results, task definitions, test fixtures and example files are EX-NOLOG. A strand that
  did not confirm logs is not a contrary finding when another strand found them.
- **Scope (IN-2).** Agent security and agent safety are read as harmful or unauthorised behaviour of the agent:
  prompt injection, harmful tool use, misuse, sabotage, misalignment towards harmful actions, AI control and
  monitoring, and contextual privacy. Out of scope: general agentic tasks (coding, web, GUI, customer service),
  capability evaluations including offensive cyber and CTF solving, reliability and error propagation, reward
  hacking and specification gaming, and AI-welfare studies. Borderline calls say so in their note.
- **Counting runs.** Runs are distinct executions. A file count from a listing is not a run count and is reported as
  `files`; size criteria are applied only to run counts (exact counts, a census, a count stated by the paper or the
  deposit metadata, or AgentDojo-shaped files not byte-identical to known sources). A source that passes every other
  criterion and has only a file count is pending. Inspect `.eval` file counts are lower bounds on samples.
- **Included versus pending.** `included` is used for sources whose eligibility rests on verified evidence: the six
  sources AgentPROV already converts, DTap-Bench (full census) and DRIFT (verified source card). At screening, every
  other source that passed the criteria on listing-level evidence was `pending-verification`, in one of five
  categories: phase 10c (AgentDojo format), strand conflict, licence unresolved, access, listing only. Phases 10c and
  10e resolved all of them.
- **Readings added in phase 10e** (decisions D-140 to D-143 and D-147, approved by the user on 2026-10-12):
  - *Executions without tool use* (chat-only probes, single text responses, tool-less pipelines, conversations between
    agents without tools, harnesses that script the tool call so that the model only writes the answer) fail IN-1 and
    are EX-NOLOG (D-140).
  - *Outcome-only records* (labels, a final response, hashes, tool names) are EX-NOLOG, as phase 10c coded saber.
    *Partial trajectories* (tool calls without arguments, tool results or inputs, or with truncated results) are
    EX-FMT (D-141). EX-FMT was first used here.
  - *Counting* (D-142): Inspect samples from zip central directories; runs in containers from their headers; a verified
    lower bound passes a threshold when it is at least 10% above it (shown `>=N`, upper bounds `<=N`); mock-model
    samples are not counted; a run re-released byte-identically in another repository counts once; a normalized
    re-release of another source's runs counts only executions not in an included source.
  - *Mixed sources* (D-143, approved): a source whose faithful or in-scope part alone passes the size rule is
    included and counted on that part (Zenodo 20404563: structured gemini-cli rollouts; AgentOps-Bench: the
    prompt-injection condition and the safety tasks).
  - *Scope* (D-147, approved): unsanctioned whistleblowing by tool-using agents is unauthorised agent action, so
    in scope (whistlebench).
- **Mirrors.** A byte-identical mirror is EX-DUP with a pointer to the original; a mirror of an excluded original takes
  the original's code (`duplicate_of` is set either way).
- **Pinning.** Every eligible source can be pinned by commit, DOI version or Hugging Face revision, so EX-PIN was not
  used. At screening no source was excluded under EX-FMT as its first code; phase 10e used it for five partial
  trajectories (D-141).

## 7. De-duplication

Records were merged when they identify the same artefact:

1. **Canonical identifiers.** GitHub `owner/repo` (lower case), Hugging Face dataset id, Zenodo record id, Figshare
   id, OSF node, Kaggle dataset, other DOIs. A record's primary URL (S2: its first data or code location) gives its
   identifier, so several papers that point to one repository become one source.
2. **Alias table** (`KEY_ALIAS` in the script). Zenodo version families are merged under their concept record (for
   example the authority-caps deposits 22973266, 22996368 and 23138310 under 22973265), the GitHub-Zenodo software
   deposits and the Software Heritage origin of AgentDojo under the GitHub repository, repository redirects
   (`leolee99/AgentDyn` to `SaFo-Lab/AgentDyn`), and the same artefact in two repositories (Zenodo and Figshare,
   Zenodo and IEEE DataPort).
3. **Mirrors and copies.** Byte-identical mirrors under another owner stay separate records with EX-DUP (or the
   original's code). Run files that are byte-identical to a known source were already removed by S1's blob-SHA check
   before counting (for example 35,875 of MELON's 36,819 AgentDojo-shaped files).

This merged 873 source candidates into 756 distinct sources. Execution-level de-duplication **across** different
repositories was not done beyond S1's blob check: counts are per repository, and near-identical counts are flagged as
possible copies.

## 8. Outputs

| File | Content |
|---|---|
| `records-merged.jsonl`, `records-merged.csv` | one row per distinct source: identifiers, strands and strand record ids, type, relation to AgentDojo, licence and its source, format, adapter, runs and basis, models, decision, code, pending category, corpus licence class, strand calls, conflict, notes |
| `prisma.md` | counts per stage per strand and merged, with a flow diagram |
| `included-excluded.md` | the appendix table of every distinct source; good sources excluded only by licence; large sets; conflicts; new phase-10c candidates |
| `sensitivity.md` | included sources and runs under no threshold, 100, 1,000 and 5,000 runs |
| `justification.md` | why each source AgentPROV already converts meets the criteria |
| `scripts/merge_screen.py` | the de-duplication and screening decisions, including the phase-10c and phase-10e verification outcomes; regenerates the four files above |
| `candidates/agentdojo-format-shortlist.md`, `candidates/phase10e-candidates.md` | verification cards (licence, pin, census, adapter needs, overlap, limitations) and ranked recommendations |
| `data/V10e-verification/` | phase-10e verification log, every call, raw-response manifest, hashes of staged files |
| `records-merged.pre-10e.superseded.jsonl`, `.csv` | the records as they stood before phase 10e (kept, superseded) |

## 9. Limitations

- **Rate limits.** GitHub's primary rate limit stopped S1 once (about 07:20 UTC); queries were retried. The shared
  GitHub API quota was exhausted during S2, so S2 read repository trees from the public HTML pages (top level and up
  to four log-like sub-directories, two levels deep): its evidence is file and directory names. Semantic Scholar
  returned HTTP 429, so four keyword queries kept only the first 200 hits by relevance. DBLP answered with an anti-bot
  page and was covered only by site-restricted web search; it was not bypassed.
- **Caps per query.** GitHub search returns at most 1,000 results per query; the `"from agentdojo"` code search (9,056
  hits) was split by file size, and some size buckets still exceeded the cap. Hugging Face searches were capped at 100
  (S1) or 200 (S3) results, and file listings at 100,000 entries. Zenodo returned 25 records per page and at most 100
  (300 for four queries) per query, and unquoted Zenodo queries use OR semantics. OpenReview returned the first 1,000
  notes per query. Web searches returned about the top 10 results. Low-ranked hits were therefore not seen.
- **Unretrievable pages.** 321 non-arXiv papers could not be assessed in full (publisher pages not retrieved). 12
  Zenodo records returned 410 or an error. Gated or private Hugging Face datasets were not opened (CIAware-Bench data,
  SafeArena, `cx-cmu/agent_trajectories`, `WhitzardAgent/CyberAgentTrace`, `changdae/...`). Zenodo zip-container
  listings failed for most archives, and Figshare does not list zip contents. The GitHub dependency graph showed about
  49 of about 60 dependents. One fork returned 404 on compare. SWE-bench and OSWorld trajectories hosted outside
  GitHub were not located.
- **Formats and counts inferred from listings.** S2 and S3 opened no data file; S1 read only a handful of small
  samples to identify schemas. AgentDojo format is inferred from path patterns, and most run counts are estimates or
  file counts. The 94 pending sources exist because of this. Counts are not de-duplicated across repositories.
  Phase 10c later verified the 28 AgentDojo-format candidates from their bytes: the path pattern undercounted 17 of
  them (it misses injection-task pre-pass files and custom file names), and one (saber) turned out to hold outcome
  records only. Phase 10e verified the other 66: listing estimates were often wrong in both directions (OpenAgentSafety
  1,560 runs, not about 2,400; three large datasets turned out to be generated, not executed; many log-like directories
  held outcome records or tool-less responses). The tables carry the verified counts; no source remains pending.
- **Verification depth (phase 10e).** Formats were judged from one to three sample files per source (all run files
  where a count needed them). Counts from container headers, archive manifests and zip central directories were
  checked against one fully read file per source. Two counts are bounds (`>=802` control-arena logs, `>=1,271` MRT
  runs). Earlier versions of versioned deposits were listed but not checked for runs absent from the pinned version.
  One script wrote 73 archive members to disk by mistake; they were removed at once (`data/V10e-verification/`,
  section 5). Leads found during verification were recorded, not screened (D-148).
- **Single screener.** Each strand was screened by one automated agent session, and the final screening by one
  session, with no second independent screener and no agreement statistic; the same holds for each verification
  phase (10c, 10e). Scope readings (section 6) and borderline calls are written down so that they can be re-checked.
- **Criteria set post hoc.** The size thresholds (100 and 1,000 runs) were set after the known sources had been
  identified, and so were the licence rules, although they were fixed before this screening. `sensitivity.md` reports
  the outcome under other thresholds.
- **Search focus.** Most code-platform queries start from AgentDojo; other ecosystems were reached through generic
  terms and benchmark names, so non-AgentDojo sources are probably under-represented.
- **Snapshot.** Repositories and deposits change. Every decision refers to the state seen on 2026-10-11; included
  sources are pinned at verification.
- **Licence evidence.** Licence calls rest on LICENSE files, README text, cards and deposit metadata as recorded by
  the strands; a licence stated elsewhere (for example in a paper) was not sought. Model-provider terms on
  redistributing model outputs were not assessed (LIC 6).
- **Untrusted data.** All third-party text was treated as data. Several records carry promotional or instruction-like
  text; none was followed. Names and notes in the outputs are reduced to printable ASCII.
