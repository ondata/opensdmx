"""OAuth2 client-credentials auth declared in portals.json (`auth` field), TÜİK quirks."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from opensdmx import auth
from opensdmx.base import ExplainStop, get_provider, sdmx_request, set_explain, set_provider
from opensdmx.utils import escape_key_for_provider

_AUTH = {
    "type": "oauth2_client_credentials",
    "token_url": "https://auth.example.org/token",
    "client_id_env": "X_CLIENT_ID",
    "client_secret_env": "X_CLIENT_SECRET",
    "doc_url": "https://example.org/how-to-get-credentials",
}
_SECRET = "s3cr3t-value"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    auth.clear_tokens()
    monkeypatch.setenv("X_CLIENT_ID", "my-client")
    monkeypatch.setenv("X_CLIENT_SECRET", _SECRET)
    set_provider("https://sdmx.example.org/rest", agency_id="X", rate_limit=0.0, auth=_AUTH)
    yield
    auth.clear_tokens()
    set_explain(False)
    set_provider("eurostat")


class _TokenServer:
    """Fake token endpoint: hands out tok-1, tok-2, ... and records the form bodies."""

    def __init__(self, status: int = 200, expires_in: int = 300):
        self.calls: list[dict[str, str]] = []
        self.status = status
        self.expires_in = expires_in

    def __call__(self, url, data, timeout):
        self.calls.append(dict(data))
        request = httpx.Request("POST", url)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "invalid_client"}, request=request)
        return httpx.Response(
            200,
            json={"access_token": f"tok-{len(self.calls)}", "expires_in": self.expires_in},
            request=request,
        )


def _data_client(handler):
    """Patch the httpx.Client that sdmx_request opens with a MockTransport."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    return patch("opensdmx.base.httpx.Client", side_effect=factory)


def test_bearer_token_sent_and_cached():
    tokens = _TokenServer()
    seen: list[str | None] = []

    def handler(request):
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, content=b"ok")

    with patch("opensdmx.auth.httpx.post", side_effect=tokens), _data_client(handler):
        sdmx_request("dataflow/X")
        sdmx_request("dataflow/X")

    assert seen == ["Bearer tok-1", "Bearer tok-1"]
    assert len(tokens.calls) == 1
    assert tokens.calls[0] == {
        "grant_type": "client_credentials",
        "client_id": "my-client",
        "client_secret": _SECRET,
    }


def test_expired_token_is_renewed():
    tokens = _TokenServer(expires_in=10)  # below the 30 s margin: stale at once

    with patch("opensdmx.auth.httpx.post", side_effect=tokens), _data_client(
        lambda r: httpx.Response(200, content=b"ok")
    ):
        sdmx_request("dataflow/X")
        sdmx_request("dataflow/X")

    assert len(tokens.calls) == 2


def test_401_renews_token_once():
    tokens = _TokenServer()
    seen: list[str | None] = []

    def handler(request):
        seen.append(request.headers.get("Authorization"))
        status = 401 if request.headers.get("Authorization") == "Bearer tok-1" else 200
        return httpx.Response(status, content=b"ok")

    with patch("opensdmx.auth.httpx.post", side_effect=tokens), _data_client(handler):
        resp = sdmx_request("dataflow/X")

    assert resp.status_code == 200
    assert seen == ["Bearer tok-1", "Bearer tok-2"]


def test_persistent_401_raises_without_loop():
    tokens = _TokenServer()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, content=b"no")

    with patch("opensdmx.auth.httpx.post", side_effect=tokens), _data_client(handler):
        with pytest.raises(httpx.HTTPStatusError):
            sdmx_request("dataflow/X")

    assert len(calls) == 2  # first try + one renewal, no tenacity retries on 4xx


def test_missing_credentials_names_env_vars(monkeypatch):
    monkeypatch.delenv("X_CLIENT_SECRET")
    with _data_client(lambda r: httpx.Response(200)):
        with pytest.raises(auth.AuthError) as exc:
            sdmx_request("dataflow/X")
    msg = str(exc.value)
    assert "X_CLIENT_SECRET" in msg
    assert "X_CLIENT_ID" not in msg
    assert _AUTH["doc_url"] in msg


def test_refused_credentials_do_not_leak_secret():
    with patch("opensdmx.auth.httpx.post", side_effect=_TokenServer(status=401)), _data_client(
        lambda r: httpx.Response(200)
    ):
        with pytest.raises(auth.AuthError) as exc:
            sdmx_request("dataflow/X")
    assert "401" in str(exc.value)
    assert _SECRET not in str(exc.value)


def test_no_token_on_other_host():
    seen: list[str | None] = []

    def handler(request):
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, content=b"ok")

    with patch("opensdmx.auth.httpx.post") as post, _data_client(handler):
        sdmx_request("x", _base_url="https://hub.example.org/api")

    post.assert_not_called()
    assert seen == [None]


