"""공통 모델 정의"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar('T')


class PageParams(BaseModel):
    """페이징 파라미터"""
    page: int = Field(default=1, ge=1, description="페이지 번호")
    size: int = Field(default=20, ge=1, le=100, description="페이지 크기")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class PageResponse(BaseModel, Generic[T]):
    """페이징 응답"""
    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: list[T], total: int, page: int, size: int) -> "PageResponse[T]":
        pages = (total + size - 1) // size if size > 0 else 0
        return cls(items=items, total=total, page=page, size=size, pages=pages)


class ErrorDetail(BaseModel):
    """에러 상세 정보"""
    code: str
    message: str


class ErrorResponse(BaseModel):
    """에러 응답"""
    error: ErrorDetail
