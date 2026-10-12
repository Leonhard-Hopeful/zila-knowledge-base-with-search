from google.genai.errors import APIError

from app.core import chunker, embedder, parsers, vectorstore
from app.core.status import set_status
from app.worker.celery_app import celery

RETRYABLE = (ConnectionError, APIError)


@celery.task(
    bind=True,
    autoretry_for=RETRYABLE,
    retry_backoff=60,
    retry_backoff_max=300,
    max_retries=3,
)
def ingest_document(self, document_id, path, department, cohort_id, title,
                    filename, chunk_size=None, chunk_overlap=None):
    try:
        set_status(document_id, state="parsing")
        sections, kind = parsers.parse_file(path)

        set_status(document_id, state="chunking")
        chunks = chunker.chunk_document(sections, kind, chunk_size, chunk_overlap)
        if not chunks:
            raise ValueError("No extractable text found (scanned PDF?)")

        set_status(document_id, state="embedding", chunks=len(chunks))
        vectors = embedder.embed_documents([c.text for c in chunks])

        set_status(document_id, state="indexing")
        vectorstore.delete_document(document_id)      # clean re-ingest
        vectorstore.upsert_chunks(document_id, department, cohort_id,
                                  title, filename, chunks, vectors)
        set_status(document_id, state="done", chunks=len(chunks), error="")
    except Exception as e:
        will_retry = isinstance(e, RETRYABLE) and self.request.retries < self.max_retries
        set_status(document_id,
                   state="retrying" if will_retry else "failed",
                   error=str(e))
        raise
