#!/usr/bin/env python3
"""Stdlib-only checks for the opt-in CARS_TERM_DIAGNOSTIC startup hook (M2-HOOK1).

Loads ``celery.py`` by file path inside a throwaway package whose ``celery``
module is a STUB (``Celery`` class + a fake ``worker_ready`` signal).  No real
Celery/Django import, no app boot, no broker/DB/Redis/env-file/task access, no
worker start, and no signal handler is installed or replaced anywhere.

Run: python3 tests/check_term_startup_hook.py
Exit 0 only if every case passes.
"""
import ast
import importlib
import importlib.util
import json
import multiprocessing
import os
import signal
import sys
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "car_ads_dashboard" / "car_ads_dashboard"
CELERY, HOOK = PKG / "celery.py", PKG / "term_startup_hook.py"
DIAG, INIT = PKG / "term_handler_diagnostic.py", PKG / "__init__.py"

SHA40 = "a217884b7f8df6d5bcd3d305d461d0a6ce399d5e"
DIAG_KEYS = {
    "pid", "release", "release_valid", "handler", "module_ok", "code_name_ok",
    "freevars_ok", "sig_ok", "how", "callback", "callback_ok", "exitcode",
    "verdict",
}
REPORT_KEYS = DIAG_KEYS | {"event", "status"}
STATUSES = {"usable", "release_invalid", "verdict_unknown", "inspect_failed"}
HOOK_NAME = "fakepkg.term_startup_hook"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class Hostile:
    """Every attribute access / repr / equality / call is recorded, then inert."""

    def __init__(self):
        self.touched = []

    def _touch(self, name):
        self.touched.append(name)

    def __repr__(self):
        self._touch("__repr__")
        return "SECRET_TASKDATA hostile"

    def __eq__(self, other):
        self._touch("__eq__")
        return True

    def __hash__(self):
        self._touch("__hash__")
        return id(self)

    def __getattr__(self, name):
        self._touch("__getattr__:" + name)
        return "SECRET_TASKDATA"

    def __call__(self, *args, **kwargs):
        self._touch("__call__")
        raise AssertionError("hostile object must never be called")


class FakeSignal:
    """Celery-shaped signal: dedups on dispatch_uid, rejects weak receivers."""

    def __init__(self):
        self.receivers = []

    def connect(self, receiver, sender=None, weak=True, dispatch_uid=None, **kw):
        if weak:
            raise AssertionError("hook must connect with a strong reference")
        key = (dispatch_uid, id(sender))
        if not any(existing == key for existing, _ in self.receivers):
            self.receivers.append((key, receiver))
        return receiver

    def send(self, sender=None, **named):
        return [(r, r(sender=sender, **named)) for _, r in list(self.receivers)]


class FakeApp:
    def __init__(self, name):
        self.name, self.config, self.autodiscovered = name, None, False

    def config_from_object(self, obj, namespace=None):
        self.config = (obj, namespace)

    def autodiscover_tasks(self):
        self.autodiscovered = True


class Sandbox:
    """Isolated sys.modules/env sandbox: stubbed celery, real hook + diagnostic."""

    NAMES = ("celery", "celery.signals", "fakepkg", "fakepkg.celery",
             HOOK_NAME, "fakepkg.term_handler_diagnostic")

    def __init__(self, **values):
        self.env, self.signal, self.apps = values, FakeSignal(), []
        self.raw = []  # raw logged report strings, for leak checks
        self._patcher = None

    def __enter__(self):
        for name in self.NAMES:
            sys.modules.pop(name, None)
        celery_mod, signals_mod = types.ModuleType("celery"), types.ModuleType("celery.signals")
        celery_mod.Celery, celery_mod.signals = self._make_app, signals_mod
        signals_mod.worker_ready = self.signal
        package = types.ModuleType("fakepkg")
        package.__path__ = [str(PKG)]
        sys.modules.update({"celery": celery_mod, "celery.signals": signals_mod,
                            "fakepkg": package})
        # Only the two selector variables exist; the real environment and any
        # dotenv file are never read or copied.
        self._patcher = mock.patch.dict(os.environ, self.env, clear=True)
        self._patcher.start()
        return self

    def __exit__(self, *exc_info):
        self._patcher.stop()
        for name in self.NAMES:
            sys.modules.pop(name, None)
        return False

    def _make_app(self, name):
        self.apps.append(FakeApp(name))
        return self.apps[-1]

    def load(self):
        spec = importlib.util.spec_from_file_location("fakepkg.celery", CELERY)
        module = importlib.util.module_from_spec(spec)
        sys.modules["fakepkg.celery"] = module
        spec.loader.exec_module(module)
        return module

    @property
    def hook(self):
        return sys.modules.get(HOOK_NAME)

    def emit(self, process_name="MainProcess", sender=None, **named):
        """Send worker_ready as Celery would; return the emitted JSON reports."""
        hook = self.hook
        logger = mock.Mock(wraps=hook.logger)
        with mock.patch.object(hook, "logger", logger), mock.patch.object(
            hook, "current_process",
            return_value=types.SimpleNamespace(name=process_name),
        ):
            self.signal.send(sender=sender, **named)
        self.raw.extend(call.args[1] for call in logger.info.call_args_list)
        return [json.loads(call.args[1]) for call in logger.info.call_args_list]


