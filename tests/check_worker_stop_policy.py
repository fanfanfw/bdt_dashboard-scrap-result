#!/usr/bin/env python3
"""Offline check for ops/worker-alignment/10-safe-stop.conf.

Read-only: parses the proposal strictly, then stages throwaway fixtures under
/tmp/opencode.* and runs `systemd-analyze verify` only. Nothing is installed,
started, stopped, reloaded, or executed by a service manager. verify parses
unit files; the fixture ExecStart=/bin/true is never run.
"""
import configparser
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "ops" / "worker-alignment" / "10-safe-stop.conf"
UNIT = "celery-fixture.service"
DROPIN = "10-safe-stop.conf"
EXPECTED = {
    "KillMode": "mixed",
    "KillSignal": "SIGTERM",
    "SendSIGKILL": "no",
    "TimeoutStopSec": "infinity",
}
NEGATIVE = (
    ("KillMode", "notvalid"),
    ("KillSignal", "NOTASIGNAL"),
    ("SendSIGKILL", "perhaps"),
    ("TimeoutStopSec", "notduration"),
)
UNIT_TEXT = (
    "[Unit]\nDescription=Offline worker stop policy fixture\n"
    "DefaultDependencies=no\n\n[Service]\nType=simple\nExecStart=/bin/true\n"
)
ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LC_ALL": "C",
    "LANG": "C",
}


class PolicyError(Exception):
    pass


def parse_conf(path):
    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str
    try:
        with open(path, encoding="utf-8") as handle:
            parser.read_file(handle)
    except (configparser.Error, OSError) as exc:
        raise PolicyError("cannot parse %s: %s" % (path, exc)) from exc
    if parser.sections() != ["Service"]:
        raise PolicyError("expected only [Service], got %r" % parser.sections())
    got = dict(parser.items("Service"))
    if got != EXPECTED:
        raise PolicyError("directives differ: want %r, got %r" % (EXPECTED, got))
    return got


def check_comments(text):
    low = text.lower()
    for phrase in ("proposal only", "not installed", "indefinite",
                   "no oom protection", "preserved", "environmentfile"):
        if phrase not in low:
            raise PolicyError("required proposal/caveat text missing: %r" % phrase)


def run_verify(base):
    # --man=no keeps this offline/deterministic on local systemd 249.
    # SYSTEMD_UNIT_PATH hides host units so unrelated noise is visible as noise.
    env = dict(ENV, SYSTEMD_UNIT_PATH=str(base))
    return subprocess.run(
        ["systemd-analyze", "verify", "--man=no", str(base / UNIT)],
        env=env, capture_output=True, text=True, check=False,
    )


def stage(base, text):
    (base / UNIT).write_text(UNIT_TEXT, encoding="utf-8")
    dropin_dir = base / (UNIT + ".d")
    if dropin_dir.exists():
        shutil.rmtree(dropin_dir)
    dropin_dir.mkdir()
    (dropin_dir / DROPIN).write_text(text, encoding="utf-8")
    return base / UNIT


def show(label, proc):
    print("%s rc=%s stdout=%r stderr=%r"
          % (label, proc.returncode, proc.stdout, proc.stderr))


def main():
    failures = []

    def fail(message):
        failures.append(message)
        print("FAIL: " + message)

    probe = subprocess.run(["systemd-analyze", "verify", "--help"], env=ENV,
                           capture_output=True, text=True, check=False)
    if probe.returncode != 0 or "--man" not in probe.stdout + probe.stderr:
        show("verify-help", probe)
        fail("verify does not document --man; refusing to ignore")
        return 1
    if not CONF.is_file():
        fail("missing proposal file: %s" % CONF)
        return 1
    text = CONF.read_text(encoding="utf-8")
    try:
        parse_conf(CONF)
        check_comments(text)
        print("PASS: proposal has only [Service] and the four exact directives")
    except PolicyError as exc:
        fail(str(exc))
        return 1

    with tempfile.TemporaryDirectory(prefix="worker-stop.", dir="/tmp/opencode") as tmp:
        base = Path(tmp)
        stage(base, text)
        shutil.copyfile(CONF, base / (UNIT + ".d") / DROPIN)  # verify the real file
        proc = run_verify(base)
        show("positive", proc)
        if proc.returncode == 0 and proc.stdout == "" and proc.stderr == "":
            print("PASS: positive fixture verifies with empty stdout+stderr")
        else:
            fail("positive verify was not rc=0 with empty stdout+stderr")
        # verify returns rc=0 for parse warnings, so inspect all output, not rc.
        for key, bad in NEGATIVE:
            mutated = [(key + "=" + bad) if line.startswith(key + "=") else line
                       for line in text.splitlines()]
            stage(base, "\n".join(mutated) + "\n")
            try:
                parse_conf(base / (UNIT + ".d") / DROPIN)
            except PolicyError:
                checker_ok = True
            else:
                checker_ok = False
                fail("checker accepted drift %s=%s" % (key, bad))
            proc = run_verify(base)
            combined = proc.stdout + proc.stderr
            show("negative %s=%s" % (key, bad), proc)
            if not combined:
                fail("verify emitted no diagnostic for %s=%s; drop-in unread?"
                     % (key, bad))
            elif DROPIN not in combined:
                fail("diagnostic does not name %s; provenance unproven" % DROPIN)
            elif checker_ok:
                print("PASS: rejected %s=%s and verify named the drop-in"
                      % (key, bad))
            stage(base, text)

    if failures:
        print("RESULT: FAIL (%d issue(s))" % len(failures))
        return 1
    print("RESULT: PASS (local syntax/offline fixture only; no install or runtime action)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
