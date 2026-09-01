"""Physics, Solar Geometry, Biometeorology & Fleet Energetics for CoolPath AI.

References:
- Oke, T. R. (1988): Street design and urban canopies
- Moran, D. S. et al. (1998): An environmental Physiological Strain Index (PSI)
- Bröde, P. et al. (2012): Deriving the operational procedure for the Universal Thermal Climate Index (UTCI)
"""

import math
from typing import Dict, List, Optional, Tuple
from app.models.schemas import GeoCoordinate, WorkerProfile, RefugePoint, FleetDegradationMetrics


# Metabolic wattage per worker persona (Watts)
# - Walking: ~140W (moderate pace)
# - E-Bike / Cargo Cycling: ~280W (active pedaling under load)
# - Road / Construction: ~340W (continuous physical labor in gear)
# - Fleet Driver: ~65W (seated, but vehicle HVAC load)
# - Senior / Child: ~90W (lower metabolic capacity, higher heat sensitivity)
METABOLIC_RATE_WATTS: Dict[WorkerProfile, float] = {
    WorkerProfile.PEDESTRIAN: 140.0,
    WorkerProfile.COURIER_CYCLIST: 280.0,
    WorkerProfile.CONSTRUCTION_OUTDOOR: 340.0,
    WorkerProfile.HEAVY_FLEET: 65.0,
    WorkerProfile.VULNERABLE_CITIZEN: 90.0,
}

# Core body temperature thresholds (°C) where heat exhaustion risk escalates
CORE_TEMP_SAFE_LIMIT: Dict[WorkerProfile, float] = {
    WorkerProfile.PEDESTRIAN: 38.3,
    WorkerProfile.COURIER_CYCLIST: 38.5,
    WorkerProfile.CONSTRUCTION_OUTDOOR: 38.2,
    WorkerProfile.HEAVY_FLEET: 38.8,
    WorkerProfile.VULNERABLE_CITIZEN: 37.8,
}


def calculate_solar_position(
    lat: float,
    lon: float,
    departure_hour: float,
    day_of_year: int = 180  # Default to mid-summer (late June)
) -> Tuple[float, float]:
    """Calculate solar elevation and azimuth using Cooper's approximation."""
    # Declination angle
    declination = 23.45 * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))
    decl_rad = math.radians(declination)
    lat_rad = math.radians(lat)

    # 15 degrees rotation per hour from solar noon (12:00)
    hour_angle = (departure_hour - 12.0) * 15.0
    ha_rad = math.radians(hour_angle)

    # Solar elevation angle
    sin_elevation = (
        math.sin(lat_rad) * math.sin(decl_rad) +
        math.cos(lat_rad) * math.cos(decl_rad) * math.cos(ha_rad)
    )
    elevation_rad = math.asin(max(-1.0, min(1.0, sin_elevation)))
    elevation_deg = max(0.0, math.degrees(elevation_rad))

    # Solar azimuth angle (0° = N, 90° = E, 180° = S, 270° = W)
    if elevation_deg > 0.0:
        cos_azimuth = (
            math.sin(decl_rad) * math.cos(lat_rad) -
            math.cos(decl_rad) * math.sin(lat_rad) * math.cos(ha_rad)
        ) / math.cos(elevation_rad)
        cos_azimuth = max(-1.0, min(1.0, cos_azimuth))
        azimuth_deg = math.degrees(math.acos(cos_azimuth))
        if hour_angle > 0:
            azimuth_deg = 360.0 - azimuth_deg
    else:
        azimuth_deg = 180.0

    return (round(elevation_deg, 2), round(azimuth_deg, 2))


def calculate_street_shadow_fraction(
    u_lat: float,
    u_lon: float,
    v_lat: float,
    v_lon: float,
    solar_elevation_deg: float,
    solar_azimuth_deg: float,
    building_height_m: float = 24.0,
    street_width_m: float = 18.0
) -> Tuple[bool, float, float]:
    """
    Ray-cast building shadows across urban street canyons.
    Returns: (is_shaded, shade_factor 0.0-1.0, delta_mrt_celsius)
    """
    if solar_elevation_deg <= 2.0:
        # Near horizon / evening - full canyon shade
        return (True, 0.95, -12.0)

    # Compute street bearing from node u to node v
    delta_lon = v_lon - u_lon
    y = math.sin(math.radians(delta_lon)) * math.cos(math.radians(v_lat))
    x = (
        math.cos(math.radians(u_lat)) * math.sin(math.radians(v_lat)) -
        math.sin(math.radians(u_lat)) * math.cos(math.radians(v_lat)) * math.cos(math.radians(delta_lon))
    )
    street_bearing_deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    # Angle difference between sun azimuth and street axis
    rel_angle = abs(solar_azimuth_deg - street_bearing_deg) % 180.0
    sin_rel = math.sin(math.radians(rel_angle))

    # Shadow cast from canyon walls perpendicular to street corridor
    shadow_length_m = building_height_m / math.tan(math.radians(max(5.0, solar_elevation_deg)))
    perpendicular_shadow_m = shadow_length_m * sin_rel

    # Fraction of road width covered in shade
    shade_fraction = min(1.0, max(0.05, perpendicular_shadow_m / street_width_m))
    is_shaded = shade_fraction >= 0.45

    # Mean Radiant Temperature drops 8-14°C under shade
    delta_mrt = -1.0 * (shade_fraction * 14.0)

    return (is_shaded, round(shade_fraction, 2), round(delta_mrt, 2))


