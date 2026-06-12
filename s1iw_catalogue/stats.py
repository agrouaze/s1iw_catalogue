"""Statistics generation for the catalogue."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import polars as pl
import datetime


class CatalogueStats:
    """Compute and export catalogue statistics."""

    def __init__(self, df: pl.DataFrame) -> None:
        self.df = df

    def total_count(self) -> int:
        return self.df.height

    def product_type_counts(self) -> Dict[str, int]:
        return {
            "SLC": self.df.filter(pl.col("SAFE SLC").is_not_null()).height,
            "GRD": self.df.filter(pl.col("SAFE GRD").is_not_null()).height,
            "OCN": self.df.filter(pl.col("SAFE OCN").is_not_null()).height,
        }

    def dataset_membership_counts(self) -> Dict[str, int]:
        if "dataset(s) d'appartenance" not in self.df.columns:
            return {}
        exploded = self.df.explode("dataset(s) d'appartenance")
        counts = exploded.group_by("dataset(s) d'appartenance").agg(pl.len())
        return dict(zip(counts["dataset(s) d'appartenance"], counts["len"]))

    def presence_completeness(self, dataset: Optional[str] = None) -> Dict[str, float]:
        if dataset is not None:
            filtered = self.df.filter(
                pl.col("dataset(s) d'appartenance").list.contains(dataset)
            )
        else:
            filtered = self.df
        total = filtered.height
        if total == 0:
            return {}
        completeness = {}
        for col in ["presence SLC", "presence GRD", "presence OCN",
                    "presence L1B XSP A21", "presence L1C XSP B17"]:
            if col in filtered.columns:
                present = filtered.filter(pl.col(col).is_not_null()).height
                completeness[col] = present / total * 100.0
        return completeness

    def latest_acquisition(self) -> Tuple[str, datetime.datetime]:
        """Return (safe_name, start_date) of most recent acquisition."""
        if "start date SAFE" not in self.df.columns or self.df.height == 0:
            return ("", datetime.datetime(1970, 1, 1))
        latest_row = self.df.filter(pl.col("start date SAFE") == self.df["start date SAFE"].max())
        safe_name = None
        for col in ["SAFE SLC", "SAFE GRD", "SAFE OCN"]:
            val = latest_row[col][0]
            if val is not None:
                safe_name = val
                break
        if safe_name is None:
            safe_name = ""
        dt = latest_row["start date SAFE"][0]
        return (safe_name, dt)

    def latest_horodating(self) -> Tuple[str, datetime.datetime]:
        """Return (safe_name, horodating) of most recently updated row."""
        if "horodating" not in self.df.columns or self.df.height == 0:
            return ("", datetime.datetime(1970, 1, 1))
        latest_row = self.df.filter(pl.col("horodating") == self.df["horodating"].max())
        safe_name = None
        for col in ["SAFE SLC", "SAFE GRD", "SAFE OCN"]:
            val = latest_row[col][0]
            if val is not None:
                safe_name = val
                break
        if safe_name is None:
            safe_name = ""
        dt = latest_row["horodating"][0]
        return (safe_name, dt)

    def stale_rows(self, days_threshold: int = 30) -> pl.DataFrame:
        """Return rows where horodating is older than threshold days."""
        if "horodating" not in self.df.columns:
            return self.df
        # For now, just return empty (implement properly later)
        return self.df

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count(),
            "product_types": self.product_type_counts(),
            "dataset_counts": self.dataset_membership_counts(),
            "presence_completeness": self.presence_completeness(),
            "latest_acquisition": self.latest_acquisition(),
            "latest_horodating": self.latest_horodating(),
        }

    def to_json(self, path: Path) -> None:
        import json
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)