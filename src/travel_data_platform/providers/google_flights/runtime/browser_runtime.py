from contextlib import asynccontextmanager

from playwright.async_api import Browser, Playwright, async_playwright


@asynccontextmanager
async def google_flights_browser():
    playwright: Playwright | None = None
    browser: Browser | None = None

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        yield browser
    finally:
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()