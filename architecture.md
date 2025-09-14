# Biodata Assistant - System Architecture

## Overview
Biodata Assistant is a multi-agent system designed to automate cancer research data discovery and outreach workflows. It reduces the time researchers spend finding biological datasets from 2-3 days to minutes by automating database searches, colleague discovery, and email outreach.

## Core Problem Solved
Cancer researchers (bioinformaticians, data scientists, ML engineers) need to:
1. Search multiple biological databases (GEO, PRIDE, Ensembl)
2. Find internal colleagues who might have relevant data
3. Write and send outreach emails to request data access
4. Track responses and manage the workflow

## System Components

### 1. Backend Infrastructure (FastAPI)
- **Location**: `/backend`
- **Technology**: Python 3.10+, FastAPI, SQLAlchemy, Pydantic
- **Purpose**: RESTful API server providing endpoints for search, dataset management, and outreach

### 2. Multi-Agent System (Pydantic AI)
- **Framework**: Pydantic AI with typed agents
- **Agents**: 5 specialized agents for different workflow steps
- **Orchestration**: Central orchestrator coordinates agent interactions

### 3. External Integrations
- **Browser-Use**: Web scraping for NCBI/GEO and LinkedIn
- **AgentMail**: Email automation and webhook handling
- **Database**: SQLite (dev) / PostgreSQL (prod)

## Knowledge Graph - System Relationships

### Backend Infrastructure Relationships
```
# API Layer
FastAPI -> hosts -> APIRouter
APIRouter -> contains -> SearchEndpoint
APIRouter -> contains -> DatasetEndpoint
APIRouter -> contains -> OutreachEndpoint
APIRouter -> contains -> TaskEndpoint
APIRouter -> contains -> WebhookEndpoint

SearchEndpoint -> triggers -> AgentOrchestrator
DatasetEndpoint -> manages -> DatasetCRUD
OutreachEndpoint -> manages -> OutreachRequests
TaskEndpoint -> tracks -> BackgroundTasks
WebhookEndpoint -> receives -> EmailReplies

# Database Layer
SQLAlchemy -> manages -> DatabaseModels
DatabaseModels -> includes -> UserModel
DatabaseModels -> includes -> DatasetModel
DatabaseModels -> includes -> OutreachRequestModel
DatabaseModels -> includes -> ProvenanceModel
DatabaseModels -> includes -> TaskModel

UserModel -> represents -> ResearcherProfile
DatasetModel -> stores -> BiologicalDatasets
OutreachRequestModel -> tracks -> EmailOutreach
ProvenanceModel -> logs -> AuditTrail
TaskModel -> monitors -> AsyncOperations

# Configuration Layer
Config -> provides -> EnvironmentVariables
Config -> manages -> APIKeys
Config -> defines -> DatabaseURL
Config -> sets -> CORSOrigins
```

### Agent System Relationships
```
# Agent Hierarchy
AgentOrchestrator -> coordinates -> PlannerAgent
AgentOrchestrator -> coordinates -> BioDatabaseAgent
AgentOrchestrator -> coordinates -> ColleaguesAgent
AgentOrchestrator -> coordinates -> EmailAgent
AgentOrchestrator -> coordinates -> SummarizerAgent

# Planner Agent
PlannerAgent -> analyzes -> ResearchQuery
PlannerAgent -> identifies -> DataModalities
PlannerAgent -> creates -> WorkflowPlan
PlannerAgent -> detects -> CancerKeywords
ResearchQuery -> contains -> P53Mutations
ResearchQuery -> contains -> LungAdenocarcinoma
ResearchQuery -> contains -> TNBC

# Bio-Database Agent
BioDatabaseAgent -> uses -> BrowserUse
BioDatabaseAgent -> searches -> NCBIGEO
BioDatabaseAgent -> searches -> PRIDE
BioDatabaseAgent -> searches -> Ensembl
BioDatabaseAgent -> extracts -> DatasetMetadata
BioDatabaseAgent -> evaluates -> DatasetRelevance
NCBIGEO -> provides -> GeneExpressionData
PRIDE -> provides -> ProteomicsData
Ensembl -> provides -> GenomicsData

# Colleagues Agent  
ColleaguesAgent -> uses -> BrowserUse
ColleaguesAgent -> searches -> LinkedIn
ColleaguesAgent -> finds -> InternalExperts
ColleaguesAgent -> generates -> EmailSuggestions
InternalExperts -> worksIn -> Bioinformatics
InternalExperts -> worksIn -> Genomics
InternalExperts -> worksIn -> Oncology

# Email Agent
EmailAgent -> uses -> AgentMailSDK
EmailAgent -> composes -> ProfessionalEmails
EmailAgent -> sends -> OutreachRequests
EmailAgent -> checks -> ApprovalRequirements
EmailAgent -> flags -> PHIContent
OutreachRequests -> requestsAccess -> RestrictedDatasets
PHIContent -> requires -> HumanApproval

# Summarizer Agent
SummarizerAgent -> consolidates -> SearchResults
SummarizerAgent -> analyzes -> DatasetQuality
SummarizerAgent -> generates -> ExecutiveSummary
SummarizerAgent -> prepares -> ExportData
ExecutiveSummary -> includes -> Recommendations
ExportData -> formats -> CSV
ExportData -> formats -> Excel
```

