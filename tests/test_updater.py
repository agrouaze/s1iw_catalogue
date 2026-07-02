"""Comprehensive tests for CatalogueUpdater."""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from s1iw_catalogue.schema import SCHEMA
from s1iw_catalogue.updater import CatalogueUpdater


@pytest.fixture
def dummy_config():
    """Return a dummy configuration dictionary for testing."""
    return {
        "sources": {"cdse": {}, "s1ifr": {}, "familyprod": {}},
        "paths": {
            "reference_listings": {
                "test_slc": {
                    "path": "dummy_slc.txt",
                    "type": "slc",
                    "category": "train",
                },
                "test_grd": {"path": "dummy_grd.txt", "type": "grd", "category": "val"},
            }
        },
        "product_versions": {"l1b": ["A21"], "l1c": ["B17"]},
        "s1ifr-config-file": "dummy_s1ifr.yml",
        "cdse_cache_dir": "/tmp/cache",
    }


@pytest.fixture
def updater(dummy_config):
    return CatalogueUpdater(dummy_config)


@pytest.fixture
def sample_slc_listing(tmp_path):
    content = """
S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE
S1A_IW_SLC__1SDV_20250102T000000_20250102T000027_000002_000002_0002.SAFE
"""
    path = tmp_path / "slc_listing.txt"
    path.write_text(content.strip())
    return path


@pytest.fixture
def sample_grd_listing(tmp_path):
    content = """
S1A_IW_GRDH_1SDV_20250101T000001_20250101T000028_000001_000001_0003.SAFE
S1A_IW_GRDH_1SDV_20250102T000001_20250102T000028_000002_000002_0004.SAFE
"""
    path = tmp_path / "grd_listing.txt"
    path.write_text(content.strip())
    return path


@pytest.fixture
def sample_catalogue_df():
    data = {
        "SAFE SLC": [
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE"
        ],
        "SAFE GRD": [
            "S1A_IW_GRDH_1SDV_20250101T000001_20250101T000028_000001_000001_0003.SAFE"
        ],
        "SAFE OCN": [None],
        "PATH SLC": ["/path/to/slc"],
        "PATH GRD": ["/path/to/grd"],
        "PATH OCN": [None],
        "PATH L1B XSP A21": [None],
        "PATH L1C XSP B17": [None],
        "datasets": [["test_slc", "test_grd"]],
        "category": ["train"],
        "Hs WW3": [None],
        "Tp WW3": [None],
        "U10 ecmwf": [None],
        "v10 ecmwf": [None],
        "start date SAFE": [datetime.datetime(2025, 1, 1)],
        "horodating": [datetime.datetime(2025, 1, 1)],
        "polygon SLC": [None],
        "polygon GRD": [None],
        "S3path SLC": [None],
        "S3path GRD": [None],
        "polarization": ["1SDV"],
        "unit": ["S1A"],
    }
    return pl.DataFrame(data, schema=SCHEMA)


class TestParseSafeName:
    """Tests for parse_safe_name static method."""

    def test_parse_valid_slc(self):
        name = (
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE"
        )
        result = CatalogueUpdater.parse_safe_name(name)
        expected = {
            "safe_name": name,
            "mission": "S1A",
            "product_type": "SLC",
            "polarization": "1SDV",
            "start_date": datetime.datetime(2025, 1, 1, 0, 0, 0),
            "end_date": datetime.datetime(2025, 1, 1, 0, 0, 27),
        }
        assert result == expected

    def test_parse_valid_grd(self):
        name = (
            "S1A_IW_GRDH_1SDV_20250101T000001_20250101T000028_000001_000001_0003.SAFE"
        )
        result = CatalogueUpdater.parse_safe_name(name)
        assert result["product_type"] == "GRDH"
        assert result["start_date"] == datetime.datetime(2025, 1, 1, 0, 0, 1)

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError, match="Unable to parse SAFE name"):
            CatalogueUpdater.parse_safe_name("invalid_name")


