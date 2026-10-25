#!/usr/bin/env python3
"""OFFLINE checks for ops/worker-alignment/OPERATOR.md (dashboard M2 operator package).

Stdlib harness; never runs a documented runtime command, never reads a real env.
This file imports stdlib only. Two steps EXECUTE documented logic on synthetic
data: `patch` against the pinned baseline, and the env-packaging module run by
./venv/bin/python with its ALREADY-INSTALLED python-dotenv (pinned 1.0.1, the
same version the doc cites). In that child, os.geteuid/os.chown/os.chmod are
MOCKED -- a unit harness condition, NOT an OS-privilege bypass and NOT a root
acceptance test; no dependency is installed. git is read-only. No
service/systemd/DB/Redis/broker/network/SSH call is issued.

Run: python3 -B tests/check_worker_operator.py
"""
import ast, hashlib, importlib.util, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "ops", "worker-alignment", "OPERATOR.md")
OPS = os.path.join(ROOT, "ops", "worker-alignment")
TMPROOT = "/tmp/opencode"
UNIT, DEST = "celery.service", "celery@scrapper"
RUNTIME_CWD = "/home/scrapper/bdt_dashboard-scrap-result/car_ads_dashboard"
PYBIN = "/home/scrapper/bdt_dashboard-scrap-result/venv/bin/python"
ENV_DIR, ENV_FILE = "/etc/cars-dashboard", "/etc/cars-dashboard/worker.env"
DROPIN_DIR = "/etc/systemd/system/celery.service.d"
ROOT_STAGE, TRANSPORT = "/var/lib/cars-worker-alignment", "/home/scrapper/worker-alignment-20261024"
BROKER = "redis://localhost:6379/0"
PINS = {
    "legacy": "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c",
    "patched": "72e8ee73aa2c914f2defc22257b8c05584bb10a909b25d5a0f3c920b52a12b48",
    "patch": "8bfec61d21546fd33d398e257ae628b9530b1f3d641144aee557b72dca4383d1",
    "safe_stop": "79aaa3e7abba876f8cb367666c9eda5b7adfc97c01e48ac6c3066a995c25a69f",
    "head": "a217884b7f8df6d5bcd3d305d461d0a6ce399d5e"}
# Exact tracked files an approved increment may leave dirty: the dotenv
# selector target, plus the M2-HOOK1 opt-in startup-hook guard added to
# celery.py. This is an exact allowlist, not "any dirty file is acceptable":
# every other tracked modification is still rejected.
DIRTY_ALLOW = ("car_ads_dashboard/car_ads_dashboard/celery.py",
               "car_ads_dashboard/car_ads_dashboard/settings.py")
ALLOW = "SECRET_KEY DEBUG ALLOWED_HOSTS CSRF_TRUSTED_ORIGINS DB_NAME DB_USER DB_PASSWORD DB_HOST DB_PORT".split()
BANNED = "CELERY_BROKER_URL CELERY_RESULT_BACKEND BROKER_URL REDIS_URL CHANNEL_LAYERS DJANGO_SERVE_STATIC".split()
SECTIONS = (("## 0. Fixed contract", "## 1."), ("## 1. Session", "## 2."),
            ("## 4. G2", "## 5."), ("## 6. G4/S5", "## 7."),
            ("## 8a. Stop-condition gate", "## 8b."), ("## 8b. Privileged-path", "## 9."),
            ("## 9. Safe-stop", "## 10."), ("## 10. Stop", "## 11."),
            ("## 12. Apply", "## 13."), ("## 13. Install", "## 14."),
            ("## 15. Rollback", "## 16."))
