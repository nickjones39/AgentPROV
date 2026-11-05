"""The R07b check as a test helper (CORPUS-CHECK-PROTOCOL R07b; D.5.4 "Citation of D rules", D-24): no record cites a
class-D rule of a governed catalogue for a log whose producing code the rule's ``code`` list does not cite.

``unverified_d_citations`` re-derives, from the mapped records alone, what the mapper must have resolved: the profile's
``verified_code`` entries that apply to the log (selector facets ``variant`` and ``introduced_under`` for the AgentDojo
family, the latter from the primary artefact's git origin and the profile's history table (D-84); ``transcript`` for
transcript/v1; read from the header) against each cited D rule's catalogue ``code`` commits. Rules the family declares
independent of the producing code are exempt.

AU-RP-3: the seal's issues are checked too (subject ``seal/issues/<i>``), for the codes whose rule class is read
downstream: the loss codes (the importer's ``proven_loss_codes`` proves loss only from a class-D rule, H.3.2(2)) and
``unexecuted_tool_call`` (the PROV engine's ``apv:dispatchStatus apv:NotDispatched`` takes its class from the issue's
rule). Any other seal issue cites its rule as given (D.5.4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agentprov.adapters.agentdojo import citation as agentdojo_citation
from agentprov.adapters.agentdojo.history_table import origin_introduced_under
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.code_verification import code_commits, parse_verified_code, rule_class
from agentprov.adapters.profiles import SourceProfile
from agentprov.corpus.facets import LOSS_CODES

#: The seal issue codes whose rule class is evidence downstream (AU-RP-3).
GOVERNED_ISSUE_CODES = frozenset(LOSS_CODES) | {"unexecuted_tool_call"}


def _facets(header: Mapping[str, Any], profile: SourceProfile) -> dict[str, str | None]:
    variant = (header.get("dialect") or {}).get("variant")
    tree = (((header.get("ext") or {}).get("adprov") or {}).get("v1") or {}).get("variant")
    under = None
    if profile.family == "agentdojo":
        artefacts = header.get("artifacts") or [{}]
        under = origin_introduced_under(family_table(profile).history, artefacts[0].get("origin") or {})
    return {"variant": variant, "transcript": tree, "introduced_under": under}


def unverified_d_citations(records: Sequence[Mapping[str, Any]], profile: SourceProfile,
                           issues: Sequence[Mapping[str, Any]] | None = None) -> list[str]:
    """The ``<record id> <rule id>`` pairs that cite a governed D rule at D for unverified code (empty: the check passes).

    ``issues`` are the seal's issues; without them, those of a ``seal`` record among ``records`` are read."""
    if profile.family == "agentdojo":
        table = profile.family_table()
        entries = (table.get("harness") or {}).get("verified_code", ())
        namespaces, independent = agentdojo_citation.NAMESPACES, agentdojo_citation.INDEPENDENT
    elif profile.family == "adprov":
        entries = profile.family_table().get("verified_code", ())
        namespaces, independent = frozenset({"adprov", "agentdojo"}), frozenset()
    else:
        return []
    facets = _facets(records[0], profile)
    verified = {v.commit for v in parse_verified_code(entries, profile.id) if v.matches(facets)}
    if issues is None:
        seals = [r for r in records if r.get("k") == "seal"]
        issues = list(seals[-1].get("issues", ())) if seals else []
    cited = [r for r in records if r.get("k") != "seal"]
    cited += [{"id": f"seal/issues/{n}", "rule": [issue["rule"]]} for n, issue in enumerate(issues)
              if issue.get("code") in GOVERNED_ISSUE_CODES and issue.get("rule")]
    found = []
    for record in cited:
        for ref in record.get("rule", ()):
            rid = str(ref).partition("#")[0]
            namespace = rid.split(".", 1)[0]
            if namespace not in namespaces or rid in independent or rule_class(rid) != "D":
                continue
            if not code_commits(namespace).get(rid, frozenset()) & verified:
                found.append(f"{record.get('id')} {rid}")
    return found
