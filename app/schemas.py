from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    department: str
    cohort_id: str
    top_k: int = Field(5, ge=1, le=20)
    score_threshold: float | None = 0.35


class SearchHit(BaseModel):
    text: str
    score: float
    document_id: str
    title: str
    source: str
    page: int | None = None
    section: str | None = None


class SearchResponse(BaseModel):
    hits: list[SearchHit]
