"""D-894: the tier-4 round-trip cache's size cap is the ``compute.validation_cache_gib`` setting when it is set."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentprov import settings
from agentprov.cli.checks import CACHE_CAP_SETTING, validation_cache
from agentprov.validate.cache import DEFAULT_MAX_BYTES


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
