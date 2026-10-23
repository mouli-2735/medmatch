import pytest
from app.pipeline.validator import PrescriptionValidator
from app.pipeline.schema import MatchedCandidate

@pytest.fixture
def validator():
    return PrescriptionValidator()

@pytest.fixture
def celebrex_candidate():
    return MatchedCandidate(
        brand_name="Celebrex",
        generic_name="Celecoxib",
        strengths=["100mg", "200mg", "400mg"],
        form="Capsule",
        combined_score=0.95,
        spelling_score=0.95,
        phonetic_score=1.0
    )

@pytest.fixture
def augmentin_candidate():
    return MatchedCandidate(
        brand_name="Augmentin",
        generic_name="Amoxicillin and Potassium Clavulanate",
        strengths=["375mg", "625mg", "1000mg"],
        form="Tablet",
        combined_score=0.98,
        spelling_score=0.98,
        phonetic_score=1.0
    )

class TestFrequencyValidation:
    def test_standard_numeric_codes(self, validator):
        valid, std, flag = validator.validate_frequency("1-0-1")
        assert valid is True
        assert "Twice daily" in std
        assert flag is None

        valid, std, flag = validator.validate_frequency("1-1-1")
        assert valid is True
        assert "Thrice daily" in std

        valid, std, flag = validator.validate_frequency("1 - 0 - 0")
        assert valid is True
        assert "Morning (Once daily)" in std

        valid, std, flag = validator.validate_frequency("0-0-1")
        assert valid is True
        assert "Night" in std

    def test_latin_abbreviations(self, validator):
        valid, std, flag = validator.validate_frequency("OD")
        assert valid is True
        assert "Once daily" in std

        valid, std, flag = validator.validate_frequency("BD")
        assert valid is True
        assert "Twice daily" in std

        valid, std, flag = validator.validate_frequency("TDS")
        assert valid is True
        assert "Thrice daily" in std

        valid, std, flag = validator.validate_frequency("SOS")
        assert valid is True
        assert "As needed" in std

        valid, std, flag = validator.validate_frequency("HS")
        assert valid is True
        assert "bedtime" in std

    def test_missing_or_invalid_frequency(self, validator):
        valid, std, flag = validator.validate_frequency("")
        assert valid is False
        assert "missing" in flag.lower()

        valid, std, flag = validator.validate_frequency("unknown")
        assert valid is False

        valid, std, flag = validator.validate_frequency("take randomly")
        assert valid is False
        assert "Unrecognized" in flag

class TestDoseValidation:
    def test_valid_strengths(self, validator, celebrex_candidate, augmentin_candidate):
        valid, std, flag = validator.validate_dose("200mg", celebrex_candidate)
        assert valid is True
        assert flag is None

        # Space normalization: '625 mg' -> valid for '625mg'
        valid, std, flag = validator.validate_dose("625 mg", augmentin_candidate)
        assert valid is True
        assert flag is None

    def test_unlisted_strength(self, validator, celebrex_candidate):
        valid, std, flag = validator.validate_dose("50mg", celebrex_candidate)
        assert valid is False
        assert "not listed" in flag
        assert "100mg, 200mg, 400mg" in flag

    def test_missing_dose(self, validator, celebrex_candidate):
        valid, std, flag = validator.validate_dose("", celebrex_candidate)
        assert valid is False
        assert "missing" in flag.lower()

    def test_toxic_dosage_flag(self, validator, celebrex_candidate):
        valid, std, flag = validator.validate_dose("5000mg", celebrex_candidate)
        assert valid is False
        assert "toxic" in flag.lower() or "not listed" in flag.lower()

class TestDurationValidation:
    def test_standard_day_formats(self, validator, celebrex_candidate):
        valid, std, flag = validator.validate_duration("5d", celebrex_candidate)
        assert valid is True
        assert std == "5 days"

        valid, std, flag = validator.validate_duration("7 days", celebrex_candidate)
        assert valid is True
        assert std == "7 days"

    def test_medical_fractions(self, validator, celebrex_candidate):
        # '3/7' -> 3 days
        valid, std, flag = validator.validate_duration("3/7", celebrex_candidate)
        assert valid is True
        assert std == "3 days"

        # '1/12' -> 30 days (1 month)
        valid, std, flag = validator.validate_duration("1/12", celebrex_candidate)
        assert valid is True
        assert "30 days" in std

        # '2/52' -> 14 days (2 weeks)
        valid, std, flag = validator.validate_duration("2/52", celebrex_candidate)
        assert valid is True
        assert "14 days" in std

    def test_prolonged_antibiotic_flag(self, validator, augmentin_candidate):
        # Augmentin for 35 days should trigger antibiotic warning
        valid, std, flag = validator.validate_duration("35d", augmentin_candidate)
        assert valid is False
        assert "prolonged antibiotic" in flag.lower()

    def test_invalid_or_missing_duration(self, validator, celebrex_candidate):
        valid, std, flag = validator.validate_duration("", celebrex_candidate)
        assert valid is False
        assert "missing" in flag.lower()

        valid, std, flag = validator.validate_duration("0d", celebrex_candidate)
        assert valid is False
        assert "Invalid" in flag
