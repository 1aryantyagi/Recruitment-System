**RECRUITMENT PLATFORM**

# 1 Purpose & Scope

This document defines the complete architecture for an internal Applicant Tracking System (ATS). The platform is used exclusively by HR team members and Delivery Managers. Candidates do not have direct access to the system.

Resumes enter the system through three channels:

- Manual upload by HR team members via the HR Dashboard
- Automatic ingestion from a monitored Gmail inbox (every 5 minutes)
- Future scope: direct API integrations with LinkedIn, Naukri, and other portals

The system manages the complete hiring lifecycle: resume intake and skill extraction, job opening management, candidate scoring and ranking, telephonic screening, interview scheduling, AI-assisted interview analysis, feedback collection, and analytics reporting.

# 2 Users & Roles


| **Role**         | **Permissions**                                                                                                                               |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| HR               | Upload resumes, confirm extracted skills, create job openings, initiate screening calls, schedule interviews, submit feedback, view analytics |
| Delivery Manager | Create job openings, view and search candidates, view scored rankings, view interview feedback, view analytics                                |
| Admin            | Manage user accounts, manage skills master list, manage domains and departments, view audit logs                                              |
| Candidate        | No system access. Candidates are represented as data records only.                                                                            |


# 3 System Overview

The platform is architected as a lightweight, single-service backend built with FastAPI, deployed on a single VM, with all data persistence handled by Supabase (managed PostgreSQL and file storage). There is no message queue, no separate search cluster, and no additional managed services beyond Supabase and Twilio.


| **Component**                  | **Technology**                                                           |
| ------------------------------ | ------------------------------------------------------------------------ |
| Backend API                    | FastAPI (Python) with Uvicorn ASGI server                                |
| Reverse Proxy                  | Nginx                                                                    |
| Database                       | Supabase PostgreSQL (fully managed, no hosting required)                 |
| File Storage                   | Supabase Storage (resume files)                                          |
| Authentication                 | Supabase Auth (JWT-based, role-aware)                                    |
| Full-Text Search               | PostgreSQL tsvector (built into Supabase, no Elasticsearch needed)       |
| Skill Extraction               | LLM via API (OpenAI or equivalent) + dictionary normalisation            |
| Telephonic Screening           | Twilio (external SaaS, no hosting required)                              |
| Call / Interview Transcription | OpenAI Whisper API (external, no hosting required)                       |
| Scheduled Jobs                 | APScheduler (runs inside FastAPI process, no separate scheduler service) |
| Hosting                        | Single VM - 2 to 4 core (Railway, Render, or Hetzner VPS)                |


# 4 Design Principles

The following principles govern how every part of this system is built. Each principle states what it does and what problem it solves.

## 4.1 Pagination

All APIs that return a list of records are paginated. No API ever returns an unbounded list.

**Default page size:** 20 records

**Maximum page size:** 100 records

**Query parameters:** page (1-based) and limit

Every paginated response returns a standard envelope:

{ "data": ..., "total": 143, "page": 1, "limit": 20, "total_pages": 8 }

Solves: as the candidate pool grows to thousands, unpaginated list calls would overload the database, time out, and crash the browser. Pagination keeps every response fast and predictable regardless of data volume.

Applies to:

- GET /candidates
- GET /requisitions
- GET /requisitions/{id}/candidates
- GET /screening/{candidate_id}/calls
- GET /interviews/{candidate_id}
- Analytics event feed on GET /analytics/dashboard

## 4.2 Standard API Response Envelope

Every API in the system returns responses in one of three consistent structures regardless of which endpoint is called.


| **Response Type** | **Structure**                                                                                                              |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------- |
| List response     | { "data": ..., "total": N, "page": N, "limit": N, "total_pages": N }                                                       |
| Single object     | { "data": { ...object } }                                                                                                  |
| Error response    | { "error": { "code": "MACHINE_READABLE_CODE", "message": "Human readable message.", "detail": "optional extra context" } } |


Standard error codes used across the system:

- DUPLICATE_CANDIDATE - email already exists in candidates table
- RESUME_LIMIT_EXCEEDED - candidate already has maximum resume versions
- DUPLICATE_APPLICATION - candidate already linked to this requisition
- ACTIVE_CALL_EXISTS - screening call already in progress for this candidate
- UNAUTHORIZED - valid JWT but insufficient role for this endpoint
- NOT_FOUND - requested record does not exist

Solves: frontend developers and future integrations know exactly what shape every response takes. Error handling is consistent across the entire application rather than endpoint-by-endpoint.

## 4.3 Candidate Deduplication

Candidate email is the single unique identifier for every person in the system. No two candidate records can share the same email address.

Two layers of enforcement:

- Application layer: before any insert, the service queries candidates WHERE email = ? and rejects the request if a match is found, returning error code DUPLICATE_CANDIDATE with the existing candidate_id in the detail field so HR can navigate to the existing profile
- Database layer: unique constraint on candidates.email catches any concurrent inserts that both pass the application check simultaneously - only one insert succeeds, the other receives a constraint violation which the application translates into the same DUPLICATE_CANDIDATE error

Solves: prevents duplicate candidate records when multiple HRs upload resumes for the same person from different sources simultaneously. Keeps one canonical profile that accumulates all resume versions, scores, calls, and interviews over time.

**Gmail deduplication:** gmail_message_id stored on candidate_resumes prevents the same email attachment being processed twice across polling cycles

## 4.4 Resume Versioning

Uploading a new resume for an existing candidate never overwrites the previous file. A new row is inserted in candidate_resumes with is_latest = true and the previous version's is_latest is set to false.

**Maximum versions:** 3 per candidate. On the 4th upload attempt the system returns RESUME_LIMIT_EXCEEDED and prompts HR to update the existing record instead

**Latest version:** Always used for skill extraction, scoring, and search indexing

**Previous versions:** Retained and accessible from the candidate profile resume history tab

Solves: candidates update their CVs over time. HR needs to see the most current version while retaining history. Overwriting would lose prior versions permanently.

## 4.5 Synchronous Validation Before Any Write

All business rule checks execute synchronously at the start of a request before any file is stored, any database row is created, or any external API is called. If any check fails, the request is rejected immediately with a clear error code and nothing is written.


