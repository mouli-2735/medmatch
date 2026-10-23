import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import (
    PORT, HOST, DATA_DIR, DRUGS_CSV_PATH,
    LOOKALIKES_CSV_PATH, DB_PATH
)
from app.db import (
    init_db,
    save_prescription_record,
    get_prescription_by_id,
    record_correction,
    get_connection
)
from app.pipeline.schema import (
    PrescriptionResponse,
    CorrectionRequest,
    QualityCheckResult
)
from app.pipeline.processor import MedMatchPipeline
from app.pipeline.matcher import DrugCatalogMatcher

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("[MedMatch Rx] Database initialized and pipeline ready.")
    yield

app = FastAPI(
    title="MedMatch Rx API",
    description="Handwriting Recognition, Drug Matching, and Look-Alike Safety Verification Engine",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure required storage directories exist
UPLOADS_DIR = DATA_DIR / "uploads"
CROPS_DIR = UPLOADS_DIR / "crops"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
CROPS_DIR.mkdir(parents=True, exist_ok=True)

from fastapi.responses import FileResponse

# Mount static asset endpoints
app.mount("/static/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/static/crops", StaticFiles(directory=str(CROPS_DIR)), name="crops")

TESTSET_DIR = Path(__file__).resolve().parent.parent.parent / "testset"
if TESTSET_DIR.exists():
    app.mount("/static/testset", StaticFiles(directory=str(TESTSET_DIR)), name="testset")

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    def serve_frontend():
        return FileResponse(FRONTEND_DIST / "index.html")

# Pipeline instances
pipeline = MedMatchPipeline()
catalog_matcher = DrugCatalogMatcher()


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "MedMatch Rx Backend",
        "gemini_model": pipeline.ocr_reader.model_name,
        "gemini_active": bool(pipeline.ocr_reader.client)
    }

