"""List LM Studio models and optionally save one exact identifier."""

import argparse
import sys

from openai import OpenAIError

from llm import SETTINGS, friendly_error, list_models, load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select", help="Save an exact API model identifier into settings.json")
    args = parser.parse_args()
    try:
        settings = load_settings()
        models = list_models(settings)
        print(f"Server: {settings.base_url}")
        for identifier in models:
            print(identifier)
        if args.select is not None:
            if args.select not in models:
                raise ValueError("Identifier not listed. Copy it exactly from the server response.")
            settings.model = args.select
            SETTINGS.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
            print(f"Saved model: {args.select}")
        if not models:
            raise ValueError("No models listed. Load Gemma in LM Studio.")
        return 0
    except (OpenAIError, OSError, ValueError) as exc:
        print(f"Error: {friendly_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
