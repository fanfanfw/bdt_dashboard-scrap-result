#!/usr/bin/env python3
"""Isolated synthetic smoke for the M2-T2 dashboard image (gate PG-B, LOCAL only).

TEST-ONLY harness. Not app source, not shipped in the image, changes no app file.
Runs INSIDE the built image; the harness and the compose file are mounted
read-only from the repo (tmpfs /tmp would mask a /tmp mount, so the mount point
is /smoke).

REQUIRED inputs -- the run FAILS CLOSED (exit 2) if either is missing/invalid:
  SMOKE_EXPECT_STATIC_SHA   sha256 of car_ads_dashboard/dashboard/static/css/login.css
  SMOKE_COMPOSE_FILE        read-only path to the repo's compose.dokploy.yaml

Exact copy-paste command (both mounts, no ports, non-root, read-only, no net):

  REPO=/home/ifcon/ff/bdt_dashboard-scrap-result
  SMOKE_EXPECT_STATIC_SHA=$(sha256sum \\
      "$REPO/car_ads_dashboard/dashboard/static/css/login.css" | cut -d' ' -f1)
  docker run --rm --network none --read-only --cap-drop ALL \\
      --security-opt no-new-privileges --tmpfs /tmp:rw,noexec,nosuid,size=64m \\
      --init --user 1000:1000 \\
      -e SMOKE_EXPECT_STATIC_SHA="$SMOKE_EXPECT_STATIC_SHA" \\
      -e SMOKE_COMPOSE_FILE=/smoke/compose.dokploy.yaml \\
      -v "$REPO/tests/smoke_dashboard_docker.py:/smoke/smoke_dashboard_docker.py:ro" \\
      -v "$REPO/compose.dokploy.yaml:/smoke/compose.dokploy.yaml:ro" \\
      cars-dashboard:m2-t2-20261023 python3 /smoke/smoke_dashboard_docker.py

Coverage (each line printed as PASS/FAIL):
  A. The REAL settings module, imported with deliberately CONFLICTING env, still
     resolves CELERY_BROKER_URL / CELERY_RESULT_BACKEND to redis://localhost:6379/0
     and CHANNEL_LAYERS hosts to [("127.0.0.1", 6379)] on the channels_redis
     RedisChannelLayer backend -- i.e. these targets are hardcoded, not env-driven.
  B. The Channels layer is overridden to IN-MEMORY for this test only, from a
     derived TEST-ONLY settings module written outside the app tree.
  C. Redis / non-loopback contact is MEASURED via sys.addaudithook and asserted
     absent. Scope is exactly the audited processes (harness + daphne child); the
     healthcheck/egress subprocesses are NOT audited, and the healthcheck's own
     target is loopback:18111 by construction.
  D. No DB connection is created (connection_created never fires); sqlite :memory:.
  E. Real daphne boot using the image's own CMD with TEST-ONLY settings: bounded
     readiness poll, only loopback:18111 listens, / -> 302, login -> 200, a NAMED
     static asset -> 200 whose sha256 equals the REQUIRED repo hash, the literal
     compose.dokploy.yaml healthcheck exits 0 live and 1 for a host outside
     ALLOWED_HOSTS, a bad Host really returns 400, SIGTERM exits 0 within bound.
  F. Real WebSocket handshake through the real routing table wrapped in the real
     AllowedHostsOriginValidator over a real in-memory layer: staff accepted with
     real group_add / frames / group_send broadcast / group_discard; anonymous
     rejected with 4403; bad Origin rejected.

DELIBERATELY NOT TESTED -- do not read this file as proof of these:
  - production auth stack: channels.auth.AuthMiddlewareStack and the DB-backed
    session lookup are replaced by a test-only scope["user"] injection; no real
    session is created or read, no login POST is performed;
  - the DB accessor behind recent_jobs() is stubbed; no job row is read;
  - no task enqueued, no migration, no business table touched, no production env.
"""

import asyncio
import hashlib
import ipaddress
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP_DIR = os.environ.get("SMOKE_APP_DIR", "/app/car_ads_dashboard")
WORK_DIR = os.environ.get("SMOKE_WORK_DIR", "/tmp/smoke_run")
AUDIT_LOG = os.environ.get("SMOKE_AUDIT_LOG", os.path.join(WORK_DIR, "socket-audit.jsonl"))
DAPHNE_LOG = os.path.join(WORK_DIR, "daphne.log")
LISTEN_PORT = int(os.environ.get("SMOKE_PORT", "18111"))
HEALTH_HOST = "example.invalid"
BAD_HOST = "not-in-allowed-hosts.example"
SHUTDOWN_BOUND_S = 30.0
# Synthetic, test-only. Never a production value.
SECRET_KEY = "smoke-test-only-not-a-secret-django-insecure-0123456789abcdef"
CMD = ["daphne", "-b", "127.0.0.1", "-p", str(LISTEN_PORT), "car_ads_dashboard.asgi:application"]
STATIC_PATH = "/static/css/login.css"
STATIC_DISK = os.path.join(APP_DIR, "dashboard/static/css/login.css")

