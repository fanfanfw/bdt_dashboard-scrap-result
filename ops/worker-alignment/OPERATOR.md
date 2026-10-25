# OPERATOR RUN PACKAGE v2 — dashboard M2 worker alignment + env isolation

**PROPOSAL ONLY — not installed, not executed. No runtime action by the authoring session.**
Document only: no executable remote-mutation script, no secrets, no privileged step has run.
Overall dashboard M2 remains **BELUM SELESAI**. Readiness is **NOT** claimed; gates
**G2–G6 are BLOCKED**, so nothing from §9 onward may be attempted.

Executable commands below run **only** in a future, separately approved window by a **human
operator in a real root session**. This document contains **no privilege-escalation prefix**.
Any ambiguity, mismatch, missing file, or permission denial ⇒ **STOP and report**; never
normalise a path/alias/case, never substitute source for runtime, never retry the identical
failing input.

## 0. Fixed contract (absolute; exact)

| Item | Exact value |
|---|---|
| Source workdir | `/home/ifcon/ff/bdt_dashboard-scrap-result` |
| Source HEAD | `a217884b7f8df6d5bcd3d305d461d0a6ce399d5e` |
| Runtime worker cwd | `/home/scrapper/bdt_dashboard-scrap-result/car_ads_dashboard` |
| Runtime unit | `celery.service`, `/etc/systemd/system/celery.service` `root:root 0644` |
| Runtime user | `scrapper` |
| Legacy settings | `<runtime>/car_ads_dashboard/settings.py` |
| Legacy sha256 (baseline) | `03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c` |
| Patched sha256 (expected) | `72e8ee73aa2c914f2defc22257b8c05584bb10a909b25d5a0f3c920b52a12b48` |
| Patch sha256 | `8bfec61d21546fd33d398e257ae628b9530b1f3d641144aee557b72dca4383d1` |
| Safe-stop sha256 | `79aaa3e7abba876f8cb367666c9eda5b7adfc97c01e48ac6c3066a995c25a69f` |
| Canonical DB (settled, not reopened) | `db_fastapi_scrap_stage` |
| Writer role | `bdt_stage_owner` (never the API read-only role) |
| DB host/port | `127.0.0.1` / `5432` (loopback) |
| Broker literal (pinned) | `redis://localhost:6379/0`; queue `celery`, priority steps `[0, 3, 6, 9]` |
| Celery destination | `celery@scrapper` (single node; exactly one worker) |
| Runtime interpreter (contract) | `/home/scrapper/bdt_dashboard-scrap-result/venv/bin/python` |
| Transport inbox (scrapper-owned) | `/home/scrapper/worker-alignment-20261024` |
| Root staging (root-owned) | `/var/lib/cars-worker-alignment` |
| PROPOSED env file (absent) | `/etc/cars-dashboard/worker.env` `root:scrapper 0640` |
| PROPOSED env dir (absent) | `/etc/cars-dashboard` `root:scrapper 0750` |
| PROPOSED selector drop-in | `/etc/systemd/system/celery.service.d/20-worker-env.conf`, exact content `[Service]` + `Environment=DASHBOARD_DOTENV_PATH=/etc/cars-dashboard/worker.env` |
| PROPOSED safe-stop drop-in | `/etc/systemd/system/celery.service.d/10-worker-safe-stop.conf` |

`PROPOSED` = **not created**; verify absence, never assume presence.

`settings.py` runs `load_dotenv(override=True)`, so a systemd environment is overridden by
whatever dotenv file the caller-source search finds. `EnvironmentFile` alone therefore
**does not make the worker env authoritative**; the approved mechanism is the fail-closed
selector `DASHBOARD_DOTENV_PATH` loading exactly one absolute, non-symlink, regular file.
The selector drop-in must **not** carry `EnvironmentFile=`, and the legacy `.env` must not
be edited, moved, or copied.

## 1. Session initialisation — ONCE (variables are non-readonly, never redeclared)

Start **one dedicated root shell** and keep it for the whole window; do not paste blocks
into unrelated shells. Non-interactive `set -e` caveats are documented in §16.

```bash
bash -euo pipefail
```

Then, once, in that shell. This block asserts its own invariants: it must run as root, it
must not be re-entered with a stale run directory, and every shared variable must be set —
so a failure aborts instead of leaving a half-initialised session.

```bash
set -euo pipefail
set +x
test "$(id -u)" = "0" || { echo "STOP: not a root session" >&2; exit 1; }
test -z "${RUN_DIR:-}" || { echo "STOP: session already initialised; do not re-source" >&2; exit 1; }
RUNTIME_CWD=/home/scrapper/bdt_dashboard-scrap-result/car_ads_dashboard
LEGACY_SETTINGS=$RUNTIME_CWD/car_ads_dashboard/settings.py
UNIT_FILE=/etc/systemd/system/celery.service
DROPIN_DIR=/etc/systemd/system/celery.service.d
TRANSPORT_DIR=/home/scrapper/worker-alignment-20261024
ROOT_STAGE=/var/lib/cars-worker-alignment
PYBIN=/home/scrapper/bdt_dashboard-scrap-result/venv/bin/python
ENV_DIR=/etc/cars-dashboard
ENV_FILE=$ENV_DIR/worker.env
RUN_DIR=""
BACKUP=""
CG=""
CG_PATH=""
OPERATOR_OBSERVATION_SECONDS=""
for required in "$RUNTIME_CWD" "$LEGACY_SETTINGS" "$UNIT_FILE" "$DROPIN_DIR" "$TRANSPORT_DIR" "$ROOT_STAGE" "$PYBIN" "$ENV_DIR" "$ENV_FILE"; do
  test -n "$required" || { echo "STOP: empty shared context variable" >&2; exit 1; }
done
echo "context: runtime=$RUNTIME_CWD unit=$UNIT_FILE python=$PYBIN"
```

Every later block begins with `set -euo pipefail` plus a shared-context assertion; a block
pasted into a shell that lost the context **aborts** instead of guessing a default.

## 2. B2 — root-owned snapshot of the transported artifacts (hash-gated)

Transport is out of band into the scrapper-owned inbox; **no root read/patch ever uses that
user-writable path**. Root copies once into a unique root-owned run directory and every
later step reads only the root-owned copy. `mktemp -d` makes the name unpredictable (no
clobber, no symlink pre-seed).

