# 크론, 잡 관리, 로그 조회 화면/API 개발 및 테스트

## 개요
크론 잡 관리를 위한 Admin API 서버 개발. FastAPI 기반으로 RESTful API를 제공하며, 크론 등록/수정/삭제, 잡 실행 이력 조회, 로그 조회 기능을 구현한다.

## 구조
```
admin/
├── __init__.py
├── main.py                    # FastAPI 앱 진입점
├── api/
│   ├── __init__.py
│   ├── router/
│   │   ├── __init__.py
│   │   └── api.py             # 모든 API 라우터 통합
│   ├── handler/
│   │   ├── __init__.py
│   │   ├── cron.py            # 크론 비즈니스 로직
│   │   └── job.py             # 잡 비즈니스 로직
│   ├── model/
│   │   ├── __init__.py
│   │   ├── cron.py            # 크론 요청/응답 모델
│   │   ├── job.py             # 잡 요청/응답 모델
│   │   └── common.py          # 공통 모델 (페이징, 에러 등)
│   └── sql/
│       └── admin.sql          # Admin 전용 쿼리 (aiosql)
└── front/
    ├── cron.html              # 크론 관리 화면 (CSS 없음, 기본 HTML)
    └── job.html               # 잡 이력 조회 화면 (CSS 없음, 기본 HTML)

config/
└── admin.yaml                 # Admin 서버 설정 (기존 config 폴더 사용)
```

## 라이브러리
- FastAPI: 웹 프레임워크
- uvicorn: ASGI 서버
- pydantic: 데이터 검증 및 직렬화
- jinja2: HTML 템플릿 렌더링

## 설정 파일
```yaml
# config/admin.yaml
admin:
  host: "0.0.0.0"
  port: 8080
  debug: true
  cors:
    origins: ["*"]
    allow_credentials: true
    allow_methods: ["*"]
    allow_headers: ["*"]
```

## API 명세

### 1. 크론 관리 API

#### GET /api/crons
크론 목록 조회 (페이징)
- Query Parameters:
  - `page`: 페이지 번호 (default: 1)
  - `size`: 페이지 크기 (default: 20)
  - `is_enabled`: 활성화 필터 (optional)
- Response:
  ```json
  {
    "items": [
      {
        "id": 1,
        "name": "daily_backup",
        "description": "매일 백업",
        "cron_expression": "0 0 * * *",
        "handler_name": "backup_handler",
        "handler_params": {"target": "db"},
        "is_enabled": true,
        "allow_overlap": false,
        "max_retry": 3,
        "timeout_seconds": 3600,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 100,
    "page": 1,
    "size": 20,
    "pages": 5
  }
  ```

#### GET /api/crons/{id}
크론 상세 조회
- Response: 크론 단일 객체

#### POST /api/crons
크론 등록
- Request Body:
  ```json
  {
    "name": "daily_backup",
    "description": "매일 백업",
    "cron_expression": "0 0 * * *",
    "handler_name": "backup_handler",
    "handler_params": {"target": "db"},
    "is_enabled": true,
    "allow_overlap": false,
    "max_retry": 3,
    "timeout_seconds": 3600
  }
  ```
- Validation:
  - `name`: 필수, 유니크
  - `cron_expression`: 필수, 유효한 크론 표현식, 1분 미만 간격 차단
  - `handler_name`: 필수, 등록된 핸들러 존재 여부 확인

#### PUT /api/crons/{id}
크론 수정
- Request Body: POST와 동일 (부분 수정 지원)

#### DELETE /api/crons/{id}
크론 삭제
- Response: 204 No Content

#### POST /api/crons/{id}/toggle
크론 활성화/비활성화 토글
- Response: 수정된 크론 객체

### 2. 잡 실행 이력 API

#### GET /api/jobs
잡 실행 이력 목록 (페이징)
- Query Parameters:
  - `page`: 페이지 번호 (default: 1)
  - `size`: 페이지 크기 (default: 20)
  - `cron_id`: 크론 ID 필터 (optional)
  - `status`: 상태 필터 (PENDING/RUNNING/SUCCESS/FAILED/TIMEOUT)
  - `from_date`: 시작일 (optional)
  - `to_date`: 종료일 (optional)
