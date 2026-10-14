"""Local API connection and structured extraction. No calendar actions occur here."""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain import Journey

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "settings.json"
PROMPT = ROOT / "prompts/extract.txt"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str = "http://localhost:1234/v1"
    model: str = ""
    timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)
    max_tokens: int = Field(default=1000, gt=0)
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    structured_output: bool = True


def load_settings():
    return Settings.model_validate_json(SETTINGS.read_text(encoding="utf-8"))


def client_for(settings):
    url = urlsplit(settings.base_url)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.path.rstrip("/") != "/v1" or url.username or url.password or url.query or url.fragment):
        raise ValueError("Use a localhost HTTP endpoint ending in /v1.")
    return OpenAI(
        base_url=settings.base_url,
        api_key=os.environ.get("LM_STUDIO_API_KEY") or "lm-studio",
        timeout=httpx.Timeout(settings.timeout_seconds, connect=5), max_retries=0,
        http_client=httpx.Client(trust_env=False, follow_redirects=False),
    )


def list_models(settings):
    with client_for(settings) as client:
        return [model.id for model in client.models.list(timeout=10).data]


@dataclass
class Extraction:
    journey: Journey
    raw_text: str
    model: str
    elapsed_seconds: float
    structured_output: bool


def parse_response(text):
    # Prompt-only mode may produce a fenced JSON block. Nothing else is repaired.
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if lines[0] in {"```json", "```"}:
            cleaned = "\n".join(lines[1:-1])
    try:
        return Journey.model_validate_json(cleaned)
    except ValidationError as exc:
        raise ValueError("The model did not return the required JSON fields/types. Inspect its response in LM Studio or try structured output.") from exc


def extract_journey(source, settings):
    if not source.strip():
        raise ValueError("Paste booking text first.")
    if len(source) > 12000:
        raise ValueError("Use a single booking excerpt of at most 12,000 characters.")
    if not settings.model.strip():
        raise ValueError("Choose your model in the Connection panel first.")
    schema = Journey.model_json_schema()
    system = PROMPT.read_text(encoding="utf-8")
    request = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system + "\nJSON schema:\n" + json.dumps(schema)},
            {"role": "user", "content": "Extract from this booking text:\n\n" + source},
        ],
        "temperature": settings.temperature, "max_tokens": settings.max_tokens,
    }
    if settings.structured_output:
        request["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "journey", "strict": True, "schema": schema,
        }}
    started = time.perf_counter()
    with client_for(settings) as client:
        response = client.chat.completions.create(**request)
    elapsed = time.perf_counter() - started
    if not response.choices:
        raise ValueError("The server returned no completion.")
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise ValueError("Output reached the token limit. Increase max_tokens in settings.json or shorten the input.")
    if choice.message.refusal:
        raise ValueError("The model refused this extraction.")
    text = choice.message.content
    if not text or not text.strip():
        raise ValueError("The model returned no text. Check the LM Studio log and output-token budget.")
    return Extraction(parse_response(text), text, response.model, elapsed, settings.structured_output)


def friendly_error(exc):
    if isinstance(exc, APITimeoutError):
        return "LM Studio timed out. Check model activity, shorten the input, or increase timeout_seconds."
    if isinstance(exc, APIConnectionError):
        return "Cannot reach LM Studio. Start its server on port 1234 and load Gemma."
    if isinstance(exc, APIStatusError):
        if exc.status_code in {401, 403}:
            return "Server authentication failed. Set LM_STUDIO_API_KEY to your LM Studio server token."
        return f"LM Studio returned HTTP {exc.status_code}. Check the model identifier and server log. If JSON-schema output is unsupported, explicitly switch it off in the Connection panel and retry."
    if isinstance(exc, ValidationError):
        return "Invalid settings.json. Check the documented field names and types."
    return str(exc)
