"""Unit tests for H3 spatial indexing and GeoJSON polygon generation."""

import pytest
from app.clients.fortyguard import FortyGuardClient
from app.core.h3_grid import H3GridManager


def test_latlng_to_h3_conversion():
    """Verify coordinate to H3 resolution 9 conversion."""
    lat, lon = 33.4484, -112.0740
    h3_idx = H3GridManager.latlng_to_h3(lat, lon, resolution=9)
    assert isinstance(h3_idx, str)
    assert len(h3_idx) > 5

    centroid = H3GridManager.h3_to_latlng(h3_idx)
    assert pytest.approx(centroid[0], abs=0.01) == lat
    assert pytest.approx(centroid[1], abs=0.01) == lon


def test_h3_boundary_geojson_format():
    """Verify H3 polygon boundary follows GeoJSON [lon, lat] closed loop convention."""
    lat, lon = 33.4484, -112.0740
    h3_idx = H3GridManager.latlng_to_h3(lat, lon, resolution=9)
    ring = H3GridManager.h3_to_boundary_geojson(h3_idx)

    assert isinstance(ring, list)
    assert len(ring) >= 6
    # Strictly check [longitude, latitude] bounds
    for pt in ring:
        assert -180.0 <= pt[0] <= 180.0  # lon
        assert -90.0 <= pt[1] <= 90.0    # lat
    # Check ring is closed
    assert ring[0] == ring[-1]


@pytest.mark.asyncio
async def test_heatmap_generation():
    """Verify regional H3 heatmap FeatureCollection generation."""
    client = FortyGuardClient(use_mock=True)
    manager = H3GridManager(client)

    heatmap = await manager.generate_heatmap_for_region(
        center_lat=33.4484,
        center_lon=-112.0740,
        radius_km=1.0,
        resolution=9,
        ambient_temp=40.0
    )

    assert heatmap.type == "FeatureCollection"
    assert heatmap.total_cells > 0
    assert len(heatmap.features) == heatmap.total_cells
    first_feat = heatmap.features[0]
    assert first_feat["geometry"]["type"] == "Polygon"
    assert "surface_temp" in first_feat["properties"]
    assert "fillColor" in first_feat["properties"]
