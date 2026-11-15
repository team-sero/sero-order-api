"""주문 처리 작업 메모리(6단계).

주문 생성 요청 하나가 끝날 때까지 정한 크기(ORDER_BUFFER_MIB)의 메모리를 잡았다가 놓는다. 처리 중인 주문이 늘면
그만큼 메모리가 오르고, 줄면 바로 내려간다(A-4: 처리 중 주문 수에 비례하는 메모리).

* mmap 익명 메모리를 잡고 페이지를 미리 채운다. 잡자마자 컨테이너 메모리(working set)에 잡히고, close(munmap)하면
  바로 운영체제에 돌아간다
* 채우기: 리눅스는 큰 페이지(THP, MADV_HUGEPAGE)를 청한 뒤 MADV_POPULATE_WRITE로 한 번에 채운다. 4KiB 페이지로
  채울 때보다 CPU가 1/3쯤 든다(샌드박스에서 25MiB에 2ms와 6ms). 둘 다 안 되는 커널이나 운영체제(맥)는 페이지마다
  한 바이트씩 써서 채운다
* bytearray(n)이나 bytes(n)은 쓰지 않는다. 0으로 된 페이지는 쓰기 전까지 실제로 잡히지 않고, 파이썬과 malloc은
  놓은 메모리를 바로 돌려주지 않아서 메모리가 처리 중 주문 수를 따라가지 않는다
"""
import mmap
import sys
from collections.abc import Iterator
from contextlib import contextmanager

PAGE = mmap.PAGESIZE
MADV_HUGEPAGE = getattr(mmap, "MADV_HUGEPAGE", None)
# 리눅스 5.14부터. 파이썬 mmap 모듈에 이름이 없으면 리눅스 값(23)을 쓴다
MADV_POPULATE_WRITE = getattr(mmap, "MADV_POPULATE_WRITE", 23 if sys.platform.startswith("linux") else None)


def _fill(buf: mmap.mmap, size: int) -> None:
    if MADV_HUGEPAGE is not None:
        try:
            buf.madvise(MADV_HUGEPAGE)
        except OSError:
            pass
    if MADV_POPULATE_WRITE is not None:
        try:
            buf.madvise(MADV_POPULATE_WRITE)
            return
        except OSError:
            pass
    for i in range(0, size, PAGE):
        buf[i] = 1


@contextmanager
def work_buffer(size: int) -> Iterator[mmap.mmap | None]:
    """size 바이트를 잡고, with 블록이 끝나면(예외로 끝나도) 놓는다. size가 0 이하면 잡지 않는다"""
    if size <= 0:
        yield None
        return
    buf = mmap.mmap(-1, size, flags=mmap.MAP_PRIVATE)
    try:
        _fill(buf, size)
        yield buf
    finally:
        buf.close()
