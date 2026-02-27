from fastapi import APIRouter, Response
from tortoise import Tortoise

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness():
    return {"status": "ok"}


@router.get("/ready")
async def readiness():
    try:
        conn = Tortoise.get_connection("default")
        await conn.execute_query("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        return Response(
            content=f'{{"status": "error", "detail": "{exc}"}}',
            status_code=503,
            media_type="application/json",
        )
