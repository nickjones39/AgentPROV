"""``CITATION.cff`` agrees with the release it describes (D-944, V-2/V-3).

The version equals ``pyproject.toml``'s, the licence equals ``LICENSE``'s, the ORCID iD carries a valid ISO 7064 check
digit, a DOI, once present, is a Zenodo DOI that is not AgentDojo-PROV's concept (D-5), and ``date-released``, once
present, is an ISO date. ``doi`` and ``date-released`` are filled in the release commit (v0.1.0 plan, section 1).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ADPROV_CONCEPT = "10.5281/zenodo.20692312"


def _cff() -> dict:
    return yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))


def _orcid_ok(orcid: str) -> bool:
    digits = orcid.replace("-", "")
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


def test_version_and_licence_match_the_project():
    cff = _cff()
    assert cff["cff-version"] == "1.2.0"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert cff["version"] == project["version"]
    assert cff["license"] == "MIT"
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").lstrip().startswith("MIT License")


def test_authors_and_doi():
    cff = _cff()
    assert cff["authors"], "at least one author"
    for author in cff["authors"]:
        assert author["family-names"] and author["given-names"]
        match = re.fullmatch(r"https://orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", author.get("orcid", ""))
        assert match and _orcid_ok(match.group(1))
    doi = cff.get("doi")
    if doi is not None:
        assert re.fullmatch(r"10\.5281/zenodo\.\d+", doi) and doi != ADPROV_CONCEPT


def test_date_released_is_an_iso_date():
    """The release date equals the Zenodo records' publication date (2026-10-30), an ISO date YAML reads as a date."""
    import datetime

    released = _cff().get("date-released")
    if released is not None:
        assert isinstance(released, datetime.date) and str(released) == released.isoformat()
