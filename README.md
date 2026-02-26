# ploshtadka-bookings-ms

Manages venue bookings and status transitions.

**Port:** `8002` | **Prefix:** `/bookings`

## Endpoints

| Method | Path | Scope |
|---|---|---|
| `GET` | `/bookings/slots?venue_id=` | Any auth — returns `[{start, end}]` |
| `GET` | `/bookings` | `bookings:read` / `bookings:manage` / admin |
| `POST` | `/bookings` | `bookings:write` |
| `GET` | `/bookings/{id}` | Same as list |
| `PATCH` | `/bookings/{id}/status` | Depends on transition |
| `DELETE` | `/bookings/{id}` | `admin:bookings:delete` |

## Status transitions

```
PENDING  → CONFIRMED  (venue owner)   PENDING  → CANCELLED  (customer)
CONFIRMED → COMPLETED  (venue owner)   CONFIRMED → CANCELLED  (customer)
CONFIRMED → NO_SHOW    (venue owner)
```

## Running

```bash
uv run uvicorn main:application --host 0.0.0.0 --port 8002
uv run pytest
```

## Key env vars

| Variable | Default |
|---|---|
| `DB_URL` | `sqlite://:memory:` |
| `VENUES_MS_URL` | `http://localhost:8001` |
| `PAYMENTS_MS_URL` | `http://localhost:8003` |
| `REDIS_URL` | `redis://redis:6379/0` |

## Notes

- Auth via Traefik headers — no JWT validation here.
- Calls `venues-ms` to fetch venue owner at booking creation; `venue_owner_id` is then denormalized on the booking.
- Calls `payments-ms` to issue a refund when a venue owner cancels a confirmed booking.
- Redis caches `/bookings/slots` keyed by `slots:{venue_id}`, TTL 60s.
- Tests mock CRUD with `AsyncMock`; use `customer_client`/`owner_client`/`admin_client` fixtures.
