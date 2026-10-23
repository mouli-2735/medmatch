import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

from google import genai
from google.genai import types

api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

print(f"Testing live Gemini API with model: {model_name}")
client = genai.Client(api_key=api_key)

crop_path = BASE_DIR.parent / "testset" / "crops" / "rx_001_line_1.png"
with open(crop_path, "rb") as f:
    img_bytes = f.read()

prompt = """You are a clinical pharmacist AI. Transcribe the prescription crop attached.
Return ONLY valid JSON matching this schema:
{
  "guesses": ["Augmentin", "Augmentan", "Amoxicillin"],
  "dose_raw": "625mg",
  "freq_raw": "1-0-1",
  "duration_raw": "5d"
}
"""

for test_model in [model_name, "gemini-3.5-flash"]:
    print(f"\n--- Trying model: {test_model} ---")
    try:
        response = client.models.generate_content(
            model=test_model,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                prompt
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        print("Success with", test_model)
        print(response.text)
        parsed = json.loads(response.text)
        print("Parsed JSON:", parsed)
        break
    except Exception as e:
        print(f"Failed with {test_model}: {e}")