### External Integration Relationships
```
# Browser-Use Integration
GEOScraper -> implements -> BrowserUseAgent
GEOScraper -> navigates -> NCBIWebsite
GEOScraper -> extracts -> DatasetAccession
GEOScraper -> extracts -> SampleSize
GEOScraper -> extracts -> ContactInfo
LinkedInScraper -> implements -> BrowserUseAgent
LinkedInScraper -> searches -> CompanyEmployees
LinkedInScraper -> extracts -> JobTitles
LinkedInScraper -> calculates -> RelevanceScore

# AgentMail Integration
AgentMailClient -> wraps -> AsyncAgentMail
AgentMailClient -> sends -> EmailMessages
AgentMailClient -> handles -> DeliveryStatus
AgentMailClient -> processes -> EmailReplies
WebhookReceiver -> verifies -> Signatures
WebhookReceiver -> updates -> OutreachStatus
WebhookReceiver -> logs -> Provenance

# Database Relationships
Dataset -> hasAccessType -> Public
Dataset -> hasAccessType -> Request
Dataset -> hasAccessType -> Restricted
Dataset -> hasModality -> Transcriptomics
Dataset -> hasModality -> Proteomics
Dataset -> hasModality -> Genomics
OutreachRequest -> hasStatus -> Pending
OutreachRequest -> hasStatus -> Sent
OutreachRequest -> hasStatus -> Replied
```

### Workflow Relationships
```
# Main Workflow
UserQuery -> triggers -> WorkflowExecution
WorkflowExecution -> step1 -> UnderstandQuery
WorkflowExecution -> step2 -> SearchDatabases
WorkflowExecution -> step3 -> FindColleagues
WorkflowExecution -> step4 -> EvaluateResults
WorkflowExecution -> step5 -> SendOutreach
WorkflowExecution -> step6 -> GenerateSummary

# Step Details
UnderstandQuery -> uses -> PlannerAgent
UnderstandQuery -> produces -> WorkflowPlan
SearchDatabases -> parallelizes -> DatabaseSearches
SearchDatabases -> uses -> BioDatabaseAgent
FindColleagues -> uses -> ColleaguesAgent
FindColleagues -> searches -> InternalNetwork
EvaluateResults -> categorizes -> Datasets
EvaluateResults -> prioritizes -> OutreachTargets
SendOutreach -> uses -> EmailAgent
SendOutreach -> respects -> ApprovalWorkflow
GenerateSummary -> uses -> SummarizerAgent
GenerateSummary -> creates -> FinalReport

# Safety & Compliance
SafetyChecker -> detects -> PHIIndicators
SafetyChecker -> flags -> SensitiveData
SafetyChecker -> requires -> ExecutiveApproval
ProvenanceLogger -> tracks -> AllActions
ProvenanceLogger -> maintains -> AuditTrail
ProvenanceLogger -> ensures -> Compliance
```

## Directory Structure
```
biodata-assistant/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API endpoints
│   │   ├── core/
│   │   │   ├── agents/       # Pydantic AI agents
│   │   │   ├── scrapers/     # Browser-Use implementations
│   │   │   ├── integrations/ # AgentMail client
│   │   │   └── utils/        # Utilities (provenance, etc.)
│   │   ├── models/           # Database models & schemas
│   │   └── utils/            # Email templates, exceptions
│   ├── tests/                # Unit and integration tests
│   ├── requirements.txt      # Python dependencies
│   └── docker-compose.yml    # Container orchestration
├── phase_*.md                # Implementation plans
└── *-doc.md                  # Documentation files
```

## Data Flow

### Search Request Flow
```
1. User -> submits -> SearchQuery
2. SearchEndpoint -> creates -> Task
3. Task -> triggers -> AgentOrchestrator
4. AgentOrchestrator -> executes -> PlannerAgent
5. PlannerAgent -> creates -> WorkflowPlan
6. AgentOrchestrator -> parallelizes -> SearchAgents
7. BioDatabaseAgent -> scrapes -> NCBIGEO
8. ColleaguesAgent -> scrapes -> LinkedIn
9. Results -> stored -> Database
10. EmailAgent -> sends -> OutreachEmails
11. SummarizerAgent -> generates -> Report
12. Report -> returned -> User
```

