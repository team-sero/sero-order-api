# order-api

배달 서비스 주문 API. S.E.R.O 테스트 환경에서 장애를 재현하는 대상 서비스 (카드 A-1).

## 준비물

* Python 3.11 이상 (팀 기준 3.13)
* Docker Desktop (로컬 Postgres와 결제사 payment-mock용)
* 결제사 payment-mock: sero-payment-mock 저장소를 order-api 옆 폴더에 받아 두고, 그 폴더에서 `docker compose up -d --build`

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
* 결제사 payment-mock이 안 떠 있으면 주문 생성은 502(결제사 연결 불가)가 난다

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

* `POST /orders`: 주문 생성. 저장 전에 결제사를 부르고, 승인된 주문만 상태 `PAID`로 저장한다
  * 201 결제 승인, 402 결제 거절, 422 입력 오류, 502 결제사 오류나 연결 불가, 503 DB 문제, 504 결제 시간 초과
  * 402, 502, 504에는 주문을 저장하지 않는다
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
* `PAYMENT_URL`: 기본 `http://127.0.0.1:8090` (payment-mock의 compose.yaml과 같음)
* `PAYMENT_TIMEOUT_SECONDS`: 기본 `5`. 결제사 연결, 응답 대기 각각의 제한 시간

## 로그 형식

한 줄에 JSON 하나, 표준 출력으로 나간다.

* 공통 필드: `ts`, `level`, `service`, `version`, `pod`, `logger`, `message`
* 추가 필드: `event`, `order_id`, `user_id`, `error_type` (4단계부터 `method`, `path`, `status`, `duration_ms`, 5단계부터 `trace_id`, `span_id`)
* 주요 `event`: `startup`, `shutdown`, `db_connect_retry`, `db_connected`, `db_unavailable`, `order_created`, `payment_declined`, `payment_failed`, `payment_timeout`, `order_save_failed`
* 결제 오류 줄의 `error_type`: 결제사가 오류로 답하면 `PaymentProviderError`(메시지에 결제사 상태 코드), 닿지 않으면 원래 오류 이름(예: `ConnectionRefusedError`), 시간 초과면 `ReadTimeout` 같은 이름
* `order_save_failed`: 결제는 승인됐는데 주문을 저장하지 못했을 때. 메시지에 `payment_id`가 있다
* 정상 종료(SIGTERM)면 `event: shutdown` 줄이 남고, OOMKilled(SIGKILL)면 안 남는다

## 진행 단계

1. 뼈대: 설정, JSON 로그, 헬스체크 (완료)
2. 주문 API와 Postgres (완료)
3. 결제 호출 (완료, 결제사는 sero-payment-mock 저장소)
4. 요청 로그
5. OTel
6. 메모리 구조 (처리 중 주문 버퍼, 주문 캐시)
7. Dockerfile과 v1 이미지