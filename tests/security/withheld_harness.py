"""A purged working corpus sealed as a new corpus version that withholds the purged object (P-3; G.9.5, G.9.6; H.4.5;
D-230..D-236). Helpers for the withholding suites (``withheld_harness``; not collected).

The template is built once per session, as an operator would: two synthetic AgentDojo logs are imported in release mode
(T1 worker, a test pin that vouches for every file); one tool output carries a credential-shaped sentinel assembled at run
time (no source file holds it whole). A copy is sealed as ``0.1.0`` (the version released before the leak was found);
then the working corpus is purged (``agentprov.corpus.purge``: tombstone, ``release.withheld``, unlink) and sealed as
``0.2.0`` with ``release.previous`` naming ``0.1.0``. Every test gets a fresh copy of the ``0.2.0`` corpus and of its
private sidecar ``DIR.withheld/``. Everything lives under pytest's temporary directories; nothing under ``~/.agentprov``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Final

#: The leaked value (fake; assembled at run time) and every 8-character fragment of it. Never printed.
SECRET: Final = "sk-" + "live-" + "Qzxv" + "-" + "k9f2m7p4t1w8r6n3y5"
FRAGMENTS: Final = [SECRET[i:i + 8] for i in range(len(SECRET) - 7)]
DAY: Final = "2026-10-12"

_TEMPLATE: dict[str, Any] = {}


def fragments_in(data: bytes | str) -> int:
    """How many 8-character fragments of :data:`SECRET` the text holds (a count, so a failure never prints the value)."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    return sum(1 for f in FRAGMENTS if f in text)


def _import(inp: Path, corpus: Path) -> Any:
    import import_support as support
    import seal_support as ss

    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    with CorpusWriter(corpus) as writer:
        return import_source("agentdojo", LocalTree(inp), corpus=writer, part="2024-06", workers=1, mode="release",
                             pin_check=support.vouch(inp), pin=ss.PIN)


def spec(version: str) -> bytes:
    import seal_support as ss

    return ss.SPEC.replace('corpus_version = "0.1.0"', f'corpus_version = "{version}"').encode()


CHANGES_020: Final = b'''[[change]]
version = "0.1.0"
bump = "initial"
summary = "Test corpus."

[[change]]
version = "0.2.0"
bump = "major"
summary = "One raw object was purged (a leaked credential); this version withholds it and the execution derived from it (G.9.5)."
'''


def _build(base: Path) -> dict[str, Any]:
    import agentdojo_support as ad
    import seal_support as ss

    from agentprov.corpus import purge
    from agentprov.corpus.package import ReleaseArgs, seal

    inp = base / "in"
    leaking = ad.base_log()
    leaking["messages"][3]["content"] = f"api key: {SECRET}"
    clean = ad.base_log(user_task_id="user_task_2")
    for doc in (leaking, clean):
        path = inp / ad.path_of(doc)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ad.log_bytes(doc))
    working = base / "work" / "c"
    assert _import(inp, working).exit_code == 0
    partial = working.with_name("c.partial")
    leak = hashlib.sha256((inp / ad.path_of(leaking)).read_bytes()).hexdigest()
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_bytes().split(b"\n") if line]
    ex = next(r["ex"] for r in rows if r["raw"][0]["sha256"] == "sha256:" + leak)
    aer_digest = next(r["digests"]["aer"] for r in rows if r["ex"] == ex)

    # 0.1.0: released before the leak was found (a copy of the same working corpus)
    first = base / "v010" / "c"
    first.parent.mkdir(parents=True)
    shutil.copytree(partial, first.with_name("c.partial"), symlinks=True)
    v010 = seal(first, corpus_version="0.1.0", inputs=ss.inputs(), release=ReleaseArgs(release_date="2026-10-01"))

    # the purge, then 0.2.0
    plan = purge.plan_corpus(partial, leak, "secret", today=lambda: DAY)
    purge.apply(plan)
    release = ReleaseArgs(release_date=DAY, previous={"content_digest": v010.content_digest, "corpus_version": "0.1.0"})
    report = seal(working, corpus_version="0.2.0", inputs=ss.inputs(spec=spec("0.2.0"), changes=CHANGES_020),
                  release=release)
    return {"root": working, "sidecar": working.with_name("c.withheld"), "leak": leak, "ex": ex, "aer_digest": aer_digest,
            "report": report, "v010": v010, "first": first}


def purged_sealed(tmp_path_factory: Any, where: Path) -> dict[str, Any]:
    """A fresh copy of the sealed ``0.2.0`` corpus (``where/c``) and its sidecar (``where/c.withheld``)."""
    if "built" not in _TEMPLATE:
        _TEMPLATE["built"] = _build(tmp_path_factory.mktemp("withheld-template"))
    built = _TEMPLATE["built"]
    where.mkdir(parents=True, exist_ok=True)
    root, sidecar = where / "c", where / "c.withheld"
    shutil.copytree(built["root"], root, symlinks=True)
    shutil.copytree(built["sidecar"], sidecar, symlinks=True)
    return {**built, "root": root, "sidecar": sidecar}


def files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
