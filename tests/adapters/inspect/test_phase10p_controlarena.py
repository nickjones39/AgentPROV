"""The phase-10p control-arena profile (D-340..D-348; docs/reports/phase10p/README.md; docs/architecture D.9.9).

No real log is committed (D-346): every real sample holds a generated credential at ``/metadata/API_KEY`` and the smallest
complete real log is over the per-source fixture cap. The tests use synthetic logs built in code (``inspect_support``;
synthetic text, sentinels assembled at run time, never a real value) and, when the staged copy of the pin is present
(``$AGENTPROV_CONTROLARENA_STAGE``, else ``~/.agentprov/staging/10p/hf_idacy_control-arena``), check the small auditor
input against its pin. Nothing here prints source content; assertions compare counts, codes and digests.

Since ingest-formats-3 (D-380..D-387) the importer takes ``.eval`` members of an archive input and, through the profile's
``[[import.nested]]`` entry (D-382), the logs inside the split zips' nested zips.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tomllib
import warnings
import zipfile
from pathlib import Path
from typing import Any

import inspect_support as support
import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.aer.rules import load_catalogue

PROFILE_ID = "controlarena-persistent"
REVISION = "84d39e0a485d7ea6ca10f4ceb2a3fbf88dab0e62"
DATASET = "idacy/control-arena-persistent-state-eval-archive-2026-07-30"
PARTS = ("zip-3-001", "zip-3-002", "zip-3-003", "batch-runs", "auditor")
SPLIT_TOTALS = {"zip-3-001": (8, 2147474457), "zip-3-002": (8, 2147478676), "zip-3-003": (3, 781063343)}
NESTED_ZIPS = ("logs/gradual_f3m1.zip", "logs/2026-01-15_last-two-days.zip", "logs/honest_all.zip", "logs/run_2.zip",
               "logs/positional_f3m1.zip")
STAGE = Path(os.environ.get("AGENTPROV_CONTROLARENA_STAGE",
                            Path.home() / ".agentprov" / "staging" / "10p" / "hf_idacy_control-arena"))


def _toml() -> dict[str, Any]:
    path = support.REPO / "src/agentprov/adapters/inspect/profiles" / f"{PROFILE_ID}.profile.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _policy() -> Any:
    from agentprov.corpus.withhold import policy_of_profile

    data = (support.REPO / "src/agentprov/adapters/inspect/profiles" / f"{PROFILE_ID}.profile.toml").read_bytes()
    return policy_of_profile(data, profile_id=PROFILE_ID, profile_version=4)


def _sentinels() -> dict[str, bytes]:
    """One value of each key shape, assembled at run time (never a real credential, never committed as a literal)."""
    return {"sk-key-shape": b"sk-" + b"T" * 40, "aws-key-shape": b"AKIA" + b"Q" * 16, "github-token-shape": b"ghp_" + b"Z" * 36,
            "google-api-key-shape": b"AIza" + b"Y" * 35, "private-key-header": b"-" * 5 + b"BEGIN RSA PRIVATE KEY" + b"-" * 5,
            "slack-token-shape": b"xoxb-" + b"1" * 12}


def _header(producer: str = "0.3.159", model: str = "none/none") -> dict[str, Any]:
    header = support.synthetic_header(producer)
    header["eval"].update({
        "task": "vibe_coding_persistent_synthetic_attack_policy_attack_0000",
        "task_args": {},
        "model": model,
        "model_roles": {"untrusted": {"model": "ollama/synthetic-agent:1b", "config": {}},
                        "trusted": {"model": "ollama/synthetic-judge:1b", "config": {}}},
        "packages": {"inspect_ai": producer},
    })
    header["plan"]["steps"] = [{"solver": "control_arena/inject_previous_state", "params": {}},
                               {"solver": "control_arena/control_solver", "params": {}},
                               {"solver": "control_arena/extract_state_and_pr_diff", "params": {}}]
    return header


def _sample(sid: str = "PR0_synthetic", key: bytes | None = None) -> dict[str, Any]:
    def tune(_s: support.Sample, sample: dict[str, Any]) -> None:
        sample["metadata"] = {"eval_mode": "attack", "setting_name": "vibe_coding_persistent",
                              "main_task_name": "synthetic-main", "side_task_name": "synthetic-side",
                              **({"API_KEY": key.decode()} if key is not None else {})}

    return support.basic_sample(sid, tune=tune)


def _eval(key: bytes | None = None, producer: str = "0.3.159") -> bytes:
    return support.build_eval(_header(producer), {"PR0_synthetic_epoch_1.json": _sample(key=key)})


# ------------------------------------------------------------------------------------------------ profile and registry
def test_profile_pins_one_hf_pin_per_part_at_the_revision() -> None:
    data, profile = _toml(), load_profile(PROFILE_ID)
    assert profile.version == 4 and profile.family == "inspect" and profile.parts == PARTS
    pins = {p["part"]: p for p in data["source"]["pins"]}
    assert tuple(pins) == PARTS and all(p["primary"] is True and p["role"] == p["part"] for p in pins.values())
    for part, pin in pins.items():
        assert (pin["kind"], pin["dataset"], pin["revision"], pin["gated"]) == ("hf", DATASET, REVISION, False)
        if part in SPLIT_TOTALS:
            n, total = SPLIT_TOTALS[part]
            assert pin["archive"] == "split-zip" and pin["file"] == f"logs_tmp_zips/logs-20260610T154758Z-{part[4:]}.zip"
            assert [p["file"] for p in pin["parts"]] == [f"{pin['file']}.part-{i:04d}" for i in range(n)]
            assert sum(p["bytes"] for p in pin["parts"]) == total and all(len(p["sha256"]) == 64 for p in pin["parts"])
        else:
            assert pin["file"].endswith(".tar.zst") and len(pin["sha256"]) == 64 and pin["size"] > 0
    assert sum(t for _n, t in SPLIT_TOTALS.values()) == 5076016476  # the large-download consent's total (U-07)


def test_split_pins_give_one_recipe_per_part() -> None:
    from agentprov.raw.fetch import part_recipes

    for part, (n, total) in SPLIT_TOTALS.items():
        (pin,) = [p for p in _toml()["source"]["pins"] if p["part"] == part]
        recipes = part_recipes(pin)
        assert len(recipes) == n and sum(r.size or 0 for r in recipes) == total


def test_licence_band_and_family_values() -> None:
    data = _toml()
    assert data["licence"]["spdx"] == "MIT" and data["licence"]["policy"] == "include"
    family = data["family"]["inspect"]
    assert family["benchmark"] == "control-arena" and family["producer_band"] == {"inspect_ai": ["0.3.159"]}
    assert family["log_versions"] == [2] and family["span_roles"] == {"solver": "agent", "scorer": "judge"}
    assert "no_attack" not in family and "submit_tools" not in family  # D-343


def test_family_table_conforms_to_the_closed_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((support.REPO / "src/agentprov/adapters/inspect/family.schema.json").read_bytes())
    jsonschema.validate(_toml()["family"]["inspect"], schema)


def test_quirk_rules_exist() -> None:
    for quirk in _toml()["family"]["inspect"].get("quirk", ()):
        for rule in quirk.get("rules", ()):
            entry = load_catalogue("inspect").get(rule)
            assert entry is not None and entry.citable, (quirk["id"], rule)


def test_registry_parts_are_supported_and_share_one_corpus() -> None:
    registration = get_source(PROFILE_ID)
    assert tuple(c.part for c in registration.capabilities) == PARTS
    for cap in registration.capabilities:
        assert cap.profile == PROFILE_ID and cap.corpus_id == PROFILE_ID and cap.semantics == ()
        assert cap.import_status == "supported" and cap.target_import_status == "supported"
    assert registration.family == "inspect" and registration.licence.spdx == "MIT"


def test_selection_takes_eval_members_only() -> None:
    from agentprov.adapters.runner.importer import _match

    imp = _toml()["import"]

    def selected(label: str) -> bool:
        return any(_match(label, g) for g in imp["include"]) and not any(_match(label, e["glob"]) for e in imp["exclude"])

    assert selected("logs/F2M1_strict_necessity_20260126/deploy-helper/secret-exfil/attack/run_3/2026-01-26T23-03-10+00-00_x.eval")
    assert selected("dbl_honest/batch_20260605_225504/deploy-helper/no_side_task/honest/run_1/2026-06-05T22-55-04+00-00_x.eval")
    assert selected("agent_monitor_logs/agentic_smoke_input/2026-06-05T22-32-50+00-00_x.eval")
    for label in (*NESTED_ZIPS, "logs/x/run_1/stdout.txt", "logs/x/run_1/run_eval.py", "dbl_honest/batch_1/results.json",
                  "agent_monitor_logs/agentic_auditor/smoke_dry/auditor_scores.jsonl", "logs/._x.eval"):
        assert not selected(label), label


def test_the_nested_zips_are_declared_with_bounded_raises() -> None:
    """D-382 (version 2): the five nested zips, as one [[import.nested]] entry within the fixed ceilings."""
    from agentprov.ingest.limits import NESTED_MAX_DEPTH, NESTED_MAX_MEMBER_BYTES
    from agentprov.raw.members import nested_selection

    (entry,) = _toml()["import"]["nested"]
    (child,) = nested_selection(_toml()["import"]["include"], [entry]).children
    assert entry["pattern"] == "logs/*.zip" and entry["max_depth"] == 3 <= NESTED_MAX_DEPTH
    assert 2091106621 <= entry["max_member_bytes"] <= NESTED_MAX_MEMBER_BYTES  # the largest, logs/positional_f3m1.zip
    assert all(child.matches(label) for label in NESTED_ZIPS)  # glob semantics: '*' stays in one segment
    assert not child.matches("logs/x/run_1/x.eval") and not child.matches("logs/a/b.zip")
    assert load_profile(PROFILE_ID).data["import"]["nested"][0]["id"] == entry["id"]  # validated at load


# ------------------------------------------------------------------------------------------------ withholding (D-344)
def test_withhold_policy_rules_and_scope() -> None:
    policy = _policy()
    assert policy is not None
    secret = [r for r in policy.rules if r.id != "users-account-path"]
    assert {r.id for r in secret} == set(_sentinels()) and {(r.scope, r.reason) for r in secret} == {("executions", "secret")}
    (account,) = [r for r in policy.rules if r.id == "users-account-path"]
    assert (account.scope, account.reason) == ("object", "personal_data")  # D-604 (version 4)
    assert {"openai-api-key", "aws-access-token", "private-key"} <= set(policy.scan_rules)


@pytest.mark.parametrize("rule_id", sorted(_sentinels()))
def test_each_rule_hits_its_shape_and_nothing_else(rule_id: str) -> None:
    (rule,) = [r for r in _policy().rules if r.id == rule_id]
    assert rule.hits(b'{"x": "' + _sentinels()[rule_id] + b'"}')
    assert not rule.hits(json.dumps(_sample()).encode())  # a clean synthetic sample
    assert not rule.hits(b"sk-short AKIA123 ghp_x AIza -----BEGIN PUBLIC KEY----- xoxb-")


def test_the_metadata_key_reaches_the_aer_so_every_execution_is_withheld(tmp_path: Path) -> None:
    """D-344's prediction: /metadata/API_KEY is copied into ext.inspect.sample_metadata, so a derived-file hit withholds the
    execution (D-235) whatever else the sample holds."""
    key = _sentinels()["sk-key-shape"]
    imp = support.import_log(_eval(key=key), tmp_path, path="logs/x/run_1/x.eval", profile=load_profile(PROFILE_ID))
    (unit,) = imp.units
    (rule,) = [r for r in _policy().rules if r.id == "sk-key-shape"]
    assert rule.hits(unit.data)
    clean = support.import_log(_eval(), tmp_path / "clean", path="logs/x/run_1/x.eval", profile=load_profile(PROFILE_ID))
    assert not any(r.hits(clean.units[0].data) for r in _policy().rules)


# ------------------------------------------------------------------------------------------------ synthetic logs
def _validate(imp: support.Imported, unit: support.Unit) -> Any:
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import AerValidator

    profile = load_profile(PROFILE_ID)
    validator = AerValidator(store=imp.store, catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(profile.id, profile.version): profile.sha256})
    for line in unit.data.splitlines(keepends=True):
        validator.feed(line)
    return validator.finish()


def test_a_band_log_maps_to_valid_aer(tmp_path: Path) -> None:
    imp = support.import_log(_eval(), tmp_path, path="logs/x/run_1/x.eval", profile=load_profile(PROFILE_ID))
    (unit,) = imp.units
    assert not imp.register and not unit.outcome.degenerate
    report = _validate(imp, unit)
    assert report.ok, [f.code for f in report.findings if f.severity == "error"]
    task = unit.header["task"]
    assert task["benchmark"] == "control-arena" and "attack_id" not in task  # D-343: no attack declared
    actors = {a["id"]: a for a in unit.of_kind("actor")}
    # R-10p-2 (routed): model_roles is not mapped, so the agent's requested model is eval.model as recorded
    assert actors["agent"]["model"]["requested"] == "none/none"
    assert any(a.get("kind") == "judge" for a in actors.values())


def test_a_sandbox_write_without_output_maps_to_valid_aer(tmp_path: Path) -> None:
    """Every real control-arena sample has a sandbox write_file event without an output (trial t1: 5,522 of 5,522
    executions degenerate with map.adapter_defect, aer.write.invalid); fixed by R-10p-7 (no sandbox_output artefact
    without an output string)."""
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        span = next(e["span_id"] for e in s.events if e["event"] == "tool")
        start = s.tick()  # the event's own start first: an argument tick would end it before it starts (AER-V19)
        s.event("sandbox", span, action="write_file", file="/workspace/synthetic.txt", input="synthetic", result=None,
                output=None, timestamp=start, completed=s.tick(0.1))
        sample["events"] = s.events

    data = support.build_eval(_header(), {"PR0_synthetic_epoch_1.json": support.basic_sample("PR0_synthetic", tune=tune)})
    imp = support.import_log(data, tmp_path, path="logs/x/run_1/x.eval", profile=load_profile(PROFILE_ID))
    (unit,) = imp.units
    assert not unit.outcome.degenerate and "adapter_defect" not in unit.issue_codes()


@pytest.mark.parametrize("producer", ["0.3.158", "0.3.247.dev69+g53c1fa98b"])
def test_a_producer_outside_the_band_is_planned(tmp_path: Path, producer: str) -> None:
    imp = support.import_log(_eval(producer=producer), tmp_path, path="logs/x.eval", profile=load_profile(PROFILE_ID))
    assert not imp.units and [r["code"] for r in imp.register] == ["select.dialect_planned"]


def test_an_unfinished_log_without_header_is_planned(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w") as z:
            for name, body in (("_journal/start.json", {"version": 2, "eval": _header()["eval"]}),
                               ("samples/PR0_synthetic_epoch_1.json", _sample())):
                info = zipfile.ZipInfo(name, (2026, 3, 16, 0, 0, 0))
                info.compress_type = zipfile.ZIP_ZSTANDARD
                z.writestr(info, json.dumps(body).encode())
    imp = support.import_log(buf.getvalue(), tmp_path, path="logs/x.eval", profile=load_profile(PROFILE_ID))
    assert not imp.units
    assert [(r["code"], r["detail"]) for r in imp.register] == [("select.dialect_planned", "inspect.eval: no header.json member")]


@pytest.mark.parametrize("data", [b"", b"PK\x03\x04" + b"\0" * 4092], ids=["empty", "truncated"])
def test_an_empty_or_truncated_log_is_not_mapped(tmp_path: Path, data: bytes) -> None:
    """The archive's 358 empty or truncated .eval members: the expand gate rejects the container; nothing is mapped."""
    imp = support.import_log(data, tmp_path, path="logs/x.eval", profile=load_profile(PROFILE_ID))
    assert not imp.units and imp.events and all(str(e.code).startswith("ingest.") for e in imp.events)


