"""Test S1IWCatalogue class."""

import datetime
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import polars as pl
import pytest

from s1iw_catalogue.catalogue import S1IWCatalogue


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return {
        "paths": {
            "reference_listings": {
                "SLC": {
                    "path": "/test/slc",
                    "description": "SLC products",
                    "category": "SAR",
                    "type": "SLC",
                },
                "GRD": {
                    "path": "/test/grd",
                    "description": "GRD products",
                    "category": "SAR",
                    "type": "GRD",
                },
            }
        }
    }


@pytest.fixture
def mock_catalogue_df():
    """Create a mock catalogue DataFrame."""
    return pl.DataFrame(
        {
            "SAFE SLC": ["S1A_IW_SLC_001", "S1A_IW_SLC_002", None],
            "SAFE GRD": [None, None, "S1A_IW_GRD_001"],
            "datasets": [["SLC"], ["SLC", "GRD"], ["GRD"]],
            "horodating": [datetime.datetime.now()] * 3,
            "start date SAFE": [datetime.datetime.now()] * 3,
            "polarization": ["VV", "VH", "VV"],
            "unit": ["S1A", "S1A", "S1B"],
            "category": ["SAR", "SAR", "SAR"],
        }
    )


@pytest.fixture
def temp_catalogue_path(tmp_path):
    """Return a temporary catalogue file path."""
    return tmp_path / "catalogue.parquet"


@pytest.fixture
def catalogue_with_mocks(temp_catalogue_path, mock_config):
    """Create a catalogue instance with mocked dependencies."""
    with (
        patch("s1iw_catalogue.catalogue.load_config") as mock_load_config,
        patch("s1iw_catalogue.catalogue.CatalogueUpdater") as mock_updater_class,
    ):

        mock_load_config.return_value = mock_config
        mock_updater = Mock()
        mock_updater_class.return_value = mock_updater

        cat = S1IWCatalogue(temp_catalogue_path, config=mock_config)

        # Store mocks for later use
        cat._mock_updater = mock_updater
        cat._mock_load_config = mock_load_config

        return cat


