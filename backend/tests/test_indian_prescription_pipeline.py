import pytest
import numpy as np
import cv2
from pathlib import Path

from app.pipeline.validator import RegimenParser, PrescriptionValidator
from app.pipeline.matcher import DrugCatalogMatcher
from app.pipeline.image_processing import ImageQualityProcessor


class TestIndianPrescriptionPipeline:
    """
    Comprehensive verification of the redesigned Indian prescription clinical pipeline:
    1. Regimen parsing (frequencies, combination doses, durations, dispensing syntax)
    2. Strength-boosted clinical drug matching
    3. Optical preprocessing & printed boilerplate detection
    """

    @pytest.fixture
    def validator(self):
        return PrescriptionValidator()

    @pytest.fixture
    def matcher(self):
        return DrugCatalogMatcher()

    @pytest.fixture
    def image_processor(self):
        return ImageQualityProcessor()

    # -------------------------------------------------------------------------
    # 1. Regimen Parsing Tests
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("freq_input,expected_keyword", [
        ("1-0-1", "Twice daily"),
        ("1 - 0 - 1", "Twice daily"),
        ("1+0+1", "Twice daily"),
        ("1 + 0 + 1", "Twice daily"),
        ("1-1-1", "Thrice daily"),
        ("1+1+1", "Thrice daily"),
        ("1-0-0", "Once daily"),
        ("1+0+0", "Once daily"),
        ("0-0-1", "Night"),
        ("OD", "Once daily"),
        ("BD", "Twice daily"),
        ("TDS", "Thrice daily"),
        ("QID", "Four times daily"),
        ("HS", "bedtime"),
        ("SOS", "As needed"),
    ])
    def test_frequency_parsing_and_standardization(self, validator, freq_input, expected_keyword):
        is_valid, standardized, flag = validator.validate_frequency(freq_input)
        assert is_valid is True, f"Failed for frequency: {freq_input}"
        assert standardized is not None
        assert expected_keyword.lower() in standardized.lower()

    @pytest.mark.parametrize("dose_input", [
        "80+10",
        "80 + 10",
        "80/10",
        "80+10mg",
        "500/125",
        "40+12.5",
        "100+325",
        "650mg",
        "500 mg",
        "5ml",
        "0.5%",
    ])
    def test_combination_and_standard_dose_parsing(self, validator, dose_input):
        is_valid, standardized, flag = validator.validate_dose(dose_input, candidate=None)
        assert is_valid is True, f"Failed for dose: {dose_input}"
        assert standardized is not None

    def test_indian_arrow_dispensing_notation_parsing(self):
        """Tests doctor arrow dispensing notation e.g. '1 -------- 90'"""
        text = "Alwidipin 1 -------- 90"
        reg = RegimenParser.parse_regimen_from_text(text)
        assert reg["freq"] == "1-0-0"
        assert reg["duration"] == "90 days"

    def test_duration_parsing_varieties(self, validator):
        """Tests standard days, weeks, months, and fractions (1/12, 2/52)"""
        test_cases = [
            ("5d", "5 days"),
            ("x 5 days", "5 days"),
            ("7 days", "7 days"),
            ("for 10 days", "10 days"),
            ("1/12", "30 days"),
            ("2/52", "14 days"),
            ("3/7", "3 days"),
            ("x (30)", "30 days"),
        ]
        for dur_raw, expected_days in test_cases:
            is_valid, std, flag = validator.validate_duration(dur_raw, candidate=None)
            assert is_valid is True, f"Failed on duration: {dur_raw}"
            assert expected_days in std

    def test_never_guess_missing_fields(self, validator):
        """Safety requirement: missing fields must return unknown / False, never hallucinated values"""
        reg = RegimenParser.parse_regimen_from_text("RandomScribbleWithoutNumbers")
        assert reg["dose"] == "unknown"
        assert reg["freq"] == "unknown"
        assert reg["duration"] == "unknown"

        f_valid, _, _ = validator.validate_frequency("")
        assert f_valid is False
        d_valid, _, _ = validator.validate_dose("", candidate=None)
        assert d_valid is False
        dur_valid, _, _ = validator.validate_duration("", candidate=None)
        assert dur_valid is False

    # -------------------------------------------------------------------------
    # 2. Drug Matching & Strength Boosting Tests
    # -------------------------------------------------------------------------

    def test_indian_brand_catalog_coverage(self, matcher):
        """Verifies key Indian prescription brands are present in local catalog"""
        brands = [
            "Lotaz", "Losar", "Amlodac", "Amlokind", "Telma", "Telma AM",
            "Dolo 650", "Pan D", "Pantocid", "Rantac", "Actineron", "Sensonae",
            "Afaspan", "Moxicip", "Toba", "Nepastar", "Volibo", "Zerodol"
        ]
        catalog_names = [item["brand_name"].lower() for item in matcher.catalog]
        for b in brands:
            assert b.lower() in catalog_names, f"Missing Indian brand: {b}"

    def test_strength_compatibility_boost(self, matcher):
        """
        Prescriptions follow patterns: drug name + strength (e.g. '80+10' or '650').
        A candidate whose known strengths include the number read must score higher.
        """
        # Match 'Telma' with 80+10 context -> Telma AM (strengths: 80mg/10mg, 80+10) should be boosted
        cands_boosted = matcher.match_guesses(["Telma AM"], top_k=3, dose_context="80+10")
        assert len(cands_boosted) > 0
        top = cands_boosted[0]
        assert top.brand_name == "Telma AM"
        assert "Dose strength compatibility boost applied" in top.phonetic_match_description

    def test_fuzzy_brand_matching_for_misspelled_doctor_writing(self, matcher):
        """Tests that noisy doctor cursive (e.g. 'Augmntn', 'Kuifinlox', 'Lotas') resolves to correct brand"""
        cands = matcher.match_guesses(["Augmntn"], top_k=3)
        assert len(cands) > 0
        assert cands[0].brand_name == "Augmentin"

        cands_lotaz = matcher.match_guesses(["Lotas"], top_k=3)
        assert len(cands_lotaz) > 0
        assert cands_lotaz[0].brand_name in ["Lotaz", "Losar"]

    # -------------------------------------------------------------------------
    # 3. Optical Preprocessing & Layout Filtering Tests
    # -------------------------------------------------------------------------

    def test_clahe_contrast_enhancement(self, image_processor):
        """Verifies CLAHE enhances contrast while preserving dimensions"""
        test_img = np.full((300, 300, 3), 180, dtype=np.uint8)
        # Add faint ink stroke
        cv2.putText(test_img, "Faint Ink", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 1)

        enhanced = image_processor.enhance_contrast_and_ink(test_img)
        assert enhanced.shape == test_img.shape
        # Ink should now have higher contrast (darker stroke relative to background)
        assert np.min(enhanced) < np.min(test_img)

    def test_printed_boilerplate_pattern_detection(self, image_processor):
        """Verifies regex detects printed stationery headers and footers"""
        header_text = "DR. P. MANOJ PRABHAKAR M.B.B.S., M.S (ORTHO) Regd. No. 116354"
        footer_text = "Cell: 8072855054 | E-Mail: selvihealthcare23@gmail.com Coimbatore - 641 017"
        vitals_text = "BP: 150/90 mmHg  Sugar: 215, 338 mg/dl  Weight: 80 kg"
        prescription_line = "1. Tab. Lotaz 50mg 1-0-1 x 30 days"

        assert image_processor.PRINTED_KEYWORDS.search(header_text) is not None
        assert image_processor.PRINTED_KEYWORDS.search(footer_text) is not None
        assert image_processor.PRINTED_KEYWORDS.search(vitals_text) is not None
        # Actual medication line should NOT trigger printed boilerplate match
        assert image_processor.PRINTED_KEYWORDS.search(prescription_line) is None
