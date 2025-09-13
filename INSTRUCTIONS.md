The project 'biodata-assistant' is solving the pain-points of a data scientist, ml engineer or bioinformatician in a biotech or pharma company. The user workflow is shown below and is the most important priority of this project. Everything that we do is to solve this painpoint: 
```
user profile: 
I am a researcher at a biotech/pharma/bio AI company. I'm working with biological data. Biological data could consists of genomics, transcriptomics, proteomics, imaging, microbiome data. I have a new project and my task is to combine datasets to answer my research question. I am usually a bioinformatician, data scientists or ml engineer. VERY IMPORTANT = I WORK IN CANCER RESEARCH!!
my usual journey: 
Normally if I'm a bigger company I would check the internal database which is normally just a onedrive or google drive but I dont have access. But first I would have to reach out to the colleague that would be responsible for this kind of data. For this I have to check who is responsible in this wet-lab department (done via Linkedin). I would have to find out their email adress and reach out to them manually asking them if they could send me the data. This is tedious and takes time as I might have to reach out to multiple people. 
Simultaniously I want to check what datasets are out there. This is normaly done via different checking different publically available biobanks (GEO, pride, useast.ensembl [genome], fungi.ensembl [fungi], microbiomedb), search the databases. The easiest to start with would be 'https://www.ncbi.nlm.nih.gov/'  . Sometimes I need to send an email to these collegues to ask them to send me the dataset as they do not provide it directly. 
After doing my initial search I would write down all the fitting datasets in an excel so that I can harmonize them. 

Conclusion: 
As you can see there are multiple tedious steps from reaching out to people, waiting for their responses, searching databases manually, identfying data, writing them down, figuring out if they fit my target goal. 

{
  "user_flow": [
    {
      "step": "Researcher starts new project",
      "input": "Research question (P53 behavior in lung adenocarcinoma)",
      "tasks": [
        "Understand the research question deeply and understand the data requirement.",
        "Confirm the research question and the data requirements with user to align with him",
        "Generate a plan with the steps for the user to confirm before I begin. In this plan I would show which databases I would search, how I would search the departments in the company and which external people I would contact"
      ]
    },
    {
      "step": "Internal collegues: Identify internal dataset owners",
      "input": "Dataset modality and type",
      "tasks": [
        "Check my company via Linkedin, search the employees and the fitting roles",
        "Match researchers/lab owners by department or title",
        "Return list of potential contacts with emails or names",
        "Store contact info in temporary database to get confirmation of the user whom to reach out to",
        "Update provenance log"
      ]
    },
    {
      "step": "Internal collegues: Prepare outreach for internal collegues asking for data availability",
      "input": "Dataset ID + Contact Info + User identity",
      "tasks": [
        "Generate professional email from template (presenting yourself, mentioning what department you are from etc)",
        "Insert dataset metadata (requiremenets) and project context",
        "Queue email for review if flagged as sensitive/PHI, send once the user confirms",
        "Store outreach request in database",
        "Update provenance log"
      ]
    },
    {
      "step": "Internal collegues: Send email to collegue",
      "input": "Approved email request",
      "tasks": [
        "Send via AgentMail API",
        "Attach unique outreach_id / thread_id metadata",
        "Record delivery status (queued → sent → delivered)",
        "Update provenance log"
      ]
    },    
    {
      "step": "Public datasets: Search public datasets",
      "input": "Curated and optimized query based on user interaction",
      "tasks": [
        "Trigger Browser-Use microservice (use the https://www.ncbi.nlm.nih.gov/ website) to use the searchbar, select the right database",
        "Go through the search result list and extract the datasets or links which fit with the topic.",
        "for the ones that fit, Open the search result links (example https://www.ncbi.nlm.nih.gov/gds/?term=lung+adenocarcinoma+P53) and check if this dataset would fit, extract conctact information from author",
        "Make a structured entry in the tmp database to return to the user for confirmation to download",
        "Store candidate datasets in database",
        "Update provenance log"
      ]
    },
    {
      "step": "Public datasets: Prepare outreach for public datasets which do not contain a processed dataset (raw instead of .txt file for example in single cell transcriptomics)",
      "input": "Dataset ID + Contact Info + User identity",
      "tasks": [
        "Generate professional outreach email from template",
        "Insert dataset metadata and project context",
        "Queue email for review if flagged as sensitive/PHI, send once the user confirms",
        "Store outreach request in database",
        "Update provenance log"
      ]
    },
    {
      "step": "Public datasets: Send outreach to author",
      "input": "Approved outreach request",
      "tasks": [
        "Send via AgentMail API",
        "Attach unique outreach_id / thread_id metadata",
        "Record delivery status (queued → sent → delivered)",
        "Update provenance log"
      ]
    },
    {
      "step": "Public datasets AND Internal collegues: Handle replies",
      "input": "AgentMail webhook event (reply, attachment, bounce, etc.)",
      "tasks": [
        "Map reply to outreach_request via metadata",
        "Update status (replied, attachment received, closed)",
        "Store reply content or attachment reference",
        "Flag attachments for manual approval if sensitive",
        "Update provenance log"
      ]
    },
    {
      "step": "User cockpit: Harmonize and present datasets",
      "input": "All collected dataset candidates (public + internal) in the typescript frontend",
      "tasks": [
        "Based on all previous steps present all the identified datasets in a nice way",
        "The user then makes the decisions in this overview dashboard. He can confirm outreaches, confirm further analysis",
        "Provide structured view in frontend",
        "Enable actions (Open dataset, Request access, Mark as received)"
      ]
    },
    {
      "step": "Finalize research input",
      "input": "Curated shortlist of datasets",
      "tasks": [
        "Export to Excel/CSV for harmonization",
        "Allow researcher to transfer the shortlist to 3th parties like the app 'omics-os' which allows them to analyze the data",
        "Close provenance log with summary"
      ]
    }
  ]
}
```


