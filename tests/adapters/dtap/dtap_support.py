"""Helpers for the ``dtap`` adapter tests (imported as ``dtap_support``; not collected).

The committed fixtures (tests/fixtures/dtap/, built by tools/dtap/build_fixtures.py) sit at their dataset paths below
``runs/`` (trajectories and judges, byte-identical except F16, whose one third-party account token is replaced by
``user``: fixture scrub 2026-10-21, SOURCE.json ``derived_from``), ``tasks/`` (configurations without ``env_vars``, byte-identical) and
``derived/tasks/`` (configurations with ``env_vars`` deleted). The files hold prompt-injection payloads by design: they
are data, and no helper prints their content.

* :func:`map_label` maps one primary file the way the import pipeline's ``map`` job does (the reader's
  ``auxiliary_for`` plan, ``map_artefact_total`` with the auxiliary rows), returning the sealed AER and its SEM and PROV;
* :func:`run_import` runs ``import_source`` on a tree assembled from the fixtures (runner items R1-R3).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.dtap.dialect import DtapTrajectoryReader
from agentprov.adapters.dtap.matcher import needles
from agentprov.adapters.dtap.semantics.tools import PROFILE_VERSION
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import (
    ContextTree,
    LocalTree,
    PinCheck,
    PinnedObject,
    _AuxListing,
    aux_media,
    git_blob_sha1,
    import_source,
)
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.corpus.writer import CorpusWriter

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "dtap"
RUNS_REPO = "https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories"
RUNS_COMMIT = "836caf2fdd78b888ddd14fb62dc038e932e17898"
TASKS_REPO = "https://huggingface.co/datasets/AI-Secure/DecodingTrust-Agent-Platform"
TASKS_COMMIT = "a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04"
PROFILE = "dtap-bench"

#: Fixture ids -> the primary trajectory (dataset path) the tests map.
F = {
    "F01": "openaisdk/gpt-5.2/code/benign/math/57/20260220_133459.json",
    "F02": "openaisdk/gpt-5.2/workflow/malicious/direct/sensitive-file-deletion/011/20260418_191506.json",
    "F03": "openaisdk/gpt-5.2/travel/malicious/indirect/payment-credential-collection/005/20260329_151728.json",
    "F04": "claudesdk/claude-sonnet-4-5/macos/malicious/indirect/system-integrity/6/20260425_061317.json",
    "F05": "claudesdk/claude-opus-4-6/research/benign/search-related-paper/11/20260318_204842.json",
    "F06": "googleadk/gemini-3-pro-preview/telecom/malicious/indirect/refund_violation/014/20260403_161754.json",
    "F07": "openclaw/claude-opus-4-6/code/malicious/indirect/Bias-code-generation/7/20260316_194029.json",
    "F08": "openclaw/gpt-5.2/telecom/malicious/indirect/privacy_leak_email/007/20260221_052816.json",
    "F09": "openaisdk/gpt-5.4/finance/malicious/direct_prompt/churning/9/20260323_063933.json",
    "F10": "googleadk/gemini-3-pro-preview/medical/malicious/direct_no_attack/excessive-test/014/20260224_003510.json",
    "F11": "googleadk/gemini-3-pro-preview/windows/benign/60/20260409_015822.json",
    "F12": "openaisdk/gpt-5.2/windows/malicious/indirect/privilege-escalation/1/20260322_130400.json",
    "F13": "googleadk/gemini-3-pro-preview/medical/benign/diagnostic-qa-214/20260223_224829.json",
    "F14": "claudesdk/claude-opus-4-6/macos/benign/1/20260425_035217.json",
    "F15": "googleadk/gemini-3-pro-preview/windows/malicious/direct_prompt/data-exfiltration/7/20260402_102744.json",
    "F16": "googleadk/gemini-3-pro-preview/workflow/benign/53/trajectory.json",
    "F17": "claudesdk/claude-sonnet-4-5/workflow/malicious/indirect/financial-fraud/007/trajectory.json",
    "F18": "googleadk/gemini-3-pro-preview/customer-service/malicious/direct/pii_disclosure/pii-1_004/20260321_084002.json",
    "F19": "googleadk/gemini-3-pro-preview/os-filesystem/malicious/direct/consent-violations/32/20260313_174954.json",
    "F20a": "googleadk/gemini-3-pro-preview/telecom/malicious/indirect/credential_takeover/011/20260402_213642.json",
    "F20b": "googleadk/gemini-3-pro-preview/telecom/malicious/indirect/credential_takeover/011/20260403_154959.json",
    "F21": "claudesdk/claude-sonnet-4-5/windows/benign/32/20260401_095722.json",
    "X01": "openclaw/gpt-5.2/customer-service/malicious/direct/policy_misrepresentation/pol-1_002/20260320_101852.json",
    "X02": "openaisdk/gpt-5.2/research/malicious/direct/Biosecurity_Risks/42/judge_result.json",
    "X03": "openaisdk/gpt-5.1/finance/malicious/direct/pig_butchering/5/20260319_195025_1.json",
    "X04": "openaisdk/gpt-5.1/legal/malicious/direct_prompt/fabricated_evidence/20/20260327_005714.json",
}
#: The fixtures that are executions (F17 is synthetic, F21 an LFS pointer).
MAPPED = tuple(k for k in F if k not in ("F17", "F21"))


@cache
def source_entries() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def runs_files() -> dict[str, bytes]:
    """Dataset path -> bytes of every committed run-tree file."""
    out: dict[str, bytes] = {}
    for e in source_entries():
        sample = str(e["sample_file"])
        if sample.startswith("runs/"):
            out[sample.removeprefix("runs/")] = (FIXTURES / sample).read_bytes()
    return out


def tasks_files() -> dict[str, bytes]:
    """Configuration path -> bytes (verbatim, or the derived copy without env_vars)."""
    out: dict[str, bytes] = {}
    for e in source_entries():
        sample = str(e["sample_file"])
        for prefix in ("tasks/", "derived/tasks/"):
            if sample.startswith(prefix):
                out[sample.removeprefix(prefix)] = (FIXTURES / sample).read_bytes()
    return out


def git_origin(repo: str, commit: str, path: str, data: bytes) -> Origin:
    return Origin.git(repo, commit, path, git_blob_sha1(data))


@dataclass
class Mapped:
    label: str
    outcome: MapOutcome
    data: bytes
    doc: AerDocument
    sem: Any = None
    prov: Any = None

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.doc.records

    @property
    def header(self) -> dict[str, Any]:
        return self.doc.header

    @property
    def issues(self) -> list[dict[str, Any]]:
        return list(self.doc.seal.get("issues", []))

    def codes(self) -> list[str]:
        return [i["code"] for i in self.issues]

    def get(self, rid: str) -> dict[str, Any]:
        found = self.doc.get(rid)
        assert found is not None, rid
        return found

    def of(self, kind: str) -> list[dict[str, Any]]:
        return self.doc.of_kind(kind)

    def annotations(self, type_: str | None = None) -> list[dict[str, Any]]:
        assert self.sem is not None
        return [a for a in self.sem.annotations if type_ is None or a["type"] == type_]


def map_label(label: str, *, runs: Mapping[str, bytes] | None = None, tasks: Mapping[str, bytes] | None = None,
              sem: bool = False, prov: bool = False, data: bytes | None = None, origin: Origin | None = None) -> Mapped:
    """Map one primary file as the import pipeline's ``map`` job would (auxiliary rows from the reader's plan)."""
    runs = dict(runs_files() if runs is None else runs)
    tasks = dict(tasks_files() if tasks is None else tasks)
    reader = DtapTrajectoryReader()
    listing = _AuxListing(runs, {"tasks": list(tasks)})
    plan = reader.auxiliary_for(label, listing)
    rows: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for role, ref in sorted(plan.items()):
        if role.startswith("copy:"):
            continue
        if ref.startswith("tasks:"):
            path = ref.removeprefix("tasks:")
            raw, row_origin = tasks[path], git_origin(TASKS_REPO, TASKS_COMMIT, path, tasks[path])
        else:
            raw, row_origin = runs[ref], git_origin(RUNS_REPO, RUNS_COMMIT, ref, runs[ref])
        rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": hashlib.sha256(raw).hexdigest(),
                     "size": len(raw), "origin": row_origin.to_json()})
        blobs[role] = raw
    primary = runs[label] if data is None else data
    outcome, _unit = map_artefact_total(primary, origin or git_origin(RUNS_REPO, RUNS_COMMIT, label, primary),
                                        profile_id=PROFILE, auxiliary=rows, auxiliary_bytes=blobs)
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    result = Mapped(label, outcome, sealed, doc)
    if sem or prov:
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("dtap.tools", PROFILE_VERSION)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


def write_tree(root: Path, files: Mapping[str, bytes]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def vouch(root: Path, repo: str, commit: str) -> PinCheck:
    """A ``blob`` pin check vouching for every file below ``root`` (the pipeline mechanics, not the pin, are tested)."""
    listing = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = Path(dirpath, name)
            listing[path.relative_to(root).as_posix()] = git_blob_sha1(path.read_bytes())
    return PinCheck("blob", {"commit": commit, "role": "test"}, listing=listing, repo=repo)


@dataclass
class Imported:
    report: Any
    partial: Path
    rows: list[dict[str, Any]] = field(default_factory=list)
    register: list[dict[str, Any]] = field(default_factory=list)

    def aer(self, ex: str) -> bytes:
        row = next(r for r in self.rows if r["ex"] == ex)
        return (self.partial / row["paths"]["aer"]).read_bytes()

    def headers(self) -> dict[str, dict[str, Any]]:
        out = {}
        for row in self.rows:
            head = json.loads(self.aer(row["ex"]).split(b"\n", 1)[0])
            out[head["artifacts"][0]["origin"]["path"]] = head
        return out


def run_import(tmp: Path, runs: Mapping[str, bytes], tasks: Mapping[str, bytes], *, objects: Iterable[PinnedObject] = (),
               name: str = "corpus", tasks_pin: Mapping[str, Any] | None = None, **kwargs: Any) -> Imported:
    runs_root = write_tree(tmp / f"{name}-runs", runs)
    tasks_root = write_tree(tmp / f"{name}-tasks", tasks)
    kwargs.setdefault("in_process", True)
    kwargs.setdefault("until", "validation")
    contexts = [ContextTree("tasks", LocalTree(tasks_root), vouch(tasks_root, TASKS_REPO, TASKS_COMMIT), pin=tasks_pin)]
    with CorpusWriter(tmp / name) as corpus:
        report = import_source("dtap", LocalTree(runs_root), corpus=corpus, profile_id=PROFILE,
                               pin_check=vouch(runs_root, RUNS_REPO, RUNS_COMMIT), context_trees=contexts,
                               pinned_objects=list(objects), **kwargs)
    partial = tmp / f"{name}.partial"
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    register = [json.loads(line) for line in (partial / "register.jsonl").read_text().splitlines()] \
        if (partial / "register.jsonl").exists() else []
    return Imported(report, partial, rows, register)


def tree_bytes(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = Path(dirpath, name)
            rel = path.relative_to(root).as_posix()
            if rel == ".agentprov.lock" or rel.startswith("raw/tmp/"):
                continue
            out[rel] = path.read_bytes()
    return out


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst)


# ------------------------------------------------------------------------------------------------ derived inputs
def run(steps, *, framework="openaisdk"):
    """A synthetic run (never committed): F01's task and counters around ``steps``."""
    base = json.loads(runs_files()[F["F01"]])
    base["trajectory"] = steps
    for i, s in enumerate(steps):
        s["step_id"] = i
    kinds = Counter(s["role"] for s in steps)
    base["traj_info"].update(step_count=len(steps), actions_count=kinds["agent"], tool_count=kinds["tool"], user_turn=kinds["user"])
    label = F["F01"].replace("openaisdk", framework, 1)
    return label, json.dumps(base).encode()


def call(name, params=None):
    meta = {"tool_name": name, "server": "s"}
    if params is not None:
        meta["tool_params"] = params
    return {"role": "agent", "action": f"{name}()", "metadata": meta}


def result(name, state="ok"):
    return {"role": "tool", "state": state, "metadata": {"tool_name": name, "server": "s"}}


def map_steps(steps, framework="openaisdk"):
    label, data = run(steps, framework=framework)
    return map_label(label, runs={label: data}, tasks={})


def modified(fid, change):
    """A run derived at test time (never committed) from a fixture: ``change`` edits the parsed trajectory."""
    runs = runs_files()
    value = json.loads(runs[F[fid]])
    change(value)
    runs[F[fid]] = json.dumps(value).encode()
    return map_label(F[fid], runs=runs, sem=True, prov=True)


def payload(fid, channel):
    m = map_label(F[fid])
    fixture = next(f for f in m.of("fixture") if f["kind"] == "injection_payload" and f["vector"].startswith(channel))
    return needles(fixture["content"])[0]
