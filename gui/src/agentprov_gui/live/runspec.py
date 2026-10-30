"""Run live settings → the ``run`` job and its R0 helpers (design §8.1–§8.3; D-651, D-652, D-655, D-701). No Qt.

* :func:`job_spec` is the live run: the ``run`` form of :mod:`jobs.commands` filled from :class:`RunSettings`. For a
  real model (not a dry run) it adds ``--keychain`` (the CLI reads the key itself, D-702) and, only when the user
  ticked the consent box, ``--i-consent-to-api-costs``; both raise it to R2.
* :func:`estimate_argv` is ``agentprov estimate … --format json`` (D-701): the CLI plans the cells, prices them and
  returns the estimate; the GUI only shows it. A real model is planned with its key (``--keychain``) only when the live
  part admits real runs and the keychain holds the key; otherwise the CLI uses its scripted stand-in and says the
  estimate is high (a resumed real-model corpus's settled units are not subtracted).
* :func:`catalogue_argv` is ``run SOURCE --catalogue``.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

from agentprov_gui.jobs.commands import FORMS, JobSpec, build_spec, tier_of_argv

__all__ = ["DECLARED_CONTAINMENT", "RunSettings", "catalogue_argv", "containment_choices", "containment_line",
           "estimate_argv", "job_spec", "key_names"]

#: AD-13(b), G.4.10: what the operator's containments are, said plainly wherever they are offered (G5 note §2.3)
DECLARED_CONTAINMENT: Final = ("dedicated-user and vm are your declaration that the run executes as a dedicated user or "
                               "inside a VM. AgentPROV records them as declared (declared_by: operator); it does not "
                               "enforce or check them.")


def containment_choices(platform: str | None = None) -> tuple[str, ...]:
    """The ``--containment`` values Run Live offers: ``sandbox-exec`` only on macOS, where the probe can pass; the
    operator's declarations everywhere."""
    return (("sandbox-exec",) if (sys.platform if platform is None else platform) == "darwin" else ()) + (
        "dedicated-user", "vm")


def containment_line(value: str) -> str:
    """How a containment choice reads in the R2 confirmation."""
    if value == "sandbox-exec":
        return "sandbox-exec (enforced by the probed macOS profile)"
    if value in ("dedicated-user", "vm"):
        return f"{value} (declared by you, not enforced or checked by AgentPROV)"
    return value or "none"



@dataclass(frozen=True, slots=True)
class RunSettings:
    source: str = "agentdojo"
    corpus: str = ""
    campaign: str = ""
    scripted: bool = True
    script: str = ""  # SCRIPT.json for the scripted transport
    model: str = ""  # endpoints.toml shorthand
    model_id: str = ""
    suites: tuple[str, ...] = ()
    attacks: tuple[str, ...] = ()
    user_tasks: str = ""  # "" = all
    injection_tasks: str = ""
    benign: str = ""  # "" = the CLI default (include)
    benchmark_version: str = ""
    repeats: int | None = None
    jobs: int | None = None
    max_attempts: int | None = None
    canary: int | None = None
    cell_timeout: float | None = None
    containment: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # any other run field by key (More options)

    @property
    def real(self) -> bool:
        return not self.scripted


def _values(s: RunSettings, **over: Any) -> dict[str, Any]:
    values: dict[str, Any] = dict(s.extra)
    values.update({
        "source": s.source, "corpus": s.corpus, "campaign": s.campaign, "suite": ",".join(s.suites),
        "attack": ",".join(s.attacks), "user_tasks": s.user_tasks, "injection_tasks": s.injection_tasks,
        "benign": s.benign, "benchmark_version": s.benchmark_version, "repeats": s.repeats, "jobs": s.jobs,
        "max_attempts": s.max_attempts, "canary": s.canary, "cell_timeout": s.cell_timeout,
    })  # fmt: skip
    if s.scripted:
        values.update({"llm_script": s.script, "model": "", "model_id": s.model_id, "containment": s.containment})
    else:
        values.update({"llm_script": "", "model": s.model, "model_id": s.model_id, "containment": s.containment})
    values.update(over)
    return values


def _insert(spec: JobSpec, flags: tuple[str, ...]) -> JobSpec:
    argv = (*spec.argv[:-1], *flags, spec.argv[-1])  # the positional SOURCE stays last
    return replace(spec, argv=argv, tier=tier_of_argv(argv, spec.tier))


def job_spec(s: RunSettings, *, consent: bool, conformance: bool = True, conformance_option: str | None = None,
             label: str = "", local_consent: bool = False) -> JobSpec:
    """The live run (or, with ``extra["dry_run"]`` / ``extra["preflight_only"]``, its dry run or preflight).
    ``local_consent``: the endpoint is a local server and the CLI has ``--i-consent-to-local-run`` (D-726), which the
    consent tick then adds instead of ``--i-consent-to-api-costs``."""
    spec = build_spec(FORMS["run"], _values(s), label=label or f"Run live · {Path(s.corpus).name or s.source}",
                      conformance=conformance, conformance_option=conformance_option)
    if s.real and not s.extra.get("dry_run"):
        flag = "--i-consent-to-local-run" if local_consent else "--i-consent-to-api-costs"
        spec = _insert(spec, ("--keychain", flag) if consent else ("--keychain",))
    return spec


def estimate_argv(s: RunSettings, *, real_allowed: bool, stats_corpora: Sequence[str] = ()) -> tuple[str, ...]:
    """``agentprov estimate`` for these settings (``--format json``). ``real_allowed``: the live part admits real
    models and the keychain holds the key, so the CLI may plan with it (``--keychain``)."""
    keep = {k: v for k, v in s.extra.items() if k in {f.key for f in FORMS["estimate"].fields}}
    values = _values(replace(s, extra=keep), stats_corpus=list(stats_corpora), format="json")
    if s.real:
        values["containment"] = s.containment if real_allowed else ""
    spec = build_spec(FORMS["estimate"], values)
    if s.real and real_allowed:
        return (*spec.argv[:-1], "--keychain", spec.argv[-1])
    return spec.argv


def catalogue_argv(source: str, benchmark_version: str = "") -> tuple[str, ...]:
    from agentprov_gui.live.backends import live_backends

    if source not in {b.source for b in live_backends()}:
        raise ValueError("unknown live source")
    return ("run", "--catalogue", *(("--benchmark-version", benchmark_version) if benchmark_version else ()), source)


def key_names(api_key_env: str | None, *, optional: bool = False) -> list[str]:
    """The keychain names a real run needs: the endpoint's key variable. A local endpoint needs none; its optional key
    (oMLX's ``OMLX_API_KEY``, D-827: ``optional=True``) is read by ``run --keychain`` when it is stored, and a run
    without it sends no key."""
    return [api_key_env] if api_key_env and not optional else []
