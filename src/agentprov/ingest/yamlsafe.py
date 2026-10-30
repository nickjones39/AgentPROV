"""Bounded, alias-free ``safe_load`` (docs/architecture G.3.7; AD-17; SEC-05).

This is the **only** module that imports ``yaml`` (PyYAML). Readers and loaders never parse YAML; only the SEM marker
normaliser and the compat port's ``safe_load`` shim (R-31) do, and only through :func:`safe_load` here.

Rules, in order:

1. input at most ``max_yaml_bytes`` (``ingest.size.record`` otherwise; the caller's marker status is ``ambiguous``);
2. an event pre-scan with the pure-Python ``SafeLoader`` rejects any alias (``ingest.yaml.alias``; an alias document
   such as "billion laughs" is never constructed), nesting deeper than :data:`MAX_YAML_DEPTH`, and a base-60 int scalar
   longer than :data:`MAX_SEXAGESIMAL_CHARS` (its construction is quadratic);
3. the document is constructed by a pure-Python ``SafeLoader`` subclass that also rejects duplicate mapping keys.

``yaml.load``, ``unsafe_load``, ``full_load`` and the C loaders are never used. The values returned are exactly those of
``yaml.safe_load`` for a document that passes (YAML 1.1 implicit typing included: tool outputs stay strings in AER and are
never re-parsed into canonical values by callers).

Failures: ``IngestError`` (``ingest.yaml.alias``, ``ingest.size.record``) or a ``yaml.YAMLError`` (syntax errors, duplicate
keys, excessive depth, scalars PyYAML cannot construct). :data:`YAMLError` is re-exported so that callers and the compat shim never import ``yaml``. G.3.9
assigns no ``ingest.*`` code to duplicate keys or depth, so these two stay ``YAMLError`` subclasses.
"""

from __future__ import annotations

import re
from typing import IO, Any, Final

import yaml
from yaml.composer import ComposerError
from yaml.constructor import ConstructorError

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits

YAMLError: Final = yaml.YAMLError

#: Nesting cap for YAML. PyYAML composes and constructs recursively, so this is far below CPython's recursion limit.
MAX_YAML_DEPTH: Final = 64
#: The longest base-60 ("sexagesimal", ``1:30:00``) int scalar constructed. PyYAML builds one with a growing bigint, in
#: time quadratic in its parts (about 50 s for 1 MiB); CPython's own int-string limit is 4,300 digits (pre-round review D
#: #4). A longer one is a ``YAMLError``.
MAX_SEXAGESIMAL_CHARS: Final = 4_300
#: YAML 1.1's sexagesimal int (PyYAML's implicit int resolver, the base-60 branch).
_SEXAGESIMAL_INT: Final = re.compile(r"[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+")
_INT_TAG: Final = "tag:yaml.org,2002:int"


class StrictSafeLoader(yaml.SafeLoader):
    """Pure-Python ``SafeLoader`` that rejects aliases and duplicate mapping keys."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise ComposerError(None, None, "YAML aliases are rejected", event.start_mark)
        return super().compose_node(parent, index)

    def construct_mapping(self, node: Any, deep: bool = False) -> Any:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in seen:
                    raise ConstructorError(None, None, "duplicate mapping key", key_node.start_mark)
                seen.add(key)
            except TypeError:  # an unhashable key: let SafeLoader report it
                break
        return super().construct_mapping(node, deep)


def _prescan(text: str) -> None:
    """Event pre-scan: no aliases, bounded depth. PyYAML's parser is a state machine, so this never recurses."""
    depth = 0
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, yaml.AliasEvent):
            raise IngestError("ingest.yaml.alias", "YAML alias rejected")
        if (
            isinstance(event, yaml.ScalarEvent)
            and len(event.value) > MAX_SEXAGESIMAL_CHARS
            and ((event.style is None and event.tag is None) or event.tag == _INT_TAG)
            and _SEXAGESIMAL_INT.fullmatch(event.value)
        ):
            raise yaml.YAMLError(f"base-60 int scalar longer than {MAX_SEXAGESIMAL_CHARS} characters")
        if isinstance(event, yaml.CollectionStartEvent):
            depth += 1
            if depth > MAX_YAML_DEPTH:
                mark = event.start_mark if isinstance(event.start_mark, yaml.error.Mark) else None
                raise ComposerError(None, None, "YAML nesting too deep", mark)
        elif isinstance(event, yaml.CollectionEndEvent):
            depth -= 1


def safe_load(stream: str | bytes | IO[str] | IO[bytes], limits: IngestLimits | None = None) -> Any:
    """Parse one YAML document from untrusted input (G.3.7). See the module docstring for the rules and failures."""
    limits = limits or IngestLimits()
    data: str | bytes = stream if isinstance(stream, str | bytes) else stream.read(limits.max_yaml_bytes + 1)
    size = len(data.encode("utf-8", "surrogatepass")) if isinstance(data, str) else len(data)
    if size > limits.max_yaml_bytes:
        raise IngestError("ingest.size.record", "YAML input exceeds max_yaml_bytes", limit=limits.max_yaml_bytes)
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
    except UnicodeDecodeError:
        raise yaml.YAMLError("YAML input is not valid UTF-8") from None
    _prescan(text)
    try:
        return yaml.load(text, Loader=StrictSafeLoader)  # noqa: S506 - StrictSafeLoader is a SafeLoader subclass
    except RecursionError:
        raise ComposerError(None, None, "YAML nesting too deep", None) from None
    except (ValueError, TypeError, AttributeError, OverflowError, KeyError, IndexError):
        # PyYAML's constructors raise these for impossible scalars (a timestamp of month 13, an int tag on text).
        raise yaml.YAMLError("YAML scalar could not be constructed") from None
