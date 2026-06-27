# Technical Requirements Document — Recruitment Platform (ATS)

> **Source of truth:** This document is the technical requirements specification (TRD) derived from `product-req.md`. It preserves **every** functional requirement, design principle, data structure, API, and rule from the product document and re-states them as buildable technical requirements.
>
> **Architectural mandate:** Per the engineering directive, the runtime is **Node.js**, **all seven agents are implemented as LangGraph (LangGraph.js) agents**, the data layer is the **Datagraph** layer, and asynchronous / scheduled orchestration runs on the **Flow** layer. The original product document described a Python/FastAPI/Supabase implementation; this TRD ports the implementation surface to the mandated Node.js + LangGraph stack while keeping the data model, behavior, and guarantees identical.

| Field | Value |
| ----- | ----- |
| Document type | Technical Requirements Document (TRD) |
| Derived from | `product-req.md` (Recruitment Platform / internal ATS) |
| Runtime | Node.js 22 LTS (TypeScript, strict mode) |
| Agent framework | LangGraph.js (`@langchain/langgraph`) |
| Data layer | Datagraph (typed data-access + relationship graph over PostgreSQL) |
| Orchestration layer | Flow (durable async + scheduled workflows) |
| Status | Draft v1.0 |
| Date | 2026-06-17 |

---

## 0. Terminology Mapping & Interpretation Notes

The directive named four mandatory stack pillars: **Node.js, LangGraph, Datagraph, Flow.** Two of these (Datagraph, Flow) are not single named OSS products, so this TRD fixes a precise, buildable definition for each and recommends the concrete best-in-class tools that realize them. These definitions are normative for the rest of the document.

| Pillar | Definition in this TRD | Recommended concrete tool(s) |
| ------ | ---------------------- | ---------------------------- |
| **Node.js** | The single backend runtime. All API handlers, agents, schedulers, and background work run inside one Node.js service (mirrors the original "single FastAPI service" constraint). | Node.js 22 LTS, TypeScript 5.x, **NestJS** (structured DI/modules) or **Fastify** (minimal, high-throughput). This TRD assumes **NestJS** as the API framework. |
| **LangGraph** | The agent orchestration framework. Each of the 7 agents (§7) is a `StateGraph` with explicit state, nodes, edges, tools, and checkpointing. | `@langchain/langgraph`, `@langchain/core`, `@langchain/anthropic` (LLM), plus LangGraph **checkpointers** for durable agent state. |
| **Datagraph** | The data-access + relationship layer. It owns all reads/writes to PostgreSQL, full-text search, the typed schema, the migration system, and the candidate ↔ skill ↔ requisition relationship graph used for scoring/matching. | **Drizzle ORM** (typed SQL + migrations) over **Supabase PostgreSQL**; `pgvector` reserved for future semantic search; the "graph" view is materialized through normalized join tables + recursive SQL. |
| **Flow** | The asynchronous + scheduled orchestration layer. It runs work that must not block the HTTP response (transcription, AI analysis, notifications) and runs the every-5-minute Gmail poll. Replaces FastAPI `BackgroundTasks` + `APScheduler`. | **Inngest** (durable, retryable, step-based flows + cron) — recommended; **BullMQ** (Redis-backed queues) + **node-cron** is the lighter-weight alternative. This TRD assumes **Inngest**. |

> Where a requirement in the source document referenced a Python-specific tool (`pdfminer`, `python-docx`, FastAPI `BackgroundTasks`, APScheduler, the Supabase **Python** SDK), this TRD substitutes the Node.js equivalent and records it in the tool tables. The **behavioral requirement is unchanged**; only the implementing library differs.

---

## 1. Purpose & Scope

This platform is an **internal Applicant Tracking System (ATS)** used exclusively by HR team members and Delivery Managers. **Candidates have no direct access** to the system — they exist only as data records.

### 1.1 Resume Intake Channels (REQ-SCOPE-1)
Resumes enter the system through three channels:

1. **Manual upload** by HR via the HR Dashboard (single or batch).
2. **Automatic ingestion** from a monitored Gmail inbox, polled **every 5 minutes**.
3. **Future scope:** direct API integrations with LinkedIn, Naukri, and other portals.

### 1.2 Lifecycle Coverage (REQ-SCOPE-2)
The system manages the **complete hiring lifecycle**:
- Resume intake and skill extraction
- Job opening (requisition) management
- Candidate scoring and ranking (per-requisition)
- Telephonic screening
- Interview scheduling
- AI-assisted interview analysis
- Feedback collection
- Analytics reporting

### 1.3 Out of Scope (current release)
- Candidate-facing endpoints / portal.
- Direct LinkedIn/Naukri API ingestion.
- Offer-letter generation, e-signature, WhatsApp notifications.
- Semantic vector search (reserved via `pgvector`).
- Separate search cluster (Elasticsearch) — Postgres FTS used instead.

---

## 2. Users & Roles

Three system roles plus the non-system Candidate record. Role is a JWT claim, enforced at the route level (§4.8).

| Role | Permissions |
| ---- | ----------- |
| **HR** | Upload resumes, confirm extracted skills, create job openings, initiate screening calls, schedule interviews, submit feedback, view analytics. |
| **Delivery Manager (DM)** | Create job openings, view & search candidates, view scored rankings, view interview feedback, view analytics. |
| **Admin** | Manage user accounts, manage skills master list, manage domains & departments, view audit logs. |
| **Candidate** | **No system access.** Represented as data records only. |

Role enum values (used in code and DB): `HR | DELIVERY_MANAGER | ADMIN`.

---

## 3. System Architecture Overview

The platform is a **lightweight, single-service backend** on Node.js, deployed on a single VM, with all persistence handled by Supabase (managed PostgreSQL + file storage). No message-queue broker is mandatory at current scale; **Flow** provides durable async/scheduled execution. There is no separate search cluster and no managed services beyond Supabase, Twilio, the LLM provider, and a transcription provider.

### 3.1 Component → Technology Map (REQ-ARCH-1)

| Component | Original (product-req) | This TRD (Node.js stack) | Notes |
| --------- | ---------------------- | ------------------------- | ----- |
| Backend API | FastAPI + Uvicorn | **Node.js 22 + NestJS** (HTTP via the built-in cluster / PM2 workers) | Single service hosting API + agents + Flow workers. |
| Reverse Proxy | Nginx | **Nginx** (unchanged) | TLS termination, static, buffering, connection limits. |
| Database | Supabase PostgreSQL | **Supabase PostgreSQL** (unchanged) | Accessed only through the **Datagraph** layer (Drizzle ORM). |
| File Storage | Supabase Storage | **Supabase Storage** (unchanged) | Accessed via `@supabase/supabase-js` (Node SDK). Pre-signed URLs. |
| Authentication | Supabase Auth (JWT) | **Supabase Auth** (JWT, role claim) | JWT verified in Node middleware using the Supabase JWT secret / JWKS. |
| Full-Text Search | Postgres `tsvector` | **Postgres `tsvector`** (unchanged) | GIN index; `plainto_tsquery` + `ts_rank`. |
| Skill Extraction | LLM (OpenAI) + dictionary | **LLM via LangGraph agent (Claude)** + dictionary normalization | See §3.5 for model choice. |
| Telephonic Screening | Twilio | **Twilio** (`twilio` Node SDK) | TwiML, recordings, signed webhooks. |
| Transcription | OpenAI Whisper API | **Speech-to-text provider** (Whisper API, or Deepgram / AssemblyAI) | Claude does not transcribe audio — a dedicated STT service is required. See §3.5. |
| Scheduled Jobs | APScheduler (in-process) | **Flow** (Inngest cron, or `node-cron` + BullMQ) | Every-5-min Gmail poll; runs inside/alongside the Node process. |
| Async post-response work | FastAPI `BackgroundTasks` | **Flow** (Inngest steps) | Durable, retryable, observable (vs. fire-and-forget). |
| Hosting | Single VM (2–4 core) | **Single VM** (Hetzner / Railway / Render) | Unchanged. |

### 3.2 Logical Layering

```
                ┌──────────────────────────────────────────────────────┐
   HTTPS ─────► │ Nginx (TLS, proxy, buffering)                          │
                └───────────────────────────┬──────────────────────────┘
                                            ▼
                ┌──────────────────────────────────────────────────────┐
                │ Node.js service (NestJS)                               │
                │                                                        │
                │  ┌───────────────┐   ┌─────────────────────────────┐   │
                │  │ HTTP layer    │   │ Flow layer (Inngest)         │   │
                │  │ - routes      │   │ - async post-response work   │   │
                │  │ - RBAC guard  │   │ - 5-min Gmail poll (cron)    │   │
                │  │ - validation  │   │ - durable retries            │   │
                │  └──────┬────────┘   └───────────┬─────────────────┘   │
                │         │                        │                     │
                │         ▼                        ▼                     │
                │  ┌──────────────────────────────────────────────┐     │
                │  │ Agents (LangGraph StateGraphs)  — §7           │     │
                │  │ Agent1 Intake · Agent2 Scoring · Agent3 Screen │     │
                │  │ Agent4 Schedule · Agent5 Analysis · Agent6 FB  │     │
                │  │ Agent7 Analytics                               │     │
                │  └──────────────────────┬───────────────────────┘     │
                │                         ▼                              │
                │  ┌──────────────────────────────────────────────┐     │
                │  │ Datagraph layer (Drizzle ORM + FTS + graph)    │     │
                │  └──────────────────────┬───────────────────────┘     │
                └─────────────────────────┼──────────────────────────────┘
                                          ▼
        ┌─────────────────────┐  ┌────────────────────┐  ┌──────────────┐
        │ Supabase Postgres   │  │ Supabase Storage    │  │ Supabase Auth │
        └─────────────────────┘  └────────────────────┘  └──────────────┘

  External SaaS:  Twilio (calls/webhooks) · LLM provider (Claude) · STT provider · Gmail API · Google Calendar API
```

