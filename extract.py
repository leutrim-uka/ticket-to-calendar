"""Optional terminal route for inspecting extraction without the interface."""

import argparse
import json
import sys
from pathlib import Path

from openai import OpenAIError

from domain import check_journey
from llm import extract_journey, friendly_error, load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--prompt-only", action="store_true", help="Explicitly skip API schema constraints")
    parser.add_argument("--output", type=Path, help="Save extraction and validation record")
    args = parser.parse_args()
    try:
        settings = load_settings()
        if args.prompt_only:
            settings.structured_output = False
        source = args.input.read_text(encoding="utf-8")
        result = extract_journey(source, settings)
        _, errors = check_journey(result.journey)
        record = {
            "source": source, "model": result.model,
            "elapsed_seconds": round(result.elapsed_seconds, 3),
            "structured_output": result.structured_output,
            "extracted": result.journey.model_dump(), "validation_errors": errors,
        }
        print(json.dumps(record, ensure_ascii=False, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    except (OpenAIError, OSError, ValueError) as exc:
        print(f"Error: {friendly_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
