import re
from typing import Optional, List, Dict, Any, Tuple
from app.pipeline.schema import ValidationResult, MatchedCandidate

# Frequency mappings for standard clinical prescription codes
STANDARD_FREQUENCIES = {
    # Numerical patterns (Indian / Commonwealth prescription format)
    "1-0-1": "Morning and Night (Twice daily)",
    "1 - 0 - 1": "Morning and Night (Twice daily)",
    "1-1-1": "Morning, Afternoon, and Night (Thrice daily)",
    "1 - 1 - 1": "Morning, Afternoon, and Night (Thrice daily)",
    "1-0-0": "Morning (Once daily)",
    "1 - 0 - 0": "Morning (Once daily)",
    "0-0-1": "Night / At bedtime (Once daily)",
    "0 - 0 - 1": "Night / At bedtime (Once daily)",
    "0-1-0": "Afternoon (Once daily)",
    "0 - 1 - 0": "Afternoon (Once daily)",
    "1-1-0": "Morning and Afternoon (Twice daily)",
    "0-1-1": "Afternoon and Night (Twice daily)",
    "1-1-1-1": "Four times daily (QID)",
    
    # Latin medical abbreviations
    "od": "Once daily (OD)",
    "qd": "Once daily (QD)",
    "bd": "Twice daily (BD)",
    "bid": "Twice daily (BID)",
    "tds": "Thrice daily (TDS)",
    "tid": "Thrice daily (TID)",
    "qid": "Four times daily (QID)",
    "sos": "As needed (SOS / When required)",
    "prn": "As needed (PRN / When required)",
    "hs": "At bedtime (HS)",
    "qhs": "At bedtime (QHS)",
    "stat": "Immediately (Single dose)",
    
    # Interval codes
    "q4h": "Every 4 hours",
    "q6h": "Every 6 hours",
    "q8h": "Every 8 hours",
    "q12h": "Every 12 hours"
}

ANTIBIOTIC_KEYWORDS = [
    "amoxicillin", "clavulanate", "azithromycin", "ciprofloxacin",
    "cefixime", "cefpodoxime", "doxycycline", "erythromycin",
    "clarithromycin", "metronidazole", "ofloxacin", "levofloxacin"
]