RESULTS = []


def chk(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(("PASS  " if cond else "FAIL  ") + name + (("  [%s]" % detail) if detail else ""))
    return bool(cond)


# --------------------------------------------------------------- fail-closed io
class AuditError(RuntimeError):
    pass


def audit_records():
    """Read the audit log FAIL-CLOSED: a missing file, a malformed line or a
    record without event/pid is an error, never silently skipped."""
    if not os.path.exists(AUDIT_LOG):
        raise AuditError("audit log missing: %s" % AUDIT_LOG)
    out = []
    with open(AUDIT_LOG, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except ValueError as exc:
                raise AuditError("audit line %d malformed: %s" % (n, exc))
            if not isinstance(rec, dict) or "event" not in rec or "pid" not in rec:
                raise AuditError("audit line %d missing event/pid: %r" % (n, s[:80]))
            out.append(rec)
    if not out:
        raise AuditError("audit log is empty (recorder never armed?): %s" % AUDIT_LOG)
    return out


def connects(recs):
    return [r for r in recs if r.get("event") == "socket.connect"]


def db_connects(recs):
    return [r for r in recs if r.get("event") == "db.connect"]


def marker_pids(recs, event):
    return sorted({r.get("pid") for r in recs if r.get("event") == event})


def addr_port(addr):
    m = re.search(r",\s*(\d+)\)\s*$", addr or "")
    return int(m.group(1)) if m else None


# ------------------------------------------------------- required input checks
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def preflight_errors(env):
    """Pure predicate: the reasons a run must be refused. Empty list == ok."""
    errs = []
    sha = (env.get("SMOKE_EXPECT_STATIC_SHA") or "").strip().lower()
    if not sha:
        errs.append("SMOKE_EXPECT_STATIC_SHA is required (no default; fail closed)")
    elif not HEX64.match(sha):
        errs.append("SMOKE_EXPECT_STATIC_SHA must be 64 lowercase hex chars, got %r" % sha[:20])
    compose = (env.get("SMOKE_COMPOSE_FILE") or "").strip()
    if not compose:
        errs.append("SMOKE_COMPOSE_FILE is required (no default; fail closed)")
    elif not os.path.isabs(compose):
        errs.append("SMOKE_COMPOSE_FILE must be an absolute path, got %r" % compose)
    elif not os.path.isfile(compose):
        errs.append("SMOKE_COMPOSE_FILE does not exist as a file: %s" % compose)
    return errs


def shutdown_ok(returncode, elapsed, bound=SHUTDOWN_BOUND_S):
    """Pure predicate: a clean bounded shutdown. A crash (-9) is NOT clean."""
    return returncode == 0 and elapsed is not None and 0 <= elapsed < bound


# ------------------------------------------------------------- derived settings
DERIVED_SETTINGS = '''
"""TEST-ONLY derived settings, generated at runtime outside the app tree.

Not app source, never committed, never in the image. Imports the REAL settings
module unchanged, then applies test-only overrides because the production values
point at a real PostgreSQL and a real Redis.
"""
import json
import os
import sys
import time

_AUDIT = os.environ.get("SMOKE_AUDIT_LOG")


def _rec(payload):
    # Fail LOUDLY instead of silently blinding the parent's assertions.
    if not _AUDIT:
        sys.stderr.write("audit recorder: SMOKE_AUDIT_LOG unset; no measurement\\n")
        return
    try:
        with open(_AUDIT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\\n")
    except Exception as exc:                      # never a silent pass
        sys.stderr.write("audit recorder write FAILED: %r\\n" % (exc,))


def _audit_hook(event, args):
    # MEASURE, do not assume: every outbound connect attempt is recorded.
    if event != "socket.connect":
        return
    _rec({"pid": os.getpid(), "event": "socket.connect",
          "addr": str(args[1] if len(args) > 1 else None),
          "monotonic": time.monotonic()})


sys.addaudithook(_audit_hook)
_rec({"pid": os.getpid(), "event": "hook_armed", "monotonic": time.monotonic()})

# Real settings, imported UNCHANGED. The hardcoded Redis broker/Channels targets
# are asserted against this module by the harness BEFORE these overrides apply.
from car_ads_dashboard.settings import *  # noqa: F401,F403

# --- test-only overrides (this generated module is their only home) ---------
DEBUG = False
ALLOWED_HOSTS = ["example.invalid"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# --- DB contact guard -------------------------------------------------------
from django.db.backends.signals import connection_created  # noqa: E402


def _on_connection_created(sender, connection, **kwargs):
    _rec({"pid": os.getpid(), "event": "db.connect",
          "engine": connection.settings_dict.get("ENGINE", "?")})


connection_created.connect(_on_connection_created)
_rec({"pid": os.getpid(), "event": "dbguard_installed", "monotonic": time.monotonic()})
'''


def write_derived_settings():
    os.makedirs(WORK_DIR, exist_ok=True)
    target = pathlib.Path(WORK_DIR) / "smoke_settings.py"
    target.write_text(DERIVED_SETTINGS, encoding="utf-8")
    return str(target)


def synthetic_env():
    """Test-only values. Nothing here is read from the repository .env."""
    return {
        "SECRET_KEY": SECRET_KEY,
        "DEBUG": "False",
        "ALLOWED_HOSTS": HEALTH_HOST,
        "CSRF_TRUSTED_ORIGINS": "http://" + HEALTH_HOST,
        "DJANGO_SERVE_STATIC": "true",
        "DB_NAME": "smoke_db_not_used",
        "DB_USER": "smoke_user_not_used",
        "DB_PASSWORD": "smoke_password_not_used",
        "DB_HOST": "203.0.113.1",       # TEST-NET-3: unreachable, never contacted
        "DB_PORT": "5432",
        "DJANGO_SETTINGS_MODULE": "smoke_settings",
        "SMOKE_APP_DIR": APP_DIR,
        "SMOKE_WORK_DIR": WORK_DIR,
        "SMOKE_AUDIT_LOG": AUDIT_LOG,
    }


# ---------------------------------------------------------------- proc helpers
def _proc_net_addr(ip_hex, v6):
    """/proc/net/tcp* stores each 32-bit word little-endian; decode properly."""
    if not v6:
        return str(ipaddress.IPv4Address(bytes.fromhex(ip_hex)[::-1]))
    raw = b"".join(bytes.fromhex(ip_hex[i:i + 8])[::-1] for i in (0, 8, 16, 24))
    return str(ipaddress.IPv6Address(raw))


def listening_sockets():
    """{(ip, port)} of TCP LISTEN sockets in this netns (stdlib /proc parsing)."""
    found = set()
    for name, v6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
        try:
            with open(name, encoding="utf-8") as fh:
                next(fh)
                for line in fh:
                    f = line.split()
                    if len(f) < 4 or f[3] != "0A":      # 0A == TCP_LISTEN
                        continue
                    ip_hex, port_hex = f[1].split(":")
                    found.add((_proc_net_addr(ip_hex, v6), int(port_hex, 16)))
        except (OSError, StopIteration, ValueError):
            pass
    return found


def http_get(opener, path, timeout=5, host=HEALTH_HOST):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (LISTEN_PORT, path),
                                 headers={"Host": host})
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers), r.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers), exc.geturl()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report the 3xx itself instead of following it, so redirects are asserted."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def no_redirect_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


