from fastapi import APIRouter, Depends

from app.core import embedder, vectorstore
from app.schemas import SearchHit, SearchRequest, SearchResponse
from app.security import require_api_key

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    vec = embedder.embed_query(req.query)
    points = vectorstore.search(vec, req.department.lower().strip(), req.cohort_id,
                                req.top_k, req.score_threshold)
    return SearchResponse(hits=[
        SearchHit(
            text=p.payload["text"], score=p.score,
            document_id=p.payload["document_id"], title=p.payload["title"],
            source=p.payload["source"], page=p.payload.get("page"),
            section=p.payload.get("section"),
        )
        for p in points
    ])
