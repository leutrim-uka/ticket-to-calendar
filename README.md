# Ticket to Calendar — local LLM + MCP

Paste booking text → extract with your local model → review → save directly to
Apple Calendar through a local MCP server. `.ics` download remains available.
Keep your existing Gemma model. Aider is optional for editing the project.

## Run the updated app

Unzip into a new folder, open `ticket-to-calendar` in VS Code, and use its terminal.
If you previously saved your model identifier, copy that identifier into this
project's `settings.json` or select your model in the interface.

1. Load Gemma in LM Studio and start its local API server on port **1234**.
2. Install the locked dependencies and start the interface:

```bash
uv sync --locked
uv run --locked streamlit run app.py
```

3. Open [http://localhost:8501](http://localhost:8501). Click **Find models** and
   select your Gemma model.
4. Click **Load Apple calendars**. On first use, macOS may ask your terminal or
   VS Code for permission to control Calendar. Allow it. If the request times out
   while you respond, finish granting permission and click the button again.
5. Click **Extract journey**. Correct the fields against the booking and choose
   a **Destination calendar**. Only writable calendars appear; identical names
   are distinguished by their IDs.
6. Check the review checkbox and click **Add to Apple Calendar**. The app shows
   the destination after Calendar confirms the save. Open Calendar to inspect it.

No separate MCP installation, terminal server process, API token, Node.js, Swift
compiler, or Calendar account credentials are needed. The app starts its bundled
MCP server automatically using the same Python environment.

Direct Calendar access requires **macOS and Calendar.app**. `.ics` works on other
operating systems. Initial dependencies, models, and inference engines need internet;
local inference and MCP run on your laptop. Calendars connected to iCloud, Exchange,
or Google may sync using their accounts. For a demo, you can create and select a
**Workshop** calendar in Calendar. The app itself does not create calendars.

## What is MCP here?

| Component | Role |
|---|---|
| `llm.py` + LM Studio | Extract structured journey details from booking text. |
| `app.py` | Show editable fields, validate them, and require user review. |
| `calendar_mcp_client.py` | Connect, discover the server's tools, and call them. |
| `calendar_mcp_server.py` | Expose `list_calendars` and `create_event` with the official MCP SDK. |
| `calendar_bridge.js` | Use macOS Calendar automation to list calendars and save events. |
| `calendar_export.py` | Produce the optional `.ics` file. |

The app talks to LM Studio over local HTTP and to the MCP server over **stdio**:
its standard input/output. MCP needs no second HTTP port. MCP defines discovery,
argument schemas, tool calls, and results. See [MCP_WALKTHROUGH.md](MCP_WALKTHROUGH.md).

The model extracts the journey. The **reviewed button click** initiates the MCP
call. This version does not require model tool calling or an additional LLM call.
LM Studio's own MCP configuration is not used.

## Review and duplicate handling

- Saving requires complete dates/times, a valid time zone, arrival after departure,
  a writable destination, and explicit review.
- Editing a field, time zone, or destination clears the review checkbox.
- Changing the source requires a fresh extraction.
- The server also rejects unconfirmed or invalid creation requests.
- After saving, that event's button is disabled for the current app session.
- A stable identifier is included in the event notes. Repeating the same reviewed
  event in the same calendar returns the existing event while that marker remains.
  Changed details create a separate event; they do not update the previous event.
- Failed/timed-out writes are not retried automatically. Check Calendar before retrying:
  the event may have been saved even when its response was lost. Duplicate lookup
  reduces repeat additions; it cannot guarantee against simultaneous independent writes.

Human review applies to this app's calls. Another host connected to this MCP server
must provide its own review interface. A `confirmed` argument cannot independently
prove that a person reviewed the event.

## Check MCP separately from the model

Inspect actual MCP tools without accessing Calendar:

```bash
uv run --locked check_calendar.py --tools
```

List calendars and verify permissions; this creates no events:

```bash
uv run --locked check_calendar.py
```

For model diagnosis:

```bash
uv run --locked check_local.py
uv run --locked check_local.py --select "EXACT_MODEL_ID"
```

## Troubleshooting

| Problem | Action |
|---|---|
| Automation denied / error `-1743` | Open **System Settings → Privacy & Security → Automation** and allow Calendar under the terminal or VS Code used to start the app. Restart from the same app if necessary. |
| No writable calendars | Open Calendar, check the account/calendar, create a writable calendar if needed, then reload. |
| Calendar save times out | Check Calendar before retrying. First-use permission prompts may delay requests. `.ics` export remains available. |
| Different displayed hour | UTC timestamps are displayed in Calendar's configured zone. Verify the journey's time zone. |
| LM Studio cannot connect | Start its local server on 1234 and select the actual model identifier. |
| JSON schema rejected | Turn off **Schema-constrained JSON** and retry. Python still validates the response. |

If LM Studio requires authentication, set `LM_STUDIO_API_KEY` before launching.
No OpenAI account is needed. The client rejects non-local model endpoints.
Stop the app with `Ctrl+C`. After initial installation, run offline with:

```bash
uv run --offline --locked streamlit run app.py
```

## Examples and limits

Four fictional examples cover clear bookings, missing arrival information,
overnight journeys, and ambiguous dates. Resolve missing information from the source;
the app does not invent the following day's arrival date.

Text only, one journey, one time zone for both stations. PDF/OCR, timetables,
email access, and updating/deleting existing events are outside this version.
Ambiguous/nonexistent clock-change times are rejected. Validation cannot establish
that plausible extracted stations/dates actually appeared in the source.

The app has no booking database. Extraction downloads contain the source and
reviewed fields. Calendar events contain journey details and the optional booking
reference. LM Studio request logs are controlled by LM Studio.

## Tests

```bash
uv run --locked python -m unittest discover -s tests -v
```

Tests cover extraction through a local HTTP fixture, validation, `.ics` round trips,
interface review/save state, and real MCP subprocess communication with a fixture
replacing only the macOS backend. They do not establish successful Calendar access
on your Mac or Gemma extraction quality. See `VERIFICATION.md`.

References: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
[Apple Calendar scripting](https://developer.apple.com/library/archive/documentation/AppleApplications/Conceptual/CalendarScriptingGuide/Calendar-CreateanEvent.html),
[LM Studio structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output).
