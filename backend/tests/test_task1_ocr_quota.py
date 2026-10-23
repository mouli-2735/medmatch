import hashlib
import json
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import GEMINI_MODEL, GEMINI_FALLBACK_MODEL
from app.db import init_db, get_cached_ocr, set_cached_ocr
from app.pipeline.ocr import GeminiOCRReader, parse_retry_delay
from app.pipeline.schema import GeminiPageOutput, GeminiPageMedicationEntry

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

class TestTask1GeminiReliabilityAndQuota:
    def test_config_model_names_single_source_of_truth(self):
        """Task 1: Verify model names are env-driven and contain no hardcoded 'gemini-3.x' strings"""
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent.parent
        config_text = (backend_dir / "app" / "config.py").read_text(encoding="utf-8")
        ocr_text = (backend_dir / "app" / "pipeline" / "ocr.py").read_text(encoding="utf-8")
        assert "gemini-3." not in config_text
        assert "gemini-3." not in ocr_text
        assert GEMINI_MODEL is not None
        assert GEMINI_FALLBACK_MODEL is not None

    def test_health_check_exposes_model_ok_and_rxnorm(self, client):
        """Task 1: Health check exposes vision_ai_ready, model_ok, and dynamic rxnorm_service"""
        with patch.object(GeminiOCRReader, "verify_model", return_value=(True, None)):
            with patch("app.pipeline.rxnorm.RxNormClient.check_health", new_callable=AsyncMock) as mock_rx_health:
                mock_rx_health.return_value = (True, "online")
                res = client.get("/api/health")
                assert res.status_code == 200
                data = res.json()
                assert "vision_ai_ready" in data
                assert "model_ok" in data
                assert data["vision_ai_ready"] is True
                assert data["model_ok"] is True
                assert data["rxnorm_service"] == "online"

    def test_health_check_degraded_when_model_missing(self, client):
        """Task 1: Health check reflects model failure accurately"""
        with patch.object(GeminiOCRReader, "verify_model", return_value=(False, "Model not found")):
            with patch("app.pipeline.rxnorm.RxNormClient.check_health", new_callable=AsyncMock) as mock_rx_health:
                mock_rx_health.return_value = (False, "unavailable")
                res = client.get("/api/health")
                assert res.status_code == 200
                data = res.json()
                assert data["vision_ai_ready"] is False
                assert data["model_ok"] is False
                assert data["rxnorm_service"] == "unavailable"

    def test_verify_model_method(self):
        """Task 1: verify_model verifies model exists via client.models.get"""
        reader = GeminiOCRReader(api_key="test-key", model_name="gemini-2.5-flash")
        mock_client = MagicMock()
        mock_client.models.get.return_value = MagicMock(name="gemini-2.5-flash")
        reader.client = mock_client

        ok, err = reader.verify_model()
        assert ok is True
        assert err is None
        mock_client.models.get.assert_called_once_with(model="gemini-2.5-flash")

        # Test failure case
        mock_client.models.get.side_effect = Exception("Model not found in AI Studio")
        ok_fail, err_fail = reader.verify_model()
        assert ok_fail is False
        assert "Model not found in AI Studio" in err_fail

    def test_single_request_page_ocr_and_sqlite_cache(self):
        """Task 1: One request per page, results cached in SQLite by sha256(image + model)"""
        import uuid
        fake_image_bytes = b"fake-jpeg-" + uuid.uuid4().bytes
        reader = GeminiOCRReader(api_key="test-key", model_name="gemini-test-model")
        mock_client = MagicMock()
        reader.client = mock_client

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "prescriptions": [
                {
                    "bbox": [100, 50, 200, 900],
                    "guesses": ["Augmentin", "Amoxicillin"],
                    "dose_raw": "625mg",
                    "freq_raw": "1-0-1",
                    "duration_raw": "5d"
                },
                {
                    "bbox": [250, 50, 350, 900],
                    "guesses": ["Pantocid"],
                    "dose_raw": "40mg",
                    "freq_raw": "1-0-0",
                    "duration_raw": "5d"
                }
            ]
        })
        mock_client.models.generate_content.return_value = mock_response

        # First call: makes exactly 1 API call
        res1 = reader.read_prescription_page(fake_image_bytes)
        assert mock_client.models.generate_content.call_count == 1
        assert len(res1.prescriptions) == 2
        assert res1.prescriptions[0].guesses[0] == "Augmentin"

        # Verify cached in SQLite
        cache_key = hashlib.sha256(fake_image_bytes + "gemini-test-model".encode("utf-8")).hexdigest()
        cached = get_cached_ocr(cache_key)
        assert cached is not None
        assert len(cached["prescriptions"]) == 2

        # Second call: served from SQLite cache, 0 additional API calls!
        res2 = reader.read_prescription_page(fake_image_bytes)
        assert mock_client.models.generate_content.call_count == 1  # Still 1!
        assert len(res2.prescriptions) == 2

    def test_retry_backoff_and_quota_error_distinction(self):
        """Task 1: Retries 429 with backoff and only reports 'daily quota' if error states so"""
        assert parse_retry_delay("Please retry after 4.5s") == 4.5
        assert parse_retry_delay("Quota exceeded; wait 12s before next call") == 12.0
        assert parse_retry_delay("Random error with no delay") is None

        reader = GeminiOCRReader(api_key="test-key", model_name="gemini-test-model", fallback_model=None)
        mock_client = MagicMock()
        reader.client = mock_client

        # Simulate 429 rate limit
        mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Rate limit reached. retry after 0.1s")

        with patch("time.sleep", return_value=None):
            out = reader.read_prescription_page(b"dummy-image", max_retries=2)
            assert out.is_service_error is True
            assert "temporarily unavailable" in out.service_error_detail
            assert "daily quota" not in out.service_error_detail.lower()

        # Simulate daily quota exhaustion
        mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Daily quota exceeded for project.")
        with patch("time.sleep", return_value=None):
            out_daily = reader.read_prescription_page(b"dummy-image-daily", max_retries=2)
            assert out_daily.is_service_error is True
            assert "daily quota" in out_daily.service_error_detail.lower()
