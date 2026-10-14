"""Booking extraction, user review, and Calendar creation through MCP."""

import json

import streamlit as st
from openai import OpenAIError

from calendar_export import build_calendar
from calendar_mcp_client import CalendarMCPError, event_arguments, list_apple_calendars, save_reviewed_event
from domain import Journey, check_journey
from llm import ROOT, extract_journey, friendly_error, list_models, load_settings

st.set_page_config(page_title="Ticket to Calendar", page_icon="🚆", layout="wide")

EXAMPLES = {"Clear booking": "clear.txt", "Missing arrival": "missing.txt", "Overnight journey": "overnight.txt", "Ambiguous date": "ambiguous.txt"}
FIELDS = {
    "departure_station": "Departure station", "arrival_station": "Arrival station",
    "departure_date": "Departure date · YYYY-MM-DD", "departure_time": "Departure time · HH:MM",
    "arrival_date": "Arrival date · YYYY-MM-DD", "arrival_time": "Arrival time · HH:MM",
    "train_number": "Train number", "booking_reference": "Booking reference",
}


def load_example():
    st.session_state.source_text = (ROOT / "examples" / EXAMPLES[st.session_state.example]).read_text(encoding="utf-8")
    st.session_state.pop("extraction", None)
    st.session_state.pop("calendar_bytes", None)


def invalidate_export():
    st.session_state.pop("calendar_bytes", None)


def invalidate_review():
    invalidate_export()
    st.session_state.review_confirmed = False


try:
    settings = load_settings()
except (OSError, ValueError) as exc:
    st.error(friendly_error(exc))
    st.stop()

with st.sidebar:
    st.markdown("### Connection")
    st.caption("LM Studio on your laptop")
    endpoint = st.text_input("Local endpoint", value=settings.base_url)
    if st.button("Find models", use_container_width=True):
        try:
            st.session_state.models = list_models(settings.model_copy(update={"base_url": endpoint}))
            if not st.session_state.models:
                st.warning("No models listed. Load your model in LM Studio.")
        except (OpenAIError, OSError, ValueError) as exc:
            st.error(friendly_error(exc))
    choices = st.session_state.get("models", [])
    if choices:
        index = choices.index(settings.model) if settings.model in choices else 0
        model = st.selectbox("Model", choices, index=index)
    else:
        model = st.text_input("Exact model identifier", value=settings.model, placeholder="Click Find models above")
    structured = st.checkbox("Schema-constrained JSON", value=settings.structured_output)
    st.caption("Switch off only if your engine rejects JSON-schema output. Python still validates the response.")
    active = settings.model_copy(update={"base_url": endpoint, "model": model, "structured_output": structured})
    st.divider()
    st.markdown("### Apple Calendar")
    st.caption("Direct save on macOS. Allow Calendar automation when prompted.")
    if st.button("Load Apple calendars", use_container_width=True):
        invalidate_review()
        st.session_state.pop("apple_calendars", None)
        try:
            with st.spinner("Connecting to Apple Calendar…"):
                st.session_state.apple_calendars = list_apple_calendars()
            if not any(item["writable"] for item in st.session_state.apple_calendars):
                st.warning("No writable calendars found. Create one in Calendar, then reload.")
        except CalendarMCPError as exc:
            st.error(str(exc))

st.caption("LOCAL LLM DEMO")
st.title("From booking to calendar.")
st.markdown("Paste a train booking. Extract the journey on your laptop, review the details, and add it to your calendar.")

source_panel, review_panel = st.columns([1, 1], gap="large")
with source_panel:
    st.subheader("1 · Booking text")
    sample, action = st.columns([2, 1])
    with sample:
        st.selectbox("Try an example", list(EXAMPLES), key="example", label_visibility="collapsed")
    with action:
        st.button("Load example", on_click=load_example, use_container_width=True)
    if "source_text" not in st.session_state:
        st.session_state.source_text = (ROOT / "examples/clear.txt").read_text(encoding="utf-8")
    source = st.text_area("Booking email or ticket text", key="source_text", height=320, max_chars=12000, on_change=invalidate_review)
    if st.button("Extract journey", type="primary", use_container_width=True, disabled=not model.strip() or not source.strip()):
        st.session_state.pop("extraction", None)
        invalidate_export()
        try:
            with st.spinner("Reading the booking with your local model…"):
                result = extract_journey(source, active)
            st.session_state.extraction = result
            st.session_state.extracted_source = source
            for field in FIELDS:
                st.session_state["review_" + field] = getattr(result.journey, field) or ""
            st.session_state.review_timezone = "Europe/Berlin"
            st.session_state.review_confirmed = False
        except (OpenAIError, OSError, ValueError) as exc:
            st.error(friendly_error(exc))
    st.caption("One journey at a time. Built-in examples are fictional. Dates and times must be checked against the source.")

