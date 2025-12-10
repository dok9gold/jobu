"""
데이터베이스 공통 예외 클래스
"""


class DatabaseError(Exception):
    """데이터베이스 관련 기본 예외"""
    pass


class ConnectionPoolExhaustedError(DatabaseError):
    """커넥션풀 고갈 에러"""
    pass


class TransactionError(DatabaseError):
    """트랜잭션 관련 에러"""
    pass


class ReadOnlyTransactionError(TransactionError):
    """읽기 전용 트랜잭션에서 쓰기 시도 에러"""
    pass


class QueryExecutionError(DatabaseError):
    """쿼리 실행 에러"""
    pass