# --------------------------------------------------------------------------- A
def phase_literals(real_settings):
    print("\n== A. hardcoded settings literals (real module, conflicting env injected) ==")
    chk("A1 CELERY_BROKER_URL is literally redis://localhost:6379/0",
        real_settings.CELERY_BROKER_URL == "redis://localhost:6379/0",
        repr(real_settings.CELERY_BROKER_URL))
    chk("A2 CELERY_RESULT_BACKEND is literally redis://localhost:6379/0",
        real_settings.CELERY_RESULT_BACKEND == "redis://localhost:6379/0",
        repr(real_settings.CELERY_RESULT_BACKEND))
    layers = real_settings.CHANNEL_LAYERS["default"]
    chk("A3 CHANNEL_LAYERS backend is channels_redis RedisChannelLayer",
        layers["BACKEND"] == "channels_redis.core.RedisChannelLayer", layers["BACKEND"])
    chk("A4 CHANNEL_LAYERS hosts is literally [(127.0.0.1, 6379)]",
        layers["CONFIG"]["hosts"] == [("127.0.0.1", 6379)], repr(layers["CONFIG"]["hosts"]))

    # A5 measures the real claim: a fresh import of the REAL settings module is
    # given CONFLICTING env for the very same names; the literals must not move.
    probe = (
        "import json, os\n"
        "import car_ads_dashboard.settings as s\n"
        "print(json.dumps([s.CELERY_BROKER_URL, s.CELERY_RESULT_BACKEND,\n"
        "                  s.CHANNEL_LAYERS['default']['BACKEND'],\n"
        "                  s.CHANNEL_LAYERS['default']['CONFIG']['hosts']]))\n"
    )
    conflict = {k: v for k, v in os.environ.items() if k != "SMOKE_AUDIT_LOG"}
    conflict.update({
        "CELERY_BROKER_URL": "redis://conflict.invalid:6399/7",
        "CELERY_RESULT_BACKEND": "redis://conflict.invalid:6399/7",
        "CHANNEL_LAYERS": '{"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}',
        "PYTHONPATH": APP_DIR,
    })
    got = subprocess.run([sys.executable, "-c", probe], cwd=APP_DIR, env=conflict,
                         capture_output=True, text=True, timeout=120)
    try:
        vals = json.loads(got.stdout.strip().splitlines()[-1])
    except Exception:
        vals = None
    chk("A5 conflicting env for the SAME names does NOT change the Redis literals",
        vals == ["redis://localhost:6379/0", "redis://localhost:6379/0",
                 "channels_redis.core.RedisChannelLayer", [["127.0.0.1", 6379]]],
        "real import with CELERY_BROKER_URL=redis://conflict.invalid:6399/7 -> %r" % (vals,))

    chk("A6 DB HOST is env-driven while ENGINE is hardcoded (contrast: A1-A4 are literals)",
        real_settings.DATABASES["default"]["HOST"] == "203.0.113.1"
        and real_settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql",
        "ENGINE=%s (literal) HOST=%s (from synthetic env)"
        % (real_settings.DATABASES["default"]["ENGINE"],
           real_settings.DATABASES["default"]["HOST"]))
    chk("A7 SECRET_KEY came from the synthetic test env, not a baked image value",
        real_settings.SECRET_KEY == SECRET_KEY, "synthetic value in use")


