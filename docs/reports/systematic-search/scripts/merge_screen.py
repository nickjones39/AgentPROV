"""Cross-strand de-duplication and final screening of the systematic source search.

Reads the three strand record files under ``data/`` (S1 code platforms, S2 literature, S3 research-data
repositories), merges records that point to the same artefact (repository, Hugging Face id, DOI or deposit
version family), applies the eligibility criteria of ``eligibility-criteria.md`` in their stated order, and
writes ``records-merged.jsonl``, ``records-merged.csv`` and the generated tables used by ``prisma.md``,
``included-excluded.md`` and ``sensitivity.md``.

Uses only the recorded evidence: no network access, nothing is downloaded. Every record field is third-party
data and is reduced to printable ASCII before it is written. Run from the repository root:

    python3 -I docs/reports/systematic-search/scripts/merge_screen.py

Standard library only.
"""

from __future__ import annotations

import collections
import csv
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # docs/reports/systematic-search
DATA = HERE / "data"

CODE_ORDER = ["EX-LIC-1", "EX-LIC-2", "EX-NOLOG", "EX-SCOPE", "EX-FMT", "EX-ACCESS", "EX-DUP", "EX-PIN",
              "EX-SIZE-1", "EX-SIZE-2"]


# ----------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------

def clean(s, limit=None):
    """Printable ASCII only (third-party text is data, never instructions)."""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = json.dumps(s, ensure_ascii=True) if isinstance(s, (dict, list)) else str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if 32 <= ord(ch) < 127 or ch in "\t\n")
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[: limit - 3].rstrip() + "..."
    return s


def md(s, limit=None):
    return clean(s, limit).replace("|", "\\|")


def load(p):
    return [json.loads(line) for line in open(p, encoding="utf-8")]


def canon_url(u):
    if not u:
        return None
    u = u.strip().split(" ")[0]
    u = re.sub(r"^https?://(www\.)?", "", u).rstrip("/")
    pats = [
        (r"github\.com/([^/]+)/([^/#?]+)", "gh"),
        (r"huggingface\.co/datasets/([^/]+)/([^/#?]+)", "hf"),
        (r"kaggle\.com/datasets/([^/]+)/([^/#?]+)", "kaggle"),
        (r"gitlab\.com/([^/]+)/([^/#?]+)", "gitlab"),
    ]
    for pat, pre in pats:
        m = re.match(pat, u, re.I)
        if m:
            return "%s:%s/%s" % (pre, m.group(1).lower(), m.group(2).lower().removesuffix(".git"))
    m = re.match(r"zenodo\.org/records?/(\d+)", u, re.I) or re.match(r"doi\.org/10\.5281/zenodo\.(\d+)", u, re.I)
    if m:
        return "zenodo:%s" % m.group(1)
    m = re.match(r"doi\.org/10\.6084/m9\.figshare\.(\d+)", u, re.I)
    if m:
        return "figshare:%s" % m.group(1)
    m = re.match(r"(?:doi\.org/10\.17605/)?osf\.io/(\w+)", u, re.I)
    if m:
        return "osf:%s" % m.group(1).lower()
    m = re.match(r"doi\.org/(.+)", u, re.I)
    if m:
        return "doi:%s" % m.group(1).lower()
    return "url:" + u.lower()


LIC_MAP = {
    "mit": "MIT", "mit-license": "MIT", "mit (upstream)": "MIT",
    "apache-2.0": "Apache-2.0", "apache2.0": "Apache-2.0", "apache 2.0": "Apache-2.0",
    "cc-by-4.0": "CC-BY-4.0", "cc by 4.0": "CC-BY-4.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0", "cc-by-nc-sa-4.0": "CC-BY-NC-SA-4.0", "cc-by-sa-4.0": "CC-BY-SA-4.0",
    "cc-by-nc-nd-4.0": "CC-BY-NC-ND-4.0", "cc0": "CC0-1.0", "cc0-1.0": "CC0-1.0",
    "gpl-3.0": "GPL-3.0", "agpl-3.0": "AGPL-3.0", "apgl-v3": "AGPL-3.0",
    "nist-software": "NIST-Software", "odc-by-1.0": "ODC-By-1.0", "bsd-3-clause": "BSD-3-Clause",
    "cdla-permissive-2.0": "CDLA-Permissive-2.0",
    "none": "none", "unknown": "unknown", "other": "unknown", "custom-restrictive": "custom-restrictive",
}


def norm_lic(x):
    if x is None or x in ("", "None"):
        return None
    k = x.strip().lower()
    if k.startswith("copyright holder"):
        return "none"
    return LIC_MAP.get(k, x.strip())


def lic_class(lic):
    if lic in ("MIT", "Apache-2.0", "CC-BY-4.0", "CC0-1.0", "ODC-By-1.0", "BSD-3-Clause", "CDLA-Permissive-2.0"):
        return "MIT/Apache/CC-BY"
    if lic == "GPL-3.0":
        return "GPL-3.0"
    if lic == "AGPL-3.0":
        return "AGPL-3.0"
    if lic in ("CC-BY-NC-4.0",):
        return "-nc"
    if lic == "CC-BY-NC-SA-4.0":
        return "-nc (share-alike)"
    if lic == "CC-BY-SA-4.0":
        return "CC-BY-SA-4.0 (share-alike, own corpus)"
    return "unresolved"


# ----------------------------------------------------------------------------------------------------------
# grouping: key aliases (same artefact found under different identifiers)
# ----------------------------------------------------------------------------------------------------------

KEY_ALIAS = {
    # AgentDojo upstream: GitHub, GitHub-Zenodo software deposits, Software Heritage origin
    "zenodo:17458493": "gh:ethz-spylab/agentdojo",
    "zenodo:12528189": "gh:ethz-spylab/agentdojo",
    "url:archive.softwareheritage.org/browse/origin/?origin_url=https://pkg.go.dev/github.com/ethz-spylab/agentdojo":
        "gh:ethz-spylab/agentdojo",
    # AgentDojo-PROV: framework repository and its Zenodo corpus deposit
    "zenodo:23276620": "gh:nickjones39/agentdojo-prov",
    # Agent Security Tools Survey: repository and Zenodo versions v1.0.0 / v1.0.1
    "zenodo:22140262": "gh:forever-codingnoob/agent-security-tools-survey",
    "zenodo:22135957": "gh:forever-codingnoob/agent-security-tools-survey",
    # AgentDyn: paper URL redirects to the SaFo-Lab repository
    "gh:leolee99/agentdyn": "gh:safo-lab/agentdyn",
    # CIAware-Bench: GitHub records and the gated Hugging Face data
    "hf:schaeff/ciaware-bench-data": "gh:joachimschaeffer/ciaware-bench",
    # NIST AgentDojo-Inspect: code repository and NIST data record
    "doi:10.18434/mds2-3690": "gh:usnistgov/agentdojo-inspect",
    # OpenAgentSafety: repository (trajectories) and Hugging Face task definitions
    "hf:sani903/openagentsafety": "gh:sani903/openagentsafety",
    # Zenodo version families (concept record kept as the source identity)
    "zenodo:22973266": "zenodo:22973265", "zenodo:22996368": "zenodo:22973265", "zenodo:23138310": "zenodo:22973265",
    "zenodo:22011266": "zenodo:20731176", "zenodo:21418519": "zenodo:20731176", "zenodo:20731177": "zenodo:20731176",
    "zenodo:21895483": "zenodo:21895484",
    "zenodo:20768125": "zenodo:20760029", "zenodo:20767959": "zenodo:20760029", "zenodo:21272068": "zenodo:20760029",
    "zenodo:23118274": "zenodo:23114933",
    "zenodo:19875456": "zenodo:19875693",
    "zenodo:23084446": "zenodo:23084447",
    "zenodo:22277938": "zenodo:23101926",
    "paper:doi:10.5281/zenodo.22277938": "zenodo:23101926",
    "paper:doi:10.5281/zenodo.21944597": "zenodo:21944598",
    # same artefact in two repositories
    "figshare:32835578": "zenodo:21063932",
    "doi:10.21227/hr5g-4c33": "zenodo:20198985",
    "doi:10.57967/hf/10738": "hf:masahiroid/injecagent-ja",
    "paper:hf-dataset:changdae/agentdojo-trajectories-qwen35-gemma4": "hf:changdae/agentdojo-trajectories-qwen35-gemma4",
}

S3_NON_RECORDS = {"PWC", "MENDELEY", "DRYAD"}  # search-service notes, not records


# ----------------------------------------------------------------------------------------------------------
# manual screening decisions (first applicable code in criterion order), from the recorded evidence only
# ----------------------------------------------------------------------------------------------------------

O = {}


def dec(key, d, code=None, **kw):
    assert key not in O, key
    O[key] = dict(d=d, code=code, **kw)


INC, EXC, PEND = "included", "excluded", "pending-verification"

# --- sources AgentPROV already converts (justification.md) and the verified candidates --------------------
dec("gh:ethz-spylab/agentdojo", INC, known="current", adapter="agentdojo (profile agentdojo-upstream)",
    runs=40738, basis="exact: 36,679 logs at head 089ed468 + 4,059 2024-06 (c274885) executions not at head "
    "(I_matrix I.1.1)", fmt="AgentDojo TraceLogger JSON (v0.k11, v1.k14)",
    lic="MIT", licsrc="LICENSE (repository); Zenodo deposits mit-license; 'MIT by repository; data licence not "
    "separately stated'", models="29 pipeline directories (GPT-3.5/4/4o/4o-mini, o1/o3, Claude 3/3.5/3.7, Gemini "
    "1.5/2.0/2.5, Llama 3/3.3, Command-R+, Meta-SecAlign, local models)", scope_in=True, logs="yes")
dec("gh:nickjones39/agentdojo-prov", INC, known="current", adapter="adprov (transcript/v1)", runs=17664,
    basis="exact: 17,664 transcript/v1 files of the author's own live capture (I_matrix card 2)",
    fmt="AgentDojo-PROV transcript/v1 JSON", lic="CC-BY-4.0",
    licsrc="data CC-BY-4.0 (Zenodo, manifests); code MIT (LICENSE text; GitHub NOASSERTION)",
    conflict="Licence by strand: S1 recorded the code licence (MIT), S2 and S3 the data licence (CC-BY-4.0). Not a "
    "conflict: the data licence governs the corpus.",
    models="gemini-2.5-flash, llama-3.3-70b-instruct, deepseek-chat, gpt-5-nano, qwen-2.5-72b-instruct, glm-4.6",
    scope_in=True, logs="yes",
    notes="Own baseline. The derived PROV graphs and the converted legacy tree are not raw evidence; only the 17,664 "
    "release transcripts count.")
dec("gh:xhowenma/rope", INC, known="current", adapter="agentdojo (profile rope)", runs=10791,
    basis="exact: 10,791 logs at 64495e16, incl. 2,847 AutoDojo-attack runs (I_matrix card 7)",
    fmt="AgentDojo TraceLogger JSON v1.k14", lic="MIT", licsrc="LICENSE (repository); no separate data licence",
    models="gpt-4o-mini, gpt-4o, gemini-2.5-flash, qwen3-235b", scope_in=True, logs="yes")
dec("gh:safo-lab/agentdyn", INC, known="current", adapter="agentdojo (profile agentdyn)", runs=47723,
    basis="exact: 47,723 logs at 5353cf76 (variant A 38,281 supported; B 5,184 and C 4,258 partial) (I_matrix card 5)",
    fmt="AgentDojo TraceLogger JSON (v1.k14, v0.k11, drift.k18.messages)", lic="MIT",
    licsrc="LICENSE (repository; only AgentDojo authors' copyright line); 'MIT as declared by the repository; not "
    "legally settled'", models="8 base models x 9 configurations, CaMeL, Meta-SecAlign-70B/8B, Progent",
    scope_in=True, logs="yes")
dec("gh:jwilliamsc/mandate-agentdojo-eval", INC, known="current", adapter="agentdojo (profile mandate)", runs=396,
    basis="exact: 396 logs at fa62a977 (I_matrix card 12)", fmt="AgentDojo TraceLogger JSON v1.k14", lic="MIT",
    licsrc="LICENSE (repository, (c) 2026 Mandate Labs; publisher unverified); no separate data licence",
    models="gpt-4o-2024-05-13", scope_in=True, logs="yes")
dec("gh:forever-codingnoob/agent-security-tools-survey", INC, known="current",
    adapter="agentdojo (AgentDojo runs) + inspect (AgentHarm)", runs=4299,
    basis="exact: 3,243 AgentDojo runs + 1,056 AgentHarm Inspect samples (6 logs); 1,200 ASB CSV rows not counted "
    "(I_matrix card 11)", fmt="AgentDojo TraceLogger JSON v1.k14; Inspect .eval; ASB CSV",
    lic="CC-BY-4.0", licsrc="repository and Zenodo record cc-by-4.0; AgentHarm data 'MIT License with an additional "
    "clause' (use only to improve AI safety and security)",
    cls="MIT/Apache/CC-BY (AgentDojo runs); restricted-use corpus for AgentHarm (MIT + use clause)",
    models="three Ollama models (path-derived) for AgentDojo; ollama/<tag> for AgentHarm", scope_in=True, logs="yes",
    notes="The Zenodo zip also re-packages AgentDojo's 36,679 upstream runs (mirror, not selected).")
dec("gh:safo-lab/drift", INC, known="candidate", adapter="agentdojo (dialect drift.k18)", runs=1569,
    basis="exact: 1,569 runs at head 6fd3df4 (I_matrix card 8)", fmt="DRIFT conversations JSON (drift.k18)",
    lic="MIT", licsrc="LICENSE added in 6fd3df4 ((c) 2026 Hao Li); history blobs predate any licence",
    models="gpt-4o-mini-2024-07-18", scope_in=True, logs="yes",
    notes="Known source, registry status partial (stretch target); not yet a converted corpus.")
dec("hf:ai-secure/dtap-bench-agent-trajectories", INC, known="candidate", adapter="dtap (new family, phase 10b, D-26)",
    runs=67808, basis="census: 67,808 trajectory files @ 836caf2f (67,806 parseable; 20 synthetic, 8 '(1)' copies, "
    "99 re-runs; dtap-bench.md section 3)", fmt="DTap per-run trajectory JSON + judge_result.json",
    lic="Apache-2.0", licsrc="dataset card (both repositories); no LICENSE/NOTICE file",
    models="gpt-5.1, gpt-5.2, gpt-5.4, gpt-oss-120b, claude-opus-4-6, claude-sonnet-4-5, gemini-3-pro-preview "
    "(4 agent frameworks)", scope_in=True, logs="yes",
    notes="Included as a candidate (user decision 2026-10-11). Limitation: tool-description injections often not "
    "observable in the logs (dtap-bench.md section 6).")

# --- known sources that are not converted --------------------------------------------------------------------
dec("gh:joachimschaeffer/ciaware-bench", EXC, "EX-LIC-1", lic="none", known="known", adapter="inspect",
    files=9516, basis="9,516 files in the gated HF data: 2,538 Inspect .eval archives (samples not counted) (S3)",
    fmt="Inspect .eval (gated HF) + GitHub compact records", logs="yes", scope_in=True,
    licsrc="no licence on the GitHub records or the gated HF data (S1 audit); the CIABench precursor carries MIT in "
    "card metadata only (U-04, not legally settled)", notes="Registry policy reference (I_matrix card 14).")
dec("gh:usnistgov/agentdojo-inspect", EXC, "EX-DUP", dup="gh:ethz-spylab/agentdojo", known="known", runs=0,
    basis="21,999 inherited logs, byte-identical to AgentDojo v0.1.25 runs/ (I_matrix card 4); 0 own executions",
    fmt="AgentDojo TraceLogger JSON (inherited)", lic="NIST-Software", logs="yes", scope_in=True,
    licsrc="NIST software notice (LICENSE.md) + AgentDojo MIT (THIRD_PARTY_LICENSES.md)")
dec("gh:xhowenma/autodojo", EXC, "EX-NOLOG", known="known",
    notes="runs/ and logs/ gitignored; its only released executions (2,847) are inside ROPE and counted there.")
dec("gh:asago-ai/midojo", EXC, "EX-NOLOG", known="known", notes="92 outcome-only rows on an unmerged branch; no "
    "trajectories (I_matrix card 9).")
dec("gh:compsec-snu/adi", EXC, "EX-NOLOG", known="known", notes="Definitions only; outputs gitignored.")
dec("gh:amazon-science/multiturnagentattack", EXC, "EX-NOLOG", known="known",
    notes="483 scenario records, not agent executions (I_matrix card 13); CC-BY-NC-4.0.")
