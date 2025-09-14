# Biodata Assistant

AI-powered multi-agent system that automates cancer research data discovery and outreach. It reduces dataset triage from days to minutes by orchestrating live web scraping (GEO, LinkedIn), colleague discovery, and human-gated outreach.

## Key Features

- Live GEO scraping with Browser-Use
  - Fast DOM navigation tuned for reliability
  - Structured outputs via Pydantic and result.structured_output
- LinkedIn colleague discovery
  - Manual Login workflow (human-in-the-loop, no credential entry by the agent)
  - Public search fallback when a logged-in session is unavailable
- Human-gated email outreach via AgentMail (optional)
- Full provenance logging for auditability
- Rich TUI for end-to-end demonstration

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

Launch the Rich-powered TUI:
```
python backend/demo.py
```

Common flags:
```
# Include LinkedIn search and show live browsers
python backend/demo.py --include-internal --show-browser

# Provide a research query and enable visible browsers
python backend/demo.py --query "TP53 lung adenocarcinoma RNA-seq" --max-results 3 --show-browser
```

## Manual LinkedIn Login Workflow (Human-in-the-Loop)

This repository uses a human-in-the-loop sign-in for LinkedIn. The agent will never type your credentials.

Workflow:
1. The demo opens a persistent browser on https://www.linkedin.com/login.
2. You log in manually in the visible browser window.
3. In the TUI, press Enter to confirm you are signed in (keep the browser open).
4. The agent continues with the same session for company employee discovery.
5. If session reuse fails, the system falls back to public search automatically.

Technical notes:
- The LinkedIn scraper uses a persistent user data directory at `./temp-profile-linkedin` so cookies survive across steps.
- Entry points:
  - `colleagues_agent.start_linkedin_login_session()` opens the login page and keeps the browser alive.
  - `colleagues_agent.search_linkedin_direct(..., use_existing_session=True)` reuses your logged-in session to extract contacts.
- Outreach flows that send connection requests/messages still require logged-in state and will be guarded.

## Structured Outputs with Browser-Use

To make scraping robust, agents validate outputs with Pydantic and prefer `result.structured_output` when available.

- GEO scraping (`GEOScraper`):
  - Uses `output_model_schema=GEODatasets` and consumes `result.structured_output`.
  - Normalizes into strongly-typed fields (accession, title, organism, modalities, sample_size, etc.) with resilient fallbacks.

- Colleagues agent (LinkedIn public browsing utility path):
  - Uses `output_model_schema=Contacts` for Browser-Use helper agents.
  - For deterministic direct search, returns normalized JSON in Python without free-form parsing.

This avoids brittle string parsing and makes downstream filtering and export stable.

## Environment Variables

Required:
- `OPENAI_API_KEY` — enables Browser-Use LLMs

Optional (only if using outreach or agentic login fallback):
- `AGENTMAIL_API_KEY` — for sending emails via AgentMail
- `LINKEDIN_COMPANY_URL` — the company page to navigate to employees when logged in
- `LINKEDIN_EMAIL`, `LINKEDIN_PW` — not required for manual login; only used by explicit outreach/agentic flows

Convenience (TUI defaults):
- `REQUESTER_NAME`, `REQUESTER_EMAIL`, `REQUESTER_TITLE`
- `COMPANY_NAME`

## Troubleshooting

- No browser window:
  - Use `--show-browser` and ensure `settings.DEBUG` is toggled by the demo automatically
- Chromium missing:
  - Install via `uvx playwright install chromium --with-deps --no-shell`
- LinkedIn anti-bot friction:
  - Use manual login as recommended (the default), or proceed with public search fallback
- OPENAI_API_KEY missing:
  - Set it in your shell or `.env` (the TUI will warn and can continue in reduced functionality)

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
