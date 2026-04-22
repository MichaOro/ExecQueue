from typing import Optional
from datetime import datetime

from sqlmodel import SQLModel, Field


class Requirement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str
    markdown_content: str
    status: str = "backlog"
    created_at: datetime = Field(default_factory=datetime.utcnow)