### 3.3 Node.js Service Requirements (REQ-ARCH-2)
- Single deployable Node.js service; **no separate microservices**.
- Runs with multiple workers via Node `cluster` or **PM2** in cluster mode. Recommended worker count: `(2 × CPU cores) + 1` (parity with the original Uvicorn formula). On a 2-core VM → **5 workers**, sufficient for 10 concurrent HR users given the async I/O profile.
- All I/O (DB, storage, external APIs) is `async/await`; no synchronous blocking calls on the request path.

### 3.4 Recommended Library/Tooling Matrix (best-in-class)

| Concern | Recommended tool | Rationale |
| ------- | ---------------- | --------- |
| Language | TypeScript 5.x (strict) | Type safety end-to-end; required for Drizzle + LangGraph typings. |
| API framework | **NestJS** | Modules/DI, guards (clean RBAC), interceptors (response envelope), built-in validation pipes. (Fastify is the lean alternative.) |
| Validation | **Zod** (+ `nestjs-zod`) | Single schema for request validation **and** LangGraph structured-output schemas. |
| Agents | **LangGraph.js** (`@langchain/langgraph`) | Mandated. State machines, conditional edges, checkpointing, tool nodes. |
| LLM binding | **`@langchain/anthropic`** (Claude) | Best-in-class extraction/analysis; see §3.5. |
| ORM / data layer | **Drizzle ORM** | Typed SQL, lightweight, first-class Postgres + migrations; ideal "Datagraph". |
| DB driver | `postgres` (postg.js) or `pg` | Connection pooling. |
| Supabase | `@supabase/supabase-js` | Storage (pre-signed URLs), Auth helpers. |
| Async/scheduled (Flow) | **Inngest** | Durable steps, automatic retries, cron, local dev UI, observability. (BullMQ + node-cron = lighter alt.) |
| PDF text extraction | **`pdf-parse`** / **`unpdf`** | Replaces `pdfminer`. |
| DOCX text extraction | **`mammoth`** | Replaces `python-docx`. |
| Telephony | **`twilio`** (Node SDK) | Calls, TwiML, signature verification. |
| Transcription | Whisper API (`openai`), **Deepgram**, or **AssemblyAI** | Audio → text; Claude cannot do this. |
| Email (Gmail) | **`googleapis`** (Gmail + Calendar) | Service-account auth, message + attachment fetch, calendar invites. |
| Field encryption | Postgres **`pgcrypto`** or Node `crypto` (AES-256-GCM) | Encrypt phone, CTC fields at rest. |
| Logging | **`pino`** | Structured JSON logs, low overhead. |
| Config/secrets | env + a secrets manager (e.g. Doppler) | No secrets in code. |
| Testing | **Vitest** / Jest + Supertest | Unit + API. |

### 3.5 LLM & Transcription Provider (REQ-ARCH-3)

The product document referenced OpenAI for extraction/analysis and Whisper for transcription. For the rebuild this TRD selects the **best-available** models:

- **Text intelligence (skill extraction, screening Q&A extraction, interview analysis, candidate summaries):** **Claude via `@langchain/anthropic`**, bound inside the LangGraph agents.
  - **Default model: `claude-opus-4-8`** (1M context, strong reasoning) for analysis-heavy tasks (Agent 5 interview analysis).
  - **Cost-optimized model: `claude-sonnet-4-6`** ($3/$15 per 1M tokens) for high-volume routine extraction (Agent 1 skill extraction, Agent 3 Q&A extraction).
  - **Cheapest model: `claude-haiku-4-5`** ($1/$5 per 1M tokens) for short classification-style calls (e.g., skill normalization tie-breaks, short summaries).
  - Use **adaptive thinking** (`thinking: {type: "adaptive"}`) on Opus/Sonnet for complex analysis; control depth with `output_config.effort`.
  - Use **structured outputs** (`output_config.format` with a JSON schema, or LangGraph `withStructuredOutput`) for every agent that returns structured data (skills list, Q&A pairs, analysis object) — this removes brittle parsing.
- **Speech-to-text (call & interview transcription):** a dedicated STT provider — **OpenAI Whisper API**, **Deepgram**, or **AssemblyAI**. Claude does not transcribe audio. Deepgram/AssemblyAI offer streaming + diarization which is valuable for interview transcripts.

> **Model-ID rule:** Use the exact strings `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` (no date suffixes). Default to the latest Claude models for any new AI feature.

---

## 4. Design Principles (Normative)

All 13 principles from the product document are mandatory technical requirements. Each restates **what it does** and **what problem it solves**, plus the Node.js/Datagraph/Flow implementation.

### 4.1 Pagination (REQ-DP-1)
Every list-returning API **must** be paginated. No API ever returns an unbounded list.
- **Default page size:** 20. **Maximum page size:** 100.
- **Query params:** `page` (1-based), `limit`.
- **Standard list envelope:**
  ```json
  { "data": [ ... ], "total": 143, "page": 1, "limit": 20, "total_pages": 8 }
  ```
- **Implementation:** a NestJS interceptor + a Datagraph helper that applies `LIMIT/OFFSET` and a `COUNT(*)` (or windowed count) and clamps `limit ≤ 100`.
- **Applies to (minimum):** `GET /candidates`, `GET /requisitions`, `GET /requisitions/{id}/candidates`, `GET /screening/{candidate_id}/calls`, `GET /interviews/{candidate_id}`, analytics event feed on `GET /analytics/dashboard`.
- **Solves:** as the pool grows to thousands, unpaginated calls would overload the DB, time out, and crash the browser. Pagination keeps every response fast regardless of volume.

### 4.2 Standard API Response Envelope (REQ-DP-2)
Every response uses one of three shapes:

| Type | Structure |
| ---- | --------- |
| List | `{ "data": [...], "total": N, "page": N, "limit": N, "total_pages": N }` |
| Single | `{ "data": { ...object } }` |
| Error | `{ "error": { "code": "MACHINE_READABLE_CODE", "message": "Human readable.", "detail": "optional context" } }` |

**Standard error codes (system-wide):**
- `DUPLICATE_CANDIDATE` — email already exists in candidates.
- `RESUME_LIMIT_EXCEEDED` — candidate already at max resume versions.
- `DUPLICATE_APPLICATION` — candidate already linked to this requisition.
- `ACTIVE_CALL_EXISTS` — screening call already in progress for this candidate.
- `UNAUTHORIZED` — valid JWT but insufficient role.
- `NOT_FOUND` — record does not exist.

**Implementation:** global NestJS exception filter maps domain errors → envelope; a response interceptor wraps successful payloads. **Solves:** consistent contract for frontend and future integrations.

### 4.3 Candidate Deduplication (REQ-DP-3)
Candidate **email** is the single unique identifier. No two candidate records share an email.

Two enforcement layers:
1. **Application layer (Datagraph):** before insert, query `candidates WHERE email = ?`; if matched, reject with `DUPLICATE_CANDIDATE` and return the existing `candidate_id` in `detail` so HR can navigate to the profile.
2. **Database layer:** `UNIQUE` constraint on `candidates.email`. On concurrent inserts, exactly one succeeds; the other receives a constraint violation that the app translates to the same `DUPLICATE_CANDIDATE` error.

**Gmail deduplication:** `gmail_message_id` stored on `candidate_resumes` (UNIQUE where not null) prevents the same email attachment being processed twice across polling cycles.

**Solves:** prevents duplicate records when multiple HRs upload the same person from different sources simultaneously; keeps one canonical profile accumulating all versions, scores, calls, and interviews.

### 4.4 Resume Versioning (REQ-DP-4)
Uploading a new resume for an existing candidate **never overwrites** the previous file.
- New `candidate_resumes` row with `is_latest = true`; previous version set `is_latest = false`.
- **Max versions: 3** per candidate. On the 4th upload → `RESUME_LIMIT_EXCEEDED`; prompt HR to update the existing record.
- **Latest version** is always used for skill extraction, scoring, and search indexing.
- **Previous versions** are retained and visible in the candidate profile's resume-history tab.

**Solves:** candidates update CVs over time; HR needs the current version while retaining history. Overwriting would lose history permanently.

### 4.5 Synchronous Validation Before Any Write (REQ-DP-5)
All business-rule checks execute **synchronously at the start of a request**, before any file is stored, any row created, or any external API called. On failure → immediate rejection with a clear error code; **nothing is written.**

