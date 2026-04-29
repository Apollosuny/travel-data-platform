import re
from contextlib import suppress
from urllib.parse import quote_plus

from playwright.async_api import Browser, BrowserContext, Locator, Page, async_playwright

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.exceptions import ProviderFetchError
from travel_data_platform.providers.google_flights.debug.artifacts import (
  write_debug_artifact,
  write_debug_bytes,
  write_debug_json
)
from travel_data_platform.providers.google_flights.fetchers.base import GoogleFlightsRawFetcher


class GoogleFlightsBrowserFetcher(GoogleFlightsRawFetcher):
    BASE_URL = "https://www.google.com/travel/flights"

    def __init__(self, browser: Browser | None = None) -> None:
        self.browser = browser

    async def fetch_raw(self, query: FlightQuery) -> list[dict]:
        if self.browser is not None:
            return await self._fetch_with_browser(self.browser, query)

        playwright = None
        browser = None
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            return await self._fetch_with_browser(browser, query)
        except Exception as exc:
            raise ProviderFetchError("Failed to fetch Google Flights raw data") from exc
        finally:
            if browser is not None:
                with suppress(Exception):
                    await browser.close()
            if playwright is not None:
                with suppress(Exception):
                    await playwright.stop()

    async def _fetch_with_browser(self, browser: Browser, query: FlightQuery) -> list[dict]:
        context: BrowserContext | None = None
        page: Page | None = None

        try:
            context = await browser.new_context(
                locale="en-US",
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            await self._navigate_to_results(page, query)

            html = await page.content()
            body_text = await page.locator("body").inner_text()

            write_debug_artifact("page", html, "html")
            write_debug_artifact("body", body_text, "txt")

            raw_offers = await self._extract_raw_offers(page)
            raw_offers = self._dedupe_offers(raw_offers)
            write_debug_json("offers", raw_offers)

            return raw_offers
        except Exception as exc:
            if page is not None:
                await self._dump_failure_artifacts(page)
            raise ProviderFetchError("Failed to fetch Google Flights raw data") from exc
        finally:
            if page is not None:
                with suppress(Exception):
                    await page.close()
            if context is not None:
                with suppress(Exception):
                    await context.close()

    async def _dump_failure_artifacts(self, page: Page) -> None:
        with suppress(Exception):
            html = await page.content()
            write_debug_artifact("page_failure", html, "html")
        with suppress(Exception):
            body_text = await page.locator("body").inner_text()
            write_debug_artifact("body_failure", body_text, "txt")
        with suppress(Exception):
            screenshot = await page.screenshot(full_page=True)
            write_debug_bytes("screenshot_failure", screenshot, "png")

    def _build_search_url(self, query: FlightQuery) -> str:
        search_text = " ".join(
            part
            for part in [
                query.origin,
                query.destination,
                query.departure_date.isoformat(),
                query.return_date.isoformat() if query.return_date else None,
            ]
            if part
        )
        return f"{self.BASE_URL}?q={quote_plus(search_text)}"

    async def _navigate_to_results(self, page: Page, query: FlightQuery) -> None:
        url = self._build_search_url(query)
        await page.goto(url, wait_until="load", timeout=60000)
        with suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=15000)

        try:
            await self._wait_for_results(page)
            return
        except Exception:
            if not await self._looks_like_homepage(page):
                raise

        await self._submit_search_form(page, query)
        await self._wait_for_results(page)

    async def _looks_like_homepage(self, page: Page) -> bool:
        with suppress(Exception):
            return await page.locator("text=Find cheap flights").first.is_visible()
        return False

    async def _submit_search_form(self, page: Page, query: FlightQuery) -> None:
        if query.return_date is None:
            await self._select_one_way(page)

        await self._fill_location_input(page, "Where from?", query.origin)
        await self._fill_location_input(page, "Where to?", query.destination)
        await self._fill_date_input(page, "Departure", query.departure_date)
        if query.return_date is not None:
            await self._fill_date_input(page, "Return", query.return_date)

        await self._close_date_picker(page)
        await self._click_search(page)

        with suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=15000)

    async def _click_search(self, page: Page) -> None:
        candidates = [
            page.get_by_role("button", name="Search", exact=True).first,
            page.locator("div[role='button'][aria-label='Search']").first,
            page.locator("button[aria-label='Search']").first,
        ]
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                if not await candidate.count():
                    continue
                await candidate.scroll_into_view_if_needed(timeout=3000)
                await candidate.click(timeout=5000)
                return
            except Exception as exc:
                last_error = exc
                continue

        for candidate in candidates:
            try:
                if not await candidate.count():
                    continue
                await candidate.click(timeout=5000, force=True)
                return
            except Exception as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error

    async def _close_date_picker(self, page: Page) -> None:
        dialog = page.locator("div[role='dialog'][aria-modal='true']").first
        if not await dialog.count() or not await dialog.is_visible():
            return

        done_button = dialog.locator("[role='button']", has_text="Done").first
        with suppress(Exception):
            if await done_button.count():
                await done_button.click(timeout=5000)

        with suppress(Exception):
            await dialog.wait_for(state="hidden", timeout=5000)

        if await dialog.is_visible():
            with suppress(Exception):
                await page.keyboard.press("Escape")
                await dialog.wait_for(state="hidden", timeout=5000)

    async def _select_one_way(self, page: Page) -> None:
        with suppress(Exception):
            await page.get_by_label("Change ticket type.").first.click(timeout=5000)
            await page.get_by_role("option", name="One way").first.click(timeout=5000)

    async def _fill_location_input(self, page: Page, label: str, value: str) -> None:
        field = page.get_by_role("combobox", name=label).first
        await field.click(timeout=10000)
        await field.fill("")
        await field.type(value, delay=50)
        with suppress(Exception):
            await page.wait_for_selector("li[role='option']", timeout=8000)
        await page.keyboard.press("Enter")

    async def _fill_date_input(self, page: Page, label: str, value) -> None:
        dialog_field = page.locator(
            f"div[role='dialog'][aria-modal='true'] input[aria-label='{label}']"
        ).first
        if await dialog_field.count() and await dialog_field.is_visible():
            field = dialog_field
        else:
            field = await self._first_visible(page, f"input[aria-label='{label}']")

        await field.click(timeout=10000)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
        await page.keyboard.type(value.strftime("%m/%d/%Y"), delay=50)
        await page.keyboard.press("Enter")

    async def _first_visible(self, page: Page, selector: str) -> Locator:
        elements = page.locator(selector)
        count = await elements.count()
        for i in range(count):
            element = elements.nth(i)
            if await element.is_visible():
                return element
        return page.locator(selector).first

    async def _wait_for_results(self, page: Page) -> None:
        await page.wait_for_selector("ul.Rk10dc li.pIav2d", timeout=30000)

    async def _extract_raw_offers(self, page: Page) -> list[dict]:
        cards = page.locator("ul.Rk10dc > li.pIav2d")
        count = await cards.count()

        offers: list[dict] = []
        for i in range(min(count, 10)):
            card = cards.nth(i)
            offer = await self._extract_offer_from_card(card, page.url)
            if offer is not None:
                offers.append(offer)

        return offers

    def _dedupe_offers(self, offers: list[dict]) -> list[dict]:
      deduped: list[dict] = []
      seen: set[tuple] = set()

      for offer in offers:
          key = (
              offer.get("price"),
              offer.get("currency"),
              offer.get("airline"),
              offer.get("stops"),
              offer.get("card_aria_label"),
          )
          if key in seen:
              continue

          seen.add(key)
          deduped.append(offer)

      return deduped

    async def _extract_offer_from_card(self, card: Locator, source_url: str) -> dict | None:
        aria_label = await self._safe_get_attr(card.locator(".JMc5Xc").first, "aria-label")
        price_aria = await self._safe_get_attr(card.locator(".U3gSDe .YMlIz [aria-label]").first, "aria-label")
        airline_text = await self._safe_inner_text(card.locator(".sSHqwe.tPgKwe.ogfYpf").first)

        price_info = self._parse_price(price_aria or aria_label or "")
        if price_info is None:
            return None

        departure_time_text, arrival_time_text = self._parse_times_from_aria_label(aria_label or "")
        duration_text = self._parse_duration_from_aria_label(aria_label or "")
        stops = self._parse_stops(aria_label or "")

        return {
            "price": price_info["price"],
            "currency": price_info["currency"],
            "airline": airline_text or self._parse_airline_from_aria_label(aria_label or ""),
            "stops": stops,
            "duration_text": duration_text,
            "departure_time_text": departure_time_text,
            "arrival_time_text": arrival_time_text,
            "card_aria_label": aria_label,
            "source_url": source_url,
        }

    async def _safe_get_attr(self, locator: Locator, name: str) -> str | None:
        try:
            value = await locator.get_attribute(name)
            return value.strip() if value else None
        except Exception:
            return None

    async def _safe_inner_text(self, locator: Locator) -> str | None:
        try:
            value = await locator.inner_text()
            value = value.strip()
            return value if value else None
        except Exception:
            return None

    def _parse_price(self, value: str) -> dict | None:
        if not value:
            return None

        value = value.strip()
        currency = "VND"
        normalized = value

        if "Vietnamese dong" in value or "₫" in value or "VND" in value:
            currency = "VND"
        elif "USD" in value or "$" in value:
            currency = "USD"

        digits = re.findall(r"\d+", normalized.replace(",", "").replace(".", ""))
        if not digits:
            return None

        return {
            "price": int("".join(digits)),
            "currency": currency,
        }

    def _parse_stops(self, aria_label: str) -> int | None:
        if not aria_label:
            return None

        label = aria_label.lower()
        if "nonstop" in label:
            return 0

        match = re.search(r"(\d+)\s+stop", label)
        if match:
            return int(match.group(1))

        return None

    def _parse_time_range(self, text: str) -> tuple[str | None, str | None]:
        if not text:
            return None, None

        parts = [part.strip() for part in text.split("–")]
        if len(parts) != 2:
            return None, None

        return parts[0] or None, parts[1] or None

    def _normalize_duration(self, value: str | None) -> str | None:
        if not value:
            return None
        return value.replace("Total duration", "").replace(".", "").strip()

    def _parse_times_from_aria_label(self, aria_label: str) -> tuple[str | None, str | None]:
        if not aria_label:
            return None, None

        departure_match = re.search(r"Leaves .*? at ([0-9]{1,2}:[0-9]{2}\s?[AP]M)", aria_label)
        arrival_match = re.search(r"arrives .*? at ([0-9]{1,2}:[0-9]{2}\s?[AP]M)", aria_label)

        departure = departure_match.group(1) if departure_match else None
        arrival = arrival_match.group(1) if arrival_match else None
        return departure, arrival
    
    def _parse_duration_from_aria_label(self, aria_label: str) -> str | None:
      if not aria_label:
          return None

      match = re.search(r"Total duration ([^.]+)", aria_label)
      return match.group(1).strip() if match else None

    def _parse_airline_from_aria_label(self, aria_label: str) -> str | None:
        if not aria_label:
            return None

        match = re.search(r"flight with ([^.]+?)\.", aria_label, re.IGNORECASE)
        return match.group(1).strip() if match else None