"""Helpers for the deposit-builder tests (``release_support``; not collected).

Sealed test corpora are built from U3's ``seal_support`` working corpus (three golden June-2024 AgentDojo logs, licence-
cleared fixtures whose text is never printed): the corpus spec's ``corpus_id`` and ``[licence] derived`` are varied to
make corpora of different licence classes (MIT by inheritance, GPL-3.0-only, AGPL-3.0-only, CC-BY-4.0, CC-BY-NC-4.0
by user decision). One sealed template per variant is built per session; each test gets a copy.

:func:`restamp` makes a **synthetic** variant of a sealed copy for refusal tests that sealing itself cannot produce (a
restriction the source profile does not carry, an interpreter advisory, a ``test_only`` live block, a ``withhold``
snapshot, a ``views/`` file): it edits ``corpus.json``, recomputes the content digest and rewrites
``checksums.sha256``, so the copy is internally consistent. It is a test device, never a way to build a corpus.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import seal_support as ss

from agentprov.corpus.integrity import content_digest, write_checksums
from agentprov.corpus.package import seal
from agentprov.release.builder import DepositProducer, DepositReport, build_deposit
from agentprov.release.metadata import (
    GITLEAKS_CONFIG_SHA256,
    GITLEAKS_VERSION,
    PATH_SCAN_TOOL,
    PATH_SCAN_VERSION,
    RELEASE_SCAN_FORMAT,
    Creator,
    ReleaseMetadata,
)

RELEASE_DATE = date(2026, 10, 11)
AGENTHARM_CLAUSE = "test restricted-use clause: use limited to improving AI safety and security (synthetic)"
METADATA = ReleaseMetadata(title="AgentPROV test deposit", creators=(Creator("Test Creator"),), keywords=("test",),
                           description_preamble="A deposit draft built by the test suite.")
PRODUCER = DepositProducer(agentprov_version="0.1.0", git_commit=ss.COMMIT, git_tree_clean=True, python="3.14.8",
                           zlib_version="1.2.12")

_TEMPLATES: dict[tuple[str, str, str], Path] = {}


def spec_for(corpus_id: str, derived: str = "inherit", version: str = "0.1.0") -> bytes:
    text = ss.SPEC.replace('corpus_id = "mini-agentdojo"', f'corpus_id = "{corpus_id}"')
    text = text.replace('derived = "inherit"', f'derived = "{derived}"')
    text = text.replace('corpus_version = "0.1.0"', f'corpus_version = "{version}"')
    return text.encode()


def _template(tmp_path_factory: Any, corpus_id: str, derived: str, version: str) -> Path:
    key = (corpus_id, derived, version)
    if key not in _TEMPLATES:
        dest = tmp_path_factory.mktemp(f"sealed-{corpus_id}") / corpus_id
        ss.working_corpus(tmp_path_factory, dest)
        changes = ss.CHANGES.replace('version = "0.1.0"', f'version = "{version}"').encode()
        seal(dest, corpus_version=version, inputs=ss.inputs(spec=spec_for(corpus_id, derived, version), changes=changes))
        _TEMPLATES[key] = dest
    return _TEMPLATES[key]


def sealed(tmp_path_factory: Any, where: Path, corpus_id: str = "mini-mit", derived: str = "inherit",
           version: str = "0.1.0") -> Path:
    """A fresh copy of the sealed template ``(corpus_id, derived, version)`` at ``where/<corpus_id>``."""
    dest = where / corpus_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_template(tmp_path_factory, corpus_id, derived, version), dest, symlinks=True)
    return dest


def manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "corpus.json").read_text("utf-8"))


def restamp(root: Path, change: Callable[[dict[str, Any]], None] | None = None, *,
            add: Mapping[str, bytes] | None = None) -> None:
    """Synthetic variant of a sealed copy (see the module docstring)."""
    m = manifest(root)
    if change is not None:
        change(m)
    m["content_digest"] = content_digest(m)
    (root / "corpus.json").write_bytes((json.dumps(m, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode())
    for label, data in (add or {}).items():
        path = root.joinpath(*label.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "checksums.sha256").unlink()
    write_checksums(root)


def add_restriction(m: dict[str, Any], clause: str = AGENTHARM_CLAUSE) -> None:
    restrictions = sorted({*m["licences"]["restrictions"], clause})
    m["licences"]["restrictions"] = restrictions
    m["licences"]["class"]["restrictions"] = restrictions


def scan_document(root: Path, digest: str, findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    m = manifest(root)
    rows = findings or []
    return {"findings": rows, "format": RELEASE_SCAN_FORMAT,
            "summary": {"by_triage": {}, "findings": len(rows)},
            "target": {"corpus_id": m["corpus_id"], "corpus_version": m["corpus_version"], "kind": "corpus",
                       "root_digest": digest},
            "tools": [{"config_sha256": GITLEAKS_CONFIG_SHA256, "name": "gitleaks", "version": GITLEAKS_VERSION},
                      {"name": PATH_SCAN_TOOL, "version": PATH_SCAN_VERSION}]}  # the pinned scanners (G.9.4)


def clean_scan(root: Path, digest: str) -> dict[str, Any]:
    """An injected scanner with no finding (tests run without gitleaks)."""
    return scan_document(root, digest)


def build(corpora: list[Path], out: Path, **kwargs: Any) -> DepositReport:
    kwargs.setdefault("scan", clean_scan)
    kwargs.setdefault("release_date", RELEASE_DATE)
    kwargs.setdefault("producer", PRODUCER)
    metadata = kwargs.pop("metadata", METADATA)
    return build_deposit(corpora, metadata, out, **kwargs)


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


_ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_HEX = "0123456789abcdef"


def secret_shapes(seed: int = 0) -> list[tuple[str, str]]:
    """``(rule, value)``: one synthetic value per native secret shape of ``tools/release_scan.py`` (D-600; two for
    ``github-app-token``, one per prefix). Assembled at run time from a seeded generator, so no token-shaped literal is
    committed and the repository's own gitleaks hook never sees one; random enough for gitleaks' entropy floor. The Hugging
    Face value is letters only, the form gitleaks' own rule matches too. They name no account and hold no credential."""
    import random

    rnd = random.Random(seed)

    def pick(n: int, alphabet: str = _ALNUM) -> str:
        return "".join(rnd.choice(alphabet) for _ in range(n))

    def uuid() -> str:
        return "-".join(pick(n, _HEX) for n in (8, 4, 4, 4, 12))

    return [("github-pat", "gh" + "p_" + pick(36)), ("github-oauth", "gh" + "o_" + pick(36)),
            ("github-app-token", "gh" + "u_" + pick(36)), ("github-app-token", "gh" + "s_" + pick(36)),
            ("github-refresh-token", "gh" + "r_" + pick(36)),
            ("github-fine-grained-pat", "github" + "_pat_" + pick(82, _ALNUM + "_")),
            ("huggingface-access-token", "h" + "f_" + pick(34, _LETTERS)),
            ("langfuse-secret-key", "sk" + "-lf-" + uuid()), ("langfuse-public-key", "pk" + "-lf-" + uuid())]
