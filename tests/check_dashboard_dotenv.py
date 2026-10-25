#!/usr/bin/env python3
"""Stdlib-only regression check for the DASHBOARD_DOTENV_PATH selector.

AST-extracts ONLY the import nodes and the selector top-block that sits
before BASE_DIR in car_ads_dashboard/car_ads_dashboard/settings.py, then
executes those nodes against a MOCKED dotenv module. No Django import, no
settings boot, no database/Redis/network access, no repository .env read.

Run: python3 tests/check_dashboard_dotenv.py
Exit 0 only if every case passes.
"""
import ast
import builtins
import os
import sys
import tempfile
import traceback
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(ROOT, "car_ads_dashboard", "car_ads_dashboard", "settings.py")
TMP_ROOT = "/tmp/opencode"

# Only these imports are expected before BASE_DIR; anything else fails closed.
ALLOWED_IMPORTS = {
    ("pathlib", ("Path",)),
    ("os", None),
    ("dotenv", ("load_dotenv",)),
}


def _import_allowed(node):
    if isinstance(node, ast.Import):
        return all((a.name, None) in ALLOWED_IMPORTS for a in node.names)
    names = tuple(a.name for a in node.names)
    return (node.module, names) in ALLOWED_IMPORTS


def extract_selector_nodes(source):
    """Return (import_nodes, selector_nodes) from the region before BASE_DIR."""
    tree = ast.parse(source, filename=SETTINGS)
    imports, selector, found_base_dir = [], [], False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "BASE_DIR" for t in node.targets
        ):
            found_base_dir = True
            break
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if not _import_allowed(node):
                raise AssertionError(
                    "unexpected import before BASE_DIR: %s" % ast.dump(node)
                )
            imports.append(node)
        else:
            selector.append(node)

    if not found_base_dir:
        raise AssertionError("BASE_DIR assignment not found in settings.py")
    if not imports or not selector:
        raise AssertionError("selector block or imports missing before BASE_DIR")

    block = "\n".join(ast.get_source_segment(source, n) or "" for n in selector)
    if "DASHBOARD_DOTENV_PATH" not in block:
        raise AssertionError("selector block does not mention DASHBOARD_DOTENV_PATH")
    if "load_dotenv" not in block:
        raise AssertionError("selector block does not call load_dotenv")
    return imports, selector


with open(SETTINGS, encoding="utf-8") as _fh:
    _SETTINGS_SOURCE = _fh.read()
_imports, _selector = extract_selector_nodes(_SETTINGS_SOURCE)
_CODE = compile(
    ast.Module(body=_imports + _selector, type_ignores=[]), SETTINGS, "exec"
)


def run_selector(env=None, load_dotenv=None, open_guard=None):
    """Execute the extracted selector block with a fake dotenv module."""
    env = dict(env or {})
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = load_dotenv or mock.Mock(return_value=True)
    namespace = {}
    with mock.patch.dict(sys.modules, {"dotenv": fake_dotenv}), \
            mock.patch.dict(os.environ, env, clear=False):
        # Isolate the selector even if the parent process has it exported.
        os.environ.pop("DASHBOARD_DOTENV_PATH", None)
        os.environ.update(env)
        if open_guard is None:
            exec(_CODE, namespace)
        else:
            with mock.patch("builtins.open", open_guard):
                exec(_CODE, namespace)
    return namespace


class DotenvSelectorTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(TMP_ROOT, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=TMP_ROOT)
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name="selector.env", text="SECRET_KEY=from-test-file\n"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_unset_preserves_exact_fallback_call(self):
        loader = mock.Mock(return_value=True)
        run_selector(load_dotenv=loader)
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(loader.call_args, mock.call(override=True))

    def test_explicit_valid_file_loads_only_that_path_with_override(self):
        path = self.write()
        loader = mock.Mock(return_value=True)
        run_selector({"DASHBOARD_DOTENV_PATH": path}, loader)
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(loader.call_args, mock.call(path, override=True))

    def test_empty_selector_is_rejected(self):
        loader = mock.Mock(return_value=True)
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": ""}, loader)
        loader.assert_not_called()
        self.assertIn("DASHBOARD_DOTENV_PATH", str(ctx.exception))

    def test_relative_selector_is_rejected(self):
        loader = mock.Mock(return_value=True)
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": "relative.env"}, loader)
        loader.assert_not_called()
        self.assertIn("absolute", str(ctx.exception))

    def test_missing_file_is_rejected_without_fallback(self):
        path = os.path.join(self.tmp, "does-not-exist.env")
        loader = mock.Mock(return_value=True)
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": path}, loader)
        loader.assert_not_called()
        self.assertIn("existing regular file", str(ctx.exception))

    def test_directory_is_rejected(self):
        loader = mock.Mock(return_value=True)
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": self.tmp}, loader)
        loader.assert_not_called()
        self.assertIn("existing regular file", str(ctx.exception))

    def test_symlink_is_rejected(self):
        target = self.write()
        link = os.path.join(self.tmp, "selector-link.env")
        os.symlink(target, link)
        loader = mock.Mock(return_value=True)
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": link}, loader)
        loader.assert_not_called()
        self.assertIn("symlink", str(ctx.exception))

    def test_unreadable_read_oserror_is_sanitized(self):
        path = self.write("unreadable.env", "SECRET_KEY=LEAKED_FILE_CONTENT\n")
        real_open = builtins.open
        calls = []

        def guarded(file, *args, **kwargs):
            if os.fspath(file) == path:
                raise PermissionError("LEAKED_OS_ERROR_DETAIL")
            return real_open(file, *args, **kwargs)

        def loader(dotenv_path=None, **kwargs):
            # Emulate python-dotenv's single real read of the explicit path.
            calls.append((dotenv_path, kwargs))
            with builtins.open(dotenv_path, encoding="utf-8"):
                return True

        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": path}, loader,
                         open_guard=guarded)
        self.assertEqual(calls, [(path, {"override": True})])   # no fallback retry
        message = str(ctx.exception)
        self.assertNotIn("LEAKED_OS_ERROR_DETAIL", message)
        self.assertNotIn("LEAKED_FILE_CONTENT", message)
        self.assertIn("could not be loaded", message)

    def test_empty_dotenv_returning_false_is_refused(self):
        path = self.write("empty.env", "")
        loader = mock.Mock(return_value=False)
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": path}, loader)
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(loader.call_args, mock.call(path, override=True))
        self.assertIn("no environment bindings", str(ctx.exception))

    def test_load_exception_is_sanitized_and_not_retried(self):
        path = self.write("explode.env", "SECRET_KEY=LEAKED_FILE_CONTENT\n")
        loader = mock.Mock(side_effect=OSError("LEAKED_OS_ERROR_DETAIL"))
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": path}, loader)
        self.assertEqual(loader.call_count, 1)
        message = str(ctx.exception)
        self.assertNotIn("LEAKED_OS_ERROR_DETAIL", message)
        self.assertNotIn("LEAKED_FILE_CONTENT", message)
        self.assertIn("could not be loaded", message)

    def test_unicode_decode_error_is_sanitized_with_suppressed_context(self):
        path = self.write("invalid-utf8.env", "SECRET_KEY=LEAKED_FILE_CONTENT\n")
        raw = b"SECRET_KEY=LEAKED_DOTENV_BYTES_\xff\xfe_TAIL"
        # Reason carries decoded bytes, as a real decoder error can.
        error = UnicodeDecodeError("utf-8", raw, 24, 26,
                                   raw.decode("latin-1"))
        loader = mock.Mock(side_effect=error)
        with self.assertRaises(ValueError) as ctx:
            run_selector({"DASHBOARD_DOTENV_PATH": path}, loader)

        exc = ctx.exception
        self.assertEqual(loader.call_count, 1)             # no fallback retry
        self.assertEqual(loader.call_args, mock.call(path, override=True))
        self.assertIs(type(exc), ValueError)
        self.assertIn("could not be loaded", str(exc))
        self.assertNotIn("LEAKED_DOTENV_BYTES", str(exc))
        self.assertNotIn("LEAKED_FILE_CONTENT", str(exc))
        self.assertNotIn(str(path), str(exc))
        self.assertTrue(exc.__suppress_context__)          # raise ... from None
        self.assertIsNone(exc.__cause__)
        # The original decode error survives only as hidden __context__, which
        # the interpreter suppresses; it must never be rendered to a user.
        self.assertIs(exc.__context__, error)
        self.assertNotIn("LEAKED_DOTENV_BYTES",
                         "".join(traceback.format_exception(exc)))

    def test_unicode_error_sentinel_bytes_absent_from_rendered_traceback(self):
        path = self.write("invalid-utf8-tb.env", "SECRET_KEY=LEAKED_FILE_CONTENT\n")
        error = UnicodeDecodeError("utf-8", b"DB_PASSWORD=LEAKED_DOTENV_BYTES_\xff",
                                   22, 23, "LEAKED_DOTENV_BYTES")
        loader = mock.Mock(side_effect=error)
        try:
            run_selector({"DASHBOARD_DOTENV_PATH": path}, loader)
        except ValueError:
            rendered = traceback.format_exc()
        else:
            self.fail("expected ValueError")
        self.assertIn("DASHBOARD_DOTENV_PATH file could not be loaded", rendered)
        self.assertNotIn("LEAKED_DOTENV_BYTES", rendered)
        self.assertNotIn("LEAKED_FILE_CONTENT", rendered)
        self.assertNotIn("UnicodeDecodeError", rendered)
        self.assertEqual(loader.call_count, 1)             # no fallback retry


def main():
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DotenvSelectorTest)
    )
    total = result.testsRun
    if result.wasSuccessful():
        print("RESULT dotenv-selector: %d/%d PASS" % (total, total))
        return 0
    print("RESULT dotenv-selector: FAIL (run=%d failures=%d errors=%d)"
          % (total, len(result.failures), len(result.errors)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
