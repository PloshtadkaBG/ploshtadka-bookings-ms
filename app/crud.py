from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from ms_core import CRUD
from tortoise.transactions import in_transaction

from app.models import Booking, BookingStatus
from app.schemas import BookingFilters, BookingResponse, BookingSlot, BookingStatusUpdate


def _to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware, handling both aware and naive inputs."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _overlaps_unavailabilities(
    start: datetime,
    end: datetime,
    unavailabilities: list[dict],
) -> bool:
    """Return True if [start, end) overlaps any unavailability window."""
    for u in unavailabilities:
        u_start = _to_utc(datetime.fromisoformat(u["start_datetime"]))
        u_end = _to_utc(datetime.fromisoformat(u["end_datetime"]))
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
          - no DB conflict with existing active bookings (atomic, locked)
          - no overlap with venue unavailability windows
        """
        # Check unavailabilities outside the transaction (no DB rows involved)
        if _overlaps_unavailabilities(start_datetime, end_datetime, unavailabilities):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking overlaps with a venue unavailability period",
            )

        duration_hours = Decimal(
            str((end_datetime - start_datetime).total_seconds() / 3600)
        )
        total_price = (price_per_hour * duration_hours).quantize(Decimal("0.01"))

        # Atomic check-then-insert: SELECT FOR UPDATE prevents double-booking
        async with in_transaction():
            if await Booking.filter(
                venue_id=venue_id,
                status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
                start_datetime__lt=end_datetime,
                end_datetime__gt=start_datetime,
            ).select_for_update().exists():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Booking conflicts with an existing booking for this venue",
                )

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

    async def list_occupied_slots(self, venue_id: UUID) -> list[BookingSlot]:
        """Return booked time windows for a venue — no user info exposed."""
        bookings = await Booking.filter(
            venue_id=venue_id,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
        ).only("start_datetime", "end_datetime")
        return [BookingSlot.model_validate(b, from_attributes=True) for b in bookings]

    async def delete_booking(self, booking_id: UUID) -> bool:
        return await self.delete_by(id=booking_id)


booking_crud = BookingCRUD(Booking, BookingResponse)
