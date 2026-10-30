"""The graph of one execution: ``render_prov_graph`` ported to ``agentprov-prov/0.1`` (MN N.2.13; K.5.12).

The baseline (``agentdojo_prov/visualize.py:115-185``) loaded a PROV-JSON document through the ``prov`` library, drew it
with ``prov.dot`` and recoloured the nodes. This port reads the *bundled* PROV-JSON of ``agentprov-prov/0.1`` (one
``core`` bundle, optional ``inference`` bundles, optional ``assessment`` bundles) and builds the graph itself, because
``prov.dot`` sets a ``URL`` attribute from every identifier and G.8.6 forbids any link attribute set from data. The
notation is the same (see :mod:`agentprov.render.style`).

Two steps, kept apart so that the first needs no extra:

1. :func:`build_model` validates the document (the tier-4 structure checks, as the baseline validated before drawing)
   and returns a :class:`GraphModel`: sorted nodes and edges with their bundle, evidence class and labels. It is plain
   data and is a pure function of the document and the options.
2. :func:`agentprov.render.dot.build_dot` turns the model into DOT text with ``pydot``, and
   :func:`render_prov_graph` also runs ``dot`` and writes the files.

``bundles="core"`` (the default) draws exactly the elements and relations that the core bundle declares. ``"all"``
adds the inference and assessment bundles, one cluster each, and the assessment overlay (integrity, role, claim links).
Nothing in a model comes from outside the document: no timestamp, no path, no environment.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from agentprov.render import style
from agentprov.render.errors import RenderInputError, RenderTooLargeError
from agentprov.validate._provdoc import ASSESS_RE, INF_RE, ProvView, St
from agentprov.validate.prov_structure import ARG_KIND

__all__ = [
    "BUNDLE_MODES",
    "FORMATS",
    "DrawBundle",
    "DrawEdge",
    "DrawNode",
    "GraphModel",
    "build_model",
    "render_prov_graph",
    "validate_document",
]

BundleMode = Literal["core", "all"]
BUNDLE_MODES: Final = ("core", "all")
#: Output formats: ``dot`` writes the DOT text only (no Graphviz binary needed); the others run ``dot -T<fmt>``.
FORMATS: Final = ("svg", "png", "pdf", "dot")
_SECTION_ORDER: Final = {"entity": 0, "activity": 1, "agent": 2}
_OUTSIDE_NOTE: Final = "(declared outside the drawn bundles)"


@dataclass(frozen=True, slots=True)
class DrawBundle:
    """One drawn bundle: its position, kind and the slug that names it (grammar-checked, never free text)."""

    index: int
    kind: str  # core | inference | assessment
    slug: str

    @property
    def title(self) -> str:
        return f"{self.kind} bundle" + ("" if self.kind == "core" else f" · {self.slug}")


@dataclass(frozen=True, slots=True)
class DrawNode:
    key: str
    section: str  # entity | activity | agent
    bundle: int | None  # DrawBundle.index; None for a node declared outside the drawn bundles
    kind: str | None  # the bundle's kind
    cls: str | None  # O | D | I | None
    attrs: Mapping[str, Any]
    integrity: str | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class DrawEdge:
    relation: str  # a PROV-JSON relation name, or an attribute name (``apv:subject``) for a claim link
    key: str
    src: str
    dst: str
    bundle: int  # DrawBundle.index
    kind: str  # the bundle's kind
    cls: str | None
    link: bool = False  # a claim link of the assessment overlay, not a PROV relation


@dataclass(frozen=True, slots=True)
class GraphModel:
    ex: str
    mode: str
    bundles: tuple[DrawBundle, ...]
    nodes: tuple[DrawNode, ...]
    edges: tuple[DrawEdge, ...]

    @property
    def title(self) -> str:
        scope = "core bundle" if self.mode == "core" else "core, inference and assessment bundles"
        return f"{self.ex} · {scope}"

    def node_ids(self) -> dict[str, str]:
        """Stable DOT ids: ``n`` + 12 hex digits of the key's SHA-256, or ``n<k>`` by sorted position on a collision."""
        ids = {n.key: "n" + hashlib.sha256(n.key.encode("utf-8", "surrogatepass")).hexdigest()[:12] for n in self.nodes}
        if len(set(ids.values())) != len(ids):
            ids = {n.key: f"n{k}" for k, n in enumerate(self.nodes)}
        return ids


