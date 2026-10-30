# Third-party notices

AgentPROV's own code is MIT-licensed (see `LICENSE`). This file records third-party material that is
incorporated into, adapted by, or used under licence by this repository. It also records the licence
bases of the external execution data AgentPROV can import. **AgentPROV does not redistribute any
external corpus in Git.** Imported raw artefacts are handled per source under the raw policy
(`include` / `reference` / `withhold`) recorded in each corpus manifest.

## Code adapted or mirrored

| Component | Origin | Licence | Where |
|---|---|---|---|
| AgentDojo-PROV (baseline framework) | `nickjones39/agentdojo-prov` @ `579a908` | MIT, © 2026 Nicholas Jones | verbatim compat port under `src/agentprov/prov/compat/adprov_v2_3/`; capture logic in `backends/shared/` |
| AgentDojo `ToolsExecutor.query` mirror and the June-2024 security checkers (compat/replay only) | `ethz-spylab/agentdojo` (v0.1.35; June-2024 blobs) | MIT, © 2024 Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer, Florian Tramèr | `backends/shared/` (executor mirror) |

The live backends (`backends/agentdojo`, `backends/autodojo`, `backends/agentdyn`, `backends/inspect`) *install*
third-party benchmark code into isolated environments. They do not vendor it:
- `agentdojo==0.1.35` (PyPI; MIT)
- the AutoDojo fork `xhOwenMa/AutoDojo` @ `aa458794b7eb7f082e94daeac4c0f55bfc0c90cc` (MIT, © 2026 Ma,
  Li, Xiao, Yu, Zhang, Vorobeychik; contains AgentDojo MIT code and vendored defences under their own
  licences)
- AgentDyn `SaFo-Lab/AgentDyn` @ `5353cf76` (repository MIT, whose text is AgentDojo's)
- for the Inspect harness: `inspect-ai` 0.3.263 and `inspect-evals` 0.20.0 (PyPI; MIT), and the AgentHarm dataset
  at revision `e23b3fe6` (MIT with an additional clause: use only to improve AI safety and security)

The desktop app's bundles redistribute Qt and PySide6 (LGPL-3.0) and further Python packages; their notices are in
[`gui/THIRD_PARTY_NOTICES.md`](gui/THIRD_PARTY_NOTICES.md).

## Execution data AgentPROV can import (not redistributed here)

Licence bases are as recorded by the investigation of 2026-10-07; the table lists the sources known then. Every
registered source and part, with its SPDX licence id, is in the README's generated sources table, and every declared
corpus with its licence in the user guide's [Corpora and where they come from](docs/user-guide/14-corpora.md). Corpus
manifests record the licences verbatim.

| Source | Licence basis of released logs |
|---|---|
| AgentDojo upstream runs | repository MIT (no separate data licence) |
| ROPE (incl. AutoDojo-attack runs) | repository MIT |
| AgentDyn | repository MIT, whose text is AgentDojo's; the data licence is not explicit |
| DRIFT | MIT (added 2026-07-16) |
| Mandate-AgentDojo-Eval | MIT |
| Agent Security Tools Survey (Zenodo) | CC-BY-4.0. Embedded third-party data keeps its own licence; AgentHarm data carries a use clause. |
| MultiTurnAgentAttack (STAC) | CC BY-NC 4.0 (non-commercial) |
| CIAware-Bench | no licence. Reference-only; never redistributed. |
| DTap-Bench (AI-Secure, Hugging Face run logs and task definitions) | Apache-2.0 (dataset cards; upstream AI-secure/DecodingTrust-Agent LICENSE) |
| Interbolt on AgentDojo (deconvolute-labs) | Apache-2.0 |
| MELON (xwsdid/MELON) | MIT (upstream AgentDojo text) |
| Glitch (zanethomas1430-code) | MIT |
| UBAG gateway (mohameduk/agentdojo) | MIT (upstream AgentDojo text) |
| TACIT (CSSLab/Tacit) | Apache-2.0 |
| Geryon (luiacuaniello) | Apache-2.0 |
| In-context trajectory poisoning (HilaryTorn) | MIT |
| Prompt injection harness (yockcheng) | Apache-2.0 |
| llm_safety (ShreeyaVarma) | MIT (upstream AgentDojo text) |
| jspace-agentdojo-950 (kongminOS) | MIT |
| ceferisbarov/agentdojo reruns | MIT (upstream AgentDojo text) |
| Linyxus/agentdojo lacuna-exp | MIT (upstream AgentDojo text) |
| CrAIBench (AthaSSiN) | MIT |
| IPI multidomain agent study (Menelaus29) | MIT |
| gate (dafarusd) | **AGPL-3.0-only** (copyleft; its own corpus, D-25/D-94) |
| SENTRY (vinhqdang) | **AGPL-3.0-only** (copyleft; its own corpus) |
| aiAuthZ (Sports-Vision-Inc) | **AGPL-3.0-only** (copyleft; its own corpus) |
| Munim / bookkeeper (sricursion) | **GPL-3.0-or-later** (copyleft; its own corpus) |
| LLMLock (Wakeful-Cloud/llm-lock) | **GPL-3.0** (copyleft; its own corpus; the LICENSE states no version choice) |

Small test fixtures are derived from these sources. Each carries its own `SOURCE.json`, which records origin, commit,
licence and licence class. Fixtures of licence class `permissive` are part of the repository; the others (for example
the restricted-use AgentHarm excerpts) stay in the private development repository, and the tests that need them skip.
The copyleft sources' tests use synthetic fixtures (see below).

**Copyleft sources: synthetic fixtures only (D-945).** The repository holds no logs, excerpts or licence texts of the
AGPL-3.0 and GPL-3.0 sources (gate, SENTRY, aiAuthZ, bookkeeper, llm-lock). Their tests run on synthetic fixtures under
`tests/fixtures/{gate,sentry,aiauthz,bookkeeper,llm-lock}/`: self-authored AgentDojo TraceLogger logs, written by
`tests/adapters/agentdojo/phase10d_synthetic.py`, that follow each source's directory layout and dialect. Their
`SOURCE.json` entries record `synthetic: true`, `licence_class: permissive` and the repository's MIT licence. Two values
are filled in only when the tests run, and no fixture file stores them: the synthetic injection sentence, which is
assembled from fragments, and AgentDojo's default system prompt (MIT, © 2024 Debenedetti et al.), which is read from the
permissive `tests/fixtures/agentdojo/head/` fixtures. The real excerpts that these fixtures replace had licence class
`restricted` and were approved for the private repository only (user decision, 2026-10-12). They stay in the private
development history and are not part of the release commit or any package.
