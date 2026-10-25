#!/usr/bin/env python3
"""Stdlib-only checks for car_ads_dashboard.term_handler_diagnostic (M2-DIAG1).

Source/test local only: no Celery/Django import, no app boot, no broker/DB/
Redis/env/task access, no deploy/restart.  Synthetic closures are crafted to
mirror the pinned Celery 5.5.3 ``celery/apps/worker._shutdown_handler`` closure
(``_handle_request`` with free vars worker/sig/how/callback/exitcode/verbose,
renamed ``worker_Warm``/``worker_Cold``).  ``signal.getsignal`` is patched via
``unittest.mock`` for the positive/negative cases and the real handler is only
read, never replaced, in the last case.

Run: python3 tests/check_term_handler_diagnostic.py
Exit 0 only if every case passes.
"""
import ast
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "car_ads_dashboard" / "car_ads_dashboard" / "term_handler_diagnostic.py"

import signal  # noqa: E402

# Loaded by path on purpose: importing the package would execute
# car_ads_dashboard/__init__.py -> celery.py (app construction). The diagnostic
# must be importable without app boot, no Celery/Django installed here.
_spec = importlib.util.spec_from_file_location("term_handler_diagnostic_under_test", MODULE)
diag = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = diag
_spec.loader.exec_module(diag)

EXPECTED_MODULE = "celery.apps.worker"
EXPECTED_KEYS = {
    "pid", "release", "release_valid", "handler", "module_ok", "code_name_ok",
    "freevars_ok", "sig_ok", "how", "callback", "callback_ok", "exitcode",
    "verdict",
}
ALLOWED = {
    "handler": {"Warm", "Cold", "Other", "Default", "Ignored", "Unavailable"},
    "how": {"Warm", "Cold", "Other"},
    "callback": {"None", "on_cold_shutdown", "Other"},
    "exitcode": {"OK", "FAILURE", "Other"},
    "verdict": {"Warm", "Cold", "Unknown"},
}
SHA40 = "a217884b7f8df6d5bcd3d305d461d0a6ce399d5e"
SHA64 = "0123456789abcdef" * 4
CAPTURED = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------- synthetic shape
def make_cold_callback():
    def on_cold_shutdown(worker):
        raise AssertionError("cold callback must never be called by the diagnostic")

    on_cold_shutdown.__module__ = EXPECTED_MODULE
    return on_cold_shutdown


def make_closure(how, *, callback=None, exitcode=0, sig="SIGTERM", verbose=True,
                 worker=None, code_name="_handle_request", freevars=None,
                 varargs=True):
    """Build a function mirroring Celery's _handle_request closure.

    Defaults reproduce the pinned shape: code name ``_handle_request``,
    ``*args``, and the six free variables in Celery's order.  ``freevars``
    overrides the captured names to forge malformed shapes.  Every captured
    object is inert and must never be invoked.
    """
    captured = {
        "worker": worker,
        "sig": sig,
        "how": how,
        "callback": callback,
        "exitcode": exitcode,
        "verbose": verbose,
    }
    names = tuple(captured) if freevars is None else tuple(freevars)
    args = "*args" if varargs else ""
    body = f"def {code_name}({args}):\n    raise AssertionError('never called')\n"
    namespace = {}
    exec(compile(body, "<synthetic-handler>", "exec"), namespace)
    code = namespace[code_name].__code__
    if not names:
        return types.FunctionType(code, {}, code_name)
    code = code.replace(co_freevars=names)
    closure = tuple(types.CellType(captured.get(name)) for name in names)
    return types.FunctionType(code, {}, code_name, None, closure)


def warm_handler():
    func = make_closure("Warm", callback=None, exitcode=0)
    func.__name__ = "worker_Warm"
    func.__module__ = EXPECTED_MODULE
    return func


def cold_handler():
    func = make_closure("Cold", callback=make_cold_callback(), exitcode=1)
    func.__name__ = "worker_Cold"
    func.__module__ = EXPECTED_MODULE
    return func


def with_handler(handler):
    return mock.patch.object(signal, "getsignal", return_value=handler)


def run(handler, release=SHA40):
    with with_handler(handler):
        return diag.inspect_sigterm_handler(release=release)


