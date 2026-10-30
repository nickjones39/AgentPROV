"""``worker.main(worker_cls=...)``: a backend package's own Worker subclass serves the protocol (D-662)."""

import json
import subprocess
import sys

SCRIPT = """
import sys
from agentprov_backend import worker

class Sub(worker.Worker):
    def op_hello(self, msg):
        self.send("hello_ok", nonce=msg["nonce"], identity={}, worker={"backend": "sub"})

sys.exit(worker.main(worker_cls=Sub))
"""


def test_main_serves_through_a_worker_subclass():
    lines = (json.dumps({"v": "agentprov-backend/0.1", "op": "hello", "nonce": "n1"}) + "\n"
             + json.dumps({"v": "agentprov-backend/0.1", "op": "shutdown"}) + "\n")
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", SCRIPT], input=lines.encode(), capture_output=True,
                          timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    (reply,) = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert reply["op"] == "hello_ok" and reply["nonce"] == "n1" and reply["worker"] == {"backend": "sub"}