class TestReadListings:
    """Tests for reading listing files."""

    def test_read_one_listing_exists(self, tmp_path, updater):
        path = tmp_path / "listing.txt"
        path.write_text(
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE\n"
        )
        df = updater._read_one_listing(path)
        assert df.height == 1
        assert (
            df["safe_name"][0]
            == "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE"
        )

    def test_read_one_listing_not_exists(self, updater):
        df = updater._read_one_listing(Path("/nonexistent"))
        assert df.height == 0

    def test_read_listings_single_file(self, tmp_path, updater):
        path = tmp_path / "listing.txt"
        path.write_text(
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE\n"
        )
        df = updater.read_listings(path)
        assert df.height == 1

    def test_read_listings_directory(self, tmp_path, updater):
        dir_path = tmp_path / "listings"
        dir_path.mkdir()
        (dir_path / "a.txt").write_text(
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE\n"
        )
        (dir_path / "b.txt").write_text(
            "S1A_IW_SLC__1SDV_20250102T000000_20250102T000027_000001_000001_0002.SAFE\n"
        )
        df = updater.read_listings(dir_path)
        assert df.height == 2


class TestBuildFromListings:
    """Tests for build_from_listings."""

    def test_build_from_listings_single_slc(self, tmp_path, updater):
        slc_path = tmp_path / "slc.txt"
        slc_path.write_text(
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE\n"
        )
        listings = {
            "test_slc": {"path": str(slc_path), "type": "slc", "category": "train"}
        }
        df = updater.build_from_listings(listings)
        assert df.height == 1
        assert df.shape[0] == 1
        assert (
            df["SAFE SLC"][0]
            == "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE"
        )
        # assert df["datasets"][0] == ["test_slc"]
        assert df.select(pl.col("datasets")).row(0)[0] == ["test_slc"]
        # category should be set after compute_category step, but build_from_listings doesn't set it.
        # It will be None. So we don't check it here.

    def test_build_from_listings_mixed(self, tmp_path, updater):
        slc_path = tmp_path / "slc.txt"
        slc_path.write_text(
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE\n"
        )
        grd_path = tmp_path / "grd.txt"
        grd_path.write_text(
            "S1A_IW_GRDH_1SDV_20250101T000001_20250101T000028_000001_000001_0003.SAFE\n"
        )
        listings = {
            "test_slc": {"path": str(slc_path), "type": "slc", "category": "train"},
            "test_grd": {"path": str(grd_path), "type": "grd", "category": "val"},
        }
        df = updater.build_from_listings(listings)
        assert df.height == 2
        slc_rows = df.filter(pl.col("SAFE SLC").is_not_null())
        grd_rows = df.filter(pl.col("SAFE GRD").is_not_null())
        assert slc_rows.height == 1
        assert grd_rows.height == 1

    def test_build_from_listings_invalid_type_skipped(self, tmp_path, updater):
        path = tmp_path / "dummy.txt"
        path.write_text(
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE\n"
        )
        listings = {"test": {"path": str(path), "type": "invalid"}}
        df = updater.build_from_listings(listings)
        assert df.height == 0


