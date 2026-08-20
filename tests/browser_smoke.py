from pathlib import Path

from playwright.sync_api import sync_playwright

output_dir = Path("outputs")
output_dir.mkdir(exist_ok=True)
console_errors: list[str] = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(
        viewport={"width": 1440, "height": 1050}, device_scale_factor=1
    )
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.goto("http://127.0.0.1:8000", wait_until="networkidle")
    page.locator("#hardwarePill.ready").wait_for(timeout=15_000)
    assert "GPU" in page.locator("#hardwareText").inner_text()
    assert page.locator("#simulationCanvas").is_visible()
    assert page.locator("#rainVolume").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    duration = page.locator("#rain_duration_min")
    duration.evaluate(
        "el => { el.value = 5; el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.wait_for_timeout(250)
    page.get_by_role("button", name="开始").click()
    page.wait_for_timeout(1800)
    page.get_by_role("button", name="暂停").click()
    assert page.locator("#simClock").inner_text() != "00:00:00"
    assert "降雨已结束" in page.locator("#rainStatus").inner_text()
    with page.expect_download(timeout=10_000) as download_info:
        page.get_by_role("button", name="导出当前画面").click()
    assert download_info.value.suggested_filename.endswith("s.png")

    rainfall = page.locator("#rainfall_mm_h")
    rainfall.evaluate(
        "el => { el.value = 180; el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.wait_for_timeout(350)
    assert "180" in page.locator('output[data-for="rainfall_mm_h"]').inner_text()

    page.get_by_role("button", name="水深").click()
    assert page.get_by_role("button", name="水深").get_attribute("class") == "active"
    page.screenshot(path=output_dir / "raincell_desktop.png", full_page=True)

    report = browser.new_page(
        viewport={"width": 1280, "height": 900}, device_scale_factor=1
    )
    report.goto("http://127.0.0.1:8000/report", wait_until="networkidle")
    assert "技术与使用报告" in report.locator("h1").inner_text()
    assert report.locator("table").count() >= 6
    report.screenshot(path=output_dir / "raincell_report.png", full_page=False)
    report.close()

    # Exercise the largest selectable grid and regeneration path.
    page.locator("#grid_size").select_option("384")
    with page.expect_response("**/api/reset", timeout=20_000):
        page.get_by_role("button", name="生成新地形并清零").click()
    assert page.locator("#simulationCanvas").evaluate("el => el.width") == 384
    with page.expect_response("**/api/step", timeout=20_000):
        page.locator("#stepBtn").click()

    mobile = browser.new_page(
        viewport={"width": 390, "height": 844}, device_scale_factor=1
    )
    mobile.goto("http://127.0.0.1:8000", wait_until="networkidle")
    mobile.locator("#hardwarePill.ready").wait_for(timeout=15_000)
    assert mobile.locator("#simulationCanvas").is_visible()
    assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    mobile.screenshot(path=output_dir / "raincell_mobile.png", full_page=True)
    mobile.close()
    browser.close()

if console_errors:
    raise AssertionError(f"Browser console errors: {console_errors}")

print("BROWSER_SMOKE=PASS")
