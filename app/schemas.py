from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class BookingCreate(BaseModel):
    venue_id: UUID
    start_datetime: datetime
    end_datetime: datetime
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("start_datetime", "end_datetime", mode="after")
    @classmethod
    def require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware (include UTC offset)")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_time_range(self) -> BookingCreate:
        if self.end_datetime <= self.start_datetime:
            raise ValueError("end_datetime must be after start_datetime")
        duration_seconds = (self.end_datetime - self.start_datetime).total_seconds()
        if duration_seconds < 3600:
            raise ValueError("Booking duration must be at least 1 hour")
        return self


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BookingResponse(BaseModel):
    id: UUID
    venue_id: UUID
    venue_owner_id: UUID
    user_id: UUID
    start_datetime: datetime
    end_datetime: datetime
    status: BookingStatus
    price_per_hour: Decimal
    total_price: Decimal
    currency: str
    notes: str | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingSlot(BaseModel):
    """Minimal occupied slot — reveals no user identity."""

    start_datetime: datetime
    end_datetime: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingFilters(BaseModel):
    """Bind to a FastAPI route via Depends(BookingFilters)."""

    venue_id: UUID | None = None
    status: BookingStatus | None = None

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
