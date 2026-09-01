/**
 * CoolPath AI - Frontend Application Controller
 * 4D Hyperlocal Microclimate Thermal Routing Engine
 */

let map;
let heatmapLayerGroup;
let routesLayerGroup;
let refugesLayerGroup;
let originMarker;
let destMarker;
let thermalChart = null;

let currentScenarioId = "phoenix_downtown";
let currentProfile = "courier_cyclist";
let departureHour = 14.0;
let enableRefuges = true;
let isColdChain = false;
let scenariosData = {};

// Default initial coordinates (Phoenix)
let originCoords = [33.4445, -112.0805];
let destCoords = [33.4545, -112.0650];

const PROFILE_CONFIGS = {
  courier_cyclist: { name: "Marcus (E-Bike Courier • 280W)", alpha: 1.8, threshold: 33.0 },
  pedestrian: { name: "Elena (Walking Transit • 140W)", alpha: 2.0, threshold: 32.0 },
  construction_outdoor: { name: "Road Crew (Field Work • 340W)", alpha: 2.4, threshold: 31.0 },
  heavy_fleet: { name: "EV Cold-Chain Delivery", alpha: 1.2, threshold: 36.0 },
  vulnerable_citizen: { name: "Vulnerable Citizen (High Sensitivity)", alpha: 3.0, threshold: 29.5 },
};

document.addEventListener("DOMContentLoaded", async () => {
  lucide.createIcons();
  initMap();
  initChart();
  initEventListeners();
  await loadScenarios();
  await refreshHeatmapAndRoutes();
});

/**
 * Initialize Leaflet Map with OpenStreetMap tiles (100% Open Source & Free)
 */
function initMap() {
  map = L.map("map", {
    center: [33.4484, -112.0740],
    zoom: 14,
    zoomControl: false,
  });

  L.control.zoom({ position: "topright" }).addTo(map);

  // 100% Open & Free OpenStreetMap (OSM) Tile Layer
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors | FortyGuard AI',
    maxZoom: 19,
    className: "dark-tiles",
  }).addTo(map);

  heatmapLayerGroup = L.layerGroup().addTo(map);
  routesLayerGroup = L.layerGroup().addTo(map);
  refugesLayerGroup = L.layerGroup().addTo(map);

  // Custom marker icons
  const originIcon = L.divIcon({
    className: "custom-pin origin-pin",
    html: '<div style="width:28px;height:28px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#06b6d4;border:2px solid #fff;color:#0f172a;font-weight:bold;font-size:12px;box-shadow:0 0 15px rgba(6,182,212,0.6);">A</div>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

  const destIcon = L.divIcon({
    className: "custom-pin dest-pin",
    html: '<div style="width:28px;height:28px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#f43f5e;border:2px solid #fff;color:#fff;font-weight:bold;font-size:12px;box-shadow:0 0 15px rgba(244,63,94,0.6);">B</div>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

  // Origin Marker
  originMarker = L.marker(originCoords, { icon: originIcon, draggable: true }).addTo(map);
  originMarker.bindTooltip("<strong>Origin (A)</strong><br>Drag to reposition", { className: "text-xs" });
  originMarker.on("dragend", () => {
    const pos = originMarker.getLatLng();
    originCoords = [pos.lat, pos.lng];
    computeRoutes();
  });

  // Destination Marker
  destMarker = L.marker(destCoords, { icon: destIcon, draggable: true }).addTo(map);
  destMarker.bindTooltip("<strong>Destination (B)</strong><br>Drag to reposition", { className: "text-xs" });
  destMarker.on("dragend", () => {
    const pos = destMarker.getLatLng();
    destCoords = [pos.lat, pos.lng];
    computeRoutes();
  });
}

/**
 * Initialize Chart.js Multi-Layer Thermal Profile
 */
function initChart() {
  const ctx = document.getElementById("thermalChart").getContext("2d");
  thermalChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Baseline Path Surface (°C)",
          data: [],
          borderColor: "#f43f5e",
          backgroundColor: "rgba(244, 63, 94, 0.1)",
          borderWidth: 2,
          borderDash: [4, 4],
          pointRadius: 1.5,
          tension: 0.3,
          fill: false,
        },
        {
          label: "CoolPath Surface Temp (°C)",
          data: [],
          borderColor: "#06b6d4",
          backgroundColor: "rgba(6, 182, 212, 0.12)",
          borderWidth: 2.5,
          pointRadius: 2,
          tension: 0.3,
          fill: true,
        },
        {
          label: "CoolPath Feels-Like UTCI (°C)",
          data: [],
          borderColor: "#10b981",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "Simulated Core Body Temp (°C)",
          data: [],
          borderColor: "#eab308",
          borderWidth: 1.5,
          pointRadius: 0,
          borderDash: [2, 2],
          fill: false,
          yAxisID: "y1"
        },
        {
          label: "Threshold Tcrit",
          data: [],
          borderColor: "#f59e0b",
          borderWidth: 1.5,
          borderDash: [3, 3],
          pointRadius: 0,
          fill: false,
        }
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            color: "#94a3b8",
            boxWidth: 10,
            font: { size: 10 },
          },
        },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.95)",
          titleColor: "#38bdf8",
          bodyColor: "#f8fafc",
          borderColor: "#334155",
          borderWidth: 1,
          padding: 8,
          titleFont: { size: 11, weight: "bold" },
          bodyFont: { size: 10 },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(51, 65, 85, 0.2)" },
          ticks: { color: "#64748b", font: { size: 9 }, maxTicksLimit: 8 },
        },
        y: {
          position: "left",
          grid: { color: "rgba(51, 65, 85, 0.3)" },
          ticks: {
            color: "#94a3b8",
            font: { size: 9 },
            callback: (val) => `${val}°C`,
          },
        },
        y1: {
          position: "right",
          min: 36.5,
          max: 39.5,
          grid: { drawOnChartArea: false },
          ticks: {
            color: "#eab308",
            font: { size: 9 },
            callback: (val) => `${val}°C Core`,
          }
        }
      },
    },
  });
}

