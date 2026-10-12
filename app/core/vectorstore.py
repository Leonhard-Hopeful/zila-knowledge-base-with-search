import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, FilterSelector, MatchValue,
    PayloadSchemaType, PointStruct, VectorParams,
)

from app.config import settings

client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)


def ensure_collection():
    existing = {c.name for c in client.get_collections().collections}
    if settings.collection in existing:
        return
    client.create_collection(
        settings.collection,
        vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
    )
    for field in ("department", "cohort_id", "document_id"):
        client.create_payload_index(settings.collection, field, PayloadSchemaType.KEYWORD)


def _point_id(document_id: str, idx: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{idx}"))


def upsert_chunks(document_id, department, cohort_id, title, source, chunks, vectors):
    points = [
        PointStruct(
            id=_point_id(document_id, i),
            vector=vec,
            payload={
                "document_id": document_id,
                "department": department,
                "cohort_id": cohort_id,
                "title": title,
                "source": source,
                "chunk_index": i,
                "text": ch.text,
                "page": ch.page,
                "section": ch.section,
            },
        )
        for i, (ch, vec) in enumerate(zip(chunks, vectors))
    ]
    for start in range(0, len(points), 256):
        client.upsert(settings.collection, points[start:start + 256])


def delete_document(document_id: str):
    client.delete(
        settings.collection,
        points_selector=FilterSelector(filter=Filter(must=[
            FieldCondition(key="document_id", match=MatchValue(value=document_id))
        ])),
    )


def search(vector, department, cohort_id, top_k, score_threshold):
    flt = Filter(must=[
        FieldCondition(key="department", match=MatchValue(value=department)),
        FieldCondition(key="cohort_id", match=MatchValue(value=cohort_id)),
    ])
    return client.query_points(
        settings.collection, query=vector, query_filter=flt,
        limit=top_k, score_threshold=score_threshold, with_payload=True,
    ).points
