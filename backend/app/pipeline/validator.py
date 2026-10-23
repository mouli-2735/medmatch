import re
from typing import Optional, List, Dict, Any, Tuple
from app.pipeline.schema import ValidationResult, MatchedCandidate

# Frequency mappings
STANDARD_FREQUENCIES = {
    # Numerical patterns
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

ANTIBIOTIC_KEYWORDS = ["amoxicillin", "clavulanate", "azithromycin", "ciprofloxacin", "cefixime", "cefpodoxime", "doxycycline", "erythromycin", "clarithromycin", "metronidazole"]

class PrescriptionValidator:
    def validate_frequency(self, freq_raw: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates and standardizes frequency.
        Returns: (is_valid, standardized_text, flag_warning)
        """
        if not freq_raw or freq_raw.strip().lower() in ["unknown", "none", ""]:
            return False, None, "Frequency missing from prescription."
            
        cleaned = freq_raw.strip().lower()
        
        # Check standard dictionary
        if cleaned in STANDARD_FREQUENCIES:
            return True, STANDARD_FREQUENCIES[cleaned], None
            
        # Regex search for numeric patterns like 1-0-1 within text
        num_match = re.search(r"\b[0-2]\s*-\s*[0-2]\s*-\s*[0-2]\b", cleaned)
        if num_match:
            key = re.sub(r"\s+", "", num_match.group(0))
            if key in STANDARD_FREQUENCIES:
                return True, STANDARD_FREQUENCIES[key], None

        # Check for keywords within text
        for k, v in STANDARD_FREQUENCIES.items():
            if re.search(rf"\b{re.escape(k)}\b", cleaned):
                return True, v, None
                
        return False, freq_raw.strip(), f"Unrecognized frequency pattern: '{freq_raw}'."

    def validate_dose(self, dose_raw: str, candidate: Optional[MatchedCandidate]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates dose against candidate strengths.
        Returns: (is_valid, standardized_text, flag_warning)
        """
        if not dose_raw or dose_raw.strip().lower() in ["unknown", "none", ""]:
            return False, None, "Dose/strength missing from prescription."

        cleaned_dose = dose_raw.strip()
        # Normalize spacing, e.g. '650 mg' -> '650mg'
        norm_dose = re.sub(r"(\d+(\.\d+)?)\s*(mg|mcg|g|ml|iu|u)\b", r"\1\3", cleaned_dose, flags=re.IGNORECASE).lower()

        if not candidate or not candidate.strengths:
            # Cannot cross-check without candidate strengths, check basic structure
            return True, cleaned_dose, None

        # Normalize catalog strengths
        catalog_strengths = [s.strip().lower().replace(" ", "") for s in candidate.strengths]
        
        # Check exact or partial match
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
        Validates and standardizes duration (e.g. 5d, 7 days, 1/12, 3/7).
        Returns: (is_valid, standardized_text, flag_warning)
        """
        if not duration_raw or duration_raw.strip().lower() in ["unknown", "none", ""]:
            return False, None, "Duration missing from prescription."

        cleaned = duration_raw.strip().lower()
        days = None
        standardized = None
        
        # 1. '5d' or '5 days'
        d_match = re.search(r"^(\d+)\s*(d|days?)$", cleaned)
        if d_match:
            days = int(d_match.group(1))
            standardized = f"{days} days"

        # 2. '2w' or '2 weeks'
        w_match = re.search(r"^(\d+)\s*(w|weeks?)$", cleaned)
        if w_match:
            w = int(w_match.group(1))
            days = w * 7
            standardized = f"{days} days ({w} weeks)"

        # 3. '1m' or '1 month'
        m_match = re.search(r"^(\d+)\s*(m|months?)$", cleaned)
        if m_match:
            m = int(m_match.group(1))
            days = m * 30
            standardized = f"{days} days ({m} month{'s' if m>1 else ''})"

        # 4. Medical fractions: '3/7' -> 3 days (out of a 7-day week)
        frac_7_match = re.search(r"^(\d+)\s*/\s*7$", cleaned)
        if frac_7_match:
            days = int(frac_7_match.group(1))
            standardized = f"{days} days"

        # 5. Medical fractions: '1/12' -> 1 month (out of 12 months)
        frac_12_match = re.search(r"^(\d+)\s*/\s*12$", cleaned)
        if frac_12_match:
            m = int(frac_12_match.group(1))
            days = m * 30
            standardized = f"{days} days ({m} month{'s' if m>1 else ''})"

        # 6. Medical fractions: '2/52' -> 2 weeks (out of 52 weeks)
        frac_52_match = re.search(r"^(\d+)\s*/\s*52$", cleaned)
        if frac_52_match:
            w = int(frac_52_match.group(1))
            days = w * 7
            standardized = f"{days} days ({w} weeks)"

        if days is None:
            # Fallback search for just number + day
            simple_num = re.search(r"(\d+)", cleaned)
            if simple_num:
                days = int(simple_num.group(1))
                standardized = f"{days} days"
            else:
                return False, duration_raw.strip(), f"Unrecognized duration format: '{duration_raw}'."

        if days <= 0:
            return False, standardized, "Invalid zero or negative duration."

        # Clinical warning: Prolonged antibiotics
        if candidate and candidate.generic_name:
            gen_lower = candidate.generic_name.lower()
            if any(ab in gen_lower for ab in ANTIBIOTIC_KEYWORDS) and days > 21:
                return False, standardized, f"Unusually prolonged antibiotic course ({days} days). Typical courses rarely exceed 14-21 days."

        if days > 180:
            return False, standardized, f"Duration of {days} days requires regular therapeutic monitoring."

        return True, standardized, None

    def validate_line(self, dose_raw: str, freq_raw: str, duration_raw: str, candidate: Optional[MatchedCandidate]) -> ValidationResult:
        """Runs full validation suite on a line item"""
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
