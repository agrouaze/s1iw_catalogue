"""Statistics generation for the catalogue."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import polars as pl


class CatalogueStats:
    """Compute and export catalogue statistics."""

    def __init__(self, df: pl.DataFrame) -> None:
        """Initialize with a catalogue DataFrame."""
        ...

    def total_count(self) -> int:
        """Total number of SAFE entries."""
        ...

    def product_type_counts(self) -> Dict[str, int]:
        """Return counts for SLC, GRD, OCN."""
        ...

    def dataset_membership_counts(self) -> Dict[str, int]:
        """Return number of SAFE per dataset."""
        ...

    def presence_completeness(self, dataset: Optional[str] = None) -> Dict[str, float]:
        """Compute percentages of non-null presence columns.

        Args:
            dataset: If provided, filter to SAFE belonging to that dataset.

        Returns:
            Dictionary mapping column names to percentage (0-100).
        """
        ...

    def latest_acquisition(self) -> Tuple[str, pl.datetime]:
        """Return (safe_name, start_date) of most recent acquisition."""
        ...

    def latest_horodating(self) -> Tuple[str, pl.datetime]:
        """Return (safe_name, horodating) of most recently updated row."""
        ...

    def stale_rows(self, days_threshold: int = 30) -> pl.DataFrame:
        """Return rows where horodating is older than threshold days."""
        ...

    def to_dict(self) -> Dict[str, any]:
        """Return all statistics as a dictionary."""
        ...

    def to_json(self, path: Path) -> None:
        """Export statistics to JSON file."""
        ...