---

PROJECT: Omics Outreach Teammate (hackathon version)
AUTHOR: Assistant (spec)
PURPOSE: Step-by-step, comprehensive instructions to implement the Omics Outreach Teammate.
STACK:
  - Backend: Python 3.10+ (FastAPI)
  - Frontend: TypeScript (React/Adaptive Cards, overview of current status of the agentic system)
  - Secondary service: Node.js microservice for Browser-Use scraping
  - DB: SQLite for hackathon
  - Email: AgentMail API
  - Internal workplace environemnt: Linkedin via browser-use
  - Containerization: Docker + Docker Compose

------------------------------------------------------------------------------
OVERVIEW (one-liner)
------------------------------------------------------------------------------
Build a multi-agent workflow that:
  1) Searches public biobanks (NCBI/GEO, PRIDE, Ensembl, etc.) via Browser-Use,
  2) Finds internal owners of relevant data using Microsoft Graph (or a mock directory),
  3) Sends structured outreach emails via AgentMail,
  4) Consolidates results into a harmonized dataset shortlist and shows it in the frontend

Primary user flow (MVP):
  - Researcher issues query in Teams (e.g., "TNBC single-cell + proteomics datasets"),
  - System runs public search, finds candidate datasets,
  - Check linkedin to find responsible colleagues for internal data,
  - System drafts and sends outreach emails (AgentMail) and logs requests,
  - System posts results and action buttons (e.g., "Resend", "Open dataset", "Mark as received")

IMPORTANT SAFETY & COMPLIANCE
  - Add a hard-coded human-approval gating rule for "sensitive" dataset types.
  - Log every outreach with provenance: who asked, when, content, recipients, and approvals.

------------------------------------------------------------------------------
ARCHITECTURE (component summary)
------------------------------------------------------------------------------
1) Frontend (TypeScript)
   - Conversational UI, Adaptive Cards, action buttons.
   - Calls Python Backend REST endpoints.
   - Is like the cockpit for the user to oversee the process and do action steps like confirming steps etc

2) Python Backend (FastAPI)
   - REST APIs: search, find_contact, send_outreach, get_status, webhook_receiver etc. Is the agentic base.
   - Task queue worker (Celery) runs long tasks (Browser-Use jobs, large scrapes, retries).
   - Integrations: AgentMail SDK/REST, Microsoft Graph (msal), DB