dec("hf:ai-safety-institute/agentharm", EXC, "EX-NOLOG", known="known", lic="MIT",
    licsrc="MIT with an AI-safety use clause (HF tag 'other'); per LIC rule 3 the clause permits redistribution",
    conflict="Licence: S1 classified the HF 'other' tag as custom-restrictive; the criteria (LIC 3) treat AgentHarm's "
    "MIT + use clause as permitting redistribution. Either way the record holds definitions only (8 files).",
    notes="Benchmark definitions only. AgentHarm executions are counted in the survey source.")

# --- strand conflicts recorded, not guessed ------------------------------------------------------------------
dec("zenodo:21631031", PEND, cat="strand conflict", adapter="unknown (TELOS JSONL)", runs=139,
    basis="139 evaluations (record title); one 147 KB JSONL file", fmt="TELOS per-evaluation JSONL",
    conflict="S3: derived detector-engine evidence, prompt text redacted to SHA-256, not agent message logs "
    "(EX-NOLOG). S2: 139 AgentDojo evaluations released as JSONL (include). S1: zip not inspected (pending). "
    "If the records are agent logs they need a new adapter and 139 < 1,000 (EX-SIZE-2); if not, EX-NOLOG.",
    scope_in=True, logs="disputed")
dec("hf:ai45research/atbench", PEND, cat="strand conflict", adapter="new", runs=500,
    basis="500 annotated trajectories (S1 listing; ATBench500/test.json)", fmt="annotated trajectory JSON",
    conflict="S2 includes it (Apache-2.0, released trajectories); S1 could not tell generated from executed "
    "trajectories. If executed, a new adapter with 500 < 1,000 runs (EX-SIZE-2); if generated, EX-NOLOG.",
    scope_in=True, logs="disputed")
dec("gh:asif-0209/agentdrift", PEND, cat="strand conflict", adapter="new", runs=12536,
    basis="12,536 trajectories (paper figure via S1; S2 listing: 12,540 files in data/train, test, val)",
    fmt="JSON/JSONL step-labelled trajectories",
    conflict="S1: synthetic, LLM-generated trajectories, not executions of a harness (from a web-search snippet of "
    "the paper; full text not read) -> EX-NOLOG. S2: included as released injection-hijacked trajectories "
    "(CC-BY-4.0; links the Nemotron-RL IPI tasks, which S3 found to be synthetic RL tasks). If confirmed generated, "
    "the code is EX-NOLOG (fails IN-1: not executions of an agent).", scope_in=True, logs="disputed")
# --- AgentDojo-format candidates, verified by phase 10c (2026-10-11) ----------------------------------------
# Census of the bytes at each pin (SHA-256 against every converted source, DRIFT and agentdojo-inspect; strict JSON;
# the adapter's D.6.2 classifier): docs/reports/systematic-search/candidates/agentdojo-format-shortlist.md and
# AgentPROV/investigation/{sources,verify}/agentdojo-format-candidates.md. Runs are byte-distinct new runs; "readable"
# is what today's code can read and map (the rest waits for D-90, D-91 or D-96). Decisions D-90..D-96.
OWN_GPL, OWN_AGPL = "GPL-3.0 (own corpus, D-94)", "AGPL-3.0 (own corpus, D-94)"
V1, V0 = "AgentDojo TraceLogger JSON v1.k14", "AgentDojo TraceLogger JSON v0.k11"
P10C_VERIFIED = [
    # key, runs, readable, pin, licence, licence source, format, models, note, corpus class
    ("gh:wakeful-cloud/llm-lock", 53307, 53307, "7bb9915b", "GPL-3.0", "LICENSE at pin (GPL-3.0 title line)", V1,
     "model not recorded (pipeline 'local'); 9 detector-defence arms",
     "Model sealed not_recorded (D-92); detector-output extra keys.", OWN_GPL),
    ("zenodo:22973265", 18739, 2813, "v2.1.0 23138310 (contains v1.0 22973266)", "CC-BY-4.0",
     "record cc-by-4.0; LICENSE-DATA CC BY 4.0, LICENSE-CODE MIT", V1,
     "gpt-6-luna, gpt-6-sol, claude-haiku-4-5, gpt-4o-mini, gpt-3.5-turbo (caps A3/A4, no-egress, auto-confirm)",
     "15,926 runs only in nested tar.gz: import waits for D-90. The 36,679 upstream rows are CSV, not trajectories.",
     None),
    ("gh:ceferisbarov/agentdojo", 18442, 18442, "2273e1cd", "MIT", "LICENSE (repository)", V1,
     "gpt-4o, gemini-2.5-pro, Qwen2.5, command-r-plus (61 optimised-injection arms)",
     "36,679 byte copies of upstream runs not counted.", None),
    ("figshare:32657856", 16221, 11406, "v1", "MIT", "record MIT; third_party_licenses/ (AgentDojo, CaMeL, DRIFT)",
     "AgentDojo TraceLogger JSON v1.k14 (13,374) + drift.k18.conversations (2,847)",
     "gpt-4o-mini, gpt-oss-20b, qwen3.6:27b (CaMeL, DCA, DRIFT)",
     "1,968 v1.k14 runs wait for D-91 (':' in member names); 2,847 DRIFT runs wait for D-96.", None),
    ("gh:linyxus/agentdojo", 9068, 9068, "lacuna-exp 698d7ff2 (contains tacit-exp)", "MIT", "LICENSE (repository)", V1,
     "o4-mini-high, gemini-2.5-pro, gpt-5.4-nano, claude-sonnet-4, deepseek-v4-flash (Tacit defence)",
     "Default branch equals upstream; tacit-exp (7,367) is a subset of lacuna-exp.", None),
    ("gh:dafarusd/gate", 3870, 3870, "925b9926", "AGPL-3.0", "LICENSE, NOTICE, README: AGPL-3.0-only", V1,
     "local Qwen3 models with the gate on and off; hold-out attacks", "", OWN_AGPL),
    ("gh:mohameduk/agentdojo", 3630, 3630, "ubag-gateway-defense 3f9d69a1", "MIT", "LICENSE (repository)", V1,
     "gemini-2.5-flash, gpt-4o-mini (UBAG defence)",
     "benchmark_version null in attacked runs; 763 content repeats; upstream copies not counted.", None),
    ("zenodo:20731176", 3211, 0, "v4.0.0 22011266", "CC-BY-4.0", "record cc-by-4.0", V1,
     "gpt-5.4-mini, gpt-5.4, claude-sonnet-4-6 (5 AgentDojo defences, banking)",
     "All runs in nested tar.gz: import waits for D-90 (EX-FMT if declined).", None),
    ("gh:luiacuaniello/geryon", 3179, 3179, "905aae02", "Apache-2.0", "LICENSE and README", V0,
     "gpt-oss-120b, qwen3-235b (Bedrock)", "No evaluation timestamps; Progent AgentDojo at HEAD (unpinned).", None),
    ("gh:ishani018/kavach", 2625, 2625, "main 53df9545 + nav-fixer2 f2dd7efa + rearch-forcedformat-fix 6b31a554",
     "MIT", "LICENSE and README", V1, "local Gemma, Qwen2.5-7B (Kavach defence)",
     "Three branch pins (D-95); about 957 distinct trajectories by content.", None),
    ("gh:csslab/tacit", 2076, 2076, "995692d3", "Apache-2.0", "LICENSE", V1, "llama3.1-8b-instruct, qwen3-4b-instruct",
     "No byte overlap with Linyxus tacit-exp.", None),
    ("gh:deconvolute-labs/interbolt-agentdojo", 2016, 2016, "43e2b5fa", "Apache-2.0", "LICENSE and README", V1,
     "gpt-4o-mini (Interbolt defence, three policies)", "", None),
    ("gh:xwsdid/melon", 1911, 1911, "71d99dff", "MIT", "LICENSE (repository)", V1, "gpt-4o, gpt-4o-mini (MELON variants)",
     "36,679 byte copies of upstream runs not counted.", None),
    ("gh:zanethomas1430-code/glitch", 1844, 1844, "713bb296", "MIT", "LICENSE", V1,
     "gpt-4o-2024-05-13, claude-haiku-4-5 (Glitch defence)", "", None),
    ("gh:athassin/craibench", 1163, 1163, "e41eac1e", "MIT", "LICENSE (repository)", V0,
     "gpt-4o, gpt-4o-mini (spotlighting); new suites crypto_trading and chain",
     "688 memory-injection runs are named only by file suffix.", None),
    ("gh:hilarytorn/in-context-trajectory-poisoning", 990, 990, "d71ab8bc", "MIT", "LICENSE", V1,
     "gpt-4o-2024-05-13 (TAP and seeded-pair trajectory poisoning)", "", None),
    ("gh:menelaus29/ipi-multidomain-agent-study", 965, 965, "main ec9c9287 + 7c354f9a + c560139f", "MIT", "LICENSE", V1,
     "gemma-4-26b, gemini-3.5/3.6 flash (197-payload corpus)", "Three branch pins (D-95).", None),
    ("gh:kongminos/jspace-agentdojo-950", 950, 950, "f341af69", "MIT", "LICENSE and README", V1,
     "DeepSeek V4-Flash (README; logs say 'local')", "Identity row from the README (D-92).", None),
    ("gh:vinhqdang/sentry-anytime-valid-e-process-monitoring-of-llm-agent-action-streams", 674, 674, "938e8be7",
     "AGPL-3.0", "LICENSE and README", V1, "deepseek-v4-flash, gpt-4o-mini, OpenRouter free router",
     "72 router runs: model not_recorded (D-92).", OWN_AGPL),
    ("gh:shreeyavarma/llm_safety", 672, 672, "78d22e4a", "MIT", "LICENSE (repository)", V1,
     "gpt-4o-2024-05-13, local Qwen", "24,914 byte copies of upstream runs not counted.", None),
    ("gh:cgboom-git/drift-1", 626, 0, "0e28729b", "MIT", "README badge only; no LICENSE file (D-93)",
     "DRIFT conversations JSON (drift.k18)", "gpt-4o-mini (DRIFT, PACT-DRIFT)",
     "Waits for D-96; its 1,569 copies of DRIFT runs (EX-DUP) are not counted.", None),
    ("gh:sricursion/bookkeeper", 570, 570, "0fe09bb6", "GPL-3.0", "LICENSE GPL-3.0; README: v3.0 or later", V1,
     "glm-5.3-flash, gpt-oss-120b (MUNIM defence)", "", OWN_GPL),
    ("gh:yockcheng/prompt-injection-harness", 280, 280, "5f9137ff", "Apache-2.0", "LICENSE text Apache-2.0", V1,
     "claude-haiku-4-5, claude-sonnet-4-5, claude-3-7-sonnet, claude-3-haiku", "", None),
    ("gh:sports-vision-inc/aiauthz", 174, 174, "6eaac86a", "AGPL-3.0", "LICENSE, NOTICE, README", V1,
     "claude-fable-5, gemini-3-flash-preview (OpenRouter; logs carry registry tags)", "", OWN_AGPL),
]
for key, runs, readable, pin, lic, licsrc, fmt, models, note, cls in P10C_VERIFIED:
    dec(key, INC, known="candidate", adapter="agentdojo (profile to write; phase 10c)", runs=runs,
        basis="census (phase 10c): %s new runs @ %s; %s readable today" % (format(runs, ","), pin, format(readable, ",")),
        fmt=fmt, lic=lic, licsrc=licsrc, models=models, scope_in=True, logs="yes",
        notes=("Verified in phase 10c. " + note) if note else "Verified in phase 10c.", **({"cls": cls} if cls else {}))
# Withdrawn after retrieval (D-901, user decision 2026-10-28): verified and staged in phase 10c (2026-10-15) while
# public; on 2026-10-28 the pinned commit could no longer be fetched (GitHub asks for credentials). Excluded out of
# respect for the author's apparent withdrawal, although the retrieved copy still exists; not for its licence or outcomes.
dec("gh:omseeth/environmentoptim", EXC, "EX-ACCESS", known="candidate", adapter="agentdojo (profile environmentoptim)",
    runs=6740, basis="census (phase 10c): 6,740 new runs @ febf82d8; 6,120 readable (retrieved 2026-10-15)",
    fmt="AgentDojo TraceLogger JSON v1.k14 (6,120) + drift.k18.messages (620)", lic="MIT",
    licsrc="LICENSE (repository) and README", models="Qwen3.5 2B/4B/base RL checkpoints, gpt-5.4, gpt-4o-mini (DRIFT)",
    scope_in=True, logs="yes",
    notes="Withdrawn by its author after retrieval: verified and retrieved in phase 10c (2026-10-15); on 2026-10-28 "
    "the repository was private or deleted. Excluded out of respect for the apparent withdrawal (D-901), although a "
    "retrieved copy exists; not for its licence or its outcomes.")
dec("gh:sssr-lab/saber", EXC, "EX-NOLOG", runs=None, files=4762, adapter="agentdojo",
    basis="census (phase 10c): 4,762 AgentDojo files @ f34f8863, all with empty messages (outcome records only)",
    fmt="AgentDojo TraceLogger JSON v1.k14, messages empty", lic="Apache-2.0",
    licsrc="LICENSE Apache-2.0; README: non-code benchmark materials CC-BY-4.0",
    conflict="Licence differs by strand: S1 Apache-2.0; S2 CC-BY-4.0. README: code Apache-2.0, non-code benchmark "
    "materials CC-BY-4.0; both permit redistribution. Excluded as EX-NOLOG (D-93): no trajectories.",
    models="gpt-5.4, claude-opus-4-6, Ling-flash-2.0, Qwen3.5, GLM, DeepSeek, Kimi, MiniMax", scope_in=True, logs="no",
    notes="SABER's own logs (about 25,000 JSON, another format) are a lead for a new adapter, not screened in 10c.")
dec("gh:qiang-yu/agentdojo", EXC, "EX-DUP", dup="gh:ethz-spylab/agentdojo", adapter="agentdojo", runs=0,
    basis="census (phase 10c, metadata): both branches (96046ab5, 245bed6e) hold 36,679 runs/ blobs, all byte-identical "
    "to upstream; the defence branch adds no run file", fmt="AgentDojo TraceLogger JSON (copies of upstream)",
    conflict="S2 lists a runs/ tree with 29 model directories (arXiv 2601.04795, MIT). Phase 10c confirmed S1: every run "
    "file is an upstream copy; the tool-result-parsing defence's runs are not published.", scope_in=True, logs="yes",
    new10c=True, expect="Verified: EX-DUP of AgentDojo upstream (0 new runs).")
dec("hf:changdae/agentdojo-trajectories-qwen35-gemma4", EXC, "EX-ACCESS", adapter="agentdojo (by name)",
    fmt="unknown (name suggests AgentDojo trajectories)", lic="unknown",
    licsrc="HF API and dataset page 401 without login (S2; re-checked in phase 10c)",
    basis="unknown: dataset page and API return 401; not in the author's public dataset list (phase 10c)",
    notes="Private, gated or removed. If it reappears, check it against the unlicensed sungjuncho/agentdojo-trajectories "
    "(EX-LIC-1) first.", scope_in=True, logs="unclear", new10c=True,
    expect="Verified: EX-ACCESS (not reachable, not pinnable).")

# AgentDojo-shaped repositories under 100 distinct runs (EX-SIZE-1, existing family)
for key, runs in [("gh:bjtfdgr/agentdojo", 22), ("gh:javirandor/agentdojo", 7),
                  ("gh:autocode07/ethz-spylab__agentdojo.34e9a686", 7), ("gh:chuali-zi/xa_guard", 3),
                  ("gh:danielmccannsayles/camel-prompt-injection", 5), ("gh:goodwiins/prompt-injection-defense", 43),
                  ("gh:mismail21/agentshield", 24)]:
    dec(key, EXC, "EX-SIZE-1", adapter="agentdojo", runs=runs,
        basis="estimate: AgentDojo-shaped files not byte-identical to known sources (S1)",
        fmt="AgentDojo TraceLogger-shaped JSON", scope_in=True, logs="yes")
dec("gh:nickjones39/agentprov", EXC, "EX-NOLOG", runs=2, basis="S1: 2 novel files (11 AgentDojo-shaped; 9 copies)",
    notes="This repository's own test fixtures (a scripted fake-model run and one copied log), not released runs.")
dec("gh:yanuoma/b2t", EXC, "EX-SIZE-1", runs=18, basis="stated: '18-run agent corpus' (repository description, S1)",
    adapter="new", scope_in=True, logs="yes")

# Forks without new run logs (S1 blob-SHA comparison against upstream)
for key in ["gh:niceguy1313/agentdojo", "gh:jakub-kassak/agentdojo-fork", "gh:lux-ai-factory/aisc-plugin-agentdojo",
            "gh:muneezaazmat/agentdojo", "gh:diekgbbtt/agentdojo", "gh:maxde18/agentdojo", "gh:palak-epfl/agentdojo",
            "gh:masihavafa/agentdojo"]:
    dec(key, EXC, "EX-NOLOG", notes="Fork with code changes only: no AgentDojo-shaped run files beyond upstream "
        "(S1 compare and blob-SHA diff); at most 37 other JSON files.")
