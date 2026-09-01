"""Unit tests for FortyGuard client and microclimate simulator."""

import pytest
from app.clients.fortyguard import FortyGuardClient


@pytest.mark.asyncio
async def test_fortyguard_simulator_point_temp():
    """Verify deterministic microclimate point temperature generator."""
    client = FortyGuardClient(use_mock=True)
    res = await client.get_point_temperature(33.4484, -112.0740, ambient_temp=40.0)

    assert "surface_temp" in res
    assert "ambient_temp" in res
    assert "shade_factor" in res
    assert res["surface_temp"] >= 20.0
    assert 0.0 <= res["shade_factor"] <= 1.0


@pytest.mark.asyncio
async def test_fortyguard_cell_thermal_data():
    """Verify H3 cell thermal data generation and risk scoring."""
    client = FortyGuardClient(use_mock=True)
    data = await client.get_cell_thermal_data(
        h3_index="89269460293ffff",
        center_lat=33.4484,
        center_lon=-112.0740,
        scenario_ambient=42.0
    )

    assert data.h3_index == "89269460293ffff"
    assert data.surface_temp_celsius > 0
    assert data.color_hex.startswith("#")
    assert 0.0 <= data.risk_score <= 100.0
    assert data.albedo_type in ["asphalt", "concrete", "park_vegetation", "water", "urban_dense"]
