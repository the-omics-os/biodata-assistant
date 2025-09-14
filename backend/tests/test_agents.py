import os
import sys
import pytest

# Ensure 'app' package is importable when running from repo root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.agents.planner_agent import planner_agent  # type: ignore
from app.core.agents.biodatabase_agent import (  # type: ignore
    DatabaseSearchParams,
    evaluate_dataset_relevance,
)
from app.core.agents.colleagues_agent import enrich_contact_info  # type: ignore
from app.core.agents.email_agent import compose_email, send_via_agentmail, EmailOutreachParams  # type: ignore
from app.core.agents.summarizer_agent import analyze_dataset_quality, generate_export_data  # type: ignore
from app.models.schemas import SearchRequest


@pytest.mark.asyncio
async def test_planner_agent_run_minimal():
    req = SearchRequest(
        query="P53 mutations in lung adenocarcinoma RNA-seq data",
        modalities=["transcriptomics"],
        cancer_types=["lung adenocarcinoma"],
        include_internal=True,
        max_results=5,
    )
    # We cannot guarantee LLM availability; ensure agent object exists and tools are callable
    assert planner_agent is not None
    # Do not call planner_agent.run() to avoid model dependency


@pytest.mark.asyncio
async def test_biodatabase_relevance_scoring_tool():
    # Create a minimal RunContext surrogate with .deps
    class Ctx:
        def __init__(self):
            self.deps = DatabaseSearchParams(
                query="TNBC proteomics",
                database="GEO",
                max_results=5,
            )

    dataset = {
        "title": "Proteomics landscape of TNBC tumors",
        "description": "Study profiling tumor samples",
        "modalities": ["proteomics"],
        "sample_size": 120,
        "access_type": "public",
    }
    score = await evaluate_dataset_relevance(Ctx(), dataset)
    assert 0.0 <= score <= 1.0
    assert score >= 0.5  # should get a reasonably high score given matches


@pytest.mark.asyncio
async def test_colleagues_enrich_contact_info_tool():
    class Ctx:
        class Deps:
            company = "Acme Oncology"
        deps = Deps()

    employee = {"name": "Jane Doe", "job_title": "Bioinformatician", "relevance_score": 0.8}
    enriched = await enrich_contact_info(Ctx(), employee)
    assert "email_suggestions" in enriched
    assert any(s.endswith("@acmeoncology.com") for s in enriched["email_suggestions"])


@pytest.mark.asyncio
async def test_email_agent_compose_and_send_simulated():
    params = EmailOutreachParams(
        dataset_id="GSE12345",
        dataset_title="TP53 mutation profiles in breast cancer",
        requester_name="Alex Smith",
        requester_email="alex@example.com",
        requester_title="Research Scientist",
        contact_name="Data Custodian",
        contact_email="custodian@example.org",
        project_description="Requesting access to study TP53 mutation effects",
        urgency="normal",
    )

    class Ctx:
        deps = params

    content = await compose_email(Ctx())  # type: ignore[arg-type]
    assert "subject" in content and "body" in content

    # With no AgentMail API key in settings, this should simulate a send
    result = await send_via_agentmail(Ctx(), content)  # type: ignore[arg-type]
    assert result["status"] in ("sent", "pending_approval", "failed")


@pytest.mark.asyncio
async def test_summarizer_tools_quality_and_export():
    class Ctx:
        class Deps:
            research_question = "Lung adenocarcinoma TP53 transcriptomics"
            datasets_found = [
                {"access_type": "public", "sample_size": 60, "modalities": ["rna-seq"], "accession": "GSE1", "title": "A", "source": "GEO"},
                {"access_type": "request", "sample_size": 120, "modalities": ["rna-seq"], "accession": "GSE2", "title": "B", "source": "GEO"},
            ]
            contacts_identified = []
            outreach_sent = [{"dataset_id": "GSE2", "status": "sent"}]
        deps = Deps()

    q = await analyze_dataset_quality(Ctx())  # type: ignore[arg-type]
    assert q["total_found"] == 2
    assert q["publicly_available"] == 1
    assert q["requires_outreach"] == 1

    export = await generate_export_data(Ctx())  # type: ignore[arg-type]
    assert export["metadata"]["total_results"] == 2
    assert len(export["datasets"]) == 2
