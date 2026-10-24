import hashlib
import hmac
import logging
import secrets
import smtplib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any, Tuple
import asyncio

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Request, Header, HTTPException, Depends

from app.config import (
    JWT_SECRET,
    LOGIN_OTP_REQUIRED,
    DEV_MODE,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_APP_PASSWORD,
    SMTP_FROM
)
from app.db import (
    get_user_by_id,
    get_user_by_email,
    get_latest_otp,
    increment_otp_attempts,
    mark_otp_used,
    count_otps_in_last_hour,
    seconds_since_last_otp,
    create_otp
)

logger = logging.getLogger("medmatch.auth")

# Password hasher via argon2-cffi
_ph = PasswordHasher()

SESSION_COOKIE_NAME = "medmatch_session"
JWT_EXPIRATION_MINUTES = 60
OTP_EXPIRATION_MINUTES = 5
MAX_OTP_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_HOURLY_OTPS = 5

def hash_password(password: str) -> str:
    """Hashes a password with Argon2id"""
    return _ph.hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    """Verifies a plain password against an Argon2 hash"""
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, Exception):
        return False

def generate_otp_code() -> str:
    """Generates a secure 6-digit numeric OTP"""
    return "".join(secrets.choice("0123456789") for _ in range(6))

def hash_otp_code(otp_code: str) -> str:
    """Computes HMAC-SHA256 of the OTP code using JWT_SECRET"""
    return hmac.new(JWT_SECRET.encode(), otp_code.strip().encode(), hashlib.sha256).hexdigest()

def verify_otp_hash(otp_code: str, expected_hash: str) -> bool:
    """Constant-time comparison of OTP HMAC hash"""
    computed = hash_otp_code(otp_code)
    return hmac.compare_digest(computed, expected_hash)

