import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
import cv2
import numpy as np
import pytest

from app.pipeline.processor import MedMatchPipeline
from app.pipeline.schema import GeminiPageOutput, GeminiPageMedicationEntry, RxNormLookupResult

@pytest.fixture
def sample_prescription_image(tmp_path):
    img = np.full((1600, 1200, 3), 245, dtype=np.uint8)
    # 3 lines of medicine
    cv2.putText(img, "Augmentin 625mg PO TID x 5d", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    cv2.putText(img, "Dolo 650mg PO SOS x 3d", (100, 500), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    cv2.putText(img, "Pan 40mg PO OD x 7d", (100, 700), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    path = tmp_path / "test_async_rx.png"
    cv2.imwrite(str(path), img)
    return path

class TestTask4AsyncAndSpeed:
    @pytest.mark.anyio
    async def test_rxnorm_lookups_run_concurrently_with_gather(self, sample_prescription_image):
        """Task 4: RxNorm lookups run concurrently via asyncio.gather, not sequentially"""
        proc = MedMatchPipeline()

        # Mock OCR reader
        mock_ocr = MagicMock()
        mock_ocr.detect_orientation.return_value = (0, True)
        mock_ocr.read_prescription_page.return_value = GeminiPageOutput(
            prescriptions=[
                GeminiPageMedicationEntry(guesses=["Augmentin 625mg"], dose_raw="625mg", freq_raw="TID", duration_raw="5 days", bbox=[150, 80, 250, 900]),
                GeminiPageMedicationEntry(guesses=["Dolo 650mg"], dose_raw="625mg", freq_raw="SOS", duration_raw="3 days", bbox=[280, 80, 380, 900]),
                GeminiPageMedicationEntry(guesses=["Pan 40mg"], dose_raw="40mg", freq_raw="OD", duration_raw="7 days", bbox=[410, 80, 510, 900]),
            ],
            is_service_error=False
        )
        proc.ocr_reader = mock_ocr

        # Each lookup takes 0.3s. Sequential would take 3 * 0.3s = 0.9s+.
        # Concurrent with asyncio.gather will take ~0.3s to 0.5s.
        async def slow_lookup(name: str):
            await asyncio.sleep(0.3)
            return RxNormLookupResult(
                original_term=name,
                normalized_term=name,
                status="exact_match",
                is_exact=True,
                rxcui="12345",
                display_name=f"{name} Oral Tablet",
                source="NLM RxNorm"
            )

        mock_rxnorm = MagicMock()
        mock_rxnorm.lookup_medicine = AsyncMock(side_effect=slow_lookup)
        proc.rxnorm_client = mock_rxnorm

        start_time = time.perf_counter()
        res = await proc.process_prescription_image(sample_prescription_image, prescription_id="rx_async_test")
        duration = time.perf_counter() - start_time

        assert res.total_lines == 3
        # Must finish well under the sequential time of 3 * 0.3 = 0.9s (should be ~0.35s - 0.6s)
        assert duration < 0.8, f"RxNorm took {duration:.2f}s; expected concurrent execution under 0.8s"

    @pytest.mark.anyio
    async def test_rxnorm_timeout_budget_caps_at_3s_and_returns_neutral_note(self, sample_prescription_image):
        """Task 4: Total RxNorm budget is capped at 3s and returns neutral US database note"""
        proc = MedMatchPipeline()

        mock_ocr = MagicMock()
        mock_ocr.detect_orientation.return_value = (0, True)
        mock_ocr.read_prescription_page.return_value = GeminiPageOutput(
            prescriptions=[
                GeminiPageMedicationEntry(guesses=["SlowMed 500mg"], dose_raw="500mg", freq_raw="TID", duration_raw="5 days", bbox=[150, 80, 250, 900]),
            ],
            is_service_error=False
        )
        proc.ocr_reader = mock_ocr

        # Simulate RxNav hanging for 10 seconds
        async def hanging_lookup(name: str):
            await asyncio.sleep(10.0)
            return RxNormLookupResult(original_term=name, status="exact_match")

        mock_rxnorm = MagicMock()
        mock_rxnorm.lookup_medicine = AsyncMock(side_effect=hanging_lookup)
        proc.rxnorm_client = mock_rxnorm

        start_time = time.perf_counter()
        res = await proc.process_prescription_image(sample_prescription_image, prescription_id="rx_timeout_test")
        duration = time.perf_counter() - start_time

        # Bounded by 3.0s budget
        assert duration < 3.8, f"Expected lookup to be bounded by 3s budget, took {duration:.2f}s"
        assert res.total_lines == 1
        line = res.lines[0]
        assert line.rxnorm.status == "not_found"
        assert "not found in RxNorm (US database)" in line.rxnorm.message

    def test_sync_runner_cannot_deadlock(self, sample_prescription_image):
        """Task 4: process_prescription_image_sync executes safely and does not deadlock"""
        proc = MedMatchPipeline()
        mock_ocr = MagicMock()
        mock_ocr.detect_orientation.return_value = (0, True)
        mock_ocr.read_prescription_page.return_value = GeminiPageOutput(
            prescriptions=[
                GeminiPageMedicationEntry(guesses=["Amoxicillin 500mg"], dose_raw="500mg", freq_raw="TID", duration_raw="7 days", bbox=[150, 80, 250, 900]),
            ],
            is_service_error=False
        )
        proc.ocr_reader = mock_ocr

        # Calling sync runner from non-async context
        res = proc.process_prescription_image_sync(sample_prescription_image, prescription_id="rx_sync_safe")
        assert res.status == "pending"
        assert res.total_lines == 1

        # Calling sync runner when an event loop is running in thread (nested)
        async def nested_call():
            # In an active event loop, calling sync runner must not deadlock
            return proc.process_prescription_image_sync(sample_prescription_image, prescription_id="rx_nested_safe")

        res_nested = asyncio.run(nested_call())
        assert res_nested.status == "pending"
        assert res_nested.total_lines == 1
