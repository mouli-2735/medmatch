import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from app.config import DB_PATH

def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with foreign key enforcement enabled"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes SQLite schema, migrations, and indexes"""
    conn = get_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prescriptions (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                image_path TEXT NOT NULL,
                quality_passed BOOLEAN NOT NULL,
                blur_score REAL,
                mean_brightness REAL,
                glare_share REAL,
                quality_message TEXT,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lines (
                id TEXT PRIMARY KEY,
                prescription_id TEXT NOT NULL,
                line_id INTEGER NOT NULL,
                crop_path TEXT NOT NULL,
                raw_guesses TEXT,
                dose_raw TEXT,
                freq_raw TEXT,
                duration_raw TEXT,
                original_ocr_trace TEXT,
                suggested_drug TEXT,
                suggested_generic TEXT,
                top_candidates TEXT,
                rxnorm_cui TEXT,
                rxnorm_name TEXT,
                rxnorm_status TEXT,
                rxnorm_data TEXT,
                confidence_score REAL,
                confidence_level TEXT,
                can_confirm BOOLEAN,
                lookalike_flag BOOLEAN,
                lookalike_paired TEXT,
                lasa_acknowledged BOOLEAN DEFAULT 0,
                validation_flags TEXT,
                field_confidence TEXT,
                status TEXT NOT NULL,
                final_drug TEXT,
                final_dose TEXT,
                final_freq TEXT,
                final_duration TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prescription_id) REFERENCES prescriptions (id) ON DELETE CASCADE
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prescription_id TEXT NOT NULL,
                line_id INTEGER NOT NULL,
                original_suggestion TEXT NOT NULL,
                final_value TEXT NOT NULL,
                corrected_by TEXT DEFAULT 'pharmacist',
                notes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prescription_id) REFERENCES prescriptions (id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prescription_id TEXT NOT NULL,
                line_id INTEGER,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prescription_id) REFERENCES prescriptions (id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ocr_cache (
                cache_key TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'pharmacist',
                is_verified BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                email TEXT NOT NULL,
                purpose TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                used BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # Schema migration checks for existing databases
        rx_table_info = conn.execute("PRAGMA table_info(prescriptions)").fetchall()
        rx_existing_cols = {col["name"] for col in rx_table_info}
        if "updated_at" not in rx_existing_cols:
            conn.execute("ALTER TABLE prescriptions ADD COLUMN updated_at TIMESTAMP")

        table_info = conn.execute("PRAGMA table_info(lines)").fetchall()
        existing_cols = {col["name"] for col in table_info}

        migrations = [
            ("original_ocr_trace", "TEXT"),
            ("rxnorm_cui", "TEXT"),
            ("rxnorm_name", "TEXT"),
            ("rxnorm_status", "TEXT"),
            ("rxnorm_data", "TEXT"),
            ("lasa_acknowledged", "BOOLEAN DEFAULT 0"),
            ("field_confidence", "TEXT")
        ]
        for col_name, col_type in migrations:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE lines ADD COLUMN {col_name} {col_type}")

        # Indexes for query performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lines_prescription_id ON lines(prescription_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_prescription_id ON corrections(prescription_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_prescription_id ON audit_logs(prescription_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prescriptions_status ON prescriptions(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ocr_cache_key ON ocr_cache(cache_key);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_otp_email_purpose ON otp_codes(email, purpose);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_otp_expires ON otp_codes(expires_at);")

    conn.close()

def get_cached_ocr(cache_key: str) -> Optional[Dict[str, Any]]:
    """Retrieves cached Vision AI response by hash key"""
    conn = get_connection()
    row = conn.execute("SELECT response_json FROM ocr_cache WHERE cache_key = ?", (cache_key,)).fetchone()
    conn.close()
    if row and row["response_json"]:
        try:
            return json.loads(row["response_json"])
        except Exception:
            return None
    return None

def set_cached_ocr(cache_key: str, model: str, data: Dict[str, Any]):
    """Stores Vision AI response in SQLite cache"""
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO ocr_cache (cache_key, model, response_json, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (cache_key, model, json.dumps(data)))
    conn.close()

def recalculate_prescription_status(conn: sqlite3.Connection, prescription_id: str) -> str:
    """
    Recalculates parent prescription status based on all line states:
    - 'rejected' if image quality check failed.
    - 'confirmed' if EVERY line has status 'confirmed'.
    - 'in_review' if some lines are confirmed/corrected or currently under pharmacist review.
    - 'pending' if all lines are pending.
    """
    rx_row = conn.execute("SELECT quality_passed, status FROM prescriptions WHERE id = ?", (prescription_id,)).fetchone()
    if not rx_row:
        return "pending"
    if not rx_row["quality_passed"]:
        return "rejected"

    lines = conn.execute("SELECT status FROM lines WHERE prescription_id = ?", (prescription_id,)).fetchall()
    if not lines:
        new_status = "pending"
    else:
        statuses = [l["status"] for l in lines]
        if all(s == "confirmed" for s in statuses):
            new_status = "confirmed"
        elif any(s in ["confirmed", "corrected", "reviewed"] for s in statuses):
            new_status = "in_review"
        else:
            new_status = "pending"

    conn.execute(
        "UPDATE prescriptions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_status, prescription_id)
    )
    return new_status

def record_audit_event(conn: sqlite3.Connection, prescription_id: str, line_id: Optional[int], action: str, actor: str, details: str):
    """Inserts a structured entry into the clinical audit trail"""
    conn.execute("""
        INSERT INTO audit_logs (prescription_id, line_id, action, actor, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        prescription_id,
        line_id,
        action,
        actor,
        details,
        datetime.now(timezone.utc).isoformat()
    ))

def save_prescription_record(prescription_data: Dict[str, Any], image_rel_path: str):
    """Persists newly uploaded and segmented prescription into SQLite transactionally"""
    conn = get_connection()
    pid = prescription_data["prescription_id"]
    qc = prescription_data["quality_check"]
    initial_status = "pending" if qc["passed"] else "rejected"
    
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO prescriptions 
            (id, filename, image_path, quality_passed, blur_score, mean_brightness, glare_share, quality_message, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pid,
            prescription_data["original_filename"],
            image_rel_path,
            qc["passed"],
            qc["blur_score"],
            qc["mean_brightness"],
            qc["glare_share"],
            qc["message"],
            initial_status,
            prescription_data.get("created_at", datetime.now(timezone.utc).isoformat()),
            datetime.now(timezone.utc).isoformat()
        ))
        
        # Save lines
        for line in prescription_data.get("lines", []):
            line_pk = f"{pid}_{line['line_id']}"
            sel = line.get("selected_candidate") or {}
            conf = line.get("confidence") or {}
            lk = line.get("lookalike") or {}
            val = line.get("validation") or {}
            rxn = line.get("rxnorm") or {}
            
            conn.execute("""
                INSERT OR REPLACE INTO lines
                (id, prescription_id, line_id, crop_path, raw_guesses, dose_raw, freq_raw, duration_raw,
                 original_ocr_trace, suggested_drug, suggested_generic, top_candidates,
                 rxnorm_cui, rxnorm_name, rxnorm_status, rxnorm_data,
                 confidence_score, confidence_level, can_confirm, lookalike_flag, lookalike_paired,
                 lasa_acknowledged, validation_flags, field_confidence, status,
                 final_drug, final_dose, final_freq, final_duration, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                line_pk,
                pid,
                line["line_id"],
                line["crop"],
                json.dumps(line.get("guesses", [])),
                line.get("dose_raw", ""),
                line.get("freq_raw", ""),
                line.get("duration_raw", ""),
                json.dumps(line.get("original_ocr_trace", {})),
                sel.get("brand_name", "unreadable"),
                sel.get("generic_name", ""),
                json.dumps(line.get("top_candidates", [])),
                rxn.get("rxcui"),
                rxn.get("display_name"),
                rxn.get("status"),
                json.dumps(rxn),
                conf.get("score", 0.0),
                conf.get("level", "red"),
                conf.get("can_confirm", False),
                lk.get("is_flagged", False),
                lk.get("paired_drug", ""),
                line.get("lasa_acknowledged", False),
                json.dumps({
                    "dose_flag": val.get("dose_flag"),
                    "freq_flag": val.get("freq_flag"),
                    "dur_flag": val.get("duration_flag")
                }),
                json.dumps(conf.get("field_confidence", {})),
                line.get("status", "pending"),
                line.get("final_drug"),
                line.get("final_dose"),
                line.get("final_freq"),
                line.get("final_duration"),
                datetime.now(timezone.utc).isoformat()
            ))

        record_audit_event(
            conn,
            pid,
            None,
            "Ingestion",
            "System",
            f"Prescription ingested with {len(prescription_data.get('lines', []))} segmented lines. QC: {'Passed' if qc['passed'] else 'Failed'}."
        )

    conn.close()

def record_correction(
    prescription_id: str,
    line_id: int,
    original: str,
    final_val: Dict[str, Any],
    user: str = "pharmacist",
    notes: str = "",
    lasa_acknowledged: bool = False
):
    """
    Records a pharmacist correction and updates line and prescription statuses transactionally.
    """
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO corrections (prescription_id, line_id, original_suggestion, final_value, corrected_by, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            prescription_id,
            line_id,
            original,
            json.dumps(final_val),
            user,
            notes
        ))
        
        conn.execute("""
            UPDATE lines
            SET status = 'corrected',
                final_drug = ?,
                final_dose = ?,
                final_freq = ?,
                final_duration = ?,
                lasa_acknowledged = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE prescription_id = ? AND line_id = ?
        """, (
            final_val.get("final_drug"),
            final_val.get("final_dose"),
            final_val.get("final_freq"),
            final_val.get("final_duration"),
            1 if lasa_acknowledged else 0,
            prescription_id,
            line_id
        ))

        record_audit_event(
            conn,
            prescription_id,
            line_id,
            "Correction",
            user,
            f"Line {line_id} corrected from '{original}' to '{final_val.get('final_drug')} {final_val.get('final_dose')} {final_val.get('final_freq')} {final_val.get('final_duration')}'. Notes: {notes or 'None'}"
        )

        recalculate_prescription_status(conn, prescription_id)

    conn.close()

def record_confirmation(
    prescription_id: str,
    line_id: int,
    final_val: Dict[str, Any],
    confirmed_by: str = "pharmacist",
    notes: str = "",
    lasa_acknowledged: bool = False
):
    """
    Records a pharmacist line confirmation and recalculates parent status transactionally.
    """
    conn = get_connection()
    with conn:
        conn.execute("""
            UPDATE lines 
            SET status = 'confirmed',
                final_drug = ?,
                final_dose = ?,
                final_freq = ?,
                final_duration = ?,
                lasa_acknowledged = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE prescription_id = ? AND line_id = ?
        """, (
            final_val.get("final_drug"),
            final_val.get("final_dose"),
            final_val.get("final_freq"),
            final_val.get("final_duration"),
            1 if lasa_acknowledged else 0,
            prescription_id,
            line_id
        ))

        record_audit_event(
            conn,
            prescription_id,
            line_id,
            "Confirmation",
            confirmed_by,
            f"Line {line_id} confirmed ({final_val.get('final_drug')}). LASA acknowledged: {lasa_acknowledged}. Notes: {notes or 'None'}"
        )

        recalculate_prescription_status(conn, prescription_id)

    conn.close()

def batch_confirm_prescription(prescription_id: str, confirmed_by: str = "pharmacist") -> Tuple[bool, str, List[int]]:
    """
    Confirms all pending lines if safety rules are met.
    Blocks if ANY line is flagged RED or has an unacknowledged LASA warning!
    Returns: (success, message, affected_line_ids)
    """
    conn = get_connection()
    rx_cur = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (prescription_id,))
    rx_row = rx_cur.fetchone()
    if not rx_row:
        conn.close()
        return False, "Prescription not found.", []

    lines_cur = conn.execute("SELECT * FROM lines WHERE prescription_id = ? ORDER BY line_id ASC", (prescription_id,))
    lines = lines_cur.fetchall()
    
    blocked_lines = []
    for l in lines:
        if l["status"] == "confirmed":
            continue
        is_red = l["confidence_level"] == "red"
        is_lasa = bool(l["lookalike_flag"]) and not bool(l["lasa_acknowledged"])
        if is_red or is_lasa or not l["final_drug"] or l["final_drug"] == "unreadable":
            blocked_lines.append(l["line_id"])

    if blocked_lines:
        conn.close()
        return False, f"Batch confirmation blocked. Lines {blocked_lines} have unresolved safety alerts (Red confidence / LASA risk / Missing drug name) requiring individual pharmacist review.", blocked_lines

    with conn:
        conn.execute("""
            UPDATE lines
            SET status = 'confirmed',
                updated_at = CURRENT_TIMESTAMP
            WHERE prescription_id = ? AND status != 'confirmed'
        """, (prescription_id,))

        record_audit_event(
            conn,
            prescription_id,
            None,
            "Batch Approval",
            confirmed_by,
            f"Batch confirmation approved for prescription #{prescription_id} by {confirmed_by}."
        )

        recalculate_prescription_status(conn, prescription_id)

    conn.close()
    return True, f"All lines in prescription #{prescription_id} successfully confirmed.", [l["line_id"] for l in lines]

