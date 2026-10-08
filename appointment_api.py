"""Client for Munich's current public appointment availability API."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


API_BASE = "https://www48.muenchen.de/buergeransicht/api/citizen"
APPOINTMENT_PAGE = "https://stadt.muenchen.de/buergerservice/terminvereinbarung.html"
try:
    LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")
except ZoneInfoNotFoundError:
    # Windows may lack an IANA database before requirements are installed.
    LOCAL_TIMEZONE = None


class AppointmentApiError(RuntimeError):
    """Raised when Munich's appointment API cannot provide a usable response."""


@dataclass(frozen=True)
class AppointmentService:
    id: int
    name: str
    variant_id: int | None = None
    parent_id: int | None = None


@dataclass(frozen=True)
class AppointmentSlot:
    service: AppointmentService
    office_id: str
    office_name: str
    address: str
    date: dt.date
    time: str


class MunichAppointmentClient:
    """Read the public service catalog and availability calendar."""

    def __init__(self, opener=None, timeout: float = 25):
        self.opener = opener or urlopen
        self.timeout = timeout
        self._catalog: dict | None = None
        self._catalog_loaded_at = 0.0

    def _get_json(self, path: str, params: dict | None = None) -> dict:
        url = f"{API_BASE}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MunichAppointmentSearch/1.0",
            },
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise AppointmentApiError(f"Munich appointment API request failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise AppointmentApiError("Munich appointment API returned an unexpected response.")
        if payload.get("errors"):
            messages = [
                item.get("errorMessage") or item.get("errorCode") or str(item)
                for item in payload["errors"]
            ]
            raise AppointmentApiError("; ".join(messages))
        return payload

    def catalog(self, refresh: bool = False) -> dict:
        if self._catalog is None or refresh or monotonic() - self._catalog_loaded_at >= 3600:
            catalog = self._get_json("offices-and-services/")
            if not all(key in catalog for key in ("offices", "services", "relations")):
                raise AppointmentApiError("Munich returned an incomplete service catalog.")
            self._catalog = catalog
            self._catalog_loaded_at = monotonic()
        return self._catalog

    def find_services(self, query: str) -> list[AppointmentService]:
        query = query.strip().casefold()
        services = [
            AppointmentService(
                id=int(item["id"]),
                name=item["name"],
                variant_id=item.get("variantId"),
                parent_id=item.get("parentId"),
            )
            for item in self.catalog()["services"]
            if item.get("name") and query in item["name"].casefold()
        ]
        return sorted(services, key=lambda service: (service.name.casefold(), service.id))

    def services_for_offices(self, office_ids: set[str] | None = None) -> list[AppointmentService]:
        catalog = self.catalog()
        service_ids = {
            int(relation["serviceId"])
            for relation in catalog["relations"]
            if relation.get("public") is not False
            and (office_ids is None or str(relation.get("officeId")) in office_ids)
        }
        return sorted(
            (
                AppointmentService(
                    id=int(item["id"]),
                    name=item["name"],
                    variant_id=item.get("variantId"),
                    parent_id=item.get("parentId"),
                )
                for item in catalog["services"]
                if int(item["id"]) in service_ids and item.get("name")
            ),
            key=lambda service: service.name.casefold(),
        )

    def offices_for_service(self, service_id: int) -> list[dict]:
        catalog = self.catalog()
        office_ids = {
            str(relation["officeId"])
            for relation in catalog["relations"]
            if int(relation.get("serviceId", -1)) == service_id
            and relation.get("public") is not False
        }
        return [office for office in catalog["offices"] if str(office.get("id")) in office_ids]

    def search(
        self,
        service: AppointmentService | int,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
        office_ids: list[str] | None = None,
    ) -> list[AppointmentSlot]:
        if isinstance(service, int):
            matches = [item for item in self.find_services("") if item.id == service]
            if not matches:
                raise LookupError(f"Unknown Munich appointment service ID: {service}")
            service = matches[0]

        start_date = start_date or dt.datetime.now(LOCAL_TIMEZONE).date()
        end_date = end_date or (start_date + dt.timedelta(days=180))
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        offices = self.offices_for_service(service.id)
        if office_ids is not None:
            requested_ids = {str(office_id) for office_id in office_ids}
            offices = [office for office in offices if str(office.get("id")) in requested_ids]
        if not offices:
            return []

        offices_by_id = {str(office["id"]): office for office in offices}
        payload = self._get_json(
            "available-calendar/",
            params={
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "officeIds": ",".join(offices_by_id),
                "serviceIds": str(service.id),
                "serviceCounts": "1",
            },
        )

        slots: list[AppointmentSlot] = []
        for day in payload.get("availableDays", []):
            try:
                day_date = dt.date.fromisoformat(str(day["date"])[:10])
            except (KeyError, ValueError):
                continue
            for office_result in day.get("offices", []):
                office_id = str(office_result.get("officeId", ""))
                office = offices_by_id.get(office_id)
                if office is None:
                    continue
                address_data = office.get("address") or {}
                address = " ".join(
                    str(part)
                    for part in (
                        address_data.get("street"),
                        address_data.get("house_number"),
                        address_data.get("postal_code"),
                        address_data.get("city"),
                    )
                    if part
                )
                for timestamp in office_result.get("appointments", []):
                    if LOCAL_TIMEZONE is None:
                        appointment_time = dt.datetime.fromtimestamp(int(timestamp)).astimezone()
                    else:
                        appointment_time = dt.datetime.fromtimestamp(
                            int(timestamp), tz=dt.timezone.utc
                        ).astimezone(LOCAL_TIMEZONE)
                    slots.append(
                        AppointmentSlot(
                            service=service,
                            office_id=office_id,
                            office_name=office.get("name", "Munich appointment office"),
                            address=address,
                            date=day_date,
                            time=appointment_time.strftime("%H:%M"),
                        )
                    )
        return sorted(slots, key=lambda slot: (slot.date, slot.time, slot.office_name))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search Munich's public appointment calendar by service name."
    )
    parser.add_argument("service", help="Full or partial appointment service name")
    parser.add_argument("--start", type=dt.date.fromisoformat, help="First date (YYYY-MM-DD)")
    parser.add_argument("--end", type=dt.date.fromisoformat, help="Last date (YYYY-MM-DD)")
    args = parser.parse_args()

    client = MunichAppointmentClient()
    try:
        services = client.find_services(args.service)
        if not services:
            print(f"No appointment service matched {args.service!r}.", file=sys.stderr)
            return 1
        if len(services) > 1:
            print("More than one service matched. Re-run with one of these exact names:")
            for service in services:
                print(f"  {service.id}: {service.name}")
            return 2

        service = services[0]
        start = args.start or dt.datetime.now(LOCAL_TIMEZONE).date()
        end = args.end or (start + dt.timedelta(days=180))
        print(f"{service.name} ({service.id})")
        print(f"Checking {start.isoformat()} through {end.isoformat()}…")
        slots = client.search(service, start, end)
    except (AppointmentApiError, ValueError, LookupError) as exc:
        print(f"Appointment search failed: {exc}", file=sys.stderr)
        return 1

    if not slots:
        print("No available appointments in this date range.")
    else:
        for slot in slots:
            print(f"{slot.date.isoformat()} {slot.time} — {slot.office_name}, {slot.address}")
        print(f"\nBook through the official site: {APPOINTMENT_PAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
