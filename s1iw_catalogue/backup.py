"""Backup utilities for the catalogue."""

from pathlib import Path
from typing import List, Optional


class CatalogueBackup:
    """Manage timestamped backups of the catalogue file."""

    def __init__(self, catalogue_path: Path, backup_dir: Path, keep_last: int = 7) -> None:
        """Initialize backup manager.

        Args:
            catalogue_path: Path to the current catalogue file.
            backup_dir: Directory to store backups.
            keep_last: Number of backups to retain (oldest are deleted).
        """
        ...

    def create_backup(self) -> Path:
        """Create a new timestamped backup.

        Returns:
            Path to the created backup file.
        """
        ...

    def restore_backup(self, backup_path: Path) -> None:
        """Restore a specific backup as the main catalogue."""
        ...

    def list_backups(self) -> List[Path]:
        """Return sorted list of existing backups (newest first)."""
        ...

    def clean_old_backups(self) -> None:
        """Delete backups beyond keep_last count."""
        ...