def assert_report_shape(report):
    check(isinstance(report, dict), "report must be a dict")
    check(set(report) == EXPECTED_KEYS, f"unexpected report keys: {sorted(report)}")
    check(type(report["pid"]) is int, "pid must be int")
    check(type(report["release_valid"]) is bool, "release_valid must be bool")
    for flag in ("module_ok", "code_name_ok", "freevars_ok", "sig_ok", "callback_ok"):
        check(type(report[flag]) is bool, f"{flag} must be bool")
    for key, allowed in ALLOWED.items():
        check(report[key] in allowed, f"{key}={report[key]!r} outside allowlist")
    check(report["release"] is None or type(report["release"]) is str,
          "release must be str or None")
    CAPTURED.append(report)


# ---------------------------------------------------------------- positive cases
def case_warm_positive():
    report = run(warm_handler())
    assert_report_shape(report)
    check(report["handler"] == "Warm", f"handler={report['handler']}")
    check(report["how"] == "Warm" and report["verdict"] == "Warm",
          f"how/verdict={report['how']}/{report['verdict']}")
    check(report["callback"] == "None" and report["callback_ok"] is True,
          "Warm callback must be None")
    check(report["exitcode"] == "OK", f"exitcode={report['exitcode']}")
    check(report["sig_ok"] is True, "captured SIGTERM must be recognized")
    check(report["release"] == SHA40 and report["release_valid"] is True,
          "release must be the validated commit SHA")


def case_cold_positive():
    report = run(cold_handler())
    assert_report_shape(report)
    check(report["handler"] == "Cold", f"handler={report['handler']}")
    check(report["how"] == "Cold" and report["verdict"] == "Cold",
          f"how/verdict={report['how']}/{report['verdict']}")
    check(report["callback"] == "on_cold_shutdown" and report["callback_ok"] is True,
          f"cold callback={report['callback']}/{report['callback_ok']}")
    check(report["exitcode"] == "FAILURE", f"exitcode={report['exitcode']}")
    check(report["sig_ok"] is True, "captured SIGTERM must be recognized")


# ------------------------------------------------------------ captured signal
def case_sigquit_warm_shape_rejected():
    """The SIGQUIT channel uses the same closure; it must never read as TERM."""
    func = make_closure("Warm", callback=None, exitcode=0, sig="SIGQUIT")
    func.__name__, func.__module__ = "worker_Warm", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["sig_ok"] is False, "SIGQUIT capture must set sig_ok False")
    check(report["handler"] == "Other", f"handler={report['handler']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


def case_sigquit_cold_shape_rejected():
    func = make_closure("Cold", callback=make_cold_callback(), exitcode=1,
                        sig="SIGQUIT")
    func.__name__, func.__module__ = "worker_Cold", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["sig_ok"] is False and report["callback"] == "on_cold_shutdown",
          f"sig_ok/callback={report['sig_ok']}/{report['callback']}")
    check(report["handler"] == "Other", f"handler={report['handler']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


def case_hostile_sig_values():
    """Non-exact-str / lookalike sig captures must fail closed without touching."""
    hostile = Hostile()
    lookalikes = (
        hostile,                        # arbitrary object
        "sigterm",                      # wrong case
        "SIGTERM ",                     # trailing space
        " SIGTERM",                     # leading space
        "sig.SIGTERM",                  # qualname-ish text
        "",
        b"SIGTERM",                     # bytes
        signal.SIGTERM,                 # the int 15, not the name
        None,
    )

    class FakeSig(str):
        def __eq__(self, other):  # pragma: no cover - must never be reached
            CAPTURED.append("FakeSig.__eq__")
            return True

        __hash__ = str.__hash__

        def __repr__(self):
            CAPTURED.append("FakeSig.__repr__")
            return "SIGTERM"

    lookalikes = lookalikes + (FakeSig("SIGTERM"),)
    for index, value in enumerate(lookalikes):
        func = make_closure("Warm", callback=None, exitcode=0, sig=value)
        func.__name__, func.__module__ = "worker_Warm", EXPECTED_MODULE
        report = run(func)
        assert_report_shape(report)
        # Never format `value` into a message: that would call its __repr__
        # from the harness and mask the property under test.
        check(report["sig_ok"] is False, f"lookalike sig #{index} must not be accepted")
        check(report["handler"] == "Other", f"handler={report['handler']} for #{index}")
        check(report["verdict"] == "Unknown", f"verdict={report['verdict']} for #{index}")
    check(hostile.touched == [], f"hostile sig object touched: {hostile.touched}")
    check("FakeSig.__eq__" not in CAPTURED and "FakeSig.__repr__" not in CAPTURED,
          f"str-subclass sig methods were invoked: {CAPTURED}")


# ---------------------------------------------------------------- negative cases
def case_warm_carrying_cold_callback():
    func = make_closure("Warm", callback=make_cold_callback(), exitcode=1)
    func.__name__, func.__module__ = "worker_Warm", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")
    check(report["callback"] == "on_cold_shutdown", "callback label must stay factual")


def case_cold_with_missing_callback():
    func = make_closure("Cold", callback=None, exitcode=1)
    func.__name__, func.__module__ = "worker_Cold", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


def case_cold_with_foreign_callback():
    def other(worker):
        raise AssertionError("never called")

    func = make_closure("Cold", callback=other, exitcode=1)
    func.__name__, func.__module__ = "worker_Cold", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["callback"] == "Other" and report["callback_ok"] is False,
          f"callback={report['callback']}/{report['callback_ok']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


def case_cold_with_wrong_exitcode():
    func = make_closure("Cold", callback=make_cold_callback(), exitcode=0)
    func.__name__, func.__module__ = "worker_Cold", EXPECTED_MODULE
    report = run(func)
    check(report["exitcode"] == "OK" and report["verdict"] == "Unknown",
          f"exitcode/verdict={report['exitcode']}/{report['verdict']}")


def case_wrong_name():
    func = make_closure("Warm", callback=None, exitcode=0)
    func.__name__, func.__module__ = "worker_Cold", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["handler"] == "Other" and report["verdict"] == "Unknown",
          f"name/how mismatch must not be Warm: {report['handler']}")