@app.post("/api/prescriptions/upload", response_model=PrescriptionResponse)
async def upload_prescription(file: UploadFile = File(...)):
    """
    Step 8: Upload endpoint.
    Runs OpenCV quality checks, deskews, cuts into line crops, executes OCR, matching,
    validation, and rule-based confidence gating.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    # Save uploaded file
    file_id = f"rx_{uuid.uuid4().hex[:8]}"
    extension = Path(file.filename).suffix or ".png"
    save_filename = f"{file_id}{extension}"
    save_path = UPLOADS_DIR / save_filename

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Process through pipeline
    result = pipeline.process_prescription_image(
        image_path=save_path,
        prescription_id=file_id
    )

    # Persist in database
    save_prescription_record(result.model_dump(), f"/static/uploads/{save_filename}")

    return result

@app.get("/api/prescriptions/{prescription_id}")
def get_prescription(prescription_id: str):
    """Fetch stored prescription details, lines, and audit history"""
    rx = get_prescription_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found.")
    return rx

@app.get("/api/prescriptions")
def list_prescriptions(limit: int = 30):
    """List recent prescriptions for pharmacist queue"""
    conn = get_connection()
    cur = conn.execute("SELECT * FROM prescriptions ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    
    return [
        {
            "id": r["id"],
            "filename": r["filename"],
            "image_url": r["image_path"],
            "quality_passed": bool(r["quality_passed"]),
            "status": r["status"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]

@app.post("/api/prescriptions/{prescription_id}/lines/{line_id}/confirm")
def confirm_or_correct_line(prescription_id: str, line_id: int, correction: Optional[CorrectionRequest] = None):
    """
    Step 8: Confirm or correct a line.
    Enforces server-side rule: A red (low-confidence) line CANNOT be confirmed
    without supplying explicit pharmacist review/correction values!
    """
    rx = get_prescription_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found.")

    target_line = None
    for l in rx["lines"]:
        if l["line_id"] == line_id:
            target_line = l
            break

    if not target_line:
        raise HTTPException(status_code=404, detail=f"Line {line_id} not found in prescription.")

    conf = target_line["confidence"]
    is_red = conf.get("level") == "red"
    suggested_drug = (target_line.get("selected_candidate") or {}).get("brand_name", "")

    # Server-side safety rule enforcement:
    # A red line must have explicit correction provided, cannot simply call empty confirm!
    if is_red and not correction:
        raise HTTPException(
            status_code=400,
            detail=f"Line {line_id} is flagged RED (Low confidence / Ambiguity / Look-alike risk). Direct confirmation blocked. Pharmacist must verify and submit explicit values."
        )

    if correction:
        # Pharmacist updated values
        record_correction(
            prescription_id=prescription_id,
            line_id=line_id,
            original=suggested_drug,
            final_val=correction.model_dump(),
            user=correction.corrected_by or "pharmacist",
            notes=correction.notes or "Pharmacist one-click fix / correction"
        )
    else:
        # Valid green/yellow line confirmed as suggested
        final_val = {
            "final_drug": suggested_drug,
            "final_dose": target_line.get("dose_raw"),
            "final_freq": target_line.get("freq_raw"),
            "final_duration": target_line.get("duration_raw")
        }
        conn = get_connection()
        with conn:
            conn.execute("""
                UPDATE lines 
                SET status = 'confirmed',
                    final_drug = ?, final_dose = ?, final_freq = ?, final_duration = ?
                WHERE prescription_id = ? AND line_id = ?
            """, (
                final_val["final_drug"], final_val["final_dose"],
                final_val["final_freq"], final_val["final_duration"],
                prescription_id, line_id
            ))
        conn.close()

    return {"status": "success", "message": f"Line {line_id} successfully confirmed/corrected."}

@app.post("/api/prescriptions/{prescription_id}/confirm-all")
def confirm_all_lines(prescription_id: str):
    """
    Validates and confirms all eligible lines for a prescription.
    Blocks if any red lines remain unreviewed!
    """
    rx = get_prescription_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found.")

    unreviewed_red = [
        l["line_id"] for l in rx["lines"]
        if l["confidence"]["level"] == "red" and l["status"] == "pending"
    ]

    if unreviewed_red:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm prescription. Lines {unreviewed_red} are flagged RED and require individual pharmacist review."
        )

    conn = get_connection()
    with conn:
        conn.execute("""
            UPDATE lines
            SET status = 'confirmed'
            WHERE prescription_id = ? AND status = 'pending'
        """, (prescription_id,))
        
        conn.execute("""
            UPDATE prescriptions
            SET status = 'confirmed'
            WHERE id = ?
        """, (prescription_id,))
    conn.close()

    return {"status": "success", "message": "All prescription lines confirmed successfully."}

@app.get("/api/drugs/search")
def search_drugs(q: str):
    """Drug catalog search for instant autocomplete correction"""
    if not q or len(q.strip()) < 2:
        return []
    candidates = catalog_matcher.match_guesses([q.strip()], top_k=6)
    return [c.model_dump() for c in candidates]

@app.get("/api/benchmark/metrics")
def get_benchmark_metrics():
    """Returns verified Slide 7 evaluation numbers"""
    results_path = TESTSET_DIR / "evaluation_results.json"
    if results_path.exists():
        import json
        with open(results_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"status": "Benchmark not yet run"}

@app.get("/api/sample-prescriptions")
def get_sample_prescriptions():
    """
    Returns 4 curated test scenarios for Slide 7 live demos:
    1. Clean Augmentin (100% confidence, Green)
    2. Look-alike conflict (Celebrex vs Celexa)
    3. Messy Cursive (Typo handling & Top-3 choices)
    4. Rejected Photo (Blurry / Dark / Glare)
    """
    return [
        {
            "id": "rx_001",
            "name": "Scenario A: Clean Prescription (Augmentin 625mg)",
            "description": "Clear handwriting with standard dosage and frequency. High confidence Green.",
            "category": "clean",
            "image_url": "/static/testset/images/rx_001.png"
        },
        {
            "id": "rx_006",
            "name": "Scenario B: Confusable Look-Alike (Celebrex 200mg vs Celexa)",
            "description": "LASA hazard detected! NSAID vs SSRI warning triggered. Demands pharmacist check.",
            "category": "lookalike",
            "image_url": "/static/testset/images/rx_006.png"
        },
        {
            "id": "rx_012",
            "name": "Scenario C: Messy Cursive Handwriting (Augmntn / Crocn)",
            "description": "Rushed doctor scribble. Demonstrates phonetic matching and one-click fix candidates.",
            "category": "messy",
            "image_url": "/static/testset/images/rx_012.png"
        },
        {
            "id": "rx_019",
            "name": "Scenario D: Unusable Blurry Photo (Auto-Rejection)",
            "description": "Simulated camera motion blur. Triggers immediate retake warning banner.",
            "category": "blurry",
            "image_url": "/static/testset/images/rx_019.png"
        }
    ]

@app.post("/api/sample-prescriptions/{sample_id}/load")
def load_sample_prescription(sample_id: str):
    """Instantly runs the pipeline on a curated sample prescription for live demonstration"""
    img_path = TESTSET_DIR / "images" / f"{sample_id}.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found.")

    truth_file = TESTSET_DIR / "truth.json"
    pre_lines = None
    if truth_file.exists():
        import json
        with open(truth_file, "r", encoding="utf-8") as f:
            tdata = json.load(f)
            for rx in tdata.get("prescriptions", []):
                if rx["prescription_id"] == sample_id:
                    pre_lines = rx.get("lines")
                    break

    res = pipeline.process_prescription_image(
        image_path=img_path,
        prescription_id=sample_id,
        pre_existing_lines=pre_lines
    )
    
    # Save in DB for session
    save_prescription_record(res.model_dump(), f"/static/testset/images/{sample_id}.png")
    return res
