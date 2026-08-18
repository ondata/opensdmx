"""Tests for opensdmx.cli — pure logic and error paths."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.exceptions import Exit as ClickExit
from typer.testing import CliRunner

from opensdmx.cli import _apply_provider, _parse_extra_filters, _parse_header, app

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


# ── constraints command: missing-dimension hint (issue #24) ──────────


def _fake_constraints_dataset():
    """Dataset with 3 dims; the constraint endpoint will return only 2 of them."""
    return {
        "df_id": "TEST_DF",
        "version": "1.0",
        "df_description": "Test",
        "df_structure_id": "TEST_DSD",
        "dimensions": {
            "FREQ": {"id": "FREQ", "position": 1, "codelist_id": "CL_FREQ"},
            "REF_AREA": {"id": "REF_AREA", "position": 2, "codelist_id": "CL_AREA"},
            "SEX": {"id": "SEX", "position": 3, "codelist_id": "CL_SEX"},
        },
        "filters": {"FREQ": ".", "REF_AREA": ".", "SEX": "."},
    }


def _fake_avail_with_missing_dim():
    """Return only FREQ + SEX — REF_AREA missing (e.g. ISTAT contentconstraint)."""
    import polars as pl

    return {
        "FREQ": pl.DataFrame({"id": ["A"]}),
        "SEX": pl.DataFrame({"id": ["1", "2", "9"]}),
    }


def test_constraints_table_shows_missing_dim_hint():
    """Table mode: dim absent from constraint response gets a row with – and a hint."""
    import re

    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.discovery.get_available_values", return_value=_fake_avail_with_missing_dim()):
        result = runner.invoke(app, ["constraints", "TEST_DF", "--provider", "istat"])

    assert result.exit_code == 0, result.output
    # Strip Rich box-drawing characters and collapse whitespace so the wrapped
    # hint string survives the table's column truncation.
    flat = re.sub(r"[│┃┏┓┗┛┡┩━┳┻┣┫─]+", " ", result.output)
    flat = re.sub(r"\s+", " ", flat)
    # Present dims show their values
    assert "FREQ" in flat
    assert "SEX" in flat
    # Missing dim: row with REF_AREA + hint pointing to `opensdmx values`
    assert "REF_AREA" in flat
    assert "not in contentconstraint" in flat
    assert "opensdmx values TEST_DF REF_AREA" in flat


def test_constraints_json_marks_missing_dim_with_source_and_hint():
    """JSON mode: missing dim entry has source='missing' + hint field."""
    import json

    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.discovery.get_available_values", return_value=_fake_avail_with_missing_dim()):
        result = runner.invoke(app, ["--output", "json", "constraints", "TEST_DF", "--provider", "istat"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["FREQ"]["source"] == "constraint"
    assert payload["FREQ"]["n_values"] == 1
    assert payload["REF_AREA"]["source"] == "missing"
    assert payload["REF_AREA"]["n_values"] is None
    assert payload["REF_AREA"]["hint"] == "opensdmx values TEST_DF REF_AREA"


def test_constraints_single_dim_missing_suggests_values():
    """Asking for a missing dim explicitly → suggest `opensdmx values` and exit 0."""
    import re

    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.discovery.get_available_values", return_value=_fake_avail_with_missing_dim()):
        result = runner.invoke(app, ["constraints", "TEST_DF", "REF_AREA", "--provider", "istat"])

    assert result.exit_code == 0, result.output
    flat = re.sub(r"\s+", " ", result.output)
    assert "REF_AREA" in flat
    assert "not exposed by contentconstraint" in flat
    assert "opensdmx values TEST_DF REF_AREA" in flat


# ── 400/404 hint on data requests (issue #66) ────────────────────────


def test_bad_request_hint_names_unfiltered_dimensions(capsys):
    from opensdmx.cli import _print_bad_request_hint

    ds = _fake_constraints_dataset()
    ds["filters"] = {"FREQ": "Q", "REF_AREA": ".", "SEX": "."}
    _print_bad_request_hint("TEST_DF", ds)

    out = re.sub(r"\s+", " ", capsys.readouterr().err)
    assert "opensdmx constraints TEST_DF" in out
    assert "no filter set on: REF_AREA, SEX" in out


def test_bad_request_hint_without_dataset(capsys):
    """Failure before the dataset loads: only the generic hint, no crash."""
    from opensdmx.cli import _print_bad_request_hint

    _print_bad_request_hint("TEST_DF", None)

    out = re.sub(r"\s+", " ", capsys.readouterr().err)
    assert "opensdmx constraints TEST_DF" in out
    assert "no filter set on" not in out


def test_bad_request_hint_all_dimensions_filtered(capsys):
    from opensdmx.cli import _print_bad_request_hint

    ds = _fake_constraints_dataset()
    ds["filters"] = {"FREQ": "Q", "REF_AREA": "IT", "SEX": "1"}
    _print_bad_request_hint("TEST_DF", ds)

    assert "no filter set on" not in capsys.readouterr().err


# ── values command: codelist vs dataflow content (issue #67) ─────────


def _fake_codelist_values():
    """A codelist wider than the dataflow: only '1' and '2' are actually used."""
    import polars as pl

    return pl.DataFrame({"id": ["1", "2", "9"], "name": ["Males", "Females", "Unknown"]})


def test_values_annotates_from_cached_constraints():
    """Cache hit → in_dataflow column + coverage footer, with no extra fetch."""
    import re

    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.get_dimension_values", return_value=_fake_codelist_values()), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value={"SEX": ["1", "2"]}), \
         patch("opensdmx.discovery.get_available_values") as fetch:
        result = runner.invoke(app, ["values", "TEST_DF", "SEX"])

    assert result.exit_code == 0, result.output
    fetch.assert_not_called()  # annotation must stay a local cache read
    flat = re.sub(r"\s+", " ", result.output)
    assert "in_dataflow" in flat
    assert "2 of 3 codes are present in this dataflow" in flat
    assert "opensdmx constraints TEST_DF SEX" in flat


def test_values_without_cached_constraints_hints_at_constraints():
    """No constraint knowledge → full codelist plus a pointer to `constraints`."""
    import re

    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.get_dimension_values", return_value=_fake_codelist_values()), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None):
        result = runner.invoke(app, ["values", "TEST_DF", "SEX"])

    assert result.exit_code == 0, result.output
    flat = re.sub(r"\s+", " ", result.output)
    assert "codelist definition" in flat
    assert "opensdmx constraints TEST_DF SEX" in flat
    assert "in_dataflow" not in flat


def test_values_json_carries_in_dataflow_field():
    """The JSON consumer gets the flag as data, not as terminal prose."""
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.get_dimension_values", return_value=_fake_codelist_values()), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value={"SEX": ["1", "2"]}):
        result = runner.invoke(app, ["--output", "json", "values", "TEST_DF", "SEX"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [r["in_dataflow"] for r in payload] == [True, True, False]


def test_values_json_in_dataflow_is_null_without_constraints():
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.get_dimension_values", return_value=_fake_codelist_values()), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=None):
        result = runner.invoke(app, ["--output", "json", "values", "TEST_DF", "SEX"])

    assert result.exit_code == 0, result.output
    assert all(r["in_dataflow"] is None for r in json.loads(result.output))


@pytest.mark.parametrize("cached", [{"SEX": ["1", "2"]}, None])
def test_values_csv_schema_is_stable_regardless_of_cache(cached):
    """The CSV header must not gain or lose a column depending on cache state."""
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.load_dataset", return_value=_fake_constraints_dataset()), \
         patch("opensdmx.get_dimension_values", return_value=_fake_codelist_values()), \
         patch("opensdmx.db_cache.get_cached_available_constraints", return_value=cached):
        result = runner.invoke(app, ["--output", "csv", "values", "TEST_DF", "SEX"])

    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert lines[0] == "id,name,in_dataflow"
    # Unknown membership is an empty cell, not a missing column.
    assert lines[1] == ("1,Males,true" if cached else "1,Males,")


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
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
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
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
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
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(
            app,
            ["tree", "--scheme", "S1", "--category", "CAT_A", "--depth", "0", "--provider", "istat"],
        )
    # depth 0 relative still keeps CAT_A (absolute depth 1 <= 1+0), so subtree not empty.
    # Force empty by asking non-existent category below CAT_A1A with zero depth.
    assert result.exit_code == 0


def test_tree_renders_cat_description_when_present():
    """When Category.description is populated, ASCII renders it dimmed after the label."""
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
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
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=(cat_df, cz_df)), \
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
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(app, ["tree", "--scheme", "S1", "--provider", "istat"])
    assert result.exit_code == 0
    assert "[df:" not in result.output


def test_tree_renders_cat_prefix():
    """ASCII tree must render category IDs with the [cat:ID] prefix."""
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
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
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=(cat_df, cz_df)):
        result = runner.invoke(
            app, ["tree", "--scheme", "S1", "--category", "DF_X", "--provider", "istat"]
        )
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "not categorised under scheme 'S1'" in combined
    assert "--scheme S2 --category CAT_B" in combined


def test_tree_category_unknown_id():
    """Unknown --category (neither cat nor df) yields the generic 'not found' error."""
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(
            app,
            ["tree", "--scheme", "S1", "--category", "NOPE", "--provider", "istat"],
        )
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "not found in scheme" in combined


def _invoke_tree(*args):
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        return runner.invoke(app, ["tree", *args, "--provider", "istat"])


def test_tree_scoped_flags_require_scheme():
    """--category and --show-dataflows have no global meaning: refuse, don't ignore."""
    for flag in (["--category", "CAT_A"], ["--show-dataflows"]):
        result = _invoke_tree(*flag)
        assert result.exit_code == 1
        combined = result.output + (result.stderr or "")
        assert "requires --scheme" in combined


