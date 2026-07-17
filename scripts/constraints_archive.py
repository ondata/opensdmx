#!/usr/bin/env python3
"""Incremental constraints archive for SDMX providers.

Builds a per-provider archive of available constraints (dataflow -> dimension
-> codes) under data/constraints/, growing a few dataflows per run instead of
bulk-sweeping the provider. Designed to run daily from GitHub Actions with a
small budget; the committed files are the persistent state, so stateless
runners resume where the previous run stopped.

Files per provider:
    data/constraints/{provider}.parquet     df_id, dimension_id, code_id, checked_at
    data/constraints/{provider}_status.csv  probe status per dataflow (human-diffable)
    data/constraints/istat_territorial.csv  derived view: territorial granularity (ISTAT only)

Probe strategy:
    istat    hub bulk endpoint (databrowser API): one sub-second JSON call per
             dataflow, no DSD call, outside the SDMX rate limiter. Failures are
             retried on later runs; `--sdmx-fallback` enables the (slow,
             rate-limited) SDMX chain as fallback.
    others   `load_dataset()` + `get_available_values()`, paced automatically
             by the package rate limiter.

Usage:
    uv run python scripts/constraints_archive.py --provider istat
    uv run python scripts/constraints_archive.py --provider eurostat --budget 300
    uv run python scripts/constraints_archive.py --provider istat --stats

Exit codes: 0 success, 1 fatal error (catalog fetch failed, unknown provider).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl

import opensdmx
# Direct hub access: lets the ISTAT probe skip the per-dataflow DSD call
# (15 s each under the SDMX rate limiter) that the public API would require.
from opensdmx.hub import _get_all_dimension_values_via_hub_bulk

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "constraints"

DEFAULT_BUDGETS = {"istat": 200, "eurostat": 300}
FALLBACK_BUDGET = 50

# Failed dataflows are retried with exponential backoff and never abandoned.
# Hub failures are typically transient — the endpoint sheds load under a burst
# of requests, so a dataflow that failed a few runs in a row is usually fine
# when probed again later. Backoff keeps genuinely dead dataflows from eating
# the budget every run without dropping them from the archive for good.
ERROR_RETRY_BACKOFF_DAYS = 1
MAX_BACKOFF_DOUBLINGS = 6  # caps the wait at 64 days

STATUS_COLUMNS = {
    "df_id": pl.Utf8,
    "df_description": pl.Utf8,
    "status": pl.Utf8,  # ok | empty | error
    "source": pl.Utf8,  # hub | sdmx
    "n_dims": pl.Int64,
    "n_codes": pl.Int64,
    "error_count": pl.Int64,
    "last_error": pl.Utf8,
    "checked_at": pl.Utf8,  # ISO date
}

# ITTER107 territorial levels, least to most detailed.
TERRITORIAL_LEVELS = ["nazionale", "ripartizione", "regione", "provincia", "comune"]


def classify_territorial_code(code: str) -> str | None:
    """Map an ITTER107 code to its territorial level (None if unrecognized)."""
    if code == "IT":
        return "nazionale"
    if re.fullmatch(r"IT[A-Z0-9]", code):
        return "ripartizione"
    if re.fullmatch(r"IT[A-Z0-9]{2}", code):
        return "regione"
    if re.fullmatch(r"IT[A-Z0-9]{3}", code):
        return "provincia"
    if re.fullmatch(r"[0-9]{6}", code):
        return "comune"
    return None


def parquet_path(provider: str) -> Path:
    return DATA_DIR / f"{provider}.parquet"


def status_path(provider: str) -> Path:
    return DATA_DIR / f"{provider}_status.csv"


def load_status(provider: str) -> dict[str, dict]:
    path = status_path(provider)
    if not path.exists():
        return {}
    df = pl.read_csv(path, schema_overrides=STATUS_COLUMNS)
    return {row["df_id"]: dict(row) for row in df.iter_rows(named=True)}


def save_status(provider: str, status: dict[str, dict]) -> None:
    rows = sorted(status.values(), key=lambda r: r["df_id"])
    df = pl.DataFrame(rows, schema=STATUS_COLUMNS)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(status_path(provider))


def merge_archive(provider: str, new_rows: pl.DataFrame, probed_ids: set[str]) -> pl.DataFrame:
    """Replace archive rows for probed dataflows, keep everything else."""
    path = parquet_path(provider)
    if path.exists():
        existing = pl.read_parquet(path).filter(~pl.col("df_id").is_in(sorted(probed_ids)))
        merged = pl.concat([existing, new_rows]) if new_rows.height else existing
    else:
        merged = new_rows
    merged = merged.sort(["df_id", "dimension_id", "code_id"])
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    merged.write_parquet(path)
    return merged


def probe_istat_hub(df_id: str, version: str | None) -> dict[str, list[str]]:
    result = _get_all_dimension_values_via_hub_bulk(df_id, version=version)
    if not result:
        raise RuntimeError("hub bulk endpoint returned no data")
    return result


def probe_sdmx(df_id: str) -> dict[str, list[str]]:
    dataset = opensdmx.load_dataset(df_id)
    available = opensdmx.get_available_values(dataset)
    return {dim: frame["id"].to_list() for dim, frame in available.items()}


def error_retry_due(entry: dict, today: date) -> bool:
    """True when a failed dataflow has waited long enough to be retried.

    The wait doubles with each consecutive failure (1, 2, 4 ... days, capped),
    so a transient hub failure is retried the next run while a dataflow that
    keeps failing decays to a negligible cost. Nothing is ever abandoned.
    """
    checked = date.fromisoformat(entry["checked_at"])
    doublings = min(max(entry["error_count"] - 1, 0), MAX_BACKOFF_DOUBLINGS)
    wait = ERROR_RETRY_BACKOFF_DAYS * (2**doublings)
    return (today - checked).days >= wait


def pick_candidates(
    catalog: pl.DataFrame, status: dict[str, dict], stale_days: int
) -> list[dict]:
    """Order: never probed, then errored (backoff elapsed), then stale."""
    today = date.today()
    pending, errored, stale = [], [], []
    for row in catalog.sort("df_id").iter_rows(named=True):
        entry = status.get(row["df_id"])
        if entry is None:
            pending.append(row)
            continue
        checked = date.fromisoformat(entry["checked_at"])
        if entry["status"] == "error":
            if error_retry_due(entry, today):
                errored.append((checked, row))
        elif (today - checked).days > stale_days:
            stale.append((checked, row))
    errored.sort(key=lambda item: item[0])
    stale.sort(key=lambda item: item[0])
    return pending + [row for _, row in errored] + [row for _, row in stale]


def rebuild_istat_territorial(archive: pl.DataFrame, status: dict[str, dict]) -> None:
    """Derive per-dataflow territorial granularity from territorial dimension codes.

    Older ISTAT dataflows use ITTER107 as territorial dimension, newer ones use
    REF_AREA with the same code hierarchy. Codes that match no pattern
    (aggregates like `IT108_NC`, `FILTER__*`, foreign areas) are ignored;
    dataflows where nothing classifies are skipped.
    """
    territorial = archive.filter(
        pl.col("dimension_id").str.starts_with("ITTER")
        | (pl.col("dimension_id") == "REF_AREA")
    )
    rows = []
    for (df_id,), group in territorial.group_by(["df_id"], maintain_order=True):
        codes = group["code_id"].to_list()
        levels_seen = {lvl for code in codes if (lvl := classify_territorial_code(code))}
        ordered = [lvl for lvl in TERRITORIAL_LEVELS if lvl in levels_seen]
        if not ordered:
            continue
        entry = status.get(df_id, {})
        rows.append(
            {
                "df_id": df_id,
                "df_description": entry.get("df_description", ""),
                "dimension_id": group["dimension_id"][0],
                "max_level": ordered[-1] if ordered else "",
                "levels": "|".join(ordered),
                "n_territories": len(codes),
                "checked_at": entry.get("checked_at", ""),
            }
        )
    rows.sort(key=lambda r: r["df_id"])
    out = DATA_DIR / "istat_territorial.csv"
    pl.DataFrame(
        rows,
        schema={
            "df_id": pl.Utf8,
            "df_description": pl.Utf8,
            "dimension_id": pl.Utf8,
            "max_level": pl.Utf8,
            "levels": pl.Utf8,
            "n_territories": pl.Int64,
            "checked_at": pl.Utf8,
        },
    ).write_csv(out)
    print(f"territorial view: {len(rows)} dataflows -> {out.name}")


def print_stats(provider: str) -> None:
    status = load_status(provider)
    if not status:
        print(f"{provider}: no archive yet")
        return
    counts: dict[str, int] = {}
    for entry in status.values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    total_codes = sum(e["n_codes"] or 0 for e in status.values())
    print(f"{provider}: {len(status)} dataflows probed "
          f"({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))}), "
          f"{total_codes:,} codes archived")


def run(provider: str, budget: int, pause: float, stale_days: int,
        max_minutes: float, sdmx_fallback: bool) -> int:
    opensdmx.set_provider(provider)
    opensdmx.set_timeout(60)

    print(f"fetching {provider} catalog...")
    catalog = opensdmx.all_available()
    print(f"catalog: {len(catalog)} dataflows")

    status = load_status(provider)
    candidates = pick_candidates(catalog, status, stale_days)
    print(f"candidates: {len(candidates)} (budget {budget}, max {max_minutes:.0f} min)")

    today = date.today().isoformat()
    deadline = time.monotonic() + max_minutes * 60
    archive_rows: list[dict] = []
    probed_ids: set[str] = set()
    n_ok = n_empty = n_error = 0

    for row in candidates[:budget]:
        if time.monotonic() > deadline:
            print("time budget exhausted, stopping")
            break
        df_id = row["df_id"]
        previous = status.get(df_id, {})
        entry = {
            "df_id": df_id,
            "df_description": row["df_description"] or "",
            "status": "error",
            "source": "",
            "n_dims": 0,
            "n_codes": 0,
            "error_count": (previous.get("error_count") or 0),
            "last_error": "",
            "checked_at": today,
        }
        try:
            if provider == "istat":
                try:
                    result = probe_istat_hub(df_id, row["version"])
                    entry["source"] = "hub"
                except Exception:
                    if not sdmx_fallback:
                        raise
                    result = probe_sdmx(df_id)
                    entry["source"] = "sdmx"
            else:
                result = probe_sdmx(df_id)
                entry["source"] = "sdmx"
        except Exception as exc:
            entry["error_count"] += 1
            entry["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
            n_error += 1
            print(f"  {df_id}: ERROR ({entry['last_error']})")
        else:
            entry["error_count"] = 0
            entry["n_dims"] = len(result)
            entry["n_codes"] = sum(len(codes) for codes in result.values())
            entry["status"] = "ok" if entry["n_codes"] else "empty"
            if entry["n_codes"]:
                n_ok += 1
                probed_ids.add(df_id)
                for dim_id, codes in result.items():
                    for code in codes:
                        archive_rows.append(
                            {"df_id": df_id, "dimension_id": dim_id,
                             "code_id": code, "checked_at": today}
                        )
            else:
                n_empty += 1
            print(f"  {df_id}: {entry['status']} "
                  f"({entry['n_dims']} dims, {entry['n_codes']} codes, {entry['source']})")
        status[df_id] = entry
        time.sleep(pause)

    new_rows = pl.DataFrame(
        archive_rows,
        schema={"df_id": pl.Utf8, "dimension_id": pl.Utf8,
                "code_id": pl.Utf8, "checked_at": pl.Utf8},
    )
    archive = merge_archive(provider, new_rows, probed_ids)
    save_status(provider, status)
    if provider == "istat":
        rebuild_istat_territorial(archive, status)

    done = sum(1 for e in status.values() if e["status"] != "error")
    print(f"\nrun: {n_ok} ok, {n_empty} empty, {n_error} errors | "
          f"progress: {done}/{len(catalog)} dataflows resolved")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", required=True, help="opensdmx provider id (istat, eurostat, ...)")
    parser.add_argument("--budget", type=int, default=None,
                        help="max dataflows probed this run (default: per-provider)")
    parser.add_argument("--pause", type=float, default=1.0,
                        help="courtesy pause between dataflows, seconds (default: 1)")
    parser.add_argument("--stale-days", type=int, default=180,
                        help="re-probe entries older than this (default: 180)")
    parser.add_argument("--max-minutes", type=float, default=20,
                        help="wall-clock cap for the probe loop (default: 20)")
    parser.add_argument("--sdmx-fallback", action="store_true",
                        help="istat only: fall back to the rate-limited SDMX chain on hub failure")
    parser.add_argument("--stats", action="store_true", help="print archive stats and exit")
    args = parser.parse_args()

    if args.stats:
        print_stats(args.provider)
        return 0

    budget = args.budget if args.budget is not None else DEFAULT_BUDGETS.get(args.provider, FALLBACK_BUDGET)
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"constraints archive | provider={args.provider} budget={budget} | {started}")
    try:
        return run(args.provider, budget, args.pause, args.stale_days,
                   args.max_minutes, args.sdmx_fallback)
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
