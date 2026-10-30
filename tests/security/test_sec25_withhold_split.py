"""A withheld member of a split archive takes the descriptor and every byte part with it (D-315; F-1 of ingest-formats-3;
D-244, D-249; HL H.4.5; G.9.5).

Synthetic only: the committed FooBench fixtures are zipped with **deflate** and cut into 700-byte parts, pinned as an
HF split archive, imported in release mode and sealed. The policy (injected at
``agentprov.corpus.withhold.policy_of_profile``, as in ``test_sec25_withhold_policy.py``) is an object-scope marker
found in one member only: no derived file and, because the parts are deflated, no part holds it. So the parts can only
be withheld by the D-315 link from their descriptor. Checked:

* sealing withholds the member, the descriptor (AD-12) and every part (basis ``container``, D-315's note); the execution
  stays released; release-mode ``chain`` passes; no part is left under ``raw/objects/``; the sidecar keeps them;
* a ledger that lists the descriptor but drops one part fails ``chain`` with ``withheld.split_part``.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import zipfile
from importlib import resources
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest
import verify_support as vs
from corpus_harness import verify

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters" / "runner"))
import test_ingest_formats_2 as t2  # noqa: E402

cli = harness.cli

#: A literal of ``sub-trace-001.jsonl`` that no derived record and no deflated part holds (asserted below).
MARKER = "Research the note topic."
SPEC = '''corpus_id = "mini-foobench-split"
corpus_version = "0.1.0"
title = "A FooBench split archive (test corpus)"
mode = "import"

[[sources]]
source_id = "foobench"
profile = "foobench@1"
parts = ["fixture"]

[[sources.snapshots]]
snapshot_id = "fixture"
origin = { kind = "hf", dataset = "owner/name", revision = "''' + "c" * 40 + '''", gated = false, path = "logs" }
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["foobench.toy@1"]
prov_specs = ["agentprov-prov/0.1"]
views = []
options = { context_encoding = "members" }

[licence]
derived = "inherit"
decided_by = "test"
files = ["LICENSE"]

[layout]
shard_depth = 1
'''
POLICY = f'''
[withhold]
reason = "secret"
public_note = "a planted value in one member of a split archive (test)"

[[withhold.rules]]
id = "member-marker"
marker = "{MARKER}"
scope = "object"
'''


def _spec(pin: dict[str, Any]) -> str:
    """The spec with the sealed snapshot origin of corpus/0.2: an archive stored as byte parts lists its parts (D-217)."""
    from agentprov.corpus.manifest import _sealed_parts

    parts = ", ".join("{ " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in sorted(part.items())) + " }"
                      for part in _sealed_parts(pin["parts"]))
    old = 'gated = false, path = "logs" }'
    assert SPEC.count(old) == 1
    return SPEC.replace(old, f'gated = false, path = "logs", parts = [{parts}] }}')


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    base = tmp_path_factory.mktemp("split")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in t2._members().items():
            archive.writestr(name, data)
    deflated = buf.getvalue()
    original = t2._zip_bytes
    t2._zip_bytes = lambda: deflated
    try:
        pin, paths = t2._split_deposit(base / "in", part_size=700, kind="hf")
    finally:
        t2._zip_bytes = original
    assert len(paths) >= 3 and not any(MARKER.encode() in p.read_bytes() for p in paths)  # deflate hides it
    report = t2._import(t2._split_tree(pin, paths), pin, base / "c", mode="release", workers=1, in_process=False)
    assert report.counters["mapped"] == 1, report.counters
    partial = base / "c.partial"
    origins = _jsonl(partial / "raw" / "origins.jsonl")
    descriptor = next(o["sha256"][7:] for o in origins if o["origin"]["kind"] == "split")
    member = next(o["sha256"][7:] for o in origins if o["origin"].get("label") == "deposit/traces/sub-trace-001.jsonl")
    derived = [p for d in ("aer", "sem", "prov") for p in (partial / d).rglob("*") if p.is_file()]
    assert derived and not any(MARKER.encode() in p.read_bytes() for p in derived)
    return {"partial": partial, "parts": [p["sha256"] for p in pin["parts"]], "descriptor": descriptor, "member": member,
            "pin": pin}


@pytest.fixture
def sealed(working_template: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import tomllib

    import seal_support as ss

    from agentprov.corpus import withhold
    from agentprov.corpus.package import ReleaseArgs, seal

    shutil.copytree(working_template["partial"], tmp_path / "c.partial", symlinks=True)
    policy = withhold.parse_policy(tomllib.loads(POLICY), profile_id="foobench", profile_version=1,
                                   profile_sha256="sha256:" + "0" * 64)
    monkeypatch.setattr(withhold, "policy_of_profile", lambda data, *, profile_id, profile_version: policy)
    profile = resources.files("agentprov").joinpath("adapters", "foobench", "profiles", "foobench.profile.toml").read_bytes()
    node = resources.files("agentprov").joinpath("adapters", "foobench", "semantics", "foobench.toy-1")
    semantics = {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name) if c.is_file()}
    inputs = ss.inputs(spec=_spec(working_template["pin"]).encode(), source_profile=profile,
                       semantics_profiles={"foobench.toy@1": semantics})
    report = seal(tmp_path / "c", corpus_version="0.1.0", inputs=inputs, release=ReleaseArgs(release_date="2026-10-14"))
    return {**working_template, "root": tmp_path / "c", "report": report}


def test_a_withheld_split_member_takes_the_descriptor_and_every_deflated_part(cli, sealed):
    from agentprov.corpus.withhold import LINK_NOTES
    from agentprov.corpus.withheld import decode_withheld

    root = sealed["root"]
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    entries = {e.sha256: e for e in document.entries}
    assert set(entries) == {sealed["member"], sealed["descriptor"], *sealed["parts"]}
    assert entries[sealed["member"]].basis == "profile_rule" and entries[sealed["descriptor"]].basis == "container"
    for part in sealed["parts"]:
        assert (entries[part].basis, entries[part].public_note) == ("container", LINK_NOTES["part"])
    assert document.executions == ()  # object scope; no derived record holds the marker
    stored = {p.name.split(".", 1)[0] for p in (root / "raw" / "objects").rglob("*") if p.is_file()}
    assert not stored & {sealed["descriptor"], *sealed["parts"]}
    side = root.with_name("c.withheld")
    assert {p.name.split(".", 1)[0] for p in (side / "raw" / "objects").rglob("*") if p.is_file()} >= set(sealed["parts"])
    check = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert check.code == 0 and check.codes() == {}, check.codes()
    assert not any(MARKER.encode() in p.read_bytes() for p in root.rglob("*") if p.is_file())


def test_a_ledger_that_drops_one_part_fails_chain(cli, sealed):
    root = sealed["root"]
    path = root / "WITHHELD.json"
    document = json.loads(path.read_bytes())
    dropped = sealed["parts"][1]
    document["entries"] = [e for e in document["entries"] if e["sha256"] != "sha256:" + dropped]
    path.chmod(0o644)
    path.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", "utf-8")
    check = verify(cli, root, "--level", "chain")
    assert check.code == 1 and "withheld.split_part" in check.codes(), check.codes()
    assert check.codes()["withheld.split_part"] == 1
