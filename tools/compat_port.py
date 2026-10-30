#!/usr/bin/env python3
"""Generate and verify the ``adprov-v2.3-compat`` port (docs/architecture J.3.3, EF E.8.1; RESOLUTIONS R-31).

The oracle is five baseline files at commit ``579a908`` (``build_prov``, ``prov_emit``, ``labeling``, ``validate``,
``conformance``) copied into ``src/agentprov/prov/compat/adprov_v2_3/`` with **import statements as the only change**:

* ``from agentdojo_prov.X import ...`` becomes ``from agentprov.prov.compat.adprov_v2_3.X import ...`` (same line, same
  names);
* the function-local ``import yaml`` of ``build_prov._decoded_forms`` becomes
  ``from agentprov.prov.compat.adprov_v2_3 import yaml_shim as yaml``, so the body's ``yaml.safe_load(...)`` reaches
  ``agentprov.ingest.yamlsafe.safe_load`` (the one PyYAML importer, AD-17).

Every line keeps its line number, so the port stays diff-able against the baseline (``build_prov.py:393-395`` and the
other line references in the audit still point at the same code).

This script is the only thing that writes the five files and ``PORT_MANIFEST.json``. It is a maintenance tool, not part
of the package. The tests import :func:`normalised_ast_digest` and :func:`import_records` from here, so the generator
and the check can never disagree on the digest algorithm.

    uv run python tools/compat_port.py generate [--baseline DIR]   # (re)write the port, the manifest and adprov.ttl
    uv run python tools/compat_port.py check [--baseline DIR]      # compare the port with the baseline repository

Baseline bytes are read with ``git show 579a908:<path>`` so a dirty or moved working tree cannot change the result.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BASELINE_COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"
BASELINE_TAG = "agentprov-baseline-2026-10-07"
BASELINE_PACKAGE = "agentdojo_prov"
PORT_PACKAGE = "agentprov.prov.compat.adprov_v2_3"
FILES = ("build_prov", "prov_emit", "labeling", "validate", "conformance")
TTL_BASELINE_PATH = "docs/ns/adprov.ttl"
DIGEST_ALGORITHM = "agentprov-compat-ast-digest/1"

REPO = Path(__file__).resolve().parents[1]
PORT_DIR = REPO / "src" / "agentprov" / "prov" / "compat" / "adprov_v2_3"
MANIFEST = PORT_DIR / "PORT_MANIFEST.json"
DEFAULT_BASELINE = REPO.parent / "AgentDojo-PROV-framework"

YAML_SHIM_IMPORT = f"from {PORT_PACKAGE} import yaml_shim as yaml"

# The glue files that sit beside the oracle and are not part of it.
GLUE = ("__init__.py", "serialise.py", "yaml_shim.py")


# --------------------------------------------------------------------------------------------- digest


def _canon(node: Any) -> Any:
    """A version-robust structural form of an AST: node type plus non-empty fields; imports masked.

    ``ast.dump`` output changes between CPython releases (new fields such as ``type_params``), so the digest walks the
    tree itself and drops fields that are ``None`` or an empty list. Every ``import`` / ``from ... import`` statement
    is replaced by one marker: import statements are the only permitted difference and are recorded separately in the
    manifest (see :func:`import_records`). Docstrings and constants are kept, so a changed literal changes the digest.
    """
    if isinstance(node, ast.Import | ast.ImportFrom):
        return ["<import>"]
    if isinstance(node, ast.AST):
        out: list[Any] = [type(node).__name__]
        for name in node._fields:
            value = getattr(node, name, None)
            if value is None or value == []:
                continue
            out.append([name, _canon(value)])
        return out
    if isinstance(node, list):
        return [_canon(item) for item in node]
    return [type(node).__name__, repr(node)]


def normalised_ast_digest(source: str) -> str:
    """sha256 of the import-masked canonical AST of ``source`` (algorithm :data:`DIGEST_ALGORITHM`)."""
    tree = ast.parse(source)
    blob = json.dumps(_canon(tree), separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(blob).hexdigest()


def import_records(source: str) -> list[dict[str, Any]]:
    """Every import statement of ``source`` in source order: ``{"line", "end_line", "text"}`` (``ast.unparse``)."""
    out: list[dict[str, Any]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import | ast.ImportFrom):
            out.append({"line": node.lineno, "end_line": node.end_lineno, "text": ast.unparse(node)})
    out.sort(key=lambda r: (r["line"], r["text"]))
    return out


# --------------------------------------------------------------------------------------------- porting


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def port_source(source: str, name: str) -> str:
    """Apply the import rewrites of R-31 to the baseline ``source`` of module ``name``; nothing else changes."""
    if "\r" in source:
        raise ValueError(f"{name}: carriage returns would make line numbers ambiguous")
    lines = source.split("\n")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == BASELINE_PACKAGE or node.module.startswith(BASELINE_PACKAGE + "."):
                old = f"from {BASELINE_PACKAGE}."
                line = lines[node.lineno - 1]
                if line.count(old) != 1 or not line.lstrip().startswith(old):
                    raise ValueError(f"{name}:{node.lineno}: unexpected import layout: {line!r}")
                lines[node.lineno - 1] = line.replace(old, f"from {PORT_PACKAGE}.", 1)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "yaml":
                    line = lines[node.lineno - 1]
                    if line.strip() != "import yaml" or node.end_lineno != node.lineno:
                        raise ValueError(f"{name}:{node.lineno}: unexpected yaml import layout: {line!r}")
                    lines[node.lineno - 1] = line.replace("import yaml", YAML_SHIM_IMPORT, 1)
                elif alias.name.split(".")[0] == BASELINE_PACKAGE:
                    raise ValueError(f"{name}:{node.lineno}: plain import of the baseline package")
    ported = "\n".join(lines)
    leftovers = [r for r in import_records(ported) if BASELINE_PACKAGE in r["text"]]
    if leftovers:
        raise ValueError(f"{name}: baseline imports left after porting: {leftovers}")
    return ported


def _git_show(baseline: Path, path: str) -> bytes:
    return subprocess.run(  # noqa: S603 - fixed argv, a pinned commit and a repo-relative path
        ["git", "-C", str(baseline), "show", f"{BASELINE_COMMIT}:{path}"],  # noqa: S607
        check=True,
        capture_output=True,
    ).stdout


def build_manifest(baseline: Path) -> tuple[dict[str, Any], dict[str, str], bytes]:
    """Return ``(manifest, {filename: port source}, ttl bytes)`` for the baseline repository at ``baseline``."""
    files: dict[str, Any] = {}
    ported: dict[str, str] = {}
    for name in FILES:
        path = f"{BASELINE_PACKAGE}/{name}.py"
        raw = _git_show(baseline, path)
        source = raw.decode("utf-8")
        port = port_source(source, name)
        base_imports, port_imports = import_records(source), import_records(port)
        if [(r["line"], r["end_line"]) for r in base_imports] != [(r["line"], r["end_line"]) for r in port_imports]:
            raise ValueError(f"{name}: import statements moved")
        records = []
        for before, after in zip(base_imports, port_imports, strict=True):
            records.append(
                {
                    "line": before["line"],
                    "end_line": before["end_line"],
                    "baseline": before["text"],
                    "port": after["text"],
                    "changed": before["text"] != after["text"],
                }
            )
        base_digest, port_digest = normalised_ast_digest(source), normalised_ast_digest(port)
        if base_digest != port_digest:
            raise ValueError(f"{name}: AST digest changed by porting")
        files[f"{name}.py"] = {
            "baseline_path": path,
            "baseline_sha256": sha256_hex(raw),
            "baseline_lines": source.count("\n") + (0 if source.endswith("\n") else 1),
            "ast_sha256": base_digest,
            "port_sha256": sha256_hex(port.encode("utf-8")),
            "imports": records,
        }
        ported[f"{name}.py"] = port
    ttl = _git_show(baseline, TTL_BASELINE_PATH)
    manifest = {
        "schema": "agentprov-compat-port-manifest/1",
        "spec_id": "adprov-v2.3-compat",
        "status": "apv:RegressionOracle",
        "note": (
            "A strict port (RESOLUTIONS R-31): every function and class body is AST-equal to the baseline, and import "
            "statements are the only change. The oracle MUST NOT be edited; semantics changes belong in agentprov-prov."
        ),
        "baseline": {"repository": "AgentDojo-PROV-framework", "commit": BASELINE_COMMIT, "tag": BASELINE_TAG},
        "ast_digest": {
            "algorithm": DIGEST_ALGORITHM,
            "definition": (
                "sha256 of the compact JSON of a recursive form of ast.parse(source): [node type, [field, value]...] "
                "with None and empty-list fields dropped, constants as [python type, repr], and every import "
                "statement replaced by the marker '<import>'. Implemented by tools/compat_port.py:normalised_ast_digest."
            ),
        },
        "files": files,
        "rewrites": [
            {
                "kind": "package",
                "from": f"from {BASELINE_PACKAGE}.<module> import ...",
                "to": f"from {PORT_PACKAGE}.<module> import ...",
                "reason": "the oracle's own modules are addressed inside the new package",
            },
            {
                "kind": "yaml",
                "file": "build_prov.py",
                "from": "import yaml",
                "to": YAML_SHIM_IMPORT,
                "reason": (
                    "R-31 / AD-17: PyYAML is imported only by agentprov.ingest.yamlsafe; yaml_shim.safe_load is the "
                    "only route. The body's yaml.safe_load(content) is untouched. The parsed fallback is reached on "
                    "7 outputs of the frozen corpora, none with aliases or duplicate keys, all below 1 KiB (MR-3)."
                ),
            },
        ],
        "glue": list(GLUE),
        "adprov_ttl": {
            "port_path": "adprov.ttl",
            "baseline_path": TTL_BASELINE_PATH,
            "sha256": sha256_hex(ttl),
        },
    }
    return manifest, ported, ttl


# --------------------------------------------------------------------------------------------- commands


def manifest_text(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"


def cmd_generate(baseline: Path) -> int:
    manifest, ported, ttl = build_manifest(baseline)
    PORT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, text in ported.items():
        (PORT_DIR / filename).write_bytes(text.encode("utf-8"))
    (PORT_DIR / "adprov.ttl").write_bytes(ttl)
    MANIFEST.write_text(manifest_text(manifest), encoding="utf-8")
    print(f"wrote {len(ported)} oracle files, adprov.ttl and PORT_MANIFEST.json in {PORT_DIR}")
    return 0


def cmd_check(baseline: Path) -> int:
    manifest, ported, ttl = build_manifest(baseline)
    bad = [f for f, text in ported.items() if (PORT_DIR / f).read_bytes() != text.encode("utf-8")]
    if (PORT_DIR / "adprov.ttl").read_bytes() != ttl:
        bad.append("adprov.ttl")
    if MANIFEST.read_text(encoding="utf-8") != manifest_text(manifest):
        bad.append("PORT_MANIFEST.json")
    if bad:
        print("port differs from a fresh port of the baseline: " + ", ".join(bad), file=sys.stderr)
        return 1
    print("port, adprov.ttl and PORT_MANIFEST.json match a fresh port of the baseline")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=("generate", "check"))
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="baseline repository (read-only)")
    args = parser.parse_args(argv)
    return {"generate": cmd_generate, "check": cmd_check}[args.command](args.baseline)


if __name__ == "__main__":
    raise SystemExit(main())
