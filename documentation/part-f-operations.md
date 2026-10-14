# Zigex AI Services: Documentation

# Part F: Operations

This part covers how to verify the system, watch it, fix it, budget for it and keep it safe. It uses the real errors encountered while building the system, with their fixes.

---

## 30. Testing

### 30.1 Test layers

| Layer | What it proves | Needs | Where |
|---|---|---|---|
| **Automated tests** | Logic is correct: chunking, validation, signatures, auth, API errors | Nothing external (everything is mocked) | `tests/` |
| **Manual smoke test** | A fresh deployment works end to end | Running stack and real keys | Section 30.5 |
| **Retrieval evaluation** | Search actually finds the right notes | Uploaded documents and a question list | Section 30.5 |
| **Digest review** | Weekly content is safe and useful | A human | Section 30.7 |

### 30.2 Running the automated suite

```powershell
pip install -r requirements-dev.txt      # pytest, fakeredis
pytest
```

Expected: **20 passed**. (Part B's checklist mentions 3 tests. That was the digest file alone. This section adds three more files.) No Docker, Redis, Qdrant or API keys are needed.

Run a single file with `pytest tests/test_delivery.py -v`, or a single test with `pytest -k signature`.

### 30.3 What the tests cover

| File | Tests | Covers |
|---|---|---|
| `test_digest.py` | 3 | Agent validation (drops expired, hallucinated, duplicate and already-seen items), segmentation (small groups merge, student IDs never in the public view), and the full segment task using an in-memory Redis |
| `test_chunker.py` | 6 | Chunk size and overlap defaults, overlap clamped below size, Markdown heading breadcrumbs, page numbers kept, tiny fragments dropped, long text split into several chunks |
| `test_delivery.py` | 4 | Webhook signature equals the HMAC of the raw body, non-ASCII text survives, no URL means no delivery, 3 attempts then give up, non-2xx counts as failure |
| `test_api.py` | 7 | `/health` needs no key, wrong or missing key gives `401`, invalid search body gives `422`, upload rejects an unknown department (`400`), unsupported type (`415`) and bad chunk settings (`422`), and a digest preview with mocked providers |

How they stay offline:

- **Tavily and Gemini** are replaced by small fake functions (`monkeypatch`).
- **Redis** is replaced by `fakeredis`.
- **The tokenizer:** the chunker tests swap the token-based splitter for a character-based one, so they do not need the one-time `tiktoken` download. They check the logic around splitting, not tokenization itself.
- **Startup hook:** the API tests use `TestClient(app)` without a `with` block, so the Qdrant startup check does not run.

### 30.4 What the automated tests do not cover

Real calls to Gemini, Tavily and Qdrant, Celery running in separate processes, the Docker images, and the Zigex side. Those are covered by the smoke test below.

### 30.5 Manual smoke test (after every deployment)

Run in order. Each step has an expected result.

| # | Action | Expected |
|---|---|---|
| 1 | `GET /health` | `{"ok": true}` |
| 2 | `GET /v1/digests` with no key | `401` |
| 3 | `GET /v1/digests` with the key | `200` and a list |
| 4 | Upload a small text-based file (`department=ml`, `cohort_id=smoke-1`) | `202`, then `state: done` within a few minutes |
| 5 | Search a question from that file (`score_threshold: 0.0`) | At least one hit with the right `title` |
| 6 | Same search with `department=web` | `{"hits": []}` |
| 7 | Same search with `cohort_id=other` | `{"hits": []}` |
| 8 | `DELETE /v1/documents/{id}` | `200`. A repeat search returns no hits |
| 9 | `POST /v1/digests/preview` | A digest with items, links and `markdown` |
| 10 | `docker compose logs beat` | `beat: Starting...` |
| 11 | `docker compose ps` | All six services `running` |

**Release gate (before going live):** open `.env` and confirm that `MOCK_MODE` is `false` or absent, `API_KEY` is not `change-me`, and `ZIGEX_WEBHOOK_SECRET` is set.

### 30.6 Retrieval evaluation

Judge search quality with numbers, not impressions, every time you change chunk size, the embedding model or the score threshold.

**1. Build a question set** (30 to 50 questions from real interns, or written by supervisors) as a CSV:

```csv
question,department,cohort_id,expected_title
What is gradient descent?,ml,2026-q3,week1_ml_basics.pdf
How do I tune the learning rate?,ml,2026-q3,week2_optimization.md
```

**2. Run `tools/eval_retrieval.py`:**

```powershell
$env:AI_SERVICE_KEY = "your-key"
python tools/eval_retrieval.py eval.csv
```

Example output:

```
MISS: How do I tune the learning rate? -> ['week1_ml_basics.pdf', ...]
hit@5: 41/45 = 91%    MRR: 0.812
```

| Metric | Meaning |
|---|---|
| `hit@5` | Share of questions where the right document appears in the top 5 |
| `MRR` | Average of 1 divided by the rank of the right document. 1.0 means always first |

The script sets `score_threshold` to 0 so the measurement is not hidden by the cut-off. Choose the production threshold separately (Part C, 15.4).

**3. Interpret and act:**

| Result | Next step |
|---|---|
| `hit@5` above about 90% | Good. Record it as the baseline |
| Misses concentrated in one file | Check that file's parsing (scanned? tables?) |
| Misses on broad questions | Increase `chunk_size` |
| Misses on specific facts | Decrease `chunk_size`, or add hybrid search and reranking (Part G) |

Change one thing at a time and re-run on the same question set.

### 30.7 Weekly digest review

During review mode (Part E, step 10 to 12), a staff member checks each digest against this list:

- [ ] Every link opens, and goes to the organiser's real page
- [ ] Deadlines and dates match the page, and none are in the past
- [ ] No opportunity asks for a fee, a deposit or personal documents up front
- [ ] The opportunity is relevant to the segment's department and location
- [ ] Images match the item they sit beside, and nothing is inappropriate
- [ ] Tone is friendly and accurate, with no exaggerated promises
- [ ] The verify-before-applying notice is present

Keep a simple log (week, segment, approved or rejected, reason). Patterns in rejections show which prompt rules or settings to adjust.

---

## 31. Monitoring and logs

### 31.1 Everyday commands

```powershell
docker compose ps                                  # service state
docker compose logs -f api                         # follow one service
docker compose logs --since 1h worker digest-worker
docker compose logs --tail 100 beat
docker stats                                       # CPU and memory per container
docker system df                                   # disk used by Docker
```

### 31.2 What healthy and unhealthy look like

| Service | Healthy | Unhealthy |
|---|---|---|
| `api` | `Application startup complete.` | `Cannot reach Qdrant`, repeated restarts |
| `worker` | `celery@... ready.` then `Task ... succeeded` | `Cannot connect to redis`, no `ready.` line |
| `digest-worker` | `ready.` and `digest.build_segment ... succeeded` | `retry:` lines repeating, `raised unexpected` |
| `beat` | `beat: Starting...` and, on Mondays, `Sending due task weekly-opportunity-digest` | Missing start line, container restarting |
| `qdrant` | `Qdrant HTTP listening on 6333` | Storage or permission errors |
| `redis` | `Ready to accept connections` | Out-of-memory or disk errors |

### 31.3 Health endpoint limits

`GET /health` shows only that the API process is alive. It does **not** check Redis, Qdrant or Gemini. A green health check with a dead Qdrant is possible. Use the smoke test (30.5) for a real check. A deeper `/health/ready` endpoint is on the roadmap.

### 31.4 Watching the queues

Pending jobs sit in Redis lists named after the queue:

```powershell
docker compose exec redis redis-cli llen celery    # waiting ingestion jobs
docker compose exec redis redis-cli llen digest    # waiting digest jobs
```

A number that keeps growing means workers are down or too slow. Ask the workers directly:

```powershell
docker compose exec worker celery -A app.worker.celery_app.celery inspect active
docker compose exec worker celery -A app.worker.celery_app.celery inspect stats
```

### 31.5 Monitoring the weekly run

| Check | How | Alert when |
|---|---|---|
| Did the run start? | `GET /v1/digests/run-status` | `404` after Monday 07:00 |
| Did segments fail? | Same endpoint, `failed` counter | `failed` above 0 |
| Did it finish? | `done + empty + failed == total` | Not finished 1 hour after the start |
| Too many empty digests? | `empty` counter | More than about 20% of segments |
| Was delivery successful? | `GET /v1/digests`, `delivered` field | A `published` digest with `delivered: false` |

`tools/check_weekly_run.py` does these checks and exits with code `0` (healthy), `1` (alert) or `2` (still running):

```powershell
$env:AI_SERVICE_KEY = "your-key"
python tools/check_weekly_run.py
```

Run it on a schedule, for example Monday at 08:00 (two hours after the job), from any scheduler or uptime tool that can alert on a non-zero exit code.

### 31.6 Inspecting stored data

```powershell
# Digests of a week
docker compose exec redis redis-cli smembers digests:2026-W42
docker compose exec redis redis-cli get digest:2026-W42:ml__bamenda

# Run counters and the weekly lock
docker compose exec redis redis-cli hgetall digest_run:2026-W42
docker compose exec redis redis-cli ttl digest_run_lock:2026-W42

# Course vectors: point count
curl.exe http://localhost:6333/collections/course_content
```

The `points_count` in the last response is the total number of chunks stored.

### 31.7 Log rotation

By default Docker keeps container logs without a size limit, so they can fill the disk over months. Add this to each service (or use a YAML anchor) in `docker-compose.yml`:

```yaml
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
```

This is not in the delivered compose file and should be added before production.

### 31.8 Backups

| Data | Method |
|---|---|
| **Qdrant vectors** | Create a snapshot: `curl.exe -X POST http://localhost:6333/collections/course_content/snapshots`. Copy the snapshot file off the server |
| **Redis (digests, status)** | Back up the `redisdata` volume. Append-only persistence is on |
| **Uploaded originals** | Back up the `uploads` volume. These are your source of truth for rebuilding |
| **Rebuild option** | Course vectors can be regenerated by re-uploading originals. This is the fallback if a backup is lost |

Test a restore at least once. An untested backup is only a hope.

### 31.9 Not built yet

Structured logs with a `document_id` on every line, metrics (Prometheus or similar), and an ingestion-complete event are on the roadmap (Part G). Until then, rely on the commands above and the weekly check script.

---

## 32. Troubleshooting

Messages below are the ones met while building the system. Find the symptom, apply the fix.

### 32.1 Docker and build

| Symptom (exact text) | Cause | Fix |
|---|---|---|
| `docker : The term 'docker' is not recognized` | Docker not installed, or terminal opened before install | Install Docker Desktop, then **open a new terminal**. Check `docker --version` |
| `no configuration file provided: not found` | Wrong folder | `cd` into the folder that holds `docker-compose.yml` |
| `ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org')` during `pip install` | Slow or unstable network | Rerun `docker compose build api` (finished layers are cached). The Dockerfile already sets a long timeout and retries. Use a steadier connection if it keeps failing |
| Build downloads dozens of unrelated packages (huggingface, networkx, and so on) | `requirements.txt` is a full `pip freeze` from a Windows environment | Replace it with the short list in the project. Never use a Windows `pip freeze` for Docker |
| `failed to resolve reference "docker.io/library/rag-ingest:latest"` | The worker tried to pull an image that has not been built | Run `docker compose build api` first, then `docker compose up` |
| `failed to solve ... read-only file system` (writing `metadata_v2.db`) | Docker Desktop's storage went read-only, often after interrupted builds or a full disk | Free disk space. Quit Docker Desktop, run `wsl --shutdown`, reopen it, run `docker builder prune -f`. If it persists, Troubleshoot, then Clean / Purge data |
| `port is already allocated` | Port 8000 or 6333 is in use | `docker ps` and stop leftovers, close local `uvicorn`, `docker stop qdrant redis` |
| Changes to code have no effect | Code is baked into the image | `docker compose up -d --build` |
| Changes to `.env` have no effect | Containers still hold old values | `docker compose up -d` |

### 32.2 Startup and connectivity

| Symptom | Cause | Fix |
|---|---|---|
| `httpx.ConnectError: [WinError 10061]` ... `qdrant_client` at API startup | Qdrant is not running or not reachable | Start Qdrant. In Docker, wait for the startup retry loop. Locally, run the Qdrant container |
| `Error 10061 connecting to localhost:6379` (Celery) | Redis not running | Start Redis (`docker start redis`) |
| `Failed to obtain server version. Unable to check client-server compatibility` | Qdrant unreachable at that moment (the code now skips the version check) | Make sure Qdrant is up. Safe to ignore once it connects |
| `ValueError: not enough values to unpack (expected 3, got 0)` on the first task (Windows) | Celery's default pool does not work on Windows | Start the worker with `--pool=solo` (not needed in Docker) |
| `CPendingDeprecationWarning: broker_connection_retry` | Celery setting missing | Already fixed by `broker_connection_retry_on_startup=True`. Rebuild if you still see it |
| `localhost` works in the browser but Python cannot connect (Windows) | `localhost` resolved to IPv6 | Use `127.0.0.1` in `QDRANT_URL` and `REDIS_URL` for local runs |
| Local worker steals jobs from the containers | A local Celery process and Docker both consume the queue | Stop local processes before `docker compose up` |

### 32.3 Authentication

| Symptom | Cause | Fix |
|---|---|---|
| `401 Invalid API key` | The header does not match `API_KEY` | Use the same value. Check what the server loaded: `docker compose exec api python -c "from app.config import settings; print(settings.api_key)"` |
| `502 ... API key not valid` on a digest preview | `GEMINI_API_KEY` or `TAVILY_API_KEY` is wrong | Fix the key and run `docker compose up -d`, or use `MOCK_MODE=true` to test the plumbing |
| `GEMINI_API_KEY is not set` | Missing from `.env` | Set it, then `docker compose up -d` |

### 32.4 Ingestion

| Symptom | Cause | Fix |
|---|---|---|
| Status stays `queued` | Worker not running, or a different worker took the job | `docker compose logs worker`, look for `ready.` |
| `Got a larger chunk overlap (300) than chunk size (100)` | Swagger prefilled the optional chunk fields | Leave `chunk_size` and `chunk_overlap` empty. The API now rejects this with `422` |
| Status shows `queued` **with an old `error`** | Old status fields survived a re-upload (fixed: re-uploads now clear status) | Rebuild with the latest code |
| `No extractable text found (scanned PDF?)` | Image-only PDF | Upload a text-based version, or add OCR (Part G) |
| `429 Too Many Requests` repeating in the worker log | Gemini free-tier quota | Wait. The embedder backs off and the job retries. Upload one document at a time, use a larger `chunk_size`, or enable billing |
| `retrying` state for a long time | Same, with repeated rate limits | Same. A daily quota only resets the next day |
| `Ignoring wrong pointing object ...` | `pypdf` reading a slightly malformed PDF | Harmless. Text is still extracted |
| First ingestion after a rebuild is slow, then fine | The `tiktoken` tokenizer downloads once | Normal. Needs internet on that first run |

### 32.5 Search

| Symptom | Cause | Fix |
|---|---|---|
| `{"hits": []}` for a relevant question | Document not `done`, `department` or `cohort_id` differs from the stored value, or threshold too high | Check status. Compare with stored payloads (Part C, 14.5). Retry with `"score_threshold": 0.0` |
| Query was a filename, for example `notes.pptx` | Filenames are not in chunk text | Ask a question about the content |
| `500` mentioning vector dimensions | Old collection has a different size (for example 384 from the earlier local model) | `curl.exe -X DELETE http://localhost:6333/collections/course_content`, restart the API, re-upload |
| `500` after a fresh Docker start, search finds nothing | The new Qdrant volume is empty | Re-upload documents |
| First search after startup is slow | Client initialization | Normal. Later calls are fast |

### 32.6 Weekly digest

| Symptom | Cause | Fix |
|---|---|---|
| `POST /run` returns `202` but nothing happens | `digest-worker` down, or profiles failed to load | `docker compose logs digest-worker` |
| Every segment `failed` | Cannot reach or authenticate to `ZIGEX_API_URL` | Test with the command in Part E, 24.6. For a Zigex backend on your own machine use `host.docker.internal` |
| Run `skipped` | Lock for this week exists | Use `force=true` |
| Digest `empty` | No valid, current, unseen items | Normal for niche segments. Check `queries` in a preview |
| `student/{id}` returns `404` | Student joined after the last run, digest unpublished, or run not finished | Check `run-status` and the digest's `status` |
| Nothing ran on Monday | `beat` was down at the scheduled time. Missed runs are not replayed | Start `beat`, then trigger `POST /v1/digests/run` |
| Beat triggered twice | More than one `beat` instance | Keep exactly one. The weekly lock normally prevents a double run |

### 32.7 Zigex integration

See Part E, 29.2 (webhook `401` and `413`, only 200 students loaded, duplicates in the UI, wrong segments).

### 32.8 When you are stuck

Collect these before asking for help, in this order:

1. `docker compose ps`
2. `docker compose logs --tail 100` of the failing service
3. The exact error text and the request that caused it
4. Whether it worked before, and what changed since

---

## 33. Cost and rate limits

> Prices and quotas of Gemini and Tavily change. The numbers below are **estimates of usage**, not prices. Check the current limits and prices in Google AI Studio and the Tavily dashboard before budgeting.

### 33.1 Course content (RAG)

**Embedding at upload time**

| Quantity | Formula | Example |
|---|---|---|
| Chunks per document | Depends on length. About 50 to 80 for a 50-slide deck | 80 |
| Embedding requests | `ceil(chunks / 20)` | 4 |
| Tokens embedded | About 250 to 450 per chunk | About 30,000 |

100 documents in a term is therefore roughly 400 requests. This is a **one-time cost per document**. Re-uploads cost again.

**Embedding at question time**

Every intern question is one embedding request (a short query). Estimate: `interns × questions per week`. For example, 300 interns asking 10 questions a week is 3,000 requests a week, or about 430 a day. Free-tier daily request limits can be reached by heavy chat use. Compare this number with your quota.

**Qdrant storage**

A 768-dimension vector is `768 × 4 bytes`, about 3 KB. One hundred thousand chunks is roughly 300 MB of raw vectors, plus the stored text and indexes. A single small server handles this comfortably.

### 33.2 Weekly digest

Assume `S` segments (10 to 25 for 700 students).

| Resource | Per segment | For 25 segments |
|---|---|---|
| Tavily searches (basic) | 4 to 8 | 100 to 200 per week |
| Gemini LLM calls | 2 to 4 | 50 to 100 per week |
| LLM tokens | About 10,000 to 20,000 (the curate prompt carries up to 24 sources) | About 250,000 to 500,000 per week |

If one basic Tavily search costs one credit, 100 to 200 searches a week is roughly 400 to 800 credits a month. Compare this with your Tavily plan.

### 33.3 Rate-limit controls already in the system

| Control | Where | Value |
|---|---|---|
| Embedding batch size and pause | `embedder.py` | 20 chunks per request, 3 seconds apart |
| Retries on 429 and 5xx | `embedder.py`, `llm.py` | Up to 8 and 6 attempts, waits growing to 65 seconds |
| Job-level retries | Celery tasks | Ingestion 3, digest segments 2 |
| Digest pacing | `digest_tasks.py` | 6 segment tasks per minute per `digest-worker` |
| Parallelism | `docker-compose.yml` | 2 processes per worker |

### 33.4 Ways to reduce cost

| Lever | Effect | Trade-off |
|---|---|---|
| Fewer segments (raise `MIN_SEGMENT_SIZE`, or drop location from the key) | Fewer searches and LLM calls | Less local relevance |
| Lower `DIGEST_QUERIES_PER_SEGMENT` (for example 3) | Fewer searches | Less variety |
| `MAX_ROUNDS = 1` | Halves worst-case cost | Fewer second chances for thin segments |
| Lower `MAX_SOURCES` (for example 15) | Shorter LLM prompts | Fewer candidates to choose from |
| A smaller or cheaper Gemini model through `LLM_MODEL` | Lower LLM cost | Possibly weaker curation |
| Bigger `chunk_size` | Fewer chunks and embedding calls | Coarser retrieval |
| Cache embeddings of repeated questions | Fewer query embeddings | Small code addition |
| Skip segments with no change in profile mix | Fewer weekly runs | More logic |

### 33.5 Scaling for throughput

- More ingestion capacity: `docker compose up -d --scale worker=3`
- More digest capacity: `docker compose up -d --scale digest-worker=2` (the 6-per-minute pace applies to each instance)
- **Never scale `beat`.**
- Provider quotas are the real ceiling. More workers cannot exceed the Gemini or Tavily limits, and extra workers only make quota errors more frequent.

---

## 34. Security and privacy

### 34.1 Secrets

| Secret | Stored in | Rules |
|---|---|---|
| `API_KEY` | `.env` on the AI service, secret store on Zigex | Random, at least 32 bytes. Rotate with the procedure in Part E, 23.3 |
| `GEMINI_API_KEY`, `TAVILY_API_KEY` | `.env` | Restrict by project and set usage alerts in each provider's console |
| `ZIGEX_API_TOKEN`, `ZIGEX_WEBHOOK_SECRET` | `.env` | Different values for each. Read-only token scope |

- `.env` is in `.gitignore` and `.dockerignore`. Check `git status` before every push.
- **If a key was ever committed or pasted somewhere public, revoke and replace it.** Deleting it in a later commit does not remove it from git history.
- Do not log keys or full webhook bodies.

### 34.2 Network exposure

| Port | Default in `docker-compose.yml` | Production |
|---|---|---|
| 8000 (API) | Published | Allow only the Zigex backend, behind HTTPS (Caddy or Nginx) |
| 6333 (Qdrant) | Published, **no authentication** | Remove the `ports` entry, or bind to localhost with `"127.0.0.1:6333:6333"` |
| 6379 (Redis) | Not published | Keep it that way |

Qdrant has no login in this setup. Anyone who can reach port 6333 can read or delete every course chunk.

### 34.3 Uploaded files

Existing controls: extension allow-list, 50 MB limit, filename path stripped, containers run as a non-root user.

Recommended additions: virus-scan uploads (for example ClamAV) before parsing, set CPU and memory limits on the worker, and keep the worker without access to anything else (it already has no database credentials).

Document parsers read untrusted files. Keep `pypdf`, `python-docx` and `python-pptx` up to date.

### 34.4 Access control

The single shared key identifies the **Zigex backend**, not a person. This means:

- Any caller with the key can read, replace or delete any document by ID, and read any digest.
- Therefore the key must exist only in the Zigex backend, and all user-level checks (section 23.4 of Part E) must happen there.

Production hardening (Part G): per-user JWTs from Zigex with department and cohort claims, ownership checks in the AI service, and two accepted keys for rotation.

### 34.5 Personal data inventory

| Data | Where | Retention |
|---|---|---|
| Course notes (original files) | `uploads` volume | Until deleted |
| Course chunks and vectors | Qdrant | Until the document is deleted |
| Chunk text sent for embedding | Google (Gemini) | Governed by Google's terms. On a free tier, content may be used to improve Google products. Check the current terms. Use a paid tier for confidential material |
| Student IDs and segment membership | Redis (`segment_students:*`, `student_segment:*`) | 30 days from the last run |
| Digests | Redis, and Zigex database | 120 days in Redis |
| Search query text | Tavily | Governed by Tavily's terms. Contains only department, location and month, no personal data |
| Segment attributes (aggregate skills and interests) | Google (Gemini) | As above. No names or IDs |

The AI service never stores names, emails or phone numbers.

### 34.6 Removing a student's data

```powershell
docker compose exec redis redis-cli get student_segment:s_101           # find the segment
docker compose exec redis redis-cli srem segment_students:ml__bamenda s_101
docker compose exec redis redis-cli del student_segment:s_101
```

The student's ID may also appear in the Zigex tables (`student_digests`), which Zigex must clear itself. Check applicable data-protection law for your country and for your students' countries, and get legal review. This document is not legal advice.

### 34.7 Prompt injection

Two untrusted inputs reach a language model: **uploaded course documents** (through the agent's context) and **web pages** (through the digest).

| Input | Mitigation |
|---|---|
| Course documents | The agent prompt marks context as reference text, not instructions. Only supervisors can upload |
| Web pages | Text is labelled untrusted. The model can only select source and image IDs, so injected text cannot create links. Review mode catches misleading wording |

No prompt is a perfect defense. The structural controls (ID mapping, validation in code, review mode) matter more.

### 34.8 Safety of published content

- **Verify-before-applying notice** on every digest.
- **Review mode** for the first weeks (Part E, step 10 to 12).
- **Image rights:** images are third-party and only credited, not licensed. Decide with Zigex whether to show images, link cards, or host only licensed images.
- **Safe rendering** of Markdown on the Zigex side (Part E, 26.4).

### 34.9 If a bad digest is published

There is currently no "unpublish" endpoint, so remove it in this order:

1. **Zigex:** delete or hide the row in `weekly_digests` (the cascade removes `student_digests`). This is what students see, so do it first.
2. **AI service:** `docker compose exec redis redis-cli del digest:<week>:<segment_id>` and `srem digests:<week> <segment_id>`.
3. **Prevent a repeat:** the bad URLs stay in the segment's `seen:` set only if the digest was published, so they will not reappear for 60 days. If it was a source problem, note it for the prompt rules.
4. **Record** what happened and adjust the prompt or review checklist.

An unpublish endpoint and a domain blocklist are on the roadmap.

### 34.10 Go-live security checklist

- [ ] `API_KEY` is random and not `change-me`
- [ ] `.env` is not in git history
- [ ] `MOCK_MODE` is `false` or absent
- [ ] The AI service is reachable only from the Zigex backend, over HTTPS
- [ ] Qdrant port 6333 is not public
- [ ] Webhook secret is set and the receiver verifies signatures
- [ ] Google and Tavily keys have usage alerts
- [ ] Log rotation is configured (31.7)
- [ ] A backup and a restore have been tested (31.8)
- [ ] Review mode is on for the first digests
- [ ] The Zigex frontend renders digest Markdown safely

---

## Part F checklist

You have completed Part F when:

- [ ] `pytest` reports 20 passed
- [ ] The smoke test (30.5) passes on the deployed system
- [ ] A retrieval baseline (`hit@5`) is recorded from a real question set
- [ ] `tools/check_weekly_run.py` is scheduled and has alerted correctly on a deliberate failure
- [ ] Log rotation is on, and a backup restore has been tested
- [ ] You can name the daily and monthly limits of your Gemini and Tavily plans and compare them with section 33
- [ ] The go-live security checklist (34.10) is complete

**Next: Part G, Deployment and handoff** (sections 35 to 37) and the appendices.