### Email Outreach Flow
```
1. Dataset -> requires -> AccessRequest
2. EmailAgent -> composes -> OutreachEmail
3. SafetyChecker -> validates -> EmailContent
4. ApprovalRequired? -> queues -> HumanReview
5. Approved -> sends -> AgentMail
6. AgentMail -> delivers -> Email
7. Recipient -> replies -> Email
8. Webhook -> receives -> Reply
9. WebhookHandler -> updates -> OutreachStatus
10. User -> notified -> ReplyReceived
```

## Key Technologies

### Core Stack
- **Backend**: FastAPI (Python 3.10+)
- **Database**: SQLAlchemy + SQLite/PostgreSQL
- **Validation**: Pydantic
- **Agents**: Pydantic AI
- **Scraping**: Browser-Use
- **Email**: AgentMail SDK
- **Container**: Docker + Docker Compose

### Agent Technologies
- **LLM Provider**: OpenAI GPT-4o / Anthropic Claude
- **Agent Framework**: Pydantic AI with typed tools
- **Browser Automation**: Browser-Use with Puppeteer
- **Email Service**: AgentMail API

## Security & Compliance

### PHI Protection
```
PHIDetector -> scans -> DatasetTitles
PHIDetector -> scans -> EmailContent
PHIDetector -> triggers -> ApprovalWorkflow
ApprovalWorkflow -> requires -> HumanReview
ApprovalWorkflow -> logs -> DecisionProvenance
```

### Audit Trail
```
Every action -> logged -> ProvenanceTable
ProvenanceTable -> contains -> Actor
ProvenanceTable -> contains -> Action
ProvenanceTable -> contains -> Timestamp
ProvenanceTable -> contains -> ResourceID
ProvenanceTable -> enables -> Compliance
```

## Performance Optimizations

### Caching
```
ResultCache -> stores -> SearchResults
ResultCache -> reduces -> RedundantSearches
ResultCache -> expires -> After30Minutes
```

### Parallel Processing
```
ParallelExecutor -> limits -> ConcurrentTasks
ParallelExecutor -> manages -> RateLimiting
ParallelExecutor -> prevents -> APIOverload
```

## Testing Strategy

### Test Coverage
```
UnitTests -> cover -> Agents
UnitTests -> cover -> Scrapers
IntegrationTests -> cover -> Workflow
IntegrationTests -> cover -> EmailFlow
E2ETests -> cover -> UserJourney
E2ETests -> validate -> TimeReduction
```

## Deployment Configuration

### Docker Services
```
DockerCompose -> orchestrates -> Backend
DockerCompose -> orchestrates -> Database
DockerCompose -> orchestrates -> Redis
Backend -> depends -> Database
Backend -> depends -> Redis
Frontend -> connects -> BackendAPI
```

## Success Metrics

### Key Performance Indicators
```
TimeReduction -> from -> 2-3Days
TimeReduction -> to -> Minutes
DatasetDiscovery -> increases -> 10x
OutreachAutomation -> saves -> 95%Time
ComplianceMaintained -> equals -> 100%
```

## API Endpoints Summary

### Core Endpoints
- `POST /api/v1/search` - Initiate dataset search
- `GET /api/v1/search/{task_id}` - Check search status
- `GET /api/v1/datasets` - List discovered datasets
- `POST /api/v1/outreach` - Send outreach emails
- `POST /api/v1/webhooks/agentmail` - Receive email replies
- `GET /api/v1/tasks/{id}` - Monitor async tasks

## Environment Variables

### Required Configuration
```
OPENAI_API_KEY -> enables -> LLMAgents
AGENTMAIL_API_KEY -> enables -> EmailAutomation
DATABASE_URL -> connects -> PostgreSQL
REDIS_URL -> enables -> TaskQueue
CORS_ORIGINS -> allows -> FrontendAccess
```

## Future Enhancements

### Planned Features
```
WebInterface -> provides -> UserDashboard
RealtimeUpdates -> via -> WebSockets
MLRanking -> improves -> DatasetRelevance
AutoFollowup -> handles -> NoReplies
IntegrationAPI -> exports -> OmicsOS
```

## Troubleshooting Guide

### Common Issues
```
BrowserTimeout -> increase -> WaitTime
EmailNotSent -> check -> AgentMailKey
NoResults -> verify -> SearchQuery
PHIBlocked -> review -> ApprovalQueue
RateLimited -> implement -> Backoff
```

## Contact & Support

This system was developed for the CodeRabbit hackathon to solve real pain points in cancer research data discovery. The architecture is designed to be extensible, compliant, and performant while maintaining a clear separation of concerns.

---

**Note**: This architecture document uses triplet syntax (subject-predicate-object) throughout to facilitate knowledge graph construction and make relationships explicit for automated parsing and understanding.