with review_panel:
    st.subheader("2 · Review the journey")
    result = st.session_state.get("extraction")
    if result is None:
        st.info("Choose your model in the Connection panel, then extract a journey. The details will appear here.")
    elif source != st.session_state.extracted_source:
        invalidate_export()
        st.warning("The booking text changed. Extract it again before reviewing or downloading an event.")
    else:
        st.caption(f"{result.elapsed_seconds:.1f} seconds · {result.model}")
        for issue in result.journey.issues:
            st.warning(issue)
        if result.journey.issues:
            st.caption("Resolve these points from the original booking before confirming below.")
        values = {}
        for pair in (("departure_station", "arrival_station"), ("departure_date", "departure_time"), ("arrival_date", "arrival_time"), ("train_number", "booking_reference")):
            columns = st.columns(2)
            for column, field in zip(columns, pair):
                with column:
                    text = st.text_input(FIELDS[field], key="review_" + field, on_change=invalidate_review)
                    values[field] = text.strip() or None
        timezone_name = st.text_input("Time zone for both stations", key="review_timezone", on_change=invalidate_review)
        st.caption("Default: Europe/Berlin. This demo supports journeys within one time zone.")
        reviewed = Journey(**values, issues=result.journey.issues)
        checked, errors = check_journey(reviewed, timezone_name)
        if errors:
            for error in errors:
                st.error(error)
        else:
            duration = (checked.end.timestamp() - checked.start.timestamp()) / 60
            st.success(f"{reviewed.departure_station} → {reviewed.arrival_station} · {duration / 60:.1f} hours")
        writable = [item for item in st.session_state.get("apple_calendars", []) if item["writable"]]
        calendar_id = None
        if writable:
            by_id = {item["id"]: item for item in writable}
            calendar_id = st.selectbox("Destination calendar", list(by_id), key="destination_calendar",
                                       format_func=lambda identifier: f"{by_id[identifier]['name']} · {identifier[-8:]}",
                                       on_change=invalidate_review)
        else:
            st.caption("For direct save, click Load Apple calendars in the sidebar and choose a destination.")
        confirmed = st.checkbox("I checked these details against the booking and resolved any warnings.", key="review_confirmed", on_change=invalidate_export)
        request_id = None
        if confirmed and not errors and calendar_id:
            request_id = event_arguments(reviewed, timezone_name, calendar_id, confirmed=True)["request_id"]
        saves = st.session_state.setdefault("calendar_saves", {})
        saved = saves.get(request_id)
        if st.button("Add to Apple Calendar", type="primary",
                     disabled=bool(errors) or not confirmed or not calendar_id or bool(saved),
                     use_container_width=True):
            try:
                with st.spinner("Saving the reviewed event to Calendar…"):
                    saved = save_reviewed_event(reviewed, timezone_name, calendar_id, confirmed=confirmed)
                saves[request_id] = saved
                st.rerun()
            except CalendarMCPError as exc:
                st.error(str(exc))
                st.warning("Calendar did not confirm this action. Check Calendar before trying again. The app does not retry automatically.")
        if saved:
            label = "Added to" if saved["status"] == "created" else "Already exists in"
            st.success(f"{label} {saved['calendar_name']}. This event will not be added again by this session.")
        if st.button("Prepare calendar event", type="primary", disabled=bool(errors) or not confirmed, use_container_width=True):
            st.session_state.calendar_bytes = build_calendar(reviewed, timezone_name, confirmed=confirmed)
        if "calendar_bytes" in st.session_state:
            st.download_button("Download calendar event (.ics)", st.session_state.calendar_bytes,
                               file_name="train-journey.ics", mime="text/calendar", use_container_width=True)
            st.caption("Open the file in your calendar app to import it. Nothing is added automatically.")
        with st.expander("Inspect the extracted JSON"):
            st.json(result.journey.model_dump())
            st.caption("JSON structure is checked in Python. Correct-looking fields can still be factually wrong.")
        record = {
            "source": st.session_state.extracted_source, "model": result.model,
            "elapsed_seconds": round(result.elapsed_seconds, 3),
            "structured_output": result.structured_output,
            "extracted": result.journey.model_dump(), "reviewed": reviewed.model_dump(),
            "timezone": timezone_name, "validation_errors": errors,
            "review_confirmed": confirmed,
        }
        st.download_button("Download extraction record (JSON)", json.dumps(record, ensure_ascii=False, indent=2),
                           file_name="extraction-record.json", mime="application/json")

st.divider()
st.caption("Booking text → local extraction → Python validation → your review → Apple Calendar via MCP, or .ics export")