| Endpoint | Synchronous checks |
| -------- | ------------------ |
| `POST /candidates` | 1. Email exists? → `DUPLICATE_CANDIDATE`  2. Version count at limit? → `RESUME_LIMIT_EXCEEDED` |
| `POST /job-applications` | 1. Candidate already linked to this requisition? → `DUPLICATE_APPLICATION` |
| `POST /screening/start-call` | 1. Active call already in progress? → `ACTIVE_CALL_EXISTS` |
| `POST /interviews` | 1. Duplicate round type already scheduled for this candidate + requisition? |
| `POST /interviews/{id}/feedback` | 1. Interview exists and belongs to a valid application? |

**Solves:** immediate, accurate responses; no success-then-silent-background-failure. Fail fast, fail clearly, before side effects.

### 4.6 Asynchronous Post-Response Processing (REQ-DP-6)
Work that does not affect the immediate response runs **after** the HTTP response, on the **Flow** layer. HR receives **202 Accepted** immediately; results appear in the UI when processing completes.

| Operation | Async behavior |
| --------- | -------------- |
| Interview transcription | `POST /interviews/{id}/recording` returns 202; STT transcription runs in a Flow step; transcript saved when done. |
| AI interview analysis | Chains from transcription completion (Flow step); LLM analysis runs after; `ai_analysis` + `ai_overall_rating` populated when done. |
| Agent 6 feedback notification | Triggered automatically after AI analysis completes; notification to interviewer sent in a Flow step. |

**Solves:** interview recordings can be 30–60 min; transcription takes equivalent time. HR should not wait with an open tab. Background processing keeps the UI responsive.

> **Improvement over original:** FastAPI `BackgroundTasks` are fire-and-forget (lost on crash). **Flow (Inngest)** gives **durable, retryable, observable** steps — a crash mid-transcription resumes rather than silently dropping work.

**Note:** **skill extraction on resume upload runs synchronously** within the request (it completes in ~2–3 s and HR needs the results immediately for the confirmation step).

### 4.7 Scoped Candidate Queries (REQ-DP-7)
When viewing candidates in the context of a specific job opening, every query is **scoped to that requisition**. Candidates not linked to that job do not appear.

- **Match scores are per-requisition, not global.** A candidate has a different score per job, based on that job's skill requirements, experience range, location, and work mode. `candidate_scores` stores one row per candidate per requisition.
- **Find Best 20:** `GET /requisitions/{id}/candidates?limit=20&sort=match_score` returns the 20 highest-scoring candidates from the entire pool scored against this specific job.

**Solves:** recruiters see only relevant, ranked candidates; a DevOps requisition never shows AI engineers. Scores are meaningful because computed against specific criteria.

### 4.8 Role-Based Access Control (REQ-DP-8)
Every endpoint enforces the caller's role claim from the JWT. Roles: `HR`, `DELIVERY_MANAGER`, `ADMIN`. Role checked **at the route level before any business logic** (NestJS `RolesGuard`).

| Operation | HR | DM | Admin |
| --------- | -- | -- | ----- |
| Upload resumes | ✅ | ❌ | — |
| Confirm extracted skills | ✅ | ❌ | — |
| Create job openings | ✅ | ✅ | — |
| View & search candidates | ✅ | ✅ | — |
| Initiate screening calls | ✅ | ❌ | — |
| Schedule interviews | ✅ | ❌ | — |
| Submit & update feedback | ✅ | ❌ | — |
| View interview AI analysis | ✅ | ✅ | — |
| View analytics dashboard | ✅ | ✅ | — |
| Manage user accounts | ❌ | ❌ | ✅ |
| Manage skills master list | ❌ | ❌ | ✅ |
| Manage domains/departments | ❌ | ❌ | ✅ |
| View audit logs | ❌ | ❌ | ✅ |

**Solves:** DMs can view pipeline & search but cannot modify candidate data or submit feedback; HRs manage workflow but cannot create accounts. Prevents unintended cross-role data modification.

### 4.9 Sensitive Field Encryption (REQ-DP-9)
Three candidate fields are **encrypted at rest**: `phone`, `current_ctc`, `expected_ctc`. They are **never returned in list responses**; decrypted and included **only** in the full single-profile response (`GET /candidates/{id}`).

| Field | Behavior |
| ----- | -------- |
| `phone` | Encrypted at rest. Excluded from list. Included in single profile. |
| `current_ctc` | Encrypted at rest. Excluded from list. Included in single profile. |
| `expected_ctc` | Encrypted at rest. Excluded from list. Included in single profile. |

**Implementation:** Postgres `pgcrypto` (column-level) **or** application-level AES-256-GCM in the Datagraph layer (encrypt on write, decrypt only in the single-profile read path). **Solves:** if the DB is compromised, the most sensitive fields aren't plaintext; list responses are also faster (decryption only on explicit profile open).

### 4.10 Skill Normalisation (REQ-DP-10)
Every extracted skill is normalized against the `skills` master via `skill_aliases` before being stored in `candidate_skills`. Raw strings like `ML`, `machine learning`, `Machine Learning Engineer` all resolve to canonical `Machine Learning`.

Process:
1. LLM (LangGraph extractor node) extracts raw skill strings from resume text.
2. Each string is lowercased and looked up: `skill_aliases WHERE alias = lower(extracted_string)`.
3. **Found:** canonical `skill_id` is used to insert into `candidate_skills`.
4. **Not found:** create a new `skills` entry with `is_verified = false`, flag for Admin review, and add the alias so future occurrences resolve.

**Solves:** without normalization, filtering by `Python` misses candidates whose resume says `Python3` or `Python programming`. Normalization makes filter/search results complete and accurate.

### 4.11 Database Constraints as Final Guarantee (REQ-DP-11)
Application-level checks (Datagraph) are the first line of defense; **DB-level unique constraints are the last.** Both exist on every uniqueness rule.

| Table + Column(s) | Constraint |
| ----------------- | ---------- |
| `candidates.email` | UNIQUE |
| `candidate_skills (candidate_id, skill_id)` | UNIQUE composite |
| `job_applications (candidate_id, requisition_id)` | UNIQUE composite |
| `requisition_skills (requisition_id, skill_id)` | UNIQUE composite |
| `skill_aliases.alias` | UNIQUE |
| `candidate_resumes.gmail_message_id` | UNIQUE where not null |

**Solves:** under concurrent load, two requests can both pass an app-level check before either writes. The DB constraint guarantees exactly one insert succeeds. Integrity is independent of app logic/timing.

### 4.12 Source Tracking (REQ-DP-12)
Every candidate stores the channel it was sourced from. `source` is **required** (non-null). Optional `source_detail` stores context.

| Source | `source_detail` example |
| ------ | ----------------------- |
| `LINKEDIN` | Profile URL or HR note |
| `NAUKRI` | Profile URL or search query |
| `GMAIL` | Sender email (auto-populated) |
| `REFERRAL` | Name of referrer |
| `EMAIL` | Sender email |
| `OTHER` | Free text |

**Solves:** Analytics (Agent 7) reports which channel produces the highest-quality candidates and best hire rates. HR leadership decides where to invest sourcing effort.

### 4.13 Audit Trail (REQ-DP-13)
Two separate append-only log tables, for two purposes:

| Table | Purpose / what it records |
| ----- | ------------------------- |
| `audit_logs` | **Accountability.** Every user action that creates/updates/deletes a record: who, what, which record, when, from which IP. For HR-team accountability & compliance. |
| `analytics_events` | **Pipeline reporting.** Every significant candidate-journey milestone (added, scored, screened, interview scheduled, feedback submitted, hired, rejected). Powers Agent 7 funnel/conversion reports. |

Both are **write-only** from the application's perspective — no feature ever deletes or updates rows. Permanent, append-only.

**Solves:** `audit_logs` gives accountability if a record is wrongly modified/deleted; `analytics_events` is the data foundation for pipeline analytics without complex query-time joins.

---

## 5. Architecture Components (Node.js Detail)

### 5.1 Nginx (Reverse Proxy) — unchanged
Runs on the same VM. Receives all inbound HTTP and forwards to the Node.js process. Handles **TLS termination, static file serving, request buffering, connection limits**.
- All routes except `POST /webhooks/twilio` require a valid JWT.
- Nginx does **not** validate JWTs; it forwards everything to Node, which enforces auth at the route level.
- **Public endpoint:** `POST /webhooks/twilio` is the only endpoint not requiring HR auth. Twilio signs all webhook requests; the service verifies the **Twilio signature** before processing.

### 5.2 Node.js Application (replaces "FastAPI Application")
The **only** backend service. Contains all business logic, route handlers, agent logic (LangGraph), the Flow workers, and the scheduler.
- Runs with multiple workers (PM2 cluster / Node `cluster`). Recommended: `(2 × cores) + 1` → 5 workers on a 2-core VM.
- Each worker is single-threaded but handles concurrent async requests; I/O-bound ops (DB, storage, external APIs) do not block other requests within a worker.
- For 10 concurrent HR users, 5 workers on a 2-core VM is sufficient.

