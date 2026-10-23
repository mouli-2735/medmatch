import csv
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.config import LOOKALIKES_CSV_PATH
from app.pipeline.schema import (
    MatchedCandidate,
    ValidationResult,
    LookalikeWarning,
    ConfidenceResult,
    FieldConfidence
)
from app.pipeline.matcher import normalize_drug_string

class LookalikeChecker:
    """
    Checks candidates against the ISMP (Institute for Safe Medication Practices)
    Look-Alike / Sound-Alike (LASA) list of confusable drug pairs.
    """
    def __init__(self, lookalikes_csv_path: Optional[Path] = None):
        self.csv_path = Path(lookalikes_csv_path or LOOKALIKES_CSV_PATH)
        self.lookalikes: List[Dict[str, str]] = []
        self._load_pairs()

    def _load_pairs(self):
        if not self.csv_path.exists():
            return
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d1 = row.get("drug_1", "").strip()
                d2 = row.get("drug_2", "").strip()
                reason = row.get("risk_reason", "").strip()
                if d1 and d2:
                    self.lookalikes.append({
                        "drug_1": d1,
                        "drug_2": d2,
                        "norm_1": normalize_drug_string(d1),
                        "norm_2": normalize_drug_string(d2),
                        "risk_reason": reason
                    })

    def check_candidate(self, candidate_name: str) -> LookalikeWarning:
        """Checks if a drug name appears in known confusable look-alike pairs"""
        if not candidate_name:
            return LookalikeWarning()

        norm = normalize_drug_string(candidate_name)
        for pair in self.lookalikes:
            paired = None
            if norm == pair["norm_1"]:
                paired = pair["drug_2"]
            elif norm == pair["norm_2"]:
                paired = pair["drug_1"]

            if paired:
                return LookalikeWarning(
                    is_flagged=True,
                    paired_drug=paired,
                    warning_message=f"CONFUSABLE PAIR (LASA RISK): '{candidate_name}' is clinically confusable with '{paired}'. {pair['risk_reason']}",
                    risk_level="high",
                    ismp_reference=True
                )

        return LookalikeWarning(is_flagged=False)

class ConfidenceEvaluator:
    """
    Evaluates heuristic field-level confidence and overall confirmation eligibility.
    NOTE: Confidence scores are explicit heuristic quality indicators based on
    clinical heuristics and model evidence, NOT calibrated statistical probabilities.
    """
    GREEN_THRESHOLD = 0.80
    YELLOW_THRESHOLD = 0.55

    def evaluate_confidence(
        self,
        guesses: List[str],
        candidates: List[MatchedCandidate],
        validation: ValidationResult,
        lookalike: LookalikeWarning,
        is_service_error: bool = False,
        service_error_detail: Optional[str] = None
    ) -> ConfidenceResult:
        reasons = []

        # Case 0: Vision AI service error
        if is_service_error:
            field_conf = FieldConfidence(
                drug_level="low",
                dose_level="low",
                freq_level="low",
                duration_level="low",
                indicator_type="heuristic",
                details={"error": service_error_detail or "Vision AI service was unavailable."}
            )
            return ConfidenceResult(
                score=0.0,
                level="red",
                can_confirm=False,
                reasons=[f"AI Service Unavailable: {service_error_detail or 'Vision AI offline'}."],
                field_confidence=field_conf
            )

        # Case 1: unreadable or no matches
        if not candidates or not guesses or guesses == ["unreadable"]:
            field_conf = FieldConfidence(
                drug_level="low",
                dose_level="low" if not validation.dose_valid else "medium",
                freq_level="low" if not validation.freq_valid else "medium",
                duration_level="low" if not validation.duration_valid else "medium",
                indicator_type="heuristic",
                details={"drug": "Handwriting is unreadable or ambiguous."}
            )
            return ConfidenceResult(
                score=0.0,
                level="red",
                can_confirm=False,
                reasons=["Handwriting marked unreadable or no catalog candidate found."],
                field_confidence=field_conf
            )

        top_cand = candidates[0]
        base_score = top_cand.combined_score
        score = base_score

        # 1. Candidate Margin Analysis
        drug_level = "medium"
        if len(candidates) >= 2:
            second_cand = candidates[1]
            margin = top_cand.combined_score - second_cand.combined_score
            if margin >= 0.20 and base_score >= 0.85:
                score += 0.05
                drug_level = "high"
                reasons.append(f"Clear leading candidate (margin: +{margin:.2f}).")
            elif margin < 0.08:
                score -= 0.15
                drug_level = "low"
                reasons.append(f"High ambiguity with runner-up '{second_cand.brand_name}' (margin only {margin:.2f}).")
        else:
            if base_score >= 0.85:
                drug_level = "high"
            reasons.append("Sole candidate matched.")

        # 2. Guesses Agreement
        clean_guesses = [normalize_drug_string(g) for g in guesses if g and g.lower() != "unreadable"]
        if len(clean_guesses) >= 2:
            if len(set(clean_guesses)) == 1:
                score += 0.05
                reasons.append("All OCR guesses strongly agree on drug name.")
            elif len(clean_guesses) == 3 and len(set(clean_guesses)) == 3:
                score -= 0.06
                if drug_level == "high":
                    drug_level = "medium"
                reasons.append("OCR guesses show moderate variance across attempts.")

        # 3. Clinical Validation impact
        dose_level = "high" if validation.dose_valid else "low"
        freq_level = "high" if validation.freq_valid else "low"
        dur_level = "high" if validation.duration_valid else "low"

        if validation.all_valid:
            score += 0.05
            reasons.append("Dose, frequency, and duration clinically verified.")
        else:
            if not validation.dose_valid:
                score -= 0.12
                reasons.append(f"Dose flag: {validation.dose_flag}")
            if not validation.freq_valid:
                score -= 0.08
                reasons.append(f"Frequency flag: {validation.freq_flag}")
            if not validation.duration_valid:
                score -= 0.05
                reasons.append(f"Duration flag: {validation.duration_flag}")

        # 4. Look-alike risk impact
        if lookalike.is_flagged:
            score -= 0.15
            reasons.append(f"Look-alike alert active: Confusable with '{lookalike.paired_drug}'. Requires pharmacist verification.")

        # Clamp between 0.0 and 1.0
        final_score = max(0.0, min(1.0, round(score, 4)))

        # Level determination
        if final_score >= self.GREEN_THRESHOLD and validation.all_valid and not lookalike.is_flagged:
            level = "green"
            can_confirm = True
        elif final_score >= self.YELLOW_THRESHOLD:
            level = "yellow"
            can_confirm = True
        else:
            level = "red"
            can_confirm = False

        field_conf = FieldConfidence(
            drug_level=drug_level,
            dose_level=dose_level,
            freq_level=freq_level,
            duration_level=dur_level,
            indicator_type="heuristic",
            details={
                "drug": f"Score: {top_cand.combined_score*100:.1f}% ({top_cand.phonetic_match_description})",
                "dose": validation.dose_standardized or validation.dose_flag or "Missing",
                "freq": validation.freq_standardized or validation.freq_flag or "Missing",
                "duration": validation.duration_standardized or validation.duration_flag or "Missing"
            }
        )

        return ConfidenceResult(
            score=final_score,
            level=level,
            can_confirm=can_confirm,
            reasons=reasons,
            field_confidence=field_conf
        )
