# U-06 follow-up: licence classes for the 145 unclassified fixture entries (D-946)

Date: 2026-10-29. Decision: D-946 (follows D-943, U-06 decided). Byte class 0.

D-943 makes real third-party fixtures of class `permissive` public and keeps every other real fixture private,
including the ones with no `licence_class`. It also says the 145 unclassified entries are classified first and then
follow their class. This report records that classification. It lists paths and licence facts only, never fixture
content. The `SOURCE.json` files were read and edited by a script that printed only origin metadata (container digest,
repository, revision, member label, method, licence field). The fixture data files were not opened.

## Method

For each source the evidence is, in this order:

1. the source profile's `[licence]` table (`spdx`, `data_licence`, `policy`, `restrictions`, `basis`);
2. the K.4.2 table (`docs/architecture/K_testing.md`);
3. the pre-check report and its research record (`docs/reports/precheck/<source>.md`,
   `docs/reports/precheck/data/<source>/research.json`, field `licence`);
4. the entry's own origin fields, which tie it to the pinned origin the licence covers (container sha256 equal to the
   profile's pin, or repository and revision equal to the profile's commit).

An entry is classed only when all four agree. An entry with insufficient evidence would stay unclassified and be
listed as undecided.

## Result

| Source (`tests/fixtures/`) | Entries | Class | `synthetic` | Pinned origin of every entry | Licence facts (evidence) |
|---|---:|---|---|---|---|
| `agentops/` | 25 | `permissive` | `false` | Zenodo 10.5281/zenodo.19875693: 13 members of `agentops-bench-v1.0-pilot-traces.tar.gz` (sha256 `e185bfd0…`), 12 of the code snapshot `kunwarshivam/agentops-bench-v1.0.zip` (`852a372d…`: 11 task YAMLs and the LICENSE) | Apache-2.0 on the record and in the snapshot's LICENSE; the pilot traces carry no separate licence (`agentops/profiles/agentops-bench-pilot.profile.toml`: `spdx = data_licence = "Apache-2.0"`, `policy = "include"`, no restrictions; `precheck/data/agentops-bench/research.json` `licence`). Notice: `tests/fixtures/LICENSES/AgentOps-Bench-Apache-2.0.txt`, itself one of the 25 entries |
| `autogen/` | 9 | `permissive` | `false` | Zenodo 10.5281/zenodo.23025259 v1.0, one zip (sha256 `af2f5193…`, the profile's pin): the three licence texts, `config.json`, the InjecAgent cases, the phase-0 capture and the phase-6 tool arm's three JSONL files | Data CC-BY-4.0 (LICENSE-DATA), code MIT (LICENSE), AgentDojo templates and InjecAgent cases MIT (LICENSE-THIRD-PARTY) (`autogen/profiles/autogen-guard-placement.profile.toml`, `policy = "include"`, no restrictions; `precheck/data/autogen-guard-placement/research.json`). Notices: the deposit's own `LICENSE`, `LICENSE-DATA` and `LICENSE-THIRD-PARTY`, committed as three of the 9 entries |
| `drift/` | 9 | `permissive` | `false` | `SaFo-Lab/DRIFT` at `6fd3df47…`, the profile's `head` pin; every entry is a blob of that tree (6 introduced at `7c7d982`, 3 at `f9ef3a3`, both still present at the pin) | MIT, LICENSE added at `6fd3df47` ("Copyright (c) 2026 Hao Li"), no separate data licence (`agentdojo/profiles/drift.profile.toml`, `policy = "include"`). K.4.2 classes DRIFT HEAD blobs `permissive` and history-only blobs `restricted`. None of the 9 is a history-only blob: the `history` pin `53dbc6c5` (`policy = "reference"`, D-279) holds no fixture |
| `mcphunt/` | 1 (one object, 11 record slices in 7 files) | `permissive` | `false` | Hugging Face `lihaonan0716/mcphunt-agent-traces` at `c4c69322…`, the profile's revision: byte slices of 7 pinned documents, each with source offset, length and sha256, inside a project-written JSON envelope (a derived fixture, not a synthetic one) | CC-BY-4.0 in the dataset card at the pin (`mcphunt/profiles/mcphunt.profile.toml`, `policy = "include"`, no restrictions; `precheck/data/mcphunt/research.json`). CC BY permits adaptation with attribution. The planted canary credentials are benchmark design, not a use restriction; the slices are canary-free (phase 10m part B) |
| `memo-ozdincer/` | 3 | `permissive` | `false` | `memo-ozdincer/agentdojo` at `7c331d97…`, the profile's pin: two results files and the pin's LICENSE | MIT LICENSE at the pin (the upstream AgentDojo text), which covers `results/`; the fork adds no licence of its own (`agentdojo/profiles/memo-ozdincer-agentdojo.profile.toml`, `data_licence = "none"`, `policy = "include"`). There is no pre-check report for this source. The entry's own `licence` field and `tools/agentdojo/phase10q_fixtures.py` record the same basis. Notice: `tests/fixtures/memo-ozdincer/LICENSE` |
| `wirelog/` | 98 | `permissive` | `false` | Zenodo 10.5281/zenodo.21944598, one zip (sha256 `08e60afd…`, the profile's pin; every entry's `container_sha256` equals it): 96 members of 12 run directories under `runs_named/`, plus `results.csv` and `attacks.json` | CC-BY-4.0 on the record. LICENSE-DATA in the zip puts `runs_named/`, `results.csv`, `attacks.json` and `PAPER.md` under CC BY 4.0 and code under MIT (`wirelog/profiles/what-surrounds.profile.toml`, `policy = "include"`; `precheck/data/what-surrounds/research.json`). All 98 are deposit members, so none is synthetic. Notice: `tests/fixtures/LICENSES/WhatSurrounds-LICENSE-DATA.txt` |
| **Total** | **145** | `permissive` 145 | | | |

**Undecided: none.** Every one of the 145 entries has a pinned origin that its profile's licence covers. No profile
declares restrictions, and no source has a non-commercial or no-licence basis.

### `synthetic` added to already-classified entries

Three classified sources had no `synthetic` field. Each entry is a member of a pinned real origin, so each gets
`synthetic: false` and keeps its class:

| Source | Entries | Class (unchanged) | Origin |
|---|---:|---|---|
| `credleak/` | 11 (3 of them derived, `modified: true`, K.4.1(6)) | `permissive` | the deposit zip named by each entry's `doi` and `container_sha256` |
| `seagent/` | 10 | `permissive` | the deposit zip named by each entry's `doi` and `container_sha256` |
| `inspect/whistlebench/` | 1 | `permissive` | `legobridge/whistlebench` at `9c27637c…` |

After this change every `SOURCE.json` entry in the tree (72 files, 949 entries) records `synthetic`. Every real entry
records a class from the closed set: 931 `permissive`, 14 `restricted` (the copyleft fixtures of P-1) and
4 `restricted_use` (AgentHarm).

## Gaps the class does not close (follow-ups, not blockers for the class)

- **Licence notices for the public export.** K.4.2 asks for the licence text and copyright line of a `permissive`
  source in `tests/fixtures/LICENSES/<source>.txt`. D-943 makes each public permissive fixture go out "with its
  `SOURCE.json` and licence text". Matched by file name, no source-specific notice exists for DRIFT (the MIT text with
  "Copyright (c) 2026 Hao Li" appears only in the entries' `licence` field) or for MCPHunt (only the generic
  `LICENSES/CC-BY-4.0.txt`, without the dataset's attribution line). Both need a notice file from the pinned origin
  before the release commit. That would add a fixture file, so it is left to the D-943 export work.
- **Model-provider terms** stay "not assessed", as D-943 states. No class depends on them.
- **Snapshots of earlier building commits.** `tools/building_commit_snapshots.py` (D-942 S-4) reads each commit's own
  `SOURCE.json`. A snapshot of a commit before this one still leaves the 145 entries out, which is the conservative
  side.

## Downstream effects

- Changed: 9 `SOURCE.json` files (fixture metadata; 8,537 B in total). No fixture data file changed, and no file under
  `src/agentprov`. No stage digest scope covers `tests/fixtures/`, so no AER, SEM or PROV byte and no corpus manifest
  changes. The `tests/FIXTURES.json` caps still hold (`fixture_caps.check_tree` is clean), and no pin hashes these
  files.
- Guard: `tests/golden/test_fixture_licence_classes.py` fails when any `SOURCE.json` entry lacks a boolean
  `synthetic`, or when a real entry lacks a `licence_class` from the closed set. It also pins the 145 classifications
  above.
- Generators: `tools/agentdojo/phase10q_fixtures.py`, `tools/agentdojo/phase10f_fixtures.py` and
  `tools/credleak/build_fixtures.py` now write `licence_class` and `synthetic`, so a rebuild keeps the fields. None of
  the other five sources has a committed generator that writes its `SOURCE.json`.
