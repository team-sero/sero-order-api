"""실행: python -m app"""
import uvicorn

from .config import get_settings
from .logging_setup import setup_logging


def main() -> None:
    settings = get_settings()
    setup_logging(settings.service_name, settings.app_version, settings.log_level)
    # log_config=None: uvicorn 자체 로그도 위 JSON 형식으로 나간다
    # access_log=False: 요청 로그는 4단계에서 직접 남긴다
    # workers=1: 파드 하나 = 프로세스 하나라야 메모리 계산이 맞는다
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