| **Endpoint**                   | **Synchronous checks performed**                                                                          |
| ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| POST /candidates               | 1 Candidate email exists? → DUPLICATE_CANDIDATE 2. Resume version count at limit? → RESUME_LIMIT_EXCEEDED |
| POST /job-applications         | 1 Candidate already linked to this requisition? → DUPLICATE_APPLICATION                                   |
| POST /screening/start-call     | 1 Active call already in progress for this candidate? → ACTIVE_CALL_EXISTS                                |
| POST /interviews               | 1 Duplicate round type already scheduled for this candidate + requisition?                                |
| POST /interviews/{id}/feedback | 1 Interview exists and belongs to a valid application?                                                    |


Solves: HR receives an immediate, accurate response for every action. No success message followed by a silent background failure. Fail fast, fail clearly, fail before any side effects occur.

## 4.6 Asynchronous Post-Response Processing

Work that does not affect the immediate response to HR runs after the HTTP response is returned, using FastAPI BackgroundTasks. HR receives a 202 Accepted immediately and results appear in the UI when processing completes.


| **Operation**                 | **Async behaviour**                                                                                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Interview transcription       | POST /interviews/{id}/recording returns 202 immediately. Whisper API transcription runs in background. Transcript appears in interview record when done.   |
| AI interview analysis         | Chains from transcription completion. LLM analysis runs in background after transcription finishes. ai_analysis and ai_overall_rating populated when done. |
| Agent 6 feedback notification | Triggered automatically after AI analysis completes. Notification sent to interviewer in background.                                                       |


Solves: interview recordings can be 30 to 60 minutes long. Transcription takes equivalent time. HR should not wait with an open browser tab. Background processing keeps the UI responsive at all times.

Note: skill extraction on resume upload runs synchronously within the request because it completes in 2 to 3 seconds and HR needs the results immediately for the confirmation step.

## 4.7 Scoped Candidate Queries

When viewing candidates in the context of a specific job opening, every query is scoped to that requisition. Candidates not linked to that job do not appear in the results.

Match scores are per-requisition, not global. A candidate has a different score against each job opening based on that job's specific skill requirements, experience range, location, and work mode. The candidate_scores table stores one row per candidate per requisition.

**Find Best 20:** GET /requisitions/{id}/candidates?limit=20&sort=match_score - returns the 20 highest-scoring candidates from the entire pool scored against this specific job's requirements

Solves: recruiters see only relevant, ranked candidates for the role they are actively hiring for. A DevOps requisition never shows AI engineers in its candidate list. Scores are meaningful because they are computed against specific job criteria.

## 4.8 Role-Based Access Control

Every endpoint enforces the caller's role claim from the JWT token. Three roles exist: HR, DELIVERY_MANAGER, and ADMIN. Role is checked at the FastAPI route level before any business logic executes.


| **Operation**              | **HR** | **Delivery Manager** |
| -------------------------- | ------ | -------------------- |
| Upload resumes             | Yes    | No                   |
| Confirm extracted skills   | Yes    | No                   |
| Create job openings        | Yes    | Yes                  |
| View and search candidates | Yes    | Yes                  |
| Initiate screening calls   | Yes    | No                   |
| Schedule interviews        | Yes    | No                   |
| Submit and update feedback | Yes    | No                   |
| View interview AI analysis | Yes    | Yes                  |
| View analytics dashboard   | Yes    | Yes                  |
| Manage user accounts       | No     | No - Admin only      |
| Manage skills master list  | No     | No - Admin only      |


Solves: Delivery Managers can view pipeline and search candidates but cannot modify candidate data or submit feedback. HRs manage the workflow but cannot create user accounts. Prevents unintended data modification across roles.

## 4.9 Sensitive Field Encryption

Three candidate fields are encrypted at rest: phone number, current CTC, and expected CTC. These fields are never returned in list API responses. They are decrypted and included only in the full single candidate profile response from GET /candidates/{id}.


| **Field**    | **Behaviour**                                                                            |
| ------------ | ---------------------------------------------------------------------------------------- |
| phone        | Encrypted at rest. Excluded from GET /candidates list. Included in GET /candidates/{id}. |
| current_ctc  | Encrypted at rest. Excluded from GET /candidates list. Included in GET /candidates/{id}. |
| expected_ctc | Encrypted at rest. Excluded from GET /candidates list. Included in GET /candidates/{id}. |


Solves: if the database is compromised, the most personally sensitive candidate fields are not readable in plaintext. List API responses are also faster because decryption only happens when a single profile is explicitly opened.

## 4.10 Skill Normalisation

Every skill extracted from a resume is normalised against the skills master table via the skill_aliases table before being stored in candidate_skills. A raw extracted string like ML, machine learning, or Machine Learning Engineer all resolve to the canonical skill entry Machine Learning.

Normalisation process:

- LLM extracts raw skill strings from resume text
- Each string is lowercased and looked up in skill_aliases WHERE alias = lower(extracted_string)
- If found: the canonical skill_id is used to insert into candidate_skills
- If not found: a new skill entry is created with is_verified = false and flagged for Admin review. The alias is also added so future occurrences resolve correctly.

Solves: without normalisation, filtering by Python returns only candidates where exactly that string was extracted. Candidates whose resume says Python3 or Python programming are missed. Normalisation ensures filter and search results are complete and accurate across all candidates.

## 4.11 Database Constraints as Final Guarantee

Application-level checks are the first line of defence for uniqueness rules. Database-level unique constraints are the last line of defence. Both exist on every uniqueness requirement. The system never relies on application checks alone.


| **Table + Column(s)**                           | **Constraint type**   |
| ----------------------------------------------- | --------------------- |
| candidates.email                                | UNIQUE                |
| candidate_skills (candidate_id, skill_id)       | UNIQUE composite      |
| job_applications (candidate_id, requisition_id) | UNIQUE composite      |
| requisition_skills (requisition_id, skill_id)   | UNIQUE composite      |
| skill_aliases.alias                             | UNIQUE                |
| candidate_resumes.gmail_message_id              | UNIQUE where not null |


Solves: under concurrent load, two requests can both pass an application-level uniqueness check before either has written to the database. The database constraint catches this and ensures exactly one insert succeeds. Data integrity is guaranteed independent of application logic or timing.

## 4.12 Source Tracking

Every candidate record stores the channel it was sourced from. Source is a required field - it cannot be null. An optional source_detail field stores additional context.


