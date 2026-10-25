"""Opt-in worker startup SIGTERM-handler report hook (M2-HOOK1).

SOURCE/TEST ONLY; NOT DEPLOYED, NO RUNTIME PROOF.  ``celery.py`` (the existing
app boot context) imports and registers this module only when the single
environment selector ``CARS_TERM_DIAGNOSTIC`` is exactly ``"1"``;
unset/empty/anything else leaves the worker untouched and this module is not
even imported.  That opt-in wiring is approved and implemented here, and is
disabled by default.  The receiver fires on Celery's ``worker_ready`` signal,
which the installed worker emits from ``Worker.on_consumer_ready`` *after*
``Worker.on_start`` ran ``install_platform_tweaks`` (the SIGTERM handler
installation), so the read happens after handler installation.

The receiver is MainProcess-only, using the same trusted process guard as the
installed handler (``multiprocessing.current_process().name``) rather than
the signal's ``sender``/kwargs identity.  ``CARS_RELEASE_SHA`` is read only
when enabled and handed to the existing read-only diagnostic, which validates
it (missing/invalid is reported as unusable, never echoed).  Nothing here
installs, replaces or sets a signal handler, writes a signal, enqueues work,
touches Django/settings/tasks/DB/broker, or reads task data.

Exactly one report per process is emitted through the standard logging
logger (no new handler, no new dependency): a single JSON object with a fixed
key set and a fixed ``status`` enum.  Evidence is usable only for
``status == "usable"``; ``release_invalid``, ``verdict_unknown`` and
``inspect_failed`` all mean "REMAP unproven" and are logged only -- they
never raise, abort or stop the worker.  A report is valid only for the PID
that produced it and goes stale if the handler changes later.

No runtime proof is delivered by this module: the wire-up is source-only,
and deployment, restart and any live read each need their own approval.
"""

import json
import logging
import os
from multiprocessing import current_process

from celery.signals import worker_ready

from .term_handler_diagnostic import inspect_sigterm_handler

logger = logging.getLogger(__name__)

SELECTOR_ENV = "CARS_TERM_DIAGNOSTIC"
RELEASE_ENV = "CARS_RELEASE_SHA"
EVENT = "cars_term_startup_diagnostic"
DISPATCH_UID = "cars-term-startup-diagnostic"

STATUS_USABLE = "usable"
STATUS_RELEASE_INVALID = "release_invalid"
STATUS_VERDICT_UNKNOWN = "verdict_unknown"
STATUS_INSPECT_FAILED = "inspect_failed"

_EMITTED_PID = None


def emit_startup_report(sender=None, **kwargs):
    """``worker_ready`` receiver: at most one fixed report per process.

    ``sender``/``kwargs`` are never used, echoed or reformatted -- the guard is
    the trusted process identity, exactly like the installed handler's.
    """
    global _EMITTED_PID
    if current_process().name != "MainProcess":
        return
    pid = os.getpid()
    if _EMITTED_PID == pid:
        return
    _EMITTED_PID = pid
    report = {"event": EVENT}
    try:
        result = inspect_sigterm_handler(os.environ.get(RELEASE_ENV))
        report.update(result)
        if not result["release_valid"]:
            report["status"] = STATUS_RELEASE_INVALID
        elif result["verdict"] in ("Warm", "Cold"):
            report["status"] = STATUS_USABLE
        else:
            report["status"] = STATUS_VERDICT_UNKNOWN
    except Exception:  # a diagnostic fault must never disturb worker startup
        report = {"event": EVENT, "status": STATUS_INSPECT_FAILED}
    try:
        # Only a pre-rendered JSON string is handed to the logger: no dict or
        # object is formatted by the logging layer.
        logger.info("%s", json.dumps(report, sort_keys=True))
    except Exception:  # a broken logger must not abort worker startup either
        return


def register():
    """Connect the receiver once, with a stable uid and a strong reference."""
    worker_ready.connect(
        emit_startup_report, weak=False, dispatch_uid=DISPATCH_UID
    )
