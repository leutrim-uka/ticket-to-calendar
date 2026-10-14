import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from llm import ROOT, Extraction
from calendar_mcp_client import CalendarMCPError
from test_domain import complete_journey


class InterfaceTests(unittest.TestCase):
    def connect_calendar(self, at):
        calendars = [{"id": "cal-1", "name": "Workshop", "writable": True},
                     {"id": "cal-2", "name": "Other", "writable": True},
                     {"id": "readonly", "name": "Holidays", "writable": False}]
        with patch("calendar_mcp_client.list_apple_calendars", return_value=calendars):
            next(button for button in at.button if button.label == "Load Apple calendars").click().run()
        return at

    def start(self, journey=None):
        at = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
        at.text_input[1].set_value("gemma-fixture").run()
        result = Extraction(journey or complete_journey(), "{}", "gemma-fixture", 0.2, True)
        with patch("llm.extract_journey", return_value=result):
            next(button for button in at.button if button.label == "Extract journey").click().run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_full_review_and_export_then_edit_invalidation(self):
        at = self.start()
        prepare = next(button for button in at.button if button.label == "Prepare calendar event")
        self.assertTrue(prepare.disabled)
        at.checkbox(key="review_confirmed").check().run()
        next(button for button in at.button if button.label == "Prepare calendar event").click().run()
        self.assertTrue(at.session_state["calendar_bytes"].startswith(b"BEGIN:VCALENDAR"))
        at.text_input(key="review_arrival_time").set_value("12:00").run()
        self.assertFalse(at.session_state["review_confirmed"])
        with self.assertRaises(KeyError):
            at.session_state["calendar_bytes"]
        self.assertEqual(len(at.exception), 0)

    def test_missing_arrival_blocks_export_until_corrected(self):
        at = self.start(complete_journey(arrival_time=None, issues=["Arrival time missing"]))
        self.assertTrue(at.error)
        at.checkbox(key="review_confirmed").check().run()
        self.assertTrue(next(button for button in at.button if button.label == "Prepare calendar event").disabled)
        at.text_input(key="review_arrival_time").set_value("11:45").run()
        self.assertEqual(len(at.error), 0)
        self.assertFalse(at.session_state["review_confirmed"])

    def test_source_change_hides_review_and_export(self):
        at = self.start()
        at.text_area(key="source_text").set_value("A different booking.").run()
        self.assertTrue(any("changed" in warning.value for warning in at.warning))
        self.assertFalse(any(button.label == "Prepare calendar event" for button in at.button))
        self.assertEqual(len(at.exception), 0)

    def test_bad_extraction_shows_error_and_clears_old_result(self):
        at = self.start()
        with patch("llm.extract_journey", side_effect=ValueError("Invalid extraction")):
            next(button for button in at.button if button.label == "Extract journey").click().run()
        self.assertTrue(any("Invalid extraction" in error.value for error in at.error))
        self.assertFalse(any(button.label == "Prepare calendar event" for button in at.button))
        self.assertEqual(len(at.exception), 0)

    def test_calendar_save_requires_review_and_blocks_repeat(self):
        at = self.connect_calendar(self.start())
        self.assertEqual(len(at.selectbox(key="destination_calendar").options), 2)
        self.assertTrue(next(button for button in at.button if button.label == "Add to Apple Calendar").disabled)
        at.checkbox(key="review_confirmed").check().run()
        response = {"status": "created", "event_id": "event-1", "calendar_id": "cal-1", "calendar_name": "Workshop"}
        with patch("calendar_mcp_client.save_reviewed_event", return_value=response) as save:
            next(button for button in at.button if button.label == "Add to Apple Calendar").click().run()
            save.assert_called_once()
            self.assertTrue(save.call_args.kwargs["confirmed"])
        self.assertTrue(next(button for button in at.button if button.label == "Add to Apple Calendar").disabled)
        self.assertTrue(any("Added to Workshop" in item.value for item in at.success))
        self.assertEqual(len(at.exception), 0)

    def test_destination_change_resets_review(self):
        at = self.connect_calendar(self.start())
        at.checkbox(key="review_confirmed").check().run()
        at.selectbox(key="destination_calendar").set_value("cal-2").run()
        self.assertFalse(at.session_state["review_confirmed"])
        self.assertTrue(next(button for button in at.button if button.label == "Add to Apple Calendar").disabled)

    def test_calendar_error_retains_ics_fallback_without_auto_retry(self):
        at = self.connect_calendar(self.start())
        at.checkbox(key="review_confirmed").check().run()
        with patch("calendar_mcp_client.save_reviewed_event", side_effect=CalendarMCPError("Calendar timed out")) as save:
            next(button for button in at.button if button.label == "Add to Apple Calendar").click().run()
            self.assertTrue(any("timed out" in error.value for error in at.error))
            at.run()
            save.assert_called_once()
        self.assertEqual(len(at.session_state["calendar_saves"]), 0)
        self.assertFalse(next(button for button in at.button if button.label == "Prepare calendar event").disabled)
        self.assertEqual(len(at.exception), 0)


if __name__ == "__main__":
    unittest.main()
