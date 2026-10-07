"""주문 API (카드 A-1).

2단계: 주문 생성, 조회. 3단계에서 생성 흐름 가운데에 결제 호출이 들어가고,
결제가 승인된 주문만 저장한다 (상태 PAID, payment_id 기록).
"""
import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .db import Database

log = logging.getLogger("order_api.orders")
router = APIRouter()

STATUS_CREATED = "CREATED"

ORDER_COLUMNS = "order_id, user_id, store_id, items, total_amount, status, created_at"


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
    created_at: datetime


def get_db(request: Request) -> Database:
    return request.app.state.db


DB = Annotated[Database, Depends(get_db)]


@router.post("/orders", status_code=201, response_model=Order)
async def create_order(body: OrderCreate, db: DB, response: Response) -> Order:
    order_id = uuid4()
    total_amount = sum(item.price * item.qty for item in body.items)
    items = [item.model_dump() for item in body.items]

    async with db.connection() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO orders (order_id, user_id, store_id, items, total_amount, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING {ORDER_COLUMNS}
            """,
            order_id,
            body.user_id,
            body.store_id,
            items,
            total_amount,
            STATUS_CREATED,
        )

    log.info(
        "order created",
        extra={"event": "order_created", "order_id": str(order_id), "user_id": body.user_id},
    )
    response.headers["Location"] = f"/orders/{order_id}"
    return Order.model_validate(dict(row))


@router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: UUID, db: DB) -> Order:
    async with db.connection() as conn:
        row = await conn.fetchrow(f"SELECT {ORDER_COLUMNS} FROM orders WHERE order_id = $1", order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    return Order.model_validate(dict(row))