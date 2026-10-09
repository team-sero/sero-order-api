"""주문 API (카드 A-1).

3단계: 주문을 저장하기 전에 결제사를 부르고, 결제가 승인된 주문만 저장한다 (상태 PAID, payment_id 기록).
거절(402), 결제사 오류(502), 결제 시간 초과(504)면 저장하지 않는다. 이 응답은 main.py의 예외 처리기가 만든다.
"""
import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .db import Database, DatabaseUnavailable
from .payments import Payments

log = logging.getLogger("order_api.orders")
router = APIRouter()

STATUS_PAID = "PAID"

ORDER_COLUMNS = "order_id, user_id, store_id, items, total_amount, status, payment_id, created_at"


class OrderItem(BaseModel):
    menu_id: str = Field(min_length=1, max_length=64)
    qty: int = Field(ge=1, le=20)
    price: int = Field(ge=0, le=1_000_000, description="원 단위 단가")


class OrderCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    store_id: str = Field(min_length=1, max_length=64)
    items: list[OrderItem] = Field(min_length=1, max_length=20)


class Order(BaseModel):
    order_id: UUID
    user_id: str
    store_id: str
    items: list[OrderItem]
    total_amount: int
    status: str
    payment_id: str | None = None  # 2단계에 저장된 주문(CREATED)은 비어 있다
    created_at: datetime


def get_db(request: Request) -> Database:
    return request.app.state.db


DB = Annotated[Database, Depends(get_db)]


def get_payments(request: Request) -> Payments:
    return request.app.state.payments


PAY = Annotated[Payments, Depends(get_payments)]

# /docs에 실패 응답도 보이게 적어 둔다
CREATE_RESPONSES = {
    402: {"description": "결제 거절"},
    502: {"description": "결제사 오류 또는 연결 불가"},
    503: {"description": "DB 문제"},
    504: {"description": "결제 시간 초과"},
}
GET_RESPONSES = {404: {"description": "없는 주문"}, 503: {"description": "DB 문제"}}


@router.post("/orders", status_code=201, response_model=Order, responses=CREATE_RESPONSES)
async def create_order(body: OrderCreate, db: DB, payments: PAY, response: Response) -> Order:
    # 주문번호는 저장 전에 만든다. 저장되지 않는 주문(결제 거절, 실패)도 로그로 추적하려는 것
    order_id = uuid4()
    total_amount = sum(item.price * item.qty for item in body.items)
    items = [item.model_dump() for item in body.items]

    # DB에 쿼리가 안 되면 결제부터 하지 않는다. 승인만 되고 저장하지 못하는 경우를 줄인다.
    # 커넥션은 결제를 기다리는 동안 들고 있지 않는다(0.8초씩 쥐고 있으면 풀이 금방 바닥난다)
    async with db.connection() as conn:
        await conn.fetchval("SELECT 1")

    payment_id = await payments.charge(order_id, total_amount)

    try:
        async with db.connection() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO orders (order_id, user_id, store_id, items, total_amount, status, payment_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING {ORDER_COLUMNS}
                """,
                order_id,
                body.user_id,
                body.store_id,
                items,
                total_amount,
                STATUS_PAID,
                payment_id,
            )
    except Exception as exc:
        # 결제는 승인됐는데 저장하지 못했다. 실제 서비스라면 결제를 취소해야 하는 상황이라 payment_id를 남긴다.
        # 응답(503이나 500)은 그대로 위로 올려서 기존 처리기가 만든다
        error_type = str(exc) if isinstance(exc, DatabaseUnavailable) else type(exc).__name__
        log.error(
            f"order not saved after payment approved (payment_id {payment_id})",
            extra={"event": "order_save_failed", "order_id": str(order_id), "error_type": error_type},
        )
        raise

    log.info(
        "order created",
        extra={"event": "order_created", "order_id": str(order_id), "user_id": body.user_id},
    )
    response.headers["Location"] = f"/orders/{order_id}"
    return Order.model_validate(dict(row))


@router.get("/orders/{order_id}", response_model=Order, responses=GET_RESPONSES)
async def get_order(order_id: UUID, db: DB) -> Order:
    async with db.connection() as conn:
        row = await conn.fetchrow(f"SELECT {ORDER_COLUMNS} FROM orders WHERE order_id = $1", order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    return Order.model_validate(dict(row))