"""Playwright End-to-End Visual and Functional Verification Test for CoolPath AI 4D."""

import os
import pytest
from playwright.async_api import async_playwright


@pytest.mark.asyncio
async def test_dashboard_visual_and_functional():
    """Execute end-to-end verification of CoolPath AI 4D dashboard using Playwright."""
    os.makedirs("screenshots", exist_ok=True)

    chrome_path = "/home/shirsh/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=chrome_path if os.path.exists(chrome_path) else None,
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("response", lambda res: print(f"[HTTP {res.status}] {res.url}") if res.status >= 400 else None)

        # 1. Load Dashboard
        response = await page.goto("http://127.0.0.1:8000/", wait_until="networkidle", timeout=15000)
        assert response.status == 200

        # 2. Verify Title & Header
        title = await page.title()
        assert "CoolPath AI" in title

        header_title = await page.locator("h1").text_content()
        assert "CoolPath AI" in header_title

        # Wait for map & routes to render
        await page.wait_for_selector(".coolpath-line", timeout=10000)
        await page.wait_for_selector(".baseline-line", timeout=10000)

        # Verify Initial Stats Cards & Physiological stress
        cool_mean = await page.locator("#coolMeanTemp").text_content()
        base_mean = await page.locator("#baseMeanTemp").text_content()
        utci_mean = await page.locator("#coolUtciTemp").text_content()
        core_temp = await page.locator("#coolCoreTemp").text_content()
        assert "°C" in cool_mean
        assert "°C" in base_mean
        assert "°C" in utci_mean
        assert "°C" in core_temp

        # Capture Initial Load Screenshot (Phoenix Downtown with Physiological Stress)
        await page.screenshot(path="screenshots/01_phoenix_initial_load.png", full_page=True)
        print("✓ Screenshot saved: screenshots/01_phoenix_initial_load.png")

        # 3. Test 4D Solar Time Slider (Move to 17:30 / Evening shadow cast)
        await page.evaluate("""() => {
            const slider = document.getElementById('timeSlider');
            slider.value = '17.5';
            slider.dispatchEvent(new Event('input'));
            slider.dispatchEvent(new Event('change'));
        }""")
        await page.wait_for_timeout(2000)
        time_label = await page.locator("#departureTimeLabel").text_content()
        assert "17:30" in time_label
        await page.screenshot(path="screenshots/02_solar_canyon_shadows.png", full_page=True)
        print("✓ Screenshot saved: screenshots/02_solar_canyon_shadows.png")

        # 4. Test Cold-Chain & EV Fleet Mode
        await page.locator("#toggleColdChain").click()
        await page.wait_for_timeout(1500)
        fleet_energy = await page.locator("#fleetEnergySaved").text_content()
        assert "kWh" in fleet_energy
        await page.screenshot(path="screenshots/03_fleet_degradation_roi.png", full_page=True)
        print("✓ Screenshot saved: screenshots/03_fleet_degradation_roi.png")

        # 5. Switch Scenario to Dubai Marina
        await page.select_option("#scenarioSelector", "dubai_marina")
        await page.wait_for_timeout(2000)
        await page.wait_for_selector(".coolpath-line", timeout=10000)

        # Capture Dubai Marina Screenshot
        await page.screenshot(path="screenshots/04_dubai_marina_scenario.png", full_page=True)
        print("✓ Screenshot saved: screenshots/04_dubai_marina_scenario.png")

        # 6. Switch Profile to Vulnerable Citizen
        await page.locator("button[data-profile='vulnerable_citizen']").click()
        await page.wait_for_timeout(1500)
        alpha_val = await page.locator("#alphaVal").text_content()
        assert float(alpha_val) == 3.0

        # Capture Vulnerable Citizen Profile Screenshot
        await page.screenshot(path="screenshots/05_vulnerable_citizen_profile.png", full_page=True)
        print("✓ Screenshot saved: screenshots/05_vulnerable_citizen_profile.png")

        # 7. Verify Chart.js Canvas
        chart_visible = await page.locator("#thermalChart").is_visible()
        assert chart_visible is True

        # Assert no critical console errors occurred
        critical_errors = [e for e in console_errors if "favicon" not in e.lower()]
        assert len(critical_errors) == 0, f"Unexpected console errors: {critical_errors}"

        await browser.close()
        print("✓ All 4 breakthrough features verified with Playwright!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_dashboard_visual_and_functional())