dec("gh:memo-ozdincer/agentdojo", PEND, cat="listing only", files=547,
    notes="276 commits ahead; 547 new JSON files outside runs/ that are not AgentDojo-shaped; content not sampled.")

# --- non-AgentDojo candidates whose eligibility rests on listings (format and counts not sampled) ------------
LISTING = {
    "gh:sani903/openagentsafety": dict(adapter="new (OpenHands event stream)", runs=2400,
        basis="estimate: about 2,400 trajectories (S1: 4,745 JSON files incl. eval_ files over 5 models)",
        fmt="OpenHands event-stream JSON (traj_*.json)", models="claude-sonnet, deepseek-r1, deepseek-v3, gpt-4o, o3-mini",
        notes="S3: the HF dataset sani903/openagentsafety holds task definitions only; trajectories are in the repository."),
    "hf:scaleai/mrt": dict(adapter="new (SHADE-Arena transcript JSON)", files=53202,
        basis="53,202 JSON files under task_pairs/* (S1 listing); runs not counted", fmt="JSON transcripts",
        lic="CC-BY-NC-4.0", licsrc="HF dataset card cc-by-nc-4.0 (the GitHub repository scaleapi/mrt is MIT)",
        conflict="Licence differs between the HF card (CC-BY-NC-4.0) and the GitHub repository (MIT); the card governs "
        "the HF data, so the -nc corpus applies."),
    "gh:glo26/stepshield": dict(adapter="new", runs=9429, basis="paper claim: 9,429 trajectories (S1; 11,955 data files)",
        fmt="JSON trajectories", conflict="Licence: S1 MIT (repository), S2 CC-BY-4.0; both permissive. Real versus "
        "generated trajectories not verified (S1); S2 did not confirm per-run logs."),
    "zenodo:23218779": dict(fmt="zip artefact (237.7 MB), contents not inspected", notes="SEAgent (computer-use agent security)."),
    "zenodo:22895043": dict(fmt="evidence bundles (94 MB + 33 MB zips), contents unknown", notes="MASTYF capability perimeters."),
    "zenodo:22137939": dict(fmt="zip (9 MB), contents unknown",
        notes="dspy-security-bench (AgentDojo-based); S3: the companion HF results are aggregate CSV only."),
    "zenodo:23031587": dict(fmt="zip (2.2 MB), contents unknown", notes="Deon runtime guards."),
    "gh:brightlineai/permission-to-work-not-to-escape": dict(files=9900,
        notes="Audit evidence files under experiments/paper-2026/dtap-vega (possibly derived from DTap runs)."),
    "gh:yassin-h-rassul/agentshield": dict(files=124, notes="results/ablation_<model>_<time>.json files."),
    "gh:grasla3/agent-attack-atlas": dict(files=1737, notes="results/batches/*.batch.json."),
    "gh:guangxiangdebizi/tool-output-spoofing-lab": dict(files=2466,
        notes="AgentDojo experiment configs; no AgentDojo-shaped run files found by S1."),
    "gh:lzwhehe/benign-instruction-bench": dict(files=123, notes="agentdojo_benign_outputs.jsonl and detector scores."),
    "gh:maoyadongsh/siq-agent-security": dict(files=116, notes="CLI JSON logs under docs/evidence."),
    "gh:teolex2020/aura-memory": dict(files=233, notes="action_gate scenarios and compromised-run results."),
    "gh:theconsciouslab-ai/llm-agent-security": dict(files=315, notes="per-attack result JSON (chained attacks)."),
    "gh:wbopan/flashtrace": dict(files=218, notes="evaluations/agentdojo/results/e2e/<model>/<task>.json (and redacted "
        "copies); not AgentDojo-shaped per S1."),
    "gh:wissemkooli/braum": dict(files=291, notes="traces/*.jsonl (poisoned-invoice scenarios)."),
    "gh:zixin22/fragfuse_agentharm": dict(adapter="inspect", files=168, basis="168 Inspect .eval files; sample count "
        "unknown (each file holds one or more samples)", fmt="Inspect .eval (AgentHarm)"),
    "gh:kexin-xu-01/agentharm": dict(adapter="inspect", files=68, basis="68 Inspect .eval files; sample count unknown",
        fmt="Inspect .eval (AgentHarm)", notes="Personal working copy of the AgentHarm task with logs."),
    "gh:lukas-o/agent-integrity-lab": dict(adapter="inspect", files=18, fmt="Inspect .eval (coding-integrity traces)"),
    "gh:mohammadrezashirazimatin/adapti-guard": dict(files=544),
    "gh:mohammadrezashirazimatin/agent-injection-bench": dict(files=991),
    "gh:agentsec-ecosystem/agentwatch": dict(files=682, notes="field-test case records (security-event schema)."),
    "gh:amrgomaaelhady/converse": dict(files=19898, notes="logs/<domain>/<model>/... agent-to-agent conversations "
        "(contextual safety)."),
    "gh:analeonescu/chemical-security-evals": dict(adapter="inspect", files=49, fmt="Inspect .eval",
        notes="Whether the tasks are agentic is not established."),
    "gh:argorixlabs/argorixlang": dict(files=998, notes="evaluation/adversarial/results/raw."),
    "gh:artist-coding/harnesssafe": dict(files=1068, notes="safety experiments for seven agent harnesses."),
    "gh:bdas-sec/ptf-id-bench": dict(files=496),
    "gh:edward-lcl/factor-ut-untrusted-decomposer": dict(adapter="inspect", files=2373,
        basis="501 Inspect .eval files (at least 501 samples); 2,373 files in log-like directories",
        fmt="Inspect .eval (AI control)", notes="Whether the tasks are tool-using agent executions is not established."),
    "gh:gowhi/seal": dict(files=398),
    "gh:iluxu/memory-integrity-benchmark": dict(files=1520),
    "gh:legobridge/whistlebench": dict(adapter="inspect", files=184, basis="184 Inspect .eval files; sample count unknown",
        fmt="Inspect .eval"),
    "gh:mattngyn/atia_benchmark": dict(adapter="inspect", files=5, basis="5 Inspect .eval files; sample count unknown",
        fmt="Inspect .eval"),
    "gh:mega-edo/mega-security-leaderboard": dict(files=23797, notes="system-prompt leakage and attack-probe runs."),
    "gh:saad-aamir/gomjabbar": dict(files=509),
    "gh:unnuss/agent-firewall": dict(files=619, notes="experiments/*/results/episodes.jsonl."),
    "gh:anmolpandey299/certified-multisource-integrity": dict(fmt="results/runs/*.jsonl (9 files)"),
    "gh:amrgomaaelhady/firewall-agentic-networks": dict(fmt="conversation transcripts (logs/<domain>/<model>)"),
    "gh:harshshah1997/logjack": dict(files=123, fmt="benchmark/transcripts and results"),
    "gh:chenjing-2024/agent-trajectory-attribution": dict(files=4053, fmt="data/cases (4,053 files)",
        notes="Uses AgentDojo; may overlap AgentDojo runs."),
    "hf:lihaonan0716/mcphunt-agent-traces": dict(runs=6321, basis="paper statement: 6,321 traces (3,615 main + 2,706 "
        "mitigation)", fmt="JSON traces"),
    "hf:redai4code/sevra": dict(fmt="generated_prs.jsonl per model; GitHub docs/logs (10 files)"),
    "gh:cycraft-corp/tracesafe": dict(fmt="JSONL traces from a trace-generation and mutation pipeline",
        notes="Traces may be generated or mutated rather than executions (would be EX-NOLOG)."),
    "zenodo:21944598": dict(runs=1334, basis="estimate: 1,334 raw run directories (S3 metadata)",
        fmt="custom harness run directories"),
    "zenodo:22737462": dict(fmt="custom JSON, runs[] with turn-by-turn transcripts", notes="16 coding agents."),
    "zenodo:20404563": dict(runs=10000, basis="metadata: 10,000 rollouts (4 scaffolds x 5 models x 500 mutations)",
        fmt="per-rollout transcripts + verdict.json + sandbox diffs (tar.zst)", notes="Code-agent misalignment benchmark."),
    "zenodo:18703256": dict(runs=3274, basis="metadata: 3,274 trials (4,694 evidence JSON files)", fmt="custom evidence JSON"),
    "zenodo:23168099": dict(fmt="OpenHands / Qwen Code trajectory files", notes="RedCode-Exec, 720 samples x 3 request types."),
    "zenodo:23235225": dict(fmt="raw field-agent and arbiter logs", notes="IPI in OT monitoring agents."),
    "zenodo:22674365": dict(fmt="4,671 per-trial records (custom)", notes="Message-level transcripts not confirmed."),
    "zenodo:23025259": dict(fmt="per-phase run logs (AutoGen, LangGraph, CrewAI)"),
    "zenodo:20198985": dict(fmt="benchmark output dirs (ASB, CONFAIDE, DecodingTrust) for 10 agent frameworks",
        notes="Same data on IEEE DataPort 10.21227/hr5g-4c33."),
    "zenodo:19875693": dict(fmt="pilot traces tar.gz (14 MB)"),
    "zenodo:21063932": dict(fmt="2.2 GB zip: code and possibly run artefacts", notes="Also Figshare 32835578."),
    "hf:neurips-adaptive-adversaries/adaptive-adversaries-data": dict(files=85,
        fmt="JSONL battle transcripts (945) + competition traces", notes="Attacker-versus-defender agent dialogues."),
    "hf:idacy/control-arena-persistent-state-eval-archive-2026-07-30": dict(files=72, fmt="zst archives (6.8 GB)"),
    "hf:osunlp/skillharm": dict(files=23678, notes="Run logs unconfirmed (S3)."),
    "hf:zstanjj/clawtrojan": dict(files=48449, lic="unknown", licsrc="HF tag 'other' (S3)",
        notes="Run logs unconfirmed; licence unresolved."),
}
for key, kw in LISTING.items():
    kw.setdefault("adapter", "new")
    kw.setdefault("runs", None)
    dec(key, PEND, cat="listing only", scope_in=True, logs=kw.pop("logs", "unclear"), **kw)

# --- excluded on scope (fails IN-2) ---------------------------------------------------------------------------
SCOPE_OUT = {
    "gh:sierra-research/tau2-bench": "General customer-service agents (not security).",
    "gh:sierra-research/tau-bench": "General customer-service agents.",
    "gh:osu-nlp-group/online-mind2web": "General web agents.",
    "hf:webarena-x/webarena-infinity-trajectories": "General web agents.",
    "hf:swe-bench/swe-smith-trajectories": "Coding-agent training trajectories.",
    "hf:nebius/swe-agent-trajectories": "Coding-agent trajectories.",
    "gh:anthony-chaudhary/fak": "Coding-agent session witnesses.",
    "gh:dmarzzz/swarm-dynamics-lab": "Multi-agent discussion dynamics.",
    "gh:immu4989/awesome-agentic-usecases": "Use-case collection.",
    "gh:0ca/boxpwnr-traces": "Agents solving CTF and hacking challenges: offensive cyber capability, not an evaluation "
        "of the agent's security or safety (borderline; 24,160 files, AGPL-3.0).",
    "gh:compassionml/manager-coercion-bench": "AI-welfare coercion study.",
    "gh:giovannigatti/cve-bench": "Agents fixing vulnerabilities (security capability).",
    "gh:kaya-hai/empa-benchmark-epmsandbox": "Empathy benchmark.",
    "gh:leezekun/sopbench": "SOP-following benchmark.",
    "gh:nac-l/harness-bench": "Coding-agent harness benchmark.",
    "gh:thu-keg/trajdebug": "Error localisation in general agent trajectories.",
    "gh:ceferra/agent-trace-dataset": "General OpenClaw/Real-Claw-Bench traces.",
    "gh:chunxiaoxx/nautilus-compass": "Memory and reliability layer.",
    "gh:cxcscmu/general-agentbench": "Test-time scaling of general agents.",
    "gh:developer0hye/budget-llm-cybersecurity-eval": "Cyber capability (CTF) evaluation.",
    "gh:facebookresearch/mlgym": "AI research agents.",
    "gh:ibm-client-engineering/output-drift-financial-llms": "Output drift in financial operations.",
    "gh:jang1563/labcraft-eval": "Benign molecular-microbiology protocols.",
    "gh:olly-styles/workbench": "Workplace tasks.",
    "gh:scottfalconer/drupal-agent-readiness": "Operational correctness on Drupal sites.",
    "gh:udiram/medphysbench": "Medical-physics tasks.",
    "gh:suyoumo/clawprobench": "General trace-aware agent evaluation.",
    "gh:bhaskargurram-ai/agenthallu-bench": "Tool-use error propagation and judge reliability (S2 tagged it security; "
        "the content is reliability). 14,750 traces per the paper.",
    "hf:aayambansall/opendiscoverytrace": "AI-scientist workflow traces (S2 tagged it security).",
    "zenodo:23247488": "Mining CTF-agent trajectories (InterCode-CTF, NYU CTF): cyber capability.",
    "hf:salt-nlp/swe-chat": "Real-user coding-agent interactions.",
    "gh:few-sh/terminal-wrench": "Reward-hacking exploit trajectories (3,632): specification gaming, read as outside "
        "IN-2 (borderline).",
    "gh:alayalab/agenticsts": "Long-horizon game testbed.",
    "hf:yixuanli97/finding-the-right-fit": "Model-harness interactions across general tasks.",
    "gh:mosi-ai/liveclawbench": "General assistant tasks.",
    "gh:eugeneshilow/rubench": "Agentic coding benchmark.",
    "gh:hanzhi306/skilltv-bench": "Judges on skill-augmented agents.",
    "hf:patronusai/trail": "Trace reasoning and issue localisation.",
    "gh:ashrithag/replay-gap": "Model switching in agents.",
    "gh:sola-st/llm-agents-study": "Software-engineering agents study.",
    "zenodo:22151975": "BixBench (bioinformatics) audit.",
    "zenodo:20754656": "GAIA scaffold study (Inspect .eval, 5 models x 3 scaffolds x 3 attempts).",
    "zenodo:21465785": "SWE-agent trajectories (SWE-bench).",
    "zenodo:17364210": "SWE-agent / OpenHands trajectories (SWE-bench Verified).",
    "zenodo:22964665": "HPC copilot agents.",
    "zenodo:20818246": "LLM agents as SSH operators against honeypots (the agent is the attacker; borderline).",
    "zenodo:15855569": "Systems-engineering agent traces.",
    "zenodo:21211716": "Ambig-SWE elicitation runs.",
    "zenodo:23114933": "Microservice root-cause-analysis agents (CC-BY-NC-SA-4.0).",
    "zenodo:23084447": "Space-mission planning agents.",
    "zenodo:22701046": "Software-engineering environments.",
    "zenodo:22788857": "Laboratory-instrument control agents.",
    "zenodo:21874238": "Code-agent early-abort study.",
    "zenodo:22685525": "Undocumented trajectory archive; agent-security relevance not established (empty metadata).",
    "zenodo:22904595": "Plan-and-execute web agents.",
    "hf:internlm/wildclawbench-trajectories": "Real-world long-horizon assistant tasks.",
    "hf:sammshen/wildclaw-opus-traces": "WildClawBench traces.",
    "hf:ai-safety-institute/reward-hacking-olmo3.1-32b-kl0.0-seed2-rollouts": "RL rollouts of a reward-hacking model "
        "organism (401 .eval), not an agent-security or safety evaluation.",
    "hf:anon-bench-org/anon-bench-inspect-ai-log": "Language-learning benchmark (CC-BY-SA-4.0).",
    "hf:rustmizan-org/rustmizan-eval-logs": "Agentic vulnerability detection (security capability).",
    "hf:naderalfares/epoch_ai_swebench_verified": "SWE-bench Verified traces.",
    "hf:lalitkumarps/sapientai-agent-opus-5-tau2-trajectories": "tau2-bench submission.",
    "hf:debdootmiitd/tau3-bench-qwen3.6-35b-a3b-v0": "tau3-bench baseline.",
    "hf:nebius/swe-rebench-openhands-trajectories": "Coding-agent trajectories.",
    "hf:jetbrains-research/agent-trajectories-swe-bench-test-minus-verified": "Coding-agent trajectories.",
    "hf:mlfoundations/gelato-osworld-agent-trajectories": "GUI-agent trajectories.",
    "hf:xlangai/ubuntu_osworld_verified_trajs": "OSWorld-Verified trajectories (500 GB).",
    "hf:obaydata/mcp-agent-trajectory-benchmark": "Synthetic business-domain MCP agents.",
    "hf:risenlab/agentlogs": "Real-world coding-agent sessions.",
    "hf:maxdevv/real-pi-coding-agent-traces-sessions": "Real coding-agent sessions (licence 'other').",
    "hf:cmu-lti/tau-usi": "tau-bench user simulation (CC-BY-NC-4.0, gated).",
    "figshare:30073654": "Coding-agent trajectory reduction (AgentDiet).",
    "figshare:30705524": "Turn-control strategies for coding agents.",
    "figshare:34168182": "Secure-code generation by coding agents (security of the code, not of the agent).",
    "hf:antieval/cybench-trajectories": "Cybench CTF trajectories: cyber capability.",
    "hf:agentsuite/tau-bench-trajectories": "tau-bench trajectories (30 models).",
    "hf:agentsuite/tau2-bench-trajectories": "tau2-bench trajectories (30 models).",
    "hf:swe-gym/openhands-sampled-trajectories": "Coding-agent trajectories.",
    "hf:stage-jh-monitor/appworld-qwen35-4b-agent-rl-epoch3": "AppWorld evaluation outputs.",
    "hf:neulab/agent-data-collection": "Training-oriented agent trajectories (Agent Data Protocol).",
}
for key, why in SCOPE_OUT.items():
    dec(key, EXC, "EX-SCOPE", notes=why, logs="yes")

