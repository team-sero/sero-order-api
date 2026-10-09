"""환경변수 설정. 쿠버네티스에서는 Deployment의 env로 넣는다."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "order-api"
    app_version: str = "dev"  # 이미지 빌드할 때 넣는다 (예: 1.4.2)
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8080

    # DB. 로컬 기본값은 compose.yaml과 맞춰 뒀다. 쿠버네티스에선 Secret으로 넣는다.
    database_url: str = "postgresql://order:order@127.0.0.1:5432/orders"
    db_pool_min: int = 1
    db_pool_max: int = 10
    db_timeout_seconds: float = 3.0  # 연결, 커넥션 대기, 쿼리 각각의 제한 시간

    # 결제사(payment-mock). 로컬 기본값은 payment-mock의 compose.yaml과 맞춰 뒀다.
    payment_url: str = "http://127.0.0.1:8090"
    # 연결, 응답 대기 각각의 제한 시간. 결제사 지연 3초(S12)가 504가 아니라 메모리 증가로 나타나게 3초보다 길게 둔다
    payment_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()