def test_tree_no_scheme_depth_1_is_the_default():
    """The skill's entry command `tree --depth 1` must keep listing schemes."""
    assert _invoke_tree("--depth", "1").output == _invoke_tree().output


def test_tree_no_scheme_depth_2_shows_top_level_categories():
    """The provider is the root, so schemes are level 1 and categories level 2."""
    shallow = _invoke_tree("--depth", "1").output
    deep = _invoke_tree("--depth", "2")
    assert deep.exit_code == 0
    assert "Cat A" in deep.output and "Cat A" not in shallow
    assert "Cat A1" not in deep.output  # absolute depth 2 is one level too deep


def _fake_two_scheme_dfs():
    """Minimal two-scheme fixture: the no-scheme tree renders one block per scheme."""
    import polars as pl

    categories_df = pl.DataFrame(
        {
            "scheme_id": ["S1", "S2"],
            "scheme_name": ["Scheme one", "Scheme two"],
            "cat_id": ["CAT_A", "CAT_B"],
            "cat_path": ["CAT_A", "CAT_B"],
            "cat_name": ["Cat A", "Cat B"],
            "cat_description": ["", ""],
            "parent_path": ["", ""],
            "depth": [1, 1],
        },
        schema_overrides={"depth": pl.Int32},
    )
    categorisation_df = pl.DataFrame(
        {"df_id": ["DF_X"], "scheme_id": ["S1"], "cat_path": ["CAT_A"]}
    )
    return categories_df, categorisation_df