# ----------------------------------------------------------------------------------------------- validation
def validate_document(doc: Any) -> ProvView:
    """Parse and validate ``doc`` as PROV-JSON of ``agentprov-prov/0.1``; raise :class:`RenderInputError` otherwise.

    The tier-4 structure checks run first (the baseline validated before drawing, ``visualize.py:136``); the error names
    the failing check ids only, never document text.
    """
    from agentprov.validate import prov_structure

    if not isinstance(doc, dict):
        raise RenderInputError("the PROV document is not a JSON object", code="render.invalid_prov")
    failed = [o.id for o in prov_structure.check(doc) if o.failed]
    if failed:
        raise RenderInputError(
            "the PROV document is not valid agentprov-prov/0.1 PROV-JSON (failed: " + ", ".join(sorted(failed)) + ")",
            code="render.invalid_prov",
        )
    view = ProvView.parse(doc)
    if view.core is None:
        raise RenderInputError("the PROV document has no core bundle", code="render.no_core_bundle")
    return view


# ----------------------------------------------------------------------------------------------- the model
def _slug(kind: str, iri: str) -> str:
    if kind == "inference":
        m = INF_RE.fullmatch(iri)
        return style.slug_token(m.group(1) if m else None)
    if kind == "assessment":
        m2 = ASSESS_RE.fullmatch(iri)
        return style.slug_token(m2.group(1) if m2 else None)
    return "core"


def _selected_bundles(view: ProvView, mode: str) -> list[tuple[Any, str]]:
    core = view.core
    assert core is not None
    chosen = [(core, "core")]
    if mode == "all":
        chosen += [(b, "inference") for b in sorted(view.inference(), key=lambda b: b.iri)]
        chosen += [(b, "assessment") for b in sorted(view.assessment(), key=lambda b: b.iri)]
    return chosen


def _first_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def build_model(doc: Any, *, ex: str, mode: str = "core") -> GraphModel:
    """The drawable graph of ``doc`` (validated first). ``mode`` is ``core`` or ``all``."""
    if mode not in BUNDLE_MODES:
        raise ValueError("mode is 'core' or 'all'")
    view = validate_document(doc)
    chosen = _selected_bundles(view, mode)
    bundles = tuple(DrawBundle(i, kind, _slug(kind, b.iri)) for i, (b, kind) in enumerate(chosen))

    nodes: dict[str, DrawNode] = {}
    for i, (bundle, kind) in enumerate(chosen):
        for st in bundle.statements:
            if st.is_element and st.key not in nodes:
                nodes[st.key] = DrawNode(st.key, st.section, i, kind, style.evidence_letter(st.attrs), st.attrs)

    edges: list[DrawEdge] = []
    for i, (bundle, kind) in enumerate(chosen):
        for st in bundle.statements:
            if st.is_element or st.section not in style.EDGE_TARGETS:
                continue
            source_arg, target_args = style.EDGE_TARGETS[st.section]
            src = _first_str(st.attrs.get(source_arg))
            if src is None:
                continue
            for arg in target_args:
                dst = _first_str(st.attrs.get(arg))
                if dst is None:
                    continue
                for endpoint, arg_name in ((src, source_arg), (dst, arg)):
                    if endpoint not in nodes:
                        nodes[endpoint] = _ghost(view, endpoint, arg_name)
                edges.append(DrawEdge(st.section, st.key, src, dst, i, kind, style.evidence_letter(st.attrs)))

    if mode == "all":
        nodes, links = _assessment_overlay(chosen, nodes)
        edges.extend(links)

    ordered_nodes = tuple(
        sorted(nodes.values(), key=lambda n: (99 if n.bundle is None else n.bundle, _SECTION_ORDER.get(n.section, 9), n.key))
    )
    edges.sort(key=lambda e: (e.bundle, e.link, e.relation, e.key, e.src, e.dst))
    return GraphModel(style.id_token(ex), mode, bundles, ordered_nodes, tuple(edges))


def _ghost(view: ProvView, key: str, arg: str) -> DrawNode:
    """A node that a drawn relation names but no drawn bundle declares: taken from the top level if it is declared
    there, else a bare node of the kind the argument position requires. Drawn with the 'outside' style."""
    top = view.top_elements.get(key)
    if top is not None:
        return DrawNode(key, top.section, None, None, style.evidence_letter(top.attrs), top.attrs)
    return DrawNode(key, ARG_KIND.get(arg, "entity"), None, None, None, {})


