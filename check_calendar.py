"""Read-only checks; never creates a calendar event."""

import argparse
import json

from calendar_mcp_client import CalendarMCPError, list_apple_calendars, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", action="store_true", help="Inspect MCP discovery without accessing Calendar")
    args = parser.parse_args()
    try:
        result = request() if args.tools else {"calendars": list_apple_calendars()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except CalendarMCPError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
