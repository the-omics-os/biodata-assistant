# Implementation Plan

[Overview]
Pivot the system from LinkedIn colleague discovery to GitHub issue prospecting in Scanpy and AnnData repositories to identify potential users struggling with bioinformatics tooling, extract their contact info, score "novice-likelihood," and execute human-gated, persona-based outreach emails promoting the no-code omics-os product.

This change replaces the "colleagues" search path with a GitHub-repos-first lead generation flow while preserving the system's existing Browser-Use scraping backbone, Pydantic-typed outputs, provenance logging, DB persistence, and AgentMail-driven, human-approved outreach. The core additions are a GitHub issues scraper, a leads agent with rule-based/LLM-tailored novice scoring, a modular persona router for outreach sender identity, and minor TUI changes to select and email leads.

[Types]
Introduce new strongly-typed models for prospects/leads and modular personas.

- Enums (backend/app/models/enums.py)
  - class LeadStage(str, Enum):
    - NEW = "new"
    - ENRICHED = "enriched"  // contact signals/novice_score added
    - SELECTED = "selected"  // chosen for outreach
    - EMAILED = "emailed"
    - RESPONDED = "responded"
    - DISQUALIFIED = "disqualified"
- DB Models (backend/app/models/database.py)
  - class Lead(Base):
    - id: String (uuid, pk)
    - source: String = "github-issues"
    - repo: String  // "scverse/scanpy" | "scverse/anndata"
    - issue_number: Integer
    - issue_url: String (unique index)
    - issue_title: String
    - issue_labels: JSON (list[str])
    - issue_created_at: DateTime (nullable)
    - user_login: String
    - profile_url: String
    - email: String (nullable)
    - website: String (nullable)
    - signals: JSON  // see "scoring signals" below
    - novice_score: Float (0..1)
    - stage: String (LeadStage) default NEW
    - created_at: DateTime (server_default=now)
    - updated_at: DateTime (onupdate=now)
- Pydantic Schemas (backend/app/models/schemas.py)
  - class LeadCreate(BaseModel):
    - source: Literal["github-issues"] = "github-issues"
    - repo: str
    - issue_number: int
    - issue_url: str
    - issue_title: str
    - issue_labels: List[str] = []
    - issue_created_at: Optional[datetime] = None
    - user_login: str
    - profile_url: str
    - email: Optional[EmailStr] = None
    - website: Optional[str] = None
    - signals: Dict[str, Any] = {}
    - novice_score: float = Field(ge=0, le=1, default=0.0)
    - stage: LeadStage = LeadStage.NEW
  - class LeadResponse(LeadCreate):
    - id: str
    - created_at: datetime
    - updated_at: Optional[datetime] = None
    - Config: from_attributes = True
- Persona Config (backend/app/utils/personas.py)
  - class Persona(BaseModel):
    - name: str
    - title: str
    - from_email: EmailStr
    - linkedin_url: Optional[str]
    - modalities: List[str]  // routing keywords
    - repos: List[str]       // optional repo routing
  - PERSONAS: Dict[str, Persona] keyed by slug, initially:
    - "transcripta_quillborne": {
        name="Transcripta Quillborne",
        title="Transcriptomics Specialist",
        from_email="transcripta@omics-os.com",
        linkedin_url="https://www.linkedin.com/in/transcripta-quillborne-96a87b384/",
        modalities=["rna-seq","scrna-seq","transcriptomics"],
        repos=["scverse/scanpy","scverse/anndata"]
      }
    - Placeholders (expandable): "proteos_maximus" (proteomics), "genomus_vitale" (genomics)
- Scoring Signals schema (embedded in Lead.signals)
  - {
      "account_age_days": int | null,
      "followers": int | null,
      "public_repos": int | null,
      "issue_body_length": int | null,
      "labels": List[str],
      "keywords": List[str],        // e.g., ["beginner","install","help","error"]
      "code_blocks_present": bool | null,
      "punctuation_excess": bool | null
    }

