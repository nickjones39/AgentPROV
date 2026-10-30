"""The C.16 examples embedded in docs/architecture/C_data_model.md are valid AERs: each block's records hash to the
``records_sha256`` its seal states, and each block equals its vector file under docs/architecture/examples/C line for
line (the C.16.4 block once carried item 3's edits without a reseal; regeneration-batch item 30)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SPEC = REPO / "docs" / "architecture" / "C_data_model.md"
VECTORS = REPO / "docs" / "architecture" / "examples" / "C"
NAMES = ("agentdojo_2024_pi_detector", "adprov_v1_llama_injecagent", "stac_case_223", "rope_denial_qwen_autodojo")


def _blocks() -> dict[str, list[str]]:
    """Every run of JSON lines in the spec that starts with an execution header and ends with a seal, by ``ex``."""
    lines = SPEC.read_text(encoding="utf-8").split("\n")
    out: dict[str, list[str]] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('{"') and '"k":"execution"' in line:
            j = i
            while j + 1 < len(lines) and lines[j + 1].startswith("{"):
                j += 1
            block = lines[i:j + 1]
            if json.loads(block[-1]).get("k") == "seal":
                out[json.loads(line)["ex"]] = block
            i = j
        i += 1
    return out


@pytest.mark.parametrize("name", NAMES)
def test_the_spec_block_is_the_vector_and_its_seal_holds(name: str) -> None:
    vector = (VECTORS / f"{name}.aer.jsonl").read_text(encoding="utf-8").splitlines()
    ex = json.loads(vector[0])["ex"]
    block = _blocks().get(ex)
    assert block is not None, f"no C.16 block for {name} ({ex}) in C_data_model.md"
    assert block == vector, f"the spec block of {name} differs from its vector file"
    body = "".join(line + "\n" for line in block[:-1]).encode("utf-8")
    assert json.loads(block[-1])["records_sha256"] == hashlib.sha256(body).hexdigest()
