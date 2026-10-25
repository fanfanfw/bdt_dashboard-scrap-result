"""Read-only in-process SIGTERM handler diagnostic (M2-DIAG1).

Standalone callable prepared for a FUTURE approved worker startup hook.
It is NOT imported by ``celery.py`` or ``__init__.py``, installs no handler,
replaces no handler, sets no signal, logs nothing, and is not wired or live.

Standard library only: no Celery or Django import, no app boot, no broker,
DB, Redis, filesystem or environment access.  Task/env data is never read,
so the only identity in the output is the caller-supplied release id (an
exact 40- or 64-char lowercase/uppercase hex commit SHA, or ``None``) and the
calling PID.

Intended use (only once a startup hook is separately approved, from the
worker MainProcess, after handler installation)::

    from car_ads_dashboard.term_handler_diagnostic import inspect_sigterm_handler
    report = inspect_sigterm_handler(release=COMMIT_SHA)   # caller-owned

The reading is valid only for the PID that produced it; a later handler
replacement can make it stale, so the caller must record PID and release
together and never reuse an older report as current proof.

Expected shape is Celery 5.5.3 ``celery/apps/worker.py``: the installed
handler is the closure ``_handle_request`` (module ``celery.apps.worker``)
renamed to ``worker_Warm`` / ``worker_Cold``, over free variables
``worker, sig, how, callback, exitcode, verbose``.  ``Warm`` has
``callback is None``, ``Cold`` has ``celery.apps.worker.on_cold_shutdown``;
captured ``sig`` must be exactly ``SIGTERM`` (a ``SIGQUIT``-shaped handler is
the same closure and must not be read as warm/cold TERM); exit codes are
``EX_OK`` (0) and ``EX_FAILURE`` (1).  Anything not matching that shape is
reported as ``Other``/``Unknown``.

WHAT THIS IS NOT.  The shape check is a heuristic structural comparison of
Python objects (module string, code name, free-variable names, captured
enum values).  It is NOT cryptographic code identity: it does not hash or
verify bytecode, and equal-looking shapes prove nothing about who installed
the handler.  It also assumes a trusted, uncorrupted process: an attacker who
can already rewrite ``__code__``/cells or monkeypatch ``signal.getsignal``
in the same interpreter can forge a matching shape.  Treat the report as an
operator consistency signal, never as tamper evidence or a security control.
"""

import os
import signal
import types

# Closed output vocabulary.  Only these exact strings are ever emitted.
_SHUTDOWNS = ("Warm", "Cold")
_EXPECTED_MODULE = "celery.apps.worker"
_EXPECTED_CODE_NAME = "_handle_request"
_EXPECTED_SIG = "SIGTERM"
_EXPECTED_FREEVARS = frozenset(
    ("worker", "sig", "how", "callback", "exitcode", "verbose")
)
_EXPECTED_HANDLER_NAMES = {"Warm": "worker_Warm", "Cold": "worker_Cold"}
_COLD_CALLBACK = "on_cold_shutdown"

_CO_VARARGS = 0x04
_RELEASE_HEX = frozenset("0123456789abcdefABCDEF")
_RELEASE_LENGTHS = (40, 64)


def _exact_str(value):
    """Return value only if it is exactly ``str`` (never a subclass)."""
    return value if type(value) is str else None


def _release_state(release):
    """Validate the release id; anything invalid is dropped, never echoed.

    Only an exact ``str`` of length 40 or 64 made solely of hex digits is
    accepted (a commit SHA).  This keeps the field a machine identifier rather
    than free text, so no arbitrary allowlisted text can carry secrets out.
    """
    if type(release) is not str:
        return None, False
    if len(release) not in _RELEASE_LENGTHS:
        return None, False
    for char in release:
        if char not in _RELEASE_HEX:
            return None, False
    return release, True


def _function_parts(func):
    """Return ``(code, closure)`` for an exact Python function, else None.

    The strict type test runs first, so no attribute of a foreign object
    (custom property, ``__getattr__``, ``__repr__``, ``__eq__``) is touched.
    """
    if type(func) is not types.FunctionType:
        return None
    try:
        code = func.__code__
        closure = func.__closure__
    except (AttributeError, TypeError):
        return None
    if type(code) is not types.CodeType:
        return None
    return code, closure


def _cell_values(code, closure):
    """Map free-variable name -> cell contents without calling anything."""
    if closure is None:
        return {} if not code.co_freevars else None
    if type(closure) is not tuple:
        return None
    if len(closure) != len(code.co_freevars):
        return None
    values = {}
    for name, cell in zip(code.co_freevars, closure):
        if type(cell) is not types.CellType:
            return None
        try:
            values[name] = cell.cell_contents
        except ValueError:
            return None
    return values


