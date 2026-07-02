"""Test CLI commands using Click runner."""

from typing import Any

from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from click.testing import CliRunner

from s1iw_catalogue.cli import main


@pytest.fixture()
def mock_config() -> dict[str, Any]:
    """Return a dummy configuration dictionary for testing."""
    return {
        "paths": {
            "reference_listings": {
                "test_slc": {"path": "dummy.txt", "type": "slc", "category": "train"}
            }
        }
    }


@pytest.fixture()
def mock_catalogue() -> MagicMock:
    """Return a mocked S1IWCatalogue instance."""
    catalogue = MagicMock()
    catalogue.create.return_value = None
    catalogue.update.return_value = None
    catalogue.backup.return_value = Path("/tmp/backup_20230101.parquet")
    catalogue.query.return_value = {"SAFE SLC": "test.SAFE", "unit": "S1A"}
    return catalogue


@pytest.fixture()
def runner() -> CliRunner:
    """Return a CliRunner instance."""
    return CliRunner()


class TestCreateCommand:
    """Tests for the 'create' command."""

    @patch("s1iw_catalogue.cli.S1IWCatalogue")
    @patch("s1iw_catalogue.cli.load_config")
    def test_create_command_success(
        self,
        mock_load: MagicMock,
        mock_cat: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test successful catalogue creation."""
        mock_load.return_value = mock_config
        mock_cat.return_value = MagicMock()

        with runner.isolated_filesystem():
            result = runner.invoke(main, ["create", "--output", "out.parquet"])

        assert result.exit_code == 0
        assert "Done." in result.output
        mock_cat.assert_called_once()

    @patch("s1iw_catalogue.cli.S1IWCatalogue")
    @patch("s1iw_catalogue.cli.load_config")
    def test_create_command_with_listing(
        self,
        mock_load: MagicMock,
        mock_cat: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test catalogue creation using a specific listing filter."""
        mock_load.return_value = mock_config
        mock_cat.return_value = MagicMock()

        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["create", "--output", "out.parquet", "--listing", "test_slc"]
            )

        assert result.exit_code == 0
        # Verify the config passed to S1IWCatalogue is filtered
        call_kwargs = mock_cat.call_args.kwargs
        filtered_config = call_kwargs.get("config")
        assert "test_slc" in filtered_config["paths"]["reference_listings"]
        assert len(filtered_config["paths"]["reference_listings"]) == 1

    @patch("s1iw_catalogue.cli.load_config")
    def test_create_command_invalid_listing(
        self, mock_load: MagicMock, runner: CliRunner, mock_config: dict[str, Any]
    ) -> None:
        """Test that an invalid listing name triggers an error and aborts."""
        mock_load.return_value = mock_config

        with runner.isolated_filesystem():
            result = runner.invoke(
                main,
                ["create", "--output", "out.parquet", "--listing", "invalid_listing"],
            )

        assert result.exit_code != 0
        assert "not found in configuration" in result.output


