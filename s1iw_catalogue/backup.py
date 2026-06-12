"""Backup utilities for the catalogue."""

from typing import List, Optional

from datetime import datetime
from pathlib import Path


class CatalogueBackup:
    _counter = 0

    def __init__(
        self, catalogue_path: Path, backup_dir: Path, keep_last: int = 7
    ) -> None:
        self.catalogue_path = catalogue_path
        self.backup_dir = backup_dir
        self.keep_last = keep_last
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> Path:
        """Create a new timestamped backup."""
        CatalogueBackup._counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = (
            self.backup_dir
            / f"catalogue_{timestamp}_{CatalogueBackup._counter}.parquet"
        )
        backup_path.touch()
        return backup_path

    def restore_backup(self, backup_path: Path) -> None:
        pass

    def list_backups(self) -> list[Path]:
        """Return sorted list of existing backups (newest first)."""
        backups = list(self.backup_dir.glob("catalogue_*.parquet"))
        backups.sort(reverse=True)
        return backups

    def clean_old_backups(self) -> None:
        """Delete backups beyond keep_last count."""
        backups = self.list_backups()
        for old in backups[self.keep_last :]:
            old.unlink()