def calculate_utci_approximation(
    air_temp_c: float,
    mrt_delta_c: float = 0.0,
    wind_speed_ms: float = 1.5,
    relative_humidity_pct: float = 40.0
) -> float:
    """
    Universal Thermal Climate Index (UTCI) polynomial approximation.
    Integrates dry bulb air temp, Mean Radiant Temp offset, humidity, and wind.
    """
    # Direct sunlight adds ~12°C to effective MRT; shadows mitigate this
    base_solar_mrt_boost = 12.0
    effective_mrt = air_temp_c + base_solar_mrt_boost + mrt_delta_c

    delta_t_mrt = effective_mrt - air_temp_c
    utci = (
        air_temp_c +
        (0.42 * delta_t_mrt) -
        (1.2 * math.sqrt(max(0.2, wind_speed_ms))) +
        (0.03 * relative_humidity_pct)
    )
    return round(utci, 1)


class HumanThermoregulationModel:
    """
    Gagge 2-node thermoregulation model tracking metabolic heat generation,
    sweat evaporation rate, core body temperature, and Moran's PSI.
    """

    def __init__(self, profile: WorkerProfile):
        self.profile = profile
        self.metabolic_watts = METABOLIC_RATE_WATTS.get(profile, 160.0)
        self.safe_limit = CORE_TEMP_SAFE_LIMIT.get(profile, 38.3)
        self.current_core_temp = 37.0  # Normal human baseline (°C)
        self.accumulated_thermal_debt = 0.0  # Heat stress debt (Watts * min)
        self.total_traversal_minutes = 0.0
        self.peak_psi = 0.0

    def step(self, segment_length_m: float, ambient_temp_c: float, utci_c: float, speed_mps: float = 1.4) -> Dict[str, float]:
        """Step physiological simulation forward for one road segment."""
        duration_min = (segment_length_m / max(0.5, speed_mps)) / 60.0
        self.total_traversal_minutes += duration_min

        # Heat gain = (Metabolic Work - Rest) + Convective transfer from air > skin temp (34°C)
        skin_temp_c = 34.0
        convective_heat_watts = max(0.0, (utci_c - skin_temp_c) * 8.5)
        net_heat_production_watts = (self.metabolic_watts - 75.0) + convective_heat_watts

        # Maximum sweat evaporation capacity in dry air ~260W
        max_sweat_cooling_watts = 260.0
        uncompensated_heat_watts = max(0.0, net_heat_production_watts - max_sweat_cooling_watts)

        # Delta T = Q_stored / Body heat capacity (~260,000 J/°C for 75kg person)
        heat_stored_joules = uncompensated_heat_watts * (duration_min * 60.0)
        delta_core_temp = heat_stored_joules / 260000.0

        if utci_c < 30.0:
            delta_core_temp -= 0.015 * duration_min

        self.current_core_temp = max(36.8, min(41.0, self.current_core_temp + delta_core_temp))
        self.accumulated_thermal_debt += uncompensated_heat_watts * duration_min

        # Moran et al. (1998) Physiological Strain Index (0-10)
        core_fraction = max(0.0, (self.current_core_temp - 37.0) / 2.5)
        simulated_hr = min(180.0, 70.0 + (self.metabolic_watts * 0.22) + (uncompensated_heat_watts * 0.15))
        hr_fraction = max(0.0, (simulated_hr - 60.0) / 120.0)

        psi = min(10.0, max(0.0, (5.0 * core_fraction) + (5.0 * hr_fraction)))
        if psi > self.peak_psi:
            self.peak_psi = psi

        return {
            "core_temp_c": round(self.current_core_temp, 2),
            "psi": round(psi, 1),
            "thermal_debt_wmin": round(self.accumulated_thermal_debt, 1),
            "heart_rate_bpm": round(simulated_hr, 0),
            "is_dangerous": self.current_core_temp >= self.safe_limit or psi >= 7.0
        }

    def reset_with_refuge(self, rest_duration_min: float = 5.0) -> float:
        """Apply cooling recovery at an air-conditioned or misting oasis stop."""
        cooling_recovery = 0.08 * rest_duration_min
        self.current_core_temp = max(37.0, self.current_core_temp - cooling_recovery)
        self.accumulated_thermal_debt = max(0.0, self.accumulated_thermal_debt - (200.0 * rest_duration_min))
        return round(self.current_core_temp, 2)


