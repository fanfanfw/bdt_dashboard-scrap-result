#!/usr/bin/env python3
"""Stdlib-only contract checker for M2-T1 packaging (gate PG-A).

Reads Dockerfile, .dockerignore and compose.dokploy.yaml as TEXT/JSON only: no
Django import, no .env read, no Docker daemon, network, DB or runtime action.
Nothing here builds, starts or deploys anything.

Run: python3 tests/check_dashboard_docker_contract.py
Exit 0 only if every positive assertion passes AND every negative control
(deliberately broken fixture) is rejected for the expected reason.
"""
import fnmatch
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Registry-verified 2026-10-23 (read-only manifest + config blob, no pull):
# tag 3.12-slim -> this index digest; amd64 config PYTHON_VERSION=3.12.15.
# NOT exact parity: the live UI runs Python 3.12.3 (patch delta disclosed).
BASE_REF = "python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"
CMD_EXPECTED = ["daphne", "-b", "127.0.0.1", "-p", "18111", "car_ads_dashboard.asgi:application"]
COPY_ALLOWED = {"requirements.txt": "/tmp/requirements.txt",
                "car_ads_dashboard/": "/app/car_ads_dashboard/"}
# Must appear literally (structure, not a tautology).
REQUIRED_IGNORES = (".env **/.env **/.env.* venv **/venv graphify-out __pycache__ "
                    "**/__pycache__ **/staticfiles **/logs **/*.sqlite3 **/*.backup "
                    "**/models **/artifacts").split()
# Must be EXCLUDED: secrets, venvs, caches, generated output, data/model archives.
EXCLUDED = (".env car_ads_dashboard/.env .env.prod a/.env.local venv/bin/daphne .venv/x "
            "x/y/notes.log logs/app.log graphify-out/GRAPH_REPORT.md "
            "d/dashboard/__pycache__/a.pyc d/staticfiles/css/login.css "
            "d/dashboard/db.sqlite3 d/data/a.dump d/data/backup.backup "
            "d/artifacts/m.pkl d/models/w.h5").split()
# Must REMAIN included: the app cannot run without these.
INCLUDED = ("requirements.txt car_ads_dashboard/car_ads_dashboard/settings.py "
            "car_ads_dashboard/car_ads_dashboard/asgi.py car_ads_dashboard/dashboard/models.py "
            "car_ads_dashboard/dashboard/models_extra.py "
            "car_ads_dashboard/dashboard/templates/dashboard/user_dashboard.html "
            "car_ads_dashboard/dashboard/static/js/user_dashboard.js "
            "car_ads_dashboard/dashboard/migrations/0001_initial.py").split()


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def uncomment(text):
    """Drop comment lines/trailing comments so prose cannot trip a check."""
    keep = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    return re.sub(r"\s+#(?![^{}]*\}).*$", "", "\n".join(keep), flags=re.M)


def chk(errs, cond, msg):
    if not cond:
        errs.append(msg)


def must(errs, pattern, block, msg):
    chk(errs, re.search(pattern, block, re.M | re.I), msg)


def deny(errs, pattern, block, msg):
    chk(errs, not re.search(pattern, block, re.M | re.I), msg)


# --------------------------------------------------------------- .dockerignore
def seg_match(pattern, path):
    """Docker-style: '**' spans segments; a dir pattern covers its children."""
    pat = [s for s in pattern.split("/") if s not in ("", ".")]
    segs = [s for s in path.split("/") if s not in ("", ".")]
    if not pat or not segs:
        return False

    def rec(pi, si):
        if pi == len(pat):
            return True
        if pat[pi] == "**":
            return any(rec(pi + 1, k) for k in range(si, len(segs) + 1))
        if si >= len(segs) or not fnmatch.fnmatchcase(segs[si], pat[pi]):
            return False
        return rec(pi + 1, si + 1)

    return rec(0, 0)


def ignored(text, path):
    pats = [ln.strip() for ln in text.splitlines()]
    return any(seg_match(p, path) for p in pats if p and not p.startswith("#"))


def check_dockerignore(text):
    errs, lines = [], [ln.strip() for ln in text.splitlines()]
    errs += ["missing required pattern: %s" % p for p in REQUIRED_IGNORES if p not in lines]
    errs += ["does NOT exclude %r" % p for p in EXCLUDED if not ignored(text, p)]
    errs += ["wrongly excludes needed asset %r" % p for p in INCLUDED if ignored(text, p)]
    chk(errs, not ("*" in lines or "**" in lines), "blanket wildcard makes ignores tautological")
    return errs


