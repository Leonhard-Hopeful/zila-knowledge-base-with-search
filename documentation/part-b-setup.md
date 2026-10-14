# Zigex AI Services: Documentation

# Part B: Setup and reproduction

By the end of this part, anyone should have the full stack running on their machine and be able to verify it works. Commands are given for **Windows PowerShell** first, with macOS/Linux differences noted.

---

## 5. Prerequisites

### 5.1 Software

| Tool | Version | Needed for | Check with |
|---|---|---|---|
| **Docker Desktop** | Current, with WSL 2 enabled on Windows | Running the whole stack (recommended path) | `docker --version` and `docker compose version` |
| **Git** | Any recent | Cloning and pushing the repo | `git --version` |
| **Python** | **3.10** | Only for running without Docker, or running tests | `python --version` |

The code uses `str | None` type syntax, so **Python 3.10 or newer is required** outside Docker. Inside Docker the image uses `python:3.10-slim`, so nothing needs installing.

### 5.2 Accounts and keys

| Key | Where to get it | Needed for | Required? |
|---|---|---|---|
| **Gemini API key** | https://aistudio.google.com/apikey | Embeddings (RAG) and the digest LLM | Yes, for RAG. Digest can run in mock mode without it |
| **Tavily API key** | https://app.tavily.com | Web search in the weekly digest | Only for real digest runs |
| **Service API key** | You create it (see 7.2) | Protecting this service's own endpoints | Yes |

### 5.3 Machine requirements

- At least **10 GB free disk space** (Docker images, build cache and volumes)
- A working internet connection. The first build downloads about 1 GB
- Hardware virtualization enabled (Task Manager, Performance, CPU: "Virtualization: Enabled")

### 5.4 Windows notes

- After installing Docker Desktop, **close and reopen PowerShell**. `PATH` is only read when a terminal starts.
- If Docker reports that WSL 2 is missing, run `wsl --install` in an **administrator** PowerShell and reboot.
- In PowerShell, `curl` is an alias for another command. Use **`curl.exe`** instead.
- If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

---

## 6. Project structure

```
rag-ingest/
├── app/
│   ├── main.py                  # FastAPI app, startup (waits for Qdrant, creates collection)
│   ├── config.py                # All settings, read from environment / .env
│   ├── schemas.py               # Pydantic models for the search endpoint
│   ├── security.py              # x-api-key check (Swagger "Authorize" button)
│   ├── api/
│   │   ├── documents.py         # Upload, status, delete
│   │   ├── search.py            # Department/cohort-filtered semantic search
│   │   └── digests.py           # Digest preview, run, status, list, publish, student lookup
│   ├── core/
│   │   ├── parsers.py           # PDF, DOCX, PPTX, MD, TXT to text sections
│   │   ├── chunker.py           # Dynamic chunking strategies
│   │   ├── embedder.py          # Gemini embeddings with batching and backoff
│   │   ├── vectorstore.py       # Qdrant collection, upsert, delete, filtered search
│   │   ├── status.py            # Ingestion status in Redis
│   │   ├── profiles.py          # Student profiles, segmentation, Zigex profile fetch
│   │   ├── tavily_search.py     # Tavily client (results + images)
│   │   ├── llm.py               # Gemini JSON generation with retries
│   │   ├── digest_agent.py      # Plan, search, curate, validate, render
│   │   ├── digest_store.py      # Digest storage, de-duplication, run counters (Redis)
│   │   └── delivery.py          # Signed webhook to Zigex
│   └── worker/
│       ├── celery_app.py        # Celery config, queues, weekly Beat schedule
│       ├── tasks.py             # Document ingestion task
│       └── digest_tasks.py      # Weekly run + per-segment digest tasks
├── tests/
│   └── test_digest.py           # Digest pipeline tests (mocked Tavily and Gemini)
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # pytest, fakeredis
├── pytest.ini
├── Dockerfile                   # One image, used by api, worker, digest-worker and beat
├── docker-compose.yml           # The six services
├── .dockerignore
├── .gitignore
├── .env.example                 # Template for .env (committed)
├── .env                         # Your real secrets (never committed)
└── README.md
```

**Rule of thumb for where things live:** `api/` handles HTTP only, `core/` holds logic with no HTTP or Celery code, `worker/` holds background jobs that call into `core/`.

---

## 7. Configuration

### 7.1 How configuration works

`app/config.py` defines a `Settings` class. Each field is filled from an **environment variable of the same name (case-insensitive)**, falling back to a default. A `.env` file in the project root is read automatically. `docker-compose.yml` passes `.env` into the `api`, `worker`, `digest-worker` and `beat` containers.

