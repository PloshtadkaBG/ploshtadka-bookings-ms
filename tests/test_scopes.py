"""Tests for BookingScope values and descriptions."""

from app.scopes import BOOKING_SCOPE_DESCRIPTIONS, BookingScope


class TestBookingScopeValues:
    def test_customer_read_scope(self):
        assert BookingScope.READ == "bookings:read"

    def test_customer_write_scope(self):
        assert BookingScope.WRITE == "bookings:write"

    def test_customer_cancel_scope(self):
        assert BookingScope.CANCEL == "bookings:cancel"

    def test_venue_owner_manage_scope(self):
        assert BookingScope.MANAGE == "bookings:manage"

    def test_admin_super_scope(self):
        assert BookingScope.ADMIN == "admin:bookings"

    def test_admin_read_scope(self):
        assert BookingScope.ADMIN_READ == "admin:bookings:read"

    def test_admin_write_scope(self):
        assert BookingScope.ADMIN_WRITE == "admin:bookings:write"

    def test_admin_delete_scope(self):
        assert BookingScope.ADMIN_DELETE == "admin:bookings:delete"

    def test_all_scopes_are_strings(self):
        for scope in BookingScope:
            assert isinstance(scope, str)


class TestBookingScopeDescriptions:
    def test_descriptions_is_a_dict(self):
        assert isinstance(BOOKING_SCOPE_DESCRIPTIONS, dict)

    def test_customer_scopes_have_descriptions(self):
        for scope in (BookingScope.READ, BookingScope.WRITE, BookingScope.CANCEL):
            assert scope in BOOKING_SCOPE_DESCRIPTIONS
            assert len(BOOKING_SCOPE_DESCRIPTIONS[scope]) > 0

    def test_manage_scope_has_description(self):
        assert BookingScope.MANAGE in BOOKING_SCOPE_DESCRIPTIONS

    def test_admin_scopes_have_descriptions(self):
        for scope in (
            BookingScope.ADMIN_READ,
            BookingScope.ADMIN_WRITE,
            BookingScope.ADMIN_DELETE,
        ):
            assert scope in BOOKING_SCOPE_DESCRIPTIONS

    def test_all_description_values_are_non_empty_strings(self):
        for key, value in BOOKING_SCOPE_DESCRIPTIONS.items():
            assert isinstance(key, str)
            assert isinstance(value, str)
            assert len(value) > 0
