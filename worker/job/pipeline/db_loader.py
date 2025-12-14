"""
DB 적재 핸들러 템플릿

Parquet 파일을 읽어 PostgreSQL COPY로 적재하는 예시입니다.

params 예시:
{
    "input_path": "/data/processed/sample.parquet",
    "target_table": "sample_data",
    "target_db": "data",
    "truncate_before": false
}
"""

import logging
import io
from pathlib import Path

from worker.base import BaseHandler, handler, HandlerParams, HandlerResult
from database import transactional, get_connection

logger = logging.getLogger(__name__)


@handler("db_loader")
class DbLoaderHandler(BaseHandler):
    """
    DB 적재 핸들러

    기능:
    - Parquet 파일 읽기
    - PostgreSQL COPY 명령으로 벌크 적재
    - TRUNCATE 옵션
    """

    async def execute(self, params: HandlerParams) -> HandlerResult:
        try:
            import pandas as pd
        except ImportError:
            return HandlerResult(
                action="load",
                success=False,
                error="pandas is required. Install with: pip install pandas pyarrow"
            )

        input_path = params.handler_params.get("input_path")
        target_table = params.handler_params.get("target_table")
        target_db = params.handler_params.get("target_db", "default")
        truncate_before = params.handler_params.get("truncate_before", False)

        if not input_path or not target_table:
            return HandlerResult(
                action="load",
                success=False,
                error="input_path and target_table are required"
            )

        # Parquet 읽기
        try:
            df = pd.read_parquet(input_path)
            logger.info(f"Loaded {len(df)} rows from {input_path}")
        except Exception as e:
            return HandlerResult(
                action="load",
                success=False,
                error=f"Failed to read Parquet: {e}"
            )

        # DB 적재
        try:
            rows_loaded = await self._load_to_db(
                df, target_table, target_db, truncate_before
            )
            logger.info(f"Loaded {rows_loaded} rows to {target_table}")
        except Exception as e:
            return HandlerResult(
                action="load",
                success=False,
                error=f"Failed to load to DB: {e}"
            )

        return HandlerResult(
            action="load",
            success=True,
            data={
                "input_path": input_path,
                "target_table": target_table,
                "rows_loaded": rows_loaded,
            }
        )

    @transactional
    async def _load_to_db(
        self,
        df,
        target_table: str,
        target_db: str,
        truncate_before: bool
    ) -> int:
        """
        DataFrame을 DB에 적재

        PostgreSQL의 경우 COPY FROM STDIN 사용
        다른 DB는 executemany 사용
        """
        ctx = get_connection(target_db)

        if truncate_before:
            await ctx.execute(f"TRUNCATE TABLE {target_table}")
            logger.info(f"Truncated table {target_table}")

        # CSV 형식으로 변환
        buffer = io.StringIO()
        df.to_csv(buffer, index=False, header=False)
        buffer.seek(0)

        # PostgreSQL COPY (asyncpg)
        if hasattr(ctx.connection, "copy_to_table"):
            columns = list(df.columns)
            await ctx.connection.copy_to_table(
                target_table,
                source=buffer,
                columns=columns,
                format="csv",
            )
            return len(df)

        # 일반 INSERT (fallback)
        columns = ", ".join(df.columns)
        placeholders = ", ".join(["?" for _ in df.columns])
        sql = f"INSERT INTO {target_table} ({columns}) VALUES ({placeholders})"

        for row in df.itertuples(index=False):
            await ctx.execute(sql, *row)

        return len(df)
