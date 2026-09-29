"""A few serial, zero-automatic-retry Gemini availability/style probes."""
import getpass
import json
import os
from pathlib import Path
import time

from google import genai
from google.genai import errors, types

MODELS = ("gemini-3.8-flash", "gemini-3.1-pro-preview", "gemini-3.5-flash-lite")
SOURCE = ("A handwritten set of notes detailing an alchemical recipe for a potion to increase your dexterity. "
          "It looks like the undead will be catching these hands.")
PROMPT = (
    "Translate this Cataclysm survival role-playing game item description into natural Simplified Chinese. "
    "Use restrained black humour and deadpan wit without changing the meaning or inventing facts. "
    "Return only the translation.\nDeveloper comment: Description of book "
    '"scribbled notes (potion of wicked quick hands)"\n' + SOURCE
)


def main():
    key = getpass.getpass("Gemini API key (hidden): ")
    os.environ["GEMINI_API_KEY"] = key
    results = []
    try:
        for model in MODELS:
            row = {"model": model, "status": "UNKNOWN"}
            started = time.time()
            try:
                with genai.Client(api_key=key, vertexai=False, http_options=types.HttpOptions(
                        timeout=60000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    response = client.models.generate_content(
                        model=model, contents=PROMPT,
                        config=types.GenerateContentConfig(response_mime_type="text/plain"))
                row.update(status="PASS", translation=response.text)
            except errors.APIError as exc:
                row.update(status="FAIL", http_code=exc.code)
            except Exception:
                row.update(status="UNKNOWN", may_have_been_charged=True)
            row["seconds"] = round(time.time() - started, 2)
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
        key = None
    evidence = {"sample_id": "714aaeedf0d97e4999698956112c1ae7a6551ae301b9952d5ea256314cbf8bcc",
                "automatic_retries": 0, "results": results}
    Path(__file__).with_name("model-comparison.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