# ------------------------------------------------------------------ Dockerfile
def check_dockerfile(text):
    errs, code = [], uncomment(text)
    insts = re.findall(r"^([A-Z]+)[ \t]+(.*(?:\\\n.*)*)$", code, re.M)
    ops = [k for k, _ in insts]
    froms = [v.strip() for k, v in insts if k == "FROM"]
    if len(froms) != 1:
        errs.append("expected exactly 1 FROM, found %d" % len(froms))
    else:
        chk(errs, froms[0] == BASE_REF, "base image not pinned to verified digest: %r" % froms[0])
    must(errs, r"^USER\s+1000:1000\s*$", code, "no explicit non-root 'USER 1000:1000'")
    must(errs, r"^WORKDIR\s+/app/car_ads_dashboard\s*$", code, "WORKDIR is not /app/car_ads_dashboard")
    deny(errs, r":latest\b", code, "image reference uses ':latest'")
    deny(errs, r"^\s*(RUN|USER|CMD|ENTRYPOINT)[^\n]*\bsudo\b", code, "sudo invoked")
    deny(errs, r"ALLOWED_HOSTS", code, "ALLOWED_HOSTS must not be set in the Dockerfile")
    for word in ("migrate", "collectstatic", "beat", "nginx", "whitenoise", "gunicorn",
                 "uvicorn", "--upgrade"):
        deny(errs, r"^[^#\n]*\b%s\b" % re.escape(word), code, "forbidden concern: %s" % word)
    # The LAST USER wins: it must be exactly the numeric non-root identity.
    users = [v.strip() for k, v in insts if k == "USER"]
    if not users:
        errs.append("no USER instruction")
    else:
        chk(errs, users[-1] == "1000:1000", "final USER must be exactly 1000:1000, got %r" % users[-1])
    chk(errs, not any(re.match(r"(root|0)(:|$)", u) for u in users), "root USER present")
    # One launcher: image CMD as an exact argv array, no ENTRYPOINT/shell form.
    chk(errs, "ENTRYPOINT" not in ops, "ENTRYPOINT present: launcher must be the image CMD only")
    chk(errs, len(re.findall(r"\bdaphne\b", code)) == 1, "Daphne must be launched exactly once")
    cmd = re.search(r"^CMD\s+(\[.*\])\s*$", code, re.M)
    if not cmd:
        errs.append("no exec-form CMD")
    else:
        try:
            argv = json.loads(cmd.group(1))
        except ValueError:
            errs.append("CMD is not valid JSON argv")
        else:
            chk(errs, argv == CMD_EXPECTED, "CMD argv must be exactly %r, got %r" % (CMD_EXPECTED, argv))
    # COPY: exactly two, allowlisted source, fixed destination.
    copies = [v.split() for k, v in insts if k == "COPY"]
    chk(errs, len(copies) == 2, "expected 2 COPY lines, found %d" % len(copies))
    for parts in copies:
        deny(errs, r"--from", " ".join(parts), "COPY --from not allowed")
        toks = [p for p in parts if not p.startswith("--")]
        if len(toks) != 2:
            errs.append("COPY needs exactly src+dst: %r" % parts)
            continue
        src, dst = toks
        deny(errs, r"\.env|venv|graphify|staticfiles|\.git", src, "COPY pulls excluded material: %r" % src)
        if src not in COPY_ALLOWED:
            errs.append("COPY source outside allowlist: %r" % src)
        else:
            chk(errs, dst == COPY_ALLOWED[src], "COPY %s must land in %s, got %r" % (src, COPY_ALLOWED[src], dst))
    for src in COPY_ALLOWED:
        chk(errs, any(p and p[0] == src for p in copies), "%s not copied from context" % src)
    # pip: exactly one, unchanged requirements file, no extra args or packages.
    pips = re.findall(r"pip install[^\n]*", code)
    chk(errs, len(pips) == 1, "expected exactly 1 pip install, found %d" % len(pips))
    if pips:
        run = re.split(r"&&|;", pips[0])[0].strip()
        must(errs, r"-(r|requirement)\s+/tmp/requirements\.txt\b", run,
             "pip install must use /tmp/requirements.txt: %r" % run)
        chk(errs, not run.split("requirements.txt", 1)[-1].strip(),
            "pip install must not add extra arguments/packages: %r" % run)
    return errs


# --------------------------------------------------------------------- compose
def services_of(text):
    """Minimal `services:` reader -> {name: {"keys": set, "lines": [...]}}."""
    out, cur, section = {}, None, None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent, line = len(raw) - len(raw.lstrip(" ")), raw.strip()
        if indent == 0:
            section = line.split(":")[0].strip()
        elif section == "services" and indent == 2 and line.endswith(":"):
            cur = line[:-1].strip()
            out[cur] = {"keys": set(), "lines": []}
        elif cur:
            out[cur]["lines"].append(line)
            if indent == 4 and ":" in line:
                out[cur]["keys"].add(line.split(":")[0].strip())
    return out


