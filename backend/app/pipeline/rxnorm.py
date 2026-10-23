import asyncio
import re
import time
from typing import Optional, List, Dict, Any, Tuple
import httpx

from app.config import (
    RXNORM_API_BASE,
    RXNORM_REQUEST_TIMEOUT,
    RXNORM_CACHE_TTL_SECONDS
)
from app.pipeline.schema import RxNormCandidate, RxNormLookupResult

CLEAN_TERM_PATTERN = re.compile(r"^(tab\.?|tablets?|cap\.?|capsules?|syp\.?|syrup|inj\.?|injection|t\.?|c\.?)\s+", re.IGNORECASE)
DOSAGE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|u)\b", re.IGNORECASE)
PUNCT_PATTERN = re.compile(r"[^a-zA-Z0-9\s]")
NUMBER_PREFIX_PATTERN = re.compile(r"^\d+[\).\s\-]+")

def normalize_search_term(term: str) -> str:
    """
    Normalizes search term for RxNorm query:
    Strips formulation prefixes ('Tab.', 'Cap.'), dosages, list numbers, and extra symbols.
    """
    if not term:
        return ""
    cleaned = term.strip()
    cleaned = NUMBER_PREFIX_PATTERN.sub("", cleaned).strip()
    cleaned = CLEAN_TERM_PATTERN.sub("", cleaned).strip()
    cleaned = DOSAGE_PATTERN.sub("", cleaned).strip()
    cleaned = PUNCT_PATTERN.sub(" ", cleaned)
    return " ".join(cleaned.split()).strip()

