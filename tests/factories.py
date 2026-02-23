"""
All test-data builders in one place.
Import from here in every test file — never define dummy data inline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.deps import CurrentUser
from app.scopes import BookingScope

# ---------------------------------------------------------------------------
# Stable IDs — use these when a specific, repeatable UUID is needed.
# Call uuid4() inline when you need a fresh one per test.
# ---------------------------------------------------------------------------

CUSTOMER_ID: UUID = uuid4()
VENUE_OWNER_ID: UUID = uuid4()
ADMIN_ID: UUID = uuid4()
OTHER_USER_ID: UUID = uuid4()

BOOKING_ID: UUID = uuid4()
VENUE_ID: UUID = uuid4()

NOW = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=2)


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------


def make_customer(
    user_id: UUID = CUSTOMER_ID,
    scopes: list[str] | None = None,
) -> CurrentUser:
    """Customer with read/write/cancel booking scopes and venues:read."""
    if scopes is None:
        scopes = [
            BookingScope.READ,
            BookingScope.WRITE,
            BookingScope.CANCEL,
            "venues:read",
        ]
    return CurrentUser(id=user_id, username=f"customer_{user_id}", scopes=scopes)


def make_venue_owner(
    user_id: UUID = VENUE_OWNER_ID,
    scopes: list[str] | None = None,
) -> CurrentUser:
    """Venue owner with manage booking scope and venues:read."""
    if scopes is None:
        scopes = [
            BookingScope.MANAGE,
            "venues:read",
        ]
    return CurrentUser(id=user_id, username=f"owner_{user_id}", scopes=scopes)


def make_admin() -> CurrentUser:
    """Admin with all admin:bookings:* scopes."""
    return CurrentUser(
        id=ADMIN_ID,
        username="admin",
        scopes=[
            "admin:scopes",
            "venues:read",
            BookingScope.READ,
            BookingScope.ADMIN,
            BookingScope.ADMIN_READ,
            BookingScope.ADMIN_WRITE,
            BookingScope.ADMIN_DELETE,
        ],
    )


# ---------------------------------------------------------------------------
# Response dict factories  (mirror what the CRUD layer returns as dicts)
# ---------------------------------------------------------------------------


def booking_response(**overrides) -> dict:
    base = dict(
        id=str(BOOKING_ID),
        venue_id=str(VENUE_ID),
        venue_owner_id=str(VENUE_OWNER_ID),
        user_id=str(CUSTOMER_ID),
        start_datetime=NOW.isoformat(),
        end_datetime=LATER.isoformat(),
        status="pending",
        price_per_hour="20.00",
        total_price="40.00",
        currency="EUR",
        notes=None,
        updated_at=NOW.isoformat(),
    )
    return {**base, **overrides}


def venue_dict(**overrides) -> dict:
    """Minimal venues-ms venue representation used by VenuesClient mocks."""
    base = dict(
        id=str(VENUE_ID),
        owner_id=str(VENUE_OWNER_ID),
        name="Test Court",
        status="active",
        price_per_hour="20.00",
        currency="EUR",
    )
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Request payload factories
# ---------------------------------------------------------------------------


def user_dict(user_id: UUID = CUSTOMER_ID, **overrides) -> dict:
    """Minimal users-ms user representation used by UsersClient mocks."""
    base = dict(
        id=str(user_id),
        username=f"user_{str(user_id)[:8]}",
        full_name="Test User",
        email="test@example.com",
        is_active=True,
        scopes=[],
        created_at=NOW.isoformat(),
    )
    return {**base, **overrides}


def booking_create_payload(**overrides) -> dict:
    base = dict(
        venue_id=str(VENUE_ID),
        start_datetime=NOW.isoformat(),
        end_datetime=LATER.isoformat(),
        notes=None,
    )
    return {**base, **overrides}
