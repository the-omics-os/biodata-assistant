# Omics-OS Automated Lead Generation System

**Fully automated AI-powered FastAPI system** for GitHub prospecting and personalized outreach. Continuously identifies struggling bioinformatics users in scanpy/anndata repositories and converts them into omics-os prospects through automated persona-based outreach.

## 🚀 Key Features

### **Automated GitHub Prospecting**
- **Continuous monitoring** of scverse/scanpy and scverse/anndata repositories
- **AI-powered lead qualification** using multi-signal scoring algorithms
- **Contact information extraction** from GitHub profiles and personal websites
- **Structured data processing** via Pydantic and Browser-Use integration

### **Background Task Processing**
- **Celery-powered background tasks** for scalable processing
- **Scheduled daily prospecting** runs automatically
- **Real-time email monitoring** checks for replies every 30 seconds
- **Automated outreach queuing** with human approval gates

### **Intelligent Outreach System**
- **Persona-based email generation** (Transcripta Quillborne for transcriptomics)
- **AgentMail integration** for reliable email delivery
- **Human approval workflow** with bulk operations support
- **Full provenance logging** for complete auditability

### **Production-Ready REST API**
- **FastAPI framework** with comprehensive OpenAPI documentation
- **Lead management endpoints** for viewing and managing prospects
- **Outreach automation APIs** with status tracking
- **Real-time monitoring** of background services and tasks

## 🏗️ Architecture

- **API Server**: FastAPI with async/await support
- **Background Tasks**: Celery + Redis for distributed task processing
- **Database**: SQLAlchemy (SQLite/PostgreSQL) with migration support
- **Email Service**: AgentMail integration with webhook support
- **Web Scraping**: Browser-Use with Playwright for reliable GitHub scraping
- **AI Agents**: Pydantic AI for lead qualification and content generation

## ⚡ Quick Start

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt

# Install Chromium for web scraping
uvx playwright install chromium --with-deps --no-shell
```

### 2. Configure Environment
Create a `.env` file in the backend directory:
```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional (for email functionality)
AGENTMAIL_API_KEY=your_agentmail_api_key_here
REDIS_URL=redis://localhost:6379/0

# GitHub Prospecting Configuration
GITHUB_TARGET_REPOS=scverse/scanpy,scverse/anndata
GITHUB_MAX_ISSUES_PER_REPO=25
GITHUB_PROSPECTING_ENABLED=true

# Email Monitoring
EMAIL_MONITORING_ENABLED=true
EMAIL_MONITORING_INTERVAL_SECONDS=30

# Automated Outreach (requires approval by default)
AUTOMATED_OUTREACH_ENABLED=false
```

### 3. Start the System
```bash
# Start FastAPI server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In separate terminals, start background workers:
celery -A app.core.celery_app worker --loglevel=info
celery -A app.core.celery_app beat --loglevel=info
```

### 4. Access the System
- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **API Status**: http://localhost:8000/api/v1/status/detailed
- **Health Check**: http://localhost:8000/health

## 📡 API Endpoints

### **Lead Management**
```bash
# Trigger GitHub prospecting
POST /api/v1/leads/prospect?repos=scverse/scanpy&max_issues=25

# List qualified leads
GET /api/v1/leads?stage=enriched&has_email=true

# Send outreach to specific lead
POST /api/v1/leads/{lead_id}/outreach

# Bulk outreach
POST /api/v1/leads/outreach/bulk
```

### **Outreach Management**
```bash
# List outreach requests
GET /api/v1/outreach?status=sent

# Send outreach email
POST /api/v1/outreach/{outreach_id}/send

# Approve outreach (for approval-required emails)
POST /api/v1/outreach/{outreach_id}/approve?approved_by=user@example.com

# Bulk operations
POST /api/v1/outreach/bulk-send
```

### **System Monitoring**
```bash
# Detailed system status
GET /api/v1/status/detailed

# Background task status
GET /api/v1/status/background-tasks

# Email monitoring health
GET /api/v1/webhooks/email-monitoring/health

# Lead statistics
GET /api/v1/leads/stats/summary?days=7
```

## 🤖 Automated Workflows

### **Daily GitHub Prospecting**
- Runs automatically at 9 AM UTC (configurable)
- Processes configured repositories for new issues
- AI qualifies leads based on struggle indicators
- Persists qualified leads to database

### **Continuous Email Monitoring**
- Checks for email replies every 30 seconds
- Updates lead and outreach status automatically
- Processes missed replies with fallback checks
- Logs all email activity for analytics

### **Intelligent Lead Scoring**
The system uses a multi-factor scoring algorithm:
- **Account Age**: <1 year = higher score
- **Community Engagement**: <5 followers = higher score
- **Repository Activity**: <5 repos = higher score
- **Struggle Keywords**: "help", "install", "error", "beginner"
- **Issue Quality**: Missing code blocks, question labels
- **Contact Availability**: Email address extractable

### **Persona-Based Outreach**
- **Transcripta Quillborne**: Transcriptomics specialist for scanpy/anndata
- **Smart Content**: Tailored examples for specific problems
- **Casual Tone**: Empathetic "hei I saw you were struggling..." approach
- **Approval Gates**: Human review required for sensitive outreach

## 🔧 Configuration

### **Environment Variables**

**Required:**
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

**Optional (Production Setup):**
```bash
# Background Tasks
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Database
DATABASE_URL=postgresql://user:password@localhost/biodata_assistant