[Files]
Add new GitHub prospecting components, update email templates and TUI.

- New
  - backend/app/core/scrapers/github_issues_scraper.py
    - Browser-Use workflows:
      - fetch_issue_list(repo: str, max_issues: int=25) -> List[IssueSummary]
      - enrich_author_contacts(issue: IssueSummary) -> Dict[str, Any]  // email/website via profile + optional website scan
      - Structured outputs via Pydantic models: IssueSummary, IssueSummaries
      - Rate limiting, provenance logging
  - backend/app/core/agents/github_leads_agent.py
    - Agent orchestration to:
      - iterate target repos (scanpy, anndata)
      - call scraper for issue list
      - compute signals + novice_score
      - filter leads novice_score >= 0.6
      - persist into DB (upsert by issue_url)
      - return normalized List[Lead-like dict]
  - backend/app/utils/personas.py
    - Persona definitions and router: select_persona(lead) -> Persona
  - backend/app/utils/scoring.py
    - calculate_novice_score(signals) -> float
    - extract_signals(issue, profile_html?) -> Dict[str, Any]
- Modified
  - backend/app/models/database.py: add Lead model (and alembic/migration note if applicable)
  - backend/app/models/enums.py: add LeadStage
  - backend/app/models/schemas.py: add LeadCreate/LeadResponse
  - backend/app/utils/email_templates.py:
    - add product_invite_template(dataset_title? not needed) -> subject/body tuned to "hei I saw you were struggling… try omics-os"
    - parameterize with persona name/title and repo/issue context
  - backend/app/core/agents/email_agent.py:
    - add compose_product_invite(ctx: ProductInviteParams) tool OR generalize compose_email to accept template_type
    - add ProductInviteParams(BaseModel): lead_id, repo, issue_title, persona_{name,title,from_email}, recipient_{name,email}, message_style="casual"
    - add send_product_invite_via_agentmail(ctx, content)
  - backend/demo.py:
    - add GitHub prospecting path:
      - run_github_prospecting(repos=["scverse/scanpy","scverse/anndata"], max_issues=25)
      - render_leads(leads, highlight novices)
      - select_leads_for_outreach(leads)
      - send_outreach_for_leads(selected, persona_router)
    - maintain human-gated confirmation and preview
- Optional
  - backend/app/api/v1/leads.py: CRUD/List endpoints for leads (nice-to-have)

[Functions]
Implement new scraping, scoring, persona routing, and outreach functions.

- New
  - backend/app/core/scrapers/github_issues_scraper.py
    - class GitHubIssuesScraper:
      - async def fetch_issue_list(self, repo: str, max_issues: int=25) -> List[Dict]
      - async def enrich_author_contacts(self, issue: Dict) -> Dict
      - async def _open_issue_list(self, repo: str) -> bool
      - async def _parse_issue_cards(self, result: Any) -> List[Dict]
      - async def _open_profile_and_extract(self, profile_url: str) -> Dict[str, Optional[str]]
      - async def _extract_email_from_website(self, url: str, max_bytes=200_000) -> Optional[str]
      - async def _log_provenance(self, action: str, details: Dict[str, Any]) -> None
  - backend/app/utils/scoring.py
    - def extract_signals(issue: Dict, profile_meta: Dict) -> Dict[str, Any]
    - def calculate_novice_score(signals: Dict[str, Any]) -> float
      - Heuristic:
        - +0.2 if account_age_days < 365
        - +0.2 if followers < 5
        - +0.1 if public_repos < 5
        - +0.2 if issue contains novice keywords: {"beginner","new","help","install","error"}
        - +0.1 if no code blocks detected
        - +0.1 if labels include {"question","usage","help wanted"}
        - +0.1 if body length < 400
        - Clamp to [0,1]; threshold >= 0.6
  - backend/app/utils/personas.py
    - def select_persona(lead: Dict[str, Any]) -> Persona
      - Match by repo and inferred modality keywords (e.g., "scanpy" => transcriptomics)
  - backend/app/core/agents/github_leads_agent.py
    - async def prospect_github_issues(target_repos: List[str], max_issues: int=25) -> List[Dict]
      - Loops repos → fetch_issue_list → enrich contacts → signals/scoring → persist → return filtered leads
  - backend/app/core/agents/email_agent.py (either)
    - class ProductInviteParams(BaseModel): lead_id, repo, issue_title, recipient_name/email, persona_name/title/from_email, message_style="casual"
    - @email_agent.tool async def compose_product_invite(ctx) -> Dict[str,str]
    - @email_agent.tool async def send_product_invite_via_agentmail(ctx, content) -> Dict[str, Optional[str]]
