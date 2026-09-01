"""Pydantic data schemas and contracts for CoolPath AI."""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class WorkerProfile(str, Enum):
    """Routing profile tailored to human heat tolerance and transit mode."""
    PEDESTRIAN = "pedestrian"
    COURIER_CYCLIST = "courier_cyclist"
    CONSTRUCTION_OUTDOOR = "construction_outdoor"
    HEAVY_FLEET = "heavy_fleet"
    VULNERABLE_CITIZEN = "vulnerable_citizen"


class GeoCoordinate(BaseModel):
    """Geographic coordinate representation."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")

    def to_tuple(self) -> Tuple[float, float]:
        """Return (lat, lon) tuple."""
        return (self.latitude, self.longitude)

    def to_geojson_coords(self) -> List[float]:
        """Return standard GeoJSON [lon, lat] coordinate format."""
        return [self.longitude, self.latitude]


class RouteRequest(BaseModel):
    """Request payload for dual-route thermal computation."""
    origin: GeoCoordinate
    destination: GeoCoordinate
    profile: WorkerProfile = Field(
        default=WorkerProfile.COURIER_CYCLIST,
        description="Worker or vehicle profile for calibrated thermal sensitivity"
    )
    alpha: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Heat aversion penalty weight. If None, derived from profile."
    )
    temp_threshold: Optional[float] = Field(
        default=None,
        ge=15.0,
        le=60.0,
        description="Thermal threshold (°C) above which penalty scales. If None, derived from profile."
    )
    departure_hour: Optional[float] = Field(
        default=14.0,
        ge=6.0,
        le=20.0,
        description="Time of departure (e.g. 14.5 = 2:30 PM) for 4D solar angle & dynamic building shadow simulation"
    )
    enable_refuge_stops: bool = Field(
        default=True,
        description="Automatically calculate and insert heat refuges/cooling stops when physiological thermal debt exceeds safety limits"
    )
    is_cold_chain_fleet: bool = Field(
        default=False,
        description="Enable Cold-Chain & Fleet EV battery thermal degradation economic calculation"
    )
    h3_resolution: Optional[int] = Field(
        default=9,
        ge=7,
        le=11,
        description="Uber H3 hexagon indexing resolution"
    )
    scenario_id: Optional[str] = Field(
        default=None,
        description="Optional demo scenario ID override"
    )


class RefugePoint(BaseModel):
    """Micro-refuge or cooling node along the route trajectory."""
    id: Optional[str] = Field(default=None, description="Unique identifier")
    name: str
    type: str = Field(..., description="'Indoor Municipal Cooling Hub', 'Misting Station', 'Transit Breezeway'")
    coordinate: GeoCoordinate
    distance_along_route_m: float = Field(default=0.0, description="Meters along route")
    recommended_rest_minutes: float
    temp_celsius: float
    core_temp_reset_celsius: float


class FleetDegradationMetrics(BaseModel):
    """Fleet EV battery & refrigeration compressor degradation and economic impact."""
    ev_battery_cooling_overhead_kwh: float
    refrigeration_aux_power_kwh: float
    battery_cell_degradation_pct: float = Field(default=0.0, description="Battery capacity fade percentage")
    estimated_battery_cell_degradation_cost_usd: float = Field(default=0.0, description="Estimated battery replacement share")
    total_delivery_cooling_cost_usd: float
    co2_cooling_emissions_saved_g: float = Field(default=0.0, description="Estimated CO2 emissions prevented in grams")


class ThermalProfilePoint(BaseModel):
    """Single elevation-style thermal observation point along route trajectory."""
    distance_along_route_m: float
    temperature_celsius: float
    mrt_celsius: float = Field(default=42.0, description="Mean Radiant Temperature taking into account sun & shadows")
    utci_celsius: float = Field(default=38.0, description="Universal Thermal Climate Index (Feels-Like Heat Stress)")
    physiological_strain_index: float = Field(default=3.5, description="Physiological Strain Index (0 to 10 scale)")
    core_temp_estimate_celsius: float = Field(default=37.2, description="Estimated Core Body Temperature in °C")
    is_shaded: bool = Field(default=False, description="True if inside dynamic building or canopy shadow")
    is_hotspot: bool
    h3_index: str


class RouteStats(BaseModel):
    """Comprehensive performance and thermal exposure statistics for a single route."""
    total_distance_meters: float
    estimated_duration_minutes: float
    mean_temperature_celsius: float
    peak_temperature_celsius: float
    min_temperature_celsius: float
    mean_utci_celsius: float = Field(
        default=38.0,
        description="Mean Universal Thermal Climate Index along trajectory"
    )
    peak_physiological_strain: float = Field(
        default=4.0,
        description="Maximum Physiological Strain Index (0-10) reached"
    )
    peak_core_temp_celsius: float = Field(
        default=37.4,
        description="Maximum estimated internal human core body temperature in °C"
    )
    accumulated_thermal_debt_score: float = Field(
        default=0.0,
        description="Cumulative physiological thermal strain (Watts * min)"
    )
    shaded_distance_meters: float = Field(
        default=0.0,
        description="Meters traveled under building canyon or canopy micro-shade"
    )
    shaded_percentage: float = Field(
        default=0.0,
        description="Percentage of route protected from direct solar radiation"
    )
    heat_exposure_index: float = Field(
        ...,
        description="Cumulative thermal degree-meters experienced above critical threshold"
    )
    severe_exposure_distance_meters: float = Field(
        ...,
        description="Distance traveled inside extreme heat zones (>38°C or >Threshold+3°C)"
    )
    severe_exposure_percentage: float
    thermal_stress_category: str = Field(
        ...,
        description="'Low', 'Moderate', 'High', 'Severe', 'Extreme'"
    )
    refuges_recommended: List[RefugePoint] = Field(default_factory=list)
    fleet_metrics: Optional[FleetDegradationMetrics] = None


class RouteOption(BaseModel):
    """Single route trajectory and thermal analysis."""
    route_id: str = Field(..., description="'baseline' or 'coolpath'")
    name: str
    description: str
    geometry: Dict[str, Any] = Field(
        ...,
        description="GeoJSON LineString geometry {'type': 'LineString', 'coordinates': [[lon, lat], ...]}"
    )
    h3_cells_traversed: List[str]
    stats: RouteStats
    thermal_profile: List[ThermalProfilePoint]


class DualRouteResponse(BaseModel):
    """Response containing both baseline standard route and CoolPath thermal mitigated route."""
    scenario_name: str
    profile: WorkerProfile
    alpha_applied: float
    temp_threshold_applied: float
    departure_hour: float = 14.0
    solar_elevation_deg: float = 45.0
    solar_azimuth_deg: float = 210.0
    baseline_route: RouteOption
    coolpath_route: RouteOption
    delta_metrics: Dict[str, Any] = Field(
        ...,
        description="Side-by-side comparison metrics (temperature reduction, physiological savings, fleet ROI)"
    )
    h3_summary: Dict[str, Any]
    computation_time_ms: float


class H3CellThermalData(BaseModel):
    """Hyperlocal FortyGuard microclimate data for an H3 cell."""
    h3_index: str
    center_lat: float
    center_lon: float
    surface_temp_celsius: float
    ambient_temp_celsius: float
    shade_factor: float = Field(..., ge=0.0, le=1.0, description="0.0 = full direct solar, 1.0 = full tree/building shade")
    albedo_type: str = Field(..., description="'asphalt', 'concrete', 'park_vegetation', 'water', 'urban_dense'")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="0 to 100 heat vulnerability score")
    color_hex: str


class HeatmapRequest(BaseModel):
    """Request for H3 microclimate heatmap."""
    center_lat: float
    center_lon: float
    radius_km: float = Field(default=2.5, ge=0.5, le=15.0)
    resolution: int = Field(default=9, ge=7, le=10)
    scenario_id: Optional[str] = None
    departure_hour: Optional[float] = 14.0


class HeatmapResponse(BaseModel):
    """GeoJSON FeatureCollection of H3 hexagons with microclimate temperature attributes."""
    type: str = "FeatureCollection"
    features: List[Dict[str, Any]]
    total_cells: int
    min_temp_celsius: float
    max_temp_celsius: float
    mean_temp_celsius: float
    source: str = "FortyGuard 2-Meter Hyperlocal Microclimate Engine"
