"""Test package.

Runs BEFORE any test module imports ``app``: points the app at a throw-away
instance folder so tests never touch (or pollute) the real databases.
"""
import atexit
import os
import shutil
import tempfile

_TEST_INSTANCE = tempfile.mkdtemp(prefix="smartfit-test-")
os.environ["SMARTFIT_INSTANCE_DIR"] = _TEST_INSTANCE
atexit.register(shutil.rmtree, _TEST_INSTANCE, ignore_errors=True)
