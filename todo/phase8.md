# Phase 8: 코드 정리 및 구조 개선

## 개요
- Python 3.12 마이그레이션 완료 후 남은 정리 작업
- 실행 환경 일원화 및 코드 품질 개선

---

## 1. aiomysql 어댑터 검토 (완료)

### 현재 상태
- `database/mysql/aiosql_adapter.py`: asyncmy용 커스텀 aiosql 어댑터 구현
- aiomysql에서 asyncmy로 전환 완료

### 검토 결과
- aiosql 14.1 기준 asyncmy **내장 지원 없음**
- aiosql이 내장 지원하는 MySQL 드라이버(PyMySQL, mysqlclient, mysql-connector)는 모두 **동기 드라이버**
- 비동기 MySQL 드라이버 사용 시 커스텀 어댑터 필수

### 결론: 현재 상태 유지
- 커스텀 어댑터 제거 불가 (aiosql이 asyncmy 내장 지원 안 함)
- asyncmy + 커스텀 어댑터 조합이 최선의 선택
- 추가 작업 없음

---

## 2. 모듈 실행 위치 정리 (완료)

### 이전 상태
각 모듈의 main.py에 sys.path 조작 코드 존재:

```python
# dispatcher/main.py, worker/main.py 등
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### 결정: 옵션 C - `-m` 방식 사용
- sys.path 조작 코드 제거
- `python -m` 방식으로 실행 (파이썬 표준)
- 루트 main.py 통합 실행도 유지

### 실행 방법
```bash
# 개별 모듈 실행
python -m dispatcher.main
python -m worker.main

# 통합 실행
python main.py                    # 전체
python main.py dispatcher worker  # 선택
```

### 완료 작업
1. `dispatcher/main.py` - sys.path 코드 제거
2. `worker/main.py` - sys.path 코드 제거
3. CLAUDE.md 실행 방법 업데이트

---

## 3. Worker 모델 활용 방안 (완료)

### 이전 상태
- `worker/model/executor.py`: JobInfo 등 존재
- 핸들러에서 dict 기반으로 params 받고 dict 반환
- Pydantic 모델 활용 미흡

### 개선 내용
공통 Pydantic 모델로 타입 안전성 확보:

```python
# worker/model/handler.py (신규)
from pydantic import BaseModel, ConfigDict
from typing import Any

class HandlerParams(BaseModel):
    """핸들러 입력 파라미터 (공통)"""
    model_config = ConfigDict(extra='allow')  # 정의 안 된 필드도 허용

    action: str = 'read'
    id: int | None = None
    name: str | None = None
    value: str | None = None

class HandlerResult(BaseModel):
    """핸들러 실행 결과 (공통)"""
    model_config = ConfigDict(extra='allow')

    action: str
    success: bool = True
    id: int | None = None
    count: int | None = None
    data: Any = None
    error: str | None = None
```

### BaseHandler 변경

```python
# worker/base.py
from worker.model.handler import HandlerParams, HandlerResult

class BaseHandler(ABC):
    @abstractmethod
    async def execute(self, params: HandlerParams) -> HandlerResult:
        pass
```

### Executor 변경

```python
# worker/executor.py
from worker.model.handler import HandlerParams

# dict -> HandlerParams 변환
params = HandlerParams(**json.loads(job_info.handler_params or '{}'))
result = await handler.execute(params)

# HandlerResult -> JSON 저장
result_str = result.model_dump_json()
```

### 핸들러 사용 예시

```python
@handler("sample1")
class Sample1Handler(BaseHandler):
    async def execute(self, params: HandlerParams) -> HandlerResult:
        if params.action == 'write':
            # IDE 자동완성, 타입 체크 가능
            data_id = await self.write_data(params.name, params.value)
            return HandlerResult(action='write', id=data_id)
        else:
            rows = await self.read_data()
            return HandlerResult(action='read', count=len(rows), data=rows)
```

### 완료 작업
1. `worker/model/handler.py` 생성 (HandlerParams, HandlerResult)
2. `worker/base.py` BaseHandler 시그니처 변경
3. `worker/executor.py` dict -> HandlerParams 변환 로직 추가
4. 샘플 핸들러 전체 수정 (sample, sample1-8)
5. 테스트 수정 및 전체 통과 (87개)

---

## 4. 비동기 DB 동시 쿼리 샘플 핸들러 (완료)

### 목적
- 비동기 DB 연결의 실질적 활용 예제
- `asyncio.gather`를 사용한 동시 쿼리 실행 패턴 학습

### 구현 위치
- `worker/job/group3/sample9.py`

### 구현 내용
3개 DB(SQLite, PostgreSQL, MySQL)에서 동시에 통계를 조회하는 핸들러:

```python
@handler("sample9")
class Sample9Handler(BaseHandler):
    async def execute(self, params: HandlerParams) -> HandlerResult:
        if params.action == 'sequential':
            # 순차 실행 (비교용)
            sqlite_stats = await fetch_sqlite_stats()
            pg_stats = await fetch_postgres_stats()
            mysql_stats = await fetch_mysql_stats()
        else:
            # 동시 실행 (기본)
            sqlite_stats, pg_stats, mysql_stats = await asyncio.gather(
                fetch_sqlite_stats(),
                fetch_postgres_stats(),
                fetch_mysql_stats(),
            )

        return HandlerResult(
            action=params.action,
            data={
                "sqlite": sqlite_stats,
                "postgres": pg_stats,
                "mysql": mysql_stats,
                "elapsed_ms": round(elapsed_ms, 2),
                "mode": "sequential" if params.action == 'sequential' else "concurrent",
            }
        )
```

### 포인트
- 커넥션 풀에서 여러 커넥션을 사용해 동시 쿼리
- 멀티스레드 대비 코드 간결성 (한 메서드에서 처리)
- 순차 실행 대비 성능 향상 (독립적인 쿼리일 경우)
- `action='sequential'` 파라미터로 순차/동시 실행 비교 가능

---

## 5. 구현 순서 (권장)

1. **모듈 실행 위치 정리** - 구조적 결정 먼저
2. **aiomysql 어댑터 검토** - 의존성 정리 (검토 완료: 현재 상태 유지)
3. **Worker 모델 활용** - 코드 품질 개선
4. **비동기 DB 동시 쿼리 샘플** - 비동기 활용 예제

---

## 6. 참고

### 관련 파일
- `database/mysql/aiosql_adapter.py` - 커스텀 asyncmy 어댑터
- `dispatcher/main.py` - sys.path 조작 코드
- `worker/main.py` - sys.path 조작 코드
- `worker/model/executor.py` - 기존 Worker 모델
- `worker/job/group3/service/sample7_service.py` - 서비스 레이어 패턴 예제