SHAPES = [
    (r"\bsudo\b|\bdoas\b|\bpkexec\b|\bsu\s+-", "privilege escalation"),
    (r"systemctl\s+(restart|enable|disable|edit|mask|kill)\b", "unit mutation"),
    (r"kill\s+-9|\bpkill\b|\bkillall\b", "force kill"),
    (r"\bpurge\b|\breplay\b|flushdb|flushall", "queue purge/replay"),
    (r"git\s+apply|git\s+(commit|push|reset|checkout|clean)\b", "git mutation"),
    (r"\bpsql\b|\bdocker\s+(compose\s+)?(up|build|rm|down)\b", "DB/container mutation"),
    (r"celery\s+(-A|inspect|control|purge)", "celery CLI imports the app"),
    (r"(^|[;&|]\s*)cat\s+[^|]*(\.env|ENV_FILE|cars-dashboard)", "env file dump"),
    (r"\benv\s*\||\bprintenv\b|\bset\s+-x\b", "environment dump"),
    (r"timeoutstopsec\b(?!_)", "TimeoutStopSec alias"),
    (r"\\x1[0-9a-fA-F]", "hardcoded control-char escape"),
    (r"test\s+-s\s+\"?[^\"]*cgroup\.procs", "test -s on size-0 pseudo-file"),
    (r"\bset\s+\+e\b", "error checking disabled"),
    (r"EXAMPLE", "placeholder path"),
    (r"gdb|ptrace|strace|/proc/\d+", "process instrumentation"),
    (r"\bcurl\b|\bwget\b|\bssh\b", "network/remote shell"),
    (r"chmod\s+0?7?77|chmod\s+0?666", "world-writable mode"),
    (r"\bhead\b|printf\s+'%s\\n'\s+\"\$out\"", "printing captured diagnostics")]


class Reject(Exception):
    pass


def require(cond, msg):
    if not cond:
        raise Reject(msg)


CHECKS = []


def check(label, needs=()):
    """Register a check; `needs` names the (text, blocks) args it receives."""
    def deco(fn):
        CHECKS.append((label, fn, needs))
        return fn
    return deco


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def prose(text):
    return " ".join(text.replace("*", "").replace("`", "").split())


def heredocs(body):
    found, tag, buf = [], None, []
    for line in body.splitlines():
        if tag is None:
            hit = re.search(r"<<-?'([A-Za-z_]+)'", line)
            if hit:
                tag, buf = hit.group(1), []
        elif line.strip() == tag:
            found.append("\n".join(buf) + "\n")
            tag, buf = None, []
        else:
            buf.append(line)
    if tag is not None:
        raise Reject("unterminated heredoc %r" % tag)
    return found


def fences(text):
    """Bash fence bodies plus every embedded python heredoc payload."""
    out, kind, buf = {"bash": [], "python": []}, None, []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if kind:
                body = "\n".join(buf) + "\n"
                out[kind].append(body)
                if kind == "bash":
                    out["python"].extend(heredocs(body))
                kind, buf = None, []
            else:
                kind = {"bash": "bash", "sh": "bash", "python": "python",
                        "py": "python"}.get(line.strip()[3:].strip())
            continue
        if kind:
            buf.append(line)
    if kind:
        raise Reject("unterminated fence")
    return out


def section(text, head, stop):
    if head not in text:
        raise Reject("missing section: %r" % head)
    return text.split(head)[1].split(stop)[0]


