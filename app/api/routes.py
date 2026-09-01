"""FastAPI API routes for CoolPath AI."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.clients.fortyguard import FortyGuardClient
from app.config import settings
from app.core.h3_grid import H3GridManager
from app.core.routing_engine import ThermalRoutingEngine
from app.models.schemas import (
    DualRouteResponse,
    HeatmapResponse,
    RouteRequest,
)

logger = logging.getLogger("coolpath.api")

router = APIRouter(prefix="/api/v1", tags=["CoolPath Routing & Heatmap"])

# Dependency instances
fortyguard_client = FortyGuardClient()
h3_manager = H3GridManager(fortyguard_client)
routing_engine = ThermalRoutingEngine(fortyguard_client, h3_manager)


@router.get("/health", response_model=Dict[str, Any])
async def health_check() -> Dict[str, Any]:
    """Check system health, FortyGuard connection status, and operational configuration."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "simulation_fallback" if fortyguard_client.use_mock or not fortyguard_client.api_key else "live_fortyguard_api",
        "h3_resolution_default": settings.DEFAULT_H3_RESOLUTION,
        "default_alpha": settings.DEFAULT_ALPHA,
        "default_temp_threshold": settings.DEFAULT_TEMP_THRESHOLD
    }


@router.get("/scenarios", response_model=Dict[str, Any])
async def get_preset_scenarios() -> Dict[str, Any]:
    """Retrieve curated demo city scenarios with severe heat islands and cool corridors."""
    return {
        "status": "success",
        "count": len(settings.PRESET_SCENARIOS),
        "scenarios": settings.PRESET_SCENARIOS
    }


@router.post("/route", response_model=DualRouteResponse)
async def compute_dual_route(request: RouteRequest) -> DualRouteResponse:
    """
    Compute dual routes:
    1. Standard Shortest Distance Route (Baseline)
    2. CoolPath Thermal-Mitigated Route (Heat Aversion Optimized)
    Includes side-by-side thermal exposure statistics and elevation-style temperature profile.
    """
    try:
        ambient = 38.0
        if request.scenario_id and request.scenario_id in settings.PRESET_SCENARIOS:
            ambient = settings.PRESET_SCENARIOS[request.scenario_id].get("baseline_ambient_temp", 38.0)

        response = await routing_engine.calculate_dual_routes(request, ambient_temp=ambient)
        return response
    except Exception as err:
        logger.exception("Error computing dual routes")
        raise HTTPException(status_code=500, detail=f"Thermal routing calculation failed: {str(err)}")


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_h3_heatmap(
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Center latitude"),
    lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Center longitude"),
    center_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Center latitude alias"),
    center_lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Center longitude alias"),
    radius_km: float = Query(2.5, ge=0.5, le=10.0, description="Radius in kilometers"),
    resolution: int = Query(9, ge=7, le=10, description="Uber H3 hexagon resolution"),
    scenario_id: Optional[str] = Query(None, description="Optional preset scenario key"),
    departure_hour: Optional[float] = Query(14.0, description="Time of day")
) -> HeatmapResponse:
    """
    Generate GeoJSON FeatureCollection of Uber H3 hexagons with 2-meter FortyGuard
    microclimate temperatures, risk scores, and color styling.
    """
    effective_lat = lat if lat is not None else center_lat
    effective_lon = lon if lon is not None else center_lon

    if effective_lat is None or effective_lon is None:
        raise HTTPException(status_code=422, detail="Missing required latitude/longitude parameters ('lat' or 'center_lat')")

    try:
        ambient = 38.0
        if scenario_id and scenario_id in settings.PRESET_SCENARIOS:
            ambient = settings.PRESET_SCENARIOS[scenario_id].get("baseline_ambient_temp", 38.0)

        heatmap = await h3_manager.generate_heatmap_for_region(
            center_lat=effective_lat,
            center_lon=effective_lon,
            radius_km=radius_km,
            resolution=resolution,
            ambient_temp=ambient
        )
        return heatmap
    except Exception as err:
        logger.exception("Error generating H3 heatmap")
        raise HTTPException(status_code=500, detail=f"H3 heatmap generation failed: {str(err)}")
