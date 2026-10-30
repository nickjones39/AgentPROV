"""``agentprov estimate``: the cost and time of a live run before it starts (D-701; design §8.3 as amended by D-650,
D-653, D-656; reverse CLI parity D-700).

    agentprov estimate SOURCE <run options> [--stats-corpus DIR]... [--format text|json]

It takes the options of ``agentprov run`` (less the ones of :data:`agentprov.cli.run.ESTIMATE_OMITS`), plans the
cells with a dry run (``run --dry-run --plan-json``, D-651: hello and plan only, no model call, nothing written) and
reads the backend catalogue (D-652) for the tool-definition sizes. Then, per suite × attack, it takes calls, tokens and
time from the ``--stats-corpus`` corpora (sampled; counts only), else the shipped priors, else the
``estimate.default.*`` settings, and prices them with ``agentprov prices``. It prints p50 and p90 cost and time, the
breakdown per suite and per attack, the worst case and every assumption it made. Nothing is charged.

An Inspect plan (D-770) is priced per sample × epoch: the agent's calls and the scorer's judge calls, each judge
role at its model's price at the agent's endpoint (a capped run's judges must use the agent's model, D-740, which the
estimate warns about), with the D-740 bound of billed calls per sample shown beside it.

A real model is planned with its key only when ``--keychain`` (or ``--env-stdin`` / ``--env-file``) is given and its
live part admits real runs; otherwise a scripted stand-in plans the same cells (no key, no network), and the estimate
says that units a resumed real-model corpus already holds are not subtracted. The model id comes from ``--model-id``
only (no ``.env`` is read for it).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text
from agentprov.errors import AgentProvError

ESTIMATE_FORMAT: Final = "agentprov-estimate/0.1"
MAX_STATS_CORPORA: Final = 16
#: the destinations ESTIMATE_OMITS removes, with run's defaults (store_true flags are False, the rest None)
_OMITTED_FLAGS: Final = ("preflight_only", "dry_run", "plan_json", "catalogue", "keep_staging", "skip_prov_conformance",
                         "i_consent_to_api_costs", "i_consent_to_local_run", "m5ultra")
_OMITTED_VALUES: Final = ("preset", "model_dir", "model_size_gb", "active_params_b", "context_tokens",
                          "kv_gb_per_trace", "server_max_concurrency")


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    from agentprov.cli.run import add_run_options

    p = sub.add_parser("estimate", parents=[shared],
                       help="the cost and time of a live run before it starts (p50/p90; no model call)",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="estimate", handler=run_estimate, feedback=False)
    add_run_options(p, shared, estimate=True)
    e = p.add_argument_group("estimate")
    e.add_argument("--stats-corpus", action="append", metavar="DIR",
                   help="measure calls, tokens and time in this stored corpus (a sample of its AER files, counts only; "
                        "repeatable, at most 16)")
    e.add_argument("--format", choices=["text", "json"], default="text",
                   help="json: one agentprov-estimate/0.1 document on stdout")


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _plan_args(args: argparse.Namespace, home: Path, *, keyed: bool) -> argparse.Namespace:
    from agentprov.estimate import STAND_IN_SCRIPT

    values = dict(vars(args))
    values.update(dict.fromkeys(_OMITTED_FLAGS, False))
    values.update(dict.fromkeys(_OMITTED_VALUES))
    values.update(dry_run=True, plan_json=True, json=False, command="run")
    if not args.llm_script and not keyed:  # the scripted stand-in: the same cells, no key, no network
        values.update(llm_script=str(STAND_IN_SCRIPT), model=None, endpoint=None, model_id=None, containment=None,
                      keychain=False, env_stdin=False, env_file=None, allow_custom_endpoint=False,
                      # the local-server options (D-691..D-698) belong to the real endpoint, not the stand-in
                      base_url=None, accept_served_model=None, allow_lan_endpoint=False, no_hash_weights=False)
    if values.get("corpus") is None:
        values["corpus"] = str(home / "corpora" / "estimate-only")  # never written: a dry run writes nothing
    if not (values.get("campaign") or values.get("corpus_id") or values.get("spec")):
        values["campaign"] = "estimate"
    return argparse.Namespace(**values)


def _stats(roots: list[str]) -> tuple[dict[Any, Any], list[dict[str, Any]]]:
    from agentprov.estimate.usage import aggregate, sample_corpus

    usages: list[Any] = []
    read = []
    for raw in roots:
        root = Path(raw)
        if not (root / "aer").is_dir():
            raise CliUsageError(f"agentprov estimate: --stats-corpus {safe_text(raw, 200)} is not a stored corpus "
                                "(no aer/ directory)")
        sample = sample_corpus(root)
        usages += sample
        read.append({"corpus": safe_text(root.name, 120), "executions_sampled": len(sample)})
    return {**aggregate(usages, with_model=True), **aggregate(usages, with_model=False)}, read


def _tool_chars(ctx: Context, args: argparse.Namespace, warnings: list[str]) -> dict[str, int | None]:
    from agentprov.cli.run import _catalogue

    try:
        result = _catalogue(ctx, argparse.Namespace(source=args.source, benchmark_version=args.benchmark_version))
        doc = json.loads(result.payload or b"{}")
    except (AgentProvError, ValueError) as exc:
        warnings.append(f"The backend catalogue is unavailable ({safe_text(str(exc).splitlines()[0], 200)}): "
                        "token estimates from message sizes leave out the tool definitions.")
        return {}
    return {s["name"]: s.get("tool_definition_chars") for s in doc.get("suites", []) if isinstance(s, dict)}


INSPECT_PREFIX: Final = "inspect-"


def _judge_price(home: Path, judges: dict[str, str], *, real: bool, endpoint: str | None, model_id: str | None,
                 price: Any, warnings: list[str]) -> Any:
    """D-770: the price the judge calls are charged at. Judges run at the agent's endpoint (D-667), so each role's model
    is looked up there; when the roles use different models, the dearest prices them all (a high estimate). ``None``
    when a judge model has no price."""
    from agentprov.cli.prices import book

    if not judges or not real:
        return price
    models = sorted(set(judges.values()))
    if models == [model_id]:
        return price
    found = {m: book(home).lookup(str(endpoint), m) for m in models}
    missing = [m for m, p in found.items() if p is None]
    if missing:
        warnings.append("No price for the judge model(s) " + ", ".join(safe_text(m, 120) for m in missing)
                        + " at this endpoint: set one with 'agentprov prices set'.")
        return None
    if len(models) > 1:
        warnings.append("The judge roles use different models (" + ", ".join(safe_text(m, 120) for m in models)
                        + "): every judge call is priced at the dearest of them.")
    return max(found.values(), key=lambda p: (p.input + p.output, p.output))


def _sample_call_bound(backend: str, info: Any) -> int | None:
    """D-740's billed-call bound of one sample, ``((M - 1) x (1 + a) + j) x (1 + K)``, for a task with a recorded bound
    and a message limit (the run itself also checks the task code's digest); ``None`` otherwise."""
    from agentprov.cli.live import envs

    try:
        bound = envs.backend_kind(backend).call_bounds.get(info.task)
    except AgentProvError:
        return None
    if bound is None or info.message_limit is None:
        return None
    return ((info.message_limit - 1) * (1 + bound.per_agent_call) + bound.per_sample) * (1 + envs.INSPECT_MAX_RETRIES)


def _local_time_basis(endpoint: str, model_id: str) -> tuple[Any, str] | None:
    """D-826: ``(CellSeconds row, label)`` for a local endpoint's model when a calibrated preset for that endpoint (the
    setting ``compute.preset``, else ``m5ultra``) has measured seconds per cell and this host is the preset's; the row
    is the model's active-parameter class (``local_models.*.active_params_b``, else the last row). ``None`` otherwise."""
    from agentprov import settings
    from agentprov.cli.live.localmodels import local_endpoint_names
    from agentprov.errors import AgentProvError
    from agentprov.host import detect_host
    from agentprov.presets import check_host, load_preset

    if endpoint not in local_endpoint_names():
        return None
    name = settings.get("compute.preset") or "m5ultra"
    try:
        preset = load_preset(str(name))
    except AgentProvError:
        return None
    if not preset.calibrated or preset.endpoint != endpoint or not preset.cell_seconds:
        return None
    if check_host(preset, detect_host(probe=False)):
        return None  # measured on another kind of machine: not this host's time
    active = settings.local_model(endpoint, model_id).get("active_params_b")
    row = preset.cell_seconds_for(float(active) if isinstance(active, int | float) else None)
    if row is None:
        return None
    return row, (f"preset {preset.name} v{preset.version}, {row.p50:g}/{row.p90:g} s per cell (p50/p90) measured at "
                 f"jobs {row.jobs} ({row.source})")


def run_estimate(ctx: Context) -> CommandResult:
    from agentprov import settings
    from agentprov.cli.live.envs import agentprov_home
    from agentprov.cli.prices import book
    from agentprov.cli.run import run_run
    from agentprov.estimate.cost import estimate
    from agentprov.estimate.plan import parse_plan
    from agentprov.estimate.prices import Price
    from agentprov.estimate.priors import StatsSource, load_priors

    args = ctx.args
    if args.format == "json" and getattr(args, "json", False):
        raise CliUsageError("agentprov estimate: --format json prints to stdout, which --json takes")
    if not (args.model or args.endpoint or args.llm_script):
        raise CliUsageError("agentprov estimate: one of --model, --endpoint with --model-id, or --llm-script")
    roots = list(args.stats_corpus or [])
    if len(roots) > MAX_STATS_CORPORA:
        raise CliUsageError(f"agentprov estimate: at most {MAX_STATS_CORPORA} --stats-corpus")
    home = agentprov_home(ctx.env)
    real = not args.llm_script
    keyed = real and bool(args.keychain or args.env_stdin or args.env_file)
    endpoint = (args.model or {"local": "ollama"}.get(args.endpoint, args.endpoint)) if real else None
    model_id = args.model_id if real else None
    warnings: list[str] = []
    corpus_stats, read = _stats(roots)  # before any worker: a bad path fails fast

    planned = run_run(Context(args=_plan_args(args, home, keyed=keyed), progress=ctx.progress, stdout=ctx.stdout,
                              stderr=ctx.stderr, env=ctx.env, log=ctx.log))
    plan = parse_plan(planned.payload or b"")
    tool_chars = _tool_chars(ctx, args, warnings)

    today = dt.date.today()
    if not real:
        price: Price | None = Price("local", "scripted", Decimal(0), Decimal(0), None,
                                    "scripted transport: no model call is billed", today)
    elif not model_id:
        price = None
        warnings.append("No --model-id: the model cannot be priced (the estimate never reads .env).")
    else:
        price = book(home).lookup(str(endpoint), model_id)
    if real and not keyed:
        warnings.append("Planned with a scripted stand-in (no key, no network): the cells are the same, but units a "
                        "resumed real-model corpus already holds are not subtracted, so this estimate is high.")
    defaults = {k[len("estimate.default."):]: v for k, v in settings.items("estimate.default.").items()}
    inspect_backend = plan.backend.startswith(INSPECT_PREFIX)
    # an Inspect backend's executions carry its benchmark (``inspect-agentharm`` → agentharm) and live profile
    # ``<benchmark>-live``, so that is their backend label too
    benchmark = plan.backend[len(INSPECT_PREFIX):] if inspect_backend else \
        "agentdyn" if plan.backend == "agentdyn" else "agentdojo"
    stats = StatsSource(benchmark=benchmark, model=model_id,
                        backend=(benchmark if inspect_backend else plan.backend) or None, corpus=corpus_stats,
                        priors=load_priors()[1], defaults=defaults, tool_chars=tool_chars)
    stats_for: Any = stats
    measured = _local_time_basis(str(endpoint), model_id) if real and endpoint and model_id else None
    if measured is not None:  # D-826: a calibrated preset's measured seconds per cell replace the priors' time
        from dataclasses import replace as _replace

        from agentprov.estimate.cost import Quantiles

        row, label = measured

        def stats_for(suite: str, attack: str | None, kind: str) -> Any:
            s = stats(suite, attack, kind)
            return _replace(s, seconds=Quantiles(row.p50, row.p90), basis=f"{s.basis}; time: {label}")

        warnings.append(f"Time from the concurrency sweep: {label} (D-826); calls and tokens from the usual sources.")
    judges = dict(plan.inspect.judges) if plan.inspect is not None else {}
    judge_price = _judge_price(home, judges, real=real, endpoint=endpoint, model_id=model_id, price=price,
                               warnings=warnings)
    if judges and real and (args.max_calls is not None or args.max_cost_usd is not None):
        others = sorted(r for r, m in judges.items() if m != model_id)
        if others:
            warnings.append("A capped Inspect run is refused unless every judge uses the agent's model (D-740): "
                            + ", ".join(safe_text(r, 64) for r in others) + " do(es) not.")
    jobs = max(1, args.jobs or 1)
    e = estimate(plan.cells, repeats=plan.repeats, attempts_due=plan.attempts_due, jobs=jobs, price=price,
                 stats_for=stats_for, preflight=real, today=today, judged=bool(judges), judge_price=judge_price)
    # D-725 caps pass through to the dry plan (a keyed API plan needs them, D-721); here they are compared with the
    # estimate: a run stops starting cells at a cap, so a cap below the p90 means an unfinished run
    if args.max_cost_usd is not None and e.cost_p90 is not None and e.cost_p90 > Decimal(str(args.max_cost_usd)):
        warnings.append(f"The p90 cost is above --max-cost-usd ${args.max_cost_usd:g}: the run would stop starting cells "
                        "at the cap, before every cell is done.")
    if args.max_calls is not None and e.calls_p90 > args.max_calls:
        warnings.append(f"The p90 model calls ({e.calls_p90:,.0f}) are above --max-calls {args.max_calls:,}: the run "
                        "would stop starting cells at the cap.")
    body = e.to_json(today)
    body["warnings"] = [*body["warnings"], *warnings]
    doc = {"format": ESTIMATE_FORMAT, "source": safe_text(str(args.source), 40),
           "transport": "http" if real else "scripted", "endpoint": endpoint, "model": model_id,
           "planned_with": "model" if keyed or not real else "stand-in", "jobs": jobs, "plan": plan.to_json(),
           "stats_corpora": read, **body}
    if plan.inspect is not None:
        doc["plan"]["inspect"]["calls_bound_per_sample"] = _sample_call_bound(plan.backend, plan.inspect)
        doc["judge_price"] = None if judge_price is None else judge_price.to_json()

    result = CommandResult(dry_run=True)
    result.notices.extend(planned.notices)
    result.counters = {"units": e.units, "attempts_due": e.attempts_due}
    doc["text"] = text_lines(doc)  # the wording the text form prints and the GUI shows
    if args.format == "json":
        result.payload = _payload(doc)
    else:
        for line in doc["text"]:
            result.output(line)
    return result


def text_lines(doc: dict[str, Any]) -> list[str]:
    """The estimate as text (also what the GUI shows, from the JSON document)."""
    from agentprov.estimate.cost import duration_text, money

    def _money(value: str | None) -> str:
        return "-" if value is None else money(Decimal(value))

    plan = doc["plan"]
    scripted = doc["transport"] == "scripted"
    head = f"{doc['units']:,} cell run(s); scripted transport: no cost." if scripted else doc["headline"]
    lines = [f"{head} Time ≈ {duration_text(doc['seconds_p50'])} (p90 {duration_text(doc['seconds_p90'])}) at --jobs "
             f"{doc['jobs']}.",
             f"Plan {plan['plan_sha256'][:16]}…: {plan['cells']:,} cells × {plan['repeats']} repeat(s) = "
             f"{plan['units']:,} units; {plan['settled']:,} already settled; up to {plan['attempts_due']:,} attempts "
             f"due (--max-attempts {plan['max_attempts']})."]
    ins = plan.get("inspect")
    if ins is not None:  # D-770
        judges = ", ".join(f"{safe_text(r, 64)} {safe_text(m, 120)}" for r, m in sorted(ins["judges"].items()))
        bound = ins.get("calls_bound_per_sample")
        lines.append(f"Inspect {safe_text(ins['task'], 120)}: {ins['samples']:,} sample(s) × {ins['epochs']} epoch(s), "
                     f"{ins['max_connections']} at a time; judges (priced at their model, at the agent's endpoint): "
                     f"{judges or 'none'}"
                     + ("." if bound is None else f"; at most {bound:,} billed calls per sample (D-740)."))
    if not scripted and doc["cost_p50"] is not None:
        lines.append(f"Cost: p50 {_money(doc['cost_p50'])}, p90 {_money(doc['cost_p90'])}, worst case (every due "
                     f"attempt at p90) {_money(doc['cost_worst'] or doc['cost_p90'])}; model calls p50 "
                     f"{doc['calls_p50']:,.0f}, p90 {doc['calls_p90']:,.0f}.")
    for title, rows in (("By suite", doc["by_suite"]), ("By attack", doc["by_attack"])):
        lines += ["", f"{title}:"]
        for g in rows:
            cost = "" if scripted or g["cost_p50"] is None else \
                f"  p50 {_money(g['cost_p50'])}  p90 {_money(g['cost_p90'])}"
            lines.append(f"  {safe_text(g['label'], 60):<40} {g['units']:>7,} units{cost}  [{', '.join(g['sources'])}]")
    lines += ["", "Sources of the cell statistics: " + ", ".join(f"{k} {v:,} units" for k, v in doc["sources"].items())]
    lines += [f"Warning: {safe_text(w, 300)}" for w in doc["warnings"]]
    return lines