### 5.3 Supabase PostgreSQL — unchanged
Fully managed Postgres. No DB server provisioned/maintained/backed-up by the team. Node connects via a standard Postgres connection string (through the Datagraph/Drizzle layer + a connection pool). Supabase handles uptime, backups, SSL, scaling.
- `tsvector` columns on `candidate_resumes` provide full-text search across resume content — **no separate Elasticsearch** at current scale.

### 5.4 Supabase Storage — unchanged
Resume files (PDF, DOCX) stored in Supabase Storage buckets. The Node service uploads via `@supabase/supabase-js`. File URLs stored in `candidate_resumes`. HR accesses files only through **pre-signed URLs** generated per request.

### 5.5 Supabase Auth — unchanged
All auth handled by Supabase Auth. HR & DM accounts created by an Admin. Login returns a JWT. Node validates JWTs on every protected route using the Supabase JWT secret (HS256) or JWKS. Role (`HR | DELIVERY_MANAGER | ADMIN`) is a custom claim, enforced at the route level.

### 5.6 Flow — Gmail Polling & Async Work (replaces "APScheduler")
The **Flow** layer (Inngest, or `node-cron` + BullMQ) runs:
1. **Gmail polling cron — every 5 minutes:** connects to Gmail API (service account), checks the monitored inbox for new emails with PDF/DOCX attachments, and passes each new attachment through the **same Agent 1 pipeline** used for manual uploads.
   - **Dedup:** each processed Gmail message ID is stored in `candidate_resumes`. Before processing, the job checks whether the message ID already exists (UNIQUE-where-not-null), preventing duplicate imports.
2. **Post-response async chains:** transcription → analysis → feedback notification (§4.6).

The Flow layer runs **inside / alongside** the Node process (no separate scheduler service required), satisfying the original "single-service" constraint.

---

## 6. Data Entry Points

### 6.1 HR Manual Upload — Single or Batch (REQ-INGEST-1)
HR selects one or many files. The frontend sends **parallel individual HTTP requests — one per file.** Each file is processed independently and concurrently by Node workers. HR sees per-file progress/status in real time.

Per-file processing (synchronous, within the single request — this is **Agent 1**, §7.1):
1. Validate file (PDF or DOCX, max size enforced).
2. Upload to Supabase Storage.
3. Extract text — **`pdf-parse`/`unpdf`** (PDF) or **`mammoth`** (DOCX). *(Replaces pdfminer/python-docx.)*
4. Send extracted text to the **LLM skill-extraction node** (LangGraph).
5. LLM returns raw skill list; each skill normalized against `skill_aliases`.
6. Unrecognized skills flagged `is_verified = false`, added to `skills`.
7. Candidate record created or matched by email (dedup).
8. `candidate_skills` rows inserted with `is_verified = false`.
9. `tsvector` search index updated automatically by Postgres (generated column).
10. Response returned to HR with extracted skill list **for confirmation**.

HR reviews extracted skills, removes false positives, adds missed skills, and confirms. On confirmation, `is_verified = true` for confirmed skills. This balances automation with human oversight for data quality.

### 6.2 Gmail Auto-Ingestion (REQ-INGEST-2)
Every 5 minutes the Flow Gmail job authenticates with Gmail API (service account), fetches all unread emails in the monitored inbox, and processes any PDF/DOCX attachments. Each attachment goes through the **identical Agent 1 pipeline**. The candidate's `source = GMAIL` and `source_detail = sender email address`.

---

## 7. Agents (LangGraph)

> **MANDATE:** **Every agent is a LangGraph (`@langchain/langgraph`) `StateGraph`.** Agents are logical processing units that live **inside the single Node.js service** (not separate deployed services) — synchronous ones run on the request path; asynchronous ones run as Flow steps that invoke the graph. Each agent below specifies: trigger, state schema, nodes, edges, tools, LLM/model, and DB writes.

### 7.0 Common Agent Conventions

- **Graph construction:** each agent exports a `buildXGraph()` returning a compiled `StateGraph`. State is a typed channel object (Zod/`Annotation`).
- **Checkpointing:** long-running / async agents (3, 5, 6) use a LangGraph **checkpointer** (Postgres-backed via Datagraph) so a Flow retry resumes mid-graph rather than restarting.
- **Tools:** DB access, storage, Twilio, Gmail, Calendar, and STT are exposed to agents as **LangGraph tool nodes / typed functions** (not free-form bash). The LLM node only handles language tasks; all side-effecting I/O is explicit nodes.
- **Structured output:** every LLM node that emits structured data uses `withStructuredOutput(zodSchema)` (Claude structured outputs) — no regex parsing of model text.
- **Model selection:** see §3.5. Default Sonnet 4.6 for extraction-class nodes; Opus 4.8 for the interview-analysis node; Haiku 4.5 for short normalization/summary calls.
- **Events:** agents write to `analytics_events` (always) and `audit_logs` (for user-initiated, record-mutating actions).

---

### 7.1 Agent 1 — Resume Intake (synchronous)

Handles all resume ingestion regardless of source. **Runs synchronously within the upload request** (and within the Gmail Flow job). Responsible for file storage, text extraction, LLM skill extraction, skill normalization, candidate creation + dedup, search-index update, and returning the skill-confirmation payload to HR.

- **Trigger:** `POST /candidates` (HR manual) **or** the Flow Gmail job.
- **Writes to:** `candidates`, `candidate_resumes`, `candidate_skills`, `skills`, `skill_aliases`, `analytics_events`.
- **Model:** `claude-sonnet-4-6` (extraction); `claude-haiku-4-5` optional for alias tie-breaks.

**State schema:**
```ts
type IntakeState = {
  source: "MANUAL" | "GMAIL";
  uploadedBy: string;            // user id (HR) or system user (Gmail)
  fileBuffer: Buffer;
  fileName: string;
  mimeType: string;
  gmailMessageId?: string;
  sourceDetail?: string;
  // derived
  parsedText?: string;
  fileUrl?: string;
  candidateId?: string;
  rawSkills?: string[];
  normalizedSkills?: Array<{ skillId: string; isNew: boolean }>;
  aiSummary?: string;
  error?: { code: string; detail?: string };
};
```

**Nodes & edges:**
```
START
  → validateFile           // PDF/DOCX, size, dedup (gmail_message_id) — synchronous checks (§4.5)
  → dedupCandidate         // by email if known; sets DUPLICATE_CANDIDATE / RESUME_LIMIT_EXCEEDED on error
      ├─(error)→ END (return error envelope)
  → uploadToStorage        // Supabase Storage → fileUrl
  → extractText            // pdf-parse / mammoth
  → llmExtractSkills       // LLM node, withStructuredOutput({ skills: string[], summary: string })
  → normalizeSkills        // alias lookup; create unverified skills; (§4.10)
  → persist                // candidates (create/match), candidate_resumes (is_latest), candidate_skills (is_verified=false)
  → emitAnalytics          // CANDIDATE_ADDED
  → END (return extracted skill list + ai_summary for confirmation)
```

> **Skill confirmation** is a separate user action: `POST /candidates/{id}/confirm-skills` sets `is_verified = true` (not part of the intake graph run).

---

### 7.2 Agent 2 — Resume Scoring (automatic)

After a candidate enters the system, Agent 2 automatically computes a per-requisition match score for all **open** job openings in the **same domain**. Scoring is **heuristic-based** (deterministic — not an LLM call) and produces an overall score plus a per-dimension breakdown for transparency.

- **Trigger:** automatically after Agent 1 completes **or** when a new job opening is created.
- **Writes to:** `candidate_scores`, `job_applications` (`match_score` column), `analytics_events`.
- **Model:** none (pure heuristic). LangGraph orchestrates the deterministic scoring nodes.

**Scoring dimensions & weights (REQ-AGENT2-1):**

| Dimension | Weight |
| --------- | ------ |
| Mandatory skills match (candidate has all required skills) | 40% |
| Total experience within requisition range | 20% |
| Per-skill depth (years per skill vs minimum required) | 20% |
| Location & work-mode match | 10% |
| Notice period within role requirements | 10% |

`total_score` = weighted sum, normalized to `0.0–1.0`. Each component stored separately (`skills_score`, `experience_score`, `skills_depth_score`, `location_score`, `notice_period_score`) in `candidate_scores`, with a `scoring_version` string for tracking logic changes.

**State / nodes:**
```ts
type ScoreState = {
  candidateId: string;
  requisitionIds: string[];   // open reqs in same domain (fan-out)
  scores: CandidateScore[];
};
```
```
START
  → resolveRequisitions    // open reqs in the candidate's domain (Datagraph graph query)
  → computeScores          // per req: 5 components → total (deterministic)
  → persistScores          // candidate_scores (one row per req); job_applications.match_score
  → emitAnalytics          // SCORE_COMPUTED
  → END
```
Run **once per (candidate, requisition)** pair; the graph fans out over requisitions. Dual trigger means the same graph is invoked both on new-candidate and new-requisition events (the latter scores the whole eligible pool against the new req).

---

### 7.3 Agent 3 — Telephonic Screening

