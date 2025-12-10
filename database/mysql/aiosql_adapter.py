"""
asyncmy용 aiosql 어댑터

aiosql에서 asyncmy 드라이버를 사용할 수 있도록 하는 어댑터.
PyFormat 스타일 (:name -> %(name)s)로 변환하여 처리.
"""

from contextlib import asynccontextmanager

import aiosql
from aiosql.utils import VAR_REF

ParamType = dict | list | None


def _replacer(ma):
    """Regex hook for named to pyformat conversion."""
    gd = ma.groupdict()
    if gd["dquote"] is not None:
        return gd["dquote"]
    elif gd["squote"] is not None:
        return gd["squote"]
    else:
        return f'{gd["lead"]}%({gd["var_name"]})s'


class AsyncmyAdapter:
    """asyncmy용 aiosql 어댑터"""

    is_aio_driver = True

    def process_sql(self, _query_name, _op_type, sql):
        """named parameter를 pyformat으로 변환 (:name -> %(name)s)"""
        return VAR_REF.sub(_replacer, sql)

    async def select(self, conn, _query_name, sql, parameters, record_class=None):
        """SELECT 쿼리 실행 - 여러 행 반환"""
        from asyncmy.cursors import DictCursor
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(sql, parameters or None)
            results = await cur.fetchall()
            if record_class is not None:
                results = [record_class(**dict(row)) for row in results]
        return results

    async def select_one(self, conn, _query_name, sql, parameters, record_class=None):
        """SELECT 쿼리 실행 - 단일 행 반환"""
        from asyncmy.cursors import DictCursor
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(sql, parameters or None)
            result = await cur.fetchone()
            if result is not None and record_class is not None:
                result = record_class(**dict(result))
        return result

    async def select_value(self, conn, _query_name, sql, parameters):
        """SELECT 쿼리 실행 - 단일 값 반환"""
        async with conn.cursor() as cur:
            await cur.execute(sql, parameters or None)
            result = await cur.fetchone()
        return result[0] if result else None

    @asynccontextmanager
    async def select_cursor(self, conn, _query_name, sql, parameters):
        """SELECT 쿼리 실행 - 커서 반환"""
        from asyncmy.cursors import DictCursor
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(sql, parameters or None)
            yield cur

    async def insert_returning(self, conn, _query_name, sql, parameters):
        """INSERT RETURNING 실행 (MySQL은 RETURNING 미지원, lastrowid 반환)"""
        async with conn.cursor() as cur:
            await cur.execute(sql, parameters or None)
            return cur.lastrowid

    async def insert_update_delete(self, conn, _query_name, sql, parameters):
        """INSERT/UPDATE/DELETE 실행 - affected rows 반환"""
        async with conn.cursor() as cur:
            await cur.execute(sql, parameters or None)
            return cur.rowcount

    async def insert_update_delete_many(self, conn, _query_name, sql, parameters):
        """INSERT/UPDATE/DELETE 다중 실행 - affected rows 반환"""
        async with conn.cursor() as cur:
            await cur.executemany(sql, parameters)
            return cur.rowcount

    async def execute_script(self, conn, sql):
        """스크립트 실행"""
        async with conn.cursor() as cur:
            for statement in sql.split(';'):
                statement = statement.strip()
                if statement:
                    await cur.execute(statement)
        return "DONE"


# aiosql에 asyncmy 어댑터 등록
aiosql.register_adapter("asyncmy", AsyncmyAdapter)
