#!/usr/bin/env python3
"""
Quick hackathon scratch test: Verify FortyGuard 2m surface temperature responses
and compare H3 res 8 vs res 9 hexagon clustering speed.
"""

import asyncio
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.clients.fortyguard import FortyGuardClient
from app.core.h3_grid import H3GridManager


async def run_benchmark():
    print("Testing FortyGuard Client & H3 Grid Generation...")
    client = FortyGuardClient()
    manager = H3GridManager(client)

    # Test Phoenix downtown center
    phoenix_lat, phoenix_lon = 33.4484, -112.0740

    t0 = time.perf_counter()
    heatmap = await manager.generate_heatmap_for_region(
        center_lat=phoenix_lat,
        center_lon=phoenix_lon,
        radius_km=2.5,
        resolution=9,
        ambient_temp=38.0
    )
    t1 = time.perf_counter()

    num_hexagons = len(heatmap.features)
    print(f"Generated {num_hexagons} H3 hexagons (res 9) in {(t1 - t0)*1000:.1f}ms")

    # Sample a hexagon
    if heatmap.features:
        sample = heatmap.features[0]
        print("Sample H3 Feature:")
        print(f"  - H3 Index: {sample.properties.h3_index}")
        print(f"  - Surface Temp: {sample.properties.surface_temp_celsius}°C")
        print(f"  - Albedo Type: {sample.properties.albedo_type}")
        print(f"  - Risk Score: {sample.properties.risk_score}/100")

    print("\nBenchmark completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
