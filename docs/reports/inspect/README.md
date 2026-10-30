# Survey AgentHarm Inspect logs: full import (phase 6, 2026-10-08)

`import-cli-agentharm.json` records the import of the six survey AgentHarm `.eval` logs (part `agentharm` of
`agent-security-tools-survey`, profile `survey-agentharm`, producer band `inspect_ai 0.3.247.dev69`) through
`agentprov import`, written by `tools/import_report.py`. It holds numbers, codes and digests only; AgentHarm text is
restricted-use data and is never printed. The corpus `ast-survey-agentharm` is a separate restricted-use corpus (U-05)
outside the repository.

```bash
uv run agentprov import agent-security-tools-survey --input <survey clone> --verify-against-pin --release --jobs 10 \
    --corpus ~/.agentprov/corpora/ast-survey-agentharm --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/ast-survey-agentharm.partial --summary <summary> \
    --out docs/reports/inspect/import-cli-agentharm.json --extra <pin check>
```

**Origin.** The input is the local shallow clone of the survey at the pinned commit `89c4db2c…` (untrusted third-party
data, read through `agentprov.ingest.paths`). `--verify-against-pin` needs the pin's tree listing in the fetch cache. It
was seeded offline from that clone through the `raw.fetch` test seam (git `file://` remote; the 40-hex commit id and
`transfer.fsckObjects` authenticate every object; recorded in `~/.agentprov/cache/acquisitions.jsonl` with a consent text
naming the local source). The pinned tree `agentharm/results` holds 7 blobs, 11,911,647 bytes: the 6 logs plus
`timing_summary.csv`, a context artefact of the profile and not a candidate (the profile's `expected_files` and
`expected_bytes`, 6 and 11,825,414, count the logs only). All 6 logs matched their tree entries and carry the pinned
`git` origin; their size, sha256 and git blob id also equal the SWEEP_r2 EV-3 values (`pinned_snapshot_check`).

AgentPROV source at commit `61b39d3` (`src/` clean), CPython 3.14.8, M2 Max, 10 T1 workers, **release mode**.

| `agentprov import agent-security-tools-survey` | |
|---|---|
| Exit code / wall time | 0 / 119.4 s |
| Candidates (`.eval` containers) / samples mapped / sealed clean / with issues / degenerate / failed | 6 / 1,056 / 1,052 / 4 / 0 / 0 |
| `expand` | 6 containers; 1,062 members selected (6 `header.json` + 1,056 samples), 629 not selected |
| Variant / unit | `v2` 1,056 / `agent_execution` 1,056 |
| Origins | containers `git` 6; members `member` 1,062 |
| AER execution digests equal to the index / AER validator pass (release) | 1,056 / 1,056 |
| `agentprov-prov/0.1` derived / tier-4 pass (strict) / PROV re-derived byte-identically | 1,056 / 1,056 / 1,056 |
| Accounting | `consistent` 1,056 |

| Seal issue | issues | executions |
|---|---|---|
| `inspect.sample_limit` | 54 | 54 |
| `dangling_source_ref` | 16 | 4 |
| `missing_tool_result` | 16 | 4 |

These equal the D.9.5 record (`tests/full_corpus/test_inspect_survey.py`): 1,056 samples; `inspect.sample_limit` 54,
`dangling_source_ref` 16, `missing_tool_result` 16; accounting `consistent` for every sample.

Determinism: a second import with `--jobs 3` into another working corpus gave a byte-identical tree (3,188 files,
`corpus.json` and `derivation.json` included; `determinism` in the report).
