"""Key/type skeleton of the envelope and of trace 0 of one document (keys and types only, no values; scalars of
enumerated fields are printed only for a fixed allowlist of label keys)."""
import os, sys
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
LAB = {"model", "defense", "mitigation_level", "env_type", "risk_mechanism", "outcome", "schema_version", "split",
       "finish_reason", "role", "server", "status"}
def sk(v, d=0, k=None):
    pad = "  " * d
    if isinstance(v, dict):
        for kk, vv in v.items():
            t = type(vv).__name__
            extra = f" = {vv!r}"[:60] if kk in LAB and isinstance(vv, (str, int, float, bool)) else ""
            print(f"{pad}{kk}: {t}{extra}")
            if isinstance(vv, dict) and d < 3: sk(vv, d + 1)
            if isinstance(vv, list) and vv and isinstance(vv[0], dict) and d < 3:
                print(f"{pad}  [0] of {len(vv)}:"); sk(vv[0], d + 2)
root = os.path.expanduser(sys.argv[1]); lab = sys.argv[2]
lim = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
with open(os.path.join(root, lab), "rb") as f:
    s = open_json_stream(f, lim, arrays=("/traces",))
    print("ENVELOPE"); sk(s.envelope)
    for it in s:
        print("TRACE0"); sk(it.value); break