| **Source value** | **source_detail example**                     |
| ---------------- | --------------------------------------------- |
| LINKEDIN         | Profile URL or HR note                        |
| NAUKRI           | Profile URL or search query                   |
| GMAIL            | Sender email address (auto-populated)         |
| REFERRAL         | Name of the person who referred the candidate |
| EMAIL            | Sender email address                          |
| OTHER            | Free text description                         |


Solves: Analytics Agent 7 uses source data to report which sourcing channel produces the highest quality candidates and the best hire rates. Without mandatory source tracking this analysis is impossible. HR leadership uses this to decide where to invest sourcing effort.

## 4.13 Audit Trail

Two separate event log tables track everything that happens in the system for two different purposes.


| **Table**        | **Purpose and what it records**                                                                                                                                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| audit_logs       | Accountability. Every user action that creates, updates, or deletes a record. Who did what, to which record, at what time, from which IP address. Used for HR team accountability and compliance.                                |
| analytics_events | Pipeline reporting. Every significant candidate journey milestone - added, scored, screened, interview scheduled, feedback submitted, hired, rejected. Used by Analytics Agent 7 to build funnel reports and conversion metrics. |


These tables are write-only from the application's perspective. No application feature ever deletes or updates rows in either table. They are permanent append-only logs.

Solves: audit_logs provides accountability if a candidate record is incorrectly modified or deleted. analytics_events provides the data foundation for all pipeline analytics without requiring complex joins across multiple tables at query time.

# 5 Architecture Components

## 5.1 Nginx (Reverse Proxy)

Nginx runs on the same VM as the FastAPI application. It receives all inbound HTTP requests and forwards them to the Uvicorn process. Nginx handles TLS termination, static file serving, request buffering, and connection limits.

All routes except POST /webhooks/twilio require a valid JWT token. Nginx does not perform JWT validation itself - it forwards every request to FastAPI, which enforces authentication at the route level.

**Public endpoint:** POST /webhooks/twilio is the only endpoint that does not require HR authentication. Twilio signs all webhook requests; FastAPI verifies the Twilio signature before processing.

## 5.2 FastAPI Application

The FastAPI application is the only backend service. It contains all business logic, all route handlers, all agent logic, and the APScheduler instance for background jobs. It runs with multiple Uvicorn workers to handle concurrent requests.

Recommended worker configuration: (2 × CPU cores) + 1. On a 2-core VM this gives 5 workers. Each worker handles concurrent async requests within it, meaning I/O-bound operations (database queries, S3 reads, external API calls) do not block other requests within the same worker. For 10 concurrent HR users, 5 workers on a 2-core VM is sufficient.

## 5.3 Supabase PostgreSQL

Supabase provides a fully managed PostgreSQL instance. No database server needs to be provisioned, maintained, or backed up by the development team. The FastAPI application connects via a standard PostgreSQL connection string. Supabase handles uptime, backups, SSL, and scaling.

PostgreSQL tsvector columns on the candidate_resumes table provide full-text keyword search across resume content. This eliminates the need for a separate Elasticsearch cluster at the current scale.

## 5.4 Supabase Storage

Resume files (PDF and DOCX) are stored in Supabase Storage buckets. The FastAPI application uploads files directly to Supabase Storage via the Supabase Python SDK. File URLs are stored in the candidate_resumes table. HR users access files through pre-signed URLs generated by the application.

## 5.5 Supabase Auth

All authentication is handled by Supabase Auth. HR and Delivery Manager accounts are created by an Admin. Login returns a JWT token. FastAPI validates JWT tokens on every protected route using the Supabase JWT secret. Role (HR, DELIVERY_MANAGER, ADMIN) is stored as a custom claim in the JWT and enforced at the route level.

## 5.6 APScheduler (Gmail Polling)

APScheduler runs inside the FastAPI process. It executes a Gmail polling job every 5 minutes. The job connects to Gmail API, checks the monitored inbox for new emails with PDF or DOCX attachments, and passes each new attachment through the same resume processing pipeline used for manual HR uploads.

Deduplication: each processed Gmail message ID is stored in the candidate_resumes table. Before processing, the job checks whether the message ID already exists, preventing duplicate imports.

# 6 Data Entry Points

## 6.1 HR Manual Upload (Single or Batch)

HR selects one or multiple resume files from the dashboard. The frontend sends them as parallel individual HTTP requests - one per file. Each file is processed independently and concurrently by FastAPI workers. HR sees per-file progress and status in real time.

Processing steps per file (synchronous, all within the single request):

- File validated (PDF or DOCX, max size enforced)
- File uploaded to Supabase Storage
- Text extracted from file using pdfminer (PDF) or python-docx (DOCX)
- Extracted text sent to LLM API with skill extraction prompt
- LLM returns raw skill list; each skill normalised against skill_aliases table
- Unrecognised skills flagged as unverified and added to skills master table
- Candidate record created or matched by email (deduplication)
- candidate_skills rows inserted with is_verified = false
- tsvector search index updated automatically by PostgreSQL
- Response returned to HR with extracted skill list for confirmation

HR reviews the extracted skills, removes false positives, adds any missed skills, and confirms. On confirmation, is_verified is set to true for confirmed skills. This balance between automation and human oversight ensures data quality without requiring full manual tagging.

## 6.2 Gmail Auto-Ingestion

Every 5 minutes, APScheduler triggers the Gmail polling job. The job authenticates with Gmail API using a service account, fetches all unread emails in the monitored inbox, and processes any PDF or DOCX attachments. Each attachment goes through the identical processing pipeline as a manual upload. The source field on the candidate record is set to GMAIL and source_detail records the sender email address.

# 7 Agents

Agents are logical processing units implemented as FastAPI route handlers and background functions within the single FastAPI application. They are not separate deployed services.

## Agent 1 - Resume Intake

Handles all resume ingestion regardless of source. Runs synchronously within the upload request. Responsible for file storage, text extraction, LLM-based skill extraction, skill normalisation, candidate record creation and deduplication, search index update, and returning the skill confirmation payload to HR.

**Trigger:** POST /candidates (HR manual upload) or APScheduler Gmail job

**Writes to:** candidates, candidate_resumes, candidate_skills, skills, skill_aliases, analytics_events

## Agent 2 - Resume Scoring

After a candidate enters the system, Agent 2 automatically computes a match score for all open job openings in the same domain. Scoring is heuristic-based and produces both an overall score and a per-dimension breakdown stored for transparency.

Scoring dimensions and weights:

