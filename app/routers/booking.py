import asyncio
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.cache import get_slots_cache, invalidate_slots_cache, set_slots_cache
from app.crud import booking_crud
from app.deps import (
    CurrentUser,
    PaymentsClient,
    UsersClient,
    VenuesClient,
    can_admin_delete_booking,
    can_read_or_manage_booking,
    can_write_booking,
    get_current_user,
    get_payments_client,
    get_users_client,
    get_venues_client,
)
from app.schemas import (
    BookingCreate,
    BookingEnriched,
    BookingFilters,
    BookingResponse,
    BookingSlot,
    BookingStatus,
    BookingStatusUpdate,
)
from app.scopes import BookingScope

router = APIRouter(prefix="/bookings", tags=["bookings"])


# ---------------------------------------------------------------------------
# Enrichment helper
# ---------------------------------------------------------------------------


async def _enrich(
    bookings: list,
    current_user: CurrentUser,
    venues_client: VenuesClient,
    users_client: UsersClient,
) -> list[BookingEnriched]:
    """
    Convert a list of raw booking objects into BookingEnriched by fetching
    venue names and user names from upstream services in parallel.
    Both upstream calls degrade gracefully — enriched fields become None on error.
    """
    if not bookings:
        return []

    parsed = [BookingResponse.model_validate(b, from_attributes=True) for b in bookings]

    venue_ids = {b.venue_id for b in parsed}
    user_ids = {b.user_id for b in parsed} | {b.venue_owner_id for b in parsed}

    venues_raw, users_raw = await asyncio.gather(
        venues_client.get_by_ids(venue_ids, current_user),
        users_client.get_by_ids(user_ids, current_user),
    )

    venue_map: dict[str, str | None] = {v["id"]: v.get("name") for v in venues_raw}
    user_map: dict[str, dict] = {
        u["id"]: {"username": u.get("username"), "full_name": u.get("full_name")}
        for u in users_raw
    }

    result = []
    for b in parsed:
        customer = user_map.get(str(b.user_id), {})
        owner = user_map.get(str(b.venue_owner_id), {})
        result.append(
            BookingEnriched(
                **b.model_dump(),
                venue_name=venue_map.get(str(b.venue_id)),
                customer_username=customer.get("username"),
                customer_full_name=customer.get("full_name"),
                owner_username=owner.get("username"),
                owner_full_name=owner.get("full_name"),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Transition guard helpers
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.NO_SHOW: set(),
}

# Which scope is required (on top of the valid-transition check) per target status
_MANAGE_STATUSES = {
    BookingStatus.CONFIRMED,
    BookingStatus.COMPLETED,
    BookingStatus.NO_SHOW,
}
_CANCEL_STATUSES = {BookingStatus.CANCELLED}


def _assert_transition(
    old_status: BookingStatus,
    new_status: BookingStatus,
    booking_user_id: UUID,
    booking_venue_owner_id: UUID,
    current_user: CurrentUser,
) -> None:
    """
    Raise HTTP 400/403 if the transition is invalid or the caller lacks permission.

    Rules:
      pending  → confirmed  : MANAGE + venue owner, OR admin
      pending  → cancelled  : CANCEL + booker, OR MANAGE + venue owner, OR admin
      confirmed → completed  : MANAGE + venue owner, OR admin
      confirmed → cancelled  : CANCEL + booker, OR MANAGE + venue owner, OR admin
      confirmed → no_show    : MANAGE + venue owner, OR admin
    """
    if new_status not in _VALID_TRANSITIONS.get(old_status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition from '{old_status}' to '{new_status}'. "
                "Allowed: "
                f"{[s.value for s in _VALID_TRANSITIONS.get(old_status, set())]}"
            ),
        )

    is_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_WRITE in current_user.scopes
    )
    if is_admin:
        return

    is_venue_owner = current_user.id == booking_venue_owner_id
    has_manage = BookingScope.MANAGE in current_user.scopes

    if new_status in _MANAGE_STATUSES:
        if not (has_manage and is_venue_owner):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Transitioning to '{new_status}' requires "
                    f"'{BookingScope.MANAGE}' scope and being the venue owner."
                ),
            )

    elif new_status in _CANCEL_STATUSES:
        is_booker = current_user.id == booking_user_id
        has_cancel = BookingScope.CANCEL in current_user.scopes
        # Either the customer cancels their own booking, or the venue owner refuses it
        if not ((has_cancel and is_booker) or (has_manage and is_venue_owner)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Transitioning to '{new_status}' requires "
                    f"'{BookingScope.CANCEL}' scope as the booking owner, "
                    f"or '{BookingScope.MANAGE}' scope as the venue owner."
                ),
            )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/slots", response_model=list[BookingSlot])
