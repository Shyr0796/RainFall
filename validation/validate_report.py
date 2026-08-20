#!/usr/bin/env python3
"""Static and browser checks for validation.html."""

from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "validation.html"


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.sections = 0
        self.tables = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag == "section":
            self.sections += 1
        if tag == "table":
            self.tables += 1


def static_checks() -> dict[str, object]:
    parser = ReportParser()
    parser.feed(REPORT.read_text(encoding="utf-8"))
    required_ids = {"decision", "design", "advanced", "status", "metrics", "calibration", "data-needs", "results", "sources"}
    missing_ids = sorted(required_ids - parser.ids)
    broken_local = []
    for link in parser.links:
        parsed = urlparse(link)
        if parsed.scheme or link.startswith("#"):
            continue
        candidate = ROOT / unquote(parsed.path)
        if not candidate.exists():
            broken_local.append(link)
    result = {
        "sections": parser.sections,
        "tables": parser.tables,
        "links": len(parser.links),
        "missing_required_ids": missing_ids,
        "broken_local_links": broken_local,
    }
    if parser.sections < 7 or parser.tables < 2 or missing_ids or broken_local:
        raise AssertionError(result)
    return result


def browser_checks(base_url: str) -> dict[str, object]:
    from playwright.sync_api import sync_playwright

    screenshot_dir = ROOT / "logs"
    screenshot_dir.mkdir(exist_ok=True)
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
        desktop.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        desktop.goto(base_url, wait_until="networkidle")
        assert "RainFall" in desktop.title()
        assert "分层实验验证提案" in desktop.locator("h1").inner_text()
        assert desktop.locator("section").count() >= 7
        assert desktop.locator("table").count() >= 2
        assert desktop.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        desktop.screenshot(path=screenshot_dir / "validation_desktop.png", full_page=True)
        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(base_url, wait_until="networkidle")
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        mobile.screenshot(path=screenshot_dir / "validation_mobile.png", full_page=True)
        browser.close()
    if console_errors:
        raise AssertionError({"console_errors": console_errors})
    return {"desktop_width": 1440, "mobile_width": 390, "console_errors": []}


def main() -> None:
    result: dict[str, object] = {"static": static_checks()}
    if len(sys.argv) > 1:
        result["browser"] = browser_checks(sys.argv[1])
    result["status"] = "PASS"
    (ROOT / "logs" / "report_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
