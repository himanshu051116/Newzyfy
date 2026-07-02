# News Intelligence Platform

An event-centric news intelligence system with recall-optimized global acquisition, primary-source trace-back, historical context, claim-level verification, propagation analysis, geographic intelligence, knowledge-graph exploration, and evidence-backed assessments, briefings, and research.

This repository now contains the first production-oriented backend slices: acquisition
setup, discovery polling, frontier admission, article fetching, article extraction,
article versioning, and read APIs for ingested articles/events.

## Design documents

- [System architecture](docs/ARCHITECTURE.md)
- [Event-centric intelligence architecture](docs/EVENT_INTELLIGENCE_ARCHITECTURE.md)
- [Recall-optimized acquisition architecture](docs/ACQUISITION_ARCHITECTURE.md)
- [Implementation roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Critical implementation guardrails](docs/IMPLEMENTATION_GUARDRAILS.md)
- [Zero-cost local AI strategy](docs/LOCAL_AI_STRATEGY.md)
- [Module synchronization contract](docs/MODULE_SYNCHRONIZATION.md)

## Proposed stack

- Python 3.12+ and FastAPI
- PostgreSQL for canonical structured data
- PostGIS for geographic intelligence
- Qdrant for dense and sparse retrieval
- S3-compatible object storage for raw and extracted artifacts
- Redis for caching, rate limits, and lightweight coordination
- Kafka-compatible event streaming in the production topology
- Next.js and TypeScript for the dashboard
- Optional Neo4j projection when measured multi-hop graph workloads justify it

The implementation begins as a modular monolith with independently scalable API and worker processes. Service boundaries are explicit so high-load components can be separated later without rewriting the domain model.

## Current implementation

Phase 1 development has started. The repository currently contains:

- a FastAPI application with liveness and database-readiness endpoints;
- PostgreSQL/PostGIS persistence models and the initial Alembic migration;
- RSS, Atom, XML sitemap, and Google News sitemap parsing;
- WebSub hub discovery;
- an SSRF-aware bounded HTTP fetcher with conditional request support;
- publisher-aware URL canonicalization and fingerprints;
- listing-page link-set change detection;
- auditable distributed-frontier priority calculations;
- provisional/candidate/confirmed event-assignment policy;
- transactional publisher/channel/discovery orchestration;
- versioned integration-event envelopes, transactional outbox, and consumer inbox;
- idempotent cross-channel discovery synchronization;
- lease-based asynchronous RSS/Atom/sitemap polling;
- conditional requests, `304 Not Modified` handling, adaptive scheduling, and failure backoff;
- persisted poll-run metrics and automatic sitemap-index expansion;
- a separate article-processing worker that leases URL candidates from the frontier;
- real HTML article extraction using JSON-LD, OpenGraph/canonical metadata, and
  conservative visible-text heuristics;
- immutable article versions with extraction method, warnings, content hash,
  fetch-run provenance, and redirect metadata;
- deterministic event matching that compares incoming articles against recent event
  records using title/text overlap, entity/identifier overlap, temporal compatibility,
  and geographic hints;
- existing-event linking, provisional new-event creation, and stored assignment
  feature scores for newly ingested articles;
- article fetch-run audit records and retry/terminal-failure tracking;
- deterministic claim extraction from exact stored article sentences;
- claim/evidence/verification lineage tables with origin evidence links;
- initial `not_checkable` claim verification records when independent evidence has
  not yet been retrieved, with reasoning traces and confidence-factor placeholders
  stored transparently rather than invented;
- homepage-based publisher onboarding that discovers RSS/Atom feeds from HTML
  `<link rel="alternate">`, sitemap declarations from `robots.txt`, common feed and
  sitemap paths, and optional manual fallback endpoints;
- fetch job records and fetch scheduling endpoints that queue discovery work for the
  poller instead of doing extraction inside HTTP requests;
- a local `/news-sources` dashboard for adding sources, fetching one/all publishers,
  polling fetch progress, viewing source health, and visually browsing extracted
  article cards;
- recent-news URL filtering before frontier admission: by default only article-like
  URLs with publication timestamps from the last 48 hours are admitted, with
  categories, tags, videos, archives, feeds, media files, and other non-article paths
  rejected;
- per-channel poll cap for newly admitted URLs, defaulting to 200, tunable through
  `NEWSINTEL_MAX_NEW_URLS_PER_CHANNEL_POLL`;
- read APIs for article lists, article details, and event details;
- unit and API integration tests;
- a local zero-cost service topology for PostgreSQL/PostGIS, Redis, Qdrant, and MinIO.

No AI endpoint or fabricated analysis is present. Model-backed features remain disabled until a real local model and evidence pipeline are implemented and evaluated.

## Development setup

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
.\scripts\services.ps1 init
.\scripts\test.ps1
```

Run the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn newsintel.main:app --app-dir backend/src
```