def _assessment_overlay(
    chosen: Sequence[tuple[Any, str]], nodes: dict[str, DrawNode]
) -> tuple[dict[str, DrawNode], list[DrawEdge]]:
    """The baseline's integrity and role colours, from the assessment bundles (MN N.2.13), and the claim links.

    Integrity comes from ``apv:integrity`` on the mention entity that ``mentionOf`` ties to the node (or on a
    ``Labelled`` claim); role from ``apv:securityRole`` on the same. Several labels combine fail-closed: the weakest
    integrity, and a sink over an endorser over unknown over neutral. A node with no label keeps its plain style; it is
    not drawn as trusted or neutral because of it.
    """
    integrity: dict[str, list[str]] = {}
    roles: dict[str, list[str]] = {}
    links: list[DrawEdge] = []
    for index, (bundle, kind) in enumerate(chosen):
        if kind != "assessment":
            continue
        elements: dict[str, St] = {s.key: s for s in bundle.statements if s.is_element}
        for st in bundle.statements:
            if st.section == "mentionOf":
                specific, general = _first_str(st.attrs.get("prov:specificEntity")), _first_str(st.attrs.get("prov:generalEntity"))
                body = elements.get(specific or "")
                if general is not None and body is not None:
                    integrity.setdefault(general, []).extend(style.qnames(body.attrs.get("apv:integrity")))
                    roles.setdefault(general, []).extend(style.qnames(body.attrs.get("apv:securityRole")))
        for element in sorted(elements.values(), key=lambda s: s.key):
            claim = style.qnames(element.attrs.get("apv:claim"))
            if not claim:
                continue
            if "apv:Labelled" in claim:
                for subject in style.qnames(element.attrs.get("apv:subject")):
                    integrity.setdefault(subject, []).extend(style.qnames(element.attrs.get("apv:integrity")))
                    roles.setdefault(subject, []).extend(style.qnames(element.attrs.get("apv:securityRole")))
            for attribute in ("apv:subject", "apv:object"):
                for target in style.qnames(element.attrs.get(attribute)):
                    if target in nodes and element.key in nodes:
                        links.append(
                            DrawEdge(attribute, f"{element.key}>{attribute}>{target}", element.key, target, index, kind, None, True)
                        )
    out: dict[str, DrawNode] = {}
    for key, node in nodes.items():
        out[key] = DrawNode(
            node.key, node.section, node.bundle, node.kind, node.cls, node.attrs,
            integrity=style.integrity_overlay(integrity.get(key, [])), role=style.role_overlay(roles.get(key, [])),
        )  # fmt: skip
    return out, links


# ----------------------------------------------------------------------------------------------- render
def render_prov_graph(
    doc: Any,
    out_stem: Path | str,
    *,
    ex: str,
    formats: Sequence[str] = ("svg",),
    direction: str = "LR",
    bundles: str = "core",
    show_content: bool = False,
    content_chars: int = style.DEFAULT_CONTENT_CHARS,
    dry_run: bool = False,
    max_edges: int | None = None,
) -> tuple[list[Path], str]:
    """Validate ``doc``, build its DOT text and write ``<out_stem>.dot`` and ``<out_stem>.<fmt>`` for each image format.

    ``max_edges`` (default :data:`agentprov.render.dot.MAX_LAYOUT_EDGES`; 0 means no limit) bounds the graph that is
    laid out for an image. Above it the ``.dot`` text is still written and :class:`RenderTooLargeError` is raised before
    ``dot`` starts, in a dry run too, instead of a 120 s timeout.

    The port of the baseline's ``render_prov_graph(doc_dict, out_path, title, formats, direction)``: ``out_stem`` is the
    file stem without extension. Files are written atomically; ``dot`` runs with a timeout. With ``dry_run`` the DOT text
    is built and nothing is written or run. Returns the paths written (or that would be) and the DOT text.
    """
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.render import dot as dotmod

    wanted = list(dict.fromkeys(formats))
    unknown = [f for f in wanted if f not in FORMATS]
    if unknown:
        raise ValueError("formats are svg, png, pdf and dot")
    model = build_model(doc, ex=ex, mode=bundles)
    text = dotmod.build_dot(model, direction=direction, show_content=show_content, content_chars=content_chars)
    stem = Path(out_stem)
    images = [f for f in wanted if f != "dot"]
    paths = [stem.with_name(stem.name + ".dot"), *(stem.with_name(f"{stem.name}.{f}") for f in images)]
    limit = dotmod.MAX_LAYOUT_EDGES if max_edges is None else max_edges
    too_large = bool(images) and limit > 0 and len(model.edges) > limit
    if dry_run and not too_large:
        return paths, text
    if not dry_run:
        stem.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(paths[0], text.encode("utf-8"))
    if too_large:
        raise RenderTooLargeError(
            f"the {bundles} graph has {len(model.nodes)} nodes and {len(model.edges)} edges, over the image layout limit "
            f"of {limit} edges (Graphviz dot would take minutes; G.8.6). The .dot text was "
            f"{'not written (dry run)' if dry_run else 'written'}. Draw the core bundle (--bundle core), lay the .dot "
            "out offline, or raise --max-edges (0 = no limit; dot still stops at its 120 s timeout)"
        )
    exe = dotmod.find_dot() if images else None
    for fmt, dest in zip(images, paths[1:], strict=True):
        assert exe is not None
        atomic_write_bytes(dest, dotmod.run_dot(exe, text, fmt))
    return paths, text
