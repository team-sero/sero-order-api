"""order-api: 배달 서비스 주문 API (카드 A-1)."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import Database, DatabaseUnavailable
from .orders import router as orders_router

log = logging.getLogger("order_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = Database(
        settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        timeout=settings.db_timeout_seconds,
    )
    app.state.db = db
    # DB 연결은 뒤에서 기다린다. 앱은 바로 뜨고, 연결 전까지는 readiness만 503
    connect_task = asyncio.create_task(db.connect_forever())
    log.info("service started", extra={"event": "startup"})
    yield
    # SIGTERM(정상 종료)일 때만 여기까지 온다. OOMKilled(SIGKILL)면 이 줄이 안 남는다.
    log.info("service stopping", extra={"event": "shutdown"})
    connect_task.cancel()
    with suppress(asyncio.CancelledError):
        await connect_task
    await db.close()


app = FastAPI(title="order-api", lifespan=lifespan)
app.include_router(orders_router)


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
    log.error("database unavailable", extra={"event": "db_unavailable", "error_type": str(exc)})
    return JSONResponse({"detail": "database unavailable"}, status_code=503)


@app.get("/healthz")
async def healthz():
    """liveness: 프로세스가 응답하는지만 본다. DB 같은 바깥 의존성은 확인하지 않는다."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request):
    """readiness: DB에 쿼리가 되면 준비 완료. 안 되면 503이라 트래픽에서 빠진다."""
    if not await request.app.state.db.is_healthy():
        return JSONResponse({"status": "not_ready", "reason": "database"}, status_code=503)
    return {"status": "ready"}