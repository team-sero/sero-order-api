"""결제사(payment-mock) 호출.

* 주문을 저장하기 전에 부른다. 승인되면 payment_id를 돌려주고, 아니면 아래 예외를 올린다
  * PaymentDeclined: 결제사가 거절했다 → 402
  * PaymentFailed: 결제사가 오류로 답했거나 닿지 않는다 → 502
  * PaymentTimeout: 제한 시간 안에 답이 없다 → 504
* httpx.AsyncClient 하나를 앱이 떠 있는 동안 계속 쓴다(keep-alive 연결 재사용).
  동기 클라이언트로 바꾸면 이벤트 루프 전체가 멈춘다(S07)
* 재시도는 일부러 하지 않는다. 재시도가 들어간 버전은 S27에서 따로 만든다
"""
from uuid import UUID

import httpx


class PaymentError(Exception):
    def __init__(self, order_id: UUID, message: str, error_type: str | None = None) -> None:
        super().__init__(message)
        self.order_id = order_id
        self.message = message
        self.error_type = error_type


class PaymentDeclined(PaymentError):
    def __init__(self, order_id: UUID, reason: str) -> None:
        super().__init__(order_id, f"payment declined ({reason})")
        self.reason = reason


class PaymentFailed(PaymentError):
    pass


class PaymentTimeout(PaymentError):
    pass


def _root_cause(exc: BaseException) -> BaseException:
    """httpx 예외가 감싼 맨 안쪽 오류. 연결 거부(ConnectionRefusedError)와 DNS 실패(gaierror)를 가르려고 쓴다."""
    seen = {id(exc)}
    while True:
        inner = exc.__cause__ or exc.__context__
        if inner is None or id(inner) in seen:
            return exc
        seen.add(id(inner))
        exc = inner


class Payments:
    def __init__(self, base_url: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def charge(self, order_id: UUID, amount: int) -> str:
        """결제를 요청하고 승인되면 payment_id를 돌려준다."""
        try:
            resp = await self._client.post("/payments", json={"order_id": str(order_id), "amount": amount})
        except httpx.TimeoutException as exc:
            # ConnectTimeout, ReadTimeout, PoolTimeout 같은 이름이 error_type에 남는다
            raise PaymentTimeout(order_id, "payment timeout", type(exc).__name__) from exc
        except httpx.TransportError as exc:
            # 연결 거부, DNS 실패 같은 것. 원래 오류 이름을 남겨야 S13(연결 불가)과 S16(DNS 실패)이 갈린다
            error_type = type(_root_cause(exc)).__name__
            raise PaymentFailed(order_id, "payment provider unreachable", error_type) from exc

        if resp.status_code != 200:
            message = f"payment failed: provider returned {resp.status_code}"
            raise PaymentFailed(order_id, message, "PaymentProviderError")
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if body.get("status") == "APPROVED" and body.get("payment_id"):
            return body["payment_id"]
        if body.get("status") == "DECLINED":
            raise PaymentDeclined(order_id, body.get("reason") or "UNKNOWN")
        raise PaymentFailed(order_id, "payment failed: unexpected response", "PaymentProviderError")