def env(release=SHA40, selector="1"):
    values = {} if selector is None else {"CARS_TERM_DIAGNOSTIC": selector}
    if release is not None:
        values["CARS_RELEASE_SHA"] = release
    return values


def fake_result(verdict="Warm", release=SHA40):
    warm = verdict == "Warm"
    return {
        "pid": os.getpid(), "release": release, "release_valid": release is not None,
        "handler": verdict, "module_ok": True, "code_name_ok": True,
        "freevars_ok": True, "sig_ok": True, "callback_ok": True,
        "how": "Warm" if warm else "Other",
        "callback": "None" if warm else "Other",
        "exitcode": "OK" if warm else "Other",
        "verdict": verdict,
    }


def one(reports):
    check(len(reports) == 1, f"expected exactly one report, got {len(reports)}")
    report = reports[0]
    check(report.get("status") in STATUSES, f"status outside fixed enum: {report!r}")
    check(set(report) == REPORT_KEYS or set(report) == {"event", "status"},
          f"report keys must be fixed, got {sorted(report)}")
    if "pid" in report:
        check(type(report["pid"]) is int, "pid must be int")
    return report


# ------------------------------------------------------------------ disabled
def case_disabled_by_default():
    selectors = (None, "0", "", "true", " 1", "1 ", "01", "1.0", "yes")
    for selector in selectors:
        with Sandbox(**env(selector=selector)) as box:
            module = box.load()
            check(HOOK_NAME not in sys.modules,
                  f"selector {selector!r} must not import the hook")
            check(box.signal.receivers == [],
                  f"selector {selector!r} must not connect")
            app, = box.apps
            check(module.app is app and len(box.apps) == 1,
                  "celery.py must still build exactly one app")
            check((app.config, app.autodiscovered)
                  == (("django.conf:settings", "CELERY"), True),
                  "baseline celery.py config/autodiscover must be unchanged")


# ------------------------------------------------------------------- wiring
def case_enabled_registration():
    with Sandbox(**env()) as box:
        box.load()
        hook = box.hook
        check(hook is not None, "selector '1' must import the hook")
        (key, receiver), = box.signal.receivers
        check(key[0] == hook.DISPATCH_UID and type(hook.DISPATCH_UID) is str
              and hook.DISPATCH_UID, f"stable dispatch_uid required: {key[0]!r}")
        check(receiver is hook.emit_startup_report,
              "strong reference to the module-level receiver required")
        box.load()
        check(len(box.signal.receivers) == 1,
              "duplicate registration must dedup on dispatch_uid")
        check(len(box.apps) == 2, "second boot must build a second app only")
        importlib.import_module(HOOK_NAME)
        check(len(box.signal.receivers) == 1, "re-import must not duplicate")


# ------------------------------------------------------------------ statuses
def case_status_table():
    rows = (("Warm", "usable"), ("Cold", "usable"), ("Unknown", "verdict_unknown"),
            ("Default", "verdict_unknown"), ("Unavailable", "verdict_unknown"))
    for verdict, expected in rows:
        with Sandbox(**env()) as box:
            box.load()
            with mock.patch.object(box.hook, "inspect_sigterm_handler",
                                   return_value=fake_result(verdict)):
                report = one(box.emit())
        check(report["status"] == expected,
              f"verdict {verdict} -> {report['status']}, want {expected}")
        check(report["verdict"] == verdict and report["release"] == SHA40
              and report["release_valid"] is True, f"report={report!r}")


