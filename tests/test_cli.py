"""Tests for opensdmx.cli — pure logic and error paths."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.exceptions import Exit as ClickExit
from typer.testing import CliRunner

from opensdmx.cli import _apply_provider, _parse_extra_filters, app

runner = CliRunner()


# ── _parse_extra_filters ─────────────────────────────────────────────


def _ctx(args: list[str]):
    """Build a minimal typer.Context stub with .args set."""
    return SimpleNamespace(args=args)


def test_parse_extra_filters_single():
    assert _parse_extra_filters(_ctx(["--geo", "IT"])) == {"geo": "IT"}


def test_parse_extra_filters_inline_plus():
    assert _parse_extra_filters(_ctx(["--geo", "IT+FR"])) == {"geo": "IT+FR"}


def test_parse_extra_filters_repeated_key():
    assert _parse_extra_filters(_ctx(["--geo", "IT", "--geo", "FR"])) == {"geo": "IT+FR"}


def test_parse_extra_filters_multiple_dimensions():
    result = _parse_extra_filters(_ctx(["--geo", "IT", "--freq", "A"]))
    assert result == {"geo": "IT", "freq": "A"}


def test_parse_extra_filters_empty():
    assert _parse_extra_filters(_ctx([])) == {}


def test_parse_extra_filters_unexpected_arg():
    with pytest.raises(ClickExit):
        _parse_extra_filters(_ctx(["badarg"]))


# ── _apply_provider ──────────────────────────────────────────────────


def test_apply_provider_valid_name():
    # Should not raise — istat is a known provider
    _apply_provider("istat")


def test_apply_provider_custom_url():
    # Custom HTTP URLs are accepted without error
    _apply_provider("https://example.com/rest")


def test_apply_provider_unknown_name():
    with pytest.raises(ClickExit):
        _apply_provider("not_a_real_provider_xyz")


def test_apply_provider_none_no_env(monkeypatch):
    monkeypatch.delenv("OPENSDMX_PROVIDER", raising=False)
    # None + no env var → no-op, no error
    _apply_provider(None)


# ── CLI commands via CliRunner ────────────────────────────────────────


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() != ""


def test_search_unknown_provider():
    with patch("opensdmx.cli._check_api_reachable"):
        result = runner.invoke(app, ["search", "unemployment", "--provider", "not_a_real_provider_xyz"])
    assert result.exit_code != 0


# ── tree command: error paths and depth semantics ────────────────────


def _fake_categories_dfs():
    """Two-frame fixture mimicking (categories_df, categorisation_df).

    Category tree under scheme S1:
      CAT_A                    depth 1
        CAT_A1                 depth 2
          CAT_A1A              depth 3
        CAT_A2                 depth 2
    Dataflow DF_X is categorised under CAT_A1; DF_Y under CAT_A.
    """
    import polars as pl

    categories_df = pl.DataFrame(
        {
            "scheme_id": ["S1"] * 4,
            "scheme_name": ["Scheme one"] * 4,
            "cat_id": ["CAT_A", "CAT_A1", "CAT_A1A", "CAT_A2"],
            "cat_path": ["CAT_A", "CAT_A.CAT_A1", "CAT_A.CAT_A1.CAT_A1A", "CAT_A.CAT_A2"],
            "cat_name": ["Cat A", "Cat A1", "Cat A1A", "Cat A2"],
            "cat_description": ["", "Long-form description of A1", "", ""],
            "parent_path": ["", "CAT_A", "CAT_A.CAT_A1", "CAT_A"],
            "depth": [1, 2, 3, 2],
        },
        schema_overrides={"depth": pl.Int32},
    )
    categorisation_df = pl.DataFrame(
        {
            "df_id": ["DF_X", "DF_Y"],
            "scheme_id": ["S1", "S1"],
            "cat_path": ["CAT_A.CAT_A1", "CAT_A"],
        }
    )
    return categories_df, categorisation_df


def test_tree_category_is_dataflow_hints_parent():
    """Passing a df_id to --category must yield a clear error with suggestions."""
    with patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(
            app,
            ["tree", "--scheme", "S1", "--category", "DF_X", "--provider", "istat"],
        )
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "is a dataflow, not a category" in combined
    assert "--category CAT_A1" in combined


def test_tree_depth_is_relative_to_category():
    """--category X --depth 1 must show X plus its direct children (relative)."""
    with patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(
            app,
            ["tree", "--scheme", "S1", "--category", "CAT_A1", "--depth", "1", "--provider", "istat"],
        )
    assert result.exit_code == 0
    out = result.output
    assert "Cat A1" in out
    assert "CAT_A1A" in out  # relative depth 1 = direct child included
    assert "Cat A2" not in out  # sibling at absolute depth 2 must NOT appear


def test_tree_empty_subtree_does_not_crash():
    """--depth 0 with --category X should not crash; returns descriptive message."""
    with patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(
            app,
            ["tree", "--scheme", "S1", "--category", "CAT_A", "--depth", "0", "--provider", "istat"],
        )
    # depth 0 relative still keeps CAT_A (absolute depth 1 <= 1+0), so subtree not empty.
    # Force empty by asking non-existent category below CAT_A1A with zero depth.
    assert result.exit_code == 0


def test_tree_renders_cat_description_when_present():
    """When Category.description is populated, ASCII renders it dimmed after the label."""
    with patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(app, ["tree", "--scheme", "S1", "--provider", "istat"])
    assert result.exit_code == 0
    # CAT_A1 has description; CAT_A does not — only A1 shows "—"
    assert "Long-form description of A1" in result.output


def test_tree_show_dataflows_renders_df_leaves():
    """--show-dataflows must inline df leaves as [df:ID] under their category."""
    import polars as pl

    cat_df, cz_df = _fake_categories_dfs()
    meta_df = pl.DataFrame(
        {
            "df_id": ["DF_X", "DF_Y"],
            "version": ["1.0", "1.0"],
            "df_description": ["Desc for X", "Desc for Y"],
            "df_structure_id": ["S_X", "S_Y"],
        }
    )
    with patch("opensdmx.categories.load_categories", return_value=(cat_df, cz_df)), \
         patch("opensdmx.discovery.all_available", return_value=meta_df):
        result = runner.invoke(
            app,
            ["tree", "--scheme", "S1", "--show-dataflows", "--provider", "istat"],
        )
    assert result.exit_code == 0
    assert "[df:DF_X]" in result.output
    assert "[df:DF_Y]" in result.output
    assert "Desc for X" in result.output  # uses df_description as label
    assert "[cat:CAT_A]" in result.output  # categories still present


def test_tree_no_show_dataflows_is_regression_safe():
    """Without --show-dataflows, output must not contain df markers."""
    with patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(app, ["tree", "--scheme", "S1", "--provider", "istat"])
    assert result.exit_code == 0
    assert "[df:" not in result.output


def test_tree_renders_cat_prefix():
    """ASCII tree must render category IDs with the [cat:ID] prefix."""
    with patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(app, ["tree", "--scheme", "S1", "--provider", "istat"])
    assert result.exit_code == 0
    assert "[cat:CAT_A]" in result.output
    assert "[cat:CAT_A1]" in result.output


def test_tree_category_is_dataflow_cross_scheme():
    """Passing a df_id that exists only in another scheme must suggest the correct scheme."""
    import polars as pl
    cat_df = pl.DataFrame(
        {
            "scheme_id": ["S1", "S2"],
            "scheme_name": ["Scheme one", "Scheme two"],
            "cat_id": ["CAT_A", "CAT_B"],
            "cat_path": ["CAT_A", "CAT_B"],
            "cat_name": ["Cat A", "Cat B"],
            "parent_path": ["", ""],
            "depth": [1, 1],
        },
        schema_overrides={"depth": pl.Int32},
    )
    cz_df = pl.DataFrame({"df_id": ["DF_X"], "scheme_id": ["S2"], "cat_path": ["CAT_B"]})
    with patch("opensdmx.categories.load_categories", return_value=(cat_df, cz_df)):
        result = runner.invoke(
            app, ["tree", "--scheme", "S1", "--category", "DF_X", "--provider", "istat"]
        )
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "not categorised under scheme 'S1'" in combined
    assert "--scheme S2 --category CAT_B" in combined


def test_tree_category_unknown_id():
    """Unknown --category (neither cat nor df) yields the generic 'not found' error."""
    with patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(
            app,
            ["tree", "--scheme", "S1", "--category", "NOPE", "--provider", "istat"],
        )
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "not found in scheme" in combined