class TestLocalLinkSlcGrd:
    """Tests for _local_link_slc_grd."""

    def test_local_link_with_matching(self, updater):
        slc_name = (
            "S1A_IW_SLC__1SDV_20250101T000000_20250101T000027_000001_000001_0001.SAFE"
        )
        grd_name = (
            "S1A_IW_GRDH_1SDV_20250101T000001_20250101T000028_000001_000001_0003.SAFE"
        )
        data = {
            "SAFE SLC": [None, slc_name],
            "SAFE GRD": [grd_name, None],
            "SAFE OCN": [None, None],
            "PATH SLC": [None, None],
            "PATH GRD": [None, None],
            "PATH OCN": [None, None],
            "PATH L1B XSP A21": [None, None],
            "PATH L1C XSP B17": [None, None],
            "datasets": [[], []],
            "category": [None, None],
            "Hs WW3": [None, None],
            "Tp WW3": [None, None],
            "U10 ecmwf": [None, None],
            "v10 ecmwf": [None, None],
            "start date SAFE": [
                datetime.datetime(2025, 1, 1, 0, 0, 1),
                datetime.datetime(2025, 1, 1, 0, 0, 0),
            ],
            "horodating": [
                datetime.datetime(2025, 1, 1),
                datetime.datetime(2025, 1, 1),
            ],
            "polygon SLC": [None, None],
            "polygon GRD": [None, None],
            "S3path SLC": [None, None],
            "S3path GRD": [None, None],
            "polarization": ["1SDV", "1SDV"],
            "unit": ["S1A", "S1A"],
        }
        df = pl.DataFrame(data, schema=SCHEMA)
        result = updater._local_link_slc_grd(df)
        linked = result.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_not_null()
        )
        assert linked.height == 2

    def test_local_link_no_match(self, updater):
        grd_name = (
            "S1A_IW_GRDH_1SDV_20250101T000001_20250101T000028_000001_000001_0003.SAFE"
        )
        data = {
            "SAFE SLC": [None],
            "SAFE GRD": [grd_name],
            "SAFE OCN": [None],
            "PATH SLC": [None],
            "PATH GRD": [None],
            "PATH OCN": [None],
            "PATH L1B XSP A21": [None],
            "PATH L1C XSP B17": [None],
            "datasets": [[]],
            "category": [None],
            "Hs WW3": [None],
            "Tp WW3": [None],
            "U10 ecmwf": [None],
            "v10 ecmwf": [None],
            "start date SAFE": [datetime.datetime(2025, 1, 1, 0, 0, 1)],
            "horodating": [datetime.datetime(2025, 1, 1)],
            "polygon SLC": [None],
            "polygon GRD": [None],
            "S3path SLC": [None],
            "S3path GRD": [None],
            "polarization": ["1SDV"],
            "unit": ["S1A"],
        }
        df = pl.DataFrame(data, schema=SCHEMA)
        result = updater._local_link_slc_grd(df)
        linked = result.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_not_null()
        )
        assert linked.height == 0


class TestMergeLinkedRows:
    """Tests for _merge_linked_rows."""

    def test_merge_simple(self, updater):
        slc = "SLC1"
        grd = "GRD1"
        data = {
            "SAFE SLC": [slc, slc],
            "SAFE GRD": [grd, grd],
            "SAFE OCN": [None, None],
            "PATH SLC": ["/path1", "/path2"],
            "PATH GRD": ["/path1", "/path2"],
            "PATH OCN": [None, None],
            "PATH L1B XSP A21": [None, None],
            "PATH L1C XSP B17": [None, None],
            "datasets": [["ds1"], ["ds2"]],
            "category": ["train", "val"],
            "Hs WW3": [None, None],
            "Tp WW3": [None, None],
            "U10 ecmwf": [None, None],
            "v10 ecmwf": [None, None],
            "start date SAFE": [
                datetime.datetime(2025, 1, 1),
                datetime.datetime(2025, 1, 1),
            ],
            "horodating": [
                datetime.datetime(2025, 1, 1, 10),
                datetime.datetime(2025, 1, 1, 12),
            ],
            "polygon SLC": [None, None],
            "polygon GRD": [None, None],
            "S3path SLC": [None, None],
            "S3path GRD": [None, None],
            "polarization": ["1SDV", "1SDV"],
            "unit": ["S1A", "S1A"],
        }
        df = pl.DataFrame(data, schema=SCHEMA)
        merged = updater._merge_linked_rows(df)
        assert merged.height == 1
        datasets = merged["datasets"][0]
        assert sorted(datasets) == ["ds1", "ds2"]
        # Category should be val (priority 2 > train priority 1)
        assert merged["category"][0] == "val"
        assert merged["horodating"][0] == datetime.datetime(2025, 1, 1, 12)


