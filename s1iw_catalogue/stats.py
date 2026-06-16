"""Statistics generation for the catalogue."""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import polars as pl


class CatalogueStats:
    """Compute and export catalogue statistics."""

    def __init__(self, df: pl.DataFrame) -> None:
        self.df = df

    def total_count(self) -> int:
        """Total number of SAFE entries."""
        return self.df.height

    def product_type_counts(self) -> Dict[str, int]:
        """Return counts for SLC, GRD, OCN."""
        return {
            "SLC": self.df.filter(pl.col("SAFE SLC").is_not_null()).height,
            "GRD": self.df.filter(pl.col("SAFE GRD").is_not_null()).height,
            "OCN": self.df.filter(pl.col("SAFE OCN").is_not_null()).height,
        }

    def product_type_percentages(self) -> Dict[str, float]:
        """Return percentages for SLC, GRD, OCN."""
        counts = self.product_type_counts()
        total = self.total_count()
        if total == 0:
            return {k: 0.0 for k in counts}
        return {k: v / total * 100.0 for k, v in counts.items()}

    def dataset_membership_counts(self) -> Dict[str, int]:
        """Return number of SAFE per dataset."""
        if "dataset(s) d'appartenance" not in self.df.columns:
            return {}
        exploded = self.df.explode("dataset(s) d'appartenance")
        counts = exploded.group_by("dataset(s) d'appartenance").agg(pl.len())
        return dict(zip(counts["dataset(s) d'appartenance"], counts["len"]))

    def presence_completeness(self, dataset: Optional[str] = None) -> Dict[str, float]:
        """Compute percentages of non-null presence columns."""
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
        for col in [
            "presence SLC",
            "presence GRD",
            "presence OCN",
            "presence L1B XSP A21",
            "presence L1C XSP B17",
        ]:
            if col in filtered.columns:
                present = filtered.filter(pl.col(col).is_not_null()).height
                completeness[col] = present / total * 100.0

        return completeness

    def latest_acquisition(self) -> Tuple[str, datetime.datetime]:
        """Return (safe_name, start_date) of most recent acquisition."""
        if "start date SAFE" not in self.df.columns or self.df.height == 0:
            return ("", datetime.datetime(1970, 1, 1))
        latest_row = self.df.filter(
            pl.col("start date SAFE") == self.df["start date SAFE"].max()
        )
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
        latest_row = self.df.filter(
            pl.col("horodating") == self.df["horodating"].max()
        )
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
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days_threshold)
        return self.df.filter(pl.col("horodating") < cutoff)

    def stale_count(self, days_threshold: int = 30) -> int:
        """Return number of rows where horodating is older than threshold days."""
        return self.stale_rows(days_threshold).height

    def satellite_counts(self) -> Dict[str, int]:
        """Return counts per satellite (unité)."""
        if "unité" not in self.df.columns:
            return {}
        counts = self.df.group_by("unité").agg(pl.len())
        return dict(zip(counts["unité"], counts["len"]))

    def polarization_counts(self) -> Dict[str, int]:
        """Return counts per polarization."""
        if "polarization" not in self.df.columns:
            return {}
        counts = self.df.group_by("polarization").agg(pl.len())
        return dict(zip(counts["polarization"], counts["len"]))

    def linked_count(self) -> int:
        """Return number of rows with both SLC and GRD."""
        return self.df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_not_null()
        ).height

    def unlinked_slc_count(self) -> int:
        """Return number of SLC-only rows."""
        return self.df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_null()
        ).height

    def unlinked_grd_count(self) -> int:
        """Return number of GRD-only rows."""
        return self.df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("SAFE SLC").is_null()
        ).height

    def to_dict(self) -> Dict[str, Any]:
        """Return all statistics as a dictionary."""
        stats = {
            "total_count": self.total_count(),
            "product_type_counts": self.product_type_counts(),
            "product_type_percentages": self.product_type_percentages(),
            "linked_count": self.linked_count(),
            "unlinked_slc_count": self.unlinked_slc_count(),
            "unlinked_grd_count": self.unlinked_grd_count(),
            "dataset_counts": self.dataset_membership_counts(),
            "presence_completeness": self.presence_completeness(),
            "latest_acquisition": self.latest_acquisition(),
            "latest_horodating": self.latest_horodating(),
            "stale_count_30d": self.stale_count(30),
            "satellite_counts": self.satellite_counts(),
            "polarization_counts": self.polarization_counts(),
        }
        # Convert datetimes to strings for JSON serialization
        if stats["latest_acquisition"][1]:
            stats["latest_acquisition"] = (
                stats["latest_acquisition"][0],
                stats["latest_acquisition"][1].isoformat(),
            )
        if stats["latest_horodating"][1]:
            stats["latest_horodating"] = (
                stats["latest_horodating"][0],
                stats["latest_horodating"][1].isoformat(),
            )
        return stats

    def to_json(self, path: Path) -> None:
        """Export statistics to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    def to_string(self) -> str:
        """Return a human-readable summary as a string."""
        lines = []
        lines.append("=" * 60)
        lines.append("CATALOGUE STATISTICS")
        lines.append("=" * 60)

        # Basic counts
        lines.append(f"\n📊 Total SAFE entries: {self.total_count()}")
        counts = self.product_type_counts()
        pcts = self.product_type_percentages()
        lines.append("  Product types:")
        for ptype, count in counts.items():
            pct = pcts.get(ptype, 0)
            lines.append(f"    {ptype}: {count} ({pct:.1f}%)")

        # Linking status
        lines.append(f"\n🔗 Linking status:")
        lines.append(f"  Both SLC and GRD: {self.linked_count()}")
        lines.append(f"  SLC only: {self.unlinked_slc_count()}")
        lines.append(f"  GRD only: {self.unlinked_grd_count()}")

        # Dataset memberships
        ds_counts = self.dataset_membership_counts()
        if ds_counts:
            lines.append("\n📁 Dataset memberships:")
            for ds, cnt in sorted(ds_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {ds}: {cnt} products")

        # Presence completeness
        presence = self.presence_completeness()
        if presence:
            lines.append("\n💾 Presence completeness:")
            for col, pct in presence.items():
                lines.append(f"  {col}: {pct:.1f}%")

        # Satellite distribution
        sat_counts = self.satellite_counts()
        if sat_counts:
            lines.append("\n🛰️  Satellite distribution:")
            for sat, cnt in sorted(sat_counts.items()):
                lines.append(f"  {sat}: {cnt} products")

        # Polarization distribution
        pol_counts = self.polarization_counts()
        if pol_counts:
            lines.append("\n🔬 Polarization distribution:")
            for pol, cnt in sorted(pol_counts.items()):
                lines.append(f"  {pol}: {cnt} products")

        # Timestamps
        latest_acq, latest_acq_dt = self.latest_acquisition()
        if latest_acq_dt and latest_acq_dt.year > 1970:
            lines.append(f"\n📅 Latest acquisition:")
            lines.append(f"  {latest_acq_dt} ({latest_acq})")

        latest_horo, latest_horo_dt = self.latest_horodating()
        if latest_horo_dt and latest_horo_dt.year > 1970:
            lines.append(f"\n🔄 Latest catalogue update (horodating):")
            lines.append(f"  {latest_horo_dt} ({latest_horo})")

        # Stale rows
        stale = self.stale_count(30)
        if stale > 0:
            lines.append(f"\n⚠️  Rows not updated in 30+ days: {stale}")
            if stale > 0:
                lines.append("  Consider running --update to refresh these rows")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)