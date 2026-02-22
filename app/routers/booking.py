from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.crud import booking_crud
from app.deps import (
    CurrentUser,
    VenuesClient,
    can_admin_delete_booking,
    can_read_or_manage_booking,
    can_write_booking,
    get_current_user,
    get_venues_client,
)
from app.schemas import (
    BookingCreate,
    BookingFilters,
    BookingResponse,
    BookingStatus,
    BookingStatusUpdate,
)
from app.scopes import BookingScope

router = APIRouter(prefix="/bookings", tags=["bookings"])

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
      pending  → cancelled  : CANCEL + booker,       OR admin
      confirmed → completed  : MANAGE + venue owner, OR admin
      confirmed → cancelled  : CANCEL + booker,       OR admin
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

    if new_status in _MANAGE_STATUSES:
        is_venue_owner = current_user.id == booking_venue_owner_id
        has_manage = BookingScope.MANAGE in current_user.scopes
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
        if not (has_cancel and is_booker):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Transitioning to '{new_status}' requires "
                    f"'{BookingScope.CANCEL}' scope and being the booking owner."
                ),
            )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[BookingResponse])
async def list_bookings(
    filters: BookingFilters = Depends(),
    current_user: CurrentUser = Depends(can_read_or_manage_booking),
) -> list[BookingResponse]:
    is_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_READ in current_user.scopes
    )
    is_manager = BookingScope.MANAGE in current_user.scopes
    is_reader = BookingScope.READ in current_user.scopes

    if is_admin:
        return await booking_crud.list_bookings(filters=filters)
    if is_manager and not is_reader:
        # Venue owner: see bookings for their venues
        return await booking_crud.list_bookings(
            filters=filters, venue_owner_id=current_user.id
        )
    # Customer: see own bookings
    return await booking_crud.list_bookings(filters=filters, user_id=current_user.id)


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

    return await booking_crud.create_booking(
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


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    current_user: CurrentUser = Depends(can_read_or_manage_booking),
) -> BookingResponse:
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
    return booking


@router.patch("/{booking_id}/status", response_model=BookingResponse)
async def update_booking_status(
    booking_id: UUID,
    payload: BookingStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
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
