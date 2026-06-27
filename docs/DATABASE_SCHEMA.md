# Database Schema Reference — Recruitment System

A complete reference for the application database: every table, the purpose of every column,
all primary and foreign keys, and which API routes / AI agents read and write each table.

> Generated from the live ORM models in `backend/app/models/`. If a model changes, update this file.

---

## 1. Stack & conventions

| Aspect | Detail |
|--------|--------|
| ORM | SQLAlchemy 2.x (`DeclarativeBase` via `app.database.base.Base`) |
| Database | PostgreSQL 16 |
| Migrations | Alembic (`backend/alembic/versions/`) |
| Engine / session | `backend/app/database/base.py` — `create_engine` (pool_size=10, max_overflow=20), `SessionLocal`, `get_db()` FastAPI dependency |
| Connection string | `backend/app/config.py` → `database_url` (`postgresql+psycopg2://…`) |
| Model files | `backend/app/models/{org,skill,candidate,requisition,interview,logs,integration}.py` |
| Enums | `backend/app/models/enums.py` (member name == stored value) |
| Column factories | `backend/app/models/common.py` |

**Conventions applied to every table** (from `common.py`):

- **Primary key** — `id` is `UUID` (`primary_key=True`, `default=uuid.uuid4`). All 21 tables use this.
- **`created_at`** — `TIMESTAMPTZ NOT NULL`, `server_default = now()`.
- **`updated_at`** — `TIMESTAMPTZ NOT NULL`, `server_default = now()`, `onupdate = now()`.
- **Foreign keys** (`fk_col`) — UUID. **ON DELETE behavior is derived from nullability:**
  - nullable FK → **`ON DELETE SET NULL`**
  - non-nullable FK → **`ON DELETE CASCADE`**
- **At-rest encryption** (AES-256-GCM via `EncryptedString`/`EncryptedInt`, key from env not DB):
  `candidates.phone`, `candidates.current_ctc`, `candidates.expected_ctc`,
  `integration_credentials.refresh_token`, `integration_credentials.access_token`.

**21 tables**, grouped by model file:

| File | Tables |
|------|--------|
| `org.py` | `users`, `domains`, `departments` |
| `skill.py` | `skills`, `skill_aliases`, `candidate_skills` |
| `candidate.py` | `candidates`, `candidate_resumes`, `candidate_detail_requests` |
| `requisition.py` | `requisitions`, `requisition_skills`, `job_applications`, `candidate_scores` |
| `interview.py` | `call_logs`, `interviews`, `interview_feedback` |
| `logs.py` | `analytics_events`, `audit_logs`, `pipeline_status_reasons`, `application_status_history` |
| `integration.py` | `integration_credentials` |

---

## 2. AI agents and the tables they touch

All agents live in `backend/app/agents/` and are orchestrated as LangGraph state machines.

| # | Agent (file) | Reads | Writes |
|---|--------------|-------|--------|
| 1 | Resume Intake (`resume_intake.py`) | candidates, candidate_resumes, skills, skill_aliases | candidates, candidate_resumes, candidate_skills, skills, skill_aliases, analytics_events |
| 2 | Resume Scoring (`resume_scoring.py`) | candidates, requisitions, candidate_skills, requisition_skills, job_applications | candidate_scores, job_applications, application_status_history, analytics_events |
| 3 | Telephonic Screening (`telephonic_screening.py`) | candidates, requisitions, call_logs, job_applications | call_logs, job_applications, application_status_history, analytics_events |
| 4 | Detail Collection (`detail_collection.py`) | candidates, candidate_detail_requests | candidate_detail_requests, candidates, analytics_events |
| 5 | Interview Scheduling (`interview_scheduling.py`) | candidates, users, requisitions, job_applications | interviews, job_applications, application_status_history, analytics_events |
| 6 | Interview Analysis (`interview_analysis.py`) | interviews | interviews, interview_feedback, analytics_events |
| 7 | Feedback Collection (`feedback_collection.py`) | interviews, users, interview_feedback | interview_feedback, analytics_events |
| — | Analytics (`analytics.py`) | candidates, job_applications, call_logs, interviews, interview_feedback, requisitions, candidate_scores, analytics_events | *(read-only)* |

Event writes route through `backend/app/core/events.py` (`log_event` → `analytics_events`,
`log_audit` → `audit_logs`).

---

## 3. Table details

### 3.1 `users` — `org.py`
Application accounts (recruiters, delivery managers, admins) and interviewers; backs login and role-based access.

