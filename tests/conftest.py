"""Pin the user-level portals file so a developer's own config cannot change the suite.

`opensdmx` reads `$OPENSDMX_PORTALS` (or `$XDG_CONFIG_HOME/opensdmx/portals.json`) at
import time, and pytest imports the package at collection: a per-test monkeypatch comes
too late. `tests/test_user_portals.py` sets the variable itself, per test.
"""

import os
import tempfile

os.environ.pop("OPENSDMX_PORTALS", None)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="opensdmx-tests-config-")

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
