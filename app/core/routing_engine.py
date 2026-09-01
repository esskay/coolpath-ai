"""
CoolPath AI - Thermal Graph Routing Engine
Constructs urban road networks and runs Dijkstra / A* graph optimization with thermal penalty weights.
"""

import math
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import networkx as nx
from app.clients.fortyguard import FortyGuardClient
from app.core.h3_grid import H3GridManager
from app.core.physics import (
    calculate_solar_position,
    calculate_street_shadow_fraction,
    calculate_utci_approximation,
    HumanThermoregulationModel,
    generate_autonomous_refuges_if_needed,
    calculate_fleet_degradation_roi,
)
from app.models.schemas import (
    DualRouteResponse,
    GeoCoordinate,
    RouteOption,
    RouteRequest,
    RouteStats,
    ThermalProfilePoint,
    WorkerProfile,
)

logger = logging.getLogger("coolpath.routing_engine")


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in meters."""
    r = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class ThermalRoutingEngine:
    """Computes dual routes comparing baseline distance routing vs CoolPath thermal routing."""

    def __init__(self, fortyguard_client: FortyGuardClient, h3_manager: H3GridManager):
        self.client = fortyguard_client
        self.h3_manager = h3_manager

    def build_urban_graph(
        self,
        center_lat: float,
        center_lon: float,
        radius_km: float = 2.5,
        grid_density: int = 15
    ) -> nx.DiGraph:
        """
        Construct a detailed directed graph representing the street & pedestrian network
        covering the designated urban microclimate bounding box.
        """
        graph = nx.DiGraph()

        # Spatial step in degrees (roughly ~100m - 150m between node intersections)
        lat_step = (radius_km / 111.0) / (grid_density / 2.0)
        lon_step = (radius_km / (111.0 * math.cos(math.radians(center_lat)))) / (grid_density / 2.0)

        nodes_grid: Dict[Tuple[int, int], str] = {}

        # 1. Create grid intersection nodes
        for i in range(-grid_density, grid_density + 1):
            for j in range(-grid_density, grid_density + 1):
                # Add organic curvature to simulate real city streets
                jitter_lat = math.sin(j * 0.4) * (lat_step * 0.12)
                jitter_lon = math.cos(i * 0.4) * (lon_step * 0.12)

                node_lat = center_lat + (i * lat_step) + jitter_lat
                node_lon = center_lon + (j * lon_step) + jitter_lon
                node_id = f"n_{i}_{j}"

                graph.add_node(node_id, lat=node_lat, lon=node_lon)
                nodes_grid[(i, j)] = node_id

        # 2. Add standard street edges (grid connections in 4 cardinal directions)
        for (i, j), u in nodes_grid.items():
            u_lat = graph.nodes[u]["lat"]
            u_lon = graph.nodes[u]["lon"]

            for di, dj in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                target_key = (i + di, j + dj)
                if target_key in nodes_grid:
                    v = nodes_grid[target_key]
                    v_lat = graph.nodes[v]["lat"]
                    v_lon = graph.nodes[v]["lon"]
                    length_m = haversine_distance_meters(u_lat, u_lon, v_lat, v_lon)
                    graph.add_edge(u, v, length_m=length_m)

            # Add diagonal pedestrian greenways and alleyways for high-connectivity routing
            if (i + j) % 2 == 0:
                for di, dj in [(1, 1), (-1, -1), (1, -1), (-1, 1)]:
                    target_key = (i + di, j + dj)
                    if target_key in nodes_grid:
                        v = nodes_grid[target_key]
                        v_lat = graph.nodes[v]["lat"]
                        v_lon = graph.nodes[v]["lon"]
                        length_m = haversine_distance_meters(u_lat, u_lon, v_lat, v_lon)
                        graph.add_edge(u, v, length_m=length_m)

        return graph

    async def assign_thermal_weights(
        self,
        graph: nx.DiGraph,
        alpha: float,
        temp_threshold: float,
        ambient_temp: float = 38.0,
        departure_hour: float = 14.0
    ) -> Tuple[float, float]:
        """
        Evaluate edge microclimate temperatures, compute 4D solar canyon shadows,
        and calculate Pareto thermal penalty weights.
        """
        # Get solar position for the current departure time
        center_node = list(graph.nodes())[0]
        ref_lat = graph.nodes[center_node]["lat"]
        ref_lon = graph.nodes[center_node]["lon"]
        solar_elevation, solar_azimuth = calculate_solar_position(ref_lat, ref_lon, departure_hour)

        for u, v, data in graph.edges(data=True):
            u_lat, u_lon = graph.nodes[u]["lat"], graph.nodes[u]["lon"]
            v_lat, v_lon = graph.nodes[v]["lat"], graph.nodes[v]["lon"]

            # Edge midpoint
            mid_lat = (u_lat + v_lat) / 2.0
            mid_lon = (u_lon + v_lon) / 2.0

            # Get H3 cell for edge
            h3_cell = self.h3_manager.latlng_to_h3(mid_lat, mid_lon, resolution=9)
            thermal_data = await self.client.get_cell_thermal_data(
                h3_index=h3_cell,
                center_lat=mid_lat,
                center_lon=mid_lon,
                scenario_ambient=ambient_temp
            )

            raw_surface_temp = thermal_data.surface_temp_celsius
            length_m = data.get("length_m", 100.0)

            # 4D Solar & Canyon Shadow Simulation
            is_shaded, shade_frac, delta_mrt = calculate_street_shadow_fraction(
                u_lat, u_lon, v_lat, v_lon,
                solar_elevation_deg=solar_elevation,
                solar_azimuth_deg=solar_azimuth
            )

            # Effective perceived surface/ambient temperature under dynamic shadow
            # Tree canopy or building shadow drops microclimate temperature by 2.0°C - 5.5°C
            effective_surface_temp = raw_surface_temp - (shade_frac * 4.5)
            
            # Universal Thermal Climate Index (UTCI) approximation
            utci = calculate_utci_approximation(
                air_temp_c=effective_surface_temp,
                mrt_delta_c=delta_mrt,
                wind_speed_ms=1.8,
                relative_humidity_pct=35.0
            )

            # Thermal penalty cost formula: Incorporates both UTCI and surface heat
            heat_excess = max(0.0, utci - temp_threshold)
            
            # Additional bonus for shaded corridors
            shade_discount = 0.85 if is_shaded else 1.0
            thermal_penalty_factor = (1.0 + (alpha * heat_excess)) * shade_discount
            coolpath_cost = length_m * max(0.5, thermal_penalty_factor)

            # Store rich edge attributes
            data["temperature_c"] = effective_surface_temp
            data["mrt_delta_c"] = delta_mrt
            data["utci_c"] = utci
            data["is_shaded"] = is_shaded
            data["shade_fraction"] = shade_frac
            data["h3_index"] = h3_cell
            data["weight_baseline"] = length_m  # Standard distance-only routing
            data["weight_coolpath"] = coolpath_cost  # FortyGuard thermal routing

        return solar_elevation, solar_azimuth

    def find_nearest_node(self, graph: nx.DiGraph, lat: float, lon: float) -> str:
        """Find the closest graph node to a geographic coordinate."""
        best_node = ""
        min_dist = float("inf")

        for node, data in graph.nodes(data=True):
            dist = haversine_distance_meters(lat, lon, data["lat"], data["lon"])
            if dist < min_dist:
                min_dist = dist
                best_node = node

        return best_node

    async def calculate_dual_routes(
        self,
        request: RouteRequest,
        ambient_temp: float = 38.0
    ) -> DualRouteResponse:
        """
        Execute dual-route search comparing baseline shortest distance route against
        the CoolPath thermal-mitigated route with full physiological and 4D physics.
        """
        t_start = time.perf_counter()

        # 1. Calibrate profile parameters
        alpha, temp_threshold = self._calibrate_profile(
            request.profile,
            request.alpha,
            request.temp_threshold
        )

        departure_hour = request.departure_hour if request.departure_hour is not None else 14.0

        # 2. Compute bounding midpoint and radius
        origin_lat, origin_lon = request.origin.latitude, request.origin.longitude
        dest_lat, dest_lon = request.destination.latitude, request.destination.longitude

        center_lat = (origin_lat + dest_lat) / 2.0
        center_lon = (origin_lon + dest_lon) / 2.0
        od_dist_km = haversine_distance_meters(origin_lat, origin_lon, dest_lat, dest_lon) / 1000.0
        search_radius_km = max(2.0, od_dist_km * 1.5)

        # 3. Build & thermally weight urban graph with 4D Solar & Canyon Shadows
        graph = self.build_urban_graph(center_lat, center_lon, radius_km=search_radius_km, grid_density=14)
        solar_elevation, solar_azimuth = await self.assign_thermal_weights(
            graph,
            alpha=alpha,
            temp_threshold=temp_threshold,
            ambient_temp=ambient_temp,
            departure_hour=departure_hour
        )

        # 4. Snap origin and destination
        start_node = self.find_nearest_node(graph, origin_lat, origin_lon)
        end_node = self.find_nearest_node(graph, dest_lat, dest_lon)

        # 5. Compute shortest paths for baseline vs CoolPath
        try:
            baseline_path = nx.shortest_path(graph, start_node, end_node, weight="weight_baseline")
        except nx.NetworkXNoPath:
            baseline_path = [start_node, end_node]

        try:
            coolpath_path = nx.shortest_path(graph, start_node, end_node, weight="weight_coolpath")
        except nx.NetworkXNoPath:
            coolpath_path = baseline_path

        # 6. Extract route details, physiological thermoregulation & micro-refuges
        baseline_opt = self._extract_route_option(
            graph=graph,
            path_nodes=baseline_path,
            route_id="baseline",
            name="Standard Shortest Path (OSRM / Google Maps)",
            description="Pure distance optimization. Exposes worker to unmitigated asphalt heat canyons.",
            temp_threshold=temp_threshold,
            profile=request.profile,
            origin_coord=request.origin,
            dest_coord=request.destination,
            enable_refuges=request.enable_refuge_stops,
            is_cold_chain=request.is_cold_chain_fleet,
            ambient_temp=ambient_temp
        )

        coolpath_opt = self._extract_route_option(
            graph=graph,
            path_nodes=coolpath_path,
            route_id="coolpath",
            name="CoolPath AI (FortyGuard Thermal Optimized)",
            description="4D heat-mitigated routing via shaded building canyons, tree canopies, and cool high-albedo corridors.",
            temp_threshold=temp_threshold,
            profile=request.profile,
            origin_coord=request.origin,
            dest_coord=request.destination,
            enable_refuges=request.enable_refuge_stops,
            is_cold_chain=request.is_cold_chain_fleet,
            ambient_temp=ambient_temp
        )

        # 7. Compute delta comparison metrics
        dist_diff_m = coolpath_opt.stats.total_distance_meters - baseline_opt.stats.total_distance_meters
        dist_diff_pct = (
            (dist_diff_m / baseline_opt.stats.total_distance_meters) * 100.0
            if baseline_opt.stats.total_distance_meters > 0 else 0.0
        )
        temp_reduction_avg = baseline_opt.stats.mean_temperature_celsius - coolpath_opt.stats.mean_temperature_celsius
        temp_reduction_peak = baseline_opt.stats.peak_temperature_celsius - coolpath_opt.stats.peak_temperature_celsius
        utci_reduction = baseline_opt.stats.mean_utci_celsius - coolpath_opt.stats.mean_utci_celsius

        base_debt = baseline_opt.stats.accumulated_thermal_debt_score
        cool_debt = coolpath_opt.stats.accumulated_thermal_debt_score
        cardiac_strain_mitigated_pct = (
            ((base_debt - cool_debt) / max(1.0, base_debt)) * 100.0
            if base_debt > 0 else 0.0
        )

        shaded_gain_m = coolpath_opt.stats.shaded_distance_meters - baseline_opt.stats.shaded_distance_meters

        # Fleet economic savings
        fleet_energy_saved_kwh = 0.0
        fleet_cost_saved_usd = 0.0
        if baseline_opt.stats.fleet_metrics and coolpath_opt.stats.fleet_metrics:
            fleet_energy_saved_kwh = max(
                0.0,
                (baseline_opt.stats.fleet_metrics.ev_battery_cooling_overhead_kwh + baseline_opt.stats.fleet_metrics.refrigeration_aux_power_kwh) -
                (coolpath_opt.stats.fleet_metrics.ev_battery_cooling_overhead_kwh + coolpath_opt.stats.fleet_metrics.refrigeration_aux_power_kwh)
            )
            fleet_cost_saved_usd = max(
                0.0,
                baseline_opt.stats.fleet_metrics.total_delivery_cooling_cost_usd -
                coolpath_opt.stats.fleet_metrics.total_delivery_cooling_cost_usd
            )

        base_hei = baseline_opt.stats.heat_exposure_index
        cool_hei = coolpath_opt.stats.heat_exposure_index
        heat_saved_pct = ((base_hei - cool_hei) / base_hei * 100.0) if base_hei > 0 else 0.0

        # Overall Mitigation Score out of 100
        mitigation_score = min(100.0, max(0.0, (temp_reduction_avg * 10.0) + (utci_reduction * 8.0) + (heat_saved_pct * 0.4)))

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        scenario_label = request.scenario_id or "Custom Coordinates"

        departure_str = f"{int(departure_hour):02d}:{int((departure_hour % 1) * 60):02d}"

        return DualRouteResponse(
            scenario_name=scenario_label,
            profile=request.profile,
            alpha_applied=alpha,
            temp_threshold_applied=temp_threshold,
            departure_hour=departure_hour,
            solar_elevation_deg=solar_elevation,
            solar_azimuth_deg=solar_azimuth,
            baseline_route=baseline_opt,
            coolpath_route=coolpath_opt,
            delta_metrics={
                "distance_diff_meters": round(dist_diff_m, 1),
                "distance_diff_percent": round(dist_diff_pct, 1),
                "temp_reduction_avg_celsius": round(max(0.0, temp_reduction_avg), 1),
                "temp_reduction_peak_celsius": round(max(0.0, temp_reduction_peak), 1),
                "utci_reduction_avg_celsius": round(max(0.0, utci_reduction), 1),
                "cardiac_strain_mitigated_pct": round(max(0.0, cardiac_strain_mitigated_pct), 1),
                "shaded_distance_gain_meters": round(max(0.0, shaded_gain_m), 1),
                "heat_exposure_saved_percent": round(max(0.0, heat_saved_pct), 1),
                "heat_mitigation_score": round(mitigation_score, 1),
                "ambient_reference_temp": ambient_temp,
                "departure_time": departure_str,
                "solar_elevation_deg": solar_elevation,
                "solar_azimuth_deg": solar_azimuth,
                "fleet_cooling_energy_saved_kwh": round(fleet_energy_saved_kwh, 3),
                "fleet_cost_saved_usd": round(fleet_cost_saved_usd, 2)
            },
            h3_summary={
                "baseline_unique_cells": len(set(baseline_opt.h3_cells_traversed)),
                "coolpath_unique_cells": len(set(coolpath_opt.h3_cells_traversed)),
                "resolution": request.h3_resolution or 9
            },
            computation_time_ms=round(t_elapsed_ms, 2)
        )

    def _extract_route_option(
        self,
        graph: nx.DiGraph,
        path_nodes: List[str],
        route_id: str,
        name: str,
        description: str,
        temp_threshold: float,
        profile: WorkerProfile,
        origin_coord: GeoCoordinate,
        dest_coord: GeoCoordinate,
        enable_refuges: bool = True,
        is_cold_chain: bool = False,
        ambient_temp: float = 38.0
    ) -> RouteOption:
        """Extract geometry, physiological thermoregulation, and fleet metrics from path nodes."""
        coords: List[List[float]] = [origin_coord.to_geojson_coords()]
        h3_cells: List[str] = []
        thermal_profile: List[ThermalProfilePoint] = []
        raw_points_for_refuge: List[Dict[str, float]] = []

        # Initialize human thermoregulation model
        thermo_model = HumanThermoregulationModel(profile)

        total_dist_m = 0.0
        shaded_dist_m = 0.0
        temps: List[float] = []
        utcis: List[float] = []
        cumulative_heat_index = 0.0
        severe_dist_m = 0.0

        # Transit speed in m/s
        speed_mps = 4.8 if profile == WorkerProfile.COURIER_CYCLIST else (8.0 if profile == WorkerProfile.HEAVY_FLEET else 1.3)

        for i in range(len(path_nodes) - 1):
            u = path_nodes[i]
            v = path_nodes[i + 1]
            u_lat, u_lon = graph.nodes[u]["lat"], graph.nodes[u]["lon"]
            v_lat, v_lon = graph.nodes[v]["lat"], graph.nodes[v]["lon"]

            edge_data = graph.get_edge_data(u, v, default={})
            length_m = edge_data.get("length_m", haversine_distance_meters(u_lat, u_lon, v_lat, v_lon))
            temp_c = edge_data.get("temperature_c", 38.0)
            utci_c = edge_data.get("utci_c", temp_c + 3.0)
            delta_mrt = edge_data.get("mrt_delta_c", 0.0)
            is_shaded = edge_data.get("is_shaded", False)
            h3_cell = edge_data.get("h3_index", self.h3_manager.latlng_to_h3(u_lat, u_lon))

            coords.append([round(v_lon, 6), round(v_lat, 6)])
            h3_cells.append(h3_cell)
            temps.append(temp_c)
            utcis.append(utci_c)

            total_dist_m += length_m
            if is_shaded:
                shaded_dist_m += length_m

            # Step physiological state
            thermo_step = thermo_model.step(
                segment_length_m=length_m,
                ambient_temp_c=temp_c,
                utci_c=utci_c,
                speed_mps=speed_mps
            )

            heat_excess = max(0.0, utci_c - temp_threshold)
            cumulative_heat_index += (heat_excess * length_m)

            is_hotspot = utci_c >= (temp_threshold + 3.0) or utci_c >= 40.0
            if is_hotspot:
                severe_dist_m += length_m

            point_dict = {
                "lat": v_lat,
                "lon": v_lon,
                "distance_along_route_m": total_dist_m,
                "psi": thermo_step["psi"],
                "core_temp_c": thermo_step["core_temp_c"]
            }
            raw_points_for_refuge.append(point_dict)

            thermal_profile.append(
                ThermalProfilePoint(
                    distance_along_route_m=round(total_dist_m, 1),
                    temperature_celsius=round(temp_c, 1),
                    mrt_celsius=round(temp_c + 12.0 + delta_mrt, 1),
                    utci_celsius=round(utci_c, 1),
                    physiological_strain_index=round(thermo_step["psi"], 1),
                    core_temp_estimate_celsius=round(thermo_step["core_temp_c"], 2),
                    is_shaded=is_shaded,
                    is_hotspot=is_hotspot,
                    h3_index=h3_cell
                )
            )

        coords.append(dest_coord.to_geojson_coords())

        duration_min = (total_dist_m / speed_mps) / 60.0 if speed_mps > 0 else 0.0

        mean_t = (sum(temps) / len(temps)) if temps else temp_threshold
        peak_t = max(temps) if temps else temp_threshold
        min_t = min(temps) if temps else temp_threshold
        mean_utci = (sum(utcis) / len(utcis)) if utcis else mean_t
        severe_pct = (severe_dist_m / total_dist_m * 100.0) if total_dist_m > 0 else 0.0
        shaded_pct = (shaded_dist_m / total_dist_m * 100.0) if total_dist_m > 0 else 0.0

        # Thermal stress classification based on UTCI
        if mean_utci >= 42.0 or severe_pct > 60.0:
            stress_cat = "Extreme"
        elif mean_utci >= 38.0 or severe_pct > 35.0:
            stress_cat = "Severe"
        elif mean_utci >= 34.0 or severe_pct > 15.0:
            stress_cat = "High"
        elif mean_utci >= 30.0:
            stress_cat = "Moderate"
        else:
            stress_cat = "Low"

        # Check for autonomous micro-refuges if enabled
        refuges: List[RefugePoint] = []
        if enable_refuges and route_id == "baseline":
            center_lat = (origin_coord.latitude + dest_coord.latitude) / 2.0
            center_lon = (origin_coord.longitude + dest_coord.longitude) / 2.0
            refuges = generate_autonomous_refuges_if_needed(raw_points_for_refuge, profile, center_lat, center_lon)

        # Fleet economic calculations
        fleet_metrics = calculate_fleet_degradation_roi(
            distance_meters=total_dist_m,
            mean_surface_temp_c=mean_t,
            ambient_temp_c=ambient_temp,
            is_cold_chain=is_cold_chain
        )

        stats = RouteStats(
            total_distance_meters=round(total_dist_m, 1),
            estimated_duration_minutes=round(duration_min, 1),
            mean_temperature_celsius=round(mean_t, 1),
            peak_temperature_celsius=round(peak_t, 1),
            min_temperature_celsius=round(min_t, 1),
            mean_utci_celsius=round(mean_utci, 1),
            peak_physiological_strain=round(thermo_model.peak_psi, 1),
            peak_core_temp_celsius=round(thermo_model.current_core_temp, 2),
            accumulated_thermal_debt_score=round(thermo_model.accumulated_thermal_debt, 1),
            shaded_distance_meters=round(shaded_dist_m, 1),
            shaded_percentage=round(shaded_pct, 1),
            heat_exposure_index=round(cumulative_heat_index, 1),
            severe_exposure_distance_meters=round(severe_dist_m, 1),
            severe_exposure_percentage=round(severe_pct, 1),
            thermal_stress_category=stress_cat,
            refuges_recommended=refuges,
            fleet_metrics=fleet_metrics
        )

        return RouteOption(
            route_id=route_id,
            name=name,
            description=description,
            geometry={
                "type": "LineString",
                "coordinates": coords
            },
            h3_cells_traversed=h3_cells,
            stats=stats,
            thermal_profile=thermal_profile
        )

    @staticmethod
    def _calibrate_profile(
        profile: WorkerProfile,
        custom_alpha: Optional[float],
        custom_threshold: Optional[float]
    ) -> Tuple[float, float]:
        """Calibrate alpha and temp_threshold based on worker heat sensitivity profile."""
        defaults = {
            WorkerProfile.COURIER_CYCLIST: (1.8, 33.0),
            WorkerProfile.CONSTRUCTION_OUTDOOR: (2.4, 31.0),
            WorkerProfile.HEAVY_FLEET: (1.2, 36.0),
            WorkerProfile.PEDESTRIAN: (2.0, 32.0),
            WorkerProfile.VULNERABLE_CITIZEN: (3.0, 29.5),
        }
        def_alpha, def_thresh = defaults.get(profile, (1.8, 33.0))
        final_alpha = custom_alpha if custom_alpha is not None else def_alpha
        final_thresh = custom_threshold if custom_threshold is not None else def_thresh
        return final_alpha, final_thresh