```bash
set -euo pipefail
[ -n "${TRANSPORT_DIR:-}" ] && [ -n "${ROOT_STAGE:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
test "$(id -u)" = "0" || { echo "STOP: not a root session" >&2; exit 1; }
test "$(sha256sum "$TRANSPORT_DIR/settings-legacy-dotenv.patch" | cut -d' ' -f1)" = "8bfec61d21546fd33d398e257ae628b9530b1f3d641144aee557b72dca4383d1" || { echo "STOP: patch hash mismatch in inbox" >&2; exit 1; }
test "$(sha256sum "$TRANSPORT_DIR/10-safe-stop.conf" | cut -d' ' -f1)" = "79aaa3e7abba876f8cb367666c9eda5b7adfc97c01e48ac6c3066a995c25a69f" || { echo "STOP: safe-stop hash mismatch in inbox" >&2; exit 1; }
# /var/lib must be a root-owned real directory that group/other cannot write.
test -d /var/lib && test ! -L /var/lib || { echo "STOP: /var/lib is not a real directory" >&2; exit 1; }
test "$(stat -c '%U' /var/lib)" = "root" || { echo "STOP: /var/lib not root-owned" >&2; exit 1; }
modes="$(stat -c '%a' /var/lib)"
test "$(( 0${modes} & 022 ))" -eq 0 || { echo "STOP: /var/lib group/other-writable" >&2; exit 1; }
if [ -e "$ROOT_STAGE" ]; then
  # Existing stage: verify it, never re-permission an unknown directory blindly.
  test -d "$ROOT_STAGE" && test ! -L "$ROOT_STAGE" || { echo "STOP: existing root stage is not a real dir" >&2; exit 1; }
  test "$(stat -c '%U:%G' "$ROOT_STAGE")" = "root:root" || { echo "STOP: existing root stage owner" >&2; exit 1; }
  test "$(stat -c '%a' "$ROOT_STAGE")" = "700" || { echo "STOP: existing root stage mode not 0700" >&2; exit 1; }
else
  install -d -o root -g root -m 0700 "$ROOT_STAGE"
  test ! -L "$ROOT_STAGE" || { echo "STOP: root stage is a symlink" >&2; exit 1; }
fi
RUN_DIR="$(mktemp -d "$ROOT_STAGE/run.XXXXXXXX")"
test -d "$RUN_DIR" && test ! -L "$RUN_DIR" || { echo "STOP: run dir not a real directory" >&2; exit 1; }
chmod 0700 "$RUN_DIR"
install -o root -g root -m 0644 "$TRANSPORT_DIR/settings-legacy-dotenv.patch" "$RUN_DIR/settings-legacy-dotenv.patch"
install -o root -g root -m 0644 "$TRANSPORT_DIR/10-safe-stop.conf" "$RUN_DIR/10-safe-stop.conf"
test "$(sha256sum "$RUN_DIR/settings-legacy-dotenv.patch" | cut -d' ' -f1)" = "8bfec61d21546fd33d398e257ae628b9530b1f3d641144aee557b72dca4383d1" || { echo "STOP: root copy patch hash mismatch" >&2; exit 1; }
test "$(sha256sum "$RUN_DIR/10-safe-stop.conf" | cut -d' ' -f1)" = "79aaa3e7abba876f8cb367666c9eda5b7adfc97c01e48ac6c3066a995c25a69f" || { echo "STOP: root copy safe-stop hash mismatch" >&2; exit 1; }
BACKUP="$RUN_DIR/settings.py.legacy.bak"
test ! -e "$BACKUP" || { echo "STOP: backup exists, refusing to overwrite" >&2; exit 1; }
cp --preserve=mode,ownership,timestamps "$LEGACY_SETTINGS" "$BACKUP"
test "$(sha256sum "$BACKUP" | cut -d' ' -f1)" = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c" || { echo "STOP: baseline backup hash mismatch" >&2; exit 1; }
stat -c 'run_dir=%n mode=%a owner=%U:%G' "$RUN_DIR"
echo "run_dir=$RUN_DIR backup=$BACKUP"
```

The backup is the only rollback source for `settings.py`; it lives in the root-private run
directory and is never deleted in this package.

## 3. B1 — bounded live readback (booleans for sensitive fields, no raw dumps)

Historical snapshot (may be stale): no drop-ins, no `ExecStop`/`ExecStopPost`, no
`EnvironmentFiles`, `Restart=always`, `KillMode=control-group`, `KillSignal=SIGTERM`,
`TimeoutStopSec=90s`, `SendSIGKILL=yes`, systemd `255.4`, Celery `5.5.3` prefork 8.
Absence of drop-ins is historical only — re-prove live; mismatch ⇒ STOP.

Sensitive properties (`Environment`, `ExecStart`, `ExecStop`, `ExecStopPost`,
`EnvironmentFiles`) are tested **as booleans only** and never echoed: their raw values can
carry secrets or command lines. Only named non-sensitive policy fields are printed.

```bash
set -euo pipefail
[ -n "${UNIT_FILE:-}" ] && [ -n "${LEGACY_SETTINGS:-}" ] && [ -n "${PYBIN:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
test -f "$UNIT_FILE" || { echo "STOP: unit file absent" >&2; exit 1; }
test -x "$PYBIN" || { echo "STOP: contract interpreter path not executable; do not substitute" >&2; exit 1; }
test "$(sha256sum "$LEGACY_SETTINGS" | cut -d' ' -f1)" = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c" || { echo "STOP: legacy settings hash is not the baseline" >&2; exit 1; }
test -z "$(systemctl show -p Environment --value celery.service)" || { echo "STOP: unit already sets Environment=; selector parity unknown" >&2; exit 1; }
test -z "$(systemctl show -p EnvironmentFiles --value celery.service)" || { echo "STOP: unit already sets EnvironmentFiles=" >&2; exit 1; }
test -z "$(systemctl show -p ExecStop --value celery.service)" || { echo "STOP: ExecStop present" >&2; exit 1; }
test -z "$(systemctl show -p ExecStopPost --value celery.service)" || { echo "STOP: ExecStopPost present" >&2; exit 1; }
test -n "$(systemctl show -p ExecStart --value celery.service)" || { echo "STOP: no ExecStart" >&2; exit 1; }
test "$(systemctl show -p User --value celery.service)" = "scrapper" || { echo "STOP: unexpected User" >&2; exit 1; }
test "$(systemctl show -p WorkingDirectory --value celery.service)" = "$RUNTIME_CWD" || { echo "STOP: unexpected WorkingDirectory" >&2; exit 1; }
test -z "$(systemctl show -p DropInPaths --value celery.service)" || { echo "STOP: unexpected drop-in(s) already present" >&2; exit 1; }
test "$(systemctl show -p WatchdogUSec --value celery.service)" = "0" || { echo "STOP: unexpected watchdog" >&2; exit 1; }
test "$(systemctl show -p Restart --value celery.service)" = "always" || { echo "STOP: unexpected Restart policy" >&2; exit 1; }
KILLSIGNAL_NOW="$(systemctl show -p KillSignal --value celery.service)"
case "$KILLSIGNAL_NOW" in
  15|SIGTERM) echo "policy: killsignal=$KILLSIGNAL_NOW (numeric 15 per systemd)" ;;
  *) echo "STOP: KillSignal is neither 15 nor SIGTERM" >&2; exit 1 ;;
esac
test "$(systemctl show -p KillMode --value celery.service)" = "control-group" || { echo "STOP: unexpected current KillMode; re-derive the stop plan" >&2; exit 1; }
test "$(systemctl show -p SendSIGKILL --value celery.service)" = "yes" || { echo "STOP: unexpected current SendSIGKILL" >&2; exit 1; }
echo "policy: active=$(systemctl show -p ActiveState --value celery.service) sub=$(systemctl show -p SubState --value celery.service) mainpid=$(systemctl show -p MainPID --value celery.service) restarts=$(systemctl show -p NRestarts --value celery.service)"
echo "policy: timeoutstop_us=$(systemctl show -p TimeoutStopUSec --value celery.service) sendhup=$(systemctl show -p SendSIGHUP --value celery.service)"
```