- Mandatory skills match (candidate has all required skills): 40%
- Total experience within requisition range: 20%
- Per-skill depth (years per skill vs minimum required): 20%
- Location and work mode match: 10%
- Notice period within role requirements: 10%

**Trigger:** Automatically after Agent 1 completes, or when a new job opening is created

**Writes to:** candidate_scores, job_applications (match_score column), analytics_events

## Agent 3 - Telephonic Screening

HR initiates a screening call from the candidate profile. The system calls the candidate via Twilio, plays predefined screening questions, records responses, receives webhook updates as the call progresses, and after call completion runs transcription and structured Q&A extraction.

Call flow:

- HR clicks Start Screening on candidate profile
- POST /screening/start-call triggers Twilio API call to candidate phone number
- Twilio executes TwiML script: greets candidate, asks predefined questions, records answers
- Twilio sends webhook callbacks to POST /webhooks/twilio as call progresses
- On call completion, recording URL stored; Whisper API transcribes the audio
- LLM extracts structured Q&A pairs from transcript
- call_logs record created with full transcript and structured answers

**Trigger:** POST /screening/start-call (HR initiated)

**Webhook:** POST /webhooks/twilio (public endpoint, Twilio signature verified)

**Writes to:** call_logs, analytics_events

## Agent 4 - Interview Scheduling

HR creates an interview round for a candidate, specifying the round type (L1, L2, L3, HR, Final), interviewer, and time slot. Agent 4 creates the interview record, sends calendar invites via Google Calendar API to the interviewer, and logs the scheduling event.

**Trigger:** POST /interviews (HR initiated)

**Writes to:** interviews, analytics_events

## Agent 5 - Interview Analysis

After an interview is completed, HR uploads the recording. Agent 5 transcribes the audio using Whisper API, then sends the transcript to an LLM for structured analysis. The LLM evaluates communication clarity, technical depth, problem-solving approach, and cultural fit signals. It also produces a per-question breakdown showing the question asked, the candidate's answer, and the AI's assessment of that answer. Results are stored and made available to HR alongside the interviewer's human feedback.

**Trigger:** POST /interviews/{id}/recording (HR initiated)

**Writes to:** interviews (transcript, ai_analysis, ai_overall_rating columns), analytics_events

## Agent 6 - Feedback Collection

Automatically triggered after Agent 5 completes analysis. Sends the interviewer a notification (email or in-app) with a link to the feedback form for that interview round. The interviewer submits structured ratings and written comments. Feedback can be updated after initial submission. Both AI analysis and human feedback are visible together on the candidate profile.

**Trigger:** Automatic chain after Agent 5 completes

**HR action:** POST /interviews/{id}/feedback (submit or update feedback)

**Writes to:** interview_feedback, analytics_events

## Agent 7 - Analytics

Reads from all tables to produce pipeline metrics and dashboards for HR and management. Queries are served on demand via the analytics API endpoints. The analytics_events table provides the event log that powers funnel and timeline reporting.

Dashboard metrics provided:

- Candidate pipeline funnel (count at each stage: added, scored, screened, interviewed, offered, hired, rejected)
- Source effectiveness (which source produces highest-scoring or hired candidates)
- Open requisition health (days open, candidates in pipeline per role)
- Interviewer feedback patterns and rating distributions
- Average time-to-hire per domain and per seniority level
- Scoring accuracy over time (correlation between match score and hire outcome)

**Trigger:** GET /analytics/dashboard and related GET endpoints (HR or DM initiated)

**Reads from:** candidates, candidate_scores, call_logs, interviews, interview_feedback, job_applications, analytics_events

# 8 API Reference

All endpoints require JWT authentication except POST /webhooks/twilio. Role column indicates minimum role required.

## 8.1 Authentication


| **Endpoint**                  | **Description**                                                   |
| ----------------------------- | ----------------------------------------------------------------- |
| POST /auth/login              | Login with email and password. Returns JWT token with role claim. |
| POST /auth/logout             | Invalidate current session token.                                 |
| POST /auth/users (Admin only) | Create a new HR or Delivery Manager account.                      |


## 8.2 Candidates


| **Method** | **Endpoint**                    | **Role**  | **Description**                                                                                                                                                                             |
| ---------- | ------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST       | /candidates                     | HR        | Upload one or multiple resumes. No position required. Multipart form. Returns extracted skills and ai_summary for confirmation. Candidates enter the pool independently of any job opening. |
| POST       | /candidates/{id}/confirm-skills | HR        | HR confirms or adjusts extracted skills. Sets is_verified = true.                                                                                                                           |
| GET        | /candidates                     | HR, DM    | List all candidates. Excludes blacklisted by default. Supports all filters. Paginated. Returns ai_summary per candidate for quick scanning.                                                 |
| GET        | /candidates?blacklisted=true    | Admin     | List blacklisted candidates only. Admin role required.                                                                                                                                      |
| GET        | /candidates/{id}                | HR, DM    | Full candidate profile including ai_summary, skills, resume versions, scores, call logs, interview history, and custom_metadata.                                                            |
| PATCH      | /candidates/{id}                | HR        | Update candidate metadata including custom_metadata jsonb field.                                                                                                                            |
| GET        | /candidates/{id}/resume         | HR, DM    | Retrieve pre-signed URL to view latest resume file.                                                                                                                                         |
| POST       | /candidates/{id}/blacklist      | HR, Admin | Blacklist a candidate system-wide. Body: reason_id, note. Sets is_blacklisted = true, records who and when, automatically drops all active pipeline applications with a system note.        |
| DELETE     | /candidates/{id}/blacklist      | Admin     | Remove blacklist if applied in error. Adds entry to audit_logs. Does not restore previous application statuses.                                                                             |


## 8.3 Job Openings (Requisitions)


| **Method** | **Endpoint**                  | **Role** | **Description**                                                                                                                                      |
| ---------- | ----------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST       | /requisitions                 | HR, DM   | Create a new job opening with title, description, domain, department, skills required, experience range, location, work mode, CTC budget, headcount. |
| GET        | /requisitions                 | HR, DM   | List all job openings. Filter by status, domain, department.                                                                                         |
| GET        | /requisitions/{id}            | HR, DM   | Full job opening detail including required skills and candidate pipeline summary.                                                                    |
| PATCH      | /requisitions/{id}            | HR, DM   | Update job opening details or status (OPEN, ON_HOLD, CLOSED).                                                                                        |
| GET        | /requisitions/{id}/candidates | HR, DM   | All candidates linked to this job opening, sorted by match score descending. Supports same filters as /candidates.                                   |


