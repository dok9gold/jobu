# Admin 모듈

크론 관리 및 잡 실행 이력 조회를 위한 FastAPI 기반 Admin API 서버입니다.

## 동작 원리

```
[Client] --HTTP--> [FastAPI] --SQL--> [Database]
```

1. 클라이언트가 API 엔드포인트 호출
2. Router에서 요청 검증 후 Handler로 전달
3. Handler에서 비즈니스 로직 처리 및 DB 쿼리 실행
4. 결과 반환 (JSON 또는 HTML)

## 구조

```
admin/
  main.py          # FastAPI 앱, lifespan
  exception.py     # 예외 클래스
  api/
    router/        # API 라우터
      cron.py      # 크론 CRUD API
      job.py       # 잡 이력 API
    handler/       # 비즈니스 로직
    model/         # Pydantic 모델
    sql/           # SQL 쿼리
  front/           # HTML 화면
    cron.html      # 크론 관리 화면
    job.html       # 잡 이력 화면
```

## 설정

`config/admin.yaml`

```yaml
admin:
  database: default       # 사용할 DB (database.yaml에 정의된 이름)
  host: "0.0.0.0"
  port: 8080
  debug: true
  cors:
    origins: ["*"]
```

## 실행

```bash
python -m uvicorn admin.main:app --reload --port 8080
```

## 사용법

### 접속 URL

| URL | 설명 |
|-----|------|
| /docs | Swagger API 문서 |
| /crons | 크론 관리 화면 |
| /jobs | 잡 이력 화면 |

### API 엔드포인트

#### 크론 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /api/crons | 크론 목록 조회 |
| POST | /api/crons | 크론 등록 |
| GET | /api/crons/{id} | 크론 상세 조회 |
| PUT | /api/crons/{id} | 크론 수정 |
| DELETE | /api/crons/{id} | 크론 삭제 |
| POST | /api/crons/{id}/toggle | 활성화/비활성화 토글 |

#### 잡 이력

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /api/jobs | 잡 목록 조회 (페이징, 필터링) |
| GET | /api/jobs/{id} | 잡 상세 조회 |
| POST | /api/jobs/{id}/retry | 재시도 (FAILED/TIMEOUT만) |
| DELETE | /api/jobs/{id} | 잡 삭제 |

### 크론 등록 예시

```json
{
  "name": "daily-report",
  "description": "일일 리포트 생성",
  "cron_expression": "0 9 * * *",
  "handler_name": "report",
  "handler_params": {"type": "daily"},
  "max_retry": 3,
  "timeout_seconds": 300
}
```

## 예외

| 예외 | 설명 |
|------|------|
| AdminError | Admin 기본 예외 |
| CronNotFoundError | 크론을 찾을 수 없음 |
| CronValidationError | 크론 유효성 검사 실패 |
| CronDuplicateError | 크론 이름 중복 |
| JobNotFoundError | 잡 실행 이력을 찾을 수 없음 |
| JobStatusError | 잡 상태 에러 (재시도 불가 등) |