- Modified
  - backend/demo.py
    - async def run_github_prospecting(repos: List[str], max_issues: int) -> List[Dict]
    - def render_leads(leads: List[Dict]) -> None
    - def select_leads_for_outreach(leads: List[Dict]) -> List[Dict]
    - async def send_outreach_for_leads(leads: List[Dict], style="casual") -> List[Dict]
      - For each lead: persona = select_persona(lead), compose_product_invite, preview, confirm, send via AgentMail
- Removed
  - None (LinkedIn path remains available; this is an additive pivot)

[Classes]
Add scraper and agent classes with key methods and persona data structures.

- New classes
  - GitHubIssuesScraper (backend/app/core/scrapers/github_issues_scraper.py)
    - Methods above; uses Browser-Use Agent/Browser/ChatOpenAI; structured outputs preferred
  - Persona (backend/app/utils/personas.py)
  - Optional: IssueSummary(BaseModel), IssueSummaries(BaseModel) for structured outputs
- Modified classes
  - Email agent: extend with ProductInviteParams/compose_product_invite/send_product_invite_via_agentmail
- Removed classes
  - None

[Dependencies]
No new heavy dependencies; reuse Browser-Use and existing stack.

- Continue using Browser-Use (already installed/configured)
- Optional convenience:
  - python-dateutil (account age parsing) — if needed
- Env additions (.env)
  - OMICS_OS_URL="https://www.omics-os.com" (used in email template CTA)
  - PERSONA_… optional if mapping done via env; otherwise hardcoded in personas.py
  - AgentMail must support from_email identities for personas

[Testing]
Add unit and integration coverage for scoring and end-to-end workflow.

- Unit tests
  - tests/test_scoring.py: signals → novice_score (edge cases)
  - tests/test_personas.py: lead → persona routing
  - tests/test_email_templates.py: product_invite_template style="casual"
- Integration tests
  - tests/test_github_scraper.py: parse mock HTML extracts of GitHub issues and profiles
  - tests/test_leads_agent.py: end-to-end on mocked scraper results; DB persistence; filtering threshold
- E2E (manual/dev)
  - Run demo with --show-browser to validate GitHub scraping, selection, preview, and human-gated send

[Implementation Order]
Implement foundation first (types/DB/personas), then scraper/agent, then TUI and email, then tests.

1) Types and DB:
   - Add LeadStage enum and Lead model; add schemas LeadCreate/LeadResponse
2) Personas:
   - Add personas.py with Transcripta Quillborne; placeholders for other modalities; router select_persona
3) Email:
   - Add product_invite_template; extend email_agent with ProductInviteParams and compose/send tools
4) Scraper:
   - Implement GitHubIssuesScraper with issue list extraction and author enrichment (profile + website regex)
5) Scoring:
   - Implement extract_signals + calculate_novice_score; integrate into agent
6) Agent:
   - Implement github_leads_agent.prospect_github_issues(...) to orchestrate repos, scoring, persistence, filtering
7) TUI:
   - Update demo.py with GitHub prospecting flow: render, select, preview, confirm, send
8) Tests:
   - Add unit/integration tests; adjust CI if applicable
9) Docs:
   - Update README quickstart; note env/AgentMail sender identities and safety (human gate remains)