HR initiates a screening call from the candidate profile. The system calls the candidate via Twilio, plays predefined questions, records responses, receives webhook updates as the call progresses, and after completion runs **transcription + structured Q&A extraction**.

- **Trigger:** `POST /screening/start-call` (HR-initiated).
- **Webhook:** `POST /webhooks/twilio` (public; **Twilio signature verified**).
- **Writes to:** `call_logs`, `analytics_events`.
- **Model:** `claude-sonnet-4-6` (Q&A extraction). STT provider for transcription.
- **Synchronous check (§4.5):** active call already in progress → `ACTIVE_CALL_EXISTS`.

**Call flow:**
1. HR clicks **Start Screening** on the candidate profile.
2. `POST /screening/start-call` triggers a Twilio call to the candidate's phone (body: `candidate_id`, `requisition_id`, `question_set_id`). A `call_logs` row is created (`status = INITIATED`).
3. Twilio executes a **TwiML** script: greets the candidate, asks predefined questions, records answers.
4. Twilio sends webhook callbacks to `POST /webhooks/twilio` as the call progresses (status transitions `INITIATED → IN_PROGRESS → COMPLETED/FAILED/NO_ANSWER`).
5. On completion, recording URL stored; the **STT provider** transcribes the audio (Flow step).
6. LLM node extracts structured Q&A pairs from the transcript.
7. `call_logs` updated with full transcript and structured answers.

**LangGraph design:** Agent 3 spans an external boundary (the live call), so it is modeled as a **graph with a checkpointer** that pauses after initiating the call and **resumes from the webhook** (Flow step) once Twilio reports completion.
```
START
  → validateNoActiveCall   // ACTIVE_CALL_EXISTS (§4.5)
  → initiateTwilioCall     // create call_logs (INITIATED); place call
  → [interrupt/checkpoint]  ← resumes on webhook COMPLETED
  → transcribe             // STT provider → transcript
  → llmExtractQA           // withStructuredOutput([{question, answer, ai_comment, ai_rating}])
  → persist                // call_logs (transcript, screening_answers jsonb)
  → emitAnalytics          // CALL_COMPLETED
  → END
```
`screening_answers` jsonb shape: `[{ question, answer, ai_comment, ai_rating }]`.

---

### 7.4 Agent 4 — Interview Scheduling

HR creates an interview round, specifying round type (L1, L2, L3, HR, Final, Technical, Cultural), interviewer, and time slot. Agent 4 creates the interview record, sends **Google Calendar** invites to the interviewer, and logs the scheduling event.

- **Trigger:** `POST /interviews` (HR-initiated).
- **Writes to:** `interviews`, `analytics_events`.
- **Model:** none (orchestration + Calendar tool).
- **Synchronous check (§4.5):** duplicate round type already scheduled for this candidate + requisition → reject.

**Nodes:**
```
START
  → validateNoDuplicateRound   // (§4.5)
  → createInterview            // interviews row (SCHEDULED); round_number/round_type
  → sendCalendarInvite         // Google Calendar API → calendar_event_id, meeting_link
  → emitAnalytics              // INTERVIEW_SCHEDULED
  → END
```

---

### 7.5 Agent 5 — Interview Analysis (asynchronous)

After an interview is completed, HR uploads the recording. Agent 5 transcribes the audio (STT), then sends the transcript to the **LLM for structured analysis**. The LLM evaluates **communication clarity, technical depth, problem-solving approach, and cultural-fit signals**, and produces a **per-question breakdown** (question asked, candidate's answer, AI's assessment). Results are stored and shown to HR alongside the interviewer's human feedback.

- **Trigger:** `POST /interviews/{id}/recording` (HR-initiated) → returns **202**; runs on the **Flow** layer.
- **Writes to:** `interviews` (`transcript`, `ai_analysis`, `ai_overall_rating`, `analysis_completed_at`), `analytics_events`.
- **Model:** **`claude-opus-4-8`** (deep analysis; adaptive thinking, `effort: high`). STT provider for transcription.

**Nodes (runs as Flow steps, with checkpointer):**
```
START
  → storeRecording        // Supabase Storage → recording_url
  → transcribe            // STT provider (long audio) → transcript
  → llmAnalyze            // Opus; withStructuredOutput(AnalysisSchema)
  → persist               // interviews: ai_analysis (jsonb), ai_overall_rating (0.0–1.0), transcript
  → emitAnalytics         // (analysis complete)
  → triggerAgent6         // chains feedback notification (§7.6)
  → END
```
`ai_analysis` jsonb captures the four dimensions + `ai_qa_breakdown` = `[{question, candidate_answer, ai_comment, ai_rating}]`. `ai_overall_rating` is `0.0–1.0`.

---

### 7.6 Agent 6 — Feedback Collection (auto-chained)

Automatically triggered after Agent 5 completes analysis. Sends the interviewer a notification (email or in-app) with a link to the feedback form for that round. The interviewer submits structured ratings + written comments. Feedback can be **updated** after initial submission. Both AI analysis and human feedback are visible together on the candidate profile.

- **Trigger:** automatic chain after Agent 5 completes (Flow step).
- **HR/Interviewer action:** `POST /interviews/{id}/feedback` (submit or update).
- **Writes to:** `interview_feedback`, `analytics_events`.
- **Model:** none (notification + persistence). Optional Haiku for templated message text.

**Nodes:**
```
START
  → resolveInterviewer     // from interviews.interviewer_id
  → sendNotification       // email/in-app with feedback-form link (Flow step, retryable)
  → emitAnalytics
  → END
```
The feedback submission itself is a separate endpoint (`POST /interviews/{id}/feedback`), upserting `interview_feedback` (`is_submitted`, `submitted_at`, `last_updated_at`). On submission → `analytics_events: FEEDBACK_SUBMITTED`.

---

### 7.7 Agent 7 — Analytics

Reads from all tables to produce pipeline metrics and dashboards for HR and management. Queries served **on demand** via the analytics endpoints. `analytics_events` is the event log powering funnel & timeline reporting.

- **Trigger:** `GET /analytics/dashboard` and related GET endpoints (HR or DM).
- **Reads from:** `candidates`, `candidate_scores`, `call_logs`, `interviews`, `interview_feedback`, `job_applications`, `analytics_events`.
- **Model:** none required (pure aggregation). LangGraph orchestrates parallel aggregation nodes; an **optional** LLM summary node (`claude-haiku-4-5`) can produce a natural-language digest of the dashboard.

**Dashboard metrics (REQ-AGENT7-1):**
- Candidate pipeline funnel (count per stage: added, scored, screened, interviewed, offered, hired, rejected).
- Source effectiveness (which source produces highest-scoring / hired candidates).
- Open requisition health (days open, candidates in pipeline per role).
- Interviewer feedback patterns & rating distributions.
- Average time-to-hire per domain and per seniority.
- Scoring accuracy over time (correlation between `match_score` and hire outcome).

**Nodes:** fan-out parallel aggregation queries (funnel, sources, req-health, feedback, time-to-hire, scoring-accuracy) → merge → optional `summarize` (LLM) → return.

### 7.8 Agent Trigger Summary

| Agent | Sync/Async | Trigger | Model |
| ----- | ---------- | ------- | ----- |
| 1 Resume Intake | **Sync** | `POST /candidates`, Gmail Flow job | Sonnet 4.6 (+ Haiku) |
| 2 Resume Scoring | Auto (sync after A1 / on new req) | after Agent 1, or new requisition | none (heuristic) |
| 3 Telephonic Screening | **Async** (call + webhook) | `POST /screening/start-call` | Sonnet 4.6 + STT |
| 4 Interview Scheduling | Sync | `POST /interviews` | none + Calendar |
| 5 Interview Analysis | **Async (202)** | `POST /interviews/{id}/recording` | **Opus 4.8** + STT |
| 6 Feedback Collection | Async (auto-chain) | after Agent 5 | none (+ Haiku) |
| 7 Analytics | Sync (on demand) | `GET /analytics/*` | none (+ optional Haiku) |

---

## 8. API Reference

All endpoints require JWT auth **except `POST /webhooks/twilio`**. The **Role** column = minimum role required. All list endpoints are paginated (§4.1) and use the standard envelope (§4.2).

### 8.1 Authentication

| Endpoint | Description |
| -------- | ----------- |
| `POST /auth/login` | Login with email + password. Returns JWT with role claim. |
| `POST /auth/logout` | Invalidate the current session token. |
| `POST /auth/users` (Admin only) | Create a new HR or Delivery Manager account. |

### 8.2 Candidates

