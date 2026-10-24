import re
import logging
from typing import Optional, List, Dict, Any, Tuple
from app.pipeline.schema import ValidationResult, MatchedCandidate

logger = logging.getLogger("medmatch.validator")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Frequency mappings for standard clinical prescription codes
STANDARD_FREQUENCIES = {
    # Numerical patterns (Indian / Commonwealth prescription format)
    "1-0-1": "Morning and Night (Twice daily)",
    "1 - 0 - 1": "Morning and Night (Twice daily)",
    "1+0+1": "Morning and Night (Twice daily)",
    "1 + 0 + 1": "Morning and Night (Twice daily)",
    "1-1-1": "Morning, Afternoon, and Night (Thrice daily)",
    "1 - 1 - 1": "Morning, Afternoon, and Night (Thrice daily)",
    "1+1+1": "Morning, Afternoon, and Night (Thrice daily)",
    "1-0-0": "Morning (Once daily)",
    "1 - 0 - 0": "Morning (Once daily)",
    "1+0+0": "Morning (Once daily)",
    "0-0-1": "Night / At bedtime (Once daily)",
    "0 - 0 - 1": "Night / At bedtime (Once daily)",
    "0+0+1": "Night / At bedtime (Once daily)",
    "0-1-0": "Afternoon (Once daily)",
    "0 - 1 - 0": "Afternoon (Once daily)",
    "1-1-0": "Morning and Afternoon (Twice daily)",
    "0-1-1": "Afternoon and Night (Twice daily)",
    "1-1-1-1": "Four times daily (QID)",
    "2-0-2": "Two tablets morning and night (Twice daily)",

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
    "q12h": "Every 12 hours",

    # Eye drops & topical frequencies
    "e/d": "Eye Drops",
    "1 drop": "1 drop",
    "2 drops": "2 drops"
}

ANTIBIOTIC_KEYWORDS = [
    "amoxicillin", "clavulanate", "azithromycin", "ciprofloxacin",
    "cefixime", "cefpodoxime", "doxycycline", "erythromycin",
    "clarithromycin", "metronidazole", "ofloxacin", "levofloxacin"
]


class RegimenParser:
    """
    Stage 6: Clinical Regimen Pattern Parser.
    Extracts dose, frequency, and duration using regex patterns for Indian and Latin notations.
    Never hallucinates missing fields: returns 'unknown' if absent.
    """
    # Dose pattern: combinations (80+10, 500/125, 40+12.5), standard units (650mg, 5ml, 0.5%), or fractional tablets (1/2 tab)
    DOSE_REGEX = re.compile(
        r"(\b\d+(?:\.\d+)?\s*(?:\+|\/)\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%)?\b|"
        r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|u|%)\b|"
        r"\b(?:1\/2|half)\s*(?:tab|cap)?\b)",
        re.IGNORECASE
    )

    # Frequency pattern: 1-0-1, 1+0+1, OD, BD, TDS, QID, HS, SOS, etc.
    FREQ_REGEX = re.compile(
        r"(\b[0-2]\s*[-+]\s*[0-2]\s*[-+]\s*[0-2]\b|"
        r"\b[0-2]\s*[-+]\s*[0-2]\b|"
        r"\b(?:od|bd|tds|tid|qid|bid|hs|qhs|sos|prn|stat|q4h|q6h|q8h|q12h)\b|"
        r"\b[1-2]\s*(?:tab|cap|pill)?\s*(?:od|bd|tds|daily)\b)",
        re.IGNORECASE
    )

    # Duration pattern: x 5 days, 5d, 7 days, 1/12, 2/52, x (30), for 1 week
    DURATION_REGEX = re.compile(
        r"((?:x\s*|for\s*)?\(?\d+\)?\s*(?:d|days?|w|weeks?|m|months?)\b|"
        r"\b\d+\s*\/\s*(?:7|12|52)\b|"
        r"\bx\s*\(?(\d+)\)?(?:\s*chr|\s*days)?\b)",
        re.IGNORECASE
    )

    # Indian arrow / quantity dispensing notation: '1 ---------- 90' or '1 ----> 30'
    ARROW_DISPENSE_REGEX = re.compile(
        r"\b([0-2])\s*[-—–>]{2,}\s*\(?(\d+)\)?",
        re.IGNORECASE
    )

    @classmethod
    def parse_regimen_from_text(cls, text: str) -> Dict[str, str]:
        """
        Parses dose, frequency, and duration from raw line text.
        """
        if not text:
            return {"dose": "unknown", "freq": "unknown", "duration": "unknown"}

        dose = "unknown"
        freq = "unknown"
        duration = "unknown"

        # Check for Indian arrow dispensing pattern e.g. '1 -------- 90'
        arrow_match = cls.ARROW_DISPENSE_REGEX.search(text)
        if arrow_match:
            daily_dose = arrow_match.group(1)
            total_qty = arrow_match.group(2)
            if daily_dose == "1":
                freq = "1-0-0"
            elif daily_dose == "2":
                freq = "1-0-1"
            duration = f"{total_qty} days"

        # Check explicit dose
        dose_match = cls.DOSE_REGEX.search(text)
        if dose_match:
            dose = dose_match.group(1).strip()

        # Check explicit frequency if not determined from arrow
        if freq == "unknown":
            freq_match = cls.FREQ_REGEX.search(text)
            if freq_match:
                freq = freq_match.group(1).strip()

        # Check explicit duration if not determined from arrow
        if duration == "unknown":
            dur_match = cls.DURATION_REGEX.search(text)
            if dur_match:
                duration = dur_match.group(1).strip()

        return {"dose": dose, "freq": freq, "duration": duration}


