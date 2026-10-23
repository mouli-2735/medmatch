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
    GeminiPageOutput,
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
        # Never block event loop: run OpenCV read with asyncio.to_thread
        image_bgr = await asyncio.to_thread(cv2.imread, str(image_path))
        
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

        # 1. OpenCV Image Quality Check (run in thread)
        quality = await asyncio.to_thread(self.quality_processor.analyze_quality, image_bgr)
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

        # 2. OpenCV Auto-orient and Deskew (run in thread)
        deskewed_img, angle, rot_applied, orient_conf = await asyncio.to_thread(
            self.quality_processor.auto_orient_and_deskew,
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
        success_enc, encoded = await asyncio.to_thread(cv2.imencode, ".jpg", deskewed_img)
        page_bytes = encoded.tobytes() if success_enc else b""

        # Run page OCR without blocking event loop
        page_output = await asyncio.to_thread(
            self.ocr_reader.read_prescription_page,
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
            line_items = await asyncio.to_thread(
                self._extract_page_crops,
                deskewed_img,
                usable_entries,
                crops_out_dir,
                pid,
                page_output
            )

        # Fallback to OpenCV line segmentation if no usable boxes returned
        if not line_items:
            segmented = await asyncio.to_thread(
                self.quality_processor.segment_lines, deskewed_img, crops_out_dir, pid
            )
            if self.quality_processor.last_segmentation_warning:
                overall_vision_msg = (
                    (overall_vision_msg + "; " if overall_vision_msg else "")
                    + self.quality_processor.last_segmentation_warning
                )

            async def _read_single_crop(crop_filename: str, bbox: List[int]) -> Tuple[str, List[int], GeminiLineOutput]:
                crop_full_path = crops_out_dir / crop_filename
                ocr_line = await asyncio.to_thread(
                    self.ocr_reader.read_line_crop,
                    str(crop_full_path),
                    allow_demo_fallback=allow_demo_fallback
                )
                return (crop_filename, bbox, ocr_line)

            crop_reads = [_read_single_crop(fn, bb) for fn, bb in segmented]
            if crop_reads:
                read_results = await asyncio.gather(*crop_reads)
                for crop_filename, bbox, ocr_line in read_results:
                    if ocr_line.is_service_error and not page_output.is_service_error:
                        overall_vision_status = "service_unavailable"
                        overall_vision_msg = ocr_line.service_error_detail
                    line_items.append((crop_filename, bbox, ocr_line))

        # If no lines found (e.g. blank page): return rejected response
        if not line_items:
            quality.passed = False
            quality.message = "No handwriting found. Retake the photo or crop manually."
            return PrescriptionResponse(
                prescription_id=pid,
                original_filename=image_path.name,
                image_url=f"/static/uploads/{image_path.name}",
                quality_check=quality,
                lines=[],
                total_lines=0,
                status="rejected",
                all_can_confirm=False,
                vision_ai_status=overall_vision_status,
                vision_ai_message="No handwriting found. Retake the photo or crop manually.",
                created_at=datetime.now(timezone.utc).isoformat()
            )

        # 4, 5, 6, 7, 8, 9: Process each line item
        line_prep = []
        for idx, (crop_filename, bbox, ocr_output) in enumerate(line_items):
            candidates = self.matcher.match_guesses(ocr_output.guesses, top_k=4)
            selected_cand = candidates[0] if candidates else None
            rxnorm_query = selected_cand.brand_name if selected_cand else (
                ocr_output.guesses[0] if (ocr_output.guesses and ocr_output.guesses[0] != "unreadable") else ""
            )
            line_prep.append((crop_filename, bbox, ocr_output, candidates, selected_cand, rxnorm_query))

        # Run RxNorm lookups with asyncio.gather and a total 3 s budget
        async def _safe_rxnorm_lookup(term: str) -> RxNormLookupResult:
            if not term or term.lower() in ["unreadable", "unknown"]:
                return RxNormLookupResult(
                    original_term=term,
                    normalized_term=term,
                    status="unreadable",
                    is_exact=False,
                    candidates=[],
                    source="NLM RxNorm",
                    message="not found in RxNorm (US database)"
                )
            try:
                return await self.rxnorm_client.lookup_medicine(term)
            except Exception:
                return RxNormLookupResult(
                    original_term=term,
                    normalized_term=term,
                    status="not_found",
                    is_exact=False,
                    candidates=[],
                    source="NLM RxNorm",
                    message="not found in RxNorm (US database)"
                )

        rxnorm_tasks = [_safe_rxnorm_lookup(q) for _, _, _, _, _, q in line_prep]
        try:
            rxnorm_results = await asyncio.wait_for(
                asyncio.gather(*rxnorm_tasks, return_exceptions=True),
                timeout=3.0
            )
        except (asyncio.TimeoutError, TimeoutError):
            rxnorm_results = [
                RxNormLookupResult(
                    original_term=q,
                    normalized_term=q,
                    status="not_found",
                    is_exact=False,
                    candidates=[],
                    source="NLM RxNorm",
                    message="not found in RxNorm (US database)"
                )
                for _, _, _, _, _, q in line_prep
            ]

        processed_lines: List[ProcessedLine] = []
        all_can_confirm = True

        for idx, (crop_filename, bbox, ocr_output, candidates, selected_cand, _) in enumerate(line_prep):
            line_id = idx + 1
            rx_res = rxnorm_results[idx] if idx < len(rxnorm_results) else None
            if isinstance(rx_res, Exception) or rx_res is None:
                rx_res = RxNormLookupResult(
                    original_term="",
                    status="not_found",
                    message="not found in RxNorm (US database)"
                )

            # Store original raw OCR extraction for full clinical auditability
            original_ocr_trace = {
                "raw_guesses": list(ocr_output.guesses),
                "raw_dose": ocr_output.dose_raw,
                "raw_freq": ocr_output.freq_raw,
                "raw_duration": ocr_output.duration_raw,
                "is_service_error": ocr_output.is_service_error,
                "service_error_detail": ocr_output.service_error_detail
            }

            validation = self.validator.validate_line(
                ocr_output.dose_raw,
                ocr_output.freq_raw,
                ocr_output.duration_raw,
                selected_cand
            )

            candidate_for_lasa = selected_cand.brand_name if selected_cand else ""
            lookalike = self.lookalike_checker.check_candidate(candidate_for_lasa)

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
                rxnorm=rx_res,
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

    @staticmethod
    def _extract_page_crops(
        deskewed_img: np.ndarray,
        usable_entries: List[Any],
        crops_out_dir: Path,
        pid: str,
        page_output: GeminiPageOutput
    ) -> List[Tuple[str, List[int], GeminiLineOutput]]:
        h_img, w_img = deskewed_img.shape[:2]
        line_items = []
        for idx, entry in enumerate(usable_entries):
            line_num = idx + 1
            ymin, xmin, ymax, xmax = entry.bbox
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
        return line_items

    def process_prescription_image_sync(
        self,
        image_path: Path,
        prescription_id: Optional[str] = None,
        allow_demo_fallback: bool = False,
        manual_rotation: Optional[int] = None
    ) -> PrescriptionResponse:
        """Synchronous wrapper for offline testing and CLI benchmark execution (cannot deadlock)"""
        coro = self.process_prescription_image(
            image_path,
            prescription_id,
            allow_demo_fallback,
            manual_rotation=manual_rotation
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)
