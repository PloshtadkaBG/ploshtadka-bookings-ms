from enum import StrEnum


class BookingScope(StrEnum):
    # Customer scopes
    READ = "bookings:read"  # view own bookings
    WRITE = "bookings:write"  # create a booking
    CANCEL = "bookings:cancel"  # cancel own booking

    # Venue owner scopes
    MANAGE = "bookings:manage"  # confirm / complete / no_show for own venue's bookings

    # Admin scopes
    ADMIN = "admin:bookings"
    ADMIN_READ = "admin:bookings:read"
    ADMIN_WRITE = "admin:bookings:write"
    ADMIN_DELETE = "admin:bookings:delete"


BOOKING_SCOPE_DESCRIPTIONS: dict[str, str] = {
    BookingScope.READ: "View your own bookings.",
    BookingScope.WRITE: "Create a new booking at a venue.",
    BookingScope.CANCEL: "Cancel your own pending or confirmed booking.",
    BookingScope.MANAGE: "Confirm, complete, or mark no-show on your venue bookings.",
    BookingScope.ADMIN_READ: "Read any booking regardless of owner (admin).",
    BookingScope.ADMIN_WRITE: "Modify any booking status (admin).",
    BookingScope.ADMIN_DELETE: "Hard-delete any booking (admin).",
}
