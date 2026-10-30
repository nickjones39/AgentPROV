"""Regenerate the C.16.1 worked example with the shipped mapper and profile (erratum E22; D.6.11 item 1).

    uv run python tools/agentdojo/regen_c161.py [--write]

Maps the C.16.1 artefact (``tests/fixtures/agentdojo/v0.k11/runs/…/injection_task_7.json``, the pinned blob
``4cbf0840…`` at ``c274885``) with ``agentdojo.tracelogger`` and ``agentdojo-upstream``, checks the KAT
``ex_7uz2oys57hugtsueixylme4fl5``, and prints the execution digest. With ``--write`` it rewrites the vector file
``docs/architecture/examples/C/agentdojo_2024_pi_detector.aer.jsonl`` and the C.16.1 block and digest row of
``docs/architecture/C_data_model.md``. Pins elsewhere (``tests/unit/aer/test_seal.py``) are updated by hand, on purpose.
Prints digests only.

Since ``aer/0.2`` (deferrals part C, D-212) the writer seals ``"aer": "0.2"``. The published C.16 vectors stay
``aer/0.1`` (C.21): the vector and the spec block are the mapper's records with the header's ``aer`` member set to
``"0.1"`` and resealed (they differ from the ``aer/0.2`` output only there and in the seal), and the ``aer/0.2`` copy
``examples/C/aer-0.2/agentdojo_2024_pi_detector.aer.jsonl`` is the mapper's output as written.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VECTOR = REPO / "docs" / "architecture" / "examples" / "C" / "agentdojo_2024_pi_detector.aer.jsonl"
VECTOR_02 = REPO / "docs" / "architecture" / "examples" / "C" / "aer-0.2" / "agentdojo_2024_pi_detector.aer.jsonl"
SPEC = REPO / "docs" / "architecture" / "C_data_model.md"
REL = "runs/gpt-4o-2024-05-13-transformers_pi_detector/banking/user_task_13/important_instructions/injection_task_7.json"
FIXTURE = REPO / "tests" / "fixtures" / "agentdojo" / "v0.k11" / REL
SHA256 = "99e641af97e56971dd67308beec96ac08fdca7063141f3714389733ba845cc8a"
BLOB = "4cbf084087345a813c6d93e99aa2d37eec2ca507"
COMMIT = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
KAT1 = "ex_7uz2oys57hugtsueixylme4fl5"


def regenerate() -> tuple[bytes, str]:
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.adapters.types import Origin

    raw = FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise SystemExit("the C.16.1 fixture does not have its pinned sha256")
    outcome, _unit = map_artefact(raw, Origin.git("https://github.com/ethz-spylab/agentdojo", COMMIT, REL, BLOB),
                                  profile_id="agentdojo-upstream")
    data, info = aer_bytes(outcome)
    if info.ex != KAT1:
        raise SystemExit(f"KAT broken: {info.ex}")
    return data, info.execution_digest


def as_aer_01(data: bytes) -> tuple[bytes, str]:
    """The records of an ``aer/0.2`` file resealed as the frozen ``aer/0.1`` vector: the header's ``aer`` member set to
    ``"0.1"`` and the seal's ``records_sha256`` recomputed (C.11.6), every other byte unchanged."""
    import json

    from agentprov.aer.canon import dumps_line

    lines = data.split(b"\n")[:-1]
    header, seal = json.loads(lines[0]), json.loads(lines[-1])
    header["aer"] = "0.1"
    body = dumps_line(header) + b"".join(line + b"\n" for line in lines[1:-1])
    seal["records_sha256"] = hashlib.sha256(body).hexdigest()
    return body + dumps_line(seal), seal["records_sha256"]


def rewrite_spec(data: bytes, digest: str) -> None:
    text = SPEC.read_text(encoding="utf-8")
    head, sep, tail = text.partition("### C.16.1 AgentDojo June-2024 native log (PI-detector pipeline)")
    start = tail.index("```jsonl\n") + len("```jsonl\n")
    end = tail.index("```", start)
    tail = tail[:start] + data.decode("utf-8") + tail[end:]
    head = re.sub(r"(\| C\.16\.1 AgentDojo June-2024 \|.*\| `fd33a762…1345` \| `)[0-9a-f]{64}(` \|)",
                  lambda m: m.group(1) + digest + m.group(2), head)
    SPEC.write_text(head + sep + tail, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    written, _digest_02 = regenerate()
    data, digest = as_aer_01(written)
    print(f"C.16.1: {len(data.splitlines())} records, {len(data)} bytes, ex {KAT1}, execution digest {digest} (aer/0.1)")
    if args.write:
        VECTOR.write_bytes(data)
        VECTOR_02.write_bytes(written)
        rewrite_spec(data, digest)
        print(f"wrote {VECTOR.relative_to(REPO)}, {VECTOR_02.relative_to(REPO)} and the C.16.1 block of "
              f"{SPEC.relative_to(REPO)}")
    elif VECTOR.read_bytes() != data or VECTOR_02.read_bytes() != written:
        print("the committed vector differs: run with --write")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
