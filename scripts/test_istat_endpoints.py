#!/usr/bin/env python3
"""Test ISTAT SDMX 2.1 endpoints to discover available metadata.

This script probes various SDMX 2.1 endpoints to see which ones ISTAT
implements, particularly those that could provide territorial granularity
or temporal coverage without needing to probe data.

Endpoints tested:
1. actualconstraint - Real constraints vs theoretical
2. metadatastructure - Structured metadata definitions
3. metadata/dataflow - Reference metadata for dataflows
4. dataflow annotations - Check for useful annotations
5. constraint?type=actual - Alternative actual constraint syntax

Usage:
    python scripts/test_istat_endpoints.py
    python scripts/test_istat_endpoints.py --verbose
    python scripts/test_istat_endpoints.py --sample-dataflow 121_331
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
import time

import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

ISTAT_BASE = "https://esploradati.istat.it/SDMXWS/rest"

# Stratified sample: 40 dataflows covering different characteristics
SAMPLE_DATAFLOWS = [
    # WITH territorial dimension (10)
    "22_289_DF_DCIS_POPRES1_23",
    "73_440_DF_DCCV_PROCEEDCRIME_A_10",
    "164_164_DF_DCIS_RICPOPRES2011_19",
    "150_915",
    "6_471_TS_DF_DCSP_LACIS_30",
    "68_380_DF_DCCV_VIAGGI_CHARACT_17",
    "6_471_TS_DF_DCSP_LACIS_6",
    "DF_DCSS_ISTR_LAV_PEN_2_TV_4",
    "609_1_DF_DCCV_URBANENV_9",
    "6_471_TS_DF_DCSP_LACIS_21",
    
    # WITHOUT territorial dimension (10)
    "78_1112_DF_DCCV_VIOL_CARAT_11",
    "145_361_DF_DCSC_FABBRESID_1_8",
    "3_156",
    "34_728_DF_DCCV_POVERTA_BRKN1_4",
    "172_1198_DF_DCCV_NEET1_UNT2020_11",
    "DF_BULK_CEN2011_DICA_TRASVEMI",
    "164_279_DF_DCIS_RICPOPRES1991_11",
    "174_66_DF_DCCV_CONCHI_2",
    "93_1227_DF_DCCN_TNA1_2",
    "172_926_DF_DCCV_COMPL1_20",
    
    # WITH constraint (10)
    "47_940_DF_DCIS_SPESESERSOC1_5",
    "123_712_DF_DCAR_INDBILPER_1",
    "DF_DCSS_MIGR_BACKG_PAR_TV_10_COM",
    "56_858_DF_DCIS_ISCRITTI1_1",
    "DF_DCSS_POP_DEMCITMIG_TV_1",
    "183_285_DF_DICA_ASIAULP_5",
    "41_270_DF_DCIS_MORTIFERITISTR1_1",
    "41_270_DF_DCIS_MORTIFERITISTR1_TS3_1",
    "165_889_DF_DCIS_PREVDEM1_1",
    "22_315_DF_DCIS_POPORESBIL1_24",
    
    # WITHOUT constraint (10)
    "145_361_DF_DCSC_FABBRESID_1_6",
    "DF_DCSS_POPRESABR_4_REGIO",
    "49_62_DF_DCIS_OSPITIPRESIDI1_21",
    "6_39_DF_DCSP_ICT_9",
    "162_1064",
    "73_440_DF_DCCV_PROCEEDCRIME_A_3",
    "19_366_DF_DCCN_PROTSOC_B19_1",
    "742_1103_DF_DCSI_CPI_RISORSE_14",
    "183_286_DF_DICA_ADIPWP_2",
    "9_951_DF_DCCV_CAVE_MIN_2",
]


def test_endpoint(url: str, description: str, wait_time: float = 13.0) -> dict:
    """Test a single endpoint and return results."""
    result = {
        "endpoint": url.replace(ISTAT_BASE, ""),
        "description": description,
        "status": None,
        "content_length": 0,
        "has_data": False,
        "error": None,
    }
    
    try:
        # Rate limiting
        time.sleep(wait_time)
        
        response = httpx.get(url, timeout=30.0, headers={"Accept": "application/xml"})
        result["status"] = response.status_code
        
        if response.status_code == 200:
            content = response.text
            result["content_length"] = len(content)
            
            # Check if response has meaningful data (not just empty structure)
            result["has_data"] = (
                len(content) > 500  # More than just XML wrapper
                and ("Constraint" in content or "Metadata" in content or "Annotation" in content)
            )
        
    except httpx.TimeoutException:
        result["error"] = "Timeout"
    except httpx.HTTPError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Unexpected: {e}"
    
    return result


def test_actualconstraint(dataflow_id: str) -> dict:
    """Test actualconstraint endpoint."""
    url = f"{ISTAT_BASE}/actualconstraint/ISTAT,{dataflow_id},1.0"
    return test_endpoint(url, "ActualConstraint for specific dataflow")


def test_metadatastructure() -> dict:
    """Test metadatastructure endpoint."""
    url = f"{ISTAT_BASE}/metadatastructure/ISTAT"
    return test_endpoint(url, "Metadata Structure Definitions")


def test_metadata_dataflow(dataflow_id: str) -> dict:
    """Test metadata/dataflow endpoint."""
    url = f"{ISTAT_BASE}/metadata/dataflow/ISTAT,{dataflow_id},1.0"
    return test_endpoint(url, "Reference Metadata for dataflow")


def test_dataflow_annotations(dataflow_id: str) -> dict:
    """Test dataflow with references=all to get annotations."""
    url = f"{ISTAT_BASE}/dataflow/ISTAT,{dataflow_id},1.0?references=all"
    result = test_endpoint(url, "Dataflow with annotations")
    
    # Additional check for annotations
    if result["status"] == 200:
        try:
            response = httpx.get(url, timeout=30.0)
            content = response.text
            has_annotations = "<Annotation" in content or '"annotations"' in content
            result["has_annotations"] = has_annotations
        except Exception:
            pass
    
    return result


def test_constraint_type_param(dataflow_id: str) -> dict:
    """Test constraint endpoint with type=actual parameter."""
    url = f"{ISTAT_BASE}/contentconstraint/ISTAT,{dataflow_id},1.0?type=actual"
    return test_endpoint(url, "ContentConstraint with type=actual")


def main():
    parser = argparse.ArgumentParser(description="Test ISTAT SDMX endpoints")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--sample-dataflow",
        help="Test with specific dataflow (default: test multiple samples)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=13.0,
        help="Seconds between calls (default: 13)",
    )
    args = parser.parse_args()
    
    console.print("\n[bold blue]🔍 Testing ISTAT SDMX 2.1 Endpoints[/bold blue]\n")
    console.print(
        f"[yellow]⏱️  Rate limit: {args.rate_limit}s between calls[/yellow]\n"
    )
    
    # Determine dataflows to test
    if args.sample_dataflow:
        dataflows = [args.sample_dataflow]
    else:
        dataflows = SAMPLE_DATAFLOWS
    
    results = []
    
    # Test 1: MetadataStructure (only once, not per dataflow)
    console.print("[dim]Testing metadatastructure endpoint...[/dim]")
    results.append(test_metadatastructure())
    
    # Tests 2-5: Per dataflow
    for df_id in dataflows:
        console.print(f"\n[bold]Testing dataflow: {df_id}[/bold]")
        
        console.print("[dim]  Testing actualconstraint...[/dim]")
        results.append(test_actualconstraint(df_id))
        
        console.print("[dim]  Testing metadata/dataflow...[/dim]")
        results.append(test_metadata_dataflow(df_id))
        
        console.print("[dim]  Testing dataflow annotations...[/dim]")
        results.append(test_dataflow_annotations(df_id))
        
        console.print("[dim]  Testing constraint with type param...[/dim]")
        results.append(test_constraint_type_param(df_id))
    
    # Summary table
    console.print("\n[bold]📊 Results Summary[/bold]\n")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("Endpoint")
    table.add_column("Description")
    table.add_column("Status")
    table.add_column("Has Data?")
    table.add_column("Size")
    
    working_endpoints = []
    
    for r in results:
        status_color = "green" if r["status"] == 200 else "red"
        status_str = f"[{status_color}]{r['status'] or r['error']}[/{status_color}]"
        
        has_data_str = "✅" if r.get("has_data") else "❌"
        size_str = f"{r['content_length']:,}" if r["content_length"] > 0 else "-"
        
        table.add_row(
            r["endpoint"][:50],
            r["description"][:40],
            status_str,
            has_data_str,
            size_str,
        )
        
        if r["status"] == 200 and r.get("has_data"):
            working_endpoints.append(r)
    
    console.print(table)
    
    # Recommendations
    console.print(f"\n[bold]💡 Recommendations[/bold]\n")
    
    if working_endpoints:
        console.print("[green]✅ Found working endpoints with data:[/green]\n")
        for endpoint in working_endpoints:
            console.print(f"  • {endpoint['description']}: {endpoint['endpoint']}")
        
        console.print(
            "\n[bold]These endpoints can be used to avoid empirical probes![/bold]"
        )
    else:
        console.print(
            "[yellow]⚠️  No endpoints found with useful metadata.[/yellow]\n"
            "Recommendation: Use empirical probes (firstNObservations) for "
            "territorial granularity and temporal coverage."
        )
    
    return 0 if working_endpoints else 1


if __name__ == "__main__":
    sys.exit(main())
