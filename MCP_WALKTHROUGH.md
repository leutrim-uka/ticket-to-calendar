# How the Calendar MCP extension works

## 1. Extract and review

`app.py → llm.py → localhost:1234/v1 → LM Studio → Gemma`

This is an ordinary model API call. The model returns journey JSON. Python checks
its structure/dates, and the app lets the user correct and confirm the details.

## 2. Discover Calendar tools

Clicking **Load Apple calendars** calls `list_apple_calendars()` in the client.
The client starts `calendar_mcp_server.py` using the project's Python, initializes
an MCP session over stdio, and calls `list_tools()`. It verifies `list_calendars`
is available, calls it, receives calendar IDs/names/writability, and closes the process.

Run `uv run --locked check_calendar.py --tools` to see the actual descriptions
and JSON schemas. The server's `@mcp.tool()` decorators and Python type hints
produce the schemas through the official SDK.

## 3. Choose a destination and confirm

The app offers writable calendars and requires a review checkbox. Changing the
journey or destination clears confirmation. Extraction alone never triggers a write.

## 4. Invoke the MCP tool

`event_arguments()` validates the reviewed journey again, converts dates to UTC,
and builds arguments containing `calendar_id`, `title`, `start`, `end`, `location`,
`notes`, a deterministic `request_id`, and `confirmed: true`.

The client opens a session and invokes:

```python
result = await session.call_tool("create_event", arguments=arguments)
```

That invocation uses MCP. Constructing event details and converting times are
ordinary Python application logic. This version calls the tool from the reviewed
button; it does not ask the model to choose a tool.

## 5. Save through the macOS adapter

The server validates the arguments and runs `calendar_bridge.js` through
`/usr/bin/osascript`. Journey text arrives as JSON data, not generated script code.
The bridge selects Calendar by its ID, checks writability, looks for a previous
request marker, and creates the event through Calendar.app automation.

Calendar automation is the underlying action. MCP is the communication protocol
around discovery, invocation, and the result. The returned result includes the
event UID, destination, and `created` or `already_exists` status.

## Roles in this architecture

| Term | Implementation |
|---|---|
| MCP host | The ticket app coordinating input, review, and actions. |
| MCP client | `calendar_mcp_client.py`, its connection to the server. |
| MCP server | `calendar_mcp_server.py`, publishing the tools. |
| Underlying service | Calendar.app, controlled by the local automation bridge. |

LM Studio provides inference here. Aider may help edit code but is not in the
application's runtime path. No LM Studio MCP configuration is required.

## Workshop extensions

This implementation demonstrates MCP initialization, discovery, schemas,
invocation, results, and user review. A model-directed version would also give
the model the discovered tool schemas, receive its proposed call, and execute
that proposal after review. The reviewed-button version works with extraction
models that do not support tool calling.
