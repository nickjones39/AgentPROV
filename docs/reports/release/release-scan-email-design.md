# An e-mail detector for `tools/release_scan.py` (design, decision D-810)

Status: **approved with conditions (2026-10-23) and built**; the sections below are the design as proposed, and the conditions
that changed it are at the end (section 8). Branch `release-scan-email`, base `main` `1b0a6e9c`; continued 2026-10-28 on
`claude/release-scan-email-d810-402999` (base `main` `57b4a4df`): the persona files (section 12), the not-in-AER pass and
its recommendation (section 11, approved and built: section 14) and the datasheet drafts (section 13, open).
Origin: finding 1 of the Zenodo sandbox trial (`zenodo-sandbox-trial.md`): a fictional AgentDojo persona address sat in a
deposit and the release scan said nothing, because it has no e-mail rule.

## 1. What it matches

A new native rule `email-address`, in the same machinery as the D-600 secret shapes (`SECRET_SHAPES`): a cheap literal
(`@`) is found, then a bounded pattern is matched there. It runs over stored files and over the decoded members of
archives (D-491), so every layer a corpus holds is covered.

* Shape: one or more of `[A-Za-z0-9._%+-]` immediately before `@`, then a domain of labels `[A-Za-z0-9-]+` separated by
  dots, ending in an alphabetic TLD of 2 to 24 letters that does not continue into another token. A version string
  (`pkg@1.2.3`, `inspect_ai@0.3.247.dev69`) does not match, because its last label is numeric or alphanumeric; neither
  does a decorator (`@pytest.mark...`) or an npm scope (`@scope/name`), which have no local part.
* The finding records `detector`, rule, path, line and fingerprint (`<path>:email-address:<line>`) like every other
  finding: never the address, the local part or the domain. The scan document's path-scan version goes from `4` to `5`
  (`PATH_SCAN_VERSION`), so the builder refuses scan documents made before the rule existed. No deposit exists, so none
  is affected.
* Not covered, and said so in the tool's docstring: addresses written with JSON `\uXXXX` escapes, obfuscated forms
  (`name at host dot com`), internationalised domains, and addresses split across a line break.

## 2. Triage: how a persona is told from a real address

Today triage is a human decision per fingerprint and per sealed root digest (D-42). A fingerprint names a line, and the
counts below show why that cannot work for e-mail: one persona address in a benchmark appears in thousands of lines (raw
objects, the AER that quotes them, the PROV that quotes the AER). Per-fingerprint review of 10^5 lines is not review.

Three layers, none of them an allowlist of "anything that looks fake":

1. **Reserved domains, in the tool.** An address whose domain is `example.com`, `example.org`, `example.net`, or ends in
   `.example`, `.test`, `.invalid` or `.localhost` (RFC 2606 and 6761) cannot be a real mailbox. The scan records it as
   `false-positive` with the reason "reserved domain (RFC 2606)". The list is closed and in the code. (My prototype
   counts below also put `test.com` in this class. It is a registered domain and would **not** be in the real rule; those
   addresses would go to layer 3.)
2. **The corpus's persona list, in its spec.** A new optional table `[scan]` in `corpora/<id>/corpus-spec.toml`:

   ```toml
   [scan]
   personas_basis = "AgentDojo v1 workspace/travel/banking/slack suites at c274885: environment YAML and tasks"
   persona_addresses = ["<local>@<domain>", ...]      # exact, lower-case, one per fictional person
   persona_domains   = [ {domain = "...", reason = "..."} ]   # optional; see below
   ```

   An address matches only when the whole address, lower-cased, equals an entry (never a pattern, never a suffix match),
   or its domain equals a `persona_domains` entry. Such a finding is recorded by the scan as `synthetic-benchmark`, with
   the reason "persona list of corpus <id>, spec sha256 <digest>". Anything else stays **untriaged**, and untriaged
   findings stop the builder as they do now. A real address is never `synthetic-benchmark` unless a person put that exact
   address in the list while reviewing the spec; `real` still needs withholding (G.9.5).
   * Why the spec and not the source profile: the corpus spec is already hashed into the sealed manifest
     (`files.spec`, and the copy `rules/corpus-spec.toml`), so the list that triaged the scan is bound to the root digest
     and the scan reads it from the sealed tree after checking its digest, as the builder does for the profile copy. A
     `[scan]` table in the *profile* would be a profile change: `adapters/profiles.py` is in the `aer` stage's import
     closure (`AER_CLOSURE`), so it moves every family's AER code digest (class 1), and it changes the profile digest
     of every profile that gains it (D-31 bump, regeneration). One corpus has exactly one source and one profile, so the
     spec is the same scope. If you prefer the profile anyway, that is the cost.
   * Domain entries are the risky part: an address at a real company's domain would pass. So they are off by default, each
     needs a reason, and I recommend allowing none at the first review: the lists are exact addresses (sizes below).
