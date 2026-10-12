import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import digests, documents, search
from app.config import settings
from app.core import vectorstore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Qdrant may still be booting under docker compose: retry.
    for attempt in range(20):
        try:
            vectorstore.ensure_collection()
            break
        except Exception as e:
            if attempt == 19:
                raise RuntimeError(
                    f"Cannot reach Qdrant at {settings.qdrant_url}. Is it running?"
                ) from e
            time.sleep(3)
    yield


app = FastAPI(title="Zigex Internship RAG + Opportunity Digest", lifespan=lifespan)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(digests.router)


@app.get("/health")
def health():
    return {"ok": True}
