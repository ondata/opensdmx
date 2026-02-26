"""CLI for istatpy — ISTAT SDMX REST API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .base import _RATE_LIMIT_FILE, get_base_url

app = typer.Typer(help="istatpy — ISTAT SDMX REST API CLI")
console = Console()
err_console = Console(stderr=True)


def _check_api_reachable() -> None:
    """If no rate-limit log exists, do a lightweight HEAD check on the API."""
    if _RATE_LIMIT_FILE.exists():
        return
    try:
        with httpx.Client(timeout=5.0) as client:
            client.head(get_base_url())
    except (httpx.ConnectTimeout, httpx.NetworkError):
        err_console.print(
            "[red]⚠ ISTAT API non raggiungibile.[/red] "
            "L'IP potrebbe essere bloccato (rate limit: max 5 req/min). "
            "Il blocco può durare 1-2 giorni."
        )
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def _startup(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        _check_api_reachable()


@app.command()
def search(keyword: str = typer.Argument(..., help="Keyword to search in dataset descriptions")):
    """Search datasets by keyword."""
    from . import search_dataset
    try:
        df = search_dataset(keyword)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if df.is_empty():
        err_console.print(f"[yellow]No datasets found for:[/yellow] {keyword}")
        raise typer.Exit(1)

    table = Table(title=f"Search: {keyword}", show_lines=False)
    table.add_column("df_id", style="cyan", no_wrap=True)
    table.add_column("df_description")

    for row in df.iter_rows(named=True):
        table.add_row(row["df_id"], row["df_description"] or "")

    console.print(table)


@app.command()
def info(dataset_id: str = typer.Argument(..., help="Dataset ID (e.g. 139_176)")):
    """Show metadata and dimensions for a dataset."""
    from . import dimensions_info, istat_dataset
    try:
        ds = istat_dataset(dataset_id)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    meta = (
        f"ID:          {ds['df_id']}\n"
        f"Version:     {ds['version']}\n"
        f"Description: {ds['df_description']}\n"
        f"Structure:   {ds['df_structure_id']}"
    )
    console.print(Panel(meta, title="Dataset Info", expand=False))

    try:
        dim_df = dimensions_info(ds)
    except Exception as e:
        err_console.print(f"[yellow]Warning:[/yellow] could not fetch dimension info: {e}")
        return

    if dim_df.is_empty():
        console.print("[yellow]No dimensions found.[/yellow]")
        return

    table = Table(title="Dimensions", show_lines=False)
    table.add_column("dimension_id", style="cyan", no_wrap=True)
    table.add_column("position")
    table.add_column("codelist_id")
    table.add_column("description")

    for row in dim_df.iter_rows(named=True):
        table.add_row(
            row["dimension_id"],
            str(row["position"]) if row["position"] is not None else "",
            row["codelist_id"] or "",
            row.get("description") or "",
        )

    console.print(table)


@app.command()
def values(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    dim: str = typer.Argument(..., help="Dimension ID (e.g. FREQ)"),
):
    """Show available values for a dimension."""
    from . import get_dimension_values, istat_dataset
    try:
        ds = istat_dataset(dataset_id)
        val_df = get_dimension_values(ds, dim)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if val_df.is_empty():
        err_console.print(f"[yellow]No values found for dimension:[/yellow] {dim}")
        raise typer.Exit(1)

    table = Table(title=f"{dataset_id} / {dim}", show_lines=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name")

    for row in val_df.iter_rows(named=True):
        table.add_row(row["id"] or "", row["name"] or "")

    console.print(table)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def get(
    ctx: typer.Context,
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file (.csv/.parquet/.json)"),
):
    """Get data for a dataset. Extra --DIM VALUE pairs are used as filters."""
    from . import get_data, istat_dataset, set_filters

    # Parse extra args as --KEY VALUE pairs
    extra = ctx.args
    filters = {}
    i = 0
    while i < len(extra):
        arg = extra[i]
        if arg.startswith("--") and i + 1 < len(extra):
            key = arg[2:]
            filters[key] = extra[i + 1]
            i += 2
        else:
            err_console.print(f"[red]Unexpected argument:[/red] {arg}")
            raise typer.Exit(1)

    try:
        ds = istat_dataset(dataset_id)
        if filters:
            ds = set_filters(ds, **filters)
        df = get_data(ds)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if out is None:
        # Write CSV to stdout
        sys.stdout.write(df.write_csv())
    else:
        suffix = out.suffix.lower()
        if suffix == ".parquet":
            df.write_parquet(out)
        elif suffix == ".json":
            df.write_ndjson(out)
        else:
            df.write_csv(out)
        console.print(f"[green]Saved:[/green] {out}")


def main():
    app()
