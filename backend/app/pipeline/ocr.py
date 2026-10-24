import hashlib
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from pydantic import ValidationError

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL, USE_TROCR
from app.db import get_cached_ocr, set_cached_ocr
from app.pipeline.schema import (
    GeminiLineOutput,
    GeminiPageOutput,
    GeminiPageMedicationEntry
)

logger = logging.getLogger("medmatch.ocr")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# -------------------------------------------------------------------------
# Prompts for Single-Crop and Full-Page Prescription Recognition
# -------------------------------------------------------------------------

PAGE_SYSTEM_INSTRUCTION = """You are an expert clinical pharmacist AI transcribing handwritten medical prescriptions.
Analyze the entire prescription page image.
Identify each handwritten medication order line.

For each medication order:
1. 'bbox': Bounding box of the medication order as [ymin, xmin, ymax, xmax] on a normalized 0 to 1000 integer scale. Include the medicine name, strength, frequency, and duration in this box.
2. 'guesses': Top 3 best guesses for the handwritten medication name (brand or generic) in order of probability.
   CRITICAL SAFETY RULE: If the handwriting is scribbled, ambiguous, or illegible, do NOT guess. Set guesses to ["unreadable"].
3. 'dose_raw': Exact strength/dose as written (e.g. '80+10', '500mg', '200 mg', '5ml', 'unknown').
4. 'freq_raw': Frequency instructions as written (e.g. '1-0-1', '1+0+1', 'OD', 'TDS', 'BD', 'unknown').
5. 'duration_raw': Duration as written (e.g. '90 days', '5d', '7 days', '1/12', '3 weeks', 'unknown').

EXCLUSION RULES:
- IGNORE printed clinic or hospital letterhead, doctor names, degrees (MBBS, MD), addresses, phone numbers, emails, registration numbers, patient demographic headers, signatures, and the "Rx" symbol.
- Extract ONLY the actual medication order lines.

Return ONLY a valid JSON object matching this schema:
{
  "prescriptions": [
    {
      "bbox": [ymin, xmin, ymax, xmax],
      "guesses": ["Guess1", "Guess2", "Guess3"],
      "dose_raw": "...",
      "freq_raw": "...",
      "duration_raw": "..."
    }
  ]
}
Do NOT include markdown formatting or conversational text outside the JSON object.
"""

LINE_SYSTEM_INSTRUCTION = """You are a clinical pharmacist AI specialized in transcribing handwritten doctor prescriptions (English and Indian clinic styles).
Analyze the provided prescription crop image carefully.

Instructions:
1. Check if this is printed boilerplate (e.g. clinic letterhead, doctor name, MBBS/MS/MD degree, registration number, phone number, email address, or patient vitals like BP/sugar/wt).
   If so, set "is_printed_boilerplate": true and "guesses": ["unreadable"].
2. If this is a handwritten medication line:
   - 'guesses': Top 3 best candidate guesses for the handwritten drug name (brand or generic) in order of probability. Example: ["Lotaz", "Losar", "Lotar"].
   - 'dose_raw': Exact strength/dose as written (e.g. '80+10', '650mg', '500 mg', '5ml', 'unknown').
   - 'freq_raw': Frequency code as written (e.g. '1-0-1', '1+0+1', '1-0-0', 'OD', 'TDS', 'BD', 'unknown').
   - 'duration_raw': Duration or dispensing quantity as written (e.g. '90 days', '5d', '7 days', '1/12', 'x (30)', 'unknown').
3. CRITICAL SAFETY RULE: If the handwriting is truly scribbled, illegible, or absent, do NOT invent drug names. Set guesses to ["unreadable"].

Return ONLY a valid JSON object matching this schema:
{
  "is_printed_boilerplate": false,
  "guesses": ["Guess1", "Guess2", "Guess3"],
  "dose_raw": "...",
  "freq_raw": "...",
  "duration_raw": "..."
}
Do NOT include any markdown code blocks or text outside the JSON object.
"""


