"""CLI startup must not issue requests ahead of the command."""

import sys

import httpx
import pytest
from typer.testing import CliRunner

from opensdmx import base, cli


@pytest.fixture
def requests_seen(tmp_path, monkeypatch):
    requests: list[httpx.Request] = []
    client = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"TIME_PERIOD,OBS_VALUE\n2020,1\n")

    monkeypatch.setenv("OPENSDMX_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENSDMX_USER_AGENT", "opensdmx-test")
    monkeypatch.setattr(base, "_active_provider", "eurostat")
    monkeypatch.setattr(base, "_extra_headers", {})
    monkeypatch.setattr(sys, "argv", ["opensdmx"])
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs)
    )
    return requests


def test_invalid_header_does_not_make_any_request(requests_seen):
    result = CliRunner().invoke(cli.app, ["get", "X", "--header", "missing-colon"])

    assert result.exit_code != 0
    assert "Invalid header" in result.stderr
    assert requests_seen == []


def test_get_rejects_unsupported_output_before_loading_dataset(requests_seen, monkeypatch):
    loaded = []

    def load_dataset(dataset_id):
        loaded.append(dataset_id)
        return {"df_id": dataset_id, "filters": {}}

    monkeypatch.setattr("opensdmx.load_dataset", load_dataset)
    result = CliRunner().invoke(cli.app, ["get", "X", "--out", "data.xlsx"])

    assert result.exit_code == 1, result.output
    assert "unsupported output format '.xlsx'" in result.stderr
    assert requests_seen == []
    assert loaded == []


def test_first_request_uses_selected_provider_and_headers(requests_seen, monkeypatch):
    monkeypatch.setattr("opensdmx.load_dataset", lambda _: {"df_id": "X", "filters": {}})
    result = CliRunner().invoke(
        cli.app,
        ["get", "X", "--provider", "https://selected.example/rest", "--yes", "--header", "X-Test: value"],
    )

    assert result.exit_code == 0, result.output
    assert [str(req.url) for req in requests_seen] == ["https://selected.example/rest/data/X"]
    assert requests_seen[0].headers["X-Test"] == "value"
    assert requests_seen[0].headers["User-Agent"] == "opensdmx-test"
