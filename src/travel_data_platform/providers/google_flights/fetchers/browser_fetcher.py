import re
from contextlib import suppress
from urllib.parse import quote_plus

from playwright.async_api import Browser, BrowserContext, Locator, Page, async_playwright

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.exceptions import ProviderFetchError
from travel_data_platform.providers.google_flights.debug.artifacts import (
  write_debug_artifact,
  write_debug_json
)
from travel_data_platform.providers.google_flights.fetchers.base import GoogleFlightsRawFetcher


class GoogleFlightsBrowserFetcher(GoogleFlightsRawFetcher):
    BASE_URL = "https://www.google.com/travel/flights"

    async def fetch_raw(self, query: FlightQuery) -> list[dict]:
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
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

                url = self._build_search_url(query)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await self._wait_for_results(page)

                html = await page.content()
                body_text = await page.locator("body").inner_text()

                write_debug_artifact("page", html, "html")
                write_debug_artifact("body", body_text, "txt")

                raw_offers = await self._extract_raw_offers(page)
                raw_offers = self._dedupe_offers(raw_offers)
                write_debug_json("raw_offers", raw_offers)
                return raw_offers

        except Exception as exc:
            raise ProviderFetchError("Failed to fetch Google Flights raw data") from exc

        finally:
            if page is not None:
                with suppress(Exception):
                    await page.close()
            if context is not None:
                with suppress(Exception):
                    await context.close()
            if browser is not None:
                with suppress(Exception):
                    await browser.close()

    def _build_search_url(self, query: FlightQuery) -> str:
        search_text = " ".join(
            part
            for part in [
                query.origin,
                query.destination,
                query.departure_date,
                query.return_date,
            ]
            if part
        )
        return f"{self.BASE_URL}?q={quote_plus(search_text)}"

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