async def get_venue_slots(
    venue_id: UUID,
    _: CurrentUser = Depends(get_current_user),
) -> list[BookingSlot]:
    """
    Returns occupied time windows for a venue.
    Any authenticated user can call this — response contains NO user identity.
    """
    cached = await get_slots_cache(venue_id)
    if cached is not None:
        logger.debug("Cache hit for slots: venue_id={}", venue_id)
        return [BookingSlot(**s) for s in cached]

    logger.debug("Cache miss for slots: venue_id={}", venue_id)
    slots = await booking_crud.list_occupied_slots(venue_id)
    await set_slots_cache(venue_id, [s.model_dump(mode="json") for s in slots])
    return slots


@router.get("/", response_model=list[BookingEnriched])
async def list_bookings(
    filters: BookingFilters = Depends(),
    current_user: CurrentUser = Depends(can_read_or_manage_booking),
    venues_client: VenuesClient = Depends(get_venues_client),
    users_client: UsersClient = Depends(get_users_client),
) -> list[BookingEnriched]:
    is_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_READ in current_user.scopes
    )
    is_manager = BookingScope.MANAGE in current_user.scopes
    is_reader = BookingScope.READ in current_user.scopes

    if is_admin:
        bookings = await booking_crud.list_bookings(filters=filters)
    elif is_manager and not is_reader:
        bookings = await booking_crud.list_bookings(
            filters=filters, venue_owner_id=current_user.id
        )
    else:
        bookings = await booking_crud.list_bookings(
            filters=filters, user_id=current_user.id
        )

    return await _enrich(bookings, current_user, venues_client, users_client)


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    current_user: CurrentUser = Depends(can_write_booking),
    venues_client: VenuesClient = Depends(get_venues_client),
) -> BookingResponse:
    # 1. Validate venue exists and is ACTIVE
    venue = await venues_client.get_venue(payload.venue_id, current_user)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )
    if venue.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Venue is not available for booking (status: {venue.get('status')})"
            ),
        )

    # 2. Fetch unavailabilities and check for conflicts in CRUD
    unavailabilities = await venues_client.get_unavailabilities(
        payload.venue_id, current_user
    )

    booking = await booking_crud.create_booking(
        venue_id=payload.venue_id,
        venue_owner_id=UUID(venue["owner_id"]),
        user_id=current_user.id,
        start_datetime=payload.start_datetime,
        end_datetime=payload.end_datetime,
        price_per_hour=Decimal(str(venue["price_per_hour"])),
        currency=venue.get("currency", "EUR"),
        notes=payload.notes,
        unavailabilities=unavailabilities,
    )
    await invalidate_slots_cache(payload.venue_id)
    return booking


@router.get("/{booking_id}", response_model=BookingEnriched)
async def get_booking(
    booking_id: UUID,
    current_user: CurrentUser = Depends(can_read_or_manage_booking),
    venues_client: VenuesClient = Depends(get_venues_client),
    users_client: UsersClient = Depends(get_users_client),
) -> BookingEnriched:
    is_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_READ in current_user.scopes
    )
    is_manager = BookingScope.MANAGE in current_user.scopes
    is_reader = BookingScope.READ in current_user.scopes

    if is_admin:
        booking = await booking_crud.get_booking(booking_id)
    elif is_manager and not is_reader:
        booking = await booking_crud.get_booking(
            booking_id, venue_owner_id=current_user.id
        )
    else:
        booking = await booking_crud.get_booking(booking_id, user_id=current_user.id)

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    results = await _enrich([booking], current_user, venues_client, users_client)
    return results[0]


@router.patch("/{booking_id}/status", response_model=BookingResponse)
async def update_booking_status(
    booking_id: UUID,
    payload: BookingStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    payments_client: PaymentsClient = Depends(get_payments_client),
) -> BookingResponse:
    # Fetch the booking without ownership filter — we validate permissions manually
    booking = await booking_crud.get_booking(booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    _assert_transition(
        old_status=booking.status,
        new_status=payload.status,
        booking_user_id=booking.user_id,
        booking_venue_owner_id=booking.venue_owner_id,
        current_user=current_user,
    )

    updated = await booking_crud.update_booking_status(booking_id, payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    await invalidate_slots_cache(booking.venue_id)

    # Trigger Stripe refund when the venue owner (or admin) cancels a paid booking.
    # Customer cancellations do NOT refund — per the no-refund policy for customers.
    # Failure to refund does not block the cancellation response.
    if payload.status == BookingStatus.CANCELLED:
        is_admin = (
            BookingScope.ADMIN in current_user.scopes
            or BookingScope.ADMIN_WRITE in current_user.scopes
        )
        is_venue_owner = current_user.id == booking.venue_owner_id
        if is_admin or is_venue_owner:
            await payments_client.refund_booking(booking_id, current_user)

    return updated


@router.delete(
    "/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(can_admin_delete_booking)],
)
async def delete_booking(booking_id: UUID) -> None:
    deleted = await booking_crud.delete_booking(booking_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
