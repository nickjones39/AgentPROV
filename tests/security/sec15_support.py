"""Tampering devices for the SEC-15 matrix (``sec15_support``; not collected).

They play an attacker who edits one file of a sealed corpus tree in one of four ways and may then regenerate
``checksums.sha256`` over the result (``verify_support.regenerate_checksums``). Test devices only, never a way to build
a corpus.

* **edit**: a well-formed change. A JSON or JSONL file is re-serialised in its own byte style with one string value
  changed (so the file still parses and only the meaning differs); a text file gets an appended line; a raw object gets
  one letter changed.
* **remove**: the file is deleted.
* **add**: a new, grammar-admitted file of the same kind (an orphan copy of an execution file under a fresh id, a new
  digest-named raw object, another licence, rules or schema file).
* **reorder**: the lines of a JSONL (or checksums) file reversed, or a JSON object's keys written in reverse order.

``KINDS`` maps every file kind a sealed corpus holds (H.1.2) to a function that picks one such file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from agentprov.io.canonical import jcs_bytes

Pick = Callable[[Path], str]


def _first(top: str, suffix: str = "") -> Pick:
    def pick(root: Path) -> str:
        files = sorted(p for p in (root / top).rglob("*") if p.is_file() and p.name.endswith(suffix))
        return files[0].relative_to(root).as_posix()

    return pick


def _fixed(label: str) -> Pick:
    return lambda root: label


#: kind -> (picker, format). Every file kind of the sealed test corpus ``mini-mit``.
KINDS: Final[dict[str, tuple[Pick, str]]] = {
    "manifest": (_fixed("corpus.json"), "json"),
    "index": (_fixed("executions.jsonl"), "jsonl"),
    "register": (_fixed("register.jsonl"), "jsonl"),
    "derivation": (_fixed("derivation.json"), "json"),
    "origins": (_fixed("raw/origins.jsonl"), "jsonl"),
    "members": (_fixed("raw/members.jsonl"), "jsonl"),
    "raw_object": (_first("raw/objects"), "bytes"),
    "aer": (_first("aer"), "jsonl"),
    "sem": (_first("sem"), "jsonl"),
    "prov": (_first("prov"), "json"),
    "validation_results": (_fixed("validation/results.jsonl"), "jsonl"),
    "validation_summary": (_fixed("validation/summary.json"), "json"),
    "datasheet": (_fixed("DATASHEET.md"), "text"),
    "changelog": (_fixed("CHANGELOG.md"), "text"),
    "licence_derived": (_fixed("LICENSES/DERIVED.txt"), "text"),
    "licence_source": (_fixed("LICENSES/agentdojo/LICENSE"), "text"),
    "licence_notice": (_fixed("LICENSES/agentdojo/NOTICE.md"), "text"),
    "rules_catalogue": (_fixed("rules/agentdojo.rules.toml"), "text"),
    "rules_prov": (_fixed("rules/prov/agentprov-prov-0.1.toml"), "text"),
    "rules_source_profile": (_fixed("rules/agentdojo-upstream.profile.toml"), "text"),
    "rules_semantics": (_fixed("rules/agentdojo.suites-2.labels.profile.toml"), "text"),
    "rules_spec": (_fixed("rules/corpus-spec.toml"), "text"),
    "rules_card": (_fixed("rules/CARD.md"), "text"),
    "rules_changes": (_fixed("rules/CHANGES.toml"), "text"),
    "schema": (_fixed("schemas/aer-0.2.schema.json"), "json"),  # the AER schema of the current corpus format (D-212)
}

#: A fresh execution id (H.1.3 grammar) for orphan execution files.
ORPHAN_EX: Final = "ex_" + "a" * 26


# ------------------------------------------------------------------------------------------------ byte styles
def _styles() -> list[Callable[[Any], bytes]]:
    return [
        lambda v: jcs_bytes(v),
        lambda v: jcs_bytes(v) + b"\n",
        lambda v: (json.dumps(v, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(),
        lambda v: json.dumps(v, sort_keys=True, indent=2, ensure_ascii=False).encode(),
        lambda v: (json.dumps(v, indent=2, ensure_ascii=False) + "\n").encode(),
        lambda v: json.dumps(v, ensure_ascii=False).encode(),
        lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False).encode(),
    ]


def style_of(data: bytes) -> Callable[[Any], bytes]:
    """The serialiser that reproduces ``data`` byte for byte (``AssertionError`` when none does)."""
    value = json.loads(data)
    for style in _styles():
        if style(value) == data:
            return style
    raise AssertionError("no known byte style reproduces the file")


def _mutate_first_string(value: Any) -> bool:
    """Append ``"x"`` to the first string leaf (keys sorted, depth first); ``False`` when there is none."""
    if isinstance(value, dict):
        for key in sorted(value):
            if isinstance(value[key], str):
                value[key] += "x"
                return True
            if _mutate_first_string(value[key]):
                return True
    elif isinstance(value, list):
        for i, item in enumerate(value):
            if isinstance(item, str):
                value[i] += "x"
                return True
            if _mutate_first_string(item):
                return True
    return False


def _reverse_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _reverse_keys(value[k]) for k in sorted(value, reverse=True)}
    if isinstance(value, list):
        return [_reverse_keys(v) for v in value]
    return value


def _writable(path: Path) -> None:
    path.chmod(0o644)  # stored raw objects are read-only (0444)


# ------------------------------------------------------------------------------------------------ the four operations
def edit(root: Path, label: str, fmt: str) -> None:
    path = root / label
    _writable(path)
    data = path.read_bytes()
    if fmt == "json":
        value = json.loads(data)
        assert _mutate_first_string(value)
        path.write_bytes(style_of(data)(value))
    elif fmt == "jsonl":
        lines = data.splitlines(keepends=True)
        if not lines:  # an empty JSONL file (no archive members): a well-formed edit is one plausible row
            path.write_bytes(jcs_bytes({"disposition": "selected"}) + b"\n")
            return
        first = json.loads(lines[0])
        assert _mutate_first_string(first)
        lines[0] = style_of(lines[0].rstrip(b"\n"))(first) + b"\n"
        path.write_bytes(b"".join(lines))
    elif fmt == "text":
        path.write_bytes(data + b"\nAn added line.\n")
    else:  # bytes: change one ASCII letter, keeping the length
        i = next(i for i, b in enumerate(data) if 0x61 <= b <= 0x7A)
        path.write_bytes(data[:i] + bytes([0x61 + (data[i] - 0x61 + 1) % 26]) + data[i + 1:])


def remove(root: Path, label: str) -> None:
    """Delete the file and the shard directories it leaves empty (the attacker keeps the tree closed-world)."""
    path = root / label
    path.unlink()
    for parent in path.parents:
        if parent == root or any(parent.iterdir()):
            break
        parent.rmdir()


def reorder(root: Path, label: str, fmt: str) -> bool:
    """Reorder in place; ``False`` when the file has nothing to reorder (one line, a text file)."""
    path = root / label
    _writable(path)
    data = path.read_bytes()
    if fmt == "jsonl" or label == "checksums.sha256":
        lines = data.splitlines(keepends=True)
        if len(lines) < 2:
            return False
        path.write_bytes(b"".join(reversed(lines)))
        return True
    if fmt == "json":
        value = json.loads(data)
        if not isinstance(value, dict) or len(value) < 2:
            return False
        style = style_of(data)
        compact = style(value).endswith(b"\n")
        text = json.dumps(_reverse_keys(value), indent=2, ensure_ascii=False) if b"\n  " in data else json.dumps(
            _reverse_keys(value), ensure_ascii=False)
        path.write_bytes(text.encode() + (b"\n" if compact else b""))
        return True
    return False


def _orphan(label: str) -> str:
    """The same execution file under :data:`ORPHAN_EX` (in its shard, H.1.3)."""
    from agentprov.corpus.layout import shard

    head, _, name = label.rpartition("/")
    top = head.rsplit("/", 1)[0]
    return f"{top}/{shard(ORPHAN_EX, 1)}/{ORPHAN_EX}{name[name.index('.'):]}"


def add(root: Path, kind: str) -> str | None:
    """Add a new grammar-admitted file of ``kind``; returns its label, or ``None`` when the kind has no second file
    (a fixed name: the manifest, the index, ...)."""
    from agentprov.corpus.layout import classify_relpath

    pick, _fmt = KINDS[kind]
    label = pick(root)
    if kind in ("aer", "sem", "prov"):
        new = _orphan(label)
        data = (root / label).read_bytes()
    elif kind == "raw_object":
        data = b'{"added": "an object nobody lists"}\n'
        sha = hashlib.sha256(data).hexdigest()
        new = f"raw/objects/{sha[:2]}/{sha}.json"
    elif kind.startswith("licence"):
        new, data = "LICENSES/added/LICENSE", b"An added licence text.\n"
    elif kind.startswith("rules") and kind not in ("rules_spec", "rules_card", "rules_changes"):
        new, data = "rules/added.rules.toml", b"# an added catalogue\n"
    else:
        return None
    assert classify_relpath(new) is not None, new
    target = root / new
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return new

