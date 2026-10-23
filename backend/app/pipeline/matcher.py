import csv
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from rapidfuzz import fuzz
import jellyfish

from app.config import DRUGS_CSV_PATH
from app.pipeline.schema import MatchedCandidate

PREFIX_PATTERN = re.compile(r"^(tab\.?|tablets?|cap\.?|capsules?|syp\.?|syrup|inj\.?|injection|t\.?|c\.?)\s+", re.IGNORECASE)
STRENGTH_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|u)\b", re.IGNORECASE)
PUNCT_PATTERN = re.compile(r"[^a-zA-Z0-9\s]")
NUMBER_PREFIX = re.compile(r"^\d+[\).\s\-]+")

def normalize_drug_string(text: str) -> str:
    """
    Normalizes a guess:
    - strips list numbers like '1)'
    - strips tablet/capsule prefixes like 'Tab.', 'Cap.'
    - strips dosage amounts like '200mg', '500 mg'
    - lowercases and removes extraneous punctuation
    """
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = NUMBER_PREFIX.sub("", cleaned).strip()
    cleaned = PREFIX_PATTERN.sub("", cleaned).strip()
    cleaned = STRENGTH_PATTERN.sub("", cleaned).strip()
    cleaned = PUNCT_PATTERN.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split()).lower()
    return cleaned

class DrugCatalogMatcher:
    def __init__(self, drugs_csv_path: Optional[Path] = None):
        self.csv_path = Path(drugs_csv_path or DRUGS_CSV_PATH)
        self.catalog: List[Dict[str, Any]] = []
        self._load_catalog()

    def _load_catalog(self):
        if not self.csv_path.exists():
            print(f"[DrugCatalogMatcher] Warning: {self.csv_path} not found.")
            return

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                brand = row.get("brand_name", "").strip()
                generic = row.get("generic_name", "").strip()
                strengths = [s.strip() for s in row.get("strengths", "").split(",") if s.strip()]
                form = row.get("form", "Tablet").strip()
                
                norm_brand = normalize_drug_string(brand)
                norm_generic = normalize_drug_string(generic)
                
                brand_meta = jellyfish.metaphone(norm_brand) if norm_brand else ""
                
                self.catalog.append({
                    "brand_name": brand,
                    "generic_name": generic,
                    "strengths": strengths,
                    "form": form,
                    "norm_brand": norm_brand,
                    "norm_generic": norm_generic,
                    "brand_metaphone": brand_meta
                })

    def match_guesses(self, guesses: List[str], top_k: int = 3) -> List[MatchedCandidate]:
        """
        Takes top 3 guesses from OCR.
        Scores every candidate in drugs.csv with RapidFuzz for spelling
        and Jellyfish metaphone for sound.
        Returns top_k candidates.
        """
        # If unreadable
        clean_guesses = [normalize_drug_string(g) for g in guesses if g and g.lower() != "unreadable"]
        if not clean_guesses:
            return []

        scored_candidates: List[MatchedCandidate] = []
        
        for item in self.catalog:
            best_combined = 0.0
            best_spell = 0.0
            best_phone = 0.0
            
            cand_norm = item["norm_brand"]
            cand_meta = item["brand_metaphone"]
            
            # Weight guesses: 1st guess has 1.0 weight, 2nd 0.95, 3rd 0.90
            rank_weights = [1.0, 0.95, 0.90]
            
            for idx, guess in enumerate(clean_guesses[:3]):
                if not guess:
                    continue
                w = rank_weights[idx] if idx < len(rank_weights) else 0.85
                
                # 1. RapidFuzz spelling similarity (0 to 100 -> normalize 0 to 1)
                r_ratio = fuzz.ratio(guess, cand_norm) / 100.0
                r_token = fuzz.token_sort_ratio(guess, cand_norm) / 100.0
                spell_score = max(r_ratio, r_token)
                
                # Also check generic name partial match
                if item["norm_generic"]:
                    gen_ratio = fuzz.partial_ratio(guess, item["norm_generic"]) / 100.0
                    if gen_ratio > 0.85:
                        spell_score = max(spell_score, gen_ratio * 0.95)
                
                # 2. Phonetic similarity with Metaphone
                phone_score = 0.0
                guess_meta = jellyfish.metaphone(guess)
                if cand_meta and guess_meta:
                    if cand_meta == guess_meta:
                        phone_score = 1.0
                    elif cand_meta[:3] == guess_meta[:3] and len(cand_meta) >= 3 and len(guess_meta) >= 3:
                        phone_score = 0.80
                    elif jellyfish.levenshtein_distance(cand_meta, guess_meta) <= 1:
                        phone_score = 0.65
                    elif jellyfish.levenshtein_distance(cand_meta, guess_meta) <= 2:
                        phone_score = 0.40
                
                # Weighted average: 70% spelling, 30% phonetic
                combined = (0.70 * spell_score + 0.30 * phone_score) * w
                
                if combined > best_combined:
                    best_combined = combined
                    best_spell = spell_score
                    best_phone = phone_score
            
            if best_combined > 0.20:
                scored_candidates.append(MatchedCandidate(
                    brand_name=item["brand_name"],
                    generic_name=item["generic_name"],
                    strengths=item["strengths"],
                    form=item["form"],
                    combined_score=round(best_combined, 4),
                    spelling_score=round(best_spell, 4),
                    phonetic_score=round(best_phone, 4)
                ))

        scored_candidates.sort(key=lambda x: x.combined_score, reverse=True)
        return scored_candidates[:top_k]
