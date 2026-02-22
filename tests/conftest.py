"""
Shared pytest fixtures available to every test file automatically.
No imports needed in test files — pytest discovers this by convention.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import (
    can_admin_delete_booking,
    can_read_or_manage_booking,
    can_write_booking,
    get_current_user,
    get_venues_client,
)
from app.routers.booking import router

from .factories import make_admin, make_customer, make_venue_owner

# ---------------------------------------------------------------------------
# App builder — used by all client fixtures
# ---------------------------------------------------------------------------


def build_app(current_user, venues_client=None) -> FastAPI:
    """
    Fresh FastAPI app with auth/scope dependencies overridden to return
    `current_user` unconditionally.

    Pass `venues_client` to inject a mock VenuesClient for create-booking tests.
    Tests that need real deps to run (e.g. 403 assertions) should use `anon_app`.
    """
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return current_user

    for dep in (
        can_read_or_manage_booking,
        can_write_booking,
        can_admin_delete_booking,
        get_current_user,
    ):
        app.dependency_overrides[dep] = _user

    if venues_client is not None:
        app.dependency_overrides[get_venues_client] = lambda: venues_client

    return app


# ---------------------------------------------------------------------------
# Reusable client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def customer_client():
    """TestClient authenticated as a regular customer."""
    return TestClient(build_app(make_customer()), raise_server_exceptions=True)


@pytest.fixture()
def owner_client():
    """TestClient authenticated as a venue owner."""
    return TestClient(build_app(make_venue_owner()), raise_server_exceptions=True)


@pytest.fixture()
def admin_client():
    """TestClient authenticated as an admin."""
    return TestClient(build_app(make_admin()), raise_server_exceptions=True)


@pytest.fixture()
def anon_app():
    """
    Bare app with NO dependency overrides.
    Use this when you want real scope/auth deps to run so you can assert 401/403/422.
    """
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client_factory():
    """
    Callable fixture: call it with any CurrentUser (and optional mock VenuesClient).

    Usage:
        def test_something(client_factory):
            client = client_factory(make_customer())
            resp = client.get("/bookings")
    """

    def _make(current_user, venues_client=None) -> TestClient:
        return TestClient(
            build_app(current_user, venues_client=venues_client),
            raise_server_exceptions=True,
        )

    return _make
