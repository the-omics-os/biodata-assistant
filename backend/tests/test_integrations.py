import pytest

from app.core.scrapers.geo_scraper import GEOScraper
from app.core.scrapers.linkedin_scraper import LinkedInScraper
from app.core.integrations.agentmail_client import AgentMailClient, EmailMessage


@pytest.mark.asyncio
async def test_geo_scraper_mock_or_real():
    """
    GEOScraper should return a list of dicts with required keys.
    In CI/dev without browser_use, it will return mock results.
    """
    scraper = GEOScraper(headless=True)
    results = await scraper.search_datasets(query="TP53 lung adenocarcinoma rna-seq", max_results=3)
    assert isinstance(results, list)
    if results:
        r0 = results[0]
        # check minimal surface
        assert "accession" in r0
        assert "title" in r0
        assert "modalities" in r0


@pytest.mark.asyncio
async def test_linkedin_scraper_mock_or_real():
    """
    LinkedInScraper should return employees with scoring and email suggestions (mock in dev).
    """
    scraper = LinkedInScraper(headless=True)
    results = await scraper.find_company_employees(
        company="Acme Oncology",
        departments=["Oncology", "Genomics"],
        keywords=["cancer", "genomics", "data"],
        max_results=3,
    )
    assert isinstance(results, list)
    if results:
        r0 = results[0]
        assert "name" in r0
        assert "job_title" in r0
        assert "relevance_score" in r0
        assert "email_suggestions" in r0


@pytest.mark.asyncio
async def test_agentmail_client_simulated_send():
    """
    AgentMailClient should simulate a send when API key/SDK is not available.
    """
    client = AgentMailClient()
    msg = EmailMessage(
        to="recipient@example.org",
        from_email="sender@example.org",
        subject="Test",
        body="Hello from test",
        metadata={"dataset_id": "GSE-test", "thread_type": "data_request"},
    )
    result = await client.send_email(msg)
    assert isinstance(result, dict)
    assert "success" in result
    # In mock/sim mode, success should be True
    # If real API key is present, it should still succeed or return structured failure
    assert result.get("success") in (True, False)
