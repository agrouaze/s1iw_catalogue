# tests/conftest.py (add to existing conftest.py)

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import box


@pytest.fixture
def mock_ww3_dataset():
    """Create a mock WW3 xarray dataset."""
    # Create coordinates
    lons = np.linspace(-10, 10, 20)
    lats = np.linspace(45, 55, 20)
    times = pd.date_range("2023-01-15 00:00:00", periods=3, freq="3H")
    
    # Create data
    hs_data = np.random.rand(len(times), len(lats), len(lons)) * 5  # 0-5m wave height
    t01_data = np.random.rand(len(times), len(lats), len(lons)) * 15 + 5  # 5-20s period
    
    # Create dataset
    ds = xr.Dataset(
        {
            "hs": (["time", "latitude", "longitude"], hs_data),
            "t01": (["time", "latitude", "longitude"], t01_data),
        },
        coords={
            "time": times,
            "latitude": lats,
            "longitude": lons,
        }
    )
    return ds


@pytest.fixture
def mock_catalogue_df():
    """Create a mock catalogue DataFrame with polygons in the Iroise Sea."""
    polygons = []
    for lon in [-5, -4.5, -4]:
        for lat in [48, 48.5]:
            poly = box(lon - 0.2, lat - 0.2, lon + 0.2, lat + 0.2)
            polygons.append(poly)
    
    data = {
        "SAFE SLC": [f"S1A_IW_SLC_{i:03d}" for i in range(len(polygons))],
        "SAFE GRD": [f"S1A_IW_GRD_{i:03d}" for i in range(len(polygons))],
        "start date SAFE": [
            pd.Timestamp("2023-01-15 12:00:00") + pd.Timedelta(hours=i)
            for i in range(len(polygons))
        ],
        "polygon SLC": [p.wkt for p in polygons],
        "geometry": polygons,
        "datasets": [["SLC"], ["SLC", "GRD"], ["GRD"]] * (len(polygons) // 3 + 1),
        "polarization": ["VV", "VH", "HV"] * (len(polygons) // 3 + 1),
        "unit": ["S1A", "S1A", "S1B"] * (len(polygons) // 3 + 1),
    }
    return pd.DataFrame(data[:len(polygons)])