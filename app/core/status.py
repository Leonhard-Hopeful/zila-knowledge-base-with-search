import redis

from app.config import settings

r = redis.from_url(settings.redis_url, decode_responses=True)


def set_status(doc_id: str, **fields):
    r.hset(f"doc:{doc_id}", mapping={k: str(v) for k, v in fields.items()})


def get_status(doc_id: str) -> dict | None:
    data = r.hgetall(f"doc:{doc_id}")
    return data or None


def reset_status(doc_id: str):
    """Clear stale fields (e.g. an old error) when a document is re-uploaded."""
    r.delete(f"doc:{doc_id}")
