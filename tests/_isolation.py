"""Tests keep their records out of the person's real Haejo folder.

Importing this once sends every in-process access receipt, task record and
preference read to a folder that is removed when the test process exits. A
test that patches these functions itself still gets its own folder.
"""
import atexit
import shutil
import tempfile
from pathlib import Path

from haejo import access_log, preferences

ROOT = Path(tempfile.mkdtemp(prefix='haejo-tests-'))
atexit.register(shutil.rmtree, ROOT, True)


def _product_directory():
    return ROOT/'Haejo'


def _log_directory():
    return ROOT/'Haejo/Logs'


preferences.product_directory = _product_directory
access_log.log_directory = _log_directory
