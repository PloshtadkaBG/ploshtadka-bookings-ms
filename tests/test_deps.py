"""
Tests for app/deps.py — get_current_user, require_scopes, VenuesClient, etc.
These tests use the real dep functions (no overrides) to get coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.deps import (
    VenuesClient,
    can_read_or_manage_booking,
    get_current_user,
    get_venues_client,
)
from app.routers.booking import router

from .factories import CUSTOMER_ID, make_customer, make_venue_owner

CRUD_PATH = "app.routers.booking.booking_crud"


def _make_anon_app_with_scope_passthrough() -> FastAPI:
    """
    App that uses the real get_current_user dep but ignores scope checks
    (scope check is replaced with a passthrough that still calls get_current_user).
    """
    app = FastAPI()
    app.include_router(router)

    async def _passthrough(user=Depends(get_current_user)):
        return user

    app.dependency_overrides[can_read_or_manage_booking] = _passthrough
    return app


class TestGetCurrentUser:
    def test_valid_headers_authenticate(self):
        """get_current_user reads Traefik headers and returns CurrentUser."""
        app = _make_anon_app_with_scope_passthrough()
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[])
            with TestClient(app) as c:
                resp = c.get(
                    "/bookings",
                    headers={
                        "X-User-Id": str(CUSTOMER_ID),
                        "X-Username": "customer1",
                        "X-User-Scopes": "bookings:read",
                    },
                )
        assert resp.status_code == 200

    def test_invalid_user_id_returns_401(self):
        """get_current_user raises 401 when X-User-Id is not a valid UUID."""
        app = _make_anon_app_with_scope_passthrough()
        with TestClient(app) as c:
            resp = c.get(
                "/bookings",
                headers={
                    "X-User-Id": "not-a-uuid",
                    "X-Username": "customer1",
                    "X-User-Scopes": "",
                },
            )
        assert resp.status_code == 401

    def test_empty_scopes_string_parsed_as_empty_list(self):
        """X-User-Scopes: '' should produce scopes=[]."""
        app = _make_anon_app_with_scope_passthrough()
        captured = {}

        async def _capture(user=Depends(get_current_user)):
            captured["user"] = user
            return user

        app.dependency_overrides[can_read_or_manage_booking] = _capture
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[])
            with TestClient(app) as c:
                c.get(
                    "/bookings",
                    headers={
                        "X-User-Id": str(CUSTOMER_ID),
                        "X-Username": "u",
                        "X-User-Scopes": "",
                    },
                )
        assert captured["user"].scopes == []


class TestCanReadOrManageBooking:
    def _app_for(self, current_user) -> FastAPI:
        app = FastAPI()
        app.include_router(router)

        async def _user():
            return current_user

        app.dependency_overrides[get_current_user] = _user
        return app

    def test_customer_with_read_scope_passes(self):
        app = self._app_for(make_customer())
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[])
            with TestClient(app) as c:
                resp = c.get("/bookings")
        assert resp.status_code == 200

    def test_venue_owner_with_manage_scope_passes(self):
        app = self._app_for(make_venue_owner())
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[])
            with TestClient(app) as c:
                resp = c.get("/bookings")
        assert resp.status_code == 200

    def test_user_with_no_relevant_scope_gets_403(self):
        app = self._app_for(make_customer(scopes=["venues:read"]))
        with TestClient(app) as c:
            resp = c.get("/bookings")
        assert resp.status_code == 403


class TestGetVenuesClient:
    def test_returns_venues_client_instance(self):
        client = get_venues_client()
        assert isinstance(client, VenuesClient)

    def test_same_instance_returned_each_time(self):
        """get_venues_client returns the module-level singleton."""
        assert get_venues_client() is get_venues_client()

    def test_headers_built_from_current_user(self):
        user = make_customer()
        client = VenuesClient()
        headers = client._headers(user)
        assert headers["X-User-Id"] == str(user.id)
        assert headers["X-Username"] == user.username
        assert "bookings:read" in headers["X-User-Scopes"]

    def test_client_property_returns_async_client(self):
        """Accessing ._client triggers the lru_cache factory."""
        import httpx

        client = VenuesClient()
        http_client = client._client
        assert isinstance(http_client, httpx.AsyncClient)


class TestCurrentUserIsAdmin:
    def test_is_admin_true_when_has_admin_scope(self):
        from uuid import uuid4

        from app.deps import CurrentUser

        user = CurrentUser(id=uuid4(), username="admin", scopes=["admin:scopes"])
        assert user.is_admin is True

    def test_is_admin_false_without_admin_scope(self):
        assert make_customer().is_admin is False


class TestRequireScopesHappyPath:
    def test_delete_endpoint_passes_with_admin_delete_scope(self, anon_app):
        """
        Tests the require_scopes happy path (line 74: return current_user).
        Uses the real can_admin_delete_booking dep with a user that has the scope.
        """
        from .factories import BOOKING_ID, make_admin

        async def _admin():
            return make_admin()

        anon_app.dependency_overrides[get_current_user] = _admin
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.delete_booking = AsyncMock(return_value=True)
            with TestClient(anon_app) as c:
                resp = c.delete(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 204