Facts that must be re-proved live, not assumed: the `Environment=` assertion is deliberately
**strict — it requires the property to be empty**. If this unit legitimately presets something
such as `PATH`, the check STOPs: that is fail-closed by design and is reported as a blocked
precondition, **not** as readiness. `systemctl` reports `KillSignal` as a **numeric** signal
(`15`), so the current-policy assert accepts `15` or `SIGTERM` and nothing else;
`WatchdogUSec=0`, `Restart=always`, `SendSIGKILL=yes`, `KillMode=control-group`, and **zero**
`DropInPaths` are all asserted, not merely printed. `TimeoutStopUSec` is the real property;
`TimeoutStopSec` is a display alias and is not compared.

## 4. G2 — env packaging (MANUAL-ENV-01) — **BLOCKED**, procedure now exact

Owner-only, in-process, allowlist extraction from the known edge env
`/home/scrapper/bdt_dashboard-scrap-result-edge-stage-01/.env`. Values are never printed;
only key names and metadata. This package does **not** run it now (no env read authorised).

Allowlist (keys the worker settings actually read): `SECRET_KEY`, `DEBUG`,
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
`DB_PORT`. Forbidden: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `BROKER_URL`,
`REDIS_URL`, `CHANNEL_LAYERS`, `DJANGO_SERVE_STATIC` (ASGI/UI-only). Broker/backend are
hardcoded in `settings.py` and are not env-driven.


The extraction module performs **no ownership or mode operation at all**: it creates the
staging file `0600` from birth via `mkstemp`, validates, reads back, and atomically renames.
`chown root:scrapper` / `chmod 0640` are the **final shell step**, run only in the future
root session. The module's own root precondition is `os.geteuid() == 0`.

Offline exercise: `tests/check_worker_operator.py` (a stdlib harness **plus** an integration
step that imports the locally installed `python-dotenv`) AST-extracts this module, executes
it against **synthetic** files in a temp directory with `os.geteuid`/`os.chown`/`os.chmod`
**mocked** and synthetic `sys.argv`, and asserts the calls the code would make. It never
reads a real env, never touches `/etc/cars-dashboard`, and needs no privilege. Signing/DB
identity stay **G6** gates (booleans/identity only; never values, hashes, prefixes).

```bash
set -euo pipefail
[ -n "${PYBIN:-}" ] && [ -n "${ENV_DIR:-}" ] && [ -n "${ENV_FILE:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
test "$(id -u)" = "0" || { echo "STOP: env packaging is a root-only step" >&2; exit 1; }
SRC_ENV=/home/scrapper/bdt_dashboard-scrap-result-edge-stage-01/.env
test -f "$SRC_ENV" || { echo "STOP: source env absent" >&2; exit 1; }
test ! -L "$SRC_ENV" || { echo "STOP: source env is a symlink; refuse" >&2; exit 1; }
test -r "$SRC_ENV" || { echo "STOP: source env unreadable" >&2; exit 1; }
test ! -e "$ENV_DIR" || { echo "STOP: target env dir already exists" >&2; exit 1; }
install -d -o root -g scrapper -m 0750 "$ENV_DIR"
"$PYBIN" -B - "$SRC_ENV" "$ENV_FILE" <<'PY'
import os, sys, tempfile
from pathlib import Path
from dotenv import dotenv_values, set_key

ALLOW = ["SECRET_KEY", "DEBUG", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS",
         "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"]
src, dst = Path(sys.argv[1]), Path(sys.argv[2])

def fail(msg):
    sys.exit("STOP: " + msg)          # fixed strings only, never a value

if os.geteuid() != 0:
    fail("packaging must run as root")
# The source is opened read-only by dotenv_values; it is never written.
if src.is_symlink() or not src.is_file():
    fail("source env is not a regular non-symlink file")

# Validate EVERYTHING before a single byte of output exists.
try:
    vals = dotenv_values(src, interpolate=False)
except Exception:
    fail("source parse failed")
if not vals:
    fail("source defines no bindings")
missing = [k for k in ALLOW if vals.get(k) in (None, "")]
if missing:
    fail("allowlisted keys absent: " + ", ".join(missing))
for key in ALLOW:
    if "${" in vals[key]:
        fail("%s contains an interpolation marker" % key)
expected = {k: vals[k] for k in ALLOW}

# Private file from birth: mkstemp creates it 0600, no predictable name, no reuse.
fd, tmp = tempfile.mkstemp(dir=str(dst.parent), prefix=".worker.env.", suffix=".tmp")
os.close(fd)
try:
    for key in ALLOW:
        set_key(tmp, key, expected[key], quote_mode="always")
    # Read back through the same parser the loader uses (interpolate default True):
    # a ${} marker written downstream would show up as a difference here too.
    written = dotenv_values(tmp)
    if set(written) != set(ALLOW):
        fail("written key set differs from the allowlist")
    for key in ALLOW:
        if written.get(key) != expected[key]:
            fail("%s did not round-trip through the dotenv parser" % key)
    if any(k in written for k in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND",
                                  "BROKER_URL", "REDIS_URL", "CHANNEL_LAYERS",
                                  "DJANGO_SERVE_STATIC")):
        fail("forbidden key present in output")
except SystemExit:
    os.unlink(tmp)
    raise
except Exception:
    os.unlink(tmp)
    fail("packaging failed while writing")
if dst.exists() or dst.is_symlink():
    os.unlink(tmp)
    fail("target already exists")
os.rename(tmp, dst)                   # atomic, same directory; mode stays 0600
print("packaged %d keys (names only; no values printed)" % len(ALLOW))
PY
test ! -L "$ENV_FILE" || { echo "STOP: env file is a symlink" >&2; exit 1; }
test -f "$ENV_FILE" || { echo "STOP: env file missing" >&2; exit 1; }
# Final metadata step: root-only, separate from the module, outside its write path.
test "$(id -u)" = "0" || { echo "STOP: metadata step is root-only" >&2; exit 1; }
chown root:scrapper "$ENV_FILE"
chmod 0640 "$ENV_FILE"
test "$(stat -c '%U:%G' "$ENV_DIR")" = "root:scrapper" || { echo "STOP: env dir owner" >&2; exit 1; }
test "$(stat -c '%a' "$ENV_DIR")" = "750" || { echo "STOP: env dir mode" >&2; exit 1; }
test "$(stat -c '%U:%G' "$ENV_FILE")" = "root:scrapper" || { echo "STOP: env file owner" >&2; exit 1; }
test "$(stat -c '%a' "$ENV_FILE")" = "640" || { echo "STOP: env file mode" >&2; exit 1; }
echo "packaged: allowlist validated before write, readback matched, metadata applied last"
```

No byte of output exists until every key has been validated, so a missing key or an
interpolation marker aborts with **no final file**. Exceptions are caught and reported
through `fail()` with fixed strings only. The tested error paths emitted only fixed text with
no value content; this is **not** an absolute guarantee about every possible
`python-dotenv` diagnostic (pinned version is `1.0.1`; its parser warnings cite line numbers,
not values). The renamed file is `0600` until the shell's final `chown root:scrapper` /
`chmod 0640`, which is the only step that needs ownership change and is therefore kept out
of the module.

The offline fixture runs the module with `os.geteuid` **mocked to return 0** — that is a unit
harness condition, **not** an OS-privilege bypass and **not** a root acceptance test. It
proves the guard exists and that no ownership call is made; it proves nothing about running
with real privilege.

