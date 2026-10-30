# Phase 10e verification log

Status: record of the verification as run on 2026-10-12 (UTC 00:32 to 01:25). Session: phase 10e (branch
`phase-10e-verify`). It verifies the 66 sources that were `pending-verification` after phase 10c. Outcomes are in
`../../records-merged.jsonl` (each record's note starts with `Verified in phase 10e [was pending: ...]`) and
`../../included-excluded.md` section 7. Cards and the ranked recommendation are in `../../candidates/phase10e-candidates.md`.

## 1. Approvals (user, in chat, 2026-10-12)

| Step | Approval | Scope |
|---|---|---|
| Metadata reads | yes ("Approve all") | GitHub REST through the authenticated `gh` CLI (repository metadata, commits, recursive trees, LICENSE and README at the pinned commit), Hugging Face API (dataset info, revision, file tree, card), Zenodo API (record and version metadata, file lists, zip-preview member listings), arXiv HTML pages (generated versus executed questions) |
| Sample downloads | yes ("Approve all", about 510 MB) | the files listed in section 4, staged under `~/.agentprov/staging/10e/`, read in memory, no LFS smudge, no extraction to disk |
| Reading for tool-less executions | yes: EX-NOLOG | executions without tool use fail IN-1 (protocol section 6; decision D-140) |
| memo-ozdincer header reads | yes | first 4 KB of each results container at the pinned commit (HTTP range) |
| Decisions D-141 to D-148 | yes (D-143 and D-147 first, then the rest) | as written in `../../candidates/phase10e-candidates.md` section 5 |

No terms of service, gate or cookie banner was accepted. The gated `cx-cmu/agent_trajectories` was assessed from its
public card only.

## 2. Calls

Every call is one line in `V10e-calls-metadata.jsonl` (GitHub API, HTTP metadata) or `V10e-calls-downloads.jsonl`
(whole-file downloads and HTTP range reads): UTC time, kind, target, status, bytes, sha256 of the response body, and the
source id. The response bodies of metadata calls are kept outside Git in `~/.agentprov/migration-work/phase10e/raw/`,
named by their sha256 (`V10e-raw-manifest.txt`: name and size of each). Local paths are written with `~`.

| Kind | Calls | Hosts | First / last (UTC) |
|---|---:|---|---|
| github-api | 247 | api.github.com | 00:32 / 00:49 |
| http (metadata, docs, papers, zip previews) | 295 | huggingface.co, zenodo.org, arxiv.org | 00:32 / 01:25 |
| download (whole files) | 466 | raw.githubusercontent.com, huggingface.co, zenodo.org | 00:55 / 01:17 |
| range (zip central directories, members, headers) | 1,366 | raw.githubusercontent.com, huggingface.co, zenodo.org | 01:09 / 01:20 |

Bytes: 490.2 MB whole-file downloads, 38.5 MB range reads. Errors, all handled: 320 HTTP 416 on range reads of
`.eval` files smaller than the 64 KB tail request (re-read whole, in memory); 16 HTTP 400 from the Zenodo
`/versions` endpoint (version families re-read through the search API with `allversions=true`); GitHub 404 for the
`license` endpoint of `theconsciouslab-ai/llm-agent-security` (no LICENSE file; the README states MIT) and for
`YeranG30/llm-agent-security-research` (the code repository named by Zenodo 18703256 is not public); one GitHub 422
from a mistyped tree SHA (repeated with the correct commit). One MRT transcript was downloaded twice because of a
file-name length error on the first attempt.

## 3. Queries and readings by source

Pass 1 (all 66): pin (default-branch head commit, HF revision or Zenodo record), licence at the pin (LICENSE path,
sha256, first line; card licence; deposit licence), README at the pin, full file tree (GitHub trees API, sub-tree walk
when truncated: `firewall-agentic-networks`, `memo-ozdincer/agentdojo`, and the upstream AgentDojo tree at `089ed468`
for blob comparison), Zenodo file lists and zip previews. Then, per source, documentation reads (data READMEs, NOTICE,
methodology docs, SCHEMA/DATASHEET, archive manifests), papers where the generated-versus-executed question needed them
(arXiv 2601.22136 StepShield, 2604.02022 ATBench, 2604.07223 TraceSafe), and the sample reads of section 4. The
evidence for each decision is in the record's `runs_basis`, `licence_source` and `notes`.

## 4. Downloads and range reads

Staged files and their sha256 are listed in `V10e-staged-files.sha256` (466 files). Whole archives:

| Source | File | Bytes | sha256 (first 16) |
|---|---|---:|---|
| Zenodo 20404563 | RESULTS_raw.tar.zst | 207,950,011 | f7186010db235cbf (matches the record description) |
| Zenodo 20198985 | Benchmarks_Results (1).zip | 48,841,799 | ecc414c810264b65 |
| Zenodo 19875693 | agentops-bench-v1.0-pilot-traces.tar.gz | 14,819,650 | e185bfd037fa9fa5 |
| Zenodo 22737462 | p15b-run-data-v3-2026-09-13.zip | 11,060,394 | 7e5f7e40b86abfda |
| Zenodo 23168099 | trajectories_OH-sonnet_S1.zip, trajectories_Qwen-qwen3coder.zip | 10,207,154; 9,402,535 | ef8ecfc0c1c5e6b7; 2fd0cada13db9064 |
| Zenodo 22137939 | dspy-security-bench-v0.19.0.zip | 9,048,364 | b47c293b4ae074a3 |
| Zenodo 18703256 | ipi_research_evidence_data.zip | 8,271,473 | 5531fa64736bdc52 |
| Zenodo 21944598 | prompt-injection-study.zip | 6,354,708 | 08e60afd5ba0c0c0 |
| Zenodo 23025259 | autogen-guard-placement-data-code-v1.0.zip | 4,978,620 | af2f519347c9554b |
| Zenodo 23235225 | dataset.zip | 4,623,260 | b7a2d203e66abef4 |
| Zenodo 22674365 | exposure-before-success-v1.0.1.zip | 2,169,556 | b8baf933ee31addd |

Smaller files: one to three samples each for OpenAgentSafety, MRT (one SHADE-Arena and one CUA transcript), MCPHunt,
ConVerse (JSON and text log), agent-attack-atlas, tool-output-spoofing-lab, memo-ozdincer, consciouslab, adapti-guard,
seal and whistlebench; all run files of agent-firewall (12), logjack (60) and yassin agentshield (122); all `.eval`
files of kexin-xu-01/agentharm (68) and fragfuse_agentharm (168); the two loose control-arena `.eval` logs. Range
reads: zip central directories of 184 whistlebench, 5 ATIA, and the Zenodo 22895043, 23218779 and 23168099 archives;
three MASTYF members, one SEAgent member, one ATIA sample and header; the central directories of the three
control-arena split zips (across their 256 MB parts); the first 4 KB of 172 memo-ozdincer results containers.

Secret-like strings were counted, never printed (`secrets_scan.py`): Zenodo 22737462 (planted canaries) 17,479
OpenAI-like, 1,355 AWS-like and 1,354 Anthropic-like hits; Zenodo 22137939 2 OpenAI-like and 1 private-key header;
Zenodo 23025259 2 OpenAI-like; the other archives none.

## 5. Incident

While streaming `RESULTS_raw.tar.zst` (Zenodo 20404563) in memory, a census script wrote 73 member copies (`_sample_*`)
to disk in `~/.agentprov/staging/10e/zenodo_20404563/`, against the rule that archives are never extracted to disk.
They were this session's own copies of single members, not source data; they were removed at once and the archive was
left unchanged (`~/.agentprov/migration-work/phase10e/incidents.log`). All later reads stayed in memory.

## 6. Scripts

Census and fetch scripts are outside Git in `~/.agentprov/migration-work/phase10e/scripts/` (stdlib; untrusted data read
with `python3.14 -I`). sha256 at the end of the session:

```
7855310449031b153549939b770326273a64889f3146aa48446c38c1055e4872  fetch.py
564b191eae415844b205dd7fcc72f2b4486921f04e4378e7c7fc264463ad926c  dl.py
8dc7311332e54dc9ee2a7d1e6abf17235d07e1c5fa3d135bb4af294ba30c41db  pass1.py
eeb01a27d794df3bc3070c575ee257680694527c49fe46b8ad684bbc345af156  batch_dl.py
5d7e54f2df649424b004d0fce70018182cc89b01e6b82166f8143841f5a67264  eval_counts.py
0ac5b641840d8ab80f262a1f325b6bae243a77bb9592cef21b1cd151cd47d8f5  peek.py
67123b0ddafe8ebcf821249c9e679e61eb41d133e990d9dfa044be7185750d5f  secrets_scan.py
7dfc34e0a60f5943107d61ce0d3105805519af3703cb8162a1da52b7219cb476  zpreview.py
fc4428339d8691477693068f089adb0284f6832a1d893db183993f2403945693  zparse.py
5799eff99560a291b6b44b7be7fa70d841211b696369e47c93ff2a3f198bf9e3  subtree.py
aee7f98dbfcfd95b2c1a45bca634c5e297fbe978a4fdfd35d61e7ca9a969c1f6  paper.py
220874529fa7086ee3ba59c00aa97d87d57daee9bf2310a47414462e29a6fa65  readfile.py
2e8b597068f959b91109d6cb7258dab4dfd892ee764d00b2cdce060375ecfcc6  hfdoc.py
32e12411bea76a1ec5d22851d76990702442c1652797c7dd6f9f8ea42808c943  extra.py
95daec7acd42182b2b67a8dff5b14ef70256732c7480bcc2e1c8624d9db94a2f  ghview.py
```

Census outputs (pass-1 records, trees, eval counts, container headers, Zenodo versions) are in
`~/.agentprov/migration-work/phase10e/census/`.

## 7. Leads found during verification (not screened)

The search is closed, so these are recorded, not added to the PRISMA flow (decision D-148, user-approved 2026-10-12):
`antgroup/Agent3Sigma-Stage` and `antgroup/Agent3Sigma-Canary` (originals of 711 normalized trajectories in
`chenjing-2024/agent-trajectory-attribution`); `Open-Agent-Safety/OpenAgentSafety` (maintained copy of OpenAgentSafety);
the HF dataset `idacy/control-arena-persistent-state-eval-vast-backup-20260423-archives` (earlier control-arena archive);
SABER's own logs (from phase 10c).