- **PK:** `id`
- **FKs:** none (referenced *by* most other tables)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Unique user id |
| `name` | String(150) | NOT NULL | Display name |
| `email` | String(255) | UNIQUE, INDEXED, NOT NULL | Login identifier |
| `role` | enum `user_role` | NOT NULL | Access level: `HR`, `DELIVERY_MANAGER`, `ADMIN` |
| `password_hash` | String(255) | nullable | Bcrypt hash for local-dev login |
| `is_interviewer` | Boolean | NOT NULL, default `False` | Eligible to be assigned to interviews |
| `is_active` | Boolean | NOT NULL, default `True` | Soft enable/disable |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Timestamps |

**Used by:** `core/auth.py` (authenticate login); `routes/auth.py`, `routes/users.py` (create/list users & interviewers); `interview_scheduling` & `feedback_collection` agents (resolve interviewer email).

---

### 3.2 `domains` — `org.py`
Reference list of domains/practices (e.g. Java, DevOps). Used to classify candidates and requisitions.

- **PK:** `id` · **FKs:** none

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Domain id |
| `name` | String(100) | UNIQUE, NOT NULL | Domain name |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Writes:** seed data only. **Reads:** `routes/meta.py` (dropdowns); candidate & requisition filters.

---

### 3.3 `departments` — `org.py`
Organizational units that requisitions belong to.

- **PK:** `id` · **FKs:** none

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Department id |
| `name` | String(100) | UNIQUE, NOT NULL | Department name |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Writes:** seed data only. **Reads:** `routes/meta.py`; requisition filters.

---

### 3.4 `skills` — `skill.py`
Canonical skill registry. Recognized skills are admin-verified; unknown skills extracted from resumes are auto-created as unverified pending review.

- **PK:** `id` · **FKs:** none

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Skill id |
| `name` | String(100) | UNIQUE, NOT NULL | Canonical skill name |
| `category` | enum `skill_category` | NOT NULL, default `TOOL` | `PROGRAMMING_LANGUAGE`, `FRAMEWORK`, `CLOUD`, `DATABASE`, `TOOL`, `DOMAIN_SKILL`, `SOFT_SKILL` |
| `is_verified` | Boolean | NOT NULL, default `False` | `False` = auto-created by LLM, awaiting admin review |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Relationships:** `aliases` → `skill_aliases` (cascade delete-orphan).
**Writes:** `agents/common.normalize_skill` (auto-create unknown skill); `routes/skills.py` (admin create/verify).
**Reads:** `routes/skills.py`; `resume_scoring` (match against requirements).

---

### 3.5 `skill_aliases` — `skill.py`
Maps skill-name variants (e.g. "JS", "node") to a canonical `skills` row, enabling robust matching from resume text.

- **PK:** `id`
- **FK:** `skill_id` → `skills.id` — **ON DELETE CASCADE** (not nullable)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Alias id |
| `skill_id` | UUID | FK → `skills.id`, CASCADE | Canonical skill |
| `alias` | String(100) | UNIQUE, INDEXED, NOT NULL | Variant spelling (stored lowercase) |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Relationships:** `skill` → `skills` (back_populates `aliases`).
**Writes:** `agents/common.normalize_skill` / `_ensure_alias`; `routes/skills.py` (add aliases).
**Reads:** `agents/common.normalize_skill` (resolve alias → skill_id).

---

### 3.6 `candidate_skills` — `skill.py`
Junction table linking a candidate to a skill with proficiency and experience.

- **PK:** `id`
- **FKs:** `candidate_id` → `candidates.id` (**CASCADE**), `skill_id` → `skills.id` (**CASCADE**)
- **Unique:** (`candidate_id`, `skill_id`) — `uq_candidate_skill`
- **Indexes:** `ix_candidate_skills_candidate_id`, `ix_candidate_skills_skill_id`

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Row id |
| `candidate_id` | UUID | FK → `candidates.id`, CASCADE | Owning candidate |
| `skill_id` | UUID | FK → `skills.id`, CASCADE | Linked skill |
| `proficiency_level` | enum `proficiency_level` | nullable | `BEGINNER`, `INTERMEDIATE`, `EXPERT` |
| `years_of_experience` | Float | nullable | Per-skill years |
| `is_verified` | Boolean | NOT NULL, default `False` | `False` = LLM-extracted; `True` = HR-confirmed |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Writes:** `resume_intake.persist` (auto-link extracted skills); `routes/candidates.confirm_skills` (verify / delete false positives / add).
**Reads:** `resume_scoring.compute` (skill match).

---

### 3.7 `candidates` — `candidate.py`
The central candidate profile. Holds identity, contact, current employment, preferences, AI summary, and blacklist state.