class TestS1IWCatalogue:
    """Test suite for S1IWCatalogue class."""

    def test_init_with_config_path(self, temp_catalogue_path, mock_config):
        """Test initialization with config_path parameter."""
        with patch("s1iw_catalogue.catalogue.load_config") as mock_load_config:
            mock_load_config.return_value = mock_config

            cat = S1IWCatalogue(temp_catalogue_path, config_path="/path/to/config.yml")

            assert cat._catalogue_path == temp_catalogue_path
            assert cat._config_path == Path("/path/to/config.yml").resolve()
            # Fix: Use assert_called_once_with with Path object
            mock_load_config.assert_called_once_with(
                config_path=Path("/path/to/config.yml")
            )

    def test_init_with_config_dict(self, temp_catalogue_path, mock_config):
        """Test initialization with config dictionary."""
        with patch("s1iw_catalogue.catalogue.load_config") as mock_load_config:
            cat = S1IWCatalogue(temp_catalogue_path, config=mock_config)

            assert cat._catalogue_path == temp_catalogue_path
            assert cat._config == mock_config
            mock_load_config.assert_not_called()

    def test_init_with_config_path_string(self, temp_catalogue_path, mock_config):
        """Test initialization with config as string path."""
        with patch("s1iw_catalogue.catalogue.load_config") as mock_load_config:
            mock_load_config.return_value = mock_config

            cat = S1IWCatalogue(temp_catalogue_path, config="config.yml")

            assert cat._config_path == Path("config.yml").resolve()
            mock_load_config.assert_called_once_with(config_path="config.yml")

    def test_write_parquet_with_metadata_success(
        self, catalogue_with_mocks, mock_catalogue_df, tmp_path
    ):
        """Test writing parquet with metadata successfully."""
        cat = catalogue_with_mocks
        test_path = tmp_path / "test.parquet"

        with patch("pyarrow.parquet.write_table") as mock_write:
            cat._write_parquet_with_metadata(mock_catalogue_df, test_path)
            mock_write.assert_called_once()

    def test_write_parquet_with_metadata_fallback(
        self, catalogue_with_mocks, mock_catalogue_df, tmp_path
    ):
        """Test writing parquet with metadata fallback on error."""
        cat = catalogue_with_mocks
        test_path = tmp_path / "test.parquet"

        with patch("pyarrow.parquet.write_table") as mock_write:
            mock_write.side_effect = Exception("PyArrow error")

            with patch.object(pl.DataFrame, "write_parquet") as mock_write_parquet:
                cat._write_parquet_with_metadata(mock_catalogue_df, test_path)
                mock_write_parquet.assert_called_once_with(
                    test_path, compression="snappy"
                )

    def test_create_catalogue(self, catalogue_with_mocks, mock_catalogue_df, tmp_path):
        """Test creating a new catalogue."""
        cat = catalogue_with_mocks
        mock_updater = cat._mock_updater

        # Setup mocks
        mock_updater.build_from_listings.return_value = mock_catalogue_df
        mock_updater.core_update.return_value = mock_catalogue_df
        mock_updater._compute_category_and_conflicts.return_value = mock_catalogue_df

        output_path = tmp_path / "new_catalogue.parquet"

        with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
            cat.create(output_path)

            mock_updater.build_from_listings.assert_called_once()
            mock_updater.core_update.assert_called_once()
            mock_updater._compute_category_and_conflicts.assert_called_once()
            mock_write.assert_called_once_with(mock_catalogue_df, output_path)

    def test_create_catalogue_default_path(
        self, catalogue_with_mocks, mock_catalogue_df
    ):
        """Test creating a new catalogue with default path."""
        cat = catalogue_with_mocks
        mock_updater = cat._mock_updater

        mock_updater.build_from_listings.return_value = mock_catalogue_df
        mock_updater.core_update.return_value = mock_catalogue_df
        mock_updater._compute_category_and_conflicts.return_value = mock_catalogue_df

        with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
            cat.create()

            mock_write.assert_called_once_with(mock_catalogue_df, cat._catalogue_path)

    def test_update_catalogue_not_exists(self, catalogue_with_mocks):
        """Test updating when catalogue doesn't exist."""
        cat = catalogue_with_mocks

        # Ensure catalogue doesn't exist
        if cat._catalogue_path.exists():
            cat._catalogue_path.unlink()

        with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
            cat.update()
            mock_write.assert_not_called()

    def test_update_catalogue_with_merge(
        self, catalogue_with_mocks, mock_catalogue_df, tmp_path
    ):
        """Test updating catalogue with merge operations."""
        cat = catalogue_with_mocks
        mock_updater = cat._mock_updater

        # Create existing catalogue
        existing_df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
                "SAFE GRD": [None],
                "datasets": [["SLC"]],
                "horodating": [datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now()],
            }
        )
        existing_df.write_parquet(cat._catalogue_path)

        # Mock new data with one existing and one new row
        new_df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001", "S1A_IW_SLC_003"],
                "SAFE GRD": [None, None],
                "datasets": [["SLC", "GRD"], ["SLC"]],
                "horodating": [datetime.datetime.now(), datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now(), datetime.datetime.now()],
            }
        )

        mock_updater.build_from_listings.return_value = new_df
        mock_updater.core_update.side_effect = lambda x: x
        mock_updater._compute_category_and_conflicts.return_value = (
            existing_df  # Return existing df
        )

        with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
            # Mock the rename operation to avoid FileNotFoundError
            with patch("pathlib.Path.rename") as mock_rename:
                cat.update()

                # Should call write with metadata
                mock_write.assert_called_once()
                # Should have merged and appended
                assert mock_updater.core_update.call_count >= 2

    def test_update_catalogue_only_append(
        self, catalogue_with_mocks, mock_catalogue_df, tmp_path
    ):
        """Test updating catalogue with only append operations."""
        cat = catalogue_with_mocks
        mock_updater = cat._mock_updater

        # Create existing catalogue with different data
        existing_df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_OLD"],
                "SAFE GRD": [None],
                "datasets": [["SLC"]],
                "horodating": [datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now()],
            }
        )
        existing_df.write_parquet(cat._catalogue_path)

        # Mock new data with only new rows
        new_df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_NEW1", "S1A_IW_SLC_NEW2"],
                "SAFE GRD": [None, None],
                "datasets": [["SLC"], ["SLC"]],
                "horodating": [datetime.datetime.now(), datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now(), datetime.datetime.now()],
            }
        )

        mock_updater.build_from_listings.return_value = new_df
        mock_updater.core_update.side_effect = lambda x: x
        mock_updater._compute_category_and_conflicts.return_value = existing_df

        with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
            with patch("pathlib.Path.rename") as mock_rename:
                cat.update()

                mock_write.assert_called_once()
                # Should have only appended
                assert mock_updater.core_update.call_count >= 1

    def test_update_catalogue_with_existing_grd(self, catalogue_with_mocks, tmp_path):
        """Test updating catalogue with existing GRD product."""
        cat = catalogue_with_mocks
        mock_updater = cat._mock_updater

        # Create existing catalogue with GRD product
        existing_df = pl.DataFrame(
            {
                "SAFE SLC": [None],
                "SAFE GRD": ["S1A_IW_GRD_001"],
                "datasets": [["GRD"]],
                "horodating": [datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now()],
            }
        )
        existing_df.write_parquet(cat._catalogue_path)

        # Mock new data with same GRD product
        new_df = pl.DataFrame(
            {
                "SAFE SLC": [None],
                "SAFE GRD": ["S1A_IW_GRD_001"],
                "datasets": [["GRD", "OCN"]],
                "horodating": [datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now()],
            }
        )

        mock_updater.build_from_listings.return_value = new_df
        mock_updater.core_update.side_effect = lambda x: x
        mock_updater._compute_category_and_conflicts.return_value = existing_df

        with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
            with patch("pathlib.Path.rename") as mock_rename:
                cat.update()

                mock_write.assert_called_once()

    def test_merge_catalogues(self, catalogue_with_mocks):
        """Test merging catalogues."""
        cat = catalogue_with_mocks
        mock_updater = cat._mock_updater

        input_paths = [Path("/test/input1.parquet"), Path("/test/input2.parquet")]
        output_path = Path("/test/output.parquet")

        cat.merge(input_paths, output_path)

        mock_updater.merge_catalogues.assert_called_once_with(
            input_paths, output_path, cat._config_path
        )

    def test_stats_all(self, catalogue_with_mocks, mock_catalogue_df, tmp_path):
        """Test generating statistics for all data."""
        cat = catalogue_with_mocks

        # Save a mock catalogue
        mock_catalogue_df.write_parquet(cat._catalogue_path)

        with patch("s1iw_catalogue.catalogue.CatalogueStats") as mock_stats_class:
            mock_stats = Mock()
            mock_stats.to_dict.return_value = {
                "total": 3,
                "datasets": {"SLC": 2, "GRD": 1},
            }
            mock_stats_class.return_value = mock_stats

            result = cat.stats()

            assert result == {"total": 3, "datasets": {"SLC": 2, "GRD": 1}}
            mock_stats_class.assert_called_once()

    def test_stats_with_dataset_filter(self, catalogue_with_mocks, mock_catalogue_df):
        """Test generating statistics with dataset filter."""
        cat = catalogue_with_mocks

        mock_catalogue_df.write_parquet(cat._catalogue_path)

        with patch("s1iw_catalogue.catalogue.CatalogueStats") as mock_stats_class:
            mock_stats = Mock()
            mock_stats.to_dict.return_value = {"total": 2, "datasets": {"SLC": 2}}
            mock_stats_class.return_value = mock_stats

            result = cat.stats(dataset="SLC")

            assert result == {"total": 2, "datasets": {"SLC": 2}}

    def test_stats_with_no_data(self, catalogue_with_mocks, tmp_path):
        """Test generating statistics with no data for filter."""
        cat = catalogue_with_mocks

        # Create catalogue with empty datasets column
        empty_df = pl.DataFrame(
            {
                "SAFE SLC": [],
                "SAFE GRD": [],
                "datasets": pl.Series(
                    [], dtype=pl.List(pl.Utf8)
                ),  # Use proper List type
                "horodating": [],
                "start date SAFE": [],
            }
        )
        empty_df.write_parquet(cat._catalogue_path)

        result = cat.stats(dataset="SLC")
        assert result == {}

    def test_stats_with_output_file(
        self, catalogue_with_mocks, mock_catalogue_df, tmp_path
    ):
        """Test generating statistics with output file."""
        cat = catalogue_with_mocks

        mock_catalogue_df.write_parquet(cat._catalogue_path)

        output_path = tmp_path / "stats.json"

        with patch("s1iw_catalogue.catalogue.CatalogueStats") as mock_stats_class:
            mock_stats = Mock()
            mock_stats.to_dict.return_value = {"total": 3}
            mock_stats_class.return_value = mock_stats

            result = cat.stats(output=output_path)

            assert result == {"total": 3}
            mock_stats.to_json.assert_called_once_with(output_path)

    def test_stats_verbose(self, catalogue_with_mocks, mock_catalogue_df, capsys):
        """Test generating statistics with verbose output."""
        cat = catalogue_with_mocks

        mock_catalogue_df.write_parquet(cat._catalogue_path)

        with patch("s1iw_catalogue.catalogue.CatalogueStats") as mock_stats_class:
            mock_stats = Mock()
            mock_stats.to_dict.return_value = {"total": 3}
            mock_stats.to_string.return_value = "Statistics Summary"
            mock_stats_class.return_value = mock_stats

            result = cat.stats(verbose=True)

            captured = capsys.readouterr()
            assert "Statistics Summary" in captured.out
            assert result == {"total": 3}

    def test_backup(self, catalogue_with_mocks):
        """Test backup method."""
        cat = catalogue_with_mocks
        result = cat.backup(backup_dir="/backup")
        assert result == Path()

    def test_query(self, catalogue_with_mocks):
        """Test query method."""
        cat = catalogue_with_mocks
        result = cat.query("S1A_IW_SLC_001")
        assert result is None

    def test_get_centroids(self, catalogue_with_mocks):
        """Test get_centroids method."""
        cat = catalogue_with_mocks

        with patch("s1iw_catalogue.catalogue.create_empty_catalogue") as mock_create:
            mock_create.return_value = pl.DataFrame({"centroid": [1, 2, 3]})
            result = cat.get_centroids()
            assert result.height == 3

    def test_get_dataset_metadata(self, catalogue_with_mocks, mock_config):
        """Test getting dataset metadata."""
        cat = catalogue_with_mocks

        metadata = cat.get_dataset_metadata()

        assert "SLC" in metadata
        assert "GRD" in metadata
        assert metadata["SLC"]["description"] == "SLC products"
        assert metadata["SLC"]["category"] == "SAR"
        assert metadata["GRD"]["type"] == "GRD"

    def test_get_dataset_metadata_empty(self, catalogue_with_mocks):
        """Test getting dataset metadata when empty."""
        cat = catalogue_with_mocks
        cat._config = {"paths": {"reference_listings": {}}}

        metadata = cat.get_dataset_metadata()
        assert metadata == {}

    def test_get_dataset_metadata_non_dict(self, catalogue_with_mocks):
        """Test getting dataset metadata with non-dict entries."""
        cat = catalogue_with_mocks
        cat._config = {
            "paths": {
                "reference_listings": {
                    "SLC": "not a dict",
                    "GRD": {"path": "/test", "description": "GRD"},
                }
            }
        }

        metadata = cat.get_dataset_metadata()
        assert "SLC" not in metadata
        assert "GRD" in metadata

    def test_get_config_path(self, catalogue_with_mocks):
        """Test getting config path."""
        cat = catalogue_with_mocks
        assert cat.get_config_path() == cat._config_path

    def test_load_catalogue_success(self, catalogue_with_mocks, mock_catalogue_df):
        """Test loading catalogue successfully."""
        cat = catalogue_with_mocks
        mock_catalogue_df.write_parquet(cat._catalogue_path)

        df = cat._load_catalogue()
        assert df.height == mock_catalogue_df.height

    def test_load_catalogue_not_found(self, catalogue_with_mocks):
        """Test loading catalogue when file doesn't exist."""
        cat = catalogue_with_mocks

        # Ensure catalogue doesn't exist
        if cat._catalogue_path.exists():
            cat._catalogue_path.unlink()

        with pytest.raises(FileNotFoundError):
            cat._load_catalogue()

    def test_save_catalogue(self, catalogue_with_mocks):
        """Test save catalogue method."""
        cat = catalogue_with_mocks
        df = pl.DataFrame({"col": [1, 2, 3]})

        # Should not raise any exception
        cat._save_catalogue(df)

    def test_merge_updates(self, catalogue_with_mocks):
        """Test merge updates method."""
        cat = catalogue_with_mocks
        df = pl.DataFrame({"col": [1, 2, 3]})

        result = cat._merge_updates(df)
        assert result.height == 0  # Returns empty dataframe

    def test_write_parquet_with_metadata_pyarrow_not_installed(
        self, catalogue_with_mocks, mock_catalogue_df, tmp_path
    ):
        """Test writing parquet when pyarrow is not available."""
        cat = catalogue_with_mocks
        test_path = tmp_path / "test.parquet"

        with patch.dict("sys.modules", {"pyarrow": None, "pyarrow.parquet": None}):
            # Force import error by making pyarrow import fail
            with patch("builtins.__import__", side_effect=ImportError("No pyarrow")):
                with patch.object(pl.DataFrame, "write_parquet") as mock_write:
                    cat._write_parquet_with_metadata(mock_catalogue_df, test_path)
                    mock_write.assert_called_once_with(test_path, compression="snappy")

    def test_update_with_force_meteo_refresh(self, catalogue_with_mocks, tmp_path):
        """Test update with force_meteo_refresh parameter."""
        cat = catalogue_with_mocks
        mock_updater = cat._mock_updater

        # Create existing catalogue
        existing_df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
                "SAFE GRD": [None],
                "datasets": [["SLC"]],
                "horodating": [datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now()],
            }
        )
        existing_df.write_parquet(cat._catalogue_path)

        # Create new data with proper schema
        new_df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
                "SAFE GRD": [None],
                "datasets": [["SLC", "GRD"]],
                "horodating": [datetime.datetime.now()],
                "start date SAFE": [datetime.datetime.now()],
            }
        )

        mock_updater.build_from_listings.return_value = new_df
        mock_updater.core_update.side_effect = lambda x: x
        mock_updater._compute_category_and_conflicts.return_value = existing_df

        with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
            with patch("pathlib.Path.rename") as mock_rename:
                cat.update(force_meteo_refresh=True)
                mock_write.assert_called_once()