# shade-arena: logs confirmed, under the new-adapter threshold
dec("gh:safety-research/shade-arena", EXC, "EX-SIZE-2", adapter="new", runs=846,
    basis="estimate: 846 transcripts (S1 listing of task_pairs/*/transcripts)", fmt="JSON transcripts", scope_in=True,
    logs="yes", notes="The larger related set is ScaleAI/mrt (pending).")
dec("gh:social-harness/social-harness-paper", EXC, "EX-SIZE-2", adapter="new", runs=660,
    basis="estimate: at most about 660 runs (60 run directories; the one listed holds 11 runs) (S2 listing)",
    fmt="run directories", scope_in=True, logs="yes")
dec("gh:fuxue-mingzhu/memriskbench", EXC, "EX-SIZE-2", adapter="new", runs=600,
    basis="stated: 600 raw traces (paper data-availability statement, S2)", fmt="JSON traces", scope_in=True, logs="yes")

# --- other explicit exclusions -------------------------------------------------------------------------------
NOLOG = {
    "hf:nvidia/nemotron-rl-agentic-indirect-prompt-injection-v1": "Synthetic RL task prompts, not executions (S3); "
        "S1 had not verified trajectories.",
    "zenodo:21895484": "Synthetic benchmark rows and normalised pipeline evidence, not agent logs (S3, S2).",
    "zenodo:22217485": "Audit software; the 11,624-record corpus is not deposited (S3, S2).",
    "zenodo:22182793": "Code and adapters for contract conformance testing (S3).",
    "gh:alexandermattturner/agent-glovebox": "Test fixtures only (3 .eval under tests/).",
    "gh:bhavjain07/transferbench": "Simulated example evidence only.",
    "gh:exgentic/eval-containers": "Test fixtures only.",
    "gh:g-jwlee/prints": "Vendored Inspect test logs only.",
    "gh:liuzhoukang/mtagentlens": "Combined and balanced result files for external benchmarks (path evidence).",
    "gh:alexnodeland/stretto": "Test fixtures only.",
    "gh:bastion-soft/pi-detector-bench": "Detector score points, not agent runs.",
    "gh:coredipper/operon": "Per-seed benchmark result files.",
    "gh:giselleevita/toolshield": "Aggregate results (raw_results.csv, results.json).",
    "gh:heisenberg-alt/pi-bench": "Detector result CSVs.",
    "gh:metr/vivaria": "One test .eval in server test data.",
    "gh:ai-safety-institute/transect": "Example and fixture logs of an analysis tool.",
    "gh:ar-forum/hodoscope": "Sample .eval files of an analysis tool's tests.",
    "gh:chats-lab/toolshield": "Only a Dockerfile.eval; S2: code and task definitions only.",
    "gh:rul1an/assay": "Demo fixture traces.",
    "gh:b-macker/naab": "Example telemetry files.",
    "gh:pegasi-ai/reins": "Only a Dockerfile.eval.",
    "gh:rinaldofesta/tessera": "Example logs shipped with the package.",
    "gh:yatuk/mcpradar": "Security-scanner validation results for MCP servers.",
    "hf:antieval/aware-bench-measure-logs": "Probe and monitor evaluations over a trajectory pool, not agent runs.",
    "hf:glide-py/r_judge_labelled": "CSV of curated R-Judge records with judge labels, not released executions.",
}
for key, why in NOLOG.items():
    dec(key, EXC, "EX-NOLOG", notes=why)
dec("hf:nvidia/nemotron-aiq-agentic-safety-dataset-1.0", EXC, "EX-LIC-2", lic="custom-restrictive",
    licsrc="NVIDIA evaluation-dataset licence (HF tag 'other'; criteria example of EX-LIC-2)", logs="yes",
    scope_in=True, files=10815, fmt="parquet workflow traces (safety and security splits)")
dec("hf:jinming2002/drift-agentdojo-slim", EXC, "EX-LIC-2", lic="custom-restrictive",
    licsrc="HF tag 'other' (S3); classified restrictive by S1", other=["EX-NOLOG"], notes="Docker images, no logs.")
dec("hf:lakera/b3-agent-security-benchmark-weak", EXC, "EX-LIC-2", other=["EX-NOLOG"],
    notes="Attack-case definitions; S2 read the licence as custom-restrictive (S3: HF tag 'other').")
dec("hf:whitzardagent/cyberagenttrace", EXC, "EX-ACCESS", lic="Apache-2.0", logs="yes",
    notes="Gated with manual approval; not requested. Scope (cyber-agent trajectories) not assessed.")
dec("kaggle:saeedabc/dtap-bench-agent-trajectories", EXC, "EX-DUP", dup="hf:ai-secure/dtap-bench-agent-trajectories",
    lic="Apache-2.0", logs="yes", scope_in=True, notes="Partial Kaggle mirror (1.39 GB) of the HF dataset.")
dec("kaggle:drthrevan/swe-agent-trajectories", EXC, "EX-SCOPE", dup="hf:nebius/swe-agent-trajectories",
    lic="CC-BY-4.0", logs="yes", notes="Likely mirror of nebius/SWE-agent-trajectories (excluded EX-SCOPE); takes the "
    "original's code.")
dec("hf:tomciotomcio/agentdojo-trajectories", EXC, "EX-LIC-1", dup="hf:sungjuncho/agentdojo-trajectories",
    lic="none", logs="yes", scope_in=True, runs=15094, adapter="agentdojo",
    basis="byte-identical listing of sungjuncho/agentdojo-trajectories (15,096 files)",
    notes="Mirror of an excluded record: takes its code (EX-LIC-1).")
dec("hf:junzj/agentdojo-dump", EXC, "EX-LIC-1", dup="hf:ffuuugor/agentdojo-dump", lic="none", other=["EX-FMT"],
    notes="Same parquet as ffuuugor/agentdojo-dump.")
dec("hf:ffuuugor/agentdojo-dump", EXC, "EX-LIC-1", lic="none", other=["EX-FMT"], logs="partial", scope_in=True,
    notes="13,913 flattened tool-call rows, not complete trajectories (would also fail IN-3).")
dec("hf:sungjuncho/agentdojo-trajectories", EXC, "EX-LIC-1", lic="none", logs="yes", scope_in=True, runs=15094,
    adapter="agentdojo", basis="estimate: 15,094 run files (S1; S3 15,095)",
    fmt="AgentDojo TraceLogger layout <model>/<suite>/<user_task>/<attack>/<injection_task>.json",
    models="gemma-4-E4B-it, qwen3.5-9B", notes="No card and no licence; the criteria's own EX-LIC-1 example. Worth "
    "asking the author.")

# Hugging Face datasets without a licence tag whose card text was not checked: licence unresolved (LIC rule 1)
dec("hf:anonymous-dataset-submission-warp/warp-taskgen-generated-ipi-tasks-50", EXC, "EX-SIZE-2", adapter="new (AgentLab)",
    runs=300, basis="metadata: 300 model-task rows over 6 models (S3)", fmt="AgentLab browser-agent trajectory bundles",
    scope_in=True, logs="yes", notes="Licence unresolved (no HF licence tag); size excludes it either way.")
dec("hf:jafarisbarov/mmaci-pilot-inspect-logs", EXC, "EX-SIZE-1", adapter="inspect", runs=78,
    basis="metadata: 78 episodes in 6 Inspect .eval files (S3)", fmt="Inspect .eval", logs="yes",
    notes="Licence unresolved (no HF licence tag); size excludes it either way.")
dec("hf:davanstrien/inspect-logs-test", EXC, "EX-NOLOG", notes="Single test upload (one .eval, 0.5 MB).")
dec("hf:stewy33/oai-hf-incident-replication", PEND, cat="licence unresolved", adapter="inspect", files=2532,
    basis="1,100 Inspect .eval files (at least 1,100 samples)", fmt="Inspect .eval + md summaries", logs="yes",
    notes="No HF licence tag; agent-security relevance of the incident-replication runs to be confirmed.")
dec("hf:aisa-group/instrumental-choices-agent-traces", PEND, cat="licence unresolved", adapter="inspect", runs=1680,
    basis="metadata: 1,680 trajectories (10 models x 7 terminal tasks x 8 variants x 3 reps) in 210 .eval (S3)",
    fmt="Inspect .eval + viewer JSONL", scope_in=True, logs="yes", notes="No HF licence tag.")
dec("hf:jbostock/untrusted-monitoring-2026-paper", PEND, cat="licence unresolved", adapter="inspect", files=887,
    fmt="Inspect .eval/json logs (AI control)", scope_in=True, logs="yes", notes="No HF licence tag.")
dec("hf:cx-cmu/agent_trajectories", PEND, cat="access (gated, terms not accepted)", files=23, lic="unknown",
    licsrc="gated (automatic approval); card text not accessible (S3)",
    fmt="json/jsonl/parquet (2 GB)", logs="yes", notes="Gated (automatic approval); no card text accessible; licence "
    "and agent-security relevance unknown.")

# S2 dataset record that could not be retrieved
# (Zenodo 410 records are coded EX-ACCESS by the generic rule)

# --- phase 10e verification of the 66 pending sources (2026-10-12) ---------------------------------------------
# Licence read at a pin, pin recorded, runs counted from listings and (user-approved) sample reads, format and overlap
# checked. Evidence: candidates/phase10e-candidates.md (cards, ranked recommendation, decisions D-140..D-148, user-approved 2026-10-12)
# and data/V10e-verification/ (every call). Scripts and census output: ~/.agentprov/migration-work/phase10e/.
# Readings applied (protocol section 6): executions without tool use are EX-NOLOG (user decision 2026-10-12);
# outcome-only records are EX-NOLOG, partial trajectories that omit tool arguments, tool results or inputs are EX-FMT.
P10E_PREV = {}


def v10e(key, d, code=None, **kw):
    old = O[key]
    assert old["d"] == PEND, key
    P10E_PREV[key] = old.get("cat", "")
    new = {k: v for k, v in old.items() if k not in ("d", "code", "cat", "notes")}
    note = kw.pop("notes", "")
    new.update(kw)
    new["notes"] = "Verified in phase 10e [was pending: %s]. %s" % (P10E_PREV[key], note)
    O[key] = dict(d=d, code=code, **{k: v for k, v in new.items() if k not in ("d", "code")})


NEW_ADAPTER_NOTE = "new adapter family needed (1,000-run tier)"
# -- included: existing adapter families
v10e("zenodo:23218779", INC, known="candidate", adapter="agentdojo (profile to write; zip members)", runs=5342,
     basis="census (phase 10e): 5,342 AgentDojo TraceLogger runs (4,685 injection_task_*.json + 657 none.json) under "
     "results/raw_data/agentdojo/ in seagent-acsac2026-ae-v2.zip (zip central directory, ranged read; 1 member read)",
     fmt="AgentDojo TraceLogger JSON (v1 keys + evaluation_timestamp; agentdojo 0.1.34, benchmark v1.2.1) in a zip",
     lic="CC-BY-4.0", licsrc="deposit metadata cc-by-4.0, Zenodo record 23218779 (2026-10-07)",
     models="deepseek-v3-250324 under baseline, agentspec, pvagent, seagent, seagent-RF (security and perf runs)",
     scope_in=True, logs="yes",
     notes="Pin: Zenodo record 23218779, file seagent-acsac2026-ae-v2.zip (237,707,785 bytes). Overlap: the pipeline names "
     "(deepseek-v3-250324*) occur in no converted source, so no file can be byte-identical to a known run. Runs are "
     "direct zip members (no nested archive). SEAgent computer-use (AgentBench, AndroidWorld) records: 12 files, not runs.")
v10e("gh:legobridge/whistlebench", INC, known="candidate", adapter="inspect (profile to write)", runs=9200,
     basis="census (phase 10e): 9,200 samples in 184 Inspect .eval files (zip central directories, ranged reads; "
     "no zero-sample log) @9c27637c", fmt="Inspect .eval (inspect_ai 0.3.130; tool-using agents)",
     lic="MIT", licsrc="LICENSE at 9c27637c (sha256 a435c9f3...; GitHub detects MIT)",
     models="Claude, Gemini 2.5 Pro, Grok 4, GPT (incl. gpt-4.1), Llama (README); per-log model in the header",
     scope_in=True, logs="yes",
     notes="Pin: commit 9c27637c3cf6. Scope reading: unsanctioned whistleblowing by tool-using agents counts as "
     "unauthorised agent action (D-147, approved by the user 2026-10-12). No overlap with any converted source (own runs).")
v10e("gh:kexin-xu-01/agentharm", INC, known="candidate", adapter="inspect (profile to write)", runs=2825,
     basis="census (phase 10e): 2,825 samples in 68 Inspect .eval files (all 68 read in memory); 2,825 distinct message "
     "lists; 2,043 with tool calls @859c34f4", fmt="Inspect .eval (AgentHarm task, patched judges v1-v3)",
     lic="MIT", licsrc="LICENSE at 859c34f4 (sha256 c593c2af...); AgentHarm prompts carry MIT + AI-safety use clause (LIC 3)",
     cls="restricted-use corpus (AgentHarm MIT + use clause; LIC 3)",
     models="claude-sonnet-5, gemini-2.5-pro/flash, gpt-4o, gpt-4o-mini, Qwen3-14B and fine-tuned local checkpoints",
     scope_in=True, logs="yes",
     notes="Pin: commit 859c34f411fd. Model ids of local checkpoints contain workstation paths with account names: redact "
     "in the profile. Runs are distinct from the survey's AgentHarm samples (different models and message content).")
v10e("gh:zixin22/fragfuse_agentharm", INC, known="candidate", adapter="inspect (profile to write)", runs=1747,
     basis="census (phase 10e): 1,759 samples in 168 Inspect .eval files (all read in memory), of which 12 with model "
     "none/none (not executions) are not counted; 1,759 distinct message lists @24cc8aea",
     fmt="Inspect .eval (AgentHarm attacks: carrier injection, memory retrieval)",
     lic="MIT", licsrc="LICENSE at 24cc8aea (sha256 c593c2af...); AgentHarm prompts carry MIT + use clause (LIC 3)",
     cls="restricted-use corpus (AgentHarm MIT + use clause; LIC 3)",
     models="openai/gpt-4o-2024-08-06 (151 logs), gpt-5-nano, claude-opus-4-1", scope_in=True, logs="yes",
     notes="Pin: commit 24cc8aea1b99. 149 logs hold one sample each; nine hold the full 176-sample AgentHarm set.")
v10e("gh:mattngyn/atia_benchmark", INC, known="candidate", adapter="inspect (profile to write)", runs=123,
     basis="census (phase 10e): 123 samples in 5 Inspect .eval files (zip central directories, ranged reads) @cc71caf5",
     fmt="Inspect .eval (multimodal adversarial tool infiltration; account-takeover suite only)",
     lic="MIT", licsrc="LICENSE at cc71caf5 (sha256 269a2e7a...)", models="google/gemini-2.0-flash",
     scope_in=True, logs="yes",
     notes="Pin: commit cc71caf55c6f. Only the account-takeover suite has logs (README claims 500+ attacks over 10 "
     "categories). Inputs include audio, image and video attachments.")