3. **Everything else is untriaged and stops the release.** The human then decides per address, not per line: a helper
   (`tools/release_scan.py --list-addresses`, counts and hashes only unless `--show` is given in the user's terminal)
   groups findings by distinct address so the review is of 100 to 500 addresses, not 10^5 lines.

**Evidence for the list, never "it looks fake":** each entry must be found in the benchmark's own data at the pinned
commit, not only in the model outputs. A helper `tools/scan_personas.py --corpus ... --source <pinned tree>` lists the
distinct addresses of a corpus that occur verbatim in the upstream source tree (suite YAML, task files), so a
model-invented or user-supplied address is not offered as a persona.

## 3. How many findings it would raise on the existing corpora

Counts only. A read-only prototype of the rule was run through the scan's own `path_scan` (stored files, and archive
members decoded) over the eight current stored corpora; it printed no address, wrote nothing in the corpora, and kept the
distinct addresses in memory only (as hashes for counting). Corpora used: the `rg1` ones, and `rg2` for
`ast-survey-agentdojo`. 0 archives were unreadable in any of them.

| Corpus | Findings (file, line) | Files | raw / aer / prov | Distinct addresses | of which other / freemail / reserved* | Distinct domains |
|---|---:|---:|---|---:|---|---:|
| mandate-agentdojo-eval | 0 | 0 | - | 0 | - | 0 |
| ast-survey-agentharm | 4,137 | 934 | 554 / 3,363 / 220 | 123 | 70 / 17 / 36 | 52 |
| ast-survey-agentdojo | 23,294 | 5,243 | 11,728 / 10,738 / 828 | 107 | 77 / 24 / 6 | 46 |
| adprov-v1-release | 130,405 | 29,242 | 65,648 / 60,445 / 4,312 | 278 | 169 / 75 / 34 | 60 |
| agentdojo-upstream-2024-06 | 94,357 | 23,672 | 47,983 / 42,804 / 3,570 | 122 | 90 / 20 / 12 | 54 |
| rope | 88,468 | 19,070 | 47,181 / 37,022 / 4,265 | 135 | 96 / 26 / 13 | 35 |
| agentdojo-upstream-head | 226,514 | 51,684 | 115,938 / 103,308 / 7,268 | 134 | 97 / 21 / 16 | 57 |
| agentdyn-a | 279,516 | 66,287 | 153,721 / 115,345 / 10,450 | 491 | 287 / 80 / 123 (+1 `git@` form) | 84 |

\* "reserved" in the prototype also contained `test.com`, which the real rule would not treat as reserved; "freemail" is
`gmail.com`, `outlook.com`, `hotmail.com`, `yahoo.com`, `proton.me`, `protonmail.com` and `icloud.com`. Mandate's AER files contain `@` only with no domain after it (396 files checked by hand);
nothing matches. Running time: 1 s to 204 s per corpus,
`nice`d, one process.

What this says:
* The rule fires in about 850,000 lines across the eight corpora, so a persona rule is necessary: without one the
  release scan would never be clean, and a person cannot review that many fingerprints.
* The distinct addresses are 107 to 491 per corpus, so an exact-address list per corpus is reviewable. The per-corpus
  lists overlap heavily (the AgentDojo personas recur across AgentDojo, ROPE, adprov and the surveys).
* A third of the distinct addresses are at freemail domains, so a domain rule for those is impossible: exact addresses
  only. Some of them are real-looking; the review is where a real one is found, and it is withheld (`real`) instead.
* 52 % of findings are in `raw/`, 44 % in `aer/`, 4 % in `prov/`. A withheld raw object would take its executions with
  it (H.4.5); the AER and PROV findings of a `real` address are what makes withholding costly. Nothing is withheld by this
  change.

## 4. The D-236 withholding backstop and the datasheet

* `email-address` is a native rule id, so a `[withhold]` policy may name it in `scan_rules` (credleak-style canaries).
  For such a policy the existing backstop applies unchanged: every finding of that rule must be `false-positive`, so a
  persona address (`synthetic-benchmark`) in that corpus would stop the build, which is right for a corpus where an
  address is a canary. No shipped profile names it, so no existing build changes.
* The builder trusts the scan document as today. One addition: a finding triaged by the persona rule carries
  `basis: "persona-list"` and the digest of the spec it used; the builder checks that digest against the sealed
  `files.spec` and refuses a mismatch, so a list that was not sealed with the corpus cannot triage a release.
* Datasheet: a decided statement in `corpora/datasheet-statements.toml` (like the private-key fixture and the
  home-directory ones): benchmark data holds fictional e-mail addresses (personas); they are kept verbatim; the release
  scan triages each as `synthetic-benchmark` by the corpus's persona list or as a reserved-domain false positive. The
  statement is applied to the corpora whose list is non-empty, with counts as placeholders computed from the manifest.
  No claim is made that a corpus holds no personal address; the claim is "none that the review found".

## 5. Byte class

Expected **0**: `tools/release_scan.py` (outside the package), `release/metadata.py` (the version constant and the basis
check), `corpus/spec.py` (an optional closed table; existing specs stay valid), the statements file, tests and docs. None
of these is in a stage scope today (`stage_scopes.py`: `adapters/profiles.py`, `runner`, `aer`, `prov`, `vocab`, `validate`,
`sem` and their closures). It will be proved at build by a before/after computation of every stage digest, as for D-780.
Sealed corpora change only when their spec gains a `[scan]` table and they are sealed again; no corpus is sealed today
(33 kept corpora, 0 sealed) and nothing is deposited. If the profile route is chosen instead, it is class 1.

