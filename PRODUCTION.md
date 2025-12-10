# jobu Production Guide

jobu 프로덕션 환경 배포 및 운영 가이드입니다.

프로젝트 개요 및 설치는 [README.md](README.md), 개발 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참조하세요.

## Production Checklist

| 항목 | 상태 | 설명 |
|------|------|------|
| Graceful Shutdown | O | SIGTERM/SIGINT 시그널 핸들링 |
| HA 중복 방지 | O | UNIQUE 제약 + ON CONFLICT DO NOTHING |
| 재시도 메커니즘 | O | max_retry 설정, 실패/타임아웃 시 자동 재시도 |
| 타임아웃 처리 | O | 핸들러별 timeout_seconds 설정 |
| 커넥션풀 | O | SQLite, PostgreSQL, MySQL 비동기 풀 |
| 다중 DB 트랜잭션 | O | 2개 이상 DB 동시 트랜잭션 (원자성 보장) |
| 테스트 | O | 87개 유닛 테스트 통과 |

## Graceful Shutdown

Dispatcher와 Worker 모두 SIGTERM/SIGINT 시그널을 처리합니다.

```bash
# 종료 시그널 전송
kill -SIGTERM <pid>
# 또는 Ctrl+C (SIGINT)
```

**동작 방식:**
- Dispatcher: 폴링 루프 즉시 종료
- Worker: 실행 중인 태스크 완료 대기 (shutdown_timeout_seconds까지)
- 타임아웃 시 실행 중인 태스크 강제 취소

## HA (High Availability)

Dispatcher를 여러 인스턴스로 실행해도 Job이 중복 생성되지 않습니다.

```sql
-- job_executions 테이블
UNIQUE(job_id, scheduled_time)

-- Job 생성 쿼리
INSERT INTO job_executions ... ON CONFLICT DO NOTHING
```

동일한 (job_id, scheduled_time) 조합은 한 번만 생성됩니다.

## Retry/Timeout

`cron_jobs` 테이블에서 Job별로 설정:

| 컬럼 | 기본값 | 설명 |
|------|--------|------|
| max_retry | 3 | 최대 재시도 횟수 |
| timeout_seconds | 300 | 핸들러 실행 타임아웃 (초) |

실패/타임아웃 시 retry_count를 증가시키고 PENDING으로 재설정하여 재시도합니다.

## Connection Pool

커넥션풀 설정은 [database/README.md](database/README.md)를 참조하세요.

### 권장 설정

| 환경 | pool_size | 설명 |
|------|-----------|------|
| 개발 | 5 | 기본값 |
| 운영 (소규모) | 10 | Worker 2-3대 |
| 운영 (대규모) | 20+ | Worker 5대 이상 |

## Deployment

### 권장 구성

```
VM 1: Dispatcher + Worker (또는 분리)
VM 2: Worker (스케일 아웃 시)
DB: Azure Database for PostgreSQL/MySQL 또는 VM 내 SQLite
```

### 실행 명령

```bash
# 의존성 설치
pip install -r requirements.txt

# Dispatcher 실행 (백그라운드)
nohup python -m dispatcher.main > dispatcher.log 2>&1 &

# Worker 실행 (백그라운드)
nohup python -m worker.main > worker.log 2>&1 &

# Admin API 실행 (백그라운드)
nohup python -m uvicorn admin.main:app --host 0.0.0.0 --port 8080 > admin.log 2>&1 &
```

### systemd 서비스 (권장)

```ini
# /etc/systemd/system/jobu-dispatcher.service
[Unit]
Description=jobu Dispatcher
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/jobu
ExecStart=/home/ubuntu/jobu/venv/bin/python -m dispatcher.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/jobu-worker.service
[Unit]
Description=jobu Worker
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/jobu
ExecStart=/home/ubuntu/jobu/venv/bin/python -m worker.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 등록 및 시작
sudo systemctl daemon-reload
sudo systemctl enable jobu-dispatcher jobu-worker
sudo systemctl start jobu-dispatcher jobu-worker
```

## Configuration Files

| 파일 | 용도 |
|------|------|
| config/database.yaml | 다중 DB 커넥션풀 설정 |
| config/dispatcher.yaml | Dispatcher 폴링 주기, 크론 간격 제한 |
| config/worker.yaml | WorkerPool 크기, 셧다운 타임아웃 |
| config/admin.yaml | Admin API 서버 설정 |

## Job States

| 상태 | 설명 |
|------|------|
| PENDING | 생성됨, 실행 대기 |
| RUNNING | Worker가 실행 중 |
| SUCCESS | 성공 완료 |
| FAILED | 실패 (재시도 소진 시 최종) |
| TIMEOUT | 타임아웃 (재시도 소진 시 최종) |

## Logging

프로덕션에서는 JSON 로깅 권장:

```python
# common/logging.py 사용
from common.logging import setup_json_logging
setup_json_logging(level=logging.INFO)
```

## Security Notes

- database.yaml에 민감 정보(비밀번호) 포함 - 환경변수 또는 비밀 관리 서비스 사용 권장
- Admin API는 내부 네트워크에서만 접근 허용 권장
- 프로덕션에서 debug=False 설정

## Health Check

Admin API의 헬스체크 엔드포인트:
- `/health`: 기본 상태 확인 (liveness)
- `/docs`: Swagger UI (개발용)

## Notes

- **MySQL + aiosql**: asyncmy 드라이버 사용. aiosql에서 `"asyncmy"` 어댑터로 SQL 파일 로드 가능

- **분산락 불필요**: Redis 같은 별도 분산락이 필요 없음. DB 레벨에서 동시성 제어:
  - Dispatcher: `UNIQUE(job_id, scheduled_time)` + `ON CONFLICT DO NOTHING`으로 중복 Job 생성 방지
  - Worker: `UPDATE ... WHERE status = 'PENDING'` 경쟁 방식으로 한 Worker만 Job 획득 (affected_rows > 0인 쪽만 실행)