def _classify_exitcode(value):
    if type(value) is not int:
        return "Other"
    if value == 0:
        return "OK"
    if value == 1:
        return "FAILURE"
    return "Other"


def _classify_callback(callback):
    """Return ``(state, shape_ok)``; never calls or inspects foreign objects."""
    if callback is None:
        return "None", True
    parts = _function_parts(callback)
    if parts is None:
        return "Other", False
    code = parts[0]
    module = _exact_str(getattr(callback, "__module__", None))
    name = _exact_str(getattr(callback, "__name__", None))
    if (
        module == _EXPECTED_MODULE
        and name == _COLD_CALLBACK
        and code.co_name == _COLD_CALLBACK
        and not code.co_freevars
    ):
        return _COLD_CALLBACK, True
    return "Other", False


def _classify_handler(handler):
    """Classify the installed SIGTERM handler against the pinned Celery shape."""
    result = {
        "handler": "Other",
        "module_ok": False,
        "code_name_ok": False,
        "freevars_ok": False,
        "sig_ok": False,
        "how": "Other",
        "callback": "Other",
        "callback_ok": False,
        "exitcode": "Other",
    }
    if handler is signal.SIG_DFL:
        result["handler"] = "Default"
        return result
    if handler is signal.SIG_IGN:
        result["handler"] = "Ignored"
        return result
    parts = _function_parts(handler)
    if parts is None:
        return result
    code, closure = parts
    module = _exact_str(getattr(handler, "__module__", None))
    name = _exact_str(getattr(handler, "__name__", None))
    result["module_ok"] = module == _EXPECTED_MODULE
    result["code_name_ok"] = code.co_name == _EXPECTED_CODE_NAME
    if set(code.co_freevars) != _EXPECTED_FREEVARS:
        return result
    if not code.co_flags & _CO_VARARGS:
        return result
    values = _cell_values(code, closure)
    if values is None:
        return result
    result["freevars_ok"] = True
    # The same closure serves SIGTERM, SIGQUIT and SIGINT; only a handler
    # captured for SIGTERM says anything about REMAP_SIGTERM behaviour.
    captured_sig = values["sig"]
    result["sig_ok"] = type(captured_sig) is str and captured_sig == _EXPECTED_SIG
    how = values["how"]
    choice = how if (type(how) is str and how in _SHUTDOWNS) else "Other"
    result["how"] = choice
    result["callback"], result["callback_ok"] = _classify_callback(values["callback"])
    result["exitcode"] = _classify_exitcode(values["exitcode"])
    if (
        result["module_ok"]
        and result["code_name_ok"]
        and result["sig_ok"]
        and choice != "Other"
        and name == _EXPECTED_HANDLER_NAMES[choice]
    ):
        result["handler"] = choice
    return result


def _verdict(result):
    """Warm/Cold only when every checked element agrees with the pinned shape."""
    if result["handler"] == "Other" or not (
        result["module_ok"]
        and result["code_name_ok"]
        and result["freevars_ok"]
        and result["sig_ok"]
    ):
        return "Unknown"
    if (
        result["handler"] == "Warm"
        and result["how"] == "Warm"
        and result["callback"] == "None"
        and result["exitcode"] == "OK"
    ):
        return "Warm"
    if (
        result["handler"] == "Cold"
        and result["how"] == "Cold"
        and result["callback"] == _COLD_CALLBACK
        and result["callback_ok"]
        and result["exitcode"] == "FAILURE"
    ):
        return "Cold"
    return "Unknown"


def inspect_sigterm_handler(release=None):
    """Return a fixed-key report describing the current SIGTERM handler.

    Reads ``signal.getsignal(signal.SIGTERM)`` in-process at call time and
    ``os.getpid()``; both reads are the only side effects (none).  Never
    replaces the handler, never sets a signal, never logs.
    """
    pid = os.getpid()
    if type(pid) is not int:
        pid = -1
    release_value, release_valid = _release_state(release)
    try:
        handler = signal.getsignal(signal.SIGTERM)
    except (ValueError, OSError):
        classified = {
            "handler": "Unavailable",
            "module_ok": False,
            "code_name_ok": False,
            "freevars_ok": False,
            "sig_ok": False,
            "how": "Other",
            "callback": "Other",
            "callback_ok": False,
            "exitcode": "Other",
        }
    else:
        classified = _classify_handler(handler)
    return {
        "pid": pid,
        "release": release_value,
        "release_valid": release_valid,
        "handler": classified["handler"],
        "module_ok": classified["module_ok"],
        "code_name_ok": classified["code_name_ok"],
        "freevars_ok": classified["freevars_ok"],
        "sig_ok": classified["sig_ok"],
        "how": classified["how"],
        "callback": classified["callback"],
        "callback_ok": classified["callback_ok"],
        "exitcode": classified["exitcode"],
        "verdict": _verdict(classified),
    }
