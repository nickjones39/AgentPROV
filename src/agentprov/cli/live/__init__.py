"""The parent (T0) side of live runs (docs/architecture MN N.2.1, N.2.1b, N.2.10; D.10.0, D.10.6, D.11.3; G.6).

* :mod:`~agentprov.cli.live.envs`: the repository root, the backend environment ``$AGENTPROV_HOME/envs/<b>-<commit8>/``,
  its ``AGENTPROV_ENV.json`` marker, the ``uv sync`` command of ``backends build`` and the T0 identity digests computed
  from the environment's files without importing anything from it (D.10.6);
* :mod:`~agentprov.cli.live.sandbox`: the ``sandbox-exec`` profile of real-model runs and its feasibility probe (G.4.10);
* :mod:`~agentprov.cli.live.worker`: spawning ``<env>/bin/python -I -B -m agentprov_backend.worker`` with the explicit
  environment allowlist of G.6.3 and speaking ``agentprov-backend/0.1`` (strict loader, 1 MiB lines, timeouts);
* :mod:`~agentprov.cli.live.staging`: ingesting one staged session like an ``--input`` tree (G.3.6, G.6.3), the
  literal-value secret scan and quarantine (G.6.4), and the capture identity cross-check (D.11.3 rule 1);
* :mod:`~agentprov.cli.live.quality`: the canary conditions and the capture-quality report from sealed evidence (D.10.9).

Nothing here imports ``agentdojo`` or ``agentprov_backend``: the core sees the backend only through the files of its
environment, the JSON lines of the protocol and the files the worker leaves in staging (D.10.0; M.5.2(9)).
"""
