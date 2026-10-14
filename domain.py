"""Typed extraction result and deterministic validation before calendar export."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict


class Journey(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    departure_station: str | None
    arrival_station: str | None
    departure_date: str | None
    departure_time: str | None
    arrival_date: str | None
    arrival_time: str | None
    train_number: str | None
    booking_reference: str | None
    issues: list[str]


@dataclass
class CheckedJourney:
    journey: Journey
    start: datetime
    end: datetime
    timezone_name: str


def localized(date_text, time_text, zone):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        raise ValueError("use YYYY-MM-DD for dates")
    if not re.fullmatch(r"\d{2}:\d{2}", time_text):
        raise ValueError("use HH:MM in 24-hour format for times")
    naive = datetime.fromisoformat(f"{date_text}T{time_text}")
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    valid = [item for item in (first, second)
             if item.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive]
    if not valid:
        raise ValueError("this local time does not exist because the clock moves forward")
    if len(valid) == 2 and first.utcoffset() != second.utcoffset():
        raise ValueError("this local time occurs twice during the clock change; this demo cannot resolve it")
    return valid[0]


def check_journey(journey, timezone_name="Europe/Berlin"):
    """Return (validated result, errors); never guess dates or journey duration."""
    errors = []
    for field in ("departure_station", "arrival_station", "departure_date", "departure_time", "arrival_date", "arrival_time"):
        value = getattr(journey, field)
        if not value or not value.strip():
            errors.append(f"Missing {field.replace('_', ' ')}.")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append("Choose a valid IANA time zone, for example Europe/Berlin.")
        return None, errors
    if errors:
        return None, errors
    start, end = None, None
    for label in ("departure", "arrival"):
        try:
            value = localized(getattr(journey, label + "_date"), getattr(journey, label + "_time"), zone)
            if label == "departure":
                start = value
            else:
                end = value
        except ValueError as exc:
            errors.append(f"Invalid {label}: {exc}.")
    if start and end and end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
        errors.append("Arrival must be after departure. For an overnight trip, verify the arrival date.")
    if errors:
        return None, errors
    return CheckedJourney(journey, start, end, timezone_name), []
