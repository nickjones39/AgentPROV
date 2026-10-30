# Systematic source search: justification of the converted sources

Status: 2026-10-11. The sources AgentPROV already converts were screened with the same criteria as every other
record (`eligibility-criteria.md`; D-25). This file states, for each of them, why it meets the criteria, citing the
search records and the source cards. Record ids: the merged id (`records-merged.jsonl`) and the strand record ids
(S1 `data/S1-code/S1-records.jsonl`, S2 `data/S2-literature/S2-records.jsonl`, S3 `data/S3-data/S3-records.jsonl`).
Facts about content (counts, formats, models) come from the verified source cards in `docs/architecture/I_matrix.md`
(section I.1.2), which cite the investigation notes. Licence bases are quoted verbatim from those cards.

Common to all six: each releases per-execution agent logs (IN-1) of a prompt-injection evaluation (IN-2), in a format
an existing adapter family reads (IN-3), under a licence that permits redistributing derived data (IN-4), at a pinned
commit or DOI version (IN-5). None is a mirror (EX-DUP) and all exceed 100 distinct runs (EX-SIZE-1). Together they
hold 121,611 distinct runs with no execution shared between them (I_matrix section I.2).

| Source | Merged id | Runs | Licence | Adapter family |
|---|---|---|---|---|
| AgentDojo upstream (`head` and `2024-06`) | `gh:ethz-spylab/agentdojo` | 40,738 | MIT | `agentdojo` |
| AgentDyn | `gh:safo-lab/agentdyn` | 47,723 | MIT | `agentdojo` |
| AgentDojo-PROV (release) | `gh:nickjones39/agentdojo-prov` | 17,664 | CC-BY-4.0 (data), MIT (code) | `adprov` |
| ROPE (with the AutoDojo slice) | `gh:xhowenma/rope` | 10,791 | MIT | `agentdojo` |
| Agent Security Tools Survey | `gh:forever-codingnoob/agent-security-tools-survey` | 4,299 | CC-BY-4.0 (AgentHarm part: MIT + use clause) | `agentdojo` + `inspect` |
| Mandate-AgentDojo-Eval | `gh:jwilliamsc/mandate-agentdojo-eval` | 396 | MIT | `agentdojo` |

## 1. AgentDojo upstream

- **Records.** S1 `known-agentdojo-upstream`; S2 `arxiv:2406.13352` (the benchmark paper) and `zenodo:17458493`;
  S3 `ZEN-17458493` (v0.1.35), `ZEN-12528189` (v0.1.7) and `SWH-pkg.go.dev-agentdojo`. Found by all three strands
  (S1 by repository and code search).
- **Licence (IN-4).** "Code: MIT (© 2024 Debenedetti et al.). Raw data: `runs/` is covered by the repository MIT
  licence; no separate data licence; Zenodo records declare `mit-license`" (I_matrix card 1, C03). The datasheet
  records the basis as "MIT by repository; data licence not separately stated". This is the repository-level licence
  that LIC rule 2 accepts.
- **Runs.** 40,738 distinct executions: the 36,679 logs at `head` (`089ed468`) plus the 4,059 `2024-06` executions
  (`c274885`) that are no longer at `head` (I_matrix I.1.1). 207 `claude-3-opus` logs carry outcomes but no
  messages and are reported as outcome-only records, not executions.
- **Pinning (IN-5).** Commits `089ed468` and `c274885`; Zenodo concept `10.5281/zenodo.12528188` (36 versions).
- **Contribution.** The reference benchmark of the family and the largest set of closed-model runs: 29 pipeline
  directories (OpenAI, Anthropic, Google and Cohere models, Llama 3 and 3.3, Meta-SecAlign, and 11,765 local-model
  logs); 15 attacks plus benign runs; defences in the pipeline names (tool filter, prompt-injection detector,
  spotlighting with delimiting, repeated user prompt); four suites (workspace, travel, banking, slack); two log
  generations (`v0.k11`, `v1.k14`). It is also the owner of the bytes mirrored by NIST AgentDojo-Inspect (excluded
  EX-DUP) and by the survey's Zenodo zip.

