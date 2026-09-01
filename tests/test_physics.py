"""Unit tests for the Physics, Solar Geometry, Biometeorology & Fleet Energetics module."""

import pytest
from app.core.physics import (
    calculate_solar_position,
    calculate_street_shadow_fraction,
    calculate_utci_approximation,
    HumanThermoregulationModel,
    generate_autonomous_refuges_if_needed,
    calculate_fleet_degradation_roi,
    METABOLIC_RATE_WATTS,
    CORE_TEMP_SAFE_LIMIT,
)
from app.models.schemas import WorkerProfile


def test_solar_position_calculation():
    """Verify solar elevation and azimuth across different hours of the day."""
    # Noon in Phoenix
    elev_noon, azim_noon = calculate_solar_position(33.4484, -112.0740, departure_hour=12.0)
    assert elev_noon > 60.0  # High sun at solar noon in summer
    
    # Morning (8 AM)
    elev_morn, azim_morn = calculate_solar_position(33.4484, -112.0740, departure_hour=8.0)
    assert elev_morn < elev_noon
    assert azim_morn < 180.0  # Eastern sky in the morning

    # Evening (6 PM)
    elev_eve, azim_eve = calculate_solar_position(33.4484, -112.0740, departure_hour=18.0)
    assert elev_eve < elev_noon
    assert azim_eve > 180.0  # Western sky in the evening


def test_street_shadow_fraction():
    """Verify 3D building canyon shadow cast calculations."""
    # Low solar angle produces longer shadows
    is_shaded, shade_frac, delta_mrt = calculate_street_shadow_fraction(
        u_lat=33.4484, u_lon=-112.0740,
        v_lat=33.4584, v_lon=-112.0740,
        solar_elevation_deg=20.0,
        solar_azimuth_deg=270.0,
        building_height_m=30.0,
        street_width_m=20.0
    )
    assert shade_frac >= 0.4
    assert delta_mrt < 0.0  # Shadow drops radiant temperature


def test_utci_approximation():
    """Verify Universal Thermal Climate Index calculation."""
    # Shaded street with lower MRT should have lower UTCI than exposed street
    utci_sun = calculate_utci_approximation(air_temp_c=40.0, mrt_delta_c=0.0)
    utci_shade = calculate_utci_approximation(air_temp_c=40.0, mrt_delta_c=-10.0)
    assert utci_shade < utci_sun
    assert utci_sun > 40.0


def test_human_thermoregulation_model():
    """Verify dynamic physiological state stepping, core temperature rise, and PSI."""
    cyclist_model = HumanThermoregulationModel(WorkerProfile.COURIER_CYCLIST)
    assert cyclist_model.current_core_temp == 37.0
    assert cyclist_model.metabolic_watts == 280.0

    # Step in extreme heat (45°C UTCI, 500 meters at 4.8 m/s ~ 104 seconds)
    step1 = cyclist_model.step(segment_length_m=500.0, ambient_temp_c=43.0, utci_c=45.0, speed_mps=4.8)
    assert step1["core_temp_c"] >= 37.0
    assert step1["psi"] > 0.0
    assert step1["thermal_debt_wmin"] > 0.0

    # Test refuge recovery
    prev_core = cyclist_model.current_core_temp
    reset_temp = cyclist_model.reset_with_refuge(rest_duration_min=5.0)
    assert reset_temp < prev_core


def test_autonomous_refuge_generation():
    """Verify autonomous detection and injection of cooling hubs during severe heat."""
    critical_points = [
        {"lat": 33.445, "lon": -112.075, "distance_along_route_m": 400.0, "psi": 7.2, "core_temp_c": 38.4},
        {"lat": 33.446, "lon": -112.074, "distance_along_route_m": 800.0, "psi": 7.8, "core_temp_c": 38.6},
    ]
    refuges = generate_autonomous_refuges_if_needed(critical_points, WorkerProfile.COURIER_CYCLIST, 33.445, -112.075)
    assert len(refuges) > 0
    assert "Cooling" in refuges[0].name or "Misting" in refuges[0].name or "Transit" in refuges[0].name
    assert refuges[0].recommended_rest_minutes > 0.0


def test_fleet_degradation_roi():
    """Verify EV battery chiller overhead and cold-chain ROI calculation."""
    metrics_standard = calculate_fleet_degradation_roi(
        distance_meters=5000.0,
        mean_surface_temp_c=44.0,
        ambient_temp_c=40.0,
        is_cold_chain=False
    )
    assert metrics_standard.ev_battery_cooling_overhead_kwh > 0.0
    assert metrics_standard.total_delivery_cooling_cost_usd > 0.0

    metrics_cold_chain = calculate_fleet_degradation_roi(
        distance_meters=5000.0,
        mean_surface_temp_c=44.0,
        ambient_temp_c=40.0,
        is_cold_chain=True
    )
    # Cold chain has additional refrigeration auxiliary load
    assert metrics_cold_chain.refrigeration_aux_power_kwh > metrics_standard.refrigeration_aux_power_kwh
