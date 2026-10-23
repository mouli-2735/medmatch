import csv
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.config import LOOKALIKES_CSV_PATH
from app.pipeline.schema import MatchedCandidate, ValidationResult, LookalikeWarning, ConfidenceResult
from app.pipeline.matcher import normalize_drug_string

class LookalikeChecker:
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
                    warning_message=f"CONFUSABLE PAIR: '{candidate_name}' is known to be easily confused with '{paired}'. {pair['risk_reason']}"
                )

        return LookalikeWarning(is_flagged=False)

class ConfidenceEvaluator:
    GREEN_THRESHOLD = 0.80
    YELLOW_THRESHOLD = 0.55

    def evaluate_confidence(
        self,
        guesses: List[str],
        candidates: List[MatchedCandidate],
        validation: ValidationResult,
        lookalike: LookalikeWarning
    ) -> ConfidenceResult:
        """
        Calculates rule-based confidence score based on:
        - match score of 1st candidate
        - margin between 1st and 2nd candidate
        - agreement among the 3 guesses
        - validation status of dose, frequency, and duration
        - look-alike warning penalty
        """
        reasons = []

        # Case 1: unreadable or no matches
        if not candidates or not guesses or guesses == ["unreadable"]:
            return ConfidenceResult(
                score=0.0,
                level="red",
                can_confirm=False,
                reasons=["Handwriting marked unreadable or no catalog candidate found."]
            )

        top_cand = candidates[0]
        base_score = top_cand.combined_score
        score = base_score

        # 1. Candidate Margin Analysis
        if len(candidates) >= 2:
            second_cand = candidates[1]
            margin = top_cand.combined_score - second_cand.combined_score
            if margin >= 0.20:
                score += 0.05
                reasons.append(f"Clear leading candidate (margin: +{margin:.2f}).")
            elif margin < 0.08:
                score -= 0.15
                reasons.append(f"High ambiguity with runner-up '{second_cand.brand_name}' (margin only {margin:.2f}).")
        else:
            reasons.append("Sole candidate matched.")

        # 2. Guesses Agreement
        clean_guesses = [normalize_drug_string(g) for g in guesses if g and g.lower() != "unreadable"]
        if len(clean_guesses) >= 2:
            # Check how many guesses normalize identically
            if len(set(clean_guesses)) == 1:
                score += 0.05
                reasons.append("All OCR guesses strongly agree on drug name.")
            elif len(clean_guesses) == 3 and len(set(clean_guesses)) == 3:
                score -= 0.06
                reasons.append("OCR guesses show moderate variance across attempts.")

        # 3. Clinical Validation impact
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
            score -= 0.12
            reasons.append(f"Look-alike alert active: {lookalike.paired_drug} requires pharmacist cross-check.")

        # Clamp between 0.0 and 1.0
        final_score = max(0.0, min(1.0, round(score, 4)))

        # Level determination
        if final_score >= self.GREEN_THRESHOLD and validation.all_valid and not lookalike.is_flagged:
            level = "green"
            can_confirm = True
        elif final_score >= self.YELLOW_THRESHOLD:
            level = "yellow"
            # Can confirm only if pharmacist reviews, but not blocked
            can_confirm = True
        else:
            level = "red"
            can_confirm = False
            reasons.append("Low confidence score blocks auto-confirmation; manual pharmacist review required.")

        return ConfidenceResult(
            score=final_score,
            level=level,
            can_confirm=can_confirm,
            reasons=reasons
        )
