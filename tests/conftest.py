"""
Shared pytest fixtures available to every test file automatically.
No imports needed in test files — pytest discovers this by convention.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import (
    can_admin_delete_booking,
    can_read_or_manage_booking,
    can_write_booking,
    get_current_user,
    get_payments_client,
    get_users_client,
    get_venues_client,
)
from app.routers.booking import router

from .factories import make_admin, make_customer, make_venue_owner

# ---------------------------------------------------------------------------
# Default no-op client mocks — prevent real HTTP calls in tests
# ---------------------------------------------------------------------------


def _noop_venues_client():
    mock = MagicMock()
    mock.get_venue = AsyncMock(return_value=None)
    mock.get_unavailabilities = AsyncMock(return_value=[])
    mock.get_by_ids = AsyncMock(return_value=[])
    return mock


def _noop_users_client():
    mock = MagicMock()
    mock.get_by_ids = AsyncMock(return_value=[])
    return mock


def _noop_payments_client():
    mock = MagicMock()
    mock.refund_booking = AsyncMock(return_value=True)
    return mock


# ---------------------------------------------------------------------------
# App builder — used by all client fixtures
# ---------------------------------------------------------------------------


def build_app(current_user, venues_client=None, users_client=None, payments_client=None) -> FastAPI:
    """
    Fresh FastAPI app with auth/scope dependencies overridden to return
    `current_user` unconditionally.

    Pass `venues_client` / `users_client` to inject custom mocks.
    Defaults to no-op mocks that return empty lists, avoiding real HTTP calls.
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

    vc = venues_client if venues_client is not None else _noop_venues_client()
    uc = users_client if users_client is not None else _noop_users_client()
    pc = payments_client if payments_client is not None else _noop_payments_client()
    app.dependency_overrides[get_venues_client] = lambda: vc
    app.dependency_overrides[get_users_client] = lambda: uc
    app.dependency_overrides[get_payments_client] = lambda: pc

    return app


# ---------------------------------------------------------------------------
# Reusable client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def customer_client():
    return TestClient(build_app(make_customer()), raise_server_exceptions=True)


@pytest.fixture()
def owner_client():
    return TestClient(build_app(make_venue_owner()), raise_server_exceptions=True)


@pytest.fixture()
def admin_client():
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
    def _make(
        current_user,
        venues_client=None,
        users_client=None,
        payments_client=None,
    ) -> TestClient:
        return TestClient(
            build_app(
                current_user,
                venues_client=venues_client,
                users_client=users_client,
                payments_client=payments_client,
            ),
            raise_server_exceptions=True,
        )

    return _make
