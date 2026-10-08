"""Compatibility layer for the original bot, backed by Munich's current API."""

from __future__ import annotations

import datetime
from typing import ClassVar

from appointment_api import MunichAppointmentClient


_client = MunichAppointmentClient()
_APPOINTMENT_PAGE = "https://stadt.muenchen.de/buergerservice/terminvereinbarung.html"


class Meta(type):
    def __repr__(cls):
        return cls.get_name()


class Buro(metaclass=Meta):
    """Appointment department backed by matching offices in Munich's catalog."""

    office_match: ClassVar[tuple[str, ...]] = ()
    typical_match: ClassVar[tuple[str, ...]] = ()
    appointment_types: ClassVar[list[str] | None] = None
    appointment_type_date: ClassVar[datetime.datetime | None] = None

    @classmethod
    def get_available_appointment_types(cls) -> list[str]:
        now = datetime.datetime.now()
        if (
            cls.appointment_types is not None
            and cls.appointment_type_date is not None
            and (now - cls.appointment_type_date).total_seconds() < 3600
        ):
            return cls.appointment_types

        catalog = _client.catalog()
        office_ids = {
            str(office["id"])
            for office in catalog["offices"]
            if cls.matches_office(office)
        }
        cls.appointment_types = [
            service.name for service in _client.services_for_offices(office_ids)
        ]
        cls.appointment_type_date = now
        return cls.appointment_types

    @classmethod
    def matches_office(cls, office: dict) -> bool:
        terms = cls.office_match
        searchable = " ".join(
            str(office.get(key) or "")
            for key in ("name", "organization", "organizationUnit")
        ).casefold()
        searchable += " " + " ".join(
            str(value) for value in office.get("displayNameAlternatives", [])
        ).casefold()
        return any(term.casefold() in searchable for term in terms)

    @staticmethod
    def get_frame_url():
        return _APPOINTMENT_PAGE

    @staticmethod
    def get_info_message():
        return ""

    @staticmethod
    def _get_base_page():
        return _APPOINTMENT_PAGE

    @staticmethod
    def get_name():
        raise NotImplementedError

    @staticmethod
    def get_id():
        return "baseburo"

    @classmethod
    def get_typical_appointments(cls) -> list[tuple[int, str]]:
        return [
            (index, name)
            for index, name in enumerate(cls.get_available_appointment_types())
            if any(term.casefold() in name.casefold() for term in cls.typical_match)
        ]

    @staticmethod
    def get_buro_by_id(buro_id):
        return next(
            (department() for department in Buro.__subclasses__()
             if department.get_id() == buro_id),
            None,
        )


class DMV(Buro):
    office_match = ("Führerscheinstelle",)
    typical_match = ("Umschreibung", "Abholung")

    @staticmethod
    def get_name():
        return "Führerscheinstelle"

    @staticmethod
    def get_id():
        return "fs"


class CityHall(Buro):
    office_match = ("Bürgerbüro",)
    typical_match = ("An- oder Ummeldung", "Wohnsitz")

    @staticmethod
    def get_name():
        return "Bürgerbüro"

    @staticmethod
    def get_id():
        return "bb"


class KFZ(Buro):
    office_match = ("KfZ Zulassungsstelle", "Kfz-Zulassungsstelle")
    typical_match = ("Umschreibung", "Adressänderung", "Adresse")

    @staticmethod
    def get_name():
        return "Kfz-Zulassungsstelle"

    @staticmethod
    def get_id():
        return "kfz"


class Pension(Buro):
    office_match = ("Versicherungsamt",)
    typical_match = ("Wartezeit",)

    @staticmethod
    def get_name():
        return "Versicherungsamt"

    @staticmethod
    def get_id():
        return "va"


class KVR(Buro):
    office_match = ("Kreisverwaltungsreferat",)

    @staticmethod
    def get_name():
        return "KVR"

    @staticmethod
    def get_id():
        return "kvr"


class ForeignLabor(Buro):
    office_match = ("Servicestelle für Zuwanderung und Einbürgerung",)
    typical_match = ("Niederlassungserlaubnis", "Aufenthaltserteilung", "Blue Card")

    @staticmethod
    def get_name():
        return "Servicestelle für Zuwanderung und Einbürgerung"

    @staticmethod
    def get_id():
        return "ausl"


def get_termins(buro, termin_type):
    """Return available slots in the legacy shape consumed by worker.py."""

    services = [
        service
        for service in _client.services_for_offices(
            {
                str(office["id"])
                for office in _client.catalog()["offices"]
                if buro.matches_office(office)
            }
        )
        if service.name.casefold() == termin_type.casefold()
    ]
    if not services:
        return None

    slots = _client.search(services[0])
    result: dict[str, dict] = {}
    for slot in slots:
        entry = result.setdefault(
            slot.office_id,
            {"caption": f"{slot.office_name}, {slot.address}", "id": slot.office_id, "appoints": {}},
        )
        entry["appoints"].setdefault(slot.date.isoformat(), []).append(slot.time)

    for entry in result.values():
        for times in entry["appoints"].values():
            times.sort()
    return result


if __name__ == "__main__":
    from appointment_api import main

    raise SystemExit(main())