# ------------------------------------------------------------------------------------------------ archive inputs
def _split_zip(tmp_path: Path, member: bytes) -> tuple[dict[str, Any], list[tuple[Path, str, int]]]:
    """A synthetic zip holding one .eval member, cut into two byte parts, with its split pin (D-249)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo("logs/x/run_1/2026-01-26T23-03-10+00-00_x.eval", (2026, 1, 26, 0, 0, 0))
        z.writestr(info, member)
    whole = buf.getvalue()
    cut = len(whole) // 2
    parts, pinned = [], []
    for i, chunk in enumerate((whole[:cut], whole[cut:])):
        path = tmp_path / f"s.zip.part-{i:04d}"
        path.write_bytes(chunk)
        sha = hashlib.sha256(chunk).hexdigest()
        parts.append((path, sha, len(chunk)))
        pinned.append({"file": f"logs_tmp_zips/{path.name}", "bytes": len(chunk), "sha256": sha})
    pin = {"role": "zip-3-003", "part": "zip-3-003", "kind": "hf", "dataset": DATASET, "revision": REVISION, "gated": False,
           "file": "logs_tmp_zips/s.zip", "archive": "split-zip", "parts": pinned}
    return pin, parts


def test_a_split_zip_of_eval_logs_imports(tmp_path: Path) -> None:
    # R-10p-6 landed with ingest-formats-3 (D-380): the strict xfail flipped; D-200's refusal is lifted
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    pin, parts = _split_zip(tmp_path, _eval())
    tree = ArchiveTree.split(parts, pin=pin)
    with CorpusWriter(tmp_path / "corpus") as writer:  # dev mode: in-process workers (release mode refuses them)
        report = import_source(PROFILE_ID, tree, corpus=writer, profile_id=PROFILE_ID, part="zip-3-003",
                               snapshot_id="zip-3-003", corpus_id=PROFILE_ID, in_process=True, pin=pin)
    assert report.exit_code == 0 and report.counters["mapped"] == 1


# ------------------------------------------------------------------------------------------------ D-349 redaction
#: A made-up account name (never a real one), assembled at run time.
FAKE_ACCOUNT = "synthetic" + "-account-q7"


def test_versions_2_and_3_are_archived_with_the_bytes_the_scratch_trials_recorded() -> None:
    """D-31: version 4 is current. Versions 2 and 3 load from profiles/archive/ with the digests the scratch corpora built
    under them record: version 2 (phase10p t1 and t2, the precheck l2-* corpora) and version 3 (phase10p t3)."""
    v2, v3, v4 = load_profile(PROFILE_ID, 2), load_profile(PROFILE_ID, 3), load_profile(PROFILE_ID)
    assert (v2.version, v3.version, v4.version) == (2, 3, 4)
    assert v2.sha256.removeprefix("sha256:").startswith("629818bd1af4")
    assert v3.sha256.removeprefix("sha256:").startswith("a73e37822707")
    assert "users-account-path" not in {r["id"] for r in v3.data["withhold"]["rules"]}
    assert len([e for e in v2.data["import"]["exclude"] if e["code"] == "select.redaction_pending"]) == 36
    assert "redact" not in v2.data["family"]["inspect"] and "redact" in v3.data["family"]["inspect"]


def test_the_holds_are_replaced_by_one_harness_text_redaction_rule() -> None:
    """Version 3 (D-349): no select.redaction_pending hold is left; one structural harness_text rule names no account."""
    from agentprov.adapters.inspect.redact import parse_redact_rules

    imp = _toml()["import"]
    assert not [e for e in imp["exclude"] if e["code"] == "select.redaction_pending"]
    (rule,) = parse_redact_rules(_toml()["family"]["inspect"]["redact"], "test")
    assert (rule.id, rule.scope, rule.replacement) == ("workstation_account_path", "harness_text", "/Users/acct-{span12}")
    assert rule.pattern.search(f'File "/Users/{FAKE_ACCOUNT}/proj/x.py", line 1').group(0) == f"/Users/{FAKE_ACCOUNT}"
    assert rule.pattern.search("/home/agent/x") is None and rule.pattern.search("/Users/") is None


def _forms(name: str) -> tuple[bytes, ...]:
    """The account segment as it could appear in a derived file: plain, JSON-escaped, pointer-escaped, URL-encoded."""
    return (name.encode(), json.dumps(name)[1:-1].encode(), f"~1Users~1{name}".encode(), name.replace("-", "%2D").encode())


def test_a_traceback_account_path_is_redacted_everywhere_in_the_aer(tmp_path: Path) -> None:
    """The account segment in a sample error, an error event and the header's eval.metadata reaches the AER in no form;
    the redacted label and the D-182 issue do."""
    error = {"message": "synthetic failure", "traceback": f'File "/Users/{FAKE_ACCOUNT}/proj/x.py", line 1',
             "traceback_ansi": f'File "/Users/{FAKE_ACCOUNT}/proj/x.py", line 1'}

    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        span = next(e["span_id"] for e in s.events if e["event"] == "tool")
        s.event("error", span, error=dict(error))
        sample["events"] = s.events
        sample["error"] = error

    header = _header()
    header["eval"]["metadata"] = {"micro_protocol": {"prompt_file": f"/Users/{FAKE_ACCOUNT}/proj/prompts/p.txt"}}
    data = support.build_eval(header, {"PR0_synthetic_epoch_1.json": support.basic_sample("PR0_synthetic", tune=tune)})
    imp = support.import_log(data, tmp_path, path="logs/x/run_1/x.eval", profile=load_profile(PROFILE_ID))
    (unit,) = imp.units
    assert not unit.outcome.degenerate and "adapter_defect" not in unit.issue_codes()
    assert not any(form in unit.data for form in _forms(FAKE_ACCOUNT))
    assert b"/Users/acct-" in unit.data and "inspect.value_redacted" in unit.issue_codes()
    report = _validate(imp, unit)
    assert report.ok, [f.code for f in report.findings if f.severity == "error"]


RAW_ACCOUNT = "synthetic" + "acct7"  # a segment without '-', the class the raw-object rule targets


def test_the_raw_account_rule_hits_raw_paths_and_not_the_redaction_form() -> None:
    """D-604 (version 4): the object-scope rule hits the account path as raw headers and tracebacks hold it, and never
    the redacted form the derived records carry (so no derived file escalates, D-235)."""
    (rule,) = [r for r in _policy().rules if r.id == "users-account-path"]
    header = {"eval": {"metadata": {"micro_protocol": {"prompt_file": f"/Users/{RAW_ACCOUNT}/proj/prompts/p.txt"}}}}
    assert rule.hits(json.dumps(header).encode())
    assert rule.hits(f'File "/Users/{RAW_ACCOUNT}", line 1'.encode())  # a bare home before a quote
    assert not rule.hits(b'File "/Users/acct-0123456789ab/proj/x.py", line 1')
    assert not rule.hits(b'"/Users/acct-0123456789ab"') and not rule.hits(b"/home/agent/x /Users/")


def test_a_redacted_aer_holds_nothing_the_raw_account_rule_hits(tmp_path: Path) -> None:
    """The account in a traceback and the header's eval.metadata: the raw log is hit, the AER (redacted) is not."""
    error = {"message": "synthetic failure", "traceback": f'File "/Users/{RAW_ACCOUNT}/proj/x.py", line 1'}

    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["error"] = error

    header = _header()
    header["eval"]["metadata"] = {"micro_protocol": {"prompt_file": f"/Users/{RAW_ACCOUNT}/proj/prompts/p.txt"}}
    data = support.build_eval(header, {"PR0_synthetic_epoch_1.json": support.basic_sample("PR0_synthetic", tune=tune)})
    (rule,) = [r for r in _policy().rules if r.id == "users-account-path"]
    assert rule.hits(json.dumps(header).encode())
    imp = support.import_log(data, tmp_path, path="logs/x/run_1/x.eval", profile=load_profile(PROFILE_ID))
    (unit,) = imp.units
    assert b"/Users/acct-" in unit.data and RAW_ACCOUNT.encode() not in unit.data
    assert not rule.hits(unit.data)