def case_wrong_module():
    func = make_closure("Warm", callback=None, exitcode=0)
    func.__name__, func.__module__ = "worker_Warm", "custom.worker"
    report = run(func)
    assert_report_shape(report)
    check(report["handler"] == "Other" and report["module_ok"] is False,
          f"handler/module_ok={report['handler']}/{report['module_ok']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


def case_inconsistent_code_name():
    func = make_closure("Cold", callback=make_cold_callback(), exitcode=1,
                        code_name="_shutdown_handler")
    func.__name__, func.__module__ = "worker_Cold", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["code_name_ok"] is False and report["verdict"] == "Unknown",
          f"code_name_ok/verdict={report['code_name_ok']}/{report['verdict']}")


def case_malformed_freevars():
    func = make_closure("Warm", callback=None, exitcode=0,
                        freevars=("how", "callback", "exitcode"))
    func.__name__, func.__module__ = "worker_Warm", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["freevars_ok"] is False and report["verdict"] == "Unknown",
          f"freevars_ok/verdict={report['freevars_ok']}/{report['verdict']}")


def case_non_varargs_closure():
    func = make_closure("Warm", callback=None, exitcode=0, varargs=False)
    func.__name__, func.__module__ = "worker_Warm", EXPECTED_MODULE
    report = run(func)
    check(report["freevars_ok"] is False and report["verdict"] == "Unknown",
          "non-varargs handler is not the pinned shape")


def case_string_how():
    func = make_closure("SIGQUIT", callback=None, exitcode=0)
    func.__name__, func.__module__ = "worker_SIGQUIT", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["how"] == "Other" and report["handler"] == "Other",
          f"how/handler={report['how']}/{report['handler']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


def case_custom_builtin_default_ignored():
    def custom(signum, frame):
        raise AssertionError("never called")

    for handler, label in ((custom, "Other"), (signal.SIG_DFL, "Default"),
                           (signal.SIG_IGN, "Ignored"), (object(), "Other"),
                           (print, "Other"), (None, "Other")):
        report = run(handler)
        assert_report_shape(report)
        check(report["handler"] == label,
              f"{type(handler)!r} handler={report['handler']} expected {label}")
        check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


# ---------------------------------------------------------------- hostile objects
class Hostile:
    """Every attribute access / repr / equality must be recorded, then ignored."""

    def __init__(self):
        self.touched = []

    def _touch(self, name):
        self.touched.append(name)
        CAPTURED.append(name)

    def __repr__(self):
        self._touch("__repr__")
        return "worker_Warm"

    def __eq__(self, other):
        self._touch("__eq__")
        return True

    def __hash__(self):
        self._touch("__hash__")
        return id(self)

    def __getattr__(self, name):
        self._touch(f"__getattr__:{name}")
        return warm_handler()

    def __call__(self, *args, **kwargs):
        self._touch("__call__")
        raise AssertionError("hostile object must never be called")