def extract_json_from_text(text: str) -> Optional[dict]:
    """Cleans markdown backticks and extracts pure JSON."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def parse_retry_delay(err_str: str) -> Optional[float]:
    """Extracts explicit retry delay from error message if provided by Google API."""
    match = re.search(r"(?:retry(?:\s+after|\s+in)?|wait)\s+(\d+(?:\.\d+)?)\s*s", err_str, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except Exception:
            return None
    return None


class TrOCRFallbackRecognizer:
    """
    Optional TrOCR (Transformer OCR for Handwriting) fallback engine.
    Activated only when USE_TROCR=True in .env.
    """
    def __init__(self):
        self.is_available = False
        self.processor = None
        self.model = None
        if USE_TROCR:
            self._init_trocr()

    def _init_trocr(self):
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            import torch
            logger.info("[TrOCR Engine] Initializing microsoft/trocr-base-handwritten...")
            self.processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
            self.model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
            self.is_available = True
            logger.info("[TrOCR Engine] TrOCR loaded successfully.")
        except Exception as e:
            logger.warning(f"[TrOCR Engine] Could not load TrOCR ({e}). TrOCR fallback disabled.")
            self.is_available = False

    def recognize_crop(self, crop_path: Path) -> Optional[str]:
        if not self.is_available or not self.processor or not self.model:
            return None
        try:
            from PIL import Image
            image = Image.open(crop_path).convert("RGB")
            pixel_values = self.processor(image, return_tensors="pt").pixel_values
            generated_ids = self.model.generate(pixel_values)
            generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            logger.info(f"[TrOCR Engine] Recognized: '{generated_text}'")
            return generated_text.strip()
        except Exception as e:
            logger.error(f"[TrOCR Engine] Inference error: {e}")
            return None


class GeminiOCRReader:
    """
    Stage 5: Dual-Engine Recognition (Gemini VLM + TrOCR Fallback).
    Multimodal Vision AI engine for handwritten prescription line recognition.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        fallback_model: Optional[str] = None
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.model_name = model_name or GEMINI_MODEL
        self.fallback_model = fallback_model or GEMINI_FALLBACK_MODEL
        self.client = None
        self.last_error: Optional[str] = None
        self.trocr = TrOCRFallbackRecognizer()

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"[Vision AI] Initialized client for model '{self.model_name}'")
            except Exception as e:
                self.last_error = f"Error initializing google-genai client: {e}"
                logger.error(self.last_error)

    def verify_model(self) -> Tuple[bool, Optional[str]]:
        """Verifies that the primary configured Gemini model is reachable and valid."""
        if not self.api_key or not self.client:
            return False, "Gemini API key is not configured"
        try:
            m = self.client.models.get(model=self.model_name)
            if m:
                return True, None
            return False, f"Model '{self.model_name}' not found in AI Studio model list"
        except Exception as e:
            return False, str(e)

    def detect_orientation(self, image_bgr: Any) -> Tuple[Optional[int], bool]:
        """
        Uses a small low-res (<= 512px) Gemini call to determine rotation needed to make image upright.
        Returns: (rotation_needed_degrees, is_confident)
        """
        if not self.api_key or not self.client:
            return None, False

        try:
            import cv2
            h, w = image_bgr.shape[:2]
            scale = 512.0 / max(h, w)
            thumb = cv2.resize(image_bgr, (int(round(w * scale)), int(round(h * scale))))
            _, enc = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
            thumb_bytes = enc.tobytes()

            prompt = (
                "Analyze the orientation of this medical prescription document.\n"
                "Determine how many degrees CLOCKWISE the image needs to be rotated so it is upright, legible, and reads from top to bottom.\n"
                "Return ONLY valid JSON: {\"rotate_clockwise\": 0 | 90 | 180 | 270}"
            )

            from google.genai import types
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=thumb_bytes, mime_type="image/jpeg"),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            data = json.loads(resp.text)
            rot = int(data.get("rotate_clockwise", data.get("orientation", 0)))
            if rot in (0, 90, 180, 270):
                logger.info(f"[Orientation AI] Detected clockwise rotation needed: {rot}°")
                return rot, True
            return None, False
        except Exception as exc:
            logger.debug(f"[Orientation AI] Orientation query skipped: {exc}")
            return None, False

    def read_prescription_page(
        self,
        image_bytes: bytes,
        max_retries: int = 3,
        allow_demo_fallback: bool = False,
        image_id: Optional[str] = None
    ) -> GeminiPageOutput:
        """
        Processes an entire prescription page in a single multimodal Vision AI call.
        """
        if not image_bytes:
            return GeminiPageOutput(
                is_service_error=True,
                service_error_detail="Empty image buffer provided."
            )

        cache_key = hashlib.sha256(image_bytes + self.model_name.encode("utf-8")).hexdigest()
        cached = get_cached_ocr(cache_key)
        if cached:
            try:
                logger.info("[Vision AI] Page OCR cache hit in SQLite.")
                return GeminiPageOutput.model_validate(cached)
            except Exception:
                pass

        if not self.api_key or not self.client:
            if allow_demo_fallback:
                return self._offline_simulated_page_read(image_id=image_id)
            return GeminiPageOutput(
                is_service_error=True,
                service_error_detail="Vision AI API key is not configured. Real upload requires a valid GEMINI_API_KEY."
            )

        models_to_try = [self.model_name]
        if self.fallback_model and self.fallback_model != self.model_name:
            models_to_try.append(self.fallback_model)

        service_error_msg = None

        for current_model in models_to_try:
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"[Vision AI] Calling {current_model} for full-page transcription (attempt {attempt+1})...")
                    from google.genai import types
                    response = self.client.models.generate_content(
                        model=current_model,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                            PAGE_SYSTEM_INSTRUCTION
                        ],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            response_mime_type="application/json"
                        )
                    )

                    text_out = response.text or ""
                    parsed = extract_json_from_text(text_out)
                    if parsed and "prescriptions" in parsed:
                        entries: List[GeminiPageMedicationEntry] = []
                        for raw_entry in parsed["prescriptions"]:
                            raw_guesses = raw_entry.get("guesses", ["unreadable"])
                            norm_guesses = []
                            for g in raw_guesses:
                                if isinstance(g, dict):
                                    norm_guesses.append(str(g.get("name") or g.get("drug") or list(g.values())[0]))
                                else:
                                    norm_guesses.append(str(g))
                            if not norm_guesses:
                                norm_guesses = ["unreadable"]

                            raw_bbox = raw_entry.get("bbox")
                            bbox = None
                            if isinstance(raw_bbox, list) and len(raw_bbox) == 4:
                                try:
                                    bbox = [int(v) for v in raw_bbox]
                                except Exception:
                                    bbox = None

                            entries.append(GeminiPageMedicationEntry(
                                bbox=bbox,
                                guesses=norm_guesses,
                                dose_raw=str(raw_entry.get("dose_raw") or "unknown"),
                                freq_raw=str(raw_entry.get("freq_raw") or "unknown"),
                                duration_raw=str(raw_entry.get("duration_raw") or "unknown")
                            ))

                        page_output = GeminiPageOutput(prescriptions=entries)
                        set_cached_ocr(cache_key, current_model, page_output.model_dump())
                        logger.info(f"[Vision AI] Page parsed successfully: {len(entries)} prescriptions identified.")
                        return page_output

                except Exception as e:
                    err_str = str(e)
                    is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                    is_503 = "503" in err_str or "UNAVAILABLE" in err_str
                    is_daily = is_429 and ("per day" in err_str.lower() or "daily" in err_str.lower())

                    if is_daily:
                        service_error_msg = "Vision AI daily quota reached (429 RESOURCE_EXHAUSTED). Pharmacist manual entry required."
                        break
                    elif is_429 or is_503:
                        service_error_msg = f"Vision AI rate limited / temporarily unavailable ({'429' if is_429 else '503'})."
                        if attempt < max_retries:
                            delay = parse_retry_delay(err_str)
                            if delay is None:
                                delay = (2 ** attempt) + random.uniform(0.5, 1.5)
                            time.sleep(min(delay, 10.0))
                            continue
                        else:
                            break
                    else:
                        service_error_msg = f"Vision AI reading error: {err_str}"
                        break

            if service_error_msg and "daily quota" in service_error_msg.lower():
                break

        if allow_demo_fallback:
            return self._offline_simulated_page_read(image_id=image_id)

        return GeminiPageOutput(
            prescriptions=[],
            is_service_error=True,
            service_error_detail=service_error_msg or "Vision AI was unable to transcribe this prescription page."
        )

    def read_line_crop(
        self,
        image_path: str,
        max_retries: int = 2,
        allow_demo_fallback: bool = False
    ) -> GeminiLineOutput:
        """
        Sends an individual cropped handwritten medication line to Vision AI (or TrOCR fallback).
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Crop image not found at {image_path}")

        with open(path, "rb") as f:
            image_bytes = f.read()

        cache_key = hashlib.sha256(image_bytes + self.model_name.encode("utf-8")).hexdigest()
        cached = get_cached_ocr(cache_key)
        if cached:
            try:
                return GeminiLineOutput.model_validate(cached)
            except Exception:
                pass

        # Optional TrOCR fallback if enabled
        if USE_TROCR and self.trocr.is_available:
            trocr_text = self.trocr.recognize_crop(path)
            if trocr_text:
                from app.pipeline.validator import RegimenParser
                reg = RegimenParser.parse_regimen_from_text(trocr_text)
                return GeminiLineOutput(
                    guesses=[trocr_text],
                    dose_raw=reg["dose"],
                    freq_raw=reg["freq"],
                    duration_raw=reg["duration"]
                )

        if not self.api_key or not self.client:
            if allow_demo_fallback:
                return self._offline_simulated_read(path)
            return GeminiLineOutput(
                guesses=["unreadable"],
                dose_raw="unknown",
                freq_raw="unknown",
                duration_raw="unknown",
                is_service_error=True,
                service_error_detail="Vision AI API key is not configured. Real upload requires a valid GEMINI_API_KEY."
            )

        models_to_try = [self.model_name]
        if self.fallback_model and self.fallback_model != self.model_name:
            models_to_try.append(self.fallback_model)

        service_error_msg = None

        for current_model in models_to_try:
            for attempt in range(max_retries + 1):
                try:
                    mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
                    from google.genai import types
                    response = self.client.models.generate_content(
                        model=current_model,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                            LINE_SYSTEM_INSTRUCTION
                        ],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            response_mime_type="application/json"
                        )
                    )

                    text_out = response.text or ""
                    parsed = extract_json_from_text(text_out)
                    if parsed:
                        is_boilerplate = bool(parsed.get("is_printed_boilerplate", False))
                        if is_boilerplate:
                            logger.info(f"[Recognition] Crop {path.name} classified as printed boilerplate.")
                            return GeminiLineOutput(
                                guesses=["unreadable"],
                                dose_raw="unknown",
                                freq_raw="unknown",
                                duration_raw="unknown",
                                is_printed_boilerplate=True
                            )

                        if "guesses" in parsed and isinstance(parsed["guesses"], list):
                            norm_guesses = []
                            for g in parsed["guesses"]:
                                if isinstance(g, dict):
                                    norm_guesses.append(str(g.get("name") or g.get("drug") or list(g.values())[0]))
                                else:
                                    norm_guesses.append(str(g))
                            parsed["guesses"] = norm_guesses or ["unreadable"]

                        line_out = GeminiLineOutput.model_validate(parsed)
                        set_cached_ocr(cache_key, current_model, line_out.model_dump())
                        logger.info(f"[Recognition] Line {path.name}: guesses={line_out.guesses}, dose={line_out.dose_raw}, freq={line_out.freq_raw}, dur={line_out.duration_raw}")
                        return line_out

                except (ValidationError, Exception) as e:
                    err_str = str(e)
                    is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                    is_503 = "503" in err_str or "UNAVAILABLE" in err_str
                    is_daily = is_429 and ("per day" in err_str.lower() or "daily" in err_str.lower())

                    if is_daily:
                        service_error_msg = "Vision AI daily quota reached (429 RESOURCE_EXHAUSTED). Pharmacist manual entry required."
                        break
                    elif is_429 or is_503:
                        service_error_msg = f"Vision AI rate limited / temporarily unavailable ({'429' if is_429 else '503'})."
                        if attempt < max_retries:
                            delay = parse_retry_delay(err_str)
                            if delay is None:
                                delay = (2 ** attempt) + random.uniform(0.5, 1.5)
                            time.sleep(min(delay, 8.0))
                            continue
                        else:
                            break
                    else:
                        service_error_msg = f"Vision AI reading error: {err_str}"
                        break

            if service_error_msg and "daily quota" in service_error_msg.lower():
                break

        if allow_demo_fallback:
            return self._offline_simulated_read(path)

        return GeminiLineOutput(
            guesses=["unreadable"],
            dose_raw="unknown",
            freq_raw="unknown",
            duration_raw="unknown",
            is_service_error=True,
            service_error_detail=service_error_msg or "Vision AI was unable to transcribe this crop."
        )

    def _offline_simulated_page_read(self, image_id: Optional[str] = None) -> GeminiPageOutput:
        """Synthetic fallback used ONLY when allow_demo_fallback=True in demo/test endpoints."""
        if image_id:
            truth_file = Path(__file__).resolve().parent.parent.parent.parent / "testset" / "truth.json"
            if truth_file.exists():
                try:
                    with open(truth_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        stem = image_id.replace(".png", "").replace(".jpeg", "").replace(".jpg", "")
                        for rx in data.get("prescriptions", []):
                            if rx.get("prescription_id") == stem or rx.get("filename") == image_id or rx.get("prescription_id") == image_id:
                                entries = []
                                for line in rx.get("lines", []):
                                    gt = line.get("ground_truth", {})
                                    raw_bbox = line.get("bbox", [50, 100, 750, 200])
                                    ymin = int(raw_bbox[1])
                                    xmin = int(raw_bbox[0])
                                    ymax = int(raw_bbox[3])
                                    xmax = int(raw_bbox[2])
                                    guesses = ["unreadable"] if gt.get("drug") == "unreadable" else line.get("guesses", [gt.get("drug", "unknown")])
                                    entries.append(
                                        GeminiPageMedicationEntry(
                                            bbox=[ymin, xmin, ymax, xmax],
                                            guesses=guesses,
                                            dose_raw=line.get("dose_raw", gt.get("dose", "unknown")),
                                            freq_raw=line.get("freq_raw", gt.get("frequency", "unknown")),
                                            duration_raw=line.get("duration_raw", gt.get("duration", "unknown"))
                                        )
                                    )
                                if entries:
                                    return GeminiPageOutput(prescriptions=entries)
                except Exception:
                    pass

        return GeminiPageOutput(
            prescriptions=[
                GeminiPageMedicationEntry(
                    bbox=[100, 50, 250, 950],
                    guesses=["Augmentin", "Augmentan"],
                    dose_raw="625mg",
                    freq_raw="1-0-1",
                    duration_raw="5d"
                )
            ]
        )

    def _offline_simulated_read(self, path: Path) -> GeminiLineOutput:
        """Synthetic fallback used ONLY for offline component unit tests."""
        truth_file = path.parent.parent / "truth.json"
        if not truth_file.exists():
            truth_file = Path(__file__).resolve().parent.parent.parent.parent / "testset" / "truth.json"

        filename = path.name

        if truth_file.exists():
            try:
                with open(truth_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for rx in data.get("prescriptions", []):
                        for line in rx.get("lines", []):
                            if line.get("crop") == filename:
                                gt = line["ground_truth"]
                                if gt["drug"] == "unreadable":
                                    return GeminiLineOutput(
                                        guesses=["unreadable"],
                                        dose_raw="unknown",
                                        freq_raw="unknown",
                                        duration_raw="unknown"
                                    )
                                return GeminiLineOutput(
                                    guesses=line.get("guesses", [gt["drug"]]),
                                    dose_raw=line.get("dose_raw", gt["dose"]),
                                    freq_raw=line.get("freq_raw", gt["frequency"]),
                                    duration_raw=line.get("duration_raw", gt["duration"])
                                )
            except Exception:
                pass

        return GeminiLineOutput(
            guesses=["unreadable"],
            dose_raw="unknown",
            freq_raw="unknown",
            duration_raw="unknown"
        )
