# `derive` / `recompute` timings and profile (phase 11, U2; 2026-10-11)

Measured on **copies** of two phase-10 working corpora (`~/.agentprov/corpora/*` untouched; copies under
`/private/tmp/u2-realdata/`, deleted afterwards), with the code of branch `phase-11-u2`. Host: MacBook Pro M2 Max,
12 cores (8 performance + 4 efficiency), 32 GB, macOS 27.0, CPython 3.14.8. The machine was **shared** with other
sessions during every run (load average 5-12), so wall times are noisy; repeated runs differ by up to 30 %.

## Q.14: zero unexplained differences on real corpora

Every run below exited 0 with `identical == selected` and 0 `changed_explained`, 0 `unexplained_change`, 0 `failed`,
0 `unverified`, 0 `index_refreshed`, 0 corpus-level differences (register, origins, members). The source copies were
checked unchanged with `testing.fs_guard` around every command. Notices: the code digests of the `aer`, `sem`, `prov`
and `validation` stages differ from those recorded at import (code changed since the phase-10 imports, and this unit
adds files under `prov/`), with every declared version equal and every output identical, i.e. refactors that pass
(H.8.4(2)).

| Corpus copy | Executions | Command (`--jobs 8`) | Wall time |
|---|---:|---|---:|
| `mandate-agentdojo-eval-p10` | 396 | `recompute --dry-run --stages sem,prov,validation` | 46.8 s |
| | | `recompute --dry-run` (full re-map from raw: `aer,sem,prov,validation`) | 59.3 s |
| | | `recompute --out NEW --stages sem,prov,validation` | 49.2 s |
| | | `recompute --out NEW` (full re-map) | 58.0 s |
| | | `recompute --out NEW2 --stages sem,prov,validation` over the previous `NEW`, reuse cache hit for all 396 | 6.4 s |
| `ast-survey-agentharm-p10` | 1,056 | `recompute --dry-run --stages sem,prov,validation` | 160.2 s |
| | | `recompute --dry-run` (full re-map: `expand,aer,sem,prov,validation`) | 176.9 s |
| | | `recompute --out NEW --stages sem,prov,validation` | 161.8 s |
| | | `recompute --out NEW` (full re-map) | 168.5 s |
| | | `recompute --out NEW2 --stages sem,prov,validation` over the previous `NEW`, reuse cache hit for all 1,056 | 16.2 s |

