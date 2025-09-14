# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Omics-OS Lead Generation System is an AI-powered multi-agent system that automates GitHub prospecting and personalized outreach for omics-os user acquisition. It identifies struggling bioinformatics users in scanpy/anndata repositories and converts them into omics-os prospects through persona-based casual outreach.

## Key Features

- **GitHub issues scraping with Browser-Use**
  - Targets scverse/scanpy and scverse/anndata repositories
  - Fast DOM navigation tuned for reliability
  - Structured outputs via Pydantic and result.structured_output
- **Novice user detection and scoring**
  - Multi-signal scoring algorithm (account age, followers, keywords, etc.)
  - Threshold-based lead qualification (score ≥0.6)
  - Contact information extraction from profiles and websites
- **Persona-based casual outreach via AgentMail**
  - Transcripta Quillborne (transcriptomics specialist) for scanpy/anndata users
  - Modular persona system expandable to other modalities
  - Problem-specific solution examples in emails
- **Human-gated email outreach** with approval workflow
- **Full provenance logging** for auditability
- **Rich TUI** for end-to-end GitHub prospecting demonstration

## Core Architecture

- **Backend**: FastAPI application with Pydantic AI agents
- **Agents**: GitHub leads agent, email agent with persona routing, scoring utilities
- **Integrations**: Browser-Use for GitHub scraping, AgentMail for multi-persona email automation
- **Database**: SQLAlchemy with SQLite (dev) / PostgreSQL (prod) with Lead tracking
- **TUI**: Rich-powered interactive terminal interface for GitHub prospecting demonstrations

## Common Development Commands

### Environment Setup
```bash
cd backend
pip install -r requirements.txt
```

### Install Chromium for Browser-Use
```bash
# Install Chromium for Browser-Use (if needed)
uvx playwright install chromium --with-deps --no-shell
```

### Running the Application
```bash
# FastAPI development server
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Alternative: direct execution
python backend/app/main.py

# Docker Compose (full stack)
docker-compose up --build
```

### Interactive Demo (TUI)
```bash
# Interactive terminal UI for GitHub prospecting (recommended)
cd backend && uv run python demo.py

# Prospect specific repositories with visible browsers
uv run python demo.py --repos "scverse/scanpy,scverse/anndata" --max-issues 25 --show-browser

# Run in demo mode with email sending enabled
uv run python demo.py --demo --show-browser --send-emails

# Adjust scoring threshold for lead qualification
uv run python demo.py --score-threshold 0.7 --max-issues 50
```

### Testing
```bash
cd backend
python -m pytest tests/ -v
python -m pytest tests/test_agents.py -v
python -m pytest tests/test_integrations.py -v
```

## GitHub Issues Prospecting Workflow

The system identifies potential omics-os users by analyzing GitHub issues in bioinformatics repositories, focusing on users showing signs of struggle with current tools.

### Prospecting Process:
1. **Issue Scraping:** Browser-Use navigates to repository issues pages (scanpy/anndata)
2. **Signal Extraction:** Analyzes issue titles, labels, and author profiles for novice indicators
3. **Contact Discovery:** Extracts email addresses from GitHub profiles and personal websites
4. **Scoring Algorithm:** Multi-factor scoring based on:
   - Account age (<1 year = higher score)
   - Follower count (<5 = higher score)
   - Repository count (<5 = higher score)
   - Novice keywords ("help", "install", "error", "beginner")
   - Missing code blocks in issues
   - Question/usage labels
5. **Lead Qualification:** Filters for score ≥0.6 and available email contact
6. **Database Persistence:** Stores qualified leads with full signal tracking

### Persona-Based Outreach:
- **Transcripta Quillborne:** Transcriptomics specialist for scanpy/anndata issues
- **Smart Routing:** Automatically selects appropriate persona based on repository and issue content
- **Tailored Messages:** Email examples specific to their exact problem (installation, data loading, plotting, etc.)
- **Casual Tone:** "hei I saw you were struggling..." empathetic approach

## Structured Outputs with Browser-Use

To make scraping robust, agents validate outputs with Pydantic and prefer `result.structured_output` when available.

### GitHub Issues scraping (`GitHubIssuesScraper`):
- Uses `output_model_schema=IssueSummaries` and consumes `result.structured_output`.
- Normalizes into strongly-typed fields (issue_number, issue_title, user_login, labels, etc.) with resilient fallbacks.
- Contact enrichment via profile and website scanning.

### Lead Generation (`github_leads_agent`):
- Uses structured scoring and filtering pipelines.
- Database persistence with upsert logic to prevent duplicates.
- Full provenance logging for audit trails.

This avoids brittle string parsing and makes downstream lead management stable.

## Environment Variables

### Required
- `OPENAI_API_KEY`: Enables Browser-Use LLM functionality (required for GitHub scraping)

### Optional (for full functionality)
- `AGENTMAIL_API_KEY`: Enables email automation via AgentMail
- `DATABASE_URL`: Database connection (defaults to SQLite)
- `REDIS_URL`: Redis connection for task queuing
- `CORS_ORIGINS`: Frontend origins for CORS (comma-separated)
- `DEBUG`: Enable debug mode (boolean)