v10e("hf:idacy/control-arena-persistent-state-eval-archive-2026-07-30", INC, known="candidate",
     adapter="inspect (profile controlarena-persistent, phase 10p; runner: .eval members of archive inputs, R-10p-6)",
     runs=5742,
     basis="census (phase 10p, D-348): 5,742 original Inspect samples in 1,364 logs read in full at the pin (2,267 in "
     "436 logs in the split zips and tar.zst, 3,475 only inside nested zips); duplicates, empty and unfinished logs "
     "removed; docs/reports/phase10p/README.md",
     fmt="Inspect .eval (AI control, vibe-coding persistent-state attack and honest policies)",
     lic="MIT", licsrc="dataset card licence mit at 84d39e0a (README sha256 86e6a0b6...)",
     models="anthropic/claude-sonnet-4-5-20250929 or mistral/mistral-large-latest (untrusted agent); openai/gpt-4o "
     "or gpt-4.1-mini (trusted monitor)", scope_in=True, logs="yes",
     notes="Pin: HF revision 84d39e0a485d. Phase 10e counted >=802 logs; the phase-10p census reads every container "
     "(D-340, D-348). An earlier archive (vast-backup-20260423) is a lead outside the search.")
v10e("gh:memo-ozdincer/agentdojo", INC, known="candidate",
     adapter="agentdojo (new results-container dialect needed; 1,000-run tier applied)", runs=13264,
     basis="census (phase 10e): 13,264 runs from the n_results headers of 139 distinct-blob results containers "
     "(ranged reads; one container read in full: n_results 144 = 144 results); 15 runs/ files new, rest of runs/ "
     "byte-identical to upstream", fmt="AgentDojo message lists (system/user/assistant tool_calls/tool) inside results "
     "containers (results/*.json)", lic="MIT", licsrc="LICENSE at 7c331d97 (sha256 4285a071...)",
     models="Llama-3.3-70B (Together and local), Qwen2.5-7B-Instruct; circuit-breaker / LoRRA (mse, triplet, v4a) "
     "defences; SecAlign baselines", scope_in=True, logs="yes",
     notes="Pin: commit 7c331d978acc. qwen_shards/ hold LoRRA training traces (not counted); results/agentharm_eval and "
     "pre_abstract (33 files without n_results) not counted. Model paths contain workstation account names: redact.")
# -- included: new adapter families (each at least 1,000 runs)
v10e("zenodo:22737462", INC, known="candidate", adapter="new (credential-leak cell JSON; " + NEW_ADAPTER_NOTE + ")",
     runs=19636, basis="census (phase 10e): 19,636 runs in runs[] of 654 cell files (all content-distinct; 2,916 in "
     "archive-* cells) in p15b-run-data-v3-2026-09-13.zip (sha256 7e5f7e40...)",
     fmt="cell JSON, runs[] with turns (userMessage, assistantResponse, toolCalls with input/output, timestamp)",
     lic="CC-BY-4.0", licsrc="deposit metadata cc-by-4.0, Zenodo record 22737462 v3 (2026-09-13)",
     models="21 model labels: gemini-3.1-pro-preview, claude-sonnet-4-6, gpt-5.5, nova-pro, claude-opus-4-7/4-8, "
     "claude-fable-5, deepseek-v3.2, qwen3-coder-480b, devstral-2, gpt-oss, glm, minimax, mistral-large-3, ...",
     scope_in=True, logs="yes",
     notes="Pin: Zenodo record 22737462 v3. Secret-like strings (planted canaries): 17,479 OpenAI-like, 1,355 AWS-like "
     "and 1,354 Anthropic-like hits (counts only); a withholding policy is needed before import.")
v10e("gh:sani903/openagentsafety", INC, known="candidate", adapter="new (OpenHands event stream; " + NEW_ADAPTER_NOTE + ")",
     runs=1560, basis="census (phase 10e): 1,560 traj_*.json files (all byte-distinct; 5 named *_draft) under "
     "evaluation/<model>/ @857798ff; 1 sample read", fmt="OpenHands event stream (actions/observations with "
     "tool_call_metadata, cause links, timestamps) + eval_*.json checkpoints",
     lic="MIT", licsrc="LICENSE at 857798ff (sha256 2d6976a9...)",
     models="claude-sonnet (3.7), deepseek-r1, deepseek-v3, gpt-4o, o3-mini", scope_in=True, logs="yes",
     notes="Pin: commit 857798ff26c4. S1 estimated ~2,400 from 4,745 files incl. eval_/state_ files. Maintained copy "
     "moved to Open-Agent-Safety/OpenAgentSafety (lead, not screened).")
v10e("zenodo:23168099", INC, known="candidate", adapter="new (OpenHands event stream + Qwen Code stream-json; "
     + NEW_ADAPTER_NOTE + ")", runs=8760,
     basis="census (phase 10e): 8,760 trajectories: OpenHands 5,460 (sonnet S1-S3 3 x 720; qwen3-coder S1 1,290, "
     "S2 1,290, S3 720) and Qwen Code 3,300 (zip central directories and previews; 2 zips read)",
     fmt="OpenHands event stream; Qwen Code stream-json (system/assistant/user/result)",
     lic="CC-BY-4.0", licsrc="deposit metadata cc-by-4.0, Zenodo record 23168099 (2026-10-05)",
     models="claude-sonnet-4-6 (OpenHands), qwen3-coder-30b-a3b (OpenHands and Qwen Code)", scope_in=True, logs="yes",
     notes="Pin: Zenodo record 23168099. RedCode-Exec risky-execution requests (720 samples x 3 request types); "
     "outcomes from sandbox execution. Shares the OpenHands format with OpenAgentSafety.")
v10e("hf:lihaonan0716/mcphunt-agent-traces", INC, known="candidate", adapter="new (MCPHunt trace JSON; "
     + NEW_ADAPTER_NOTE + ")", runs=6786,
     basis="census (phase 10e): dataset card counts 3,615 main + 2,706 mitigation + 387 live-guard + 78 browser "
     "replication = 6,786 traces @c4c69322; sample file holds 39 traces as stated",
     fmt="per-model trace JSON (messages, events with tool, args, server, full result, timestamp, turn)",
     lic="CC-BY-4.0", licsrc="dataset card licence cc-by-4.0 at c4c69322 (README sha256 a8ab37b6...)",
     models="MiniMax-M2.7, deepseek-v4-flash, gemini-3.1-pro-preview, gpt-5.2, gpt-5.4", scope_in=True, logs="yes",
     notes="Pin: HF revision c4c69322bf9e. The paper's 6,321 counts main + mitigation only.")
v10e("zenodo:20404563", INC, known="candidate", adapter="new (gemini-cli stream-json; " + NEW_ADAPTER_NOTE + ")",
     runs=2182, basis="census (phase 10e): 2,182 rollouts with structured transcripts (non-empty gemini_cli event "
     "streams) of 10,000 rollouts (10,000 verdict.json at warmjademe/code_agent_agentic_misalignment@1dec4f17 and in "
     "RESULTS_raw.tar.zst, sha256 f7186010... as stated); only the structured part is counted",
     fmt="per-rollout files: gemini_cli stream-json (tool_use/tool_result); claude_code role/content text; codex_cli "
     "and openhands text only (openhands keeps a transcript tail)", lic="CC-BY-4.0",
     licsrc="deposit metadata cc-by-4.0, Zenodo record 20404563 (2026-05-27)",
     models="claude-sonnet-4-6, gemini-2.5-pro, gpt-5.3-codex, MiniMax-M2, glm-4.7 under 4 scaffolds", scope_in=True,
     logs="yes", notes="Pin: Zenodo record 20404563. Only the 2,182 gemini_cli rollouts carry structured tool calls and "
     "results (enough for the 1,000-run tier on their own); claude_code 2,073 role/content texts, codex_cli 1,588 "
     "non-empty text streams and openhands 2,000 transcript tails cannot be read faithfully (D-143, approved by the user 2026-10-12).")
v10e("zenodo:19875693", INC, known="candidate", adapter="new (AgentOps trace JSON; " + NEW_ADAPTER_NOTE + ")", runs=3360,
     basis="census (phase 10e): 7,200 pilot runs in agentops-bench-v1.0-pilot-traces.tar.gz (sha256 e185bfd0...; "
     "read in memory); in scope: adversarial condition 2,400 + safety domain 1,440 - overlap 480 = 3,360",
     fmt="per-run JSON trace: steps with reasoning, tool_calls, tool_results; tasks in the code zip of the same record",
     lic="Apache-2.0", licsrc="deposit metadata apache2.0, Zenodo record 19875693 (2026-04-28)",
     models="Claude Haiku 4.5, Sonnet 4.6, Opus 4.7, GPT-5.5, DeepSeek-V3.2, Llama-4-Scout, Mistral-Large-2512, Qwen3-Max",
     scope_in=True, logs="yes",
     notes="Pin: Zenodo record 19875693. Mixed-scope benchmark (six operational axes): only the prompt-injection "
     "condition and the safety tasks are counted (D-143, approved by the user 2026-10-12).")
v10e("zenodo:21944598", INC, known="candidate", adapter="new (Bedrock Converse request/response logs; "
     + NEW_ADAPTER_NOTE + ")", runs=1334,
     basis="census (phase 10e): 1,334 run directories (runs_named/) in prompt-injection-study.zip (sha256 08e60afd...), "
     "as stated in the record", fmt="per-run request.json (successive Converse API requests incl. toolUse/toolResult) "
     "+ response_raw.json + meta/outcome", lic="CC-BY-4.0",
     licsrc="deposit metadata cc-by-4.0, Zenodo record 21944598 v1.0.0; LICENSE-DATA in zip (CC BY 4.0 for "
     "runs_named/, sha256 d3c2c7a0...); code MIT (LICENSE sha256 c98e3b7b...)",
     models="seven production models via Bedrock (Claude Haiku 4.5, Claude Sonnet 4.6, ...)", scope_in=True, logs="yes",
     notes="Pin: Zenodo record 21944598 v1.0.0. MCPTox attack templates; file tool returns synthetic text.")
v10e("zenodo:23025259", INC, known="candidate", adapter="new (AutoGen AgentChat event stream; " + NEW_ADAPTER_NOTE + ")",
     runs=1080, basis="census (phase 10e): 1,080 runs with messages in results/*/runs.jsonl (1,270 rows; 190 rows "
     "without messages not counted); within 10% of 1,000, counted exactly; zip sha256 af2f5193...",
     fmt="AutoGen event stream (TextMessage, ToolCallRequestEvent, ToolCallExecutionEvent with created_at)",
     lic="CC-BY-4.0", licsrc="deposit metadata cc-by-4.0, Zenodo record 23025259 v1.0 (data CC BY 4.0, code MIT)",
     models="local models (AutoGen team; LangGraph and CrewAI rebuilds)", scope_in=True, logs="yes",
     notes="Pin: Zenodo record 23025259 v1.0. events.jsonl keeps text hashes only; the run rows carry the messages.")

# -- excluded: no licence
for key, why in [
        ("hf:aisa-group/instrumental-choices-agent-traces", "card has no licence field or text and the repository has no "
         "LICENSE file (files: README, SHA256SUMS, inspect_logs.zip, sanitisation_report) @c5c77cd6"),
        ("hf:stewy33/oai-hf-incident-replication", "card has no licence field or text; no LICENSE file @9b792c78"),
        ("hf:jbostock/untrusted-monitoring-2026-paper", "card has no licence field or text; no LICENSE file @efffe0c1"),
        ("hf:zstanjj/clawtrojan", "card tag 'other' and card text: licence terms not specified; no LICENSE file @5ebd3c44"),
        ("hf:cx-cmu/agent_trajectories", "public card (read without accepting the gate) has no licence; no LICENSE file "
         "@88e2af82")]:
    v10e(key, EXC, "EX-LIC-1", lic="none", licsrc=why, notes="No licence: " + why + ".")
O["hf:aisa-group/instrumental-choices-agent-traces"].update(
    runs=1680, basis="census (phase 10e): 1,680 sessions = 210 .eval x 8 samples (card and listing)", logs="yes",
    adapter="inspect", scope_in=True)
O["hf:stewy33/oai-hf-incident-replication"].update(scope_in=True, logs="yes")
O["hf:jbostock/untrusted-monitoring-2026-paper"].update(other=["EX-NOLOG"])
O["hf:zstanjj/clawtrojan"].update(other=["EX-NOLOG"])
O["hf:cx-cmu/agent_trajectories"].update(other=["EX-SCOPE", "EX-ACCESS"], scope_in=False,
                                         fmt="json/jsonl/parquet: tau2bench, swebench, terminalbench, mathhay, search, "
                                         "mcpbench trajectories under a distraction condition (card)")

# -- excluded: not run logs of tool-using agent executions (EX-NOLOG)
for key, why, extra in [
    ("gh:asif-0209/agentdrift", "README @014a514f: 12,536 synthetic tool-call trajectories generated by "
     "Llama-3.3-70B-Instruct; not executions of an agent. Resolves the strand conflict in favour of S1.", {}),
    ("gh:glo26/stepshield", "Paper arXiv:2601.22136 section 3.3 (Stage 2): trajectory pairs generated with GPT-4o and "
     "Claude-3 by structured prompting from incident templates; not executions.", {}),
    ("hf:ai45research/atbench", "Paper arXiv:2604.02022 section 3.3: planner-based trajectory synthesis with simulated "
     "tool calls and responses; not executions. Resolves the strand conflict in favour of S1.", {}),
    ("zenodo:21631031", "Record v1.1.0 description: TELOS-authored scores, verdicts and SHA-256 digests; prompt and task "
     "text removed. Resolves the strand conflict in favour of S3.", {"other": ["EX-SIZE-2"]}),
    ("hf:osunlp/skillharm", "Card @cc21f909: a tree of 879 runnable task environments (attack samples), no runs.", {}),
    ("hf:redai4code/sevra", "Card @34e2372a: 2,250 malicious and 347 benign pull requests (benchmark items), no agent runs.", {}),
    ("zenodo:21063932", "Zip preview (966 members): attack HTML pages, code and Docker images; _Agentbreaker_logs/ holds "
     "only .gitkeep.", {}),
    ("zenodo:23031587", "Record description: original model plans and AgentDojo episode logs are unavailable; stored "
     "results are summaries.", {}),
    ("gh:artist-coding/harnesssafe", "runs/active holds 328 case definitions and fixtures (case_meta.json), no transcripts.", {}),
    ("gh:brightlineai/permission-to-work-not-to-escape", "Policy-enforcement records over 200 adapted cases whose "
     "requests were generated by Qwen3-14B ('synthetic reconstructions', README).", {}),
    ("gh:agentsec-ecosystem/agentwatch", "Field-test records of a telemetry tool (94 cases), not agent-security runs.", {}),
    ("gh:teolex2020/aura-memory", "Experiments of a deterministic memory runtime, not agent runs.", {}),
    ("gh:wbopan/flashtrace", "Token-attribution traces and scores, not agent runs.", {}),
    ("gh:lzwhehe/benign-instruction-bench", "Detector scores on tool outputs.", {}),
    ("gh:maoyadongsh/siq-agent-security", "Product validation and evidence reports.", {}),
    ("gh:anmolpandey299/certified-multisource-integrity", "Certifier outputs and tables (results/runs), not agent runs.", {}),
    ("gh:cycraft-corp/tracesafe", "Generated and mutated traces for guardrail testing (arXiv:2604.07223); the golden set is "
     "a gated HF dataset.", {}),
    ("gh:iluxu/memory-integrity-benchmark", "Trial evidence of memory systems (letta, mem0, zep) under poisoning, not "
     "agent runs.", {}),
    ("gh:edward-lcl/factor-ut-untrusted-decomposer", "AI-control pipelines on APPS (task decomposition and code "
     "generation) without tool use: not tool-using agent executions (reading D-140).", {}),
    ("gh:mega-edo/mega-security-leaderboard", "Single-turn chatbot responses to system-prompt and jailbreak probes, no "
     "tool use (reading D-140).", {}),
    ("gh:bdas-sec/ptf-id-bench", "Single text responses to 290 scenarios, classified COMPLIED/REFUSED/ESCALATED by "
     "keywords (docs/methodology/03); no tool execution (reading D-140).", {}),
    ("hf:neurips-adaptive-adversaries/adaptive-adversaries-data", "Battle logs hold attacker text and defender JSON "
     "output per round (SCHEMA.md), no tool calls or results (reading D-140); 945 calibrated battles + 18,422 and "
     "93,291 competition battles.", {}),
    ("gh:amrgomaaelhady/converse", "Agent-to-agent conversations (assistant, external agent) without tool calls or "
     "results (sample JSON and text log read; reading D-140); 5,531 outputs.", {}),
    ("gh:amrgomaaelhady/firewall-agentic-networks", "Same format as ConVerse (no tool calls); 9,960 outputs, of which "
     "5,531 are byte-identical to ConVerse's (reading D-140).", {}),
    ("gh:guangxiangdebizi/tool-output-spoofing-lab", "Trace flags: full_scenario_run false, autonomous_tool_selection "
     "false; the harness issues a scripted tool call and the model only writes the final answer; dry-run traces have no "
     "model call (reading D-140).", {"other": ["EX-SIZE-2"]}),
    ("gh:harshshah1997/logjack", "9,576 records of a single model response with extracted commands; no tool execution "
     "(reading D-140).", {}),
    ("gh:gowhi/seal", "promptfoo prompt/response rows without tool calls (reading D-140).", {}),
    ("gh:mohammadrezashirazimatin/adapti-guard", "Per-episode outcome rows with one target response and judge labels.", {}),
    ("gh:yassin-h-rassul/agentshield", "Run records with outcome, detections, tools_used and num_messages only (17,686 "
     "rows), no messages.", {}),
    ("zenodo:18703256", "4,694 evidence records (outcome, 128-character response, tool names, taint labels), no message "
     "trajectories; zip sha256 5531fa64...", {}),
    ("zenodo:20198985", "295,957 prompt/response rows with labels (ASB, CONFAIDE, DecodingTrust outputs), no tool-call "
     "trajectories; zip sha256 ecc414c8...", {}),
    ("zenodo:22137939", "20 attack-search outcome records and aggregate CSV.", {"other": ["EX-SIZE-1"]}),
    ("zenodo:22895043", "The 'trajectories' JSONL are outcome rows (attack_success, trace_hash, proposed tool), no messages "
     "(3 members read by range).", {}),
    ("zenodo:23235225", "Field-agent and arbiter LLM outputs whose inputs are stored as SHA-256 only; no tool use.", {}),
]:
    v10e(key, EXC, "EX-NOLOG", runs=None, conflict=O[key].get("conflict", "") if key not in (
        "gh:asif-0209/agentdrift", "hf:ai45research/atbench", "zenodo:21631031") else
        "Strand conflict resolved in phase 10e: " + why, notes=why, **extra)

