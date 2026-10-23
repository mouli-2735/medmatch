from pathlib import Path
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db
from app.pipeline.image_processing import ImageQualityProcessor
from app.pipeline.ocr import GeminiOCRReader

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

class TestTask2OrientationAndDeskew:
    def test_resize_to_long_side_1600(self):
        """Task 2: Resize to long side 1600 before processing so thresholds are scale-independent"""
        processor = ImageQualityProcessor()
        # Small image (800x600)
        small = np.zeros((600, 800, 3), dtype=np.uint8)
        scaled_up = processor.resize_to_long_side(small, 1600)
        assert max(scaled_up.shape[:2]) == 1600
        assert scaled_up.shape == (1200, 1600, 3)

        # Large image (3200x2400)
        large = np.zeros((2400, 3200, 3), dtype=np.uint8)
        scaled_down = processor.resize_to_long_side(large, 1600)
        assert max(scaled_down.shape[:2]) == 1600
        assert scaled_down.shape == (1200, 1600, 3)

    def test_deskew_projection_profile_search(self):
        """Task 2: Projection-profile search over -10..+10 degrees accurately detects skew"""
        processor = ImageQualityProcessor()
        # Create an image with clear horizontal text lines
        img = np.full((1200, 1600, 3), 255, dtype=np.uint8)
        for y in range(200, 1000, 100):
            cv2.putText(img, "AMOXICILLIN 500MG CAPSULE 1-0-1 FOR 7 DAYS", (100, y), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3)

        # Artificially tilt by +3.0 degrees
        center = (800, 600)
        M = cv2.getRotationMatrix2D(center, 3.0, 1.0)
        tilted = cv2.warpAffine(img, M, (1600, 1200), borderMode=cv2.BORDER_REPLICATE)

        deskewed, detected_angle = processor.deskew(tilted)
        # Should detect ~ -3.0 degrees correction (+- 0.5)
        assert abs(detected_angle - (-3.0)) <= 0.5
        assert deskewed.shape == tilted.shape

    def test_manual_rotation_override(self):
        """Task 2: Manual rotation (0/90/180/270) overrides auto-detection and marks orientation_confident=True"""
        processor = ImageQualityProcessor()
        img = np.zeros((1200, 1600, 3), dtype=np.uint8)

        # Test 270 degrees
        deskewed, angle, rot, conf = processor.auto_orient_and_deskew(img, manual_rotation=270)
        assert rot == 270
        assert conf is True
        assert deskewed.shape[0] == 1600  # Rotated to portrait!
        assert deskewed.shape[1] == 1200

        # Test 180 degrees
        deskewed_180, _, rot_180, conf_180 = processor.auto_orient_and_deskew(img, manual_rotation=180)
        assert rot_180 == 180
        assert conf_180 is True

    def test_gemini_orientation_detection_when_available(self):
        """Task 2: Low-res Gemini call resolves orientation when available"""
        processor = ImageQualityProcessor()
        mock_reader = MagicMock()
        mock_reader.detect_orientation.return_value = (270, True)

        img = np.zeros((1200, 1600, 3), dtype=np.uint8)
        deskewed, angle, rot, conf = processor.auto_orient_and_deskew(img, ocr_reader=mock_reader)
        assert rot == 270
        assert conf is True
        assert mock_reader.detect_orientation.called

    def test_orientation_fallback_when_gemini_unavailable(self):
        """Task 2: When Gemini is unavailable, applies default and marks orientation_confident=False"""
        processor = ImageQualityProcessor()
        # Reader without API key or failing orientation
        mock_reader = MagicMock()
        mock_reader.detect_orientation.return_value = (None, False)

        # Landscape image (1200x1600)
        img = np.zeros((1200, 1600, 3), dtype=np.uint8)
        deskewed, angle, rot, conf = processor.auto_orient_and_deskew(img, ocr_reader=mock_reader)
        assert rot == 270  # Default portrait orientation
        assert conf is False  # Flagged uncertain for UI notice!

    def test_rx_bf0ce0de_real_photo_sideways_crops_upright(self):
        """Task 2: Real photo rx_bf0ce0de.jpeg is oriented upright and crops follow top-to-bottom reading order"""
        real_img_path = Path("data/uploads/rx_bf0ce0de.jpeg")
        processor = ImageQualityProcessor()
        if real_img_path.exists():
            img_bgr = cv2.imread(str(real_img_path))
        else:
            # Create synthetic sideways page: 1200 H x 1600 W (which rotates 270 deg to 1600 H x 1200 W)
            img_bgr = np.full((1200, 1600, 3), 245, dtype=np.uint8)
            # Draw vertical bars that become horizontal text lines after 270 deg rotation
            for x in range(300, 1300, 180):
                cv2.rectangle(img_bgr, (x, 200), (x + 30, 1000), (30, 30, 30), -1)
        assert img_bgr is not None
        assert img_bgr.shape[1] > img_bgr.shape[0]  # Sideways (1600 wide, 1200 high)

        deskewed, deskew_angle, rot_applied, orient_conf = processor.auto_orient_and_deskew(img_bgr)
        # Must be rotated to portrait!
        assert deskewed.shape[0] > deskewed.shape[1]  # Height > width (1600 high, 1200 wide)
        assert rot_applied == 270

        # Segment lines on deskewed upright image
        crops_dir = Path("data/test_crops_rx_bf0ce0de")
        crops = processor.segment_lines(deskewed, crops_dir, "test_bf0")
        assert len(crops) > 0

        # Verify bboxes are in top-to-bottom reading order (y coordinates strictly increasing)
        y_coords = [bbox[1] for _, bbox in crops]
        assert y_coords == sorted(y_coords)

    def test_upload_endpoint_accepts_rotation_form_field(self, client):
        """Task 2: POST /api/prescriptions/upload accepts optional rotation form field"""
        img_path = Path("../testset/images/rx_001.png")
        if img_path.exists():
            img_bytes = img_path.read_bytes()
        else:
            dummy_img = np.full((1200, 1600, 3), 245, dtype=np.uint8)
            for y in range(100, 1100, 100):
                cv2.putText(dummy_img, f"Prescription Test Line at Y={y} ABCDEFGHIJKLMNOPQRSTUVWXYZ", (100, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
            _, enc = cv2.imencode(".png", dummy_img)
            img_bytes = enc.tobytes()

        res = client.post(
            "/api/prescriptions/upload",
            files={"file": ("test_rx.png", img_bytes, "image/png")},
            data={"rotation": "270"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["quality_check"]["rotation_applied"] == 270
        assert data["quality_check"]["orientation_confident"] is True