### Persona Configuration (optional, defaults hardcoded)
- `OMICS_OS_URL`: URL for omics-os platform (default: https://www.omics-os.com)
- Persona email addresses should be configured in AgentMail for multi-sender support:
  - `transcripta@omics-os.com` for Transcripta Quillborne
  - `proteos@omics-os.com` for Proteos Maximus (future)
  - `genomus@omics-os.com` for Genomus Vitale (future)

## Key Components

### Agents (`backend/app/core/agents/`)
- `github_leads_agent.py`: GitHub prospecting workflow orchestration and lead qualification
- `email_agent.py`: Composes and sends persona-based outreach emails with safety checks

### Scrapers (`backend/app/core/scrapers/`)
- `github_issues_scraper.py`: GitHub issues and profile scraping via Browser-Use

### Utils (`backend/app/utils/`)
- `personas.py`: Persona definitions and routing (Transcripta Quillborne, etc.)
- `scoring.py`: Novice detection and lead scoring algorithms

### Integrations (`backend/app/core/integrations/`)
- `agentmail_client.py`: Multi-persona email automation and webhook handling

### API (`backend/app/api/v1/`)
- Lead endpoints for GitHub prospecting
- Outreach endpoints for persona-based email management
- Webhook endpoints for email reply handling
- Task monitoring endpoints

## Development Workflow

### Adding New Personas
1. Add persona definition in `backend/app/utils/personas.py`
2. Update persona routing logic in `github_leads_agent.py`
3. Configure email addresses in AgentMail for multi-sender support
4. Add tests for persona selection and email composition

### Adding New Target Repositories
1. Update repository list in GitHub scraping configuration
2. Adjust scoring algorithms for repository-specific signals
3. Test persona routing for new repository content
4. Update lead qualification thresholds if needed

### Adding New Scrapers
1. Create scraper in `backend/app/core/scrapers/`
2. Use Browser-Use framework with structured outputs
3. Implement safety checks and rate limiting
4. Test with `settings.DEBUG=True` for visible browsers

### Database Changes
1. Modify models in `backend/app/models/`
2. Create Alembic migration: `alembic revision --autogenerate -m "description"`
3. Apply migration: `alembic upgrade head`

## Safety & Compliance

- **Human Approval Gates**: Required for all email sending with preview and explicit confirmation
- **Provenance Logging**: All prospecting actions logged for audit trails
- **Rate Limiting**: Prevents GitHub API overload and anti-bot detection
- **Ethical Prospecting**: Respectful approach to open source community engagement

## API Endpoints

- `POST /api/v1/leads/prospect` - Initiate GitHub prospecting workflow
- `GET /api/v1/leads` - List qualified leads with scoring data
- `POST /api/v1/outreach` - Send persona-based outreach emails
- `POST /api/v1/webhooks/agentmail` - Receive email replies and conversion tracking
- `GET /api/v1/tasks/{id}` - Monitor async prospecting task progress

## Troubleshooting

### Browser-Use Issues
- **No browser window**: Use `--show-browser` and ensure `settings.DEBUG` is toggled by the demo automatically
- **Chromium missing**: Install via `uvx playwright install chromium --with-deps --no-shell`
- **Import errors**: Verify `browser-use>=0.1.0` installed
- **Timeouts**: Increase wait times or reduce `--max-issues`

### GitHub Issues
- **GitHub scraping fails**: System gracefully falls back to mock data for testing
- **Rate limiting**: Check Browser-Use logs for CDP connection issues and implement backoff
- **No qualified leads found**: Lower `--score-threshold` (try 0.4 instead of 0.6) or increase `--max-issues`
- **Contact extraction fails**: Check that target repositories have recent issues with profile information

### Agent Issues
- **OPENAI_API_KEY missing**: Set it in your shell or `.env` (required for GitHub scraping functionality)
- **OpenAI API errors**: Verify `OPENAI_API_KEY` is set correctly
- **Scoring issues**: Check signal extraction logic and qualification thresholds
- **Memory issues**: Agents are stateless; check prompt sizes

### Email Issues
- **Email sending fails**: Ensure `AGENTMAIL_API_KEY` is set and persona email addresses are configured
- **AgentMail failures**: Verify `AGENTMAIL_API_KEY` and webhook URLs
- **Delivery failures**: Check recipient addresses and email formatting
- **Persona routing errors**: Verify persona definitions and routing logic

### Database Issues
- **Migration failures**: Check Alembic versions and model consistency
- **Connection errors**: Verify `DATABASE_URL` format and permissions
- **Lead duplication**: Check upsert logic in lead persistence

## File Structure Context

```
backend/
├── app/
│   ├── api/v1/          # FastAPI endpoints for lead management and outreach
│   ├── core/
│   │   ├── agents/      # GitHub leads agent, email agents
│   │   ├── scrapers/    # GitHub issues scraper
│   │   ├── integrations/# AgentMail client
│   │   └── utils/       # Scoring, provenance utilities
│   ├── models/          # Lead models, schemas, enums
│   └── utils/           # Personas, email templates, scoring
├── tests/               # Unit and integration tests
├── demo.py              # GitHub prospecting TUI
└── main.py              # Simple backend entry point
```

## Testing Strategy

- **Unit Tests**: Individual agent and scraper functionality
- **Integration Tests**: GitHub prospecting workflow and email automation
- **TUI Testing**: Interactive demo for end-to-end GitHub prospecting validation
- **Safety Testing**: Human approval gates and email preview validation

## Performance Considerations

- **Parallel Execution**: GitHub scraping across multiple repositories concurrently
- **Caching**: Lead results cached to prevent duplicate processing
- **Rate Limiting**: Prevents overwhelming GitHub APIs and anti-bot detection
- **Timeout Management**: Configurable timeouts for Browser-Use operations

This system automates omics-os user acquisition through intelligent GitHub prospecting, with a focus on ethical prospecting practices, persona-based outreach, and respectful engagement with the open source community.