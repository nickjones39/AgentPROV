"""The macOS ``sandbox-exec`` containment of real-model runs and its feasibility probe (AD-13(b); G.4.10; G.11.3 open
question 12; MN N.1.11(3), N.2.10).

The profile is fixed text (its sha256 is recorded as ``producer.sandbox.profile_sha256``, HL H.2.7); per-run paths enter
as ``-D`` parameters, so the digest does not depend on them. It allows everything by default and then:

* denies every file write except below the staging root (``STAGING``) and the T2 home root (``T2HOME``) and a few
  device nodes;
* denies reads and writes of the repository root (``REPO``), of credential locations under the user's home (``HOME``:
  ``~/.ssh``, ``~/.aws``, ``~/.azure``, ``~/.config/gh``, ``~/.config/gcloud``, ``~/.docker``, ``~/.kube``, ``~/.gnupg``,
  ``~/Library/Keychains``, ``~/.netrc``) and of every file named ``.env`` or ``.env.*``;
* denies every outbound connection except to two loopback ports, ``EGRESS_PORT`` and ``LOOPBACK_PORT`` (D-664). For a
  remote endpoint both are the port of T0's CONNECT-only egress proxy (:mod:`agentprov.cli.live.egress`), which tunnels
  only to the run's allowlisted endpoint hosts; for a loopback endpoint (a local model server) ``LOOPBACK_PORT`` is the
  server's port. Name resolution goes out through the denied path too, so T2 resolves nothing but ``localhost``: every
  remote name is resolved by the proxy in T0. Before D-664 the profile allowed the whole network (v0.1, G.6.3).

The **probe** runs the built environment's interpreter under the profile, with a scratch home, repository and staging
root, and checks each property by trying it: a write inside staging and inside the T2 home succeeds; a write elsewhere,
a read of a file under the repository, of a credential file and of a ``.env`` file are denied; a connection to the
egress port and one over IPv6 to the ``LOOPBACK_PORT`` listener on ``::1`` succeed, while one to another loopback port and one to a remote address (``192.0.2.1``, TEST-NET-1, RFC
5737: unroutable, so even a broken profile sends nothing to a real host) are denied; the worker module still imports. It touches none of the user's real credential files. ``passed`` only when every check has the expected result.
On a host without ``sandbox-exec`` (every non-macOS host) the result is ``not_applicable``, and a real-model run there
needs ``--containment dedicated-user`` or ``vm`` (operator declarations).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

__all__ = ["PROFILE", "PROFILE_SHA256", "PROBE_REMOTE", "SANDBOX_EXEC", "probe", "wrap_argv"]

SANDBOX_EXEC: Final = "/usr/bin/sandbox-exec"

PROFILE: Final = """(version 1)
(allow default)
(deny file-write*)
(allow file-write*
    (subpath (param "STAGING"))
    (subpath (param "T2HOME"))
    (literal "/dev/null")
    (literal "/dev/zero")
    (literal "/dev/tty")
    (literal "/dev/dtracehelper")
    (regex #"^/dev/fd/[0-9]+$"))
(deny file-read* file-write*
    (subpath (param "REPO"))
    (subpath (string-append (param "HOME") "/.ssh"))
    (subpath (string-append (param "HOME") "/.aws"))
    (subpath (string-append (param "HOME") "/.azure"))
    (subpath (string-append (param "HOME") "/.config/gh"))
    (subpath (string-append (param "HOME") "/.config/gcloud"))
    (subpath (string-append (param "HOME") "/.docker"))
    (subpath (string-append (param "HOME") "/.kube"))
    (subpath (string-append (param "HOME") "/.gnupg"))
    (subpath (string-append (param "HOME") "/Library/Keychains"))
    (literal (string-append (param "HOME") "/.netrc"))
    (regex #"/\\.env(\\.[^/]*)?$"))
(deny network-outbound)
(allow network-outbound
    (remote ip (string-append "localhost:" (param "EGRESS_PORT")))
    (remote ip (string-append "localhost:" (param "LOOPBACK_PORT"))))
"""
PROFILE_SHA256: Final = "sha256:" + hashlib.sha256(PROFILE.encode("utf-8")).hexdigest()

#: What each probe check must observe for the profile to be usable.
EXPECTED: Final[Mapping[str, str]] = {
    "write_staging": "allowed",
    "write_t2home": "allowed",
    "write_outside": "denied",
    "read_repo": "denied",
    "read_credential": "denied",
    "read_dotenv": "denied",
    "connect_egress": "allowed",
    "connect_loopback_v6": "allowed",
    "connect_other_loopback": "denied",
    "connect_remote": "denied",
    "import_worker": "allowed",
}
#: The remote address the probe tries (TEST-NET-1, RFC 5737): unroutable, so a profile that fails to deny it reaches no
#: real host; the attempt then ends in a timeout, which is reported as an unexpected result, never as ``denied``.
PROBE_REMOTE: Final = ("192.0.2.1", 443)

_PROBE_SCRIPT: Final = r"""
import json, os, sys
import socket
staging, t2home, outside, repo_file, cred_file, dotenv_file = sys.argv[1:7]
egress_port, other_port, remote_host, remote_port = int(sys.argv[7]), int(sys.argv[8]), sys.argv[9], int(sys.argv[10])
v6_port = int(sys.argv[11])
res = {}
def attempt(name, fn):
    try:
        fn()
        res[name] = "allowed"
    except PermissionError:
        res[name] = "denied"
    except OSError as exc:
        res[name] = "error:" + type(exc).__name__
    except Exception as exc:
        res[name] = "error:" + type(exc).__name__
def write(path):
    with open(path, "w") as fh:
        fh.write("x")
def read(path):
    with open(path, "rb") as fh:
        fh.read()
attempt("write_staging", lambda: write(os.path.join(staging, "probe.txt")))
attempt("write_t2home", lambda: write(os.path.join(t2home, "probe.txt")))
attempt("write_outside", lambda: write(os.path.join(outside, "probe.txt")))
attempt("read_repo", lambda: read(repo_file))
attempt("read_credential", lambda: read(cred_file))
attempt("read_dotenv", lambda: read(dotenv_file))
def connect(host, port, family=socket.AF_INET):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((host, port))
    finally:
        s.close()
attempt("connect_egress", lambda: connect("127.0.0.1", egress_port))
attempt("connect_loopback_v6", lambda: connect("::1", v6_port, socket.AF_INET6))
attempt("connect_other_loopback", lambda: connect("127.0.0.1", other_port))
attempt("connect_remote", lambda: connect(remote_host, remote_port))
attempt("import_worker", lambda: __import__("agentprov_backend.worker"))
sys.stdout.write(json.dumps(res, sort_keys=True))
"""


def wrap_argv(argv: list[str], *, staging_root: Path, t2home_root: Path, repo: Path, home: Path, egress_port: int,
              loopback_port: int | None = None) -> list[str]:
    """``argv`` run under the profile, with the run's paths (real paths: the kernel sees them resolved) and the two
    loopback ports T2 may connect to as parameters. ``loopback_port`` defaults to ``egress_port``."""
    ports = {"EGRESS_PORT": egress_port, "LOOPBACK_PORT": egress_port if loopback_port is None else loopback_port}
    for name, port in ports.items():
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError(f"{name} must be a port in 1-65535")
    params = {"STAGING": staging_root, "T2HOME": t2home_root, "REPO": repo, "HOME": home}
    out = [SANDBOX_EXEC]
    for key, value in params.items():
        out += ["-D", f"{key}={os.path.realpath(value)}"]
    for key, port in ports.items():
        out += ["-D", f"{key}={port}"]
    return [*out, "-p", PROFILE, *argv]


def probe(python: Path, scratch_parent: Path, *, timeout: float = 120.0) -> dict[str, Any]:
    """Run the feasibility probe with the environment interpreter ``python``. Returns the marker record."""
    record: dict[str, Any] = {"kind": "sandbox_exec", "profile_sha256": PROFILE_SHA256, "checks": {}, "reason": None}
    if platform.system() != "Darwin":
        return {**record, "status": "not_applicable", "reason": "sandbox-exec exists only on macOS"}
    if not os.path.exists(SANDBOX_EXEC):
        return {**record, "status": "failed", "reason": f"{SANDBOX_EXEC} is not present"}
    scratch = scratch_parent / f"sandbox-probe-{uuid.uuid4().hex}"
    try:
        dirs = {name: scratch / name for name in ("staging", "t2home", "outside", "repo", "home", "proj")}
        for path in dirs.values():
            path.mkdir(parents=True, mode=0o700)
        (dirs["home"] / ".ssh").mkdir(mode=0o700)
        repo_file = dirs["repo"] / "canary.txt"
        cred_file = dirs["home"] / ".ssh" / "canary"
        dotenv_file = dirs["proj"] / ".env"
        for path in (repo_file, cred_file, dotenv_file):
            path.write_text("canary\n", encoding="utf-8")
        from agentprov.cli.live.egress import loopback_listeners

        with loopback_listeners(2) as (egress_port, other_port), loopback_listeners(1, "::1") as (v6_port,):
            # LOOPBACK_PORT is a listener on ::1: the rule's "localhost" covers both loopback families (a local
            # endpoint named "localhost" may connect over ::1)
            argv = wrap_argv(
                [str(python), "-I", "-B", "-c", _PROBE_SCRIPT, str(dirs["staging"]), str(dirs["t2home"]),
                 str(dirs["outside"]), str(repo_file), str(cred_file), str(dotenv_file), str(egress_port),
                 str(other_port), PROBE_REMOTE[0], str(PROBE_REMOTE[1]), str(v6_port)],
                staging_root=dirs["staging"], t2home_root=dirs["t2home"], repo=dirs["repo"], home=dirs["home"],
                egress_port=egress_port, loopback_port=v6_port,
            )  # fmt: skip
            env = {"PATH": "/usr/bin:/bin", "HOME": str(dirs["t2home"]), "LANG": "C.UTF-8", "TZ": "UTC"}
            try:
                proc = subprocess.run(argv, capture_output=True, env=env, cwd=dirs["staging"], timeout=timeout,
                                      check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {**record, "status": "failed", "reason": f"the probe did not run: {type(exc).__name__}"}
        try:
            checks = json.loads(proc.stdout.decode("utf-8")) if proc.returncode == 0 else None
        except ValueError:
            checks = None
        if not isinstance(checks, dict):
            return {**record, "status": "failed",
                    "reason": f"sandbox-exec exited {proc.returncode} without a probe result (nested sandbox or a "
                              "rejected profile)"}
        record["checks"] = {k: str(checks.get(k)) for k in sorted(EXPECTED)}
        wrong = sorted(k for k, v in EXPECTED.items() if record["checks"].get(k) != v)
        if wrong:
            return {**record, "status": "failed", "reason": "unexpected result for " + ", ".join(wrong)}
        return {**record, "status": "passed", "macos": platform.mac_ver()[0] or None}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
