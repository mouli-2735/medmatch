from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# OCR Raw Output from Multimodal Vision AI
class GeminiLineOutput(BaseModel):
    guesses: List[str] = Field(
        ...,
        description="Candidate guesses for handwritten drug name, or ['unreadable'] if illegible"
    )
    dose_raw: str = Field(..., description="Dose text as written on prescription, e.g. '200mg' or 'unknown'")
    freq_raw: str = Field(..., description="Frequency as written, e.g. '1-0-1', 'OD', 'TDS' or 'unknown'")
    duration_raw: str = Field(..., description="Duration as written, e.g. '5d', '7 days' or 'unknown'")
    bbox: Optional[List[int]] = Field(default=None, description="[ymin, xmin, ymax, xmax] in 0-1000 scale")
    is_service_error: bool = False
    service_error_detail: Optional[str] = None

class GeminiPageMedicationEntry(BaseModel):
    bbox: Optional[List[int]] = Field(default=None, description="[ymin, xmin, ymax, xmax] in 0-1000 scale")
    guesses: List[str] = Field(default_factory=lambda: ["unreadable"])
    dose_raw: str = "unknown"
    freq_raw: str = "unknown"
    duration_raw: str = "unknown"

class GeminiPageOutput(BaseModel):
    prescriptions: List[GeminiPageMedicationEntry] = []
    is_service_error: bool = False
    service_error_detail: Optional[str] = None

class LineCropData(BaseModel):
    line_id: int
    crop: str
    guesses: List[str]
    dose_raw: str
    freq_raw: str
    duration_raw: str
    bbox: Optional[List[int]] = None

class AgreedPipelineData(BaseModel):
    lines: List[LineCropData]

# Local Catalog Matching Candidates (RapidFuzz & Metaphone)
class MatchedCandidate(BaseModel):
    brand_name: str
    generic_name: str
    strengths: List[str] = []
    form: str = "Tablet"
    combined_score: float
    spelling_score: float
    phonetic_score: float
    phonetic_code: Optional[str] = None
    phonetic_match_description: Optional[str] = None
    source: str = "Local Clinical Catalog (NLEM/Jan Aushadhi)"

# Online RxNorm Live Reference Candidate
class RxNormCandidate(BaseModel):
    rxcui: str
    name: str
    synonym: Optional[str] = None
    term_type: Optional[str] = None
    match_type: str = "exact"  # "exact" or "approximate"
    score: Optional[float] = None
    source: str = "RXNORM"

class RxNormLookupResult(BaseModel):
    original_term: str
    normalized_term: str
    status: str  # "exact_match", "approximate_match", "not_found", "unreadable", "service_unavailable", "error"
    is_exact: bool = False
    rxcui: Optional[str] = None
    display_name: Optional[str] = None
    candidates: List[RxNormCandidate] = []
    source: str = "NLM RxNorm"
    message: str = ""

# Clinical Validation
class ValidationResult(BaseModel):
    dose_valid: bool = True
    dose_standardized: Optional[str] = None
    dose_flag: Optional[str] = None
    freq_valid: bool = True
    freq_standardized: Optional[str] = None
    freq_flag: Optional[str] = None
    duration_valid: bool = True
    duration_standardized: Optional[str] = None
    duration_flag: Optional[str] = None
    all_valid: bool = True

# ISMP Look-Alike Sound-Alike (LASA) Warning
class LookalikeWarning(BaseModel):
    is_flagged: bool = False
    paired_drug: Optional[str] = None
    paired_generic: Optional[str] = None
    warning_message: Optional[str] = None
    risk_level: str = "high"  # "high", "medium", "none"
    ismp_reference: bool = True

# Field-Level Heuristic Confidence Indicators
class FieldConfidence(BaseModel):
    drug_level: str = "low"      # "high", "medium", "low"
    dose_level: str = "low"      # "high", "medium", "low"
    freq_level: str = "low"      # "high", "medium", "low"
    duration_level: str = "low"  # "high", "medium", "low"
    indicator_type: str = "heuristic"  # Clearly labeled as heuristic indicator, not calibrated probability
    details: Dict[str, str] = {}

class ConfidenceResult(BaseModel):
    score: float
    level: str  # "green", "yellow", "red"
    can_confirm: bool
    reasons: List[str] = []
    field_confidence: Optional[FieldConfidence] = None

# Comprehensive Processed Line
class ProcessedLine(BaseModel):
    line_id: int
    crop: str
    bbox: Optional[List[int]] = None
    guesses: List[str]
    dose_raw: str
    freq_raw: str
    duration_raw: str
    # Original OCR extraction trace for full clinical auditability
    original_ocr_trace: Dict[str, Any] = Field(default_factory=dict)
    top_candidates: List[MatchedCandidate] = []
    selected_candidate: Optional[MatchedCandidate] = None
    # Live RxNorm integration
    rxnorm: Optional[RxNormLookupResult] = None
    validation: ValidationResult
    lookalike: LookalikeWarning
    confidence: ConfidenceResult
    lasa_acknowledged: bool = False
    status: str = "pending"  # "pending", "reviewed", "corrected", "confirmed"
    final_drug: Optional[str] = None
    final_dose: Optional[str] = None
    final_freq: Optional[str] = None
    final_duration: Optional[str] = None

class QualityCheckResult(BaseModel):
    passed: bool
    is_blurry: bool
    blur_score: float
    is_dark: bool
    mean_brightness: float
    has_glare: bool
    glare_share: float
    message: str
    deskew_angle: float = 0.0
    rotation_applied: int = 0
    orientation_confident: bool = True

class PrescriptionResponse(BaseModel):
    prescription_id: str
    original_filename: str
    image_url: str
    quality_check: QualityCheckResult
    lines: List[ProcessedLine]
    total_lines: int
    status: str = "pending"  # "pending", "in_review", "confirmed", "rejected"
    all_can_confirm: bool
    vision_ai_status: str = "operational"  # "operational", "quota_exhausted", "service_unavailable", "demo_mode"
    vision_ai_message: Optional[str] = None
    created_at: str

class CorrectionRequest(BaseModel):
    final_drug: str
    final_dose: str
    final_freq: str
    final_duration: str
    lasa_acknowledged: Optional[bool] = False
    corrected_by: Optional[str] = "pharmacist"
    notes: Optional[str] = None

class ConfirmLineRequest(BaseModel):
    lasa_acknowledged: Optional[bool] = False
    confirmed_by: Optional[str] = "pharmacist"
    notes: Optional[str] = None

class ConfirmLinePayload(BaseModel):
    final_drug: Optional[str] = None
    final_dose: Optional[str] = None
    final_freq: Optional[str] = None
    final_duration: Optional[str] = None
    lasa_acknowledged: Optional[bool] = False
    confirmed_by: Optional[str] = "pharmacist"
    corrected_by: Optional[str] = None
    notes: Optional[str] = None