- **PK:** `id`
- **FKs:**
  - `domain_id` → `domains.id` — **SET NULL** (nullable), INDEXED
  - `uploaded_by` → `users.id` — **SET NULL**
  - `blacklist_reason_id` → `pipeline_status_reasons.id` — **SET NULL**
  - `blacklisted_by` → `users.id` — **SET NULL**

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Candidate id |
| `full_name` | String(200) | NOT NULL | Candidate name |
| `email` | String(255) | UNIQUE, INDEXED, NOT NULL | Contact + **dedup key** |
| `phone` | EncryptedString | nullable, **encrypted** | Phone number |
| `current_location` | String(200) | nullable | Location |
| `linkedin_url` | String(500) | nullable | LinkedIn profile |
| `portfolio_url` | String(500) | nullable | Portfolio / GitHub |
| `domain_id` | UUID | FK → `domains.id`, SET NULL, INDEXED | Domain classification |
| `total_experience_years` | Float | nullable, INDEXED | Total experience |
| `current_company` | String(200) | nullable | Current employer |
| `current_designation` | String(200) | nullable | Current title |
| `current_ctc` | EncryptedInt | nullable, **encrypted** | Current compensation |
| `expected_ctc` | EncryptedInt | nullable, **encrypted** | Expected compensation |
| `notice_period_days` | Integer | nullable, INDEXED | Notice period |
| `availability_date` | Date | nullable | Earliest availability |
| `work_mode_preference` | enum `work_mode` | nullable, INDEXED | `REMOTE`, `HYBRID`, `ONSITE` |
| `shift_preference` | enum `shift_preference` | nullable | `DAY`, `NIGHT`, `FLEXIBLE` |
| `source` | enum `candidate_source` | NOT NULL, INDEXED | `LINKEDIN`, `NAUKRI`, `EMAIL`, `REFERRAL`, `GMAIL`, `OTHER` |
| `source_detail` | Text | nullable | Free-text source note |
| `uploaded_by` | UUID | FK → `users.id`, SET NULL | User who added the candidate |
| `custom_metadata` | JSONB | NOT NULL, default `{}` | Flexible extra fields |
| `ai_summary` | Text | nullable | LLM-generated profile summary |
| `is_blacklisted` | Boolean | NOT NULL, default `False`, INDEXED | Blacklist flag |
| `blacklist_reason_id` | UUID | FK → `pipeline_status_reasons.id`, SET NULL | Reason category |
| `blacklisted_by` | UUID | FK → `users.id`, SET NULL | Who blacklisted |
| `blacklisted_at` | TIMESTAMPTZ | nullable | When blacklisted |
| `blacklist_note` | Text | nullable | Free-text reason |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Timestamps |

**Relationships:** `domain`; `skills` (`candidate_skills`, cascade); `resumes` (`candidate_resumes`, cascade); `detail_requests` (`candidate_detail_requests`, cascade).
**Writes:** `resume_intake.persist` (create); `routes/candidates` (update / blacklist / unblacklist); `detail_collection._apply_extraction` (fill CTC/notice/availability from email replies).
**Reads:** candidate list/detail routes; `resume_scoring`, `telephonic_screening`, `interview_scheduling`, `detail_collection`, `analytics`; Gmail intake.

---

### 3.8 `candidate_resumes` — `candidate.py`
Versioned resume store (intake keeps up to ~3 versions). Holds parsed text, full-text search vector, and Gmail intake idempotency key.

- **PK:** `id`
- **FKs:** `candidate_id` → `candidates.id` (**CASCADE**, INDEXED), `uploaded_by` → `users.id` (**SET NULL**)
- **Indexes:** `ix_resume_search_vector` (GIN on `search_vector`); `uq_resume_gmail_message_id` (UNIQUE partial, `WHERE gmail_message_id IS NOT NULL`)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Resume version id |
| `candidate_id` | UUID | FK → `candidates.id`, CASCADE, INDEXED | Owning candidate |
| `file_url` | String(1000) | nullable | Stored original file |
| `redacted_file_url` | String(1000) | nullable | PII-redacted copy |
| `parsed_text` | Text | nullable | Extracted resume text |
| `search_vector` | TSVECTOR | GENERATED (persisted) from `parsed_text` | Full-text search index source |
| `gmail_message_id` | String(200) | UNIQUE (partial) | Gmail intake idempotency |
| `is_latest` | Boolean | NOT NULL, default `True` | Marks the current version |
| `uploaded_by` | UUID | FK → `users.id`, SET NULL | Uploader |
| `uploaded_at` | TIMESTAMPTZ | NOT NULL | Upload time |

**Relationships:** `candidate` (back_populates `resumes`).
**Writes:** `resume_intake.persist` (flip prior versions `is_latest=False`, insert new).
**Reads:** `routes/candidates.get_resume_url`; intake dedup / version count.

---

### 3.9 `candidate_detail_requests` — `candidate.py`
Tracks an auto-sent email asking a candidate for logistics fields their resume omitted (CTC, notice, availability, shift/work-mode), and the parsed reply.