/**
 * Event Listeners
 */
function initEventListeners() {
  // Scenario Dropdown
  document.getElementById("scenarioSelector").addEventListener("change", async (e) => {
    currentScenarioId = e.target.value;
    await applyScenario(currentScenarioId);
  });

  // Calculate Button
  document.getElementById("calculateRouteBtn").addEventListener("click", () => {
    computeRoutes();
  });

  // 4D Time Slider
  const timeSlider = document.getElementById("timeSlider");
  timeSlider.addEventListener("input", (e) => {
    departureHour = parseFloat(e.target.value);
    const hrs = Math.floor(departureHour);
    const mins = Math.round((departureHour % 1) * 60);
    const ampm = hrs >= 12 ? "PM" : "AM";
    const displayHrs = hrs > 12 ? hrs - 12 : hrs;
    document.getElementById("departureTimeLabel").textContent = 
      `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')} (${displayHrs}:${mins.toString().padStart(2, '0')} ${ampm})`;
  });
  timeSlider.addEventListener("change", () => {
    computeRoutes();
  });

  // Refuges and Cold-Chain Toggles
  document.getElementById("toggleRefuges").addEventListener("change", (e) => {
    enableRefuges = e.target.checked;
    computeRoutes();
  });

  document.getElementById("toggleColdChain").addEventListener("change", (e) => {
    isColdChain = e.target.checked;
    const fleetBox = document.getElementById("fleetMetricsContainer");
    if (isColdChain) {
      fleetBox.classList.remove("hidden");
    } else {
      fleetBox.classList.add("hidden");
    }
    computeRoutes();
  });

  // Profile Buttons
  document.querySelectorAll(".profile-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".profile-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentProfile = btn.getAttribute("data-profile");

      const cfg = PROFILE_CONFIGS[currentProfile];
      document.getElementById("profileBadge").textContent = cfg.name;
      document.getElementById("alphaSlider").value = cfg.alpha;
      document.getElementById("alphaVal").textContent = cfg.alpha.toFixed(1);
      document.getElementById("threshSlider").value = cfg.threshold;
      document.getElementById("threshVal").textContent = `${cfg.threshold.toFixed(1)}°C`;

      computeRoutes();
    });
  });

  // Sliders
  const alphaSlider = document.getElementById("alphaSlider");
  alphaSlider.addEventListener("input", (e) => {
    document.getElementById("alphaVal").textContent = parseFloat(e.target.value).toFixed(1);
  });
  alphaSlider.addEventListener("change", () => computeRoutes());

  const threshSlider = document.getElementById("threshSlider");
  threshSlider.addEventListener("input", (e) => {
    document.getElementById("threshVal").textContent = `${parseFloat(e.target.value).toFixed(1)}°C`;
  });
  threshSlider.addEventListener("change", () => computeRoutes());

  // Reset Button
  document.getElementById("resetParamsBtn").addEventListener("click", () => {
    const cfg = PROFILE_CONFIGS[currentProfile];
    alphaSlider.value = cfg.alpha;
    document.getElementById("alphaVal").textContent = cfg.alpha.toFixed(1);
    threshSlider.value = cfg.threshold;
    document.getElementById("threshVal").textContent = `${cfg.threshold.toFixed(1)}°C`;
    computeRoutes();
  });

  // Heatmap Toggle
  document.getElementById("toggleHeatmap").addEventListener("change", (e) => {
    if (e.target.checked) {
      map.addLayer(heatmapLayerGroup);
    } else {
      map.removeLayer(heatmapLayerGroup);
    }
  });

  // Basemap Switcher
  document.getElementById("mapThemeSelector").addEventListener("change", (e) => {
    switchBasemap(e.target.value);
  });
}