## 5. G3 — producer quiesce — **BLOCKED**

Bounded AST inventory of the two app roots: **seven enqueue sites, five flows**, all in
`dashboard/views.py`: `views.py:644` (NULL Inspector), `views.py:647` (Ambiguous Resolver),
`views.py:1072` (insert-missing execute), `views.py:1195` (fill execute), `views.py:1248`
(fill again), `views.py:1294` and `views.py:1297` (jobs/start). Real runs are additionally
source-blocked at `views.py:1272-1277` — a source guard, not a runtime quiesce proof.

These five flows are **not** all producers: admin autodiscovery, cron, sync containers,
other hosts, and any consumer outside the inspected roots are **unknown**. Stopping the UI
unit is therefore **not** accepted as proof. No executable "pause" configuration is
invented here. Incomplete or ambiguous producer inventory ⇒ **fail closed, record an
explicit blocked precondition, STOP**; producers stay paused for the window.

## 6. G4/S5 — temporal reconciliation: embedded raw client, counts only

No `celery` CLI, no `-A <app>` (that imports Django settings), no payload/args/results, no
key dumps. A raw, target-limited Celery client queries the **pinned destination only**;
broker/result literals and the absence of custom transport options are proven from the
settings **AST** (parsed via `ast.walk`, never imported). Priority keys are built from
Kombu's own `priority_steps`/`sep` objects, never typed by hand. Timeouts: inspect 3 s,
broker connect 5 s, socket connect/read 5 s, outer wall 30 s.

```bash
set -euo pipefail
[ -n "${PYBIN:-}" ] && [ -n "${LEGACY_SETTINGS:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
timeout 30s "$PYBIN" -B - "$LEGACY_SETTINGS" <<'PY'
import ast, sys, time
PINNED_BROKER = "redis://localhost:6379/0"
DEST = "celery@scrapper"
TIMEOUT, CONNECT, SOCKET, WALL = 3.0, 5.0, 5.0, 25.0

tree = ast.parse(open(sys.argv[1], encoding="utf-8").read())
literals, banned = {}, []
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            name = getattr(target, "id", None)
            if name in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    literals[name] = node.value.value
            if name and "transport_options" in name.lower():
                banned.append(name)
    if isinstance(node, ast.keyword) and node.arg and "transport_options" in node.arg:
        banned.append(node.arg)
if banned:
    sys.exit("STOP: custom transport options present: %s" % ", ".join(sorted(set(banned))))
if literals.get("CELERY_BROKER_URL") != PINNED_BROKER:
    sys.exit("STOP: broker literal is not the pinned contract value")
if literals.get("CELERY_RESULT_BACKEND") != PINNED_BROKER:
    sys.exit("STOP: result backend literal is not the pinned contract value")

start = time.monotonic()
from celery import Celery
probe = Celery("worker_alignment_probe", broker=PINNED_BROKER,
               backend=None, set_as_current=False)
probe.conf.broker_connection_retry_on_startup = False
# Bound the connection phase itself, not just the reply wait.
probe.conf.broker_connection_timeout = CONNECT
probe.conf.broker_transport_options = {"socket_timeout": SOCKET,
                                       "socket_connect_timeout": SOCKET}
inspect = probe.control.inspect(destination=[DEST], timeout=TIMEOUT)
for kind in ("active", "reserved", "scheduled"):
    if time.monotonic() - start > WALL:
        sys.exit("STOP: wall clock exceeded before %s" % kind)
    reply = getattr(inspect, kind)()
    if not reply:
        sys.exit("STOP: no reply to inspect %s (destination %s)" % (kind, DEST))
    if DEST not in reply:
        sys.exit("STOP: destination %s absent from %s reply" % (DEST, kind))
    items = reply[DEST]
    if not isinstance(items, list):
        sys.exit("STOP: unexpected %s reply shape" % kind)
    print("%s=%d" % (kind, len(items)))

from kombu.transport import redis as kbredis
sep = kbredis.Channel.sep
steps = list(kbredis.Channel.priority_steps)
keys = ["celery"] + [("celery" + sep + str(s)) for s in steps if s]
import redis
client = redis.Redis(host="127.0.0.1", port=6379, db=0,
                     socket_timeout=SOCKET, socket_connect_timeout=SOCKET)
total = 0
for key in keys:
    length = client.llen(key)
    total += length
    print("queue_len_prio_%s=%d" % (key.rsplit(sep, 1)[-1] if sep in key else "0", length))
print("queue_total=%d" % total)
print("unacked_hlen=%d" % client.hlen("unacked"))
print("unacked_index_zcard=%d" % client.zcard("unacked_index"))
print("transport_default_visibility_timeout=%d (library default, NOT effective config)"
      % kbredis.Channel.visibility_timeout)
PY
```

`queue_total=0` is **not** a drain proof: it is a non-atomic snapshot taken while producers
are in an unknown state. Task **origin** and effective **visibility timeout** remain
**required and unresolved** ⇒ if they cannot be established authoritatively, or counts are
inconsistent, or any reply is absent ⇒ **STOP**. Repeated approved observations plus the
producer pause are prerequisites, not substitutes. **Never purge, replay, revoke-retry, or
restart to clear a queue.** Celery control RPC publishes ephemeral control/reply traffic
(approved separately); it is not business enqueue and does not prove "zero broker writes".

## 7. G5 — `REMAP_SIGTERM` — **BLOCKED** (before any stop)

Celery `5.5.3` SIGTERM is **warm** unless `REMAP_SIGTERM == "SIGQUIT"`. Evidence is
**PARTIAL**: absent from the initial `/proc` environment, the known legacy dotenv, a runtime
`.env` (absent), and `settings.py` literals — but post-import `os.environ` mutation was never
exhaustively proven, so `/proc` observation is **not authoritative**. This package provides
**no** process instrumentation (no ptrace/gdb/injection). Without owner-proven in-process
authority: warm-vs-cold is unknown ⇒ **STOP before any stop request**. Never stop "to see".

## 8. G6 — signing parity + DB/catalog preflight — **BLOCKED**

UI and worker must present an equal `SECRET_KEY` (preview tokens are signed in the UI and
validated in the worker). Acceptance is **booleans/identity only** — equal/absent, never
values, hashes, prefixes, or lengths. Old preflight proof is **stale**: a new proof is
required, including DB identity `db_fastapi_scrap_stage` / `bdt_stage_owner` /
`127.0.0.1:5432` and the catalog/schema min-requirements. Mismatch ⇒ STOP, never repair.

## 8a. Stop-condition gate: `$RUN_DIR/gates-approved` manifest — machine-checked

Prose is not a gate. Before §9 may run, a **root-private manifest** must exist at the exact
path `$RUN_DIR/gates-approved` (i.e. `<root run dir>/gates-approved`), `root:root 0600`,
regular non-symlink, containing exactly these lines in this order:

```
operator=<operator identity string recorded by the owner>
accepted_utc=<RFC3339 UTC timestamp>
G2=ACCEPTED
G3=ACCEPTED
G4=ACCEPTED
G5=ACCEPTED
G6=ACCEPTED
evidence_dir=<absolute path holding the owner's accepted evidence>
```