- **PK:** `id`
- **FK:** `candidate_id` → `candidates.id` (**CASCADE**, INDEXED)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Request id |
| `candidate_id` | UUID | FK → `candidates.id`, CASCADE, INDEXED | Target candidate |
| `gmail_thread_id` | String(200) | nullable, INDEXED | Matches the candidate's reply to this request |
| `original_message_id` | String(998) | nullable | RFC822 Message-ID (for `In-Reply-To`) |
| `sent_message_id` | String(200) | nullable | Id of the email we sent |
| `requested_fields` | JSONB | NOT NULL, default `[]` | Which fields were asked for |
| `status` | enum `detail_request_status` | NOT NULL, default `SENT`, INDEXED | `SENT`, `RECEIVED`, `FAILED` |
| `sent_at` | TIMESTAMPTZ | nullable | When the request was sent |
| `received_at` | TIMESTAMPTZ | nullable | When the reply arrived |
| `reply_raw_text` | Text | nullable | Raw reply body |
| `parsed_values` | JSONB | nullable | Parsed field values from reply |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Timestamps |

**Relationships:** `candidate` (back_populates `detail_requests`).
**Writes/Reads:** `detail_collection` agent (`request_details`, `ingest_detail_reply`, `_latest_request`).

---

### 3.10 `requisitions` — `requisition.py`
Job openings. Stores the role spec, requirements, budget, and ownership.

- **PK:** `id`
- **FKs:** `domain_id` → `domains.id` (**SET NULL**, INDEXED), `department_id` → `departments.id` (**SET NULL**), `created_by` → `users.id` (**SET NULL**), `hiring_manager_id` → `users.id` (**SET NULL**)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Requisition id |
| `title` | String(300) | NOT NULL | Job title |
| `description` | Text | nullable | Job description |
| `domain_id` | UUID | FK → `domains.id`, SET NULL, INDEXED | Domain |
| `department_id` | UUID | FK → `departments.id`, SET NULL | Department |
| `seniority_level` | enum `seniority_level` | nullable | `INTERN`, `JUNIOR`, `MID`, `SENIOR`, `LEAD`, `MANAGER`, `DIRECTOR` |
| `location` | String(200) | nullable | Location |
| `work_mode` | enum `work_mode` | nullable | `REMOTE`, `HYBRID`, `ONSITE` |
| `shift_timing` | enum `shift_preference` | nullable | `DAY`, `NIGHT`, `FLEXIBLE` |
| `min_experience_years` | Float | nullable | Min experience |
| `max_experience_years` | Float | nullable | Max experience |
| `min_budget_ctc` | Integer | nullable | Budget floor |
| `max_budget_ctc` | Integer | nullable | Budget ceiling |
| `number_of_openings` | Integer | NOT NULL, default `1` | Headcount |
| `status` | enum `requisition_status` | NOT NULL, default `OPEN`, INDEXED | `DRAFT`, `OPEN`, `ON_HOLD`, `CLOSED`, `CANCELLED` |
| `created_by` | UUID | FK → `users.id`, SET NULL | Creator |
| `hiring_manager_id` | UUID | FK → `users.id`, SET NULL | Hiring manager |
| `target_close_date` | Date | nullable | Target fill date |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Timestamps |

**Relationships:** `domain`, `department`, `skills` (`requisition_skills`, cascade).
**Writes:** `routes/requisitions` (create/update).
**Reads:** `routes/requisitions` (list/detail); `resume_scoring` (open reqs); `telephonic_screening` (call script); `analytics` (open-req health).

---

### 3.11 `requisition_skills` — `requisition.py`
Skill requirements for a requisition.

- **PK:** `id`
- **FKs:** `requisition_id` → `requisitions.id` (**CASCADE**), `skill_id` → `skills.id` (**CASCADE**)
- **Unique:** (`requisition_id`, `skill_id`) — `uq_requisition_skill`

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Row id |
| `requisition_id` | UUID | FK → `requisitions.id`, CASCADE | Owning requisition |
| `skill_id` | UUID | FK → `skills.id`, CASCADE | Required skill |
| `is_mandatory` | Boolean | NOT NULL, default `True` | Must-have vs nice-to-have |
| `minimum_years` | Float | nullable | Minimum years required |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Relationships:** `requisition` (back_populates `skills`), `skill`.
**Writes:** `routes/requisitions` (create/update). **Reads:** `resume_scoring.compute`.

---

### 3.12 `job_applications` — `requisition.py`
Links a candidate to a requisition and tracks their pipeline stage. One application per candidate–requisition pair.

