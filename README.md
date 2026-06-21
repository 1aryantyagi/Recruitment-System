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
npm run dev                                    # http://localhost:3000
```

**Dev logins (seeded):**


| Email                               | Password   | Role             |
| ----------------------------------- | ---------- | ---------------- |
| `admin@local.dev`                   | `admin123` | ADMIN            |
| `hr@local.dev`                      | `hr123`    | HR               |
| `dm@local.dev`                      | `dm123`    | DELIVERY_MANAGER |
| `alice@local.dev` / `bob@local.dev` | `int123`   | interviewers     |


## Environment variables


| Group      | Variables                                                                                                                                                                                 |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| App        | `APP_ENV`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `BACKEND_BASE_URL`, `FRONTEND_BASE_URL`                                                                                           |
| Encryption | `ENCRYPTION_KEY` (AES-256-GCM for `phone` / `current_ctc` / `expected_ctc`)                                                                                                               |
| Thresholds | `RESUME_SCORE_THRESHOLD`, `CALL_SCORE_THRESHOLD`, `GMAIL_POLL_INTERVAL_MINUTES`                                                                                                           |
| Database   | `POSTGRES_HOST`, `POSTGRES_PORT` (5434), `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`                                                                                              |
| LLM        | `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (Anthropic wins if set)                                                                                          |
| Gmail      | `GOOGLE_SERVICE_ACCOUNT_JSON`, `GMAIL_IMPERSONATE_EMAIL` (Path A); `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (Path B); `GOOGLE_REFRESH_TOKEN` (legacy) — see [Gmail setup](#gmail-setup) |
| MS Graph   | `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`                                                                                                                                        |
| Twilio     | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`                                                                                                                          |
| Deepgram   | `DEEPGRAM_API_KEY`                                                                                                                                                                        |


**Graceful degradation:** every external integration is optional. With no LLM
key, extraction/analysis return clearly-labeled stubs; with no Twilio/Deepgram/
Gmail/MS keys, those steps are skipped/mocked — the pipeline always completes.

> **Twilio note:** real outbound calls require a publicly reachable webhook URL.
> For local testing, expose `:8000` with ngrok and set `BACKEND_BASE_URL` to the
> public URL (or `NGROK_ENABLED=true`). Without it, screening runs in mock mode.

## Gmail setup

The 5-minute Gmail poll auto-ingests resume attachments. Auth is resolved in
this order: **service account → DB-stored OAuth token → legacy `.env` refresh
token**. Access tokens refresh automatically in-process; you never paste a
short-lived token. Pick one path:

### Path B — OAuth "Connect Gmail" (personal / non-Workspace Gmail) — recommended here

1. In the [Google Cloud Console](https://console.cloud.google.com/), enable the
  **Gmail API** and create an **OAuth 2.0 Client ID** of type **Web application**.
2. Add the authorized redirect URI: `${BACKEND_BASE_URL}/integrations/gmail/callback`
  (e.g. `http://localhost:8000/integrations/gmail/callback`).
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.
4. **Publish the OAuth consent screen to Production** (OAuth consent screen →
  "Publish app"). ⚠️ While the app stays in *Testing* mode, Google expires the
   refresh token every **7 days** regardless of our code — that 7-day expiry is
   the original cause of the `invalid_grant` errors. Publishing removes it.
5. Start the app, sign in as an **Admin**, go to **Admin → Integrations →
  Connect Gmail**, and complete Google consent. The refresh token is stored
   **encrypted in Postgres** (`integration_credentials`). Polling now works
   across restarts with no token in `.env`.

If the token is ever revoked/expired, polling auto-disables (it stops retrying
and logging every minute) and the Integrations card shows **Needs reconnect** —
click **Connect Gmail** again to fix it.

### Path A — Google Workspace service account (most durable; no refresh token)

For a Workspace domain only (cannot impersonate a personal `@gmail.com`):

1. Create a **service account** and download its JSON key.
2. In the Google Workspace **Admin console → Security → API controls →
  Domain-wide delegation**, authorize the service account's client ID for scope
   `https://www.googleapis.com/auth/gmail.modify`.
3. Set `GOOGLE_SERVICE_ACCOUNT_JSON` (path to the key file or inline JSON) and
  `GMAIL_IMPERSONATE_EMAIL` (the mailbox to read, e.g. `resumes@company.com`).

> **Do not commit secrets:** `.env` and any service-account JSON must stay out of
> version control. Stored OAuth tokens are encrypted at rest with `ENCRYPTION_KEY`.

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