The re-map adds only 10-25 % to a re-derive: mapping and sealing cost ~33 ms per execution against ~620 ms for the
layers above the AER (profile below). A recompute from the p10 copies cannot reuse (their recorded code digests differ
from this build's), so those runs recompute everything; the reuse rows show the cache when the key is unchanged
(`derivation.json` then records `"reuse": {"enabled": true, "recomputed": 0, "reused": N, ...}`, and the output equals
the `--no-reuse` output byte for byte apart from that record and `derived_from`).

## Per-stage profile (single process, 200 executions each)

`time.perf_counter` around each stage function, the same functions the T1 `prov` job and the parent call, run in one
process on the first 200 executions of each copy (`release` mode, as the corpora were imported).

| Stage | mandate (AgentDojo family), ms/execution | agentharm (Inspect), ms/execution |
|---|---:|---:|
| read raw object | 0.5 | 0.5 |
| map (parse + map, T1 `map` job) | 16.8 | (container family: not isolated here) |
| seal (write gate, digests) | 15.9 | — |
| AER read + seal verify | 3.1 | 8.8 |
| AER validator (parent) | 6.1 | 18.6 |
| SEM annotate + serialise | 2.7 | 1.0 |
| SEM validate (tier 3) | 7.7 | 2.5 |
| PROV derive (`agentprov-prov/0.1`) | 28.8 | 25.7 |
| **PROV validate (tier 4)** | **601.6 (87.9 %)** | **557.8 (90.5 %)** |
| — of which `roundtrip` (PROV-JSON → PROV-O round trip and completeness) | 571 (83.4 % of all) | 532 (86.3 % of all) |
| — `linkage` / `prov_structure` / `profiles` / `constraints` | 9.8 / 6.1 / 2.3 / 0.9 | 4.1 / 6.1 / 2.6 / 0.5 |
| index facets (parent) | 0.4 | 0.3 |
| atomic writes (AER + PROV) | 0.9 | 1.1 |
| **total** | **684** | **616** |

Inside `validate/roundtrip.py`, per execution (20 mandate executions): `_model_round_trip` 408 ms, `_completeness`
178 ms. A cProfile of `_model_round_trip` puts ~62 % in the `prov` library's RDF encoder
(`ProvRDFSerializer.encode_document`, `_encode_relation`; the document is encoded twice) and ~28 % in rdflib's TriG
parser (`notation3.py`, three parses per execution), the rest in model comparison. Sealing, digests, SEM, PROV
derivation, the AER validator and the writes together are under 10 % of the cost.

## Worker count (`recompute --dry-run --stages sem,prov,validation`, mandate copy, 396 executions)

Back to back, two rounds; machine shared, so the spread is noise as much as signal.

| `--jobs` | round 0 | round 1 |
|---:|---:|---:|
| 8 | 49.1 s | 47.2 s |
| 10 | 52.2 s | 57.2 s |
| 11 | 43.5 s | 78.1 s |
| 12 | **42.7 s** | 53.6 s |

Fastest observed: `--jobs 12` (42.7 s, about 9.3 executions/s), with `--jobs 11` within noise. The single-process cost
(~620 ms/execution, ~245 CPU-seconds for 396) means 8 workers would finish in ~31 s on an idle machine; the measured
47-49 s reflect the shared load, worker start-up (each T1 worker imports the engines and every profile) and the tail of
each 256-job batch. The default (`--jobs 0`, host default) is appropriate on an idle machine.

## Projection for the regeneration batch

At the measured 7-9 executions/s (8-12 workers, shared machine), a full re-derive of SEM/PROV/validation costs about
35-45 minutes for the 2024-06 AgentDojo corpus (18,241 executions), 20-26 minutes for ROPE (10,791) and minutes for the
small corpora; a full re-map adds 10-25 %. With the reuse cache, an item that changes only some AERs (e.g. B3: 386
AgentDyn CaMeL logs) recomputes only those executions; the rest are copied (~65 executions/s here, I/O bound). An item
that bumps a semantics profile or catalogue used by every execution (e.g. B1 through `agentdojo.suites@2`) changes the
`sem` stage `fn_digest` and so recomputes every execution of the corpora using it: the cache key is deliberately
coarse there (D-30), because which executions a rule change affects cannot be known without recomputing them.

## Hot spot: proposed fix for the owner (not applied; `validate/` is outside phase 11's ownership)

Tier-4 `pv.roundtrip` is 83-86 % of the derivation cost. Proposals for the `validate/` owner, each to be shown output-
and verdict-equivalent on the golden set before it is adopted:

1. Encode the PROV-JSON to PROV-O **once** per execution and share the rdflib graph between `_model_round_trip` and
   `_completeness` (today both encode; ~25-30 % of tier 4).
2. Parse the library's output as **N-Quads** instead of TriG: rdflib's N-Quads parser is a line parser, its TriG parser
   is the notation3 machinery (~28 % of the round trip).
3. With no blank nodes (already a finding), compare the graphs of the two serialisations as sets of canonical N-Quads
   lines rather than through the model, removing the second decode.

Cheap fixes inside phase-11 code were applied where they exist: the reuse cache (D-30) and the parent-side work
(AER validator, facets, writes) overlapped with the T1 batches; per-worker caching of catalogues and profiles already
happens in `adapters/runner/provjob.py` (module-level `PROFILES`), so nothing there was changed.
