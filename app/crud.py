from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from ms_core import CRUD

from app.models import Booking, BookingStatus
from app.schemas import BookingFilters, BookingResponse, BookingStatusUpdate


def _overlaps_unavailabilities(
    start: datetime,
    end: datetime,
    unavailabilities: list[dict],
) -> bool:
    """Return True if [start, end) overlaps any unavailability window."""
    for u in unavailabilities:
        u_start = datetime.fromisoformat(u["start_datetime"])
        u_end = datetime.fromisoformat(u["end_datetime"])
        if start < u_end and end > u_start:
            return True
    return False


class BookingCRUD(CRUD[Booking, BookingResponse]):  # type: ignore
    async def _has_db_conflict(
        self,
        venue_id: UUID,
        start: datetime,
        end: datetime,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Return True if an active booking overlaps the given window."""
        qs = Booking.filter(
            venue_id=venue_id,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
            start_datetime__lt=end,
            end_datetime__gt=start,
        )
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        return await qs.exists()

    async def create_booking(
        self,
        venue_id: UUID,
        venue_owner_id: UUID,
        user_id: UUID,
        start_datetime: datetime,
        end_datetime: datetime,
        price_per_hour: Decimal,
        currency: str,
        notes: str | None,
        unavailabilities: list[dict],
    ) -> BookingResponse:
        """
        Persist a new booking after validating:
          - no DB conflict with existing active bookings
          - no overlap with venue unavailability windows
        """
        if await self._has_db_conflict(venue_id, start_datetime, end_datetime):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking conflicts with an existing booking for this venue",
            )

        if _overlaps_unavailabilities(start_datetime, end_datetime, unavailabilities):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking overlaps with a venue unavailability period",
            )

        duration_hours = Decimal(
            str((end_datetime - start_datetime).total_seconds() / 3600)
        )
        total_price = (price_per_hour * duration_hours).quantize(Decimal("0.01"))

        inst = await Booking.create(
            venue_id=venue_id,
            venue_owner_id=venue_owner_id,
            user_id=user_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            price_per_hour=price_per_hour,
            total_price=total_price,
            currency=currency,
            notes=notes,
        )
        return BookingResponse.model_validate(inst, from_attributes=True)

    async def get_booking(
        self,
        booking_id: UUID,
        user_id: UUID | None = None,
        venue_owner_id: UUID | None = None,
    ) -> BookingResponse | None:
        """
        Fetch a booking by id.
        If user_id is set: only return if booking belongs to that customer.
        If venue_owner_id is set: only return if booking belongs to that venue owner.
        If neither is set: admin access — return any booking.
        """
        if user_id is not None:
            inst = await Booking.get_or_none(id=booking_id, user_id=user_id)
        elif venue_owner_id is not None:
            inst = await Booking.get_or_none(
                id=booking_id, venue_owner_id=venue_owner_id
            )
        else:
            inst = await Booking.get_or_none(id=booking_id)

        if not inst:
            return None
        return BookingResponse.model_validate(inst, from_attributes=True)

    async def list_bookings(
        self,
        filters: BookingFilters,
        user_id: UUID | None = None,
        venue_owner_id: UUID | None = None,
    ) -> list[BookingResponse]:
        """
        List bookings with optional ownership scoping.
        user_id restricts to customer's bookings.
        venue_owner_id restricts to bookings at the owner's venues.
        Neither means admin — returns all bookings.
        """
        qs = Booking.all()

        if user_id is not None:
            qs = qs.filter(user_id=user_id)
        if venue_owner_id is not None:
            qs = qs.filter(venue_owner_id=venue_owner_id)
        if filters.venue_id is not None:
            qs = qs.filter(venue_id=filters.venue_id)
        if filters.status is not None:
            qs = qs.filter(status=filters.status)

        offset = (filters.page - 1) * filters.page_size
        qs = qs.offset(offset).limit(filters.page_size)

        bookings = await qs
        return [
            BookingResponse.model_validate(b, from_attributes=True) for b in bookings
        ]

    async def update_booking_status(
        self,
        booking_id: UUID,
        payload: BookingStatusUpdate,
    ) -> BookingResponse | None:
        inst = await Booking.get_or_none(id=booking_id)
        if not inst:
            return None
        inst.status = payload.status  # type: ignore
        await inst.save(update_fields=["status"])
        return BookingResponse.model_validate(inst, from_attributes=True)

    async def delete_booking(self, booking_id: UUID) -> bool:
        return await self.delete_by(id=booking_id)


booking_crud = BookingCRUD(Booking, BookingResponse)
