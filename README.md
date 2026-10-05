# order-api

배달 서비스 주문 API. S.E.R.O 테스트 환경의 장애 재현 대상 (카드 A-1).
저장소에선 `app/order-api/` 아래에 둔다.

## 로컬 실행

파이썬 3.10 이상 (3.12 권장)

```bash
python -m venv .venv
source .venv/bin/activate          # 윈도우: .venv\Scripts\activate
pip install -r requirements.txt

APP_VERSION=1.4.2 python -m app    # 윈도우 PowerShell: $env:APP_VERSION="1.4.2"; python -m app
```

다른 터미널에서

```bash
curl localhost:8080/healthz   # {"status":"ok"}
curl localhost:8080/readyz    # {"status":"ready"}
```

## 환경변수

* `SERVICE_NAME`: 기본 `order-api`
* `APP_VERSION`: 기본 `dev`, 이미지 빌드할 때 넣는다
* `LOG_LEVEL`: 기본 `INFO`
* `HOST`, `PORT`: 기본 `0.0.0.0`, `8080`

## 헬스체크

* `/healthz` (liveness): 프로세스가 응답하는지만 본다. DB 같은 바깥 의존성은 안 본다
* `/readyz` (readiness): 요청 받을 준비가 됐는지. DB 확인은 2단계에서 들어간다

## 로그 형식

한 줄에 JSON 하나, 표준 출력으로 나간다.

* 공통 필드: `ts`, `level`, `service`, `version`, `pod`, `logger`, `message`
* 추가 필드: `event`, `order_id`, `user_id`, `method`, `path`, `status`, `duration_ms`, `trace_id`, `span_id`, `error_type`
* 정상 종료(SIGTERM)면 `event: shutdown` 줄이 남고, OOMKilled(SIGKILL)면 안 남는다

## 진행 단계

1. 뼈대: 설정, JSON 로그, 헬스체크, 시작/종료 로그 ← 지금
2. 주문 API와 DB
3. payment-mock과 결제 호출
4. 요청 로그
5. OTel
6. 메모리 구조 (처리 중 주문 버퍼, 주문 캐시)
7. Dockerfile과 v1 이미지
