"""
Pandas 전처리 핸들러 템플릿

CSV 파일을 읽어 전처리 후 Parquet으로 저장하는 예시입니다.

params 예시:
{
    "input_path": "/data/raw/sample.csv",
    "output_path": "/data/processed/sample.parquet",
    "columns": ["id", "name", "value"],
    "filters": {"value": {"gt": 0}}
}
"""

import logging
from pathlib import Path
from typing import Any

from worker.base import BaseHandler, handler, HandlerParams, HandlerResult

logger = logging.getLogger(__name__)


@handler("pandas_preprocess")
class PandasPreprocessHandler(BaseHandler):
    """
    Pandas 전처리 핸들러

    기능:
    - CSV 파일 읽기
    - 컬럼 선택
    - 필터 적용
    - Parquet 저장
    """

    async def execute(self, params: HandlerParams) -> HandlerResult:
        try:
            import pandas as pd
        except ImportError:
            return HandlerResult(
                action="preprocess",
                success=False,
                error="pandas is required. Install with: pip install pandas pyarrow"
            )

        # 파라미터 추출
        input_path = params.handler_params.get("input_path")
        output_path = params.handler_params.get("output_path")
        columns = params.handler_params.get("columns")
        filters = params.handler_params.get("filters", {})

        if not input_path:
            return HandlerResult(
                action="preprocess",
                success=False,
                error="input_path is required"
            )

        logger.info(f"Starting preprocessing: {input_path}")

        # 1. CSV 읽기
        try:
            df = pd.read_csv(input_path)
            logger.info(f"Loaded {len(df)} rows from {input_path}")
        except Exception as e:
            return HandlerResult(
                action="preprocess",
                success=False,
                error=f"Failed to read CSV: {e}"
            )

        # 2. 컬럼 선택
        if columns:
            missing = [c for c in columns if c not in df.columns]
            if missing:
                return HandlerResult(
                    action="preprocess",
                    success=False,
                    error=f"Missing columns: {missing}"
                )
            df = df[columns]
            logger.info(f"Selected columns: {columns}")

        # 3. 필터 적용
        df = self._apply_filters(df, filters)
        logger.info(f"After filtering: {len(df)} rows")

        # 4. Parquet 저장
        if output_path:
            try:
                output_dir = Path(output_path).parent
                output_dir.mkdir(parents=True, exist_ok=True)
                df.to_parquet(output_path, index=False)
                logger.info(f"Saved to {output_path}")
            except Exception as e:
                return HandlerResult(
                    action="preprocess",
                    success=False,
                    error=f"Failed to save Parquet: {e}"
                )

        return HandlerResult(
            action="preprocess",
            success=True,
            data={
                "input_rows": len(pd.read_csv(input_path)),
                "output_rows": len(df),
                "output_path": output_path,
            }
        )

    def _apply_filters(self, df: Any, filters: dict) -> Any:
        """
        필터 적용

        filters 형식:
        {
            "column_name": {"gt": 0, "lt": 100},
            "another_column": {"eq": "value"}
        }
        """
        for column, conditions in filters.items():
            if column not in df.columns:
                continue

            for op, value in conditions.items():
                if op == "gt":
                    df = df[df[column] > value]
                elif op == "gte":
                    df = df[df[column] >= value]
                elif op == "lt":
                    df = df[df[column] < value]
                elif op == "lte":
                    df = df[df[column] <= value]
                elif op == "eq":
                    df = df[df[column] == value]
                elif op == "ne":
                    df = df[df[column] != value]
                elif op == "in":
                    df = df[df[column].isin(value)]
                elif op == "notnull":
                    df = df[df[column].notna()]

        return df