- **PK:** `id`
- **FKs:** `candidate_id` → `candidates.id` (**CASCADE**, INDEXED), `requisition_id` → `requisitions.id` (**CASCADE**, INDEXED), `created_by` → `users.id` (**SET NULL**)
- **Unique:** (`candidate_id`, `requisition_id`) — `uq_application_candidate_requisition`

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Application id |
| `candidate_id` | UUID | FK → `candidates.id`, CASCADE, INDEXED | Candidate |
| `requisition_id` | UUID | FK → `requisitions.id`, CASCADE, INDEXED | Requisition |
| `status` | enum `application_status` | NOT NULL, default `NEW`, INDEXED | `NEW`, `SCREENING`, `SHORTLISTED`, `INTERVIEW_SCHEDULED`, `OFFERED`, `REJECTED`, `WITHDRAWN`, `HIRED` |
| `match_score` | Float | nullable, INDEXED | Cached ranking score |
| `rejection_reason` | Text | nullable | Reason text if rejected |
| `notes` | Text | nullable | Recruiter notes |
| `created_by` | UUID | FK → `users.id`, SET NULL | Creator |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Timestamps |

**Writes:** `resume_scoring.persist` (create on match); `telephonic_screening._move_application` & `interview_scheduling` (advance status); `routes/candidates.blacklist_candidate` (set `WITHDRAWN`).
**Reads:** candidate filters; `analytics` (funnel).
Status changes are mirrored to `application_status_history`.

---

### 3.13 `candidate_scores` — `requisition.py`
Algorithmic match score breakdown between a candidate and a requisition (deterministic heuristics, no LLM).

- **PK:** `id`
- **FKs:** `candidate_id` → `candidates.id` (**CASCADE**, INDEXED), `requisition_id` → `requisitions.id` (**CASCADE**, INDEXED)
- **Unique:** (`candidate_id`, `requisition_id`) — `uq_score_candidate_requisition`

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Score id |
| `candidate_id` | UUID | FK → `candidates.id`, CASCADE, INDEXED | Candidate |
| `requisition_id` | UUID | FK → `requisitions.id`, CASCADE, INDEXED | Requisition |
| `total_score` | Float | NOT NULL, default `0.0` | Overall match score |
| `skills_score` | Float | NOT NULL, default `0.0` | Skill-match component |
| `experience_score` | Float | NOT NULL, default `0.0` | Experience-fit component |
| `skills_depth_score` | Float | NOT NULL, default `0.0` | Depth-of-skill component |
| `location_score` | Float | NOT NULL, default `0.0` | Location-fit component |
| `notice_period_score` | Float | NOT NULL, default `0.0` | Notice-period component |
| `scoring_version` | String(20) | NOT NULL, default `"v1"` | Scoring algorithm version |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Writes:** `resume_scoring.persist` (upsert). **Reads:** candidate ranking/serialization.

---

### 3.14 `call_logs` — `interview.py`
Telephonic screening call records (Twilio + STT + LLM Q&A scoring).

- **PK:** `id`
- **FKs:** `candidate_id` → `candidates.id` (**CASCADE**, INDEXED), `requisition_id` → `requisitions.id` (**SET NULL**, INDEXED), `initiated_by` → `users.id` (**SET NULL**)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Call id |
| `candidate_id` | UUID | FK → `candidates.id`, CASCADE, INDEXED | Candidate called |
| `requisition_id` | UUID | FK → `requisitions.id`, SET NULL, INDEXED | Related requisition |
| `initiated_by` | UUID | FK → `users.id`, SET NULL | Who started the call |
| `twilio_call_sid` | String(100) | UNIQUE, nullable | Twilio call identifier |
| `status` | enum `call_status` | NOT NULL, default `INITIATED` | `INITIATED`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `NO_ANSWER`, `CALLBACK_REQUESTED` |
| `recording_url` | String(1000) | nullable | Call recording |
| `transcript` | Text | nullable | Full transcript |
| `screening_answers` | JSONB | nullable | `[{question, answer, ai_comment, ai_rating}]` |
| `ai_score` | Float | nullable | Overall screening score (0–1) |
| `question_set` | JSONB | nullable | Questions asked |
| `duration_seconds` | Integer | nullable | Call length |
| `called_at` | TIMESTAMPTZ | NOT NULL | Call start |
| `completed_at` | TIMESTAMPTZ | nullable | Call end |

**Writes:** `telephonic_screening` (`persist_initiated`, `persist_completed`).
**Reads:** `routes/screening.list_calls`; screening agent (live-transcript checks).

---

### 3.15 `interviews` — `interview.py`
Scheduled interviews plus AI analysis of the recording.