# --------------------------------------------------------------------------- B
def phase_override(django_settings):
    print("\n== B. TEST-ONLY in-memory channel layer override ==")
    from channels.layers import get_channel_layer

    chk("B1 effective CHANNEL_LAYERS is channels.layers.InMemoryChannelLayer",
        django_settings.CHANNEL_LAYERS["default"]["BACKEND"] == "channels.layers.InMemoryChannelLayer",
        django_settings.CHANNEL_LAYERS["default"]["BACKEND"])
    layer = get_channel_layer()
    chk("B2 get_channel_layer() returns an InMemoryChannelLayer",
        type(layer).__name__ == "InMemoryChannelLayer", type(layer).__name__)
    chk("B3 the effective channel layer is not a RedisChannelLayer "
        "(Redis contact itself is proven absent by C1, not by this type check)",
        type(layer).__name__ != "RedisChannelLayer", type(layer).__name__)
    chk("B4 effective DEBUG is False", django_settings.DEBUG is False, str(django_settings.DEBUG))
    chk("B5 effective ALLOWED_HOSTS is the single synthetic host",
        list(django_settings.ALLOWED_HOSTS) == [HEALTH_HOST], repr(list(django_settings.ALLOWED_HOSTS)))
    chk("B6 effective DB backend is sqlite (no PostgreSQL client path)",
        django_settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3",
        django_settings.DATABASES["default"]["ENGINE"])


