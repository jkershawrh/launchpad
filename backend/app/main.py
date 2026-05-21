import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, branding, catalog, lab_requests, lab_sessions, tenants, workshops
from app.storage.database import get_database_url, init_db

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
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenants.router)
app.include_router(catalog.router)
app.include_router(lab_requests.router)
app.include_router(lab_sessions.router)
app.include_router(branding.router)
app.include_router(admin.router)
app.include_router(workshops.router)


@app.on_event("startup")
def startup():
    if get_database_url():
        init_db()


@app.get("/health")
def health():
    db_url = get_database_url()
    mode = os.environ.get("LAUNCHPAD_MODE", "mock")
    return {
        "status": "ok",
        "mode": mode,
        "persistence": "postgresql" if db_url else "in-memory",
    }
