#!/usr/bin/env python3
"""OFFLINE validator for ops/worker-alignment/settings-legacy-dotenv.patch.

Stdlib only, no runtime apply: no Django import/settings boot, no DB/Redis/
network/service, no real .env read, no repo mutation. Reads the fixed legacy
baseline from git in-process, proves the candidate is the single-path "replace
top-level load_dotenv(override=True) with the approved selector" edit, git
applies it in a throwaway /tmp/opencode dir, then re-runs the existing dotenv
self-check against the PATCHED legacy text (mocked dotenv).

Run: python3 tests/check_worker_rollout.py   Exit 0 only if every check passes.
"""
import ast, hashlib, importlib.util, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP, OBJ = "/tmp/opencode", "e6da99a3f83773b15d875410f26c17164426fa0b"
BASE_SHA = "03203b820c8261ec9fe9ba54a3ee0deeb09898446cc6eaee067147469552625c"
REL = "car_ads_dashboard/car_ads_dashboard/settings.py"
PATCH = os.path.join(ROOT, "ops", "worker-alignment", "settings-legacy-dotenv.patch")
CURRENT = os.path.join(ROOT, *REL.split("/"))
NEEDLE = b"\nload_dotenv(override=True)\n"          # exact-one baseline hit
START = b"# Optional fail-closed dotenv selector."
END = b'raise ValueError("DASHBOARD_DOTENV_PATH file could not be loaded") from None'

class Reject(Exception):
    """Contract violation: the candidate must not be accepted."""

