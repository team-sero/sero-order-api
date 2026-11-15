"""최근 주문 캐시(6단계).

주문을 만든 직후에는 앱이 주문 상태를 자주 다시 묻는다. 만든 주문을 잠깐 메모리에 두고, 그 조회가 DB까지 가지 않게 한다.

* 만든 주문만 넣는다. 조회한 주문은 넣지 않는다. 조회는 캐시에 있으면 캐시에서, 없으면 DB에서 읽는다
* 주문마다 상세 정보(주문 화면에 같이 보이는 가게와 메뉴 정보 묶음)를 같이 둔다. 크기는 ORDER_CACHE_ENTRY_KIB이고,
  실제로 채운 바이트라 넣자마자 메모리에 잡힌다
* 크기는 만료(ORDER_CACHE_TTL_SECONDS)와 개수 상한(ORDER_CACHE_MAX)으로 묶는다. 넣을 때마다 만료됐거나 상한을 넘은 것을
  오래된 것부터 지운다
* 한 프로세스 안의 캐시다. 파드마다 따로 있고, 다시 뜨면 비어서 시작한다
"""
import time
from collections import OrderedDict
from uuid import UUID

from pydantic import BaseModel


class OrderCache:
    def __init__(self, ttl_seconds: float, max_entries: int, entry_bytes: int) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.entry_bytes = entry_bytes
        # order_id → (넣은 시각, 주문, 상세 정보). 넣은 순서대로 있어서 맨 앞이 가장 오래된 것이다
        self._items: OrderedDict[UUID, tuple[float, BaseModel, bytes]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._items)

    def _detail(self, order: BaseModel) -> bytes:
        seed = order.model_dump_json().encode()
        return (seed * (self.entry_bytes // len(seed) + 1))[: self.entry_bytes]

    def put(self, order_id: UUID, order: BaseModel) -> None:
        if self.max_entries <= 0:
            return
        now = time.monotonic()
        self._items[order_id] = (now, order, self._detail(order))
        self._items.move_to_end(order_id)
        self._evict(now)

    def get(self, order_id: UUID) -> BaseModel | None:
        item = self._items.get(order_id)
        if item is None:
            return None
        if time.monotonic() - item[0] > self.ttl:
            del self._items[order_id]
            return None
        return item[1]

    def _evict(self, now: float) -> None:
        while self._items:
            oldest = next(iter(self._items))
            added = self._items[oldest][0]
            if len(self._items) > self.max_entries or now - added > self.ttl:
                del self._items[oldest]
            else:
                break