def case_hostile_handler_object():
    hostile = Hostile()
    report = run(hostile)
    assert_report_shape(report)
    check(report["handler"] == "Other", f"handler={report['handler']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")
    check(hostile.touched == [], f"hostile handler touched attributes: {hostile.touched}")


def case_hostile_closure_values():
    hostile = Hostile()
    func = make_closure("Warm", callback=None, exitcode=0, worker=hostile)
    func.__name__, func.__module__ = "worker_Warm", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["verdict"] == "Warm", "inert worker object must not block Warm")
    check(hostile.touched == [], f"closure object touched: {hostile.touched}")


def case_hostile_callback_object():
    hostile = Hostile()
    func = make_closure("Cold", callback=hostile, exitcode=1)
    func.__name__, func.__module__ = "worker_Cold", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["callback"] == "Other" and report["verdict"] == "Unknown",
          f"callback/verdict={report['callback']}/{report['verdict']}")
    check(hostile.touched == [], f"hostile callback touched: {hostile.touched}")


def case_str_subclass_release_and_values():
    class FakeStr(str):
        def __eq__(self, other):  # pragma: no cover - must never be reached
            CAPTURED.append("FakeStr.__eq__")
            return True

        __hash__ = str.__hash__

        def __repr__(self):
            CAPTURED.append("FakeStr.__repr__")
            return "worker_Warm"

    report = run(warm_handler(), release=FakeStr("release-x"))
    assert_report_shape(report)
    check(report["release"] is None and report["release_valid"] is False,
          "str subclass release must be rejected, not echoed")

    func = make_closure(FakeStr("Warm"), callback=None, exitcode=0)
    func.__name__, func.__module__ = "worker_Warm", EXPECTED_MODULE
    report = run(func)
    assert_report_shape(report)
    check(report["how"] == "Other", f"str subclass how must be Other: {report['how']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")

    check("FakeStr.__eq__" not in CAPTURED and "FakeStr.__repr__" not in CAPTURED,
          f"str subclass methods were invoked: {CAPTURED}")


def case_release_validation():
    # Only an exact 40/64-char hex commit SHA survives; everything else is
    # dropped so no free text (potentially a secret) can be echoed back.
    bad = (
        None, "", "-x", ".", "..", "has space", "a" * 121, 42, b"release",
        ["release"], "../etc", "line\nbreak", "\x00",
        "SECRET_TOKEN_abc123", "release-20261024.1", "edge-stage-01/prod",
        "a" * 39, "a" * 41, "a" * 63, "a" * 65, "g" * 40, "z" * 64,
        SHA40 + " ", " " + SHA40, SHA40.upper() + "g",
        "0x" + SHA40, "refs/heads/main", "/home/scraper/release",
        "0123456789abcdef" * 5,
    )
    for value in bad:
        report = run(warm_handler(), release=value)
        assert_report_shape(report)
        check(report["release"] is None and report["release_valid"] is False,
              f"release {value!r} must be rejected, got {report['release']!r}")
    for good in (SHA40, SHA64, "A" * 40, "f" * 64):
        report = run(warm_handler(), release=good)
        assert_report_shape(report)
        check(report["release"] == good and report["release_valid"] is True,
              f"valid commit SHA {good!r} must be echoed unchanged")


def case_getsignal_failure():
    with mock.patch.object(signal, "getsignal", side_effect=ValueError("no threads")):
        report = diag.inspect_sigterm_handler(release=None)
    assert_report_shape(report)
    check(report["handler"] == "Unavailable" and report["verdict"] == "Unknown",
          f"handler/verdict={report['handler']}/{report['verdict']}")
    check(report["release"] is None and report["release_valid"] is False,
          "missing release must be reported, not invented")


# ---------------------------------------------------------------- static/no-boot
FORBIDDEN_TOKENS = (
    "import celery", "import django", "from celery", "from django",
    "signal.signal", "os.environ", "getenv", "import logging",
    "import requests", "import socket", "import redis", "import psycopg",
    "import subprocess", "open(", "setproctitle", "print(",
)


