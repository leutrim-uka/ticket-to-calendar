"""Build an interoperable calendar file from reviewed, validated fields."""

from datetime import datetime, timezone
from uuid import uuid4

from icalendar import Calendar, Event

from domain import check_journey


def build_calendar(journey, timezone_name="Europe/Berlin", *, confirmed=False):
    if not confirmed:
        raise ValueError("Review and confirm the journey before export.")
    checked, errors = check_journey(journey, timezone_name)
    if errors:
        raise ValueError(" ".join(errors))
    calendar = Calendar()
    calendar.add("prodid", "-//Local Ticket to Calendar//EN")
    calendar.add("version", "2.0")
    event = Event()
    event.add("uid", str(uuid4()) + "@ticket-to-calendar.local")
    event.add("dtstamp", datetime.now(timezone.utc))
    # UTC avoids relying on clients to interpret an embedded time-zone definition.
    event.add("dtstart", checked.start.astimezone(timezone.utc))
    event.add("dtend", checked.end.astimezone(timezone.utc))
    prefix = journey.train_number.strip() if journey.train_number else "Train"
    event.add("summary", f"{prefix}: {journey.departure_station} → {journey.arrival_station}")
    event.add("location", journey.departure_station)
    description = [
        f"From: {journey.departure_station}", f"To: {journey.arrival_station}",
        f"Departure: {journey.departure_date} {journey.departure_time} ({timezone_name})",
        f"Arrival: {journey.arrival_date} {journey.arrival_time} ({timezone_name})",
    ]
    if journey.booking_reference:
        description.append("Booking reference: " + journey.booking_reference)
    event.add("description", "\n".join(description))
    calendar.add_component(event)
    return calendar.to_ical()
