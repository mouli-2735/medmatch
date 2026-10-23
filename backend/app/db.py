import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes SQLite schema for prescriptions, lines, and corrections audit table"""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                suggested_drug TEXT,
                suggested_generic TEXT,
                top_candidates TEXT,
                confidence_score REAL,
                confidence_level TEXT,
                can_confirm BOOLEAN,
                lookalike_flag BOOLEAN,
                lookalike_paired TEXT,
                validation_flags TEXT,
                status TEXT NOT NULL,
                final_drug TEXT,
                final_dose TEXT,
                final_freq TEXT,
                final_duration TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prescription_id) REFERENCES prescriptions (id)
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
                FOREIGN KEY (prescription_id) REFERENCES prescriptions (id)
            )
        """)
    conn.close()

def save_prescription_record(prescription_data: Dict[str, Any], image_rel_path: str):
    conn = get_connection()
    pid = prescription_data["prescription_id"]
    qc = prescription_data["quality_check"]
    
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO prescriptions 
            (id, filename, image_path, quality_passed, blur_score, mean_brightness, glare_share, quality_message, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pid,
            prescription_data["original_filename"],
            image_rel_path,
            qc["passed"],
            qc["blur_score"],
            qc["mean_brightness"],
            qc["glare_share"],
            qc["message"],
            "pending" if qc["passed"] else "rejected",
            prescription_data.get("created_at", datetime.utcnow().isoformat())
        ))
        
        # Save each line
        for line in prescription_data.get("lines", []):
            line_pk = f"{pid}_{line['line_id']}"
            sel = line.get("selected_candidate") or {}
            conf = line.get("confidence") or {}
            lk = line.get("lookalike") or {}
            val = line.get("validation") or {}
            
            conn.execute("""
                INSERT OR REPLACE INTO lines
                (id, prescription_id, line_id, crop_path, raw_guesses, dose_raw, freq_raw, duration_raw,
                 suggested_drug, suggested_generic, top_candidates, confidence_score, confidence_level,
                 can_confirm, lookalike_flag, lookalike_paired, validation_flags, status,
                 final_drug, final_dose, final_freq, final_duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                line_pk,
                pid,
                line["line_id"],
                line["crop"],
                json.dumps(line.get("guesses", [])),
                line.get("dose_raw", ""),
                line.get("freq_raw", ""),
                line.get("duration_raw", ""),
                sel.get("brand_name", "unreadable"),
                sel.get("generic_name", ""),
                json.dumps(line.get("top_candidates", [])),
                conf.get("score", 0.0),
                conf.get("level", "red"),
                conf.get("can_confirm", False),
                lk.get("is_flagged", False),
                lk.get("paired_drug", ""),
                json.dumps({
                    "dose_flag": val.get("dose_flag"),
                    "freq_flag": val.get("freq_flag"),
                    "dur_flag": val.get("duration_flag")
                }),
                line.get("status", "pending"),
                line.get("final_drug"),
                line.get("final_dose"),
                line.get("final_freq"),
                line.get("final_duration")
            ))
    conn.close()

def record_correction(prescription_id: str, line_id: int, original: str, final_val: Dict[str, Any], user: str = "pharmacist", notes: str = ""):
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
        
        # Update line status in database
        conn.execute("""
            UPDATE lines
            SET status = 'corrected',
                final_drug = ?,
                final_dose = ?,
                final_freq = ?,
                final_duration = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE prescription_id = ? AND line_id = ?
        """, (
            final_val.get("final_drug"),
            final_val.get("final_dose"),
            final_val.get("final_freq"),
            final_val.get("final_duration"),
            prescription_id,
            line_id
        ))
    conn.close()

def get_prescription_by_id(pid: str) -> Optional[Dict[str, Any]]:
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
    conn.close()
    
    lines = []
    for lr in line_rows:
        lines.append({
            "line_id": lr["line_id"],
            "crop": lr["crop_path"],
            "guesses": json.loads(lr["raw_guesses"] or "[]"),
            "dose_raw": lr["dose_raw"],
            "freq_raw": lr["freq_raw"],
            "duration_raw": lr["duration_raw"],
            "top_candidates": json.loads(lr["top_candidates"] or "[]"),
            "selected_candidate": {
                "brand_name": lr["suggested_drug"],
                "generic_name": lr["suggested_generic"]
            },
            "confidence": {
                "score": lr["confidence_score"],
                "level": lr["confidence_level"],
                "can_confirm": bool(lr["can_confirm"])
            },
            "lookalike": {
                "is_flagged": bool(lr["lookalike_flag"]),
                "paired_drug": lr["lookalike_paired"]
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
        "total_lines": len(lines),
        "created_at": rx_row["created_at"]
    }