# --------------------------------------------------------------------------- F
def phase_websocket():
    print("\n== F. real WebSocket handshake on cars-standard jobs ==")
    from unittest import mock

    from channels.layers import get_channel_layer
    from channels.routing import URLRouter
    from channels.security.websocket import AllowedHostsOriginValidator
    from channels.testing import WebsocketCommunicator
    from django.contrib.auth.models import AnonymousUser, User

    import dashboard.routing
    from dashboard.consumers import CarsStandardJobConsumer
    from dashboard.services.cars_standard_maintenance import CARS_STANDARD_JOBS_GROUP

    chk("F1 routing table exposes the real cars-standard jobs consumer",
        any("ws/cars-standard/jobs/" in str(p.pattern) for p in dashboard.routing.websocket_urlpatterns),
        "dashboard.routing.websocket_urlpatterns")
    chk("F2 broadcast group name is literally cars_standard_jobs",
        CARS_STANDARD_JOBS_GROUP == "cars_standard_jobs", CARS_STANDARD_JOBS_GROUP)

    FAKE_JOB = {"id": 424242, "job_type": "synthetic", "status": "success",
                "requested_by": "smoke", "dry_run": True, "created_at": None}

    async def _stub_recent_jobs(self):
        # TEST-ONLY stub of the SINGLE DB accessor. Everything else in the
        # consumer (is_admin gate, group_add, accept, send, disconnect,
        # group_discard) runs for real.
        return [FAKE_JOB]

    class InjectUser:
        """TEST-ONLY: replaces the auth/session stack with a fixed scope user.

        The real AllowedHostsOriginValidator and the real URLRouter stay in
        place, in their real order, so origin rejection and routing are genuine.
        """

        def __init__(self, app, user):
            self.app, self.user = app, user

        async def __call__(self, scope, receive, send):
            scope = dict(scope)
            scope["user"] = self.user
            return await self.app(scope, receive, send)

    def build_app(user):
        return AllowedHostsOriginValidator(
            InjectUser(URLRouter(dashboard.routing.websocket_urlpatterns), user))

    layer = get_channel_layer()
    ok_hdr = [(b"origin", b"http://" + HEALTH_HOST.encode())]
    bad_hdr = [(b"origin", b"http://evil.example")]

    async def run():
        comm = WebsocketCommunicator(build_app(User(is_staff=True, username="smoke")),
                                     "/ws/cars-standard/jobs/", headers=bad_hdr)
        accepted, code = await asyncio.wait_for(comm.connect(timeout=5), 10)
        chk("F3 invalid Origin is rejected by the real AllowedHostsOriginValidator",
            accepted is False, "accepted=%r close=%r" % (accepted, code))
        await asyncio.wait_for(comm.wait(5), 10)

        comm = WebsocketCommunicator(build_app(AnonymousUser()),
                                     "/ws/cars-standard/jobs/", headers=ok_hdr)
        accepted, code = await asyncio.wait_for(comm.connect(timeout=5), 10)
        chk("F4 unauthenticated connect is rejected with close code 4403",
            accepted is False and code == 4403, "accepted=%r close=%r" % (accepted, code))
        await asyncio.wait_for(comm.wait(5), 10)

        staff = User(is_staff=True, username="smoke_staff", is_active=True)
        with mock.patch.object(CarsStandardJobConsumer, "recent_jobs", new=_stub_recent_jobs):
            before = set(layer.groups.get(CARS_STANDARD_JOBS_GROUP, {}))
            comm = WebsocketCommunicator(build_app(staff),
                                         "/ws/cars-standard/jobs/", headers=ok_hdr)
            accepted, _ = await asyncio.wait_for(comm.connect(timeout=5), 10)
            chk("F5 staff connect is ACCEPTED (real accept())",
                accepted is True, "accepted=%r" % (accepted,))
            added = set(layer.groups.get(CARS_STANDARD_JOBS_GROUP, {})) - before
            chk("F6 real group_add registered exactly one new channel on cars_standard_jobs",
                len(added) == 1, "added=%d groups=%s" % (len(added), list(layer.groups)))

            first = await asyncio.wait_for(comm.receive_json_from(timeout=5), 10)
            second = await asyncio.wait_for(comm.receive_json_from(timeout=5), 10)
            chk("F7 connect emits initial + jobs_update frames from the (stubbed) accessor",
                first.get("type") == "initial" and second.get("type") == "jobs_update"
                and first.get("jobs") == [FAKE_JOB],
                "%s/%s" % (first.get("type"), second.get("type")))

            await layer.group_send(CARS_STANDARD_JOBS_GROUP,
                                   {"type": "cars_standard_job_update", "job": FAKE_JOB})
            update = await asyncio.wait_for(comm.receive_json_from(timeout=5), 10)
            chk("F8 group broadcast is delivered as a job_update frame",
                update.get("type") == "job_update" and update.get("job") == FAKE_JOB,
                str(update.get("type")))

            await asyncio.wait_for(comm.disconnect(), 10)
            remaining = set(layer.groups.get(CARS_STANDARD_JOBS_GROUP, {}))
            chk("F9 real disconnect ran group_discard (the added channel is gone)",
                not (added & remaining),
                "remaining=%d groups=%s" % (len(remaining), list(layer.groups)))

    asyncio.run(run())