- **PK:** `id`
- **FKs:** `candidate_id` → `candidates.id` (**CASCADE**, INDEXED), `requisition_id` → `requisitions.id` (**SET NULL**, INDEXED), `interviewer_id` → `users.id` (**SET NULL**), `created_by` → `users.id` (**SET NULL**)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Interview id |
| `candidate_id` | UUID | FK → `candidates.id`, CASCADE, INDEXED | Candidate |
| `requisition_id` | UUID | FK → `requisitions.id`, SET NULL, INDEXED | Requisition |
| `interviewer_id` | UUID | FK → `users.id`, SET NULL | Assigned interviewer |
| `round_number` | Integer | NOT NULL, default `1` | Round sequence |
| `round_type` | enum `round_type` | NOT NULL | `L1`, `L2`, `L3`, `HR`, `FINAL`, `TECHNICAL`, `CULTURAL` |
| `status` | enum `interview_status` | NOT NULL, default `SCHEDULED` | `SCHEDULED`, `COMPLETED`, `CANCELLED`, `NO_SHOW`, `RESCHEDULED` |
| `scheduled_at` | TIMESTAMPTZ | nullable | Scheduled time |
| `meeting_link` | String(500) | nullable | Video meeting URL |
| `calendar_event_id` | String(200) | nullable | Calendar event reference |
| `recording_url` | String(1000) | nullable | Interview recording |
| `transcript` | Text | nullable | Transcript |
| `ai_analysis` | JSONB | nullable | LLM analysis payload |
| `ai_overall_rating` | Float | nullable | AI rating (0.0–1.0) |
| `analysis_completed_at` | TIMESTAMPTZ | nullable | When analysis finished |
| `created_by` | UUID | FK → `users.id`, SET NULL | Creator |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Timestamps |

**Relationships:** `interviewer` → `users`; `feedback` → `interview_feedback` (1:1, cascade).
**Writes:** `interview_scheduling.create_interview`; `routes/interviews.update`; `interview_analysis.persist`.
**Reads:** `routes/interviews` (list/detail); `feedback_collection`.

---

### 3.16 `interview_feedback` — `interview.py`
One-to-one with `interviews`: holds both the AI-generated analysis (Agent 5) and the human interviewer's structured feedback (Agent 6).

- **PK:** `id`
- **FKs:** `interview_id` → `interviews.id` (**CASCADE**, INDEXED), `submitted_by` → `users.id` (**SET NULL**)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Feedback id |
| `interview_id` | UUID | FK → `interviews.id`, CASCADE, INDEXED | Parent interview (1:1) |
| `submitted_by` | UUID | FK → `users.id`, SET NULL | Interviewer who submitted |
| `ai_summary` | Text | nullable | AI summary |
| `ai_strengths` | Text | nullable | AI-identified strengths |
| `ai_concerns` | Text | nullable | AI-identified concerns |
| `ai_qa_breakdown` | JSONB | nullable | Per-question AI breakdown |
| `human_summary` | Text | nullable | Interviewer summary |
| `human_strengths` | Text | nullable | Interviewer strengths |
| `human_concerns` | Text | nullable | Interviewer concerns |
| `technical_rating` | Integer | nullable | Technical score |
| `communication_rating` | Integer | nullable | Communication score |
| `problem_solving_rating` | Integer | nullable | Problem-solving score |
| `culture_fit_rating` | Integer | nullable | Culture-fit score |
| `overall_rating` | Integer | nullable | Overall score |
| `recommendation` | enum `recommendation` | nullable | `STRONG_YES`, `YES`, `MAYBE`, `NO`, `STRONG_NO` |
| `is_submitted` | Boolean | NOT NULL, default `False` | Human feedback submitted? |
| `submitted_at` | TIMESTAMPTZ | nullable | Submission time |
| `last_updated_at` | TIMESTAMPTZ | nullable | Last edit time |

**Relationships:** `interview` (back_populates `feedback`).
**Writes:** `interview_analysis.persist` (seed AI fields); `feedback_collection` (create draft, submit human feedback).
**Reads:** `routes/interviews.get_interview_feedback`.

---

### 3.17 `analytics_events` — `logs.py` *(append-only, REQ-DP-13)*
Immutable event stream powering dashboards/funnels.

- **PK:** `id`
- **FKs:** `candidate_id` → `candidates.id` (**SET NULL**, INDEXED), `requisition_id` → `requisitions.id` (**SET NULL**, INDEXED), `triggered_by` → `users.id` (**SET NULL**)
- **Index:** `ix_analytics_events_occurred_at`

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Event id |
| `event_type` | String(100) | NOT NULL, INDEXED | e.g. `CANDIDATE_ADDED`, `SCORE_COMPUTED`, `CALL_COMPLETED`, `INTERVIEW_SCHEDULED`, `ANALYSIS_COMPLETED`, `FEEDBACK_SUBMITTED`, `STATUS_CHANGED`, `HIRED`, `REJECTED`, `BLACKLISTED` |
| `candidate_id` | UUID | FK → `candidates.id`, SET NULL, INDEXED | Related candidate |
| `requisition_id` | UUID | FK → `requisitions.id`, SET NULL, INDEXED | Related requisition |
| `triggered_by` | UUID | FK → `users.id`, SET NULL | Acting user (if any) |
| `event_metadata` | JSONB | nullable | DB column name is `metadata` |
| `occurred_at` | TIMESTAMPTZ | NOT NULL, INDEXED | Event time |

