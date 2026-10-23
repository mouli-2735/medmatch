import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, get_connection

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

class TestServerConfirmationSafety:
    def test_direct_confirmation_of_red_line_blocked(self, client):
        # rx_027 has an illegible scribbled line (RED)
        load_res = client.post("/api/sample-prescriptions/rx_027/load")
        assert load_res.status_code == 200
        rx_data = load_res.json()
        assert rx_data["lines"][0]["confidence"]["level"] == "red"

        # Direct confirmation without correction payload
        res = client.post("/api/prescriptions/rx_027/lines/1/confirm")
        assert res.status_code == 400
        assert "RED" in res.json()["detail"]

    def test_lasa_line_requires_explicit_acknowledgment(self, client):
        # rx_006 has Celebrex (LASA flagged against Celexa)
        load_res = client.post("/api/sample-prescriptions/rx_006/load")
        assert load_res.status_code == 200
        rx_data = load_res.json()
        assert rx_data["lines"][0]["lookalike"]["is_flagged"] is True

        # Attempt confirm without acknowledging LASA
        res = client.post(
            "/api/prescriptions/rx_006/lines/1/confirm",
            json={"confirmed_by": "pharmacist", "lasa_acknowledged": False}
        )
        assert res.status_code == 400
        assert "LASA" in res.json()["detail"] or "ISMP" in res.json()["detail"]

        # Now confirm with explicit acknowledgment
        ack_res = client.post(
            "/api/prescriptions/rx_006/lines/1/confirm",
            json={"confirmed_by": "Dr. Sarah", "lasa_acknowledged": True, "notes": "Verified orthography"}
        )
        assert ack_res.status_code == 200
        assert ack_res.json()["status"] == "success"

    def test_batch_confirmation_blocks_when_unresolved_hazards_exist(self, client):
        # rx_027 contains an unreadable RED line
        client.post("/api/sample-prescriptions/rx_027/load")

        batch_res = client.post("/api/prescriptions/rx_027/confirm-all")
        assert batch_res.status_code == 400
        assert "Batch confirmation blocked" in batch_res.json()["detail"]

    def test_parent_prescription_status_recalculation(self, client):
        # Load clean rx_001
        load_res = client.post("/api/sample-prescriptions/rx_001/load")
        assert load_res.status_code == 200
        rx_id = "rx_001"

        # Initially status is pending
        rx = client.get(f"/api/prescriptions/{rx_id}").json()
        assert rx["status"] == "pending"

        # Confirm line 1
        client.post(f"/api/prescriptions/{rx_id}/lines/1/confirm", json={"lasa_acknowledged": True})
        rx_after_1 = client.get(f"/api/prescriptions/{rx_id}").json()
        assert rx_after_1["status"] == "in_review"

        # Confirm lines 2 and 3
        client.post(f"/api/prescriptions/{rx_id}/lines/2/confirm", json={"lasa_acknowledged": True})
        client.post(f"/api/prescriptions/{rx_id}/lines/3/confirm", json={"lasa_acknowledged": True})
        
        # When all lines confirmed, parent status transitions to 'confirmed'
        rx_all = client.get(f"/api/prescriptions/{rx_id}").json()
        assert rx_all["status"] == "confirmed"

    def test_corrected_line_persists_audit_entry(self, client):
        client.post("/api/sample-prescriptions/rx_027/load")
        
        correct_res = client.post(
            "/api/prescriptions/rx_027/lines/1/confirm",
            json={
                "final_drug": "Amoxicillin",
                "final_dose": "500mg",
                "final_freq": "TDS",
                "final_duration": "7d",
                "corrected_by": "Senior Pharmacist John",
                "notes": "Illegible ink clarified by phone call with prescriber"
            }
        )
        assert correct_res.status_code == 200
        assert correct_res.json()["action"] == "corrected"

        # Verify DB records
        rx = client.get("/api/prescriptions/rx_027").json()
        assert rx["lines"][0]["status"] == "corrected"
        assert rx["lines"][0]["final_drug"] == "Amoxicillin"
        assert any(c["final_value"].get("final_drug") == "Amoxicillin" for c in rx["corrections"])
