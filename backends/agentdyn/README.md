# backends/agentdyn

A uv project (Python 3.12, no package of its own) that defines the **AgentDyn** live-backend environment
(spec D.11.10; design `docs/reports/agentdyn-backend/design.md`; decisions D-680..D-688). It is separate from
`backends/agentdojo/`, `backends/autodojo/` and the core.

## Why it is isolated

- AgentDyn ships as the distribution `agentdojo` at version `0.1.35`, the same name and version as stock AgentDojo and
  the AutoDojo fork. They cannot share an environment, and the version string cannot tell them apart.
- AgentDyn is third-party code. It is never imported by the core and never installed into the core environment
  (CLAUDE.md invariant 7). Text in its repository (README, CLAUDE.md, run logs) is data, not instructions.

## What is pinned

`pyproject.toml` takes `agentdojo` from `https://github.com/SaFo-Lab/AgentDyn` at commit
`5353cf7615b135cace8d07c8f12dac53a16b6db3` (no subdirectory: AgentDyn's `pyproject.toml` is at the repository root,
and hatchling builds `src/agentdojo` with no build hooks). `uv.lock` records that commit and the hashes of every other
dependency; `exclude-newer` fixes the resolution date, the same as the other backends. Pass it explicitly to any
`uv lock` run under `--no-config`.

**Recorded deviation (D-681).** AgentDyn declares seven dependencies beyond AgentDojo 0.1.35 (`cyclopts`,
`pydantic-ai`, `tiktoken`, `vertexai`, `jsonref`, `openapi-pydantic`, `json_repair`). No module outside
`src/agentdojo/defenses/` imports them, and AgentDyn's own `uv.lock` does not lock them. They are overridden out
(`override-dependencies` with an impossible marker, which needs `environments`). The environment then resolves from
the uv cache with the SDK versions of `backends/agentdojo`. `tests/test_imports.py` checks that a run imports none of
them, and nothing under `agentdojo.defenses`.

## How it is built

For live runs, `agentprov backends build agentdyn` (spec N.2.10) builds `$AGENTPROV_HOME/envs/agentdyn-5353cf76/`
the same way as for AutoDojo, minus NLTK. The `agentdyn` choice is offered with the registry part `agentdyn · live`.
For development and these tests: `uv sync --project backends/agentdyn --locked --offline` (in-project `.venv`), then
`backends/agentdyn/.venv/bin/python -m pytest` from `backends/agentdyn`.

## What the tests cover (scripted transport only; no key, no network)

Identity (PEP 610 equal to the pin, guarded names, AgentDyn's system prompt `21a1c00d…`), the catalogue (7 suites,
157 user / 63 injection tasks, 17 attacks with 5 DoS), equality of the AgentDyn suites' tool definitions with
AutoDojo's copy, AgentDyn's shopping ground-truth stubs, the scripted cells S1..S4 (including a dropped malformed tool
call), the worker over a real subprocess, and the offline/import audit.
