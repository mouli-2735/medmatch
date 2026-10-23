import pytest
import io
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, get_connection

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

class TestUploadSecurityAndIntegrity:
    def test_disallowed_file_extension_rejected(self, client):
        fake_file = io.BytesIO(b"malicious script")
        res = client.post(
            "/api/prescriptions/upload",
            files={"file": ("malware.exe", fake_file, "application/x-msdownload")}
        )
        assert res.status_code == 400
        assert "Unsupported file format" in res.json()["detail"]

    def test_corrupt_or_unreadable_image_rejected(self, client):
        corrupt_data = io.BytesIO(b"not a valid png or jpeg header")
        res = client.post(
            "/api/prescriptions/upload",
            files={"file": ("corrupt.png", corrupt_data, "image/png")}
        )
        assert res.status_code == 400
        assert "corrupt" in res.json()["detail"].lower()

    def test_file_size_limit_enforced(self, client):
        # 11MB file (exceeds 10MB limit)
        oversized_data = io.BytesIO(b"0" * (11 * 1024 * 1024))
        res = client.post(
            "/api/prescriptions/upload",
            files={"file": ("huge.jpg", oversized_data, "image/jpeg")}
        )
        assert res.status_code == 413
        assert "exceeds" in res.json()["detail"].lower()

class TestDatabaseForeignKeysAndIntegrity:
    def test_foreign_keys_pragma_enabled(self):
        conn = get_connection()
        cur = conn.execute("PRAGMA foreign_keys;")
        val = cur.fetchone()[0]
        conn.close()
        assert val == 1, "SQLite foreign keys must be active (PRAGMA foreign_keys = 1)"

    def test_cascading_delete_or_fk_constraint(self):
        conn = get_connection()
        import sqlite3
        with conn:
            # Attempt to insert an orphaned line referencing non-existent prescription
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""
                    INSERT INTO lines (id, prescription_id, line_id, crop_path, status)
                    VALUES (?, ?, ?, ?, ?)
                """, ("orphaned_line_999", "non_existent_rx_999", 1, "/crops/none.png", "pending"))
        conn.close()
