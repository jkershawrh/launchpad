from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, branding, catalog, lab_requests, lab_sessions, tenants

app = FastAPI(
    title="Partner AI Launchpad",
    description="Reusable Red Hat/Intel partner demo and lab platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenants.router)
app.include_router(catalog.router)
app.include_router(lab_requests.router)
app.include_router(lab_sessions.router)
app.include_router(branding.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
