"""order-api: 배달 서비스 주문 API (카드 A-1).

1단계: 앱 뼈대, 헬스체크, 시작/종료 로그.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

log = logging.getLogger("order_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 2단계에서 DB 연결이 확인된 뒤에 True로 바꾼다
    app.state.ready = True
    log.info("service started", extra={"event": "startup"})
    yield
    # SIGTERM(정상 종료)일 때만 여기까지 온다. OOMKilled(SIGKILL)면 이 줄이 안 남는다.
    app.state.ready = False
    log.info("service stopping", extra={"event": "shutdown"})


app = FastAPI(title="order-api", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    """liveness: 프로세스가 응답하는지만 본다. DB 같은 바깥 의존성은 확인하지 않는다."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """readiness: 요청을 받을 준비가 됐는지. 2단계에서 DB 확인이 들어간다."""
    if not getattr(app.state, "ready", False):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ready"}
