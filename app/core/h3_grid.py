"""Uber H3 Spatial Indexing and Microclimate Grid Manager."""

import math
import logging
from typing import Any, Dict, List, Set, Tuple
import h3
from app.clients.fortyguard import FortyGuardClient
from app.models.schemas import H3CellThermalData, HeatmapResponse

logger = logging.getLogger("coolpath.h3_grid")


class H3GridManager:
    """Manages spatial aggregation, H3 cell tessellation, and GeoJSON heatmap generation."""

    def __init__(self, fortyguard_client: FortyGuardClient):
        self.client = fortyguard_client

    @staticmethod
    def latlng_to_h3(lat: float, lon: float, resolution: int = 9) -> str:
        """
        Convert (lat, lon) to H3 index string.
        Compatible with both H3 v3 (geo_to_h3) and v4 (latlng_to_cell).
        """
        try:
            if hasattr(h3, "latlng_to_cell"):
                return h3.latlng_to_cell(lat, lon, resolution)
            return h3.geo_to_h3(lat, lon, resolution)
        except Exception as err:
            logger.error(f"Failed to convert ({lat}, {lon}) to H3: {err}")
            # Fallback deterministic cell generator for safety
            return f"89{abs(int(lat*100)):04x}{abs(int(lon*100)):04x}"

    @staticmethod
    def h3_to_latlng(h3_index: str) -> Tuple[float, float]:
        """
        Convert H3 index string to (lat, lon) centroid.
        Compatible with both H3 v3 (h3_to_geo) and v4 (cell_to_latlng).
        """
        try:
            if hasattr(h3, "cell_to_latlng"):
                return h3.cell_to_latlng(h3_index)
            return h3.h3_to_geo(h3_index)
        except Exception as err:
            logger.error(f"Failed to get centroid for H3 {h3_index}: {err}")
            return (0.0, 0.0)

    @staticmethod
    def h3_to_boundary_geojson(h3_index: str) -> List[List[float]]:
        """
        Convert H3 cell to GeoJSON polygon ring format: [[lon, lat], [lon, lat], ...].
        Strictly enforces [longitude, latitude] GeoJSON standard and closes the ring.
        """
        try:
            if hasattr(h3, "cell_to_boundary"):
                coords = h3.cell_to_boundary(h3_index)
            else:
                coords = h3.h3_to_geo_boundary(h3_index)

            # coords is list of (lat, lon) pairs
            geojson_ring = [[round(lon, 6), round(lat, 6)] for lat, lon in coords]
            # Ensure polygon ring is explicitly closed
            if geojson_ring and geojson_ring[0] != geojson_ring[-1]:
                geojson_ring.append(geojson_ring[0])
            return geojson_ring
        except Exception as err:
            logger.error(f"Failed to get boundary for H3 {h3_index}: {err}")
            return []

    @staticmethod
    def get_k_ring(center_h3: str, radius: int = 4) -> Set[str]:
        """Get neighboring H3 cells within k-ring radius."""
        try:
            if hasattr(h3, "grid_disk"):
                return set(h3.grid_disk(center_h3, radius))
            return set(h3.k_ring(center_h3, radius))
        except Exception as err:
            logger.error(f"Failed to get k-ring for H3 {center_h3}: {err}")
            return {center_h3}

    async def generate_heatmap_for_region(
        self,
        center_lat: float,
        center_lon: float,
        radius_km: float = 2.0,
        resolution: int = 9,
        ambient_temp: float = 38.0
    ) -> HeatmapResponse:
        """
        Generate complete GeoJSON FeatureCollection of H3 hexagons with thermal metrics
        for the given geographic bounding radius.
        """
        center_h3 = self.latlng_to_h3(center_lat, center_lon, resolution)
        # Approximate k-ring distance: Res 9 edge length is ~170m, diameter ~350m
        # For 2km radius, k approx ceil(2000 / 350) = 6
        k_radius = max(2, min(15, int(math.ceil((radius_km * 1000) / 320.0))))
        cell_indexes = self.get_k_ring(center_h3, k_radius)

        features: List[Dict[str, Any]] = []
        temps: List[float] = []

        for cell_idx in cell_indexes:
            lat, lon = self.h3_to_latlng(cell_idx)
            thermal_data = await self.client.get_cell_thermal_data(
                h3_index=cell_idx,
                center_lat=lat,
                center_lon=lon,
                scenario_ambient=ambient_temp
            )
            boundary = self.h3_to_boundary_geojson(cell_idx)
            if not boundary:
                continue

            temps.append(thermal_data.surface_temp_celsius)

            feature = {
                "type": "Feature",
                "id": cell_idx,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [boundary]
                },
                "properties": {
                    "h3_index": cell_idx,
                    "surface_temp": thermal_data.surface_temp_celsius,
                    "ambient_temp": thermal_data.ambient_temp_celsius,
                    "shade_factor": thermal_data.shade_factor,
                    "albedo_type": thermal_data.albedo_type,
                    "risk_score": thermal_data.risk_score,
                    "fillColor": thermal_data.color_hex,
                    "fillOpacity": 0.45,
                    "strokeColor": "#1e293b",
                    "strokeWeight": 1
                }
            }
            features.append(feature)

        min_t = min(temps) if temps else ambient_temp
        max_t = max(temps) if temps else ambient_temp + 5.0
        mean_t = (sum(temps) / len(temps)) if temps else ambient_temp

        return HeatmapResponse(
            type="FeatureCollection",
            features=features,
            total_cells=len(features),
            min_temp_celsius=round(min_t, 1),
            max_temp_celsius=round(max_t, 1),
            mean_temp_celsius=round(mean_t, 1)
        )

    def route_points_to_h3_sequence(
        self,
        coords: List[List[float]],
        resolution: int = 9
    ) -> List[str]:
        """Convert a list of [lon, lat] route coordinates to an ordered sequence of unique H3 cells."""
        cells: List[str] = []
        for lon, lat in coords:
            cell = self.latlng_to_h3(lat, lon, resolution)
            if not cells or cells[-1] != cell:
                cells.append(cell)
        return cells
