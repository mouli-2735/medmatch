import pytest
from app.pipeline.confidence import ConfidenceEvaluator, LookalikeChecker
from app.pipeline.schema import MatchedCandidate, ValidationResult, LookalikeWarning

@pytest.fixture
def evaluator():
    return ConfidenceEvaluator()

@pytest.fixture
def lookalike_checker():
    return LookalikeChecker()

class TestLookalikeChecker:
    def test_celebrex_celexa_flagged(self, lookalike_checker):
        warning = lookalike_checker.check_candidate("Celebrex")
        assert warning.is_flagged is True
        assert warning.paired_drug == "Celexa"
        assert "CONFUSABLE PAIR" in warning.warning_message

    def test_zantac_xanax_flagged(self, lookalike_checker):
        warning = lookalike_checker.check_candidate("Zantac")
        assert warning.is_flagged is True
        assert warning.paired_drug == "Xanax"

    def test_non_lookalike_unflagged(self, lookalike_checker):
        warning = lookalike_checker.check_candidate("Dolo 650")
        assert warning.is_flagged is False

class TestConfidenceEvaluator:
    def test_high_confidence_green(self, evaluator):
        candidates = [
            MatchedCandidate(brand_name="Augmentin", generic_name="Amoxicillin", strengths=["625mg"], form="Tablet", combined_score=0.96, spelling_score=0.96, phonetic_score=1.0),
            MatchedCandidate(brand_name="Augmentan", generic_name="Amoxicillin", strengths=["500mg"], form="Capsule", combined_score=0.65, spelling_score=0.65, phonetic_score=0.6)
        ]
        validation = ValidationResult(all_valid=True)
        lookalike = LookalikeWarning(is_flagged=False)

        res = evaluator.evaluate_confidence(["Augmentin", "Augmentin", "Augmentin"], candidates, validation, lookalike)
        assert res.level == "green"
        assert res.can_confirm is True
        assert res.score >= 0.80

    def test_lookalike_penalty_forces_yellow_or_red(self, evaluator):
        candidates = [
            MatchedCandidate(brand_name="Celebrex", generic_name="Celecoxib", strengths=["200mg"], form="Capsule", combined_score=0.88, spelling_score=0.88, phonetic_score=0.88),
            MatchedCandidate(brand_name="Celexa", generic_name="Citalopram", strengths=["20mg"], form="Tablet", combined_score=0.82, spelling_score=0.82, phonetic_score=0.82)
        ]
        validation = ValidationResult(all_valid=True)
        lookalike = LookalikeWarning(is_flagged=True, paired_drug="Celexa", warning_message="CONFUSABLE")

        res = evaluator.evaluate_confidence(["Celebrex", "Celexa"], candidates, validation, lookalike)
        # Small margin (0.88 - 0.82 = 0.06) + lookalike flag should drop score below green threshold
        assert res.level in ["yellow", "red"]

    def test_unreadable_blocks_confirmation(self, evaluator):
        res = evaluator.evaluate_confidence(["unreadable"], [], ValidationResult(all_valid=False), LookalikeWarning())
        assert res.level == "red"
        assert res.can_confirm is False
        assert res.score == 0.0