class PrescriptionValidator:
    """
    Field-level clinical verification of prescription instructions:
    Dose, Frequency, and Duration are validated independently.
    Supports Indian & Latin clinical formats, combination strengths, and dispensing notation.
    """
    def __init__(self):
        self.parser = RegimenParser()

    def validate_frequency(self, freq_raw: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates frequency string.
        Returns: (is_valid, standardized_text, flag_warning)
        """
        if not freq_raw or freq_raw.strip().lower() in ["unknown", "none", "", "unreadable"]:
            return False, None, "Frequency missing from prescription."

        cleaned = freq_raw.strip().lower()

        # Exact dictionary match
        if cleaned in STANDARD_FREQUENCIES:
            return True, STANDARD_FREQUENCIES[cleaned], None

        # Numeric pattern '1-0-1' or '1+0+1' with flexible separators
        num_match = re.search(r"\b([0-2])\s*[-+]\s*([0-2])\s*[-+]\s*([0-2])\b", cleaned)
        if num_match:
            key = f"{num_match.group(1)}-{num_match.group(2)}-{num_match.group(3)}"
            if key in STANDARD_FREQUENCIES:
                return True, STANDARD_FREQUENCIES[key], None

        # 2-dose pattern '1-1' or '1+1'
        two_match = re.search(r"\b([0-2])\s*[-+]\s*([0-2])\b", cleaned)
        if two_match:
            d1, d2 = two_match.group(1), two_match.group(2)
            if d1 == "1" and d2 == "1":
                return True, "Morning and Night (Twice daily)", None
            elif d1 == "1" and d2 == "0":
                return True, "Morning (Once daily)", None
            elif d1 == "0" and d2 == "1":
                return True, "Night / At bedtime (Once daily)", None

        # Latin abbreviation token
        for k, v in STANDARD_FREQUENCIES.items():
            if "-" not in k and "+" not in k and re.search(rf"\b{re.escape(k)}\b", cleaned):
                return True, v, None

        return False, freq_raw.strip(), f"Unrecognized frequency instruction: '{freq_raw}'. Pharmacist review required."

    def validate_dose(self, dose_raw: str, candidate: Optional[MatchedCandidate]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates dose string against candidate strengths.
        Handles combination doses like '80+10', '500/125' and liquid percentages (0.5%).
        Never infers a missing dose from drug name alone.
        """
        if not dose_raw or dose_raw.strip().lower() in ["unknown", "none", "", "unreadable"]:
            return False, None, "Dose/strength missing from prescription."

        cleaned_dose = dose_raw.strip()

        # Combination strengths e.g. 80+10, 80/10, 40+12.5, 500/125
        combo_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:\+|\/)\s*(\d+(?:\.\d+)?)\s*(?:mg|mcg)?\b", cleaned_dose, re.IGNORECASE)
        if combo_match:
            return True, cleaned_dose, None

        # Check basic unit or percentage presence
        has_unit = bool(re.search(r"(?:mg|mcg|g|ml|iu|u|tab|cap)\b|%", cleaned_dose, re.IGNORECASE))
        if not has_unit and not combo_match:
            # Check if bare number corresponds to a known catalog strength (e.g. 650 for Dolo 650)
            if candidate and candidate.strengths:
                for s in candidate.strengths:
                    if cleaned_dose in s:
                        return True, f"{cleaned_dose} (catalog: {s})", None
            return False, cleaned_dose, f"Dose '{cleaned_dose}' lacks a recognized clinical unit (e.g. mg, mcg, ml, %)."

        if not candidate or not candidate.strengths:
            return True, cleaned_dose, None

        # Compare with known strengths for candidate
        catalog_strengths = [s.strip().lower().replace(" ", "") for s in candidate.strengths]
        norm_dose = cleaned_dose.lower().replace(" ", "")

        matched = False
        for s in catalog_strengths:
            if norm_dose == s or norm_dose in s or s in norm_dose:
                matched = True
                break

        if matched:
            return True, cleaned_dose, None

        available_str = ", ".join(candidate.strengths)
        return False, cleaned_dose, f"Strength '{cleaned_dose}' not listed for {candidate.brand_name}. Available: {available_str}."

    def validate_duration(self, duration_raw: str, candidate: Optional[MatchedCandidate]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Strict duration validation. Supports explicit units, medical fractions (1/12, 2/52),
        and dispensing quantity notation '90 days' or '(30)'.
        """
        if not duration_raw or duration_raw.strip().lower() in ["unknown", "none", "", "unreadable"]:
            return False, None, "Duration missing from prescription."

        cleaned = duration_raw.strip().lower()
        days = None
        standardized = None

        # Explicit days
        d_match = re.search(r"^(?:for\s+|x\s*)?\(?(\d+)\)?\s*(?:d|days?|chr)?$", cleaned)
        if d_match:
            days = int(d_match.group(1))
            standardized = f"{days} days"

        # Explicit weeks
        if days is None:
            w_match = re.search(r"^(?:for\s+|x\s*)?(\d+)\s*(?:w|weeks?)$", cleaned)
            if w_match:
                w = int(w_match.group(1))
                days = w * 7
                standardized = f"{days} days ({w} week{'s' if w > 1 else ''})"

        # Explicit months
        if days is None:
            m_match = re.search(r"^(?:for\s+|x\s*)?(\d+)\s*(?:m|months?)$", cleaned)
            if m_match:
                m = int(m_match.group(1))
                days = m * 30
                standardized = f"{days} days ({m} month{'s' if m > 1 else ''})"

        # Medical fractions (1/12 = 1 month, 2/52 = 2 weeks, 3/7 = 3 days)
        if days is None:
            f12 = re.search(r"^(\d+)\s*/\s*12$", cleaned)
            if f12:
                m = int(f12.group(1))
                days = m * 30
                standardized = f"{days} days ({m} month{'s' if m > 1 else ''})"

        if days is None:
            f52 = re.search(r"^(\d+)\s*/\s*52$", cleaned)
            if f52:
                w = int(f52.group(1))
                days = w * 7
                standardized = f"{days} days ({w} week{'s' if w > 1 else ''})"

        if days is None:
            f7 = re.search(r"^(\d+)\s*/\s*7$", cleaned)
            if f7:
                days = int(f7.group(1))
                standardized = f"{days} days"

        if days is None:
            return False, duration_raw.strip(), f"Ambiguous duration '{duration_raw}'. Explicit time unit ('days', 'weeks') required."

        if days <= 0:
            return False, standardized, "Invalid zero or negative duration specified."

        # Safety Alert: Prolonged antibiotic course
        if candidate and candidate.generic_name:
            gen_lower = candidate.generic_name.lower()
            if any(ab in gen_lower for ab in ANTIBIOTIC_KEYWORDS) and days > 21:
                return False, standardized, f"Prolonged antibiotic course ({days} days). Typical clinical course rarely exceeds 14-21 days."

        if days > 180:
            return False, standardized, f"Extended duration of {days} days requires ongoing therapeutic monitoring."

        return True, standardized, None

    def validate_line(self, dose_raw: str, freq_raw: str, duration_raw: str, candidate: Optional[MatchedCandidate]) -> ValidationResult:
        """Executes independent clinical validation across dose, frequency, and duration."""
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