def dur_seconds(block, key):
    """Parse a compose duration; None when absent or not a duration."""
    m = re.search(r"%s:\s*([0-9]+)(ms|s|m)\b" % key, block)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return n / 1000.0 if unit == "ms" else n * (60 if unit == "m" else 1)


COMPOSE_NEED = [
    (r"\$\{DASHBOARD_IMAGE:\?[^}]+\}", "image must use required ${DASHBOARD_IMAGE:?...}"),
    (r"\$\{DASHBOARD_ENV_FILE:\?[^}]+\}", "env_file must use required ${DASHBOARD_ENV_FILE:?...}"),
    (r'DEBUG:\s*"False"', 'DEBUG must be pinned "False"'),
    (r'DJANGO_SERVE_STATIC:\s*"true"', 'DJANGO_SERVE_STATIC must be pinned "true"'),
    (r"privileged:\s*false", "privileged: false should be explicit"),
    (r"read_only:\s*true", "read_only: true missing"),
    (r"init:\s*true", "init: true missing"),
    (r"cap_drop:\s*\n\s*-\s*ALL", "cap_drop: [ALL] missing"),
    (r"no-new-privileges:true", "security_opt no-new-privileges:true missing"),
    (r"network_mode:\s*host", "network_mode: host template missing"),
    (r"restart:\s*unless-stopped", "restart: unless-stopped missing"),
    (r"max-size:", "json-file log rotation max-size missing"),
    (r"max-file:", "json-file log rotation max-file missing"),
    (r"127\.0\.0\.1:18111", "healthcheck must target loopback 127.0.0.1:18111"),
    (r"DASHBOARD_HEALTH_HOST", "healthcheck Host must come from DASHBOARD_HEALTH_HOST"),
    (r"ProxyHandler\(\{\}\)", "healthcheck must disable env proxies (ProxyHandler({}))"),
]
COMPOSE_BAN = [
    (r"\$\{DASHBOARD_IMAGE:-", "image interpolation must not carry a default"),
    (r"env_file:[^\n]*\n\s*-\s*/(home|etc|srv|opt|root)/", "env_file must not hardcode a path"),
    (r"ALLOWED_HOSTS\s*[:=]", "compose must not set/weaken ALLOWED_HOSTS"),
    (r"privileged:\s*true", "privileged: true is forbidden"),
    (r"^\s*pid:\s*host", "pid: host is forbidden"),
    (r"18111:18111", "host port mapping forbidden"),
    (r"^\s*(command|entrypoint):", "command/entrypoint override found"),
    (r"redis://|celery", "service references redis/celery"),
]


def check_compose(text):
    errs, svcs = [], services_of(uncomment(text))
    chk(errs, len(svcs) == 1, "expected exactly 1 service, found %d: %r" % (len(svcs), list(svcs)))
    errs += ["service %r is a forbidden runtime" % n for n in svcs
             if re.search(r"redis|celery|beat|worker|postgres", n, re.I)]
    if not svcs:
        return errs
    svc = next(iter(svcs.values()))
    keys, block = svc["keys"], "\n".join(svc["lines"])
    chk(errs, "image" in keys, "no image key")
    for key in ("build", "ports", "volumes"):
        chk(errs, key not in keys, "%s key present: must stay image/CMD driven" % key)
    if "user" not in keys:
        errs.append("user: must be explicit")
    else:
        must(errs, r'user:\s*"?1000:1000"?\s*$', block, "user must be exactly 1000:1000")
    for pattern, msg in COMPOSE_NEED:
        must(errs, pattern, block, msg)
    for pattern, msg in COMPOSE_BAN:
        deny(errs, pattern, block, msg)
    grace, timeout = dur_seconds(block, "stop_grace_period"), dur_seconds(block, "timeout")
    chk(errs, grace is not None, "stop_grace_period missing or not a duration")
    chk(errs, timeout is not None, "healthcheck timeout missing or not a duration")
    if grace is not None and timeout is not None:
        chk(errs, grace > timeout * 2,
            "stop_grace_period (%ss) too short vs health timeout (%ss)" % (grace, timeout))
    return errs


CHECKS = [("Dockerfile", check_dockerfile), (".dockerignore", check_dockerignore),
          ("compose.dokploy.yaml", check_compose)]
