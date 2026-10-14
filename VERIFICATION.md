# Verification

Updated 2026-10-12 using Python 3.12 on Linux.

- All 27 automated tests: passed.
- JavaScript bridge syntax check: passed.
- Original 17 extraction, domain/calendar-file, and interface tests retained.
- Seven MCP tests: review/validation guards, UTC conversion, stable request IDs,
  argument validation, data/script separation, permission/timeout errors, invalid
  responses, and real MCP discovery/calls over stdio with fixture duplicate handling.
- Three added interface tests: confirmed saving, destination changes, repeated-save
  blocking, error handling without automatic retry, and availability of `.ics` export.
- Actual bundled MCP server discovery works without Calendar access.

MCP tests run the real SDK/server with only the native Calendar backend replaced.
The duplicate fixture verifies protocol behavior; native marker lookup needs a Mac.

Not available here: Calendar.app, macOS permission prompts, native event creation,
real Calendar duplicate lookup, iCloud sync, or your Gemma/LM Studio combination.
Check these locally using the README. No event has been added to your Calendar here.
