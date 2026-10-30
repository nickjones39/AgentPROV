"""Shared helpers of the Level-2 pre-check tools (``l2_sample.py``, ``l2_import.py``, ``l2_check.py``).

Stdlib only (``agentprov`` is imported lazily by the tools that need it). Nothing here reads raw data: these are the
scratch-path guards, the glob escaping of sampled labels, the JSON pointer normaliser and the account-path and
secret-like patterns the redaction census counts (counts and pointers only, never a matched value).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any, Final

REPO: Final = Path(__file__).resolve().parents[2]
#: The protocol's seed (CORPUS-CHECK-PROTOCOL, README section 4).
SEED: Final = "20261011"
SAMPLE_FORMAT: Final = "agentprov-precheck-l2-sample/1"
IMPORT_FORMAT: Final = "agentprov-precheck-l2-import/1"
CHECK_FORMAT: Final = "agentprov-precheck-l2-check/1"


def agentprov_home() -> Path:
    return Path(os.environ.get("AGENTPROV_HOME") or (Path.home() / ".agentprov")).expanduser()


def precheck_root() -> Path:
    """The pre-check output root: ``$AGENTPROV_PRECHECK_ROOT`` when set, else ``$AGENTPROV_HOME/migration-work/precheck``
    (the only place scratch corpora of the pre-check may live). Guarded by :func:`guard_output` under pytest."""
    explicit = os.environ.get("AGENTPROV_PRECHECK_ROOT")
    root = Path(explicit).expanduser() if explicit else agentprov_home() / "migration-work" / "precheck"
    return guard_output(root)


def guard_output(path: str | os.PathLike[str]) -> Path:
    """Refuse, under pytest (``PYTEST_CURRENT_TEST`` set), any output path inside the real ``~/.agentprov`` or the repo's
    ``docs/reports/precheck`` (2026-10-15 incident: a test run without the repo conftest overwrote real scratch rows).
    Tests must write under ``tmp_path`` (the repo conftest isolates ``AGENTPROV_HOME``). Returns the path."""
    out = Path(path).expanduser()
    if os.environ.get("PYTEST_CURRENT_TEST"):
        for real in (Path.home() / ".agentprov", REPO / "docs" / "reports" / "precheck"):
            if inside(out, real) or _real(out) == _real(real):
                raise SystemExit(f"refused under pytest: {tilde(out)} is a real pre-check output location")
    return out


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def inside(path: Path, root: Path) -> bool:
    try:
        _real(path).relative_to(_real(root))
    except ValueError:
        return False
    return True


def guard_scratch(path: Path) -> Path:
    """Refuse any corpus path outside the pre-check scratch root, or inside ``$AGENTPROV_HOME/corpora``."""
    corpora = agentprov_home() / "corpora"
    if inside(path, corpora):
        raise SystemExit(f"refused: {tilde(path)} is under {tilde(corpora)} (stored corpora are read-only)")
    if not inside(path, precheck_root()):
        raise SystemExit(f"refused: scratch corpora live under {tilde(precheck_root())}, not {tilde(path)}")
    return path


def tilde(path: str | os.PathLike[str]) -> str:
    """A path for reports: the home directory written as ``~`` (no account name in a committed file)."""
    text = os.fspath(path)
    home = str(Path.home())
    return "~" + text[len(home):] if home and text.startswith(home) else text


def load_tool(relative: str, name: str | None = None) -> ModuleType:
    """Import a maintenance script of ``tools/`` by path (the tool directories are not packages)."""
    path = REPO / "tools" / relative
    module_name = name or "precheck_dep_" + re.sub(r"\W", "_", relative.removesuffix(".py"))
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load tools/{relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------------------------ globs
_GLOB_ESCAPES: Final = {"[": "[[]", "*": "[*]", "?": "[?]"}


def escape_label(label: str) -> str:
    """``label`` as an ``fnmatch`` glob that matches exactly ``label`` (``[`` -> ``[[]``, ``*`` -> ``[*]``, ``?`` -> ``[?]``;
    a lone ``]`` is literal in fnmatch). The importer's ``**/`` rule cannot fire: an escaped ``*`` is ``[*]``."""
    return "".join(_GLOB_ESCAPES.get(ch, ch) for ch in label)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(lines: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Rows of a tool-written JSONL file (the pre-check's own L1 rows; not untrusted source bytes)."""
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise SystemExit(f"{tilde(path)} line {number}: not a JSON object")
            yield value


def write_json(path: Path, value: Any) -> None:
    """Write ``value`` as sorted, indented JSON (a deterministic report file)."""
    guard_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------ redaction patterns
#: A workstation account path: ``/Users/<name>/`` or ``/home/<name>/`` (also after ``file://`` or a ``provider/``
#: prefix). Benchmark fiction such as ``/home/user`` in sandbox transcripts matches too; the census reports the pointer
#: so that the dossier can tell the two apart, never the value.
ACCOUNT_PATH: Final = re.compile(rb"/(?:Users|home)/[A-Za-z0-9._-]{1,64}/")
#: The trial drivers' local-path model id test (``tools/inspect/phase10h_trial.py``).
LOCAL_PATH_MODEL: Final = re.compile(r"(^|/|:)/(workspace|Users|home|mnt|scratch|data|root|tmp)/")
#: Secret-like shapes (bounded, never printed): the key shapes of the profiles' ``[withhold]`` rules and of gitleaks'
#: default rules that ``tools/release_scan.py`` relies on.
SECRET_PATTERNS: Final[dict[str, re.Pattern[bytes]]] = {
    "aws-access-key-id": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "anthropic-api-key": re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,200}"),
    "openai-style-key": re.compile(rb"sk-(?!ant-)[A-Za-z0-9_-]{20,200}"),
    "stripe-key": re.compile(rb"[sr]k_(?:live|test)_[A-Za-z0-9]{16,200}"),
    "github-token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,200}"),
    "slack-token": re.compile(rb"xox[abpors]-[A-Za-z0-9-]{10,200}"),
    "google-api-key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "private-key-header": re.compile(rb"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----"),
}


def personal_needles() -> dict[str, list[bytes]]:
    """The operator's own home path and host name (``tools/release_scan.py`` ``personal_needles``, R-51)."""
    module = load_tool("release_scan.py", "precheck_dep_release_scan")
    needles: dict[str, list[bytes]] = module.personal_needles()
    return needles


# ------------------------------------------------------------------------------------------------ pointers
_PLAIN_KEY: Final = re.compile(r"[A-Za-z_][A-Za-z_:$@.-]{0,47}")


def norm_segment(segment: str | int) -> str:
    """A JSON pointer segment as reported: array indices and identifier-like or data-valued keys become ``*``/``{k}``,
    so a pointer names a field, never a value (model ids used as keys, attachment hashes, statement ids)."""
    if isinstance(segment, int):
        return "*"
    if not _PLAIN_KEY.fullmatch(segment) or any(p.search(segment.encode("utf-8", "replace")) for p in SECRET_PATTERNS.values()):
        return "{k}"
    return segment.replace("~", "~0").replace("/", "~1")


def iter_strings(value: Any, pointer: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], str, bool]]:
    """``(normalised pointer, string, is_key)`` for every string value and every object key of ``value``."""
    if isinstance(value, str):
        yield pointer, value, False
    elif isinstance(value, dict):
        for key, item in value.items():
            seg = norm_segment(str(key))
            yield (*pointer, seg), str(key), True
            yield from iter_strings(item, (*pointer, seg))
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item, (*pointer, "*"))


def pointer_text(pointer: tuple[str, ...]) -> str:
    return "/" + "/".join(pointer) if pointer else ""


def scrub(text: str, limit: int = 300) -> str:
    """Tool output for a report: home path written as ``~``, account paths and secret shapes masked, truncated."""
    out = text.replace(str(Path.home()), "~") if str(Path.home()) else text
    data = out.encode("utf-8", "replace")
    data = ACCOUNT_PATH.sub(b"/<account-path>/", data)
    for pattern in SECRET_PATTERNS.values():
        data = pattern.sub(b"<secret-like>", data)
    out = data.decode("utf-8", "replace")
    return out if len(out) <= limit else out[: limit - 3] + "..."