**Writes:** `core/events.log_event` (emitted throughout the agent pipeline & routes).
**Reads:** `analytics` agent (aggregation).

---

### 3.18 `audit_logs` — `logs.py` *(append-only, REQ-DP-13)*
Who-did-what accountability trail.

- **PK:** `id`
- **FK:** `user_id` → `users.id` (**SET NULL**)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Log id |
| `user_id` | UUID | FK → `users.id`, SET NULL | Acting user |
| `action` | String(200) | NOT NULL | e.g. `UPLOADED_RESUME`, `CONFIRMED_SKILLS`, `BLACKLISTED_CANDIDATE`, `CREATED_REQUISITION`, `SCHEDULED_INTERVIEW`, `STARTED_SCREENING_CALL`, `CREATED_USER` |
| `entity_type` | String(100) | nullable | Affected entity type |
| `entity_id` | String(100) | nullable | Affected entity id |
| `audit_metadata` | JSONB | nullable | DB column name is `metadata` |
| `ip_address` | String(50) | nullable | Caller IP |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Writes:** `core/events.log_audit` (called by candidate/requisition/interview/auth/screening routes).

---

### 3.19 `pipeline_status_reasons` — `logs.py`
Reference vocabulary for status-change / rejection / blacklist reasons.

- **PK:** `id` · **FKs:** none

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Reason id |
| `status` | String(50) | NOT NULL, INDEXED | Applies to which status/category (spans `application_status` values + extras like `DROPPED`, `L1_REJECTED`, `BLACKLISTED`) |
| `reason` | String(200) | NOT NULL | Human-readable reason |
| `is_active` | Boolean | NOT NULL, default `True` | Selectable in UI? |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp |

**Writes:** seed data only. **Reads:** `routes/meta.py`; referenced as FK by `candidates.blacklist_reason_id` and `application_status_history.reason_id`.

---

### 3.20 `application_status_history` — `logs.py`
Audit of every `job_applications` status transition.

- **PK:** `id`
- **FKs:** `application_id` → `job_applications.id` (**CASCADE**, INDEXED), `reason_id` → `pipeline_status_reasons.id` (**SET NULL**), `changed_by` → `users.id` (**SET NULL**)

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | History row id |
| `application_id` | UUID | FK → `job_applications.id`, CASCADE, INDEXED | Application |
| `from_status` | enum `application_status` | nullable | Previous status (null on first entry) |
| `to_status` | enum `application_status` | NOT NULL | New status |
| `reason_id` | UUID | FK → `pipeline_status_reasons.id`, SET NULL | Reason category |
| `reason_note` | Text | nullable | Free-text note |
| `changed_by` | UUID | FK → `users.id`, SET NULL | Who changed it |
| `changed_at` | TIMESTAMPTZ | NOT NULL | When |

**Writes:** `resume_scoring`, `telephonic_screening`, `interview_scheduling`, blacklist flow — on every status move.

---

### 3.21 `integration_credentials` — `integration.py`
Per-provider OAuth credentials (currently Gmail) so re-authorization is a one-time admin action rather than editing `.env`. One row per provider.

- **PK:** `id` · **FKs:** none

| Column | Type | Key / Constraints | Purpose |
|--------|------|-------------------|---------|
| `id` | UUID | PK | Row id |
| `provider` | String(50) | UNIQUE, INDEXED, NOT NULL | e.g. `"gmail"` |
| `auth_mode` | String(30) | nullable | e.g. `"oauth_db"` |
| `connected_email` | String(255) | nullable | Mailbox this credential reads |
| `refresh_token` | EncryptedString | nullable, **encrypted** | OAuth refresh token |
| `access_token` | EncryptedString | nullable, **encrypted** | Cached short-lived access token |
| `token_expiry` | TIMESTAMPTZ | nullable | Access-token expiry |
| `scopes` | Text | nullable | Space-delimited granted scopes |
| `disabled` | Boolean | NOT NULL, default `False` | Disabled on auth failure to stop retry/log spam |
| `last_error` | Text | nullable | Last auth/sync error |
| `last_synced_at` | TIMESTAMPTZ | nullable | Last successful poll |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Timestamps |

**Writes/Reads:** `integrations/gmail/client.py` (load / refresh / disable / upsert / disconnect); `routes/integrations_gmail.py` (OAuth callback, status).

---

## 4. Foreign-key relationship map