## 6. Questions for the user

1. Persona list in the corpus spec (recommended, class 0) or in the source profile (class 1, D-31 bump)?
2. Domain entries: none at first (recommended), or allowed per entry with a reason?
3. Reserved domains triaged `false-positive` by the tool itself (recommended)?
4. Build the two helpers (`--list-addresses` and `tools/scan_personas.py`) in this branch? The second needs the pinned
   upstream trees, which are in the local fetch cache; it would run offline.

## 7. Rejected

A blanket allowlist of freemail or "fake-looking" domains (a real address at gmail.com would pass); a domain suffix or
pattern rule; triaging by the e-mail's local part (`john.doe`); auto-triage by the fixture the log came from (a log can
carry real addresses next to persona ones); one global persona list in the tool (it would hide a real address that
happens to be a persona elsewhere; the list is per corpus and sealed with it); recording the matched address in the scan
document (the scan never records a matched value).

## 8. Conditions of the user's go (2026-10-23) and what changed

1. **Digests, not addresses.** The persona list is not a list of addresses in the spec. Each entry is the digest
   `"sha256:" + hex(sha256(address))` of the ASCII lower-cased `local@domain`, with evidence (source id, pinned commit or
   DOI, the upstream file). A persona file per benchmark, shared by every spec that needs it, is referenced from the spec by
   path and sha256; sealing writes it under `rules/personas/`. Still in the corpus spec (class 0), bound by `files.spec`.
2. **Domain entries: none.** The format has no domain entry. To be revisited after the counts of the helpers, and then only
   for a domain the benchmark itself invented, with a reason and evidence, never a public mail domain.
3. **Reserved domains** are RFC 2606 / RFC 6761 names only. The count caveat in section 3 stands corrected: the prototype's
   "reserved" class contained `test.com`, which the built rule does not clear. (The checkpoint below recounts with the built
   rule.)
4. **Helpers built:** `--list-addresses` (digest, class, findings, corpora, layers; never an address) and
   `tools/scan_personas.py` (digests against upstream data, offline, `GIT_NO_LAZY_FETCH=1`).

## 9. Checkpoint: the helpers run read-only on the eight stored corpora (2026-10-23)

Run through the queue (`--class rehearsal --cpu 2`, `nice`), with the built rule and `tools/scan_personas.py`. Counts only;
no address, local part or domain was printed or stored. Upstream data is the benchmark's own tree at the pinned commit, with
run logs excluded (`runs/`, `*/results/`, `logs/`): AgentDojo at `c274885` and `089ed468` (99 and 106 distinct addresses
in 93 and 181 files) for the AgentDojo corpora; AutoDojo `aa458794` and ROPE `64495e16` as well for `rope`; AgentDyn
`5353cf76` (153 addresses in 1,496 files) and AgentDojo for `agentdyn-a`; the survey repo and AgentDojo for
`ast-survey-agentdojo`; the survey repo and `Kexin-xu-01/agentharm` `859c34f4` (137 addresses in 274 files) for
`ast-survey-agentharm`. No blob was absent and none was too large; no archive was unreadable.

"Reserved" is now the strict RFC set. "Found" is a non-reserved address whose digest occurs in an upstream file.

| Corpus | Distinct | Reserved | Found upstream | **Not found** | Not found: other / public-freemail |
|---|---:|---:|---:|---:|---|
| mandate-agentdojo-eval | 0 | 0 | 0 | 0 | - |
| ast-survey-agentharm | 123 | 36 | 48 | 39 | 38 / 1 |
| ast-survey-agentdojo | 107 | 6 | 76 | 25 | 15 / 10 |
| adprov-v1-release | 187 | 32 | 81 | 74 | 62 / 12 |
| agentdojo-upstream-2024-06 | 122 | 12 | 83 | 27 | 24 / 3 |
| rope | 135 | 13 | 94 | 28 | 22 / 6 |
| agentdojo-upstream-head | 134 | 16 | 83 | 35 | 31 / 4 |
| agentdyn-a | 491 | 121 | 35 | 335 | 266 / 69 |

The not-found group by layer: addresses (one address can be in several layers) and findings (lines).

| Corpus | Not found, addresses raw / aer / prov | Not found, findings raw / aer / prov |
|---|---|---|
| ast-survey-agentharm | 39 / 37 / 22 | 81 / 211 / 24 |
| ast-survey-agentdojo | 23 / 17 / 11 | 96 / 73 / 22 |
| adprov-v1-release | 73 / 72 / 60 | 1,171 / 1,139 / 269 |
| agentdojo-upstream-2024-06 | 27 / 27 / 21 | 372 / 369 / 128 |
| rope | 28 / 28 / 28 | 266 / 195 / 105 |
| agentdojo-upstream-head | 35 / 35 / 29 | 1,123 / 973 / 284 |
| agentdyn-a | 335 / 290 / 262 | 4,661 / 3,880 / 1,048 |

Reading it:

* Against the roughly 850,000 findings of the prototype, the **not-found group is small**: 563 address entries over seven
  corpora (the same address recurs across corpora, so fewer distinct), about 16,500 findings in `raw/`, `aer/` and
  `prov/` together. Everything else is either reserved, or an address the benchmark's own data holds (a persona).
  A persona list by exact digests is workable: at most 491 digests for one corpus, mostly shared.
* **The not-found group is the open question.** These are addresses that appear in the logs and in no upstream file:
  invented or copied by the model, supplied by a task prompt the logs hold, or present in an upstream file this check did
  not read (a different version of the benchmark; AgentHarm's HF dataset is not in the cache, only a fork's tree).
  They need a person's decision per address, either withholding (an execution or a raw object, which also removes its AER
  and PROV) or a new triage class.
  About 81 % are at invented-looking domains ("other"), 19 % at a public mail provider. 335 of them are in `agentdyn-a`,
  a corpus whose model runs invent many users.
* The prototype's distinct-address count for `adprov-v1-release` (278) was too high: it judged an address in a chunk's
  carried bytes twice, once with a cut local part. The built rule judges each `@` once (by absolute position) and gives 187.
  The other corpora were not affected (their files are smaller than a chunk).
* **File-name-shaped matches** (`icon@2x.png`) in the not-found group, counted separately by the last label being a common
  file extension or the first label having the `@Nx` shape: **0** in six corpora, and 2 addresses (25 findings) in
  `adprov-v1-release` and 2 addresses (49 findings) in `agentdyn-a`; none has the `@Nx` shape. They are noise, but few.

### Proposed fix for file-name-shaped matches (not built; the user decides it with the not-found group)

In `find_addresses`, after the pattern matches, drop a match when (a) the first domain label is `[0-9]{1,2}x` (the
`@2x`/`@3x` image-density suffix), or (b) the last label is in a small denylist of **file extensions that are not
top-level domains**: `png jpg jpeg gif svg webp bmp ico tiff json jsonl yaml yml toml ini cfg txt csv tsv html htm css xml
pdf doc docx xls xlsx ppt pptx gz tgz tar bz2 xz zst mp3 mp4 wav avi log bat exe dll ipynb lock`. Extensions that are also
country or generic TLDs (`py`, `md`, `sh`, `rs`, `so`, `cc`, `pl`, `zip`, `mov`) must **not** be on the list: a real address at
such a domain would pass unseen, and a rule that hides a real address is worse than a noisy one. Test: each denylisted
form is not a finding; each ambiguous one (`py`, `md`, `zip`) still is; a real-looking address with a denylisted extension
as a subdomain (`a@png.example.org`) still is; digest and chunk-boundary behaviour unchanged. Alternative if the user
prefers no denylist: leave the four addresses as findings and triage their lines by hand (74 fingerprints).

## 10. Second checkpoint: where the not-found addresses first appear (2026-10-23)

Run through the queue (`--class rehearsal --cpu 2`), counts only, by digest; no address, local part or domain printed. For
each execution's AER, every string of every record is searched and the **first** appearance of a not-found address is
classified by position in the conversation (message index; a tool call's arguments at its call message, its other fields
and a state change just after it; the header, actors and fixtures before the conversation):

* **benchmark-supplied input:** a message of the benchmark, the simulated user, the environment or tool runtime (a tool
  result), the attacker (an injection), a defence, or a fixture or header field;
* **model output only:** a message of the agent or of an LLM judge, or a tool call's arguments, and no earlier appearance in
  benchmark input in any execution; **mixed** (benchmark-supplied in some executions, model-only in others): none occurred;
* **not in any AER:** the address is in the raw object or the PROV only (a raw field the AER does not map).

The 4 file-name matches are excluded here (they are now `file-name` entries, below); "not found" is therefore 72 for
`adprov-v1-release` and 333 for `agentdyn-a`.

| Corpus (executions) | Benchmark-supplied: other / freemail (addr; findings) | **Model-only**: other / freemail (addr; findings) | Not in AER: other / freemail (addr; findings) |
|---|---|---|---|
| ast-survey-agentharm (1,056) | 18 (229) / 0 | 16 (70) / 1 (3) | 4 (14) / 0 |
| ast-survey-agentdojo (3,243) | 2 (6) / 2 (7) | 10 (130) / 3 (17) | 3 (15) / 5 (16) |
| adprov-v1-release (17,664) | 4 (21) / 0 | 48 (2,422) / 9 (67) | 8 (33) / 3 (11) |
| agentdojo-upstream-2024-06 (18,241) | 0 / 0 | 21 (774) / 3 (89) | 3 (6) / 0 |
| rope (10,791) | 0 / 0 | 21 (435) / 6 (104) | 1 (27) / 0 |
| agentdojo-upstream-head (36,679) | 0 / 0 | 28 (2,268) / 4 (106) | 3 (6) / 0 |
| agentdyn-a (38,281) | 5 (66) / 4 (96) | 220 (7,513) / 57 (1,175) | 39 (677) / 8 (13) |

What withholding the **model-only, public-freemail** addresses would remove (executions whose AER holds one, and the raw
objects of those executions; the closure through shared raw objects adds nothing, each primary object holds one execution;
shared `supporting` context objects are not counted):