## 8.4 Skills


| **Method** | **Endpoint**         | **Role** | **Description**                                                                         |
| ---------- | -------------------- | -------- | --------------------------------------------------------------------------------------- |
| GET        | /skills              | All      | Full skills master list grouped by category. Used to populate filter dropdowns.         |
| POST       | /skills              | Admin    | Add a new skill to the master list.                                                     |
| POST       | /skills/{id}/aliases | Admin    | Add aliases for a skill (e.g. 'ML', 'machine learning' both map to 'Machine Learning'). |


## 8.5 Screening Calls


| **Method** | **Endpoint**                    | **Role** | **Description**                                                                                                     |
| ---------- | ------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------- |
| POST       | /screening/start-call           | HR       | Initiate Twilio screening call for a candidate. Body: candidate_id, requisition_id, question_set_id.                |
| GET        | /screening/{candidate_id}/calls | HR, DM   | All call logs for a candidate including transcripts and Q&A breakdowns.                                             |
| POST       | /webhooks/twilio                | Public   | Twilio webhook receiver. Twilio signature verified before processing. Updates call status and stores recording URL. |


## 8.6 Interviews


| **Method** | **Endpoint**               | **Role** | **Description**                                                                                                          |
| ---------- | -------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------ |
| POST       | /interviews                | HR       | Schedule an interview round. Body: candidate_id, requisition_id, interviewer_id, round_type, scheduled_at, meeting_link. |
| GET        | /interviews/{candidate_id} | HR, DM   | All interview rounds for a candidate across all job openings.                                                            |
| PATCH      | /interviews/{id}           | HR       | Update interview status (COMPLETED, CANCELLED, NO_SHOW, RESCHEDULED).                                                    |
| POST       | /interviews/{id}/recording | HR       | Upload interview recording. Triggers Agent 5 transcription and AI analysis.                                              |
| POST       | /interviews/{id}/feedback  | HR       | Submit or update human feedback for an interview round. Can be called multiple times to update.                          |
| GET        | /interviews/{id}/feedback  | HR, DM   | Retrieve combined AI analysis and human feedback for one interview round.                                                |


## 8.7 Analytics


| **Endpoint**                     | **Description**                                                                  |
| -------------------------------- | -------------------------------------------------------------------------------- |
| GET /analytics/dashboard         | Overall pipeline summary: counts by stage, source breakdown, open roles health.  |
| GET /analytics/funnel            | Stage-by-stage funnel with conversion rates.                                     |
| GET /analytics/sources           | Source effectiveness: application volume and hire rate per source.               |
| GET /analytics/time-to-hire      | Average days from candidate added to hired, broken down by domain and seniority. |
| GET /analytics/requisitions/{id} | Per-job analytics: pipeline depth, scoring distribution, interview outcomes.     |


# 9 Database Schema

All tables reside in Supabase PostgreSQL. UUIDs are used for all primary keys. Timestamps are stored in UTC.

## 9.1 users


| **Column** | **Type**            | **Notes**                             |
| ---------- | ------------------- | ------------------------------------- |
| id         | uuid PK             |                                       |
| name       | varchar(150)        |                                       |
| email      | varchar(255) UNIQUE | Login identifier                      |
| role       | enum                | HR                                    |
| is_active  | boolean             | Soft disable without deleting account |
| created_at | timestamptz         |                                       |
| updated_at | timestamptz         |                                       |


## 9.2 domains


| **Column** | **Type**            | **Notes**                                           |
| ---------- | ------------------- | --------------------------------------------------- |
| id         | uuid PK             |                                                     |
| name       | varchar(100) UNIQUE | e.g. AI/ML, DevOps, Frontend, Backend, Data Science |
| created_at | timestamptz         |                                                     |


## 9.3 departments


| **Column** | **Type**            | **Notes**                                     |
| ---------- | ------------------- | --------------------------------------------- |
| id         | uuid PK             |                                               |
| name       | varchar(100) UNIQUE | e.g. Engineering, Product, Design, Operations |
| created_at | timestamptz         |                                               |


## 9.4 skills


| **Column**  | **Type**            | **Notes**                                                       |
| ----------- | ------------------- | --------------------------------------------------------------- |
| id          | uuid PK             |                                                                 |
| name        | varchar(100) UNIQUE | Canonical skill name e.g. Python, PyTorch, Kubernetes           |
| category    | enum                | PROGRAMMING_LANGUAGE                                            |
| is_verified | boolean             | False for auto-created unrecognised skills pending admin review |
| created_at  | timestamptz         |                                                                 |


## 9.5 skill_aliases


| **Column** | **Type**            | **Notes**                                                                           |
| ---------- | ------------------- | ----------------------------------------------------------------------------------- |
| id         | uuid PK             |                                                                                     |
| skill_id   | uuid FK → skills    |                                                                                     |
| alias      | varchar(100) UNIQUE | Lowercase. e.g. ml, machine learning, ml engineer all map to Machine Learning skill |
| created_at | timestamptz         |                                                                                     |


Index: alias column for fast normalisation lookups during skill extraction.

## 9.6 candidates


