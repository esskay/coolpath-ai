"""Unit tests for Thermal Graph Routing Engine and Cost Function."""

import pytest
from app.clients.fortyguard import FortyGuardClient
from app.core.h3_grid import H3GridManager
from app.core.routing_engine import ThermalRoutingEngine, haversine_distance_meters
from app.models.schemas import GeoCoordinate, RouteRequest, WorkerProfile


def test_haversine_distance():
    """Verify distance computation between two known points."""
    # NYC Times Square to Grand Central (~800m)
    dist = haversine_distance_meters(40.7580, -73.9855, 40.7527, -73.9772)
    assert 700.0 < dist < 1000.0


@pytest.mark.asyncio
async def test_dual_route_calculation():
    """Verify dual route calculation produces baseline and thermal mitigated paths."""
    client = FortyGuardClient(use_mock=True)
    manager = H3GridManager(client)
    engine = ThermalRoutingEngine(client, manager)

    req = RouteRequest(
        origin=GeoCoordinate(latitude=33.4445, longitude=-112.0805),
        destination=GeoCoordinate(latitude=33.4545, longitude=-112.0650),
        profile=WorkerProfile.COURIER_CYCLIST,
        alpha=2.0,
        temp_threshold=33.0,
        scenario_id="phoenix_downtown"
    )

    resp = await engine.calculate_dual_routes(req, ambient_temp=42.0)

    assert resp.baseline_route is not None
    assert resp.coolpath_route is not None

    # Both routes must have valid GeoJSON LineString coordinates
    assert resp.baseline_route.geometry["type"] == "LineString"
    assert resp.coolpath_route.geometry["type"] == "LineString"
    assert len(resp.baseline_route.geometry["coordinates"]) >= 2
    assert len(resp.coolpath_route.geometry["coordinates"]) >= 2

    # CoolPath route should have lower or equal mean temperature than unmitigated baseline
    assert resp.coolpath_route.stats.mean_temperature_celsius <= resp.baseline_route.stats.mean_temperature_celsius + 0.1
    assert "temp_reduction_avg_celsius" in resp.delta_metrics
    assert "heat_exposure_saved_percent" in resp.delta_metrics
    assert resp.computation_time_ms > 0
