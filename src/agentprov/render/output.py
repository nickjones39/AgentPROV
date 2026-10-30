"""Where renders go (MN N.2.13; guard G8; HL consumers; K.5.12 item 6).

A render is a derived view, not corpus content: it is written beside the corpus, never into it, and never into any other
corpus either. The default is ``<corpus>-rendered/`` (``<corpus>.partial`` of a working corpus gives the same name), kept
out of git by the ``*-rendered/`` ignore rule; ``--out DIR`` replaces it. Below the output directory the layout mirrors
the corpus' PROV tree: ``<spec_dir>/<ss>/<ex>.<ext>``.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from agentprov.corpus.layout import PARTIAL_SUFFIX, assert_writable
from agentprov.render.errors import RenderError, RenderOutputRefusedError

__all__ = ["RenderOutputRequiredError", "assert_output_allowed", "default_output_dir", "output_stem"]


class RenderOutputRequiredError(RenderError):
    """No default output directory exists for this corpus path (the filesystem root); ``--out`` is required (exit 2)."""

    code = "render.output_required"
    exit_code = 2


def default_output_dir(corpus_root: str | os.PathLike[str]) -> Path:
    """``<corpus>-rendered`` beside the corpus (the ``.partial`` suffix of a working tree is dropped).

    The name comes from the resolved path, so ``.``, ``..`` and ``C/sub/..`` name the corpus directory itself rather than
    a ``..-rendered`` child of it (or nothing at all).
    """
    root = Path(os.path.realpath(corpus_root))
    if not root.name:
        raise RenderOutputRequiredError("the corpus is the filesystem root, which has no sibling directory; use --out DIR")
    name = root.name[: -len(PARTIAL_SUFFIX)] if root.name.endswith(PARTIAL_SUFFIX) else root.name
    return root.with_name(name + "-rendered")


def assert_output_allowed(out: str | os.PathLike[str], corpus_root: str | os.PathLike[str]) -> Path:
    """Refuse (exit 4) an output directory inside the corpus being rendered or inside any other corpus.

    The check is on the resolved paths, so a symlink into a corpus is caught. A sealed corpus above the output raises
    :class:`agentprov.corpus.layout.SealedCorpusError` (H.1.5(2)); any ancestor that holds a ``corpus.json`` (a working
    corpus too) or the corpus root itself raises :class:`RenderOutputRefusedError`. So does the corpus' twin: the final
    directory ``<C>`` that a working ``<C>.partial`` is swapped into at seal (it must not exist before then, or the
    working corpus can be neither resumed nor sealed), and an existing ``<C>.partial`` beside a corpus root ``<C>``.
    Returns the resolved output path.
    """
    resolved = Path(os.path.realpath(out))
    root = Path(os.path.realpath(corpus_root))
    assert_writable(resolved)  # SealedCorpusError: a sealed corpus is closed-world
    refused = {root}
    if root.name.endswith(PARTIAL_SUFFIX) and len(root.name) > len(PARTIAL_SUFFIX):
        refused.add(root.with_name(root.name[: -len(PARTIAL_SUFFIX)]))
    elif root.name and (twin := root.with_name(root.name + PARTIAL_SUFFIX)).exists():
        refused.add(Path(os.path.realpath(twin)))
    for directory in (resolved, *resolved.parents):
        if directory in refused or (directory / "corpus.json").exists() or (directory / "executions.jsonl").exists():
            raise RenderOutputRefusedError(
                "refusing to write renders inside a corpus; use --out DIR outside every corpus (guard G8)",
                code="render.output_in_corpus",
            )
    return resolved


def output_stem(out: Path, prov_label: str, *, spec_dir: str) -> Path:
    """``<out>/<spec_dir>/<ss>/<ex>`` (no extension) for the corpus path ``prov/<spec_dir>/<ss>/<ex>.prov.json``."""
    parts = PurePosixPath(prov_label).parts
    if len(parts) < 4 or parts[0] != "prov" or parts[1] != spec_dir or not parts[-1].endswith(".prov.json"):
        raise ValueError("not a PROV path of the layout")
    return out.joinpath(*parts[1:-1], parts[-1][: -len(".prov.json")])

