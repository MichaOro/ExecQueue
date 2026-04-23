from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Requirement(SQLModel, table=True):
    __tablename__ = "requirement"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    markdown_content: Optional[str] = None
    status: str = Field(default="pending", index=True)
    verification_prompt: Optional[str] = None
    is_test: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
