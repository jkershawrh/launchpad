from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from app.domain.catalog_intake import CatalogIntakeSubmission
from app.services.catalog_intake_submissions import CatalogIntakeSubmissionService
from app.storage import database
from app.storage.catalog_intakes import (
    CatalogIntakeDraftConflictError,
    PostgresCatalogIntakeDraftStore,
)

TEST_DATABASE_URL = os.environ.get("CATALOG_INTAKE_TEST_DATABASE_URL")
MIGRATION = Path(__file__).parents[1] / "migrations/010_catalog_intake_drafts.sql"
requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="CATALOG_INTAKE_TEST_DATABASE_URL is not configured",
)


def _submission() -> CatalogIntakeSubmission:
    return CatalogIntakeSubmission(
        catalog_item_id="durable-agent-lab",
        display_name="Durable Agent Lab",
        repository_url="https://github.com/example/durable-agent-lab.git",
        revision="c" * 40,
        owner="owner@example.com",
        audience=["solution-architects"],
        duration_hours=4,
        lab_type="guided_build",
        expected_scale=25,
    )


def test_catalog_intake_migration_owns_durable_draft_schema():
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS catalog_intake_drafts" in sql
    assert "intake_id" in sql
    assert "request_fingerprint" in sql
    assert "CHECK (state = 'draft')" in sql
    assert "JSONB NOT NULL" in sql
    assert "repository_url" in sql
    assert "revision" in sql


@pytest.fixture(autouse=True)
def intake_schema(monkeypatch):
    if not TEST_DATABASE_URL:
        yield
        return
    import psycopg2

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    database._initialize_database(psycopg2, TEST_DATABASE_URL)
    conn = psycopg2.connect(TEST_DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE catalog_intake_drafts")
    conn.commit()
    conn.close()
    yield


@requires_postgres
def test_postgres_intake_survives_service_restart():
    first = CatalogIntakeSubmissionService(
        store=PostgresCatalogIntakeDraftStore(TEST_DATABASE_URL)
    ).submit(_submission())

    restarted = CatalogIntakeSubmissionService(
        store=PostgresCatalogIntakeDraftStore(TEST_DATABASE_URL)
    )

    assert restarted.get(first.intake_id) == first
    assert restarted.list_all() == [first]


@requires_postgres
def test_concurrent_identical_submissions_converge_on_one_durable_draft():
    services = [
        CatalogIntakeSubmissionService(
            store=PostgresCatalogIntakeDraftStore(TEST_DATABASE_URL)
        )
        for _ in range(4)
    ]

    with ThreadPoolExecutor(max_workers=4) as executor:
        drafts = list(executor.map(lambda service: service.submit(_submission()), services))

    assert all(draft == drafts[0] for draft in drafts)
    assert PostgresCatalogIntakeDraftStore(TEST_DATABASE_URL).list_all() == [drafts[0]]


@requires_postgres
def test_postgres_store_rejects_conflicting_data_for_same_intake_id():
    service = CatalogIntakeSubmissionService(
        store=PostgresCatalogIntakeDraftStore(TEST_DATABASE_URL)
    )
    draft = service.submit(_submission())
    conflict = draft.model_copy(
        update={"blockers": [*draft.blockers, "tampered after identity creation"]}
    )

    with pytest.raises(CatalogIntakeDraftConflictError, match="different draft"):
        PostgresCatalogIntakeDraftStore(TEST_DATABASE_URL).create_idempotent(conflict)