/**
 * Basemap provider switcher
 */
let activeTileLayer = null;
function switchBasemap(mode) {
  if (activeTileLayer) {
    map.removeLayer(activeTileLayer);
  }

  let tileUrl = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  let attribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
  let cssClass = "dark-tiles";

  if (mode === "osm_standard") {
    cssClass = "standard-tiles";
  } else if (mode === "opentopo") {
    tileUrl = "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png";
    attribution = '&copy; <a href="https://opentopomap.org">OpenTopoMap</a>';
    cssClass = "standard-tiles";
  }

  activeTileLayer = L.tileLayer(tileUrl, {
    attribution: attribution,
    maxZoom: 19,
    className: cssClass,
  }).addTo(map);
}

/**
 * Load Scenarios from Backend
 */
async function loadScenarios() {
  try {
    const res = await fetch("/api/v1/scenarios");
    const data = await res.json();
    scenariosData = data.scenarios;
  } catch (err) {
    console.error("Failed to fetch scenarios:", err);
  }
}

/**
 * Apply selected scenario
 */
async function applyScenario(scenarioId) {
  const scenario = scenariosData[scenarioId];
  if (!scenario) return;

  originCoords = [scenario.default_origin.latitude, scenario.default_origin.longitude];
  destCoords = [scenario.default_destination.latitude, scenario.default_destination.longitude];

  originMarker.setLatLng(originCoords);
  destMarker.setLatLng(destCoords);

  map.flyTo([scenario.center_lat, scenario.center_lon], 14, { duration: 1.2 });

  await refreshHeatmapAndRoutes();
}

/**
 * Refresh Heatmap & Routes
 */
async function refreshHeatmapAndRoutes() {
  await fetchHeatmap();
  await computeRoutes();
}

/**
 * Fetch H3 Microclimate Heatmap
 */
async function fetchHeatmap() {
  heatmapLayerGroup.clearLayers();

  const center = map.getCenter();
  try {
    const res = await fetch(
      `/api/v1/heatmap?center_lat=${center.lat}&center_lon=${center.lng}&radius_km=3.0&resolution=9&scenario_id=${currentScenarioId}`
    );
    const geojson = await res.json();

    L.geoJSON(geojson, {
      style: (feature) => ({
        fillColor: feature.properties.color_hex || "#10b981",
        weight: 1,
        opacity: 0.7,
        color: "#0f172a",
        fillOpacity: 0.45,
      }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties;
        layer.bindTooltip(
          `<strong>H3: ${p.h3_index}</strong><br>` +
          `Surface Temp: <span style="color:${p.color_hex};font-weight:bold;">${p.surface_temp_celsius}°C</span><br>` +
          `Albedo: ${p.albedo_type}<br>` +
          `Heat Hazard Score: ${p.risk_score}/100`,
          { className: "text-xs", sticky: true }
        );
      },
    }).addTo(heatmapLayerGroup);
  } catch (err) {
    console.error("Failed to load H3 heatmap:", err);
  }
}

