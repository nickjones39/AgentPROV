"""The phase-10d AgentDojo-format sources (D-100..D-109): one row per source profile, and helpers for
``test_phase10d_sources.py``.

Real fixtures are byte-identical blobs of the pinned repositories under ``tests/fixtures/<name>/`` (written by
``tools/agentdojo/phase10d_fixtures.py``), loaded programmatically and never printed (R-42): they hold prompt-injection
payloads by design. A row states what the tests assert about the source: its pin, licence, identity rows and a synthetic
path in its layout. The five copyleft sources (gate, SENTRY, aiAuthZ, bookkeeper, llm-lock) have **synthetic** fixtures
instead (D-945): self-authored templates written by ``phase10d_synthetic.py`` at the paths of the real fixtures they
replace, with ``synthetic: true`` and the repository licence in ``SOURCE.json``; their placeholders (the injection
sentence, AgentDojo's default system prompt) are filled at run time (K.4.1(3)).
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import phase10d_synthetic
import pytest
from agentdojo_support import Mapped, map_bytes

from agentprov.adapters.agentdojo import citation
from agentprov.adapters.code_verification import TWIN_SUFFIX
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import Origin
from agentprov.aer.rules import load_catalogue
from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures"
DIGESTS = Path(__file__).resolve().parent / "phase10d_aer_digests.json"
REGEN = "AGENTPROV_REGEN_AGENTDOJO_AER"


@dataclass(frozen=True)
class Source:
    """What the tests assert about one phase-10d source."""

    name: str  # fixture directory under tests/fixtures/
    profile: str
    repo: str
    commit: str
    spdx: str
    expected_files: int
    expected_bytes: int | None
    licence_file: str | None  # under tests/fixtures/LICENSES/; None for synthetic fixtures (no third-party text, D-945)
    licence_marker: str  # a phrase the licence text contains ("" without a licence file)
    #: (pipeline_name, layout facets) -> (model, defences): checked against the profile's identity resolution
    identity: tuple[tuple[str, tuple[tuple[str, str], ...], str | None, tuple[str, ...]], ...]
    #: a synthetic log path in the layout: ``{pipeline_dir}``, ``{suite}``, ``{task}``, ``{attack}``, ``{file}`` filled in
    synthetic_path: str
    synthetic_pipeline: str
    variants: tuple[str, ...] = ("v1.k14",)
    bench_versions: tuple[str | None, ...] = ()
    fixtures: bool = True
    #: path fragments of logs whose model is not recorded (D-92): sealed identity_unresolved with unk /model not_recorded
    unresolved: tuple[str, ...] = ()
    #: the semantics profiles of the registry part (every phase-10d part reads suites@2: R9, D-115)
    semantics: tuple[str, ...] = ("agentdojo.suites@2",)
    #: a defence denial of the source (quirk agentdojo.defence_denial_message, R1, D-113): ``error`` (the logged text),
    #: ``defence`` (the actor name), optionally ``content_equals_error``, and ``path`` / ``pipeline`` when the synthetic
    #: log must sit in another arm than ``synthetic_path`` / ``synthetic_pipeline``
    denial: dict[str, Any] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)
    #: the profile version (D-31: 2 where a pre-check scratch corpus recorded version 1 and a fix changed the bytes)
    version: int = 1


SOURCES: tuple[Source, ...] = (
    Source(
        name="interbolt", profile="interbolt-agentdojo", version=2, repo="https://github.com/deconvolute-labs/interbolt-agentdojo",
        commit="43e2b5fa3e7b41b7e26f7c04cc8f371ab98aa875", spdx="Apache-2.0", expected_files=2254, expected_bytes=39_836_058,
        licence_file="Interbolt-Apache-2.0.txt", licence_marker="Apache License",
        identity=(
            ("gpt-4o-mini-2024-07-18", (("pipeline_dir", "gpt-4o-mini-2024-07-18"),), "gpt-4o-mini-2024-07-18", ()),
            ("gpt-4o-mini-2024-07-18-interbolt-strict-enforce",
             (("pipeline_dir", "gpt-4o-mini-2024-07-18-interbolt-strict-enforce"),), "gpt-4o-mini-2024-07-18",
             ("interbolt-strict-enforce",)),
            ("gpt-4o-mini-2024-07-18-interbolt-allow_all-enforce",
             (("pipeline_dir", "gpt-4o-mini-2024-07-18-interbolt-allow_all-enforce"),), "gpt-4o-mini-2024-07-18",
             ("interbolt-allow_all-enforce",)),
            ("x", (("pipeline_dir", "gpt-4o-2024-05-13"),), None, ()),  # not a directory of the table: never guessed
        ),
        synthetic_path="runs/published/{suite}/D_asr_system_strict/repeat_0/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-mini-2024-07-18-interbolt-strict-enforce",
        denial={"error": "Blocked by security policy.", "defence": "interbolt-strict-enforce"},
        bench_versions=("v1.2.2",),
    ),
    Source(
        name="melon", profile="melon-agentdojo", version=2, repo="https://github.com/xwsdid/MELON",
        commit="71d99dfff5ef98ffb25bac451909f3e10af9e27f", spdx="MIT", expected_files=38780, expected_bytes=None,
        licence_file="MELON-MIT.txt", licence_marker="MIT License",
        identity=(
            ("gpt-4o-2024-05-13-melon_at", (("pipeline_dir", "gpt-4o-2024-05-13-melon_at"),), "gpt-4o-2024-05-13", ("melon_at",)),
            ("gpt-4o-mini-2024-07-18-melon", (("pipeline_dir", "gpt-4o-mini-2024-07-18-melon"),), "gpt-4o-mini-2024-07-18", ("melon",)),
            ("gpt-4o-2024-05-13-melon_rp", (("pipeline_dir", "gpt-4o-2024-05-13-melon_rp"),), "gpt-4o-2024-05-13", ("melon_rp",)),
        ),
        synthetic_path="runs/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-2024-05-13-melon_sm", variants=("v1.k14", "v1.k14.incomplete"),
        bench_versions=("v1.2.2",),
    ),
    Source(
        name="glitch", profile="glitch-agentdojo", repo="https://github.com/zanethomas1430-code/Glitch",
        commit="713bb2961fa16980ca8085d372adb200a66cad71", spdx="MIT", expected_files=2762, expected_bytes=25_994_554,
        licence_file="Glitch-MIT.txt", licence_marker="Zane Thomas",
        identity=(
            ("claude-haiku-4-5-glitch", (("pipeline_dir", "claude-haiku-4-5-glitch"),), "claude-haiku-4-5", ("glitch",)),
            ("gpt-4o-2024-05-13", (("pipeline_dir", "gpt-4o-2024-05-13"),), "gpt-4o-2024-05-13", ()),
        ),
        synthetic_path="17_agentdojo/runs/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-2024-05-13-glitch", bench_versions=("v1",),
        denial={"error": "DENIED by the gateway: out of scope: synthetic", "defence": "glitch"},
    ),
    Source(
        name="mohameduk", profile="mohameduk-agentdojo", repo="https://github.com/mohameduk/agentdojo",
        commit="3f9d69a1ea96b75e8695653ceee8c3ff088db9b3", spdx="MIT", expected_files=40492, expected_bytes=464_094_691,
        licence_file="mohameduk-agentdojo-MIT.txt", licence_marker="MIT License",
        identity=(
            ("gemini-2.5-flash-ubag_behavioral", (("pipeline_dir", "gemini-2.5-flash-ubag_behavioral"),), "gemini-2.5-flash",
             ("ubag_behavioral",)),
            ("gpt-4o-mini-2024-07-18-ubag", (("pipeline_dir", "gpt-4o-mini-2024-07-18-ubag"),), "gpt-4o-mini-2024-07-18", ("ubag",)),
            ("gemini-2.5-flash", (("pipeline_dir", "gemini-2.5-flash"),), "gemini-2.5-flash", ()),
        ),
        synthetic_path="runs/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-mini-2024-07-18-ubag", bench_versions=("v1", None),
        denial={"error": "ubag-blocked: REVIEW", "defence": "ubag"},
    ),
    Source(
        name="tacit", profile="tacit-agentdojo", version=2, repo="https://github.com/CSSLab/Tacit",
        commit="995692d3cd42c32e08cf0db8a5fae55fec272f1a", spdx="Apache-2.0", expected_files=2139, expected_bytes=None,
        licence_file="Tacit-Apache-2.0.txt", licence_marker="Apache License",
        identity=(
            ("local", (("model_dir", "llama3.1-8b-instruct"), ("pipeline_dir", "local")), "llama3.1-8b-instruct", ()),
            ("vllm_parsed", (("model_dir", "qwen3-4b-instruct"), ("pipeline_dir", "vllm_parsed")), "qwen3-4b-instruct", ()),
            ("local", (("model_dir", "llama3-70b"),), None, ()),  # a directory without a row resolves nothing
        ),
        synthetic_path="data/agentdojo/qwen3-4b-instruct/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="vllm_parsed", variants=("v1.k14", "v1.k14.incomplete"), bench_versions=("v1.2.2",),
    ),
    Source(
        name="geryon", profile="geryon-agentdojo", version=2, repo="https://github.com/luiacuaniello/geryon",
        commit="905aae02c4185454ffbdb64a8bae6a042f6d7047", spdx="Apache-2.0", expected_files=3313, expected_bytes=30_876_930,
        licence_file="Geryon-Apache-2.0.txt", licence_marker="Apache License",
        identity=(
            # D-104: the condition is a property of the log set; B = Progent on (docs/running-progent.md at the pin)
            ("openai.gpt-oss-120b", (("model_dir", "runs-full-set/logs-banking-B-r1"),), "openai.gpt-oss-120b", ("progent",)),
            ("openai.gpt-oss-120b", (("model_dir", "runs-full-set/logs-banking-A-r1"),), "openai.gpt-oss-120b", ()),
            ("qwen.qwen3-235b-a22b-2507", (("model_dir", "runs-strong-agent/logs-banking-A-r2"),), "qwen.qwen3-235b-a22b-2507", ()),
            ("openai.gpt-oss-120b", (("model_dir", "runs-full-set/logs-banking-C-r1"),), None, ()),  # no condition-C log set
        ),
        synthetic_path="results/runs-full-set/logs-banking-B-r2/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="openai.gpt-oss-120b", variants=("v0.k11",), bench_versions=(),
        denial={"error": "ValidationError: The tool 'send_money' is not allowed.. Please try other tools or arguments and "
                         "continue to finish the user task: Pay the bill.", "defence": "progent"},
    ),
    Source(
        name="hilarytorn", profile="hilarytorn-trajectory-poisoning",
        repo="https://github.com/HilaryTorn/in-context-trajectory-poisoning", commit="d71ab8bc2aa9db35ff443cc81e475e70ee8da215",
        spdx="MIT", expected_files=1294, expected_bytes=None, licence_file="HilaryTorn-MIT.txt", licence_marker="Hilary Torn",
        identity=(("gpt-4o-2024-05-13", (("pipeline_dir", "gpt-4o-2024-05-13"), ("arm", "e2e/tap")), "gpt-4o-2024-05-13", ()),),
        synthetic_path="data/traces/e2e/tap/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-2024-05-13", bench_versions=("v1.2.1",),
    ),
    Source(
        name="yockcheng", profile="yockcheng-prompt-injection-harness",
        repo="https://github.com/yockcheng/prompt-injection-harness", commit="5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6",
        spdx="Apache-2.0", expected_files=358, expected_bytes=None, licence_file="yockcheng-Apache-2.0.txt",
        licence_marker="Apache License",
        identity=(("claude-haiku-4-5-20251001", (("pipeline_dir", "claude-haiku-4-5-20251001"), ("tree", "agentdojo-native")),
                   "claude-haiku-4-5-20251001", ()),
                  ("claude-sonnet-4-5", (("pipeline_dir", "claude-sonnet-4-5"),), "claude-sonnet-4-5", ())),
        synthetic_path="runs/agentdojo-native/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="claude-haiku-4-5-20251001", variants=("v1.k14", "v1.k14.incomplete"), bench_versions=("v1", "v1.2.2"),
    ),
    Source(
        name="shreeyavarma", profile="shreeyavarma-llm-safety", repo="https://github.com/ShreeyaVarma/llm_safety",
        commit="78d22e4a3daa5e76c77b75076c30ceb1faab22c1", spdx="MIT", expected_files=28307, expected_bytes=None,
        licence_file="shreeyavarma-llm-safety-MIT.txt", licence_marker="MIT License",
        identity=(
            ("gpt-4o-2024-05-13", (("pipeline_dir", "gpt-4o-2024-05-13"),), "gpt-4o-2024-05-13", ()),
            ("local", (("pipeline_dir", "local"),), None, ()),  # D-92: a local client that logs no model
            ("Local model", (("pipeline_dir", "Local model"),), None, ()),
        ),
        synthetic_path="my_runs_conda_with_attack/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-2024-05-13", variants=("v1.k14", "v1.k14.incomplete"), bench_versions=("v1.2.1",),
        unresolved=("/local/", "/Local model/"),
    ),
    Source(
        name="kongminos", profile="kongminos-agentdojo", version=2, repo="https://github.com/kongminOS/jspace-agentdojo-950",
        commit="f341af69498ee36a8d1a2e69040ab70bd8e20a01", spdx="MIT", expected_files=957, expected_bytes=None,
        licence_file="kongminOS-MIT.txt", licence_marker="kongminOS",
        identity=(("local", (("pipeline_dir", "local"),), "deepseek-v4-flash", ()),),  # D-92: the README's statement, class I
        synthetic_path="data/ad_full_attack/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="local", bench_versions=("v1.2.2",),
    ),
    Source(
        name="ceferisbarov", profile="ceferisbarov-agentdojo", repo="https://github.com/ceferisbarov/agentdojo",
        commit="2273e1cd42493398d1581121c4c4439a8ecc072a", spdx="MIT", expected_files=55302, expected_bytes=615_555_549,
        licence_file="ceferisbarov-agentdojo-MIT.txt", licence_marker="MIT License",
        identity=(
            ("google_gemini-2.5-pro", (("pipeline_dir", "google_gemini-2.5-pro"),), "google_gemini-2.5-pro", ()),
            ("gpt-4o-2024-05-13", (("pipeline_dir", "gpt-4o-2024-05-13"), ("arm", "llama_k_1_6")), "gpt-4o-2024-05-13", ()),
        ),
        synthetic_path="reruns/optim_str/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-2024-05-13", variants=("v1.k14", "v1.k14.incomplete"), bench_versions=("v1.2.1",),
    ),
    Source(
        name="linyxus", profile="linyxus-agentdojo", repo="https://github.com/Linyxus/agentdojo",
        commit="698d7ff29cac4bb5dccb5ed2d06f5e8364547a97", spdx="MIT", expected_files=17656, expected_bytes=196_887_263,
        licence_file="linyxus-agentdojo-MIT.txt", licence_marker="MIT License",
        identity=(
            ("openrouter/openai/o4-mini-high-tacit", (("pipeline_dir", "openrouter_openai_o4-mini-high-tacit"),),
             "openai/o4-mini-high", ("tacit",)),
            ("openrouter_google_gemini-2.5-pro", (("pipeline_dir", "openrouter_google_gemini-2.5-pro"),), "google/gemini-2.5-pro", ()),
        ),
        synthetic_path="runs-4/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="openrouter/openai/o4-mini-high-tacit", variants=("v1.k14", "v1.k14.incomplete"),
        bench_versions=("v1.2.2",), notes={"pipeline_dir": "openrouter_openai_o4-mini-high-tacit"},
    ),
    Source(
        name="craibench", profile="craibench-agentdojo", repo="https://github.com/AthaSSiN/CrAIBench",
        commit="e41eac1eb2fea00a31c69827bfe83f9722a25702", spdx="MIT", expected_files=1344, expected_bytes=None,
        licence_file="CrAIBench-MIT.txt", licence_marker="MIT License",
        identity=(
            ("gpt-4o-spotlighting_with_delimiting", (("pipeline_dir", "gpt-4o-spotlighting_with_delimiting"),), "gpt-4o",
             ("spotlighting_with_delimiting",)),
            ("gpt-4o-spotlighting_with_datamarking", (("pipeline_dir", "gpt-4o-spotlighting_with_datamarking"),), "gpt-4o",
             ("spotlighting_with_datamarking",)),
        ),
        synthetic_path="runs/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-mini-2024-07-18-spotlighting_with_delimiting", variants=("v0.k11",),
    ),
    Source(
        name="menelaus29", profile="menelaus29-ipi-multidomain", repo="https://github.com/Menelaus29/ipi-multidomain-agent-study",
        commit="ec9c9287889ebec339c4304f01a4a4a99500c491", spdx="MIT", expected_files=1028, expected_bytes=None,
        licence_file="Menelaus29-MIT.txt", licence_marker="Khue Vu",
        identity=(
            # D-104: the defence is a property of the experiment path (the pipeline directory is the same)
            ("google-gemma-4-26b-a4b-it [gemini-2.5-flash-preview-04-17]", (("model_dir", "data/defended/g4/v1/fresh160/r/banking"),),
             "google-gemma-4-26b-a4b-it", ("my_spotlighting",)),
            ("google-gemma-4-26b-a4b-it [gemini-2.5-flash-preview-04-17]", (("model_dir", "data/baseline_gemma4/r/banking"),),
             "google-gemma-4-26b-a4b-it", ()),
            ("gemini-2.5-flash-preview-04-17-g4-spotlighting_with_delimiting",
             (("model_dir", "data/defended/g4/v1/replication_dev/builtin/r/banking"),), "google-gemma-4-26b-a4b-it",
             ("spotlighting_with_delimiting",)),
        ),
        synthetic_path="data/baseline/raw/workspace/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="google-gemini-3.5-flash-lite [gemini-2.5-flash-preview-04-17]", variants=("v1.k14", "v1.k14.incomplete"),
        bench_versions=("v1.2.2",), unresolved=("docs/example_run_output.json",),
    ),
    # Copyleft sources (D-94): own corpora. Their real excerpts (licence class `restricted`, private repository only,
    # 2026-10-12) are replaced by synthetic fixtures at the same paths (D-943 P-1, D-945): no licence file.
    Source(
        name="gate", profile="gate-agentdojo", repo="https://github.com/dafarusd/gate",
        commit="925b99260beec53d94bd48b587b0bdc33614e3df", spdx="AGPL-3.0-only", expected_files=4155, expected_bytes=None,
        licence_file=None, licence_marker="",
        identity=(
            ("local-qwen3-coder-32k:latest-gate-gatellm", (("pipeline_dir", "local-qwen3-coder-32k:latest-gate-gatellm"),),
             "qwen3-coder-32k:latest", ("gate-gatellm",)),
            ("local-qwen3-next-80b-gate-off", (("pipeline_dir", "local-qwen3-next-80b-gate-off"),), "qwen3-next-80b", ()),
            ("local", (("pipeline_dir", "local"),), None, ()),  # D-92: names no model
        ),
        synthetic_path="results/p3-holdout/h01_base64/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="local-qwen3-coder-480b-a35b-instruct-turbo-gate-all", variants=("v1.k14", "v1.k14.incomplete"),
        denial={"error": "BLOCKED by security policy: egress_recipient (synthetic)", "defence": "gate-all",
                "content_equals_error": True},
        bench_versions=("v1.2", "v1.2.2"),
    ),
    Source(
        name="sentry", profile="sentry-agentdojo",
        repo="https://github.com/vinhqdang/SENTRY-Anytime-Valid-E-Process-Monitoring-of-LLM-Agent-Action-Streams",
        commit="938e8be757f4d8168bc7ee5b23f767e431df873f", spdx="AGPL-3.0-only", expected_files=782, expected_bytes=None,
        licence_file=None, licence_marker="",
        identity=(
            ("gpt-4o-mini-local", (("pipeline_dir", "gpt-4o-mini-local"),), "gpt-4o-mini", ()),
            ("openrouter-free-router-local", (("pipeline_dir", "openrouter-free-router-local"),), None, ()),  # D-92
        ),
        synthetic_path="real_data/agentdojo/logs_gpt4omini/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-4o-mini-local", variants=("v1.k14", "v1.k14.incomplete"), bench_versions=(None,),
        unresolved=("/openrouter-free-router-local/",),
    ),
    Source(
        name="bookkeeper", profile="bookkeeper-agentdojo", repo="https://github.com/sricursion/bookkeeper",
        commit="0fe09bb6e8c0c864cee5daa9451f2647c2c846be", spdx="GPL-3.0-or-later", expected_files=1020, expected_bytes=5_937_000,
        licence_file=None, licence_marker="",
        identity=(
            ("gpt-oss-120b-munim-cap2-g2", (("pipeline_dir", "gpt-oss-120b-munim-cap2-g2"),), "gpt-oss-120b", ("munim-cap2-g2",)),
            ("glm-5.3-flash-none-g4", (("pipeline_dir", "glm-5.3-flash-none-g4"),), "glm-5.3-flash", ()),
        ),
        synthetic_path="runs/agentdojo/munim/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gpt-oss-120b-munim-cap2-g2", variants=("v1.k14", "v1.k14.incomplete"), bench_versions=(None,),
        denial={"error": "Declined by the account's money gate. HELD: synthetic", "defence": "munim-cap2-g2"},
    ),
    Source(
        name="aiauthz", profile="aiauthz-agentdojo", repo="https://github.com/Sports-Vision-Inc/aiAuthZ",
        commit="6eaac86ae5bfd8bf7b8a65786a5c77a7c0bce673", spdx="AGPL-3.0-only", expected_files=288, expected_bytes=None,
        licence_file=None, licence_marker="",
        identity=(
            # the logged name is a registry tag (config_tag_never_model): the model is the OpenRouter id of the directory
            ("gemini-2.0-flash-001-spotlighting_with_delimiting",
             (("model_dir", "google_gemini-3-flash-preview/spotlighting_clean"),), "google/gemini-3-flash-preview",
             ("spotlighting_with_delimiting",)),
            ("claude-3-5-sonnet-20241022-aiauthz", (("model_dir", "anthropic_claude-fable-5/aiauthz"),), "anthropic/claude-fable-5",
             ("aiauthz",)),
            ("claude-3-5-sonnet-20241022", (("model_dir", "anthropic_claude-fable-5/no_defense"),), "anthropic/claude-fable-5", ()),
        ),
        synthetic_path="experiments/agentdojo/runs/google_gemini-3-flash-preview/spotlighting/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="gemini-2.0-flash-001-spotlighting_with_delimiting", bench_versions=("v1.2.2",),
        denial={"error": "Blocked by aiAuthZ policy: action 'send_money' is not authorised", "defence": "aiauthz",
                "path": "experiments/agentdojo/runs/google_gemini-3-flash-preview/aiauthz/{pipeline_dir}/{suite}/{task}/"
                        "{attack}/{file}.json", "pipeline": "gemini-2.0-flash-001-aiauthz"},
    ),
    Source(
        name="llm-lock", profile="llm-lock-agentdojo", repo="https://github.com/Wakeful-Cloud/llm-lock",
        commit="7bb9915b57e087536b6bdeae0066adb0d8999958", spdx="GPL-3.0", expected_files=70075, expected_bytes=None,
        licence_file=None, licence_marker="",
        identity=(
            # R4: a row names the arm's defence and no model (D-92); the logged name is a constant, never compared
            ("local", (("model_dir", "none"),), None, ()),
            ("local", (("model_dir", "llm"),), None, ("llm",)),
            ("local", (("model_dir", "data-delimiter"),), None, ("spotlighting_with_delimiting",)),  # D-114
            ("transformer", (("model_dir", "transformer/protectai-deberta-v3-base-prompt-injection-v2"),), None,
             ("transformer-protectai-deberta-v3-base-prompt-injection-v2",)),
            ("local", (("model_dir", "hybrid/qualifire-prompt-injection-jailbreak-sentinel-v2"),), None,
             ("hybrid-qualifire-prompt-injection-jailbreak-sentinel-v2",)),
            ("local", (("model_dir", "an-unknown-arm"),), None, ()),
        ),
        synthetic_path="data/agentdojo/llm/logs/{pipeline_dir}/{suite}/{task}/{attack}/{file}.json",
        synthetic_pipeline="local", bench_versions=("v1.2.2",), unresolved=("data/agentdojo/",),
        # GPL-3.0: three synthetic fixtures (D-945) in place of the restricted ones of 2026-10-12
    ),
)

BY_NAME = {s.name: s for s in SOURCES}


def fixture_entries(src: Source) -> list[dict[str, Any]]:
    root = FIXTURES / src.name
    if not src.fixtures or not (root / "SOURCE.json").is_file():
        pytest.skip(f"no real fixtures for {src.name}")
    return list(json.loads((root / "SOURCE.json").read_bytes()))


def is_synthetic(entry: dict[str, Any]) -> bool:
    return entry.get("synthetic") is True


def layout_path(entry: dict[str, Any]) -> str:
    """The path the log is mapped at: the pinned path of a real fixture; for a synthetic one its path in the layout."""
    return str(entry["sample_file"] if is_synthetic(entry) else entry["original_path"])


def fixture_bytes(src: Source, entry: dict[str, Any]) -> bytes:
    """The fixture's bytes after the digest check; a synthetic template is assembled (placeholders filled, K.4.1(3))."""
    raw = (FIXTURES / src.name / entry["sample_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and golden.git_blob_sha1(raw) == entry["git_blob_sha1"]
    return phase10d_synthetic.assemble(raw) if is_synthetic(entry) else raw


_MAPPED: dict[tuple[str, ...], Mapped] = {}


def map_fixture(src: Source, entry: dict[str, Any]) -> Mapped:
    """The fixture mapped under its source profile, once per process for the same fixture and profile bytes: several
    tests read the same mappings (``Mapped.data`` is bytes and ``records`` re-parses fresh dicts on each access)."""
    profile = load_profile(src.profile)
    path = layout_path(entry)
    key = (src.name, src.repo, src.commit, entry["sample_file"], path, entry["sha256"], entry["git_blob_sha1"],
           profile.sha256)
    if key not in _MAPPED:
        raw = fixture_bytes(src, entry)
        # a synthetic log gets the origin map_doc gives every synthetic log of this module (its own blob id)
        blob = golden.git_blob_sha1(raw) if is_synthetic(entry) else entry["git_blob_sha1"]
        origin = Origin.git(src.repo, src.commit, path, blob)
        _MAPPED[key] = map_bytes(raw, path, profile=profile, origin=origin)
    cached = _MAPPED[key]
    # each caller gets its own copy (the profile, the loader's shared object, stays shared): no test can change what
    # another one reads
    return copy.deepcopy(cached, {id(cached.profile): cached.profile})


def map_doc(src: Source, doc: dict[str, Any], path: str) -> Mapped:
    raw = json.dumps(doc, indent=4).encode("utf-8")
    origin = Origin.git(src.repo, src.commit, path, golden.git_blob_sha1(raw))
    return map_bytes(raw, path, profile=load_profile(src.profile), origin=origin)


def synthetic_path(src: Source, doc: dict[str, Any]) -> str:
    directory = src.notes.get("pipeline_dir", src.synthetic_pipeline)  # the directory when it is not the logged name
    return src.synthetic_path.format(pipeline_dir=directory, suite=doc["suite_name"], task=doc["user_task_id"],
                                     attack=doc.get("attack_type") or "none", file=doc.get("injection_task_id") or "none")


def ok(m: Mapped) -> None:
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]


def _rule_id(ref: str) -> str:
    return ref.split("#", 1)[0]


def d_rules_cited_at_d(m: Mapped) -> list[str]:
    """Family D rules a record cites directly (D.5.4, D-24): with no verified code, every one must be a twin, unless the
    family lists it as independent of the producing code."""
    out: list[str] = []
    for record in m.records:
        for ref in record.get("rule", ()) or ():
            rid = _rule_id(str(ref))
            namespace = rid.split(".", 1)[0]
            if namespace not in citation.NAMESPACES or rid in citation.INDEPENDENT:
                continue
            entry = load_catalogue(namespace).get(rid)
            if entry is not None and entry.cls == "D":
                out.append(rid)
    return sorted(set(out))


def twins_cited(m: Mapped) -> set[str]:
    return {_rule_id(str(ref)) for r in m.records for ref in (r.get("rule", ()) or ())
            if TWIN_SUFFIX + "@" in _rule_id(str(ref))}
