"""Test backup management."""

from pathlib import Path
import time

import pytest

from s1iw_catalogue.backup import CatalogueBackup


@pytest.fixture
def dummy_catalogue(tmp_path):
    cat_path = tmp_path / "main.parquet"
    cat_path.write_bytes(b"dummy content")
    return cat_path


def test_backup_creation(dummy_catalogue, tmp_path):
    backup_dir = tmp_path / "backups"
    backup = CatalogueBackup(dummy_catalogue, backup_dir, keep_last=2)
    backup_path = backup.create_backup()
    assert backup_path.exists()
    assert backup_path.parent == backup_dir
    # Name pattern: catalogue_YYYYMMDD_HHMMSS.parquet
    assert backup_path.name.startswith("catalogue_")
    assert backup_path.suffix == ".parquet"


def test_list_backups(dummy_catalogue, tmp_path):
    backup_dir = tmp_path / "backups"
    backup = CatalogueBackup(dummy_catalogue, backup_dir, keep_last=2)
    b1 = backup.create_backup()
    import time
    time.sleep(0.01)  # small delay to ensure different microsecond
    b2 = backup.create_backup()
    backups = backup.list_backups()
    assert len(backups) == 2
    assert b1 in backups
    assert b2 in backups


def test_clean_old_backups(dummy_catalogue, tmp_path):
    backup_dir = tmp_path / "backups"
    backup = CatalogueBackup(dummy_catalogue, backup_dir, keep_last=1)
    backup.create_backup()
    time.sleep(0.1)
    backup.create_backup()
    backup.clean_old_backups()
    remaining = backup.list_backups()
    assert len(remaining) == 1