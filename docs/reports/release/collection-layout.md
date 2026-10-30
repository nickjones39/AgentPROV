# Zenodo collection layout for the combined release (U-10)

Date: 2026-10-29, Mac Studio. Branch `claude/reverent-blackwell-cc6b30` (base `4870173b`). Brief:
`~/.agentprov/handoff/release-prep-v0.1.0.md`, item 1. Class 0: a report; no code, corpus or deposit changed.

**Nothing was deposited, uploaded, packaged or published, and Zenodo was not contacted.** The corpora under
`~/.agentprov/corpora/` were only read (file sizes, `corpus.json`, a byte sample per stage for the compression
estimate). The scratch script and its JSON output are listed in section 8.

## Your decisions, in one list (each with my recommendation)

**Approved (the user, 2026-10-29, in the release-preparation window: "i approve your recommendation"): every
recommendation below, recorded as D-941.** Outward steps stay the user's to run.

| # | Decision | Recommendation |
|---|---|---|
| L-1 | **Grouping rule** for the part records | **A:** one record per licence class and harness family, split so that no record has more than about 70 files (table 2). 15 part records. B (one record per class, with a file-limit increase from Zenodo) and C (one record per corpus) are in section 3 |
| L-2 | **ControlArena persistent** (est. 40 GB compressed, 60 archives): its own record | Yes. If the real deposit comes out above 50 GB, ask Zenodo for a quota increase for this one record. A corpus cannot be split across deposits |
| L-3 | **Copyleft corpora:** one record each (gate, SENTRY, aiAuthZ, bookkeeper, llm-lock) | Yes, as D-94's one-corpus-per-source rule suggests. aiAuthZ and SENTRY could share a record only if their restriction texts were the same, and they are not (finding F-2) |
| L-4 | **Community** | Create one Zenodo community, for example `agentprov` (you create it in the web UI; the helper only requests inclusion, `--community`, D-870). Every part record, the umbrella and the software record request it |
| L-5 | **Umbrella record:** what it holds | **Index-only**, with a small class-0 builder change (`package --index`, section 5). Until that exists the umbrella must hold a corpus (D-880), and the smallest choice, `mandate-agentdojo-eval` (MIT, 10 files), would make the umbrella MIT and give Mandate two homes |
| L-6 | **Software record** (AgentPROV v0.1.0 + the D-911 building-commit snapshots) | A separate record, created by hand in the web UI as a draft (the helper only takes `package --deposit` directories). **Do not** switch on Zenodo's GitHub integration for the public repository: it publishes a record automatically on every GitHub release (section 6) |
| L-7 | **Cross-links** | Members `isPartOf` the umbrella, the umbrella `hasPart` each member (D-870's `--cross-link`); every corpus record `isSupplementTo` the software record and `isDerivedFrom` its sources' DOIs or repositories (already written by `release.toml` `[[related]]`); the software record `isSupplementedBy` the umbrella |
| L-8 | **Order and the limits trial** | Confirm the 100-file and 50 GB limits in the sandbox with one large synthetic deposit before the production drafts (they are documented values, never tested; D-800). Then: part drafts → umbrella draft → `--cross-link` → software draft → you publish |

Findings to route (not mine to fix): F-1 duplicate corpus ids among the wave-2 trees, F-2 two wordings of the AGPL
restriction, F-3 `GPL-3.0` (a deprecated SPDX id) on llm-lock (section 7).

## 1. Constraints (from the code and the decisions)

* **One licence class per deposit and per record.** `package --deposit` refuses mixed classes (D-42,
  `release.refused.mixed_licence_classes`) and never mixes a `-nc` class (D-25). The uploader refuses a deposit with more
  than one class and maps only the SPDX ids in `LICENCE_IDS` (`zenodo/src/agentprov_zenodo/draft.py`). A class is
  `(derived SPDX id, sorted restriction texts)` (`release.metadata.licence_class`), so two corpora with the same SPDX id
  but different restriction wording are different classes.
* **Copyleft sources stay one corpus per source** (D-94), each under its source licence (no relicensing, D-25).
* **Record limits** (`MAX_FILES = 100`, `MAX_TOTAL_BYTES = MAX_FILE_BYTES = 50 * 10**9`): taken from Zenodo's
  documentation, never tested (D-800).
* **Files per deposit** = the archives + one datasheet copy per corpus + `README.md`, `CHANGELOG.md`,
  `DEPOSIT-MANIFEST.json` and `deposit-metadata.json`. Each corpus has at least 5 archives (meta, raw, aer, one SEM and
  one PROV series; `release/builder.py` `_plan`), so **a corpus costs at least 6 files** and a record holds at most
  about 15 corpora.
* **No archive mixes corpora,** and a corpus never spans deposits. An archive stays below 2^31 − 1 bytes and 65,535
  members (no ZIP64) and is split only on shard boundaries.
* **Versioning.** A later version of one corpus is a `newversion` of the record that holds it, which inherits every
  file of the record (D-790: the helper never deletes; you remove inherited files in the web UI). The more corpora a
  record holds, the more inherited files a new version of one of them drags along. This argues for small, coherent
  records.

## 2. The proposal (L-1, option A)

Sizes are estimates from the trees on 2026-10-29 at about 10:00 (method in section 8). Wave-2 trees are still
`.partial`; `dtap-bench-w2b` and `mcphunt-w2b` were still importing, so `dtap-bench` uses the `w2` tree's size.
`est. GB` is the compressed estimate; `tree GB` is the uncompressed bytes (the builder's archive bound).

| Record | Licence class | Corpora | Archives | Files | est. GB | tree GB | Executions |
|---|---|---|---:|---:|---:|---:|---:|
| R1 AgentDojo and AgentDyn reference runs | MIT | `mandate-agentdojo-eval`, `agentdojo-upstream-2024-06`, `agentdojo-upstream-head`, `rope`, `agentdyn-a`, `agentdyn` (b), `agentdyn` (c) | 47 | 58 | 3.9 | 41.0 | 113,663 |
| R2 AgentDojo-format studies I | MIT | `ceferisbarov-agentdojo`, `craibench-agentdojo`, `dca-agentdojo`, `drift`, `drift1-agentdojo`, `glitch-agentdojo`, `hilarytorn-trajectory-poisoning`, `kavach-agentdojo` | 43 | 55 | 1.2 | 11.9 | 43,480 |
| R3 AgentDojo-format studies II | MIT | `kongminos-agentdojo`, `linyxus-agentdojo`, `melon-agentdojo`, `memo-ozdincer-agentdojo`, `menelaus29-ipi-multidomain`, `mohameduk-agentdojo`, `shreeyavarma-llm-safety` | 36 | 47 | 0.9 | 8.9 | 30,159 |
| R4 Inspect and OpenHands studies | MIT | `atia-benchmark`, `whistlebench`, `openagentsafety` | 18 | 25 | 3.5 | 14.0 | 10,883 |
| R5 ControlArena persistent | MIT | `controlarena-persistent` | 60 | 65 | 39.6 | 116.2 | 5,742 |
| R6 Apache-2.0 corpora | Apache-2.0 | `agentops-bench`, `dtap-bench`, `geryon-agentdojo`, `interbolt-agentdojo`, `tacit-agentdojo`, `yockcheng-prompt-injection-harness` | 51 | 61 | 4.7 | 50.4 | 78,622 |
| R7 CC BY, AgentDojo-format | CC-BY-4.0 | `adprov-v1-release`, `ast-survey-agentdojo`, `authority-caps-agentdojo`, `ipi-defenses-agentdojo`, `seagent-agentdojo` | 29 | 38 | 1.6 | 13.6 | 48,180 |
| R8 CC BY, other harnesses | CC-BY-4.0 | `autogen-guard-placement`, `code-agent-misalignment`, `credleak-p15b`, `mcphunt`, `redcode-exec-openhands`, `redcode-exec-qwencode`, `what-surrounds` | 40 | 51 | 1.9 | 19.0 | 39,777 |
| R9 AgentHarm survey | CC-BY-4.0 + AgentHarm clause | `ast-survey-agentharm` | 5 | 10 | 0.04 | 0.3 | 1,055 |
| R10 AgentHarm-derived studies | MIT + AgentHarm clause | `fragfuse-agentharm`, `kexin-xu-01-agentharm` | 10 | 16 | 0.3 | 1.8 | 4,544 |
| R11 aiAuthZ | AGPL-3.0-only + its clause | `aiauthz-agentdojo` | 5 | 10 | 0.003 | 0.03 | 174 |
| R12 SENTRY | AGPL-3.0-only + its clause | `sentry-agentdojo` | 5 | 10 | 0.02 | 0.2 | 674 |
| R13 gate | AGPL-3.0-only + its clause | `gate-agentdojo` | 5 | 10 | 0.1 | 0.9 | 3,870 |
| R14 bookkeeper | GPL-3.0-or-later + its clause | `bookkeeper-agentdojo` | 5 | 10 | 0.01 | 0.1 | 570 |
| R15 llm-lock | GPL-3.0 (see F-3) | `llm-lock-agentdojo` | 11 | 16 | 1.8 | 16.6 | 53,307 |
| **Parts** | | **52 trees** | **370** | | **≈ 59.5** | **≈ 384** | **≈ 434,700** |
| U Umbrella (index) | CC-BY-4.0 | none (index, datasheets, collection README) | 0 | ≈ 55 | < 0.1 | | |
| S Software | MIT | AgentPROV v0.1.0 source + desktop bundles + building-commit snapshots | | ≈ 25 | ≈ 1.5 | | |

How the rows were chosen:
* **By licence class first** (required), **then by harness family** (AgentDojo format; Inspect, OpenHands and the other
  dialects), so each record is a unit a reader can describe in one sentence.
* **MIT is too big for one record**: 26 corpora, 204 archives, about 230 files. It is split into the reference runs
  (round 1 and AgentDyn), two halves of the third-party AgentDojo-format studies (alphabetical), the other harnesses,
  and ControlArena alone (it is two thirds of the collection's bytes).
* **Headroom.** The largest record has 65 files. Archive counts grow when a stage crosses a 2 GiB boundary, so a
  record planned near 100 files could fail at deposit time; the plan keeps every record below about 70.
* **CC BY** (13 corpora, 93 files) is split by family for the same reason.
* **AgentHarm-derived corpora** cannot join R9: their SPDX id is MIT, R9's is CC-BY-4.0.

## 3. Alternatives to L-1

| Option | Records | For | Against |
|---|---:|---|---|
| **A (recommended):** class × family, ≤ ~70 files | 15 + U + S | every record within the documented limits with headroom; coherent units; a corpus version touches a small record | 17 DOIs to curate; the split of the MIT studies into two halves is arbitrary |
| **B:** one record per class | 10 + U + S | fewest records | the MIT record needs about 230 files and about 50 GB (a file-limit increase from Zenodo, not something the tool can test first); a new version of one MIT corpus inherits 200+ files |
| **C:** one record per corpus | 52 + U + S | the cleanest versioning and citation (one DOI per corpus) | 54 drafts, 54 typed confirmations (D-790 has no batch mode), 52 cross-links; much more web-UI review before Publish |

A hybrid of A and C is possible later: a corpus that needs frequent new versions can move into a record of its own at
its next version (its old version stays citable where it was).

## 4. Collection layer (L-4, L-7)

* **Community.** One community collects every record of the release. You create it (web UI) and curate the inclusion
  requests; the uploader sends `communities: [{"identifier": SLUG}]` with `--community SLUG` (D-870) and the GUI keeps
  the slug as `zenodo.communities` (D-880).
* **Umbrella.** A CC-BY-4.0 record with the collection README and `COLLECTION-INDEX.json`: one row per part record
  (reserved DOI, licence class, corpora), and per corpus its version, content digest and root digest, so anyone can
  check a downloaded corpus against a published digest (D-39, D-641). It also carries each corpus's datasheet and a
  pointer to the software record. The index needs the parts' reserved DOIs, which D-870's receipts record (G-1 done).
* **Relations** (DataCite vocabulary, all in the helper's `ZENODO_RELATIONS`):

| From | Relation | To | Written by |
|---|---|---|---|
| each part | `isPartOf` | umbrella | `zenodo_draft.py --cross-link` (D-870) |
| umbrella | `hasPart` | each part | `--cross-link` |
| each part | `isSupplementTo` | software record | `release.toml` `[[related]]` |
| each part | `isDerivedFrom` | each source's DOI or repository | `release.toml` `[[related]]` (`corpus_related`) |
| software record | `isSupplementedBy` | umbrella | web UI (the software draft is made by hand, L-6) |
| umbrella | `isSupplementTo` | the paper, once it has a DOI | web UI, after acceptance |

No sibling links between parts: they are linked through the umbrella (the zenodo-helper-gaps design).

## 5. The umbrella's content (L-5)

`package --deposit` needs at least one corpus archive, and the uploader only takes such directories (D-880 left the
question open). Options:

1. **Index-only deposit (recommended).** A class-0 change in `agentprov.release` (outside every stage scope): `package
   --index RECEIPT...` builds a deposit directory with the README, `COLLECTION-INDEX.json`, the datasheets and a
   `DEPOSIT-MANIFEST.json` of kind `index`, from the part drafts' receipts and the sealed corpora; the uploader accepts
   that kind (no archive, no corpus verify, the index's digests checked against the corpora instead). About half a day
   with tests. Decision number reserved when built.
2. **An umbrella that holds a small corpus** (works today): `mandate-agentdojo-eval` alone. The umbrella would be MIT,
   and Mandate would be both in R1 and in the umbrella (two DOIs for one corpus), or R1 would lose it.
3. **A hand-made umbrella** in the web UI (no tool): the index is a file you upload. It loses the closed-world and
   digest checks the uploader runs before any request.

## 6. The software record (L-6)

The software record holds what D-911 and the v0.1.0 plan (`docs/reports/release/v0.1.0-plan.md`) name: the v0.1.0
source archive and sdist/wheels, the desktop bundles, `SHA256SUMS`, and the building-commit snapshots with
`BUILDING-COMMITS.json` (`docs/reports/release/building-commit-snapshots.md`; about 25 MB per commit, about 11 commits
for round 1 and wave 2, so about 0.3 GB). It is a new concept DOI (D-5: never a version of AgentDojo-PROV's
`10.5281/zenodo.20692312`). An optional restricted-access file is the full `git bundle` of the development
repository (D-911).

**Zenodo's GitHub integration** creates **and publishes** a record for every GitHub release of a repository it watches.
That would publish without your Publish click, so it must stay off for `nickjones39/AgentPROV` (and for
`agentprov-framework`). The software record is made as a draft in the web UI and published by you.

## 7. Findings for the wave-2 pre-release session (not changed here)

* **F-1 duplicate corpus ids.** `agentdyn-b-w2` and `agentdyn-c-w2` both record `corpus_id` `agentdyn`; so do
  `mcphunt-w2` and `mcphunt-w2b` (`mcphunt`) and `dtap-bench-w2` and `-w2b`. One deposit cannot hold two corpora with one
  id, and the umbrella index is keyed by it. The table assumes `w2b` supersedes `w2` and counts both AgentDyn trees in
  R1; the wave-2 session decides which trees seal and under which ids.
* **F-2 two AGPL restriction texts.** `aiauthz-agentdojo` and `sentry-agentdojo` carry the restriction starting
  "AGPL-3.0: a corpus holding these logs…", `gate-agentdojo` the same sentence starting "AGPL-3.0-only:". With one record
  per copyleft corpus (L-3) this does not matter for Zenodo; it is a profile wording nit (changing it is a profile bump).
* **F-3 `GPL-3.0`.** `llm-lock-agentdojo`'s profile records SPDX `GPL-3.0`, the deprecated alias of `GPL-3.0-only`. The
  uploader maps it to `gpl-3.0-only` (D-800), so the deposit works; the datasheet shows the deprecated id. The licence
  text has no version choice (THIRD_PARTY_NOTICES.md), so `GPL-3.0-only` is the reading the uploader already takes.

## 8. Method and scratch

* `inventory.py` (session scratchpad), run through main's queue (`--class import --cpu 2`): for every tree except the
  three never-seal `rg1` trees and the `.withheld` directories, it reads `corpus.json`, finds each source profile by its
  recorded sha256 among `src/agentprov/adapters/*/profiles/**` and reads its `[licence]` table; it walks the tree and
  plans the archives with the deposit builder's own `_stage_of` and `_member_bound` (uncompressed bound, a 41-byte
  prefix); it compresses a deterministic sample of up to 400 files per stage with DEFLATE level 6 and extrapolates.
  Output: `inventory.json` (counts, sizes, ratios, licence fields; no content).
* The compressed estimate is a sample ratio: ControlArena's raw stage (52 GB, sampled ratio 0.56) dominates its 40 GB,
  so R5's size is the least certain number here. The real sizes come from `package --deposit`.
* Licence classes for wave 2 assume `[licence] derived = "inherit"` (the source SPDX id and restrictions). Checked on
  2026-10-29 against the 48 `corpus-spec.toml` files on the wave-2 pre-release branch (`claude/vibrant-darwin-c3315f`,
  read only): every one inherits. A spec with a user-decided derived licence would change its row.

## 9. The sandbox trial before any production draft (L-8, D-949): your steps

Everything below runs in your own terminal, on `sandbox.zenodo.org` only. Nothing publishes; delete the drafts in the
web UI afterwards. Report the ticks of the script's checklist back to a session.

1. **Token and parts.** Follow the user guide, chapter 5, "Sandbox trial checklist", steps 1–3: a sandbox account and a
   `deposit:write` token (`read -rs ZENODO_SANDBOX_TOKEN && export ZENODO_SANDBOX_TOKEN`), then seal the demo corpus
   and build its deposit draft (`agentprov package --deposit`). Note its root digest.
2. **A second part, copyleft.** Copy the demo spec, give it another `corpus_id` (for example `demo-agentdojo-gpl`) and
   `[licence] derived = "GPL-3.0-only"` with a decided-by line, seal a second copy of the demo working corpus with it,
   run the release scan, and build its own deposit draft. Its datasheet must then stay out of the index (D-949).
3. **A `release.toml` for the index:** title, `description_preamble`, keywords and the creator
   (`name = "Jones, Nicholas"`, `orcid = "0009-0000-2264-9490"`, `affiliation = "Torrens University Australia"`).
4. **Run the trial** (it drafts both parts, builds the index, drafts it, checks that a cross-link without the first
   part is refused, then cross-links twice):

   ```bash
   tools/zenodo_collection_trial.sh COMMUNITY release.toml ~/trial/index ~/trial/part-mit=sha256:<root-mit> ~/trial/part-gpl=sha256:<root-gpl> --corpora ~/trial/corpora/demo ~/trial/corpora/demo-gpl
   ```

5. **The file limit (optional, your call).** The 100-file limit can only be confirmed with a part near it. The demo
   corpus is too small to reach it; a copy of a sealed round-1 corpus (for example `mandate-agentdojo-eval`, MIT, 1,617
   files) built with a small `--max-archive-bytes` reaches about 95 files. That uploads real (MIT) corpus data to a
   private sandbox draft, which you delete afterwards. The 50 GB limit is not practical to trial; ControlArena (R5) is
   the one record near it, and a quota request is the fallback (L-2).
6. **Then** the production order of L-8: part drafts → `package --index` → index draft → `--cross-link`, each step at
   your terminal, and you publish.
