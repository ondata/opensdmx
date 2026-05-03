"""Core HTTP client and provider configuration for SDMX 2.1 REST APIs."""

import hashlib
import json
import os
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path

import httpx
import portalocker
from tenacity import retry, stop_after_attempt, wait_exponential

# Defaults for fields not specified in portals.json or custom providers
_DEFAULTS: dict = {
    "rate_limit": 0.5,
    "language": "en",
    "dataflow_params": {},
    "constraint_endpoint": "availableconstraint",
    "datastructure_agency": "ALL",
    "user_agent": None,
    "data_key_format": "dots",
}

# Load portals from bundled JSON
_PORTALS_FILE = Path(__file__).parent / "portals.json"
with open(_PORTALS_FILE) as f:
    _raw_portals = json.load(f)

PROVIDERS: dict[str, dict] = {
    key: {**_DEFAULTS, **entry}
    for key, entry in _raw_portals.items()
}

_active_provider: str | dict = "eurostat"
_timeout: float = 300.0
_extra_headers: dict[str, str] = {}

_rate_limit_context: str = ""


def set_extra_headers(headers: dict[str, str]) -> None:
    """Set extra HTTP headers to include in all subsequent SDMX requests."""
    global _extra_headers
    _extra_headers = dict(headers)


def get_extra_headers() -> dict[str, str]:
    """Return the currently configured extra HTTP headers."""
    return _extra_headers


def set_rate_limit_context(msg: str) -> None:
    """Set a human-readable label shown during rate-limit waits."""
    global _rate_limit_context
    _rate_limit_context = msg


def set_provider(
    name_or_url: str,
    agency_id: str | None = None,
    rate_limit: float = 0.5,
    language: str = "en",
) -> None:
    """Set the active SDMX provider.

    Args:
        name_or_url: Preset name (e.g. 'eurostat', 'istat', 'ecb') or a custom base URL.
        agency_id:   Required when name_or_url is a URL. Ignored for presets.
        rate_limit:  Minimum seconds between API calls (custom provider only).
        language:    Preferred language for descriptions (custom provider only).
    """
    global _active_provider
    if name_or_url in PROVIDERS:
        _active_provider = name_or_url
    else:
        _active_provider = {
            **_DEFAULTS,
            "base_url": name_or_url.rstrip("/"),
            "agency_id": agency_id or "",
            "rate_limit": rate_limit,
            "language": language,
        }


def get_provider() -> dict:
    """Return the active provider configuration dict."""
    if isinstance(_active_provider, dict):
        return _active_provider
    return PROVIDERS[_active_provider]


def get_base_url() -> str:
    return get_provider()["base_url"]


def get_agency_id() -> str:
    return get_provider()["agency_id"]


@lru_cache(maxsize=1)
def _resolve_cache_base_cached(env_override: str | None) -> Path:
    """Memoized resolution — keyed on OPENSDMX_CACHE_DIR so tests can override."""
    from platformdirs import user_cache_dir

    candidates = []
    if env_override:
        candidates.append(Path(env_override))
    candidates.append(Path(user_cache_dir("opensdmx")))

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.touch()
            probe.unlink()
            return path
        except OSError:
            continue

    import getpass
    fallback = Path(tempfile.gettempdir()) / f"opensdmx-{getpass.getuser()}"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _resolve_cache_base() -> Path:
    """Return the base cache directory, with fallback to /tmp if not writable.

    Resolution order:
    1. OPENSDMX_CACHE_DIR env var
    2. platformdirs.user_cache_dir (XDG on Linux, OS-native on macOS/Windows)
    3. /tmp/opensdmx-{username} if neither is writable

    The write-probe runs once per (env value) — subsequent calls hit the
    lru_cache so request-time overhead is near zero.
    """
    import os
    return _resolve_cache_base_cached(os.environ.get("OPENSDMX_CACHE_DIR"))


