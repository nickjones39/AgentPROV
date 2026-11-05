"""D-894: the tier-4 round-trip cache's size cap is the ``compute.validation_cache_gib`` setting when it is set."""

from __future__ import annotations

import sys

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentprov import settings
from agentprov.cli.checks import CACHE_CAP_SETTING, validation_cache
from agentprov.validate.cache import DEFAULT_MAX_BYTES

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the tier-4 round-trip cache is not used on Windows in 0.2.0")


def _ctx(home: Path, **args: object) -> SimpleNamespace:
    return SimpleNamespace(args=SimpleNamespace(**args), env={"AGENTPROV_HOME": str(home)})


def test_unset_keeps_the_caches_own_default(tmp_path: Path) -> None:
    cache = validation_cache(_ctx(tmp_path))
    assert cache.max_bytes == DEFAULT_MAX_BYTES and cache.root == tmp_path / "cache" / "tier4"


def test_the_setting_sets_the_cap_for_every_command_that_uses_the_cache(tmp_path: Path) -> None:
    settings.set(CACHE_CAP_SETTING, 32, home=tmp_path)
    assert validation_cache(_ctx(tmp_path)).max_bytes == 32 * 1024**3
    assert validation_cache(_ctx(tmp_path), audit=True).max_bytes == 32 * 1024**3
    assert validation_cache(_ctx(tmp_path, no_validation_cache=True)) is None


@pytest.mark.parametrize("value", [0, 0.5, 5000, "lots"])
def test_a_cap_out_of_range_is_refused(tmp_path: Path, value: object) -> None:
    with pytest.raises(settings.SettingsError):
        settings.set(CACHE_CAP_SETTING, value, home=tmp_path)


@pytest.mark.parametrize("text", [
    '{"format": "agentprov-settings/0.1", "values": {}, }',  # not strict JSON
    '{"format": "something-else", "values": {}}',  # not an agentprov-settings/0.1 document
])
def test_an_unreadable_settings_file_leaves_the_default_cap_with_a_notice(tmp_path: Path, text: str) -> None:
    """AU-CLIA-1: the cap is advisory (D-894), so a broken settings file never stops a corpus command (it was exit 2)."""
    (tmp_path / "settings.json").write_text(text + "\n", encoding="utf-8")
    notices: list[str] = []
    cache = validation_cache(_ctx(tmp_path), notices=notices)
    assert cache.max_bytes == DEFAULT_MAX_BYTES
    assert len(notices) == 1 and "left at its default" in notices[0] and CACHE_CAP_SETTING in notices[0]
    assert validation_cache(_ctx(tmp_path)).max_bytes == DEFAULT_MAX_BYTES  # no notices list: still no error