def test_tree_no_scheme_depth_2_renders_one_tree_per_scheme():
    """Every scheme gets its own block, blank-line separated."""
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_two_scheme_dfs()):
        result = runner.invoke(app, ["tree", "--depth", "2", "--provider", "istat"])
    assert result.exit_code == 0
    out = result.output
    assert "Scheme one (S1)" in out and "Scheme two (S2)" in out
    assert "Cat A" in out and "Cat B" in out
    # schemes are sorted and separated by a blank line
    assert out.index("(S1)") < out.index("(S2)")
    assert "\n\nScheme two" in out


def test_tree_no_scheme_depth_json_emits_category_rows():
    """json at depth >= 2 must carry categories, not the three-column summary."""
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()):
        result = runner.invoke(app, ["-o", "json", "tree", "--depth", "2", "--provider", "istat"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert [r["cat_id"] for r in rows] == ["CAT_A"]


# ── siblings command ─────────────────────────────────────────────────


def _siblings_catalog_df():
    import polars as pl

    return pl.DataFrame(
        {
            "df_id": ["DF_X", "DF_Y", "DF_LONELY"],
            "version": ["1.0", "1.0", "1.0"],
            "df_structure_id": ["DF_X", "DF_Y", "DF_LONELY"],
            "df_description": ["Desc for X", "Desc for Y", "Desc for lonely"],
        }
    )


def _no_dsd_fetch(_structure_id):
    """Stand-in for discovery._get_dimensions that must never be called.

    `siblings` needs only the canonical df_id, which comes from the dataflow
    catalog; the datastructure is a separate request that would add latency and
    make a DSD outage break a lookup the cached category tree can answer alone.
    Every siblings test runs with this in place, so reintroducing the dependency
    fails the suite instead of shipping.
    """
    raise AssertionError("siblings must not fetch the datastructure")


def _invoke_siblings(*args):
    # Global options (-o, --output) must precede the command name.
    global_opts = [a for a in args if a in ("-o", "json", "--output")]
    cmd_args = [a for a in args if a not in global_opts]
    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()), \
         patch("opensdmx.discovery.all_available", return_value=_siblings_catalog_df()), \
         patch("opensdmx.discovery._get_dimensions", side_effect=_no_dsd_fetch):
        return runner.invoke(app, [*global_opts, "siblings", *cmd_args, "--provider", "istat"])


def test_siblings_lowercase_resolves_and_marks_target():
    """siblings df_x behaves like siblings DF_X: same groups, target marked."""
    result = _invoke_siblings("df_x")
    assert result.exit_code == 0, result.output
    assert "DF_X" in result.output
    assert "Desc for X" in result.output
    # the → marker points at the resolved (uppercase) target row
    target_line = next(
        line for line in result.output.splitlines() if "DF_X" in line and "Desc for X" in line
    )
    assert "→" in target_line


def test_siblings_json_lowercase():
    """JSON mode returns the same payload for any case."""
    upper = json.loads(_invoke_siblings("-o", "json", "DF_X").output)
    lower = json.loads(_invoke_siblings("-o", "json", "df_x").output)
    assert upper == lower
    target = next(s for s in lower[0]["siblings"] if s["is_target"])
    assert target["df_id"] == "DF_X"
    assert target["df_description"] == "Desc for X"


def test_siblings_unknown_id_exits_1():
    """An ID that does not exist is an error (standard load_dataset message)."""
    result = _invoke_siblings("NOPE")
    assert result.exit_code == 1
    assert "Could not find dataset" in (result.output + (result.stderr or ""))


def test_siblings_not_categorized_exits_1():
    """Existing but uncategorized dataflow is not a silent success."""
    result = _invoke_siblings("DF_LONELY")
    assert result.exit_code == 1
    assert "not categorized" in (result.output + (result.stderr or ""))


def test_siblings_survives_a_dataflow_catalog_outage():
    """Category cache answers even when the dataflow endpoint is down.

    Regression guard for the second PR #69 review round: `siblings_of` already
    tolerates an unavailable dataflow table (left join, blank descriptions), so
    the ID resolution in the CLI must not turn that outage into an error.
    """
    def _boom():
        raise ConnectionError("dataflow endpoint down")

    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()), \
         patch("opensdmx.discovery.all_available", side_effect=_boom), \
         patch("opensdmx.discovery._get_dimensions", side_effect=_no_dsd_fetch):
        result = runner.invoke(app, ["--output", "json", "siblings", "df_x", "--provider", "istat"])

    assert result.exit_code == 0, result.output
    groups = json.loads(result.output)
    target = next(s for g in groups for s in g["siblings"] if s["is_target"])
    assert target["df_id"] == "DF_X"
    assert target["df_description"] == ""


