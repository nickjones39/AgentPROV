"""The AutoDojo backend (D.11): the AgentDojo-family runner of ``runner.AgentDojoBackend`` over the AutoDojo fork of
``agentdojo`` 0.1.35 at ``aa458794b7eb7f082e94daeac4c0f55bfc0c90cc`` (``backends/autodojo``).

Everything that records is shared and unchanged (D.11.4): the recording transport and ``LlmSpan`` brackets around the
fork's **unmodified** ``OpenAILLM`` (AD-09; no AgentPROV code calls a fork private helper), the pass recorder, the
executor mirror (the fork's ``ToolsExecutor.query`` is source-identical to 0.1.35, so the AST guard passes), the
recording runtime and the stock runner functions inside ``OutputLogger``. What differs:

* **Identity.** ``backend.id = "autodojo"`` in ``session.start``; ``identity()`` refuses an installed ``agentdojo``
  whose PEP 610 source is not the pinned fork commit, and reports the extra guarded names
  ``identity.AUTODOJO_GUARDED_NAMES``. The benchmark (``cell.benchmark``, the ``bench`` actor) stays ``agentdojo``: the
  suites are AgentDojo-family content, and the fork is told apart by ``identity.benchmark.{repo, commit}``.
* **Suite set.** Whatever the fork registers for the benchmark version (v1.2.2: the four AgentDojo suites,
  ``banking_v2_0..4``, ``travel_v2_0..4`` and the AgentDyn suites ``shopping``, ``github``, ``dailylife``); plans and
  cells are validated against it as for stock AgentDojo.
* **Attack ``autodojo``** (cache replay). The cache comes per cell from ``run_cell.attack_env`` (the worker contract
  below), never from the worker's process environment.
* **Run errors.** The fork's runner imposes ``utility = false, security = false`` and sets ``error_type`` in the
  TraceLogger context for the errors it skips (``benchmark.py``: context length, ``InternalServerError``,
  ``json.JSONDecodeError``, ``api_internal_server_error``, ``server_error``). The judgements come from the stock
  return values (origins ``harness_default``, as for AgentDojo); the note ``autodojo/run_error_imposed`` records the
  ``error_type`` read from the native log and the imposed values.
* **Instrumentation.** No ``agentdojo.temperature_not_transmitted@1`` (the fork sends ``temperature if not None``);
  instead the fork's stock request behaviour is declared: ``autodojo.fork_temperature_transmitted@1``,
  ``autodojo.fork_malformed_json_retry@1``, ``autodojo.fork_system_role@1``, ``autodojo.fork_openrouter_extras@1`` (on
  an ``openrouter.ai`` host) and ``autodojo.env_nltk_preprovisioned@1`` (the digest of the provisioned ``punkt_tab``
  zip, or ``null``).
* **Refusals.** ``llm_element = "gateway_compat"`` (the port binds to private helpers whose fork versions differ;
  AD-09); the defences ``drift``, ``progent``, ``camel``, ``camel_nopolicy`` (replace pipeline components) with their
  own message, every other defence as for AgentDojo; the attack ``ours`` (replays optimiser output directories,
  ``OURS_ATTACK_DIR``); the optimiser (``variant_generation``) is not part of the installed package and is never
  imported.

**Worker contract for the cache (``run_cell``).** For a cell with ``attack == "autodojo"``:

* ``cell.attack_params`` must carry ``autodojo_cache_sha256`` (64 lower-case hex) and ``autodojo_variant`` (integer
  >= 0), so the cache identity is part of the cell, ``config_sha256`` and ``session.start.cell.attack_params``;
* ``run_cell.attack_env`` must be ``{"AUTODOJO_CACHE_label": <label>, "AUTODOJO_VARIANT": <the same integer>}``;
  ``<label>`` is a relative path inside the session directory (no ``..``, no absolute path, no backslash), staged
  there by the parent before ``run_cell`` -- recommended ``raw/attack/autodojo-cache.json``, so the worker reports it
  in ``cell_done.artefacts`` with role ``supporting``;
* the worker resolves the label without following symlinks (every component ``lstat``-ed), requires a regular file
  with one link and at most 64 MiB, and requires its sha256 to equal ``autodojo_cache_sha256``; any failure seals the
  session ``errored`` (``UnsupportedConfiguration``, ``where: setup``) and nothing runs;
* ``AUTODOJO_CACHE`` (the absolute path) and ``AUTODOJO_VARIANT`` are set in ``os.environ`` only while the attack is
  constructed (the fork reads them in ``__init__``) and restored afterwards;
* the instrumentation item ``autodojo.attack_cache_replay@1`` (``attack_parameter``) records ``{cache_label,
  cache_sha256, cache_bytes, variant}``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentprov_backend.attacks import UnsupportedConfiguration
from agentprov_backend.identity import BenchmarkIdentity
from agentprov_backend.runner import (
    DECLARED_SEMANTICS,
    AgentConfig,
    AgentDojoBackend,
    BuiltLLM,
    CaptureSession,
    CellSpec,
    _is_label,
    _item,
    instrumentation_items,
)

__all__ = [
    "AUTODOJO_COMMIT",
    "AUTODOJO_REPO",
    "AutoDojoBackend",
    "CACHE_MAX_BYTES",
    "REFUSED_ATTACKS",
    "REFUSED_DEFENCES",
    "resolve_session_file",
]

AUTODOJO_REPO = "https://github.com/xhOwenMa/AutoDojo"
AUTODOJO_COMMIT = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"
CACHE_MAX_BYTES = 64 * 1024 * 1024
ITEM_CACHE = "autodojo.attack_cache_replay@1"
PUNKT_TAB = ("tokenizers", "punkt_tab.zip")

REFUSED_DEFENCES: Mapping[str, str] = {
    name: f"the {name!r} defence replaces pipeline components and needs defence-specific capture; refused in v0.1 "
          "(D.11.6)"
    for name in ("drift", "progent", "camel", "camel_nopolicy")
}
REFUSED_ATTACKS: Mapping[str, str] = {
    "ours": "the 'ours' attack replays optimiser output directories (OURS_ATTACK_DIR); optimiser runs and their "
            "outputs are not supported in v0.1 (D.11.6)",
}

AUTODOJO_DECLARED_SEMANTICS: Mapping[str, str] = {
    **DECLARED_SEMANTICS,
    "benchmark": "agentdojo (AutoDojo fork aa458794)",
    "run_error": "a caught run error (context length, InternalServerError, JSONDecodeError, API or server error) "
                 "imposes utility = false, security = false and sets error_type in the TraceLogger context (fork "
                 "benchmark.py)",
}

_HEX64 = re.compile(r"[0-9a-f]{64}")


def resolve_session_file(root: Path, label: str, *, max_bytes: int = CACHE_MAX_BYTES) -> tuple[Path, bytes]:
    """Read ``label`` under ``root`` without following a symlink anywhere below ``root``: every component is
    ``lstat``-ed, the file must be regular with ``st_nlink == 1`` and at most ``max_bytes``. Returns the path and the
    bytes."""
    if not _is_label(label):
        raise UnsupportedConfiguration("the cache label must be a relative label inside the session directory")
    current = Path(root)
    parts = label.split("/")
    for i, part in enumerate(parts):
        current = current / part
        try:
            st = os.lstat(current)
        except OSError:
            raise UnsupportedConfiguration(f"the cache label {label!r} does not exist in the session") from None
        if stat.S_ISLNK(st.st_mode):
            raise UnsupportedConfiguration(f"the cache label {label!r} goes through a symlink")
        if i < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise UnsupportedConfiguration(f"the cache label {label!r} is not inside a directory")
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise UnsupportedConfiguration(f"the cache label {label!r} is not a regular file with one link")
    if st.st_size > max_bytes:
        raise UnsupportedConfiguration(f"the cache {label!r} exceeds {max_bytes} bytes")
    fd = os.open(current, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UnsupportedConfiguration(f"the cache {label!r} exceeds {max_bytes} bytes")
    return current, data


def _punkt_tab_sha256(environ: Mapping[str, str]) -> str | None:
    root = environ.get("NLTK_DATA")
    if not root:
        return None
    path = Path(root, *PUNKT_TAB)
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class AutoDojoBackend(AgentDojoBackend):
    """The ``Backend`` of D.10.1 for the AutoDojo fork (see the module docstring)."""

    backend_id = "autodojo"
    declared_semantics = AUTODOJO_DECLARED_SEMANTICS

    def identity(self) -> BenchmarkIdentity:
        if self._identity is None:
            from agentprov_backend.identity import AUTODOJO_GUARDED_NAMES, benchmark_identity

            ident = benchmark_identity(self.benchmark_version, extra_guarded=AUTODOJO_GUARDED_NAMES)
            src = ident.source
            if src.get("kind") != "git" or src.get("repo") != AUTODOJO_REPO or src.get("commit") != AUTODOJO_COMMIT:
                raise UnsupportedConfiguration(
                    f"the installed agentdojo is not the AutoDojo fork at {AUTODOJO_COMMIT} (PEP 610 source "
                    f"{src.get('kind')!r}, commit {str(src.get('commit'))[:12]!r})")
            self._identity = ident
        return self._identity

    def plan(self, spec: Mapping[str, Any]) -> Any:
        plan = super().plan(spec)
        for cell in plan.cells:
            self.check_cell(cell)
        self.check_agent(plan.agent)
        return plan

    def catalogue(self, benchmark_version: str | None = None) -> dict[str, Any]:
        """D-652: as the stock backend's, with the fork's refused attacks and the cache the ``autodojo`` attack needs."""
        from agentprov_backend.runner import catalogue

        return {"backend": self.backend_id, **catalogue(
            benchmark_version or self.benchmark_version, refused_attacks=REFUSED_ATTACKS,
            attack_needs={"autodojo": ("--autodojo-cache", "--autodojo-variant")}, backend_id=self.backend_id,
            refused_defences=REFUSED_DEFENCES)}

    def check_agent(self, agent: AgentConfig) -> None:
        if agent.llm_element != "native":
            raise UnsupportedConfiguration(
                "llm_element 'gateway_compat' is refused for the AutoDojo fork: the port binds to private OpenAI "
                "helpers whose fork versions differ; the fork's own element is recorded at transport level (AD-09)")

    def check_cell(self, cell: CellSpec) -> None:
        if cell.defence in REFUSED_DEFENCES:
            raise UnsupportedConfiguration(REFUSED_DEFENCES[cell.defence])
        if cell.attack in REFUSED_ATTACKS:
            raise UnsupportedConfiguration(REFUSED_ATTACKS[cell.attack])
        if cell.attack == "autodojo":
            p = cell.attack_params
            digest = p.get("autodojo_cache_sha256")
            variant = p.get("autodojo_variant")
            if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
                raise UnsupportedConfiguration("an autodojo cell needs attack_params.autodojo_cache_sha256 (64 hex)")
            if not isinstance(variant, int) or isinstance(variant, bool) or variant < 0:
                raise UnsupportedConfiguration("an autodojo cell needs attack_params.autodojo_variant (integer >= 0)")

    def instrumentation(self, agent: AgentConfig, built: BuiltLLM | None, backend_config: Mapping[str, Any], *,
                        mirror_source_sha256: str | None, environ: Mapping[str, str]) -> list[dict[str, Any]]:
        items = [i for i in instrumentation_items(agent, built, backend_config,
                                                  mirror_source_sha256=mirror_source_sha256)
                 if i["id"] != "agentdojo.temperature_not_transmitted@1"]
        for item in items:
            if item["id"] == "agentdojo.http_backoff@1":
                item["detail"] = ("native element: the SDK's own retries (max_retries=2), the fork's tenacity retry "
                                  "of chat_completion_request (3 attempts) and its request-and-parse retry on "
                                  "malformed tool-call JSON (3 attempts) are stock; every wire attempt is recorded")
        temperature = built.temperature if built is not None else agent.params.get("temperature", 0.0)
        out = list(items)
        if temperature is not None:
            out.append(_item("autodojo.fork_temperature_transmitted@1", "harness_policy",
                             params={"configured": agent.params.get("temperature"), "transmitted": temperature},
                             detail="the fork sends `temperature if temperature is not None`, so 0.0 is transmitted "
                                    "(stock 0.1.35 omits a falsy temperature)"))
        out.append(_item("autodojo.fork_malformed_json_retry@1", "harness_policy",
                         params={"max": 3, "exception": "JSONDecodeError"},
                         detail="the fork's _request_and_parse re-requests when the tool-call arguments are not JSON; "
                                "each superseded reply is recorded `discarded`; the runner then skips the task as "
                                "error_type json_decode_error"))
        out.append(_item("autodojo.fork_system_role@1", "harness_policy",
                         detail="the fork sends the system message with role `system` (stock 0.1.35: `developer`)"))
        if built is not None and built.host == "openrouter.ai":
            out.append(_item("autodojo.fork_openrouter_extras@1", "harness_policy",
                             detail="on OpenRouter the fork adds extra_body: usage accounting (`usage.include`), "
                                    "the Gemini provider pin and dynamic reasoning for google/gemini models, and "
                                    "Anthropic cache_control on the system message for Claude routes"))
        out.append(_item("autodojo.env_nltk_preprovisioned@1", "behaviour_preserving",
                         params={"punkt_tab_sha256": _punkt_tab_sha256(environ)},
                         detail="NLTK punkt_tab provisioned by `agentprov backends build autodojo` (unextracted zip "
                                "under NLTK_DATA); null when the environment has none (filter defences refused)"))
        return out

    def attack_overrides(self, cell: CellSpec, session: CaptureSession,
                         attack_env: Mapping[str, Any] | None) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
        if cell.attack != "autodojo":
            return None, []
        env = attack_env if isinstance(attack_env, Mapping) else {}
        label = env.get("AUTODOJO_CACHE_label")
        variant = env.get("AUTODOJO_VARIANT")
        if not isinstance(label, str):
            raise UnsupportedConfiguration("an autodojo cell needs run_cell.attack_env.AUTODOJO_CACHE_label")
        if not isinstance(variant, int) or isinstance(variant, bool) or variant < 0:
            raise UnsupportedConfiguration("run_cell.attack_env.AUTODOJO_VARIANT must be an integer >= 0")
        if variant != cell.attack_params.get("autodojo_variant"):
            raise UnsupportedConfiguration("AUTODOJO_VARIANT differs from attack_params.autodojo_variant")
        path, data = resolve_session_file(session.dir, label)
        digest = hashlib.sha256(data).hexdigest()
        if digest != cell.attack_params.get("autodojo_cache_sha256"):
            raise UnsupportedConfiguration("the staged cache's sha256 differs from attack_params.autodojo_cache_sha256")
        item = _item(ITEM_CACHE, "attack_parameter",
                     params={"cache_label": label, "cache_sha256": digest, "cache_bytes": len(data),
                             "variant": variant},
                     detail="AUTODOJO_CACHE/AUTODOJO_VARIANT set for the attack's construction only; the fork's "
                            "logger does not record them")
        return {"AUTODOJO_CACHE": str(path.resolve()), "AUTODOJO_VARIANT": str(variant)}, [item]

    def after_outcome(self, session: CaptureSession, utility: bool, security: bool, run_error: bool) -> None:
        files = self._native_files(session)
        if len(files) != 1:
            return
        try:
            doc = json.loads(files[0].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(doc, dict):
            return
        error_type = doc.get("error_type")
        if error_type is None and doc.get("error") is None:
            return
        session.note("autodojo", "run_error_imposed", {
            "error_type": error_type if isinstance(error_type, str) else None,
            "native_error_present": doc.get("error") is not None,
            "judgements": {"utility": utility, "security": security},
            "source": "native_log.error_type",
        })
