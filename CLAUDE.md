# CLAUDE.md — ploshtadka-bookings-ms

FastAPI microservice for managing venue bookings (part of the PloshtadkaBG platform).

## Package management

Always use `uv`. Never use `pip` directly.

```bash
uv add <package>       # add dependency
uv sync                # install from lockfile
uv run <command>       # run in the venv
```

## Running

```bash
uv run pytest                                                       # run tests
uv run uvicorn main:application --host 0.0.0.0 --port 8002         # dev server
```

## Architecture

### Technology Stack

- **API Framework**: FastAPI with Uvicorn
- **Database**: PostgreSQL with Tortoise ORM and Aerich migrations
- **Testing**: pytest with AsyncMock-based CRUD mocking (no real DB in tests)

## Auth architecture — critical

Auth is delegated entirely to Traefik via `forwardAuth`. JWT validation happens at the gateway. This service only reads the headers Traefik injects after a successful check:

| Header          | Type   | Description                        |
|-----------------|--------|------------------------------------|
| `X-User-ID`     | UUID   | Authenticated user's ID            |
| `X-Username`    | string | Authenticated user's username      |
| `X-User-Scopes` | string | Space-separated list of scopes     |

`get_current_user()` in `app/deps.py` reads these headers — it does not validate any token itself. **Do not add JWT validation middleware inside this service.**

## Cross-service calls

Bookings-ms calls venues-ms via `VenuesClient` in `app/deps.py` using the internal Docker network (`http://venues-ms:8001`). It forwards the same Traefik headers so venues-ms auth works normally.

`VenuesClient` is injected as a FastAPI dependency via `get_venues_client()`. Override this in tests to mock HTTP calls.

## Project structure

```
app/
  settings.py          # DB_URL, USERS_MS_URL, VENUES_MS_URL (env vars)
  models.py            # Tortoise ORM model: Booking + BookingStatus
  schemas.py           # Pydantic schemas: BookingCreate, BookingStatusUpdate, BookingResponse, BookingFilters, BookingSlot
  crud.py              # BookingCRUD — all DB operations (conflict checks, CRUD)
  deps.py              # Auth deps, VenuesClient, scope checkers
  scopes.py            # BookingScope StrEnum + BOOKING_SCOPE_DESCRIPTIONS
  routers/
    booking.py         # /bookings CRUD + status transitions + GET /bookings/slots
tests/
  conftest.py          # Fixtures: customer_client, owner_client, admin_client, anon_app, client_factory
  factories.py         # make_customer(), make_venue_owner(), make_admin(), booking_response(), etc.
  test_bookings.py     # Full endpoint test suite
  test_scopes.py       # Scope enum/description tests
```

## Scopes

| Scope                   | Who has it     | Purpose                                      |
|-------------------------|----------------|----------------------------------------------|
| `bookings:read`         | Customer       | View own bookings                            |
| `bookings:write`        | Customer       | Create a booking                             |
| `bookings:cancel`       | Customer       | Cancel own booking                           |
| `bookings:manage`       | Venue owner    | Confirm / complete / no_show for own venues  |
| `admin:bookings`        | Admin          | Super-scope                                  |
| `admin:bookings:read`   | Admin          | Read any booking                             |
| `admin:bookings:write`  | Admin          | Modify any booking status                    |
| `admin:bookings:delete` | Admin          | Hard-delete any booking                      |

## Status transitions

```
PENDING  → CONFIRMED  (venue owner / admin)
PENDING  → CANCELLED  (customer / admin)
CONFIRMED → COMPLETED  (venue owner / admin)
CONFIRMED → CANCELLED  (customer / admin)
CONFIRMED → NO_SHOW    (venue owner / admin)
```

Terminal states: `COMPLETED`, `CANCELLED`, `NO_SHOW` — no further transitions allowed.

## Anonymous slots endpoint

`GET /bookings/slots?venue_id=<uuid>` — returns `[{start_datetime, end_datetime}]` for all PENDING+CONFIRMED bookings at a venue. **No user identity exposed.** Requires any valid auth token (blocks anonymous scraping). Used by the frontend booking grid to show occupied cells without revealing who booked them.

`BookingSlot` schema: only `start_datetime` + `end_datetime`. Define it **before** `/{booking_id}` routes in the router to avoid FastAPI matching "slots" as a UUID path param.

## Booking model

`venue_owner_id` is denormalized from venues-ms at booking creation time to avoid cross-service lookups on every status update. Do not expose it as a writable field.

## Testing conventions

- **Mock the CRUD layer** with `AsyncMock` — no DB (router tests)
- **Mock VenuesClient** via `client_factory(..., venues_client=mock_vc)` dependency override
- Status transition tests: use `booking_model(**overrides)` (Pydantic object) for `get_booking` mock, since the router accesses `.status`, `.user_id`, `.venue_owner_id` attributes
- Use `anon_app` for real scope/auth dep checks (403/422 assertions)

```python
# Router test pattern
with patch("app.routers.booking.booking_crud") as mock_crud:
    mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
    resp = customer_client.get("/bookings")
assert resp.status_code == 200
```

## Database

- Tests: SQLite in-memory (default, mocked via CRUD patch)
- Production: PostgreSQL (`DB_URL` env var)
- Migrations: Aerich

```bash
uv run aerich migrate --name <description>
uv run aerich upgrade
```

## Environment variables

| Variable        | Default                   | Description                        |
|-----------------|---------------------------|------------------------------------|
| `DB_URL`        | `sqlite://:memory:`       | Database connection string         |
| `USERS_MS_URL`  | `http://localhost:8000`   | Users microservice base URL        |
| `VENUES_MS_URL` | `http://localhost:8001`   | Venues microservice base URL       |
