from dataclasses import dataclass, field
from functools import lru_cache
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app import settings
from app.scopes import BOOKING_SCOPE_DESCRIPTIONS, BookingScope

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.users_ms_url}/auth/token",
    scopes={
        "venues:read": "Browse and search public venue listings.",
        **BOOKING_SCOPE_DESCRIPTIONS,
    },
)


@dataclass
class CurrentUser:
    id: UUID
    username: str
    scopes: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return "admin:scopes" in self.scopes


def get_current_user(
    x_user_id: str = Header(...),
    x_username: str = Header(...),
    x_user_scopes: str = Header(default=""),
) -> CurrentUser:
    """
    Reads the headers injected by Traefik after forwardAuth validation.
    The JWT has already been verified — we just trust these headers.
    NOTE: This only works behind Traefik. Run with that assumption.
    """
    try:
        user_id = UUID(x_user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity from gateway",
        ) from None

    scopes = x_user_scopes.split(" ") if x_user_scopes else []

    return CurrentUser(id=user_id, username=x_username, scopes=scopes)


def require_scopes(*required: str):
    """
    Factory that returns a dependency enforcing one or more scopes.

    Usage:
        @router.get("/protected")
        async def route(user = Depends(require_scopes("bookings:read"))):
            ...
    """

    async def _dep(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        missing = [s for s in required if s not in current_user.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {', '.join(missing)}",
            )
        return current_user

    return _dep


async def require_admin(
    current_user: CurrentUser = Depends(require_scopes("admin:scopes")),
) -> CurrentUser:
    """Shorthand for admin-only endpoints."""
    return current_user


# ---------------------------------------------------------------------------
# Pre-built scope dependencies
# ---------------------------------------------------------------------------

can_read_booking = require_scopes(BookingScope.READ)
can_write_booking = require_scopes(BookingScope.WRITE)
can_cancel_booking = require_scopes(BookingScope.CANCEL)
can_manage_booking = require_scopes(BookingScope.MANAGE)
can_admin_delete_booking = require_scopes(BookingScope.ADMIN_DELETE)


async def can_read_or_manage_booking(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Passes if the user can read bookings (customer/admin) OR manage bookings (owner).
    - bookings:read   → customer sees own bookings
    - bookings:manage → venue owner sees bookings for their venues
    - admin:bookings* → admin sees all
    """
    has_read = BookingScope.READ in current_user.scopes
    has_manage = BookingScope.MANAGE in current_user.scopes
    has_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_READ in current_user.scopes
    )
    if not (has_read or has_manage or has_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Requires '{BookingScope.READ}' (customers), "
                f"'{BookingScope.MANAGE}' (venue owners), "
                f"or '{BookingScope.ADMIN_READ}' (admin)."
            ),
        )
    return current_user


# ---------------------------------------------------------------------------
# VenuesClient — thin async wrapper around venues-ms internal API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_venues_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.venues_ms_url,
        timeout=httpx.Timeout(5.0),
    )


class VenuesClient:
    """
    Thin async wrapper around the venues-ms internal API.
    Forwards Traefik-injected user headers so venues-ms auth deps work normally.
    """

    @property
    def _client(self) -> httpx.AsyncClient:
        return _get_venues_http_client()

    def _headers(self, user: CurrentUser) -> dict[str, str]:
        return {
            "X-User-Id": str(user.id),
            "X-Username": user.username,
            "X-User-Scopes": " ".join(user.scopes),
        }

    async def get_venue(self, venue_id: UUID, user: CurrentUser) -> dict | None:
        """Returns venue dict or None if 404. Raises HTTPException on other errors."""
        resp = await self._client.get(
            f"/venues/{venue_id}", headers=self._headers(user)
        )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"venues-ms returned {resp.status_code}",
            )
        return resp.json()

    async def get_unavailabilities(
        self, venue_id: UUID, user: CurrentUser
    ) -> list[dict]:
        """Returns list of unavailability windows for the venue."""
        resp = await self._client.get(
            f"/venues/{venue_id}/unavailabilities", headers=self._headers(user)
        )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"venues-ms returned {resp.status_code} for unavailabilities",
            )
        return resp.json()


_venues_client = VenuesClient()


def get_venues_client() -> VenuesClient:
    return _venues_client
