from __future__ import annotations

from unittest.mock import patch

import pytest
from app.services.catalog_intake_submissions import (
    CatalogIntakeSubmissionService,
    create_catalog_intake_submission_service,
)
from app.storage.catalog_intakes import (
    InMemoryCatalogIntakeDraftStore,
    PostgresCatalogIntakeDraftStore,
)


def test_factory_uses_explicit_local_fallback_only_for_local_and_test_modes():
    for mode in ("mock", "local", "test"):
        service = create_catalog_intake_submission_service(
            mode=mode,
            database_url=None,
            ha_enabled=False,
        )
        assert isinstance(service, CatalogIntakeSubmissionService)
        assert isinstance(service.store, InMemoryCatalogIntakeDraftStore)


@pytest.mark.parametrize("mode", ["openshift", "rhdp", "production"])
def test_factory_fails_closed_without_postgres_outside_local_modes(mode):
    with pytest.raises(RuntimeError, match="durable PostgreSQL storage"):
        create_catalog_intake_submission_service(
            mode=mode,
            database_url=None,
            ha_enabled=False,
        )


def test_factory_fails_closed_for_ha_even_when_local_fallback_was_requested():
    with pytest.raises(RuntimeError, match="HA mode requires durable PostgreSQL storage"):
        create_catalog_intake_submission_service(
            mode="mock",
            database_url=None,
            ha_enabled=True,
        )


def test_factory_selects_postgres_without_opening_a_connection():
    with patch("app.storage.catalog_intakes.get_database_url", return_value="postgresql://unused"):
        service = create_catalog_intake_submission_service(
            mode="openshift",
            database_url="postgresql://unused",
            ha_enabled=True,
        )

    assert isinstance(service.store, PostgresCatalogIntakeDraftStore)
    assert service.store.database_url == "postgresql://unused"