class TestComputeCategoryAndConflicts:
    """Tests for _compute_category_and_conflicts."""

    def test_category_priority_simple(self, updater, tmp_path):
        df = pl.DataFrame(
            {
                "SAFE SLC": ["SLC1"],
                "SAFE GRD": [None],
                "SAFE OCN": [None],
                "PATH SLC": [None],
                "PATH GRD": [None],
                "PATH OCN": [None],
                "PATH L1B XSP A21": [None],
                "PATH L1C XSP B17": [None],
                "datasets": [["train_ds", "val_ds"]],
                "category": [None],
                "Hs WW3": [None],
                "Tp WW3": [None],
                "U10 ecmwf": [None],
                "v10 ecmwf": [None],
                "start date SAFE": [datetime.datetime(2025, 1, 1)],
                "horodating": [datetime.datetime(2025, 1, 1)],
                "polygon SLC": [None],
                "polygon GRD": [None],
                "S3path SLC": [None],
                "S3path GRD": [None],
                "polarization": ["1SDV"],
                "unit": ["S1A"],
            },
            schema=SCHEMA,
        )
        metadata = {
            "train_ds": {"category": "train"},
            "val_ds": {"category": "val"},
        }
        result = updater._compute_category_and_conflicts(df, metadata, tmp_path / "out")
        assert result["category"][0] == "val"

    def test_category_priority_undefined(self, updater, tmp_path):
        df = pl.DataFrame(
            {
                "SAFE SLC": ["SLC1"],
                "SAFE GRD": [None],
                "SAFE OCN": [None],
                "PATH SLC": [None],
                "PATH GRD": [None],
                "PATH OCN": [None],
                "PATH L1B XSP A21": [None],
                "PATH L1C XSP B17": [None],
                "datasets": [["undefined_ds", "train_ds"]],
                "category": [None],
                "Hs WW3": [None],
                "Tp WW3": [None],
                "U10 ecmwf": [None],
                "v10 ecmwf": [None],
                "start date SAFE": [datetime.datetime(2025, 1, 1)],
                "horodating": [datetime.datetime(2025, 1, 1)],
                "polygon SLC": [None],
                "polygon GRD": [None],
                "S3path SLC": [None],
                "S3path GRD": [None],
                "polarization": ["1SDV"],
                "unit": ["S1A"],
            },
            schema=SCHEMA,
        )
        metadata = {
            "undefined_ds": {},
            "train_ds": {"category": "train"},
        }
        result = updater._compute_category_and_conflicts(df, metadata, tmp_path / "out")
        assert result["category"][0] == "train"


class TestMergeCatalogues:
    """Tests for merge_catalogues."""

    def test_merge_two_simple(self, tmp_path, updater):
        df1 = pl.DataFrame(
            {
                "SAFE SLC": ["SLC1", "SLC2"],
                "SAFE GRD": [None, None],
                "SAFE OCN": [None, None],
                "PATH SLC": ["/path1", "/path2"],
                "PATH GRD": [None, None],
                "PATH OCN": [None, None],
                "PATH L1B XSP A21": [None, None],
                "PATH L1C XSP B17": [None, None],
                "datasets": [["ds1"], ["ds2"]],
                "category": ["train", "val"],
                "Hs WW3": [None, None],
                "Tp WW3": [None, None],
                "U10 ecmwf": [None, None],
                "v10 ecmwf": [None, None],
                "start date SAFE": [
                    datetime.datetime(2025, 1, 1),
                    datetime.datetime(2025, 1, 2),
                ],
                "horodating": [
                    datetime.datetime(2025, 1, 1),
                    datetime.datetime(2025, 1, 2),
                ],
                "polygon SLC": [None, None],
                "polygon GRD": [None, None],
                "S3path SLC": [None, None],
                "S3path GRD": [None, None],
                "polarization": ["1SDV", "1SDV"],
                "unit": ["S1A", "S1B"],
            },
            schema=SCHEMA,
        )
        df2 = pl.DataFrame(
            {
                "SAFE SLC": ["SLC2", "SLC3"],
                "SAFE GRD": [None, None],
                "SAFE OCN": [None, None],
                "PATH SLC": ["/path2_alt", "/path3"],
                "PATH GRD": [None, None],
                "PATH OCN": [None, None],
                "PATH L1B XSP A21": [None, None],
                "PATH L1C XSP B17": [None, None],
                "datasets": [["ds2_new"], ["ds3"]],
                "category": ["test", "train"],
                "Hs WW3": [None, None],
                "Tp WW3": [None, None],
                "U10 ecmwf": [None, None],
                "v10 ecmwf": [None, None],
                "start date SAFE": [
                    datetime.datetime(2025, 1, 2),
                    datetime.datetime(2025, 1, 3),
                ],
                "horodating": [
                    datetime.datetime(2025, 1, 3),
                    datetime.datetime(2025, 1, 3),
                ],
                "polygon SLC": [None, None],
                "polygon GRD": [None, None],
                "S3path SLC": [None, None],
                "S3path GRD": [None, None],
                "polarization": ["1SDV", "1SDV"],
                "unit": ["S1B", "S1C"],
            },
            schema=SCHEMA,
        )
        path1 = tmp_path / "cat1.parquet"
        path2 = tmp_path / "cat2.parquet"
        df1.write_parquet(path1)
        df2.write_parquet(path2)
        output = tmp_path / "merged.parquet"

        updater.merge_catalogues([path1, path2], output)

        merged = pl.read_parquet(output)
        assert merged.height == 3
        slc2_row = merged.filter(pl.col("SAFE SLC") == "SLC2")
        assert sorted(slc2_row["datasets"][0]) == ["ds2", "ds2_new"]
        # Category priority: test (3) > val (2) > train (1)
        assert slc2_row["category"][0] == "test"
        assert slc2_row["horodating"][0] == datetime.datetime(2025, 1, 3)