The liveness endpoint is `GET http://127.0.0.1:8000/api/v1/health/live`.
Swagger UI is available at `http://127.0.0.1:8000/docs`.

Useful local service commands:

```powershell
.\scripts\services.ps1 status
.\scripts\services.ps1 logs
.\scripts\services.ps1 migrate
.\scripts\services.ps1 doctor
.\scripts\services.ps1 down
```

Start the full local platform with one command:

```powershell
.\scripts\run-platform.ps1 start
```

Check or stop those local processes:

```powershell
.\scripts\run-platform.ps1 status
.\scripts\run-platform.ps1 stop
```

The dashboard is available at:

```text
http://127.0.0.1:8000/news-sources
```

## Run it like a normal Windows app

After the first setup, you do not need to keep typing terminal commands.

Portable launchers are included in the project folder:

- `Start-News-Intelligence.vbs` starts Docker if needed, starts the API, poller,
  and article worker, then opens the News Sources dashboard.
- `Open-News-Dashboard.vbs` opens the dashboard.
- `Stop-News-Intelligence.vbs` stops the local app services and Docker Compose
  infrastructure without deleting stored data.

For Desktop icons, run this once from PowerShell:

```powershell
.\scripts\install-windows-shortcuts.ps1
```

This creates:

- **News Intelligence - Start**
- **News Intelligence - Stop**
- **News Intelligence - Dashboard**
- **News Intelligence - Status**

The first start may take a little longer because Docker Desktop, PostgreSQL,
Redis, Qdrant, MinIO, migrations, the API, and workers all need to become ready.
Launcher logs are written to:

```text
.run/logs/desktop-launcher.log
```

Recent article filtering can be tuned with:

```env
NEWSINTEL_RECENT_ARTICLE_WINDOW_HOURS=48
NEWSINTEL_MAX_NEW_URLS_PER_CHANNEL_POLL=200
```

### Try the synchronized acquisition workflow

Start PostgreSQL through Compose, run the migrations, launch the API, and open:

```text
http://127.0.0.1:8000/docs
```

Click **Authorize** and enter the development token:

```text
dev-internal-token
```

Then call these endpoints in order:

1. Preferred: `POST /api/v1/publishers/discover` with publisher name and homepage URL
2. Fallback/manual mode: `POST /api/v1/admin/publishers`
3. Fallback/manual mode: `POST /api/v1/admin/discovery-channels`
4. `POST /api/v1/publishers/{publisher_id}/fetch` to schedule one publisher
5. `POST /api/v1/fetch/all` to schedule all publishers
6. `GET /api/v1/fetch-jobs/{job_id}` to poll fetch progress
7. `POST /api/v1/internal/discoveries` for collector integrations that push discoveries directly

The final request canonicalizes the URL, deduplicates it against the frontier, records channel provenance, calculates priority, and writes versioned outbox events in the same transaction.

### Run the workers

In a second PowerShell terminal, run the discovery poller:

```powershell
cd C:\Users\LENOVO\Documents\news
.\.venv\Scripts\python.exe -m newsintel.doctor
.\.venv\Scripts\python.exe -m newsintel.workers.poller
```

The worker leases due channels safely across multiple processes, uses conditional HTTP requests, parses feeds and sitemaps, records channel provenance, admits new URLs to the frontier, adapts polling intervals, and persists poll runs and failures.

In a third PowerShell terminal, run the article worker:

```powershell
cd C:\Users\LENOVO\Documents\news
.\.venv\Scripts\python.exe -m newsintel.workers.articles
```

The article worker leases URL candidates, fetches the article URL, extracts clean
article text and metadata, stores immutable article versions, creates a provisional
event for new articles or links the article to an existing event, extracts factual
claim candidates from exact article sentences, creates origin evidence links, writes
initial `not_checkable` verification records when evidence is insufficient, and emits
outbox events.

Useful read endpoints:

```text
GET /api/v1/publishers
POST /api/v1/publishers/discover
POST /api/v1/publishers/{publisher_id}/fetch
POST /api/v1/fetch/all
GET /api/v1/fetch-jobs/{job_id}
GET /api/v1/articles
GET /api/v1/articles/{article_id}
GET /api/v1/articles/{article_id}/claims
GET /api/v1/events/{event_id}
```

If the doctor reports that PostgreSQL is unreachable, install a free local database option first:

```powershell
# After installing Docker Desktop:
.\scripts\services.ps1 init
```

The poller now remains alive and retries with bounded exponential backoff if PostgreSQL temporarily becomes unavailable.

Docker Compose is provided for local infrastructure, but Docker must be installed separately.
If your terminal cannot find `docker`, use the helper script because it detects Docker
Desktop's standard Windows install path automatically:

```powershell
.\scripts\services.ps1 init
```
