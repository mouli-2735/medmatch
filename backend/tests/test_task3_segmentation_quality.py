import pytest
import numpy as np
import cv2
from pathlib import Path
from unittest.mock import MagicMock

from app.pipeline.image_processing import ImageQualityProcessor
from app.pipeline.processor import MedMatchPipeline
from app.pipeline.schema import GeminiPageOutput, GeminiLineOutput

@pytest.fixture
def processor():
    return ImageQualityProcessor()

@pytest.fixture
def pipeline_processor(tmp_path):
    proc = MedMatchPipeline()
    # Mock OCR reader to avoid real API calls
    mock_ocr = MagicMock()
    mock_ocr.detect_orientation.return_value = (0, True)
    mock_ocr.read_prescription_page.return_value = GeminiPageOutput(
        prescriptions=[],
        is_service_error=False
    )
    mock_ocr.read_line_crop.return_value = GeminiLineOutput(
        guesses=["Amoxicillin 500mg"],
        dose_raw="500mg",
        freq_raw="TID",
        duration_raw="7 days",
        is_service_error=False
    )
    proc.ocr_reader = mock_ocr
    return proc

class TestTask3SegmentationAndQualityGate:
    def test_pure_white_scan_with_text_passes(self, processor):
        """Task 3: Pure-white scan or screenshot with black text must NOT be rejected as glare"""
        # Create pure white scan (pixel values = 255) with sharp black text
        img = np.full((1600, 1200, 3), 255, dtype=np.uint8)
        cv2.putText(img, "DOCTOR CLINICAL PRESCRIPTION", (150, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        cv2.putText(img, "Rx: Amoxicillin 500mg PO TID x 7d", (150, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        cv2.putText(img, "Paracetamol 650mg SOS", (150, 600), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

        res = processor.analyze_quality(img)
        assert res.passed is True
        assert res.has_glare is False
        assert res.is_blurry is False
        assert res.is_dark is False
        assert "passed" in res.message.lower()

    def test_real_flash_hotspot_fails_glare(self, processor):
        """Task 3: Concentrated overexposed flash reflection hotspot must fail glare check"""
        # Real photo lighting: background brightness ~ 195 with a concentrated central flash reflection (255)
        img = np.full((1600, 1200, 3), 195, dtype=np.uint8)
        # Add central camera flash circle (radius 220, ~8% of image)
        cv2.circle(img, (600, 800), 220, (255, 255, 255), -1)

        res = processor.analyze_quality(img)
        assert res.passed is False
        assert res.has_glare is True
        assert res.glare_share > 0.05
        assert "glare" in res.message.lower()

    def test_11_line_page_returns_11_crops(self, processor, tmp_path):
        """Task 3: Prescription with 11 lines returns all 11 crops (no silent 8-line cap)"""
        h, w = 1800, 1200
        img = np.full((h, w, 3), 245, dtype=np.uint8)

        # Draw 11 distinct medicine lines
        for i in range(11):
            y = 150 + i * 140
            text = f"{i+1}. Amoxicillin 500mg capsules PO TID x 7 days"
            cv2.putText(img, text, (120, y), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (10, 10, 10), 2)

        crops_dir = tmp_path / "crops_11"
        crops = processor.segment_lines(img, crops_dir, "test_11")
        assert len(crops) == 11, f"Expected 11 crops, got {len(crops)}"
        # Verify files were saved
        for crop_name, bbox in crops:
            assert (crops_dir / crop_name).exists()
            assert bbox[2] > bbox[0]
            assert bbox[3] > bbox[1]

    def test_35_line_page_truncated_to_30_with_warning(self, processor, tmp_path):
        """Task 3: Allows up to 30 lines and produces warning when truncated"""
        h, w = 5000, 1200
        img = np.full((h, w, 3), 245, dtype=np.uint8)

        for i in range(35):
            y = 100 + i * 130
            text = f"Medication Item {i+1} 500mg Daily Dose Instructions"
            cv2.putText(img, text, (120, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2)

        crops_dir = tmp_path / "crops_35"
        crops, warning = processor.segment_lines(img, crops_dir, "test_35", return_warning=True)
        assert len(crops) == 30
        assert warning is not None
        assert "30 lines" in warning
        assert processor.last_segmentation_warning is not None

    def test_blank_page_returns_zero_crops_and_rejected_response(self, pipeline_processor, tmp_path):
        """Task 3: Blank page produces 0 fake crops and returns a rejected response"""
        # Create a completely blank page
        blank_img = np.full((1600, 1200, 3), 250, dtype=np.uint8)
        blank_path = tmp_path / "blank_rx.png"
        cv2.imwrite(str(blank_path), blank_img)

        # Process blank image
        res = pipeline_processor.process_prescription_image_sync(blank_path, prescription_id="rx_blank_test")
        assert res.status == "rejected"
        assert res.total_lines == 0
        assert len(res.lines) == 0
        assert res.all_can_confirm is False
        assert "No handwriting found" in res.vision_ai_message
        assert "No handwriting found" in res.quality_check.message

    def test_small_fragments_dropped_from_line_segmentation(self, processor, tmp_path):
        """Task 3: Non-prescription fragments smaller than 15% width (e.g. 'Rx' mark, bullet points) are dropped"""
        h, w = 1200, 1000
        img = np.full((h, w, 3), 245, dtype=np.uint8)

        # Draw a tiny 'Rx' mark at top (narrow, ~50px width = 5% of page width)
        cv2.putText(img, "Rx", (80, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        # Draw a tiny bullet point dot
        cv2.circle(img, (80, 300), 5, (0, 0, 0), -1)

        # Draw 2 full medicine lines (> 15% page width)
        cv2.putText(img, "1. Metformin 500mg BD after food", (100, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
        cv2.putText(img, "2. Glimepiride 1mg OD before food", (100, 650), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)

        crops_dir = tmp_path / "crops_filtered"
        crops = processor.segment_lines(img, crops_dir, "test_filter")
        # Only the 2 medicine lines should become crops, 'Rx' and bullet point dropped!
        assert len(crops) == 2
