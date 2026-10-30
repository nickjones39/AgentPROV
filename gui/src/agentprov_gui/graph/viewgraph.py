"""From a :class:`~agentprov.render.graph.GraphModel` to what the graph view lays out and draws (design §7.1, §7.2). No Qt.

One model is built per document (``render.graph.build_model(doc, mode="all")``: validated first, pure). Two views
are derived from it:

* **overlay** (the default): the *layout set* is the core bundle's nodes plus the endpoints that core relations name
  (ghosts included), laid out once by ``dot``. Inference relations between placed nodes are drawn as overlay edges.
  Every other node (assessment mentions and claims, inference-only elements) is **folded** onto the first placed node it
  is connected to, shown as a badge with a count; a badge can be expanded into a local fan without re-laying out.
  Nodes with no placed neighbour are listed as unplaced (Elements list).
* **full**: every node is laid out by the GUI's layered engine (``dot`` is impractical for all-bundle documents,
  research §M7b). With "collapse mentions" on, assessment mentions are folded onto their subjects first.

Every label line comes from ``render.style``'s trusted grammars (S5); nothing data-derived is ever put in a label.
Attribute values reach the screen only through the popover and the PROV-JSON tab, escaped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.render import style
from agentprov.render.graph import DrawEdge, DrawNode, GraphModel

__all__ = ["VEdge", "VNode", "ViewGraph", "full_view", "label_lines", "overlay_view"]

OUTSIDE_TAG: Final = "(declared outside the drawn bundles)"


def label_lines(node: DrawNode) -> tuple[str, ...]:
    """The default label of ``node`` (``render.style.node_label`` without content): trusted grammars only (S5)."""
    tags: list[str] = []
    if node.integrity is not None:
        tags.append(f"integrity: {node.integrity}")
    if node.role is not None:
        tags.append(f"role: {node.role}")
    if node.bundle is None:
        tags.append(OUTSIDE_TAG)
    text = style.node_label(node.key, node.section, node.attrs, cls=node.cls, tags=tuple(tags), show_content=False)
    return tuple(text.split("\n"))


@dataclass(frozen=True, slots=True)
class VNode:
    key: str  # the PROV identifier (data: displayed only through text.line)
    node: DrawNode
    lines: tuple[str, ...]  # the trusted-grammar label lines
    folded: tuple[str, ...] = ()  # keys folded onto this node (badge)

    @property
    def section(self) -> str:
        return self.node.section

    @property
    def kind(self) -> str | None:
        return self.node.kind

    @property
    def cls(self) -> str | None:
        return self.node.cls


@dataclass(frozen=True, slots=True)
class VEdge:
    src: str
    dst: str
    relation: str  # a PROV-JSON relation name or a claim-link attribute name (closed vocabularies)
    kind: str  # core | inference | assessment
    cls: str | None
    link: bool
    overlay: bool  # drawn over the layout, not laid out


@dataclass(slots=True)
class ViewGraph:
    model: GraphModel
    nodes: list[VNode]  # the laid-out nodes, in model order
    edges: list[VEdge]  # laid-out edges, then overlay edges
    folded: dict[str, list[str]] = field(default_factory=dict)  # anchor key -> folded keys
    unplaced: list[str] = field(default_factory=list)
    by_key: dict[str, DrawNode] = field(default_factory=dict)  # every node of the model

    @property
    def laid_out_edges(self) -> list[VEdge]:
        return [e for e in self.edges if not e.overlay]

    def anchor_of(self) -> dict[str, str]:
        return {k: a for a, ks in self.folded.items() for k in ks}


def _vedge(e: DrawEdge, overlay: bool) -> VEdge:
    return VEdge(e.src, e.dst, e.relation, e.kind, e.cls, e.link, overlay)


def _fold(
    placed: set[str],
    rest: Sequence[DrawNode],
    edges: Sequence[DrawEdge],
    prefer: Mapping[str, str] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Fold each node of ``rest`` onto its first placed neighbour (``prefer`` first: a mention's subject). Folding is
    transitive through already-folded nodes (a claim that names a mention lands on the mention's anchor)."""
    neighbours: dict[str, list[str]] = {}
    for e in edges:
        neighbours.setdefault(e.src, []).append(e.dst)
        neighbours.setdefault(e.dst, []).append(e.src)
    anchor: dict[str, str] = {}
    pending = [n.key for n in rest]
    for _ in range(3):  # a few passes settle chains (claim -> mention -> subject)
        left: list[str] = []
        for key in pending:
            target = None
            if prefer and prefer.get(key) in placed:
                target = prefer[key]
            else:
                for other in neighbours.get(key, ()):
                    if other in placed:
                        target = other
                        break
                    if other in anchor:
                        target = anchor[other]
                        break
            if target is None:
                left.append(key)
            else:
                anchor[key] = target
        pending = left
        if not pending:
            break
    folded: dict[str, list[str]] = {}
    for key, target in anchor.items():
        folded.setdefault(target, []).append(key)
    for keys in folded.values():
        keys.sort()
    return folded, sorted(pending)


def _mention_subjects(model: GraphModel) -> dict[str, str]:
    return {e.src: e.dst for e in model.edges if e.relation == "mentionOf" and e.kind == "assessment"}


def overlay_view(model: GraphModel) -> ViewGraph:
    """The default view (see the module docstring)."""
    core_edges = [e for e in model.edges if e.kind == "core"]
    placed: set[str] = {n.key for n in model.nodes if n.kind == "core"}
    for e in core_edges:
        placed.update((e.src, e.dst))
    by_key = {n.key: n for n in model.nodes}
    nodes = [n for n in model.nodes if n.key in placed]
    rest = [n for n in model.nodes if n.key not in placed]
    folded, unplaced = _fold(placed, rest, model.edges, _mention_subjects(model))
    vnodes = [VNode(n.key, n, label_lines(n), tuple(folded.get(n.key, ()))) for n in nodes]
    overlay = [
        _vedge(e, True) for e in model.edges
        if e.kind != "core" and e.src in placed and e.dst in placed and e.relation != "mentionOf"
    ]  # fmt: skip
    edges = [_vedge(e, False) for e in core_edges] + overlay
    return ViewGraph(model, vnodes, edges, folded, unplaced, by_key)


def full_view(model: GraphModel, *, collapse_mentions: bool = True) -> ViewGraph:
    """Every node laid out (layered engine), mentions folded onto their subjects when ``collapse_mentions``."""
    by_key = {n.key: n for n in model.nodes}
    subjects = _mention_subjects(model) if collapse_mentions else {}
    mentions = {k for k, v in subjects.items() if v in by_key and v not in subjects}
    nodes = [n for n in model.nodes if n.key not in mentions]
    placed = {n.key for n in nodes}
    folded, unplaced = _fold(placed, [by_key[k] for k in sorted(mentions)], model.edges, subjects)
    vnodes = [VNode(n.key, n, label_lines(n), tuple(folded.get(n.key, ()))) for n in nodes]
    edges = [_vedge(e, False) for e in model.edges if e.src in placed and e.dst in placed]
    return ViewGraph(model, vnodes, edges, folded, unplaced, by_key)


def attribute_rows(node: DrawNode) -> list[tuple[str, Any]]:
    """The node's attributes in name order (for the popover; values are data and escaped by the view)."""
    return sorted(((str(k), v) for k, v in node.attrs.items()), key=lambda kv: kv[0])
