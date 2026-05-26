import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, branding, callbacks, catalog, lab_requests, lab_sessions, tenants, workshops
from app.storage.database import get_database_url, init_db, close_db

app = FastAPI(
    title="Partner AI Launchpad",
    description="Reusable Red Hat/Intel partner demo and lab platform",
    version="0.1.0",
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


@app.on_event("startup")
async def startup():
    if get_database_url():
        await init_db()


@app.on_event("shutdown")
async def shutdown():
    await close_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "launchpad"}