This is **owner acceptance recorded**, not cryptography — no signature or hash chain is
claimed, and `accepted_utc` is a recorded string, not a parsed/validated timestamp. It may be
created **only after** the owner has separately reviewed and accepted the evidence for G2–G6
(env packaging, producer pause, authoritative origin/visibility-timeout, post-import REMAP
authority, new signing/DB proof). **This package deliberately supplies no command to
fabricate it**, and any gate still BLOCKED means it must not exist.

`check_accepted_gates()` is the single shared validator. It is **defined here** and called
explicitly in §9 (before the stop window) and again in §10 (immediately before the stop), so
neither site relies on an earlier block having run. It enforces: exact **8-line** key set
(no duplicates, no extras, no missing), `operator=` non-empty, `accepted_utc=` non-empty,
`evidence_dir=` absolute **and** an existing directory, all five gates exactly
`=ACCEPTED`, file `root:root 0600`, regular non-symlink.

```bash
set -euo pipefail
[ -n "${RUN_DIR:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
check_accepted_gates() {
  gate_file="$RUN_DIR/gates-approved"
  test -f "$gate_file" || { echo "STOP: no accepted gate manifest; G2-G6 not accepted" >&2; return 1; }
  test ! -L "$gate_file" || { echo "STOP: gate manifest is a symlink" >&2; return 1; }
  test "$(stat -c '%U:%G' "$gate_file")" = "root:root" || { echo "STOP: gate manifest owner" >&2; return 1; }
  test "$(stat -c '%a' "$gate_file")" = "600" || { echo "STOP: gate manifest mode" >&2; return 1; }
  # Exact key set/count and value shape; stdlib only, nothing is printed.
  python3 -B - "$gate_file" <<'PY' || return 1
import os, sys
path = sys.argv[1]
try:
    raw = open(path, encoding="utf-8").read()
except OSError:
    sys.exit("STOP: gate manifest unreadable")
lines = [ln for ln in raw.splitlines() if ln != ""]
if len(lines) != 8:
    sys.exit("STOP: gate manifest must have exactly 8 non-empty lines")
keys = [ln.split("=", 1)[0] for ln in lines if "=" in ln]
expected = ["operator", "accepted_utc", "G2", "G3", "G4", "G5", "G6", "evidence_dir"]
if keys != expected:
    sys.exit("STOP: gate manifest key set/order is not the accepted contract")
values = dict(ln.split("=", 1) for ln in lines if "=" in ln)
if not values["operator"].strip():
    sys.exit("STOP: operator= is empty")
if not values["accepted_utc"].strip():
    sys.exit("STOP: accepted_utc= is empty")
for gate in ("G2", "G3", "G4", "G5", "G6"):
    if values[gate] != "ACCEPTED":
        sys.exit("STOP: gate %s is not ACCEPTED" % gate)
evidence = values["evidence_dir"]
if not evidence.startswith("/") or not os.path.isdir(evidence):
    sys.exit("STOP: evidence_dir is not an existing absolute directory")
PY
  echo "gates: G2-G6 owner-accepted manifest validated at $gate_file"
}
check_accepted_gates
```

## 8b. Privileged-path review gate (unavoidable TOCTOU)

The live settings directory `/home/scrapper/bdt_dashboard-scrap-result/car_ads_dashboard/`
is writable by the service user, so a root patch-and-rename into it is **not race-proof**:
the parent path could be swapped between the hash check and the rename. This cannot be fixed
from inside this package, so it is an explicit accepted-risk record.

Exactly **one** option is implemented: the owner records acceptance of the trusted runtime in
a root-private file at the exact path `$RUN_DIR/privileged-path-approved`, regular
non-symlink, `root:root 0600`, whose entire content is exactly the single constant line

```
trusted-runtime-accepted
```

A service-user-patch option is **not** implemented here (it would need a different privilege
model); do not invent one. No command to create this file is supplied. It is read and
verified before §12, and its absence, wrong owner/mode/symlink, or any other content ⇒ STOP.

```bash
set -euo pipefail
[ -n "${RUN_DIR:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
PRIV_FILE="$RUN_DIR/privileged-path-approved"
test -f "$PRIV_FILE" || { echo "STOP: privileged-path acceptance not recorded" >&2; exit 1; }
test ! -L "$PRIV_FILE" || { echo "STOP: privileged-path record is a symlink" >&2; exit 1; }
test "$(stat -c '%U:%G' "$PRIV_FILE")" = "root:root" || { echo "STOP: privileged-path record owner" >&2; exit 1; }
test "$(stat -c '%a' "$PRIV_FILE")" = "600" || { echo "STOP: privileged-path record mode" >&2; exit 1; }
test "$(cat "$PRIV_FILE")" = "trusted-runtime-accepted" || { echo "STOP: privileged-path record content is not the accepted constant" >&2; exit 1; }
echo "privileged path: trusted-runtime-accepted (accepted risk; not a race proof)"
```

No claim of race-proofness is made. The gate is satisfied only by this explicit recorded
choice; silence ⇒ STOP.

## 9. Safe-stop policy: verify → install (worker still running)

```bash
set -euo pipefail
[ -n "${UNIT_FILE:-}" ] && [ -n "${DROPIN_DIR:-}" ] && [ -n "${RUN_DIR:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
# systemd-analyze diagnostics can quote Environment=/ExecStart= content, so the
# captured text is NEVER printed: only a fixed verdict message is emitted.
verify_unit() {
  if out="$(systemd-analyze verify "$UNIT_FILE" 2>&1)"; then rc=0; else rc=$?; fi
  if [ "$rc" -ne 0 ]; then
    echo "STOP: systemd-analyze verify failed rc=$rc (output suppressed: may contain secrets)" >&2
    return 1
  fi
  if [ -n "$out" ]; then
    echo "STOP: systemd-analyze verify emitted diagnostics (output suppressed: may contain secrets)" >&2
    return 1
  fi
  return 0
}
# Re-check the accepted-gate manifest right here: §9 must not depend on an
# earlier block having run.
check_accepted_gates
verify_unit
test "$(systemctl show -p TimeoutStopUSec --value celery.service)" != "infinity" || { echo "STOP: safe-stop already partially applied" >&2; exit 1; }
test ! -e "$DROPIN_DIR/10-worker-safe-stop.conf" || { echo "STOP: safe-stop drop-in already exists" >&2; exit 1; }
test ! -L "$DROPIN_DIR/10-worker-safe-stop.conf" || { echo "STOP: dangling symlink at drop-in path" >&2; exit 1; }
install -d -o root -g root -m 0755 "$DROPIN_DIR"
install -o root -g root -m 0644 "$RUN_DIR/10-safe-stop.conf" "$DROPIN_DIR/10-worker-safe-stop.conf"
systemctl daemon-reload
verify_unit
KILLSIGNAL_AFTER="$(systemctl show -p KillSignal --value celery.service)"
case "$KILLSIGNAL_AFTER" in
  15|SIGTERM) echo "safe_stop: killsignal=$KILLSIGNAL_AFTER" ;;
  *) echo "STOP: KillSignal is neither 15 nor SIGTERM" >&2; exit 1 ;;
esac
test "$(systemctl show -p KillMode --value celery.service)" = "mixed" || { echo "STOP: KillMode not effective" >&2; exit 1; }
test "$(systemctl show -p SendSIGKILL --value celery.service)" = "no" || { echo "STOP: SendSIGKILL not effective" >&2; exit 1; }
test "$(systemctl show -p TimeoutStopUSec --value celery.service)" = "infinity" || { echo "STOP: TimeoutStopUSec not infinity" >&2; exit 1; }
echo "safe-stop installed; stop may wait indefinitely (no deadline, no OOM protection)"
```

