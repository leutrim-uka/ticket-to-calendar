import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import calendar_mcp_client as client
import calendar_mcp_server as server
from test_domain import complete_journey


class MCPTests(unittest.TestCase):
    def test_review_validation_prevents_protocol_call(self):
        with patch.object(client, "request") as call:
            for journey, confirmed in ((complete_journey(), False), (complete_journey(arrival_time=None), True)):
                with self.assertRaises(client.CalendarMCPError):
                    client.save_reviewed_event(journey, "Europe/Berlin", "cal-1", confirmed=confirmed)
            call.assert_not_called()

    def test_utc_and_stable_request_identifier(self):
        args = client.event_arguments(complete_journey(), "Europe/Berlin", "cal-1", confirmed=True)
        self.assertTrue(args["start"].endswith("+00:00"))
        self.assertEqual(args, client.event_arguments(complete_journey(), "Europe/Berlin", "cal-1", confirmed=True))
        self.assertNotEqual(args["request_id"], client.event_arguments(complete_journey(), "Europe/Berlin", "cal-2", confirmed=True)["request_id"])

    def test_server_rejects_unconfirmed_or_naive_times(self):
        args = client.event_arguments(complete_journey(), "Europe/Berlin", "cal-1", confirmed=True)
        with patch.object(server, "run_calendar") as native:
            with self.assertRaises(ValueError):
                server.create_event(**{**args, "confirmed": False})
            with self.assertRaises(ValueError):
                server.create_event(**{**args, "start": "2026-12-01T09:00:00"})
            native.assert_not_called()

    def test_booking_data_is_passed_as_json_not_script_code(self):
        payload = {"action": "create", "title": 'quote " ; $(touch /tmp/nope)\nü'}
        with patch.object(server.sys, "platform", "darwin"), patch.object(server.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '{"status":"created"}', "")) as run:
            server.run_calendar(payload)
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["/usr/bin/osascript", "-l"])
        self.assertEqual(json.loads(command[-1]), payload)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_permission_and_timeout_messages(self):
        with patch.object(server.sys, "platform", "darwin"), patch.object(server.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "Not authorized (-1743)")):
            with self.assertRaisesRegex(ValueError, "Automation"):
                server.run_calendar({"action": "list"})
        with patch.object(server.sys, "platform", "darwin"), patch.object(server.subprocess, "run", side_effect=subprocess.TimeoutExpired("osascript", 60)):
            with self.assertRaisesRegex(ValueError, "may have been saved"):
                server.run_calendar({"action": "create"})

    def test_real_mcp_roundtrip_discovery_creation_and_duplicate(self):
        # A real MCP subprocess, with only its native Calendar backend replaced.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(__file__).resolve().parents[1]
            state = Path(folder) / "state.json"
            fixture = Path(folder) / "fixture.py"
            fixture.write_text(f'''import sys, json
from pathlib import Path
sys.path.insert(0, {str(root)!r})
import calendar_mcp_server as server
state = Path({str(state)!r})
def backend(request):
    if request["action"] == "list":
        return {{"calendars": [{{"id": "cal-1", "name": "Workshop", "writable": True}}]}}
    seen = json.loads(state.read_text()) if state.exists() else []
    duplicate = request["request_id"] in seen
    if not duplicate:
        seen.append(request["request_id"])
        state.write_text(json.dumps(seen))
    return {{"status": "already_exists" if duplicate else "created", "event_id": "event-1", "calendar_id": "cal-1", "calendar_name": "Workshop"}}
server.run_calendar = backend
server.mcp.run(transport="stdio")
''')
            discovered = client.request(server_path=fixture)
            self.assertEqual({tool["name"] for tool in discovered["tools"]}, {"list_calendars", "create_event"})
            self.assertEqual(client.request("list_calendars", server_path=fixture)["calendars"][0]["name"], "Workshop")
            args = client.event_arguments(complete_journey(), "Europe/Berlin", "cal-1", confirmed=True)
            self.assertEqual(client.request("create_event", args, server_path=fixture)["status"], "created")
            self.assertEqual(client.request("create_event", args, server_path=fixture)["status"], "already_exists")
            with self.assertRaisesRegex(client.CalendarMCPError, "review and confirm"):
                client.request("create_event", {**args, "confirmed": False}, server_path=fixture)
            self.assertEqual(len(json.loads(state.read_text())), 1)

    def test_invalid_save_response_is_not_success(self):
        with patch.object(client, "request", return_value={"status": "created"}):
            with self.assertRaisesRegex(client.CalendarMCPError, "did not confirm"):
                client.save_reviewed_event(complete_journey(), "Europe/Berlin", "cal-1", confirmed=True)


if __name__ == "__main__":
    unittest.main()