| **Column**             | **Type**                                     | **Notes**                                                                                                              |
| ---------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| id                     | uuid PK                                      |                                                                                                                        |
| full_name              | varchar(200)                                 |                                                                                                                        |
| email                  | varchar(255) UNIQUE                          | Deduplication key. Unique constraint enforced at DB level.                                                             |
| phone                  | varchar(30)                                  | Encrypted at rest                                                                                                      |
| current_location       | varchar(200)                                 |                                                                                                                        |
| linkedin_url           | varchar(500)                                 |                                                                                                                        |
| portfolio_url          | varchar(500)                                 |                                                                                                                        |
| domain_id              | uuid FK → domains                            | Primary domain of the candidate                                                                                        |
| total_experience_years | float                                        |                                                                                                                        |
| current_company        | varchar(200)                                 |                                                                                                                        |
| current_designation    | varchar(200)                                 |                                                                                                                        |
| current_ctc            | integer                                      | Annual, in INR. Encrypted at rest.                                                                                     |
| expected_ctc           | integer                                      | Annual, in INR. Encrypted at rest.                                                                                     |
| notice_period_days     | integer                                      | 0, 15, 30, 60, 90                                                                                                      |
| availability_date      | date                                         | Earliest join date                                                                                                     |
| work_mode_preference   | enum                                         | REMOTE                                                                                                                 |
| shift_preference       | enum                                         | DAY                                                                                                                    |
| source                 | enum                                         | LINKEDIN                                                                                                               |
| source_detail          | text                                         | Referrer name if REFERRAL; sender email if GMAIL or EMAIL                                                              |
| uploaded_by            | uuid FK → users                              | HR who created this record                                                                                             |
| custom_metadata        | jsonb                                        | Flexible recruiter-added key-value pairs. Examples: visa_status, willing_to_relocate, last_contacted. No fixed schema. |
| is_blacklisted         | boolean default false                        | System-wide flag. When true, candidate excluded from all search results and cannot be linked to any new job.           |
| blacklist_reason_id    | uuid FK → pipeline_status_reasons (nullable) | Structured reason. Populated only when is_blacklisted = true.                                                          |
| blacklisted_by         | uuid FK → users (nullable)                   | Who performed the blacklist action.                                                                                    |
| blacklisted_at         | timestamptz (nullable)                       | When blacklist was applied.                                                                                            |
| blacklist_note         | text (nullable)                              | Free text context beyond the structured reason.                                                                        |
| created_at             | timestamptz                                  |                                                                                                                        |
| updated_at             | timestamptz                                  |                                                                                                                        |


Indexes: email (unique), domain_id, total_experience_years, notice_period_days, work_mode_preference, source, is_blacklisted.

All GET /candidates queries append WHERE is_blacklisted = false by default. Blacklisted candidates visible only via GET /candidates?blacklisted=true (Admin only).

## 9.7 candidate_resumes


| **Column**        | **Type**             | **Notes**                                                |
| ----------------- | -------------------- | -------------------------------------------------------- |
| id                | uuid PK              |                                                          |
| candidate_id      | uuid FK → candidates |                                                          |
| file_url          | varchar(1000)        | Supabase Storage URL                                     |
| redacted_file_url | varchar(1000)        | PII-stripped version stored separately                   |
| parsed_text       | text                 | Full extracted resume text                               |
| search_vector     | tsvector GENERATED   | Auto-computed from parsed_text. Powers full-text search. |
| gmail_message_id  | varchar(200)         | For Gmail-sourced resumes. Prevents duplicate import.    |
| is_latest         | boolean              | True for most recent resume version                      |
| uploaded_by       | uuid FK → users      |                                                          |
| uploaded_at       | timestamptz          |                                                          |


Index: GIN index on search_vector for full-text search performance. Index on candidate_id. Unique on gmail_message_id where not null.

## 9.8 candidate_skills


| **Column**          | **Type**             | **Notes**                                             |
| ------------------- | -------------------- | ----------------------------------------------------- |
| id                  | uuid PK              |                                                       |
| candidate_id        | uuid FK → candidates |                                                       |
| skill_id            | uuid FK → skills     | Normalised canonical skill                            |
| proficiency_level   | enum                 | BEGINNER                                              |
| years_of_experience | float                | Years with this specific skill                        |
| is_verified         | boolean              | False = auto-extracted by LLM; True = confirmed by HR |
| created_at          | timestamptz          |                                                       |


Unique constraint on (candidate_id, skill_id). Indexes on skill_id and candidate_id.

## 9.9 requisitions


| **Column**           | **Type**              | **Notes**                    |
| -------------------- | --------------------- | ---------------------------- |
| id                   | uuid PK               |                              |
| title                | varchar(300)          | e.g. Associate AI Engineer   |
| description          | text                  | Full job description         |
| domain_id            | uuid FK → domains     |                              |
| department_id        | uuid FK → departments |                              |
| seniority_level      | enum                  | INTERN                       |
| location             | varchar(200)          |                              |
| work_mode            | enum                  | REMOTE                       |
| shift_timing         | enum                  | DAY                          |
| min_experience_years | float                 |                              |
| max_experience_years | float                 |                              |
| min_budget_ctc       | integer               | Annual, in INR               |
| max_budget_ctc       | integer               | Annual, in INR               |
| number_of_openings   | integer               | Headcount for this role      |
| status               | enum                  | DRAFT                        |
| created_by           | uuid FK → users       |                              |
| hiring_manager_id    | uuid FK → users       | Delivery Manager responsible |
| target_close_date    | date                  |                              |
| created_at           | timestamptz           |                              |
| updated_at           | timestamptz           |                              |


## 9.10 requisition_skills


| **Column**     | **Type**               | **Notes**                              |
| -------------- | ---------------------- | -------------------------------------- |
| id             | uuid PK                |                                        |
| requisition_id | uuid FK → requisitions |                                        |
| skill_id       | uuid FK → skills       |                                        |
| is_mandatory   | boolean                | True = must-have; False = nice-to-have |
| minimum_years  | float                  | Minimum years required for this skill  |
| created_at     | timestamptz            |                                        |


Unique constraint on (requisition_id, skill_id).

## 9.11 job_applications


| **Column**       | **Type**               | **Notes**                             |
| ---------------- | ---------------------- | ------------------------------------- |
| id               | uuid PK                |                                       |
| candidate_id     | uuid FK → candidates   |                                       |
| requisition_id   | uuid FK → requisitions |                                       |
| status           | enum                   | NEW                                   |
| match_score      | float                  | Overall score 0.0-1.0 from Agent 2    |
| rejection_reason | text                   | Populated when status = REJECTED      |
| notes            | text                   | HR notes on this specific application |
| created_by       | uuid FK → users        | Who linked this candidate to this job |
| created_at       | timestamptz            |                                       |
| updated_at       | timestamptz            |                                       |


Unique constraint on (candidate_id, requisition_id). Indexes on requisition_id, candidate_id, status, match_score.

## 9.12 candidate_scores


| **Column**          | **Type**               | **Notes**                                            |
| ------------------- | ---------------------- | ---------------------------------------------------- |
| id                  | uuid PK                |                                                      |
| candidate_id        | uuid FK → candidates   |                                                      |
| requisition_id      | uuid FK → requisitions |                                                      |
| total_score         | float                  | Final weighted score 0.0-1.0                         |
| skills_score        | float                  | Mandatory skills match component                     |
| experience_score    | float                  | Experience range match component                     |
| skills_depth_score  | float                  | Per-skill years depth component                      |
| location_score      | float                  | Location and work mode match component               |
| notice_period_score | float                  | Notice period fit component                          |
| scoring_version     | varchar(20)            | Scoring logic version for tracking changes over time |
| created_at          | timestamptz            |                                                      |


