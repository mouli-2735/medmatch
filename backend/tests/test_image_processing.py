import pytest
import numpy as np
import cv2
from app.pipeline.image_processing import ImageQualityProcessor

@pytest.fixture
def processor():
    return ImageQualityProcessor()

class TestImageQualityProcessor:
    def test_sharp_image_passes(self, processor):
        # Create image with high-contrast text edges
        img = np.full((400, 400, 3), 245, dtype=np.uint8)
        cv2.putText(img, "DOCTOR PRESCRIPTION Rx", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
        res = processor.analyze_quality(img)
        assert res.passed is True
        assert res.is_blurry is False
        assert res.is_dark is False
        assert res.has_glare is False

    def test_blurry_image_rejected(self, processor):
        img = np.full((400, 400, 3), 240, dtype=np.uint8)
        cv2.putText(img, "BLURRY SAMPLE", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
        blurry = cv2.GaussianBlur(img, (45, 45), 20)
        res = processor.analyze_quality(blurry)
        assert res.passed is False
        assert res.is_blurry is True
        assert "blurry" in res.message.lower()

    def test_dark_image_rejected(self, processor):
        # Very dark image
        img = np.full((400, 400, 3), 25, dtype=np.uint8)
        res = processor.analyze_quality(img)
        assert res.passed is False
        assert res.is_dark is True
        assert "dim" in res.message.lower()

    def test_glare_image_rejected(self, processor):
        # Image with large central white blowout
        img = np.full((400, 400, 3), 200, dtype=np.uint8)
        img[100:300, 100:300] = 255 # 200x200 = 40,000 / 160,000 = 25% glare
        res = processor.analyze_quality(img)
        assert res.passed is False
        assert res.has_glare is True
        assert "glare" in res.message.lower()
