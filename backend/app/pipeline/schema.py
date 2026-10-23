from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class GeminiLineOutput(BaseModel):
    guesses: List[str] = Field(
        ...,
        description="Top 3 guesses for the handwritten drug name in order of likelihood, or ['unreadable'] if illegible"
    )
    dose_raw: str = Field(..., description="Dose as written on prescription, e.g. '200mg', '500 mg', or 'unknown'")
    freq_raw: str = Field(..., description="Frequency as written, e.g. '1-0-1', 'OD', 'TDS', or 'unknown'")
    duration_raw: str = Field(..., description="Duration as written, e.g. '5d', '7 days', '1/12', or 'unknown'")

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

class MatchedCandidate(BaseModel):
    brand_name: str
    generic_name: str
    strengths: List[str] = []
    form: str = "Tablet"
    combined_score: float
    spelling_score: float
    phonetic_score: float

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

class LookalikeWarning(BaseModel):
    is_flagged: bool = False
    paired_drug: Optional[str] = None
    paired_generic: Optional[str] = None
    warning_message: Optional[str] = None

class ConfidenceResult(BaseModel):
    score: float
    level: str  # "green", "yellow", "red"
    can_confirm: bool
    reasons: List[str] = []

class ProcessedLine(BaseModel):
    line_id: int
    crop: str
    bbox: Optional[List[int]] = None
    guesses: List[str]
    dose_raw: str
    freq_raw: str
    duration_raw: str
    top_candidates: List[MatchedCandidate] = []
    selected_candidate: Optional[MatchedCandidate] = None
    validation: ValidationResult
    lookalike: LookalikeWarning
    confidence: ConfidenceResult
    status: str = "pending"  # "pending", "confirmed", "corrected"
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

class PrescriptionResponse(BaseModel):
    prescription_id: str
    original_filename: str
    image_url: str
    quality_check: QualityCheckResult
    lines: List[ProcessedLine]
    total_lines: int
    all_can_confirm: bool
    created_at: str

class CorrectionRequest(BaseModel):
    final_drug: str
    final_dose: str
    final_freq: str
    final_duration: str
    corrected_by: Optional[str] = "pharmacist"
    notes: Optional[str] = None