| Corpus | Addresses | Executions | Raw objects | Of executions in the corpus |
|---|---:|---:|---:|---:|
| ast-survey-agentharm | 1 | 1 | 1 | 1 of 1,056 |
| ast-survey-agentdojo | 3 | 11 | 11 | 11 of 3,243 |
| adprov-v1-release | 9 | 8 | 8 | 8 of 17,664 |
| agentdojo-upstream-2024-06 | 3 | 10 | 10 | 10 of 18,241 |
| rope | 6 | 17 | 17 | 17 of 10,791 |
| agentdojo-upstream-head | 4 | 13 | 13 | 13 of 36,679 |
| agentdyn-a | 57 | 127 | 127 | 127 of 38,281 |
| **Total** | **83** | **187** | **187** | |

For information, model-only with an "other" domain (kept as `model-generated` under the proposed rule): 364 addresses in
1,533 executions in total (agentdyn-a 777, head 282, adprov 248, 2024-06 123, rope 69, survey-agentdojo 22, agentharm 12).

Reading it, and its limits:

* The AgentDojo-family corpora are almost entirely **model-only**: the benchmark's own personas are all in the upstream data
  (cleared as personas); what remains is what the models wrote (invented recipients, copied or mangled addresses).
* Benchmark-supplied is small, and concentrated in AgentHarm (18 addresses not in the local copy of its data, in the
  benchmark's prompts or its stub tools' output; the dataset's JSON files in the cache did not hold them, so their source
  is the benchmark's code, which the cache does not have) and the AgentDyn suites (9).
* Withholding the 83 model-only freemail addresses costs 187 executions out of about 125,000 (0.15 %), each with its raw
  object; 127 of them are `agentdyn-a`.
* The classification is by position and actor kind, from the AER only. A defence's messages count as benchmark-supplied; an
  LLM judge's as model output; an address copied from a tool result into a later message is benchmark-supplied (first
  appearance), which is the generous reading for the proposed `synthetic-benchmark` class. The "not in AER" group has no
  AER evidence at all and is not covered by the proposed rule; it needs its own decision (the raw object is the only place).
* **AgentHarm's Hugging Face dataset** (`ai-safety-institute/AgentHarm` at `e23b3fe6`) is in the local fetch cache,
  `cache/hf/.../e23b3fe6.../` (8 files: `benchmark/*.json`, `README.md`, `LICENSE`, 352 KB), not in the corpus's raw store (its
  origins are the survey repo and its members) and not in staging. It was read offline as an upstream directory
  (`scan_personas.py --upstream-dir`); it did not change the not-found count of 39. No fetch was made or is proposed.

### File-name entries (built)

The four file-name-shaped matches are now cleared by digest: a persona-file group with `class = "file-name"`, basis
`file-name`, triage `false-positive`, only for the corpus whose spec names the file, with the spec-digest check of the
builder. The two files are `corpora/personas/adprov-v1-release.file-names.personas.toml` (2 digests; extensions `txt` and
`xlsx`; found in 3 raw files of Llama-3.3 runs) and `corpora/personas/agentdyn-a.file-names.personas.toml` (2 digests;
extension `txt` twice; 4 raw files of one Llama-3.3 variant), each referenced from its corpus spec with its sha256. No
denylist of extensions exists.

## 11. Third checkpoint: where the not-in-AER addresses sit (2026-10-28)

Run through the queue (`--class rehearsal --cpu 4`), counts only, by digest; no address, local part, domain or value
printed or stored. Trees: the sealable ones (`-rg2` for `ast-survey-agentdojo`, `adprov-v1-release` and
`ast-survey-agentharm`; `-rg1` for the others). Upstream run outputs are excluded wherever they sit: every `runs/`,
`results/`, `logs/`, `res/` and `analysis/` directory (section 12). For each not-in-AER address the pass records every
finding's layer, whether the match starts right after a backslash, the nearest JSON key before it (printed only from a
fixed list of structural names, else by shape), the raw objects that hold it with their roles in `executions.jsonl`, and,
for the AER and PROV files that hold it, every decoded string or object key of every record field, **including** the
envelope fields that the origin pass skips (`src`, `evf`, `rule`, `id`, `ns`, `after`, `k`).

| Corpus | Not in AER | Escape artefact | Double-escaped (PROV `apv:args`) | Raw only, object not imported | Raw only, compressed bytes | Executions touched |
|---|---:|---:|---:|---:|---:|---:|
| ast-survey-agentharm | 4 | 2 | 0 | 0 | 2 | 2 |
| ast-survey-agentdojo | 8 | 8 | 0 | 0 | 0 | 24 |
| rope | 1 | 0 | 1 | 0 | 0 | 6 |
| agentdojo-upstream-2024-06 | 3 | 3 | 0 | 0 | 0 | 1 |
| adprov-v1-release | 11 | 5 | 6 | 0 | 0 | 5 |
| agentdojo-upstream-head | 3 | 3 | 0 | 0 | 0 | 1 |
| agentdyn-a | 47 | 9 | 1 | 37 | 0 | 121 |
| **Total** (69 distinct over the corpora) | **77** | **30** | **8** | **37** | **2** | **160** |

