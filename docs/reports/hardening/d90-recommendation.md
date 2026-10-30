# D-90: a declared, bounded second level of extraction-free streaming (`tar.gz` inside a zip)

Date: 2026-10-12. Phase 12b. Status: **approved by the user as recommended (2026-10-12); implemented as D-57**
(`ingest/streams.py` `iter_gzip_bounded`, `ingest/archives.py` `OpenedTar`; spec G.3.5, C.3.12 note). Evidence files:
`~/.agentprov/migration-work/phase12b/d90-tar-structure-22011266.json` and `d90-names-22011266.json`, produced by the
scripts kept in the session scratchpad. They read the staged deposit in memory, without `tarfile` and without extraction.
No download.

## 1. The question

Two Zenodo deposits hold AgentDojo run logs as `tar.gz` files inside a zip (phase 10c, D-90):

| Deposit (version censused) | Runs in nested `tar.gz` | Containers | Staged locally? |
|---|---|---|---|
| 22011266 (`AgentSecurity-IPIDefenses-v4.0.zip`, 3.3 MB) | 3,211 (all of its runs) | 3 | yes |
| 22973265, version 23138310 (the 22973266 version has none) | 19,186 of 22,012 JSON | 3 (`runs_exp4`, `runs_exp5`, `runs_exp7`) | no (census only) |

These are the only runs in the candidate set with GPT-6 Luna/Sol, gpt-5.4(-mini) and claude-sonnet-4-6 under AgentDojo
defences (shortlist §4). Today `open_archive` refuses tar (`ingest.archive.format`, G.3.5: "tar refused in v0.1").

## 2. What the bytes look like (22011266, all three containers)

| | `run1_mini_pdef` | `frontier_verify` | `run2_mini_rerun` |
|---|---|---|---|
| gzip size → tar payload | 292 KB → 4.9 MB (16.4×) | 596 KB → 8.5 MB (13.9×) | 280 KB → 4.7 MB (16.7×) |
| regular files (`0`) | 845 | 1,521 | 845 |
| directories (`5`) | 346 | 618 | 346 |
| **GNU long-name headers (`L`)** | 967 | 1,450 | 802 |
| longest long name | 147 B | 134 B | 135 B |
| largest member | 16.9 KB | 46.9 KB | 31.9 KB |
| pax (`x`/`g`), links (`1`/`2`), long link (`K`), devices, sparse | 0 | 0 | 0 |
| names rejected by `logical_name` / collisions / bad header checksums | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

Every limit already in `IngestLimits` holds with a wide margin: ratio ≤ 16.7 (cap 200), member ≤ 47 KB (cap 256 MiB),
members per container ≤ 3,589 headers (cap 100,000), depth 2 (cap `max_archive_depth` = 2, so zip = 1 and `tar.gz` = 2
fit without raising a limit), names ≤ 1,024 B.

**The critical fact is the `L` headers.** The archives depend on GNU long names, and obs-G1 showed that `tarfile`
buffers a GNU LONGNAME header whatever size it declares (a 1.17 MB `.tar.gz` declaring 256 MiB reached 555 MiB RSS inside
`tarfile.next()`, before any check). A reader for these deposits therefore **must not use `tarfile`**.

## 3. Recommendation: (a), implemented as a bounded framing reader, scoped to exactly this case

Support a gzip-compressed tar **only as a member of a zip** (level 2, never top level, never nested deeper), through
a new ~200-line header parser in `ingest/archives.py`. Same guarantees as the zip path:

1. **Streaming, no extraction.** The `tar.gz` member's bytes are decompressed in bounded chunks by the existing gzip
   decoder of `ingest/streams.py` (`max_stream_bytes`, `max_ratio` over the whole stream); 512-byte headers are parsed
   by our code; a selected member's bytes go straight to `DATA` frames. Nothing reaches the disk.
2. **Header rules** (each refusal is a typed `ingest.*` code on the member or the container):
   - checksum verified on every header; octal size fields only (base-256 sizes refused); the size must fit the
     member, total and stream caps **before** any byte of the payload is read;
   - `0`/NUL regular files: gated exactly like zip members (`logical_name`, `collision_key` across the container,
     `max_member_bytes`, the running `max_total_bytes` of selected members, `max_members`);
   - `5` directories: skipped (they carry no bytes);
   - `L` GNU long name: accepted only with a declared size ≤ `max_name_bytes` (1,024), checked before the payload is
     read, and only directly before the entry it names (obs-G1 closed by construction);
   - refused: `K` long link, `x`/`g` pax (none observed; can be added later under the same bound), `1`/`2` links
     (`ingest.archive.link`), `3`/`4`/`6` devices and FIFOs, `S` sparse, any other typeflag, a header after the
     end-of-archive blocks, a truncated payload (`ingest.stream.truncated`);
   - the gzip trailer (CRC-32 and ISIZE of the whole tar) is verified at the end; a mismatch rejects the container.
3. **Provenance.** A tar member gets the existing `member` origin with `container` = sha256 of the stored `.tar.gz`
   member object, its NFC `label`, **`method` 0** and **`crc32` computed while streaming**. `aer/0.1` is frozen, and
   its `member.method` admits only {0, 8, 93}. The convention must be written down (C.3.12 note): for a tar member, 0
   means "no member-level compression inside the tar". The gzip layer belongs to the container object, and decoding it
   is part of the versioned `expand` function. Unlike zip, there is no CRC declared in the archive to check against: the
   member's integrity rests on the header checksum, the gzip trailer over the whole stream, and `rederive`
   re-expansion, which must reproduce identical member digests (AD-12). `verify --level chain` re-checks the stored
   member against its row as for zip.
4. **Release mode.** The interpreter guard (G.3.8) applies as for every archive. `tarfile` is never imported, so the
   CVE classes tied to it do not apply.
5. **Tests (phase 12b).** SEC-05/07 cases: an `L` header declaring 256 MiB refused in O(1) memory (the obs-G1 file),
   pax/links/devices/sparse refused, a ratio bomb, member and total caps at limit−1/limit/limit+1, a truncated stream,
   a bad checksum, a gzip-trailer mismatch, name collisions, a `tar.gz` at top level and at level 3 refused, and
   byte-identical members across worker counts. Plus a fuzz target for the header parser in `tests/fuzz/`.
6. **Bundle.** It changes `EXPAND_MODULES`, so it joins the phase-12b `expand` bundle (regen-batch.md). No existing
   corpus has a nested `tar.gz` (only `ast-survey-agentharm*` holds members, all zip).

**Rejected alternatives.**
- `tarfile` with checks around it: the obs-G1 buffering happens inside `tarfile.next()`, before any check could run.
- Storing the decompressed `.tar` as an intermediate raw object so that its members are truly "stored": it duplicates
  up to `max_total_bytes` per container, and the intermediate object would still need an origin kind that `aer/0.1`
  does not have.
- Top-level `tar.gz` support: no source in the candidate set needs it, and keeping it refused keeps the surface small.
- Option (b), excluding the runs as EX-FMT: it loses 22,397 runs that are the only ones with these models under
  AgentDojo defences.

## 4. Before an import (not part of this decision)

- The three 23138310 containers were censused by phase 10c but are not staged, so their header structure (in
  particular any pax or `K` headers) is unverified here. A structure scan of them needs the deposit, so it needs your
  yes for the download. The reader refuses unsupported headers with a typed code either way.
- The deposits' profiles and imports belong to the phase-10d workflow, not phase 12b.
