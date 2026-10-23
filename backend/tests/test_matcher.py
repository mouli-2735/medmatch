import pytest
from app.pipeline.matcher import DrugCatalogMatcher, normalize_drug_string

@pytest.fixture
def matcher():
    return DrugCatalogMatcher()

class TestDrugMatcher:
    def test_normalization(self):
        assert normalize_drug_string("Tab. Celebrex 200mg") == "celebrex"
        assert normalize_drug_string("Cap Pan-D 40mg/30mg") == "pan d"
        assert normalize_drug_string("1) Augmentin 625 mg") == "augmentin"
        assert normalize_drug_string("Syp. Calpol 250mg/5ml") == "calpol"
        assert normalize_drug_string("  Tab   Dolo   650   ") == "dolo 650"

    def test_exact_matches(self, matcher):
        candidates = matcher.match_guesses(["Celebrex"], top_k=3)
        assert len(candidates) > 0
        assert candidates[0].brand_name == "Celebrex"
        assert candidates[0].combined_score >= 0.85

    def test_phonetic_and_fuzzy_typo_matching(self, matcher):
        # 'Celebrx' -> should match 'Celebrex'
        candidates = matcher.match_guesses(["Celebrx", "Cetebrex", "Celebreks"], top_k=3)
        assert len(candidates) > 0
        assert candidates[0].brand_name == "Celebrex"

        # 'Augmntn' -> should match 'Augmentin'
        candidates = matcher.match_guesses(["Augmntn"], top_k=3)
        assert len(candidates) > 0
        assert candidates[0].brand_name == "Augmentin"

    def test_unreadable_returns_empty(self, matcher):
        candidates = matcher.match_guesses(["unreadable"], top_k=3)
        assert candidates == []

    def test_top_3_returned(self, matcher):
        candidates = matcher.match_guesses(["Citalopram"], top_k=3)
        assert len(candidates) <= 3
        # Should match Celexa (generic is Citalopram)
        names = [c.brand_name for c in candidates]
        assert "Celexa" in names
