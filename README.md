# NOA AI

**Floorplan-to-3D Architectural Intelligence Platform.**  
Technical Blueprint v1.1 — Phase 0 + Phase 1 + Phase 2 implemented.

## Quick start

```bash
# Dependencies
npm ci
pip install -e packages/contracts/python
pip install -e "apps/api[dev]"

# Start Postgres, Redis, Qdrant, LocalStack
docker compose up -d

# Run migrations (includes dev user seed)
export DATABASE_URL=postgresql://noa:noa@localhost:5433/noa
alembic -c db/alembic.ini upgrade head

# API (creates S3 bucket on startup)
cd apps/api && uvicorn noa_api.main:app --reload

# Worker (for PDF→PNG rasterization; requires poppler: brew install poppler)
cd apps/api && arq noa_api.worker.WorkerSettings

# Web
npm run dev
```

**Phase 1 demo:** Create project → upload PDF/image → watch progress via SSE.
**Phase 2 demo:** Upload floorplan → AI parses walls/rooms/openings → visualize parsed plan → upload inspiration images.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://noa:noa@localhost:5433/noa` | Postgres connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis for ARQ |
| `S3_ENDPOINT_URL` | — | LocalStack: `http://localhost:4566` |
| `S3_BUCKET_ASSETS` | `noa-assets` | S3 bucket (created on API startup) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API base URL for web |
| `OPENAI_API_KEY` | — | **Required for Phase 2** floorplan parsing |
| `OPENAI_VISION_MODEL` | `gpt-4o` | Vision model for floorplan analysis |

## Repo structure

- **apps/web** — Next.js 14 frontend (upload UI, SSE status)
- **apps/api** — FastAPI gateway, project CRUD, floorplan upload, SSE, ARQ worker
- **packages/contracts/v1** — 16 canonical TypeScript contracts
- **packages/contracts/python** — Pydantic v2 equivalents (snapshot-tested)
- **packages/ui** — Shared React components
- **packages/config** — Shared TS/ESLint config
- **services/** — floorplan-worker, inspiration-worker, geometry-worker, etc. (stubbed)
- **db/migrations** — Alembic 0001–0008 (full schema + dev user seed)
- **scripts/** — dev_setup.py, download_models.py, smoke_test.py
- **infrastructure/** — Placeholder

## Deliverables

### Phase 0 + Phase 1
- [x] Monorepo, all service directories scaffolded
- [x] All 16 contracts, Alembic migrations 0001–0008
- [x] Redis + ARQ, FastAPI skeleton, JWT stub
- [x] **S3 integration** (boto3 → LocalStack)
- [x] **Postgres + SQLAlchemy** (project/floorplan_asset CRUD)
- [x] **POST /v1/projects/:id/floorplan** multipart upload → FloorplanAsset
- [x] **GET /v1/projects/:id/status** SSE with Last-Event-ID replay
- [x] **project_events** writer for SSE
- [x] **PDF→PNG rasterizer** ARQ job (pdf2image)
- [x] **Upload UI** drag-drop, progress bar, SSE connection

### Phase 2 — Floorplan Parsing + Inspiration
- [x] **AI floorplan parser** (GPT-4o Vision → walls, rooms, openings, confidence)
- [x] **POST /v1/projects/:id/parse** trigger AI parsing (auto-triggered after upload)
- [x] **GET /v1/projects/:id/parsed-plan** fetch ParsedPlan results
- [x] **ParsedPlan** SQLAlchemy model + canvas visualization in UI
- [x] **Inspiration Boards** — CRUD endpoints + image upload to S3
- [x] **Inspiration UI** — board tabs, image grid, upload button

## Tests

- **Contracts (Python):** `pytest packages/contracts/python/tests -v`
- **API:** `pytest apps/api/tests -v` (skip `test_arq_roundtrip` if no Redis)
- **Migration smoke:** `DATABASE_URL=... alembic -c db/alembic.ini upgrade head`

## Blueprint

See the consolidated technical blueprint (v1.0 + Amendment v1.1) for full contracts, DB schema, pipeline stages, and phased roadmap. Project name: **NOA** (not archform).