`systemd-analyze verify` returning 0 is **not** sufficient — all stdout **and** stderr must
be empty, otherwise STOP. Its captured output is **never printed**, not even truncated:
diagnostics can quote `Environment=`/`ExecStart=` values that may carry secrets. The
operator sees only a fixed verdict message; if the raw text is needed, it is read from the
private journal/log by the owner, never echoed by this package. `KillSignal` is compared as
systemd reports it (**numeric `15`**), never as the literal string `SIGTERM` only. An
existing or dangling-conflicting drop-in ⇒ STOP (never overwrite/merge).

## 10. Stop: capture cgroup BEFORE, prove the whole cgroup empty after

`systemd` clears `ControlGroup` once inactive, so the cgroup path **must** be captured while
running. `/sys/fs/cgroup/.../cgroup.procs` is a pseudo-file with stat size `0` even when it
lists processes — `test -s` is therefore **wrong**; membership is read as **lines**, plus
the hierarchical `populated` flag from `cgroup.events`.

```bash
set -euo pipefail
[ -n "${RUNTIME_CWD:-}" ] && [ -n "${RUN_DIR:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
test -n "${OPERATOR_OBSERVATION_SECONDS:-}" || { echo "STOP: OPERATOR_OBSERVATION_SECONDS not agreed/persisted" >&2; exit 1; }
case "$OPERATOR_OBSERVATION_SECONDS" in
  ''|*[!0-9]*) echo "STOP: OPERATOR_OBSERVATION_SECONDS must be a positive integer" >&2; exit 1 ;;
esac
test "$OPERATOR_OBSERVATION_SECONDS" -gt 0 || { echo "STOP: observation window must be positive" >&2; exit 1; }
# Shared validator from §8a, called explicitly here: full key-set/owner/mode recheck.
check_accepted_gates
test "$(systemctl is-active celery.service)" = "active" || { echo "STOP: worker not active before stop" >&2; exit 1; }
CG="$(systemctl show -p ControlGroup --value celery.service)"
test -n "$CG" || { echo "STOP: ControlGroup unknown before stop" >&2; exit 1; }
test "$CG" = "/system.slice/celery.service" || { echo "STOP: unexpected ControlGroup path" >&2; exit 1; }
CG_PATH="/sys/fs/cgroup$CG"
test -d "$CG_PATH" || { echo "STOP: cgroup path missing before stop" >&2; exit 1; }
test -f "$CG_PATH/cgroup.events" || { echo "STOP: cgroup.events missing before stop" >&2; exit 1; }
populated_pre="$(awk '$1=="populated"{print $2}' "$CG_PATH/cgroup.events")"
test "$populated_pre" = "1" || { echo "STOP: cgroup not populated before stop; state contradicts an active worker" >&2; exit 1; }
MAINPID_BEFORE="$(systemctl show -p MainPID --value celery.service)"
test "$MAINPID_BEFORE" != "0" || { echo "STOP: MainPID 0 while active" >&2; exit 1; }
RESTARTS_BEFORE="$(systemctl show -p NRestarts --value celery.service)"
echo "pre_stop: cgroup=$CG_PATH mainpid=$MAINPID_BEFORE restarts=$RESTARTS_BEFORE window=${OPERATOR_OBSERVATION_SECONDS}s"
systemctl stop --no-block celery.service
DEADLINE=$((SECONDS + OPERATOR_OBSERVATION_SECONDS))
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  state="$(systemctl show -p ActiveState --value celery.service)"
  if [ "$state" = "inactive" ]; then break; fi
  sleep 5
done
test "$(systemctl show -p ActiveState --value celery.service)" = "inactive" || { echo "STOP: not inactive within the agreed window; see abort §11" >&2; exit 1; }
test "$(systemctl show -p SubState --value celery.service)" = "dead" || { echo "STOP: SubState not dead" >&2; exit 1; }
test "$(systemctl show -p MainPID --value celery.service)" = "0" || { echo "STOP: MainPID not 0" >&2; exit 1; }
test "$(systemctl show -p NRestarts --value celery.service)" = "$RESTARTS_BEFORE" || { echo "STOP: restart counter changed" >&2; exit 1; }
if [ -d "$CG_PATH" ]; then
  populated="$(awk '$1=="populated"{print $2}' "$CG_PATH/cgroup.events")" || { echo "STOP: cannot read cgroup.events" >&2; exit 1; }
  test "$populated" = "0" || { echo "STOP: cgroup still populated=$populated" >&2; exit 1; }
  procs="$(wc -l < "$CG_PATH/cgroup.procs")" || { echo "STOP: cannot read cgroup.procs" >&2; exit 1; }
  test "$procs" -eq 0 || { echo "STOP: cgroup.procs nonempty=$procs (orphans)" >&2; exit 1; }
else
  echo "cgroup dir absent after verified known path and dead state (safe absence)"
fi
sleep 15
test "$(systemctl show -p ActiveState --value celery.service)" = "inactive" || { echo "STOP: autorestarter re-entered" >&2; exit 1; }
test "$(systemctl show -p MainPID --value celery.service)" = "0" || { echo "STOP: new MainPID appeared" >&2; exit 1; }
echo "stopped: entire cgroup empty, no autorestart"
```

`OPERATOR_OBSERVATION_SECONDS` is a **human-agreed, persisted** positive integer set once in
the session context (§1) before the stop; it is an observation window, **not** a signal and
**not** a kill deadline — the drop-in's `TimeoutStopSec=infinity` means the unit may stay
`deactivating` indefinitely. There is no invented default: if it is unset, the stop does not
proceed. Read errors, a not-populated cgroup while the unit claims `active`, or an unknown
`CG_PATH` ⇒ STOP (never "assume empty").

## 11. Manual abort of an indefinite wait (human decision, never a signal)

- **Keep producers paused.** Do not retarget, start, or kill anything.
- The observation deadline is a **human agreement**; record timestamps, `MainPID`, cgroup
  membership, and `systemd` state as evidence.
- Cancelling the `systemctl stop` **client** (Ctrl-C) does **not** cancel the job systemd
  already started and does **not** restore the worker; the unit stays `deactivating`.
- **No force kill** (`kill -9`/`pkill`/`killall`), no `SendSIGKILL=yes`, no
  `systemctl restart` to break the wait, no invented process instrumentation.
- Escalate to the owner with evidence, leave producers paused, **STOP**. Continuing needs a
  new, separately approved decision.

## 12. Apply patched settings while proven stopped (atomic)

