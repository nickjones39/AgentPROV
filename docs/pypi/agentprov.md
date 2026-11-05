# agentprov

AgentPROV turns agent executions into a source-preserving, evidence-qualified canonical record, and derives W3C PROV
from that record. The executions can be captured live or released by other research projects. Every derived PROV
statement names its evidence class, the rule that produced it, and the field of the record that justifies it. Corpora
are hash-chained from the original raw bytes to the final graph. You can verify and recompute them without
re-running any model.

This package is the `agentprov` command-line program and library. It installs the capture library
([`agentprov-capture`](https://pypi.org/project/agentprov-capture/)) with it; the draft-only Zenodo uploader
([`agentprov-zenodo`](https://pypi.org/project/agentprov-zenodo/)) comes with the `zenodo` extra.

- Website: <https://w3id.org/agentprov/>
- User guide: <https://w3id.org/agentprov/docs/>
- Source code: <https://github.com/nickjones39/AgentPROV>
- Software on Zenodo: <https://doi.org/10.5281/zenodo.23970107>
- Corpora on Zenodo (one collection): <https://doi.org/10.5281/zenodo.23814758>

## Install

Python 3.14.8 or later:

```bash
pip install agentprov              # or: uv tool install agentprov
pip install "agentprov[zenodo]"    # with the draft-only Zenodo uploader
agentprov info                     # versions, the source registry, extras, host isolation grade
agentprov --help
```

The desktop app is a separate download for macOS, Windows and Linux, on the
[releases page](https://github.com/nickjones39/AgentPROV/releases/latest). Live runs need the repository checkout: the
benchmark backends are separate projects that this package does not contain.

## What it does

- **Import** released agent logs (48 sources in 13 formats, single-agent tool-calling traces) and live captures into
  one canonical execution record (`aer/0.2`), through isolated, resource-limited workers.
- **Derive** semantic annotations (`sem/0.1`) and W3C PROV-JSON in three bundles: core (observed and derived
  statements), inference and assessment (`agentprov-prov/0.1`).
- **Validate** each stage, **verify** a corpus's hash chain against its root digest, and **recompute** the derivation
  byte for byte without calling a model.
- **Package** a corpus with its datasheet and checksums for an offline deposit; `package` never uploads. The separate
  uploader creates unpublished Zenodo drafts only, and publishing is always done by hand on Zenodo.

The [user guide](https://w3id.org/agentprov/docs/) walks through each step on a small demo corpus, and its command
reference lists every command's `--help`.

## Citation

```bibtex
@software{jones_agentprov_2026,
  author  = {Jones, Nicholas},
  title   = {AgentPROV: execution provenance for LLM-agent security research},
  version = {0.2.0},
  year    = {2026},
  license = {MIT},
  url     = {https://github.com/nickjones39/AgentPROV}
}
```

## Licence

MIT, © 2026 Nicholas Jones. Third-party code and data licences are listed in
[`THIRD_PARTY_NOTICES.md`](https://github.com/nickjones39/AgentPROV/blob/main/THIRD_PARTY_NOTICES.md).