def test_explain_does_not_fetch_token():
    set_explain(True)
    with patch("opensdmx.auth.httpx.post") as post:
        with pytest.raises(ExplainStop):
            sdmx_request("dataflow/X")
    post.assert_not_called()


def test_provider_without_auth_sends_no_header():
    set_provider("https://sdmx.example.org/rest", agency_id="X", rate_limit=0.0)
    seen: list[str | None] = []

    def handler(request):
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, content=b"ok")

    with patch("opensdmx.auth.httpx.post") as post, _data_client(handler):
        sdmx_request("dataflow/X")

    post.assert_not_called()
    assert seen == [None]


def test_request_timeout_from_provider():
    set_provider("https://sdmx.example.org/rest", agency_id="X", rate_limit=0.0, request_timeout=7)
    timeouts = []
    real_client = httpx.Client

    def factory(*args, **kwargs):
        timeouts.append(kwargs.get("timeout"))
        return real_client(transport=httpx.MockTransport(lambda r: httpx.Response(200)), **kwargs)

    with patch("opensdmx.base.httpx.Client", side_effect=factory):
        sdmx_request("dataflow/X")
        sdmx_request("dataflow/X", _timeout=3)

    assert timeouts == [7.0, 3]


def test_escape_key_dots():
    assert escape_key_for_provider("A.TR..x", {"data_key_escape_dots": True}) == "A%2ETR%2E%2Ex"
    assert escape_key_for_provider("A.TR..x", {}) == "A.TR..x"


def test_escaped_key_reaches_the_wire_unchanged():
    set_provider(
        "https://sdmx.example.org/rest", agency_id="X", rate_limit=0.0, data_key_escape_dots=True
    )
    paths = []

    def handler(request):
        paths.append(request.url.raw_path.decode())
        return httpx.Response(200, content=b"A,B\n1,2\n", headers={"content-type": "text/csv"})

    from opensdmx.retrieval import get_data

    ds = {"df_id": "DF", "filters": {"FREQ": "A", "AREA": "", "X": ""}, "dimensions": {}}
    with _data_client(handler):
        get_data(ds)

    assert paths == ["/rest/data/DF/A%2E%2E"]


def test_tuik_preset_declares_auth():
    set_provider("tuik")
    p = get_provider()
    assert p["auth"]["client_id_env"] == "TUIK_CLIENT_ID"
    assert p["auth"]["client_secret_env"] == "TUIK_CLIENT_SECRET"
    assert p["data_key_escape_dots"] is True


def test_explicit_set_timeout_beats_provider_request_timeout(monkeypatch):
    import opensdmx.base as base

    set_provider("https://sdmx.example.org/rest", agency_id="X", rate_limit=0.0, request_timeout=7)
    monkeypatch.setattr(base, "_timeout", 300.0)
    monkeypatch.setattr(base, "_timeout_explicit", False)
    timeouts = []
    real_client = httpx.Client

    def factory(*args, **kwargs):
        timeouts.append(kwargs.get("timeout"))
        return real_client(transport=httpx.MockTransport(lambda r: httpx.Response(200)), **kwargs)

    with patch("opensdmx.base.httpx.Client", side_effect=factory):
        base.set_timeout(600)
        sdmx_request("dataflow/X")

    assert timeouts == [600.0]


def test_token_renewal_is_rate_limited():
    tokens = _TokenServer()

    def handler(request):
        status = 401 if request.headers.get("Authorization") == "Bearer tok-1" else 200
        return httpx.Response(status, content=b"ok")

    with patch("opensdmx.auth.httpx.post", side_effect=tokens), _data_client(handler), patch(
        "opensdmx.base._rate_limit_check"
    ) as check:
        sdmx_request("dataflow/X")

    assert check.call_count == 2  # the first request and the renewed one


def test_token_fetched_before_rate_limit_timestamp():
    order: list[str] = []
    tokens = _TokenServer()

    def fake_post(url, data, timeout):
        order.append("token")
        return tokens(url, data, timeout)

    with patch("opensdmx.auth.httpx.post", side_effect=fake_post), _data_client(
        lambda r: httpx.Response(200, content=b"ok")
    ), patch("opensdmx.base._rate_limit_check", side_effect=lambda *a: order.append("pace")):
        sdmx_request("dataflow/X")

    assert order == ["token", "pace"]


def test_rate_limit_wait_goes_to_reporter_not_stderr(capsys):
    """Under a CLI spinner the countdown must not be written as '\\r' lines on stderr."""
    import time as _time

    import opensdmx.base as base

    set_provider("https://sdmx.example.org/rest", agency_id="X", rate_limit=0.5)
    base._rate_limit_file(False).write_text(str(_time.time()))
    seen: list[float | None] = []
    previous = base.set_wait_reporter(seen.append)
    try:
        base._rate_limit_check(False)
    finally:
        base.set_wait_reporter(previous)

    assert seen and seen[-1] is None
    assert all(r > 0 for r in seen[:-1])
    assert capsys.readouterr().err == ""