3) Agentic core (pydantic)
    - The agentic core is based on the pydantic framework and is explain here: ./pydantic_doc.md
    - the agentic system contains the agents: planner-agent, collegues-agent, email-agent, bio-database-agent, summarizer-agent, etc

4) Browser-Use Microservice (Node)
   - Headless browser automation to search NCBI/GEO/PRIDE and parse structured metadata.
   - Exposes a lightweight REST API consumed by Python backend.
   - Documentation is in ./browser-use-doc.md

5) Database (sql)
   - Tables: users, datasets, outreach_requests, messages, tasks, provenance. 

6) Message/Task Queue
   - as simple as possible 

7) AgentMail Webhook Receiver
   - Endpoint to receive email replies or delivery events and map them to outreach records.
   - documentation in ./agentmail-doc.md

8) Orchestrator logic (backend) — a thin “agent” that:
   - Decomposes requests (planner), schedules searches, finds contacts, drafts emails, sends via AgentMail, logs and notifies via Teams.

------------------------------------------------------------------------------
REPOSITORY & FILE LAYOUT (suggested, needs updating)
------------------------------------------------------------------------------
/project-root
  /backend
    Dockerfile
    requirements.txt
    app/
      main.py                 # FastAPI app
      api/
        v1_search.py
        v1_contacts.py
        v1_outreach.py
        v1_webhooks.py
      core/
        agent_orchestrator.py # Planner + orchestrator logic
        auth.py               # Azure Graph auth, AgentMail client
        browser_use_client.py # thin REST client to Node microservice
      tasks/
        tasks.py              # Celery tasks (search_job, send_email_job)
      models/
        db.py                 # SQLAlchemy models
        schemas.py            # pydantic request/response schemas
        migrations/
      utils/
        email_templates.py
        provenance.py
        security.py
  /browser-service
    package.json
    Dockerfile
    src/
      server.js               # Express server exposing search endpoints
      scrapers/
        geo_scraper.js
        pride_scraper.js
      utils/
        parsers.js
  /teams-frontend (forked microsoft/teams-ai)
    README.md
    src/
      components/
        OmicsBotUI.tsx
      services/
        backendClient.ts
      adaptiveCards/
        dataset_card.json
  docker-compose.yml
  infra/
    k8s-manifests/            # optional
  README.md
  instruct.txt                # this file

------------------------------------------------------------------------------
DETAILED API DESIGN (MVP endpoints)
------------------------------------------------------------------------------

<not yet done>

------------------------------------------------------------------------------
DATABASE SCHEMA (simplified SQL, needs updates)
------------------------------------------------------------------------------
-- users (internal)
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  job_title TEXT,
  department TEXT,
  manager_email TEXT,
  source TEXT, -- 'graph'|'mock'
  created_at TIMESTAMP DEFAULT now()
);

-- datasets (candidates)
CREATE TABLE datasets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL, -- 'GEO'|'PRIDE'|'INTERNAL'
  accession TEXT, -- e.g., GSE12345 or internal id
  title TEXT,
  modalities TEXT[], -- ['scRNA-seq','proteomics']
  cancer_type TEXT,
  sample_size INT,
  download_url TEXT,
  access_type TEXT, -- 'public'|'request'|'restricted'
  owner_email TEXT, -- if available
  metadata JSONB,
  created_at TIMESTAMP DEFAULT now()
);

-- outreach_requests
CREATE TABLE outreach_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id UUID REFERENCES datasets(id),
  requester_email TEXT,
  contact_email TEXT,
  status TEXT, -- 'queued','sent','delivered','replied','closed'
  thread_id TEXT,
  message_id TEXT,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  provenance JSONB
);

-- provenance logs
CREATE TABLE provenance (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor TEXT,
  action TEXT,
  details JSONB,
  created_at TIMESTAMP DEFAULT now()
);

------------------------------------------------------------------------------
BACKEND IMPLEMENTATION DETAILS (step-by-step)
------------------------------------------------------------------------------