class RxNormClient:
    """
    Client for the official National Library of Medicine (NLM) RxNav RxNorm REST API.
    Official Documentation:
    https://lhncbc-portal.lhcaws-prod-pub.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        cache_ttl: Optional[int] = None
    ):
        self.base_url = (base_url or RXNORM_API_BASE).rstrip("/")
        self.timeout = timeout or RXNORM_REQUEST_TIMEOUT
        self.cache_ttl = cache_ttl or RXNORM_CACHE_TTL_SECONDS
        self._cache: Dict[str, Tuple[float, RxNormLookupResult]] = {}
        self._lock = asyncio.Lock()

    def _get_from_cache(self, key: str) -> Optional[RxNormLookupResult]:
        entry = self._cache.get(key)
        if entry:
            ts, result = entry
            if time.time() - ts < self.cache_ttl:
                return result
            # Expired
            del self._cache[key]
        return None

    def _set_in_cache(self, key: str, result: RxNormLookupResult):
        # Prevent unbounded cache growth
        if len(self._cache) > 2000:
            now = time.time()
            self._cache = {k: v for k, v in self._cache.items() if now - v[0] < self.cache_ttl}
        self._cache[key] = (time.time(), result)

    async def check_health(self) -> Tuple[bool, str]:
        """Performs a live connectivity check against the NLM RxNorm service"""
        try:
            url = f"{self.base_url}/version.json"
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True, "online"
                return False, f"http_{resp.status_code}"
        except Exception as e:
            return False, f"unavailable: {str(e)}"

    async def lookup_medicine(self, raw_term: str) -> RxNormLookupResult:
        """
        Asynchronously looks up a medicine in the official RxNorm database:
        1. Checks exact match via /drugs.json?name={term}
        2. If not found, checks approximate matches via /approximateTerm.json?term={term}
        3. Returns structured lookup result distinguishing exact from approximate
        4. Handles empty, not found, timeout, and API failure gracefully without fake data
        """
        original_input = raw_term.strip() if raw_term else ""
        normalized_term = normalize_search_term(original_input)

        if not normalized_term or normalized_term.lower() in ["unreadable", "unknown"]:
            return RxNormLookupResult(
                original_term=original_input,
                normalized_term=normalized_term,
                status="unreadable",
                is_exact=False,
                candidates=[],
                message="Medicine name is unreadable or empty; skipping online RxNorm lookup."
            )

        cache_key = normalized_term.lower()
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # Perform live query
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 1. Try Exact match via drugs.json
                exact_candidates = await self._query_drugs_endpoint(client, normalized_term)
                if exact_candidates:
                    res = RxNormLookupResult(
                        original_term=original_input,
                        normalized_term=normalized_term,
                        status="exact_match",
                        is_exact=True,
                        rxcui=exact_candidates[0].rxcui,
                        display_name=exact_candidates[0].name,
                        candidates=exact_candidates,
                        source="NLM RxNorm (drugs.json)",
                        message=f"Exact match verified in RxNorm: {exact_candidates[0].name} (RxCUI: {exact_candidates[0].rxcui})"
                    )
                    self._set_in_cache(cache_key, res)
                    return res

                # 2. Try Approximate match via approximateTerm.json
                approx_candidates = await self._query_approximate_endpoint(client, normalized_term)
                if approx_candidates:
                    res = RxNormLookupResult(
                        original_term=original_input,
                        normalized_term=normalized_term,
                        status="approximate_match",
                        is_exact=False,
                        rxcui=approx_candidates[0].rxcui,
                        display_name=approx_candidates[0].name,
                        candidates=approx_candidates,
                        source="NLM RxNorm (approximateTerm.json)",
                        message=f"Approximate match in RxNorm: {approx_candidates[0].name} (RxCUI: {approx_candidates[0].rxcui}). Pharmacist verification required."
                    )
                    self._set_in_cache(cache_key, res)
                    return res

                # 3. Not found in RxNorm
                res = RxNormLookupResult(
                    original_term=original_input,
                    normalized_term=normalized_term,
                    status="not_found",
                    is_exact=False,
                    candidates=[],
                    source="NLM RxNorm",
                    message="not found in RxNorm (US database)"
                )
                self._set_in_cache(cache_key, res)
                return res

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            return RxNormLookupResult(
                original_term=original_input,
                normalized_term=normalized_term,
                status="service_unavailable",
                is_exact=False,
                candidates=[],
                source="NLM RxNorm",
                message=f"RxNorm service temporarily unreachable: {type(exc).__name__}. Local catalog reference retained."
            )
        except Exception as exc:
            return RxNormLookupResult(
                original_term=original_input,
                normalized_term=normalized_term,
                status="error",
                is_exact=False,
                candidates=[],
                source="NLM RxNorm",
                message=f"Error during RxNorm online query: {str(exc)}"
            )

    async def _query_drugs_endpoint(self, client: httpx.AsyncClient, term: str) -> List[RxNormCandidate]:
        """Queries /drugs.json?name={term}"""
        url = f"{self.base_url}/drugs.json"
        resp = await client.get(url, params={"name": term})
        if resp.status_code != 200:
            return []

        data = resp.json()
        drug_group = data.get("drugGroup") or {}
        concept_groups = drug_group.get("conceptGroup") or []

        seen_cuis = set()
        candidates: List[RxNormCandidate] = []

        for cg in concept_groups:
            props = cg.get("conceptProperties") or []
            for prop in props:
                cui = prop.get("rxcui")
                name = prop.get("name")
                synonym = prop.get("synonym")
                tty = prop.get("tty")
                if cui and cui not in seen_cuis:
                    seen_cuis.add(cui)
                    candidates.append(RxNormCandidate(
                        rxcui=cui,
                        name=name or term,
                        synonym=synonym,
                        term_type=tty,
                        match_type="exact",
                        score=1.0,
                        source="RXNORM"
                    ))
                    if len(candidates) >= 5:
                        return candidates
        return candidates

    async def _query_approximate_endpoint(self, client: httpx.AsyncClient, term: str) -> List[RxNormCandidate]:
        """Queries /approximateTerm.json?term={term}&maxEntries=4"""
        url = f"{self.base_url}/approximateTerm.json"
        resp = await client.get(url, params={"term": term, "maxEntries": 4})
        if resp.status_code != 200:
            return []

        data = resp.json()
        approx_group = data.get("approximateGroup") or {}
        raw_candidates = approx_group.get("candidate") or []

        seen_cuis = set()
        candidates: List[RxNormCandidate] = []

        for item in raw_candidates:
            cui = item.get("rxcui")
            name = item.get("name")
            source = item.get("source", "RXNORM")
            score_str = item.get("score")
            score_val = float(score_str) if score_str else None

            if cui and cui not in seen_cuis:
                seen_cuis.add(cui)
                candidates.append(RxNormCandidate(
                    rxcui=cui,
                    name=name or term,
                    match_type="approximate",
                    score=score_val,
                    source=source
                ))
                if len(candidates) >= 4:
                    break
        return candidates