# Email Service
AGENTMAIL_API_KEY=your_agentmail_api_key_here
AGENTMAIL_WEBHOOK_SECRET=your_webhook_secret_here

# Feature Flags
ENABLE_BACKGROUND_TASKS=true
GITHUB_PROSPECTING_ENABLED=true
EMAIL_MONITORING_ENABLED=true
AUTOMATED_OUTREACH_ENABLED=false  # Requires approval by default

# GitHub Prospecting
GITHUB_TARGET_REPOS=scverse/scanpy,scverse/anndata
GITHUB_MAX_ISSUES_PER_REPO=25
GITHUB_PROSPECTING_SCHEDULE_HOUR=9

# Email Monitoring
EMAIL_MONITORING_INTERVAL_SECONDS=30
OUTREACH_PROCESSING_INTERVAL_MINUTES=5
```

## 🐳 Docker Deployment

```bash
# Start full system with Redis
docker-compose up --build

# Or individual services
docker run -p 8000:8000 biodata-assistant-api
docker run biodata-assistant-worker
docker run biodata-assistant-beat
```

## 🔍 Monitoring & Troubleshooting

### **System Health Checks**
```bash
# Overall system status
curl http://localhost:8000/api/v1/status/detailed

# Background tasks status
curl http://localhost:8000/api/v1/status/background-tasks

# Email monitoring health
curl http://localhost:8000/api/v1/webhooks/email-monitoring/health
```

### **Common Issues**

**No Background Workers:**
- Start Celery worker: `celery -A app.core.celery_app worker --loglevel=info`
- Check Redis connection: `redis-cli ping`

**GitHub Scraping Fails:**
- Install Chromium: `uvx playwright install chromium --with-deps --no-shell`
- Check OPENAI_API_KEY is set
- Verify target repositories are accessible

**Email Issues:**
- Verify AGENTMAIL_API_KEY is valid
- Check email monitoring service: `GET /api/v1/webhooks/email-monitoring/health`
- Test AgentMail connection: `POST /api/v1/webhooks/email-monitoring/test-connection`

**No Leads Found:**
- Check prospecting configuration: `GET /api/v1/status/detailed`
- Manually trigger prospecting: `POST /api/v1/leads/prospect`
- Review lead statistics: `GET /api/v1/leads/stats/summary`

## 📁 Project Structure

```
biodata-assistant/
├── backend/
│   ├── app/
│   │   ├── api/v1/           # REST API endpoints
│   │   ├── core/
│   │   │   ├── agents/       # GitHub leads & email agents
│   │   │   ├── tasks/        # Background task modules
│   │   │   ├── services/     # Service layer (email monitoring)
│   │   │   └── integrations/ # External service clients
│   │   ├── models/           # Database models & schemas
│   │   └── utils/            # Personas, templates, utilities
│   ├── tests/                # Comprehensive test suite
│   ├── requirements.txt      # Production dependencies
│   └── demo.py               # Legacy interactive TUI (still functional)
├── docker-compose.yml        # Production deployment
├── Dockerfile               # Container configuration
└── README.md                # This file
```

## 🚀 Production Deployment

1. **Set up Redis**: `docker run -d -p 6379:6379 redis:alpine`
2. **Configure environment**: Copy `.env.example` to `.env` and customize
3. **Start API server**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
4. **Start background workers**:
   - `celery -A app.core.celery_app worker --loglevel=info --queues=github_prospecting,email_monitoring,outreach`
   - `celery -A app.core.celery_app beat --loglevel=info`
5. **Set up monitoring**: Use API endpoints or integrate with your monitoring stack

## 📊 Analytics & Reporting

The system provides comprehensive analytics through API endpoints:
- **Lead statistics**: Conversion rates, source repositories, qualification metrics
- **Outreach performance**: Send rates, reply rates, engagement tracking
- **System health**: Task processing times, error rates, service availability

## 🔒 Security & Compliance

- **API key management**: Secure storage of external service credentials
- **Human approval gates**: Required approval for automated outreach
- **Audit logging**: Complete provenance tracking of all actions
- **Rate limiting**: Respectful GitHub API usage and email sending limits
- **Data privacy**: Secure handling of contact information and communications

---

**Need help?** Check the [API documentation](http://localhost:8000/docs) or review the comprehensive endpoint examples above.