D, I, C = "Dockerfile", ".dockerignore", "compose.dokploy.yaml"
# label, file, anchor, replacement, expected failure fragment
NEGATIVES = [
 ("root USER",D,"USER 1000:1000","USER root","root USER"),
 ("final USER 1001",D,"USER 1000:1000","USER 1001:1001","final USER"),
 ("USER 0:0",D,"USER 1000:1000","USER 0:0","root USER"),
 ("unpinned base",D,BASE_REF,"python:3.12-slim","not pinned"),
 ("ENTRYPOINT shell",D,'CMD ["daphne"','ENTRYPOINT ["/bin/sh","-c"]\nCMD ["daphne"',"ENTRYPOINT"),
 ("second daphne",D,'CMD ["daphne"','RUN ["daphne"]\nCMD ["daphne"]',"exactly once"),
 ("CMD altered port",D,'"-p", "18111"','"-p", "18112"',"CMD argv"),
 ("altered COPY dest",D,"COPY car_ads_dashboard/ /app/car_ads_dashboard/","COPY car_ads_dashboard/ /evil/","must land in"),
 ("COPY extra source",D,"COPY requirements.txt","COPY secrets.txt /app/\nCOPY requirements.txt","COPY"),
 ("pip extra package",D,"--requirement /tmp/requirements.txt","--requirement /tmp/requirements.txt foo","must not add extra"),
 ("startup migration",D,"WORKDIR /app/car_ads_dashboard","WORKDIR /app/car_ads_dashboard\nRUN python manage.py migrate","migrate"),
 ("env copied",D,"COPY requirements.txt","COPY .env /tmp/x\nCOPY requirements.txt","COPY"),
 ("ports mapped",C,"    network_mode: host",'    network_mode: host\n    ports: ["18111:18111"]',"ports"),
 ("redis service",C,"services:\n","services:\n  redis:\n    image: redis:7\n","service"),
 ("celery service",C,"services:\n","services:\n  celery:\n    image: celery:5\n","service"),
 ("privileged true",C,"    init: true","    init: true\n    privileged: true","privileged: true"),
 ("user root",C,'user: "1000:1000"','user: "0:0"',"user must be"),
 ("user removed",C,'    user: "1000:1000"\n',"","user: must be explicit"),
 ("read_only removed",C,"    read_only: true\n","","read_only"),
 ("init removed",C,"    init: true\n","","init: true"),
 ("cap_drop removed",C,"    cap_drop:\n      - ALL\n","","cap_drop"),
 ("no-new-priv removed",C,"      - no-new-privileges:true\n","","no-new-privileges"),
 ("debug on",C,'DEBUG: "False"','DEBUG: "True"',"DEBUG"),
 ("literal env path",C,"${DASHBOARD_ENV_FILE:?DASHBOARD_ENV_FILE must be an absolute path outside the repo}","/home/scrapper/prod/.env","DASHBOARD_ENV_FILE"),
 ("host pid",C,"    network_mode: host","    network_mode: host\n    pid: host","pid: host"),
 ("grace too short",C,"stop_grace_period: 40s","stop_grace_period: 1s","too short"),
 ("grace not duration",C,"stop_grace_period: 40s","stop_grace_period: soon","not a duration"),
 ("proxy guard removed",C,"urllib.request.ProxyHandler({})","urllib.request.ProxyHandler()","ProxyHandler"),
 ("tautological ignore",I,"# vcs and tooling state","*\n# vcs and tooling state","wrongly excludes"),
 ("nested env dropped",I,"**/.env\n","","**/.env"),
 ("nested logs dropped",I,"**/logs\n","","**/logs"),
 ("nested sqlite dropped",I,"**/*.sqlite3\n","","sqlite3"),
]


def run_positive():
    ok = True
    for name, fn in CHECKS:
        errs = fn(read(name))
        print(("PASS  " if not errs else "FAIL  ") + name)
        for e in errs:
            print("        - " + e)
        ok = ok and not errs
    return ok


def run_negative():
    base, fns, ok = {n: read(n) for n, _ in CHECKS}, dict(CHECKS), True
    for label, name, old, new, expect in NEGATIVES:
        if base[name].count(old) != 1:
            print("FAIL  negative anchor not unique/present: %s" % label)
            ok = False
            continue
        errs = fns[name](base[name].replace(old, new, 1))
        hit = [e for e in errs if expect in e]
        if hit:
            print("PASS  rejected %-20s -> %s" % (label, hit[0]))
        else:
            print("FAIL  %-22s %s" % (label, "wrong reason: %s" % errs[0] if errs else "NOT detected"))
            ok = False
    return ok


if __name__ == "__main__":
    pos, neg = run_positive(), run_negative()
    print("\nRESULT positive=%s negative=%s" % ("ok" if pos else "FAILED", "ok" if neg else "FAILED"))
    sys.exit(0 if (pos and neg) else 1)