class TestS1IWCatalogueIntegration:
    """Integration tests for S1IWCatalogue with real file operations."""

    def test_full_workflow(self, tmp_path, mock_config):
        """Test a complete workflow: create, update, stats."""
        catalogue_path = tmp_path / "catalogue.parquet"

        with (
            patch("s1iw_catalogue.catalogue.load_config") as mock_load_config,
            patch("s1iw_catalogue.catalogue.CatalogueUpdater") as mock_updater_class,
        ):

            mock_load_config.return_value = mock_config
            mock_updater = Mock()
            mock_updater_class.return_value = mock_updater

            # Create mock data
            test_df = pl.DataFrame(
                {
                    "SAFE SLC": ["S1A_IW_SLC_001", "S1A_IW_SLC_002"],
                    "SAFE GRD": [None, None],
                    "datasets": [["SLC"], ["SLC"]],
                    "horodating": [datetime.datetime.now(), datetime.datetime.now()],
                    "start date SAFE": [
                        datetime.datetime.now(),
                        datetime.datetime.now(),
                    ],
                    "category": ["SAR", "SAR"],
                }
            )

            mock_updater.build_from_listings.return_value = test_df
            mock_updater.core_update.return_value = test_df
            mock_updater._compute_category_and_conflicts.return_value = test_df

            # Create catalogue
            cat = S1IWCatalogue(catalogue_path, config=mock_config)

            with patch.object(cat, "_write_parquet_with_metadata") as mock_write:
                cat.create()
                mock_write.assert_called_once()

            # Write the catalogue for real
            test_df.write_parquet(catalogue_path)

            # Test stats
            with patch("s1iw_catalogue.catalogue.CatalogueStats") as mock_stats_class:
                mock_stats = Mock()
                mock_stats.to_dict.return_value = {"total": 2}
                mock_stats_class.return_value = mock_stats

                stats = cat.stats()
                assert stats == {"total": 2}

            # Test metadata
            metadata = cat.get_dataset_metadata()
            assert "SLC" in metadata