class TestUpdatePresenceColumns:
    """Tests for _update_presence_columns with mocked s1ifr."""

    @patch("s1ifr.get_path_from_base_safe.get_path_from_base_safe")
    def test_update_presence_columns_found(self, mock_get_path, updater):
        mock_get_path.return_value = "/found/path"
        df = pl.DataFrame(
            {
                "SAFE SLC": ["SLC1"],
                "SAFE GRD": [None],
                "SAFE OCN": [None],
                "PATH SLC": [None],
                "PATH GRD": [None],
                "PATH OCN": [None],
                "PATH L1B XSP A21": [None],
                "PATH L1C XSP B17": [None],
                "datasets": [[]],
                "category": [None],
                "Hs WW3": [None],
                "Tp WW3": [None],
                "U10 ecmwf": [None],
                "v10 ecmwf": [None],
                "start date SAFE": [datetime.datetime(2025, 1, 1)],
                "horodating": [datetime.datetime(2025, 1, 1)],
                "polygon SLC": [None],
                "polygon GRD": [None],
                "S3path SLC": [None],
                "S3path GRD": [None],
                "polarization": ["1SDV"],
                "unit": ["S1A"],
            },
            schema=SCHEMA,
        )
        result = updater._update_presence_columns(df)
        assert result["PATH SLC"][0] == "/found/path"

    @patch("s1ifr.get_path_from_base_safe.get_path_from_base_safe")
    def test_update_presence_columns_not_found(self, mock_get_path, updater):
        mock_get_path.return_value = None
        df = pl.DataFrame(
            {
                "SAFE SLC": ["SLC1"],
                "SAFE GRD": [None],
                "SAFE OCN": [None],
                "PATH SLC": [None],
                "PATH GRD": [None],
                "PATH OCN": [None],
                "PATH L1B XSP A21": [None],
                "PATH L1C XSP B17": [None],
                "datasets": [[]],
                "category": [None],
                "Hs WW3": [None],
                "Tp WW3": [None],
                "U10 ecmwf": [None],
                "v10 ecmwf": [None],
                "start date SAFE": [datetime.datetime(2025, 1, 1)],
                "horodating": [datetime.datetime(2025, 1, 1)],
                "polygon SLC": [None],
                "polygon GRD": [None],
                "S3path SLC": [None],
                "S3path GRD": [None],
                "polarization": ["1SDV"],
                "unit": ["S1A"],
            },
            schema=SCHEMA,
        )
        result = updater._update_presence_columns(df)
        assert result["PATH SLC"][0] is None


