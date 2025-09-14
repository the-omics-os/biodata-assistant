# Omics-OS Lead Generation System

AI-powered multi-agent system that automates GitHub prospecting and personalized outreach for omics-os user acquisition. It identifies struggling bioinformatics users in scanpy/anndata repositories and converts them into omics-os prospects through persona-based casual outreach.

## Key Features

- GitHub issues scraping with Browser-Use
  - Targets scverse/scanpy and scverse/anndata repositories
  - Fast DOM navigation tuned for reliability
  - Structured outputs via Pydantic and result.structured_output
- Novice user detection and scoring
  - Multi-signal scoring algorithm (account age, followers, keywords, etc.)
  - Threshold-based lead qualification (score ≥0.6)
  - Contact information extraction from profiles and websites
- Persona-based casual outreach via AgentMail
  - Transcripta Quillborne (transcriptomics specialist) for scanpy/anndata users
  - Modular persona system expandable to other modalities
  - Problem-specific solution examples in emails
- Human-gated email outreach with approval workflow
- Full provenance logging for auditability
- Rich TUI for end-to-end GitHub prospecting demonstration

## Requirements

- Python 3.10+
- macOS/Linux recommended (Windows may work with additional setup)
- OPENAI_API_KEY (for Browser-Use LLM)
- Optional (only if sending emails): AGENTMAIL_API_KEY

Install dependencies:
```
pip install -r backend/requirements.txt
```

Install Chromium for Browser-Use (if needed):
```
uvx playwright install chromium --with-deps --no-shell
```

## Quickstart (Interactive Demo)

Launch the Rich-powered TUI for GitHub prospecting:
```
cd backend && uv run python demo.py
```

Common flags:
```
# Prospect specific repositories with visible browsers
uv run python demo.py --repos "scverse/scanpy,scverse/anndata" --max-issues 25 --show-browser

# Run in demo mode with email sending enabled
uv run python demo.py --demo --show-browser --send-emails

# Adjust scoring threshold for lead qualification
uv run python demo.py --score-threshold 0.7 --max-issues 50
```

## GitHub Issues Prospecting Workflow

The system identifies potential omics-os users by analyzing GitHub issues in bioinformatics repositories. It focuses on users showing signs of struggle with current tools.

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

- GitHub Issues scraping (`GitHubIssuesScraper`):
  - Uses `output_model_schema=IssueSummaries` and consumes `result.structured_output`
  - Normalizes into strongly-typed fields (issue_number, issue_title, user_login, labels, etc.) with resilient fallbacks
  - Contact enrichment via profile and website scanning

- Lead Generation (`github_leads_agent`):
  - Uses structured scoring and filtering pipelines
  - Database persistence with upsert logic to prevent duplicates
  - Full provenance logging for audit trails

This avoids brittle string parsing and makes downstream lead management stable.

## Environment Variables

Required:
- `OPENAI_API_KEY` — enables Browser-Use LLMs for GitHub scraping

Optional (only if sending outreach emails):
- `AGENTMAIL_API_KEY` — for sending persona-based emails via AgentMail
- `OMICS_OS_URL` — URL for omics-os platform (default: https://www.omics-os.com)

Persona Configuration (optional, defaults hardcoded):
- Persona email addresses should be configured in AgentMail for multi-sender support
- `transcripta@omics-os.com` for Transcripta Quillborne
- `proteos@omics-os.com` for Proteos Maximus (future)
- `genomus@omics-os.com` for Genomus Vitale (future)

## Troubleshooting

- No browser window:
  - Use `--show-browser` and ensure `settings.DEBUG` is toggled by the demo automatically
- Chromium missing:
  - Install via `uvx playwright install chromium --with-deps --no-shell`
- GitHub scraping fails:
  - System gracefully falls back to mock data for testing
  - Check Browser-Use logs for CDP connection issues
- No qualified leads found:
  - Lower `--score-threshold` (try 0.4 instead of 0.6)
  - Increase `--max-issues` per repository
  - Check that target repositories have recent issues with struggling users
- OPENAI_API_KEY missing:
  - Set it in your shell or `.env` (required for GitHub scraping functionality)
- Email sending fails:
  - Ensure AGENTMAIL_API_KEY is set and valid
  - Verify persona email addresses are configured in AgentMail
  - Check network connectivity and AgentMail service status

## Project Structure

```
biodata-assistant/
├── backend/
│   ├── app/                  # FastAPI app, agents, scrapers, integrations
│   ├── tests/                # Unit and integration tests
│   ├── requirements.txt      # Python dependencies
│   └── demo.py               # End-to-end interactive TUI
├── architecture.md           # System architecture and diagrams
├── README.md                 # This file
└── *.md                      # Additional docs
```

## License

See `LICENSE`.
