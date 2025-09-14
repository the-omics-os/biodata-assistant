# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Biodata Assistant is an AI-powered multi-agent system that automates cancer research data discovery and outreach. It reduces dataset triage from days to minutes by orchestrating live web scraping (GEO, LinkedIn), colleague discovery, and human-gated outreach.

## Key Features

- **Live GEO scraping with Browser-Use**
  - Fast DOM navigation tuned for reliability
  - Structured outputs via Pydantic and result.structured_output
- **LinkedIn colleague discovery**
  - Manual Login workflow (human-in-the-loop, no credential entry by the agent)
  - Public search fallback when a logged-in session is unavailable
- **Human-gated email outreach** via AgentMail (optional)
- **Full provenance logging** for auditability
- **Rich TUI** for end-to-end demonstration

## Core Architecture

- **Backend**: FastAPI application with Pydantic AI agents
- **Agents**: 5 specialized agents (planner, bio-database, colleagues, email, summarizer)
- **Integrations**: Browser-Use for web scraping, AgentMail for email automation
- **Database**: SQLAlchemy with SQLite (dev) / PostgreSQL (prod)
- **TUI**: Rich-powered interactive terminal interface for demonstrations

## Common Development Commands

### Environment Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
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
# Interactive terminal UI (recommended for testing)
python backend/demo.py

# Include LinkedIn search and show live browsers
python backend/demo.py --include-internal --show-browser