# --------------------------------------------------------------------------- E
def phase_http(expected_sha, compose_path):
    print("\n== E. real daphne boot on 127.0.0.1:%d with TEST-ONLY settings ==" % LISTEN_PORT)
    env = dict(os.environ)
    env.update(synthetic_env())
    env["PYTHONPATH"] = WORK_DIR + os.pathsep + APP_DIR
    env["DJANGO_SETTINGS_MODULE"] = "smoke_settings"

    clean_log = {"text": ""}   # snapshot BEFORE the deliberate bad-Host probes
    log = open(DAPHNE_LOG, "wb")
    proc = subprocess.Popen(CMD, cwd=APP_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # ignore injected proxy
    try:
        deadline = time.monotonic() + 60
        ready, last = False, ""
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                if http_get(opener, "/accounts/login/", timeout=2)[0] == 200:
                    ready = True
                    break
            except Exception as exc:                     # not up yet
                last = type(exc).__name__
            time.sleep(0.25)
        chk("E1 daphne boot completed and /accounts/login/ answered 200 (60s bound)",
            ready, "last=%s" % (last or "n/a"))
        if not ready:
            return

        chk("E2 the only TCP listener is 127.0.0.1:%d" % LISTEN_PORT,
            listening_sockets() == {("127.0.0.1", LISTEN_PORT)},
            "listeners=%s" % sorted(listening_sockets()))

        status, _, headers, _ = http_get(no_redirect_opener(), "/")
        chk("E3 GET / returns 302 redirecting to /accounts/login/",
            status == 302 and "/accounts/login/" in headers.get("Location", ""),
            "%s -> %s" % (status, headers.get("Location")))

        status, _, _, final_url = http_get(opener, "/")
        chk("E3b following that redirect lands on the login page with 200",
            status == 200 and final_url.endswith("/accounts/login/"),
            "%s at %s" % (status, final_url))

        status, body, _, _ = http_get(opener, "/accounts/login/")
        chk("E4 GET /accounts/login/ returns 200 with the real login template",
            status == 200 and b"<title>Login - Car Ads Dashboard</title>" in body,
            "%s, %d bytes" % (status, len(body)))

        asset = pathlib.Path(STATIC_DISK).read_bytes()
        status, served, _, _ = http_get(opener, STATIC_PATH)
        served_sha = hashlib.sha256(served).hexdigest()
        chk("E5 named static asset %s served 200 through ASGIStaticFilesHandler" % STATIC_PATH,
            status == 200, "%s, %d bytes" % (status, len(served)))
        chk("E6 served static bytes equal the on-disk source asset",
            served == asset, "served=%d bytes disk=%d bytes" % (len(served), len(asset)))
        chk("E7 served static sha256 equals the REQUIRED source-repo hash",
            served_sha == expected_sha, "served=%s expected=%s"
            % (served_sha[:16], expected_sha[:16]))

        # E10/E11: run the healthcheck snippet EXACTLY as shipped in
        # compose.dokploy.yaml (parsed from the read-only mounted file).
        import yaml
        with open(compose_path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        test = doc["services"]["dashboard"]["healthcheck"]["test"]
        snippet = test[-1] if isinstance(test, list) else test
        hc_env = {k: v for k, v in os.environ.items() if k != "SMOKE_AUDIT_LOG"}
        hc_env["DASHBOARD_HEALTH_HOST"] = HEALTH_HOST
        hc = subprocess.run([sys.executable, "-c", snippet], env=hc_env,
                            capture_output=True, text=True, timeout=30)
        chk("E10 the literal compose.dokploy.yaml healthcheck exits 0 against live daphne",
            hc.returncode == 0, "rc=%d %s" % (hc.returncode, (hc.stderr or "").strip()[:120]))

        clean_log["text"] = pathlib.Path(DAPHNE_LOG).read_text(encoding="utf-8", errors="replace")

        hc_env["DASHBOARD_HEALTH_HOST"] = BAD_HOST
        bad_hc = subprocess.run([sys.executable, "-c", snippet], env=hc_env,
                                capture_output=True, text=True, timeout=30)
        chk("E11 the same healthcheck exits 1 when the Host is not in ALLOWED_HOSTS",
            bad_hc.returncode == 1,
            "rc=%d (negative control: the probe is host-strict)" % bad_hc.returncode)

        status, _, _, _ = http_get(opener, "/accounts/login/", host=BAD_HOST)
        chk("E12 a direct request with a Host outside ALLOWED_HOSTS really returns 400",
            status == 400, "HTTP %s for Host=%s" % (status, BAD_HOST))

        t0 = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=SHUTDOWN_BOUND_S)
            elapsed = time.monotonic() - t0
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
            elapsed, rc = SHUTDOWN_BOUND_S, proc.returncode
        chk("E8 daphne exits 0 (clean, not a crash) within the bounded SIGTERM window",
            shutdown_ok(rc, elapsed), "rc=%r in %.2fs (bound %.0fs)"
            % (rc, elapsed, SHUTDOWN_BOUND_S))
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
        log.close()

    text = clean_log["text"] or pathlib.Path(DAPHNE_LOG).read_text(
        encoding="utf-8", errors="replace")
    noisy = [ln for ln in text.splitlines() if re.search(r"Traceback|ERROR|Exception|CRITICAL", ln)]
    chk("E9 no traceback/error in the daphne boot log (before the deliberate bad-Host probes)",
        not noisy, "; ".join(noisy[:2]) or "%d log lines, clean" % len(text.splitlines()))


# --------------------------------------------------------------------------- C/D
def phase_no_external():
    print("\n== C/D. measured absence of Redis, non-loopback and DB contact ==")
    try:
        recs = audit_records()
    except AuditError as exc:
        chk("C0 the audit record is complete and parseable (fail closed)", False, str(exc))
        chk("C1 zero socket.connect attempts to port 6379 (Redis) were measured", False, "no audit")
        chk("C2 zero socket.connect attempts to a non-loopback address were measured", False, "no audit")
        chk("C3 recorder armed in both the harness and the daphne child", False, "no audit")
        chk("C4 every recorded socket.connect targeted loopback:%d" % LISTEN_PORT, False, "no audit")
        chk("D1 zero database connections were created", False, "no audit")
        return
    chk("C0 the audit record is complete and parseable (fail closed)", True,
        "%d records" % len(recs))

    conns = connects(recs)
    redis_hits = [r for r in conns if addr_port(r.get("addr")) == 6379]
    non_lo = [r for r in conns if not (r.get("addr") or "").startswith("('127.0.0.1'")]
    hooked = marker_pids(recs, "hook_armed")
    guarded = marker_pids(recs, "dbguard_installed")
    chk("C1 zero socket.connect attempts to port 6379 (Redis) in the audited processes",
        not redis_hits, "connects=%d redis=%d audited_pids=%s" % (len(conns), len(redis_hits), hooked))
    chk("C2 zero socket.connect attempts to a non-loopback address", not non_lo,
        [r.get("addr") for r in non_lo][:3])
    chk("C3 audit recorder armed in BOTH this process and the daphne child "
        "(scope: harness + daphne only; healthcheck/egress subprocesses are not audited)",
        os.getpid() in hooked and any(p != os.getpid() for p in hooked),
        "hook_pids=%s self=%d" % (hooked, os.getpid()))
    chk("C4 the DB guard is installed in BOTH processes", os.getpid() in guarded
        and any(p != os.getpid() for p in guarded),
        "dbguard_pids=%s" % (guarded,))
    chk("C5 every recorded socket.connect targeted loopback:%d" % LISTEN_PORT,
        all(addr_port(r.get("addr")) == LISTEN_PORT for r in conns if addr_port(r.get("addr")) is not None),
        "ports=%s" % sorted({addr_port(r.get("addr")) for r in conns}))

    # Namespace-level egress probe. Deliberately NOT audited (its own attempt is
    # not application traffic); same netns, so it proves --network none.
    probe_env = {k: v for k, v in os.environ.items() if k != "SMOKE_AUDIT_LOG"}
    probe = subprocess.run(
        [sys.executable, "-c",
         "import socket\n"
         "try:\n"
         "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
         "    print('EGRESS_ALLOWED')\n"
         "except OSError as e:\n"
         "    print('EGRESS_DENIED', type(e).__name__)"],
        capture_output=True, text=True, env=probe_env, timeout=30)
    out = (probe.stdout + probe.stderr).strip()
    chk("C6 external egress is DENIED from this container's namespace",
        "EGRESS_DENIED" in out, out)

    chk("D1 zero database connections were created (connection_created never fired)",
        not db_connects(recs), "db.connect events=%d" % len(db_connects(recs)))
    chk("D2 no .env file exists anywhere under the app tree in the image",
        not any(p.name == ".env" or p.name.startswith(".env.")
                for p in pathlib.Path(APP_DIR).rglob("*") if p.is_file()),
        APP_DIR)


# --------------------------------------------------------------- pure self-test
def self_test():
    """Runnable negative controls for the harness's own guards (no container
    runtime needed): the preflight must REFUSE bad input and the shutdown
    predicate must REJECT a crash/timeout."""
    print("smoke_dashboard_docker.py --self-test (pure predicates)")
    ok = True
    env = os.environ
    tmp = pathlib.Path(WORK_DIR) / "selftest-compose.yaml"
    os.makedirs(WORK_DIR, exist_ok=True)
    tmp.write_text("services: {}\n", encoding="utf-8")

    cases = [
        ("missing SMOKE_EXPECT_STATIC_SHA is refused", {"SMOKE_COMPOSE_FILE": str(tmp)}, True),
        ("missing SMOKE_COMPOSE_FILE is refused", {"SMOKE_EXPECT_STATIC_SHA": "a" * 64}, True),
        ("non-hex expected sha is refused", {"SMOKE_EXPECT_STATIC_SHA": "zz" * 32,
                                             "SMOKE_COMPOSE_FILE": str(tmp)}, True),
        ("short expected sha is refused", {"SMOKE_EXPECT_STATIC_SHA": "abc",
                                           "SMOKE_COMPOSE_FILE": str(tmp)}, True),
        ("relative compose path is refused", {"SMOKE_EXPECT_STATIC_SHA": "a" * 64,
                                              "SMOKE_COMPOSE_FILE": "compose.dokploy.yaml"}, True),
        ("nonexistent compose path is refused", {"SMOKE_EXPECT_STATIC_SHA": "a" * 64,
                                                 "SMOKE_COMPOSE_FILE": "/nonexistent/x.yaml"}, True),
        ("both valid inputs are accepted", {"SMOKE_EXPECT_STATIC_SHA": "a" * 64,
                                            "SMOKE_COMPOSE_FILE": str(tmp)}, False),
    ]
    for name, env_in, should_err in cases:
        errs = preflight_errors(env_in)
        ok &= chk(name, bool(errs) == should_err, "errors=%r" % (errs,))

    ok &= chk("shutdown predicate ACCEPTS rc=0 in 1.0s", shutdown_ok(0, 1.0) is True)
    ok &= chk("shutdown predicate REJECTS a crash rc=-9", shutdown_ok(-9, 0.1) is False, "rc=-9")
    ok &= chk("shutdown predicate REJECTS rc=None (still running)",
              shutdown_ok(None, 1.0) is False)
    ok &= chk("shutdown predicate REJECTS rc=0 but over the time bound",
              shutdown_ok(0, SHUTDOWN_BOUND_S + 1) is False, "elapsed>bound")
    try:
        tmp.unlink()
    except OSError:
        pass
    print("\nSELFTEST %s" % ("ok" if ok else "FAILED"))
    return 0 if ok else 1


def main():
    print("smoke_dashboard_docker.py -- M2-T2 isolated synthetic smoke (TEST-ONLY)")
    print("python=%s cwd=%s loopback_port=%d" % (sys.version.split()[0], os.getcwd(), LISTEN_PORT))

    errs = preflight_errors(os.environ)
    if errs:
        print("\nREFUSED (fail closed) -- required inputs missing/invalid:")
        for e in errs:
            print("  - " + e)
        print("\nBoth SMOKE_EXPECT_STATIC_SHA and SMOKE_COMPOSE_FILE are REQUIRED; "
              "there is no default and no skipped-PASS path.")
        return 2
    expected_sha = os.environ["SMOKE_EXPECT_STATIC_SHA"].strip().lower()
    compose_path = os.environ["SMOKE_COMPOSE_FILE"].strip()

    os.makedirs(WORK_DIR, exist_ok=True)
    if os.path.exists(AUDIT_LOG):
        os.remove(AUDIT_LOG)
    write_derived_settings()

    sys.path.insert(0, WORK_DIR)
    sys.path.insert(0, APP_DIR)
    os.environ.update(synthetic_env())

    import smoke_settings  # noqa: F401  (arms the auditor, imports real settings)
    import car_ads_dashboard.settings as real_settings

    phase_literals(real_settings)

    import django
    django.setup()
    from django.conf import settings as django_settings

    phase_override(django_settings)
    phase_websocket()
    phase_http(expected_sha, compose_path)
    phase_no_external()

    failed = [r for r in RESULTS if not r[0]]
    print("\nRESULT %d passed, %d failed, %d total"
          % (len(RESULTS) - len(failed), len(failed), len(RESULTS)))
    for _, name, detail in failed:
        print("  FAILED: %s  [%s]" % (name, detail))
    print("SCOPE  production AuthMiddlewareStack/session DB NOT tested; recent_jobs DB "
          "accessor stubbed; no task enqueued; no migration; no business row read; "
          "no production env used.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else main())
