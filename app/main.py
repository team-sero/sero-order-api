"""order-api: 배달 서비스 주문 API (카드 A-1)."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import Database, DatabaseUnavailable
from .orders import router as orders_router
from .payments import PaymentDeclined, PaymentFailed, Payments, PaymentTimeout

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
    # 결제사 클라이언트는 앱이 떠 있는 동안 하나를 계속 쓴다(연결 재사용)
    app.state.payments = Payments(settings.payment_url, settings.payment_timeout_seconds)
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
    await app.state.payments.close()


app = FastAPI(title="order-api", lifespan=lifespan)
app.include_router(orders_router)


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
    log.error("database unavailable", extra={"event": "db_unavailable", "error_type": str(exc)})
    return JSONResponse({"detail": "database unavailable"}, status_code=503)


# 결제 결과별 응답. 주문은 저장하지 않았고, 저장 전에 만든 order_id를 응답과 로그에 같이 남겨 추적한다
@app.exception_handler(PaymentDeclined)
async def payment_declined(request: Request, exc: PaymentDeclined) -> JSONResponse:
    log.info(exc.message, extra={"event": "payment_declined", "order_id": str(exc.order_id)})
    body = {"detail": "payment declined", "reason": exc.reason, "order_id": str(exc.order_id)}
    return JSONResponse(body, status_code=402)


@app.exception_handler(PaymentFailed)
async def payment_failed(request: Request, exc: PaymentFailed) -> JSONResponse:
    extra = {"event": "payment_failed", "order_id": str(exc.order_id), "error_type": exc.error_type}
    log.error(exc.message, extra=extra)
    return JSONResponse({"detail": "payment failed", "order_id": str(exc.order_id)}, status_code=502)


@app.exception_handler(PaymentTimeout)
async def payment_timeout(request: Request, exc: PaymentTimeout) -> JSONResponse:
    extra = {"event": "payment_timeout", "order_id": str(exc.order_id), "error_type": exc.error_type}
    log.error(exc.message, extra=extra)
    return JSONResponse({"detail": "payment timeout", "order_id": str(exc.order_id)}, status_code=504)


@app.get("/healthz")
async def healthz():
    """liveness: 프로세스가 응답하는지만 본다. DB 같은 바깥 의존성은 확인하지 않는다."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request):
    """readiness: DB에 쿼리가 되면 준비 완료. 안 되면 503이라 트래픽에서 빠진다.

    결제사는 확인하지 않는다. 결제사가 멈췄다고 모든 파드가 트래픽에서 빠지면 주문 조회까지 막힌다.
    """
    if not await request.app.state.db.is_healthy():
        return JSONResponse({"status": "not_ready", "reason": "database"}, status_code=503)
    return {"status": "ready"}