# Internship RAG Ingestion Service

Supervisors upload course notes; the service chunks them, embeds them with
Gemini, and stores them in Qdrant, filtered by department and cohort so the AI
agent only sees the right course content.

## Architecture
FastAPI (upload/search) -> Redis (queue + status) -> Celery worker
(parse -> chunk -> embed -> upsert) -> Qdrant (one collection, filtered by
`department` + `cohort_id`).

## Quick start (Docker)
1. Install Docker Desktop and wait for "Engine running".
2. `cp .env.example .env` (Windows: `copy .env.example .env`) and fill in
   `API_KEY` and `GEMINI_API_KEY` (https://aistudio.google.com/apikey).
3. `docker compose up --build`
4. Open http://localhost:8000/docs, click **Authorize**, paste your `API_KEY`.

## Endpoints (header: `x-api-key`)
- `POST /v1/documents`: form fields `file`, `department`, `cohort_id`
  (optional: `title`, `chunk_size`, `chunk_overlap`, `document_id`)
- `GET /v1/documents/{id}`: status (queued, parsing, chunking, embedding, indexing, done, failed)
- `DELETE /v1/documents/{id}`
- `POST /v1/search`: `{"query", "department", "cohort_id", "top_k", "score_threshold"}`

## Operations
- Logs: `docker compose logs -f api worker`
- Scale workers: `docker compose up -d --scale worker=3`
- Stop (keep data): `docker compose down`
- Reset everything (deletes data): `docker compose down -v`

## Local development without Docker (Windows)
Run Redis and Qdrant in Docker, then:
- `uvicorn app.main:app --reload`
- `celery -A app.worker.celery_app.celery worker --loglevel=info --pool=solo`
  (`--pool=solo` is required on Windows only)

## Known limits
- Gemini free tier is rate limited; large uploads ingest slowly (built-in backoff).
- Document text is sent to Google for embedding; use a paid tier for sensitive material.
- Changing EMBEDDING_MODEL or EMBEDDING_DIM requires deleting the Qdrant
  collection (`curl -X DELETE http://localhost:6333/collections/course_content`)
  and re-uploading all documents.
- The agent backend must take `department` and `cohort_id` from the
  authenticated intern's profile, never from the chat text.

## Production notes
- Replace the shared API key with JWT auth (supervisor can upload only to own department).
- Move uploads to S3/MinIO if workers run on multiple machines.
- Don't expose port 6333 publicly; put the API behind HTTPS.

## Weekly opportunity digest (Zigex)
Every week a cron job finds opportunities for students and writes a blog post per segment.

Flow: Celery Beat (`digest.run_weekly`) -> fetch student profiles from Zigex -> group into
segments (department + location) -> per segment: LLM plans queries -> Tavily search (with
images) -> LLM curates by source/image ID -> code validates (no invented links, no expired
items, no repeats) -> Markdown blog stored in Redis and pushed to the Zigex webhook (HMAC-signed).

Endpoints (all need `x-api-key`):
- `POST /v1/digests/preview`: test one segment synchronously (nothing saved/sent)
- `POST /v1/digests/run`: trigger the weekly job now (`dry_run`, `force`, optional `profiles`)
- `GET /v1/digests/run-status`, `GET /v1/digests?week=2026-W42`
- `GET /v1/digests/{week}/{segment_id}`, `GET /v1/digests/student/{student_id}`
- `POST /v1/digests/{week}/{segment_id}/publish`: approve (when DIGEST_AUTO_PUBLISH=false)

Services: `digest-worker` (queue `digest`) and `beat` (exactly one instance).
Privacy: only aggregate segment attributes go to Tavily/Gemini, never names, emails or IDs.
Tests: `pip install -r requirements-dev.txt && pytest`
