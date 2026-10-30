"""A stub local model server on an ephemeral loopback port, for discovery tests without a real model (D-691).

``StubServer(kind)`` serves synthetic responses in the shape of each server kind's read-only routes (``/v1/models`` and
the kind's own routes: Ollama ``/api/version``, ``/api/tags``, ``/api/show``; LM Studio ``/api/v1/models``; llama.cpp
``/props``; vLLM ``/version``). The bodies are made up here, not copied from any server; tests override any route with
``set(path, status, body)``. Nothing here runs inference. Use it as a context manager::

    with StubServer("lmstudio", models=[...]) as srv:
        srv.base_url  # http://127.0.0.1:<port>/v1
"""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["StubServer", "default_models"]


def default_models(kind: str) -> list[dict[str, Any]]:
    """Two synthetic models per kind (ids only matter to the tests)."""
    if kind == "ollama":
        return [
            {"name": "tiny-llm:1b", "model": "tiny-llm:1b", "size": 1_000_000_000, "digest": "a" * 64,
             "details": {"format": "gguf", "family": "tinyllm", "families": ["tinyllm"], "parameter_size": "1.0B",
                         "quantization_level": "Q4_K_M"}},
            {"name": "big-llm:70b-cloud", "model": "big-llm:70b-cloud", "remote_host": "https://cloud.invalid:443",
             "remote_model": "big-llm:70b", "size": 400, "digest": "b" * 64, "details": {"family": "bigllm"}},
        ]
    if kind == "lmstudio":
        return [
            {"type": "llm", "publisher": "stub-pub", "key": "tiny-model-4bit", "display_name": "Tiny Model 4bit",
             "architecture": "tiny", "quantization": {"name": "4bit", "bits_per_weight": 4}, "size_bytes": 2050,
             "params_string": "1B", "format": "mlx", "max_context_length": 32768,
             "loaded_instances": [{"id": "tiny-model-4bit", "config": {"context_length": 8192, "parallel": 4}}],
             "capabilities": {"vision": False, "trained_for_tool_use": True}},
            {"type": "llm", "publisher": "stub-pub", "key": "plain-model", "display_name": "Plain", "format": "gguf",
             "quantization": {"name": "Q8_0", "bits_per_weight": 8}, "size_bytes": 3_000_000, "loaded_instances": [],
             "capabilities": {"vision": False, "trained_for_tool_use": False}},
            {"type": "embedding", "publisher": "stub-pub", "key": "embed-small", "size_bytes": 10, "loaded_instances": []},
        ]
    return [{"id": "stub-org/tiny-model-4bit"}, {"id": "stub-org/other-model"}]


class StubServer:
    def __init__(self, kind: str, *, models: Sequence[Mapping[str, Any]] | None = None, version: str = "0.0.1-stub",
                 show: Mapping[str, Any] | None = None, api_key: str | None = None) -> None:
        self.kind = kind
        #: with a key, every route answers 401 unless the request carries ``Authorization: Bearer <key>`` (D-827)
        self.api_key = api_key
        self.routes: dict[tuple[str, str], tuple[int, bytes]] = {}
        self.seen: list[dict[str, Any]] = []
        models = list(models if models is not None else default_models(kind))
        if kind == "ollama":
            ids = [m["name"] for m in models]
            self.set("/api/version", 200, {"version": version})
            self.set("/api/tags", 200, {"models": models})
            self.set("/api/show", 200, show if show is not None else {
                "template": "{{ .Prompt }}", "parameters": "stop <end>", "modelfile": "FROM tiny",
                "capabilities": ["completion", "tools"],
                "model_info": {"general.architecture": "tinyllm", "general.parameter_count": 1_000_000_000,
                               "tinyllm.context_length": 4096}}, method="POST")
        elif kind == "lmstudio":
            ids = [m["key"] for m in models]  # LM Studio's /v1/models lists embedding models too (0.4.23)
            self.set("/api/v1/models", 200, {"models": models})
            self.set("/lmstudio-greeting", 200, {"lmstudio": True})
        else:
            ids = [m["id"] for m in models]
            if kind == "llamacpp":
                self.set("/props", 200, {"total_slots": 2, "model_path": "/models/tiny-model-4bit.gguf",
                                         "chat_template": "{{ messages }}", "build_info": "b0000-stub",
                                         "default_generation_settings": {}})
            elif kind == "vllm":
                self.set("/version", 200, {"version": version})
        owner = "vllm" if kind == "vllm" else "stub"
        if kind in ("ollama", "lmstudio"):
            data = [{"id": i, "object": "model", "owned_by": owner} for i in ids]
        else:
            data = [{"object": "model", "owned_by": owner, **m} for m in models]
        self.set("/v1/models", 200, {"object": "list", "data": data})
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def set(self, path: str, status: int, body: Any, *, method: str = "GET") -> None:
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.routes[(method, path)] = (status, raw)

    def drop(self, path: str, *, method: str = "GET") -> None:
        self.routes.pop((method, path), None)

    @property
    def port(self) -> int:
        assert self._httpd is not None
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def __enter__(self) -> StubServer:
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                stub.seen.append({"method": method, "path": self.path, "body": body,
                                  "headers": {k.lower(): v for k, v in self.headers.items()}})
                # LM Studio answers an unknown route with HTTP 200 and an error object (observed on 0.4.23)
                missing = (200, b'{"error":"Unexpected endpoint or method."}') if stub.kind == "lmstudio" else \
                    (404, b'{"error":"not found"}')
                status, raw = stub.routes.get((method, self.path), missing)
                if stub.api_key is not None and self.headers.get("Authorization") != f"Bearer {stub.api_key}":
                    status, raw = 401, b'{"error":{"message":"Invalid API key","type":"authentication_error"}}'
                self.send_response(status)
                if 300 <= status < 400:
                    self.send_header("Location", "http://192.0.2.1/v1/models")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                self._answer("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._answer("POST")

            def log_message(self, *args: object) -> None:
                pass

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