A) Environment & libs
  - Python libraries:
    pip install fastapi uvicorn[standard] sqlalchemy asyncpg alembic
    pip install celery[redis] redis python-dotenv requests msal pydantic
    pip install aiohttp python-agentmail-sdk-if-available  # otherwise use requests
  - Setup .env file:
    AGENTMAIL_API_KEY="sk_xxx"
    AGENTMAIL_DOMAIN="yourdomain"
    AZURE_CLIENT_ID=...
    AZURE_TENANT_ID=...
    AZURE_CLIENT_SECRET=...
    REDIS_URL=redis://redis:6379/0
    DATABASE_URL=postgresql://user:pass@postgres:5432/omics

B) FastAPI app skeleton (app/main.py)
  - Mount routes under /api/v1
  - Add CORS for Teams frontend origin
  - Include logging, error handlers, request tracing (X-Request-ID)
  - Provide /health and /metrics endpoints

D) Browser-Use microservice (Node)
  - Purpose: keep headless browser scraping code isolated (avoid heavy Node deps in Python)
  - Implementation outline:
    - Express server with routes:
      POST /scrape/geo { query, max_results } -> returns list of dataset metadata
      POST /scrape/pride { query } -> ...
  - Each scraper in /scrapers uses Browser-Use templates to:
    - load search page, run query, parse results into structured JSON
    - gracefully handle 429/blocks and use exponential backoff + randomized waits
    - return canonical fields: { accession, title, modalities, sample_size, link, access_type, contact_info }
  - Containerize with Docker. Expose port to backend via docker-compose.

E) Celery task workers (tasks/tasks.py)
  - Define tasks:
    - search_job(task_id, query, modalities, max_results, user_id)
      - call Browser-Service endpoints,
      - normalize results, write into datasets table,
      - associate provenance entries
    - send_email_job(outreach_request_id)
      - fetch outreach_request from DB,
      - call AgentMail API to send email,
      - include `X-OMICS-THREAD-ID` header or similar to map replies,
      - update outreach status (sent -> delivered)
  - Failure handling:
    - retry policy with exponential backoff,
    - send failure notification to Teams (card) and log provenance.

F) AgentMail integration (auth.py / email_client.py)
  - Register for AgentMail API key and domain.
  - Send email via AgentMail REST:
    - POST to messages endpoint with body, to, from, subject.
    - Include custom header or metadata like `metadata`: { outreach_id: "<uuid>" } to correlate webhooks.
  - Implement /api/v1/agentmail/webhook to accept inbound replies:
    - Validate signature (AgentMail webhook signature method).
    - Map to outreach via metadata/thread header,
    - If reply contains attachment: store metadata and flag for human approval.

G) Orchestrator (core/agent_orchestrator.py)
  - Planner logic:
    - Given user query, build a plan: [search public sources] -> [filter] -> [find internal owner] -> [compose outreach] -> [send if auto_allowed OR queue for human approval].
  - Use simple rule system for hackathon:
    - If dataset.access_type == 'public' => no outreach required.
    - If access_type == 'request' or 'restricted' => outreach required.
    - If dataset contains potential PHI (metadata hint) => require human approval.
  - Expose single entry-point:
    - orchestrator.create_request(user, query, constraints) -> task_id

H) Provenance & Logging
  - Every step creates a provenance record with: actor, action, inputs, outputs, timestamp.
  - Store in provenance table.

I) Testing
  - Unit tests for: Graph client (mock responses), AgentMail client (mock requests), Browser-Service client (mock).
  - Integration: run backend + browser-service + fake AgentMail webhook server locally.

------------------------------------------------------------------------------
FRONTEND: TEAMS-AI (TypeScript) INTEGRATION DETAILS
------------------------------------------------------------------------------
Goal: Use teams-ai as the Teams conversational frontend. Add custom actions and Adaptive Cards.

A) Setup
  - Clone microsoft/teams-ai and create a feature branch.
  - Keep Teams project TypeScript code in /teams-frontend within your repo or integrate via submodule.
  - Install and run per repo instructions (you will need Node 18+).

B) Frontend responsibilities
  - Present UI to researcher: prompt input box for query and constraints.
  - Display dataset shortlist as Adaptive Cards with actions:
    - "Request access" (triggers send_outreach),
    - "Find owner" (triggers find_contact),
    - "Open dataset" (link),
    - "Mark as Received".
  - Display progress updates (task queued, results arriving).

