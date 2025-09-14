from __future__ import annotations

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from app.models.schemas import SearchRequest
from app.core.utils.provenance import log_provenance


class WorkflowStep(BaseModel):
    step_number: int
    action: str  # 'search_public'|'find_colleagues'|'send_outreach'|'summarize'
    description: str
    parameters: Dict[str, Any]
    dependencies: List[int] = []


class WorkflowPlan(BaseModel):
    research_question: str
    confirmed_requirements: Dict[str, Any]
    steps: List[WorkflowStep]
    estimated_duration_minutes: int
    requires_approval: bool = False


planner_agent = Agent[SearchRequest, WorkflowPlan](
    "openai:gpt-4o",
    deps_type=SearchRequest,
    output_type=WorkflowPlan,
    instructions=(
        "You are a biomedical research planning assistant specializing in cancer research.\n"
        "Your role is to:\n"
        "1. Understand the research question deeply (focusing on cancer research)\n"
        "2. Identify required data modalities (genomics, transcriptomics, proteomics, imaging, microbiome)\n"
        "3. Plan which databases to search (NCBI/GEO, PRIDE, Ensembl)\n"
        "4. Determine if internal colleague outreach is needed\n"
        "5. Create a structured workflow plan with clear steps\n\n"
        "Focus on cancer research priorities: P53, TP53, lung adenocarcinoma, TNBC, breast cancer, biomarkers.\n"
        "Ensure data requirements match research goals.\n"
    ),
)


@planner_agent.tool
async def analyze_research_context(ctx: RunContext[SearchRequest], query: str) -> Dict[str, Any]:
    """Extract key research concepts and identify data requirements."""
    cancer_keywords = [
        "p53",
        "tp53",
        "lung adenocarcinoma",
        "tnbc",
        "breast cancer",
        "nsclc",
        "carcinoma",
        "oncogene",
        "tumor suppressor",
    ]

    modality_keywords = {
        "genomics": ["mutation", "variant", "snp", "genome", "dna", "exome", "wgs", "wxs"],
        "transcriptomics": ["rna-seq", "expression", "transcript", "scrna-seq", "bulk rna"],
        "proteomics": ["protein", "mass spec", "proteome", "ptm", "tmt", "lc-ms"],
        "imaging": ["histology", "microscopy", "mri", "ct scan", "h&e", "pathology"],
        "microbiome": ["microbiota", "bacterial", "16s", "metagenomics"],
    }

    ql = query.lower()
    found_cancer_terms = [term for term in cancer_keywords if term in ql]
    found_modalities = {mod: any(kw in ql for kw in kws) for mod, kws in modality_keywords.items()}

    result = {
        "cancer_focus": found_cancer_terms,
        "suggested_modalities": [k for k, v in found_modalities.items() if v],
        "requires_multi_modal": sum(1 for v in found_modalities.values() if v) > 1,
        "keywords": list(set(found_cancer_terms)),
    }

    # provenance
    await log_provenance(
        actor="planner_agent",
        action="analyze_research_context",
        details={"query": query, "result": result},
    )
    return result


@planner_agent.tool
async def check_internal_resources(ctx: RunContext[SearchRequest]) -> bool:
    """Check if internal colleague search should be included."""
    decision = bool(ctx.deps.include_internal)
    await log_provenance(
        actor="planner_agent",
        action="check_internal_resources",
        details={"include_internal": decision},
    )
    return decision
