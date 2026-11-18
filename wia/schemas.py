"""Data shapes shared across the app. Pydantic validates everything the LLM returns."""
from typing import Literal

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    revision: str
    status: str
    effective_date: str
    section: str
    text: str


class RetrievedChunk(Chunk):
    score: float


class Citation(BaseModel):
    doc_id: str
    revision: str
    section: str


class LLMAnswer(BaseModel):
    """The structured output we force the LLM to return."""
    answer: str = Field(description="Short, direct answer for a technician.")
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    insufficient_information: bool = Field(
        default=False,
        description="True if the sources do not contain the answer.",
    )


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    confidence: Literal["high", "medium", "low"]
    insufficient_information: bool
    status: Literal["answered", "refused", "needs_review"]
    review_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    sources_considered: list[str] = Field(default_factory=list)
