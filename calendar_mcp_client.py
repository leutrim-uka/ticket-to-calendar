"""The app's MCP client: launches a local server over stdio, discovers and calls tools."""

import asyncio
import hashlib
import json
import sys
from datetime import timedelta, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from domain import check_journey

SERVER = Path(__file__).with_name("calendar_mcp_server.py")


class CalendarMCPError(ValueError):
    pass


def _error_message(error):
    if isinstance(error, BaseExceptionGroup):
        return " ".join(_error_message(item) for item in error.exceptions)
    return str(error) or type(error).__name__


async def _request(tool: str | None, arguments: dict, *, server_path=SERVER):
    parameters = StdioServerParameters(command=sys.executable, args=[str(server_path)])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=75)) as session:
            await session.initialize()
            available = await session.list_tools()
            tools = {item.name: item for item in available.tools}
            if tool is None:
                return {"tools": [item.model_dump(mode="json") for item in available.tools]}
            if tool not in tools:
                raise CalendarMCPError(f"Calendar MCP server does not expose {tool}.")
            result = await session.call_tool(tool, arguments=arguments)
            messages = [item.text for item in result.content if item.type == "text"]
            if result.isError:
                raise CalendarMCPError(" ".join(messages))
            if result.structuredContent is not None:
                return result.structuredContent
            return json.loads("\n".join(messages))


def request(tool=None, arguments=None, *, server_path=SERVER):
    """One MCP session per action; subprocess cleanup is automatic. No write retries."""
    try:
        return asyncio.run(_request(tool, arguments or {}, server_path=server_path))
    except Exception as exc:
        raise CalendarMCPError(_error_message(exc)) from exc


def list_apple_calendars():
    response = request("list_calendars")
    calendars = response.get("calendars")
    if not isinstance(calendars, list):
        raise CalendarMCPError("Calendar server returned an invalid calendar list.")
    for item in calendars:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("name"), str) or not isinstance(item.get("writable"), bool):
            raise CalendarMCPError("Calendar server returned an invalid calendar entry.")
    return calendars


def event_arguments(journey, timezone_name, calendar_id, *, confirmed=False):
    if confirmed is not True:
        raise CalendarMCPError("Review and confirm the journey before saving to Calendar.")
    checked, errors = check_journey(journey, timezone_name)
    if errors:
        raise CalendarMCPError(" ".join(errors))
    if not calendar_id or not calendar_id.strip():
        raise CalendarMCPError("Choose a destination calendar.")
    prefix = journey.train_number.strip() if journey.train_number else "Train"
    notes = [f"From: {journey.departure_station}", f"To: {journey.arrival_station}",
             f"Departure: {journey.departure_date} {journey.departure_time} ({timezone_name})",
             f"Arrival: {journey.arrival_date} {journey.arrival_time} ({timezone_name})"]
    if journey.booking_reference:
        notes.append("Booking reference: " + journey.booking_reference)
    arguments = {"calendar_id": calendar_id,
                 "title": f"{prefix}: {journey.departure_station} → {journey.arrival_station}",
                 "start": checked.start.astimezone(timezone.utc).isoformat(),
                 "end": checked.end.astimezone(timezone.utc).isoformat(),
                 "location": journey.departure_station, "notes": "\n".join(notes)}
    arguments["request_id"] = hashlib.sha256(json.dumps(arguments, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    arguments["confirmed"] = True
    return arguments


def save_reviewed_event(journey, timezone_name, calendar_id, *, confirmed=False):
    arguments = event_arguments(journey, timezone_name, calendar_id, confirmed=confirmed)
    response = request("create_event", arguments)
    if response.get("status") not in ("created", "already_exists") or not response.get("event_id") or response.get("calendar_id") != calendar_id:
        raise CalendarMCPError("Calendar did not confirm the save. Check Calendar before trying again.")
    return response
