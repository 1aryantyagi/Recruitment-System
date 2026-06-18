# Recruitment Platform (ATS) — Multi-Agent AI

An internal Applicant Tracking System that automates the hiring pipeline end to
end: **resume intake → AI skill extraction → per-requisition scoring → AI
telephonic screening → interview scheduling → AI interview analysis → feedback
collection → analytics**.

Built **from the specifications** in `[product-req.md](./product-req.md)` and
`[technical-requirements.md](./technical-requirements.md)`. The seven pipeline
stages are implemented as **LangGraph agents** running inside a single
**FastAPI** service, with a **Next.js** frontend.

> **Stack note.** The TRD mandates a Node/LangGraph/Drizzle/Inngest/Claude
> stack on Supabase. Per the chosen build configuration this implementation uses
> **Python (FastAPI) + LangGraph + LangChain + SQLAlchemy + APScheduler**, runs
> on **local Docker Postgres** with **local-disk storage** and **JWT auth**, and
> is **provider-agnostic** for the LLM (OpenAI by default, swappable to Claude by
> setting `ANTHROPIC_API_KEY`). Every functional requirement, the 19-table data
> model, the API surface, and the 13 design principles are preserved.

## Architecture

```
backend/app/
├── agents/          # 7 LangGraph StateGraphs (the pipeline)
│   ├── resume_intake.py          # 1. file → text → LLM extract → normalize → dedup/version → persist
│   ├── resume_scoring.py         # 2. deterministic 5-dimension match score (per requisition)
│   ├── telephonic_screening.py   # 3. Twilio call + STT + LLM Q&A evaluation (start + webhook)
│   ├── interview_scheduling.py   # 4. create round + MS Graph / Teams invite
│   ├── interview_analysis.py     # 5. STT + LLM structured analysis (async, 202)
│   ├── feedback_collection.py    # 6. interviewer notification + human feedback upsert
│   └── analytics.py              # 7. funnel / sources / time-to-hire aggregations
├── api/routes/      # REST endpoints (Swagger at /docs)
├── core/            # auth+RBAC, AES-256-GCM encryption, response envelope, errors, events, logging
├── llm/             # provider-agnostic LangChain client (OpenAI ⇄ Anthropic) + structured output
├── integrations/    # storage(local) / gmail / twilio / stt(deepgram|whisper) / ms_graph
├── models/          # SQLAlchemy: all 19 tables, enums, tsvector FTS, encrypted columns
├── schemas/         # Pydantic request + LLM structured-output schemas
├── services/        # scheduler (APScheduler 5-min Gmail poll) + flow (async background work)
└── utils/           # PDF/DOCX parsing

frontend/            # Next.js 15 + TypeScript + Tailwind + recharts
```

## Pipeline flow

1. **Resume Intake** — `POST /candidates` (or the 5-min Gmail poll) stores the
  file, extracts text (PDF/DOCX), runs an LLM to pull structured profile +
   skills, normalizes skills against the alias dictionary, dedupes by email,
   versions resumes (max 3), and returns extracted skills for HR confirmation.
2. **Resume Scoring** — deterministic 0–1 match score per open requisition
  (skills 40% / experience 20% / skill-depth 20% / location 10% / notice 10%).
3. **Telephonic Screening** — `POST /screening/start-call` places a Twilio call;
  the webhook drives status; the recording is transcribed and the answers are
   evaluated by an LLM.
4. **Interview Scheduling** — `POST /interviews` creates a round and a Teams
  meeting (MS Graph).
5. **Interview Analysis** — `POST /interviews/{id}/recording` returns **202** and
  runs transcription + structured LLM analysis on the background Flow layer.
6. **Feedback Collection** — auto-notifies the interviewer; `POST
  /interviews/{id}/feedback` records human ratings alongside the AI analysis.
7. **Analytics** — `GET /analytics/dashboard` powers funnel, source
  effectiveness, time-to-hire, and open-requisition health.

## Quick start (local dev)

**Prereqs:** Python 3.12+, Node 20–24 LTS (see `.nvmrc`; avoid Node 25+ for the
Next.js dev server), Docker.

```bash
cp .env.example .env        # then fill in keys (OpenAI etc.) — see table below
                            # ENCRYPTION_KEY: python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

# 1. Database (host port 5434 to avoid clashing with other local Postgres)
docker compose up -d db

# 2. Backend
cd backend
python3 -m venv .venv 
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload --port 8000      # Swagger: http://localhost:8000/docs

# 3. Frontend
cd ../frontend
npm install
cp .env.local.example .env.local               # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                                     # http://localhost:3000
```

**Dev logins (seeded):**


| Email                               | Password   | Role             |
| ----------------------------------- | ---------- | ---------------- |
| `admin@local.dev`                   | `admin123` | ADMIN            |
| `hr@local.dev`                      | `hr123`    | HR               |
| `dm@local.dev`                      | `dm123`    | DELIVERY_MANAGER |
| `alice@local.dev` / `bob@local.dev` | `int123`   | interviewers     |


## Environment variables


| Group      | Variables                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------------ |
| App        | `APP_ENV`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `BACKEND_BASE_URL`, `FRONTEND_BASE_URL`  |
| Encryption | `ENCRYPTION_KEY` (AES-256-GCM for `phone` / `current_ctc` / `expected_ctc`)                      |
| Thresholds | `RESUME_SCORE_THRESHOLD`, `CALL_SCORE_THRESHOLD`, `GMAIL_POLL_INTERVAL_MINUTES`                  |
| Database   | `POSTGRES_HOST`, `POSTGRES_PORT` (5434), `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`     |
| LLM        | `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (Anthropic wins if set) |
| Gmail      | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`                               |
| MS Graph   | `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`                                               |
| Twilio     | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`                                 |
| Deepgram   | `DEEPGRAM_API_KEY`                                                                               |


**Graceful degradation:** every external integration is optional. With no LLM
key, extraction/analysis return clearly-labeled stubs; with no Twilio/Deepgram/
Gmail/MS keys, those steps are skipped/mocked — the pipeline always completes.

> **Twilio note:** real outbound calls require a publicly reachable webhook URL.
> For local testing, expose `:8000` with ngrok and set `BACKEND_BASE_URL` to the
> public URL (or `NGROK_ENABLED=true`). Without it, screening runs in mock mode.

## Tests

```bash
cd backend
python -m pytest                 # unit + API integration (DB must be up + seeded)
python -m scripts.smoke_test     # full end-to-end against a running server on :8000
```

## Security highlights

- JWT auth on every route except the signed Twilio webhook; RBAC enforced before
business logic.
- `phone`, `current_ctc`, `expected_ctc` encrypted at rest; excluded from list
responses, decrypted only in the single-profile view.
- Twilio webhook signature verification.
- Resume/transcript text is treated as data, never injected into LLM
instructions.
- Append-only `audit_logs` (accountability) and `analytics_events` (reporting).

## Deployment

- **Backend:** `backend/Dockerfile` (migrate + seed + uvicorn). `docker compose up` runs Postgres + backend together.
- **Frontend:** Vercel/Node host; set `NEXT_PUBLIC_API_URL`.
- **Production swaps:** point `POSTGRES_`* at managed Postgres (or Supabase),
swap local-disk storage for object storage, set `ANTHROPIC_API_KEY` to use
Claude, and front the service with Nginx + ngrok/public URL for webhooks.

