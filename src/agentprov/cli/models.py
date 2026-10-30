"""``agentprov models``: the models a running local server serves, and the observed identity of one (D-691, D-692).

Read-only and loopback-only (:mod:`agentprov.cli.live.localmodels`): no inference, no model load, no credential. The
GUI's Run live model picker calls this command (``--format json``) and has no discovery code of its own (D-654).

* no option: every ``local = true`` endpoint of ``endpoints.toml``, up or down, with its models;
* ``--endpoint NAME`` or ``--base-url URL`` (loopback): that server only (unreachable: exit 3; the wrong server kind
  for the shorthand, or a non-loopback URL: exit 4);
* ``--model-id ID``: the ``agentprov-local-model/0.2`` identity record ``run`` would record (not served: exit 3, with
  the served ids; a model the server marks remote: exit 4). Weight files are hashed unless ``--no-hash-weights``;
  digests are cached in ``$AGENTPROV_HOME/cache/model-digests.jsonl``.

``--format json`` puts the document (``agentprov-local-models/0.1`` or ``agentprov-local-model/0.2``) on stdout, as
``info --format json`` does.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import Any, Final

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text

__all__ = ["MODELS_ENDPOINTS", "register", "run_models"]

#: ``--endpoint`` choices: the local shorthands (D-690) and the API providers with a model list (D-730). Tests keep
#: both equal to the registry.
MODELS_ENDPOINTS: Final = ("anthropic", "deepseek", "gemini", "glm", "llama", "openai", "openrouter", "qwen",
                           "llamacpp", "lmstudio", "mlx_lm", "ollama", "omlx", "vllm")


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "models",
        parents=[shared],
        help="list the models a local server serves (and one model's observed identity), or an API provider's list",
        description="Local model servers (loopback only; read-only, no inference): the models each local endpoint of "
        "endpoints.toml serves, or one server's, and with --model-id the identity record a live run records (D-691). "
        "API providers (D-730): the dated cached model list; --allow-network fetches it now (no tokens, no cost).",
        allow_abbrev=False,
    )
    p.set_defaults(command="models", handler=run_models, feedback=False)
    p.add_argument("--endpoint", metavar="NAME", choices=MODELS_ENDPOINTS,
                   help="an endpoint shorthand: local (ollama, omlx, lmstudio, mlx_lm, llamacpp, vllm) or an API "
                        "provider (openrouter, anthropic, openai, deepseek, gemini, llama, qwen, glm)")
    p.add_argument("--base-url", metavar="URL", help="a loopback base URL (overrides the endpoint's; the server kind "
                   "is fingerprinted)")
    p.add_argument("--model-id", metavar="ID", help="show the observed identity of this served model")
    p.add_argument("--model-dir", metavar="PATH", help="the model's directory or file, where the server does not name "
                   "it (oMLX, llama.cpp); hashed, never parsed")
    p.add_argument("--no-hash-weights", action="store_true", help="record weight files by size only (weights_hashed false)")
    p.add_argument("--find-folders", action="store_true",
                   help="with --model-id: list the folders on this machine that may hold the model's files (oMLX, the "
                        "Hugging Face cache, LM Studio; names only, nothing opened, no server contacted; D-828)")
    p.add_argument("--allow-lan-endpoint", action="store_true",
                   help="allow --base-url on a literal private LAN address (D-698; data leaves this machine)")
    provider = p.add_argument_group("API providers (D-730..D-735)")
    provider.add_argument("--allow-network", action="store_true",
                          help="fetch the provider's model list now (R2; the provider's registry host only) and cache it")
    provider.add_argument("--refresh-if-stale", action="store_true",
                          help="fetch only when the setting models.auto_refresh is on and the cached list is older than "
                               "24 h; otherwise show the cache")
    provider.add_argument("--keychain", action="store_true",
                          help="read the endpoint's key from the OS keychain (D-702): an API provider's, or a local "
                               "server's optional key (D-827); exclusive with --env-file/--env-stdin")
    provider.add_argument("--env-file", metavar="PATH", help="read the endpoint's key variable from this .env file")
    provider.add_argument("--env-stdin", action="store_true",
                          help="read the endpoint variables as one JSON object from stdin (D-395)")
    p.add_argument("--format", choices=["text", "json"], default="text", help="payload format (default text)")


def _gb(n: Any) -> str:
    return f"{n / 1e9:.1f} GB" if isinstance(n, int) else "-"


def _row_line(row: Mapping[str, Any]) -> str:
    flags = [f for f, on in (("loaded", row.get("loaded")), ("tools", row.get("tool_use")), ("REMOTE", row.get("remote")),
                             ("not-served", not row.get("servable"))) if on]
    facts = " ".join(safe_text(str(row[k]), 40) for k in ("architecture", "family", "params", "quantization", "format")
                     if row.get(k) is not None)
    return f"  {safe_text(row['id'], 120)}  {facts}  {_gb(row.get('size_bytes'))}" + (f"  [{', '.join(flags)}]" if flags else "")


def _identity_lines(rec: Mapping[str, Any]) -> list[str]:
    server = rec.get("server") or {}
    lines = [f"model {safe_text(str(rec.get('model_id')), 160)} on {safe_text(str(rec.get('endpoint') or '-'), 40)} "
             f"({safe_text(str(rec.get('base_url')), 120)})",
             f"  server {safe_text(str(server.get('kind')), 30)} version {safe_text(str(server.get('version') or '-'), 60)}",
             f"  identity {rec.get('identity_sha256')}"]
    for key, value in sorted((rec.get("server_identity") or {}).items()):
        lines.append(f"  {key}: {safe_text(str(value), 160)}")
    files = rec.get("files")
    if files:
        lines.append(f"  files ({safe_text(files['method'], 20)}) {safe_text(files['label'], 160)}"
                     + (f" @ {files['snapshot_commit']}" if files.get("snapshot_commit") else "")
                     + ("" if files.get("weights_hashed") else "  (weights not hashed)"))
        for f in files["files"]:
            lines.append(f"    {safe_text(f['name'], 160)}  {f['size']}  {f.get('sha256') or '-'} ({f['sha256_source']})")
        for problem in files.get("problems", []):
            lines.append(f"    problem: {safe_text(problem, 60)}")
    else:
        lines.append(f"  files: none ({safe_text(str(rec.get('files_reason')), 80)})")
    return lines


def run_models(ctx: Context) -> CommandResult:
    from agentprov.cli.live import envs, localmodels as lm
    from agentprov.io.canonical import jcs_bytes

    args = ctx.args
    if args.find_folders:
        return _find_folders(ctx)
    if args.model_id is not None and args.endpoint is None and args.base_url is None:
        raise CliUsageError("agentprov models: --model-id needs --endpoint or --base-url")
    if (args.model_dir or args.no_hash_weights) and args.model_id is None:
        raise CliUsageError("agentprov models: --model-dir and --no-hash-weights go with --model-id")
    from agentprov.cli.live import providermodels as pm

    provider = args.endpoint in pm.PROVIDER_ENDPOINTS
    key_flags = [f for f, on in (("--keychain", args.keychain), ("--env-file", args.env_file),
                                 ("--env-stdin", args.env_stdin)) if on]
    provider_flags = [f for f, on in (("--allow-network", args.allow_network),
                                      ("--refresh-if-stale", args.refresh_if_stale)) if on]
    if key_flags and not provider and _local_key_variable(args.endpoint) is None:
        raise CliUsageError(f"agentprov models: {', '.join(key_flags)} go with an API provider --endpoint, or a local "
                            "one that has a key setting (api_key_env, D-827)")
    if provider_flags and not provider:
        raise CliUsageError(f"agentprov models: {', '.join(provider_flags)} go with an API provider --endpoint")
    if provider:
        local_flags = [f for f, on in (("--base-url", args.base_url), ("--model-dir", args.model_dir),
                                       ("--no-hash-weights", args.no_hash_weights),
                                       ("--allow-lan-endpoint", args.allow_lan_endpoint)) if on]
        if local_flags:
            raise CliUsageError(f"agentprov models: {', '.join(local_flags)} go with a local endpoint")
        return _provider_models(ctx)
    result = CommandResult()
    document: dict[str, Any]
    if args.endpoint is None and args.base_url is None:
        entries = []
        for shorthand, entry in lm.local_endpoints().items():
            url, _source = lm.configured_base_url(entry)  # D-699: the user's setting, else the registry default
            try:
                key = _local_key(ctx, shorthand, result) if entry.api_key_env and not args.allow_lan_endpoint else None
                entries.append(lm.listing_entry(lm.list_server(url, endpoint=shorthand, expected_kind=entry.server,
                                                               allow_lan=args.allow_lan_endpoint, api_key=key)))
            except lm.LocalModelError as exc:
                entries.append(lm.down_entry(shorthand, url, entry.server, exc))
        document = lm.listing_document(entries)
        up = [e for e in entries if e["status"] == "up"]
        result.counters = {"endpoints": len(entries), "up": len(up), "models": sum(len(e["models"]) for e in up)}
    else:
        try:
            name, base_url, kind = lm.resolve_local(args.endpoint, args.base_url, allow_lan=args.allow_lan_endpoint)
        except lm.LocalModelError as exc:
            if exc.exit_code == 2:
                raise CliUsageError(f"agentprov models: {exc}") from None
            raise
        key = _local_key(ctx, name, result) if name is not None and _local_key_variable(name) else None
        listing = lm.list_server(base_url, endpoint=name, expected_kind=kind, allow_lan=args.allow_lan_endpoint,
                                 api_key=key)
        if listing.lan:
            result.notices.append("LAN endpoint (--allow-lan-endpoint): the server is on another machine")
        if args.model_id is None:
            document = lm.listing_document([lm.listing_entry(listing)])
            result.counters = {"endpoints": 1, "up": 1, "models": len(listing.rows)}
        else:
            cache = lm.DigestCache(envs.agentprov_home(ctx.env) / "cache" / "model-digests.jsonl", writable=True)
            model_dir = args.model_dir
            if model_dir is None and name is not None:  # D-828: flag > the setting (Settings › Local models)
                from agentprov.cli.run import model_settings, setting_model_dir

                stored, label = model_settings(name, args.model_id)
                model_dir = setting_model_dir(stored, label)
                if model_dir is not None:
                    result.notices.append(f"model folder from the setting {label}model_dir (D-828)")
            document = lm.model_identity(listing, args.model_id, environ=ctx.env, model_dir=model_dir,
                                         hash_weights=not args.no_hash_weights, cache=cache, api_key=key)
            result.counters = {"files": len((document.get("files") or {}).get("files", []))}
    if args.format == "json":
        text = jcs_bytes(document) + b"\n"
    else:
        lines: list[str] = []
        if document["format"] == lm.IDENTITY_FORMAT:
            lines = _identity_lines(document)
        else:
            for e in document["endpoints"]:
                server = e["server"]
                head = f"{safe_text(str(e['endpoint'] or '-'), 40)}  {safe_text(e['base_url'], 120)}  {e['status']}"
                if e["status"] == "up":
                    head += f"  {safe_text(str(server['kind_observed']), 30)} {safe_text(str(server['version'] or ''), 60)}"
                    head += f"  {len(e['models'])} model(s)"
                else:
                    head += f" ({e['reason']})"
                lines.append(head)
                lines.extend(_row_line(r) for r in e["models"])
        text = ("\n".join(lines) + "\n").encode("utf-8")
    if args.json:
        for line in text.decode("utf-8").splitlines():
            result.info(line)
    else:
        result.payload = text
    return result


# ---------------------------------------------------------------------------------------------- folders (D-828)


def _find_folders(ctx: Context) -> CommandResult:
    """``--find-folders --model-id ID``: candidate folders of a model (the GUI's Find Folder), with the folder the
    setting names, if any. Read-only: directory listings only; no server, keychain or network."""
    from agentprov.cli.live import localmodels as lm
    from agentprov.cli.run import model_settings
    from agentprov.io.canonical import jcs_bytes

    args = ctx.args
    if args.model_id is None:
        raise CliUsageError("agentprov models: --find-folders needs --model-id")
    others = [f for f, on in (("--base-url", args.base_url), ("--model-dir", args.model_dir),
                              ("--no-hash-weights", args.no_hash_weights), ("--allow-network", args.allow_network),
                              ("--refresh-if-stale", args.refresh_if_stale), ("--keychain", args.keychain),
                              ("--env-file", args.env_file), ("--env-stdin", args.env_stdin)) if on]
    if others:
        raise CliUsageError(f"agentprov models: --find-folders lists folders only; {', '.join(others)} do not apply")
    if args.endpoint is not None and args.endpoint not in lm.local_endpoint_names():
        raise CliUsageError("agentprov models: --find-folders is for a local endpoint's model")
    stored, _label = model_settings(args.endpoint, args.model_id) if args.endpoint else ({}, None)
    folders = lm.find_model_folders(args.model_id, environ=ctx.env)
    document = {"format": lm.FOLDERS_FORMAT, "endpoint": args.endpoint, "model_id": args.model_id,
                "setting": stored.get("model_dir"), "folders": folders}
    result = CommandResult()
    result.counters = {"folders": len(folders)}
    if args.format == "json":
        text = jcs_bytes(document) + b"\n"
    else:
        lines = [f"{safe_text(args.model_id, 200)}: {len(folders)} folder(s)"
                 + (f"; setting: {safe_text(str(stored['model_dir']), 300)}" if stored.get("model_dir") else "")]
        lines += [f"  {safe_text(f['path'], 300)}  ({f['source']})" for f in folders]
        text = ("\n".join(lines) + "\n").encode("utf-8")
    if args.json:
        for line in text.decode("utf-8").splitlines():
            result.info(line)
    else:
        result.payload = text
    return result


# ---------------------------------------------------------------------------------------------- local keys (D-827)


def _local_key_variable(endpoint: str | None) -> str | None:
    """A local entry's optional key variable (``api_key_env``, D-827); ``None`` for any other endpoint."""
    from agentprov.cli.live.localmodels import local_key_variable

    return local_key_variable(endpoint)


def _local_key(ctx: Context, endpoint: str, result: CommandResult) -> str | None:
    """A local server's optional key (D-827), from the same sources as a provider's (D-702: the keychain first, then
    ``.env``; or only the source an option names). Not found is a notice, never an error: the server is then asked
    without a key, as before. The value is registered for redaction; only the variable's name is ever shown."""
    from agentprov.cli.live.envs import RepositoryRootMissing
    from agentprov.cli.run import LiveEnvironmentError

    variable = _local_key_variable(endpoint)
    if variable is None:
        return None
    try:
        found = _endpoint_keys(ctx, endpoint, variable, result)
    except (LiveEnvironmentError, RepositoryRootMissing) as exc:  # no 'live' extra for .env, no checkout, no keychain
        result.notices.append(f"key {variable}: not read ({exc.code}); the server is asked without a key")
        return None
    if not found.get(variable):
        result.notices.append(f"key {variable}: not set; the server is asked without a key (optional, D-827)")
        return None
    return found[variable]


# ---------------------------------------------------------------------------------------------- API providers (D-730)


def _provider_keys(ctx: Context, endpoint: str, result: CommandResult) -> dict[str, str]:
    """The provider's key variable, registered for redaction at once (D-731; user decision 2026-10-22: the keychain is
    the source of truth). With no option: the OS keychain first (D-702), then the default ``.env`` when the keychain
    holds no such key or cannot be read. ``--keychain`` reads only the keychain; ``--env-file`` / ``--env-stdin`` only
    those. Which source supplied the key is a notice (never the value). OpenRouter's list is public: its key is read
    only when the caller passes one of the options."""
    from agentprov.cli.live import providermodels as pm

    args = ctx.args
    variable, required = pm.key_variable(endpoint)
    explicit = bool(args.keychain or args.env_file or args.env_stdin)
    if variable is None or (not required and not explicit):
        return {}  # OpenRouter's list is public: its key is read only when the caller asks for it
    return _endpoint_keys(ctx, endpoint, variable, result)


def _endpoint_keys(ctx: Context, endpoint: str, variable: str, result: CommandResult) -> dict[str, str]:
    """``{variable: value}`` from the source the options name, else the keychain first and then ``.env``; ``{}`` when
    no source holds it. Shared by the providers' lists (D-731) and the local servers' optional keys (D-827)."""
    import argparse as _argparse

    from agentprov.cli import run as run_cmd
    from agentprov.cli.common import register_secret
    from agentprov.cli.live import envs

    args = ctx.args
    if sum(map(bool, (args.keychain, args.env_file, args.env_stdin))) > 1:
        raise CliUsageError("agentprov models: --keychain, --env-stdin and --env-file are exclusive")
    explicit = bool(args.keychain or args.env_file or args.env_stdin)
    shim = _argparse.Namespace(model=None, endpoint=endpoint, llm_script=None, env_file=args.env_file,
                               env_stdin=args.env_stdin)
    if args.keychain:
        from_keychain = run_cmd._read_keychain(shim)  # {} only for a local entry's optional key (D-827)
        if from_keychain:
            result.notices.append(f"key {variable}: from the keychain")
        return from_keychain
    if not explicit:  # the keychain is the source of truth; .env is the fallback
        from agentprov.keys import KeychainError, read

        try:
            found = read([variable])
        except KeychainError as exc:
            found = {}
            if exc.code != "keychain.missing":
                result.notices.append(f"the keychain cannot be read ({exc.code}); trying .env")
        if found.get(variable):
            register_secret(found[variable])
            result.notices.append(f"key {variable}: from the keychain")
            return {variable: found[variable]}
    values = run_cmd._read_env_stdin(shim) if args.env_stdin else run_cmd._read_env_file(shim, envs.repository_root())
    key = values.get(variable)
    if key:
        register_secret(key)
        result.notices.append(f"key {variable}: from {'stdin' if args.env_stdin else '.env'}")
        return {variable: key}
    return {}


def _provider_models(ctx: Context) -> CommandResult:
    from agentprov import settings
    from agentprov.cli.live import envs
    from agentprov.cli.live import providermodels as pm

    args = ctx.args
    endpoint = str(args.endpoint)
    home = envs.agentprov_home(ctx.env)
    result = CommandResult()
    cache = pm.read_cache(home, endpoint)
    stale = cache is None or pm.age(cache) > pm.STALE_AFTER
    auto = settings.get("models.auto_refresh") is True
    fetch_now = bool(args.allow_network) or (bool(args.refresh_if_stale) and auto and stale)
    if args.refresh_if_stale and not auto and not args.allow_network:
        result.notices.append("models.auto_refresh is off: showing the cached list (turn it on with 'agentprov settings "
                              "set models.auto_refresh true', or fetch now with --allow-network)")
    source = "cache" if cache is not None else "none"
    refresh_error: str | None = None
    if fetch_now:
        try:
            doc = pm.fetch(endpoint, _provider_keys(ctx, endpoint, result))
        except pm.ProviderModelError as exc:
            if cache is None:
                raise
            refresh_error = exc.code
            result.notices.append(f"the refresh failed ({exc.code}); showing the cached list from {cache['fetched_at']}")
        else:
            pm.write_cache(home, doc)
            cache, source = doc, "network"
    try:
        from agentprov.cli.prices import book

        price_book: Any = book(home)
    except Exception:  # noqa: BLE001 - without a price table every row is no_price, never invented
        price_book = None
        result.notices.append("the price table could not be read: price status is shown as no_price")
    document = pm.document(endpoint, cache, source=source, price_book=price_book, refresh_error=refresh_error)
    if args.model_id is not None:
        row = next((m for m in document["models"] if m["id"] == args.model_id), None)
        document["model"] = row
        if row is None and cache is not None:
            result.notices.append(f"{safe_text(args.model_id, 160)} is not in {endpoint}'s list (lists can lag; a run "
                                  "warns but is not refused)")
    if source == "none":
        result.notices.append(f"no cached model list for {endpoint}: fetch it with --allow-network (R2)")
    result.counters = {"models": len(document["models"]), "not_listed": len(document["not_listed"])}
    if args.format == "json":
        from agentprov.io.canonical import jcs_bytes

        text = jcs_bytes(document) + b"\n"
    else:
        state = "stale" if document["stale"] else "fresh"
        lines = [f"{endpoint}  {safe_text(str(document['host'] or '-'), 80)}  {source}, fetched "
                 f"{document['fetched_at'] or 'never'} ({state})  {len(document['models'])} model(s)"]
        for m in document["models"]:
            extra = " ".join(safe_text(str(m[k]), 40) for k in ("lifecycle", "context_length") if m.get(k) is not None)
            lines.append(f"  {safe_text(m['id'], 160)}  {safe_text(str(m.get('display_name') or ''), 80)}  {extra}  "
                         f"[{m['price_status']}]")
        lines.extend(f"  {safe_text(m['id'], 160)}  [priced; not listed by the provider]" for m in document["not_listed"])
        text = ("\n".join(lines) + "\n").encode("utf-8")
    if args.json:
        for line in text.decode("utf-8").splitlines():
            result.info(line)
    else:
        result.payload = text
    return result
