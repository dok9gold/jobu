# Python 3.12 Migration

Python 3.9 -> 3.12 업그레이드 및 라이브러리 버전 조정

## 변경 사항 요약

| 항목 | 이전 | 이후 | 비고 |
|------|------|------|------|
| Python | 3.9 | 3.12 | EOL 대응 (3.9는 2025-10 종료) |
| aiosql | >=9.0 (14.1 설치됨) | >=13.0,<14.0 | 14.x async generator breaking change 회피 |

## 1. 라이브러리 버전 조사

### 현재 설치된 버전 vs 권장 버전

| 패키지 | 현재 설치 | 권장 버전 | 비고 |
|--------|----------|----------|------|
| aiosql | 14.1 | **>=13.0,<14.0** | 14.x breaking change |
| aiosqlite | 0.21.0 | >=0.20.0,<0.22.0 | 0.2x 범위 |
| asyncmy | 0.2.10 | >=0.2.9,<0.3.0 | 0.2.x 범위 |
| asyncpg | 0.31.0 | >=0.30.0,<0.32.0 | 0.3x 범위 |
| pydantic | 2.12.5 | >=2.10.0,<3.0 | 2.x 메이저 |
| fastapi | 0.124.0 | >=0.115.0,<0.130.0 | 0.11x~0.12x 범위 |
| uvicorn | 0.38.0 | >=0.34.0,<0.40.0 | 0.3x 범위 |
| pytest | 9.0.2 | >=8.0.0,<10.0 | 메이저 |
| pytest-asyncio | 1.3.0 | >=1.0.0,<2.0 | 1.x 메이저 |
| pyyaml | 6.0.3 | >=6.0.0,<7.0 | 메이저 |
| croniter | 6.0.0 | >=5.0.0,<7.0 | 메이저 |
| jinja2 | 3.1.6 | >=3.1.0,<4.0 | 메이저 |
| httpx | 0.28.1 | >=0.27.0,<0.30.0 | 0.2x 범위 |
| python-json-logger | 4.0.0 | >=3.0.0,<5.0 | 메이저 |

### 버전 범위 전략

```
1.x 이상 버전: 메이저 버전 기준 (<3.0, <10.0 등)
0.x 버전: 마이너 버전 범위로 제한 (0.3x, 0.2x 등)
  - 0.x에서는 마이너 버전 변경도 breaking change 가능
  - 예: >=0.34.0,<0.40.0 (0.3x대만 허용)
```

## 2. requirements.txt 버전 고정

```txt
# Core
aiosqlite>=0.20.0,<0.22.0
aiosql>=13.0,<14.0              # 14.x는 async generator breaking change
pyyaml>=6.0.0,<7.0
pydantic>=2.10.0,<3.0
croniter>=5.0.0,<7.0

# Test
pytest>=8.0.0,<10.0
pytest-asyncio>=1.0.0,<2.0

# Admin API
fastapi>=0.115.0,<0.130.0       # 0.x이므로 마이너 범위 제한
uvicorn>=0.34.0,<0.40.0         # 0.x이므로 마이너 범위 제한
jinja2>=3.1.0,<4.0
httpx>=0.27.0,<0.30.0           # 0.x이므로 마이너 범위 제한

# Multi-DB Support
asyncpg>=0.30.0,<0.32.0         # 0.x이므로 마이너 범위 제한
asyncmy>=0.2.9,<0.3.0

# Logging
python-json-logger>=3.0.0,<5.0
```

## 3. 타입 힌트 현대화 (선택)

Python 3.10+에서는 `typing` 모듈 없이 직접 사용 가능:

```python
# Before (Python 3.9)
from typing import Optional, List, Dict
def foo(x: Optional[str]) -> List[dict]:
    ...

# After (Python 3.10+)
def foo(x: str | None) -> list[dict]:
    ...
```

### 대상 파일
- worker/executor.py
- worker/main.py
- worker/model/executor.py
- database/mysql/aiosql_adapter.py
- database/mysql/connection.py
- database/postgres/connection.py
- database/sqlite3/connection.py
- database/registry.py
- dispatcher/main.py
- dispatcher/model/dispatcher.py
- admin/api/model/*.py
- admin/api/handler/*.py
- admin/api/router/api.py
- common/logging.py

**참고**: 타입 힌트 변경은 기능에 영향 없음. 코드 가독성/현대화 목적.

## 4. Pydantic Config 경고 수정

Pydantic v2에서 `class Config` deprecated, `model_config` 사용 권장:

```python
# Before
class CronResponse(BaseModel):
    class Config:
        from_attributes = True

# After
from pydantic import ConfigDict

class CronResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

### 대상 파일
- admin/api/model/cron.py
- admin/api/model/job.py

## 5. 실행 순서

```bash
# 1. requirements.txt 수정 후 재설치
pip install -r requirements.txt

# 2. aiosql 버전 확인 (13.x인지)
pip show aiosql | grep Version

# 3. 테스트 실행
python -m pytest test/ -v

# 4. main.py 실행 테스트
python main.py

# 5. (선택) Pydantic config 수정
# 6. (선택) 타입 힌트 현대화

# 7. 커밋
git add -A && git commit -m "chore: Python 3.12 migration, 라이브러리 버전 고정"
```

## 6. 검증

- [ ] 전체 테스트 통과 (87개)
- [ ] main.py 정상 실행
- [ ] Dispatcher 정상 동작
- [ ] Worker 정상 동작
- [ ] Admin API 정상 동작

## 참고 링크

- aiosql 14.0 changelog: https://nackjicholson.github.io/aiosql/versions.html
- Python 3.12 release: https://www.python.org/downloads/release/python-3120/
- Pydantic v2 migration: https://docs.pydantic.dev/latest/migration/
- FastAPI releases: https://github.com/fastapi/fastapi/releases
- asyncpg PyPI: https://pypi.org/project/asyncpg/
- asyncmy PyPI: https://pypi.org/project/asyncmy/
