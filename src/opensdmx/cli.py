"""CLI for opensdmx — SDMX 2.1 REST API client."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

_HELP_FLAGS = {"--help", "-h"}

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .base import get_base_url, get_provider

app = typer.Typer(help="opensdmx — SDMX 2.1 REST API CLI\n\nEnv vars: OPENSDMX_PROVIDER (provider name or URL), OPENSDMX_AGENCY (agency ID for custom URLs)")
console = Console()
err_console = Console(stderr=True)

# Global output mode — set by --output in the app callback.
_output_mode: str = "table"


@contextmanager
def _status_ctx(msg: str):
    """Show a Rich spinner only in table mode; silent otherwise."""
    if _output_mode == "table":
        with console.status(msg):
            yield
    else:
        yield


def _emit(data: object, df=None) -> None:
    """Write structured output to stdout based on _output_mode.

    data  — Python list/dict for JSON mode
    df    — Polars DataFrame for CSV mode (falls back to data if None)
    """
    if _output_mode == "json":
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    elif _output_mode == "csv":
        if df is not None:
            sys.stdout.write(df.write_csv())
        else:
            # Fallback: serialise list-of-dicts manually
            if isinstance(data, list) and data:
                keys = list(data[0].keys())
                sys.stdout.write(",".join(keys) + "\n")
                for row in data:
                    sys.stdout.write(",".join(str(row.get(k, "")) for k in keys) + "\n")
            else:
                sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version
        console.print(version("opensdmx"))
        raise typer.Exit()

_PROVIDER_HELP = "Provider name ('eurostat', 'ecb') or custom base URL. Env: OPENSDMX_PROVIDER"


def _parse_extra_filters(ctx: typer.Context) -> dict:
    """Parse extra --KEY VALUE args from context as dimension filters.

    Supports multiple values per dimension:
      --geo IT --geo FR  →  {"geo": "IT+FR"}
      --geo IT+FR        →  {"geo": "IT+FR"}
    """
    accumulated: dict[str, list[str]] = {}
    extra = ctx.args
    i = 0
    while i < len(extra):
        arg = extra[i]
        if arg.startswith("--") and i + 1 < len(extra):
            key = arg[2:]
            accumulated.setdefault(key, []).append(extra[i + 1])
            i += 2
        else:
            err_console.print(f"[red]Unexpected argument:[/red] {arg}")
            raise typer.Exit(1)
    return {k: "+".join(v) if len(v) > 1 else v[0] for k, v in accumulated.items()}


def _apply_provider(provider: str | None) -> None:
    """Set active provider from CLI option or OPENSDMX_PROVIDER env var."""
    import os
    resolved = provider or os.environ.get("OPENSDMX_PROVIDER")
    if resolved:
        from .base import PROVIDERS, set_provider
        if resolved not in PROVIDERS and not resolved.startswith("http"):
            valid = ", ".join(sorted(PROVIDERS))
            err_console.print(f"[red]Error:[/red] unknown provider '{resolved}'. Valid: {valid}")
            raise typer.Exit(1)
        agency_id = os.environ.get("OPENSDMX_AGENCY")
        set_provider(resolved, agency_id=agency_id)


def _check_api_reachable() -> None:
    """Do a lightweight GET check on the active provider's base URL."""
    from .base import _rate_limit_file
    if _rate_limit_file().exists():
        return
    try:
        with httpx.Client(timeout=5.0) as client:
            client.get(get_base_url())
    except (httpx.HTTPError, OSError):
        provider_name = get_provider().get("agency_id", "API")
        err_console.print(
            f"[red]⚠ {provider_name} API unreachable.[/red] "
            "Check your network connection or provider URL."
        )
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def _startup(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table (default), json, csv"),
) -> None:
    global _output_mode
    if output not in ("table", "json", "csv"):
        err_console.print(f"[red]Error:[/red] invalid --output value '{output}'. Choose: table, json, csv")
        raise typer.Exit(1)
    _output_mode = output
    if ctx.invoked_subcommand is None:
        from importlib.metadata import version as _version
        console.print(f"opensdmx {_version('opensdmx')}\n")
        console.print(ctx.get_help())
        raise typer.Exit()
    if not _HELP_FLAGS.intersection(sys.argv):
        _check_api_reachable()


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Keyword to search in dataset descriptions"),
    semantic: bool = typer.Option(False, "--semantic", "-s", help="Use semantic search via Ollama embeddings"),
    n: int = typer.Option(50, "--n", help="Results per page (default: 50). Combine with --page to paginate."),
    page: int = typer.Option(1, "--page", help="Page number, 1-based (default: 1). Use with --n to paginate. Title shows range e.g. '21-40 of 114'."),
    all_results: bool = typer.Option(False, "--all", help="Show ALL results from cache, ignoring --n and --page."),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Restrict search to a category (leaf id or dotted path). Provider must support categories. See `opensdmx tree`."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Search datasets by keyword in the local cache (or semantically with --semantic).

    Results come from the local cache — fast, no network call.
    Default provider: eurostat. Use --provider to switch.

    PAGINATION: By default shows 50 results (page 1). Use --page to navigate,
    --n to change page size, or --all to retrieve every match at once.
    The title always shows the current range and total, e.g. '51-100 of 114'.

    Tip: semantic search matches meaning, not exact words. Try synonyms
    or related terms for better results (e.g. "jobless" instead of "unemployment").

    Examples:

      opensdmx search unemployment              # page 1, 50 results ranked by relevance
      opensdmx search unemployment --all        # all 114 results
      opensdmx search unemployment --page 2     # results 21-40
      opensdmx search unemployment --n 5 --page 3   # results 11-15
      opensdmx search --semantic disoccupazione --n 5
      opensdmx search population --provider istat
    """
    _apply_provider(provider)

    if semantic:
        from .embed import semantic_search
        try:
            with _status_ctx("[dim]Semantic search...[/dim]"):
                df = semantic_search(keyword, n=n)
        except FileNotFoundError:
            err_console.print(
                "[red]Error:[/red] Embeddings cache not found.\n"
                "Build it first:  opensdmx embed"
            )
            raise typer.Exit(1)
        except Exception as e:
            err_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        rows = [
            {"df_id": r["df_id"], "df_description": r["df_description"] or "", "score": round(r["score"], 3)}
            for r in df.iter_rows(named=True)
        ]
        if _output_mode != "table":
            _emit(rows, df=df.select(["df_id", "df_description", "score"]))
            return

        table = Table(title=f"Semantic search: {keyword}", show_lines=False)
        table.add_column("df_id", style="cyan", no_wrap=True)
        table.add_column("df_description")
        table.add_column("score", style="dim")
        for r in rows:
            table.add_row(r["df_id"], r["df_description"], f"{r['score']:.3f}")
        console.print(table)
        return

    from . import search_dataset
    try:
        with _status_ctx("[dim]Searching...[/dim]"):
            df = search_dataset(keyword)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if category:
        import polars as pl

        from .categories import CategoriesNotSupported, filter_by_category
        try:
            cat_df = filter_by_category(category)
        except CategoriesNotSupported as e:
            err_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        if cat_df.is_empty():
            err_console.print(f"[yellow]No dataflow found for category:[/yellow] {category}")
            raise typer.Exit(0)
        allowed = set(cat_df["df_id"].to_list())
        df = df.filter(pl.col("df_id").is_in(list(allowed)))

    if df.is_empty():
        msg = f"No datasets found for: {keyword}"
        if category:
            msg += f" (category={category})"
        err_console.print(f"[yellow]{msg}[/yellow]")
        raise typer.Exit(0)

    total = len(df)

    if all_results:
        page_df = df
        title = f"Search: {keyword} ({total})"
    else:
        offset = (page - 1) * n
        if offset >= total:
            err_console.print(f"[yellow]Page {page} out of range.[/yellow] Total results: {total}")
            raise typer.Exit(0)
        page_df = df.slice(offset, n)
        end = min(offset + n, total)
        if total > n:
            title = f"Search: {keyword} ({offset + 1}-{end} of {total})"
        else:
            title = f"Search: {keyword} ({total})"

    if _output_mode != "table":
        rows = [
            {"df_id": r["df_id"], "df_description": r["df_description"] or "", "score": r.get("score", 0)}
            for r in page_df.iter_rows(named=True)
        ]
        _emit(rows, df=page_df.select(["df_id", "df_description", "score"]))
        return

    table = Table(title=title, show_lines=False)
    table.add_column("df_id", style="cyan", no_wrap=True)
    table.add_column("df_description")
    table.add_column("score", style="dim")

    for row in page_df.iter_rows(named=True):
        table.add_row(row["df_id"], row["df_description"] or "", str(row.get("score", "")))

    console.print(table)


@app.command()
def info(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Show metadata and dimensions for a dataset.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx info NAMA_10_GDP
      opensdmx info DCIS_POPRES1 --provider istat
    """
    _apply_provider(provider)
    from . import dimensions_info, load_dataset
    try:
        with _status_ctx("[dim]Loading dataset...[/dim]"):
            ds = load_dataset(dataset_id)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        with _status_ctx("[dim]Loading dimensions...[/dim]"):
            dim_df = dimensions_info(ds)
    except Exception as e:
        err_console.print(f"[yellow]Warning:[/yellow] could not fetch dimension info: {e}")
        dim_df = None

    from .base import get_provider as _get_provider
    _provider_cfg = _get_provider()
    _page_url_tpl = _provider_cfg.get("dataflow_page_url")
    _page_url = _page_url_tpl.format(dataflow_id=ds["df_id"]) if _page_url_tpl else None

    if _output_mode != "table":
        dims = []
        if dim_df is not None and not dim_df.is_empty():
            dims = [
                {
                    "dimension_id": r["dimension_id"],
                    "position": r["position"],
                    "codelist_id": r["codelist_id"] or None,
                    "description": r.get("description") or None,
                }
                for r in dim_df.iter_rows(named=True)
            ]
        data = {
            "df_id": ds["df_id"],
            "version": ds["version"],
            "df_description": ds["df_description"],
            "df_structure_id": ds["df_structure_id"],
            "dimensions": dims,
        }
        if _page_url:
            data["page_url"] = _page_url
        _emit(data)
        return

    meta = (
        f"ID:          {ds['df_id']}\n"
        f"Version:     {ds['version']}\n"
        f"Description: {ds['df_description']}\n"
        f"Structure:   {ds['df_structure_id']}"
    )
    if _page_url:
        meta += f"\nPage:        {_page_url}"
    console.print(Panel(meta, title="Dataset Info", expand=False))

    if dim_df is None or dim_df.is_empty():
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
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
    grep: Optional[str] = typer.Option(None, "--grep", help="Filter results by regex (matches id or name, case-insensitive)"),
):
    """Show available values for a dimension.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx values NAMA_10_GDP FREQ
      opensdmx values DCIS_POPRES1 ITTER107 --provider istat
      opensdmx values WEO INDICATOR --provider imf --grep "growth|change"
      opensdmx values DSD_NAMAIN10@DF_TABLE1_EXPENDITURE_GROWTH UNIT_MEASURE --provider oecd --grep "percent"
    """
    _apply_provider(provider)
    import re

    from . import get_dimension_values, load_dataset
    try:
        with _status_ctx("[dim]Loading...[/dim]"):
            ds = load_dataset(dataset_id)
            val_df = get_dimension_values(ds, dim)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if val_df.is_empty():
        err_console.print(f"[yellow]No values found for dimension:[/yellow] {dim}")
        raise typer.Exit(1)

    if grep:
        pattern = re.compile(grep, re.IGNORECASE)
        mask = [
            bool(pattern.search(str(r["id"] or "")) or pattern.search(str(r["name"] or "")))
            for r in val_df.iter_rows(named=True)
        ]
        val_df = val_df.filter(mask)

    if _output_mode != "table":
        rows = [{"id": r["id"] or "", "name": r["name"] or ""} for r in val_df.iter_rows(named=True)]
        _emit(rows, df=val_df)
        return

    table = Table(title=f"{dataset_id} / {dim}", show_lines=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name")

    for row in val_df.iter_rows(named=True):
        table.add_row(row["id"] or "", row["name"] or "")

    console.print(table)


@app.command()
def constraints(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    dimension: Optional[str] = typer.Argument(None, help="Dimension ID (optional); if omitted shows all dimensions"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
    grep: Optional[str] = typer.Option(None, "--grep", help="Filter results by regex (matches id or name, case-insensitive); only applies with DIMENSION"),
):
    """Show constrained (actually present) values for a dataflow's dimensions.

    Without DIMENSION: shows all dimensions with their count and a short sample.
    With DIMENSION: shows the full list of codes present in the dataflow for that
    dimension, enriched with human-readable labels from the codelist.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx constraints NAMA_10_GDP
      opensdmx constraints NAMA_10_GDP FREQ
      opensdmx constraints DCIS_POPRES1 ITTER107 --provider istat
      opensdmx constraints WEO INDICATOR --provider imf --grep "growth|change"
      opensdmx constraints UNE_RT_M AGE --grep "Y25"
    """
    _apply_provider(provider)
    import re

    import polars as pl

    from . import load_dataset
    from .discovery import ConstraintsUnavailable, get_available_values, get_dimension_values
    from .db_cache import get_cached_available_constraints

    try:
        with _status_ctx("[dim]Loading dataset...[/dim]"):
            ds = load_dataset(dataset_id)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    provider_cfg = get_provider()
    if provider_cfg.get("agency_id") == "IT1" and get_cached_available_constraints(dataset_id) is None:
        err_console.print(
            "[yellow]⚠ ISTAT: first constraints call may take 30–120 s. "
            "Results will be cached for 7 days.[/yellow]"
        )

    try:
        with _status_ctx("[dim]Fetching constraints...[/dim]"):
            avail = get_available_values(ds)
    except ConstraintsUnavailable:
        err_console.print(
            f"[yellow]⚠ Constraints not available for [bold]{dataset_id}[/bold] "
            f"(dataflow is hidden or not yet public).[/yellow]\n"
            f"Data is still accessible:  opensdmx get {dataset_id} ..."
        )
        raise typer.Exit(0)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not avail:
        err_console.print(
            "[red]Error:[/red] No constrained values returned. "
            "This provider may not support the availableconstraint endpoint."
        )
        raise typer.Exit(1)

    if dimension is None:
        # Summary mode: one row per dimension
        if _output_mode != "table":
            data = {
                dim_id: {"n_values": len(df["id"]), "codes": df["id"].to_list()}
                for dim_id, df in avail.items()
            }
            _emit(data)
            return

        table = Table(title=f"Constraints: {dataset_id}", show_lines=False)
        table.add_column("dimension_id", style="cyan", no_wrap=True)
        table.add_column("n_values", justify="right")
        table.add_column("sample")

        for dim_id, df in avail.items():
            codes = df["id"].to_list()
            table.add_row(dim_id, str(len(codes)), ", ".join(codes[:3]))

        console.print(table)
        return

    # Single-dimension mode
    valid_dims = list(ds["dimensions"].keys())
    dim_upper = {d.upper(): d for d in valid_dims}
    actual_dim = dim_upper.get(dimension.upper())
    if actual_dim is None:
        err_console.print(
            f"[red]Error:[/red] Dimension '{dimension}' not found.\n"
            f"Valid dimensions: {', '.join(valid_dims)}"
        )
        raise typer.Exit(1)

    if actual_dim not in avail:
        err_console.print(
            f"[yellow]No constrained values found for dimension:[/yellow] {actual_dim}"
        )
        raise typer.Exit(1)

    constrained_codes = avail[actual_dim]["id"].to_list()

    try:
        with _status_ctx("[dim]Fetching labels...[/dim]"):
            labels_df = get_dimension_values(ds, actual_dim)
    except (httpx.HTTPError, OSError, ValueError):  # labels are optional, fall back to empty
        labels_df = pl.DataFrame({"id": [], "name": []}, schema={"id": pl.Utf8, "name": pl.Utf8})

    constrained_df = pl.DataFrame({"id": constrained_codes})
    if not labels_df.is_empty():
        result_df = constrained_df.join(labels_df, on="id", how="left")
        result_df = result_df.with_columns(pl.col("name").fill_null(""))
    else:
        result_df = constrained_df.with_columns(pl.lit("").alias("name"))

    if grep:
        pattern = re.compile(grep, re.IGNORECASE)
        mask = [
            bool(pattern.search(str(r["id"] or "")) or pattern.search(str(r["name"] or "")))
            for r in result_df.iter_rows(named=True)
        ]
        result_df = result_df.filter(mask)

    if _output_mode != "table":
        rows = [{"id": r["id"] or "", "name": r["name"] or ""} for r in result_df.iter_rows(named=True)]
        _emit(rows, df=result_df)
        return

    table = Table(title=f"{dataset_id} / {actual_dim} (constrained)", show_lines=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name")

    for row in result_df.iter_rows(named=True):
        table.add_row(row["id"] or "", row["name"] or "—")

    console.print(table)


@app.command()
def embed(
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Build semantic embeddings cache for the dataset catalog.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx embed
      opensdmx embed --provider istat
    """
    _apply_provider(provider)
    from .embed import build_embeddings
    try:
        build_embeddings(progress=True)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def providers():
    """List built-in SDMX providers (alias, name, description).

    These are curated examples — opensdmx works with any SDMX 2.1 REST endpoint.
    Use --provider <URL> to connect to any provider not listed here.

    Examples:

      opensdmx providers
      opensdmx search unemployment --provider ecb
    """
    from .base import PROVIDERS

    def _cap(cfg: dict, key: str) -> str:
        val = cfg.get(key)
        if val is True:
            return "[green]✓[/green]"
        if val is False:
            return "[red]✗[/red]"
        return "[dim]?[/dim]"

    if _output_mode != "table":
        data = [
            {
                "alias": alias,
                "name": cfg.get("name", ""),
                "description": cfg.get("description", ""),
                "agency_id": cfg.get("agency_id", ""),
                "constraints_supported": cfg.get("constraints_supported"),
                "last_n_supported": cfg.get("last_n_supported"),
                "categories_supported": cfg.get("categories_supported"),
            }
            for alias, cfg in PROVIDERS.items()
        ]
        _emit(data)
        return

    console.print(
        "\n[dim]The providers below are curated examples. "
        "opensdmx works with any SDMX 2.1 REST endpoint — "
        "use [/dim][cyan]--provider <URL>[/cyan][dim] to connect to any unlisted provider.[/dim]\n"
    )

    table = Table(show_lines=True)
    table.add_column("alias", style="cyan", no_wrap=True)
    table.add_column("name", no_wrap=True)
    table.add_column("description")
    table.add_column("agency", style="dim", no_wrap=True)
    table.add_column("constraints", justify="center", no_wrap=True)
    table.add_column("last_n", justify="center", no_wrap=True)
    table.add_column("categories", justify="center", no_wrap=True)

    for alias, cfg in PROVIDERS.items():
        table.add_row(
            alias,
            cfg.get("name", ""),
            cfg.get("description", ""),
            cfg.get("agency_id", ""),
            _cap(cfg, "constraints_supported"),
            _cap(cfg, "last_n_supported"),
            _cap(cfg, "categories_supported"),
        )

    console.print(table)


@app.command()
def tree(
    scheme: Optional[str] = typer.Option(None, "--scheme", "-s", help="Render the tree for a specific scheme_id. If omitted, lists all schemes with dataflow counts."),
    depth: Optional[int] = typer.Option(None, "--depth", "-d", help="Limit tree nesting depth (1 = only top-level)."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Browse the thematic tree of dataflows (categoryscheme + categorisation).

    Without --scheme: lists all schemes with their dataflow counts.
    With --scheme: renders an ASCII tree of that scheme's categories.

    Not all providers expose categories. Use `opensdmx providers` to check.
    In table mode output is an ASCII tree; in -o json|csv a flat table.

    Examples:

      opensdmx tree --provider istat
      opensdmx tree --scheme Z1000AGR --provider istat
      opensdmx tree --scheme Z1000AGR --depth 2 --provider istat
      opensdmx tree --scheme t_economy --provider eurostat
    """
    _apply_provider(provider)

    from .categories import CategoriesNotSupported, load_categories

    try:
        with _status_ctx("[dim]Loading category tree...[/dim]"):
            categories_df, categorisation_df = load_categories()
    except CategoriesNotSupported as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if categories_df.is_empty():
        err_console.print("[yellow]No categories returned by the provider.[/yellow]")
        raise typer.Exit(0)

    import polars as pl

    df_counts = (
        categorisation_df.group_by(["scheme_id", "cat_path"])
        .agg(pl.len().alias("n_df"))
    )

    if scheme is None:
        scheme_counts = (
            categorisation_df.group_by("scheme_id")
            .agg(pl.len().alias("n_df"))
        )
        schemes = (
            categories_df.select(["scheme_id", "scheme_name"])
            .unique()
            .join(scheme_counts, on="scheme_id", how="left")
            .with_columns(pl.col("n_df").fill_null(0))
            .sort("scheme_id")
        )

        if _output_mode != "table":
            rows = [
                {"scheme_id": r["scheme_id"], "scheme_name": r["scheme_name"] or "", "n_df": int(r["n_df"])}
                for r in schemes.iter_rows(named=True)
            ]
            _emit(rows, df=schemes)
            return

        table = Table(title="Category schemes", show_lines=False)
        table.add_column("scheme_id", style="cyan", no_wrap=True)
        table.add_column("scheme_name")
        table.add_column("n_df", justify="right")
        for r in schemes.iter_rows(named=True):
            table.add_row(r["scheme_id"], r["scheme_name"] or "", str(r["n_df"]))
        console.print(table)
        return

    scheme_rows = categories_df.filter(pl.col("scheme_id") == scheme)
    if scheme_rows.is_empty():
        err_console.print(f"[red]Error:[/red] scheme not found: {scheme}")
        raise typer.Exit(1)

    if depth is not None:
        scheme_rows = scheme_rows.filter(pl.col("depth") <= depth)

    scheme_rows = scheme_rows.join(df_counts, on=["scheme_id", "cat_path"], how="left").with_columns(
        pl.col("n_df").fill_null(0)
    )

    if _output_mode != "table":
        rows = [
            {
                "scheme_id": r["scheme_id"],
                "cat_id": r["cat_id"],
                "cat_path": r["cat_path"],
                "cat_name": r["cat_name"] or "",
                "parent_path": r["parent_path"] or "",
                "depth": int(r["depth"]),
                "n_df": int(r["n_df"]),
            }
            for r in scheme_rows.iter_rows(named=True)
        ]
        _emit(rows, df=scheme_rows)
        return

    scheme_name = scheme_rows.select("scheme_name").row(0)[0] or scheme
    console.print(f"[bold]{scheme_name}[/bold] [dim]({scheme})[/dim]")

    children: dict[str, list[dict]] = {}
    for r in scheme_rows.iter_rows(named=True):
        children.setdefault(r["parent_path"] or "", []).append(r)
    for kids in children.values():
        kids.sort(key=lambda x: x["cat_name"] or x["cat_id"])

    def render(parent_path: str, prefix: str) -> None:
        kids = children.get(parent_path, [])
        for i, node in enumerate(kids):
            last = (i == len(kids) - 1)
            branch = "└── " if last else "├── "
            count_str = f" [dim]({node['n_df']} df)[/dim]" if node["n_df"] else ""
            label = node["cat_name"] or node["cat_id"]
            console.print(f"{prefix}{branch}{label} [dim][{node['cat_id']}][/dim]{count_str}")
            next_prefix = prefix + ("    " if last else "│   ")
            render(node["cat_path"], next_prefix)

    render("", "")


@app.command()
def siblings(
    dataset_id: str = typer.Argument(..., help="Dataflow ID to locate in the thematic tree"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Show dataflow siblings — other dataflows in the same category.

    Given a dataflow ID, look up its categories and list all dataflows
    sharing each category. Useful to discover related datasets that a pure
    text search would miss (e.g. "Fertilizzanti" contains 7 dataflow variants
    but only 1 contains the word "agricoltura" in its description).

    A dataflow can belong to multiple categories: one group per membership.

    Examples:

      opensdmx siblings 104_466_DF_DCSP_FERTILIZZANTI_2 --provider istat
      opensdmx siblings NAMA_10_GDP --provider eurostat
    """
    _apply_provider(provider)

    from .categories import CategoriesNotSupported, siblings_of

    try:
        with _status_ctx("[dim]Loading category tree...[/dim]"):
            groups = siblings_of(dataset_id)
    except CategoriesNotSupported as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not groups:
        err_console.print(
            f"[yellow]Dataflow {dataset_id} is not categorized (or not found).[/yellow]"
        )
        raise typer.Exit(0)

    if _output_mode != "table":
        _emit(groups)
        return

    for g in groups:
        header = f"{g['scheme_name']} > {g['cat_name'] or g['cat_path']}"
        subtitle = f"scheme={g['scheme_id']}  cat_path={g['cat_path']}  siblings={len(g['siblings'])}"
        console.print(f"\n[bold]{header}[/bold]  [dim]({subtitle})[/dim]")
        table = Table(show_lines=False)
        table.add_column("", style="green", no_wrap=True)
        table.add_column("df_id", style="cyan", no_wrap=True)
        table.add_column("df_description")
        for s in g["siblings"]:
            marker = "→" if s["is_target"] else ""
            table.add_row(marker, s["df_id"], s["df_description"])
        console.print(table)


_LARGE_DATASET_THRESHOLD = 5000


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def get(
    ctx: typer.Context,
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file (.csv/.parquet/.json)"),
    query_file: Optional[Path] = typer.Option(None, "--query-file", help="Save query as YAML file for later reuse"),
    start_period: Optional[str] = typer.Option(None, "--start-period", help="Start period (e.g. 2020, 2020-Q1, 2020-01)"),
    end_period: Optional[str] = typer.Option(None, "--end-period", help="End period (e.g. 2023, 2023-Q4, 2023-12)"),
    last_n: Optional[int] = typer.Option(None, "--last-n", help="Return only last N observations per series"),
    first_n: Optional[int] = typer.Option(None, "--first-n", help="Return only first N observations per series"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip large-dataset confirmation prompt"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Get data for a dataset. Extra --DIM VALUE pairs are used as filters.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx get NAMA_10_GDP
      opensdmx get NAMA_10_GDP --FREQ A --GEO IT --out data.csv
      opensdmx get NAMA_10_GDP --start-period 2010 --end-period 2023 --out data.parquet
      opensdmx get DCIS_POPRES1 --ITTER107 IT --provider istat
      opensdmx get TIPSUN20 --sex T --age Y15-74 --out data.csv --query-file unemployment.yaml
    """
    _apply_provider(provider)
    from . import get_data, load_dataset, set_filters

    filters = _parse_extra_filters(ctx)

    try:
        import warnings as _warnings
        with console.status("[dim]Loading dataset...[/dim]"):
            ds = load_dataset(dataset_id)
            if filters:
                with _warnings.catch_warnings(record=True) as _caught:
                    _warnings.simplefilter("always")
                    ds = set_filters(ds, **filters)
                for _w in _caught:
                    err_console.print(f"[yellow]Warning:[/yellow] {_w.message}")

        # Probe for large datasets when no last_n/first_n limit is set.
        # Skip if provider does not support lastNObservations (probe would fetch all data).
        from .base import get_provider as _get_provider
        _probe_supported = "lastNObservations" not in _get_provider().get("unsupported_params", [])
        if not last_n and not first_n and not yes and _probe_supported:
            try:
                with console.status("[dim]Checking dataset size...[/dim]"):
                    probe = get_data(ds, last_n_observations=1)
                n_series = len(probe)
                if n_series > _LARGE_DATASET_THRESHOLD:
                    err_console.print(
                        f"[yellow]Warning:[/yellow] this dataset has ~{n_series:,} series (no filters set).\n"
                        f"Download may be large. Use [cyan]--last-n N[/cyan] to limit, or [cyan]--yes[/cyan] to proceed."
                    )
                    raise typer.Exit(1)
            except httpx.HTTPStatusError:
                pass  # let the real request fail with a proper error

        with console.status("[dim]Fetching data...[/dim]"):
            df = get_data(ds, start_period=start_period, end_period=end_period,
                          last_n_observations=last_n, first_n_observations=first_n)
    except httpx.HTTPStatusError as e:
        err_console.print(f"[red]HTTP {e.response.status_code}:[/red] {e.request.url}")
        if e.response.status_code in (400, 404):
            err_console.print("[yellow]Hint:[/yellow] check filter values with: opensdmx constraints <dataset_id>")
        raise typer.Exit(1)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if out is None:
        sys.stdout.write(df.write_csv())
    else:
        suffix = out.suffix.lower()
        if suffix == ".parquet":
            df.write_parquet(out)
        elif suffix == ".json":
            df.write_ndjson(out)
        elif suffix == ".csv":
            df.write_csv(out)
        else:
            err_console.print(f"[red]Error:[/red] unsupported output format '{suffix}'. Supported: .csv, .parquet, .json")
            raise typer.Exit(1)
        console.print(f"[green]Saved:[/green] {out}")

    if query_file is not None:
        import yaml
        from .utils import build_query_dict
        query_dict = build_query_dict(
            ds=ds, filters=filters,
            start_period=start_period, end_period=end_period,
            last_n=last_n, first_n=first_n, provider=provider,
        )
        with open(query_file, "w") as fh:
            yaml.dump(query_dict, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
        console.print(f"[green]Query saved:[/green] {query_file}")


@app.command()
def run(
    query_file: Path = typer.Argument(..., help="YAML query file (created with --query-file)"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file (.csv/.parquet/.json) — default: stdout"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Run a query from a YAML file saved with --query-file.

    Examples:

      opensdmx run unemployment.yaml
      opensdmx run unemployment.yaml --out results.csv
      opensdmx run query.yaml --out results.parquet
    """
    import yaml
    from . import get_data, load_dataset, set_filters

    if not query_file.exists():
        err_console.print(f"[red]Error:[/red] file not found: {query_file}")
        raise typer.Exit(1)

    try:
        with open(query_file) as fh:
            q = yaml.safe_load(fh)
    except Exception as e:
        err_console.print(f"[red]Error reading YAML:[/red] {e}")
        raise typer.Exit(1)

    # Provider resolution: CLI flag > alias (if known) > URL + agency_id > env/default
    if provider:
        _apply_provider(provider)
    else:
        from .base import PROVIDERS, set_provider
        alias = q.get("provider")
        if alias and alias in PROVIDERS:
            set_provider(alias)
        elif q.get("provider_url"):
            set_provider(q["provider_url"], agency_id=q.get("agency_id") or None)
        else:
            _apply_provider(None)

    dataset_id = q.get("dataset")
    if not dataset_id:
        err_console.print("[red]Error:[/red] 'dataset' field missing in query file")
        raise typer.Exit(1)

    filters = {dim: info["value"] for dim, info in (q.get("filters") or {}).items()}
    start_period = q.get("start_period")
    end_period = q.get("end_period")
    last_n = q.get("last_n")
    first_n = q.get("first_n")

    try:
        import warnings as _warnings
        with console.status("[dim]Loading dataset...[/dim]"):
            ds = load_dataset(dataset_id)
            if filters:
                with _warnings.catch_warnings(record=True) as _caught:
                    _warnings.simplefilter("always")
                    ds = set_filters(ds, **filters)
                for _w in _caught:
                    err_console.print(f"[yellow]Warning:[/yellow] {_w.message}")

        with console.status("[dim]Fetching data...[/dim]"):
            df = get_data(ds, start_period=start_period, end_period=end_period,
                          last_n_observations=last_n, first_n_observations=first_n)
    except httpx.HTTPStatusError as e:
        err_console.print(f"[red]HTTP {e.response.status_code}:[/red] {e.request.url}")
        raise typer.Exit(1)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if out is None:
        sys.stdout.write(df.write_csv())
    else:
        suffix = out.suffix.lower()
        if suffix == ".parquet":
            df.write_parquet(out)
        elif suffix == ".json":
            df.write_ndjson(out)
        elif suffix == ".csv":
            df.write_csv(out)
        else:
            err_console.print(f"[red]Error:[/red] unsupported format '{suffix}'. Supported: .csv, .parquet, .json")
            raise typer.Exit(1)
        console.print(f"[green]Saved:[/green] {out}")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def plot(
    ctx: typer.Context,
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    x: str = typer.Option("TIME_PERIOD", "--x", "--time", help="Column for X axis (default: TIME_PERIOD)"),
    y: str = typer.Option("OBS_VALUE", "--y", help="Column for Y axis"),
    color: Optional[str] = typer.Option(None, "--color", help="Column for color grouping"),
    geom: str = typer.Option("line", "--geom", help="Chart type: line, bar, barh, point, scatter, heatmap"),
    title: Optional[str] = typer.Option(None, "--title", help="Chart title (default: dataset description)"),
    xlabel: Optional[str] = typer.Option(None, "--xlabel", help="X axis label (default: column name)"),
    ylabel: Optional[str] = typer.Option(None, "--ylabel", help="Y axis label (default: column name)"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file (.png/.pdf/.svg) — default: <dataset_id>.png"),
    width: float = typer.Option(10.0, "--width", help="Chart width in inches"),
    height: float = typer.Option(5.0, "--height", help="Chart height in inches"),
    facet: Optional[str] = typer.Option(None, "--facet", help="Column for facet_wrap (small multiples)"),
    ncol: Optional[int] = typer.Option(None, "--ncol", help="Number of columns in facet grid (default: auto)"),
    rotate_x: Optional[int] = typer.Option(None, "--rotate-x", help="Rotate x-axis labels by N degrees (e.g. 45 or 90)"),
    x_all: bool = typer.Option(False, "--x-all", help="Show all x-axis tick labels (useful for discrete axes with few categories)"),
    colors: Optional[str] = typer.Option(None, "--colors", help="Comma-separated hex colors for fill/color scale (e.g. '#E69F00,#56B4E9,#009E73')"),
    plot_theme: Optional[str] = typer.Option(None, "--theme", help="Plot theme: minimal (default), bw, classic, 538, tufte, void, dark, light, gray, xkcd"),
    start_period: Optional[str] = typer.Option(None, "--start-period", help="Start period (e.g. 2020, 2020-Q1, 2020-01)"),
    end_period: Optional[str] = typer.Option(None, "--end-period", help="End period (e.g. 2023, 2023-Q4, 2023-12)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Plot data as a chart (line, bar, barh, point, heatmap).

    INPUT can be a dataflow ID (fetches from SDMX) or a local file
    (.csv, .tsv, .parquet). Extra --DIM VALUE pairs are used as filters
    when fetching from SDMX.

    Examples:

      opensdmx plot une_rt_m --freq M --geo IT --color geo
      opensdmx plot /tmp/data.csv --color geo --title "Road deaths"
      opensdmx plot /tmp/ranking.csv --geom barh --x geo --title "Rate by country"
      opensdmx plot /tmp/data.csv --geom bar --x year --color geo
      opensdmx plot /tmp/data.csv --color sex --facet age --ncol 2
      opensdmx plot /tmp/data.csv --geom bar --color tipo --rotate-x 45
      opensdmx plot /tmp/data.csv --color cat --colors '#E69F00,#56B4E9,#009E73'
      opensdmx plot /tmp/data.csv --color sex --facet age --ncol 2 --theme tufte
      opensdmx plot /tmp/data.csv --x quarter --y value --rotate-x 45 --x-all
      opensdmx plot /tmp/data.csv --geom heatmap --x year --color geo --theme 538
    """
    import matplotlib
    matplotlib.use("Agg")
    from plotnine import aes, coord_flip, element_text, facet_wrap, geom_col, geom_line, geom_point, geom_tile, ggplot, labs, scale_x_date, theme
    import plotnine.themes as _themes

    _THEME_MAP = {
        "minimal": _themes.theme_minimal,
        "bw": _themes.theme_bw,
        "classic": _themes.theme_classic,
        "538": _themes.theme_538,
        "tufte": _themes.theme_tufte,
        "void": _themes.theme_void,
        "dark": _themes.theme_dark,
        "light": _themes.theme_light,
        "gray": _themes.theme_gray,
        "grey": _themes.theme_gray,
    }

    theme_name = plot_theme or "minimal"
    use_xkcd = theme_name == "xkcd"
    if not use_xkcd and theme_name not in _THEME_MAP:
        err_console.print(f"[red]Error:[/red] unknown --theme '{theme_name}'. Use: {', '.join(k for k in _THEME_MAP if k != 'grey')}, xkcd")
        raise typer.Exit(1)
    selected_theme = _THEME_MAP["minimal"] if use_xkcd else _THEME_MAP[theme_name]

    import polars as pl

    # Detect file input vs dataflow ID
    input_path = Path(dataset_id)
    ds_description = dataset_id
    if input_path.suffix.lower() in (".csv", ".tsv", ".parquet") and input_path.exists():
        try:
            if input_path.suffix.lower() == ".parquet":
                df = pl.read_parquet(input_path)
            else:
                separator = "\t" if input_path.suffix.lower() == ".tsv" else ","
                # For barh: x is the numeric value, y is the category string — override y as Utf8.
                # For all other geoms: x is the category/time axis — override x as Utf8.
                str_col = y if geom == "barh" else x
                df = pl.read_csv(input_path, separator=separator, infer_schema_length=10000, schema_overrides={str_col: pl.Utf8})
            ds_description = input_path.stem
        except Exception as e:
            err_console.print(f"[red]Error reading file:[/red] {e}")
            raise typer.Exit(1)
    else:
        _apply_provider(provider)
        from . import get_data, load_dataset, set_filters

        filters = _parse_extra_filters(ctx)

        try:
            ds = load_dataset(dataset_id)
            if filters:
                ds = set_filters(ds, **filters)
            df = get_data(ds, start_period=start_period, end_period=end_period)
            ds_description = ds["df_description"]
        except httpx.HTTPStatusError as e:
            err_console.print(f"[red]HTTP {e.response.status_code}:[/red] {e.request.url}")
            if e.response.status_code in (400, 404):
                err_console.print("[yellow]Hint:[/yellow] check filter values with: opensdmx constraints <dataset_id>")
            raise typer.Exit(1)
        except Exception as e:
            err_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    missing = [col for col in (x, y) if col not in df.columns]
    if facet and facet not in df.columns:
        missing.append(facet)
    if missing:
        err_console.print(f"[red]Error:[/red] column(s) not found in data: {', '.join(f'{chr(39)}{c}{chr(39)}' for c in missing)}")
        err_console.print(f"Available columns: {', '.join(df.columns)}")
        raise typer.Exit(1)

    # For barh: x is the numeric value column; for all other geoms: y is the numeric value column.
    value_col = x if geom == "barh" else y
    df = df.with_columns(pl.col(value_col).cast(pl.Float64, strict=False))
    if df[x].dtype == pl.Utf8 and not x_all:
        from .retrieval import parse_time_period
        parsed = parse_time_period(df[x])
        if parsed.drop_nulls().len() > 0:
            df = df.with_columns(parsed.alias(x))
    pdf = df.to_pandas()

    if geom == "scatter":
        geom = "point"
    if geom not in ("line", "bar", "barh", "point", "heatmap"):
        err_console.print(f"[red]Error:[/red] unknown --geom '{geom}'. Use: line, bar, barh, point, scatter, heatmap")
        raise typer.Exit(1)

    if geom == "heatmap":
        import pandas as pd
        if not color:
            err_console.print("[red]Error:[/red] --geom heatmap requires --color to specify the row variable")
            raise typer.Exit(1)
        if pd.api.types.is_numeric_dtype(pdf[x]):
            pdf[x] = pdf[x].astype(str)
        elif pd.api.types.is_datetime64_any_dtype(pdf[x]):
            pdf[x] = pdf[x].dt.year.astype(str)
        aes_mapping = aes(x=x, y=color, fill=y)
        p = ggplot(pdf, aes_mapping) + geom_tile()
        p = p + labs(
            title=title or ds_description,
            x=xlabel or x,
            y=ylabel or color,
            fill=y,
        ) + selected_theme()
    elif geom in ("bar", "barh"):
        import pandas as pd

        # For bar (vertical): x is the category axis — convert to string to avoid misinterpretation.
        # For barh (horizontal): x is the numeric value axis — leave it as-is.
        if geom == "bar":
            if pd.api.types.is_numeric_dtype(pdf[x]):
                pdf[x] = pdf[x].astype(str)
            elif pd.api.types.is_datetime64_any_dtype(pdf[x]):
                pdf[x] = pdf[x].dt.year.astype(str)

        # Sort categories by value for readable bar charts
        if geom == "barh":
            # For barh: --x is the numeric value, --y is the category.
            # geom_col + coord_flip needs aes(x=category, y=value), so swap.
            order = pdf.groupby(y)[x].sum().sort_values().index.tolist()
            pdf[y] = pd.Categorical(pdf[y], categories=order, ordered=True)
            if color:
                aes_mapping = aes(x=y, y=x, fill=color)
            else:
                aes_mapping = aes(x=y, y=x)
            p = ggplot(pdf, aes_mapping) + geom_col() + coord_flip()
            # After coord_flip: labs(x) appears on vertical axis, labs(y) on horizontal.
            # User's --y (category) should label the vertical axis; --x (value) the horizontal.
            p = p + labs(
                title=title or ds_description,
                x=ylabel or y,
                y=xlabel or x,
            )
        else:
            if color:
                aes_mapping = aes(x=x, y=y, fill=color)
            else:
                aes_mapping = aes(x=x, y=y)
            p = ggplot(pdf, aes_mapping) + geom_col()
            p = p + labs(
                title=title or ds_description,
                x=xlabel or x,
                y=ylabel or y,
            )
        p = p + selected_theme()
    else:
        if x_all and color:
            aes_mapping = aes(x=x, y=y, color=color, group=color)
        elif x_all:
            aes_mapping = aes(x=x, y=y, group=1)
        elif color:
            aes_mapping = aes(x=x, y=y, color=color)
        else:
            aes_mapping = aes(x=x, y=y)
        p = ggplot(pdf, aes_mapping)
        if geom == "point":
            p = p + geom_point(size=2)
        else:
            p = p + geom_line(size=1) + geom_point(size=1.5)
        p = p + labs(
            title=title or ds_description,
            x=xlabel or x,
            y=ylabel or y,
        ) + selected_theme()
        if hasattr(pdf[x], "dt"):
            p = p + scale_x_date(date_breaks="2 years", date_labels="%Y")

    if facet:
        p = p + facet_wrap(facet, ncol=ncol)

    if rotate_x is not None:
        p = p + theme(axis_text_x=element_text(angle=rotate_x, hjust=1))

    if x_all:
        from plotnine import scale_x_discrete
        all_values = pdf[x].unique().tolist()
        try:
            all_values = sorted(all_values)
        except TypeError:
            pass
        p = p + scale_x_discrete(limits=all_values)

    if colors:
        from plotnine import scale_fill_manual, scale_color_manual
        palette = [c.strip() for c in colors.split(",")]
        p = p + scale_fill_manual(values=palette) + scale_color_manual(values=palette)

    if out is None:
        import re
        safe_name = re.sub(r"[^\w\-]", "_", ds_description.lower()).strip("_")
        out = Path(f"{safe_name}.png")
    import matplotlib.pyplot as plt
    if use_xkcd:
        with plt.xkcd():
            p.save(str(out), dpi=150, width=width, height=height)
    else:
        p.save(str(out), dpi=150, width=width, height=height)
    console.print(f"[green]Saved:[/green] {out}")


@app.command(hidden=True)
def guide(
    query: Optional[str] = typer.Argument(None, help="Goal in natural language"),
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Dataset ID to use directly (skip interactive selection)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: auto-confirm all prompts and download data.csv"),
    out: Path = typer.Option(Path("data.csv"), "--out", help="Output file when --yes is set"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Guided dataset discovery: semantic search + AI multi-turn conversation for filters.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx guide "unemployment Italy"
      opensdmx guide "PIL Italia" --dataset NAMA_10_GDP --yes
      opensdmx guide "popolazione" --provider istat --yes --out pop.csv
    """
    _apply_provider(provider)
    from .guide import run_guide
    run_guide(query=query, dataset=dataset, yes=yes, out=out)


@app.command()
def blacklist(
    remove: Optional[list[str]] = typer.Option(None, "--remove", help="Dataset ID to remove from blacklist (repeatable)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """List and manage datasets marked as unavailable.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx blacklist
      opensdmx blacklist --remove NAMA_10_GDP
      opensdmx blacklist --remove NAMA_10_GDP --remove STS_INPR_M
    """
    _apply_provider(provider)
    from .db_cache import delete_invalid_dataset, list_invalid_datasets

    # Non-interactive remove via --remove flag
    if remove:
        for df_id in remove:
            if delete_invalid_dataset(df_id):
                console.print(f"[green]Removed:[/green] {df_id}")
            else:
                err_console.print(f"[yellow]Not found in blacklist:[/yellow] {df_id}")
        return

    entries = list_invalid_datasets()
    if not entries:
        console.print("[green]No datasets in the blacklist.[/green]")
        return

    table = Table(title="Blacklisted datasets", show_lines=False)
    table.add_column("df_id", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Added on", style="dim", no_wrap=True)

    import datetime
    for e in entries:
        date_str = datetime.datetime.fromtimestamp(e["marked_at"]).strftime("%Y-%m-%d %H:%M")
        table.add_row(e["df_id"], e["description"] or "", date_str)

    console.print(table)

    try:
        import questionary
    except ImportError:
        err_console.print(
            "[red]Error:[/red] questionary not installed.\n"
            "Run: pip install opensdmx[guide]"
        )
        raise typer.Exit(1)

    choices = [
        questionary.Choice(
            title=f"{e['df_id']}  {e['description'] or ''}",
            value=e["df_id"],
        )
        for e in entries
    ]
    to_remove = questionary.checkbox(
        "Select datasets to remove from blacklist:",
        choices=choices,
    ).ask()

    if not to_remove:
        console.print("[dim]No changes.[/dim]")
        return

    for df_id in to_remove:
        delete_invalid_dataset(df_id)
        console.print(f"[green]Removed:[/green] {df_id}")


def main():
    app()