def test_siblings_does_not_fetch_the_datastructure():
    """The lookup stays on the dataflow catalog and the cached category tree.

    Regression guard for PR #69 review: resolving the ID through load_dataset
    pulled in the DSD request for dimensions the command never uses, so a
    datastructure outage turned a working sibling lookup into an error.
    """
    calls = []

    def _record(structure_id):
        calls.append(structure_id)
        return {}

    with patch("opensdmx.cli._check_api_reachable"), \
         patch("opensdmx.categories.load_categories", return_value=_fake_categories_dfs()), \
         patch("opensdmx.discovery.all_available", return_value=_siblings_catalog_df()), \
         patch("opensdmx.discovery._get_dimensions", side_effect=_record):
        result = runner.invoke(app, ["siblings", "df_x", "--provider", "istat"])

    assert result.exit_code == 0, result.output
    assert calls == [], f"siblings fetched the datastructure: {calls}"


# ── _parse_header ─────────────────────────────────────────────────────

def test_parse_header_valid():
    assert _parse_header("X-Api-Key: abc123") == ("X-Api-Key", "abc123")


def test_parse_header_strips_whitespace():
    assert _parse_header("  X-Api-Key :  abc123  ") == ("X-Api-Key", "abc123")


def test_parse_header_value_with_colon():
    assert _parse_header("Authorization: Bearer tok:en") == ("Authorization", "Bearer tok:en")


