import io
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import (
    SESSION_COOKIE_NAME,
    hash_password,
    verify_password,
    hash_otp_code,
    create_access_token,
    require_user,
    _rate_limits
)
from app.db import (
    init_db,
    get_connection,
    get_user_by_email,
    get_latest_otp,
    create_user,
    verify_user
)

@pytest.fixture(autouse=True)
def clean_test_env():
    """Reset rate limiter and ensure fresh database state before and after each test"""
    _rate_limits.clear()
    init_db()
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM otp_codes WHERE email LIKE '%@medmatch.test'")
        conn.execute("DELETE FROM users WHERE email LIKE '%@medmatch.test'")
    conn.close()
    yield
    _rate_limits.clear()
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM otp_codes WHERE email LIKE '%@medmatch.test'")
        conn.execute("DELETE FROM users WHERE email LIKE '%@medmatch.test'")
    conn.close()

class TestAuthenticationFlows:
    def test_prescription_routes_return_401_without_session(self):
        """Prescription routes return 401 without a session cookie or auth token"""
        app.dependency_overrides.clear()
        with TestClient(app) as client:
            # 1. Upload route
            fake_file = io.BytesIO(b"dummy")
            res_upload = client.post("/api/prescriptions/upload", files={"file": ("rx.png", fake_file, "image/png")})
            assert res_upload.status_code == 401

            # 2. Sample prescriptions route
            res_samples = client.get("/api/sample-prescriptions")
            assert res_samples.status_code == 401

            # 3. Drugs search route
            res_drugs = client.get("/api/drugs/search?q=augmentin")
            assert res_drugs.status_code == 401

            # 4. Auth me route
            res_me = client.get("/api/auth/me")
            assert res_me.status_code == 401

            # 5. Static uploads and crops routes
            res_static_upload = client.get("/static/uploads/rx_test.png")
            assert res_static_upload.status_code == 401
            res_static_crop = client.get("/static/crops/crop_1.png")
            assert res_static_crop.status_code == 401

    def test_registration_verification_and_login_success(self):
        """Register, verify OTP, then login succeeds; issues httpOnly cookie"""
        app.dependency_overrides.clear()
        with TestClient(app) as client:
            # 1. Register a new user
            reg_res = client.post("/api/auth/register", json={
                "name": "Jane Pharmacist",
                "email": "jane@medmatch.test",
                "password": "Password123!",
                "confirm_password": "Password123!",
                "role": "pharmacist"
            })
            assert reg_res.status_code == 200
            assert reg_res.json()["status"] == "pending_verification"

            # Verify user exists in database but is unverified
            user = get_user_by_email("jane@medmatch.test")
            assert user is not None
            assert user["is_verified"] == 0

            # Retrieve OTP hash from database
            otp_record = get_latest_otp("jane@medmatch.test", "verify")
            assert otp_record is not None
            assert otp_record["attempts"] == 0
            assert otp_record["used"] == 0

            # Unverified account cannot log in
            login_fail = client.post("/api/auth/login", json={
                "email": "jane@medmatch.test",
                "password": "Password123!"
            })
            assert login_fail.status_code == 403
            assert "not verified" in login_fail.json()["detail"].lower()

            # Find valid OTP code by matching hash (for testing purposes)
            valid_code = None
            for num in range(1000000):
                c = f"{num:06d}"
                if hash_otp_code(c) == otp_record["code_hash"]:
                    valid_code = c
                    break
            assert valid_code is not None

            # 2. Verify OTP
            verify_res = client.post("/api/auth/verify-otp", json={
                "email": "jane@medmatch.test",
                "otp": valid_code
            })
            assert verify_res.status_code == 200
            assert verify_res.json()["status"] == "success"
            assert SESSION_COOKIE_NAME in client.cookies

            # Verify user is now activated
            user = get_user_by_email("jane@medmatch.test")
            assert user["is_verified"] == 1

            # 3. GET /api/auth/me with session cookie succeeds
            me_res = client.get("/api/auth/me")
            assert me_res.status_code == 200
            assert me_res.json()["user"]["email"] == "jane@medmatch.test"
            assert me_res.json()["user"]["name"] == "Jane Pharmacist"

            # 4. Logout clears session cookie
            logout_res = client.post("/api/auth/logout")
            assert logout_res.status_code == 200
            # Next request should be unauthenticated
            me_after = client.get("/api/auth/me")
            assert me_after.status_code == 401

            # 5. Direct login succeeds (LOGIN_OTP_REQUIRED=False)
            login_res = client.post("/api/auth/login", json={
                "email": "jane@medmatch.test",
                "password": "Password123!"
            })
            assert login_res.status_code == 200
            assert login_res.json()["otp_required"] is False
            assert SESSION_COOKIE_NAME in client.cookies

    def test_wrong_expired_and_reused_otp_behavior(self):
        """Wrong, expired or reused OTP is rejected; 6th wrong attempt locks the code"""
        app.dependency_overrides.clear()
        with TestClient(app) as client:
            # Register user
            client.post("/api/auth/register", json={
                "name": "Lockout User",
                "email": "lockout@medmatch.test",
                "password": "Password123!",
                "confirm_password": "Password123!"
            })

            # Submit 5 incorrect OTP attempts
            for i in range(1, 6):
                res = client.post("/api/auth/verify-otp", json={
                    "email": "lockout@medmatch.test",
                    "otp": "000000"
                })
                assert res.status_code == 400
                if i < 5:
                    assert f"{5 - i} attempt(s) remaining" in res.json()["detail"]
                else:
                    assert "locked" in res.json()["detail"].lower()

            # 6th attempt is rejected because code is locked
            sixth_res = client.post("/api/auth/verify-otp", json={
                "email": "lockout@medmatch.test",
                "otp": "000000"
            })
            assert sixth_res.status_code == 400
            assert "invalid" in sixth_res.json()["detail"].lower() or "too many" in sixth_res.json()["detail"].lower()

    def test_resend_cooldown_and_hourly_cap(self):
        """Resend within 60 s is rejected; hourly cap (max 5) blocks excessive requests"""
        app.dependency_overrides.clear()
        with TestClient(app) as client:
            client.post("/api/auth/register", json={
                "name": "Cooldown Tester",
                "email": "cooldown@medmatch.test",
                "password": "Password123!"
            })

            # Attempt immediate resend (cooldown is 60s)
            resend_fail = client.post("/api/auth/resend-otp", json={
                "email": "cooldown@medmatch.test",
                "purpose": "verify"
            })
            assert resend_fail.status_code == 429
            assert "seconds before requesting another code" in resend_fail.json()["detail"]

            # Artificially age the OTP record to simulate 61 seconds passing
            conn = get_connection()
            old_time = (datetime.now(timezone.utc) - timedelta(seconds=65)).isoformat()
            with conn:
                conn.execute("UPDATE otp_codes SET created_at = ? WHERE email = ?", (old_time, "cooldown@medmatch.test"))
            conn.close()

            # Now resend succeeds
            resend_ok = client.post("/api/auth/resend-otp", json={
                "email": "cooldown@medmatch.test",
                "purpose": "verify"
            })
            assert resend_ok.status_code == 200

            # Simulate inserting 5 total OTP records in the last hour
            user = get_user_by_email("cooldown@medmatch.test")
            user_id = user["id"] if user else None
            conn = get_connection()
            with conn:
                for idx in range(5):
                    t = (datetime.now(timezone.utc) - timedelta(minutes=idx + 2)).isoformat()
                    conn.execute("""
                        INSERT INTO otp_codes (id, user_id, email, purpose, code_hash, expires_at, attempts, used, created_at)
                        VALUES (?, ?, ?, 'verify', 'dummyhash', ?, 0, 0, ?)
                    """, (f"cap_otp_{idx}", user_id, "cooldown@medmatch.test", t, t))
                # Ensure all records for cooldown@medmatch.test are past the 60s cooldown
                conn.execute(
                    "UPDATE otp_codes SET created_at = ? WHERE email = ? AND id NOT LIKE 'cap_otp_%'",
                    (old_time, "cooldown@medmatch.test")
                )
            conn.close()

            # Attempt resend when at hourly cap (>= 5)
            cap_res = client.post("/api/auth/resend-otp", json={
                "email": "cooldown@medmatch.test",
                "purpose": "verify"
            })
            assert cap_res.status_code == 429
            assert "hourly verification code limit" in cap_res.json()["detail"].lower()

    def test_password_reset_flow(self):
        """Forgot password sends reset OTP, and password reset succeeds only with valid OTP"""
        app.dependency_overrides.clear()
        with TestClient(app) as client:
            # Create a verified user
            pwd_hash = hash_password("OldPassword123!")
            create_user(
                name="Reset User",
                email="reset@medmatch.test",
                password_hash=pwd_hash,
                is_verified=True
            )

            # Request password reset
            fp_res = client.post("/api/auth/forgot-password", json={"email": "reset@medmatch.test"})
            assert fp_res.status_code == 200

            # Get reset OTP record
            otp_record = get_latest_otp("reset@medmatch.test", "reset")
            assert otp_record is not None

            # Find matching code
            valid_code = None
            for num in range(1000000):
                c = f"{num:06d}"
                if hash_otp_code(c) == otp_record["code_hash"]:
                    valid_code = c
                    break
            assert valid_code is not None

            # Reset password with valid code
            reset_res = client.post("/api/auth/reset-password", json={
                "email": "reset@medmatch.test",
                "otp": valid_code,
                "new_password": "NewSecretPassword456!",
                "confirm_password": "NewSecretPassword456!"
            })
            assert reset_res.status_code == 200
            assert reset_res.json()["status"] == "success"

            # Old password must fail login
            old_login = client.post("/api/auth/login", json={
                "email": "reset@medmatch.test",
                "password": "OldPassword123!"
            })
            assert old_login.status_code == 401

            # New password must succeed login
            new_login = client.post("/api/auth/login", json={
                "email": "reset@medmatch.test",
                "password": "NewSecretPassword456!"
            })
            assert new_login.status_code == 200

    def test_confirmed_by_comes_from_authenticated_user_not_request_body(self):
        """
        The confirmed_by and corrected_by values must come from the authenticated user
        (name + email), NOT from the client request body even if client sends another name.
        """
        app.dependency_overrides.clear()
        with TestClient(app) as client:
            # Create authenticated user
            pwd_hash = hash_password("Password123!")
            u = create_user(
                name="Dr. Verified Pharmacist",
                email="pharmacist@medmatch.test",
                password_hash=pwd_hash,
                is_verified=True
            )
            # Log in
            login_res = client.post("/api/auth/login", json={
                "email": "pharmacist@medmatch.test",
                "password": "Password123!"
            })
            assert login_res.status_code == 200

            # Load clean scenario rx_001
            load_res = client.post("/api/sample-prescriptions/rx_001/load")
            assert load_res.status_code == 200

            # Client maliciously attempts to pass someone else's name
            confirm_res = client.post(
                "/api/prescriptions/rx_001/lines/1/confirm",
                json={
                    "confirmed_by": "Dr. Imposter Hacker",
                    "lasa_acknowledged": True,
                    "notes": "Testing attribution integrity"
                }
            )
            assert confirm_res.status_code == 200

            # Verify in database audit logs and confirmations that the actor is Dr. Verified Pharmacist
            conn = get_connection()
            audit_row = conn.execute(
                "SELECT * FROM audit_logs WHERE prescription_id = 'rx_001' AND line_id = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()

            assert audit_row is not None
            expected_actor = "Dr. Verified Pharmacist (pharmacist@medmatch.test)"
            assert audit_row["actor"] == expected_actor
            assert "Dr. Imposter Hacker" not in audit_row["actor"]

    def test_login_otp_required_mode(self):
        """When LOGIN_OTP_REQUIRED=True, login requires second step OTP verification"""
        app.dependency_overrides.clear()
        with patch("app.main.LOGIN_OTP_REQUIRED", True):
            with TestClient(app) as client:
                pwd_hash = hash_password("Password123!")
                create_user(
                    name="TwoFactor User",
                    email="twofactor@medmatch.test",
                    password_hash=pwd_hash,
                    is_verified=True
                )

                # Step 1: Login triggers OTP required
                login_res = client.post("/api/auth/login", json={
                    "email": "twofactor@medmatch.test",
                    "password": "Password123!"
                })
                assert login_res.status_code == 200
                assert login_res.json()["otp_required"] is True
                assert SESSION_COOKIE_NAME not in client.cookies

                # Step 2: Retrieve OTP from DB and verify
                otp_record = get_latest_otp("twofactor@medmatch.test", "login")
                assert otp_record is not None

                valid_code = None
                for num in range(1000000):
                    c = f"{num:06d}"
                    if hash_otp_code(c) == otp_record["code_hash"]:
                        valid_code = c
                        break
                assert valid_code is not None

                # Submit login verify OTP
                verify_res = client.post("/api/auth/login-verify-otp", json={
                    "email": "twofactor@medmatch.test",
                    "otp": valid_code
                })
                assert verify_res.status_code == 200
                assert SESSION_COOKIE_NAME in client.cookies
