import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import (
    PORT, HOST, DATA_DIR, DRUGS_CSV_PATH,
    LOOKALIKES_CSV_PATH, DB_PATH, UPLOADS_DIR, CROPS_DIR,
    ALLOWED_ORIGINS, MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES
)
from app.db import (
    init_db,
    save_prescription_record,
    get_prescription_by_id,
    record_correction,
    record_confirmation,
    batch_confirm_prescription,
    get_connection
)
from app.pipeline.schema import (
    PrescriptionResponse,
    CorrectionRequest,
    ConfirmLineRequest,
    ConfirmLinePayload,
    QualityCheckResult
)
from app.pipeline.processor import MedMatchPipeline
from app.pipeline.matcher import DrugCatalogMatcher
from app.pipeline.rxnorm import RxNormClient

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("[MedMatch Rx] Database initialized with foreign keys and schema migrations.")
    yield

app = FastAPI(
    title="MedMatch Rx API",
    description="Prescription Reading Assistant: Handwriting Recognition, Live RxNorm Lookup, and Look-Alike Safety Verification Engine",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Configuration with restricted origins from config
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Ensure required storage directories exist
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
CROPS_DIR.mkdir(parents=True, exist_ok=True)

# Mount static asset endpoints
app.mount("/static/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/static/crops", StaticFiles(directory=str(CROPS_DIR)), name="crops")

TESTSET_DIR = Path(__file__).resolve().parent.parent.parent / "testset"
TESTSET_IMAGES_DIR = TESTSET_DIR / "images"
if TESTSET_IMAGES_DIR.exists():
    app.mount("/static/testset/images", StaticFiles(directory=str(TESTSET_IMAGES_DIR)), name="testset_images")

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    def serve_frontend():
        return FileResponse(FRONTEND_DIST / "index.html")

# Pipeline instances
pipeline = MedMatchPipeline()
catalog_matcher = DrugCatalogMatcher()
rxnorm_client = RxNormClient()

@app.get("/api/health")
async def health_check():
    """System health check endpoint verifying Vision AI and online RxNorm status"""
    model_ok, model_err = pipeline.ocr_reader.verify_model()
    rxnorm_ok, _ = await rxnorm_client.check_health()
    return {
        "status": "healthy" if (model_ok or not pipeline.ocr_reader.api_key) else "degraded",
        "service": "MedMatch Rx Backend",
        "version": "2.0.0",
        "vision_ai_model": pipeline.ocr_reader.model_name,
        "vision_ai_configured": bool(pipeline.ocr_reader.api_key),
        "vision_ai_ready": model_ok,
        "model_ok": model_ok,
        "model_error": model_err,
        "rxnorm_service": "online" if rxnorm_ok else "unavailable",
        "database": str(DB_PATH)
    }

@app.post("/api/prescriptions/upload", response_model=PrescriptionResponse)
async def upload_prescription(
    file: UploadFile = File(...),
    rotation: Optional[int] = Form(None)
):
    """
    Step 8 & 9: Secure upload endpoint.
    1. Validates file size, extension, MIME type, and image data integrity.
    2. Runs OpenCV quality checks, deskews, cuts into line crops.
    3. Executes Vision AI OCR, RapidFuzz + Metaphone matching.
    4. Executes live online RxNorm reference lookup.
    5. Validates dose, frequency, and duration.
    6. Enforces ISMP LASA safety checks and heuristic confidence gating.
    7. Persists in SQLite.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was selected for upload.")

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{file_ext}'. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Validate content type if supplied
    if file.content_type and file.content_type.lower() not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported MIME type '{file.content_type}'. Must be an image (PNG, JPEG, or WEBP)."
        )

    # Read and validate payload size
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed upload size ({MAX_UPLOAD_BYTES // (1024*1024)} MB)."
        )

    # Generate secure random identifier
    file_id = f"rx_{uuid.uuid4().hex[:8]}"
    save_filename = f"{file_id}{file_ext}"
    save_path = UPLOADS_DIR / save_filename

    # Save to disk
    with open(save_path, "wb") as buffer:
        buffer.write(contents)

    # Validate image data integrity using OpenCV
    import cv2
    img_check = cv2.imread(str(save_path))
    if img_check is None:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid or corrupt image content. Please provide a valid photo.")

    # Process through pipeline without demo cheating
    result = await pipeline.process_prescription_image(
        image_path=save_path,
        prescription_id=file_id,
        allow_demo_fallback=False,
        manual_rotation=rotation
    )

    # Persist in SQLite
    save_prescription_record(result.model_dump(), f"/static/uploads/{save_filename}")

    return result

@app.get("/api/prescriptions/{prescription_id}")
def get_prescription(prescription_id: str):
    """Fetch stored prescription details, lines, corrections, and audit history"""
    rx = get_prescription_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found.")
    return rx

@app.get("/api/prescriptions")
def list_prescriptions(limit: int = Query(30, ge=1, le=100)):
    """List recent prescriptions for pharmacist verification queue"""
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
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        }
        for r in rows
    ]

@app.post("/api/prescriptions/{prescription_id}/lines/{line_id}/confirm")
def confirm_or_correct_line(
    prescription_id: str,
    line_id: int,
    payload: Optional[ConfirmLinePayload] = None,
    x_pharmacist_pin: Optional[str] = Header(None, alias="X-Pharmacist-PIN")
):
    """
    Step 7: Confirm or correct a prescription line item with server-side safety enforcement.
    Rules:
    1. A line flagged RED cannot be directly confirmed without explicit pharmacist correction values.
    2. A line with an active ISMP LASA alert cannot be confirmed without explicit acknowledgment (lasa_acknowledged=True).
    3. Unreadable or missing drug names cannot be silently confirmed.
    4. Records the designated pharmacist identifier (with PIN verification when PHARMACIST_PIN is configured).
    """
    # Verify pharmacist PIN if configured in environment
    env_pin = os.getenv("PHARMACIST_PIN", "").strip()
    if env_pin:
        provided_pin = x_pharmacist_pin or (payload.pharmacist_pin if payload else None)
        if provided_pin != env_pin:
            raise HTTPException(status_code=401, detail="Invalid or missing pharmacist PIN.")

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
    is_lasa = target_line.get("lookalike", {}).get("is_flagged", False)
    paired_drug = target_line.get("lookalike", {}).get("paired_drug", "")

    # Check LASA acknowledgment
    lasa_ack = bool(payload and payload.lasa_acknowledged)

    if is_lasa and not lasa_ack:
        raise HTTPException(
            status_code=400,
            detail=f"Line {line_id} has an active ISMP LASA warning ('{suggested_drug}' confusable with '{paired_drug}'). Confirmation requires explicit pharmacist acknowledgment."
        )

    # Determine if this is an explicit correction or a direct confirmation
    is_correction = bool(payload and payload.final_drug and payload.final_drug.strip())
    if is_correction:
        if payload.final_drug.strip().lower() == "unreadable":
            raise HTTPException(status_code=400, detail="Cannot save line with an unreadable or empty medicine name.")

        record_correction(
            prescription_id=prescription_id,
            line_id=line_id,
            original=suggested_drug or "unreadable",
            final_val=payload.model_dump(),
            user=payload.corrected_by or payload.confirmed_by or "pharmacist",
            notes=payload.notes or "Pharmacist correction submitted",
            lasa_acknowledged=lasa_ack
        )
        return {
            "status": "success",
            "action": "corrected",
            "message": f"Line {line_id} successfully corrected to '{payload.final_drug}'."
        }
    else:
        # Direct confirmation of existing suggested values
        if is_red:
            raise HTTPException(
                status_code=400,
                detail=f"Line {line_id} is flagged RED (Low confidence / Ambiguity / Missing values). Direct confirmation is blocked. Pharmacist must verify and submit explicit values."
            )

        if not suggested_drug or suggested_drug == "unreadable":
            raise HTTPException(status_code=400, detail="Cannot confirm a line with an unreadable medicine name.")

        # Store standardized dose, freq, duration (not raw OCR)
        val_obj = target_line.get("validation") or {}
        std_dose = val_obj.get("dose_standardized") or target_line.get("final_dose") or target_line.get("dose_raw")
        std_freq = val_obj.get("freq_standardized") or target_line.get("final_freq") or target_line.get("freq_raw")
        std_dur = val_obj.get("duration_standardized") or target_line.get("final_duration") or target_line.get("duration_raw")

        final_val = {
            "final_drug": suggested_drug,
            "final_dose": std_dose,
            "final_freq": std_freq,
            "final_duration": std_dur
        }
        
        actor = (payload.confirmed_by if payload else "pharmacist") or "pharmacist"
        notes = (payload.notes if payload else "") or ""

        record_confirmation(
            prescription_id=prescription_id,
            line_id=line_id,
            final_val=final_val,
            confirmed_by=actor,
            notes=notes,
            lasa_acknowledged=lasa_ack
        )
        return {
            "status": "success",
            "action": "confirmed",
            "message": f"Line {line_id} successfully confirmed as '{suggested_drug}'."
        }

@app.post("/api/prescriptions/{prescription_id}/confirm-all")
def confirm_all_lines(prescription_id: str, request: Optional[ConfirmLineRequest] = None):
    """
    Validates and batch-confirms all eligible lines for a prescription.
    Server-side rule: Blocks if ANY line is flagged RED or has an unacknowledged LASA alert!
    """
    confirmed_by = (request.confirmed_by if request else "pharmacist") or "pharmacist"
    success, message, line_ids = batch_confirm_prescription(prescription_id, confirmed_by=confirmed_by)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {
        "status": "success",
        "message": message,
        "confirmed_lines": line_ids
    }

@app.get("/api/drugs/search")
async def search_drugs(q: str = Query(..., min_length=2)):
    """
    Unified medicine search combining:
    1. Local clinical drug catalog (RapidFuzz & Metaphone)
    2. Online live RxNorm API (exact and approximate concepts)
    Returns distinct candidates with explicit source attribution.
    """
    query = q.strip()
    if len(query) < 2:
        return []

    # 1. Local catalog candidates
    local_candidates = catalog_matcher.match_guesses([query], top_k=5)
    results = [c.model_dump() for c in local_candidates]

    # 2. Online RxNorm candidates
    try:
        rxnorm_res = await rxnorm_client.lookup_medicine(query)
        if rxnorm_res.candidates:
            for rc in rxnorm_res.candidates:
                # Deduplicate against local catalog brand name
                if not any(r["brand_name"].lower() == rc.name.lower() for r in results):
                    results.append({
                        "brand_name": rc.name,
                        "generic_name": rc.synonym or rc.name,
                        "strengths": [],
                        "form": rc.term_type or "Medication",
                        "combined_score": round(rc.score or 0.85, 4),
                        "spelling_score": 0.85,
                        "phonetic_score": 0.85,
                        "phonetic_code": None,
                        "phonetic_match_description": f"RxNorm {rc.match_type.title()} Match (RxCUI: {rc.rxcui})",
                        "source": f"NLM RxNorm ({rc.source})"
                    })
    except Exception as exc:
        print(f"[Search API] RxNorm query error: {exc}")

    return results

@app.get("/api/benchmark/metrics")
def get_benchmark_metrics():
    """Returns verified evaluation results from testset/evaluation_results.json"""
    results_path = TESTSET_DIR / "evaluation_results.json"
    if results_path.exists():
        import json
        with open(results_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "status": "Benchmark not yet run",
        "instructions": "Execute 'python backend/scripts/evaluate_benchmark.py' to generate benchmark metrics."
    }

@app.get("/api/sample-prescriptions")
def get_sample_prescriptions():
    """
    Returns curated demo scenarios for testing different clinical conditions:
    1. Clean Augmentin (Standard handwriting, Green)
    2. Look-alike conflict (Celebrex 200mg vs Celexa, LASA Alert)
    3. Messy Cursive (Typo handling & Phonetic candidates)
    4. Rejected Photo (Motion blur / dark image)
    """
    return [
        {
            "id": "rx_001",
            "name": "Scenario A: Clean Prescription (Augmentin 625mg)",
            "description": "Legible handwriting with standard dosage and frequency. High confidence Green.",
            "category": "clean",
            "image_url": "/static/testset/images/rx_001.png"
        },
        {
            "id": "rx_006",
            "name": "Scenario B: Confusable Look-Alike (Celebrex 200mg vs Celexa)",
            "description": "ISMP LASA alert triggered! NSAID vs SSRI hazard detected. Requires pharmacist acknowledgment.",
            "category": "lookalike",
            "image_url": "/static/testset/images/rx_006.png"
        },
        {
            "id": "rx_012",
            "name": "Scenario C: Messy Cursive Handwriting (Augmntn / Crocn)",
            "description": "Rushed doctor scribble. Demonstrates RapidFuzz & Metaphone phonetic ranking and RxNorm lookup.",
            "category": "messy",
            "image_url": "/static/testset/images/rx_012.png"
        },
        {
            "id": "rx_019",
            "name": "Scenario D: Unusable Blurry Photo (Auto-Rejection)",
            "description": "Simulated camera motion blur. Triggers immediate OpenCV retake warning banner.",
            "category": "blurry",
            "image_url": "/static/testset/images/rx_019.png"
        }
    ]

@app.post("/api/sample-prescriptions/{sample_id}/load")
async def load_sample_prescription(sample_id: str):
    """
    Dedicated demo scenario loader.
    Clearly marked as demo mode; runs the pipeline on a sample image.
    """
    img_path = TESTSET_DIR / "images" / f"{sample_id}.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Sample prescription image '{sample_id}.png' not found.")

    res = await pipeline.process_prescription_image(
        image_path=img_path,
        prescription_id=sample_id,
        allow_demo_fallback=True
    )
    res.vision_ai_status = "demo_mode"
    res.vision_ai_message = "Demo scenario loaded. Demonstrates clinical decision-support pipeline."
    
    # Save in DB for session
    save_prescription_record(res.model_dump(), f"/static/testset/images/{sample_id}.png")
    return res
