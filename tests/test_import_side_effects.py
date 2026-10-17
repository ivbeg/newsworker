import subprocess
import sys

PROBE = """
import logging, warnings
import requests, urllib3  # noqa: F401  (they install their own default filters)
before = list(warnings.filters)
import newsworker.core, newsworker.extractor, newsworker.service  # noqa: F401
assert logging.getLogger().handlers == [], logging.getLogger().handlers
assert warnings.filters == before, "importing newsworker changed warning filters"
print("ok")
"""


def test_importing_the_library_leaves_logging_and_warnings_alone():
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
