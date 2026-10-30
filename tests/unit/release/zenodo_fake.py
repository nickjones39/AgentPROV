"""A fake Zenodo on 127.0.0.1 for ``tools/zenodo_draft.py`` (``test_zenodo_draft``; not collected).

Only the allowlisted requests are served. Any other request, a publish above all, is recorded in ``violations`` (and
answered 405): the test fixture fails the test on any violation. The server checks the bearer token, keeps every request's
method and path (never its body, apart from JSON metadata), and can be told to misbehave: a wrong md5 for one file, a
server error after N uploads, a redirect, a bucket link on another host, a token echoed into an error message, a published
deposition with inherited files for ``newversion``, a draft with no reserved DOI until ``prereserve_doi: true`` is sent, a
reserved DOI that changes, a reserved DOI that never comes.

Reserved DOIs (D-870): by default a draft has one from its creation, as the sandbox's drafts did (trial of 2026-10-23,
which never sent ``prereserve_doi``). ``reserve_on_create = False`` reserves one only on a metadata ``PUT`` that holds
``prereserve_doi: true``; a second such request on a draft that has one keeps it (the documentation: the DOI "cannot be
changed"). ``prereserve_requests`` counts those requests; ``prereserve_doi`` is never stored as metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


#: Licence ids the real sandbox stored differently from what the deposit API was sent (observed 2026-10-23).
LICENCE_READBACK = {"mit": "mit-license"}


class FakeZenodo:
    def __init__(self, token: str) -> None:
        self.token = token
        self.depositions: dict[int, dict[str, Any]] = {}
        self.buckets: dict[str, int] = {}
        self.requests: list[tuple[str, str]] = []
        self.violations: list[str] = []
        self.metadata_bodies: list[dict[str, Any]] = []
        self.md5_override: dict[str, str] = {}
        self.fail_put_after: int | None = None
        self.redirect_create = False
        self.foreign_bucket = False
        self.echo_token_on_metadata = False
        self.reserve_on_create = True
        self.never_reserve = False
        self.prereserve_requests = 0
        self._puts = 0
        self._next = 1000
        self._lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    # ------------------------------------------------------------------------------------------ lifecycle
    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self) -> FakeZenodo:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    # ------------------------------------------------------------------------------------------ seeds
    def add_published(self, *, concept_doi: str, concept_recid: str, files: dict[str, bytes] | None = None) -> int:
        """A published deposition (the latest version of a concept) that ``newversion`` can be asked of."""
        with self._lock:
            self._next += 1
            dep_id = self._next
            self.depositions[dep_id] = self._new(dep_id, submitted=True)
            self.depositions[dep_id].update({"conceptdoi": concept_doi, "conceptrecid": concept_recid, "state": "done"})
            for name, data in (files or {}).items():
                self.depositions[dep_id]["files"][name] = {"size": len(data), "md5": hashlib.md5(data).hexdigest()}
            return dep_id

    def counts(self, method: str, prefix: str = "") -> int:
        return sum(1 for m, p in self.requests if m == method and p.startswith(prefix))

    # ------------------------------------------------------------------------------------------ internals
    def _new(self, dep_id: int, *, submitted: bool = False) -> dict[str, Any]:
        bucket = str(uuid.uuid4())
        self.buckets[bucket] = dep_id
        doi = f"10.5281/zenodo.{dep_id}" if self.reserve_on_create and not self.never_reserve else None
        return {"id": dep_id, "bucket": bucket, "submitted": submitted, "state": "unsubmitted", "files": {},
                "metadata": {}, "conceptdoi": None, "conceptrecid": str(dep_id), "doi": doi}

    def publish_for_test(self, dep_id: int) -> None:
        """Mark a deposition published, as if the user had pressed Publish (no request; the tool cannot do this)."""
        self.depositions[dep_id].update({"submitted": True, "state": "done"})

    def _view(self, dep: dict[str, Any]) -> dict[str, Any]:
        host = self.base
        bucket_host = "https://evil.example" if self.foreign_bucket else host
        # as the sandbox answered (trial of 2026-10-23): a draft has no ``conceptdoi`` key, only ``conceptrecid``; the
        # licence reads back under Zenodo's own id (``mit`` is stored as ``mit-license``); a DOI is reserved, not registered
        stored = dict(dep["metadata"])
        if "license" in stored:
            stored["license"] = LICENCE_READBACK.get(stored["license"], stored["license"])
        return {
            "id": dep["id"], "submitted": dep["submitted"], "state": dep["state"],
            **({"conceptdoi": dep["conceptdoi"]} if dep["conceptdoi"] else {}),
            "metadata": {**stored, **({"prereserve_doi": {"doi": dep["doi"], "recid": dep["id"]}} if dep["doi"] else {})},
            "conceptrecid": dep["conceptrecid"],
            "links": {"bucket": f"{bucket_host}/api/files/{dep['bucket']}", "html": f"{host}/deposit/{dep['id']}",
                      "latest_draft": f"{host}/api/deposit/depositions/{dep['id']}"},
            "files": [{"id": str(uuid.uuid4()), "filename": n, "filesize": f["size"], "checksum": f["md5"]}
                      for n, f in dep["files"].items()],
        }

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _send(self, status: int, payload: Any = None, headers: dict[str, str] | None = None) -> None:
                body = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def _handle(self, method: str) -> None:
                path = self.path
                with fake._lock:
                    fake.requests.append((method, path))
                body = self._body()
                if self.headers.get("Authorization") != f"Bearer {fake.token}":
                    self._send(401, {"message": "bad token", "status": 401})
                    return
                if fake.token in path:
                    fake.violations.append(f"token in the URL: {method}")
                if "publish" in path or "discard" in path or "/actions/edit" in path or method == "DELETE":
                    fake.violations.append(f"forbidden request: {method} {path}")
                    self._send(405, {"message": "not allowed", "status": 405})
                    return
                with fake._lock:
                    self._route(method, path, body)

            def _route(self, method: str, path: str, body: bytes) -> None:
                if (method, path) == ("POST", "/api/deposit/depositions"):
                    if fake.redirect_create:
                        self._send(302, None, {"Location": "https://evil.example/"})
                        return
                    fake._next += 1
                    fake.depositions[fake._next] = fake._new(fake._next)
                    self._send(201, fake._view(fake.depositions[fake._next]))
                    return
                m = re.fullmatch(r"/api/deposit/depositions/(\d+)(/files|/actions/newversion)?", path)
                if m and int(m.group(1)) in fake.depositions:
                    dep = fake.depositions[int(m.group(1))]
                    if (method, m.group(2)) == ("GET", None):
                        self._send(200, fake._view(dep))
                    elif (method, m.group(2)) == ("PUT", None):
                        doc = json.loads(body)
                        fake.metadata_bodies.append(doc)
                        if fake.echo_token_on_metadata:
                            self._send(400, {"message": f"bad metadata, your header was Bearer {fake.token}", "status": 400})
                            return
                        metadata = dict(doc["metadata"])
                        if metadata.pop("prereserve_doi", None) is True:
                            fake.prereserve_requests += 1
                            if dep["doi"] is None and not fake.never_reserve:
                                dep["doi"] = f"10.5281/zenodo.{dep['id']}"
                        dep["metadata"] = metadata
                        self._send(200, fake._view(dep))
                    elif (method, m.group(2)) == ("GET", "/files"):
                        self._send(200, fake._view(dep)["files"])
                    elif (method, m.group(2)) == ("POST", "/actions/newversion") and dep["submitted"]:
                        fake._next += 1
                        draft = fake._new(fake._next)
                        draft["files"] = {n: dict(f) for n, f in dep["files"].items()}  # the inherited snapshot
                        draft["conceptdoi"], draft["conceptrecid"] = dep["conceptdoi"], dep["conceptrecid"]
                        fake.depositions[fake._next] = draft
                        original = fake._view(dep)
                        original["links"]["latest_draft"] = f"{fake.base}/api/deposit/depositions/{draft['id']}"
                        self._send(201, original)
                    else:
                        fake.violations.append(f"unserved: {method} {path}")
                        self._send(405, {"message": "not served", "status": 405})
                    return
                m = re.fullmatch(r"/api/files/([0-9a-f-]{36})/([A-Za-z0-9][A-Za-z0-9._-]*)", path)
                if method == "PUT" and m and m.group(1) in fake.buckets:
                    fake._puts += 1
                    if fake.fail_put_after is not None and fake._puts > fake.fail_put_after:
                        self._send(500, {"message": "storage hiccup", "status": 500})
                        return
                    name = m.group(2)
                    md5 = fake.md5_override.get(name) or hashlib.md5(body).hexdigest()
                    fake.depositions[fake.buckets[m.group(1)]]["files"][name] = {"size": len(body), "md5": md5}
                    self._send(200, {"key": name, "size": len(body), "checksum": f"md5:{md5}"})
                    return
                fake.violations.append(f"unserved: {method} {path}")
                self._send(404, {"message": "not found", "status": 404})

            def do_GET(self) -> None:
                self._handle("GET")

            def do_POST(self) -> None:
                self._handle("POST")

            def do_PUT(self) -> None:
                self._handle("PUT")

            def do_DELETE(self) -> None:
                self._handle("DELETE")

        return Handler
