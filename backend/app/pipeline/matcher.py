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

def compute_metaphone_safe(text: str) -> str:
    """Safely calculates Metaphone code using jellyfish"""
    norm = normalize_drug_string(text)
    if not norm:
        return ""
    try:
        return jellyfish.metaphone(norm)
    except Exception:
        return ""

class DrugCatalogMatcher:
    """
    Compares candidate medicine names against the clinical drug catalog
    using RapidFuzz (for orthographic/spelling similarity) and
    Metaphone (for phonetic/sound-alike similarity).
    """
    def __init__(self, drugs_csv_path: Optional[Path] = None):
        self.csv_path = Path(drugs_csv_path or DRUGS_CSV_PATH)
        self.catalog: List[Dict[str, Any]] = []
        self._load_catalog()

    def _load_catalog(self):
        if not self.csv_path.exists():
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
                
                brand_meta = compute_metaphone_safe(norm_brand)
                gen_meta = compute_metaphone_safe(norm_generic)
                
                self.catalog.append({
                    "brand_name": brand,
                    "generic_name": generic,
                    "strengths": strengths,
                    "form": form,
                    "norm_brand": norm_brand,
                    "norm_generic": norm_generic,
                    "brand_metaphone": brand_meta,
                    "generic_metaphone": gen_meta
                })

    def match_guesses(self, guesses: List[str], top_k: int = 4) -> List[MatchedCandidate]:
        """
        Takes candidate guesses from OCR.
        Scores every item in the catalog using RapidFuzz (spelling)
        and Metaphone (sound similarity).
        Returns top_k ranked candidates with explicit score breakdowns.
        """
        clean_guesses = [
            (idx, g, normalize_drug_string(g), compute_metaphone_safe(g))
            for idx, g in enumerate(guesses)
            if g and g.strip().lower() != "unreadable" and normalize_drug_string(g)
        ]
        
        if not clean_guesses:
            return []

        scored_candidates: List[MatchedCandidate] = []
        rank_weights = [1.0, 0.92, 0.85]

        for item in self.catalog:
            best_combined = 0.0
            best_spell = 0.0
            best_phone = 0.0
            best_meta_code = item["brand_metaphone"]
            best_meta_desc = "Distinct phonetic profile"
            
            cand_norm = item["norm_brand"]
            cand_meta = item["brand_metaphone"]
            cand_gen_norm = item["norm_generic"]
            cand_gen_meta = item["generic_metaphone"]

            for idx, raw_guess, guess_norm, guess_meta in clean_guesses[:3]:
                w = rank_weights[idx] if idx < len(rank_weights) else 0.80

                # 1. RapidFuzz spelling similarity
                r_ratio = fuzz.ratio(guess_norm, cand_norm) / 100.0
                r_token = fuzz.token_sort_ratio(guess_norm, cand_norm) / 100.0
                spell_score = max(r_ratio, r_token)

                # Check generic name spelling similarity if relevant
                if cand_gen_norm:
                    gen_ratio = fuzz.ratio(guess_norm, cand_gen_norm) / 100.0
                    gen_partial = fuzz.partial_ratio(guess_norm, cand_gen_norm) / 100.0
                    best_gen = max(gen_ratio, gen_partial * 0.90)
                    if best_gen > spell_score:
                        spell_score = best_gen

                # 2. Metaphone Phonetic Similarity
                phone_score = 0.0
                phone_desc = "Phonetically different"
                
                # Check brand metaphone
                if cand_meta and guess_meta:
                    if cand_meta == guess_meta:
                        phone_score = 1.0
                        phone_desc = f"Identical Metaphone sound code [{cand_meta}]"
                    elif cand_meta[:3] == guess_meta[:3] and len(cand_meta) >= 3 and len(guess_meta) >= 3:
                        phone_score = 0.80
                        phone_desc = f"Matching prefix sound code [{cand_meta[:3]}]"
                    else:
                        dist = jellyfish.levenshtein_distance(cand_meta, guess_meta)
                        if dist <= 1:
                            phone_score = 0.65
                            phone_desc = f"Close sound proximity (dist={dist}) [{cand_meta}]"
                        elif dist <= 2:
                            phone_score = 0.40
                            phone_desc = f"Moderate sound proximity (dist={dist}) [{cand_meta}]"

                # Check generic metaphone as well
                if cand_gen_meta and guess_meta:
                    if cand_gen_meta == guess_meta:
                        if 0.95 > phone_score:
                            phone_score = 0.95
                            phone_desc = f"Matches generic sound code [{cand_gen_meta}]"

                # Weighted match: 70% spelling (RapidFuzz), 30% phonetic (Metaphone)
                combined = (0.70 * spell_score + 0.30 * phone_score) * w

                if combined > best_combined:
                    best_combined = combined
                    best_spell = spell_score
                    best_phone = phone_score
                    best_meta_code = cand_meta
                    best_meta_desc = phone_desc

            if best_combined > 0.22:
                scored_candidates.append(MatchedCandidate(
                    brand_name=item["brand_name"],
                    generic_name=item["generic_name"],
                    strengths=item["strengths"],
                    form=item["form"],
                    combined_score=round(best_combined, 4),
                    spelling_score=round(best_spell, 4),
                    phonetic_score=round(best_phone, 4),
                    phonetic_code=best_meta_code,
                    phonetic_match_description=best_meta_desc
                ))

        scored_candidates.sort(key=lambda x: x.combined_score, reverse=True)
        return scored_candidates[:top_k]
