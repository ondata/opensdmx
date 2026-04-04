"""Guided dataset discovery: semantic search + AI multi-turn conversation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

console = Console()
err_console = Console(stderr=True)


def run_guide(
    query: Optional[str],
    dataset: Optional[str],
    yes: bool,
    out: Path,
) -> None:
    """Core logic for the guide command."""
    try:
        import questionary
    except ImportError:
        err_console.print(
            "[red]Error:[/red] questionary not installed.\n"
            "Run: pip install opensdmx[guide]"
        )
        raise typer.Exit(1)

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
                _resp = httpx.get(_check_url, timeout=10.0)
                if _resp.status_code >= 400:
                    _available = False
            except (httpx.HTTPError, OSError):
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
            console.print("[dim]Returning to dataset selection...[/dim]\n")
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
        except (httpx.HTTPError, OSError, ValueError):  # constraints optional, fall back to no validation
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
                _sample_ok = False
        except (httpx.HTTPError, OSError, ValueError):  # sample optional, fall back to unknown
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

        if yes:
            console.print("[cyan]Downloading data...[/cyan]")
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
