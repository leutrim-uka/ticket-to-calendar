import unittest
from datetime import datetime, timezone

from icalendar import Calendar

from calendar_export import build_calendar
from domain import Journey, check_journey


def complete_journey(**changes):
    values = {
        "departure_station": "Berlin Hbf", "arrival_station": "Leipzig Hbf",
        "departure_date": "2026-10-20", "departure_time": "10:30",
        "arrival_date": "2026-10-20", "arrival_time": "11:45",
        "train_number": "ICE 1001", "booking_reference": "DEMO42", "issues": [],
    }
    values.update(changes)
    return Journey(**values)


class JourneyTests(unittest.TestCase):
    def test_missing_value_blocks_export(self):
        journey = complete_journey(arrival_time=None)
        checked, errors = check_journey(journey)
        self.assertIsNone(checked)
        self.assertIn("Missing arrival time.", errors)
        with self.assertRaises(ValueError):
            build_calendar(journey, confirmed=True)

    def test_overnight_requires_arrival_date(self):
        wrong = complete_journey(departure_time="22:10", arrival_time="07:20")
        self.assertTrue(check_journey(wrong)[1])
        right = wrong.model_copy(update={"arrival_date": "2026-10-21"})
        checked, errors = check_journey(right)
        self.assertEqual(errors, [])
        self.assertGreater(checked.end.timestamp(), checked.start.timestamp())

    def test_invalid_date_format_or_timezone_blocks_export(self):
        for changes in ({"departure_date": "2026-02-30"}, {"departure_time": "25:00"}, {"departure_date": "20.10.2026"}):
            self.assertTrue(check_journey(complete_journey(**changes))[1])
        self.assertTrue(check_journey(complete_journey(), "Invalid/Zone")[1])

    def test_dst_gap_and_ambiguous_time_are_rejected(self):
        for date in ("2026-03-29", "2026-10-25"):
            journey = complete_journey(departure_date=date, departure_time="02:30", arrival_date=date, arrival_time="04:00")
            self.assertTrue(check_journey(journey)[1])

    def test_confirmation_is_required(self):
        with self.assertRaisesRegex(ValueError, "confirm"):
            build_calendar(complete_journey())

    def test_calendar_round_trip_and_utc_conversion(self):
        calendar = Calendar.from_ical(build_calendar(complete_journey(), confirmed=True))
        events = calendar.walk("VEVENT")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.decoded("dtstart"), datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc))
        self.assertEqual(event.decoded("dtend"), datetime(2026, 10, 20, 9, 45, tzinfo=timezone.utc))
        self.assertIn("Berlin Hbf → Leipzig Hbf", str(event["summary"]))
        self.assertIn("DEMO42", str(event["description"]))
        self.assertTrue(event["uid"])

    def test_escaping_prevents_calendar_property_injection(self):
        journey = complete_journey(departure_station="Station; Süd, Gleis 1\nBEGIN:VEVENT", booking_reference="X\\Y\nSUMMARY:Injected")
        parsed = Calendar.from_ical(build_calendar(journey, confirmed=True))
        self.assertEqual(len(parsed.walk("VEVENT")), 1)
        self.assertEqual(str(parsed.walk("VEVENT")[0]["location"]), journey.departure_station)


if __name__ == "__main__":
    unittest.main()