def test_the_raw_account_rule_limits_are_recorded_and_the_release_scan_backs_them(tmp_path: Path,
                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """The bounded grammar (D-234) cannot express (a) a name holding '-' or (b) a name at the very end of an object. The
    rule misses both (recorded in the profile and D-349's addendum; the pinned bytes hold neither), and the release scan's
    account-path rule (D-457) reports both at a deposit, while it passes the redaction label the derived records carry."""
    monkeypatch.syspath_prepend(str(support.REPO / "tools"))
    import release_scan

    (rule,) = [r for r in _policy().rules if r.id == "users-account-path"]
    hyphenated, at_end = b'{"p": "/Users/synthetic-acct7/proj"}', b"File /Users/" + RAW_ACCOUNT.encode()
    assert not rule.hits(hyphenated) and not rule.hits(at_end)  # (a) and (b): the recorded limits
    for name, data in (("a.json", hyphenated), ("b.txt", at_end), ("c.json", b'{"p": "/Users/acct-0123456789ab/x"}')):
        (tmp_path / name).write_bytes(data)
    found = {f.path for f in release_scan.path_scan(tmp_path, {}, secrets=False) if f.rule == "account-path"}
    assert found == {"a.json", "b.txt"}  # the deposit backstop sees (a) and (b), and not the D-604 label


def test_the_trial_tool_has_no_hold_mechanism_left() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("phase10p_trial", support.REPO / "tools/inspect/phase10p_trial.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not hasattr(module, "_hold_entries")


# ------------------------------------------------------------------------------------------------ staged copy (optional)
@pytest.mark.skipif(not (STAGE / "agentic_auditor_logs-20260730.tar.zst").is_file(), reason="the staged pin is not present")
def test_the_staged_auditor_input_matches_its_pin() -> None:
    from agentprov.raw.fetch import Recipe, verify_download

    (pin,) = [p for p in _toml()["source"]["pins"] if p["part"] == "auditor"]
    path = STAGE / pin["file"]
    with path.open("rb") as handle:
        sha256, _md5, size = verify_download(handle, path.name, Recipe.from_pin(pin))
    assert (sha256, size) == (pin["sha256"], pin["size"])
