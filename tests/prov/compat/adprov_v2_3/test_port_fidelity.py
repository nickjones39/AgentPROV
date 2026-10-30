"""Port fidelity of the ``adprov-v2.3-compat`` oracle (J.3.3; K.7.1; RM-2; RESOLUTIONS R-31).

The five oracle files are AST-equal to the baseline at ``579a908`` with import statements as the only change. CI does not
have the baseline repository, so the check is against ``PORT_MANIFEST.json``: it pins, for every file, the baseline sha256,
the import-masked AST digest (algorithm in ``tools/compat_port.py``) and the sha256 of the port. A second, local-only test
(``full_corpus``) re-reads the baseline repository when it is present and re-derives all of it.

The copies of the originals under ``tests/fixtures/compat_originals/`` that J.3.3 mentions are replaced by these digests.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
PORT_DIR = REPO / "src" / "agentprov" / "prov" / "compat" / "adprov_v2_3"
MANIFEST_PATH = PORT_DIR / "PORT_MANIFEST.json"
FILES = ("build_prov", "prov_emit", "labeling", "validate", "conformance")

BASELINE_COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"
#: sha256 prefixes of the five baseline files, as printed in J.3.3.
SPEC_PREFIXES = {
    "build_prov.py": "7079925a632a5b24",
    "prov_emit.py": "021b2d5ad8e45502",
    "labeling.py": "943d9b530a292ae5",
    "validate.py": "df8e49be9c072c0a",
    "conformance.py": "9648d0fd6a363dec",
}
PORT_PACKAGE = "agentprov.prov.compat.adprov_v2_3"
YAML_SHIM_IMPORT = f"from {PORT_PACKAGE} import yaml_shim as yaml"
ALLOWED_THIRD_PARTY = frozenset({"prov", "rdflib", "pyshacl"})  # conformance.py and its lazy imports


def _load_tool() -> ModuleType:
    """``tools/compat_port.py``: the generator owns the digest algorithm, so the check cannot drift from it."""
    spec = importlib.util.spec_from_file_location("_compat_port_tool", REPO / "tools" / "compat_port.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _source(name: str) -> str:
    return (PORT_DIR / f"{name}.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- the manifest


def test_manifest_pins_the_baseline_commit_and_the_five_files(manifest):
    assert manifest["schema"] == "agentprov-compat-port-manifest/1"
    assert manifest["spec_id"] == "adprov-v2.3-compat"
    assert manifest["status"] == "apv:RegressionOracle"
    assert manifest["baseline"]["commit"] == BASELINE_COMMIT
    assert manifest["ast_digest"]["algorithm"] == tool.DIGEST_ALGORITHM
    assert sorted(manifest["files"]) == sorted(f"{n}.py" for n in FILES)


@pytest.mark.parametrize("filename", sorted(SPEC_PREFIXES))
def test_manifest_baseline_sha256_matches_the_specification(manifest, filename):
    assert manifest["files"][filename]["baseline_sha256"].startswith(SPEC_PREFIXES[filename])


# ---------------------------------------------------------------------------------------------- the port


@pytest.mark.parametrize("name", FILES)
def test_the_port_is_ast_equal_to_the_baseline_apart_from_imports(manifest, name):
    entry = manifest["files"][f"{name}.py"]
    assert tool.normalised_ast_digest(_source(name)) == entry["ast_sha256"]


@pytest.mark.parametrize("name", FILES)
def test_the_port_bytes_are_pinned(manifest, name):
    data = (PORT_DIR / f"{name}.py").read_bytes()
    assert hashlib.sha256(data).hexdigest() == manifest["files"][f"{name}.py"]["port_sha256"]
    assert b"\r" not in data
    assert data.count(b"\n") + (0 if data.endswith(b"\n") else 1) == manifest["files"][f"{name}.py"]["baseline_lines"]


@pytest.mark.parametrize("name", FILES)
def test_the_manifest_lists_every_import_statement_and_every_change(manifest, name):
    entry = manifest["files"][f"{name}.py"]
    actual = tool.import_records(_source(name))
    assert [(r["line"], r["end_line"], r["text"]) for r in actual] == [
        (r["line"], r["end_line"], r["port"]) for r in entry["imports"]
    ]
    for record in entry["imports"]:
        if not record["changed"]:
            assert record["baseline"] == record["port"]
            continue
        # the only two permitted rewrites (R-31)
        if record["baseline"] == "import yaml":
            assert record["port"] == YAML_SHIM_IMPORT
            assert name == "build_prov"
        else:
            assert record["baseline"].startswith("from agentdojo_prov.")
            assert record["port"] == record["baseline"].replace("from agentdojo_prov.", f"from {PORT_PACKAGE}.", 1)


def test_exactly_the_recorded_imports_changed(manifest):
    changed = {
        f"{name}.py:{r['line']}": r["port"]
        for name in FILES
        for r in manifest["files"][f"{name}.py"]["imports"]
        if r["changed"]
    }
    assert sorted(changed) == [
        "build_prov.py:251",
        "build_prov.py:31",
        "build_prov.py:37",
        "conformance.py:49",
        "conformance.py:50",
        "validate.py:16",
        "validate.py:263",
    ]


@pytest.mark.parametrize("name", FILES)
def test_the_oracle_imports_only_the_stdlib_prov_rdflib_pyshacl_and_its_own_modules(name):
    stdlib = sys.stdlib_module_names
    bad = []
    for node in ast.walk(ast.parse(_source(name))):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in the oracle"
            targets = [node.module or ""]
        else:
            continue
        for target in targets:
            top = target.split(".")[0]
            if top in stdlib or top in ALLOWED_THIRD_PARTY:
                continue
            if target == PORT_PACKAGE or target.startswith(PORT_PACKAGE + "."):
                continue
            bad.append(f"{name}.py:{node.lineno} imports {target}")
    assert bad == []


def test_the_oracle_never_imports_yaml_or_a_benchmark_package_directly():
    for name in FILES:
        for node in ast.walk(ast.parse(_source(name))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for target in names:
                assert target.split(".")[0] not in {"yaml", "agentdojo", "agentdojo_prov", "agentprov_backend"}, (
                    f"{name}.py:{node.lineno} imports {target}"
                )


def test_the_only_yaml_route_is_the_shim_over_yamlsafe():
    shim = ast.parse((PORT_DIR / "yaml_shim.py").read_text(encoding="utf-8"))
    imported = {
        (node.module, alias.name) for node in ast.walk(shim) if isinstance(node, ast.ImportFrom) for alias in node.names
    }
    assert ("agentprov.ingest", "yamlsafe") in imported
    assert not any(isinstance(node, ast.Import) and any(a.name == "yaml" for a in node.names) for node in ast.walk(shim))


# ---------------------------------------------------------------------------------------------- the checker itself


def test_the_digest_ignores_imports_but_sees_every_other_change():
    base = "import os\n\ndef f(x):\n    '''doc'''\n    return x + 1\n"
    digest = tool.normalised_ast_digest(base)
    assert tool.normalised_ast_digest(base.replace("import os", "from a.b import c")) == digest
    assert tool.normalised_ast_digest(base.replace("+ 1", "+ 2")) != digest
    assert tool.normalised_ast_digest(base.replace("+ 1", "+ 1.0")) != digest
    assert tool.normalised_ast_digest(base.replace("'''doc'''", "'''dox'''")) != digest
    assert tool.normalised_ast_digest(base.replace("x +", "x -")) != digest
    assert tool.normalised_ast_digest(base + "\nimport sys\n") != digest  # an added statement is not masked away
    assert tool.normalised_ast_digest(base.replace("return x + 1", "return (x + 1)  # c")) == digest  # comments, parens


def test_porting_rewrites_only_import_lines():
    src = "from agentdojo_prov.labeling import (\n    A,\n)\n\n\ndef f():\n    import yaml\n    return yaml.safe_load('a')\n"
    ported = tool.port_source(src, "x")
    assert ported.count("\n") == src.count("\n")
    changed = [i for i, (a, b) in enumerate(zip(src.split("\n"), ported.split("\n"), strict=True)) if a != b]
    assert changed == [0, 6]
    assert tool.normalised_ast_digest(ported) == tool.normalised_ast_digest(src)


# ---------------------------------------------------------------------------------------------- the frozen ontology


def test_the_ontology_copy_is_the_frozen_baseline_file(manifest):
    data = (PORT_DIR / "adprov.ttl").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest.startswith("4a9dcf4a") and digest.endswith("dca3")  # K.16(3)
    assert digest == manifest["adprov_ttl"]["sha256"]


# ---------------------------------------------------------------------------------------------- local only


def _baseline_repo() -> Path | None:
    for candidate in (os.environ.get("AGENTPROV_BASELINE_REPO"), str(REPO.parent / "AgentDojo-PROV-framework")):
        if candidate and (Path(candidate) / ".git").exists():
            return Path(candidate)
    return None


@pytest.mark.full_corpus
def test_the_port_is_a_fresh_port_of_the_baseline_repository(manifest):
    """Local only: needs the baseline repository (``AGENTPROV_BASELINE_REPO`` or the sibling checkout)."""
    repo = _baseline_repo()
    if repo is None:
        pytest.skip("baseline repository not available (set AGENTPROV_BASELINE_REPO)")
    probe = subprocess.run(  # noqa: S603 - fixed argv and a pinned commit
        ["git", "-C", str(repo), "cat-file", "-e", f"{BASELINE_COMMIT}^{{commit}}"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("baseline repository does not contain commit 579a908")
    fresh, ported, ttl = tool.build_manifest(repo)
    assert fresh == manifest
    for filename, text in ported.items():
        assert (PORT_DIR / filename).read_bytes() == text.encode("utf-8"), filename
    assert (PORT_DIR / "adprov.ttl").read_bytes() == ttl
    assert MANIFEST_PATH.read_text(encoding="utf-8") == tool.manifest_text(fresh)
