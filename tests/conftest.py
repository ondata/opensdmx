"""Pin the user-level portals file so a developer's own config cannot change the suite.

`opensdmx` reads `$OPENSDMX_PORTALS` (or `$XDG_CONFIG_HOME/opensdmx/portals.json`) at
import time, and pytest imports the package at collection: a per-test monkeypatch comes
too late. `tests/test_user_portals.py` sets the variable itself, per test.
"""

import os
import tempfile

os.environ.pop("OPENSDMX_PORTALS", None)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="opensdmx-tests-config-")
