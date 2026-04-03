"""AI-assisted filter selection — Python controls flow, AI produces structured JSON."""
from __future__ import annotations


class ChangeDataset(Exception):
    """Raised when the user wants to go back to dataset selection."""


def guide_session(ds: dict, objective: str, failed_context: str = "") -> dict:
    """Guide user to select filters for a dataset.

    Architecture: Python fetches constraints and validates combos.
    AI only translates natural language → structured filter JSON.
    Returns {'filters': dict, 'start_period': str, 'end_period': str, 'reasoning': str}.
    """
    import contextlib
    import io
    import warnings

    from chatlas import ChatGoogle
    from pydantic import BaseModel, Field
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.table import Table as _Table

    from .base import get_provider, set_rate_limit_context
    from .db_cache import (
        get_cached_available_constraints,
        get_cached_codelist_values,
        is_codelist_info_cached,
    )
    from .discovery import _get_dimension_description, get_available_values

    console = Console()
    dims = ds["dimensions"]
    dims_list = list(dims.keys())

    # ── Step 1: Fetch constraints (Python, not AI) ────────────────────────────
    _cached = get_cached_available_constraints(ds["df_id"])
    if _cached is None:
        console.print("[dim]Loading available values...[/dim]")
        set_rate_limit_context(f"Downloading available values for {ds['df_id']}")
    try:
        _avail = {dim_id: df["id"].to_list() for dim_id, df in get_available_values(ds).items()}
    except Exception as _e:
        _avail = {}
        console.print(f"[yellow]⚠ Available values not loaded: {_e}[/yellow]")
    set_rate_limit_context("")

    # ── Step 2: Build constraint context (codes + labels) for AI ─────────────
    dim_context_parts: list[str] = []
    _dim_table = _Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    _dim_table.add_column("Dimension", style="cyan", no_wrap=True)
    _dim_table.add_column("Description")
    _dim_table.add_column("Values", style="dim", justify="right")

    all_labels: dict[str, dict[str, str]] = {}  # dim_id → {code: label}

    for dim_id, dim_meta in dims.items():
        codelist_id = dim_meta.get("codelist_id")
        if codelist_id and not is_codelist_info_cached(codelist_id):
            set_rate_limit_context(f"Downloading info for dimension {dim_id}")
        description = _get_dimension_description(codelist_id) or dim_id
        set_rate_limit_context("")

        codes = sorted(str(v) for v in _avail.get(dim_id, []) if v is not None)
        n_vals = len(codes)
        _dim_table.add_row(dim_id, description, str(n_vals) if n_vals else "?")

        labels: dict[str, str] = {}
        if codelist_id:
            cached_vals = get_cached_codelist_values(codelist_id)
            if cached_vals:
                labels = {r["id"]: r["name"] for r in cached_vals}
        all_labels[dim_id] = labels

        code_lines = [f"  {c} = {labels[c]}" if c in labels else f"  {c}" for c in codes]
        dim_context_parts.append(
            f"Dimension {dim_id} ({description}, {n_vals} values available):\n"
            + "\n".join(code_lines)
        )

    # Show TIME_PERIOD range if available in constraints
    time_range_str = ""
    if "TIME_PERIOD" in _avail:
        _tp = sorted(str(v) for v in _avail["TIME_PERIOD"] if v is not None)
        if _tp:
            time_range_str = f"{_tp[0]} – {_tp[-1]}"

    console.print("\n[bold]Dataset dimensions:[/bold]")
    console.print(_dim_table)
    if time_range_str:
        console.print(f"[dim]Available period: {time_range_str}[/dim]")
    console.print()

    constraint_context = "\n\n".join(dim_context_parts)
    if time_range_str:
        constraint_context += f"\n\nTIME_PERIOD available range: {time_range_str}"
    provider_name = get_provider().get("agency_id", "SDMX")

    # ── Pydantic models ───────────────────────────────────────────────────────
    # Note: Gemini does not support dict with additionalProperties — use lists.
    class DimFilter(BaseModel):
        dim_id: str = Field(description="Dimension identifier e.g. 'geo'")
        codes: list[str] = Field(description="Selected codes. Empty list = no filter.")

    class ScenarioFilter(BaseModel):
        name: str = Field(description="Short scenario name")
        description: str = Field(description="One-line description in the user's language")
        filters: list[DimFilter] = Field(description="List of dimension filters")
        start_period: str = Field(default="", description="Suggested start year e.g. '2015'")
        end_period: str = Field(default="", description="Suggested end year e.g. '2023'")

    class ScenarioProposal(BaseModel):
        scenarios: list[ScenarioFilter]
        intro: str = Field(description="Brief intro message in user's language")

    class FilterUpdate(BaseModel):
        filters: list[DimFilter] = Field(description="Full updated filter set as list of DimFilter")
        start_period: str = Field(default="", description="Start year e.g. '2019'")
        end_period: str = Field(default="", description="End year e.g. '2023'")
        message: str = Field(description="What changed and current state, in the user's language")
        confirmed: bool = Field(
            default=False,
            description="True only if the user clearly confirms to proceed (ok, yes, sure, go ahead, perfect…)"
        )

    # ── Helper: list[DimFilter] → dict ───────────────────────────────────────
    def _to_dict(filters) -> dict[str, list[str]]:
        return {f.dim_id: f.codes for f in filters}

    # ── Python validation ─────────────────────────────────────────────────────
    def _validate(filters: dict[str, list[str]]) -> tuple[bool, str]:
        """Check codes are in constraints, then try a real HTTP fetch."""
        for dim_id, codes in filters.items():
            if not codes:
                continue
            available = {str(v) for v in _avail.get(dim_id, [])}
            if available:
                bad = [c for c in codes if c not in available]
                if bad:
                    sample = sorted(available)[:8]
                    return False, f"{dim_id}: {bad} not available. Valid examples: {sample}"
        # Use the same HTTP check as the CLI to avoid false positives from CSV parsing errors
        try:
            from .discovery import set_filters
            from .retrieval import get_data
            active = {k: (v[0] if len(v) == 1 else v) for k, v in filters.items() if v}
            test_ds = set_filters(ds, **active)
            df = get_data(test_ds, last_n_observations=1)
            if df.is_empty():
                return False, "No data for this filter combination."
            # Check response has expected dataset columns (not an XML error parsed as CSV)
            if not set(dims_list).intersection(df.columns):
                return False, f"Invalid response (columns: {list(df.columns)[:3]})"
            return True, ""
        except Exception as e:
            return False, str(e)

    # ── AI helper (structured output, history maintained) ─────────────────────
    chat = ChatGoogle(model="gemini-2.5-flash")

    def _ai_structured(msg: str, model_cls, spinner: str = "AI is processing..."):
        with console.status(f"[dim]{spinner}[/dim]"):
            with warnings.catch_warnings(), contextlib.redirect_stderr(io.StringIO()):
                warnings.simplefilter("ignore")
                return chat.chat_structured(msg, data_model=model_cls)

    # ── Base system context (injected in every AI call) ───────────────────────
    base_ctx = (
        f"You are a statistical data assistant for {provider_name}.\n"
        f"Dataset: {ds['df_id']} — {ds['df_description']}\n\n"
        f"AVAILABLE CODES (use ONLY these — never invent codes):\n{constraint_context}\n\n"
        "Rules:\n"
        "- Always reply in the user's language. Translate all descriptions.\n"
        "- Use ONLY the codes listed above.\n"
        "- TOTAL means 'statistical aggregate of all items' (one row summing everything). "
        "It does NOT mean 'all individual items'. "
        "When user wants one row PER country/item → use empty list [] (no filter = all individual values returned). "
        "When user wants the aggregate total → use TOTAL.\n"
        "- Max 3 codes per dimension for specific selections; for all individual values use empty list [].\n"
        "- Every scenario must have a meaningful start_period and end_period.\n"
        "- confirmed=True only when user clearly agrees to proceed."
    )

    # ── Step 3: AI proposes scenarios ─────────────────────────────────────────
    if failed_context:
        proposal_msg = (
            f"{base_ctx}\n\n"
            f"User objective: {objective}\n\n"
            f"PREVIOUS FILTERS FAILED (returned no data): {failed_context}\n"
            "Identify why they failed and propose corrected filter scenarios."
        )
    else:
        proposal_msg = (
            f"{base_ctx}\n\n"
            f"User objective: {objective}\n\n"
            "Propose 2-3 distinct filter scenarios for the user's objective. "
            "Each must have a meaningful time range."
        )

    proposal = _ai_structured(
        proposal_msg,
        ScenarioProposal,
        spinner="AI is analysing available data and preparing scenarios...",
    )

    # ── Step 4: Python validates each scenario ────────────────────────────────
    valid_scenarios: list[ScenarioFilter] = []
    with console.status("[dim]Validating scenarios...[/dim]"):
        for s in proposal.scenarios:  # type: ignore[union-attr]
            ok, _ = _validate(_to_dict(s.filters))
            if ok:
                valid_scenarios.append(s)

    if not valid_scenarios:
        console.print("[yellow]⚠ No valid scenario — trying minimal filters...[/yellow]")
        simple_dict = {
            dim_id: ["TOTAL"] if "TOTAL" in [str(v) for v in _avail.get(dim_id, [])] else []
            for dim_id in dims_list
        }
        ok, _ = _validate(simple_dict)
        if ok:
            valid_scenarios = [ScenarioFilter(
                name="Base",
                description="Minimal filters with total values",
                filters=[DimFilter(dim_id=k, codes=v) for k, v in simple_dict.items()],
                start_period="2015",
                end_period="2023",
            )]

    # ── Step 5: Display valid scenarios ──────────────────────────────────────
    def _fmt_scenario(s: ScenarioFilter, letter: str) -> str:
        lines = [f"**Scenario {letter}: {s.name}**", s.description, f"Period: {s.start_period}–{s.end_period}"]
        for df in s.filters:
            if df.codes:
                labels = all_labels.get(df.dim_id, {})
                code_str = ", ".join(f"{c} ({labels[c]})" if c in labels else c for c in df.codes)
                lines.append(f"- {df.dim_id}: {code_str}")
        return "\n".join(lines)

    intro = getattr(proposal, "intro", "") or ""  # type: ignore[union-attr]
    parts = [intro] if intro else []
    for i, s in enumerate(valid_scenarios):
        parts.append(_fmt_scenario(s, chr(65 + i)))
    if len(valid_scenarios) > 1:
        parts.append("\nWhich scenario do you prefer? Or would you like to change something?")
    else:
        parts.append("\nWould you like to proceed with this scenario or modify it?")

    display_text = "\n\n".join(parts)
    console.print("\n[bold cyan]AI:[/bold cyan]")
    console.print(Markdown(display_text))
    console.print("[dim](type 'exit' or 'change' to go back to dataset selection)[/dim]")
    console.print()

    # ── Step 6: Multi-turn loop (Python validates every update) ───────────────
    current_filters: dict[str, list[str]] = _to_dict(valid_scenarios[0].filters) if valid_scenarios else {}
    current_start = valid_scenarios[0].start_period if valid_scenarios else ""
    current_end = valid_scenarios[0].end_period if valid_scenarios else ""

    scenarios_summary = "\n".join(
        f"Scenario {chr(65+i)}: {s.name} — filters={_to_dict(s.filters)}, period={s.start_period}–{s.end_period}"
        for i, s in enumerate(valid_scenarios)
    )

    # Map letters to scenario index for direct selection
    _letter_map = {chr(65 + i): i for i in range(len(valid_scenarios))}
    _confirm_words = {"ok", "yes", "sure", "go", "proceed", "perfect", "confirm", "fine", "done"}
    _exit_words = {"exit", "quit", "back", "change"}

    for _ in range(20):
        try:
            user_input = input("Tu: ").strip()
        except (KeyboardInterrupt, EOFError):
            raise SystemExit(0)
        if not user_input:
            continue

        # Exit / change dataset
        _words_lower_raw = user_input.lower().split()
        if _exit_words & set(_words_lower_raw) or "change dataflow" in user_input.lower() or "change dataset" in user_input.lower():
            raise ChangeDataset()

        _word = user_input.strip().upper()
        _words_lower = user_input.lower().split()

        # Direct scenario selection (A/B/C) — use already-validated filters directly
        if _word in _letter_map:
            idx = _letter_map[_word]
            current_filters = _to_dict(valid_scenarios[idx].filters)
            current_start = valid_scenarios[idx].start_period
            current_end = valid_scenarios[idx].end_period
            console.print("\n[bold cyan]AI:[/bold cyan]")
            console.print(Markdown(
                f"You selected **Scenario {_word}: {valid_scenarios[idx].name}**.\n\n"
                f"Suggested period: {current_start}–{current_end}. OK or would you like to change it?\n\n"
                + _fmt_scenario(valid_scenarios[idx], _word)
            ))
            console.print()
            continue

        # Simple confirmation — break with current (already validated) filters
        if len(_words_lower) <= 3 and _confirm_words & set(_words_lower):
            break

        # Everything else → AI interprets and returns structured update
        update_msg = (
            f"{base_ctx}\n\n"
            f"Proposed scenarios:\n{scenarios_summary}\n\n"
            f"Current filters: {current_filters}\n"
            f"Current period: {current_start}–{current_end}\n\n"
            f"User says: '{user_input}'\n\n"
            "Return the updated full filter set. "
            "Keep dimensions not mentioned by the user unchanged from current filters. "
            "Set confirmed=False — confirmation is handled separately."
        )

        update: FilterUpdate = _ai_structured(  # type: ignore[assignment]
            update_msg, FilterUpdate, spinner="AI is processing your request..."
        )

        # Python validates
        upd_dict = _to_dict(update.filters)  # type: ignore[union-attr]
        ok, err = _validate(upd_dict)
        if not ok:
            fix_msg = (
                f"{base_ctx}\n\n"
                f"Proposed filters {upd_dict} are INVALID: {err}\n"
                f"Current valid filters: {current_filters}\n"
                "Fix only what is invalid and return a working filter set."
            )
            update = _ai_structured(fix_msg, FilterUpdate, spinner="Fixing filters...")  # type: ignore[assignment]
            upd_dict = _to_dict(update.filters)  # type: ignore[union-attr]
            ok, err = _validate(upd_dict)
            if not ok:
                console.print(f"\n[yellow]⚠ Could not find a valid combination: {err}[/yellow]")
                console.print(Markdown(update.message))  # type: ignore[union-attr]
                console.print()
                continue

        current_filters = upd_dict
        current_start = update.start_period or current_start  # type: ignore[union-attr]
        current_end = update.end_period or current_end  # type: ignore[union-attr]

        console.print("\n[bold cyan]AI:[/bold cyan]")
        console.print(Markdown(update.message))  # type: ignore[union-attr]
        console.print()

        if update.confirmed:  # type: ignore[union-attr]
            break

    return {
        "filters": current_filters,
        "start_period": current_start,
        "end_period": current_end,
        "reasoning": f"Interactive guide for: {objective}",
    }