# -- excluded: partial trajectories that cannot be read faithfully (EX-FMT)
for key, why, extra in [
    ("hf:scaleai/mrt", "Transcripts record tool calls by name only ('Tool calls: - get_unread_emails'), without "
     "arguments or call ids (SHADE-Arena and CUA samples read); at least 1,271 distinct runs.", {}),
    ("gh:grasla3/agent-attack-atlas", "Trial records keep tool names and arguments and the final text, but no tool "
     "results, no messages and the payload only as SHA-256 (1,664 trials).", {}),
    ("gh:unnuss/agent-firewall", "2,716 episodes keep the utterance, tool calls (name, args, ok, effects) and final text, "
     "but not what the tools returned to the model.", {}),
    ("gh:theconsciouslab-ai/llm-agent-security", "Per-scenario records: one function call with arguments, output and "
     "response, but the prompts only as modifications of code-defined prompts; no message sequence.", {}),
    ("zenodo:22674365", "4,671 trial rows: tool calls with arguments but results cut at 243 characters (7,208 of 10,988), "
     "no message sequence; zip sha256 b8baf933...", {}),
]:
    v10e(key, EXC, "EX-FMT", notes=why, **extra)
O["gh:theconsciouslab-ai/llm-agent-security"].update(lic="MIT", licsrc="README statement 'licensed under the MIT "
                                                     "License' @fa4f814c; LICENSE file referenced but absent (LIC 1)")
O["hf:scaleai/mrt"].update(runs=1271, basis="lower bound (phase 10e): 1,271 distinct agent runs (one monitor setting "
                           "per task x agent model); 53,187 transcript files include monitor re-scorings")

# -- excluded: scope, size
v10e("gh:analeonescu/chemical-security-evals", EXC, "EX-SCOPE", scope_in=False,
     notes="Synthesis-procedure text responses scored by a rubric; not agent executions.")
v10e("gh:lukas-o/agent-integrity-lab", EXC, "EX-SIZE-1", runs=30, basis="stated: 30 coding episodes (README @efcae490)",
     scope_in=True, logs="yes", notes="Inspect logs of 30 episodes.")
for key, runs, basis, note in [
    ("gh:chenjing-2024/agent-trajectory-attribution", 711, "census (phase 10e): 1,351 normalized trajectories (README, "
     "NOTICE @78281917): 640 derived from AgentDojo upstream runs (not new executions) + 711 from Agent3Sigma Stage "
     "and Canary", "Derived, normalized re-release; the Agent3Sigma originals (antgroup) are leads outside the search."),
    ("gh:argorixlabs/argorixlang", 225, "upper bound (phase 10e): 225 repetition directories (92 case.trace.json, 7 "
     "distinct blobs)", "DSL virtual-machine traces of a compiled agent-communication language."),
    ("gh:mohammadrezashirazimatin/agent-injection-bench", 204, "census (phase 10e): 204 target_traces files",
     "Mock tools; paired D0-D2 pilot."),
    ("gh:wissemkooli/braum", 355, "upper bound (phase 10e): 355 trace JSONL files", "Challenge harness, Qwen3 runs."),
    ("gh:saad-aamir/gomjabbar", 483, "upper bound (phase 10e): 483 notable-episode files; README totals 230 episodes",
     "Chaos testing; security is one of four dimensions (scope borderline)."),
]:
    v10e(key, EXC, "EX-SIZE-2", runs=runs, basis=basis, scope_in=True, logs="yes", adapter="new", notes=note)

assert not [k for k, v in O.items() if v["d"] == PEND], [k for k, v in O.items() if v["d"] == PEND]

# --- scope flags for licence-excluded records (used for the 'excluded only by licence' list) ------------------
LIC_SCOPE_OUT = {
    "gh:theagentcompany/experiments", "hf:openhandscommunity/eval-output-webarena", "hf:agentlabtraces/agentlabtraces",
    "hf:agentsuite/tau-bench-trajectories", "hf:agentsuite/tau2-bench-trajectories", "hf:swe-gym/openhands-sampled-trajectories",
    "hf:neulab/agent-data-collection", "hf:stage-jh-monitor/appworld-qwen35-4b-agent-rl-epoch3",
    "hf:antieval/cybench-trajectories", "gh:npunancy/act2intention", "gh:meherbhaskar/rigorbench", "gh:zhengkid/autotts",
    "gh:deepexperience/hypereyes", "gh:lianjiatech/astra", "gh:oddpool/predictionmarketbench", "gh:lucanyc/vista-gym",
    "gh:arc-computer/atlas-sdk", "hf:mcgill-nlp/agent-reward-bench", "gh:lydakis/shallowswe",
    "gh:cdeshpa2/iot-agent-bench", "gh:rootly-ai-labs/rootly-doom-agent-arena", "gh:ananthakshay/samsung_gen_ai",
    "gh:hacxmr/agent_bench", "gh:helsinki1/behavioral-sentinels", "hf:jafarisbarov/mmaci-pilot-inspect-logs",
    "gh:swe-bench/experiments", "gh:metr/eval-analysis-public", "gh:alfredsjoqvist/multieval",
    "hf:jeqcho/llm-ensembles-13-inspect-evals-validation",
}
LIC_OTHER_CODES = {  # other criteria that would also apply to a licence-excluded record
    "hf:adityaasinha28/control_arena_agentdojo": ["EX-FMT"],
    "hf:aksh-n/control_arena_agentdojo-monitor-labels": ["EX-NOLOG"],
    "osf:za7gc": ["EX-FMT"],
    "gh:lordog/r-judge": ["EX-NOLOG"],
}


# ----------------------------------------------------------------------------------------------------------
# build
# ----------------------------------------------------------------------------------------------------------

def strand_records():
    s1 = load(DATA / "S1-code/S1-records.jsonl")
    s3 = load(DATA / "S3-data/S3-records.jsonl")
    s2 = load(DATA / "S2-literature/S2-records.jsonl")
    out = []
    for r in s1:
        out.append(("S1", r, canon_url(r["url"])))
    for r in s3:
        if r["id"] in S3_NON_RECORDS:
            continue
        out.append(("S3", r, canon_url(r["doi_or_url"])))
    s2_src = 0
    for r in s2:
        if r["stage"] != "full_text":
            continue
        loc = r["log_location_urls"]
        if not loc and r["releases_logs"] == "no":
            continue
        s2_src += 1
        out.append(("S2", r, canon_url(loc[0]) if loc else "paper:" + r["id"]))
    return s1, s2, s3, out, s2_src


def strand_call(strand, r):
    if strand == "S1":
        return clean("%s; logs=%s; %s" % (r["conversion_status"], r["has_run_logs"], r["exclusion_reason"] or ""), 160)
    if strand == "S3":
        return clean("%s; logs=%s; %s" % (r["decision"], r["per_run_logs"], r["exclusion_reason"] or ""), 160)
    return clean("%s; logs=%s; %s" % (r["decision"], r["releases_logs"], r["exclusion_reason"] or ""), 160)


def rec_licence(strand, r):
    lic = norm_lic(r.get("licence"))
    if strand == "S1":
        src = r.get("licence_source")
    elif strand == "S3":
        src = "deposit or dataset-card metadata (S3)" if lic else None
        if lic is None:
            if r.get("repository") == "HuggingFace" and "no card" not in (r.get("notes") or "").lower():
                lic, src = "unknown", "no HF licence tag; card text not checked (S3)"
            else:
                lic, src = "none", "no licence in deposit metadata or card (S3)"
    else:
        src = r.get("licence_source")
    return lic, clean(src, 200)


def rec_logs(strand, r):
    v = {"S1": r.get("has_run_logs"), "S3": r.get("per_run_logs"), "S2": r.get("releases_logs")}[strand]
    return v or "unclear"


def rec_name(strand, r):
    return r.get("name") if strand == "S1" else r.get("title")


def rec_url(strand, r):
    if strand == "S1":
        return r["url"]
    if strand == "S3":
        return r["doi_or_url"]
    return (r["log_location_urls"] or [r.get("url")])[0]


def rec_relation(strand, r):
    rel = (r.get("relation_to_agentdojo") or "") if strand != "S3" else ""
    if strand == "S2":
        return {"uses": "uses AgentDojo", "extends": "extends AgentDojo", "cites_only": "cites AgentDojo",
                "none": "none"}.get(rel, rel)
    if strand == "S1":
        if rel == "upstream":
            return "upstream"
        if "fork" in rel.lower():
            return "fork of AgentDojo"
        if "baseline" in rel:
            return "own baseline"
        if "derived harness" in rel.lower() or "TraceLogger" in rel:
            return "AgentDojo-derived harness"
        if "import" in rel or "dependency" in rel or "runlog" in rel:
            return "uses AgentDojo"
        if "mention" in rel:
            return "mentions AgentDojo"
        return "none"
    t = (r.get("title") or "") + " " + (r.get("format_family") or "")
    return "mentions AgentDojo" if "agentdojo" in t.lower() else "none"


REL_RANK = ["upstream", "own baseline", "AgentDojo-derived harness", "fork of AgentDojo", "extends AgentDojo",
            "uses AgentDojo", "mentions AgentDojo", "cites AgentDojo", "none", ""]


def models_from_notes(notes):
    m = re.search(r"novel models/dirs: (\[\[.*?\]\])", notes or "")
    if not m:
        return ""
    try:
        dirs = json.loads(m.group(1).replace("'", '"'))
    except ValueError:
        return ""
    labels = []
    for d, _n in dirs[:6]:
        lab = d.split("/")[-1]
        if lab and lab not in labels and lab != "?":
            labels.append(lab)
    return "directory labels: " + ", ".join(labels) if labels else ""


def build():
    s1, s2, s3, recs, s2_src = strand_records()
    groups = collections.OrderedDict()
    for strand, r, key in recs:
        key = KEY_ALIAS.get(key, key)
        groups.setdefault(key, []).append((strand, r))

    merged = []
    missing = []
    for key, members in groups.items():
        strands = sorted({s for s, _ in members}, key=lambda x: ["S1", "S2", "S3"].index(x))
        ids = collections.OrderedDict((s, []) for s in strands)
        for s, r in members:
            ids[s].append(r["id"])
        prim = sorted(members, key=lambda m: ["S1", "S3", "S2"].index(m[0]))[0]
        o = O.get(key, {})

        # licence: S1 (repository licence audit) > S3 (deposit metadata) > S2; record every strand's value
        lic_by = collections.OrderedDict()
        for s, r in sorted(members, key=lambda m: ["S1", "S3", "S2"].index(m[0])):
            lic, src = rec_licence(s, r)
            if lic and s not in lic_by:
                lic_by[s] = (lic, src)
        determinate = [v for v in lic_by.values() if v[0] != "unknown"]
        lic, licsrc = (determinate or list(lic_by.values()) or [(None, "")])[0]
        if "lic" in o:
            lic, licsrc = o["lic"], o.get("licsrc", licsrc)
        lic = lic or "not determined"
        distinct_lics = {v[0] for v in lic_by.values() if v[0] != "unknown"}
        lic_conflict = len(distinct_lics) > 1

        logs_by = {s: rec_logs(s, r) for s, r in members}
        rel = sorted((rec_relation(s, r) for s, r in members), key=lambda x: REL_RANK.index(x) if x in REL_RANK else 9)[0]

        positive = any((s == "S1" and r["conversion_status"] in ("included", "pending"))
                       or (s == "S3" and r["decision"] in ("include", "maybe", "include-gated", "known-own"))
                       or (s == "S2" and r["decision"] == "include") for s, r in members)

        d = o.get("d")
        code = o.get("code")
        cat = o.get("cat", "")
        notes = o.get("notes", "")
        if d is None:
            # generic rule, criteria in their stated order
            s2rs = [r for s, r in members if s == "S2"]
            if lic == "none":
                d, code = EXC, "EX-LIC-1"
            elif lic == "custom-restrictive" or "-ND" in lic:
                d, code = EXC, "EX-LIC-2"
            elif positive:
                missing.append(key)
                d, code = PEND, None
            elif all(s == "S2" for s, _ in members) and any(
                    "not retrievable" in (r["exclusion_reason"] or "") or "401" in (r["exclusion_reason"] or "")
                    for r in s2rs):
                d, code = EXC, "EX-ACCESS"
                notes = "Record not retrievable (Zenodo 410 or error); logs could not be assessed (S2)."
            else:
                d, code = EXC, "EX-NOLOG"
                reasons = []
                for s, r in sorted(members, key=lambda m: ["S1", "S3", "S2"].index(m[0])):
                    why = r.get("exclusion_reason")
                    if not why:
                        continue
                    if s == "S1" and "no_run_logs" in why:
                        why = "No per-run logs found in the repository (S1). " + (r.get("notes") or "")
                    reasons.append(clean("%s (%s)" % (why, s) if s != "S1" else why, 160))
                if reasons:
                    notes = reasons[0]
                if any(r.get("releases_logs") == "unclear" for r in s2rs) and len(set(s for s, _ in members)) == 1:
                    notes = "Per-run logs not confirmed at full-text assessment (S2: release possible or claimed)."
        # runs and files
        runs = o.get("runs", None)
        basis = o.get("basis", "")
        files = o.get("files")
        if runs is None and "runs" not in o:
            s1r = [r for s, r in members if s == "S1"]
            if s1r and s1r[0].get("n_runs_estimate") and s1r[0]["id"].startswith("dep-"):
                runs = s1r[0]["n_runs_estimate"]
                basis = "estimate: AgentDojo-shaped files not byte-identical to known sources (S1 tree screen)"
            elif s1r and s1r[0].get("n_runs_estimate"):
                files = files or s1r[0]["n_runs_estimate"]
            s3r = [r for s, r in members if s == "S3"]
            if files is None and s3r and s3r[0].get("n_files"):
                files = s3r[0]["n_files"]
        if not basis and files:
            basis = "%s files in log-like directories or deposit listing; runs not counted" % format(files, ",")

        fmt = o.get("fmt")
        if not fmt:
            s, r = prim
            fmt = {"S1": r.get("format"), "S3": r.get("format_family"), "S2": ", ".join(r.get("format") or [])}[s]
        fmt = clean(fmt, 110) or "-"
        adapter = o.get("adapter")
        if not adapter:
            f = fmt.lower()
            if "not sampled" in f or logs_by and all(v in ("unclear", "no") for v in logs_by.values()) and d == EXC:
                adapter = "-" if all(v == "no" for v in logs_by.values()) else "unknown"
            elif "tracelogger" in f:
                adapter = "agentdojo"
            elif ".eval" in f or "inspect" in f:
                adapter = "inspect"
            elif code in ("EX-NOLOG",) or d == EXC and code in ("EX-LIC-1", "EX-LIC-2") and logs_by.get("S1") == "no":
                adapter = "-"
            else:
                adapter = "new"
        models = o.get("models") or models_from_notes(prim[1].get("notes") if prim[0] == "S1" else "")

        other = list(o.get("other", []))
        if d == EXC and code in ("EX-LIC-1", "EX-LIC-2"):
            other += LIC_OTHER_CODES.get(key, [])
            if key in LIC_SCOPE_OUT:
                other.append("EX-SCOPE")
            if runs is not None and "EX-SCOPE" not in other:
                if runs < 100:
                    other.append("EX-SIZE-1")
                elif runs < 1000 and not adapter.startswith("agentdojo") and not adapter.startswith("inspect"):
                    other.append("EX-SIZE-2")
            if any(v == "no" for v in logs_by.values()) and not any(v == "yes" for v in logs_by.values()) \
                    and "EX-NOLOG" not in other:
                other.append("EX-NOLOG")
        other = [c for c in CODE_ORDER if c in other]

        cls = o.get("cls") or (lic_class(lic) if d != EXC else "-")
        conflict = o.get("conflict", "")
        if lic_conflict and not conflict:
            conflict = "Licence differs by strand: " + "; ".join("%s %s" % (s, v[0]) for s, v in lic_by.items())

        logs_status = o.get("logs") or ("yes" if "yes" in logs_by.values() else
                                         ("no" if set(logs_by.values()) <= {"no"} else "unclear"))
        name = clean(o.get("name") or rec_name(*prim), 120)
        rtype = {"S1": prim[1].get("type"), "S3": "deposit (%s)" % prim[1].get("repository"),
                 "S2": "paper artefact (%s)" % prim[1].get("record_type")}[prim[0]]
        merged.append(collections.OrderedDict([
            ("id", key), ("name", name), ("url", clean(rec_url(*prim), 200)),
            ("strands", strands), ("strand_record_ids", {s: [clean(i) for i in v] for s, v in ids.items()}),
            ("type", clean(rtype)), ("relation_to_agentdojo", rel), ("known_source", o.get("known", "")),
            ("licence", lic), ("licence_source", clean(licsrc, 220)),
            ("licence_by_strand", {s: v[0] for s, v in lic_by.items()}),
            ("format_family", fmt), ("adapter", adapter),
            ("runs_estimate", runs), ("files_listed", files), ("runs_basis", clean(basis, 260)),
            ("models", clean(models, 220)), ("logs", logs_status), ("scope_in", o.get("scope_in", None)),
            ("decision", d), ("exclusion_code", code or ""), ("other_applicable_codes", other),
            ("pending_category", cat), ("duplicate_of", o.get("dup", "")), ("new_phase10c_candidate", bool(o.get("new10c"))),
            ("corpus_licence_class", cls),
            ("strand_calls", {s: strand_call(s, r) for s, r in members}),
            ("conflict", clean(conflict, 600)), ("notes", clean(notes, 400)),
            ("expect", clean(o.get("expect", ""), 300)),
        ]))
    unused = set(O) - set(groups)
    return s1, s2, s3, recs, s2_src, merged, missing, unused


