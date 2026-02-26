"""Core functions for communicating with the ISTAT SDMX REST API."""

import tempfile
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

_RATE_LIMIT_FILE = Path(tempfile.gettempdir()) / "istatpy_rate_limit.log"
_MIN_INTERVAL = 12.0  # seconds between API calls


def _rate_limit_check() -> None:
    """Enforce minimum 12s between API calls. Warns and sleeps if needed."""
    if _RATE_LIMIT_FILE.exists():
        try:
            last = float(_RATE_LIMIT_FILE.read_text().strip())
            elapsed = time.time() - last
            if elapsed < _MIN_INTERVAL:
                wait = _MIN_INTERVAL - elapsed
                print(f"[istatpy] Rate limit: waiting {wait:.1f}s...")
                time.sleep(wait)
        except (ValueError, OSError):
            pass
    _RATE_LIMIT_FILE.write_text(str(time.time()))

# API configuration
_config = {
    "base_url": "https://esploradati.istat.it/SDMXWS/rest",
    "agency_id": "IT1",
    "timeout": 300.0,
}


def get_base_url() -> str:
    return _config["base_url"]


def get_agency_id() -> str:
    return _config["agency_id"]


def istat_timeout(seconds: float | None = None) -> float:
    """Get or set the API timeout in seconds (default: 300)."""
    if seconds is None:
        return _config["timeout"]
    old = _config["timeout"]
    _config["timeout"] = float(seconds)
    return old


def istat_request(path: str, accept: str = "application/xml", **params) -> httpx.Response:
    """Make a request to the ISTAT API with retry logic."""
    url = f"{get_base_url()}/{path}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    def _do_request() -> httpx.Response:
        _rate_limit_check()
        with httpx.Client(timeout=_config["timeout"]) as client:
            resp = client.get(
                url,
                params=params or None,
                headers={
                    "Accept": accept,
                    "User-Agent": "istatpy Python package",
                },
            )
            resp.raise_for_status()
            return resp

    return _do_request()


def istat_request_xml(path: str, **params):
    """Make a request and return the raw XML bytes."""
    resp = istat_request(path, accept="application/xml", **params)
    return resp.content


def istat_request_csv(path: str, **params):
    """Make a request and return CSV content as a Polars DataFrame."""
    import io
    import polars as pl

    resp = istat_request(path, accept="text/csv", **params)
    return pl.read_csv(io.BytesIO(resp.content), infer_schema_length=10000)
