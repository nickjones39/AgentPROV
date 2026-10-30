"""The `defence` rule catalogue cites only what the repository holds (review R3-6; D-670, D-677).

Every DECISIONS id it names (singly or as a range `D-670..D-679`) is a decision in DECISIONS.md or its parts, every repository path
exists, every `§` section of a cited document is a heading of it, and every `tests` entry names an existing test
function. A rule id it gives in prose (`defence.<name>@<n>`) is a rule of the catalogue.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "src/agentprov/adapters/agentdojo/rules/defence.rules.toml"
DECISIONS = REPO / "docs/architecture/DECISIONS.md"
DECISION_PARTS = REPO / "docs/architecture/decision-log"  # the entries, once DECISIONS.md is an index (D-1003)
_PATH = re.compile(r"\b((?:docs|src|tests|backends|tools)/[A-Za-z0-9_./-]+[A-Za-z0-9_])")
_DID = re.compile(r"\bD-(\d{3})(?:\s*(?:\.\.|–)\s*D-(\d{3}))?")
_SECTION = re.compile(r"§\s*(\d+(?:\.\d+)*)")


def _texts() -> list[str]:
    raw = CATALOGUE.read_text(encoding="utf-8")
    comments = [line.lstrip("# ") for line in raw.splitlines() if line.startswith("#")]
    data = tomllib.loads(raw)
    evidence = [e for rule in data["rule"] for e in rule.get("evidence", [])]
    return comments + evidence


def test_every_cited_decision_exists():
    decisions = "".join(p.read_text(encoding="utf-8") for p in [DECISIONS, *sorted(DECISION_PARTS.glob("*.md"))])
    cited: set[int] = set()
    for text in _texts():
        for first, last in _DID.findall(text):
            cited.update(range(int(first), int(last or first) + 1))
    assert cited, "the catalogue cites no decision"
    missing = [n for n in sorted(cited) if not re.search(rf"\*\*D-{n}\b|\bD-{n}[,:]? ", decisions)]
    assert missing == [], missing


def test_every_cited_path_and_section_exists():
    problems = []
    for text in _texts():
        for path in _PATH.findall(text):
            target = REPO / path
            if not target.exists():
                problems.append(f"missing {path}")
                continue
            for section in _SECTION.findall(text.split(path, 1)[1]):
                heading = re.compile(rf"^#+\s+{re.escape(section)}\b", re.M)
                if not heading.search(target.read_text(encoding="utf-8")):
                    problems.append(f"{path} has no section {section}")
    assert problems == []
    assert any(_SECTION.search(t) for t in _texts())  # the section check has something to check


def test_every_tests_entry_names_an_existing_test():
    data = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    problems = []
    for rule in data["rule"]:
        for node in rule.get("tests", []):
            path, _, name = node.partition("::")
            target = REPO / path
            if not target.is_file() or (name and not re.search(rf"^def {re.escape(name)}\(", target.read_text(), re.M)):
                problems.append(f"{rule['id']}: {node}")
    assert problems == []


def test_the_design_note_names_only_catalogue_rules():
    data = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    rules = {f"{r['id']}@{r['version']}" for r in data["rule"]}
    note = (REPO / "docs/reports/defence-backends/design.md").read_text(encoding="utf-8")
    named = set(re.findall(r"`(defence\.[a-z_]+@\d+)`", note))
    assert named - rules <= {"defence.detached_input@1"}  # lands post-round with the core part (regen-batch item 167)
    assert not re.search(r"agentdojo\.capture_defence_denial@", note)  # the pre-build name (R3-6)