# Provide a research query and enable visible browsers
python backend/demo.py --query "TP53 lung adenocarcinoma RNA-seq" --max-results 3 --show-browser
```

### Testing
```bash
cd backend
python -m pytest tests/ -v
python -m pytest tests/test_agents.py -v
python -m pytest tests/test_integrations.py -v
```

## Manual LinkedIn Login Workflow (Human-in-the-Loop)

This repository uses a human-in-the-loop sign-in for LinkedIn. The agent will never type your credentials.

### Workflow:
1. The demo opens a persistent browser on https://www.linkedin.com/login.
2. You log in manually in the visible browser window.
3. In the TUI, press Enter to confirm you are signed in (keep the browser open).
4. The agent continues with the same session for company employee discovery.
5. If session reuse fails, the system falls back to public search automatically.

### Technical notes:
- The LinkedIn scraper uses a persistent user data directory at `./temp-profile-linkedin` so cookies survive across steps.
- Entry points:
  - `colleagues_agent.start_linkedin_login_session()` opens the login page and keeps the browser alive.
  - `colleagues_agent.search_linkedin_direct(..., use_existing_session=True)` reuses your logged-in session to extract contacts.
- Outreach flows that send connection requests/messages still require logged-in state and will be guarded.

## Structured Outputs with Browser-Use

To make scraping robust, agents validate outputs with Pydantic and prefer `result.structured_output` when available.

### GEO scraping (`GEOScraper`):
- Uses `output_model_schema=GEODatasets` and consumes `result.structured_output`.
- Normalizes into strongly-typed fields (accession, title, organism, modalities, sample_size, etc.) with resilient fallbacks.

### Colleagues agent (LinkedIn public browsing utility path):
- Uses `output_model_schema=Contacts` for Browser-Use helper agents.
- For deterministic direct search, returns normalized JSON in Python without free-form parsing.

This avoids brittle string parsing and makes downstream filtering and export stable.

## Environment Variables

### Required
- `OPENAI_API_KEY`: Enables Browser-Use LLM functionality (required for scraping)

### Optional (for full functionality)
- `AGENTMAIL_API_KEY`: Enables email automation via AgentMail
- `DATABASE_URL`: Database connection (defaults to SQLite)
- `REDIS_URL`: Redis connection for task queuing
- `CORS_ORIGINS`: Frontend origins for CORS (comma-separated)
- `DEBUG`: Enable debug mode (boolean)

### LinkedIn-specific (only if using outreach or agentic login fallback)
- `LINKEDIN_COMPANY_URL`: The company page to navigate to employees when logged in
- `LINKEDIN_EMAIL`, `LINKEDIN_PW`: Not required for manual login; only used by explicit outreach/agentic flows

### Demo-specific (TUI defaults)
- `REQUESTER_NAME`: Default requester name for outreach
- `REQUESTER_EMAIL`: Default requester email
- `REQUESTER_TITLE`: Default requester title
- `COMPANY_NAME`: Company name for LinkedIn searches

## Key Components

### Agents (`backend/app/core/agents/`)
- `planner_agent.py`: Analyzes research queries and creates workflow plans
- `biodatabase_agent.py`: Searches biological databases (GEO, PRIDE, Ensembl)
- `colleagues_agent.py`: Finds internal colleagues via LinkedIn
- `email_agent.py`: Composes and sends outreach emails with safety checks
- `summarizer_agent.py`: Generates executive summaries and reports

### Scrapers (`backend/app/core/scrapers/`)
- `geo_scraper.py`: NCBI/GEO database scraping via Browser-Use
- `linkedin_scraper.py`: LinkedIn colleague discovery

### Integrations (`backend/app/core/integrations/`)
- `agentmail_client.py`: Email automation and webhook handling

### API (`backend/app/api/v1/`)
- Search endpoints for dataset discovery
- Outreach endpoints for email management
- Webhook endpoints for email reply handling
- Task monitoring endpoints

## Development Workflow

### Adding New Agents
1. Create agent file in `backend/app/core/agents/`
2. Follow Pydantic AI pattern with typed tools
3. Register in `agent_orchestrator.py`
4. Add tests in `backend/tests/test_agents.py`

### Adding New Scrapers
1. Create scraper in `backend/app/core/scrapers/`
2. Use Browser-Use framework with Puppeteer
3. Implement safety checks and rate limiting
4. Test with `settings.DEBUG=True` for visible browsers

### Database Changes
1. Modify models in `backend/app/models/`
2. Create Alembic migration: `alembic revision --autogenerate -m "description"`
3. Apply migration: `alembic upgrade head`

## Safety & Compliance

- **PHI Detection**: Automated scanning for clinical/patient data indicators
- **Human Approval Gates**: Required for sensitive content before email sending
- **Provenance Logging**: All actions logged for audit trails
- **Rate Limiting**: Prevents API overload and anti-bot detection

## API Endpoints

- `POST /api/v1/search` - Initiate dataset search workflow
- `GET /api/v1/search/{task_id}` - Check search task status
- `GET /api/v1/datasets` - List discovered datasets
- `POST /api/v1/outreach` - Send outreach emails
- `POST /api/v1/webhooks/agentmail` - Receive email replies
- `GET /api/v1/tasks/{id}` - Monitor async task progress

## Troubleshooting

### Browser-Use Issues
- **No browser window**: Use `--show-browser` and ensure `settings.DEBUG` is toggled by the demo automatically
- **Chromium missing**: Install via `uvx playwright install chromium --with-deps --no-shell`
- **Import errors**: Verify `browser-use>=0.1.0` installed
- **Timeouts**: Increase wait times or reduce `max_results`

### LinkedIn Issues
- **LinkedIn anti-bot friction**: Use manual login as recommended (the default), or proceed with public search fallback
- **Session failures**: The system automatically falls back to public search if logged-in session reuse fails
- **Login issues**: Keep the browser window open during the manual login process

### Agent Issues
- **OPENAI_API_KEY missing**: Set it in your shell or `.env` (the TUI will warn and can continue in reduced functionality)
- **OpenAI API errors**: Verify `OPENAI_API_KEY` is set correctly
- **Rate limiting**: Implement exponential backoff in agent calls
- **Memory issues**: Agents are stateless; check prompt sizes

### Email Issues
- **AgentMail failures**: Verify `AGENTMAIL_API_KEY` and webhook URLs
- **PHI blocking**: Review approval queue for sensitive content flags
- **Delivery failures**: Check recipient addresses and email formatting

### Database Issues
- **Migration failures**: Check Alembic versions and model consistency
- **Connection errors**: Verify `DATABASE_URL` format and permissions

## File Structure Context

```
backend/
├── app/
│   ├── api/v1/          # FastAPI endpoints and routing
│   ├── core/
│   │   ├── agents/      # Pydantic AI agent implementations
│   │   ├── scrapers/    # Browser-Use scraper implementations
│   │   ├── integrations/# External service clients (AgentMail)
│   │   └── utils/       # Utilities (provenance, safety checks)
│   ├── models/          # SQLAlchemy models and Pydantic schemas
│   └── utils/           # Application utilities and exceptions
├── tests/               # Unit and integration tests
├── demo.py              # Interactive TUI for end-to-end testing
└── main.py              # Simple backend entry point
```

## Testing Strategy

- **Unit Tests**: Individual agent and scraper functionality
- **Integration Tests**: Agent orchestration and external API calls
- **TUI Testing**: Interactive demo for end-to-end workflow validation
- **Safety Testing**: PHI detection and approval gate validation

## Performance Considerations

- **Parallel Execution**: Agents run database searches concurrently
- **Caching**: Results cached for 30 minutes to reduce redundant searches
- **Rate Limiting**: Prevents overwhelming external APIs
- **Timeout Management**: Configurable timeouts for scraping operations

This system was developed for a hackathon to solve real pain points in cancer research data discovery, with a focus on compliance, safety, and time reduction from days to minutes.