"""Observe appointment availability from Munich's official browser flow.

This opens the official appointment page in a visible browser. Complete the
search in the page as usual; the script prints calendar results only and never
prints or stores the CAPTCHA token.
"""

from __future__ import annotations

import asyncio
import json

from playwright.async_api import async_playwright


START_PAGE = (
    "https://stadt.muenchen.de/buergerservice/terminvereinbarung.html"
    "#/services/1063453/locations/102524"
)
CALENDAR_ENDPOINT = "/api/citizen/available-calendar/"


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=False)
        page = await browser.new_page()
        print("A browser is open on the official Reisepass appointment flow for Bürgerbüro Scheidplatz (Belgradstraße).")
        print("Choose the date range in the page and complete the CAPTCHA normally.")
        print("Calendar responses will be summarized here; CAPTCHA tokens are not logged.")

        async def report_calendar(response) -> None:
            if CALENDAR_ENDPOINT not in response.url or response.request.method != "GET":
                return
            try:
                payload = await response.json()
            except (json.JSONDecodeError, ValueError):
                print(f"Calendar response: HTTP {response.status} (not JSON)")
                return

            print(f"\nCalendar response: HTTP {response.status}")
            days = payload.get("availableDays", [])
            slots = []
            for day in days:
                for office in day.get("offices", []):
                    for timestamp in office.get("appointments", []):
                        slots.append((day.get("date"), office.get("officeId"), timestamp))
            if not slots:
                print("No available appointments in the returned calendar data.")
            else:
                print(f"Found {len(slots)} appointment slot(s):")
                for day, office_id, timestamp in slots:
                    print(f"  date={day} officeId={office_id} timestamp={timestamp}")

        async def report_captcha_verification(response) -> None:
            if "/api/citizen/captcha-verify/" not in response.url:
                return
            print(f"CAPTCHA verification response: HTTP {response.status}")
            try:
                payload = await response.json()
            except (json.JSONDecodeError, ValueError):
                return
            if isinstance(payload, dict):
                print(f"  response fields: {', '.join(sorted(payload))}")
                if "captchaToken" in payload:
                    print("  captchaToken present (value withheld)")

        page.on("response", report_calendar)
        page.on("response", report_captcha_verification)
        try:
            await page.goto(START_PAGE, wait_until="commit", timeout=120_000)
            print(f"Page opened: {await page.title()} ({page.url})")
            await page.wait_for_timeout(30 * 60 * 1000)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