## 9.13 call_logs


| **Column**        | **Type**               | **Notes**                                                 |
| ----------------- | ---------------------- | --------------------------------------------------------- |
| id                | uuid PK                |                                                           |
| candidate_id      | uuid FK → candidates   |                                                           |
| requisition_id    | uuid FK → requisitions |                                                           |
| initiated_by      | uuid FK → users        | HR who started the call                                   |
| twilio_call_sid   | varchar(100)           | Twilio unique call identifier                             |
| status            | enum                   | INITIATED                                                 |
| recording_url     | varchar(1000)          | Twilio-hosted recording URL                               |
| transcript        | text                   | Full Whisper API transcription                            |
| screening_answers | jsonb                  | Structured Q&A: {question, answer, ai_comment, ai_rating} |
| duration_seconds  | integer                |                                                           |
| called_at         | timestamptz            |                                                           |
| completed_at      | timestamptz            |                                                           |


## 9.14 interviews


| **Column**            | **Type**               | **Notes**                                   |
| --------------------- | ---------------------- | ------------------------------------------- |
| id                    | uuid PK                |                                             |
| candidate_id          | uuid FK → candidates   |                                             |
| requisition_id        | uuid FK → requisitions |                                             |
| interviewer_id        | uuid FK → users        |                                             |
| round_number          | integer                | 1 for L1, 2 for L2 etc.                     |
| round_type            | enum                   | L1                                          |
| status                | enum                   | SCHEDULED                                   |
| scheduled_at          | timestamptz            |                                             |
| meeting_link          | varchar(500)           | Google Meet or Zoom link                    |
| calendar_event_id     | varchar(200)           | Google Calendar event ID for updates        |
| recording_url         | varchar(1000)          | Uploaded recording file in Supabase Storage |
| transcript            | text                   | Whisper API transcription of recording      |
| ai_analysis           | jsonb                  | LLM structured analysis of the interview    |
| ai_overall_rating     | float                  | AI overall rating 0.0-1.0                   |
| analysis_completed_at | timestamptz            |                                             |
| created_by            | uuid FK → users        | HR who scheduled this round                 |
| created_at            | timestamptz            |                                             |
| updated_at            | timestamptz            |                                             |


## 9.15 interview_feedback


| **Column**             | **Type**             | **Notes**                                                    |
| ---------------------- | -------------------- | ------------------------------------------------------------ |
| id                     | uuid PK              |                                                              |
| interview_id           | uuid FK → interviews | One feedback record per interview round                      |
| submitted_by           | uuid FK → users      | Interviewer who submitted feedback                           |
| ai_summary             | text                 | AI overall observation of the interview                      |
| ai_strengths           | text                 | AI-identified candidate strengths                            |
| ai_concerns            | text                 | AI-identified concerns or gaps                               |
| ai_qa_breakdown        | jsonb                | {question, candidate_answer, ai_comment, ai_rating}          |
| human_summary          | text                 | Interviewer's overall written comments                       |
| human_strengths        | text                 | Interviewer-noted strengths                                  |
| human_concerns         | text                 | Interviewer-noted concerns                                   |
| technical_rating       | integer 1-5          | Human rating                                                 |
| communication_rating   | integer 1-5          | Human rating                                                 |
| problem_solving_rating | integer 1-5          | Human rating                                                 |
| culture_fit_rating     | integer 1-5          | Human rating                                                 |
| overall_rating         | integer 1-5          | Human overall rating                                         |
| recommendation         | enum                 | STRONG_YES                                                   |
| is_submitted           | boolean              | False = draft; True = finalised. Updatable after submission. |
| submitted_at           | timestamptz          | First submission time                                        |
| last_updated_at        | timestamptz          | Most recent update time                                      |


## 9.16 analytics_events


| **Column**     | **Type**                          | **Notes**                                                        |
| -------------- | --------------------------------- | ---------------------------------------------------------------- |
| id             | uuid PK                           |                                                                  |
| event_type     | varchar(100)                      | CANDIDATE_ADDED                                                  |
| candidate_id   | uuid FK → candidates              |                                                                  |
| requisition_id | uuid FK → requisitions (nullable) |                                                                  |
| triggered_by   | uuid FK → users (nullable)        | Null for system-triggered events                                 |
| metadata       | jsonb                             | Additional context e.g. previous status, new status, score value |
| occurred_at    | timestamptz                       |                                                                  |


Index on event_type, candidate_id, requisition_id, occurred_at for efficient analytics aggregations.

## 9.17 audit_logs


| **Column**  | **Type**        | **Notes**                                           |
| ----------- | --------------- | --------------------------------------------------- |
| id          | uuid PK         |                                                     |
| user_id     | uuid FK → users | Who performed the action                            |
| action      | varchar(200)    | e.g. UPLOADED_RESUME, CREATED_JOB, UPDATED_FEEDBACK |
| entity_type | varchar(100)    | candidate                                           |
| entity_id   | uuid            | ID of the affected record                           |
| metadata    | jsonb           | Before/after values for updates                     |
| ip_address  | varchar(50)     |                                                     |
| created_at  | timestamptz     |                                                     |


## 9.18 pipeline_status_reasons

Master list of predefined sub-reasons for each pipeline status. Used when HR moves a candidate to any rejected or dropped status. Ensures consistent reason tracking across the team.


| **Column** | **Type**             | **Notes**                                                           |
| ---------- | -------------------- | ------------------------------------------------------------------- |
| id         | uuid PK              |                                                                     |
| status     | enum                 | The pipeline status this reason applies to                          |
| reason     | varchar(200)         | Human-readable reason label                                         |
| is_active  | boolean default true | Inactive reasons hidden from UI but retained for historical records |
| created_at | timestamptz          |                                                                     |


Seeded values by status:

DROPPED: Candidate not responding | Accepted another offer | Personal reasons | Relocated | Withdrew voluntarily

L1_REJECTED: Technical skills insufficient | Communication poor | Attitude concerns | Salary expectation mismatch | No show

