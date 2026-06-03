import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, branding, callbacks, catalog, intelligence, lab_requests, lab_sessions, tenants, workshops
from app.storage.database import get_database_url, init_db, close_db

logger = logging.getLogger(__name__)

TTL_INTERVAL = int(os.environ.get("TTL_ENFORCEMENT_INTERVAL", "300"))
_ttl_task = None


async def _ttl_enforcement_loop():
    """Background task that enforces TTL on expired sessions every 5 minutes."""
    while True:
        await asyncio.sleep(TTL_INTERVAL)
        try:
            from app.api.deps import provisioning_service
            reclaimed = provisioning_service.enforce_ttl()
            if reclaimed:
                logger.info("TTL enforcement: reclaimed %d expired sessions", len(reclaimed))
        except Exception as e:
            logger.debug("TTL enforcement error (non-critical): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ttl_task
    if get_database_url():
        await init_db()
    _ttl_task = asyncio.create_task(_ttl_enforcement_loop())
    yield
    if _ttl_task:
        _ttl_task.cancel()
    await close_db()


app = FastAPI(
    title="Partner AI Launchpad",
    description="Reusable Red Hat/Intel partner demo and lab platform",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:5174"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)

# All routers mounted under /api/v1 prefix
API_PREFIX = "/api/v1"

app.include_router(tenants.router, prefix=API_PREFIX)
app.include_router(catalog.router, prefix=API_PREFIX)
app.include_router(lab_requests.router, prefix=API_PREFIX)
app.include_router(lab_sessions.router, prefix=API_PREFIX)
app.include_router(branding.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(workshops.router, prefix=API_PREFIX)
app.include_router(callbacks.router, prefix=API_PREFIX)
app.include_router(intelligence.router, prefix=API_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok", "service": "launchpad"}
