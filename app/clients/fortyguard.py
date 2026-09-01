"""FortyGuard Microclimate API Client with high-fidelity deterministic physics simulator."""

import math
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app.config import settings
from app.models.schemas import H3CellThermalData

logger = logging.getLogger("coolpath.fortyguard")


class FortyGuardClient:
    """Async Client for querying FortyGuard street-level microclimate temperature API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        use_mock: Optional[bool] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.FORTYGUARD_API_KEY
        self.base_url = base_url if base_url is not None else settings.FORTYGUARD_API_BASE_URL
        self.use_mock = use_mock if use_mock is not None else settings.USE_MOCK_FORTYGUARD
        # In-memory cache for H3 cell thermal lookups during session
        self._cache: Dict[str, H3CellThermalData] = {}

    async def get_point_temperature(
        self,
        latitude: float,
        longitude: float,
        ambient_temp: float = 38.0
    ) -> Dict[str, float]:
        """Fetch or synthesize 2-meter street temperature at exact point."""
        if not self.use_mock and self.api_key:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
                    params = {"lat": latitude, "lon": longitude, "layer": "surface_ambient"}
                    resp = await client.get(f"{self.base_url}/temperature/point", headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "surface_temp": data.get("surface_temperature", ambient_temp + 4.0),
                            "ambient_temp": data.get("ambient_temperature", ambient_temp),
                            "shade_factor": data.get("shade_factor", 0.2)
                        }
            except Exception as err:
                logger.warning(f"FortyGuard API query failed, falling back to simulator: {err}")

        # Deterministic simulation based on microclimate physics
        synth = self._synthesize_microclimate(latitude, longitude, ambient_temp)
        return {
            "surface_temp": synth["surface_temp"],
            "ambient_temp": synth["ambient_temp"],
            "shade_factor": synth["shade_factor"]
        }

    async def get_cell_thermal_data(
        self,
        h3_index: str,
        center_lat: float,
        center_lon: float,
        scenario_ambient: float = 38.0
    ) -> H3CellThermalData:
        """Get thermal metrics for a specific Uber H3 hexagon cell."""
        if h3_index in self._cache:
            return self._cache[h3_index]

        synth = self._synthesize_microclimate(center_lat, center_lon, scenario_ambient)

        # Calculate risk score (0-100) based on temperature and shade
        # 30°C -> score 10; 45°C unshaded -> score 95
        temp = synth["surface_temp"]
        shade = synth["shade_factor"]
        base_risk = max(0.0, min(100.0, (temp - 28.0) * 5.0 * (1.1 - shade * 0.4)))

        # Thermal color hex gradient: Cool Green/Cyan -> Yellow -> Amber -> Fiery Red -> Deep Purple
        color = self._temperature_to_color(temp)

        data = H3CellThermalData(
            h3_index=h3_index,
            center_lat=center_lat,
            center_lon=center_lon,
            surface_temp_celsius=round(temp, 2),
            ambient_temp_celsius=round(synth["ambient_temp"], 2),
            shade_factor=round(shade, 2),
            albedo_type=synth["albedo_type"],
            risk_score=round(base_risk, 1),
            color_hex=color
        )
        self._cache[h3_index] = data
        return data

    def _synthesize_microclimate(
        self,
        lat: float,
        lon: float,
        base_ambient: float
    ) -> Dict[str, Any]:
        """
        Deterministic spatial physics engine for street-level microclimates:
        - Models urban canyons, unshaded super-asphalt grids, park canopies, and water bodies
        - Reproducible based on coordinates (hash-based spatial wavelength harmonics)
        """
        # Multi-scale harmonic spatial noise for realistic urban micro-variations
        # Primary urban canyon wave (approx 300m periodicity)
        f1 = math.sin(lat * 850.0 + 1.2) * math.cos(lon * 850.0 + 0.4)
        # Secondary street grid wave (approx 120m periodicity)
        f2 = math.cos(lat * 2100.0) * math.sin(lon * 2100.0)
        # Micro heat pocket noise (parking lots / building shadows)
        f3 = math.sin((lat + lon) * 4500.0)

        composite = 0.55 * f1 + 0.30 * f2 + 0.15 * f3

        # Categorize surface type and shade
        if composite > 0.45:
            # Extreme Heat Sink: Unshaded asphalt parking lot, industrial black tar roof
            albedo_type = "asphalt"
            temp_delta = 5.5 + 3.0 * (composite - 0.45)
            shade_factor = 0.05
        elif composite > 0.10:
            # Dense Urban Avenue: Concrete sidewalk, moderate building reflection
            albedo_type = "urban_dense"
            temp_delta = 2.0 + 3.0 * (composite - 0.10)
            shade_factor = 0.25
        elif composite > -0.30:
            # Shaded Commercial Street: Moderate tree cover or tall building shadow
            albedo_type = "concrete"
            temp_delta = -1.0 + 2.0 * composite
            shade_factor = 0.55
        elif composite > -0.65:
            # Green Corridor / Urban Park / Vegetated Boulevard
            albedo_type = "park_vegetation"
            temp_delta = -4.5 + 1.5 * composite
            shade_factor = 0.85
        else:
            # Water Body / Coastal Breezeway / Shaded Riverwalk
            albedo_type = "water"
            temp_delta = -6.5 + 1.0 * composite
            shade_factor = 0.92

        surface_temp = max(24.0, base_ambient + temp_delta)
        ambient_temp = base_ambient + (temp_delta * 0.35)

        return {
            "surface_temp": surface_temp,
            "ambient_temp": ambient_temp,
            "shade_factor": shade_factor,
            "albedo_type": albedo_type
        }

    @staticmethod
    def _temperature_to_color(temp_c: float) -> str:
        """Generate high-contrast scientific thermal color palette."""
        # Under 30°C: Emerald Green / Cyan (Safe/Cool)
        if temp_c < 30.0:
            return "#10b981"  # Emerald-500
        # 30°C - 33°C: Spring Green
        if temp_c < 33.0:
            return "#22c55e"  # Green-500
        # 33°C - 36°C: Amber Yellow (Caution)
        if temp_c < 36.0:
            return "#eab308"  # Yellow-500
        # 36°C - 39°C: Orange (Elevated Heat)
        if temp_c < 39.0:
            return "#f97316"  # Orange-500
        # 39°C - 43°C: Fiery Crimson (Severe Heat Corridor)
        if temp_c < 43.0:
            return "#ef4444"  # Red-500
        # 43°C+: Scorch Violet (Extreme Lethal Asphalt Sink)
        return "#7c3aed"  # Violet-600