* **None is in an AER or PROV pointer path.** No not-in-AER address is in any AER envelope field (`src`, `evf`, `rule`,
  `id`), in an object key of any record, or in a PROV pointer attribute. The suspicion of the second checkpoint (an
  address used as a map key and quoted in a pointer) does not hold for these corpora.
* **Escape artefacts (30) and their double-escaped form (8): a scanner defect, not new addresses.** The byte-level rule
  reads a JSON escape before an address as part of its local part: `\n` followed by a name gives a local part that
  starts with `n`, `<` (`<`) one that starts with `u003c`. The digest is then that of a string no decoded record
  holds, so the origin pass, which decodes the AER, never finds it. In the 8 double-escaped cases the PROV `apv:args`
  (`adprov:args` in the compat graphs) carries the tool arguments as a JSON string inside JSON, so the escape survives one
  decoding. With the escape prefix removed, the 38 are addresses already classified: 32 `upstream-data` personas,
  4 `model-generated` and 2 `withhold`. The field kinds are message content (`content`, `text`, `body`) and tool-call
  arguments (`body`).
* **Raw only, in objects no execution indexes (37, all in `agentdyn-a`).** 40 JSON run files of AgentDyn's part-c
  variants (`*-progent`, `*-drift`), which the import stores but does not map (register `select.dialect_planned`,
  `not_imported`; 9,442 such objects in the corpus). 0 executions touched. 33 at other domains, 4 at a public mail
  provider. Field kinds: message `content` (20 addresses), tool-call arguments `recipients` (10), `sender` (9), `body`
  (5), `email`, `address`, `bcc`, `participants`, `recipient`, `response`, an `error` message, a `path`, plain text (8)
  and snake_case keys of the suites' tools (4).
* **Raw only, compressed archive bytes (2, `ast-survey-agentharm`).** Found once each in the stored bytes of two `.eval`
  archives (`agentharm/results/<cell>/<id>.eval`), in no decoded member and in no record: almost certainly chance matches
  in deflated data (a random byte stream matches the bounded shape about once in 25 MB). 0 executions touched.
* **Operator or author metadata: none.** No field kind is a run's configuration, a log header's author, a git or
  package author, an account or environment field. Every field is benchmark or model text (messages, tool arguments,
  tool results, an error message).

### Recommendation (approved by the user 2026-10-28; built, section 14)

1. **Fix the escape defect in the rule rather than withhold** (38 addresses, 160 of the touched executions, all of
   them executions whose addresses are already classified). In `find_addresses`, when the local part starts right after a
   backslash and begins with a JSON escape letter (`n`, `t`, `r`, `b`, `f`) or `u` and four hex digits, the escape is not
   part of the local part. The finding is still reported (same file, rule and line); only its digest becomes the decoded
   one, so the persona files triage it. This matters beyond the release scan: the seal-time `withhold` rule matches file
   bytes by the same function, so an execution whose withheld address only ever follows a `\n` would today stay in the
   corpus (the release scan would then stop the deposit on the unknown digest; nothing leaks, but the withholding is
   incomplete). Raise the path-scan version 5 to 6 so no scan document made before the fix is accepted, and regenerate
   the persona files (digests of escaped forms change).
2. **`agentdyn-a`'s not-imported part-c objects (37 addresses in 40 objects):** they belong to no execution of this
   corpus, so withholding by execution does not reach them. Recommended: withhold the 40 objects by object (reason
   `personal_data`; costs nothing in this corpus, 0 executions). The wider question, whether a corpus should ship
   9,442 raw objects of a part it does not import, is a finding routed to the orchestrator.
3. **The 2 compressed-byte matches:** do not judge an archive's stored bytes by the e-mail rule when the decoded scan
   read the archive (its members are judged decoded); the secret and account rules are unchanged. Alternative without a
   rule change: two `file-name`-style digest entries with a new basis.

## 12. The persona files (built, 2026-10-28)

`corpora/personas/` holds the lists of the decided classes (decisions 2 to 6), digests only (each file checked: no `@`
anywhere). `.gitignore` excluded everything under `corpora/<x>/` except the spec, card and changes, so the two file-name
lists of section 10 had never been committed; `corpora/personas/*.personas.toml` is now un-ignored.

| File | Class | Digests | Referenced by |
|---|---|---:|---|
| `agentdojo.personas.toml` | upstream-data (AgentDojo `c274885`, `089ed468`) | 83 | ast-survey-agentdojo, rope, agentdojo-upstream-2024-06, adprov-v1-release, agentdojo-upstream-head, agentdyn-a |
| `autodojo.personas.toml` | upstream-data (AutoDojo `aa458794`) | 33 | rope |
| `rope.personas.toml` | upstream-data (ROPE `64495e16`) | 94 | rope |
| `agentdyn.personas.toml` | upstream-data (AgentDyn `5353cf76`) | 35 | agentdyn-a |
| `agentharm.personas.toml` | upstream-data (fork `859c34f4`, HF dataset `e23b3fe6`) | 46 | ast-survey-agentharm |
| `<corpus>.observed.personas.toml` (7) | benchmark-input / model-generated / withhold | see below | its own corpus only |
| `<corpus>.file-names.personas.toml` (2) | file-name | 2 + 2 | adprov-v1-release, agentdyn-a |

