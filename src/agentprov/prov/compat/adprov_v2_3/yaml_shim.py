"""The ``yaml`` seen by the oracle (glue; RESOLUTIONS R-31, AD-17; PORT_MANIFEST.json ``rewrites``).

The baseline's ``build_prov._decoded_forms`` does a function-local ``import yaml`` and calls ``yaml.safe_load(content)``
inside ``try ... except Exception``. The port rewrites that one import statement to
``from agentprov.prov.compat.adprov_v2_3 import yaml_shim as yaml``, so the call reaches this module and, through it,
:func:`agentprov.ingest.yamlsafe.safe_load` (the only PyYAML importer in the core; bounded, alias-free, pure-Python
``SafeLoader``). The oracle body is unchanged.

For a document that passes the guards the value is exactly that of ``yaml.safe_load``. The guards (aliases, duplicate keys,
depth, input above ``max_yaml_bytes``) raise instead; the oracle's ``except Exception`` turns that into "not YAML", the
same result as a syntax error. That changes no frozen byte: the fallback is reached on 7 outputs of the frozen corpora,
none with aliases or duplicate keys, all below 1 KiB (J.3.3, MR-3). The full-corpus gate re-checks it.
"""

from __future__ import annotations

from typing import Any

from agentprov.ingest import yamlsafe


def safe_load(stream: str | bytes) -> Any:
    """``yaml.safe_load`` over :func:`agentprov.ingest.yamlsafe.safe_load` with the default tier-1 limits."""
    return yamlsafe.safe_load(stream)