Create your file from the template:

```powershell
copy .env.example .env      # macOS/Linux: cp .env.example .env
```

Then edit `.env`. **Never commit `.env`.** It is listed in `.gitignore`.

### 7.2 The two kinds of API key

This causes the most confusion, so it is called out here.

| Kind | Variable | Who defines it | Used by |
|---|---|---|---|
| **This service's key** | `API_KEY` | **You.** It is any secret string you invent | Every caller of this service's endpoints sends it in the `x-api-key` header |
| **Third-party keys** | `GEMINI_API_KEY`, `TAVILY_API_KEY` | Google and Tavily issue them | This service, when it calls Gemini and Tavily |

There is nothing to "fetch" for `API_KEY`. Generate a strong value:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put it in `.env` as `API_KEY=...`, then use the **same value** in Swagger's *Authorize* dialog and in any caller.

If you get `401 Invalid API key`, the value sent does not match `API_KEY`. If you get an *"API key not valid"* error mentioning Google or Tavily, the problem is a third-party key.

### 7.3 Variable reference

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `change-me` | Secret protecting this service. **Always change it** |
| `GEMINI_API_KEY` | empty | Google AI Studio key. Used for embeddings and the digest LLM |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model. **Fixed per collection** |
| `EMBEDDING_DIM` | `768` | Vector size. **Fixed per collection** |
| `COLLECTION` | `course_content` | Qdrant collection name |
| `MAX_UPLOAD_MB` | `50` | Upload size limit |
| `ALLOWED_DEPARTMENTS` | `["ml","web","mobile","devops","data"]` | JSON list of valid departments. Format in `.env`: `ALLOWED_DEPARTMENTS=["ml","web"]` |
| `UPLOAD_DIR` | `/data/uploads` | Where uploaded files are stored (shared volume in Docker) |
| `REDIS_URL` | `redis://localhost:6379/0` | Overridden to `redis://redis:6379/0` by Compose |
| `QDRANT_URL` | `http://localhost:6333` | Overridden to `http://qdrant:6333` by Compose |
| `TAVILY_API_KEY` | empty | Tavily search key (digest) |
| `LLM_MODEL` | `gemini-2.5-flash` | Gemini text model for the digest. Change it if your key does not support it |
| `ZIGEX_API_URL` | empty | Zigex endpoint listing student profiles (Part E) |
| `ZIGEX_API_TOKEN` | empty | Bearer token for that endpoint |
| `ZIGEX_WEBHOOK_URL` | empty | Where finished digests are posted. Empty means no delivery |
| `ZIGEX_WEBHOOK_SECRET` | empty | HMAC secret used to sign webhooks |
| `DIGEST_TIMEZONE` | `Africa/Douala` | Timezone used by the schedule and for "today" |
| `DIGEST_CRON_DAY` | `mon` | Day of the week the digest runs (`mon` to `sun`) |
| `DIGEST_CRON_HOUR` | `6` | Hour of day (0 to 23, in `DIGEST_TIMEZONE`) |
| `DIGEST_QUERIES_PER_SEGMENT` | `4` | Search queries per segment, per round |
| `DIGEST_MAX_ITEMS` | `6` | Opportunities per digest |
| `DIGEST_AUTO_PUBLISH` | `true` | `false` holds digests as `pending_review` until approved |
| `MOCK_MODE` | `false` | `true` returns fake Tavily and LLM output (section 10) |

### 7.4 Rules that prevent costly mistakes

1. **Do not change `EMBEDDING_MODEL` or `EMBEDDING_DIM` after documents exist.** Vectors from different models are incompatible, and the stored collection has a fixed size. To change them, delete the collection and re-upload every document.
2. **Do not put `REDIS_URL` or `QDRANT_URL` in `.env` for Docker.** Compose sets them to the container hostnames (`redis`, `qdrant`). A leftover `localhost` value would break the containers.
3. **After editing `.env`**, run `docker compose up -d` so containers are recreated with the new values. A plain `restart` does not reliably pick up changes.
4. **After editing code or `requirements.txt`**, run `docker compose up -d --build`. The code is baked into the image.

---

## 8. Running locally with Docker (recommended)

### 8.1 Get the code

```powershell
git clone https://github.com/<org>/<repo>.git
cd <repo>
```

Or unzip the project and `cd` into the folder that contains `docker-compose.yml`.

### 8.2 Create `.env`