| Method | Endpoint | Role | Description |
| ------ | -------- | ---- | ----------- |
| POST | `/candidates` | HR | Upload one or many resumes. No position required. Multipart form. Returns extracted skills + `ai_summary` for confirmation. Candidates enter the pool independently of any job opening. |
| POST | `/candidates/{id}/confirm-skills` | HR | HR confirms/adjusts extracted skills. Sets `is_verified = true`. |
| GET | `/candidates` | HR, DM | List all candidates. Excludes blacklisted by default. Supports all filters. Paginated. Returns `ai_summary` per candidate for quick scanning. |
| GET | `/candidates?blacklisted=true` | Admin | List blacklisted candidates only. Admin role required. |
| GET | `/candidates/{id}` | HR, DM | Full profile: `ai_summary`, skills, resume versions, scores, call logs, interview history, `custom_metadata`. (Decrypts sensitive fields — §4.9.) |
| PATCH | `/candidates/{id}` | HR | Update candidate metadata incl. `custom_metadata` jsonb. |
| GET | `/candidates/{id}/resume` | HR, DM | Pre-signed URL to view latest resume file. |
| POST | `/candidates/{id}/blacklist` | HR, Admin | Blacklist system-wide. Body: `reason_id`, `note`. Sets `is_blacklisted = true`, records who/when, and **automatically drops all active pipeline applications** with a system note. |
| DELETE | `/candidates/{id}/blacklist` | Admin | Remove blacklist if applied in error. Adds an `audit_logs` entry. **Does not restore** previous application statuses. |

### 8.3 Job Openings (Requisitions)

| Method | Endpoint | Role | Description |
| ------ | -------- | ---- | ----------- |
| POST | `/requisitions` | HR, DM | Create a job opening: title, description, domain, department, skills required, experience range, location, work mode, CTC budget, headcount. |
| GET | `/requisitions` | HR, DM | List job openings. Filter by status, domain, department. |
| GET | `/requisitions/{id}` | HR, DM | Full detail incl. required skills + candidate-pipeline summary. |
| PATCH | `/requisitions/{id}` | HR, DM | Update details or status (`OPEN`, `ON_HOLD`, `CLOSED`). |
| GET | `/requisitions/{id}/candidates` | HR, DM | All candidates linked to this job, sorted by `match_score` desc. Supports same filters as `/candidates`. (Scoped — §4.7.) |

### 8.4 Skills

| Method | Endpoint | Role | Description |
| ------ | -------- | ---- | ----------- |
| GET | `/skills` | All | Full skills master list grouped by category. Populates filter dropdowns. |
| POST | `/skills` | Admin | Add a new skill to the master list. |
| POST | `/skills/{id}/aliases` | Admin | Add aliases (e.g. `ML`, `machine learning` → `Machine Learning`). |

### 8.5 Screening Calls

| Method | Endpoint | Role | Description |
| ------ | -------- | ---- | ----------- |
| POST | `/screening/start-call` | HR | Initiate Twilio screening call. Body: `candidate_id`, `requisition_id`, `question_set_id`. (Check `ACTIVE_CALL_EXISTS`.) |
| GET | `/screening/{candidate_id}/calls` | HR, DM | All call logs for a candidate incl. transcripts & Q&A breakdowns. Paginated. |
| POST | `/webhooks/twilio` | **Public** | Twilio webhook receiver. **Twilio signature verified** before processing. Updates call status; stores recording URL. |

### 8.6 Interviews

| Method | Endpoint | Role | Description |
| ------ | -------- | ---- | ----------- |
| POST | `/interviews` | HR | Schedule a round. Body: `candidate_id`, `requisition_id`, `interviewer_id`, `round_type`, `scheduled_at`, `meeting_link`. |
| GET | `/interviews/{candidate_id}` | HR, DM | All rounds for a candidate across all jobs. Paginated. |
| PATCH | `/interviews/{id}` | HR | Update status (`COMPLETED`, `CANCELLED`, `NO_SHOW`, `RESCHEDULED`). |
| POST | `/interviews/{id}/recording` | HR | Upload recording. **Triggers Agent 5** (transcription + AI analysis). Returns **202**. |
| POST | `/interviews/{id}/feedback` | HR | Submit or update human feedback. Can be called multiple times. |
| GET | `/interviews/{id}/feedback` | HR, DM | Combined AI analysis + human feedback for one round. |

### 8.7 Analytics

| Endpoint | Description |
| -------- | ----------- |
| `GET /analytics/dashboard` | Overall pipeline summary: counts by stage, source breakdown, open-roles health. |
| `GET /analytics/funnel` | Stage-by-stage funnel with conversion rates. |
| `GET /analytics/sources` | Source effectiveness: application volume + hire rate per source. |
| `GET /analytics/time-to-hire` | Avg days from added → hired, by domain & seniority. |
| `GET /analytics/requisitions/{id}` | Per-job analytics: pipeline depth, scoring distribution, interview outcomes. |

---

## 9. Database Schema (Datagraph)

All tables reside in Supabase PostgreSQL. **UUIDs** for all primary keys. Timestamps stored in **UTC** (`timestamptz`). Schema and migrations are owned by the **Datagraph** layer (Drizzle). Every table below is a Drizzle schema + a generated migration.

### 9.1 `users`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| name | varchar(150) | |
| email | varchar(255) UNIQUE | Login identifier |
| role | enum | `HR \| DELIVERY_MANAGER \| ADMIN` |
| is_active | boolean | Soft disable without deleting |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### 9.2 `domains`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| name | varchar(100) UNIQUE | e.g. AI/ML, DevOps, Frontend, Backend, Data Science |
| created_at | timestamptz | |

### 9.3 `departments`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| name | varchar(100) UNIQUE | e.g. Engineering, Product, Design, Operations |
| created_at | timestamptz | |

### 9.4 `skills`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| name | varchar(100) UNIQUE | Canonical name e.g. Python, PyTorch, Kubernetes |
| category | enum | `PROGRAMMING_LANGUAGE \| FRAMEWORK \| CLOUD \| DATABASE \| TOOL \| DOMAIN_SKILL \| SOFT_SKILL` |
| is_verified | boolean | False for auto-created unrecognized skills pending admin review |
| created_at | timestamptz | |

### 9.5 `skill_aliases`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| skill_id | uuid FK → skills | |
| alias | varchar(100) UNIQUE | Lowercase. e.g. `ml`, `machine learning`, `ml engineer` → Machine Learning |
| created_at | timestamptz | |

Index: `alias` for fast normalization lookups.

### 9.6 `candidates`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| full_name | varchar(200) | |
| email | varchar(255) UNIQUE | Dedup key. Unique at DB level. |
| phone | varchar(30) | **Encrypted at rest** |
| current_location | varchar(200) | |
| linkedin_url | varchar(500) | |
| portfolio_url | varchar(500) | |
| domain_id | uuid FK → domains | Primary domain |
| total_experience_years | float | |
| current_company | varchar(200) | |
| current_designation | varchar(200) | |
| current_ctc | integer | Annual, INR. **Encrypted at rest.** |
| expected_ctc | integer | Annual, INR. **Encrypted at rest.** |
| notice_period_days | integer | 0, 15, 30, 60, 90 |
| availability_date | date | Earliest join date |
| work_mode_preference | enum | `REMOTE \| HYBRID \| ONSITE` |
| shift_preference | enum | `DAY \| NIGHT \| FLEXIBLE` |
| source | enum | `LINKEDIN \| NAUKRI \| EMAIL \| REFERRAL \| GMAIL \| OTHER` (required) |
| source_detail | text | Referrer name if REFERRAL; sender email if GMAIL/EMAIL |
| uploaded_by | uuid FK → users | HR who created the record |
| custom_metadata | jsonb | Flexible recruiter key-value pairs (e.g. visa_status, willing_to_relocate, last_contacted). No fixed schema. |
| is_blacklisted | boolean default false | System-wide flag. When true, excluded from all search results and cannot be linked to any new job. |
| blacklist_reason_id | uuid FK → pipeline_status_reasons (nullable) | Populated only when blacklisted. |
| blacklisted_by | uuid FK → users (nullable) | Who blacklisted. |
| blacklisted_at | timestamptz (nullable) | When. |
| blacklist_note | text (nullable) | Free text beyond structured reason. |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Indexes: `email` (unique), `domain_id`, `total_experience_years`, `notice_period_days`, `work_mode_preference`, `source`, `is_blacklisted`.
All `GET /candidates` queries append `WHERE is_blacklisted = false` by default. Blacklisted visible only via `GET /candidates?blacklisted=true` (Admin only).

### 9.7 `candidate_resumes`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| candidate_id | uuid FK → candidates | |
| file_url | varchar(1000) | Supabase Storage URL |
| redacted_file_url | varchar(1000) | PII-stripped version, stored separately |
| parsed_text | text | Full extracted resume text |
| search_vector | tsvector GENERATED | Auto-computed from `parsed_text`. Powers FTS. |
| gmail_message_id | varchar(200) | Gmail-sourced; prevents duplicate import |
| is_latest | boolean | True for most recent version |
| uploaded_by | uuid FK → users | |
| uploaded_at | timestamptz | |

Indexes: **GIN** on `search_vector`; index on `candidate_id`; **UNIQUE on `gmail_message_id` where not null**.

### 9.8 `candidate_skills`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| candidate_id | uuid FK → candidates | |
| skill_id | uuid FK → skills | Normalized canonical skill |
| proficiency_level | enum | `BEGINNER \| INTERMEDIATE \| EXPERT` |
| years_of_experience | float | Years with this specific skill |
| is_verified | boolean | False = auto-extracted by LLM; True = confirmed by HR |
| created_at | timestamptz | |