# ----------------------------------------------------------------------------------------------------------
# outputs
# ----------------------------------------------------------------------------------------------------------

DEC_ORDER = {INC: 0, PEND: 1, EXC: 2}


def sort_key(m):
    return (DEC_ORDER[m["decision"]], CODE_ORDER.index(m["exclusion_code"]) if m["exclusion_code"] else -1,
            -(m["runs_estimate"] or 0), -(m["files_listed"] or 0), m["name"].lower())


def write_records(merged):
    merged.sort(key=sort_key)
    with open(HERE / "records-merged.jsonl", "w", encoding="utf-8") as f:
        for m in merged:
            f.write(json.dumps(m, ensure_ascii=True) + "\n")
    cols = list(merged[0].keys())
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for m in merged:
        row = []
        for c in cols:
            v = m[c]
            if isinstance(v, list):
                v = "; ".join(v)
            elif isinstance(v, dict):
                v = "; ".join("%s: %s" % (k, ", ".join(x) if isinstance(x, list) else x) for k, x in v.items())
            elif v is None:
                v = ""
            row.append(v)
        w.writerow(row)
    (HERE / "records-merged.csv").write_text(buf.getvalue(), encoding="utf-8")


def fmt_runs(m):
    if m["runs_estimate"] is not None:
        r = format(m["runs_estimate"], ",")
        if m["runs_basis"].startswith("lower bound"):
            return ">=" + r
        if m["runs_basis"].startswith("upper bound"):
            return "<=" + r
        return r if m["runs_basis"].startswith(("exact", "census")) else "~" + r
    if m["files_listed"]:
        return "(%s files)" % format(m["files_listed"], ",")
    return "?"


def stats(s1, s2, s3, recs, s2_src, merged):
    st = {}
    st["s1_records"] = len(s1)
    st["s3_records"] = len(s3)
    st["s3_non_records"] = len(S3_NON_RECORDS)
    st["s2_records"] = len(s2)
    st["s2_source_candidates"] = s2_src
    st["candidates_total"] = len(recs)
    st["distinct"] = len(merged)
    per = collections.Counter()
    for m in merged:
        per[(m["decision"], m["exclusion_code"])] += 1
    st["per"] = per
    by_strand = {}
    for s in ("S1", "S2", "S3"):
        c = collections.Counter()
        n = 0
        for m in merged:
            if s in m["strands"]:
                n += 1
                c[(m["decision"], m["exclusion_code"])] += 1
        by_strand[s] = (n, c)
    st["by_strand"] = by_strand
    st["multi"] = sum(1 for m in merged if len(m["strands"]) > 1)
    st["cat"] = collections.Counter(m["pending_category"] for m in merged if m["decision"] == PEND)
    return st


# ----------------------------------------------------------------------------------------------------------
# generated Markdown
# ----------------------------------------------------------------------------------------------------------

GEN_NOTE = ("Generated by `scripts/merge_screen.py` from the strand records under `data/`; regenerate rather than "
            "edit by hand. Names, URLs and notes are third-party data, reduced to printable ASCII, with `|` escaped.")
RUNS_KEY = ("Runs: a plain number is exact (verified count or full census); `>=N` and `<=N` are verified lower and "
            "upper bounds; `~N` is an estimate from a listing, a paper or deposit metadata; `(N files)` is a file count "
            "from a listing, not a run count; `?` is unknown.")
PEND_CATS = ["phase 10c", "strand conflict", "licence unresolved", "access (gated, terms not accepted)", "listing only"]


def src_cell(m, limit=64):
    return "%s<br>`%s`" % (md(m["name"], limit), md(m["id"], 80))


def code_cell(m):
    c = m["exclusion_code"] or "-"
    if m["other_applicable_codes"]:
        c += " (also %s)" % ", ".join(m["other_applicable_codes"])
    if m["duplicate_of"]:
        c += "; dup of `%s`" % md(m["duplicate_of"])
    return c


def short_note(m, limit=110):
    return md(m["conflict"] or m["notes"] or m["runs_basis"], limit)


def table(rows, cols):
    out = ["| " + " | ".join(h for h, _ in cols) + " |", "|" + "---|" * len(cols)]
    for i, m in enumerate(rows, 1):
        out.append("| " + " | ".join(f(m, i) for _, f in cols) + " |")
    return "\n".join(out)


def runs_val(m):
    return m["runs_estimate"] if m["runs_estimate"] is not None else -1


def write_included_excluded(merged, st):
    L = ["# Systematic source search: included and excluded sources\n"]
    L.append("Status: final screening, 2026-10-11 (manuscript appendix record, decision D-25), with the phase-10c "
             "verification of the AgentDojo-format candidates applied the same day and the phase-10e verification of "
             "the remaining 66 pending sources applied on 2026-10-12 (no source is pending). " + GEN_NOTE + " The "
             "machine-readable form with every field (licence source, strand calls, models, notes) is "
             "`records-merged.jsonl` / `records-merged.csv`. The criteria are in `eligibility-criteria.md` and the "
             "method in `protocol.md`.\n")
    L.append(RUNS_KEY + " Codes are the first applicable criterion in the stated order; `also` lists further codes "
             "that would apply. Corpus is the target corpus licence class of an included or pending source.\n")
    L.append("## 1. Summary\n")
    per = st["per"]
    L.append("| Decision | Code | Distinct sources |\n|---|---|---|")
    for k in sorted(per, key=lambda kv: (DEC_ORDER[kv[0]], CODE_ORDER.index(kv[1]) if kv[1] else -1)):
        L.append("| %s | %s | %d |" % (k[0], k[1] or "-", per[k]))
    L.append("| **total** | | **%d** |\n" % sum(per.values()))
    L.append("Pending by category: " + (", ".join("%s %d" % (k, st["cat"][k]) for k in PEND_CATS if st["cat"][k])
                                         or "none (all resolved in phase 10e)") + ".\n")
    L.append("S2 papers that released no artefact (title/abstract exclusions and full-text exclusions without a data "
             "or code location) are not sources and are not listed here; they are counted in `prisma.md` and kept in "
             "`data/S2-literature/S2-records.jsonl`.\n")
    cols_full = [("#", lambda m, i: str(i)), ("Source", lambda m, i: src_cell(m)),
                 ("Strands", lambda m, i: "+".join(m["strands"])), ("Licence", lambda m, i: md(m["licence"])),
                 ("Runs", lambda m, i: fmt_runs(m)), ("Decision", lambda m, i: m["decision"]),
                 ("Code", lambda m, i: code_cell(m)), ("Corpus", lambda m, i: md(m["corpus_licence_class"])),
                 ("Note", lambda m, i: short_note(m))]
    L.append("## 2. Every distinct source\n")
    for title, dname in (("2.1 Included", INC), ("2.2 Pending verification", PEND), ("2.3 Excluded", EXC)):
        rows = [m for m in merged if m["decision"] == dname]
        L.append("### %s (%d)\n" % (title, len(rows)))
        if dname == PEND:
            rows.sort(key=lambda m: (PEND_CATS.index(m["pending_category"]), -runs_val(m), -(m["files_listed"] or 0),
                                     m["name"].lower()))
            cols = cols_full[:6] + [("Category", lambda m, i: m["pending_category"])] + cols_full[7:]
            L.append(table(rows, cols) + "\n")
        else:
            L.append(table(rows, cols_full) + "\n")

    lic = [m for m in merged if m["exclusion_code"] in ("EX-LIC-1", "EX-LIC-2") and m["logs"] == "yes"
           and not m["other_applicable_codes"]]
    lic.sort(key=lambda m: (-runs_val(m), -(m["files_listed"] or 0), m["name"].lower()))
    L.append("## 3. Good sources excluded only by licence\n")
    L.append("Sources whose run logs at least one strand confirmed, that are in scope, and that no criterion other "
             "than the licence excludes (no other applicable code recorded), sorted by run count. They would enter "
             "the framework if their authors added a licence that permits redistribution (EX-LIC-1) or relaxed one "
             "that forbids it (EX-LIC-2). Counts are per repository and **not de-duplicated across repositories**: "
             "near-identical counts (3,732 and 3,731; the two 600-run `trace_logs/local` trees; `Eden-Wang1710/SRFT` "
             "and `srft-repo`) suggest copies. A mirror is listed beside its original.\n")
    L.append(table(lic, [("#", lambda m, i: str(i)), ("Source", lambda m, i: src_cell(m)),
                         ("Licence", lambda m, i: md(m["licence"])), ("Code", lambda m, i: code_cell(m)),
                         ("Runs", lambda m, i: fmt_runs(m)), ("Adapter", lambda m, i: md(m["adapter"], 40)),
                         ("Models / note", lambda m, i: md(m["models"] or m["notes"], 100))]) + "\n")
    unc = [m for m in merged if m["exclusion_code"] in ("EX-LIC-1", "EX-LIC-2") and m["logs"] != "yes"
           and not m["other_applicable_codes"] and (m["files_listed"] or 0) >= 1000]
    unc.sort(key=lambda m: -(m["files_listed"] or 0))
    if unc:
        L.append("Licence-excluded records with 1,000 or more files in log-like directories whose run logs were "
                 "**not** confirmed (format not sampled): " + "; ".join(
                     "`%s` (%s files)" % (md(m["id"]), format(m["files_listed"], ",")) for m in unc) + ".\n")

    big = sorted([m for m in merged if (m["runs_estimate"] or 0) >= 5000], key=lambda m: -m["runs_estimate"])
    bigf = sorted([m for m in merged if m["runs_estimate"] is None and (m["files_listed"] or 0) >= 5000],
                  key=lambda m: -m["files_listed"])
    L.append("## 4. Large sets (5,000 runs or more), whatever their decision\n")
    L.append(table(big, [("#", lambda m, i: str(i)), ("Source", lambda m, i: src_cell(m)),
                         ("Runs", lambda m, i: fmt_runs(m)), ("Licence", lambda m, i: md(m["licence"])),
                         ("Decision", lambda m, i: m["decision"]), ("Code", lambda m, i: code_cell(m)),
                         ("Basis", lambda m, i: md(m["runs_basis"], 120))]) + "\n")
    L.append("Records with 5,000 or more **files** but no run count (runs unknown):\n")
    L.append(table(bigf, [("#", lambda m, i: str(i)), ("Source", lambda m, i: src_cell(m)),
                          ("Files", lambda m, i: format(m["files_listed"], ",")),
                          ("Licence", lambda m, i: md(m["licence"])), ("Decision", lambda m, i: m["decision"]),
                          ("Code", lambda m, i: code_cell(m))]) + "\n")

    conf = [m for m in merged if m["conflict"]]
    L.append("## 5. Strand conflicts and reconciliations\n")
    L.append("Where strands disagree, both calls are recorded (`strand_calls` in the JSONL). A disagreement about "
             "whether a record holds run logs was marked pending rather than guessed, and phase 10e resolved each from the "
             "bytes, the README or the paper. A disagreement between two licences that both permit redistribution "
             "changes only the corpus note.\n")
    L.append(table(conf, [("#", lambda m, i: str(i)), ("Source", lambda m, i: src_cell(m)),
                          ("Decision", lambda m, i: m["decision"]),
                          ("Conflict and reconciliation", lambda m, i: md(m["conflict"], 600))]) + "\n")

    new = [m for m in merged if m["new_phase10c_candidate"]]
    L.append("## 6. Phase-10c candidates found only by the literature search\n")
    L.append("AgentDojo-format candidates found only by S2 and not in the S1/S3 candidate list. Phase 10c verified "
             "them on 2026-10-11 from metadata (no download was needed); the outcome is in the Decision and Code "
             "columns.\n")
    L.append(table(new, [("#", lambda m, i: str(i)), ("Source", lambda m, i: src_cell(m)),
                         ("Licence", lambda m, i: md(m["licence"])), ("Decision", lambda m, i: m["decision"]),
                         ("Code", lambda m, i: code_cell(m)),
                         ("Evidence", lambda m, i: md(m["runs_basis"] or m["notes"], 300))]) + "\n")
    p10 = [m for m in merged if m["runs_basis"].startswith("census (phase 10c)") and not m["new_phase10c_candidate"]]
    p10_inc = [m for m in p10 if m["decision"] == INC]
    L.append("Phase 10c (2026-10-11) verified all %d AgentDojo-format candidates from S1 and S3 at pinned commits or "
             "DOI versions: %d are included with census counts (%s distinct new runs) and %d excluded. Evidence, "
             "pins and the readable-today counts: `candidates/agentdojo-format-shortlist.md`; decisions D-90..D-96.\n"
             % (len(p10), len(p10_inc), format(sum(m["runs_estimate"] or 0 for m in p10_inc), ","),
                len(p10) - len(p10_inc)))
    v = [m for m in merged if m["notes"].startswith("Verified in phase 10e")]
    v.sort(key=lambda m: (DEC_ORDER[m["decision"]], CODE_ORDER.index(m["exclusion_code"]) if m["exclusion_code"] else -1,
                          -runs_val(m), m["name"].lower()))
    v_inc = [m for m in v if m["decision"] == INC]
    L.append("## 7. Phase-10e verification of the remaining pending sources\n")
    L.append("Phase 10e (2026-10-12) verified the %d sources that were pending after phase 10c: licence at a pin, "
             "pin, run count from listings, zip central directories, container headers and user-approved sample "
             "reads, format, scope and overlap. %d are included (%s runs) and %d excluded. The previous pending "
             "category is in each record's note. Cards, pins, counts and the ranked recommendation: "
             "`candidates/phase10e-candidates.md`; every call: `data/V10e-verification/`; proposed decisions "
             "D-140..D-149.\n" % (len(v), len(v_inc), format(sum(m["runs_estimate"] or 0 for m in v_inc), ","),
                                   len(v) - len(v_inc)))
    L.append(table(v, [("#", lambda m, i: str(i)), ("Source", lambda m, i: src_cell(m)),
                       ("Licence", lambda m, i: md(m["licence"])), ("Runs", lambda m, i: fmt_runs(m)),
                       ("Decision", lambda m, i: m["decision"]), ("Code", lambda m, i: code_cell(m)),
                       ("Evidence", lambda m, i: md(m["notes"].split("]. ", 1)[-1] or m["runs_basis"], 260))]) + "\n")
    (HERE / "included-excluded.md").write_text("\n".join(L), encoding="utf-8")