| Corpus | benchmark-input | model-generated | withhold | Withheld executions (raw objects) |
|---|---:|---:|---:|---|
| ast-survey-agentharm | 20 | 16 | 1 | 1 of 1,056 (1) |
| ast-survey-agentdojo | 4 | 10 | 3 | 11 of 3,243 (11) |
| rope | 0 | 21 | 6 | 17 of 10,791 (17) |
| agentdojo-upstream-2024-06 | 0 | 21 | 3 | 10 of 18,241 (10) |
| adprov-v1-release | 4 | 48 | 9 | 8 of 17,664 (8) |
| agentdojo-upstream-head | 0 | 28 | 4 | 13 of 36,679 (13) |
| agentdyn-a | 9 | 220 | 57 | 127 of 38,281 (127) |
| **Total** | 37 | 364 | **83** | **187** (187) |

* **Run outputs inside upstream repositories are not benchmark data.** The exclusion of section 9 (`runs/`,
  `*/results/`, `logs/`) missed three places: ROPE's `agentlab/res/` (results), the AgentHarm fork's `analysis/`
  (Inspect eval logs) and AgentDyn's `src/agentdojo/defenses/drift/runs/`. The lists exclude every directory named
  `runs`, `results`, `logs`, `res` or `analysis` at any depth. Only AgentHarm changed: 2 digests whose only upstream
  evidence was the fork's eval logs are now `benchmark-input` (upstream-data 48 to 46, benchmark-input 18 to 20). The
  withhold class is unchanged.
* **For information:** 61 of `rope.personas.toml`'s 94 digests occur in the upstream only in files a model generated
  when the benchmark was built (AutoDojo's `variant_generation/variants/` injections and ROPE's `src/rope/scopes/`). They
  are the benchmark's published input to the agent, so `upstream-data` holds, but their author is a model.
* **Owning corpus only (decision 4) is now enforced:** sealing refuses a persona file with an observed group whose
  `corpus_id` is not the spec's (`package.refused.persona`); before, any spec could reference another corpus's list.
* The `withhold` rule of section 10 is fed from these files at sealing (`agentprov-withheld/0.4`, reason
  `personal_data`); no corpus has been sealed with them yet.

## 13. Wording for the datasheet (decided 2026-10-28 by the orchestrator on the user's instruction)

Public mail providers (`public-freemail`, the closed list in `agentprov.corpus.personas`), domain names only:
`gmail.com`, `googlemail.com`, `outlook.com`, `hotmail.com`, `live.com`, `msn.com`, `yahoo.com`, `ymail.com`, `proton.me`,
`protonmail.com`, `pm.me`, `icloud.com`, `me.com`, `mac.com`, `aol.com`, `gmx.com`, `gmx.net`, `mail.com`, `zoho.com`,
`yandex.com`, `qq.com`, `163.com`, `126.com`, `fastmail.com`, `tutanota.com` (25).

Four statements for `corpora/datasheet-statements.toml` (section `known_issues`). Decided 2026-10-28 by the orchestrator
on the user's instruction: statements 2 to 4 as drafted; statement 1 with the sentence "They are fictional personas, not
contact details." replaced, because the addresses were triaged by origin, not shown one by one to be fictional, and
upstream data can hold real contact addresses. All four pass the card lint as sealing applies it (`mode: import` front
matter; no digit outside a placeholder, the RFC numbers are left out for that reason) and the statements loader:

1. `fictional-benchmark-personas` (all seven corpora with addresses): "The benchmark invents people, and this corpus
   quotes their e-mail addresses verbatim wherever the benchmark, the agent or a tool wrote them: {{f:upstream}}
   distinct addresses occur in the benchmark's own published data at its pinned commit, and {{f:input}} more are first
   supplied in the logged runs by the benchmark's prompts, tool results, injections or defences. They belong to the
   benchmark's scenarios, not to anyone the runs involved, and were not checked one by one. The release scan triages each by its digest (the corpus's persona files, which never
   hold an address) as synthetic-benchmark; addresses at the domains reserved for documentation and testing are
   triaged as false positives."
2. `model-generated-addresses-kept` (the seven): "In {{f:executions}} executions the model under test wrote e-mail
   addresses that occur neither in the benchmark's data nor in its input ({{f:addresses}} distinct addresses, none at a
   public mail provider). They are kept verbatim, as all model text is, listed by digest in the corpus's persona file
   and triaged as model-generated. They were not reviewed one by one, and a model can reproduce an address it saw in
   training."
