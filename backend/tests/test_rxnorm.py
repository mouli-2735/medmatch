import asyncio
import httpx
from unittest.mock import AsyncMock, patch
from app.pipeline.rxnorm import RxNormClient, normalize_search_term

def test_rxnorm_normalize_search_term():
    assert normalize_search_term("  Augmentin-625 mg  ") == "Augmentin"
    assert normalize_search_term("Tab. Paracetamol 500mg") == "Paracetamol"
    assert normalize_search_term("") == ""

def test_rxnorm_exact_match_success():
    client = RxNormClient(timeout=2.0, cache_ttl=60)
    mock_response_data = {
        "drugGroup": {
            "name": "augmentin",
            "conceptGroup": [
                {
                    "tty": "SBD",
                    "conceptProperties": [
                        {
                            "rxcui": "203155",
                            "name": "Augmentin 625 MG Oral Tablet",
                            "synonym": "Augmentin",
                            "tty": "SBD"
                        }
                    ]
                }
            ]
        }
    }

    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data

    async def run():
        with patch.object(httpx.AsyncClient, "get", return_value=mock_resp):
            res = await client.lookup_medicine("augmentin")
            assert res.status == "exact_match"
            assert res.is_exact is True
            assert res.rxcui == "203155"
            assert "Augmentin" in (res.display_name or "")
            assert len(res.candidates) >= 1

    asyncio.run(run())

def test_rxnorm_approximate_fallback():
    client = RxNormClient(timeout=2.0, cache_ttl=60)

    # exact returns empty drugGroup
    exact_mock_resp = AsyncMock(spec=httpx.Response)
    exact_mock_resp.status_code = 200
    exact_mock_resp.json.return_value = {"drugGroup": {"conceptGroup": []}}

    # approximate returns approximateGroup
    approx_mock_resp = AsyncMock(spec=httpx.Response)
    approx_mock_resp.status_code = 200
    approx_mock_resp.json.return_value = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "197361",
                    "name": "Amoxicillin 500 MG Oral Capsule",
                    "score": "80",
                    "rank": "1"
                }
            ]
        }
    }

    # property lookup returns concept name
    prop_mock_resp = AsyncMock(spec=httpx.Response)
    prop_mock_resp.status_code = 200
    prop_mock_resp.json.return_value = {
        "propConceptGroup": {
            "propConcept": [
                {"propName": "RxNorm Name", "propValue": "Amoxicillin 500 MG Oral Capsule"}
            ]
        }
    }

    async def side_effect(url, **kwargs):
        u = str(url)
        if "drugs.json" in u:
            return exact_mock_resp
        elif "approximateTerm.json" in u:
            return approx_mock_resp
        elif "allProperties.json" in u:
            return prop_mock_resp
        return exact_mock_resp

    async def run():
        with patch.object(httpx.AsyncClient, "get", side_effect=side_effect):
            res = await client.lookup_medicine("amoxil")
            assert res.status == "approximate_match"
            assert res.is_exact is False
            assert res.rxcui == "197361"
            assert res.display_name == "Amoxicillin 500 MG Oral Capsule"

    asyncio.run(run())

def test_rxnorm_not_found():
    client = RxNormClient(timeout=2.0, cache_ttl=60)

    empty_resp = AsyncMock(spec=httpx.Response)
    empty_resp.status_code = 200
    empty_resp.json.return_value = {"drugGroup": {"conceptGroup": []}}

    approx_empty = AsyncMock(spec=httpx.Response)
    approx_empty.status_code = 200
    approx_empty.json.return_value = {"approximateGroup": {}}

    async def side_effect(url, **kwargs):
        if "drugs.json" in str(url):
            return empty_resp
        return approx_empty

    async def run():
        with patch.object(httpx.AsyncClient, "get", side_effect=side_effect):
            res = await client.lookup_medicine("unknownmedxyz123")
            assert res.status == "not_found"
            assert res.is_exact is False
            assert res.rxcui is None
            assert res.display_name is None

    asyncio.run(run())

def test_rxnorm_timeout_handled():
    client = RxNormClient(timeout=2.0, cache_ttl=60)

    async def run():
        with patch.object(httpx.AsyncClient, "get", side_effect=httpx.TimeoutException("RxNorm connection timeout")):
            res = await client.lookup_medicine("timeout_med")
            assert res.status == "service_unavailable"
            assert res.is_exact is False
            assert "timeout" in res.message.lower()

    asyncio.run(run())

def test_rxnorm_in_memory_caching():
    client = RxNormClient(timeout=2.0, cache_ttl=60)

    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "drugGroup": {
            "conceptGroup": [
                {
                    "conceptProperties": [
                        {"rxcui": "12345", "name": "Cached Medicine 100mg", "synonym": "CachedMed"}
                    ]
                }
            ]
        }
    }

    async def run():
        with patch.object(httpx.AsyncClient, "get", return_value=mock_resp) as mock_get:
            res1 = await client.lookup_medicine("cachedmed")
            res2 = await client.lookup_medicine("cachedmed")
            assert res1.rxcui == "12345"
            assert res2.rxcui == "12345"
            assert mock_get.call_count == 1

    asyncio.run(run())