```powershell
copy .env.example .env
```

Minimum values to run the RAG part:

```
API_KEY=<your generated secret>
GEMINI_API_KEY=<your Gemini key>
```

For the digest in mock mode, also set `MOCK_MODE=true` (section 10). For real digests, add `TAVILY_API_KEY`.

### 8.3 Build the image

```powershell
docker compose build api
```

- Run this from the folder containing `docker-compose.yml`.
- The first build downloads Python packages. It takes about 5 minutes on a fast connection and can take **30 minutes or more on a slow one**.
- If it fails with a network timeout, **just run the same command again**. Finished layers are cached.
- The `worker`, `digest-worker` and `beat` services reuse the image built for `api`, so it is built only once. Always build `api` first.

### 8.4 Start the stack

```powershell
docker compose up
```

This runs in the foreground and streams logs. Press **Ctrl+C** to stop. To run in the background, use `docker compose up -d` and view logs with `docker compose logs -f`.

### 8.5 Verify it is healthy

**1. All six services running:**

```powershell
docker compose ps
```

Expect `api`, `worker`, `digest-worker`, `beat`, `redis` and `qdrant`.

**2. Expected log lines:**

| Service | Line to look for |
|---|---|
| `qdrant` | `Qdrant HTTP listening on 6333` |
| `api` | `Application startup complete.` |
| `worker` | `celery@... ready.` |
| `digest-worker` | `celery@digest@... ready.` |
| `beat` | `beat: Starting...` |

The API may print a few retries while Qdrant boots. That is normal: the startup loop waits up to about a minute.

**3. HTTP checks:**

```powershell
curl.exe http://localhost:8000/health          # {"ok":true}
curl.exe http://localhost:6333/collections     # JSON listing course_content
```

**4. Swagger UI:** open http://localhost:8000/docs, click **Authorize**, and paste your `API_KEY`. Part C walks through the first upload and search.

### 8.6 Ports

| Port | Service | Exposed to your machine |
|---|---|---|
| 8000 | API and Swagger UI | Yes |
| 6333 | Qdrant REST and dashboard (`/dashboard`) | Yes, for development. Do not expose publicly in production |
| 6379 | Redis | **No.** Reachable only inside the Compose network |

### 8.7 Everyday commands

```powershell
docker compose ps                         # what is running
docker compose logs -f api worker         # follow logs (add digest-worker, beat)
docker compose up -d                      # start in background
docker compose up -d --build              # rebuild after code/dependency changes
docker compose down                       # stop, keep data
docker compose down -v                    # stop and DELETE all data (vectors, queue, uploads)
docker compose up -d --scale worker=3     # more ingestion workers
```

**Never scale `beat`.** Two schedulers would trigger every job twice.

### 8.8 Where data lives

| Volume | Contents |
|---|---|
| `qdrantdata` | Vectors and chunk text |
| `redisdata` | Queue, ingestion status, digests, de-duplication sets (append-only persistence is on) |
| `uploads` | Original uploaded files, shared by the API and workers |

`docker compose down` keeps these. `docker compose down -v` deletes them.

---

## 9. Running without Docker (Windows development)

Use this only when you need to debug the Python code directly. The Docker path is the reference setup.

### 9.1 Stop the Compose stack first

```powershell
docker compose down
```

This avoids port clashes and prevents the containerized workers from taking jobs meant for your local process.

### 9.2 Create the environment

```powershell
py -3.10 -m venv doc-env
doc-env\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS/Linux: `python3.10 -m venv .venv && source .venv/bin/activate`.

### 9.3 Start Redis and Qdrant in Docker

```powershell
docker run -d --name redis  -p 6379:6379 redis:7
docker run -d --name qdrant -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant
```

If they already exist, use `docker start redis qdrant`. Confirm with `curl.exe http://localhost:6333/collections`.

### 9.4 `.env` for local runs

Use the same `.env`, but **do not set** `REDIS_URL` or `QDRANT_URL`. The defaults point to `localhost`. If `localhost` fails on Windows because it resolves to IPv6, set:

```
REDIS_URL=redis://127.0.0.1:6379/0
QDRANT_URL=http://127.0.0.1:6333
```

### 9.5 Start the processes (separate terminals, venv activated in each)

```powershell
# Terminal 1: API
uvicorn app.main:app --reload

# Terminal 2: worker, consuming both queues
celery -A app.worker.celery_app.celery worker --loglevel=info --pool=solo -Q celery,digest

# Terminal 3: scheduler (only if you want the weekly cron locally)
celery -A app.worker.celery_app.celery beat --loglevel=info
```