```bash
set -euo pipefail
[ -n "${LEGACY_SETTINGS:-}" ] && [ -n "${RUN_DIR:-}" ] && [ -n "${BACKUP:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
test "$(systemctl is-active celery.service)" = "inactive" || { echo "STOP: worker not inactive" >&2; exit 1; }
test "$(systemctl show -p SubState --value celery.service)" = "dead" || { echo "STOP: SubState not dead" >&2; exit 1; }
# §8b accepted-risk record must be present before any privileged path write.
PRIV_FILE="$RUN_DIR/privileged-path-approved"
test -f "$PRIV_FILE" && test ! -L "$PRIV_FILE" || { echo "STOP: privileged-path acceptance not recorded" >&2; exit 1; }
test "$(stat -c '%U:%G' "$PRIV_FILE")" = "root:root" || { echo "STOP: privileged-path record owner" >&2; exit 1; }
test "$(stat -c '%a' "$PRIV_FILE")" = "600" || { echo "STOP: privileged-path record mode" >&2; exit 1; }
test "$(cat "$PRIV_FILE")" = "trusted-runtime-accepted" || { echo "STOP: privileged-path record content" >&2; exit 1; }
test -f "$BACKUP" && test ! -L "$BACKUP" || { echo "STOP: verified backup context missing" >&2; exit 1; }
test "$(sha256sum "$BACKUP" | cut -d' ' -f1)" = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c" || { echo "STOP: backup hash mismatch" >&2; exit 1; }
test "$(sha256sum "$LEGACY_SETTINGS" | cut -d' ' -f1)" = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c" || { echo "STOP: live settings not baseline" >&2; exit 1; }
SETTINGS_DIR="$(dirname "$LEGACY_SETTINGS")"
TMP_OUT="$(mktemp "$SETTINGS_DIR/.worker-align.XXXXXXXX")"
trap 'rm -f "$TMP_OUT"' EXIT
patch --dry-run -s -o /dev/null "$LEGACY_SETTINGS" "$RUN_DIR/settings-legacy-dotenv.patch"
patch -s -o "$TMP_OUT" "$LEGACY_SETTINGS" "$RUN_DIR/settings-legacy-dotenv.patch"
test "$(sha256sum "$TMP_OUT" | cut -d' ' -f1)" = "72e8ee73aa2c914f2defc22257b8c05584bb10a909b25d5a0f3c920b52a12b48" || { echo "STOP: patched hash mismatch" >&2; exit 1; }
chown --reference="$LEGACY_SETTINGS" "$TMP_OUT"
chmod --reference="$LEGACY_SETTINGS" "$TMP_OUT"
stat -c 'tmp mode=%a owner=%U:%G' "$TMP_OUT"
mv -f "$TMP_OUT" "$LEGACY_SETTINGS"
trap - EXIT
test "$(sha256sum "$LEGACY_SETTINGS" | cut -d' ' -f1)" = "72e8ee73aa2c914f2defc22257b8c05584bb10a909b25d5a0f3c920b52a12b48" || { echo "STOP: post-move hash mismatch" >&2; exit 1; }
echo "settings patched atomically (ownership/mode preserved)"
```

`mktemp` in the settings directory (same filesystem, so `mv` is atomic) avoids the old
predictable-path `rm -f` that could have deleted an operator's file or followed a symlink.
Only the file created by `mktemp` is ever removed.

## 13. Install the selector drop-in (still stopped), verify without dumping env

```bash
set -euo pipefail
[ -n "${DROPIN_DIR:-}" ] && [ -n "${ENV_FILE:-}" ] && [ -n "${UNIT_FILE:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
test "$(systemctl is-active celery.service)" = "inactive" || { echo "STOP: worker not inactive" >&2; exit 1; }
test -f "$ENV_FILE" && test ! -L "$ENV_FILE" || { echo "STOP: packaged env missing or symlink" >&2; exit 1; }
test ! -e "$DROPIN_DIR/20-worker-env.conf" || { echo "STOP: selector drop-in already exists" >&2; exit 1; }
test ! -L "$DROPIN_DIR/20-worker-env.conf" || { echo "STOP: dangling symlink at selector path" >&2; exit 1; }
CONF_TMP="$(mktemp "$RUN_DIR/20-worker-env.XXXXXXXX")"
trap 'rm -f "$CONF_TMP"' EXIT
printf '%s\n' '[Service]' "Environment=DASHBOARD_DOTENV_PATH=$ENV_FILE" > "$CONF_TMP"
test "$(sha256sum "$CONF_TMP" | cut -d' ' -f1)" = "$(printf '%s\n' '[Service]' "Environment=DASHBOARD_DOTENV_PATH=$ENV_FILE" | sha256sum | cut -d' ' -f1)" || { echo "STOP: drop-in content mismatch" >&2; exit 1; }
install -o root -g root -m 0644 "$CONF_TMP" "$DROPIN_DIR/20-worker-env.conf"
trap - EXIT
rm -f "$CONF_TMP"
systemctl daemon-reload
# Same shared helper as §9: captured diagnostics are never printed.
verify_unit
if systemctl show -p Environment --value celery.service | grep -qF -- "DASHBOARD_DOTENV_PATH=$ENV_FILE"; then echo "selector_present=true"; else echo "STOP: selector absent from effective environment" >&2; exit 1; fi
test -z "$(systemctl show -p EnvironmentFiles --value celery.service)" || { echo "STOP: EnvironmentFile appeared" >&2; exit 1; }
echo "selector installed; effective unit environment asserted by fixed-string test only"
```

The assertion uses `grep -qF` so the raw `Environment` value is **never printed** — it may
contain secrets set by other drop-ins. The drop-in content is a known constant, created
root-owned and hash-checked before install, and installed only with `test ! -e`.

## 14. Start (separate approval) and readback

```bash
set -euo pipefail
[ -n "${RUNTIME_CWD:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
RESTARTS_PRE="$(systemctl show -p NRestarts --value celery.service)"
systemctl start celery.service
test "$(systemctl is-active celery.service)" = "active" || { echo "STOP: worker not active after start" >&2; exit 1; }
test "$(systemctl show -p SubState --value celery.service)" = "running" || { echo "STOP: SubState not running" >&2; exit 1; }
test "$(systemctl show -p NRestarts --value celery.service)" = "$RESTARTS_PRE" || { echo "STOP: restart counter changed after start" >&2; exit 1; }
test "$(systemctl show -p WorkingDirectory --value celery.service)" = "$RUNTIME_CWD" || { echo "STOP: cwd drifted" >&2; exit 1; }
echo "started: mainpid=$(systemctl show -p MainPID --value celery.service) restarts=$(systemctl show -p NRestarts --value celery.service)"
```

A failed start is a **STOP for diagnosis**; never blind-restart. The stop and this start may
be covered by a single explicit approval that names both actions (see §16); an approval
covering only the stop does not authorise the start.

## 15. Rollback — phase-specific (decide the phase first, then run only that block)

**R1 — no worker source/unit changed yet (before §9).** No restore is needed or performed.
Isolated env artifacts (§4) may already exist: **retain them as private evidence, do not
delete**; staged/root artifacts are evidence too.
**R2 — safe-stop installed, worker still RUNNING.** Do **not** stop the worker to roll back.
Retain the safe-stop drop-in, record it, abort the window, report. Removing the policy while
running is out of scope; removing it while stopping is forbidden.
**R3 — stopped, settings patched, no job activity.** Assert stopped and empty **before** the
restore, restore atomically from the verified backup, then remove only this package's own
artifacts (hash-matched, non-symlink). Never remove safe-stop until stopped.