class TestUpdateDerivedProducts:
    """Tests for _update_derived_products with mocked s1ifr."""

    @patch("s1ifr.paths_safe_product_family.get_products_family")
    def test_update_derived_products(self, mock_get_family, updater):
        import pandas as pd

        mock_df = pd.DataFrame(
            {
                "L1_SLC": ["SLC1"],
                "L1B_XSP_A21": ["/path/to/a21"],
            }
        )
        mock_get_family.return_value = mock_df

        df = pl.DataFrame(
            {
                "SAFE SLC": ["SLC1"],
                "SAFE GRD": [None],
                "SAFE OCN": [None],
                "PATH SLC": [None],
                "PATH GRD": [None],
                "PATH OCN": [None],
                "PATH L1B XSP A21": [None],
                "PATH L1C XSP B17": [None],
                "datasets": [[]],
                "category": [None],
                "Hs WW3": [None],
                "Tp WW3": [None],
                "U10 ecmwf": [None],
                "v10 ecmwf": [None],
                "start date SAFE": [datetime.datetime(2025, 1, 1)],
                "horodating": [datetime.datetime(2025, 1, 1)],
                "polygon SLC": [None],
                "polygon GRD": [None],
                "S3path SLC": [None],
                "S3path GRD": [None],
                "polarization": ["1SDV"],
                "unit": ["S1A"],
            },
            schema=SCHEMA,
        )
        result = updater._update_derived_products(df)
        assert result["PATH L1B XSP A21"][0] == "/path/to/a21"


class TestLinkOcnToGrd:
    """Tests for _link_ocn_to_grd."""

    @patch.object(CatalogueUpdater, "_call_cdse_get_ocn_from_grd")
    def test_link_ocn_to_grd_found(self, mock_ocn, updater):
        mock_ocn.return_value = "OCN1"
        df = pl.DataFrame(
            {
                "SAFE SLC": [None],
                "SAFE GRD": ["GRD1"],
                "SAFE OCN": [None],
                "PATH SLC": [None],
                "PATH GRD": [None],
                "PATH OCN": [None],
                "PATH L1B XSP A21": [None],
                "PATH L1C XSP B17": [None],
                "datasets": [[]],
                "category": [None],
                "Hs WW3": [None],
                "Tp WW3": [None],
                "U10 ecmwf": [None],
                "v10 ecmwf": [None],
                "start date SAFE": [datetime.datetime(2025, 1, 1)],
                "horodating": [datetime.datetime(2025, 1, 1)],
                "polygon SLC": [None],
                "polygon GRD": [None],
                "S3path SLC": [None],
                "S3path GRD": [None],
                "polarization": ["1SDV"],
                "unit": ["S1A"],
            },
            schema=SCHEMA,
        )
        result = updater._link_ocn_to_grd(df)
        assert result["SAFE OCN"][0] == "OCN1"

    @patch.object(CatalogueUpdater, "_call_cdse_get_ocn_from_grd")
    def test_link_ocn_to_grd_not_found_marked(self, mock_ocn, updater):
        mock_ocn.return_value = None
        df = pl.DataFrame(
            {
                "SAFE SLC": [None],
                "SAFE GRD": ["GRD1"],
                "SAFE OCN": [None],
                "PATH SLC": [None],
                "PATH GRD": [None],
                "PATH OCN": [None],
                "PATH L1B XSP A21": [None],
                "PATH L1C XSP B17": [None],
                "datasets": [[]],
                "category": [None],
                "Hs WW3": [None],
                "Tp WW3": [None],
                "U10 ecmwf": [None],
                "v10 ecmwf": [None],
                "start date SAFE": [datetime.datetime(2025, 1, 1)],
                "horodating": [datetime.datetime(2025, 1, 1)],
                "polygon SLC": [None],
                "polygon GRD": [None],
                "S3path SLC": [None],
                "S3path GRD": [None],
                "polarization": ["1SDV"],
                "unit": ["S1A"],
            },
            schema=SCHEMA,
        )
        result = updater._link_ocn_to_grd(df)
        assert result["SAFE OCN"][0] == "NOT_FOUND"
        # assert result["SAFE OCN"][0] is None
