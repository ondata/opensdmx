"""SQLite cache for dimensions and codelist data."""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

_DB_PATH = Path(tempfile.gettempdir()) / "istatpy_cache.db"
_TTL = 7 * 86400  # 7 days


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS structure_dims (
                structure_id TEXT NOT NULL,
                dimension_id TEXT NOT NULL,
                position     INTEGER,
                codelist_id  TEXT,
                cached_at    REAL NOT NULL,
                PRIMARY KEY (structure_id, dimension_id)
            );
            CREATE TABLE IF NOT EXISTS codelist_info (
                codelist_id TEXT PRIMARY KEY,
                description TEXT,
                cached_at   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS codelist_values (
                codelist_id TEXT NOT NULL,
                code_id     TEXT NOT NULL,
                code_name   TEXT,
                cached_at   REAL NOT NULL,
                PRIMARY KEY (codelist_id, code_id)
            );
        """)


_init_db()


# --- structure dims ---

def get_cached_dims(structure_id: str) -> dict | None:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM structure_dims WHERE structure_id = ? ORDER BY position",
            (structure_id,),
        ).fetchall()
    if not rows:
        return None
    if time.time() - rows[0]["cached_at"] > _TTL:
        return None
    return {
        row["dimension_id"]: {
            "id": row["dimension_id"],
            "position": row["position"],
            "codelist_id": row["codelist_id"],
        }
        for row in rows
    }


def save_dims(structure_id: str, dims: dict) -> None:
    now = time.time()
    with _get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO structure_dims VALUES (?, ?, ?, ?, ?)",
            [(structure_id, d["id"], d["position"], d["codelist_id"], now) for d in dims.values()],
        )


# --- codelist info (description) ---

def is_codelist_info_cached(codelist_id: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT cached_at FROM codelist_info WHERE codelist_id = ?",
            (codelist_id,),
        ).fetchone()
    if row is None:
        return False
    return time.time() - row["cached_at"] <= _TTL


def get_cached_codelist_info(codelist_id: str) -> str | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT description FROM codelist_info WHERE codelist_id = ?",
            (codelist_id,),
        ).fetchone()
    return row["description"] if row else None


def save_codelist_info(codelist_id: str, description: str | None) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO codelist_info VALUES (?, ?, ?)",
            (codelist_id, description, time.time()),
        )


# --- codelist values ---

def get_cached_codelist_values(codelist_id: str) -> list | None:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT code_id, code_name, cached_at FROM codelist_values WHERE codelist_id = ? ORDER BY code_id",
            (codelist_id,),
        ).fetchall()
    if not rows:
        return None
    if time.time() - rows[0]["cached_at"] > _TTL:
        return None
    return [{"id": r["code_id"], "name": r["code_name"]} for r in rows]


def save_codelist_values(codelist_id: str, values: list) -> None:
    now = time.time()
    with _get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO codelist_values VALUES (?, ?, ?, ?)",
            [(codelist_id, v["id"], v["name"], now) for v in values],
        )
