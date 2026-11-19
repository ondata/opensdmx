"""Access tokens for providers that declare `auth` in portals.json.

Only the OAuth2 client-credentials grant is supported, declared as:

    "auth": {
        "type": "oauth2_client_credentials",
        "token_url": "https://.../token",
        "client_id_env": "X_CLIENT_ID",
        "client_secret_env": "X_CLIENT_SECRET",
        "doc_url": "https://... (optional, named in the error when credentials are missing)"
    }

Credentials come from the environment only; they are never logged or cached on disk.
The token is kept in memory for this process, until shortly before it expires.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

# Renew this many seconds before the declared expiry, so a token never expires mid-request.
_EXPIRY_MARGIN = 30.0
_TOKEN_TIMEOUT = 30.0

# (token_url, client_id) -> (access_token, expires_at)
_tokens: dict[tuple[str, str], tuple[str, float]] = {}


class AuthError(RuntimeError):
    """Credentials missing, or the token endpoint refused them."""


_REQUIRED_FIELDS = ("token_url", "client_id_env", "client_secret_env")


def auth_config_problem(cfg: Any) -> str | None:
    """What is wrong with an `auth` block, or None when it is usable.

    A hand-written user portals file can hold any shape: callers check this
    instead of indexing fields that may not be there.
    """
    if not isinstance(cfg, dict):
        return "auth must be an object"
    if cfg.get("type") != "oauth2_client_credentials":
        return f"unsupported auth type {cfg.get('type')!r} (only 'oauth2_client_credentials')"
    missing = [f for f in _REQUIRED_FIELDS if not isinstance(cfg.get(f), str) or not cfg.get(f)]
    if missing:
        return f"auth is missing {', '.join(missing)}"
    return None


def _credentials(cfg: dict[str, Any]) -> tuple[str, str]:
    id_env = cfg.get("client_id_env", "")
    secret_env = cfg.get("client_secret_env", "")
    client_id = os.environ.get(id_env, "")
    client_secret = os.environ.get(secret_env, "")
    missing = [name for name, value in ((id_env, client_id), (secret_env, client_secret)) if not value]
    if missing:
        msg = f"This provider needs credentials: set {' and '.join(missing)} in the environment (once, in ~/.zshenv or ~/.bashrc)."
        if cfg.get("doc_url"):
            msg += f" How to obtain them: {cfg['doc_url']}"
        raise AuthError(msg)
    return client_id, client_secret


def _fetch_token(cfg: dict[str, Any], client_id: str, client_secret: str) -> tuple[str, float]:
    try:
        resp = httpx.post(
            cfg["token_url"],
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=_TOKEN_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        token = payload["access_token"]
    except httpx.HTTPStatusError as e:
        raise AuthError(
            f"The token endpoint {cfg['token_url']} answered HTTP {e.response.status_code}: "
            f"check {cfg.get('client_id_env')} and {cfg.get('client_secret_env')}."
        ) from None
    except (httpx.HTTPError, ValueError, KeyError) as e:
        raise AuthError(f"Could not get an access token from {cfg['token_url']}: {type(e).__name__}") from None
    expires_in = float(payload.get("expires_in") or 300)
    return token, time.monotonic() + max(expires_in - _EXPIRY_MARGIN, 0.0)


def auth_headers(provider: dict[str, Any], *, refresh: bool = False) -> dict[str, str]:
    """`Authorization` header for `provider`, or {} when it declares no `auth`.

    `refresh=True` drops the cached token first (used once after a 401).
    """
    cfg = provider.get("auth")
    if not cfg:
        return {}
    problem = auth_config_problem(cfg)
    if problem:
        raise AuthError(f"Provider configuration error: {problem}.")
    client_id, client_secret = _credentials(cfg)
    key = (cfg["token_url"], client_id)
    cached = _tokens.get(key)
    if refresh or cached is None or cached[1] <= time.monotonic():
        cached = _fetch_token(cfg, client_id, client_secret)
        _tokens[key] = cached
    return {"Authorization": f"Bearer {cached[0]}"}


def clear_tokens() -> None:
    """Forget every cached token (tests)."""
    _tokens.clear()
