import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np

from app.config import CROPS_DIR
from app.pipeline.schema import (
    ProcessedLine,
    PrescriptionResponse,
    QualityCheckResult,
    GeminiLineOutput,
    AgreedPipelineData,
    LineCropData
)
from app.pipeline.image_processing import ImageQualityProcessor
from app.pipeline.ocr import GeminiOCRReader
from app.pipeline.matcher import DrugCatalogMatcher
from app.pipeline.validator import PrescriptionValidator
from app.pipeline.confidence import ConfidenceEvaluator, LookalikeChecker

class MedMatchPipeline:
    def __init__(self):
        self.quality_processor = ImageQualityProcessor()
        self.ocr_reader = GeminiOCRReader()
        self.matcher = DrugCatalogMatcher()
        self.validator = PrescriptionValidator()
        self.confidence_evaluator = ConfidenceEvaluator()
        self.lookalike_checker = LookalikeChecker()

    def process_prescription_image(
        self,
        image_path: Path,
        prescription_id: Optional[str] = None,
        pre_existing_lines: Optional[List[dict]] = None
    ) -> PrescriptionResponse:
        """
        End-to-end execution of MedMatch Rx processing pipeline on an uploaded image:
        1. Image quality inspection (blur, dark, glare)
        2. Image deskewing
        3. Line segmentation
        4. Gemini OCR reading
        5. RapidFuzz & phonetic matching
        6. Clinical validation
        7. Rule-based confidence scoring & look-alike safety alerts
        """
        pid = prescription_id or f"rx_{uuid.uuid4().hex[:8]}"
        image_bgr = cv2.imread(str(image_path))
        
        # 1. Image Quality Check
        quality = self.quality_processor.analyze_quality(image_bgr)
        if not quality.passed:
            return PrescriptionResponse(
                prescription_id=pid,
                original_filename=image_path.name,
                image_url=f"/static/uploads/{image_path.name}",
                quality_check=quality,
                lines=[],
                total_lines=0,
                all_can_confirm=False,
                created_at=datetime.utcnow().isoformat()
            )

        # 2. Auto-orient and Deskew
        deskewed_img, angle = self.quality_processor.auto_orient_and_deskew(image_bgr)
        quality.deskew_angle = angle

        # 3. Line Segmentation or use pre-existing line definitions
        crops_out_dir = CROPS_DIR / pid
        crops_out_dir.mkdir(parents=True, exist_ok=True)
        
        line_specs = []
        if pre_existing_lines:
            # When evaluating known benchmarks with existing crops
            for item in pre_existing_lines:
                crop_name = item.get("crop", "")
                bbox = item.get("bbox", [50, 50, 700, 150])
                line_specs.append((crop_name, bbox, item))
        else:
            # Segment dynamically from image
            segmented = self.quality_processor.segment_lines(deskewed_img, crops_out_dir, pid)
            for crop_name, bbox in segmented:
                line_specs.append((crop_name, bbox, None))

        # 4, 5, 6, 7: Process each line item
        processed_lines: List[ProcessedLine] = []
        all_can_confirm = True

        for idx, (crop_filename, bbox, pre_data) in enumerate(line_specs):
            line_id = idx + 1
            crop_full_path = crops_out_dir / crop_filename
            
            # If not copied to pid folder, check root crops
            if not crop_full_path.exists():
                alt_path = image_path.parent.parent / "crops" / crop_filename
                if alt_path.exists():
                    crop_full_path = alt_path

            # Step 3: OCR
            if pre_data and "guesses" in pre_data:
                ocr_output = GeminiLineOutput(
                    guesses=pre_data.get("guesses", []),
                    dose_raw=pre_data.get("dose_raw", "unknown"),
                    freq_raw=pre_data.get("freq_raw", "unknown"),
                    duration_raw=pre_data.get("duration_raw", "unknown")
                )
            else:
                ocr_output = self.ocr_reader.read_line_crop(str(crop_full_path))

            # Step 4: Matching
            candidates = self.matcher.match_guesses(ocr_output.guesses, top_k=3)
            selected_cand = candidates[0] if candidates else None

            # Step 5: Clinical Validation
            validation = self.validator.validate_line(
                ocr_output.dose_raw,
                ocr_output.freq_raw,
                ocr_output.duration_raw,
                selected_cand
            )

            # Step 6: Look-alike and Confidence Scoring
            lookalike = self.lookalike_checker.check_candidate(selected_cand.brand_name if selected_cand else "")
            confidence = self.confidence_evaluator.evaluate_confidence(
                ocr_output.guesses,
                candidates,
                validation,
                lookalike
            )

            if not confidence.can_confirm:
                all_can_confirm = False

            # Format standardized line crop reference
            crop_url = f"/static/crops/{pid}/{crop_filename}" if (crops_out_dir / crop_filename).exists() else f"/static/testset/crops/{crop_filename}"

            processed_line = ProcessedLine(
                line_id=line_id,
                crop=crop_url,
                bbox=bbox,
                guesses=ocr_output.guesses,
                dose_raw=ocr_output.dose_raw,
                freq_raw=ocr_output.freq_raw,
                duration_raw=ocr_output.duration_raw,
                top_candidates=candidates,
                selected_candidate=selected_cand,
                validation=validation,
                lookalike=lookalike,
                confidence=confidence,
                status="pending",
                final_drug=selected_cand.brand_name if selected_cand else "unreadable",
                final_dose=validation.dose_standardized or ocr_output.dose_raw,
                final_freq=validation.freq_standardized or ocr_output.freq_raw,
                final_duration=validation.duration_standardized or ocr_output.duration_raw
            )
            processed_lines.append(processed_line)

        return PrescriptionResponse(
            prescription_id=pid,
            original_filename=image_path.name,
            image_url=f"/static/uploads/{image_path.name}",
            quality_check=quality,
            lines=processed_lines,
            total_lines=len(processed_lines),
            all_can_confirm=all_can_confirm,
            created_at=datetime.utcnow().isoformat()
        )