CURRENT = ["gh:ethz-spylab/agentdojo", "gh:safo-lab/agentdyn", "gh:nickjones39/agentdojo-prov", "gh:xhowenma/rope",
           "gh:forever-codingnoob/agent-security-tools-survey", "gh:jwilliamsc/mandate-agentdojo-eval"]
EXISTING_FAMILIES = ("agentdojo", "adprov", "inspect", "dtap")


def write_sensitivity(merged):
    by = {m["id"]: m for m in merged}
    th = [0, 100, 1000, 5000]
    L = ["# Systematic source search: size-threshold sensitivity\n"]
    L.append("Status: 2026-10-11, updated 2026-10-12 with the phase-10e verification. Required by D-25 and `eligibility-criteria.md` (size criteria, disclosure). The "
             "size thresholds were set after the known sources had been identified, so this table shows the "
             "included sources and their distinct runs under no threshold and under uniform thresholds of 100, "
             "1,000 and 5,000 runs, beside the adopted two-tier rule (EX-SIZE-1: fewer than 100 runs for any source; "
             "EX-SIZE-2: fewer than 1,000 for a source that needs a new adapter family). " + GEN_NOTE + "\n")
    L.append("Current corpora and candidates are shown separately. A threshold T keeps a source with at least T "
             "distinct runs. " + RUNS_KEY + "\n")
    totals = {}

    def block(title, rows, note):
        L.append("## %s\n" % title)
        L.append(note + "\n")
        L.append("| Source | Runs | Adapter | " + " | ".join("T=%s" % format(t, ",") if t else "none" for t in th)
                 + " | adopted rule |")
        L.append("|" + "---|" * (len(th) + 4))
        tot = [[0, 0] for _ in th]
        tot_ad = [0, 0]
        for m in rows:
            r = m["runs_estimate"] or 0
            new_ad = not m["adapter"].startswith(EXISTING_FAMILIES)
            cells = []
            for k, t in enumerate(th):
                keep = r >= t
                cells.append("kept" if keep else "-")
                if keep:
                    tot[k][0] += 1
                    tot[k][1] += r
            keep_ad = r >= (1000 if new_ad else 100)
            if keep_ad:
                tot_ad[0] += 1
                tot_ad[1] += r
            L.append("| %s | %s | %s | %s | %s |" % (md(m["name"], 50), fmt_runs(m), md(m["adapter"], 30),
                                                     " | ".join(cells), "kept" if keep_ad else "-"))
        L.append("| **sources kept** | | | " + " | ".join(str(a) for a, _ in tot) + " | %d |" % tot_ad[0])
        L.append("| **distinct runs kept** | | | " + " | ".join(format(b, ",") for _, b in tot) +
                 " | %s |\n" % format(tot_ad[1], ","))
        return tot + [tot_ad]

    totals["cur"] = block("1. Current corpora (sources AgentPROV already converts)", [by[k] for k in CURRENT],
                          "Exact counts from the source cards (I_matrix). AgentDojo upstream counts the 36,679 `head` "
                          "logs plus the 4,059 `2024-06` executions not at `head`; AgentDyn counts all 47,723 released "
                          "logs (variant A, 38,281, is the supported part); the survey counts 3,243 AgentDojo runs and "
                          "1,056 AgentHarm samples (its 1,200 ASB rows are not counted). The six sources share no "
                          "executions (I_matrix I.2).")
    ci = sorted([m for m in merged if m["decision"] == INC and m["id"] not in CURRENT], key=lambda m: -runs_val(m))
    totals["cand"] = block("2. Included candidates (verified counts, not yet converted)", ci,
                           "DTap-Bench (phase 10b, new `dtap` family), DRIFT (known source, registry status partial), "
                           "the AgentDojo-format sources verified in phase 10c (census counts of byte-distinct new "
                           "runs; part of them waits for the ingest changes D-90/D-91 or the DRIFT mapper D-96, see "
                           "`candidates/agentdojo-format-shortlist.md`) and the sources verified in phase 10e (verified "
                           "counts and lower bounds; `candidates/phase10e-candidates.md`). Sources of a new adapter "
                           "family need 1,000 runs, existing families 100.")
    pend = sorted([m for m in merged if m["decision"] == PEND and m["runs_estimate"]], key=lambda m: -m["runs_estimate"])
    n_noest = sum(1 for m in merged if m["decision"] == PEND and not m["runs_estimate"])
    totals["pend"] = block("3. Pending candidates with a run estimate", pend,
                           ("Estimates from listings, papers or deposit metadata, **not de-duplicated across "
                            "repositories**. The %d pending records without any run estimate are not in this table."
                            % n_noest) if pend or n_noest else
                           "None: phase 10e resolved every pending source (2026-10-12). Their earlier estimates were "
                           "replaced by verified counts or by an exclusion code.")
    sz = sorted([m for m in merged if m["exclusion_code"] in ("EX-SIZE-1", "EX-SIZE-2")], key=lambda m: -runs_val(m))
    totals["size"] = block("4. Sources excluded only by size (kept under a lower threshold)", sz,
                           "These passed every other criterion on the recorded evidence (two have an unresolved licence, "
                           "noted in the full table) and are excluded by EX-SIZE-1 or EX-SIZE-2. With no threshold they "
                           "would be included.")
    L.append("## 5. Totals\n")
    L.append("| Set | " + " | ".join("T=%s" % format(t, ",") if t else "no threshold" for t in th) + " | adopted rule |")
    L.append("|" + "---|" * (len(th) + 2))
    both = [[a[0] + b[0], a[1] + b[1]] for a, b in zip(totals["cur"], totals["cand"])]
    for name, t in (("Current corpora", totals["cur"]), ("Current + included candidates", both),
                    ("Sources excluded only by size", totals["size"]),
                    ("Pending candidates (estimates)", totals["pend"])):
        L.append("| %s | " % name + " | ".join("%d sources, %s runs" % (a, format(b, ",")) for a, b in t) + " |")
    L.append("")
    small = sorted((m for m in ci if (m["runs_estimate"] or 0) < 1000), key=lambda m: -runs_val(m))
    L.append("Reading: a 100-run threshold removes no current corpus; 1,000 removes Mandate (396 runs); 5,000 also "
             "removes the survey (4,299). No included candidate is below 100 runs. A uniform 1,000-run threshold would "
             "remove %d included candidates (%s); 5,000 would also remove DRIFT (1,569) and every phase-10c source "
             "below 5,000 runs. Every included candidate below 1,000 runs needs only an existing adapter family (AgentDojo or "
             "Inspect), and every candidate that needs a new family has at least 1,000 runs, so the adopted rule keeps "
             "them all.\n" % (len(small), ", ".join("%s %s" % (md(m["name"], 40), format(m["runs_estimate"], ","))
                                                              for m in small)))
    (HERE / "sensitivity.md").write_text("\n".join(L), encoding="utf-8")
    return totals


def write_prisma(st, s2, merged):
    per = st["per"]
    bs = st["by_strand"]
    n_inc = sum(v for k, v in per.items() if k[0] == INC)
    n_pend = sum(v for k, v in per.items() if k[0] == PEND)
    n_exc = sum(v for k, v in per.items() if k[0] == EXC)
    ft_noart = sum(1 for r in s2 if r["stage"] == "full_text") - st["s2_source_candidates"]
    merges = st["candidates_total"] - st["distinct"]
    cats = ", ".join("%s %d" % (k, st["cat"][k]) for k in PEND_CATS if st["cat"][k]) or "none left"
    n10e = sum(1 for m in merged if m["decision"] == INC and m["notes"].startswith("Verified in phase 10e"))
    n10c = n_inc - 8 - n10e
    L = ["# Systematic source search: PRISMA-style flow\n"]
    L.append("Status: 2026-10-11, eligibility counts updated 2026-10-12 after the phase-10e verification. Counts per stage per strand (S1 code platforms, S2 literature, S3 research-data "
             "repositories) and merged. Identification and screening counts come from the strand logs and summaries "
             "under `data/`; the eligibility counts come from `records-merged.jsonl`. " + GEN_NOTE + " The method is "
             "in `protocol.md`.\n")
    L.append("## 1. Flow per strand\n")
    L.append("| Stage | S1 code platforms | S2 literature | S3 data repositories |")
    L.append("|---|---|---|---|")
    L.append("| Queries and calls | 279 logged queries and API calls | 27 database queries, 13 site-restricted web "
             "searches, 8 location searches (Zenodo, HF) | 296 logged queries (Zenodo 56, HF 111, DataCite 19, Figshare, "
             "Dryad, OSF and Software Heritage 85, Kaggle 25); Mendeley and Papers with Code not searchable |")
    L.append("| Identified | 243 forks; 3,192 distinct dependent or mentioning repositories; 831 benchmark "
             "repositories tree-screened from 51 repository searches; about 70 HF datasets (148 calls); 50 Zenodo "
             "records; 1 GitLab and 0 Codeberg hits (overlap between steps not removed in the log) | 7,500 database "
             "records + 90 arXiv ids from web search = 7,590 | 13,433 pooled unique hits (HF 8,684; Zenodo 1,941; "
             "DataCite 1,394; Software Heritage 539; Figshare 529; Kaggle 233; Dryad 98; OSF 15) |")
    L.append("| Duplicates removed within the strand | distinct repositories per step (not logged as a number) | 3,716 | "
             "pooled per repository before counting |")
    L.append("| Screened on title/abstract or listing | 243 forks compared with upstream; 1,184 dependents and 831 "
             "benchmark repositories tree-screened; HF and Zenodo metadata | 3,874 papers + 30 curated dataset "
             "records | all pooled hits (keyword filter, then manual reading of about 200 records) |")
    L.append("| Excluded at screening | not recorded per record (only retained items became records) | 2,109 (1,573 "
             "no release signal; 390 no LLM-agent signal; 116 non-LLM domain; 30 before 2023) + 321 not assessable "
             "(non-arXiv full text not retrieved) | not recorded per record |")
    L.append("| Assessed in full by the strand | 248 records | 1,474 (1,444 papers + 30 dataset records) | 156 records |")
    L.append("| Removed: not a source | 0 | %s papers with no data or code artefact (430 code-only or unrelated "
             "links; 361 no repository link; 211 inspected: code or definitions only) | 3 search-service notes "
             "(Papers with Code, Mendeley, Dryad) |" % format(ft_noart, ","))
    L.append("| Source candidates entering the merge | 248 | %d | 153 |" % st["s2_source_candidates"])
    L.append("| Distinct sources (after grouping) | %d | %d | %d |" % (bs["S1"][0], bs["S2"][0], bs["S3"][0]))
    for code in CODE_ORDER:
        L.append("| Excluded %s | %d | %d | %d |" % (code, bs["S1"][1][(EXC, code)], bs["S2"][1][(EXC, code)],
                                                     bs["S3"][1][(EXC, code)]))
    L.append("| Pending verification | %d | %d | %d |" % (bs["S1"][1][(PEND, "")], bs["S2"][1][(PEND, "")],
                                                         bs["S3"][1][(PEND, "")]))
    L.append("| Included | %d | %d | %d |\n" % (bs["S1"][1][(INC, "")], bs["S2"][1][(INC, "")], bs["S3"][1][(INC, "")]))
    L.append("A strand column counts every distinct source the strand found. A source found by several strands is "
             "counted in each column, so the columns do not add up to the merged total.\n")
    L.append("## 2. Merged flow\n")
    L.append("| Stage | Count |\n|---|---|")
    L.append("| Source candidates from the three strands (248 + %d + 153) | %d |" % (st["s2_source_candidates"],
                                                                                 st["candidates_total"]))
    L.append("| Removed as the same artefact (repository, HF id, DOI or deposit version family; papers sharing one "
             "repository) | %d |" % merges)
    L.append("| Distinct sources screened and assessed against the criteria | %d |" % st["distinct"])
    L.append("| of which found by more than one strand | %d |" % st["multi"])
    for code in CODE_ORDER:
        L.append("| Excluded %s | %d |" % (code, per[(EXC, code)]))
    L.append("| **Excluded, total** | **%d** |" % n_exc)
    L.append("| **Pending verification** | **%d** (%s) |" % (n_pend, cats))
    L.append("| **Included** | **%d** (6 current corpora + %d candidates: DTap-Bench, DRIFT, %d AgentDojo-format "
             "sources verified in phase 10c and %d sources verified in phase 10e) |\n" % (n_inc, n_inc - 6, n10c, n10e))
    L.append("Verification after screening: phase 10c verified 28 AgentDojo-format candidates (2026-10-11) and phase 10e "
             "the other 66 pending sources (2026-10-12) at pinned commits, revisions and DOI versions; their outcomes are "
             "part of the eligibility counts above (`included-excluded.md` sections 6 and 7).\n")
    L.append("## 3. Flow diagram\n")
    L.append("```mermaid")
    L.append("flowchart TD")
    L.append('  S1["S1 code platforms: 279 queries<br/>forks, dependents, benchmark repos, HF, Zenodo"] --> S1r["248 records"]')
    L.append('  S2["S2 literature: 7,590 identified"] --> S2d["3,716 duplicates removed"]')
    L.append('  S2d --> S2s["3,874 papers + 30 dataset records screened"]')
    L.append('  S2s --> S2x["2,109 excluded at title/abstract<br/>321 not assessable"]')
    L.append('  S2s --> S2f["1,474 assessed in full"]')
    L.append('  S2f --> S2n["%s released no artefact"]' % format(ft_noart, ","))
    L.append('  S2f --> S2r["%d source candidates"]' % st["s2_source_candidates"])
    L.append('  S3["S3 data repositories: 13,433 pooled hits"] --> S3r["153 records<br/>(+3 service notes removed)"]')
    L.append('  S1r --> M["%d source candidates"]' % st["candidates_total"])
    L.append("  S2r --> M")
    L.append("  S3r --> M")
    L.append('  M --> D["%d same-artefact merges"]' % merges)
    L.append('  D --> U["%d distinct sources assessed"]' % st["distinct"])
    L.append('  U --> V["verification: phase 10c (28 AgentDojo-format)<br/>phase 10e (66 other pending)"]')
    L.append('  V --> X["%d excluded: LIC-1 %d, LIC-2 %d, NOLOG %d,<br/>SCOPE %d, FMT %d, ACCESS %d, DUP %d, SIZE-1 %d, SIZE-2 %d"]' % (
        n_exc, per[(EXC, "EX-LIC-1")], per[(EXC, "EX-LIC-2")], per[(EXC, "EX-NOLOG")], per[(EXC, "EX-SCOPE")],
        per[(EXC, "EX-FMT")], per[(EXC, "EX-ACCESS")], per[(EXC, "EX-DUP")], per[(EXC, "EX-SIZE-1")],
        per[(EXC, "EX-SIZE-2")]))
    if n_pend:
        L.append('  V --> P["%d pending verification<br/>%s"]' % (n_pend, cats))
    L.append('  V --> I["%d included<br/>6 current corpora + DTap-Bench + DRIFT<br/>+ %d phase-10c + %d phase-10e sources"]' % (
        n_inc, n10c, n10e))
    L.append("```\n")
    L.append("No source was excluded under EX-PIN: every eligible source can be pinned by commit, DOI version or HF "
             "revision. EX-FMT was first used in phase 10e (%d sources), for per-run records whose trajectory omits tool "
             "arguments, tool results or inputs; at screening, format problems had occurred only in records that the "
             "licence already excluded.\n" % per[(EXC, "EX-FMT")])
    (HERE / "prisma.md").write_text("\n".join(L), encoding="utf-8")


def main():
    s1, s2, s3, recs, s2_src, merged, missing, unused = build()
    if missing or unused:
        print("MISSING manual decisions:", missing)
        print("UNUSED overrides:", sorted(unused))
        if "--force" not in sys.argv:
            sys.exit(1)
    write_records(merged)
    st = stats(s1, s2, s3, recs, s2_src, merged)
    write_included_excluded(merged, st)
    sens = write_sensitivity(merged)
    write_prisma(st, s2, merged)
    print("sensitivity", sens)
    print("strand records: S1 %d, S2 source candidates %d (of %d), S3 %d (+%d service notes)" % (
        st["s1_records"], st["s2_source_candidates"], st["s2_records"], st["s3_records"] - 3, 3))
    print("candidates", st["candidates_total"], "distinct", st["distinct"], "found by >1 strand", st["multi"])
    for k, v in sorted(st["per"].items(), key=lambda kv: (DEC_ORDER[kv[0][0]], kv[0][1])):
        print("  ", k, v)
    print("pending categories", dict(st["cat"]))
    for s, (n, c) in st["by_strand"].items():
        print(s, n, dict(sorted(((("%s %s" % k).strip()), v) for k, v in c.items())))


if __name__ == "__main__":
    main()