L2_REJECTED: Deep technical gap | Leadership skills lacking | Culture fit concern | Salary mismatch | No show

CLIENT_REJECTED: Profile not matching requirement | Overqualified | Underqualified | Communication barrier | Client cancelled requirement

BLACKLISTED: Fraudulent information on resume | Unprofessional conduct | Repeated no shows | Policy violation

## 9.19 application_status_history

Append-only log of every pipeline status change for every application. Written automatically whenever job_applications.status is updated. Never deleted or modified.


| **Column**     | **Type**                                     | **Notes**                                                           |
| -------------- | -------------------------------------------- | ------------------------------------------------------------------- |
| id             | uuid PK                                      |                                                                     |
| application_id | uuid FK → job_applications                   |                                                                     |
| from_status    | enum (nullable)                              | Previous status. Null for first status assignment.                  |
| to_status      | enum                                         | New status after change.                                            |
| reason_id      | uuid FK → pipeline_status_reasons (nullable) | Structured sub-reason if applicable.                                |
| reason_note    | text (nullable)                              | Free text context.                                                  |
| changed_by     | uuid FK → users                              | Who triggered the status change. System user for automated changes. |
| changed_at     | timestamptz                                  |                                                                     |


Index on application_id for fast retrieval of full status history per candidate per job. This table powers the pipeline timeline view on the candidate profile.

# 10 Candidate Filtering

Filtering is handled entirely within PostgreSQL via dynamic query construction in FastAPI route handlers. No separate search service is required at the current scale.

Available filters on GET /candidates and GET /requisitions/{id}/candidates:


| **Filter Parameter**  | **Implementation**                                                                                                                             |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| skills (multi-select) | JOIN candidate_skills ON skill_id IN (...) GROUP BY candidate.id HAVING COUNT(DISTINCT skill_id) = N - candidate must have ALL selected skills |
| min_exp / max_exp     | WHERE total_experience_years BETWEEN min AND max                                                                                               |
| domain                | WHERE domain_id = ?                                                                                                                            |
| notice_period_max     | WHERE notice_period_days <= ?                                                                                                                  |
| work_mode             | WHERE work_mode_preference = ?                                                                                                                 |
| location              | WHERE current_location ILIKE '%value%'                                                                                                         |
| source                | WHERE source = ?                                                                                                                               |
| seniority             | Derived from total_experience_years ranges or explicit seniority column                                                                        |
| search (text)         | WHERE search_vector @@ plainto_tsquery('english', ?) on candidate_resumes, results ranked by ts_rank                                           |
| stage                 | WHERE stage = ?                                                                                                                                |


All filter parameters are optional. Filters are combined with AND logic. Results are paginated (default 20 per page). Default sort is match_score descending when viewing candidates for a specific requisition; created_at descending otherwise.

# 11 Concurrency Model

The system is designed for up to 10 concurrent HR users. Concurrency is handled natively by FastAPI and Uvicorn without any additional infrastructure.


| **Scenario**                                     | **How It Is Handled**                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 10 HRs using the dashboard simultaneously        | Nginx distributes requests across Uvicorn workers. Each request is handled independently and asynchronously.                                                                                                                                                                                               |
| Multiple HRs uploading resumes at the same time  | Each file upload is a separate independent request. FastAPI async I/O means file storage, LLM calls, and DB writes for different requests run concurrently without blocking each other.                                                                                                                    |
| Two HRs upload the same candidate simultaneously | Application-level check runs first. UNIQUE constraint on candidates.email at the database level guarantees only one insert succeeds even if both pass the application check simultaneously. Second insert receives a unique constraint violation; FastAPI returns a clear error: candidate already exists. |
| LLM API calls for skill extraction (concurrent)  | Each upload triggers an async LLM API call. With 10 concurrent uploads, 10 async LLM calls run in parallel. Total wait time is the duration of one call, not ten.                                                                                                                                          |
| Scheduled Gmail job overlapping with HR uploads  | APScheduler runs the Gmail job in a background thread. It does not block the HTTP request workers. Both run independently.                                                                                                                                                                                 |


Uvicorn worker formula: (2 × CPU cores) + 1. Recommended minimum: 2-core VM giving 5 workers. This comfortably handles 10 concurrent users given the async I/O nature of all operations.

# 12 Security

- All endpoints require JWT authentication via Supabase Auth. Token validated on every request.
- Role-based access control enforced at route level in FastAPI. HR and DM roles have different permission sets.
- Sensitive candidate fields (phone, current_ctc, expected_ctc) encrypted at rest using PostgreSQL pgcrypto extension or application-level encryption.
- All data in transit encrypted via TLS (enforced by Nginx and Supabase).
- Twilio webhook signature verified on every inbound webhook call before processing.
- Resume files in Supabase Storage accessed only via short-lived pre-signed URLs generated per request. Files are not publicly accessible.
- Audit log records all user actions with timestamps and IP addresses.
- No candidate-facing endpoints exist. The system is entirely internal.

# 13 Infrastructure & Cost


| **Service**                              | **Cost**                                                                                      |
| ---------------------------------------- | --------------------------------------------------------------------------------------------- |
| Supabase (database + storage + auth)     | Free tier to start. Paid tier 25/month for 8GB DB, 100GB storage.                             |
| VM for FastAPI + Nginx                   | Hetzner CX21 (2 vCPU, 4GB RAM): €4.51/month. Railway or Render: ~7/month.                     |
| Twilio (per screening call)              | Pay per minute. Approximately 0.013/min outbound. 100 calls/month at 5 min avg = ~6.50/month. |
| OpenAI API (skill extraction + analysis) | GPT-4o-mini for extraction: ~0.002 per resume. 500 resumes/month = ~1/month.                  |
| OpenAI Whisper (transcription)           | 0.006 per minute of audio. 100 interviews at 45 min avg = ~27/month.                          |
| Total estimated monthly cost             | ~40-70/month for full operation at 10-HR team scale.                                          |


# 14 Future Scope

- Naukri and LinkedIn API integration for direct resume import into Agent 1 pipeline
- Semantic vector search using pgvector (Postgres extension, no new service) for LLM-based candidate matching beyond keyword search
- Candidate portal for self-service status updates (requires adding public-facing authentication)
- Automated offer letter generation and e-signature integration
- WhatsApp notifications via Twilio for candidate communication
- Elasticsearch migration if full-text search performance degrades at high resume volumes

*End of Document*