"""Tests for opensdmx.base — provider management."""

from __future__ import annotations

from opensdmx.base import (
    PROVIDERS,
    get_extra_headers,
    get_provider,
    provider_label,
    set_extra_headers,
    set_provider,
)


def test_set_provider_preset():
    set_provider("eurostat")
    assert get_provider()["base_url"] == PROVIDERS["eurostat"]["base_url"]


def test_set_provider_custom_url_no_agency():
    """Custom URL should work without agency_id (no longer raises)."""
    set_provider("https://custom.sdmx.org/rest")
    p = get_provider()
    assert p["base_url"] == "https://custom.sdmx.org/rest"
    assert p["agency_id"] == ""


def test_set_provider_custom_url_with_agency():
    set_provider("https://custom.sdmx.org/rest", agency_id="XYZ")
    p = get_provider()
    assert p["agency_id"] == "XYZ"


def test_set_provider_custom_url_carries_portals_flags():
    """Every portals.json flag can be set for a custom URL, not just four fields."""
    set_provider(
        "https://custom.sdmx.org/rest",
        agency_id="XYZ",
        constraints_supported=False,
        user_agent="MyApp/1.0",
        unsupported_params=["lastNObservations"],
        base_url="https://evil.example",
    )
    p = get_provider()
    assert p["constraints_supported"] is False
    assert p["user_agent"] == "MyApp/1.0"
    assert p["unsupported_params"] == ["lastNObservations"]
    assert p["agency_id"] == "XYZ"
    assert p["base_url"] == "https://custom.sdmx.org/rest"  # the named args beat **kwargs
    assert p["data_key_format"] == "dots"  # still defaults when not passed


def test_set_provider_preset_ignores_extra_flags():
    set_provider("eurostat", constraints_supported=False)
    assert get_provider()["constraints_supported"] is True


def test_set_provider_warns_on_preset_extra_flags(caplog):
    """A preset drops extra fields, and says so instead of staying silent."""
    with caplog.at_level("WARNING", logger="opensdmx.base"):
        set_provider("eurostat", constraints_supported=False)
    assert get_provider()["constraints_supported"] is True
    assert "constraints_supported" in caplog.text


def test_set_provider_warns_on_unknown_field(caplog):
    """A typo is still stored (compatibility), but the user is told."""
    with caplog.at_level("WARNING", logger="opensdmx.base"):
        set_provider("https://custom.sdmx.org/rest", constraint_supported=False)
    assert get_provider()["constraint_supported"] is False
    assert "constraint_supported" in caplog.text


def test_set_provider_known_field_does_not_warn(caplog):
    """Fields used by portals.json are accepted without a warning."""
    with caplog.at_level("WARNING", logger="opensdmx.base"):
        set_provider(
            "https://custom.sdmx.org/rest",
            constraints_supported=False,
            user_agent="MyApp/1.0",
        )
    assert "user_agent" not in caplog.text
    assert "constraints_supported" not in caplog.text


def test_set_provider_constraint_tuning_does_not_warn(caplog):
    """The client reads these two fields, though no bundled portal sets them."""
    with caplog.at_level("WARNING", logger="opensdmx.base"):
        set_provider(
            "https://custom.sdmx.org/rest",
            constraint_timeout=30,
            constraint_max_retries=1,
        )
    assert get_provider()["constraint_timeout"] == 30
    assert "constraint_timeout" not in caplog.text
    assert "constraint_max_retries" not in caplog.text


def test_provider_label_uses_name_or_base_url():
    """Messages name a custom provider by its URL, not by an empty string."""
    set_provider("eurostat")
    assert provider_label(get_provider()) == "Eurostat"
    set_provider("https://custom.sdmx.org/rest/")
    assert provider_label(get_provider()) == "https://custom.sdmx.org/rest"


def test_set_provider_unknown_name_not_url():
    """Unknown non-URL string is treated as custom URL (no agency)."""
    set_provider("not_a_real_provider")
    p = get_provider()
    assert p["base_url"] == "not_a_real_provider"


def test_set_provider_restores():
    """Restore default after custom provider tests."""
    set_provider("eurostat")
    assert get_provider()["agency_id"] == "ESTAT"


# ── extra headers ────────────────────────────────────────────────────

def test_get_extra_headers_default_empty():
    set_extra_headers({})
    assert get_extra_headers() == {}


def test_set_and_get_extra_headers_roundtrip():
    set_extra_headers({"X-Api-Key": "abc123"})
    assert get_extra_headers() == {"X-Api-Key": "abc123"}
    set_extra_headers({})  # cleanup
