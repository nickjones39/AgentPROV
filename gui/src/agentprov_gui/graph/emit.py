"""DOT text for layout only (design §7.1 step 3; S5). No Qt, no pydot.

Built from ``render.style``'s tables and ``dot_quote`` alone: node shapes, pen widths and the default trusted-grammar
labels (so ``dot`` sizes the nodes the way the GUI draws them). There are **no edge labels** (they multiply ``dot``'s
time, research §M7b; the GUI draws relation names itself), no colours (layout does not need them), and no ``URL``,
``href``, ``tooltip``, ``image`` or ``shapefile`` attribute: those names do not occur in this module. Node ids are the
model's stable ``n<hex>`` ids; nothing from the document reaches the text except through the trusted label grammars.

Components are packed (``pack``, ``packmode=graph``): without it the many unconnected core nodes of a large document
stack into one column (measured 1,130 × 13,317 pt for the largest agentdyn document; 3,188 × 3,152 pt packed).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from agentprov.render import style

from agentprov_gui.graph.viewgraph import ViewGraph

__all__ = ["FAST_FLAGS", "FAST_FLAGS_ABOVE", "build_layout_dot"]

#: ``dot`` flags that bound its crossing minimisation and network simplex (research §M7, §M7b), used above 300 nodes.
FAST_FLAGS: Final = ("-Gnslimit=2", "-Gnslimit1=2", "-Gmclimit=0.2", "-Gremincross=false")
FAST_FLAGS_ABOVE: Final = 300


def _attrs(values: Mapping[str, str]) -> str:
    return ", ".join(f"{k}={style.dot_quote(v)}" for k, v in values.items())


def build_layout_dot(view: ViewGraph, ids: Mapping[str, str], *, direction: str = "LR") -> str:
    """The DOT text that lays out ``view``'s laid-out nodes and edges (overlay edges are not sent)."""
    if direction not in ("LR", "TB"):
        raise ValueError("direction is LR or TB")
    lines = [
        "digraph prov {",
        f"  graph [rankdir={direction}, fontname=\"Helvetica\", nodesep=0.25, ranksep=0.6, pack=true, "
        'packmode="graph"];',
        '  node [fontname="Helvetica", fontsize=10, margin="0.08,0.04"];',
        "  edge [arrowsize=0.7];",
    ]
    for vnode in view.nodes:
        n = vnode.node
        attrs = style.node_attrs(n.section, n.cls, n.kind, integrity=n.integrity, role=n.role)
        layout_attrs = {"shape": attrs["shape"], "penwidth": attrs["penwidth"], "label": "\n".join(vnode.lines)}
        lines.append(f"  {ids[vnode.key]} [{_attrs(layout_attrs)}];")
    for edge in view.laid_out_edges:
        lines.append(f"  {ids[edge.src]} -> {ids[edge.dst]};")
    lines.append("}")
    return "\n".join(lines) + "\n"