C) BackendClient (teams-frontend/src/services/backendClient.ts)
  - Implement HTTP client to call Python backend APIs:
    - search(query) -> POST /api/v1/search
    - findContact(department) -> POST /api/v1/find_contact
    - sendOutreach(payload) -> POST /api/v1/send_outreach
    - getStatus(task_id) -> GET /api/v1/task/{task_id}

D) Teams Bot action flow (on message or message-extension)
  - When user submits query, bot calls backend /api/v1/search,
  - Show "Searching..." Adaptive Card,
  - Poll task_id for updates (or use websockets if time permits),
  - Render results in cards, each card includes action buttons wired to message-extension commands:
    - On "Request access", bot opens an action dialog (Adaptive Card) to confirm email template, then calls send_outreach endpoint.

E) Adaptive Card example (dataset_card.json)
  - Card fields:
    - Title (dataset accession + title)
    - Subtitle (modalities / sample size / access type)
    - Buttons: "Request access" (invoke backend), "Open" (open URL)
  - For outreach button, pass dataset_id and contact defaults.

F) Authentication & identity
  - Teams bot knows the user identity; forward Teams user email as `requester_email` in API calls.
  - Use Teams SSO if needed (optional for hackathon); otherwise map Teams user email from conversation context to backend.

------------------------------------------------------------------------------
BROWSER-USE DETAILS (practical notes)
------------------------------------------------------------------------------
- Browser-Use is used to automate search pages in public biobanks. Keep scrapers conservative:
  - Use polite crawling intervals, set user agent, avoid high request rates.
  - Implement timeouts and captchas fallback (report task as "captcha_required").
  - Parse structured elements (accession, links, data type).
- For hackathon: restrict to **NCBI GEO** (single scraper) to keep scope manageable.
  - GEO search flow:
    - Query page → parse search results page for accession ID and title → open dataset page for metadata.
- Return canonical dataset JSON:
  {
    accession: "GSE12345",
    title: "...",
    modalities: ["scRNA-seq"],
    cancer_type: ["breast cancer", "TNBC"],
    sample_size: 3000,
    access_type: "public" or "request",
    contact_info: { name, email } or null,
    link: "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345"
  }




---

HACKATHON IMPLEMENTATION PLAN (48-hour timeline)

PRIORITIZE: MVP that proves value: search GEO -> produce shortlist -> find internal contact via linkedin -> one-click email send (AgentMail) -> show results in frontend

Day 0 (Before hackathon / setup)

Create repo, skeleton of backend/frontend, sign up for AgentMail, set up Azure AD app if possible, spawn test AgentMail key.

Prepare dev environment: Docker, DB, Redis.


Day 1 morning (MVP core)

Implement FastAPI skeleton, DB models, and Celery setup.

Implement Browser-Service GEO scraper (single scraper) and test locally.

Implement search_job Celery task and dataset insertion.

Implement /api/v1/search and /api/v1/task endpoints.


Day 1 afternoon (integrations)

Implement AgentMail client and /api/v1/send_outreach endpoint with Celery job.

Implement minimal MS Graph client or a JSON mock directory file.

Wire backend to teams-ai frontend minimal integration (invoke backend search).


Day 2 morning (UX + demo)

Add Adaptive Cards to show datasets in Teams; wire "Request access" to open confirmation card.

Implement AgentMail webhook receiver to update status of sent emails (simulate if no webhook reachable).

Add provenance logging and a results table endpoint.


Day 2 afternoon (polish + demo)

Add error handling & retry, add sample email templates, document demo script.

Record short demo video, prepare slide deck, and finalize README.



---

MVP vs STRETCH (recommendation)

MVP:

GEO scraper only

Mock internal directory

Send email via AgentMail (one-way)

Teams UI that triggers search and shows results, with a "Request access" action


Stretch:

Full Graph integration + real directory lookups

PRIDE, Ensembl scrapers

Incoming email parsing & attachment ingestion

Human-in-the-loop approval UI for PHI / restricted data

Slack/Teams notifications and retry dashboards

Export pipeline descriptor (omics-os JSON)



---

SAMPLE EMAIL TEMPLATES (professional)

Subject: Request for access to {dataset_accession} — {project_short_title}

Body: Dear {contact_name},

