from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkPackage(SQLModel, table=True):
    __tablename__ = "work_packages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    requirement_id: int = Field(index=True)
    title: str
    description: Optional[str] = None
    implementation_prompt: Optional[str] = None
    execution_order: int = Field(default=0)
    verification_prompt: Optional[str] = None
    status: str = Field(default="pending", index=True)
    is_test: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