def case_release_invalid_real_diagnostic():
    """Real diagnostic: missing/invalid release -> release_invalid, not echoed."""
    before = signal.getsignal(signal.SIGTERM)
    bad = (None, "", "not-a-sha", "SECRET_RELEASE_TOKEN", SHA40 + " ", "z" * 40,
           "A" * 40 + "g", "refs/heads/main", "../etc", "/home/scraper/release")
    for release in bad:
        with Sandbox(**env(release=release)) as box:
            box.load()
            report = one(box.emit())
        check(report["status"] == "release_invalid",
              f"{type(release).__name__} release -> {report['status']}")
        check(report["release"] is None and report["release_valid"] is False,
              "invalid release must be dropped, never echoed")
        blob = json.dumps(report)
        if release:  # an empty string is a substring of everything
            check(release not in blob, "invalid release text leaked into report")
    with Sandbox(**env()) as box:
        box.load()
        report = one(box.emit())
    check(report["status"] == "verdict_unknown",
          f"real non-Celery handler -> {report['status']}")
    check(report["release"] == SHA40, "valid release must be echoed")
    check(signal.getsignal(signal.SIGTERM) is before,
          "hook must not replace the process SIGTERM handler")


# ---------------------------------------------------------------- prefork/once
def case_prefork_skips():
    for name in ("ForkPoolWorker-1", "ForkPoolWorker-8", "MainProcess-1",
                 "celeryd", ""):
        with Sandbox(**env()) as box:
            box.load()
            with mock.patch.object(box.hook, "inspect_sigterm_handler") as stub:
                reports = box.emit(process_name=name)
        check(reports == [], f"child {name!r} must emit nothing")
        check(stub.call_count == 0, f"child {name!r} must not inspect the handler")


def case_once_per_pid():
    with Sandbox(**env()) as box:
        box.load()
        with mock.patch.object(box.hook, "inspect_sigterm_handler",
                               return_value=fake_result()) as stub:
            first, second = box.emit(), box.emit()
        check(len(first) == 1, f"first signal must emit one report: {len(first)}")
        check(second == [], "a repeated signal in the same PID must emit nothing")
        check(stub.call_count == 1, f"diagnostic ran {stub.call_count} times")


def case_current_process_guard_premise():
    """Stdlib premise check: a real forked child is never MainProcess."""
    check(multiprocessing.current_process().name == "MainProcess",
          "this check process must be MainProcess")
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    process = context.Process(target=lambda: queue.put(
        multiprocessing.current_process().name))
    process.start()
    try:
        name = queue.get(timeout=20)
    finally:
        process.join(20)
    check(process.exitcode == 0, f"child exit {process.exitcode}")
    check(name != "MainProcess", f"forked child {name!r} must not pass the guard")


# ------------------------------------------------------------- hostile/failed
def case_hostile_sender_and_kwargs():
    hostile = Hostile()
    with Sandbox(**env()) as box:
        box.load()
        with mock.patch.object(box.hook, "inspect_sigterm_handler",
                               return_value=fake_result()):
            report = one(box.emit(
                sender=hostile, sig=hostile, how=hostile, callback=hostile,
                exitcode=hostile, verbose=hostile, task=hostile, worker=hostile,
                headers=hostile, request={"args": ["SECRET_TASKDATA"]}))
    check(hostile.touched == [], f"hostile kwargs/sender touched: {hostile.touched}")
    blob = json.dumps(report)
    for leaked in ("SECRET_TASKDATA", "hostile", "0x"):
        check(leaked not in blob, f"signal payload leaked into report: {leaked!r}")
    check(set(report) == REPORT_KEYS, f"keys={sorted(report)}")


