import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import cv2
import numpy as np

from app.config import CROPS_DIR
from app.pipeline.schema import (
    ProcessedLine,
    PrescriptionResponse,
    QualityCheckResult,
    GeminiLineOutput,
    LineCropData,
    RxNormLookupResult
)
from app.pipeline.image_processing import ImageQualityProcessor
from app.pipeline.ocr import GeminiOCRReader
from app.pipeline.matcher import DrugCatalogMatcher
from app.pipeline.validator import PrescriptionValidator
from app.pipeline.confidence import ConfidenceEvaluator, LookalikeChecker
from app.pipeline.rxnorm import RxNormClient

class MedMatchPipeline:
    """
    End-to-end execution of MedMatch Rx prescription verification pipeline.
    Integrates all seven project technologies + live RxNorm reference:
    1. OpenCV — Image quality analysis, auto-orientation, deskewing, and line segmentation.
    2. Vision AI (Gemini) — Handwritten prescription line transcription.
    3. RapidFuzz — Orthographic medicine name similarity comparison.
    4. Metaphone — Phonetic sound-alike similarity comparison.
    5. ISMP LASA — Look-Alike / Sound-Alike clinical safety hazard detection.
    6. FastAPI — Orchestration & async endpoint handling.
    7. SQLite — Audit records, pharmacist confirmations, and corrections.
    + RxNorm API — Live online medicine-name reference lookup via NLM RxNav.
    """
    def __init__(self):
        self.quality_processor = ImageQualityProcessor()
        self.ocr_reader = GeminiOCRReader()
        self.matcher = DrugCatalogMatcher()
        self.validator = PrescriptionValidator()
        self.confidence_evaluator = ConfidenceEvaluator()
        self.lookalike_checker = LookalikeChecker()
        self.rxnorm_client = RxNormClient()

    async def process_prescription_image(
        self,
        image_path: Path,
        prescription_id: Optional[str] = None,
        allow_demo_fallback: bool = False,
        manual_rotation: Optional[int] = None
    ) -> PrescriptionResponse:
        """
        Executes pipeline on an uploaded image without hardcoded demo shortcuts:
        1. OpenCV Image Quality Analysis (blur, dark, glare)
        2. OpenCV Auto-orient and Deskew (with scale normalization & rotation override)
        3. OpenCV Line Segmentation / Vision AI Single-Page Bounding Box Extraction
        4. Vision AI OCR (real multimodal reading)
        5. RapidFuzz & Metaphone local catalog matching
        6. Live RxNorm online reference lookup
        7. Clinical validation of dose, frequency, and duration
        8. ISMP Look-alike safety check
        9. Heuristic field-level confidence scoring
        """
        pid = prescription_id or f"rx_{uuid.uuid4().hex[:8]}"
        image_bgr = cv2.imread(str(image_path))
        
        if image_bgr is None:
            # Handle unreadable image file safely
            failed_qc = QualityCheckResult(
                passed=False,
                is_blurry=False,
                blur_score=0.0,
                is_dark=False,
                mean_brightness=0.0,
                has_glare=False,
                glare_share=0.0,
                message="Image file could not be read or is corrupted. Please re-upload.",
                deskew_angle=0.0,
                rotation_applied=0,
                orientation_confident=True
            )
            return PrescriptionResponse(
                prescription_id=pid,
                original_filename=image_path.name,
                image_url=f"/static/uploads/{image_path.name}",
                quality_check=failed_qc,
                lines=[],
                total_lines=0,
                status="rejected",
                all_can_confirm=False,
                vision_ai_status="error",
                vision_ai_message="Invalid image file format or corrupt image.",
                created_at=datetime.now(timezone.utc).isoformat()
            )

        # 1. OpenCV Image Quality Check
        quality = self.quality_processor.analyze_quality(image_bgr)
        if not quality.passed:
            return PrescriptionResponse(
                prescription_id=pid,
                original_filename=image_path.name,
                image_url=f"/static/uploads/{image_path.name}",
                quality_check=quality,
                lines=[],
                total_lines=0,
                status="rejected",
                all_can_confirm=False,
                vision_ai_status="operational",
                vision_ai_message="Image rejected by OpenCV quality gate.",
                created_at=datetime.now(timezone.utc).isoformat()
            )

        # 2. OpenCV Auto-orient and Deskew
        deskewed_img, angle, rot_applied, orient_conf = self.quality_processor.auto_orient_and_deskew(
            image_bgr,
            ocr_reader=self.ocr_reader,
            manual_rotation=manual_rotation
        )
        quality.deskew_angle = angle
        quality.rotation_applied = rot_applied
        quality.orientation_confident = orient_conf

        # 3. Vision AI Single-Page OCR or OpenCV Segmentation Fallback
        crops_out_dir = CROPS_DIR / pid
        crops_out_dir.mkdir(parents=True, exist_ok=True)

        # Encode deskewed image to JPEG bytes for page-level Vision AI
        success_enc, encoded = cv2.imencode(".jpg", deskewed_img)
        page_bytes = encoded.tobytes() if success_enc else b""

        page_output = self.ocr_reader.read_prescription_page(
            page_bytes,
            allow_demo_fallback=allow_demo_fallback,
            image_id=pid or image_path.stem
        )

        overall_vision_status = "operational"
        overall_vision_msg = None
        if page_output.is_service_error:
            overall_vision_status = "service_unavailable"
            overall_vision_msg = page_output.service_error_detail

        h_img, w_img = deskewed_img.shape[:2]
        usable_entries = [
            e for e in (page_output.prescriptions or [])
            if e.bbox and len(e.bbox) == 4 and (e.bbox[2] > e.bbox[0]) and (e.bbox[3] > e.bbox[1])
        ]

        line_items: List[Tuple[str, List[int], GeminiLineOutput]] = []

        if usable_entries:
            # Build crops directly from Vision AI bboxes (clamped, padded)
            for idx, entry in enumerate(usable_entries):
                line_num = idx + 1
                ymin, xmin, ymax, xmax = entry.bbox
                # Scale from normalized [0, 1000] scale if needed, or if already in pixel coords
                if ymax <= 1000 and xmax <= 1000:
                    y1 = max(0, int((ymin / 1000.0) * h_img) - 8)
                    x1 = max(0, int((xmin / 1000.0) * w_img) - 10)
                    y2 = min(h_img, int((ymax / 1000.0) * h_img) + 8)
                    x2 = min(w_img, int((xmax / 1000.0) * w_img) + 10)
                else:
                    y1 = max(0, int(ymin) - 8)
                    x1 = max(0, int(xmin) - 10)
                    y2 = min(h_img, int(ymax) + 8)
                    x2 = min(w_img, int(xmax) + 10)

                if y2 - y1 < 10 or x2 - x1 < 10:
                    continue

                crop = deskewed_img[y1:y2, x1:x2]
                crop_name = f"{pid}_line_{line_num}.png"
                cv2.imwrite(str(crops_out_dir / crop_name), crop)

                ocr_line = GeminiLineOutput(
                    guesses=entry.guesses,
                    dose_raw=entry.dose_raw,
                    freq_raw=entry.freq_raw,
                    duration_raw=entry.duration_raw,
                    bbox=[x1, y1, x2, y2],
                    is_service_error=page_output.is_service_error,
                    service_error_detail=page_output.service_error_detail
                )
                line_items.append((crop_name, [x1, y1, x2, y2], ocr_line))

        # Fallback to OpenCV line segmentation if no usable boxes returned
        if not line_items:
            segmented = self.quality_processor.segment_lines(deskewed_img, crops_out_dir, pid)
            for idx, (crop_filename, bbox) in enumerate(segmented):
                crop_full_path = crops_out_dir / crop_filename
                ocr_line = self.ocr_reader.read_line_crop(
                    str(crop_full_path),
                    allow_demo_fallback=allow_demo_fallback
                )
                if ocr_line.is_service_error and not page_output.is_service_error:
                    overall_vision_status = "service_unavailable"
                    overall_vision_msg = ocr_line.service_error_detail
                line_items.append((crop_filename, bbox, ocr_line))

        # 4, 5, 6, 7, 8, 9: Process each line item
        processed_lines: List[ProcessedLine] = []
        all_can_confirm = True

        for idx, (crop_filename, bbox, ocr_output) in enumerate(line_items):
            line_id = idx + 1

            # Store original raw OCR extraction for full clinical auditability
            original_ocr_trace = {
                "raw_guesses": list(ocr_output.guesses),
                "raw_dose": ocr_output.dose_raw,
                "raw_freq": ocr_output.freq_raw,
                "raw_duration": ocr_output.duration_raw,
                "is_service_error": ocr_output.is_service_error,
                "service_error_detail": ocr_output.service_error_detail
            }

            # 5. RapidFuzz & Metaphone local catalog matching
            candidates = self.matcher.match_guesses(ocr_output.guesses, top_k=4)
            selected_cand = candidates[0] if candidates else None

            # 6. Online RxNorm live lookup
            # Query RxNorm using top candidate brand name or top guess
            rxnorm_query = selected_cand.brand_name if selected_cand else (
                ocr_output.guesses[0] if (ocr_output.guesses and ocr_output.guesses[0] != "unreadable") else ""
            )
            rxnorm_result = await self.rxnorm_client.lookup_medicine(rxnorm_query)

            # 7. Clinical validation
            validation = self.validator.validate_line(
                ocr_output.dose_raw,
                ocr_output.freq_raw,
                ocr_output.duration_raw,
                selected_cand
            )

            # 8. ISMP Look-alike safety check
            candidate_for_lasa = selected_cand.brand_name if selected_cand else ""
            lookalike = self.lookalike_checker.check_candidate(candidate_for_lasa)

            # 9. Heuristic field-level confidence scoring
            confidence = self.confidence_evaluator.evaluate_confidence(
                ocr_output.guesses,
                candidates,
                validation,
                lookalike,
                is_service_error=ocr_output.is_service_error,
                service_error_detail=ocr_output.service_error_detail
            )

            if not confidence.can_confirm:
                all_can_confirm = False

            crop_url = f"/static/crops/{pid}/{crop_filename}"

            processed_line = ProcessedLine(
                line_id=line_id,
                crop=crop_url,
                bbox=bbox,
                guesses=ocr_output.guesses,
                dose_raw=ocr_output.dose_raw,
                freq_raw=ocr_output.freq_raw,
                duration_raw=ocr_output.duration_raw,
                original_ocr_trace=original_ocr_trace,
                top_candidates=candidates,
                selected_candidate=selected_cand,
                rxnorm=rxnorm_result,
                validation=validation,
                lookalike=lookalike,
                confidence=confidence,
                lasa_acknowledged=False,
                status="pending",
                final_drug=selected_cand.brand_name if selected_cand else "unreadable",
                final_dose=validation.dose_standardized or ocr_output.dose_raw,
                final_freq=validation.freq_standardized or ocr_output.freq_raw,
                final_duration=validation.duration_standardized or ocr_output.duration_raw
            )
            processed_lines.append(processed_line)

        # If no lines segmented
        if not processed_lines:
            all_can_confirm = False

        return PrescriptionResponse(
            prescription_id=pid,
            original_filename=image_path.name,
            image_url=f"/static/uploads/{image_path.name}",
            quality_check=quality,
            lines=processed_lines,
            total_lines=len(processed_lines),
            status="pending",
            all_can_confirm=all_can_confirm,
            vision_ai_status=overall_vision_status,
            vision_ai_message=overall_vision_msg,
            created_at=datetime.now(timezone.utc).isoformat()
        )

    def process_prescription_image_sync(
        self,
        image_path: Path,
        prescription_id: Optional[str] = None,
        allow_demo_fallback: bool = False,
        manual_rotation: Optional[int] = None
    ) -> PrescriptionResponse:
        """Synchronous wrapper for offline testing and CLI benchmark execution"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.process_prescription_image(image_path, prescription_id, allow_demo_fallback, manual_rotation=manual_rotation),
                loop
            )
            return future.result()
        else:
            return loop.run_until_complete(
                self.process_prescription_image(image_path, prescription_id, allow_demo_fallback, manual_rotation=manual_rotation)
            )