def get_prescription_by_id(pid: str) -> Optional[Dict[str, Any]]:
    """Fetches stored prescription details, lines, corrections, and audit trail"""
    conn = get_connection()
    rx_cur = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (pid,))
    rx_row = rx_cur.fetchone()
    if not rx_row:
        conn.close()
        return None
        
    lines_cur = conn.execute("SELECT * FROM lines WHERE prescription_id = ? ORDER BY line_id ASC", (pid,))
    line_rows = lines_cur.fetchall()
    
    corr_cur = conn.execute("SELECT * FROM corrections WHERE prescription_id = ? ORDER BY timestamp DESC", (pid,))
    corr_rows = corr_cur.fetchall()

    audit_cur = conn.execute("SELECT * FROM audit_logs WHERE prescription_id = ? ORDER BY id DESC", (pid,))
    audit_rows = audit_cur.fetchall()
    conn.close()
    
    lines = []
    all_can_confirm = True

    for lr in line_rows:
        val_flags = json.loads(lr["validation_flags"] or "{}")
        field_conf = json.loads(lr["field_confidence"] or "{}")
        rxnorm_info = json.loads(lr["rxnorm_data"] or "{}")
        can_conf = bool(lr["can_confirm"])
        
        if lr["status"] != "confirmed" and not can_conf:
            all_can_confirm = False

        lines.append({
            "line_id": lr["line_id"],
            "crop": lr["crop_path"],
            "guesses": json.loads(lr["raw_guesses"] or "[]"),
            "dose_raw": lr["dose_raw"],
            "freq_raw": lr["freq_raw"],
            "duration_raw": lr["duration_raw"],
            "original_ocr_trace": json.loads(lr["original_ocr_trace"] or "{}"),
            "top_candidates": json.loads(lr["top_candidates"] or "[]"),
            "selected_candidate": {
                "brand_name": lr["suggested_drug"],
                "generic_name": lr["suggested_generic"]
            },
            "rxnorm": rxnorm_info,
            "confidence": {
                "score": lr["confidence_score"],
                "level": lr["confidence_level"],
                "can_confirm": can_conf,
                "field_confidence": field_conf
            },
            "lookalike": {
                "is_flagged": bool(lr["lookalike_flag"]),
                "paired_drug": lr["lookalike_paired"]
            },
            "lasa_acknowledged": bool(lr["lasa_acknowledged"]),
            "validation": {
                "dose_flag": val_flags.get("dose_flag"),
                "freq_flag": val_flags.get("freq_flag"),
                "duration_flag": val_flags.get("dur_flag")
            },
            "status": lr["status"],
            "final_drug": lr["final_drug"],
            "final_dose": lr["final_dose"],
            "final_freq": lr["final_freq"],
            "final_duration": lr["final_duration"]
        })
        
    corrections = []
    for c in corr_rows:
        corrections.append({
            "line_id": c["line_id"],
            "original_suggestion": c["original_suggestion"],
            "final_value": json.loads(c["final_value"] or "{}"),
            "corrected_by": c["corrected_by"],
            "notes": c["notes"],
            "timestamp": c["timestamp"]
        })

    audit_logs = []
    for a in audit_rows:
        audit_logs.append({
            "id": a["id"],
            "line_id": a["line_id"],
            "action": a["action"],
            "actor": a["actor"],
            "details": a["details"],
            "timestamp": a["timestamp"]
        })

    return {
        "prescription_id": rx_row["id"],
        "original_filename": rx_row["filename"],
        "image_url": rx_row["image_path"],
        "status": rx_row["status"],
        "quality_check": {
            "passed": bool(rx_row["quality_passed"]),
            "blur_score": rx_row["blur_score"],
            "mean_brightness": rx_row["mean_brightness"],
            "glare_share": rx_row["glare_share"],
            "message": rx_row["quality_message"]
        },
        "lines": lines,
        "corrections": corrections,
        "audit_logs": audit_logs,
        "total_lines": len(lines),
        "all_can_confirm": all_can_confirm,
        "created_at": rx_row["created_at"],
        "updated_at": rx_row["updated_at"]
    }

