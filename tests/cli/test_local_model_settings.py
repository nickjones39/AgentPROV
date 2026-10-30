"""A local model's facts as settings (D-828): ``local_models.<endpoint>.<model id>.<field>``, used by ``run`` when the
flag is not given (flag > setting > the model's folder > the preset), GGUF weight sizes, and the folder search behind
the GUI's Find Folder (``agentprov models --find-folders``).

Temporary trees stand in for oMLX's, the Hugging Face cache's and LM Studio's folders; no server and no model.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentprov import presets
from agentprov import settings as st
from agentprov.cli.live import localmodels as lm

ALIAS = "DeepSeek-V4.1-Flash-1017-Abliterated-MLX:128k"


# ---- the settings keys ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [ALIAS, "mlx-community/Qwen3-8B-4bit", "qwen3:8b", "incoai--Qwen3.8-Flash-Next"])
def test_model_ids_with_dots_colons_and_slashes_are_keys(model: str, tmp_path: Path) -> None:
    st.set(st.local_model_key("omlx", model, "active_params_b"), "13", home=tmp_path)
    st.set(st.local_model_key("omlx", model, "context_tokens"), "32768", home=tmp_path)
    assert st.local_model("omlx", model, home=tmp_path) == {"active_params_b": 13.0, "context_tokens": 32768}


@pytest.mark.parametrize("key", ["local_models.omlx..x.model_dir", "local_models.omlx.../etc.model_dir",
                                 "local_models.omlx.m.weights", "local_models.OMLX.m.model_dir",
                                 "local_models.omlx.a b.model_dir"])
def test_keys_outside_the_schema_are_refused(key: str, tmp_path: Path) -> None:
    with pytest.raises(st.SettingsError):
        st.set(key, "1", home=tmp_path)


def test_values_are_checked(tmp_path: Path) -> None:
    with pytest.raises(st.SettingsError):
        st.set("local_models.omlx.m.model_dir", "relative/path", home=tmp_path)
    with pytest.raises(st.SettingsError):
        st.set("local_models.omlx.m.active_params_b", "0", home=tmp_path)
    with pytest.raises(st.SettingsError):
        st.set("local_models.omlx.m.context_tokens", "1.5", home=tmp_path)


def test_one_models_facts_never_include_another_with_a_longer_id(tmp_path: Path) -> None:
    st.set("local_models.omlx.a.active_params_b", 1, home=tmp_path)
    st.set("local_models.omlx.a.b.active_params_b", 2, home=tmp_path)
    assert st.local_model("omlx", "a", home=tmp_path) == {"active_params_b": 1.0}
    assert st.local_model("omlx", "a.b", home=tmp_path) == {"active_params_b": 2.0}
    assert st.local_model("omlx", "../x", home=tmp_path) == {}


# ---- GGUF weight sizes ---------------------------------------------------------------------------------------


def _model(root: Path, files: dict[str, int], *, config: bool = True) -> Path:
    root.mkdir(parents=True)
    if config:
        (root / "config.json").write_text(json.dumps({"num_hidden_layers": 2, "num_attention_heads": 2,
                                                      "num_key_value_heads": 1, "head_dim": 8}))
    for name, size in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"w" * size)
    return root


def test_gguf_shards_count_when_there_are_no_safetensors(tmp_path: Path) -> None:
    top = presets.model_facts_from_dir(str(_model(tmp_path / "a", {"m-00001-of-00002.gguf": 30,
                                                                   "m-00002-of-00002.gguf": 12})))
    assert (top.weights_bytes.value, top.weights_bytes.note) == (42, "sum of 2 *.gguf sizes (stat)")
    shards = _model(tmp_path / "shards", {"x.gguf": 7})
    omlx = _model(tmp_path / "omlx", {})
    (omlx / "split").mkdir()
    os.symlink(shards / "x.gguf", omlx / "split" / "x.gguf")  # oMLX's layout: links in split/
    split = presets.model_facts_from_dir(str(omlx))
    assert split.weights_bytes.value == 7 and split.weights_bytes.note.startswith("sum of 1 split/*.gguf sizes")
    both = presets.model_facts_from_dir(str(_model(tmp_path / "b", {"m.safetensors": 5, "m.gguf": 9})))
    assert both.weights_bytes.value == 5  # safetensors first, never both
    none = presets.model_facts_from_dir(str(_model(tmp_path / "c", {})))
    assert none.weights_bytes.value is None


# ---- precedence in run's preset dry run ------------------------------------------------------------------------


def test_flag_beats_setting_beats_folder(cli: Callable[..., Any], tmp_path: Path) -> None:
    home = Path(os.environ["AGENTPROV_HOME"])
    folder = _model(tmp_path / "m", {"model.safetensors": 2_000_000_000})
    st.set("local_models.omlx.m1.model_dir", str(folder), home=home)
    st.set("local_models.omlx.m1.active_params_b", 3, home=home)
    st.set("local_models.omlx.m1.model_size_gb", 5, home=home)
    base = ("run", "agentdojo", "--m5ultra", "--dry-run", "--model-id", "m1")
    def text(*extra: str) -> str:
        run = cli(*base, *extra)
        assert run.code == 0, run.err
        return run.out + run.err  # the plan lines go to the terminal's message stream

    by_setting = text()
    assert "source=settings  (local_models.omlx.m1.active_params_b)" in by_setting
    assert "source=settings  (local_models.omlx.m1.model_size_gb)" in by_setting
    assert "J_compute = 4" in by_setting  # 3 B active: the first row (m5ultra v2: 4 in every row)
    by_flag = text("--active-params-b", "50")
    assert "source=flag  (--active-params-b)" in by_flag and "J_compute = 4" in by_flag
    st.unset("local_models.omlx.m1.model_size_gb", home=home)
    assert "source=model_dir  (sum of 1 *.safetensors sizes (stat))" in text()
    other = cli("run", "agentdojo", "--m5ultra", "--dry-run", "--model-id", "other", "--model-size-gb", "4")
    assert other.code == 0 and "source=settings" not in other.out + other.err


def test_a_setting_folder_that_is_gone_names_the_key(cli: Callable[..., Any], tmp_path: Path) -> None:
    home = Path(os.environ["AGENTPROV_HOME"])
    st.set("local_models.omlx.m2.model_dir", str(tmp_path / "gone"), home=home)
    run = cli("run", "agentdojo", "--m5ultra", "--dry-run", "--model-id", "m2")
    assert run.code == 2 and "local_models.omlx.m2.model_dir is not a readable directory" in run.err


# ---- the folder search ---------------------------------------------------------------------------------------


@pytest.fixture
def roots(tmp_path: Path) -> dict[str, str]:
    omlx, hf, lms = tmp_path / "omlx", tmp_path / "hf", tmp_path / "lms"
    _model(omlx / "models" / "DeepSeek-V4.1-Flash-1017-Abliterated-MLX", {"model.safetensors": 1})
    _model(omlx / "models" / "mlx-community" / "Qwen-mtp", {"model.safetensors": 1})
    (omlx / "models" / "empty-name").mkdir(parents=True)  # no config or weights: never offered
    _model(omlx / "gguf" / "Qwen-UD-Q4_K_XL-145d7c29e7ac", {}, config=True)
    _model(omlx / "gguf" / "Qwen-UD-Q4_K_XL-other", {}, config=True)  # not a hex suffix
    commit = "a" * 40
    _model(hf / "models--incoai--Draft" / "snapshots" / commit, {"model.safetensors": 1})
    (hf / "models--incoai--Draft" / "refs").mkdir()
    (hf / "models--incoai--Draft" / "refs" / "main").write_text(commit)
    _model(lms / "lmstudio-community" / "Tiny-4bit", {"model.safetensors": 1})
    return {"OMLX_HOME": str(omlx), "HF_HUB_CACHE": str(hf), "LMSTUDIO_HOME": str(tmp_path / "lmshome"),
            "_LMS": str(lms)}


def _find(model: str, roots: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    monkeypatch.setattr(lm, "lmstudio_models_root", lambda env: Path(roots["_LMS"]))
    return [(Path(f["path"]).name, f["source"]) for f in lm.find_model_folders(model, environ=roots)]


def test_find_model_folders(roots: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    assert _find(ALIAS, roots, monkeypatch) == [("DeepSeek-V4.1-Flash-1017-Abliterated-MLX", "omlx")]
    assert _find("Qwen-mtp", roots, monkeypatch) == [("Qwen-mtp", "omlx")]
    assert _find("Qwen-UD-Q4_K_XL", roots, monkeypatch) == [("Qwen-UD-Q4_K_XL-145d7c29e7ac", "omlx_gguf")]
    assert _find("incoai--Draft", roots, monkeypatch) == [("a" * 40, "hf_cache")]
    assert _find("incoai/Draft", roots, monkeypatch) == [("a" * 40, "hf_cache")]
    assert _find("lmstudio-community/Tiny-4bit", roots, monkeypatch) == [("Tiny-4bit", "lmstudio")]
    assert _find("empty-name", roots, monkeypatch) == []
    for hostile in ("../models", "a/../../b", "..", "x\u202ey"):
        assert _find(hostile, roots, monkeypatch) == []


def test_models_find_folders_command(cli: Callable[..., Any], roots: dict[str, str],
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in roots.items():
        if not name.startswith("_"):
            monkeypatch.setenv(name, value)
    monkeypatch.setattr(lm, "lmstudio_models_root", lambda env: Path(roots["_LMS"]))
    run = cli("models", "--endpoint", "omlx", "--model-id", ALIAS, "--find-folders", "--format", "json")
    assert run.code == 0, run.err
    doc = run.json()
    assert doc["format"] == "agentprov-model-folders/0.1" and doc["setting"] is None
    assert [Path(f["path"]).name for f in doc["folders"]] == ["DeepSeek-V4.1-Flash-1017-Abliterated-MLX"]
    assert cli("models", "--find-folders").code == 2
    assert cli("models", "--endpoint", "omlx", "--model-id", "m", "--find-folders", "--keychain").code == 2
    assert cli("models", "--endpoint", "openai", "--model-id", "m", "--find-folders").code == 2
