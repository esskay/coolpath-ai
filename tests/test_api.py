"""Integration tests for FastAPI endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify GET /api/v1/health returns 200 OK and system status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "CoolPath AI"


@pytest.mark.asyncio
async def test_scenarios_endpoint():
    """Verify GET /api/v1/scenarios returns preset scenarios."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/scenarios")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "phoenix_downtown" in data["scenarios"]
        assert "dubai_marina" in data["scenarios"]


@pytest.mark.asyncio
async def test_heatmap_endpoint():
    """Verify GET /api/v1/heatmap returns valid GeoJSON FeatureCollection."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/heatmap?lat=33.4484&lon=-112.0740&radius_km=1.0&resolution=9")
        assert res.status_code == 200
        data = res.json()
        assert data["type"] == "FeatureCollection"
        assert data["total_cells"] > 0
        assert len(data["features"]) > 0


@pytest.mark.asyncio
async def test_route_endpoint():
    """Verify POST /api/v1/route computes dual route response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "origin": {"latitude": 33.4445, "longitude": -112.0805},
            "destination": {"latitude": 33.4545, "longitude": -112.0650},
            "profile": "courier_cyclist",
            "alpha": 1.8,
            "temp_threshold": 33.0,
            "scenario_id": "phoenix_downtown"
        }
        res = await client.post("/api/v1/route", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "baseline_route" in data
        assert "coolpath_route" in data
        assert "delta_metrics" in data