# ==========================================
# User & Authentication Database Helpers
# ==========================================

def create_user(
    name: str,
    email: str,
    password_hash: str,
    role: str = "pharmacist",
    is_verified: bool = False,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    uid = user_id or str(uuid.uuid4())
    norm_email = email.lower().strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO users (id, name, email, password_hash, role, is_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (uid, name.strip(), norm_email, password_hash, role, 1 if is_verified else 0, now_iso))
    conn.close()
    return {
        "id": uid,
        "name": name.strip(),
        "email": norm_email,
        "role": role,
        "is_verified": is_verified,
        "created_at": now_iso
    }

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if not email:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)

def verify_user(email: str) -> bool:
    conn = get_connection()
    with conn:
        cur = conn.execute("UPDATE users SET is_verified = 1 WHERE email = ?", (email.lower().strip(),))
        success = cur.rowcount > 0
    conn.close()
    return success

def update_user_verification(user_id: str, is_verified: bool = True) -> bool:
    conn = get_connection()
    with conn:
        cur = conn.execute("UPDATE users SET is_verified = ? WHERE id = ?", (1 if is_verified else 0, user_id))
        success = cur.rowcount > 0
    conn.close()
    return success

def update_user_password(user_id: str, new_password_hash: str) -> bool:
    conn = get_connection()
    with conn:
        cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
        success = cur.rowcount > 0
    conn.close()
    return success

