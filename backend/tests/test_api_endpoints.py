import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

class TestApiEndpoints:
    def test_health_check(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"

    def test_sample_prescriptions_list(self, client):
        res = client.get("/api/sample-prescriptions")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 4
        assert any(d["id"] == "rx_001" for d in data)
        assert any(d["id"] == "rx_006" for d in data)

    def test_load_clean_prescription_scenario(self, client):
        res = client.post("/api/sample-prescriptions/rx_001/load")
        assert res.status_code == 200
        data = res.json()
        assert data["prescription_id"] == "rx_001"
        assert data["quality_check"]["passed"] is True
        assert len(data["lines"]) == 3
        # First line is Augmentin 625mg (can be confirmed, level is green or yellow due to Augmentan LASA warning)
        assert data["lines"][0]["selected_candidate"]["brand_name"] == "Augmentin"
        assert data["lines"][0]["confidence"]["can_confirm"] is True
        assert data["lines"][0]["confidence"]["level"] in ["green", "yellow"]

    def test_load_blurry_prescription_rejected(self, client):
        res = client.post("/api/sample-prescriptions/rx_019/load")
        assert res.status_code == 200
        data = res.json()
        assert data["quality_check"]["passed"] is False
        assert data["quality_check"]["is_blurry"] is True
        assert "blurry" in data["quality_check"]["message"].lower()
        assert len(data["lines"]) == 0

    def test_load_lookalike_prescription_warning(self, client):
        res = client.post("/api/sample-prescriptions/rx_006/load")
        assert res.status_code == 200
        data = res.json()
        assert data["quality_check"]["passed"] is True
        celebrex_line = data["lines"][0]
        assert celebrex_line["selected_candidate"]["brand_name"] == "Celebrex"
        assert celebrex_line["lookalike"]["is_flagged"] is True
        assert celebrex_line["lookalike"]["paired_drug"] == "Celexa"

    def test_server_enforces_red_line_confirmation_rule(self, client):
        # Load rx_027 (has unreadable line)
        res = client.post("/api/sample-prescriptions/rx_027/load")
        assert res.status_code == 200
        data = res.json()
        
        # Line 1 is unreadable (RED)
        unreadable_line = data["lines"][0]
        assert unreadable_line["confidence"]["level"] == "red"
        
        # Attempt to confirm RED line without correction -> must return 400!
        bad_confirm = client.post(f"/api/prescriptions/rx_027/lines/1/confirm")
        assert bad_confirm.status_code == 400
        assert "RED" in bad_confirm.json()["detail"]

        # Now submit explicit pharmacist correction -> must succeed and record audit!
        good_confirm = client.post(
            f"/api/prescriptions/rx_027/lines/1/confirm",
            json={
                "final_drug": "Augmentin",
                "final_dose": "625mg",
                "final_freq": "1-0-1",
                "final_duration": "5d",
                "corrected_by": "Dr. Pharmacist",
                "notes": "Verified against handwritten doctor notes"
            }
        )
        assert good_confirm.status_code == 200
        assert good_confirm.json()["status"] == "success"

        # Check DB audit history
        fetch_res = client.get("/api/prescriptions/rx_027")
        assert fetch_res.status_code == 200
        rx_updated = fetch_res.json()
        assert rx_updated["lines"][0]["status"] == "corrected"
        assert rx_updated["lines"][0]["final_drug"] == "Augmentin"
        assert len(rx_updated["corrections"]) >= 1

    def test_drug_search_autocomplete(self, client):
        res = client.get("/api/drugs/search?q=cele")
        assert res.status_code == 200
        results = res.json()
        assert len(results) > 0
        names = [r["brand_name"] for r in results]
        assert "Celebrex" in names or "Celexa" in names

    def test_benchmark_metrics_endpoint(self, client):
        res = client.get("/api/benchmark/metrics")
        assert res.status_code == 200
        data = res.json()
        pipeline_metrics = data.get("pipeline_metrics", data)
        assert "top_1_drug_accuracy_percent" in pipeline_metrics
        assert isinstance(pipeline_metrics["top_1_drug_accuracy_percent"], (int, float))