def case_failure_is_sanitized():
    secret = "SECRET_PASSWORD_abc123"
    with Sandbox(**env()) as box:
        box.load()
        hook = box.hook
        with mock.patch.object(hook, "inspect_sigterm_handler",
                               side_effect=RuntimeError(secret + " /home/x/.env")):
            check(one(box.emit())["status"] == "inspect_failed", "status")
            # A second signal in the same PID stays silent: no crash, no retry.
            check(box.emit() == [], "failing receiver must not re-emit")
            # A different PID is judged independently: the guard is not poisoned.
            with mock.patch.object(hook.os, "getpid", lambda: -12345):
                check(one(box.emit())["status"] == "inspect_failed", "second pid")
        # A broken logger must not propagate out of the receiver either.
        with mock.patch.object(hook, "logger", mock.Mock(
                info=mock.Mock(side_effect=RuntimeError(secret)))), \
             mock.patch.object(hook, "current_process",
                               return_value=types.SimpleNamespace(name="MainProcess")), \
             mock.patch.object(hook, "inspect_sigterm_handler",
                               return_value=fake_result()), \
             mock.patch.object(hook.os, "getpid", lambda: -54321):
            check(hook.emit_startup_report(sender=None) is None,
                  "broken logger must not raise out of the receiver")
        emitted = "".join(box.raw)
    check(len(box.raw) == 2, f"expected two reports, got {len(box.raw)}")
    for leaked in (secret, "/home", ".env", "RuntimeError", "Traceback", "None"):
        check(leaked not in emitted, f"failure payload leaked: {leaked!r}")


# ------------------------------------------------------- side effects / static
def case_no_handler_install_or_signals():
    with Sandbox(**env()) as box:
        before = signal.getsignal(signal.SIGTERM)
        with mock.patch.object(signal, "signal") as install, \
             mock.patch.object(signal, "raise_signal") as raise_signal, \
             mock.patch.object(os, "kill") as kill, \
             mock.patch.object(signal, "pthread_sigmask", create=True) as mask:
            box.load()
            box.emit()
        check(not install.called, "hook must never call signal.signal")
        check(not raise_signal.called, "hook must never raise a signal")
        check(not kill.called, "hook must never send a signal")
        check(not mask.called, "hook must never change the signal mask")
        check(signal.getsignal(signal.SIGTERM) is before,
              "hook must leave the SIGTERM handler untouched")


ALLOWED_IMPORTS = {"json", "logging", "os", "multiprocessing", "celery.signals"}
FORBIDDEN = ("signal.signal", "raise_signal", "os.kill", "pthread_sigmask",
             "apply_async", "send_task", "psycopg", "redis", "requests",
             "subprocess", "socket", "print(", "django", "task_logger",
             "basicconfig", "addhandler", "getenv")


def case_static_contract():
    source = HOOK.read_text(encoding="utf-8")
    tree = ast.parse(source)
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.add((node.level, node.module))
            else:
                absolute.add(node.module)
    check(absolute == ALLOWED_IMPORTS, f"imports changed: {sorted(absolute)}")
    check(relative == {(1, "term_handler_diagnostic")},
          f"hook must only import the existing diagnostic: {sorted(relative)}")
    doc = ast.get_docstring(tree) or ""
    code = source.replace(doc, "", 1).lower()
    for token in FORBIDDEN:
        check(token not in code, f"forbidden token in hook: {token!r}")
    check("json.dumps(" in source and '"%s"' in source,
          "report must be one pre-rendered JSON string passed as a %s argument")
    # Exactly one environment read here (the release id); the selector is read
    # in celery.py only.
    environ = ast.dump(ast.parse("os.environ", mode="eval").body)
    reads = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
             and ast.dump(node.func.value) == environ]
    check(len(reads) == 1, f"hook must read exactly one env var, saw {len(reads)}")

    celery_text = CELERY.read_text(encoding="utf-8")
    check("CARS_TERM_DIAGNOSTIC" in celery_text and "term_startup_hook" in celery_text,
          "celery.py must hold the opt-in hook guard")
    celery_tree = ast.parse(celery_text)
    guards = [n for n in celery_tree.body if isinstance(n, ast.If)]
    check(len(guards) == 1, f"expected one guard in celery.py, got {len(guards)}")
    node = guards[0].test
    check(isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.Eq)
          and isinstance(node.comparators[0], ast.Constant)
          and node.comparators[0].value == "1",
          "guard must compare the selector to the literal '1'")
    body = guards[0].body
    check(len(body) == 2 and isinstance(body[0], ast.ImportFrom)
          and body[0].module == "term_startup_hook"
          and isinstance(body[1], ast.Expr),
          f"guard body must be exactly the hook import plus register(): {body}")
    check("term_handler_diagnostic" not in celery_text,
          "celery.py must not import the diagnostic directly")
    check("term_startup_hook" not in INIT.read_text(encoding="utf-8")
          and "term_handler_diagnostic" not in INIT.read_text(encoding="utf-8"),
          "__init__.py must stay unwired")
    check("os.environ" not in DIAG.read_text(encoding="utf-8"),
          "diagnostic module must still read no environment")


