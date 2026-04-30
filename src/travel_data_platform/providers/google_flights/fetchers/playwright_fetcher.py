"""Playwright-based Google Flights fetcher.

Builds the same `tfs` deeplink as `fast_flights` (so we keep the well-tested
protobuf encoding) and renders the page in a real Chromium so JS-driven
result lists actually populate. Extraction is aria-label / semantic text
based to stay resilient against class-name churn.
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlencode

from fast_flights import FlightData, Passengers
from fast_flights.filter import create_filter

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.exceptions import ProviderFetchError
from travel_data_platform.providers.google_flights.debug.artifacts import (
    write_debug_artifact,
    write_debug_bytes,
)
from travel_data_platform.providers.google_flights.fetchers.base import (
    GoogleFlightsRawFetcher,
)

_GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights"
_RESULTS_LIST_SELECTOR = "ul.Rk10dc"
_RESULT_ITEM_SELECTOR = "ul.Rk10dc > li"
_NO_RESULTS_TEXT_HINTS = (
    "No flights found",
    "No nonstop flights",
    "No results",
)

_CURRENCY_BY_SYMBOL: list[tuple[str, str]] = [
    ("₫", "VND"),
    ("VND", "VND"),
    ("$", "USD"),
    ("USD", "USD"),
    ("€", "EUR"),
    ("EUR", "EUR"),
    ("£", "GBP"),
    ("GBP", "GBP"),
    ("¥", "JPY"),
    ("JPY", "JPY"),
]


class GoogleFlightsPlaywrightFetcher(GoogleFlightsRawFetcher):
    """Render Google Flights via Playwright Chromium and extract result cards.

    The TFS encoder from `fast_flights` is reused so the URL is identical to
    what the library would have hit; only the transport changes from `primp`
    HTTP to a real browser. This is critical because Google Flights now
    serves an empty shell page over plain HTTP for many routes — the result
    cards are populated by JS after the initial document loads.
    """

    def __init__(
        self,
        seat: str = "economy",
        currency: str = "VND",
        headless: bool = True,
        timeout_ms: int = 25_000,
        max_offers: int | None = None,
    ) -> None:
        self._seat = seat
        self._currency = currency
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._max_offers = max_offers
        self._logger = logging.getLogger(__name__)

    async def fetch_raw(self, query: FlightQuery) -> list[dict]:
        url = self._build_url(query)
        try:
            offers = await self._fetch_with_playwright(query, url)
        except ProviderFetchError:
            raise
        except Exception as exc:
            raise ProviderFetchError("Playwright Google Flights fetch failed") from exc

        self._logger.info(
            "playwright_fetch_completed origin=%s destination=%s departure=%s return=%s offers=%s",
            query.origin,
            query.destination,
            query.departure_date,
            query.return_date,
            len(offers),
        )
        return offers

    def _build_url(self, query: FlightQuery) -> str:
        flight_data = [
            FlightData(
                date=query.departure_date.isoformat(),
                from_airport=query.origin,
                to_airport=query.destination,
            )
        ]
        if query.return_date is not None:
            flight_data.append(
                FlightData(
                    date=query.return_date.isoformat(),
                    from_airport=query.destination,
                    to_airport=query.origin,
                )
            )

        trip = "round-trip" if query.return_date is not None else "one-way"
        tfs = create_filter(
            flight_data=flight_data,
            trip=trip,  # type: ignore[arg-type]
            passengers=Passengers(adults=query.adults),
            seat=self._seat,  # type: ignore[arg-type]
        ).as_b64()

        params = {
            "tfs": tfs.decode("utf-8"),
            "hl": "en",
            "tfu": "EgQIABABIgA",
            "curr": self._currency,
        }
        return f"{_GOOGLE_FLIGHTS_URL}?{urlencode(params)}"

    async def _fetch_with_playwright(self, query: FlightQuery, url: str) -> list[dict]:
        # Imported lazily so test environments without Playwright installed
        # can still import the module (CI installs deps but not browsers).
        from playwright.async_api import (
            TimeoutError as PlaywrightTimeoutError,
        )
        from playwright.async_api import (
            async_playwright,
        )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context(
                    locale="en-US",
                    viewport={"width": 1366, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                page.set_default_timeout(self._timeout_ms)

                try:
                    await page.goto(url, wait_until="domcontentloaded")
                except PlaywrightTimeoutError as exc:
                    await self._dump_debug(page, query, "goto_timeout")
                    raise ProviderFetchError(f"Google Flights navigation timed out: {exc}") from exc

                # Best-effort: dismiss any consent / cookie dialogs that
                # would otherwise hide the results list.
                await self._dismiss_overlays(page)

                if await self._page_says_no_results(page):
                    self._logger.info(
                        "playwright_no_inventory origin=%s destination=%s departure=%s return=%s",
                        query.origin,
                        query.destination,
                        query.departure_date,
                        query.return_date,
                    )
                    return []

                try:
                    await page.wait_for_selector(_RESULTS_LIST_SELECTOR, timeout=self._timeout_ms)
                except PlaywrightTimeoutError as exc:
                    if await self._page_says_no_results(page):
                        return []
                    await self._dump_debug(page, query, "results_timeout")
                    raise ProviderFetchError("Google Flights results list did not appear") from exc

                # Let JS finish hydrating result cards before scraping.
                await asyncio.sleep(1.0)

                raw_items = await page.evaluate(_EXTRACT_JS)
                final_url = page.url

                offers = self._normalize(raw_items, source_url=final_url)
                if not offers:
                    await self._dump_debug(page, query, "empty_results")
                return offers
            finally:
                await browser.close()

    async def _dismiss_overlays(self, page) -> None:
        for selector in (
            'button[aria-label*="Accept"]',
            'button[aria-label*="Agree"]',
            'button:has-text("Accept all")',
            'button:has-text("I agree")',
        ):
            try:
                btn = await page.query_selector(selector)
                if btn is not None:
                    await btn.click(timeout=2_000)
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                continue

    async def _page_says_no_results(self, page) -> bool:
        try:
            body_text = await page.inner_text("body", timeout=3_000)
        except Exception:
            return False
        return any(hint in body_text for hint in _NO_RESULTS_TEXT_HINTS)

    async def _dump_debug(self, page, query: FlightQuery, tag: str) -> None:
        slug = (
            f"playwright_{tag}_{query.origin}_{query.destination}_"
            f"{query.departure_date.isoformat()}"
        )
        try:
            html = await page.content()
            write_debug_artifact(slug, html, suffix="html")
        except Exception:
            self._logger.warning("failed to capture debug HTML", exc_info=True)
        try:
            png = await page.screenshot(full_page=True)
            write_debug_bytes(slug, png, suffix="png")
        except Exception:
            self._logger.warning("failed to capture screenshot", exc_info=True)

    def _normalize(self, raw_items: list[dict], source_url: str) -> list[dict]:
        offers: list[dict] = []
        for item in raw_items:
            offer = self._normalize_one(item, source_url=source_url)
            if offer is None:
                continue
            offers.append(offer)
            if self._max_offers is not None and len(offers) >= self._max_offers:
                break
        return offers

    def _normalize_one(self, item: dict, source_url: str) -> dict | None:
        price_text = (item.get("price_text") or "").strip()
        price_info = _parse_price(price_text)
        if price_info is None:
            return None

        return {
            "price": price_info["price"],
            "currency": price_info["currency"],
            "airline": _clean_optional(item.get("airline_text")),
            "stops": _parse_stops(item.get("stops_text")),
            "duration_text": _clean_optional(item.get("duration_text")),
            "departure_time_text": _clean_optional(item.get("departure_time_text")),
            "arrival_time_text": _clean_optional(item.get("arrival_time_text")),
            "card_aria_label": _clean_optional(item.get("aria_label")),
            "source_url": source_url,
        }


# JS executed inside the page. Returns one dict per result card with raw
# text fragments; all parsing happens in Python so we have one source of
# truth for currency/stops handling shared with the TFS fetcher.
_EXTRACT_JS = r"""
() => {
  const items = Array.from(document.querySelectorAll('ul.Rk10dc > li'));
  return items.map((li) => {
    const aria = li.getAttribute('aria-label') || '';
    const text = (sel) => {
      const el = li.querySelector(sel);
      return el ? (el.innerText || el.textContent || '').trim() : '';
    };
    // Price: Google Flights renders the price inside elements whose
    // aria-label starts with the localized currency phrase. We grab the
    // first descendant whose text contains a digit + currency symbol.
    let priceText = '';
    const priceCandidates = li.querySelectorAll(
      'div[aria-label*="đồng"], div[aria-label*="dollar"], ' +
      'div[aria-label*="euro"], div[aria-label*="pound"], ' +
      'div[aria-label*="yen"], span[aria-label*="đồng"], ' +
      'span[aria-label*="dollar"]'
    );
    // Pick the most specific (shortest aria-label) to avoid parent
    // containers whose label aggregates several child price fragments.
    let bestLabel = '';
    priceCandidates.forEach((el) => {
      const label = (el.getAttribute('aria-label') || '').trim();
      if (!label) return;
      if (!bestLabel || label.length < bestLabel.length) bestLabel = label;
    });
    priceText = bestLabel;
    if (!priceText) {
      // Fallback: scan visible text for a number followed by a currency token.
      const all = (li.innerText || '').split('\n').map((s) => s.trim()).filter(Boolean);
      priceText = all.find((s) => /[₫$€£¥]|VND|USD|EUR|GBP|JPY/.test(s) && /\d/.test(s)) || '';
    }

    // Time labels: two spans containing departure / arrival, often with
    // aria-label "Departure time: ..." / "Arrival time: ...".
    let depText = '';
    let arrText = '';
    const timeSpans = li.querySelectorAll(
      'span[aria-label^="Departure"], span[aria-label^="Arrival"]'
    );
    timeSpans.forEach((s) => {
      const label = s.getAttribute('aria-label') || '';
      if (label.startsWith('Departure')) depText = label;
      if (label.startsWith('Arrival')) arrText = label;
    });

    // Duration: element with aria-label like "Total duration 2 hr 5 min".
    let durText = '';
    const durEl = li.querySelector('div[aria-label^="Total duration"]');
    if (durEl) durText = durEl.getAttribute('aria-label') || '';

    // Stops: element with text like "Nonstop" or "1 stop".
    let stopsText = '';
    const stopsCandidates = Array.from(li.querySelectorAll('span, div'));
    for (const el of stopsCandidates) {
      const t = (el.innerText || '').trim();
      if (/^Nonstop$/.test(t) || /^\d+\s+stop/.test(t)) {
        stopsText = t;
        break;
      }
    }

    // Airline name: usually the first span inside a div with class
    // containing the carrier label. As a resilient fallback, pull any
    // text node that doesn't contain digits, currency, or time.
    let airlineText = '';
    const airlineEl = li.querySelector('div.sSHqwe span, div[class*="airline"], span.h1fkLb');
    if (airlineEl) airlineText = (airlineEl.innerText || '').trim();
    if (!airlineText) {
      const lines = (li.innerText || '').split('\n').map((s) => s.trim());
      airlineText = lines.find((s) =>
        s &&
        !/[₫$€£¥]/.test(s) &&
        !/^\d/.test(s) &&
        !/AM|PM|hr|min|stop|Nonstop/i.test(s)
      ) || '';
    }

    return {
      aria_label: aria,
      price_text: priceText,
      airline_text: airlineText,
      stops_text: stopsText,
      duration_text: durText,
      departure_time_text: depText,
      arrival_time_text: arrText,
    };
  });
}
"""


_MAX_PRICE_DIGITS = 10  # 10 digits covers up to 9.9B VND — well above any real fare.


def _parse_price(value: str | None) -> dict | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    currency = _detect_currency(text)
    digits = re.sub(r"[^0-9]", "", text)
    if not digits or len(digits) > _MAX_PRICE_DIGITS:
        return None
    return {"price": int(digits), "currency": currency}


def _detect_currency(text: str) -> str:
    for token, code in _CURRENCY_BY_SYMBOL:
        if token in text:
            return code
    return "VND"


def _parse_stops(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip().lower()
    if not text:
        return None
    if text.startswith("nonstop"):
        return 0
    match = re.match(r"^(\d+)\s+stop", text)
    if match:
        return int(match.group(1))
    return None


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