def git(*args):
    out = subprocess.run(["git", "-C", ROOT] + list(args),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if out.returncode:
        raise Reject("git %s failed" % args[0])
    return out.stdout

def blob_id(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

def baseline_bytes():
    """Fixed legacy baseline; read from git in-process, never stored in the artifact."""
    data = git("show", "%s:%s" % (OBJ, REL))
    if hashlib.sha256(data).hexdigest() != BASE_SHA:
        raise Reject("baseline blob sha256 does not match the fixed contract")
    return data

def approved_block(current):
    """Marker-bounded selector bytes, cross-checked against the pre-BASE_DIR AST."""
    lines = current.split(b"\n")
    starts = [i for i, ln in enumerate(lines) if ln.strip().startswith(START)]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == END]
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise Reject("approved selector start/end markers are not unique")
    lo, hi = starts[0], ends[0]
    block = b"\n".join(lines[lo:hi + 1]) + b"\n"
    nodes, seen = [], False
    for node in ast.parse(current.decode("utf-8")).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "BASE_DIR" for t in node.targets):
            seen = True
            break
        if not isinstance(node, (ast.Import, ast.ImportFrom)) and not (
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
            nodes.append(node)                      # docstring/imports excluded
    if not seen or not nodes:
        raise Reject("BASE_DIR or selector nodes missing before BASE_DIR")
    for node in nodes:
        if not (lo + 1 <= node.lineno and (node.end_lineno or node.lineno) <= hi + 1):
            raise Reject("selector AST node lies outside the marker region")
    if b"DASHBOARD_DOTENV_PATH" not in block or b"load_dotenv" not in block:
        raise Reject("selector block does not implement the selector")
    return block

def parse_patch(text):
    """Exactly one path, and it must be the exact allowed baseline path."""
    paths, pre, post = set(), [], []
    for line in text.splitlines():
        if line[:4] in ("--- ", "+++ ") and line[4:].strip() != "/dev/null":
            path = line[4:].strip()
            paths.add(path[2:] if path[:2] in ("a/", "b/") else path)
        elif line.startswith("index "):
            ref = line[6:].split()[0]
            if ".." not in ref:
                raise Reject("malformed index line")
            old, new = ref.split("..")
            pre.append(old)
            post.append(new)
    if paths - {REL} or ".." in REL:
        raise Reject("patch path is not the allowed baseline path: %r" % sorted(paths))
    if len(paths) != 1 or len(pre) != 1 or len(post) != 1:
        raise Reject("patch must touch one path with one index line")
    return paths.pop(), pre[0], post[0]

def apply_offline(baseline, text):
    """git apply --check then apply, inside a throwaway copy of the baseline only."""
    tmp = tempfile.mkdtemp(dir=TMP)
    try:
        target = os.path.join(tmp, *REL.split("/"))
        os.makedirs(os.path.dirname(target))
        pf = os.path.join(tmp, "candidate.patch")
        with open(target, "wb") as fh:
            fh.write(baseline)
        with open(pf, "wb") as fh:
            fh.write(text.encode("utf-8"))
        for extra in (["--check"], []):
            proc = subprocess.run(["git", "apply"] + extra + [pf], cwd=tmp,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode:
                raise Reject("git apply %s rejected" % ("--check" if extra else ""))
        with open(target, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def validate(current, baseline, text):
    """Identity, allowed path, exact-one replace, zero drift outside the selector."""
    path, pre, post = parse_patch(text)
    if not blob_id(baseline).startswith(pre):
        raise Reject("patch preimage index does not match the baseline blob")
    if baseline.count(NEEDLE) != 1:
        raise Reject("baseline must hold exactly one bare load_dotenv(override=True)")
    block = approved_block(current)
    expected = baseline.replace(NEEDLE, b"\n" + block, 1)
    if not blob_id(expected).startswith(post):
        raise Reject("patch postimage index does not match the expected bytes")
    applied = apply_offline(baseline, text)          # real git apply, tmp only
    if applied != expected:
        raise Reject("applied text differs from baseline+approved selector")
    head, _, tail = baseline.partition(NEEDLE)
    if not applied.startswith(head + b"\n" + block) or not applied.endswith(tail):
        raise Reject("bytes changed outside the selector region")
    ast.parse(applied.decode("utf-8"))
    if NEEDLE in applied:
        raise Reject("bare fallback call still present at the load site")
    return path, expected

def expect_reject(fn, *args):
    try:
        fn(*args)
    except Reject:
        return True
    raise AssertionError("negative control was NOT rejected: %s" % fn.__name__)

def run_dotenv_suite(patched):
    """Re-run the existing selector self-check against the PATCHED legacy text."""
    spec = importlib.util.spec_from_file_location(
        "check_dashboard_dotenv", os.path.join(ROOT, "tests", "check_dashboard_dotenv.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)     # no main(); reads only approved local source
    imports, selector = module.extract_selector_nodes(patched.decode("utf-8"))
    module._CODE = compile(ast.Module(body=imports + selector, type_ignores=[]), REL, "exec")
    case = module.DotenvSelectorTest
    want = len([n for n in dir(case) if n.startswith("test_")])
    result = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(case))
    if not result.wasSuccessful() or result.testsRun != want:
        raise AssertionError("patched-legacy dotenv suite failed: run=%d want=%d "
                             "failures=%d errors=%d"
                             % (result.testsRun, want, len(result.failures),
                                len(result.errors)))
    return result.testsRun

def main():
    os.makedirs(TMP, exist_ok=True)
    with open(CURRENT, "rb") as fh:
        current = fh.read()
    baseline = baseline_bytes()
    with open(PATCH, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    path, expected = validate(current, baseline, text)
    for line in ("baseline_git         %s:%s" % (OBJ[:12], REL),
                 "baseline_sha256      %s" % BASE_SHA,
                 "approved_current_sha %s" % hashlib.sha256(current).hexdigest(),
                 "patch_file_sha256    %s" % hashlib.sha256(raw).hexdigest(),
                 "patched_sha256       %s" % hashlib.sha256(expected).hexdigest(),
                 "patch_path           %s" % path):
        print(line)
    # Negative controls: real rejections, not hash self-comparison.
    tampered = baseline.replace(b"DEBUG", b"DEBU6")
    drifted = baseline.replace(b"from dotenv import load_dotenv",
                               b"from dotenv import load_dotenv_renamed")
    second = text.replace("--- a/" + REL, "--- a/README.md").replace(
        "+++ b/" + REL, "+++ b/README.md")
    for fn, *args in [
        (validate, current, tampered, text),                  # drifted preimage
        (apply_offline, drifted, text),                       # git apply refuses
        (parse_patch, second),                                # extra path
        (validate, current, baseline, text.replace("index 2e45a1b", "index 0000000")),
        (validate, current, baseline.replace(NEEDLE, b"\n"), text),    # no hit
        (approved_block, current.replace(START, b"# not a selector")),
    ]:
        expect_reject(fn, *args)
    print("negative_controls    6/6 rejected")
    tests = run_dotenv_suite(expected)
    print("dotenv_cases_patched %d/%d PASS" % (tests, tests))
    print("RESULT worker-rollout: PASS (patch offline-applies to fixed baseline only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