**Why `--pool=solo`:** Celery's default `prefork` pool does not work on Windows and fails with `ValueError: not enough values to unpack` when the first task runs. `solo` runs one task at a time, which is fine for development. This flag is not needed inside Docker (Linux).

### 9.6 Run the tests

```powershell
pip install -r requirements-dev.txt
pytest
```

Expected: `3 passed`. The tests mock Tavily, Gemini and Redis, so they need no keys or running services.

---

## 10. Mock mode

Mock mode lets you test the **weekly digest pipeline** without a Tavily key or a working Gemini LLM key. The agent still runs its full logic (planning, source selection, validation, Markdown rendering). Only the two external calls are replaced with canned data.

> **Scope:** mock mode covers the digest only. Document upload and search (Part C) call Gemini for embeddings and still need a valid `GEMINI_API_KEY`.

### 10.1 Code changes

**`app/config.py`**: add a field to `Settings`:

```python
    mock_mode: bool = False
```

**`app/core/tavily_search.py`**: add at the top of `search_web`:

```python
    if settings.mock_mode:
        return {
            "results": [{"url": f"https://example.org/opportunity-{i}",
                         "title": f"Sample opportunity {i}",
                         "content": "Sample description of a student opportunity.",
                         "score": 1 - i / 10} for i in range(5)],
            "images": [{"url": "https://placehold.co/600x300.jpg",
                        "description": "Students collaborating at a hackathon"}],
        }
```

**`app/core/llm.py`**: add at the top of `generate_json`:

```python
    if settings.mock_mode:
        if prompt.startswith("TASK: PLAN_QUERIES"):
            return {"queries": ["ml internships", "ai hackathon",
                                "data science scholarships", "tech conference"]}
        from datetime import date, timedelta
        d = (date.today() + timedelta(days=30)).isoformat()
        return {"headline": "Mock weekly digest", "intro": "Sample intro.", "items": [
            {"source_id": i, "title": f"Sample opportunity {i}", "summary": "Sample summary.",
             "why_relevant": "Matches the group's skills.", "category": "hackathon",
             "deadline": d, "image_id": 0 if i == 0 else None,
             "image_caption": "Students at a hackathon" if i == 0 else None}
            for i in range(4)]}
```

**`.env.example`**: document the switch:

```
MOCK_MODE=false
```

### 10.2 Enable and apply

In `.env`:

```
API_KEY=test123
MOCK_MODE=true
```

Rebuild so the code changes enter the image:

```powershell
docker compose up -d --build
```

### 10.3 Try it

In Swagger (http://localhost:8000/docs), click **Authorize** and enter `test123`, then call **`POST /v1/digests/preview`**:

```json
{
  "department": "ml",
  "location": "Bamenda",
  "skills": ["python", "nlp"],
  "interests": ["ai"]
}
```

**Expected result (shortened):**

```json
{
  "segment_id": "preview__ml__bamenda",
  "headline": "Mock weekly digest",
  "status": "ok",
  "items": [
    {
      "title": "Sample opportunity 0",
      "category": "hackathon",
      "url": "https://example.org/opportunity-0",
      "image_url": "https://placehold.co/600x300.jpg",
      "image_caption": "Students at a hackathon"
    }
  ],
  "markdown": "# Mock weekly digest\n\n*Week 2026-W42*\n\n..."
}
```

Check that `status` is `ok`, that `items` is non-empty, that one item has an `image_url`, and that `markdown` contains the image and the link.

### 10.4 Switching to real services

1. Set `MOCK_MODE=false`.
2. Add `TAVILY_API_KEY` (and a valid `GEMINI_API_KEY`).
3. Run `docker compose up -d`.
4. Call `/v1/digests/preview` again. It takes 30 to 90 seconds because it makes real searches and LLM calls.

### 10.5 Safety

Never leave `MOCK_MODE=true` in a production `.env`. Students would receive placeholder content. Part F's checklist includes this check.

---

## Part B checklist

You have completed Part B when all of these are true:

- [ ] `docker compose ps` shows six running services
- [ ] `http://localhost:8000/health` returns `{"ok": true}`
- [ ] Swagger's **Authorize** accepts your `API_KEY`
- [ ] `docker compose logs beat` shows `beat: Starting...`
- [ ] `/v1/digests/preview` returns a digest (mock or real)
- [ ] `pytest` reports `3 passed`

**Next: Part C, Subsystem 1: RAG ingestion** (sections 11 to 15).
