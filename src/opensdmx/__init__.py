"""opensdmx — Python interface to any SDMX 2.1 REST API."""

from .base import get_provider, set_provider, set_timeout
from .discovery import (
    ConstraintsUnavailable,
    all_available,
    dimensions_info,
    get_available_values,
    get_dimension_values,
    load_dataset,
    print_dataset,
    reset_filters,
    search_dataset,
    set_filters,
)
from .retrieval import fetch, get_data, parse_time_period
from .cli import main

__all__ = [
    "ConstraintsUnavailable",
    "set_provider",
    "get_provider",
    "all_available",
    "search_dataset",
    "load_dataset",
    "print_dataset",
    "dimensions_info",
    "get_dimension_values",
    "get_available_values",
    "set_filters",
    "reset_filters",
    "get_data",
    "fetch",
    "set_timeout",
    "parse_time_period",
    "main",
]
