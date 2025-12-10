"""
JSON 구조화 로깅 설정

ELK/Loki 등 로그 수집 시스템과 연동 가능한 JSON 포맷 로깅을 제공합니다.
"""

import logging
import sys

try:
    from pythonjsonlogger import jsonlogger
    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False


class CustomJsonFormatter(jsonlogger.JsonFormatter if HAS_JSON_LOGGER else logging.Formatter):
    """JSON 로그 포매터"""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = self.formatTime(record)
        log_record['level'] = record.levelname
        log_record['logger'] = record.name

        # message 필드 정리
        if 'message' not in log_record and record.getMessage():
            log_record['message'] = record.getMessage()


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: str | None = None
) -> None:
    """
    로깅 설정

    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: JSON 포맷 사용 여부 (False면 기본 텍스트 포맷)
        log_file: 로그 파일 경로 (None이면 stdout만 사용)
    """
    handlers = []

    # stdout 핸들러
    stream_handler = logging.StreamHandler(sys.stdout)

    if json_format and HAS_JSON_LOGGER:
        formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    # 파일 핸들러 (옵션)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # 루트 로거 설정
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=handlers,
        force=True  # 기존 설정 덮어쓰기
    )

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('aiosqlite').setLevel(logging.WARNING)
