"""Which httpx-family module the installed OpenAI SDK sends with.

The locked SDK (``openai`` 3.26.0 in ``backends/agentdojo/uv.lock``) builds its clients on ``httpx2`` (``openai/
_base_client.py`` imports ``httpx2``), not on ``httpx``; it still accepts a legacy ``httpx.Client`` through a
compatibility path. The recording and scripted transports must be transports of the module the SDK's default client
uses, so that the stock element runs on its normal code path (D.10.10 item 2). ``httpx2`` is a dependency of
``openai``; older SDKs (``openai`` 1.x, e.g. in a fork's environment) use ``httpx``.

The ``anthropic`` SDK (1.11.0 in both backend locks, a dependency of ``agentdojo==0.1.35``) is built on ``httpx2`` too;
:func:`anthropic_httpx` names its module the same way, importing the SDK only when called (D-656: the shared package
never requires it).
"""

from __future__ import annotations

import importlib
from types import ModuleType

__all__ = ["anthropic_httpx", "sdk_httpx"]

_cached: ModuleType | None = None
_cached_anthropic: ModuleType | None = None


def sdk_httpx() -> ModuleType:
    """The ``httpx2`` or ``httpx`` module the installed ``openai`` SDK's ``_base_client`` imports."""
    global _cached
    if _cached is not None:
        return _cached
    module: ModuleType | None = None
    try:
        base = importlib.import_module("openai._base_client")
        module = getattr(base, "httpx2", None) or getattr(base, "httpx", None)
    except ImportError:
        module = None
    if module is None:
        module = importlib.import_module("httpx")
    _cached = module
    return module


def anthropic_httpx() -> ModuleType:
    """The ``httpx2`` or ``httpx`` module the installed ``anthropic`` SDK's ``_base_client`` imports (``ImportError``
    when the SDK is not installed)."""
    global _cached_anthropic
    if _cached_anthropic is not None:
        return _cached_anthropic
    base = importlib.import_module("anthropic._base_client")
    module = getattr(base, "httpx2", None) or getattr(base, "httpx", None)
    if module is None:  # pragma: no cover - every supported SDK has one
        raise ImportError("the anthropic SDK names no httpx-family module")
    _cached_anthropic = module
    return module
