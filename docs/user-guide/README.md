# AgentPROV user guide

This guide explains how to use AgentPROV, the execution-provenance framework for LLM-agent security research. It
covers the `agentprov` command-line tool, the live backends and the desktop app. It is task-oriented: each chapter
says what a command is for, shows it working on a small demo corpus, lists the options that matter, and explains the
common errors.

The normative description of AgentPROV is the specification in
[`docs/architecture/`](https://github.com/nickjones39/AgentPROV/blob/main/docs/architecture/README.md) (sections A–Q).
This guide explains the specification and never overrides it. If the guide and the specification disagree, the
specification wins; if either disagrees with the code, the code describes what actually happens.

## Who it is for

- **Researchers** who want to import released agent-security logs, derive W3C PROV from them, check the result and
  package a corpus: chapters 1–6 and 14.
- **People running live captures** with AgentDojo, AutoDojo and the other backends: chapter 7.
- **Desktop-app users**: chapter 8.
- **Anyone sharing a corpus**: read chapter 9 before you do.
- **Maintainers of the vocabulary namespace**: chapter 13.

## Contents

| # | Chapter | What it covers |
|---|---|---|
| 1 | [Installing AgentPROV](01-install.md) | Requirements, `uv sync`, `agentprov info`, the optional extras, `AGENTPROV_HOME` |
| 2 | [Concepts](02-concepts.md) | The pipeline, evidence classes, bundles, withholding, version axes, the corpus layout, the `apv:` vocabulary |
| 3 | [Sources and import](03-sources-and-import.md) | The source registry, `import`, pins, issues and quirks, `inspect` |
| 4 | [Derive, recompute, validate and verify](04-derive-recompute-validate-verify.md) | New corpus versions, recomputation, validation tiers, integrity levels |
| 5 | [Package and deposit](05-package-and-deposit.md) | Sealing, root digests, the datasheet, deposit drafts, `purge` |
| 6 | [Statistics and rendering](06-stats-and-render.md) | `stats` tables and `render` graphs |
| 7 | [Live runs](07-live-runs.md) | Backends, `run`, estimates, models and endpoints, keys, consent and caps |
| 8 | [The desktop app](08-desktop-app.md) | The viewer and the job runner |
| 9 | [Safety](09-safety.md) | Untrusted input, prompt injection in data, secrets, redaction, sharing |
| 10 | [Troubleshooting](10-troubleshooting.md) | Exit codes, refusals and their fixes, stale locks, environments, `AGENTPROV_HOME` on its own macOS volume |
| 11 | [CLI reference](11-cli-reference.md) | Every command's `--help`, generated from the CLI |
| 12 | [Glossary](12-glossary.md) | The terms used in this guide |
| 13 | [Vocabulary and identifiers](13-namespace.md) | The `apv:` namespace, w3id IRIs and the `agentprov-ns` repository |
| 14 | [Corpora and where they come from](14-corpora.md) | Every declared corpus with its pinned origin, licence and counts (generated); the built corpora's post-check verdicts |
| 15 | [Known corpus artefacts](15-corpus-artefacts.md) | The harness artefacts found in each built corpus, with handling classes and counts (generated) |

## How to read it

Read chapters 1 and 2 first. Chapters 3 to 6 follow one demo corpus from import to deposit, so they work best in
order. The other chapters can be read on their own.

**The demo corpus.** The worked examples use a corpus of three AgentDojo run logs from the pinned June-2024 snapshot
(`ethz-spylab/agentdojo` at commit `c274885`). These are the same three logs the test suite and the desktop app's
screenshots use. No example uses a real corpus from `~/.agentprov/corpora`.

**Conventions.**

- Commands are shown as `agentprov …`. In a checkout, run them as `uv run agentprov …`.
- Output is real output from this build, trimmed with `…`. Long absolute paths are shortened to `…/`, and the home
  directory is shown as `~`.
- Every command prints one log line (`INFO agentprov.cli: start command=…`) on stderr when it starts and one when it
  ends. The examples leave these out. `-q` turns them off, together with the progress feedback.
- Corpora contain prompt-injection payloads by design, so the guide never quotes their content. Chapter 9 explains
  how to look at content safely.

## Website

This guide is also a website at <https://w3id.org/agentprov/docs/>, under the project's landing page at
<https://w3id.org/agentprov/>. To preview a change on your own machine: `uv sync --frozen --group docs`, then
`uv run --group docs mkdocs serve`, which serves it at <http://127.0.0.1:8000/docs/> only.