## 2. AgentDyn

- **Records.** S1 `known-agentdyn`; S2 `arxiv:2602.03117` (the paper URL `leolee99/AgentDyn` redirects to
  `SaFo-Lab/AgentDyn`). The Hugging Face dataset `agentdyn-dataset/agentdyn` (S3) holds task definitions only and has
  no licence, so it is a separate, excluded record.
- **Licence.** "Repository MIT whose only copyright line is the AgentDojo authors'. The AgentDyn authors' own
  contributions (logs, suites) are not separately licensed, so read this as 'MIT as declared by the repository; not
  legally settled'" (card 5, C03). A repository-level licence that covers the data counts (LIC 2).
- **Runs.** 47,723 logs at `5353cf76`: variant A 38,281 (the supported part), B 5,184 and C 4,258 (partial).
  Variant D (949 logs) is owned by DRIFT and not counted here.
- **Pinning.** Commit `5353cf7615b1`.
- **Contribution.** New, more dynamic suites (shopping, github, dailylife) and the widest defence comparison in the
  set: 8 base models x 9 configurations, CaMeL, Meta-SecAlign 70B and 8B, Progent and integrated DRIFT; attacks
  `important_instructions` (41,118), `direct` (291) and benign runs (6,314); four schema variants of the AgentDojo
  format, including DRIFT's re-keyed logs.

## 3. ROPE, with the AutoDojo slice

- **Records.** S1 `known-rope`; S2 `arxiv:2608.27496` ("Our code and logs are available at" the repository). AutoDojo
  itself (S1 `known-autodojo`, S2 `arxiv:2606.15057`) releases no logs and is excluded (EX-NOLOG); its only released
  executions are the 2,847 AutoDojo-attack runs inside ROPE, which are counted here.
- **Licence.** "MIT (© 2026 Ma, Xiao, Yeoh, Zhang, Vorobeychik); no separate data licence" (card 7, C03).
- **Runs.** 10,791 logs at `64495e16`: main 7,871, ablation 1,240, router 1,680; 2,847 of them use AutoDojo attacks.
- **Pinning.** Commit `64495e16e640`.
- **Contribution.** A routed origin-policy defence present in every arm, router and ablation variants, and three
  attack sources in one release: `important_instructions` (6,436), AutoDojo-optimised payloads (2,847) and AgentLAB
  long-horizon payloads (760), plus 748 clean runs; models gpt-4o-mini, gpt-4o, gemini-2.5-flash and qwen3-235b. It
  is the only released source of AutoDojo executions.

## 4. Agent Security Tools Survey (AgentDojo runs and AgentHarm)

- **Records.** S1 `known-agent-security-tools-survey` and `zenodo-22140262`; S2 `zenodo:22140262`; S3 `ZEN-22135957`
  (v1.0.0) and `ZEN-22140262` (v1.0.1). Found by all three strands.
- **Licence.** "CC-BY-4.0 (repository and Zenodo). AgentHarm task data: 'MIT License with an additional clause' (use
  only to improve AI safety and security), which any AgentHarm-derived corpus MUST carry in `licences.restrictions`"
  (card 11, C03). The use clause still permits redistribution, so it does not exclude (LIC 3); the AgentHarm part
  goes into the separate restricted-use corpus `ast-survey-agentharm` (U-05).
- **Runs.** 4,299: 3,243 AgentDojo runs (3 models x (949 + 97 + 35)) and 1,056 AgentHarm samples in 6 Inspect logs.
  The 1,200 ASB result rows are planned and not counted. The 36,679 upstream logs re-packaged in the Zenodo zip are a
  mirror of AgentDojo upstream and are not selected.
- **Pinning.** Commit `89c4db2c9497`; Zenodo `10.5281/zenodo.22140262`.
- **Contribution.** New executions on AgentDojo `089ed468` with three local open models (Ollama), and the only
  Inspect `.eval` source among the converted corpora (AgentHarm: direct harmful requests, with model and tool
  events), which exercises the `inspect` family on real data.