```
users ◄──────────────┬── candidates.uploaded_by / blacklisted_by      (SET NULL)
                      ├── candidate_resumes.uploaded_by                (SET NULL)
                      ├── requisitions.created_by / hiring_manager_id  (SET NULL)
                      ├── job_applications.created_by                  (SET NULL)
                      ├── call_logs.initiated_by                       (SET NULL)
                      ├── interviews.interviewer_id / created_by       (SET NULL)
                      ├── interview_feedback.submitted_by              (SET NULL)
                      ├── analytics_events.triggered_by                (SET NULL)
                      ├── audit_logs.user_id                           (SET NULL)
                      └── application_status_history.changed_by        (SET NULL)

domains ◄── candidates.domain_id (SET NULL) · requisitions.domain_id (SET NULL)
departments ◄── requisitions.department_id (SET NULL)

skills ◄── skill_aliases.skill_id (CASCADE)
        ◄── candidate_skills.skill_id (CASCADE)
        ◄── requisition_skills.skill_id (CASCADE)

candidates ◄── candidate_skills.candidate_id           (CASCADE)
            ◄── candidate_resumes.candidate_id          (CASCADE)
            ◄── candidate_detail_requests.candidate_id  (CASCADE)
            ◄── job_applications.candidate_id           (CASCADE)
            ◄── candidate_scores.candidate_id           (CASCADE)
            ◄── call_logs.candidate_id                  (CASCADE)
            ◄── interviews.candidate_id                 (CASCADE)
            ◄── analytics_events.candidate_id           (SET NULL)

requisitions ◄── requisition_skills.requisition_id     (CASCADE)
              ◄── job_applications.requisition_id       (CASCADE)
              ◄── candidate_scores.requisition_id       (CASCADE)
              ◄── call_logs.requisition_id              (SET NULL)
              ◄── interviews.requisition_id             (SET NULL)
              ◄── analytics_events.requisition_id       (SET NULL)

job_applications ◄── application_status_history.application_id (CASCADE)
interviews ◄── interview_feedback.interview_id (CASCADE, 1:1)
pipeline_status_reasons ◄── candidates.blacklist_reason_id (SET NULL)
                         ◄── application_status_history.reason_id (SET NULL)
```

---

## 5. Enum reference (`backend/app/models/enums.py`)

| Enum (Postgres type) | Values |
|----------------------|--------|
| `user_role` | HR, DELIVERY_MANAGER, ADMIN |
| `skill_category` | PROGRAMMING_LANGUAGE, FRAMEWORK, CLOUD, DATABASE, TOOL, DOMAIN_SKILL, SOFT_SKILL |
| `proficiency_level` | BEGINNER, INTERMEDIATE, EXPERT |
| `work_mode` | REMOTE, HYBRID, ONSITE |
| `shift_preference` | DAY, NIGHT, FLEXIBLE |
| `candidate_source` | LINKEDIN, NAUKRI, EMAIL, REFERRAL, GMAIL, OTHER |
| `detail_request_status` | SENT, RECEIVED, FAILED |
| `seniority_level` | INTERN, JUNIOR, MID, SENIOR, LEAD, MANAGER, DIRECTOR |
| `requisition_status` | DRAFT, OPEN, ON_HOLD, CLOSED, CANCELLED |
| `application_status` | NEW, SCREENING, SHORTLISTED, INTERVIEW_SCHEDULED, OFFERED, REJECTED, WITHDRAWN, HIRED |
| `call_status` | INITIATED, IN_PROGRESS, COMPLETED, FAILED, NO_ANSWER, CALLBACK_REQUESTED |
| `round_type` | L1, L2, L3, HR, FINAL, TECHNICAL, CULTURAL |
| `interview_status` | SCHEDULED, COMPLETED, CANCELLED, NO_SHOW, RESCHEDULED |
| `recommendation` | STRONG_YES, YES, MAYBE, NO, STRONG_NO |

`work_mode`, `shift_preference`, and `application_status` are shared SQLAlchemy enum instances so the Postgres `CREATE TYPE` is emitted exactly once.

---

## 6. Notes

- **Append-only tables:** `analytics_events` and `audit_logs` are never updated or deleted (compliance, REQ-DP-13).
- **`metadata` column name:** both `analytics_events.event_metadata` and `audit_logs.audit_metadata` map to a DB column literally named `metadata` (the Python attribute is renamed to avoid clashing with SQLAlchemy's reserved `metadata`).
- **Migration comment vs. reality:** the initial migration comments reference ~19 tables; the current model defines **21** (`candidate_detail_requests`, `application_status_history`, and `integration_credentials` were added later).
- **LLM-provider agnostic:** agents call a single client (`app/llm/client.py`) that resolves to Anthropic Claude or OpenAI based on env keys, and degrade gracefully when no key is set — the DB pipeline still runs.