def case_module_is_pure_and_optin_only():
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    check(imported <= {"os", "signal", "types"},
          f"module imports must be stdlib-only: {sorted(imported)}")
    lowered = source.lower()
    for token in FORBIDDEN_TOKENS:
        check(token not in lowered, f"forbidden token in module: {token!r}")
    check("getsignal" in source and "SIGTERM" in source,
          "module must read signal.getsignal(SIGTERM)")

    # Approved M2-HOOK1 wiring: celery.py may only reach this module through
    # the opt-in startup hook behind the CARS_TERM_DIAGNOSTIC guard, never
    # directly, and __init__.py stays unwired.
    celery_text = (ROOT / "car_ads_dashboard" / "car_ads_dashboard" / "celery.py").read_text(encoding="utf-8")
    init_text = (ROOT / "car_ads_dashboard" / "car_ads_dashboard" / "__init__.py").read_text(encoding="utf-8")
    check("term_handler_diagnostic" not in celery_text,
          "celery.py must not import the diagnostic directly")
    check("term_handler_diagnostic" not in init_text,
          "diagnostic must not be auto-wired into __init__.py")
    check("term_startup_hook" in celery_text and "CARS_TERM_DIAGNOSTIC" in celery_text,
          "the only approved wiring is the opt-in CARS_TERM_DIAGNOSTIC hook")


def case_real_handler_read_only():
    before = signal.getsignal(signal.SIGTERM)
    report = diag.inspect_sigterm_handler(release=SHA40)
    after = signal.getsignal(signal.SIGTERM)
    check(before is after, "diagnostic replaced the process SIGTERM handler")
    assert_report_shape(report)
    check(report["handler"] in {"Other", "Default", "Ignored"},
          f"check process must be non-Celery, got {report['handler']}")
    check(report["verdict"] == "Unknown", f"verdict={report['verdict']}")


def case_no_free_text_leak():
    hostile = Hostile()
    secret = "SECRET_TOKEN_abc123"
    # Free text is never a valid release id, so it can never reach the report.
    report = run(hostile, release=secret)
    blob = repr(report)
    check(report["release"] is None and report["release_valid"] is False,
          "free-text release must be dropped, not echoed")
    check(secret not in blob, "free-text release leaked into the report")
    rejected = "has space SECRET"
    report2 = run(hostile, release=rejected)
    check(rejected not in repr(report2), "rejected release text leaked into the report")
    check(report2["release"] is None, "rejected release must be dropped")
    check("0x" not in blob, "object address leaked into the report")
    check("hostile" not in blob.lower() and "worker_Warm" not in blob,
          "handler object text leaked into the report")
    # A valid SHA is the only echoed value.
    report3 = run(hostile, release=SHA40)
    check(report3["release"] == SHA40 and report3["release_valid"] is True,
          "commit SHA must survive")
    assert_report_shape(report)
    rendered = {key: report[key] for key in EXPECTED_KEYS}
    check(set(rendered) == EXPECTED_KEYS, "report rendering changed")


CASES = (
    ("Warm positive", case_warm_positive),
    ("Cold positive", case_cold_positive),
    ("SIGQUIT-shaped Warm rejected -> Unknown", case_sigquit_warm_shape_rejected),
    ("SIGQUIT-shaped Cold rejected -> Unknown", case_sigquit_cold_shape_rejected),
    ("hostile/lookalike sig captures rejected", case_hostile_sig_values),
    ("Warm carrying cold callback -> Unknown", case_warm_carrying_cold_callback),
    ("Cold without callback -> Unknown", case_cold_with_missing_callback),
    ("Cold with foreign callback -> Unknown", case_cold_with_foreign_callback),
    ("Cold with wrong exitcode -> Unknown", case_cold_with_wrong_exitcode),
    ("inconsistent handler name -> Other", case_wrong_name),
    ("custom module -> Other", case_wrong_module),
    ("inconsistent code name -> Unknown", case_inconsistent_code_name),
    ("malformed free vars -> Unknown", case_malformed_freevars),
    ("non-varargs closure -> Unknown", case_non_varargs_closure),
    ("non-enum how -> Other", case_string_how),
    ("custom/default/ignored/none -> Other/Default/Ignored", case_custom_builtin_default_ignored),
    ("hostile handler object untouched", case_hostile_handler_object),
    ("hostile closure value untouched", case_hostile_closure_values),
    ("hostile callback object untouched", case_hostile_callback_object),
    ("str subclass rejected without __eq__/__repr__", case_str_subclass_release_and_values),
    ("release validation", case_release_validation),
    ("getsignal failure -> Unavailable", case_getsignal_failure),
    ("module stdlib-only and opt-in wired only", case_module_is_pure_and_optin_only),
    ("real handler read-only", case_real_handler_read_only),
    ("no free text/address leak", case_no_free_text_leak),
)


def main():
    failures = 0
    for label, case in CASES:
        try:
            case()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {label}: {exc}")
        else:
            print(f"PASS {label}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} cases passed")
    if failures:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