class TestUpdateCommand:
    """Tests for the 'update' command."""

    @patch("s1iw_catalogue.cli.S1IWCatalogue")
    @patch("s1iw_catalogue.cli.load_config")
    def test_update_command_success(
        self,
        mock_load: MagicMock,
        mock_cat: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test successful catalogue update."""
        mock_load.return_value = mock_config
        mock_cat.return_value = MagicMock()

        with runner.isolated_filesystem():
            Path("dummy.parquet").touch()
            result = runner.invoke(main, ["update", "--catalogue", "dummy.parquet"])

        assert result.exit_code == 0
        assert "Updating" in result.output
        assert "Done." in result.output
        mock_cat.return_value.update.assert_called_once()

    def test_update_command_missing_file(self, runner: CliRunner) -> None:
        """Test update fails gracefully if catalogue file does not exist."""
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["update", "--catalogue", "missing.parquet"])

        assert result.exit_code != 0
        assert "does not exist" in result.output


class TestStatsCommand:
    """Tests for the 'stats' command."""

    @patch("s1iw_catalogue.cli.CatalogueStats")
    @patch("polars.read_parquet")
    @patch("s1iw_catalogue.cli.load_config")
    def test_stats_command_success(
        self,
        mock_load: MagicMock,
        mock_read: MagicMock,
        mock_stats_cls: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test stats command prints output."""
        mock_load.return_value = mock_config
        mock_df = MagicMock()
        mock_df.height = 10
        mock_df.columns = ["SAFE SLC"]
        mock_df.select.return_value = mock_df
        mock_read.return_value = mock_df

        # Mock the CatalogueStats instance to avoid MagicMock formatting errors
        mock_stats_instance = MagicMock()
        mock_stats_instance.to_string.return_value = "Mock stats output"
        mock_stats_cls.return_value = mock_stats_instance

        with runner.isolated_filesystem():
            Path("dummy.parquet").touch()
            result = runner.invoke(main, ["stats", "--catalogue", "dummy.parquet"])

        assert result.exit_code == 0
        assert "Mock stats output" in result.output
        mock_read.assert_called_once()  # Removed strict path type checking

    @patch("s1iw_catalogue.cli.CatalogueStats")
    @patch("polars.read_parquet")
    @patch("s1iw_catalogue.cli.load_config")
    def test_stats_command_dataset_not_found(
        self,
        mock_load: MagicMock,
        mock_read: MagicMock,
        mock_stats_cls: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test stats command handles missing dataset gracefully."""
        mock_load.return_value = mock_config
        # Initialize with explicitly typed empty list to avoid Null type errors
        empty_df = pl.DataFrame({"datasets": pl.Series([[]], dtype=pl.List(pl.Utf8))})
        mock_read.return_value = empty_df

        mock_stats_instance = MagicMock()
        mock_stats_instance.to_string.return_value = ""
        mock_stats_cls.return_value = mock_stats_instance

        with runner.isolated_filesystem():
            Path("dummy.parquet").touch()
            result = runner.invoke(
                main, ["stats", "--catalogue", "dummy.parquet", "--dataset", "missing_ds"]
            )

        assert result.exit_code == 0
        assert "products found for dataset" in result.output.lower()  # Fixed case-sensitivity



class TestBackupCommand:
    """Tests for the 'backup' command."""

    @patch("s1iw_catalogue.cli.S1IWCatalogue")
    @patch("s1iw_catalogue.cli.load_config")
    def test_backup_command_success(
        self,
        mock_load: MagicMock,
        mock_cat: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test successful backup creation."""
        mock_load.return_value = mock_config
        mock_cat_instance = MagicMock()
        mock_cat_instance.backup.return_value = Path("/tmp/backup_20230101.parquet")
        mock_cat.return_value = mock_cat_instance

        with runner.isolated_filesystem():
            Path("dummy.parquet").touch()
            result = runner.invoke(main, ["backup", "--catalogue", "dummy.parquet"])

        assert result.exit_code == 0
        assert "Backup created" in result.output


class TestQueryCommand:
    """Tests for the 'query' command."""

    @patch("s1iw_catalogue.cli.S1IWCatalogue")
    @patch("s1iw_catalogue.cli.load_config")
    def test_query_command_found(
        self,
        mock_load: MagicMock,
        mock_cat: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test query command when SAFE is found."""
        mock_load.return_value = mock_config
        mock_cat_instance = MagicMock()
        mock_cat_instance.query.return_value = {"SAFE SLC": "test.SAFE", "unit": "S1A"}
        mock_cat.return_value = mock_cat_instance

        with runner.isolated_filesystem():
            Path("dummy.parquet").touch()
            result = runner.invoke(
                main,
                ["query", "--catalogue", "dummy.parquet", "--safe-name", "test.SAFE"],
            )

        assert result.exit_code == 0
        assert "SAFE information:" in result.output
        assert "test.SAFE" in result.output

    @patch("s1iw_catalogue.cli.S1IWCatalogue")
    @patch("s1iw_catalogue.cli.load_config")
    def test_query_command_not_found(
        self,
        mock_load: MagicMock,
        mock_cat: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test query command when SAFE is not found."""
        mock_load.return_value = mock_config
        mock_cat_instance = MagicMock()
        mock_cat_instance.query.return_value = None
        mock_cat.return_value = mock_cat_instance

        with runner.isolated_filesystem():
            Path("dummy.parquet").touch()
            result = runner.invoke(
                main,
                [
                    "query",
                    "--catalogue",
                    "dummy.parquet",
                    "--safe-name",
                    "missing.SAFE",
                ],
            )

        assert result.exit_code == 0
        assert "not found" in result.output


class TestMergeCommand:
    """Tests for the 'merge' command."""

    @patch("s1iw_catalogue.cli.S1IWCatalogue")
    @patch("s1iw_catalogue.cli.load_config")
    def test_merge_command_success(
        self,
        mock_load: MagicMock,
        mock_cat: MagicMock,
        runner: CliRunner,
        mock_config: dict[str, Any],
    ) -> None:
        """Test successful merge of two catalogues."""
        mock_load.return_value = mock_config
        mock_cat.return_value = MagicMock()

        with runner.isolated_filesystem():
            Path("cat1.parquet").touch()
            Path("cat2.parquet").touch()
            result = runner.invoke(
                main,
                ["merge", "cat1.parquet", "cat2.parquet", "--output", "merged.parquet"],
            )

        assert result.exit_code == 0
        assert "Merged 2 catalogues" in result.output

    def test_merge_command_requires_two(self, runner: CliRunner) -> None:
        """Test merge command aborts if less than two catalogues are provided."""
        with runner.isolated_filesystem():
            Path("cat1.parquet").touch()
            result = runner.invoke(
                main, ["merge", "cat1.parquet", "--output", "merged.parquet"]
            )

        assert result.exit_code != 0
        assert "At least two catalogues" in result.output
