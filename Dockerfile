# order-api 이미지. 로컬에서는 k3d 클러스터에 넣어 쓰고, 서버에서는 k3s의 baemin 네임스페이스에 올린다
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# tini를 컨테이너의 첫 프로세스(PID 1)로 두고 파이썬은 그 아래에서 돌린다.
# 파이썬이 PID 1이면 SIGTERM으로 끝나도 종료 코드가 0이 돼서, 정상 종료(143)와 OOMKilled(137)를 가르는 근거가 흐려진다
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*

# root로 돌리지 않는다
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /srv

# 의존성을 먼저 깐다. 코드만 바뀌었을 때는 이 층을 캐시에서 다시 쓴다
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# 버전은 빌드할 때 넣는다 (예: --build-arg APP_VERSION=1.4.2). 로그의 version 필드가 이 값이다.
# 맨 뒤에 둬야 버전만 바꿔 빌드할 때 위 층을 캐시에서 다시 쓴다
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

USER 10001
EXPOSE 8080
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "app"]