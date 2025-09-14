from fastapi import APIRouter
from app.api.v1 import datasets, search, status, tasks, outreach, webhooks, leads

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(status.router, tags=["status"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(outreach.router, prefix="/outreach", tags=["outreach"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
