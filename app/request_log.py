"""요청 로그(4단계). 요청 하나가 끝나면 JSON 한 줄(event request)을 남긴다.

* 필드: method, path(경로 템플릿. 예: /orders/{order_id}), status, duration_ms. 알 수 있으면 order_id, user_id
* 남기는 것
  * 조회(GET, HEAD)가 아닌 요청은 전부 남긴다. 주문 생성이 빠짐없이 남아서 로그만으로 오류율과 응답 시간을 셀 수 있다
  * 조회는 4xx, 5xx이거나 느릴 때(SLOW_MS 이상)만 남긴다. 정상이고 빠른 조회까지 남기면 조회가 몰릴 때
    초당 천 줄 넘게 쌓여서, 근거는 늘지 않고 Loki와 조사 질의만 무거워진다
  * 헬스체크(/healthz, /readyz)는 실패했을 때만 남긴다. kubelet이 몇 초마다 부른다
* level은 5xx면 error, 나머지는 info다
* 처리기가 못 잡은 예외는 500과 error_type(예외 이름)으로 남기고 그대로 올린다. 응답은 Starlette가 500으로 만든다
* 순수 ASGI 미들웨어로 짰다. 남기지 않는 요청에는 시각 재기와 비교 몇 번만 더해진다
"""
import logging
import time

log = logging.getLogger("order_api.request")

SLOW_MS = 1000.0  # 이보다 오래 걸린 조회는 정상이어도 남긴다
PROBE_PATHS = ("/healthz", "/readyz")
READ_METHODS = ("GET", "HEAD")


def should_log(method: str, path: str, status: int, duration_ms: float) -> bool:
    """이 요청을 남길지. 실패는 언제나 남긴다."""
    if status >= 400:
        return True
    if path in PROBE_PATHS:
        return False
    if method in READ_METHODS:
        return duration_ms >= SLOW_MS
    return True


class RequestLogMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = None
        error_type = None

        async def send_and_keep_status(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_keep_status)
        except BaseException as exc:
            error_type = type(exc).__name__
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            if status is None:  # 응답을 시작하기 전에 예외가 났다. Starlette가 500으로 답한다
                status = 500
            # 라우터가 고른 경로 템플릿. 맞는 경로가 없으면(404) 원본 경로 대신 unmatched로 남긴다(주문번호 같은 값이 섞이지 않게)
            path = getattr(scope.get("route"), "path", None) or "unmatched"
            method = scope.get("method", "")
            if should_log(method, path, status, duration_ms):
                extra = {
                    "event": "request",
                    "method": method,
                    "path": path,
                    "status": status,
                    "duration_ms": round(duration_ms, 1),
                }
                # 주문 생성은 처리기가 request.state에 넣어 준다. 조회는 경로에 주문번호가 있다
                state = scope.get("state") or {}
                order_id = state.get("order_id") or (scope.get("path_params") or {}).get("order_id")
                if order_id:
                    extra["order_id"] = str(order_id)
                if state.get("user_id"):
                    extra["user_id"] = state["user_id"]
                if error_type:
                    extra["error_type"] = error_type
                level = logging.ERROR if status >= 500 else logging.INFO
                log.log(level, f"{method} {path} {status}", extra=extra)
