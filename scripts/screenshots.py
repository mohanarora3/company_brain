"""Take the README / deck screenshots of a running Last Day (needs `pip install playwright`).

    python -m lastday serve &          # in another terminal
    python scripts/screenshots.py      # writes docs/img/*.png

Also a quick visual regression check: it fails if the page logs a script error
or scrolls sideways at phone width.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.environ.get("LASTDAY_URL", "http://127.0.0.1:8000")
OUT = Path(__file__).resolve().parent.parent / "docs" / "img"


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        await pg.goto(BASE + "/")
        await pg.wait_for_selector(".dep")
        await pg.screenshot(path=OUT / "board.png")
        await pg.click(".dep >> nth=0")
        await pg.click("#run-btn")
        await pg.wait_for_selector("#replay-btn:not([hidden])", timeout=120000)
        await pg.evaluate("document.querySelector('.round[data-round=\"2\"]').scrollIntoView()")
        await pg.evaluate("window.scrollBy(0, -90)")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=OUT / "investigation.png")
        await pg.evaluate("window.scrollTo(0, 0)")
        await pg.wait_for_timeout(200)
        await pg.screenshot(path=OUT / "person.png")
        await pg.click("#tabs button[data-tab=handover]")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=OUT / "handover.png")
        await pg.evaluate("document.querySelector('#area-ledger-recon')?.scrollIntoView()")
        await pg.wait_for_timeout(200)
        await pg.screenshot(path=OUT / "handover-area.png")
        await pg.evaluate("window.scrollTo(0, 0)")
        await pg.click("#tabs button[data-tab=interview]")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=OUT / "interview.png")
        await pg.click("#tabs button[data-tab=evidence]")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=OUT / "evidence.png")
        await pg.click("#tabs button[data-tab=ask]")
        await pg.fill("#ask-q", "Why does recon run at 03:40?")
        await pg.click("#ask-form button")
        await pg.wait_for_selector(".answer", timeout=60000)
        await pg.screenshot(path=OUT / "ask.png")
        await pg.click("#open-sources")
        await pg.wait_for_selector(".src")
        await pg.screenshot(path=OUT / "sources.png")

        m = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        await m.goto(BASE + "/")
        await m.wait_for_selector(".dep")
        if await m.evaluate("document.documentElement.scrollWidth") > 390:
            errors.append("page scrolls sideways at 390 px")
        await m.screenshot(path=OUT / "mobile.png")
        await b.close()
    for e in errors:
        print("ERROR:", e, file=sys.stderr)
    print(f"screenshots in {OUT}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
