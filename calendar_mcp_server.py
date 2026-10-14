"""Two local MCP tools: discover calendars and create a reviewed event.

The MCP protocol is handled by the official Python SDK. Calendar access uses
macOS JavaScript for Automation, not a network service or generated code.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Ticket to Apple Calendar", log_level="ERROR")
BRIDGE = Path(__file__).with_name("calendar_bridge.js")


def run_calendar(request: dict) -> dict:
    if sys.platform != "darwin":
        raise ValueError("Direct Apple Calendar access requires macOS. Use the .ics export on this computer.")
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", str(BRIDGE), json.dumps(request, ensure_ascii=False)],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Calendar timed out. Check Calendar before trying again; the event may have been saved.") from exc
    if result.returncode:
        detail = result.stderr.strip()
        if "-1743" in detail or "not authorized" in detail.lower():
            raise ValueError("Allow your terminal or VS Code to control Calendar in System Settings → Privacy & Security → Automation, then retry.")
        raise ValueError("Apple Calendar could not complete the action: " + detail)
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("Calendar returned an unreadable result. Check Calendar before trying again.") from exc


@mcp.tool()
def list_calendars() -> dict:
    """List Calendar.app calendars with their stable IDs, names, and writable flags."""
    return run_calendar({"action": "list"})


@mcp.tool()
def create_event(calendar_id: str, title: str, start: str, end: str,
                 location: str, notes: str, request_id: str, confirmed: bool) -> dict:
    """Save one user-reviewed event. Requires confirmation, calendar ID, and offset-aware ISO timestamps.

    A repeated request_id returns the existing event instead of adding another.
    Returns status (created/already_exists), event_id, calendar_id, and calendar_name.
    """
    if confirmed is not True:
        raise ValueError("The user must review and confirm the event before saving.")
    if not calendar_id.strip() or not title.strip():
        raise ValueError("A selected calendar and event title are required.")
    if not re.fullmatch(r"[0-9a-f]{64}", request_id):
        raise ValueError("request_id must be the reviewed event's SHA-256 identifier.")
    first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if first.utcoffset() is None or last.utcoffset() is None:
        raise ValueError("Start and end must include a time-zone offset.")
    if last.astimezone(timezone.utc) <= first.astimezone(timezone.utc):
        raise ValueError("The event end must be after its start.")
    return run_calendar({"action": "create", "calendar_id": calendar_id, "title": title,
                         "start": start, "end": end, "location": location,
                         "notes": notes, "request_id": request_id})


if __name__ == "__main__":
    mcp.run(transport="stdio")
