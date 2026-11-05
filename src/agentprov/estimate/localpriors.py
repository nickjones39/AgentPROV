"""Estimate priors: the table rows and their document, shipped or local (D-1062).

**One builder for both tables.** :func:`build_rows` and :func:`document_bytes` turn execution counts into the
``agentprov-estimate-priors/0.1`` document. ``tools/estimate/gen_estimate_priors.py`` uses them for the shipped table
(``data/estimate_priors.json``), and ``agentprov priors build`` uses them for the local one
(``$AGENTPROV_HOME/estimate/priors-local.json``), so the two cannot drift apart. Both moved here unchanged from the tool:
the shipped table rebuilds byte for byte from the same inputs (``tests/estimate/test_local_priors.py``).

**Local priors** are built from the user's sealed corpora by ``agentprov priors build``: the corpora are read in
:mod:`agentprov.cli.priors_read` (a corpus is above this layer), which hands :func:`local_document` the counts.

**Untrusted corpus text.** Only counts are kept (:func:`agentprov.estimate.usage.usage_from_records`); the model id
becomes a family label through :func:`~agentprov.estimate.usage.model_family`, and an execution whose benchmark, suite,
attack or backend is not a plain label (:data:`LABEL`, :func:`plain_labels`) is left out. A corpus id and version go
into ``built_from`` only when they are plain labels too (:func:`label`).

**Determinism.** The document has no time and no worker count in it: the same corpora give the same bytes, whatever
``jobs`` is (the executions are counted in index order, and every quantile is order-free).

Outside every stage closure (class 0): nothing here feeds AER, SEM, PROV or a corpus.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError

from agentprov.estimate.usage import CHARS_PER_TOKEN, ExecutionUsage, aggregate

__all__ = [
    "LABEL",
    "LOCAL_PRIORS",
    "LOCAL_TOOL",
    "PriorsBuildError",
    "build_rows",
    "corpora_of",
    "document_bytes",
    "label",
    "local_document",
    "local_priors_path",
    "plain_labels",
    "write_local",
]

#: ``$AGENTPROV_HOME/estimate/<this>``
LOCAL_PRIORS: Final = "priors-local.json"
LOCAL_TOOL: Final = "agentprov priors build"
#: a benchmark, suite, attack, backend, corpus id or version kept in a priors table (the shipped table's test pins the
#: same grammar)
LABEL: Final = re.compile(r"[A-Za-z0-9_./:@+-]{1,120}")


class PriorsBuildError(AgentProvError):
    """A corpus the local priors will not be built from (the message names the reason, never corpus text). Exit 2."""

    code = "estimate.priors.refused"
    exit_code = 2


def local_priors_path(home: Path) -> Path:
    return Path(home) / "estimate" / LOCAL_PRIORS


# ------------------------------------------------------------------------------------------------ rows and document
def build_rows(usages: list[ExecutionUsage], min_executions: int) -> dict[tuple[str, ...], dict[str, Any]]:
    """The table rows: per key, this model family on this backend, this family on any backend, any model on this
    backend and any model anywhere. ``aggregate`` keys an execution without a model family (or without a backend) under
    ``""``, the key of the any-model (any-backend) row, so the per-family (per-backend) passes skip those keys: the
    executions are counted in the wider row, which must hold every execution, never only the ones without a family."""
    rows: dict[tuple[str, ...], dict[str, Any]] = {}
    for with_model in (True, False):
        for with_backend in (True, False):
            for (bench, suite, attack, family, backend), stats in sorted(aggregate(
                    usages, with_model=with_model, with_backend=with_backend,
                    min_executions=min_executions).items()):
                if (with_model and not family) or (with_backend and not backend):
                    continue
                key = (bench, suite, attack, family, backend)
                if key in rows:  # each pass yields its own key shape; a collision is a bug, never a silent overwrite
                    raise RuntimeError(f"estimate priors: two rows for {key}")
                rows[key] = {"benchmark": bench, "suite": suite, "attack": attack or None, "family": family or None,
                             "backend": backend or None, **stats.to_json()}
    return rows


def document_bytes(built_from: Mapping[str, Any], rows: Mapping[tuple[str, ...], Mapping[str, Any]]) -> bytes:
    """The ``agentprov-estimate-priors/0.1`` document: the header on the first line, one row per line, sorted by key."""
    from agentprov.estimate.priors import PRIORS_FORMAT

    doc = {"format": PRIORS_FORMAT, "built_from": dict(built_from)}
    head = json.dumps(doc, sort_keys=True, separators=(",", ":"))[:-1]
    lines = [json.dumps(rows[k], sort_keys=True, separators=(",", ":")) for k in sorted(rows)]
    return (head + ',"rows":[\n' + ",\n".join(lines) + "\n]}\n").encode("utf-8")

# ------------------------------------------------------------------------------------------------ local priors
def label(value: Any) -> str | None:
    """``value`` when it is a plain label (:data:`LABEL`), else ``None``."""
    return value if isinstance(value, str) and LABEL.fullmatch(value) else None


def plain_labels(u: ExecutionUsage) -> bool:
    """Whether an execution's benchmark, suite, attack and backend are plain labels (or absent)."""
    return all(v is None or LABEL.fullmatch(v) for v in (u.benchmark, u.suite, u.attack, u.backend))


def local_document(usages: list[ExecutionUsage], corpora: Sequence[Mapping[str, Any]],
                   skipped: Sequence[Mapping[str, Any]], min_executions: int) -> tuple[bytes, dict[str, Any]]:
    """The local priors document and its ``built_from``: no time and no worker count, so the same corpora give the
    same bytes."""
    from agentprov.versions import __version__

    rows = build_rows(usages, min_executions)
    built_from = {"tool": LOCAL_TOOL, "agentprov": __version__, "chars_per_token": CHARS_PER_TOKEN,
                  "min_executions": min_executions, "corpora": [dict(c) for c in corpora],
                  "skipped": [dict(s) for s in skipped], "rows": len(rows), "executions": len(usages)}
    return document_bytes(built_from, rows), built_from


def write_local(home: Path, data: bytes) -> Path:
    """Write the local priors atomically (a reader sees the old file or the new one, never a part)."""
    from agentprov.io.replace_retry import atomic_write_bytes_retrying

    path = local_priors_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes_retrying(path, data)
    return path


def corpora_of(header: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The corpora a priors file names in ``built_from`` (``load_priors``'s header), with every value checked: the
    file is the user's and may have been edited, so only plain labels, sha256 digests and counts are kept."""
    built = header.get("built_from")
    corpora = built.get("corpora") if isinstance(built, Mapping) else None
    out: list[dict[str, Any]] = []
    for c in corpora if isinstance(corpora, list) else []:
        if not isinstance(c, Mapping):
            continue
        sha = c.get("manifest_sha256")
        n = c.get("executions_read")
        out.append({"corpus_id": label(c.get("corpus_id")), "corpus_version": label(c.get("corpus_version")),
                    "manifest_sha256": sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha) else None,
                    "executions_read": n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None})
    return out