def _provider_cache_key() -> str:
    """Stable per-provider key for cache, rate-limit and lock files.

    For a preset provider the key is the preset name. For a custom URL
    provider it is the agency_id when set, otherwise an 8-char sha256 of
    the base URL — so two custom providers with different URLs don't share
    the same cache/lock and get serialized together.
    """
    if isinstance(_active_provider, str):
        return _active_provider
    agency = get_agency_id()
    if agency:
        return agency
    base = _active_provider.get("base_url", "")
    return "custom_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]


def get_cache_dir() -> Path:
    """Return cache directory for the active provider."""
    cache_dir = _resolve_cache_base() / _provider_cache_key()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def set_timeout(seconds: float | None = None) -> float:
    """Get or set the API timeout in seconds (default: 300)."""
    global _timeout
    if seconds is None:
        return _timeout
    old = _timeout
    _timeout = float(seconds)
    return old


def _rate_limit_dir() -> Path:
    """Return the per-user directory for rate-limit state files.

    Sits under the per-user cache base (same root as the data cache), so
    lock and timestamp files are isolated per user and not exposed in the
    world-writable system temp dir.
    """
    d = _resolve_cache_base() / "rate_limit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rate_limit_file() -> Path:
    """Return per-provider rate limit timestamp file."""
    return _rate_limit_dir() / f"{_provider_cache_key()}.log"


def _rate_limit_lock_file() -> Path:
    """Return per-provider lock file.

    Held for the entire HTTP call so that requests to the same provider are
    strictly serialized across processes. Without this lock, two parallel
    callers read the same timestamp, sleep the same amount, and fire HTTP
    requests nearly simultaneously — defeating the rate limit.
    """
    return _rate_limit_dir() / f"{_provider_cache_key()}.lock"


def _rate_limit_check() -> None:
    """Wait if needed to respect the provider's rate limit.

    Reads the last-call timestamp from the per-user rate-limit directory
    (`_rate_limit_dir()`, under the resolved cache base). If less than rate_limit seconds
    have passed since the last HTTP request was sent, sleeps for the remaining
    time. The timestamp is written at request start (before the HTTP call), so
    the interval is measured send-to-send, not receive-to-send.
    Cache hits never reach this function — only real HTTP calls apply.
    """
    min_interval = get_provider()["rate_limit"]
    rl_file = _rate_limit_file()
    if rl_file.exists():
        try:
            last = float(rl_file.read_text().strip())
            elapsed = time.time() - last
            if elapsed < min_interval:
                wait = min_interval - elapsed
                end_time = time.time() + wait
                label = _rate_limit_context or "Waiting"
                while True:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        break
                    remaining_str = "< 1s" if remaining < 1 else f"{remaining:.0f}s"
                    sys.stderr.write(f"\r{label} ({remaining_str})...  ")
                    sys.stderr.flush()
                    time.sleep(0.2)
                sys.stderr.write("\n")
                sys.stderr.flush()
        except (ValueError, OSError):
            pass


def sdmx_request(path: str, accept: str = "application/xml", **params) -> httpx.Response:
    """Make a request to the active SDMX provider with retry logic."""
    url = f"{get_base_url()}/{path}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4), reraise=True)
    def _do_request() -> httpx.Response:
        # Hold an exclusive file lock for the whole HTTP call. This serializes
        # requests to the same provider across processes, so the rate limit is
        # actually enforced instead of being defeated by parallel reads of the
        # timestamp file. Lock is per-provider, so different providers stay
        # parallel. If the process dies, the kernel releases the flock.
        with portalocker.Lock(str(_rate_limit_lock_file()), flags=portalocker.LOCK_EX):
            _rate_limit_check()
            # Record timestamp at request START (before HTTP call) so the
            # interval is measured send-to-send, not receive-to-send.
            try:
                _rate_limit_file().write_text(str(time.time()))
            except OSError:
                pass
            with httpx.Client(timeout=_timeout, follow_redirects=True) as client:
                user_agent = os.environ.get(
                    "OPENSDMX_USER_AGENT",
                    get_provider().get("user_agent") or "opensdmx Python package",
                )
                extra = {k: v for k, v in _extra_headers.items() if k.lower() != "user-agent"}
                resp = client.get(
                    url,
                    params=params or None,
                    headers={"Accept": accept, "User-Agent": user_agent, **extra},
                )
                resp.raise_for_status()
                return resp

    return _do_request()