def create_otp(
    user_id: Optional[str],
    email: str,
    purpose: str,
    code_hash: str,
    expires_at_iso: str,
    otp_id: Optional[str] = None
) -> str:
    oid = otp_id or str(uuid.uuid4())
    norm_email = email.lower().strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO otp_codes (id, user_id, email, purpose, code_hash, expires_at, attempts, used, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
        """, (oid, user_id, norm_email, purpose, code_hash, expires_at_iso, now_iso))
    conn.close()
    return oid

def get_latest_otp(email: str, purpose: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM otp_codes
        WHERE email = ? AND purpose = ?
        ORDER BY created_at DESC LIMIT 1
    """, (email.lower().strip(), purpose)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)

def increment_otp_attempts(otp_id: str) -> int:
    conn = get_connection()
    with conn:
        conn.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?", (otp_id,))
        row = conn.execute("SELECT attempts FROM otp_codes WHERE id = ?", (otp_id,)).fetchone()
    conn.close()
    return row["attempts"] if row else 0

def mark_otp_used(otp_id: str) -> bool:
    conn = get_connection()
    with conn:
        cur = conn.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (otp_id,))
        success = cur.rowcount > 0
    conn.close()
    return success

def count_otps_in_last_hour(email: str) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = get_connection()
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM otp_codes
        WHERE email = ? AND created_at >= ?
    """, (email.lower().strip(), cutoff)).fetchone()
    conn.close()
    return row["cnt"] if row else 0

def seconds_since_last_otp(email: str, purpose: Optional[str] = None) -> Optional[float]:
    conn = get_connection()
    if purpose:
        row = conn.execute("""
            SELECT created_at FROM otp_codes
            WHERE email = ? AND purpose = ?
            ORDER BY created_at DESC LIMIT 1
        """, (email.lower().strip(), purpose)).fetchone()
    else:
        row = conn.execute("""
            SELECT created_at FROM otp_codes
            WHERE email = ?
            ORDER BY created_at DESC LIMIT 1
        """, (email.lower().strip(),)).fetchone()
    conn.close()
    if not row or not row["created_at"]:
        return None
    try:
        created_str = row["created_at"]
        if "T" in created_str:
            dt = datetime.fromisoformat(created_str)
        else:
            dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (datetime.now(timezone.utc) - dt).total_seconds()
        return max(0.0, diff)
    except Exception:
        return None

