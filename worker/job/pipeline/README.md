# Pipeline Handlers

데이터 전처리 파이프라인 핸들러 템플릿입니다.

## 핸들러 목록

### pandas_preprocess

CSV 파일을 읽어 전처리 후 Parquet으로 저장합니다.

```python
params = {
    "input_path": "/data/raw/sample.csv",
    "output_path": "/data/processed/sample.parquet",
    "columns": ["id", "name", "value"],  # 선택할 컬럼
    "filters": {
        "value": {"gt": 0, "lt": 1000},  # 필터 조건
    }
}
```

### pydantic_validator

입력 데이터를 Pydantic 모델로 검증합니다.

```python
params = {
    "data": [
        {"id": 1, "name": "test", "value": 100},
    ],
    "strict": False  # True면 무효 데이터가 있으면 실패
}
```

### db_loader

Parquet 파일을 읽어 PostgreSQL로 적재합니다.

```python
params = {
    "input_path": "/data/processed/sample.parquet",
    "target_table": "sample_data",
    "target_db": "data",
    "truncate_before": False
}
```

## 파이프라인 구성 예시

Kafka 메시지로 전처리 -> 검증 -> 적재 파이프라인을 구성할 수 있습니다.

```json
// Kafka 메시지 1: 전처리
{
    "handler_name": "pandas_preprocess",
    "params": {
        "input_path": "/data/raw/sample.csv",
        "output_path": "/data/processed/sample.parquet"
    }
}

// Kafka 메시지 2: 적재
{
    "handler_name": "db_loader",
    "params": {
        "input_path": "/data/processed/sample.parquet",
        "target_table": "sample_data"
    }
}
```

## 의존성

```bash
pip install pandas pyarrow pydantic
```