/**
 * Compute Dual Routes
 */
async function computeRoutes() {
  routesLayerGroup.clearLayers();
  refugesLayerGroup.clearLayers();

  const alpha = parseFloat(document.getElementById("alphaSlider").value);
  const tempThresh = parseFloat(document.getElementById("threshSlider").value);

  const payload = {
    origin: { latitude: originCoords[0], longitude: originCoords[1] },
    destination: { latitude: destCoords[0], longitude: destCoords[1] },
    profile: currentProfile,
    alpha: alpha,
    temp_threshold: tempThresh,
    departure_hour: departureHour,
    enable_refuge_stops: enableRefuges,
    is_cold_chain_fleet: isColdChain,
    scenario_id: currentScenarioId,
  };

  try {
    const res = await fetch("/api/v1/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    renderRouteResults(data);
  } catch (err) {
    console.error("Route computation failed:", err);
  }
}

/**
 * Render Route Results on Map & UI
 */
function renderRouteResults(data) {
  const baseline = data.baseline_route;
  const coolpath = data.coolpath_route;
  const delta = data.delta_metrics;

  // 1. Draw Baseline Line (Red Dashed)
  const baselineGeo = L.geoJSON(baseline.geometry, {
    style: {
      color: "#f43f5e",
      weight: 4,
      dashArray: "6, 6",
      opacity: 0.85,
      className: "baseline-line",
    },
  }).addTo(routesLayerGroup);

  // 2. Draw CoolPath Line (Vibrant Cyan Solid with Glow)
  const coolpathGeo = L.geoJSON(coolpath.geometry, {
    style: {
      color: "#06b6d4",
      weight: 6,
      opacity: 0.95,
      className: "coolpath-line",
    },
  }).addTo(routesLayerGroup);

  // 3. Render Autonomous Micro-Refuge Markers
  if (baseline.stats.refuges_recommended && baseline.stats.refuges_recommended.length > 0) {
    baseline.stats.refuges_recommended.forEach((refuge) => {
      const oasisIcon = L.divIcon({
        className: "custom-pin oasis-pin",
        html: '<div style="width:30px;height:30px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#10b981;border:2px solid #fff;color:#0f172a;box-shadow:0 0 18px rgba(16,185,129,0.8);"><i data-lucide="umbrella" style="width:16px;height:16px;"></i></div>',
        iconSize: [30, 30],
        iconAnchor: [15, 15],
      });

      const refugeMarker = L.marker([refuge.coordinate.latitude, refuge.coordinate.longitude], {
        icon: oasisIcon,
      }).addTo(refugesLayerGroup);

      refugeMarker.bindPopup(
        `<div class="p-1 space-y-1 text-xs">` +
        `<strong class="text-emerald-400 font-bold block">${refuge.name}</strong>` +
        `<span class="text-slate-300 block">${refuge.type}</span>` +
        `<span class="text-cyan-300 block font-mono">Temp: ${refuge.temp_celsius}°C</span>` +
        `<span class="text-amber-300 block font-semibold">Recommended Rest: ${refuge.recommended_rest_minutes} mins</span>` +
        `<span class="text-emerald-300 block font-bold">Core Temp Reset: ${refuge.core_temp_reset_celsius}°C</span>` +
        `</div>`
      );
    });
    lucide.createIcons();
  }

  // 4. Update Solar Position Chip
  if (delta.solar_elevation_deg !== undefined) {
    document.getElementById("solarPositionChip").textContent = 
      `Elev: ${delta.solar_elevation_deg}° | Azimuth: ${delta.solar_azimuth_deg}°`;
  }

  // 5. Update UI Diagnostic Cards
  document.getElementById("coolMeanTemp").textContent = `${coolpath.stats.mean_temperature_celsius}°C`;
  document.getElementById("coolPeakTemp").textContent = `${coolpath.stats.peak_temperature_celsius}°C`;
  document.getElementById("coolDistance").textContent = `${coolpath.stats.total_distance_meters} m`;
  document.getElementById("coolDuration").textContent = `${coolpath.stats.estimated_duration_minutes} min`;
  document.getElementById("coolStressBadge").textContent = coolpath.stats.thermal_stress_category;

  document.getElementById("baseMeanTemp").textContent = `${baseline.stats.mean_temperature_celsius}°C`;
  document.getElementById("basePeakTemp").textContent = `${baseline.stats.peak_temperature_celsius}°C`;
  document.getElementById("baseDistance").textContent = `${baseline.stats.total_distance_meters} m`;
  document.getElementById("baseDuration").textContent = `${baseline.stats.estimated_duration_minutes} min`;
  document.getElementById("baseStressBadge").textContent = baseline.stats.thermal_stress_category;

  // 6. Update Physiological Cards
  document.getElementById("coolUtciTemp").textContent = `${coolpath.stats.mean_utci_celsius}°C`;
  document.getElementById("coolCoreTemp").textContent = `${coolpath.stats.peak_core_temp_celsius}°C`;
  document.getElementById("coolShadeGain").textContent = `+${delta.shaded_distance_gain_meters || 0} m`;
  document.getElementById("coolShadePct").textContent = `${coolpath.stats.shaded_percentage}%`;
  document.getElementById("cardiacMitigationBadge").textContent = `-${delta.cardiac_strain_mitigated_pct || 0}% Strain`;

  // 7. Update Fleet Economics if enabled
  if (isColdChain) {
    document.getElementById("fleetEnergySaved").textContent = `${delta.fleet_cooling_energy_saved_kwh || 0} kWh`;
    document.getElementById("fleetCostSaved").textContent = `$${delta.fleet_cost_saved_usd || 0.0} / trip`;
  }

  // 8. Update Trajectory Drawer Badges
  const peakDiff = delta.temp_reduction_peak_celsius;
  document.getElementById("heatReductionBadge").textContent = `-${peakDiff}°C Peak Heat Avoided`;
  document.getElementById("deltaHeatSaved").textContent = `${delta.heat_exposure_saved_percent}% Heat Mitigated`;
  document.getElementById("deltaDistance").textContent = `+${delta.distance_diff_meters}m (+${delta.distance_diff_percent}%)`;

  // 9. Update Chart.js Data
  updateChartData(baseline, coolpath, data.temp_threshold_applied);
}

/**
 * Update Chart.js with Multi-Layer Datasets
 */
function updateChartData(baseline, coolpath, threshold) {
  if (!thermalChart) return;

  const points = coolpath.thermal_profile;
  const labels = points.map((p) => `${Math.round(p.distance_along_route_m)}m`);
  const coolTemps = points.map((p) => p.temperature_celsius);
  const coolUtcis = points.map((p) => p.utci_celsius);
  const coreTemps = points.map((p) => p.core_temp_estimate_celsius);

  // Map baseline points proportionally
  const basePoints = baseline.thermal_profile;
  const baseTemps = [];
  for (let i = 0; i < points.length; i++) {
    const ratio = i / (points.length - 1 || 1);
    const baseIdx = Math.min(basePoints.length - 1, Math.floor(ratio * basePoints.length));
    baseTemps.push(basePoints[baseIdx] ? basePoints[baseIdx].temperature_celsius : coolTemps[i] + 3.0);
  }

  const threshLine = new Array(points.length).fill(threshold);

  thermalChart.data.labels = labels;
  thermalChart.data.datasets[0].data = baseTemps;
  thermalChart.data.datasets[1].data = coolTemps;
  thermalChart.data.datasets[2].data = coolUtcis;
  thermalChart.data.datasets[3].data = coreTemps;
  thermalChart.data.datasets[4].data = threshLine;

  thermalChart.update();
}
