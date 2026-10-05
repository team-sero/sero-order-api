"""환경변수 설정. 쿠버네티스에서는 Deployment의 env로 넣는다."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "order-api"
    app_version: str = "dev"  # 이미지 빌드할 때 넣는다 (예: 1.4.2)
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8080


@lru_cache
def get_settings() -> Settings:
    return Settings()
