"""
Pydantic schemas for the FastAPI layer.
"""

from pydantic import BaseModel, Field
from typing import Any


class QueryRequest(BaseModel):
    question: str = Field(..., description="The natural language question to ask the database.")


class QueryResponse(BaseModel):
    question: str
    generated_sql: str
    raw_data: list[dict[str, Any]]
    answer: str


class HealthResponse(BaseModel):
    status: str
    message: str