I am {requester_name}, a bioinformatics researcher at {company}. I am working on a cancer research project (project: {project_short_title}) focused on {brief_goal}. I located the dataset {dataset_accession} ({dataset_title}) and would like to request access to the raw data / processed results for use in our analysis.

Usage:

Purpose: {analysis_purpose}

Data handling: We will only use de-identified data and follow institutional data sharing policies.


If access requires agreements or steps, please let me know the required process or who I should contact. If easier, we can schedule a 10-minute call.

Thank you very much, {requester_name} {requester_role} {requester_email} {requester_phone}

Footer (automated): This email was sent by the Omics Outreach Teammate on behalf of {requester_name}. Reply will be tracked to request ID {outreach_id}.

IMPORTANT: Add a note: "If this dataset contains clinical PHI, do not attach PHI to replies; please contact your data governance office."


---

SECURITY & PRIVACY CHECKLIST (mandatory)

Require admin consent for Graph API access (Directory.Read.All).

Protect AgentMail key in secrets manager (do not hardcode).

Implement role-based access in backend: only authorized users can trigger outreach.

Rate-limit outreach per user to prevent spam.

Add email content templates with required legal/IRB warning lines.

Keep audit log of all outgoing messages and replies (immutable).

Implement manual approval flow for any dataset flagged as containing PHI.



---

TESTING & QA (quick list)

Unit tests: search parsing, outreach payload formatting, DB CRUD.

Integration tests: Browser-Service <-> Backend (use test fixtures),

E2E local test: Teams frontend triggers search -> backend calls Browser-Service -> returns results.

Manual test: send AgentMail to test mailbox, verify webhook mapping.

Security test: ensure no sensitive fields returned unless approved.



---

DEPLOYMENT (local hackathon + production notes)

Local (docker-compose):

Services: postgres, redis, backend (uvicorn), browser-service (node), celery-worker, teams-frontend (dev server)

Use docker-compose.yml for quick local spin-up.


Production (notes):

Host backend in cloud (Heroku/Azure Web Apps/AKS),

Browser-Service in separate container with autoscaling (if heavy scraping),

Use managed PostgreSQL and Redis,

Use HTTPS and validated AgentMail webhook URLs.



---

DEMO SCRIPT (3–5 minute)

1. Start in Teams: researcher types the project query.


2. Bot replies: "Searching public resources and internal owners..."


3. After a short wait, bot posts dataset cards (2 results: one public GEO, one internal).


4. Click "Request access" on internal dataset -> confirm dialog (show email body).


5. Click "Send" -> Bot shows "Email sent" and logs the outreach id.


6. Show backend web page (or Teams card) listing outreach request with provenance.


7. If time: show reply flow (simulate incoming AgentMail webhook) -> backend updates status to 'replied'.




---

CHECKLIST (deliverables for hackathon)

[ ] Backend (FastAPI) with /search, /send_outreach, /task endpoints

[ ] Browser-Service (GEO) scraper running locally

[ ] Celery worker or equivalent for background tasks

[ ] AgentMail integration and webhook receiver (simulate replies)

[ ] teams-ai frontend integrated to call backend and render Adaptive Cards

[ ] Mock directory or Graph integration to find internal users

[ ] DB and provenance logs

[ ] Demo script and short video + README



---

APPENDIX / TROUBLESHOOTING HINTS

If you cannot obtain Azure Graph permissions: use a mock JSON directory and document Graph integration steps in README.

If Browser-Use is blocked by anti-bot on GEO, fallback to NCBI's E-utilities (NCBI eSearch / eSummary API) for GEO metadata (eutils are official APIs) – this is a pragmatic fallback.

If AgentMail webhook signature verification fails, check timezone/clock skew and retry signature secret configuration.

To debug Celery: use flower or print task logs with full tracebacks.



---

FINAL NOTES

Keep the UI interactions crisp and the email content conservative & professional.

Emphasize human-in-the-loop gating for sensitive datasets (critical given cancer research context).

For hackathon, mock what you can but show clear integration points to the real systems (Graph, AgentMail, Browser-Use).

Prepare a 1-slide architecture diagram and a 1-minute explanation of compliance & safety for judges.
