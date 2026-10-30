"""Typed errors of ``agentprov render`` (MN N.1.3, N.2.13; K.5.12).

Every error carries a stable code and the CLI exit code of N.1.3: a missing extra or binary is ``environment`` (3), an
input that is not a valid ``agentprov-prov/0.1`` document is ``failures`` (1), and an output location inside a corpus is
a ``refused`` write (4). Messages hold codes, limits and ids only, never source text.
"""

from __future__ import annotations

from agentprov.errors import AgentProvError

__all__ = [
    "EXTRA_HINT",
    "RenderCorpusError",
    "RenderEnvironmentError",
    "RenderError",
    "RenderInputError",
    "RenderOutputRefusedError",
    "RenderProcessError",
    "RenderTooLargeError",
]

#: The hint the missing-extra error carries (MN N.2.13).
EXTRA_HINT = "uv sync --frozen --group docs --extra render"  # names the docs group: uv sync is exact


class RenderError(AgentProvError):
    """Base of the render errors."""

    code = "render.error"
    exit_code = 1


class RenderEnvironmentError(RenderError):
    """The ``render`` extra (``pydot``) or the Graphviz ``dot`` binary is missing (exit 3)."""

    code = "render.environment"
    exit_code = 3


class RenderCorpusError(RenderError):
    """The corpus (or one of its files) cannot be read as an AgentPROV corpus (exit 1)."""

    code = "render.corpus_unreadable"
    exit_code = 1


class RenderInputError(RenderError):
    """The PROV document cannot be drawn: it is not valid PROV-JSON of ``agentprov-prov/0.1`` (exit 1)."""

    code = "render.invalid_prov"
    exit_code = 1


class RenderProcessError(RenderError):
    """``dot`` failed, timed out or produced more than the output cap (exit 1)."""

    code = "render.dot_failed"
    exit_code = 1


class RenderTooLargeError(RenderProcessError):
    """The graph is over the image layout limit, so ``dot`` is not started (exit 1; the ``.dot`` text is written)."""

    code = "render.graph_too_large"
    exit_code = 1


class RenderOutputRefusedError(RenderError):
    """The output directory is inside a corpus (exit 4; G8: renders stay outside every corpus)."""

    code = "render.output_in_corpus"
    exit_code = 4