```bash
set -euo pipefail
[ -n "${LEGACY_SETTINGS:-}" ] && [ -n "${BACKUP:-}" ] && [ -n "${DROPIN_DIR:-}" ] && [ -n "${RUN_DIR:-}" ] || { echo "STOP: shared context missing" >&2; exit 1; }
test "$(systemctl is-active celery.service)" = "inactive" || { echo "STOP: rollback refused, worker not inactive" >&2; exit 1; }
test "$(systemctl show -p SubState --value celery.service)" = "dead" || { echo "STOP: rollback refused, SubState not dead" >&2; exit 1; }
test "$(systemctl show -p MainPID --value celery.service)" = "0" || { echo "STOP: rollback refused, MainPID not 0" >&2; exit 1; }
# The cgroup path must come from the stop block's captured context; systemd has
# already cleared ControlGroup, so re-deriving it here would silently compare
# against an empty string.
test -n "${CG_PATH:-}" || { echo "STOP: cgroup path unknown in context; cannot prove empty" >&2; exit 1; }
if [ -d "$CG_PATH" ]; then
  test -f "$CG_PATH/cgroup.events" || { echo "STOP: cgroup.events unreadable" >&2; exit 1; }
  populated="$(awk '$1=="populated"{print $2}' "$CG_PATH/cgroup.events")"
  test "$populated" = "0" || { echo "STOP: cgroup still populated=$populated" >&2; exit 1; }
  procs="$(wc -l < "$CG_PATH/cgroup.procs")"
  test "$procs" -eq 0 || { echo "STOP: cgroup.procs nonempty=$procs" >&2; exit 1; }
else
  echo "cgroup dir absent after verified path (safe absence)"
fi
test -f "$BACKUP" && test ! -L "$BACKUP" || { echo "STOP: verified backup missing" >&2; exit 1; }
test "$(sha256sum "$BACKUP" | cut -d' ' -f1)" = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c" || { echo "STOP: backup hash mismatch" >&2; exit 1; }
RESTORE_TMP="$(mktemp "$(dirname "$LEGACY_SETTINGS")/.worker-align.restore.XXXXXXXX")"
trap 'rm -f "$RESTORE_TMP"' EXIT
install -o root -g root -m 0600 "$BACKUP" "$RESTORE_TMP"
test "$(sha256sum "$RESTORE_TMP" | cut -d' ' -f1)" = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c" || { echo "STOP: restored bytes hash mismatch" >&2; exit 1; }
chown --reference="$LEGACY_SETTINGS" "$RESTORE_TMP"
chmod --reference="$LEGACY_SETTINGS" "$RESTORE_TMP"
mv -f "$RESTORE_TMP" "$LEGACY_SETTINGS"
trap - EXIT
test "$(sha256sum "$LEGACY_SETTINGS" | cut -d' ' -f1)" = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c" || { echo "STOP: baseline not restored" >&2; exit 1; }
# Expected content hashes for the two artifacts this package owns, derived from
# the root-owned verified sources (never from whatever is currently installed).
SAFE_STOP_SHA="79aaa3e7abba876f8cb367666c9eda5b7adfc97c01e48ac6c3066a995c25a69f"
ENV_CONF_SHA="$(printf '%s\n' '[Service]' "Environment=DASHBOARD_DOTENV_PATH=/etc/cars-dashboard/worker.env" | sha256sum | cut -d' ' -f1)"
remove_owned() {
  path="$1"; want="$2"
  if [ -L "$path" ]; then
    echo "STOP: $path is a symlink (dangling or not); refusing to remove" >&2
    return 1
  fi
  if [ ! -e "$path" ]; then
    echo "owned artifact already absent: $path"
    return 0
  fi
  got="$(sha256sum "$path" | cut -d' ' -f1)"
  if [ "$got" != "$want" ]; then
    echo "STOP: $path content hash differs from the expected owned artifact" >&2
    return 1
  fi
  rm -f -- "$path"
  echo "removed owned artifact: $path"
}
remove_owned "$DROPIN_DIR/10-worker-safe-stop.conf" "$SAFE_STOP_SHA"
remove_owned "$DROPIN_DIR/20-worker-env.conf" "$ENV_CONF_SHA"
systemctl daemon-reload
echo "rollback R3 complete: settings baseline restored, only hash-matched owned drop-ins removed"
```

**R4 — after any job write (DB or audit row).** There is **no DB rollback**. Do not delete,
update, purge, replay, or clean up job/audit/business rows. Retain evidence, investigate,
keep producers paused, report unresolved writes as an open finding, **STOP**. No restart if
any write happened. A DB decision is not reopened.

## 16. Shell semantics, forbidden operations, gates

The session is **one dedicated non-interactive `bash -euo pipefail`** that receives the
blocks as script input, so the first failing command aborts the run. Do not paste fragments
into an unrelated interactive shell. Concretely: launch `bash -euo pipefail` and
pipe/heredoc the *selected* blocks into it. The blocks above are **fragments to be selected
and streamed**, not a literal copy-paste-everything transcript — the operator chooses the
blocks for the chosen phase. Every block additionally begins with `set -euo pipefail` and an
explicit `|| { … exit 1; }` guard, so a failed check stops the session even when a fragment
is reused. Use `set +x`; never enable tracing. `verify_unit` treats its own `rc` explicitly
(`if out=$(…); then rc=0; else rc=$?; fi`) rather than relying on `set -e` inside a command
substitution, and it **never prints** the captured diagnostics.

Forbidden anywhere in this package: privilege-escalation prefixes of any kind; purge, replay,
force kill, `systemctl restart|enable|disable|edit|mask|kill`; process instrumentation;
`/proc` environment as REMAP proof; DB mutation/DDL/grants; business enqueue; deploy or
container rebuild; Kong/Nginx/domain change; shared/legacy `.env` edit or whole-env copy;
secret values in output/logs/evidence/docs; a second/staging worker; reopening the DB
decision; normalising a path, alias, case, or source-vs-runtime difference to make a check
pass; removing a drop-in whose content hash does not match the owned artifact.

| Gate | Requirement | State |
|---|---|---|
| G0 | Authority + human root session; transport done out of band | operator-side |
| G1 | Live readback, hashes, drop-in absence re-proven | ready |
| G2 | Env packaging MANUAL-ENV-01 (allowlist, no secret output) | **BLOCKED** |
| G3 | Producer quiesce, complete inventory | **BLOCKED** |
| G4 | Reconciliation, authoritative origin + visibility timeout | **BLOCKED** |
| G5 | Effective `REMAP_SIGTERM` authority | **BLOCKED** |
| G6 | Signing boolean parity + DB/catalog preflight (new proof) | **BLOCKED** |
| G7 | Safe-stop verify + install | ready |
| G8 | Atomic patch apply while proven stopped | gated by G1–G7 |
| G9 | Start + readback | separate approval |
| G10 | Health readback / controlled scan / audit writes | separate approval |

`G2–G6` are additionally enforced by `check_accepted_gates()` (§8a, called explicitly in §9
and again in §10) and by the `privileged-path-approved` record (§8b, re-read in §12).

**Conclusion: not executable-all.** G2–G6 are open, so §9 onward must not be attempted.
The stop and the start may be covered by **one explicit future approval that names both**
(for example "stop, patch, restart in window W"); this package does not require a separate
re-approval per command, but it does require that any approval state its scope. Future
acceptance (health readback, one controlled known scan writing **job state only**,
audit-write verification, and any business `INSERT`/`UPDATE`) needs its own separate
approval; no business write is authorised here, and unit `active` is not acceptance.