- Response:
  ```json
  {
    "items": [
      {
        "id": 1,
        "job_id": 1,
        "cron_name": "daily_backup",
        "scheduled_time": "2024-01-01T00:00:00Z",
        "status": "SUCCESS",
        "started_at": "2024-01-01T00:00:01Z",
        "finished_at": "2024-01-01T00:01:00Z",
        "retry_count": 0,
        "error_message": null,
        "result": "OK",
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 1000,
    "page": 1,
    "size": 20,
    "pages": 50
  }
  ```

#### GET /api/jobs/{id}
잡 실행 상세 조회
- Response: 잡 단일 객체 (상세 로그 포함)

#### POST /api/jobs/{id}/retry
실패한 잡 재시도 (FAILED/TIMEOUT 상태만 가능)
- status를 PENDING으로 변경하여 Worker가 다시 실행하도록 함
- Response: 수정된 잡 객체

#### DELETE /api/jobs/{id}
잡 실행 이력 삭제
- Response: 204 No Content

### 3. 헬스체크 API

#### GET /health
서버 상태 확인
- Response:
  ```json
  {
    "status": "healthy",
    "database": "connected",
    "version": "1.0.0"
  }
  ```

### 4. HTML 화면

#### GET /crons
크론 관리 화면 (단일 페이지에서 등록/수정/목록 처리)
- 상단: 등록/수정 폼
- 하단: 크론 목록 테이블 (수정/삭제/토글 버튼 포함)

#### GET /jobs
잡 이력 조회 화면
- 상단: 필터 (크론 선택, 상태, 날짜)
- 하단: 잡 목록 테이블 + 페이징 + 재시도 버튼

## 구현 순서
1. FastAPI 앱 기본 구조 설정
   - main.py, 라우터 연결, CORS 설정
   - 에러 핸들러 등록
   - Jinja2 템플릿 설정
   - Swagger UI 자동 제공 (`/docs`, `/redoc`)
2. 공통 모델 구현
   - 페이징 모델, 에러 응답 모델
3. 크론 관리 API 구현
   - CRUD 및 토글 기능
   - 크론 표현식 validation (croniter 사용)
4. 잡 실행 이력 API 구현
   - 목록 조회 (필터링, 페이징)
   - 재시도 기능
5. HTML 화면 구현
   - 크론 관리 화면 (front/cron.html)
   - 잡 이력 조회 화면 (front/job.html)
6. 테스트 작성

## 테스트
- 테스트 파일: test/admin_test.py
- 테스트 케이스:
  1. 크론 CRUD
     - 크론 생성, 조회, 수정, 삭제
     - 중복 이름 생성 시 409 에러
     - 잘못된 크론 표현식 시 400 에러
     - 1분 미만 간격 크론 차단
  2. 잡 실행 이력
     - 목록 조회 (페이징 확인)
     - 필터링 동작 확인
     - 재시도 기능 (FAILED → PENDING)
  3. 에러 처리
     - 존재하지 않는 리소스 404
     - 잘못된 요청 400

## 고려사항
- 트랜잭션은 handler 레벨에서 `@transactional` 데코레이터 사용
- 모든 API 응답은 일관된 JSON 포맷 유지
- 에러 응답도 표준화된 포맷 사용
  ```json
  {
    "error": {
      "code": "CRON_NOT_FOUND",
      "message": "Cron job with id 123 not found"
    }
  }
  ```
- API 버전 관리는 URL prefix로 처리 (`/api/v1/...`)
- 로그는 요청/응답 전체를 미들웨어에서 기록
- handler_params는 JSON 문자열로 저장, API에서는 객체로 변환하여 반환

## 에러 처리
- FastAPI의 HTTPException 활용
- 주요 에러 코드:
  - 400 Bad Request: 잘못된 요청 (validation 실패)
  - 404 Not Found: 리소스 없음
  - 409 Conflict: 중복 리소스 (이름 중복 등)
  - 500 Internal Server Error: 서버 내부 에러

## 향후 확장
- Phase4에서 Worker Pool 구현 후 실시간 잡 상태 조회 WebSocket 추가 검토
- Phase5에서 통합 후 실제 잡 실행 트리거 API 추가 검토