"""Recomputation determinism (E.9): byte-identical PROV-JSON across runs and processes with different hash seeds, and
independence from the order of ``ext`` members."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prov_support as ps  # noqa: E402

from agentprov.prov.engine import derive  # noqa: E402

SCRIPT = """
import sys
sys.path.insert(0, {here!r})
import prov_support as ps
from agentprov.aer.reader import load_aer
from agentprov.prov.engine import derive
sys.stdout.buffer.write(derive(load_aer({path!r}), registry=ps.registry()).prov_json)
"""


def test_same_bytes_in_fresh_processes_with_different_hash_seeds(tmp_path: Path) -> None:
    path = tmp_path / "g.aer.jsonl"
    ps.write_aer(ps.generic_records(), path)
    here = str(Path(__file__).resolve().parent)
    outputs = []
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "TZ": "Pacific/Auckland" if seed == "1" else "UTC"}
        done = subprocess.run([sys.executable, "-c", SCRIPT.format(here=here, path=str(path))], env=env,
                              capture_output=True, check=True, timeout=120)
        outputs.append(done.stdout)
    assert outputs[0] and outputs[0] == outputs[1] == outputs[2]


def test_repeated_derivation_is_byte_identical(tmp_path: Path) -> None:
    doc = ps.write_aer(ps.generic_records(), tmp_path / "g.aer.jsonl")
    first = derive(doc, registry=ps.registry())
    second = derive(doc, registry=ps.registry())
    assert first.prov_json == second.prov_json
    assert first.digests == second.digests and first.digests["prov_json"].startswith("sha256:")


def test_emit_content_is_an_option_in_every_key(tmp_path: Path) -> None:
    from agentprov.prov.engine import ProvOptions

    doc = ps.write_aer(ps.generic_records(), tmp_path / "g.aer.jsonl")
    plain = derive(doc, registry=ps.registry())
    content = derive(doc, registry=ps.registry(), options=ProvOptions(emit_content=True))
    assert {b.derivation_key for b in plain.bundles}.isdisjoint({b.derivation_key for b in content.bundles})
    assert b'"apv:text"' not in plain.prov_json and b'"apv:text"' in content.prov_json


def test_the_engine_agent_is_version_free(tmp_path: Path) -> None:
    """DECISIONS D-13: the software version is not in the document (it is recorded in the corpus derivation.json)."""
    doc = ps.write_aer(ps.generic_records(), tmp_path / "g.aer.jsonl")
    result = derive(doc, registry=ps.registry())
    agents = result.document["agent"]
    assert "sw:agentprov" in agents and "apv:softwareVersion" not in agents["sw:agentprov"]
    assert b'"sw:agentprov.' not in result.prov_json