def roll_pins():
    spec = importlib.util.spec_from_file_location(
        "roll", os.path.join(ROOT, "tests", "check_worker_rollout.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def packaging_module(blocks):
    py = [b for b in blocks["python"] if "dotenv_values" in b and "set_key" in b]
    if len(py) != 1:
        raise Reject("expected exactly one env-packaging module, got %d" % len(py))
    return py[0]


def calls_of(tree):
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name:
                out.setdefault(name, []).append(node.lineno)
    return out


# ------------------------------------------------------------------- checks ---
@check("contract/pins", ("text", "blocks"))
def check_contract(text, blocks):
    for head, stop in SECTIONS:
        section(text, head, stop)
    needles = [PYBIN, RUNTIME_CWD, ENV_DIR, ENV_FILE, DROPIN_DIR, ROOT_STAGE, TRANSPORT,
               BROKER, DEST, UNIT, "db_fastapi_scrap_stage", "bdt_stage_owner",
               "PROPOSAL ONLY", "BELUM SELESAI", "not executable-all",
               "trusted-runtime-accepted", "privileged-path-approved",
               "check_accepted_gates", "EnvironmentFile", "override=True"]
    missing = [n for n in needles + list(PINS.values()) + ALLOW + BANNED if n not in text]
    require(not missing, "contract literals absent: %s" % missing[:3])
    return len(blocks["bash"])


@check("gates fail-closed", ("text",))
def check_gates(text):
    bad = [g for g in ("G2", "G3", "G4", "G5", "G6")
           if not re.search(r"\| %s \|[^\n]*BLOCKED" % g, text)]
    require(not bad, "gates missing or not BLOCKED: %s" % bad)
    require("not executable-all" in prose(text), "must state it is not executable-all")
    require(text.count("check_accepted_gates() {") == 1,
            "check_accepted_gates() must be defined exactly once")
    for head, stop in (("## 9. Safe-stop", "## 10."), ("## 10. Stop", "## 11.")):
        require("check_accepted_gates\n" in section(text, head, stop),
                "%s must explicitly call check_accepted_gates" % head)
    return 5


@check("gate records", ("text",))
def check_manifest(text):
    body = section(text, "## 8a.", "## 8b.")
    missing = [n for n in ("len(lines) != 8", "isdir", "operator", "accepted_utc",
                           "evidence_dir") if n not in body]
    require(not missing, "manifest validator missing: %s" % missing)
    require("grep -c" not in body, "manifest must be key-set validated, not grep-counted")
    require("no command to fabricate" in prose(text), "must state no fabrication command")
    priv = section(text, "## 8b.", "## 9.")
    require(not [n for n in ("privileged-path-approved", "trusted-runtime-accepted",
                             "root:root", "600") if n not in priv],
            "privileged-path gate elements missing")
    require("not implemented" in prose(priv), "unimplemented alternative must be stated")
    require("privileged-path-approved" in section(text, "## 12.", "## 13."),
            "§12 must re-read the privileged-path record before patching")
    return 12


@check("diagnostics suppressed", ("text",))
def check_diagnostics(text):
    """systemd-analyze output must never be echoed: it can quote Environment=."""
    for body in fences(text)["bash"]:
        for line in body.splitlines():
            code = line.split(" #", 1)[0]
            if "$out" in code and re.search(r"\bprintf\b|\becho\b|\bhead\b", code):
                raise Reject("captured verify output printed: %r" % code.strip()[:50])
    require("may contain secrets" in text and "output suppressed" in text,
            "verify suppression rationale/message absent")
    sec13 = section(text, "## 13. Install", "## 14.")
    require("verify_unit" in sec13, "§13 must call the shared verify_unit helper")
    require("systemd-analyze verify" not in sec13,
            "§13 repeats inline systemd-analyze instead of verify_unit")
    return 3


@check("reconciliation client", ("blocks",))
def check_reconciliation(blocks):
    body = [b for b in blocks["python"] if "inspect" in b]
    if len(body) != 1:
        raise Reject("expected exactly one reconciliation client")
    body = body[0]
    missing = [n for n in ("priority_steps", "Channel.sep", DEST, "destination",
                           "broker_connection_timeout", "socket_timeout",
                           "socket_connect_timeout", "ast.walk") if n not in body]
    require(not missing, "reconciliation elements missing: %s" % missing)
    require(not re.search(r"sep\s*=\s*['\"]", body), "separator hardcoded")
    require(not re.search(r"\bprint\(\s*(reply|items|vals|value)", body),
            "reconciliation prints payload/reply data")
    require(not re.search(r"\b(import\s+django|DJANGO_SETTINGS_MODULE)", body),
            "reconciliation imports Django settings")
    require("no reply" in body, "absent-reply STOP guard missing")
    return 8


@check("env packaging code", ("blocks",))
def check_packaging(blocks):
    body = packaging_module(blocks)
    missing = [n for n in ("dotenv_values", "interpolate=False", "set_key",
                           'quote_mode="always"', '"${"', "sys.exit(", "geteuid",
                           "is_symlink", "mkstemp", "os.rename",
                           "forbidden key present in output") if n not in body]
    missing += [k for k in BANNED if k not in body]
    require(not missing, "packaging elements missing: %s" % missing)
    require(not re.search(r"\bprint\(\s*(value|vals\[)", body),
            "packaging code prints a secret value")
    tree, calls = ast.parse(body), calls_of(ast.parse(body))
    require(not [b for b in ("chown", "fchown", "lchown") if b in calls],
            "module performs ownership change; that is a shell step")
    require(any(isinstance(n, ast.Compare) and isinstance(n.left, ast.Call)
                and getattr(n.left.func, "attr", "") == "geteuid"
                for n in ast.walk(tree)), "module lacks its root precondition")
    writes = [ln for n in ("set_key", "mkstemp", "rename") for ln in calls.get(n, [])]
    require(bool(writes), "packaging code has no write step")
    require(len([ln for ln in calls.get("fail", []) if ln < min(writes)]) >= 4,
            "allowlist not validated before the first write")
    require("dotenv_values(tmp)" in body, "no readback of the written file")
    require(min(calls.get("rename", [0])) >= max(calls.get("dotenv_values", [0])),
            "rename occurs before the round-trip readback")
    shell = "\n".join(blocks["bash"])
    require(re.search(r'(?m)^chown root:scrapper "\$ENV_FILE"', shell)
            and re.search(r'(?m)^chmod 0640 "\$ENV_FILE"', shell),
            "separate root-only metadata step missing")
    return len(ALLOW)


@check("bash -n + fail-closed", ("blocks",))
def check_bash(blocks):
    require(len(blocks["bash"]) >= 8, "expected >=8 bash blocks, got %d" % len(blocks["bash"]))
    for idx, body in enumerate(blocks["bash"]):
        proc = subprocess.run(["bash", "-n"], input=body, text=True,
                              capture_output=True, check=False)
        require(proc.returncode == 0, "bash -n rejected block #%d" % idx)
        if idx == 0 and body.strip() == "bash -euo pipefail":
            continue
        require("set -euo pipefail" in body, "block #%d is not fail-closed" % idx)
        require(bool(re.search(r"\b(STOP|exit 1)\b", body)), "block #%d has no abort path" % idx)
    return len(blocks["bash"])


@check("python parse", ("blocks",))
def check_python(blocks):
    for idx, body in enumerate(blocks["python"]):
        try:
            ast.parse(body)
        except SyntaxError as exc:
            raise Reject("python fence #%d does not parse: %s" % (idx, exc)) from exc
    return len(blocks["python"])


@check("forbidden operations", ("text",))
def check_forbidden(text):
    hits = []
    for kind, bodies in fences(text).items():
        for idx, body in enumerate(bodies):
            for line in body.splitlines():
                code = line.split(" #", 1)[0]
                for pattern, why in SHAPES:
                    if re.search(pattern, code, re.IGNORECASE):
                        hits.append("%s#%d %s -> %r" % (kind, idx, why, code.strip()[:40]))
    if hits:
        raise Reject("forbidden operation(s): " + "; ".join(hits[:3]))
    return len(SHAPES)


@check("stop/rollback/signal", ("text",))
def check_stop(text):
    missing = [n for n in ("ControlGroup --value", "cgroup.events", "populated",
                           "wc -l <", "SubState", "MainPID", "NRestarts",
                           "OPERATOR_OBSERVATION_SECONDS", "CG_PATH:-}", "remove_owned",
                           '[ -L "$path" ]') if n not in text]
    require(not missing, "stop/rollback elements missing: %s" % missing[:3])
    require(not re.search(r"SECONDS \+ \d", text), "invented numeric tolerance deadline")
    body = text[text.find("## 15. Rollback"):]
    require(body.find('[ -L "$path" ]') < body.find('rm -f -- "$path"'),
            "symlink test must precede removal")
    require("retain them as private evidence" in prose(text),
            "R1 must state isolated env artifacts are retained")
    require(not re.search(r'(?i)\$\{?KILL_?SIGNAL\w*\}?"?\s*=\s*"SIGTERM"', text),
            "KillSignal compared to SIGTERM only (systemd reports 15)")
    require(len(re.findall(r"15\|SIGTERM", text)) >= 2,
            "numeric-or-name KillSignal acceptance missing at a site")
    require("verify_unit" in section(text, "## 9. Safe-stop", "## 10."),
            "shared verify_unit helper must be defined in §9")
    return 16


@check("no secret shapes", ("text",))
def check_no_secrets(text):
    shapes = (r"(?i)\bSECRET_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}",
              r"(?i)\bDB_PASSWORD\s*=\s*['\"]?\S{4,}",
              r"postgres(ql)?://[^\s/]+:[^\s@]+@",
              r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    require(not [p for p in shapes if re.search(p, text)], "secret-shaped literal in document")
    return len(shapes)


# ------------------------------------------------------------ executed parts ---
CHILD = r'''
import json, runpy, sys, os
spec = json.loads(sys.argv[1])
calls = {"chown": 0, "chmod": 0}
os.geteuid = lambda: 0
os.chown = lambda *a, **k: calls.__setitem__("chown", calls["chown"] + 1)
os.chmod = lambda *a, **k: calls.__setitem__("chmod", calls["chmod"] + 1)
sys.argv = ["packaging", spec["src"], spec["dst"]]
code, message = 0, ""
try:
    runpy.run_path(spec["module"], run_name="__main__")
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 1
    message = "" if isinstance(exc.code, int) else str(exc.code)
info = {}
if code == 0 and spec.get("expect") is not None:
    from dotenv import dotenv_values
    got = dotenv_values(spec["dst"], interpolate=False)
    expect = spec["expect"]
    info = {"keys_equal": sorted(got) == sorted(expect),
            "mismatch": sorted(k for k, v in expect.items() if got.get(k) != v),
            "mode": oct(os.stat(spec["dst"]).st_mode & 0o777),
            "forbidden": sorted(k for k in spec["banned"] if k in got)}
print("RESULT " + json.dumps(dict(rc=code, msg=message, **calls, **info)))
'''


def run_module(directory, body, src, dst, expect=None):
    module = os.path.join(directory, "packaging_module.py")
    open(module, "w", encoding="utf-8").write(body)
    child = os.path.join(directory, "child.py")
    open(child, "w", encoding="utf-8").write(CHILD)
    proc = subprocess.run([os.path.join(ROOT, "venv", "bin", "python"), "-B", child,
                           json.dumps({"src": src, "dst": dst, "module": module,
                                       "expect": expect, "banned": BANNED})],
                          capture_output=True, text=True, check=False)
    if "RESULT " not in proc.stdout:
        raise Reject("fixture child produced no result: %r" % proc.stderr[-100:])
    return json.loads(proc.stdout.split("RESULT ", 1)[1].splitlines()[0]), proc


def write_env(path, values):
    """Synthetic .env writer: every value quoted so parsing is unambiguous."""
    with open(path, "w", encoding="utf-8") as fh:
        for key, val in values.items():
            esc = val.replace("\\", "\\\\").replace('"', '\\"')
            fh.write('%s="%s"\n' % (key, esc.replace("\n", "\\n").replace("\t", "\\t")))


@check("env fixture (executed)", ("blocks",))
def check_env_fixture(blocks):
    body = packaging_module(blocks)
    good = {"SECRET_KEY": 'k-3 $HOME # not-a-comment/2', "DEBUG": "True",
            "ALLOWED_HOSTS": "alpha.invalid,beta.invalid",
            "CSRF_TRUSTED_ORIGINS": "https://alpha.invalid", "DB_NAME": "fixture_db",
            "DB_USER": "fixture user", "DB_HOST": "127.0.0.1", "DB_PORT": "5432",
            "DB_PASSWORD": 'p\'a"s$w\\d' + "\\nliteral\\tend"}
    partial = dict(good)
    partial.pop("DB_PASSWORD")
    leaks = ""
    with tempfile.TemporaryDirectory(dir=TMPROOT) as tmp:
        for label, values, ok in (("valid", good, True), ("missing", partial, False),
                                  ("interp", dict(good, DB_HOST="${LEAK}"), False)):
            src, dst = os.path.join(tmp, label + ".env"), os.path.join(tmp, label + ".out")
            write_env(src, values)
            result, proc = run_module(tmp, body, src, dst,
                                      expect=values if ok else None)
            leaks += proc.stdout + proc.stderr
            if not ok:
                if result["rc"] == 0:
                    raise Reject("module accepted the %s fixture" % label)
                if os.path.exists(dst):
                    raise Reject("%s abort left a final env file behind" % label)
                continue
            if result["rc"] != 0:
                raise Reject("module refused the valid fixture: %s" % result["msg"])
            if result["chown"] or result["chmod"]:
                raise Reject("module made an ownership/mode change (shell-only)")
            if result["mode"] != "0o600":
                raise Reject("staged env file is not 0600 from birth")
            if not result["keys_equal"]:
                raise Reject("written key set differs from the fixture allowlist")
            if result["mismatch"]:
                raise Reject("%s did not round-trip through dotenv" % result["mismatch"])
            if result["forbidden"]:
                raise Reject("forbidden key present in packaged output: %s"
                             % result["forbidden"])
        for key in ("SECRET_KEY", "DB_PASSWORD"):
            if good[key] in leaks:
                raise Reject("secret value leaked into fixture diagnostics")
    return len(good)


@check("patch+rollback (executed)")
def check_patch_rollback():
    """Real `patch` on the pinned baseline, plus the documented remove_owned()."""
    roll = roll_pins()
    with tempfile.TemporaryDirectory(dir=TMPROOT) as tmp:
        src, out = os.path.join(tmp, "settings.py"), os.path.join(tmp, "new.py")
        with open(src, "wb") as fh:
            fh.write(roll.git("show", "%s:%s" % (roll.OBJ, roll.REL)))
        proc = subprocess.run(["patch", "-s", "-o", out, src, roll.PATCH],
                              capture_output=True, check=False)
        if proc.returncode != 0:
            raise Reject("documented patch failed on the baseline")
        with open(out, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != PINS["patched"]:
                raise Reject("patch output does not match the pinned hash")
        text = read(DOC)
        fn = text[text.find("remove_owned() {"):]
        fn = fn[:fn.find("\n}\n") + 3]
        if "$path" not in fn:
            raise Reject("cannot extract remove_owned()")
        dropin = os.path.join(tmp, "d")
        os.makedirs(dropin)
        good = os.path.join(dropin, "10-worker-safe-stop.conf")
        with open(good, "wb") as fh:
            fh.write(b"KillMode=mixed\n")
        want = hashlib.sha256(b"KillMode=mixed\n").hexdigest()
        tampered = os.path.join(dropin, "20-worker-env.conf")
        with open(tampered, "wb") as fh:
            fh.write(b"tampered\n")
        link = os.path.join(dropin, "30-link.conf")
        os.symlink(os.path.join(tmp, "absent"), link)
        script = fn + '\nremove_owned "$1" "$2"\n'
        for path, should_go, note in ((good, True, "matching hash"),
                                      (tampered, False, "hash-changed"),
                                      (link, False, "dangling symlink")):
            res = subprocess.run(["bash", "-c", script, "_", path, want],
                                 capture_output=True, check=False)
            still_there = os.path.lexists(path)
            if should_go and still_there:
                raise Reject("%s artifact was not removed" % note)
            if not should_go and (not still_there or res.returncode == 0):
                raise Reject("%s artifact removed (must refuse)" % note)
        return 3


def dirty_violation(dirty, allow=DIRTY_ALLOW):
    """True when the dirty set is not exactly the approved allowlist."""
    return sorted(set(dirty)) != sorted(set(allow)) or len(set(dirty)) != len(set(allow))


@check("artifacts/repo pins")
def check_artifacts():
    roll = roll_pins()
    for name, pin in (("settings-legacy-dotenv.patch", PINS["patch"]),
                      ("10-safe-stop.conf", PINS["safe_stop"])):
        if hashlib.sha256(open(os.path.join(OPS, name), "rb").read()).hexdigest() != pin:
            raise Reject("artifact drifted: %s" % name)
    if hashlib.sha256(roll.git("show", "%s:%s" % (roll.OBJ, roll.REL))).hexdigest() != PINS["legacy"]:
        raise Reject("legacy baseline pin mismatch")
    if roll.git("rev-parse", "HEAD").decode().strip() != PINS["head"]:
        raise Reject("source HEAD drifted")
    # Negative control: an exact allowlist, never a blanket "any dirty passes".
    if not dirty_violation(DIRTY_ALLOW + ("car_ads_dashboard/car_ads_dashboard/__init__.py",)):
        raise Reject("dirty allowlist is not enforced: an extra file was accepted")
    if dirty_violation(DIRTY_ALLOW):
        raise Reject("dirty allowlist rejects the approved set")
    if not dirty_violation(("car_ads_dashboard/car_ads_dashboard/settings.py",)):
        raise Reject("dirty allowlist accepts a partial dirty set")
    status = roll.git("status", "--porcelain").decode().splitlines()
    tracked = [ln for ln in status if not ln.startswith("??")]
    dirty = [ln[3:] for ln in tracked if ln[:2].strip() == "M"]
    if dirty_violation(dirty):
        raise Reject("unexpected tracked modification: %r" % (dirty,))
    if roll.REL not in DIRTY_ALLOW or len(DIRTY_ALLOW) != 2:
        raise Reject("dirty allowlist must be exactly the two approved files")
    if [ln for ln in tracked if ln[:2].strip() != "M"]:
        raise Reject("unexpected non-modification tracked status")
    for need in (".dockerignore", "Dockerfile", "compose.dokploy.yaml", "graphify-out/",
                 "ops/", "tests/"):
        if not any(ln[3:] == need for ln in status if ln.startswith("??")):
            raise Reject("pre-existing untracked path lost: %s" % need)
    if any(n.endswith((".sh", ".bash", ".py")) for n in os.listdir(OPS)):
        raise Reject("executable mutation script shipped in ops/")
    return 5


def controls(text, blocks):
    """Each mutation must be rejected by the check it targets."""
    py = [b for b in blocks["python"] if "inspect" in b][0]

    def sub(old, new):
        return {**blocks, "bash": [b.replace(old, new, 1) for b in blocks["bash"]]}

    def allpy(old, new):
        return {**blocks, "python": [b.replace(old, new) for b in blocks["python"]]}

    cases = [
        ("celery CLI", check_forbidden, text.replace(
            '"$PYBIN" -B - "$LEGACY_SETTINGS"', '"$PYBIN" -m celery -A x inspect active')),
        ("hardcoded sep", check_forbidden,
         text.replace("sep = kbredis.Channel.sep", "sep = '\\x163'")),
        ("no set -e", check_bash, sub("set -euo pipefail", "")),
        ("EXAMPLE path", check_forbidden,
         text.replace("settings.py.legacy.bak", "settings-EXAMPLE.bak")),
        ("env dump", check_forbidden, text.replace(
            'echo "run_dir=$RUN_DIR backup=$BACKUP"', 'echo x; cat "$ENV_FILE"')),
        ("test -s cgroup", check_forbidden, text.replace(
            'procs="$(wc -l < "$CG_PATH/cgroup.procs")"',
            'test -s "$CG_PATH/cgroup.procs"')),
        ("payload print", check_reconciliation, {**blocks, "python": [
            py.replace('print("%s=%d" % (kind, len(items)))', "print(reply)")]}),
        ("gate promoted", check_gates, text.replace("| **BLOCKED** |", "| ready |", 1)),
        ("verify output printed", check_diagnostics, text.replace(
            '"STOP: systemd-analyze verify failed rc=$rc (output suppressed: may '
            'contain secrets)"', '"x"; printf \'%s\\n\' "$out"')),
        ("inline verify in §13", check_diagnostics, text.replace(
            "# Same shared helper as §9: captured diagnostics are never printed.\n"
            "verify_unit\n", 'out="$(systemd-analyze verify "$UNIT_FILE" 2>&1)"; rc=$?\n')),
        ("KillSignal name only", check_stop, text.replace(
            'case "$KILLSIGNAL_NOW" in\n  15|SIGTERM)',
            'test "$KILLSIGNAL_NOW" = "SIGTERM" || exit 1\ncase x in\n  SIGTERM)')),
        ("invented deadline", check_stop, text.replace(
            "DEADLINE=$((SECONDS + OPERATOR_OBSERVATION_SECONDS))",
            "DEADLINE=$((SECONDS + 900))")),
        ("gate call removed", check_gates, text.replace(
            "# Shared validator from §8a, called explicitly here: full "
            "key-set/owner/mode recheck.\ncheck_accepted_gates\n", "")),
        ("grep-counted manifest", check_manifest,
         text.replace("if len(lines) != 8:", "if False:")),
        ("privileged record dropped", check_manifest,
         text.replace("trusted-runtime-accepted", "anything-goes")),
        ("chown in module", check_packaging, allpy(
            "os.rename(tmp, dst)", "os.chown(tmp, 0, 0)\nos.rename(tmp, dst)")),
        ("no root guard", check_packaging, allpy(
            'if os.geteuid() != 0:\n    fail("packaging must run as root")', "")),
        ("rename before readback", check_packaging, allpy(
            "    written = dotenv_values(tmp)",
            "    os.rename(tmp, dst)\n    written = dotenv_values(tmp)")),
        ("shell metadata step lost", check_packaging,
         sub('chown root:scrapper "$ENV_FILE"', "true")),
        ("env fixture: value corrupted", check_env_fixture, allpy(
            'set_key(tmp, key, expected[key], quote_mode="always")',
            'set_key(tmp, key, expected[key] + "X", quote_mode="always")')),
        ("env fixture: key dropped", check_env_fixture, allpy(
            "for key in ALLOW:", "for key in ALLOW[:-1]:")),
        ("forbidden-key guard gone", check_packaging, {
            **blocks, "python": [re.sub(
                r"    if any\(k in written.*?forbidden key present in output\"\)\n",
                "", b, flags=re.S) for b in blocks["python"]]})]
    for label, fn, mutated in cases:
        if mutated == text or mutated == blocks:
            raise Reject("control %r did not change the input" % label)
        try:
            fn(mutated)
        except Reject:
            continue
        raise Reject("control NOT rejected: %s" % label)
    return len(cases)


def main():
    try:
        text = read(DOC)
    except OSError as exc:
        print("FAIL: cannot read %s: %s" % (DOC, exc))
        return 1
    if not os.path.isdir(TMPROOT):
        print("FAIL: fixture dir %s missing (create it; do not use /tmp)" % TMPROOT)
        return 1
    print("doc        %s" % DOC)
    print("doc_sha256 %s" % hashlib.sha256(text.encode()).hexdigest())
    print("doc_lines  %d" % len(text.splitlines()))
    blocks = fences(text)
    env = {"text": text, "blocks": blocks}
    failures = 0
    for label, fn, needs in CHECKS:
        try:
            detail = fn(*[env[n] for n in needs])
        except Reject as exc:
            failures += 1
            print("FAIL %-24s %s" % (label, exc))
            continue
        print("PASS %-24s %s" % (label, detail))
    try:
        count = controls(text, blocks)
        print("PASS %-24s %d/%d rejected" % ("negative controls", count, count))
    except Reject as exc:
        failures += 1
        print("FAIL %-24s %s" % ("negative controls", exc))
    if failures:
        print("RESULT: FAIL (%d issue(s))" % failures)
        return 1
    print("RESULT: PASS (offline parse + executed synthetic fixtures; no env read, "
          "no install/stop/apply; gates G2-G6 remain BLOCKED)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