def generate_autonomous_refuges_if_needed(
    route_points: List[Dict[str, float]],
    profile: WorkerProfile,
    center_lat: float,
    center_lon: float
) -> List[RefugePoint]:
    """Inject cooling oasis points if the traveler reaches dangerous thermal strain."""
    refuges: List[RefugePoint] = []
    
    critical_indices = [
        i for i, pt in enumerate(route_points)
        if pt.get("psi", 0) >= 6.0 or pt.get("core_temp_c", 37.0) >= 38.1
    ]

    if not critical_indices:
        return refuges

    # Trigger refuge near the first critical strain peak
    trigger_idx = critical_indices[0]
    critical_pt = route_points[trigger_idx]

    oasis_lat = critical_pt.get("lat", center_lat) + 0.0012
    oasis_lon = critical_pt.get("lon", center_lon) - 0.0008

    refuges.append(
        RefugePoint(
            id="refuge_hub_1",
            name="Municipal Cool Hub & Misting Station",
            type="Air-Conditioned Public Transit Oasis",
            coordinate=GeoCoordinate(latitude=round(oasis_lat, 6), longitude=round(oasis_lon, 6)),
            temp_celsius=24.5,
            recommended_rest_minutes=5.0,
            core_temp_reset_celsius=37.1
        )
    )

    if len(critical_indices) > 5 and len(route_points) > 10:
        second_idx = min(len(route_points) - 2, trigger_idx + 6)
        second_pt = route_points[second_idx]
        refuges.append(
            RefugePoint(
                id="refuge_hub_2",
                name="Urban Tree Canopy Shade Pavilion",
                type="Dense Microclimate Shade Corridor",
                coordinate=GeoCoordinate(
                    latitude=round(second_pt.get("lat", center_lat) - 0.001, 6),
                    longitude=round(second_pt.get("lon", center_lon) + 0.001, 6)
                ),
                temp_celsius=29.0,
                recommended_rest_minutes=3.5,
                core_temp_reset_celsius=37.3
            )
        )

    return refuges


def calculate_fleet_degradation_roi(
    distance_meters: float,
    mean_surface_temp_c: float,
    ambient_temp_c: float,
    is_cold_chain: bool = False
) -> FleetDegradationMetrics:
    """Calculate EV battery cooling overhead and cold-chain refrigeration savings."""
    distance_km = distance_meters / 1000.0
    trip_duration_hrs = (distance_km / 35.0)  # ~35 km/h urban delivery vehicle speed

    # Heat penalty: ambient > 30°C causes active battery chiller loops to spin up
    thermal_excess = max(0.0, mean_surface_temp_c - 30.0)
    battery_chiller_power_kw = thermal_excess * 0.14  # ~0.14 kW per °C over 30°C
    battery_energy_kwh = battery_chiller_power_kw * trip_duration_hrs

    # Cold chain refrigeration auxiliary power
    refrigeration_aux_kwh = 0.0
    if is_cold_chain:
        cargo_heat_gain_kw = max(0.0, (mean_surface_temp_c - 4.0) * 0.08)  # 4°C payload target
        refrigeration_aux_kwh = (cargo_heat_gain_kw / 2.2) * trip_duration_hrs  # COP ~ 2.2

    # Battery capacity loss: high temp accelerates SEI layer growth on Li-ion cells
    cell_degradation_pct = round(thermal_excess * trip_duration_hrs * 0.0042, 4)

    # Cost savings: $0.18 per kWh + $0.06 per delivery in avoided battery wear
    total_cooling_energy = battery_energy_kwh + refrigeration_aux_kwh
    energy_cost_usd = total_cooling_energy * 0.18
    battery_wear_cost_usd = (cell_degradation_pct / 100.0) * 4500.0  # Replacement battery pack share

    total_cost_usd = round(energy_cost_usd + battery_wear_cost_usd, 2)

    return FleetDegradationMetrics(
        ev_battery_cooling_overhead_kwh=round(battery_energy_kwh, 3),
        refrigeration_aux_power_kwh=round(refrigeration_aux_kwh, 3),
        battery_cell_degradation_pct=cell_degradation_pct,
        total_delivery_cooling_cost_usd=total_cost_usd
    )
