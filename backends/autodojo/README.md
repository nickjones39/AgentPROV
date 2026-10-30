# backends/autodojo

A uv project (Python 3.12, no package of its own) that defines the **AutoDojo** live-backend environment.
It is deliberately separate from `backends/agentdojo/` and from the core.

## Why it is isolated

- AutoDojo ships as the distribution `agentdojo` at version `0.1.35`, the same name and version as stock
  AgentDojo on PyPI. The two cannot share an environment, and the version string cannot tell them apart
  (spec M.1.7; DECISIONS D9).
- The core runs on Python >= 3.14; the fork's dependency set targets Python 3.12.
- The fork is third-party code. It is never imported by the core and never installed into the core
  environment (CLAUDE.md invariant 7).

## What is pinned

`pyproject.toml` takes `agentdojo` from `https://github.com/xhOwenMa/AutoDojo` at commit
`aa458794b7eb7f082e94daeac4c0f55bfc0c90cc`, subdirectory `agentdojo`. `uv.lock` records that commit and the
hashes of every other dependency, and `exclude-newer` fixes the resolution date. The fork's build backend is
hatchling with no custom build hooks and no `setup.py` (inspected at the pinned commit before the first lock).

## How it is built

For live runs, by `agentprov backends build autodojo` (spec N.2.10, D.11.7), which runs

    uv sync --locked --no-config --no-dev --link-mode copy [--offline] --exclude-newer <project value> ... --project backends/autodojo

with `UV_PROJECT_ENVIRONMENT=$AGENTPROV_HOME/envs/autodojo-aa458794/`, outside the repository (offline from the uv
cache unless `--allow-network` is given), verifies the result (RECORD files, the PEP 610 pin, a `hello` to the
worker), provisions NLTK `punkt_tab` from the `[tool.agentprov.nltk]` recipe when it is pinned, runs the sandbox-exec
feasibility probe and writes `AGENTPROV_ENV.json`. `--offline-check` re-verifies a build.
Note that `--no-config` also ignores the project's `[tool.uv]` table, so the build passes `--exclude-newer` itself.

For the harness tests (development and the CI job `backend-autodojo`), an in-project environment is used, as for
`backends/agentdojo`: `uv sync --locked --project backends/autodojo` (a gitignored `.venv` here, whose `uv.lock`
neighbour gives the worker its lock digest), then
`uv run --no-sync --project backends/autodojo pytest backends/autodojo/tests`. The committed fixtures under
`tests/fixtures/capture/autodojo/` come from `tools/make_capture_fixtures.py`.

## How identity is established

The identity of the environment is the observed commit, read from the PEP 610 `direct_url.json` in the
installed `agentdojo` dist-info, never the version string. `tests/test_identity.py` (marker
`backend_autodojo`) asserts it equals the pinned commit.