3. `model-freemail-addresses-withheld` (the seven): "Executions in which the model under test wrote an address at a
   public mail provider that the benchmark did not supply are withheld at sealing, because such an address may belong
   to a real third party: {{f:addresses}} distinct addresses, {{f:executions}} executions and their raw objects
   ({{f:share}} of the corpus's executions; {{f:by_suite}}; {{f:tasks}} distinct tasks). WITHHELD.json records the
   reason as personal data and lists the executions. They are withheld for what they contain, never for their outcome;
   analyses that need the full design can check the split by suite and task."
4. `uncited-raw-objects-withheld` (`agentdyn-a` only; added after the decision of section 14): "{{f:objects}} raw run
   files that the import stored but did not map to any execution (variants of a part this corpus does not import) hold
   e-mail addresses that occur in no execution's records ({{f:addresses}} distinct addresses). They are withheld at
   sealing, reason personal data; no execution is affected." Figures: objects 40, addresses 37.

Figures per corpus (statement 2 and 3; statement 1's `upstream` and `input` are the upstream-data and benchmark-input
counts of section 12). The model-generated execution counts are section 10's (the `-rg1` trees of `adprov-v1-release` and
`ast-survey-agentharm`, whose AER the `-rg2` trees keep); every figure is re-counted from the sealed corpus before the
statements are committed. **Decided format:** one row per corpus (seven rows each for statements 1 to 3, one for
statement 4), with fixed figures re-counted from each sealed corpus; no `{{v:...}}` placeholders (they would add fields
to `corpus.json`, which changes corpus bytes). The rows land in `corpora/datasheet-statements.toml` at sealing time,
not before.

| Corpus | model-generated: addresses / executions | withheld: addresses / executions / share / by suite / tasks |
|---|---|---|
| ast-survey-agentharm | 16 / 12 | 1 / 1 / 0.09 % / `inspect_evals/agentharm` 1 / 1 |
| ast-survey-agentdojo | 10 / 22 | 3 / 11 / 0.34 % / workspace 11 / 7 |
| rope | 21 / 69 | 6 / 17 / 0.16 % / dailylife 10, github 7 / 5 |
| agentdojo-upstream-2024-06 | 21 / 123 | 3 / 10 / 0.05 % / slack 1, workspace 9 / 4 |
| adprov-v1-release | 48 / 248 | 9 / 8 / 0.05 % / slack 1, travel 1, workspace 6 / 7 |
| agentdojo-upstream-head | 28 / 282 | 4 / 13 / 0.04 % / slack 3, workspace 10 / 5 |
| agentdyn-a | 220 / 777 | 57 / 127 / 0.33 % / dailylife 70, github 55, shopping 2 / 22 |

## 14. Path-scan version 6 and the regenerated lists (2026-10-28)

The user approved the three recommendations of section 11. Built (`12e3dcdc`):

* **Escapes.** `find_addresses`: a local part right after an odd run of backslashes does not begin with `n`, `t`, `r`,
  `b`, `f` or `uXXXX`; after an even run (a JSON string inside JSON) not with `n`, `t`, `r` or `uXXXX`, so a literal
  backslash followed by a name starting with `b` is read as written. A local part that would be empty without the escape
  is kept as read (still a finding). The scan, the persona helpers and the seal-time address rule share the function.
* **Archives.** `path_scan` holds each stored file's e-mail hits until the decoded scan has run, and drops them for an
  archive whose members it read (nothing left unscanned); an archive it could not read is judged by its stored bytes.
  The account, home-path and secret rules are unchanged.
* **`withhold-object`.** A persona class evidenced by the raw object's sha256 (`entries = [{address, object}]`), owned by
  one corpus. `tools/scan_origins.py` writes it for an address in no AER whose every finding is in raw objects that no
  execution indexes, and reports any other not-in-AER address. Its digests join the `withhold` digests in the one
  `address` rule, which withholds every object that holds one and the executions that cite it (here none).
* `PATH_SCAN_VERSION` 5 to 6: the builder refuses a scan document made before the change.

Regenerated through the queue (`--class rehearsal --cpu 4`), the same trees and upstream exclusions as section 12:

| Corpus | Not found (was) | upstream-data | benchmark-input | model-generated | withhold | withhold-object | Other not-in-AER |
|---|---|---:|---:|---:|---:|---:|---:|
| ast-survey-agentharm | 37 (41) | 46 | 20 | 16 | 1 | 0 | 0 |
| ast-survey-agentdojo | 17 (25) | 76 | 4 | 10 | 3 | 0 | 0 |
| rope | 27 (28) | 93 (94) | 0 | 21 | 6 | 0 | 0 |
| agentdojo-upstream-2024-06 | 24 (27) | 83 | 0 | 21 | 3 | 0 | 0 |
| adprov-v1-release | 61 (72) | 81 | 4 | 48 | 9 | 0 | 0 |
| agentdojo-upstream-head | 32 (35) | 83 | 0 | 28 | 4 | 0 | 0 |
| agentdyn-a | 323 (333) | 35 | 9 | 220 | 57 | 37 (40 objects) | 0 |

* The 38 escape artefacts are gone: each is now its decoded address, already in its class. The 2 compressed-byte matches
  are gone. `rope.personas.toml` lost one digest: an escaped form in ROPE's own upstream files is now the persona it
  quotes. The class counts and the withholding (83 addresses, 187 executions and raw objects, by suite and task as in
  section 13) are unchanged.
* `agentdyn-a`'s 37 not-imported addresses (33 at other domains, 4 at a public mail provider) are `withhold-object`;
  sealing withholds their 40 raw objects (0 executions). The wider question of shipping not-imported objects at all stays
  with the orchestrator.
