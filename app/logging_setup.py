"""한 줄에 JSON 하나씩 찍는 로그. 필드 목록은 B-1 로그 형식과 맞춘다."""
import json
import logging
import os
import sys
from datetime import datetime, timezone

# extra=로 넘길 수 있는 추가 필드. 여기 없는 키는 로그에 안 실린다.
EXTRA_FIELDS = (
    "event",        # startup, shutdown, request 등
    "order_id",
    "user_id",
    "method",
    "path",         # 원본 URL이 아니라 경로 템플릿 (/orders/{order_id})
    "status",
    "duration_ms",
    "trace_id",
    "span_id",
    "error_type",
)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, version: str) -> None:
        super().__init__()
        self.service = service
        self.version = version
        # 쿠버네티스에선 HOSTNAME이 파드 이름
        self.pod = os.environ.get("POD_NAME") or os.environ.get("HOSTNAME", "local")

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": self.service,
            "version": self.version,
            "pod": self.pod,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                line[key] = value
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False)


def setup_logging(service: str, version: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, version))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
