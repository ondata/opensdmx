"""CLI for opensdmx — SDMX 2.1 REST API client."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_HELP_FLAGS = {"--help", "-h"}

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .base import get_base_url, get_provider

app = typer.Typer(help="opensdmx — SDMX 2.1 REST API CLI")
console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version
        console.print(version("opensdmx"))
        raise typer.Exit()

_PROVIDER_HELP = "Provider name ('eurostat', 'istat') or custom base URL"


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
    """Call set_provider if a provider option was given."""
    if provider:
        from .base import set_provider
        set_provider(provider)


def _check_api_reachable() -> None:
    """Do a lightweight GET check on the active provider's base URL."""
    from .base import _rate_limit_file
    if _rate_limit_file().exists():
        return
    try:
        with httpx.Client(timeout=5.0) as client:
            client.get(get_base_url())
    except Exception:
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
) -> None:
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
    n: int = typer.Option(10, "--n", help="Number of results (semantic mode only)"),
    no_expand: bool = typer.Option(False, "--no-expand", help="Disable query expansion (semantic mode only)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show expanded query (semantic mode only)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Search datasets by keyword (or semantically with --semantic).

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx search unemployment
      opensdmx search --semantic disoccupazione --n 5
      opensdmx search population --provider istat
    """
    _apply_provider(provider)

    if semantic:
        from .embed import semantic_search
        try:
            df = semantic_search(keyword, n=n, expand=not no_expand, verbose=verbose)
        except FileNotFoundError:
            err_console.print(
                "[red]Error:[/red] Embeddings cache not found.\n"
                "Build it first:  opensdmx embed"
            )
            raise typer.Exit(1)
        except Exception as e:
            err_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        table = Table(title=f"Semantic search: {keyword}", show_lines=False)
        table.add_column("df_id", style="cyan", no_wrap=True)
        table.add_column("df_description")
        table.add_column("score", style="dim")

        for row in df.iter_rows(named=True):
            table.add_row(row["df_id"], row["df_description"] or "", f"{row['score']:.3f}")

        console.print(table)
        return

    from . import search_dataset
    try:
        with console.status("[dim]Searching...[/dim]"):
            df = search_dataset(keyword)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if df.is_empty():
        err_console.print(f"[yellow]No datasets found for:[/yellow] {keyword}")
        raise typer.Exit(0)

    table = Table(title=f"Search: {keyword}", show_lines=False)
    table.add_column("df_id", style="cyan", no_wrap=True)
    table.add_column("df_description")

    for row in df.iter_rows(named=True):
        table.add_row(row["df_id"], row["df_description"] or "")

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
        with console.status("[dim]Loading dataset...[/dim]"):
            ds = load_dataset(dataset_id)
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
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Show available values for a dimension.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx values NAMA_10_GDP FREQ
      opensdmx values DCIS_POPRES1 ITTER107 --provider istat
    """
    _apply_provider(provider)
    from . import get_dimension_values, load_dataset
    try:
        with console.status("[dim]Loading...[/dim]"):
            ds = load_dataset(dataset_id)
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


@app.command()
def constraints(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    dimension: Optional[str] = typer.Argument(None, help="Dimension ID (optional); if omitted shows all dimensions"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
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
    """
    _apply_provider(provider)
    import polars as pl

    from . import load_dataset
    from .discovery import get_available_values, get_dimension_values

    try:
        with console.status("[dim]Loading dataset...[/dim]"):
            ds = load_dataset(dataset_id)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        with console.status("[dim]Fetching constraints...[/dim]"):
            avail = get_available_values(ds)
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
        with console.status("[dim]Fetching labels...[/dim]"):
            labels_df = get_dimension_values(ds, actual_dim)
    except Exception:
        labels_df = pl.DataFrame({"id": [], "name": []}, schema={"id": pl.Utf8, "name": pl.Utf8})

    constrained_df = pl.DataFrame({"id": constrained_codes})
    if not labels_df.is_empty():
        result_df = constrained_df.join(labels_df, on="id", how="left")
        result_df = result_df.with_columns(pl.col("name").fill_null("—"))
    else:
        result_df = constrained_df.with_columns(pl.lit("—").alias("name"))

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


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def get(
    ctx: typer.Context,
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file (.csv/.parquet/.json)"),
    start_period: Optional[str] = typer.Option(None, "--start-period", help="Start period (e.g. 2020, 2020-Q1, 2020-01)"),
    end_period: Optional[str] = typer.Option(None, "--end-period", help="End period (e.g. 2023, 2023-Q4, 2023-12)"),
    last_n: Optional[int] = typer.Option(None, "--last-n", help="Return only last N observations per series"),
    first_n: Optional[int] = typer.Option(None, "--first-n", help="Return only first N observations per series"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Get data for a dataset. Extra --DIM VALUE pairs are used as filters.

    Default provider: eurostat. Use --provider to switch.

    Examples:

      opensdmx get NAMA_10_GDP
      opensdmx get NAMA_10_GDP --FREQ A --GEO IT --out data.csv
      opensdmx get NAMA_10_GDP --start-period 2010 --end-period 2023 --out data.parquet
      opensdmx get DCIS_POPRES1 --ITTER107 IT --provider istat
    """
    _apply_provider(provider)
    from . import get_data, load_dataset, set_filters

    filters = _parse_extra_filters(ctx)

    try:
        with console.status("[dim]Fetching data...[/dim]"):
            ds = load_dataset(dataset_id)
            if filters:
                ds = set_filters(ds, **filters)
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
        else:
            df.write_csv(out)
        console.print(f"[green]Saved:[/green] {out}")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def plot(
    ctx: typer.Context,
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    x: str = typer.Option("TIME_PERIOD", "--x", help="Column for X axis"),
    y: str = typer.Option("OBS_VALUE", "--y", help="Column for Y axis"),
    color: Optional[str] = typer.Option(None, "--color", help="Column for color grouping"),
    title: Optional[str] = typer.Option(None, "--title", help="Chart title (default: dataset description)"),
    xlabel: Optional[str] = typer.Option(None, "--xlabel", help="X axis label (default: column name)"),
    ylabel: Optional[str] = typer.Option(None, "--ylabel", help="Y axis label (default: column name)"),
    out: Path = typer.Option(Path("chart.png"), "--out", help="Output file (.png/.pdf/.svg)"),
    width: float = typer.Option(10.0, "--width", help="Chart width in inches"),
    height: float = typer.Option(5.0, "--height", help="Chart height in inches"),
    start_period: Optional[str] = typer.Option(None, "--start-period", help="Start period (e.g. 2020, 2020-Q1, 2020-01)"),
    end_period: Optional[str] = typer.Option(None, "--end-period", help="End period (e.g. 2023, 2023-Q4, 2023-12)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help=_PROVIDER_HELP),
):
    """Plot data for a dataset as a line chart. Extra --DIM VALUE pairs are used as filters."""
    _apply_provider(provider)
    from plotnine import aes, geom_line, geom_point, ggplot, labs, scale_x_date, theme_minimal

    import polars as pl

    from . import get_data, load_dataset, set_filters

    filters = _parse_extra_filters(ctx)

    try:
        ds = load_dataset(dataset_id)
        if filters:
            ds = set_filters(ds, **filters)
        df = get_data(ds, start_period=start_period, end_period=end_period)
    except httpx.HTTPStatusError as e:
        err_console.print(f"[red]HTTP {e.response.status_code}:[/red] {e.request.url}")
        if e.response.status_code in (400, 404):
            err_console.print("[yellow]Hint:[/yellow] check filter values with: opensdmx constraints <dataset_id>")
        raise typer.Exit(1)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if x not in df.columns or y not in df.columns:
        err_console.print(f"[red]Error:[/red] columns '{x}' or '{y}' not found in data.")
        err_console.print(f"Available columns: {', '.join(df.columns)}")
        raise typer.Exit(1)

    df = df.with_columns(pl.col(y).cast(pl.Float64, strict=False))
    pdf = df.to_pandas()

    aes_mapping = aes(x=x, y=y, color=color) if color else aes(x=x, y=y)
    p = (
        ggplot(pdf, aes_mapping)
        + geom_line(size=1)
        + geom_point(size=1.5)
        + labs(
            title=title or ds["df_description"],
            x=xlabel or x,
            y=ylabel or y,
        )
        + theme_minimal()
    )

    if hasattr(pdf[x], "dt"):
        p = p + scale_x_date(date_breaks="2 years", date_labels="%Y")

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
    import questionary

    from .ai import ChangeDataset, guide_session
    from .base import get_agency_id, get_base_url
    from .discovery import load_dataset, set_filters
    from .embed import semantic_search
    from .utils import make_url_key

    # Step 1: get query
    if not query:
        if yes:
            err_console.print("[red]Error:[/red] QUERY argument required when using --yes.")
            raise typer.Exit(1)
        query = questionary.text("What do you want to analyze? (any language):").ask()
        if not query:
            raise typer.Exit(0)

    import httpx as _httpx

    page = 0
    page_size = 10
    df_results = None
    _reuse_ds = False
    _failed_context = ""
    ds = None

    # If --dataset given, load it directly and skip interactive selection
    if dataset:
        console.print(f"\n[cyan]Loading dataset[/cyan] [bold]{dataset}[/bold]...")
        try:
            ds = load_dataset(dataset)
        except Exception as e:
            err_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        _reuse_ds = True

    while True:

        if not _reuse_ds:
            selected_id = None
            while True:
                if df_results is None:
                    try:
                        df_results = semantic_search(query, n=100)
                    except FileNotFoundError:
                        err_console.print(
                            "[red]Error:[/red] Embeddings cache not found.\n"
                            "Build it first:  opensdmx embed"
                        )
                        raise typer.Exit(1)

                slice_ = df_results.slice(page * page_size, page_size)
                if slice_.is_empty():
                    page = max(0, page - 1)
                    continue

                total = len(df_results)
                choices = [
                    questionary.Choice(
                        title=(
                            f"{row['df_id']:<40} "
                            f"{row['df_description'] or ''}"
                            + (f"  [{row['df_structure_id']}]" if row.get('df_structure_id') else "")
                            + f"  ({row['score']:.3f})"
                        ),
                        value=row["df_id"],
                    )
                    for row in slice_.iter_rows(named=True)
                ]
                if page > 0:
                    choices.insert(0, questionary.Choice(title="← Previous 10", value="__prev__"))
                if (page + 1) * page_size < total:
                    shown_end = min((page + 1) * page_size, total)
                    choices.append(questionary.Choice(
                        title=f"→ Next 10  ({page * page_size + 1}–{shown_end} of {total})",
                        value="__next__",
                    ))
                choices.append(questionary.Choice(title="✕ Cancel", value="__cancel__"))

                answer = questionary.select(
                    f"Select a dataset  (page {page + 1}):",
                    choices=choices,
                    style=questionary.Style([("highlighted", "bold underline")]),
                ).ask()

                if answer is None or answer == "__cancel__":
                    raise typer.Exit(0)
                elif answer == "__next__":
                    page += 1
                elif answer == "__prev__":
                    page -= 1
                else:
                    selected_id = answer
                    break

            console.print(f"\n[cyan]Loading dataset[/cyan] [bold]{selected_id}[/bold]...")
            try:
                ds = load_dataset(selected_id)
            except Exception as e:
                err_console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1)

            console.print(Panel(
                f"ID:          {ds['df_id']}\n"
                f"Description: {ds['df_description']}\n"
                f"Structure:   {ds['df_structure_id']}\n"
                f"Dimensions:  {', '.join(ds['dimensions'].keys())}",
                title="Dataset",
                expand=False,
            ))

            if not yes:
                confirm = questionary.select(
                    "Continue with this dataset?",
                    choices=[
                        questionary.Choice("Yes, continue", value="yes"),
                        questionary.Choice("No, go back to selection", value="back"),
                        questionary.Choice("Exit", value="no"),
                    ],
                ).ask()

                if confirm is None or confirm == "no":
                    raise typer.Exit(0)
                if confirm == "back":
                    continue

            from .db_cache import save_invalid_dataset

            _check_url = f"{get_base_url()}/dataflow/{get_agency_id()}/{ds['df_id']}"
            _available = True
            try:
                _resp = _httpx.get(_check_url, timeout=10.0)
                if _resp.status_code >= 400:
                    _available = False
            except Exception:
                _available = False

            if not _available:
                console.print(
                    f"\n[yellow]⚠ Dataflow [bold]{ds['df_id']}[/bold] "
                    "is not available via API. It will be excluded from future searches.[/yellow]"
                )
                save_invalid_dataset(ds["df_id"], ds.get("df_description"))
                if df_results is not None:
                    df_results = df_results.filter(df_results["df_id"] != ds["df_id"])
                if yes:
                    err_console.print("[red]Error:[/red] Selected dataset is not available via API.")
                    raise typer.Exit(1)
                continue

        else:
            _reuse_ds = False

        assert ds is not None  # always set: either via --dataset or the selection loop above

        try:
            result = guide_session(ds, query, failed_context=_failed_context)
            _failed_context = ""
        except SystemExit:
            raise typer.Exit(0)
        except ChangeDataset:
            _reuse_ds = False
            _failed_context = ""
            page = 0
            df_results = None
            if yes:
                err_console.print("[red]Error:[/red] AI requested dataset change; not supported in --yes mode.")
                raise typer.Exit(1)
            console.print("[dim]Torno alla selezione dataset...[/dim]\n")
            continue
        except Exception as e:
            import traceback
            err_console.print(f"[red]Error:[/red] {e}")
            err_console.print(traceback.format_exc())
            raise typer.Exit(1)

        from .discovery import get_available_values

        filters = result["filters"]
        start_period = result.get("start_period") or ""
        end_period = result.get("end_period") or ""
        active = {}
        for k, v in filters.items():
            codes = v if isinstance(v, list) else ([v] if v else [])
            codes = [c for c in codes if c]
            if codes:
                active[k] = codes[0] if len(codes) == 1 else codes

        try:
            avail = {dim_id: set(df["id"].to_list()) for dim_id, df in get_available_values(ds).items()}
        except Exception:
            avail = {}

        if avail:
            invalid = []
            for dim_id, codes in active.items():
                codes_list = codes if isinstance(codes, list) else [codes]
                if dim_id in avail:
                    bad = [c for c in codes_list if c not in avail[dim_id]]
                    if bad:
                        invalid.append((dim_id, bad, sorted(avail[dim_id])))
            if invalid:
                console.print("\n[yellow]⚠ Codes not present in dataset:[/yellow]")
                correction_notes = []
                for dim_id, bad_codes, valid_codes in invalid:
                    console.print(f"  {dim_id} = [red]{', '.join(bad_codes)}[/red]")
                    console.print(f"  Available values: [green]{', '.join(valid_codes[:20])}[/green]")
                    correction_notes.append(
                        f"{dim_id}: codes {bad_codes} do not exist, use one of: {valid_codes[:20]}"
                    )
                if yes:
                    # Auto-ask AI to fix
                    notes = "; ".join(correction_notes)
                    query = (
                        f"{query}\n\n"
                        f"CORRECTION NEEDED: {notes}. "
                        "Use ONLY the listed available codes."
                    )
                    _reuse_ds = True
                    continue
                confirm_invalid = questionary.select(
                    "What would you like to do?",
                    choices=[
                        questionary.Choice("Ask AI to fix the codes", value="ai_fix"),
                        questionary.Choice("Use these filters anyway", value="yes"),
                        questionary.Choice("Exit", value="no"),
                    ],
                ).ask()
                if confirm_invalid is None or confirm_invalid == "no":
                    raise typer.Exit(0)
                if confirm_invalid == "ai_fix":
                    notes = "; ".join(correction_notes)
                    query = (
                        f"{query}\n\n"
                        f"CORRECTION NEEDED: {notes}. "
                        "Use ONLY the listed available codes."
                    )
                    _reuse_ds = True
                    continue

        try:
            ds = set_filters(ds, **active)
        except Exception as e:
            err_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        key = make_url_key(ds["filters"])
        base, agency, version = get_base_url(), get_agency_id(), ds["version"]
        url = f"{base}/data/{agency},{ds['df_id']},{version}/{key}?format=csv"

        _sample_ok = True
        try:
            from .retrieval import get_data as _get_data
            _sample_df = _get_data(ds, last_n_observations=1)
            if _sample_df.is_empty():
                _sample_ok = False
            elif not set(ds["dimensions"].keys()).intersection(_sample_df.columns):
                _sample_ok = False  # error response parsed as CSV
        except Exception:
            _sample_ok = False

        if not _sample_ok:
            console.print(
                "\n[yellow]⚠ Filter combination does not return data.[/yellow] "
                "Some values may not be available for the chosen area or period."
            )
            if yes:
                _failed_context = ", ".join(f"{k}={v}" for k, v in active.items())
                _reuse_ds = True
                continue
            confirm_combo = questionary.select(
                "What would you like to do?",
                choices=[
                    questionary.Choice("Ask AI to verify and propose an alternative", value="ai_fix"),
                    questionary.Choice("Show the URL anyway", value="yes"),
                    questionary.Choice("Exit", value="no"),
                ],
            ).ask()
            if confirm_combo is None or confirm_combo == "no":
                raise typer.Exit(0)
            if confirm_combo == "ai_fix":
                _failed_context = ", ".join(f"{k}={v}" for k, v in active.items())
                _reuse_ds = True
                continue

        filter_summary = "\n".join(f"  {k} = {v}" for k, v in active.items()) or "  (none)"

        cli_args = " ".join(
            f"--{k} {'+'.join(v) if isinstance(v, list) else v}"
            for k, v in active.items()
        )
        period_args = ""
        if start_period:
            period_args += f" --start-period {start_period}"
        if end_period:
            period_args += f" --end-period {end_period}"
        cli_cmd = f"opensdmx get {ds['df_id']} {cli_args}{period_args} --out data.csv".strip()

        console.print(Panel(
            f"[bold]Dataset:[/bold]\n  {ds['df_id']}  {ds['df_description']}\n\n"
            f"[bold]Filters:[/bold]\n{filter_summary}\n\n"
            f"[bold]Reason:[/bold]\n  {result['reasoning']}\n\n"
            f"[bold]URL:[/bold]\n{url}\n\n"
            f"[bold]CLI:[/bold]\n{cli_cmd}",
            title="Result",
            expand=False,
        ))

        # --yes mode: auto-download and exit
        if yes:
            console.print(f"[cyan]Downloading data...[/cyan]")
            try:
                from . import get_data as _get_data
                _df = _get_data(ds)
                _df.write_csv(str(out))
                console.print(f"[green]Saved:[/green] {out.resolve()}")
            except Exception as e:
                err_console.print(f"[red]Download error:[/red] {e}")
                raise typer.Exit(1)
            raise typer.Exit(0)

        while True:
            post_action = questionary.select(
                "What would you like to do?",
                choices=[
                    questionary.Choice("Download file to current directory", value="download"),
                    questionary.Choice("Modify filters (back to AI with same dataset)", value="modify"),
                    questionary.Choice("New search (new dataset)", value="new"),
                    questionary.Choice("Exit", value="exit"),
                ],
            ).ask()

            if post_action is None or post_action == "exit":
                raise typer.Exit(0)

            elif post_action == "download":
                out_file = Path("data.csv")
                if out_file.exists():
                    overwrite = questionary.confirm(
                        f"'{out_file.resolve()}' already exists. Overwrite?"
                    ).ask()
                    if not overwrite:
                        console.print("[dim]Download cancelled.[/dim]")
                        continue
                console.print("[cyan]Downloading data...[/cyan]")
                try:
                    from . import get_data as _get_data
                    _df = _get_data(ds)
                    _df.write_csv(str(out_file))
                    console.print(f"[green]Saved:[/green] {out_file.resolve()}")
                except Exception as e:
                    err_console.print(f"[red]Download error:[/red] {e}")

            elif post_action == "modify":
                mod_input = questionary.text(
                    "What do you want to change? (e.g. geographic area, period, filter values...):"
                ).ask()
                if mod_input:
                    current_filter_str = ", ".join(f"{k}={v}" for k, v in active.items())
                    period_str = f", period={start_period}–{end_period}" if start_period or end_period else ""
                    query = f"{query}\n\nCURRENT WORKING FILTERS: {current_filter_str}{period_str}\nREQUESTED CHANGE: {mod_input}"
                _reuse_ds = True
                break

            elif post_action == "new":
                df_results = None
                page = 0
                break


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
            delete_invalid_dataset(df_id)
            console.print(f"[green]Removed:[/green] {df_id}")
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

    import questionary
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
