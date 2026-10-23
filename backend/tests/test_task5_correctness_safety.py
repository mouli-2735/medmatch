import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import (
    get_connection,
    init_db,
    save_prescription_record,
    get_prescription_by_id
)
from scripts.evaluate_benchmark import run_benchmark


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM audit_logs")
        conn.execute("DELETE FROM corrections")
        conn.execute("DELETE FROM lines")
        conn.execute("DELETE FROM prescriptions")
    conn.close()


def test_direct_confirmation_stores_standardized_values():
    """Verify direct line confirmation stores standardized final_dose, final_freq, final_duration, not raw OCR."""
    client = TestClient(app)

    # Ingest a prescription with raw values that standardize differently
    rx_id = "rx_test_std_01"
    rx_data = {
        "prescription_id": rx_id,
        "original_filename": "test.png",
        "quality_check": {
            "passed": True,
            "blur_score": 250.0,
            "mean_brightness": 200.0,
            "glare_share": 0.01,
            "message": "Clear photo"
        },
        "lines": [
            {
                "line_id": 1,
                "crop": "/static/crops/test/line_1.png",
                "guesses": ["Amoxicillin 500mg"],
                "dose_raw": "500 mg",
                "freq_raw": "1-0-1",
                "duration_raw": "5d",
                "selected_candidate": {
                    "brand_name": "Amoxicillin",
                    "generic_name": "Amoxicillin",
                    "strengths": ["500mg"],
                    "combined_score": 0.95
                },
                "validation": {
                    "dose_valid": True,
                    "dose_standardized": "500mg",
                    "freq_valid": True,
                    "freq_standardized": "Twice daily (BD)",
                    "duration_valid": True,
                    "duration_standardized": "5 days",
                    "all_valid": True
                },
                "confidence": {
                    "score": 0.92,
                    "level": "green",
                    "can_confirm": True
                },
                "lookalike": {"is_flagged": False},
                "final_drug": "Amoxicillin",
                "final_dose": "500mg",
                "final_freq": "Twice daily (BD)",
                "final_duration": "5 days"
            }
        ]
    }

    save_prescription_record(rx_data, f"/static/uploads/{rx_id}.png")

    # Confirm directly (no explicit correction overrides)
    resp = client.post(
        f"/api/prescriptions/{rx_id}/lines/1/confirm",
        json={"confirmed_by": "Pharmacist Alice"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Verify what is saved in the database
    stored_rx = get_prescription_by_id(rx_id)
    assert stored_rx is not None
    line = stored_rx["lines"][0]

    assert line["status"] == "confirmed"
    assert line["final_drug"] == "Amoxicillin"
    # Must be standardized values, not raw "500 mg", "1-0-1", "5d"
    assert line["final_dose"] == "500mg"
    assert line["final_freq"] == "Twice daily (BD)"
    assert line["final_duration"] == "5 days"


def test_pharmacist_pin_enforcement():
    """Verify pharmacist PIN verification when PHARMACIST_PIN environment variable is configured."""
    client = TestClient(app)

    rx_id = "rx_test_pin_01"
    rx_data = {
        "prescription_id": rx_id,
        "original_filename": "test.png",
        "quality_check": {"passed": True, "blur_score": 250, "mean_brightness": 200, "glare_share": 0.01, "message": "OK"},
        "lines": [
            {
                "line_id": 1,
                "crop": "/static/crops/test/line_1.png",
                "guesses": ["Paracetamol 650mg"],
                "dose_raw": "650mg",
                "freq_raw": "TDS",
                "duration_raw": "3 days",
                "selected_candidate": {"brand_name": "Dolo 650", "generic_name": "Paracetamol"},
                "confidence": {"score": 0.9, "level": "green", "can_confirm": True},
                "lookalike": {"is_flagged": False},
                "validation": {"dose_valid": True, "freq_valid": True, "duration_valid": True, "all_valid": True}
            }
        ]
    }
    save_prescription_record(rx_data, f"/static/uploads/{rx_id}.png")

    with patch.dict(os.environ, {"PHARMACIST_PIN": "9876"}):
        # 1. Without PIN -> 401 Unauthorized
        res_no_pin = client.post(f"/api/prescriptions/{rx_id}/lines/1/confirm", json={"confirmed_by": "Dr. Bob"})
        assert res_no_pin.status_code == 401

        # 2. With wrong PIN -> 401 Unauthorized
        res_wrong_pin = client.post(
            f"/api/prescriptions/{rx_id}/lines/1/confirm",
            headers={"X-Pharmacist-PIN": "0000"},
            json={"confirmed_by": "Dr. Bob"}
        )
        assert res_wrong_pin.status_code == 401

        # 3. With valid PIN -> 200 OK
        res_ok = client.post(
            f"/api/prescriptions/{rx_id}/lines/1/confirm",
            headers={"X-Pharmacist-PIN": "9876"},
            json={"confirmed_by": "Dr. Bob"}
        )
        assert res_ok.status_code == 200


def test_list_prescriptions_limit_query_validation():
    """Verify GET /api/prescriptions enforces Query(30, ge=1, le=100)."""
    client = TestClient(app)

    # Valid limits
    r1 = client.get("/api/prescriptions?limit=10")
    assert r1.status_code == 200

    r2 = client.get("/api/prescriptions?limit=100")
    assert r2.status_code == 200

    # Invalid limits: 0 (less than 1)
    r_low = client.get("/api/prescriptions?limit=0")
    assert r_low.status_code == 422

    # Invalid limits: 101 (greater than 100)
    r_high = client.get("/api/prescriptions?limit=101")
    assert r_high.status_code == 422


def test_truth_json_is_not_served():
    """Verify truth.json is not served via HTTP static files."""
    client = TestClient(app)

    # /static/testset/truth.json must return 404
    resp = client.get("/static/testset/truth.json")
    assert resp.status_code == 404

    # Direct path to testset root must also be 404
    resp2 = client.get("/static/truth.json")
    assert resp2.status_code == 404


def test_benchmark_invalid_run_on_service_failure(tmp_path):
    """Verify benchmark aborts and does NOT overwrite evaluation_results.json if OCR service fails."""
    # Mock pipeline returning an OCR service failure
    mock_line = MagicMock()
    mock_line.line_id = 1
    mock_line.original_ocr_trace = {
        "is_service_error": True,
        "service_error_detail": "429 RESOURCE_EXHAUSTED"
    }

    mock_res = MagicMock()
    mock_res.quality_check.passed = True
    mock_res.lines = [mock_line]

    results_file = tmp_path / "evaluation_results.json"
    results_file.write_text('{"dummy": "data"}', encoding="utf-8")

    with patch("scripts.evaluate_benchmark.MedMatchPipeline") as MockPipeline:
        inst = MockPipeline.return_value
        inst.process_prescription_image_sync.return_value = mock_res

        # Write dummy truth.json in tmp_path
        dummy_truth = {
            "prescriptions": [
                {
                    "prescription_id": "test_rx_1",
                    "filename": "rx_1.png",
                    "category": "sample",
                    "lines": [{"ground_truth": {"drug": "Amoxicillin"}}]
                }
            ]
        }
        (tmp_path / "truth.json").write_text(json.dumps(dummy_truth), encoding="utf-8")
        (tmp_path / "images").mkdir(exist_ok=True)

        result = run_benchmark(allow_demo_fallback=False, testset_dir=tmp_path)
        assert result.get("status") == "INVALID RUN"
        assert result.get("ocr_service_failures", 0) > 0
        # Original evaluation_results.json was NOT overwritten with new results
        assert results_file.read_text(encoding="utf-8") == '{"dummy": "data"}'