## 5. Mandate-AgentDojo-Eval

- **Records.** S1 `known-mandate` only (found by repository search). S2 and S3 did not find it: it has no paper and
  no deposit.
- **Licence.** "MIT '© 2026 Mandate Labs'; no separate data licence; outputs subject to OpenAI terms (not assessed)"
  (card 12, C03). The publisher name is unverified (card 12, C01); the licence itself is a standard MIT grant.
- **Runs.** 396 logs at `fa62a977` (baseline, envelope and intent modes; 240 declines).
- **Pinning.** Commit `fa62a977`; corpus digest recorded in card 12.
- **Contribution.** Replicates of AgentDojo's 2024 `gpt-4o-2024-05-13` banking cells (0 byte-identical files, 0 of
  615 tool-call ids shared) under an authorisation-envelope defence that records explicit `decision` events, which
  the converted corpora use for decision provenance. It is the smallest converted source: it passes EX-SIZE-1
  (100 runs) but would be removed by a 1,000-run threshold (`sensitivity.md`).

## 6. AgentDojo-PROV (release corpus)

- **Records.** S1 `known-agentdojo-prov`; S2 `zenodo:23276620`; S3 `ZEN-23276620` (concept `10.5281/zenodo.20692312`).
  This is the author's own baseline; the search found it on GitHub and Zenodo.
- **Licence.** "Code MIT. Data CC-BY-4.0 (manifests, Zenodo)" (card 2, C03). S1 recorded the code licence, S2 and
  S3 the data licence; the data licence governs the corpus.
- **Runs.** 17,664 transcript/v1 files of the author's own live capture: 6 models x (97 benign + 3 x 949 attacked).
  The 17,664 PROV graphs beside them, and the converted legacy tree, are derived data and are not counted.
- **Pinning.** Framework commit `579a908`; Zenodo version DOIs (v2.2 `10.5281/zenodo.21052314`, v2.3
  `10.5281/zenodo.23276620`).
- **Contribution.** Six models that appear in no other source (gemini-2.5-flash, llama-3.3-70b-instruct,
  deepseek-chat, gpt-5-nano, qwen-2.5-72b-instruct, glm-4.6); attacks `direct`, `important_instructions` and
  `injecagent`; and the only converted format with per-tool UTC start and end times and configured model parameters
  (`adprov.transcript_v1`), read by the `adprov` family. It also anchors the frozen compatibility oracle.

## 7. Included candidates that are not yet converted

Two further sources meet the criteria on verified evidence and are included as candidates (details in their records
and cards):

- **DTap-Bench** (`hf:ai-secure/dtap-bench-agent-trajectories`; S2 `hf-dataset:AI-Secure/DTap-Bench-Agent-Trajectories`,
  S3 `HF-AI-Secure/DTap-Bench-Agent-Trajectories`). Apache-2.0 in both dataset cards; 67,808 trajectory files at
  `836caf2f` from a full census; four agent frameworks and seven models; new `dtap` family (phase 10b, D-26). Its
  limitation (tool-description injections often not observable) is in `candidates/dtap-bench.md`.
- **DRIFT** (`gh:safo-lab/drift`; S1 `known-drift`, S2 `arxiv:2506.12104`). MIT from commit `6fd3df4`; 1,569 runs at
  `head`; read by the `agentdojo` family as dialect `drift.k18` (registry status partial).

## 8. Known sources that the criteria exclude

For completeness, the known sources that are not converted, with their codes (all in `included-excluded.md`): NIST
AgentDojo-Inspect (EX-DUP of AgentDojo upstream: 21,999 byte-identical inherited logs, no own executions); AutoDojo,
MiDojo, ADI, STAC and the AgentHarm benchmark release (EX-NOLOG: no executions released, outcome-only rows, scenario
records or definitions only); CIAware-Bench (EX-LIC-1: no licence on the records or the gated data).
