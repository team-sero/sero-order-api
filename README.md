# order-api

배달 서비스 주문 API. S.E.R.O 테스트 환경에서 장애를 재현하는 대상 서비스 (카드 A-1).

## 준비물

* Python 3.11 이상 (팀 기준 3.13)
* Docker Desktop (로컬 Postgres용)

## 로컬 실행

윈도우 PowerShell

```powershell
docker compose up -d
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:APP_VERSION="1.4.2"; python -m app
```

* `Activate.ps1`이 막히면 한 번만 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

맥, 리눅스

```bash
docker compose up -d
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
APP_VERSION=1.4.2 python -m app
```

확인

* API 문서와 테스트 화면: http://127.0.0.1:8080/docs
* 준비 상태: `curl.exe -i http://127.0.0.1:8080/readyz` (맥, 리눅스는 `curl -i`). DB가 붙으면 200

정리

* `docker compose down`: DB 끄기 (데이터는 남음)
* `docker compose down -v`: 데이터까지 삭제

## API

* `POST /orders`: 주문 생성. 201, 입력 오류 422, DB 문제 503
* `GET /orders/{order_id}`: 주문 조회. 200, 없으면 404, DB 문제 503
* `GET /healthz`: liveness. 프로세스가 응답하는지만 본다
* `GET /readyz`: readiness. DB에 쿼리가 되면 200, 아니면 503

## 환경변수

* `APP_VERSION`: 기본 `dev`. 이미지 빌드할 때 넣는다
* `SERVICE_NAME`: 기본 `order-api`
* `DATABASE_URL`: 기본 `postgresql://order:order@127.0.0.1:5432/orders` (compose.yaml과 같음)
* `DB_POOL_MIN`, `DB_POOL_MAX`: 기본 `1`, `10`
* `DB_TIMEOUT_SECONDS`: 기본 `3`
* `LOG_LEVEL`, `HOST`, `PORT`: 기본 `INFO`, `0.0.0.0`, `8080`
* `POD_NAME`: 로그의 `pod` 값. 없으면 `HOSTNAME`(쿠버네티스에서는 파드 이름), 둘 다 없으면 `local`

## 로그 형식

한 줄에 JSON 하나, 표준 출력으로 나간다.

* 공통 필드: `ts`, `level`, `service`, `version`, `pod`, `logger`, `message`
* 추가 필드: `event`, `order_id`, `user_id`, `error_type` (4단계부터 `method`, `path`, `status`, `duration_ms`, 5단계부터 `trace_id`, `span_id`)
* 주요 `event`: `startup`, `shutdown`, `db_connect_retry`, `db_connected`, `db_unavailable`, `order_created`
* 정상 종료(SIGTERM)면 `event: shutdown` 줄이 남고, OOMKilled(SIGKILL)면 안 남는다

## 진행 단계

1. 뼈대: 설정, JSON 로그, 헬스체크 (완료)
2. 주문 API와 Postgres (완료)
3. 결제 호출 (결제사는 sero-payment-mock 저장소)
4. 요청 로그
5. OTel
6. 메모리 구조 (처리 중 주문 버퍼, 주문 캐시)
7. Dockerfile과 v1 이미지