import os

db_url = os.environ.get("DB_URL", "sqlite://:memory:")
users_ms_url = os.environ.get("USERS_MS_URL", "http://localhost:8000")
venues_ms_url = os.environ.get("VENUES_MS_URL", "http://localhost:8001")
payments_ms_url = os.environ.get("PAYMENTS_MS_URL", "http://localhost:8003")
