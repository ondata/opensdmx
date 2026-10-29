"""Tests for the user-level portals.json override ($OPENSDMX_PORTALS)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from opensdmx.base import _load_portals, _user_portals_file

BUNDLED: dict = json.loads((Path(__file__).parent.parent / "src/opensdmx/portals.json").read_text())


def _write_portals(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))

    return path


def test_missing_user_file_keeps_the_bundled_providers(monkeypatch, tmp_path, caplog):
    """A path that does not exist is reported, not silently ignored."""
    missing = tmp_path / "absent.json"
    monkeypatch.setenv("OPENSDMX_PORTALS", str(missing))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals == BUNDLED
    assert any("does not exist" in record.message for record in caplog.records)


def test_user_file_adds_a_provider(monkeypatch, tmp_path):
    path = _write_portals(
        tmp_path / "portals.json",
        {
            "mysdmx": {
                "name": "My SDMX",
                "base_url": "https://sdmx.example.org/rest",
                "agency_id": "XYZ",
                "rate_limit": 2.0,
                "constraints_supported": False,
            }
        },
    )
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    portals = _load_portals()

    assert portals["mysdmx"]["base_url"] == "https://sdmx.example.org/rest"
    assert portals["mysdmx"]["agency_id"] == "XYZ"
    assert portals["mysdmx"]["constraints_supported"] is False
    # The bundled providers are still there, untouched.
    assert portals["eurostat"] == BUNDLED["eurostat"]


def test_user_file_overrides_single_fields_of_a_bundled_provider(monkeypatch, tmp_path):
    """Overriding rate_limit must not drop the bundled base_url, name or aliases."""
    path = _write_portals(tmp_path / "portals.json", {"eurostat": {"rate_limit": 9.0}})
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    eurostat = _load_portals()["eurostat"]

    assert eurostat["rate_limit"] == 9.0
    assert eurostat["base_url"] == BUNDLED["eurostat"]["base_url"]
    assert eurostat["name"] == BUNDLED["eurostat"]["name"]
    assert eurostat["aliases"] == BUNDLED["eurostat"]["aliases"]


def test_broken_user_file_falls_back_to_the_bundled_providers(monkeypatch, tmp_path, caplog):
    path = tmp_path / "portals.json"
    path.write_text("{ this is not json")
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals == BUNDLED
    assert any(str(path) in record.message for record in caplog.records)


def test_user_file_must_hold_an_object(monkeypatch, tmp_path, caplog):
    path = _write_portals(tmp_path / "portals.json", ["not", "an", "object"])
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals == BUNDLED
    assert any("expected an object" in record.message for record in caplog.records)


def test_non_object_provider_entry_is_skipped(monkeypatch, tmp_path, caplog):
    path = _write_portals(
        tmp_path / "portals.json",
        {"broken": "not an object", "good": {"base_url": "https://good.example.org/rest"}},
    )
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert "broken" not in portals
    assert portals["good"]["base_url"] == "https://good.example.org/rest"
    assert any("'broken'" in record.message for record in caplog.records)


def test_user_portals_file_defaults_to_the_xdg_config_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENSDMX_PORTALS", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert _user_portals_file() == tmp_path / "opensdmx" / "portals.json"

    path = _write_portals(
        tmp_path / "opensdmx" / "portals.json",
        {"mysdmx": {"base_url": "https://sdmx.example.org/rest"}},
    )
    assert path.is_file()
    assert "mysdmx" in _load_portals()


def test_user_portals_file_defaults_to_dot_config(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENSDMX_PORTALS", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert _user_portals_file() == tmp_path / ".config" / "opensdmx" / "portals.json"


def test_path_exists_but_is_not_a_file(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("OPENSDMX_PORTALS", str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals == BUNDLED
    assert any("is not a file" in record.message for record in caplog.records)


def test_tilde_in_the_env_var_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENSDMX_PORTALS", "~/mine.json")
    (tmp_path / "mine.json").write_text(json.dumps({"mysdmx": {"base_url": "https://a.b/rest"}}))

    assert _user_portals_file() == tmp_path / "mine.json"
    assert "mysdmx" in _load_portals()


def test_no_home_directory_does_not_crash_the_import(monkeypatch):
    """A container UID with no passwd entry has no home: the bundled list must still load."""
    monkeypatch.delenv("OPENSDMX_PORTALS", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    def _no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(_no_home))

    assert _user_portals_file() is None
    assert _load_portals() == BUNDLED


def test_non_utf8_file_falls_back_to_the_bundled_providers(monkeypatch, tmp_path, caplog):
    path = tmp_path / "portals.json"
    path.write_bytes(b'{"mysdmx": {"name": "\xff"}}')
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals == BUNDLED
    assert any(str(path) in record.message for record in caplog.records)


def test_invalid_aliases_are_ignored(monkeypatch, tmp_path, caplog):
    """`aliases: null` used to be an import-time TypeError, `"mine"` per-character aliases."""
    path = _write_portals(
        tmp_path / "portals.json",
        {
            "nulls": {"base_url": "https://a.example.org/rest", "aliases": None},
            "str": {"base_url": "https://b.example.org/rest", "aliases": "mine"},
        },
    )
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert "aliases" not in portals["nulls"]
    assert "aliases" not in portals["str"]
    assert portals["nulls"]["base_url"] == "https://a.example.org/rest"
    assert sum("aliases must be a list" in record.message for record in caplog.records) == 2


def test_provider_without_a_base_url_is_skipped(monkeypatch, tmp_path, caplog):
    path = _write_portals(tmp_path / "portals.json", {"nope": {"agency_id": "XYZ"}})
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert "nope" not in portals
    assert any("has no base_url" in record.message for record in caplog.records)


def test_null_base_url_leaves_the_bundled_provider_alone(monkeypatch, tmp_path, caplog):
    path = _write_portals(tmp_path / "portals.json", {"eurostat": {"base_url": None}})
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals["eurostat"] == BUNDLED["eurostat"]
    assert any("has no base_url" in record.message for record in caplog.records)


def test_null_rate_limit_falls_back_to_the_bundled_value(monkeypatch, tmp_path, caplog):
    path = _write_portals(tmp_path / "portals.json", {"eurostat": {"rate_limit": None}})
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals["eurostat"]["rate_limit"] == BUNDLED["eurostat"]["rate_limit"]
    assert any("rate_limit must be a number" in record.message for record in caplog.records)


def test_alias_that_shadows_a_provider_name_warns(monkeypatch, tmp_path, caplog):
    """`--provider istat` must reach ISTAT, not an alias a user attached to eurostat."""
    path = _write_portals(tmp_path / "portals.json", {"eurostat": {"aliases": ["istat"]}})
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        _load_portals()

    assert any("is also a provider name" in record.message for record in caplog.records)


def test_provider_name_wins_over_an_alias_of_the_same_spelling(tmp_path):
    path = _write_portals(
        tmp_path / "portals.json",
        {"estat": {"base_url": "https://stat.example.org/rest", "agency_id": "ME"}},
    )
    code = (
        "from opensdmx.base import get_base_url, resolve_provider;"
        "resolve_provider('estat');"
        "print(get_base_url())"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "OPENSDMX_PORTALS": str(path)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "https://stat.example.org/rest"


def test_duplicate_alias_across_user_providers_warns(monkeypatch, tmp_path, caplog):
    path = _write_portals(
        tmp_path / "portals.json",
        {
            "a": {"base_url": "https://a.example.org/rest", "aliases": ["same"]},
            "b": {"base_url": "https://b.example.org/rest", "aliases": ["same"]},
        },
    )
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        _load_portals()

    assert any("'same' is declared by" in record.message for record in caplog.records)


def test_user_file_reaches_providers_and_aliases_at_import(tmp_path):
    """End to end in a fresh interpreter: merging, aliases and the known-field set."""
    path = _write_portals(
        tmp_path / "portals.json",
        {
            "mysdmx": {
                "name": "My SDMX",
                "aliases": ["mine"],
                "base_url": "https://sdmx.example.org/rest",
                "agency_id": "XYZ",
                "my_field": "read by nothing, but declared",
            },
            "eurostat": {"rate_limit": 9.0},
        },
    )
    env = {**os.environ, "OPENSDMX_PORTALS": str(path)}
    code = (
        "from opensdmx.base import PROVIDERS, PROVIDER_ALIASES, _KNOWN_FIELDS;"
        "print(PROVIDERS['mysdmx']['agency_id']);"
        "print(PROVIDER_ALIASES['mine']);"
        "print(PROVIDERS['eurostat']['rate_limit']);"
        "print(PROVIDERS['eurostat']['base_url']);"
        "print('my_field' in _KNOWN_FIELDS);"
        "print(PROVIDERS['eurostat']['name'])"
    )

    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )

    assert result.stdout.split("\n")[:6] == [
        "XYZ",
        "mysdmx",
        "9.0",
        BUNDLED["eurostat"]["base_url"],
        "True",
        BUNDLED["eurostat"]["name"],
    ]


def test_invalid_data_rate_limit_is_ignored(monkeypatch, tmp_path, caplog):
    """`float(provider["data_rate_limit"])` runs on the next data request, not at load."""
    path = _write_portals(tmp_path / "portals.json", {"oecd": {"data_rate_limit": "oops"}})
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals["oecd"]["data_rate_limit"] == BUNDLED["oecd"]["data_rate_limit"]
    assert any("data_rate_limit must be a number" in record.message for record in caplog.records)


def test_invalid_rate_limit_group_is_ignored(monkeypatch, tmp_path, caplog):
    """An empty or non-string group would name the rate-limit file `.log` or `5.log`."""
    path = _write_portals(
        tmp_path / "portals.json",
        {
            "istat_hvd": {"rate_limit_group": ""},
            "mine": {"base_url": "https://a.example.org/rest", "rate_limit_group": 5},
        },
    )
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        portals = _load_portals()

    assert portals["istat_hvd"]["rate_limit_group"] == BUNDLED["istat_hvd"]["rate_limit_group"]
    assert "rate_limit_group" not in portals["mine"]
    assert sum("rate_limit_group must be a non-empty string" in record.message for record in caplog.records) == 2


def test_a_provider_with_only_a_base_url_has_an_agency(monkeypatch, tmp_path):
    """A minimal user entry must not KeyError in get_agency_id() on the first request."""
    path = _write_portals(tmp_path / "portals.json", {"bare": {"base_url": "https://b.example.org/rest"}})
    code = (
        "from opensdmx.base import get_agency_id, set_provider;"
        "set_provider('bare');"
        "print(repr(get_agency_id()))"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "OPENSDMX_PORTALS": str(path)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "''"


def test_unsearchable_config_directory_falls_back(monkeypatch, tmp_path, caplog):
    """`Path.is_file()` raises on Python 3.12 when a parent directory denies search."""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "portals.json").write_text("{}")
    blocked.chmod(0)

    try:
        if os.access(blocked / "portals.json", os.R_OK):
            pytest.skip("permissions are not enforced for this user")

        monkeypatch.setenv("OPENSDMX_PORTALS", str(blocked / "portals.json"))

        with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
            portals = _load_portals()
    finally:
        blocked.chmod(0o700)

    assert portals == BUNDLED
    assert any("cannot read" in record.message for record in caplog.records)


def test_duplicate_alias_warning_names_the_winner(monkeypatch, tmp_path, caplog):
    path = _write_portals(
        tmp_path / "portals.json",
        {
            "a": {"base_url": "https://a.example.org/rest", "aliases": ["same"]},
            "b": {"base_url": "https://b.example.org/rest", "aliases": ["same"]},
        },
    )
    monkeypatch.setenv("OPENSDMX_PORTALS", str(path))

    with caplog.at_level(logging.WARNING, logger="opensdmx.base"):
        _load_portals()

    warnings = [r.message for r in caplog.records if "'same' is declared by" in r.message]

    assert len(warnings) == 1
    assert "'b' wins" in warnings[0]


def test_run_query_prefers_a_provider_name_over_an_alias(tmp_path, monkeypatch):
    """A saved query with `provider: estat` must reach a user provider keyed `estat`."""
    from unittest.mock import patch

    import yaml

    from opensdmx import base
    from opensdmx.retrieval import run_query

    providers = dict(base.PROVIDERS)
    providers["estat"] = {
        **base._DEFAULTS,
        "base_url": "https://stat.example.org/rest",
        "agency_id": "ME",
    }
    monkeypatch.setattr(base, "PROVIDERS", providers)

    query = tmp_path / "q.yaml"
    query.write_text(yaml.dump({"dataset": "TEST_DF", "filters": {}, "provider": "estat"}))

    seen: list[str] = []

    def spy_load(dataset_id):
        seen.append(base.get_provider()["base_url"])
        raise RuntimeError("stop")

    with patch("opensdmx.retrieval.load_dataset", side_effect=spy_load):
        with pytest.raises(RuntimeError):
            run_query(str(query))

    assert seen == ["https://stat.example.org/rest"]
