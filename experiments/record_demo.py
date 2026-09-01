"""Record an ultra-high-definition, annotated hackathon demo video of CoolPath AI using Playwright.
Includes animated overlay cards explaining each scientific and engineering breakthrough in real-time.
"""

import asyncio
import os
import time
from playwright.async_api import async_playwright

OVERLAY_STYLES = """
<style id="demo-overlay-style">
.demo-overlay-banner {
    position: fixed;
    top: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(13, 17, 23, 0.94);
    border: 1.5px solid rgba(0, 240, 255, 0.5);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.8), 0 0 25px rgba(0, 240, 255, 0.25);
    backdrop-filter: blur(16px);
    color: #ffffff;
    padding: 16px 28px;
    border-radius: 14px;
    z-index: 99999;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    max-width: 780px;
    text-align: center;
    animation: fadeInSlide 0.5s ease-out;
    pointer-events: none;
}
.demo-badge {
    display: inline-block;
    background: linear-gradient(135deg, #00f0ff, #3b82f6);
    color: #0b0f19;
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 6px;
}
.demo-title {
    font-size: 20px;
    font-weight: 700;
    margin: 4px 0;
    color: #f1f5f9;
    letter-spacing: -0.3px;
}
.demo-subtitle {
    font-size: 13.5px;
    color: #94a3b8;
    line-height: 1.45;
    margin: 0;
}
@keyframes fadeInSlide {
    from { opacity: 0; transform: translate(-50%, -15px); }
    to { opacity: 1; transform: translate(-50%, 0); }
}
</style>
"""


async def set_demo_caption(page, badge: str, title: str, subtitle: str, duration_sec: float = 3.5):
    """Inject or update a high-contrast explanatory banner overlay on the screen."""
    js_code = f"""(() => {{
        if (!document.getElementById('demo-overlay-style')) {{
            document.head.insertAdjacentHTML('beforeend', `{OVERLAY_STYLES}`);
        }}
        let el = document.getElementById('demo-banner');
        if (!el) {{
            el = document.createElement('div');
            el.id = 'demo-banner';
            el.className = 'demo-overlay-banner';
            document.body.appendChild(el);
        }}
        el.innerHTML = `
            <div class="demo-badge">{badge}</div>
            <div class="demo-title">{title}</div>
            <p class="demo-subtitle">{subtitle}</p>
        `;
    }})()"""
    await page.evaluate(js_code)
    await asyncio.sleep(duration_sec)


async def main():
    os.makedirs("recordings", exist_ok=True)
    chrome_path = os.path.expanduser("~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")

    print("🚀 Launching Playwright with video capture (1920x1080)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=chrome_path if os.path.exists(chrome_path) else None,
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir="recordings/",
            record_video_size={"width": 1920, "height": 1080}
        )
        
        page = await context.new_page()

        # Step 1: Load Dashboard
        await page.goto("http://127.0.0.1:8000/", wait_until="networkidle", timeout=20000)
        await page.wait_for_selector(".coolpath-line", timeout=15000)
        await asyncio.sleep(1.0)

        # Introduction
        await set_demo_caption(
            page,
            badge="FortyGuard Hackathon '26 Submission",
            title="🌡️ CoolPath AI: 4D Hyperlocal Thermal Routing Engine",
            subtitle="Transforming 2-meter FortyGuard microclimate temperature data and Uber H3 grids into life-saving, heat-resilient urban navigation.",
            duration_sec=4.0
        )

        # Feature 1: FortyGuard 2m Microclimate Grid
        await set_demo_caption(
            page,
            badge="1. Hyperlocal Microclimate Intelligence",
            title="FortyGuard 2-Meter Surface Temperature & Uber H3 Hexagons",
            subtitle="Detecting extreme asphalt heat traps (up to 48°C) vs. cool microclimate corridors across downtown Phoenix, AZ.",
            duration_sec=3.5
        )

        # Feature 2: 4D Time-of-Day Solar Ray-Casting & Canyon Shadows
        await set_demo_caption(
            page,
            badge="2. 4D Temporal-Spatial Physics",
            title="3D Building Canyon Ray-Casting & Dynamic Solar Shading",
            subtitle="Simulating solar azimuth & elevation to project building shadow penetration along street canyons.",
            duration_sec=2.5
        )

        # Move time slider smoothly to 17:30 (evening shadows)
        for hour in [14.0, 15.0, 16.0, 17.0, 17.5]:
            await page.evaluate(f"""() => {{
                const slider = document.getElementById('timeSlider');
                slider.value = '{hour}';
                slider.dispatchEvent(new Event('input'));
                slider.dispatchEvent(new Event('change'));
            }}""")
            await asyncio.sleep(0.8)

        await set_demo_caption(
            page,
            badge="2. 4D Temporal-Spatial Physics",
            title="Long Evening Shadow Corridors (17:30 Sun Angle)",
            subtitle="Deep skyscraper shadows drop Mean Radiant Temperature (Tmrt) by up to 12.5°C, creating high-priority shade routes.",
            duration_sec=3.5
        )

        # Feature 3: Gagge 2-Node Human Thermoregulation
        await set_demo_caption(
            page,
            badge="3. Biometeorological Human Physiology",
            title="Gagge 2-Node Thermoregulation & Moran's PSI (0-10)",
            subtitle="Tracking metabolic wattage, core body temperature (Tcore), and cardiac strain in real time per worker persona.",
            duration_sec=3.5
        )

        # Switch to Road Crew Persona (Heavy Labor @ 340W)
        await page.click("button[data-profile='construction_outdoor']")
        await asyncio.sleep(2.5)

        # Feature 4: Autonomous Micro-Refuge Injection
        await set_demo_caption(
            page,
            badge="4. Autonomous Emergency Interventions",
            title="Autonomous Micro-Refuge & Misting Hub Injection",
            subtitle="When physiological strain exceeds safety thresholds (PSI >= 7.0), the engine automatically injects municipal cooling oasis waypoints with rest duration guidelines.",
            duration_sec=4.0
        )

        # Feature 5: EV Fleet & Cold-Chain Economics
        await set_demo_caption(
            page,
            badge="5. Industrial Logistics & Enterprise Economics",
            title="EV Battery Thermal Degradation & Cold-Chain Chiller ROI",
            subtitle="Quantifying auxiliary chiller load reduction, Li-ion battery cell life preservation, and dollar savings per delivery.",
            duration_sec=3.5
        )

        # Switch to EV Fleet
        await page.click("button[data-profile='heavy_fleet']")
        await asyncio.sleep(2.5)

        # Feature 6: Multi-City Global Microclimates
        await set_demo_caption(
            page,
            badge="6. Global Multi-City Deployment",
            title="Dubai Marina, UAE: Extreme Coastal Skyscraper Corridors",
            subtitle="Instant scaling across global urban morphologies with FortyGuard temperature calibration.",
            duration_sec=2.0
        )

        await page.select_option("#scenarioSelector", "dubai_marina")
        await asyncio.sleep(4.0)

        # Conclusion Banner
        await set_demo_caption(
            page,
            badge="Conclusion",
            title="CoolPath AI: Stay Cool, Move Smart.",
            subtitle="Built with FortyGuard 2m Microclimate API, Uber H3 Spatial Grid, FastAPI & FastMCP for Hackathon 2026.",
            duration_sec=3.5
        )

        await context.close()
        await browser.close()
        print("✅ Demo recording successfully captured in recordings/ directory!")


if __name__ == "__main__":
    asyncio.run(main())