def sdmx_request_xml(path: str, **params):
    """Make a request and return the raw XML bytes.

    Uses the SDMX 2.1 structure Accept header — the generic "application/xml"
    is not honoured by some providers (e.g. OECD) which then default to JSON.
    """
    resp = sdmx_request(
        path,
        accept="application/vnd.sdmx.structure+xml;version=2.1",
        **params,
    )
    return resp.content


def _parse_sdmx_json(payload: dict):
    """Parse an SDMX-JSON data response into a Polars DataFrame.

    Supports the SDMX-JSON 1.0 format returned by providers such as World Bank.
    Each series key is a colon-separated string of dimension indices (e.g. "0:1:2");
    each observation key is an index into the observation dimension values.
    """
    import polars as pl

    data = payload.get("data", payload)
    structure = data["structure"]
    series_dims = structure["dimensions"]["series"]
    obs_dims = structure["dimensions"]["observation"]

    # Some providers (e.g. World Bank) order the series key by descending keyPosition
    # rather than ascending. Sort accordingly so indices map correctly.
    key_ordered_dims = sorted(
        series_dims, key=lambda d: d.get("keyPosition", 0), reverse=True
    )

    rows: list[dict] = []
    for dataset in data.get("dataSets", []):
        for series_key, series_data in dataset.get("series", {}).items():
            series_indices = [int(i) for i in series_key.split(":")]
            dim_values = {
                dim["id"]: dim["values"][series_indices[idx]]["id"]
                for idx, dim in enumerate(key_ordered_dims)
            }
            for obs_key, obs_values in series_data.get("observations", {}).items():
                obs_idx = int(obs_key)
                row = dict(dim_values)
                for odim in obs_dims:
                    row[odim["id"]] = odim["values"][obs_idx]["id"]
                row["OBS_VALUE"] = obs_values[0] if obs_values else None
                rows.append(row)

    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).with_columns(pl.col("OBS_VALUE").cast(pl.Float64, strict=False))


def sdmx_request_csv(path: str, **params):
    """Make a request and return CSV content as a Polars DataFrame."""
    import io
    import polars as pl

    provider = get_provider()
    data_accept = provider.get("data_accept")
    fmt = provider.get("data_format_param")

    if data_accept:
        # Provider requires a specific Accept header (e.g. World Bank JSON)
        suffix = provider.get("data_path_suffix", "")
        unsupported = provider.get("unsupported_params", [])
        dropped = [p for p in unsupported if p in params]
        if dropped:
            import logging
            logging.getLogger(__name__).warning(
                "Provider '%s' does not support: %s. These parameters will be ignored.",
                provider.get('name', ''),
                ', '.join(dropped),
            )
        filtered_params = {k: v for k, v in params.items() if k not in unsupported}
        resp = sdmx_request(path + suffix, accept=data_accept, **filtered_params)
        import re
        text = re.sub(r"\[,", "[null,", resp.text)
        return _parse_sdmx_json(json.loads(text))
    elif fmt:
        # Provider requires a ?format= query param (e.g. Eurostat SDMX-CSV)
        resp = sdmx_request(path, accept="application/xml", format=fmt, **params)
    else:
        resp = sdmx_request(path, accept="text/csv", **params)
    return pl.read_csv(io.BytesIO(resp.content), infer_schema_length=10000, schema_overrides={"TIME_PERIOD": pl.Utf8, "OBS_VALUE": pl.Float64, "OBS_FLAG": pl.Utf8, "OBS_STATUS": pl.Utf8, "CONF_STATUS": pl.Utf8})