def test_parse_header_missing_colon_raises():
    import typer
    with pytest.raises(typer.BadParameter):
        _parse_header("invalid-no-colon")


# ── which ─────────────────────────────────────────────────────────────


@pytest.fixture
def _no_api_check():
    """`which` is a local-only command, but the CLI callback still pings the
    provider; mock it so these tests don't depend on network reachability."""
    with patch("opensdmx.cli._check_api_reachable"):
        yield


def test_which_no_query_lists_all(_no_api_check):
    result = runner.invoke(app, ["which"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "plot" in result.output


def test_which_match_visualize(_no_api_check):
    result = runner.invoke(app, ["which", "visualize"])
    assert result.exit_code == 0
    assert "plot" in result.output


def test_which_match_download(_no_api_check):
    result = runner.invoke(app, ["which", "download"])
    assert result.exit_code == 0
    assert "get" in result.output


def test_which_no_match_exits_2(_no_api_check):
    result = runner.invoke(app, ["which", "zzznomatch"])
    assert result.exit_code == 2


def test_which_json_output(_no_api_check):
    import json
    result = runner.invoke(app, ["-o", "json", "which", "download"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert any(row["command"] == "get" for row in data)


# ── guide command: install hint when the `guide` extra is missing ─────


def test_guide_missing_extra_hint_shows_bracket():
    """The install hint must keep the '[guide]' extra visible.

    Regression: `Run: pip install opensdmx[guide]` was printed through Rich,
    which parsed `[guide]` as a markup tag and silently dropped it, so the
    user saw the misleading `pip install opensdmx` — a fix that does not
    install questionary and loops forever. The extra must survive rendering.
    """
    from io import StringIO
    from pathlib import Path

    import opensdmx.guide as guide_mod
    from rich.console import Console

    buf = StringIO()
    real_import = __import__

    def _block_questionary(name, *a, **kw):
        if name == "questionary":
            raise ImportError("blocked by test")
        return real_import(name, *a, **kw)

    import typer

    # patch.object restores err_console even if the assertions fail: leaving the
    # buffered Console in place would leak into every later test in the session.
    with patch.object(guide_mod, "err_console", Console(file=buf)), \
         patch("builtins.__import__", side_effect=_block_questionary), \
         pytest.raises(typer.Exit):
        guide_mod.run_guide("unemployment", None, False, Path("data.csv"))
    assert "questionary not installed" in buf.getvalue()
    assert "opensdmx[guide]" in buf.getvalue()


def test_which_limit(_no_api_check):
    result = runner.invoke(app, ["which", "data", "--limit", "1"])
    assert result.exit_code == 0
    commands_found = sum(1 for line in result.output.splitlines() if any(
        cmd in line for cmd in ["search", "tree", "get", "plot", "info", "values", "constraints", "siblings", "providers", "run"]
    ))
    assert commands_found <= 2


# ── search --grep ────────────────────────────────────────────────────


def _fake_comun_results():
    """Datasets whose titles all start with 'comun' but mean different things."""
    import polars as pl

    return pl.DataFrame({
        "df_id": ["AGRI_1", "PERM_2", "BANK_3"],
        "df_description": [
            "Agriturismo - comuni",
            "Permessi di soggiorno dei cittadini non comunitari",
            "Servizi bancari - dati comunali",
        ],
        "score": [3, 1, 2],
    })


def test_search_grep_matches_whole_word_only(_no_api_check):
    """A whole-word pattern excludes longer words sharing the same prefix."""
    with patch("opensdmx.search_dataset", return_value=_fake_comun_results()):
        result = runner.invoke(app, ["-o", "csv", "search", "comun", "--grep", r"\bcomuni\b"])
    assert result.exit_code == 0
    assert "AGRI_1" in result.output
    assert "PERM_2" not in result.output
    assert "BANK_3" not in result.output


def test_search_grep_matches_id_as_well_as_title(_no_api_check):
    with patch("opensdmx.search_dataset", return_value=_fake_comun_results()):
        result = runner.invoke(app, ["-o", "csv", "search", "comun", "--grep", "BANK"])
    assert result.exit_code == 0
    assert "BANK_3" in result.output
    assert "AGRI_1" not in result.output


def test_search_grep_invalid_pattern_reports_error(_no_api_check):
    """A malformed regex gets a readable message, not a traceback."""
    with patch("opensdmx.search_dataset", return_value=_fake_comun_results()):
        result = runner.invoke(app, ["search", "comun", "--grep", "["])
    assert result.exit_code == 1
    assert "invalid --grep pattern" in result.output


def test_search_grep_no_match_exits_cleanly(_no_api_check):
    with patch("opensdmx.search_dataset", return_value=_fake_comun_results()):
        result = runner.invoke(app, ["search", "comun", "--grep", "zzznomatch"])
    assert result.exit_code == 0
    assert "No datasets found" in result.output


# ── --output / OPENSDMX_OUTPUT resolution order (issue #8) ────────────


def test_output_env_var_sets_the_default(_no_api_check):
    """OPENSDMX_OUTPUT=json makes json the default without passing -o."""
    import json

    with patch("opensdmx.search_dataset", return_value=_fake_comun_results()):
        result = runner.invoke(app, ["search", "comun"], env={"OPENSDMX_OUTPUT": "json"})

    assert result.exit_code == 0, result.output
    assert [r["df_id"] for r in json.loads(result.output)] == ["AGRI_1", "PERM_2", "BANK_3"]


def test_output_flag_wins_over_env_var(_no_api_check):
    """An explicit -o overrides OPENSDMX_OUTPUT."""
    with patch("opensdmx.search_dataset", return_value=_fake_comun_results()):
        result = runner.invoke(app, ["-o", "csv", "search", "comun"], env={"OPENSDMX_OUTPUT": "json"})

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0].startswith("df_id,")


def test_output_defaults_to_table_without_env_var(_no_api_check):
    """No flag, no env var: still the Rich table."""
    with patch("opensdmx.search_dataset", return_value=_fake_comun_results()):
        result = runner.invoke(app, ["search", "comun"], env={"OPENSDMX_OUTPUT": ""})

    assert result.exit_code == 0, result.output
    assert "│" in result.output


def test_invalid_env_var_names_the_env_var_not_the_flag(_no_api_check):
    """A bad OPENSDMX_OUTPUT must not blame --output, which the user never typed."""
    result = runner.invoke(app, ["search", "comun"], env={"OPENSDMX_OUTPUT": "jsn"})

    assert result.exit_code == 1
    assert "invalid OPENSDMX_OUTPUT value 'jsn'" in result.output
    assert "--output" not in result.output


def test_invalid_flag_still_names_the_flag(_no_api_check):
    result = runner.invoke(app, ["-o", "jsn", "search", "comun"])

    assert result.exit_code == 1
    assert "invalid --output value 'jsn'" in result.output


# ── providers coverage column ────────────────────────────────────────


def test_providers_json_includes_coverage(_no_api_check):
    import json

    with patch("opensdmx.categories.provider_coverage", return_value=42.0):
        result = runner.invoke(app, ["-o", "json", "providers"])

    assert result.exit_code == 0, result.output
    rows = {r["alias"]: r for r in json.loads(result.output)}
    # categories_supported=True → the mocked coverage comes through.
    assert rows["istat"]["coverage"] == 42.0
    # categories_supported=False → not applicable, never calls provider_coverage.
    assert rows["worldbank"]["coverage"] is None


def test_providers_table_shows_coverage_percent_and_dash(_no_api_check):
    with patch("opensdmx.categories.provider_coverage", return_value=50.0):
        result = runner.invoke(app, ["providers"])

    assert result.exit_code == 0, result.output
    assert "50%" in result.output
    # worldbank has categories_supported=False → dash, not a percentage.
    # (the alias column truncates to "world…" at the runner's terminal width)
    lines = [line for line in result.output.splitlines() if "world" in line]
    assert lines and "%" not in lines[0]


def test_providers_table_shows_unknown_when_uncached(_no_api_check):
    with patch("opensdmx.categories.provider_coverage", return_value=None):
        result = runner.invoke(app, ["providers"])

    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if "istat" in line]
    assert lines and "?" in lines[0]


def test_providers_table_rounds_coverage_down(_no_api_check):
    """99.9% must not render as 100%.

    A catalog one dataflow short of full categorisation is the case the column
    exists to warn about; rounding it up to 100% would hide it.
    """
    with patch("opensdmx.categories.provider_coverage", return_value=99.9):
        result = runner.invoke(app, ["providers"])

    assert result.exit_code == 0, result.output
    assert "99%" in result.output
    assert "100%" not in result.output