**UNIQUE (candidate_id, skill_id).** Indexes on `skill_id`, `candidate_id`.

### 9.9 `requisitions`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| title | varchar(300) | e.g. Associate AI Engineer |
| description | text | Full JD |
| domain_id | uuid FK → domains | |
| department_id | uuid FK → departments | |
| seniority_level | enum | `INTERN \| JUNIOR \| MID \| SENIOR \| LEAD \| MANAGER \| DIRECTOR` |
| location | varchar(200) | |
| work_mode | enum | `REMOTE \| HYBRID \| ONSITE` |
| shift_timing | enum | `DAY \| NIGHT \| FLEXIBLE` |
| min_experience_years | float | |
| max_experience_years | float | |
| min_budget_ctc | integer | Annual, INR |
| max_budget_ctc | integer | Annual, INR |
| number_of_openings | integer | Headcount |
| status | enum | `DRAFT \| OPEN \| ON_HOLD \| CLOSED \| CANCELLED` |
| created_by | uuid FK → users | |
| hiring_manager_id | uuid FK → users | Delivery Manager responsible |
| target_close_date | date | |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### 9.10 `requisition_skills`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| requisition_id | uuid FK → requisitions | |
| skill_id | uuid FK → skills | |
| is_mandatory | boolean | True = must-have; False = nice-to-have |
| minimum_years | float | Min years for this skill |
| created_at | timestamptz | |

**UNIQUE (requisition_id, skill_id).**

### 9.11 `job_applications`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| candidate_id | uuid FK → candidates | |
| requisition_id | uuid FK → requisitions | |
| status | enum | `NEW \| SCREENING \| SHORTLISTED \| INTERVIEW_SCHEDULED \| OFFERED \| REJECTED \| WITHDRAWN \| HIRED` |
| match_score | float | Overall 0.0–1.0 from Agent 2 |
| rejection_reason | text | When status = REJECTED |
| notes | text | HR notes on this application |
| created_by | uuid FK → users | Who linked candidate to job |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**UNIQUE (candidate_id, requisition_id).** Indexes on `requisition_id`, `candidate_id`, `status`, `match_score`.

### 9.12 `candidate_scores`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| candidate_id | uuid FK → candidates | |
| requisition_id | uuid FK → requisitions | |
| total_score | float | Final weighted 0.0–1.0 |
| skills_score | float | Mandatory skills match component |
| experience_score | float | Experience range component |
| skills_depth_score | float | Per-skill years depth component |
| location_score | float | Location & work-mode component |
| notice_period_score | float | Notice-period fit component |
| scoring_version | varchar(20) | Scoring-logic version |
| created_at | timestamptz | |

(One row per candidate per requisition — §4.7.)

### 9.13 `call_logs`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| candidate_id | uuid FK → candidates | |
| requisition_id | uuid FK → requisitions | |
| initiated_by | uuid FK → users | HR who started the call |
| twilio_call_sid | varchar(100) | Twilio call identifier |
| status | enum | `INITIATED \| IN_PROGRESS \| COMPLETED \| FAILED \| NO_ANSWER` |
| recording_url | varchar(1000) | Twilio-hosted recording |
| transcript | text | Full STT transcription |
| screening_answers | jsonb | `[{question, answer, ai_comment, ai_rating}]` |
| duration_seconds | integer | |
| called_at | timestamptz | |
| completed_at | timestamptz | |

### 9.14 `interviews`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| candidate_id | uuid FK → candidates | |
| requisition_id | uuid FK → requisitions | |
| interviewer_id | uuid FK → users | |
| round_number | integer | 1 for L1, 2 for L2, etc. |
| round_type | enum | `L1 \| L2 \| L3 \| HR \| FINAL \| TECHNICAL \| CULTURAL` |
| status | enum | `SCHEDULED \| COMPLETED \| CANCELLED \| NO_SHOW \| RESCHEDULED` |
| scheduled_at | timestamptz | |
| meeting_link | varchar(500) | Google Meet / Zoom |
| calendar_event_id | varchar(200) | Google Calendar event ID for updates |
| recording_url | varchar(1000) | Uploaded recording in Supabase Storage |
| transcript | text | STT transcription of recording |
| ai_analysis | jsonb | LLM structured analysis |
| ai_overall_rating | float | 0.0–1.0 |
| analysis_completed_at | timestamptz | |
| created_by | uuid FK → users | HR who scheduled |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### 9.15 `interview_feedback`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| interview_id | uuid FK → interviews | One feedback record per round |
| submitted_by | uuid FK → users | Interviewer |
| ai_summary | text | AI overall observation |
| ai_strengths | text | AI-identified strengths |
| ai_concerns | text | AI-identified concerns/gaps |
| ai_qa_breakdown | jsonb | `[{question, candidate_answer, ai_comment, ai_rating}]` |
| human_summary | text | Interviewer overall comments |
| human_strengths | text | Interviewer-noted strengths |
| human_concerns | text | Interviewer-noted concerns |
| technical_rating | integer 1-5 | Human |
| communication_rating | integer 1-5 | Human |
| problem_solving_rating | integer 1-5 | Human |
| culture_fit_rating | integer 1-5 | Human |
| overall_rating | integer 1-5 | Human overall |
| recommendation | enum | `STRONG_YES \| YES \| MAYBE \| NO \| STRONG_NO` |
| is_submitted | boolean | False = draft; True = finalized. Updatable after submission. |
| submitted_at | timestamptz | First submission time |
| last_updated_at | timestamptz | Most recent update |

### 9.16 `analytics_events`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| event_type | varchar(100) | `CANDIDATE_ADDED \| SKILLS_CONFIRMED \| SCORE_COMPUTED \| CALL_COMPLETED \| INTERVIEW_SCHEDULED \| FEEDBACK_SUBMITTED \| STATUS_CHANGED \| HIRED \| REJECTED` |
| candidate_id | uuid FK → candidates | |
| requisition_id | uuid FK → requisitions (nullable) | |
| triggered_by | uuid FK → users (nullable) | Null for system-triggered events |
| metadata | jsonb | e.g. previous status, new status, score value |
| occurred_at | timestamptz | |

Index on `event_type`, `candidate_id`, `requisition_id`, `occurred_at` (efficient aggregations). **Append-only.**

### 9.17 `audit_logs`
| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| user_id | uuid FK → users | Who performed the action |
| action | varchar(200) | e.g. UPLOADED_RESUME, CREATED_JOB, UPDATED_FEEDBACK |
| entity_type | varchar(100) | candidate \| requisition \| interview \| feedback |
| entity_id | uuid | Affected record |
| metadata | jsonb | Before/after values for updates |
| ip_address | varchar(50) | |
| created_at | timestamptz | |

**Append-only.**

### 9.18 `pipeline_status_reasons`
Master list of predefined sub-reasons per pipeline status. Used when HR moves a candidate to a rejected/dropped status. Ensures consistent reason tracking.

| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| status | enum | Pipeline status this reason applies to |
| reason | varchar(200) | Human-readable label |
| is_active | boolean default true | Inactive reasons hidden from UI but retained for historical records |
| created_at | timestamptz | |

**Seeded values by status:**
- **DROPPED:** Candidate not responding · Accepted another offer · Personal reasons · Relocated · Withdrew voluntarily
- **L1_REJECTED:** Technical skills insufficient · Communication poor · Attitude concerns · Salary expectation mismatch · No show
- **L2_REJECTED:** Deep technical gap · Leadership skills lacking · Culture fit concern · Salary mismatch · No show
- **CLIENT_REJECTED:** Profile not matching requirement · Overqualified · Underqualified · Communication barrier · Client cancelled requirement
- **BLACKLISTED:** Fraudulent information on resume · Unprofessional conduct · Repeated no shows · Policy violation

### 9.19 `application_status_history`
Append-only log of every pipeline status change for every application. Written automatically whenever `job_applications.status` changes. Never deleted or modified.

| Column | Type | Notes |
| ------ | ---- | ----- |
| id | uuid PK | |
| application_id | uuid FK → job_applications | |
| from_status | enum (nullable) | Previous status. Null for first assignment. |
| to_status | enum | New status. |
| reason_id | uuid FK → pipeline_status_reasons (nullable) | Structured sub-reason if applicable. |
| reason_note | text (nullable) | Free text context. |
| changed_by | uuid FK → users | Who changed it. System user for automated changes. |
| changed_at | timestamptz | |

Index on `application_id`. Powers the pipeline-timeline view on the candidate profile.

---

## 10. Candidate Filtering

Filtering is handled entirely within PostgreSQL via **dynamic query construction in the Datagraph layer** (Drizzle dynamic query builder). No separate search service at current scale.

Available filters on `GET /candidates` and `GET /requisitions/{id}/candidates`:

| Filter Parameter | Implementation |
| ---------------- | -------------- |
| `skills` (multi-select) | `JOIN candidate_skills ON skill_id IN (...) GROUP BY candidate.id HAVING COUNT(DISTINCT skill_id) = N` — candidate must have **ALL** selected skills |
| `min_exp` / `max_exp` | `WHERE total_experience_years BETWEEN min AND max` |
| `domain` | `WHERE domain_id = ?` |
| `notice_period_max` | `WHERE notice_period_days <= ?` |
| `work_mode` | `WHERE work_mode_preference = ?` |
| `location` | `WHERE current_location ILIKE '%value%'` |
| `source` | `WHERE source = ?` |
| `seniority` | Derived from `total_experience_years` ranges or explicit seniority column |
| `search` (text) | `WHERE search_vector @@ plainto_tsquery('english', ?)` on `candidate_resumes`, ranked by `ts_rank` |
| `stage` | `WHERE stage = ?` |

All filter params are optional, combined with **AND** logic, paginated (default 20). Default sort: `match_score` desc when viewing candidates for a specific requisition; `created_at` desc otherwise.

---

## 11. Concurrency Model

The system targets up to **10 concurrent HR users**. Concurrency is handled natively by Node.js's async event loop + multiple workers — no additional infrastructure.

| Scenario | How it is handled |
| -------- | ----------------- |
| 10 HRs using the dashboard simultaneously | Nginx distributes requests across Node workers (PM2 cluster). Each request handled independently and asynchronously. |
| Multiple HRs uploading resumes at the same time | Each file upload is a separate independent request. Node async I/O means storage, LLM calls, and DB writes for different requests run concurrently without blocking each other. |
| Two HRs upload the same candidate simultaneously | Application-level check runs first (Datagraph). `UNIQUE` constraint on `candidates.email` guarantees only one insert succeeds even if both pass the app check; the second receives a constraint violation → `DUPLICATE_CANDIDATE`. |
| LLM API calls for skill extraction (concurrent) | Each upload triggers an async LLM call. 10 concurrent uploads → 10 async LLM calls in parallel. Total wait ≈ one call, not ten. |
| Scheduled Gmail job overlapping with HR uploads | The Flow Gmail job runs as a background step (worker/queue), not on the HTTP request workers. Both run independently. |

Worker formula: `(2 × CPU cores) + 1`. Recommended minimum: a 2-core VM → **5 workers**, comfortably handling 10 concurrent users given the async I/O nature of all operations.

> **Concurrency safeguards specific to Node:** the LLM/STT client must have a bounded concurrency limit (e.g. `p-limit`) so a burst of uploads cannot exhaust provider rate limits; DB access uses a connection pool sized to the worker count.

---

## 12. Security

- **Authentication:** all endpoints require a JWT via Supabase Auth; token validated on every request (Node middleware).
- **Authorization:** RBAC enforced at the route level (NestJS `RolesGuard`); HR and DM have different permission sets (§4.8).
- **Sensitive fields:** `phone`, `current_ctc`, `expected_ctc` encrypted at rest via Postgres `pgcrypto` **or** application-level AES-256-GCM (§4.9).
- **Transport:** all data in transit encrypted via TLS (enforced by Nginx and Supabase).
- **Webhook integrity:** Twilio webhook **signature verified** on every inbound call before processing (`twilio.validateRequest`).
- **File access:** resume files in Supabase Storage are accessed only via **short-lived pre-signed URLs** generated per request; files are not publicly accessible.
- **Audit:** `audit_logs` records all user actions with timestamps and IP addresses.
- **No candidate-facing endpoints:** the system is entirely internal.
- **Secrets:** all credentials (Supabase keys, JWT secret, Twilio, LLM/STT keys, Gmail/Calendar service-account, encryption key) live in environment variables / a secrets manager — never in source.
- **Input validation:** all request bodies validated (Zod) before any handler logic; LLM structured outputs validated against schema before persistence.
- **Prompt-injection consideration (LLM):** resume text is untrusted input. Agent LLM nodes must treat resume/transcript content as **data**, never as instructions; system prompts are fixed and never concatenate raw candidate text into the instruction channel.

---

## 13. Non-Functional Requirements

| Category | Requirement |
| -------- | ----------- |
| Performance | List/profile endpoints respond < 500 ms p95 (excluding LLM/STT). Synchronous skill extraction completes in ~2–3 s. |
| Availability | Single-VM target; Supabase provides managed DB/storage uptime. Flow steps are durable + retryable. |
| Scalability | Pagination + per-requisition scoring keep response times constant as the pool grows to thousands. `pgvector` and Elasticsearch reserved for future scale (§16). |
| Reliability | Async work (transcription/analysis/notification) is retryable via Flow; no silent fire-and-forget loss. DB constraints guarantee integrity under concurrency. |
| Observability | Structured logs (`pino`); LangGraph run traces + Flow run dashboard; LLM token/cost logging per agent. |
| Data integrity | All uniqueness rules backed by DB constraints (§4.11); audit + analytics logs append-only. |
| Idempotency | Gmail ingestion idempotent via `gmail_message_id` UNIQUE; Twilio webhook idempotent via `twilio_call_sid`. |
| Internationalization | CTC in INR; timestamps in UTC. |

---

## 14. Infrastructure & Cost (Estimate)

| Service | Cost |
| ------- | ---- |
| Supabase (DB + storage + auth) | Free tier to start; paid ~$25/month for 8 GB DB, 100 GB storage. |
| VM for Node + Nginx | Hetzner CX21 (2 vCPU, 4 GB): ~€4.51/month. Railway/Render: ~$7/month. |
| Twilio (per screening call) | ~$0.013/min outbound. 100 calls/month @ 5 min avg ≈ ~$6.50/month. |
| LLM (skill extraction + analysis) | Claude — extraction on Sonnet 4.6 / Haiku 4.5 is cents per resume; ~$1–5/month at 500 resumes/month. Interview analysis on Opus 4.8 ($5/$25 per 1M tokens) is the main LLM cost driver. |
| Transcription (STT) | Whisper API ~$0.006/min; Deepgram/AssemblyAI comparable. 100 interviews @ 45 min avg ≈ ~$27/month. |
| Flow (Inngest) | Free/low tier sufficient at this volume; or self-host BullMQ on the same VM (Redis). |
| **Total estimated** | **~$40–80/month** for full operation at 10-HR team scale (model choice for analysis is the main variable). |

> Cost note: choosing Opus 4.8 only for interview analysis (the few-per-day, high-value calls) and Sonnet/Haiku for the high-volume extraction calls keeps the LLM bill close to the original estimate while improving quality.

---

## 15. Future Scope

- Naukri & LinkedIn API integration for direct resume import into the **Agent 1** pipeline.
- **Semantic vector search** using `pgvector` (Postgres extension — no new service) for LLM-based candidate matching beyond keyword search. (The Datagraph layer reserves a `vector` column path.)
- Candidate portal for self-service status updates (requires public-facing auth).
- Automated offer-letter generation + e-signature integration.
- WhatsApp notifications via Twilio for candidate communication.
- Elasticsearch migration if full-text search performance degrades at high resume volumes.
- **Agentic enhancements (enabled by LangGraph):** a supervisor/coordinator graph that routes a new candidate end-to-end (intake → score → recommend screening) and a human-in-the-loop approval node for auto-screening recommendations.

---

## 16. Requirements Traceability (Summary)

| Source section (product-req) | TRD section | Status |
| ---------------------------- | ----------- | ------ |
| 1. Purpose & Scope | §1 | Preserved |
| 2. Users & Roles | §2 | Preserved |
| 3. System Overview | §3 | Ported to Node.js |
| 4. Design Principles (4.1–4.13) | §4 (REQ-DP-1..13) | Preserved; Flow/Datagraph mapped |
| 5. Architecture Components | §5 | Ported (Nginx/Node/Supabase/Flow) |
| 6. Data Entry Points | §6 | Preserved |
| 7. Agents (1–7) | §7 | Re-implemented as LangGraph state graphs |
| 8. API Reference | §8 | Preserved verbatim |
| 9. Database Schema (9.1–9.19) | §9 | Preserved verbatim (Datagraph/Drizzle) |
| 10. Candidate Filtering | §10 | Preserved |
| 11. Concurrency Model | §11 | Ported to Node workers |
| 12. Security | §12 | Preserved + LLM hardening |
| 13. Infrastructure & Cost | §14 | Ported (Node + Claude/STT) |
| 14. Future Scope | §15 | Preserved + agentic additions |

---

## 17. Open Items / Decisions for the Team

These items are interpretations made by this TRD and should be confirmed:

1. **API framework:** NestJS (assumed) vs Fastify. NestJS recommended for clean RBAC guards + DI; Fastify if minimal footprint is preferred.
2. **Flow engine:** Inngest (assumed, durable + cron + UI) vs BullMQ + node-cron (self-hosted, one fewer external dependency).
3. **STT provider:** Whisper API vs Deepgram vs AssemblyAI (Deepgram/AssemblyAI add diarization, valuable for interview transcripts).
4. **Encryption approach:** Postgres `pgcrypto` (DB-side) vs application-level AES-256-GCM (key never in DB). App-level recommended for stronger separation.
5. **"Datagraph" / "Flow" naming:** confirm these map to (Drizzle data layer) and (Inngest workflow layer) as defined in §0 — adjust tool choices if the team has specific products in mind.

_End of Document._
