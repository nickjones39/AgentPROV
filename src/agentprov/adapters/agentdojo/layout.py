"""``[import] layout`` path templates of the AgentDojo family (docs/architecture D.4.2-D.4.4, D.6.3 R-PATH, D.6.12 item 3).

A layout is a ``/``-separated template, e.g. ``runs/{pipeline_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json`` or
``runs/{tree?}/{model_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json``. Each segment is

* a literal (``runs``), which must equal the path segment;
* ``{name}`` or ``{name}<suffix>`` (``{file}.json``): one path segment, captured without the suffix;
* ``{name?}``: an **optional** component spanning zero or more path segments (ROPE's ``ablation/<policy>`` and
  ``router/<router>[-clamp]`` trees). At most one per layout; it is captured joined by ``/``, or ``None`` when absent.

Matching is pure and total (``None`` when the path does not fit). A layout without an optional component is aligned
from the right, so a path with leading directories outside the template (an ``--input`` root above ``runs/``) still
yields its components; this is the phase-6 behaviour. A layout with an optional component is aligned at both ends: the
segments before it from the left, the segments after it from the right, and the rest is the optional component.

The named components are the **facets** of a file (D.4.1 "Selectors"): quirk and system-prompt selectors may name them.
Paths are labels, never filesystem paths (G.3.6); nothing here touches a file.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from agentprov.errors import ProfileError

__all__ = ["Layout", "Segment", "parse_layout"]

_NAMED: Final = re.compile(r"\{([a-z][a-z0-9_]*)(\?)?\}(.*)")


@dataclass(frozen=True, slots=True)
class Segment:
    literal: str | None = None
    name: str | None = None
    suffix: str = ""
    optional: bool = False

    def take(self, seg: str) -> str | None:
        """The captured value of one path segment, or ``None`` when it does not fit."""
        if self.literal is not None:
            return "" if seg == self.literal else None
        if self.suffix:
            if not seg.endswith(self.suffix) or len(seg) == len(self.suffix):
                return None
            return seg[: -len(self.suffix)]
        return seg if seg else None


@dataclass(frozen=True, slots=True)
class Layout:
    text: str
    segments: tuple[Segment, ...]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(s.name for s in self.segments if s.name is not None)

    @property
    def optional(self) -> int | None:
        return next((i for i, s in enumerate(self.segments) if s.optional), None)

    def match(self, path: object) -> dict[str, str | None] | None:
        """The named components of ``path`` under this layout, or ``None`` when it does not fit."""
        if not isinstance(path, str) or not path:
            return None
        parts = path.split("/")
        k = self.optional
        if k is None:
            if len(parts) < len(self.segments):
                return None
            return _fixed(self.segments, parts[len(parts) - len(self.segments):])
        before, after = self.segments[:k], self.segments[k + 1:]
        if len(parts) < len(before) + len(after):
            return None
        head = _fixed(before, parts[: len(before)])
        tail = _fixed(after, parts[len(parts) - len(after):])
        if head is None or tail is None:
            return None
        middle = parts[len(before): len(parts) - len(after)]
        if any(not m for m in middle):
            return None
        name = self.segments[k].name
        assert name is not None
        return {**head, name: "/".join(middle) if middle else None, **tail}


def _fixed(template: Sequence[Segment], parts: Sequence[str]) -> dict[str, str | None] | None:
    out: dict[str, str | None] = {}
    for tpl, seg in zip(template, parts, strict=True):
        value = tpl.take(seg)
        if value is None:
            return None
        if tpl.name is not None:
            out[tpl.name] = value
    return out


def parse_layout(text: str, *, where: str = "layout") -> Layout:
    """Parse a layout template; :class:`~agentprov.errors.ProfileError` on a malformed one."""
    segments: list[Segment] = []
    for raw in text.split("/"):
        if not raw:
            raise ProfileError(f"{where}: empty layout segment in {text!r}")
        found = _NAMED.fullmatch(raw)
        if found is None:
            if "{" in raw or "}" in raw:
                raise ProfileError(f"{where}: malformed layout segment {raw!r}")
            segments.append(Segment(literal=raw))
            continue
        name, optional, suffix = found.group(1), bool(found.group(2)), found.group(3)
        if "{" in suffix or "}" in suffix or (optional and suffix):
            raise ProfileError(f"{where}: malformed layout segment {raw!r}")
        segments.append(Segment(name=name, suffix=suffix, optional=optional))
    names = [s.name for s in segments if s.name is not None]
    if len(names) != len(set(names)):
        raise ProfileError(f"{where}: a layout component is named twice in {text!r}")
    if sum(s.optional for s in segments) > 1:
        raise ProfileError(f"{where}: at most one optional component per layout ({text!r})")
    return Layout(text, tuple(segments))
