"""Postgres 연결 관리 (asyncpg).

* 앱은 DB 없이도 뜬다. 연결은 뒤에서 될 때까지 다시 시도하고, 그동안 readiness만 503이다.
  DB가 늦게 떠도 앱이 죽었다 살아나지 않게 하려는 것. 재시작 횟수는 Alert 1이 보는 지표라
  배포할 때마다 재시작이 섞이면 안 된다.
* 테이블은 처음 연결할 때 만든다. 레플리카 여러 개가 동시에 떠도 겹치지 않게 advisory lock을 건다.
"""
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

log = logging.getLogger("order_api.db")

# 아무 숫자나 괜찮고, order-api 인스턴스끼리만 같으면 된다
SCHEMA_LOCK_KEY = 4_102_001

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    order_id     UUID PRIMARY KEY,
    user_id      TEXT NOT NULL,
    store_id     TEXT NOT NULL,
    items        JSONB NOT NULL,
    total_amount INTEGER NOT NULL CHECK (total_amount >= 0),
    status       TEXT NOT NULL,
    payment_id   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# DB에 못 닿거나 너무 늦을 때 나는 오류들. 503으로 돌려준다. 나머지 오류는 코드 문제라 500.
UNAVAILABLE_ERRORS = (
    OSError,
    TimeoutError,
    asyncpg.InterfaceError,
    asyncpg.exceptions.PostgresConnectionError,
    asyncpg.exceptions.OperatorInterventionError,
    asyncpg.exceptions.InsufficientResourcesError,
)


class DatabaseUnavailable(Exception):
    """DB에 연결할 수 없거나 응답이 제한 시간을 넘겼을 때. 인자는 원래 오류의 이름."""


class Database:
    def __init__(self, dsn: str, min_size: int, max_size: int, timeout: float) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._timeout = timeout
        self.pool: asyncpg.Pool | None = None

    @staticmethod
    async def _init_connection(conn: asyncpg.Connection) -> None:
        # JSONB를 파이썬 list, dict로 바로 주고받기
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    async def connect_forever(self, retry_seconds: float = 2.0) -> None:
        """연결되고 테이블이 준비될 때까지 다시 시도한다. lifespan에서 백그라운드로 돌린다."""
        attempt = 0
        while self.pool is None:
            attempt += 1
            pool = None
            try:
                pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    timeout=self._timeout,  # 연결 맺기 제한 시간
                    command_timeout=self._timeout,  # 쿼리 제한 시간
                    init=self._init_connection,
                )
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute("SELECT pg_advisory_xact_lock($1)", SCHEMA_LOCK_KEY)
                        await conn.execute(SCHEMA_SQL)
                self.pool = pool
                log.info("db connected", extra={"event": "db_connected"})
            except asyncio.CancelledError:
                if pool is not None:
                    pool.terminate()
                raise
            except Exception as exc:
                if pool is not None:
                    pool.terminate()
                log.warning(
                    f"db connect failed (attempt {attempt}), retrying in {retry_seconds:g}s",
                    extra={"event": "db_connect_retry", "error_type": type(exc).__name__},
                )
                await asyncio.sleep(retry_seconds)

    async def close(self) -> None:
        if self.pool is None:
            return
        try:
            await asyncio.wait_for(self.pool.close(), timeout=5)
        except TimeoutError:
            self.pool.terminate()
        self.pool = None

    async def is_healthy(self) -> bool:
        """readiness용. 짧은 제한 시간으로 SELECT 1이 되는지만 본다."""
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire(timeout=1.0) as conn:
                await conn.fetchval("SELECT 1", timeout=1.0)
            return True
        except Exception:
            return False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        """커넥션 하나를 빌려준다. DB 문제는 DatabaseUnavailable로 바꿔서 올린다."""
        if self.pool is None:
            raise DatabaseUnavailable("NotConnected")
        try:
            async with self.pool.acquire(timeout=self._timeout) as conn:
                yield conn
        except UNAVAILABLE_ERRORS as exc:
            raise DatabaseUnavailable(type(exc).__name__) from exc