class PrescriptionValidator:
    """
    Performs field-level clinical verification of prescription instructions:
    Dose, Frequency, and Duration are validated independently.
    Rejects malformed, unsupported, or ambiguous entries for pharmacist review.
    """
    def validate_frequency(self, freq_raw: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates frequency string.
        Returns: (is_valid, standardized_text, flag_warning)
        """
        if not freq_raw or freq_raw.strip().lower() in ["unknown", "none", "", "unreadable"]:
            return False, None, "Frequency missing from prescription."
            
        cleaned = freq_raw.strip().lower()
        
        # Check standard dictionary exact match
        if cleaned in STANDARD_FREQUENCIES:
            return True, STANDARD_FREQUENCIES[cleaned], None
            
        # Regex search for numeric pattern like '1-0-1' with flexible spacing
        num_match = re.search(r"\b([0-2])\s*-\s*([0-2])\s*-\s*([0-2])\b", cleaned)
        if num_match:
            key = f"{num_match.group(1)}-{num_match.group(2)}-{num_match.group(3)}"
            if key in STANDARD_FREQUENCIES:
                return True, STANDARD_FREQUENCIES[key], None

        # Check Latin abbreviation token within text (isolated word boundary)
        for k, v in STANDARD_FREQUENCIES.items():
            if "-" not in k and re.search(rf"\b{re.escape(k)}\b", cleaned):
                return True, v, None
                
        return False, freq_raw.strip(), f"Unrecognized frequency instruction: '{freq_raw}'. Pharmacist review required."

    def validate_dose(self, dose_raw: str, candidate: Optional[MatchedCandidate]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates dose string against candidate strengths.
        Never infers a missing dose from drug name alone.
        """
        if not dose_raw or dose_raw.strip().lower() in ["unknown", "none", "", "unreadable"]:
            return False, None, "Dose/strength missing from prescription."

        cleaned_dose = dose_raw.strip()
        norm_dose = re.sub(r"(\d+(\.\d+)?)\s*(mg|mcg|g|ml|iu|u)\b", r"\1\3", cleaned_dose, flags=re.IGNORECASE).lower()

        # Check basic unit presence
        has_unit = bool(re.search(r"(mg|mcg|g|ml|iu|u)\b", norm_dose, re.IGNORECASE))
        if not has_unit:
            return False, cleaned_dose, f"Dose '{cleaned_dose}' lacks a recognized clinical unit (e.g. mg, mcg, ml)."

        if not candidate or not candidate.strengths:
            # Without catalog strengths, check reasonable limits
            num_match = re.search(r"(\d+(\.\d+)?)", norm_dose)
            if num_match and "mg" in norm_dose and float(num_match.group(1)) > 4000:
                return False, cleaned_dose, f"High single dosage ({cleaned_dose}). Verify against therapeutic ceiling."
            return True, cleaned_dose, None

        # Compare with known strengths for the matched candidate
        catalog_strengths = [s.strip().lower().replace(" ", "") for s in candidate.strengths]
        
        matched = False
        for s in catalog_strengths:
            if norm_dose == s or norm_dose in s or s in norm_dose:
                matched = True
                break
                
        if matched:
            return True, cleaned_dose, None
            
        # Parse numeric quantity for sanity check
        num_match = re.search(r"(\d+(\.\d+)?)", norm_dose)
        if num_match:
            val = float(num_match.group(1))
            if "mg" in norm_dose and val > 4000:
                return False, cleaned_dose, f"Potentially toxic dosage ({cleaned_dose}). Exceeds safe clinical thresholds."

        available_str = ", ".join(candidate.strengths)
        return False, cleaned_dose, f"Strength '{cleaned_dose}' is not listed for {candidate.brand_name}. Available: {available_str}."

    def validate_duration(self, duration_raw: str, candidate: Optional[MatchedCandidate]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Strict duration validation.
        Requires explicit time unit or standard medical fraction.
        DOES NOT infer duration from solitary bare numbers!
        """
        if not duration_raw or duration_raw.strip().lower() in ["unknown", "none", "", "unreadable"]:
            return False, None, "Duration missing from prescription."

        cleaned = duration_raw.strip().lower()
        days = None
        standardized = None
        
        # 1. Explicit days: e.g. '5d', '5 days', 'for 5 days'
        d_match = re.search(r"^(?:for\s+)?(\d+)\s*(?:d|days?)$", cleaned)
        if d_match:
            days = int(d_match.group(1))
            standardized = f"{days} days"

        # 2. Explicit weeks: e.g. '2w', '2 weeks'
        if days is None:
            w_match = re.search(r"^(?:for\s+)?(\d+)\s*(?:w|weeks?)$", cleaned)
            if w_match:
                w = int(w_match.group(1))
                days = w * 7
                standardized = f"{days} days ({w} week{'s' if w > 1 else ''})"

        # 3. Explicit months: e.g. '1m', '1 month'
        if days is None:
            m_match = re.search(r"^(?:for\s+)?(\d+)\s*(?:m|months?)$", cleaned)
            if m_match:
                m = int(m_match.group(1))
                days = m * 30
                standardized = f"{days} days ({m} month{'s' if m > 1 else ''})"

        # 4. Standard Medical fraction: '3/7' -> 3 days of a 7-day week
        if days is None:
            frac_7_match = re.search(r"^(\d+)\s*/\s*7$", cleaned)
            if frac_7_match:
                days = int(frac_7_match.group(1))
                standardized = f"{days} days"

        # 5. Standard Medical fraction: '1/12' -> 1 month of 12 months
        if days is None:
            frac_12_match = re.search(r"^(\d+)\s*/\s*12$", cleaned)
            if frac_12_match:
                m = int(frac_12_match.group(1))
                days = m * 30
                standardized = f"{days} days ({m} month{'s' if m > 1 else ''})"

        # 6. Standard Medical fraction: '2/52' -> 2 weeks of 52 weeks
        if days is None:
            frac_52_match = re.search(r"^(\d+)\s*/\s*52$", cleaned)
            if frac_52_match:
                w = int(frac_52_match.group(1))
                days = w * 7
                standardized = f"{days} days ({w} week{'s' if w > 1 else ''})"

        # Strict safety check: If no unit matched, reject bare digits
        if days is None:
            return False, duration_raw.strip(), f"Ambiguous duration '{duration_raw}'. Explicit time unit ('days', 'weeks') required."

        if days <= 0:
            return False, standardized, "Invalid zero or negative duration specified."

        # Safety Alert: Prolonged antibiotic course (>21 days)
        if candidate and candidate.generic_name:
            gen_lower = candidate.generic_name.lower()
            if any(ab in gen_lower for ab in ANTIBIOTIC_KEYWORDS) and days > 21:
                return False, standardized, f"Prolonged antibiotic course ({days} days). Typical clinical course rarely exceeds 14-21 days."

        if days > 180:
            return False, standardized, f"Extended duration of {days} days requires ongoing therapeutic monitoring."

        return True, standardized, None

    def validate_line(self, dose_raw: str, freq_raw: str, duration_raw: str, candidate: Optional[MatchedCandidate]) -> ValidationResult:
        """Executes independent clinical validation across dose, frequency, and duration"""
        f_valid, f_std, f_flag = self.validate_frequency(freq_raw)
        d_valid, d_std, d_flag = self.validate_dose(dose_raw, candidate)
        dur_valid, dur_std, dur_flag = self.validate_duration(duration_raw, candidate)
        
        all_v = bool(f_valid and d_valid and dur_valid)
        
        return ValidationResult(
            dose_valid=d_valid,
            dose_standardized=d_std,
            dose_flag=d_flag,
            freq_valid=f_valid,
            freq_standardized=f_std,
            freq_flag=f_flag,
            duration_valid=dur_valid,
            duration_standardized=dur_std,
            duration_flag=dur_flag,
            all_valid=all_v
        )
