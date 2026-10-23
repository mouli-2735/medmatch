import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

api_key = os.getenv("GEMINI_API_KEY", "").strip()
model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

print(f"1. API Key Status: Active (Length: {len(api_key)})", flush=True)
print(f"2. Selected Model: {model_name}", flush=True)

from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

print(f"\n3. Testing Text Generation with '{model_name}'...", flush=True)
t0 = time.time()
try:
    res = client.models.generate_content(
        model=model_name,
        contents="Say 'MedMatch Rx API is live and operational' in 7 words or less."
    )
    print(f"   [SUCCESS] Responded in {time.time()-t0:.2f}s: {res.text.strip()}", flush=True)
except Exception as e:
    print(f"   [FAILED]: {e}", flush=True)

# Test Multimodal Vision OCR on sample crop
crop_path = BASE_DIR.parent / "testset" / "crops" / "rx_001_line_1.png"
if crop_path.exists():
    print(f"\n4. Testing Multimodal Handwriting OCR on '{crop_path.name}'...", flush=True)
    with open(crop_path, "rb") as f:
        img_bytes = f.read()

    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                "Extract the medication from this prescription line crop. Return ONLY valid JSON with keys: 'guesses', 'dose_raw', 'freq_raw', 'duration_raw'."
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        print(f"   [SUCCESS] Multimodal OCR responded in {time.time()-t0:.2f}s:", flush=True)
        print(f"   {resp.text.strip()}", flush=True)
    except Exception as e:
        print(f"   [FAILED]: {e}", flush=True)

print("\n=== LIVE API VERIFICATION COMPLETE ===", flush=True)