def case_startup_order_source_text():
    """Pin the post-installation ordering from installed Celery SOURCE TEXT only.

    Textual evidence only -- no import, no app boot, no live claim.  The chain
    is: ``Worker.on_start`` -> ``install_platform_tweaks`` ->
    ``install_worker_term_handler`` (handler installed), and only later does the
    consumer fire ``worker_ready`` through ``Worker.on_consumer_ready``.
    """
    candidates = sorted(ROOT.glob("venv/lib/*/site-packages/celery/apps/worker.py"))
    check(len(candidates) == 1, f"expected one installed worker.py: {candidates}")
    text = candidates[0].read_text(encoding="utf-8")

    def body(name):
        start = text.index(f"    def {name}(")
        try:
            end = text.index("\n    def ", start + 1)
        except ValueError:
            end = len(text)
        return text[start:end]

    on_start = body("on_start")
    on_ready = body("on_consumer_ready")
    tweaks = body("install_platform_tweaks")
    check("self.install_platform_tweaks(self)" in on_start,
          "Worker.on_start must still install the platform tweaks")
    check("install_worker_term_handler(worker)" in tweaks,
          "TERM handler installation must stay inside install_platform_tweaks")
    check("signals.worker_ready.send(sender=consumer)" in on_ready,
          "worker_ready must still be emitted by on_consumer_ready")
    # on_start (handler installation) must be the earlier lifecycle hook.
    check(text.index("    def on_start(") < text.index("    def on_consumer_ready("),
          "on_start must precede on_consumer_ready in the worker lifecycle")

    # The ready callback reaches the consumer as init_callback ...
    components = candidates[0].parent.parent / "worker" / "components.py"
    check("init_callback=w.ready_callback" in components.read_text(encoding="utf-8"),
          "consumer must still receive Worker.ready_callback")
    # ... and is only invoked from on_ready, in the consumer start-up loop.
    consumer = candidates[0].parent.parent / "worker" / "consumer" / "consumer.py"
    consumer_text = consumer.read_text(encoding="utf-8")
    check("callback(self)" in consumer_text and "def on_ready" in consumer_text,
          "on_ready must invoke the ready callback")
    loops = candidates[0].parent.parent / "worker" / "loops.py"
    loops_text = loops.read_text(encoding="utf-8")
    consume, ready = loops_text.index("consumer.consume()"), loops_text.index("obj.on_ready()")
    check(consume < ready, "worker_ready must fire after the consumer starts")
    # Blueprint invokes on_start before any substep.
    steps = (candidates[0].parent.parent / "bootsteps.py").read_text(encoding="utf-8")
    check(steps.index("if self.on_start:") < steps.index("step.start(parent)"),
          "blueprint on_start must run before the substeps")


CASES = (
    ("disabled by default -> no import, no connect, baseline intact", case_disabled_by_default),
    ("enabled -> one strong receiver, idempotent registration", case_enabled_registration),
    ("Warm/Cold/Unknown status table", case_status_table),
    ("missing/invalid release -> release_invalid (real diagnostic)", case_release_invalid_real_diagnostic),
    ("prefork children skip without inspecting", case_prefork_skips),
    ("one report per PID, repeated signal silent", case_once_per_pid),
    ("current_process guard premise (real fork)", case_current_process_guard_premise),
    ("hostile sender/kwargs untouched, no leak", case_hostile_sender_and_kwargs),
    ("failure sanitized, worker/disturbance-free", case_failure_is_sanitized),
    ("no handler install / no signal sent", case_no_handler_install_or_signals),
    ("static contract: imports, env reads, guard", case_static_contract),
    ("post-installation order pinned from Celery source text", case_startup_order_source_text),
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