def create_access_token(user_id: str, email: str, role: str) -> str:
    """Issues a short-lived JWT valid for 60 minutes"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email.lower().strip(),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a JWT access token"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

# ==========================================
# In-Memory Rate Limiter (Sliding Window)
# ==========================================
_rate_limits: Dict[str, list] = defaultdict(list)

def check_and_record_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    """
    Returns True if request is allowed, False if rate limit is exceeded.
    Uses sliding window tracking.
    """
    now = datetime.now(timezone.utc).timestamp()
    timestamps = _rate_limits[key]
    # Prune old timestamps
    cutoff = now - window_seconds
    _rate_limits[key] = [ts for ts in timestamps if ts > cutoff]
    
    if len(_rate_limits[key]) >= max_attempts:
        return False
    _rate_limits[key].append(now)
    return True

# ==========================================
# Email Transmission (STARTTLS)
# ==========================================
def send_otp_email_sync(email: str, otp_code: str, purpose: str):
    """
    Synchronously transmits OTP email over SMTP (STARTTLS, port 587).
    Logs to console if DEV_MODE is enabled. Never exposes OTP in API responses.
    """
    purpose_subject = {
        "verify": "Verify Your MedMatch Rx Account",
        "login": "Your MedMatch Rx Login Verification Code",
        "reset": "MedMatch Rx Password Reset Code"
    }.get(purpose, "MedMatch Rx Verification Code")

    if DEV_MODE:
        logger.info(f"[DEV_MODE] ========================================")
        logger.info(f"[DEV_MODE] Destination: {email}")
        logger.info(f"[DEV_MODE] Purpose: {purpose}")
        logger.info(f"[DEV_MODE] 6-Digit OTP: {otp_code}")
        logger.info(f"[DEV_MODE] ========================================")

    # Check SMTP configuration
    if not SMTP_HOST or not SMTP_USER:
        if DEV_MODE:
            # In local dev mode without an active SMTP server, console log is sufficient
            return
        raise RuntimeError("SMTP email service is not configured. Please set SMTP_HOST and SMTP_USER.")

    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = email
    msg["Subject"] = purpose_subject

    body_text = (
        f"Hello,\n\n"
        f"Your verification code for MedMatch Rx ({purpose}) is:\n\n"
        f"  {otp_code}\n\n"
        f"This code will expire in {OTP_EXPIRATION_MINUTES} minutes and can only be used once.\n"
        f"If you did not request this code, please ignore this email.\n\n"
        f"Regards,\n"
        f"MedMatch Rx Security Team\n"
    )
    msg.attach(MIMEText(body_text, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_APP_PASSWORD)
        server.send_message(msg)

async def send_otp_email_async(email: str, otp_code: str, purpose: str):
    """Executes email sending in a background thread to prevent blocking event loop"""
    await asyncio.to_thread(send_otp_email_sync, email, otp_code, purpose)

# ==========================================
# OTP Validation & Issue Logic
# ==========================================
def issue_and_send_otp(user_id: Optional[str], email: str, purpose: str) -> Tuple[bool, str]:
    """
    Checks rate limits, creates a hashed OTP in DB, and dispatches via email thread.
    Returns (success, message).
    """
    norm_email = email.lower().strip()
    
    # 1. Check Resend Cooldown (60 seconds)
    sec_since = seconds_since_last_otp(norm_email, purpose)
    if sec_since is not None and sec_since < RESEND_COOLDOWN_SECONDS:
        remaining = int(RESEND_COOLDOWN_SECONDS - sec_since)
        return False, f"Please wait {remaining} seconds before requesting another code."

    # 2. Check Hourly Limit (max 5 per hour per email)
    hourly_count = count_otps_in_last_hour(norm_email)
    if hourly_count >= MAX_HOURLY_OTPS:
        return False, "Maximum hourly verification code limit reached. Please try again later."

    # 3. Generate OTP & Store HMAC
    otp_code = generate_otp_code()
    code_hash = hash_otp_code(otp_code)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRATION_MINUTES)).isoformat()
    
    create_otp(user_id, norm_email, purpose, code_hash, expires_at)
    
    # 4. Dispatch Email in background
    try:
        # In synchronous context or threaded context
        asyncio.create_task(send_otp_email_async(norm_email, otp_code, purpose))
    except RuntimeError:
        # No running event loop (e.g. some sync test scenarios)
        import threading
        threading.Thread(target=send_otp_email_sync, args=(norm_email, otp_code, purpose), daemon=True).start()

    return True, "Verification code sent to your email."

def verify_submitted_otp(email: str, submitted_code: str, purpose: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Verifies submitted OTP against rules:
    - Must exist
    - Single use (used == 0)
    - Not expired (expires_at > now)
    - Max 5 wrong attempts before invalidation
    - Hash must match
    Returns (success, error_message_if_any, otp_record)
    """
    norm_email = email.lower().strip()
    clean_code = submitted_code.strip()
    
    record = get_latest_otp(norm_email, purpose)
    if not record:
        return False, "Invalid or expired verification code.", None

    if record["used"]:
        return False, "This verification code has already been used.", record

    if record["attempts"] >= MAX_OTP_ATTEMPTS:
        return False, "Too many incorrect attempts. This code is now invalid. Please request a new one.", record

    # Check expiration
    now = datetime.now(timezone.utc)
    try:
        exp_str = record["expires_at"]
        if "T" in exp_str:
            exp_dt = datetime.fromisoformat(exp_str)
        else:
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if now > exp_dt:
            return False, "Verification code has expired. Please request a new one.", record
    except Exception:
        return False, "Verification code timestamp is invalid.", record

    # Compare hash
    if not verify_otp_hash(clean_code, record["code_hash"]):
        new_attempts = increment_otp_attempts(record["id"])
        if new_attempts >= MAX_OTP_ATTEMPTS:
            return False, "Incorrect verification code. Maximum attempts reached. Code is now locked.", record
        remaining = MAX_OTP_ATTEMPTS - new_attempts
        return False, f"Incorrect verification code. {remaining} attempt(s) remaining.", record

    # Mark as used
    mark_otp_used(record["id"])
    return True, "Code verified successfully.", record

# ==========================================
# FastAPI Current User Dependencies
# ==========================================
async def get_current_user_optional(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Optional[Dict[str, Any]]:
    """Extracts authenticated user from session cookie or Bearer token"""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    
    if not token:
        return None
        
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
        
    user = get_user_by_id(payload["sub"])
    if not user or not user["is_verified"]:
        return None
        
    return user

async def require_user(
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
) -> Dict[str, Any]:
    """Dependency that enforces active authenticated user"""
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in."
        )
    return user
