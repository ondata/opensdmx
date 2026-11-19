"""Pin the user-level portals file and the cache so a developer's own files cannot change the suite.

`opensdmx` reads `$OPENSDMX_PORTALS` (or `$XDG_CONFIG_HOME/opensdmx/portals.json`) at
import time, and pytest imports the package at collection: a per-test monkeypatch comes
too late. `tests/test_user_portals.py` sets the variable itself, per test.
"""

import os
import tempfile

os.environ.pop("OPENSDMX_PORTALS", None)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="opensdmx-tests-config-")
# Same for the cache: a test must not read the developer's cached catalogs or
# category trees (their content would decide the outcome), nor write into them.
os.environ["OPENSDMX_CACHE_DIR"] = tempfile.mkdtemp(prefix="opensdmx-tests-cache-")

import pytest


@pytest.fixture(autouse=True)
def _no_reachability_probe(monkeypatch):
    """Skip the CLI's live reachability GET on the provider base URL.

    `_check_api_reachable` is skipped only when a rate-limit file already
    exists, so on a fresh machine (CI) every CLI test hits the real provider
    and fails with "API unreachable" when it is down or slow. No test is
    about that probe: stub it everywhere.
    """
    monkeypatch.setattr("opensdmx.cli._check_api_reachable", lambda: None)
