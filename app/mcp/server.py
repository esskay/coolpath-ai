"""Model Context Protocol (FastMCP) Server for CoolPath AI Agentic Integrations."""

import asyncio
import logging
from typing import Any, Dict, Optional
from fastmcp import FastMCP

from app.clients.fortyguard import FortyGuardClient
from app.config import settings
from app.core.h3_grid import H3GridManager
from app.core.routing_engine import ThermalRoutingEngine
from app.models.schemas import GeoCoordinate, RouteRequest, WorkerProfile

logger = logging.getLogger("coolpath.mcp")

# Initialize FastMCP Server
mcp = FastMCP("CoolPath AI - Thermal Routing Agent Tools")

# Initialize core engines
fortyguard_client = FortyGuardClient()
h3_manager = H3GridManager(fortyguard_client)
routing_engine = ThermalRoutingEngine(fortyguard_client, h3_manager)


@mcp.tool()
async def find_heat_safe_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    profile: str = "courier_cyclist",
    departure_hour: float = 14.0,
    enable_refuge_stops: bool = True,
    is_cold_chain_fleet: bool = False,
    alpha: float = 1.8,
    temp_threshold: float = 33.0,
    scenario_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compute a 4D heat-mitigated navigation route between two points using FortyGuard 2-meter microclimate AI.
    Features physiological human thermoregulation, dynamic building shadows, autonomous micro-refuges, and fleet economics.
    
    Args:
        origin_lat: Starting point latitude
        origin_lon: Starting point longitude
        dest_lat: Destination latitude
        dest_lon: Destination longitude
        profile: Worker/Transit profile ('courier_cyclist', 'construction_outdoor', 'heavy_fleet', 'pedestrian', 'vulnerable_citizen')
        departure_hour: Departure time (06.0 to 20.0, e.g. 14.5 = 2:30 PM) for 4D solar angle ray-casting
        enable_refuge_stops: Autonomously insert cooling centers if physiological thermal debt exceeds safety limits
        is_cold_chain_fleet: Enable cold-chain cargo & EV battery thermal degradation calculations
        alpha: Heat avoidance multiplier (default 1.8)
        temp_threshold: Base heat-stress threshold temperature in Celsius (default 33.0)
        scenario_id: Optional preset scenario identifier ('phoenix_downtown', 'dubai_marina', 'austin_east')
    """
    try:
        worker_prof = WorkerProfile(profile)
    except ValueError:
        worker_prof = WorkerProfile.COURIER_CYCLIST

    req = RouteRequest(
        origin=GeoCoordinate(latitude=origin_lat, longitude=origin_lon),
        destination=GeoCoordinate(latitude=dest_lat, longitude=dest_lon),
        profile=worker_prof,
        alpha=alpha,
        temp_threshold=temp_threshold,
        departure_hour=departure_hour,
        enable_refuge_stops=enable_refuge_stops,
        is_cold_chain_fleet=is_cold_chain_fleet,
        scenario_id=scenario_id
    )

    ambient = 38.0
    if scenario_id and scenario_id in settings.PRESET_SCENARIOS:
        ambient = settings.PRESET_SCENARIOS[scenario_id].get("baseline_ambient_temp", 38.0)

    result = await routing_engine.calculate_dual_routes(req, ambient_temp=ambient)

    return {
        "status": "success",
        "scenario": result.scenario_name,
        "profile": result.profile.value,
        "solar_conditions": {
            "departure_time": result.delta_metrics.get("departure_time", "14:00"),
            "solar_elevation_deg": result.solar_elevation_deg,
            "solar_azimuth_deg": result.solar_azimuth_deg
        },
        "baseline_standard_route": {
            "distance_meters": result.baseline_route.stats.total_distance_meters,
            "duration_minutes": result.baseline_route.stats.estimated_duration_minutes,
            "mean_temperature_celsius": result.baseline_route.stats.mean_temperature_celsius,
            "peak_temperature_celsius": result.baseline_route.stats.peak_temperature_celsius,
            "mean_utci_celsius": result.baseline_route.stats.mean_utci_celsius,
            "peak_core_temp_celsius": result.baseline_route.stats.peak_core_temp_celsius,
            "peak_physiological_strain": result.baseline_route.stats.peak_physiological_strain,
            "shaded_percentage": result.baseline_route.stats.shaded_percentage,
            "thermal_stress_category": result.baseline_route.stats.thermal_stress_category,
            "severe_exposure_distance_meters": result.baseline_route.stats.severe_exposure_distance_meters,
            "refuges_recommended": [r.model_dump() for r in result.baseline_route.stats.refuges_recommended]
        },
        "coolpath_mitigated_route": {
            "distance_meters": result.coolpath_route.stats.total_distance_meters,
            "duration_minutes": result.coolpath_route.stats.estimated_duration_minutes,
            "mean_temperature_celsius": result.coolpath_route.stats.mean_temperature_celsius,
            "peak_temperature_celsius": result.coolpath_route.stats.peak_temperature_celsius,
            "mean_utci_celsius": result.coolpath_route.stats.mean_utci_celsius,
            "peak_core_temp_celsius": result.coolpath_route.stats.peak_core_temp_celsius,
            "peak_physiological_strain": result.coolpath_route.stats.peak_physiological_strain,
            "shaded_percentage": result.coolpath_route.stats.shaded_percentage,
            "thermal_stress_category": result.coolpath_route.stats.thermal_stress_category,
            "severe_exposure_distance_meters": result.coolpath_route.stats.severe_exposure_distance_meters,
            "fleet_metrics": result.coolpath_route.stats.fleet_metrics.model_dump() if result.coolpath_route.stats.fleet_metrics else None
        },
        "benefit_comparison": {
            "temp_reduction_avg_celsius": f"{result.delta_metrics['temp_reduction_avg_celsius']}°C",
            "utci_reduction_avg_celsius": f"{result.delta_metrics.get('utci_reduction_avg_celsius', 0)}°C",
            "cardiac_strain_mitigated": f"{result.delta_metrics.get('cardiac_strain_mitigated_pct', 0)}%",
            "shaded_corridor_gain_meters": f"+{result.delta_metrics.get('shaded_distance_gain_meters', 0)}m",
            "heat_exposure_saved_percent": f"{result.delta_metrics['heat_exposure_saved_percent']}%",
            "distance_overhead": f"+{result.delta_metrics['distance_diff_meters']}m (+{result.delta_metrics['distance_diff_percent']}%)",
            "fleet_cost_saved_usd": f"${result.delta_metrics.get('fleet_cost_saved_usd', 0.0)}",
            "fleet_cooling_energy_saved_kwh": f"{result.delta_metrics.get('fleet_cooling_energy_saved_kwh', 0.0)} kWh",
            "safety_mitigation_score": f"{result.delta_metrics['heat_mitigation_score']}/100"
        },
        "coolpath_geojson": result.coolpath_route.geometry
    }


@mcp.tool()
async def get_area_heat_risk(
    center_lat: float,
    center_lon: float,
    radius_km: float = 2.0,
    resolution: int = 9,
    scenario_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get aggregated heat risk statistics and microclimate classification for an urban area.
    
    Args:
        center_lat: Center latitude
        center_lon: Center longitude
        radius_km: Scan radius in kilometers (default 2.0)
        resolution: Uber H3 spatial resolution (default 9)
        scenario_id: Optional scenario identifier
    """
    ambient = 38.0
    if scenario_id and scenario_id in settings.PRESET_SCENARIOS:
        ambient = settings.PRESET_SCENARIOS[scenario_id].get("baseline_ambient_temp", 38.0)

    geojson_data = await h3_manager.generate_heatmap_geojson(
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=radius_km,
        resolution=resolution,
        ambient_temp=ambient
    )

    features = geojson_data["features"]
    temps = [f["properties"]["surface_temp_celsius"] for f in features]
    risk_scores = [f["properties"]["risk_score"] for f in features]

    return {
        "status": "success",
        "h3_cells_evaluated": len(features),
        "min_temp_celsius": min(temps) if temps else ambient,
        "max_temp_celsius": max(temps) if temps else ambient,
        "mean_temp_celsius": round(sum(temps) / len(temps), 1) if temps else ambient,
        "average_risk_score": round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 50.0,
        "severe_hotspots_count": len([r for r in risk_scores if r >= 75.0]),
        "cool_refuges_count": len([r for r in risk_scores if r <= 35.0]),
        "source": "FortyGuard 2-Meter Hyperlocal Microclimate Engine"
    }


if __name__ == "__main__":
    mcp.run()
