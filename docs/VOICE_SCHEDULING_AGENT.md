# Voice Screening & Interview-Scheduling Agent

Complete documentation for the **telephonic screening voice agent** (Agent 3) and its
**live interview-scheduling** integration — the feature that lets an AI voice agent
call a candidate, screen them, decide qualification mid-call, and book a real interview
into an interviewer's calendar, all in a single phone conversation.

> TL;DR — During one outbound call the agent greets the candidate, runs a short
> screening, **judges qualification live** (confidence + communication), and then either
> politely defers ("we'll call you later for scheduling") or **offers the interviewer's
> open slots, says which are free vs. taken, and books one** — never double-booking an
> interviewer.

---

## 1. Where this agent sits — the agent count

The platform is built as **7 numbered LangGraph agents** plus **1 auxiliary agent**
(8 agents total). This feature is centred on **Agent 3** and directly drives **Agent 4**.

| # | Agent | File | Role in this feature |
|---|-------|------|----------------------|
| 1 | Resume Intake | `resume_intake.py` | Upstream — creates the candidate this agent calls |
| 2 | Resume Scoring | `resume_scoring.py` | Upstream — ranks candidates per requisition |
| **3** | **Telephonic Screening** | `telephonic_screening.py` | **This agent** — calls, screens, qualifies, triggers booking |
| **4** | **Interview Scheduling** | `interview_scheduling.py` | **Invoked live by Agent 3** to create the interview + calendar invite |
| 5 | Interview Analysis | `interview_analysis.py` | Downstream — analyses the interview recording later |
| 6 | Feedback Collection | `feedback_collection.py` | Downstream — interviewer feedback |
| 7 | Analytics | `analytics.py` | Downstream — funnel/event reporting |
| — | Detail Collection (aux) | `detail_collection.py` | Unrelated email-based field collection |

**Agents this feature uses: 2** — Agent 3 (the voice agent) calls **Agent 4** in-process
to perform the actual booking. Post-call, Agent 3's evaluation graph runs; upstream
Agents 1–2 produce the candidate and the screening context.

> Development provenance: this feature was built across **5 phases** and verified with
> the help of **3 read-only exploration sub-agents** (codebase mapping, frontend
> integration map, backend API/flow map).

---

## 2. Functionalities

**Call & conversation**
- Places an outbound screening call via Twilio (mock mode when no Twilio creds).
- Speech-to-speech conversation via the OpenAI Realtime API (low-latency), with a
  Deepgram live tap producing the candidate-side transcript.
- Deterministic opening line: introduces the company, confirms the candidate, asks if
  now is a good time.
- **Availability gate** on the first reply — offers a callback and hangs up if it's a bad time.
- Asks role-tailored screening questions (LLM-generated from the requisition) one at a time.
- Barge-in handling (candidate can interrupt the agent).

**Live qualification (in-call)**
- After the screening questions, the agent **judges qualification** from answer quality,
  confidence, and communication — using the audio directly.
- **Not qualified → soft defer:** speaks "we'll call you later for scheduling the
  interview. Thanks for applying." and ends. The live judgement is authoritative — the
  post-call evaluation is suppressed from auto-shortlisting; the application stays in
  `SCREENING` for HR review.

**Live scheduling (in-call)**
- **Qualified →** fetches the interviewer panel's **open slots** for the requisition and
  offers them by spoken label ("Mon 23 Jun, 4:30 PM").
- Tells the candidate which slots are **free vs. already taken**.
- On agreement, **books** the chosen slot, confirms the date/time, and promises a calendar invite.
- **Booking window rule:** Mon–Thu → the rest of the current week through Friday;
  Fri/Sat/Sun → next week Mon–Fri; never beyond.
- **Never double-books** an interviewer (app-level re-check + DB partial unique index).
- Books an **L1** round; reuses Agent 4 so a Teams/calendar invite is created and the
  application advances to `INTERVIEW_SCHEDULED`.
- Graceful fallback: if no slots are available, the agent says someone will reach out and ends.

**Post-call (existing pipeline, preserved)**
- Transcription + LLM Q&A evaluation produce `ai_score` and per-question breakdown.
- Status transitions are guarded so a booked candidate is never regressed.

**HR / admin surface**
- Assign interviewers to a requisition; define each interviewer's recurring weekly slots.
- HR slot-picker in the "Schedule interview" modal (replaces free-text date/time).

---

## 3. Tools

### 3a. Realtime function-calling tools (exposed to the model)

Defined in `app/integrations/openai_realtime/client.py`. **3 tools:**

| Tool | Args | Returns to model? | Purpose |
|------|------|-------------------|---------|
| `get_available_slots` | — | ✅ yes | Fetch open slots for the requisition; model reads them out |
| `book_interview` | `interviewer_id`, `start_iso` | ✅ yes | Book a chosen slot; returns `ok` + confirmation/meeting link |
| `end_screening` | `status` (`complete`/`unavailable`), `qualified`, `scheduled` | ❌ terminal | Hang up after the goodbye; records the live judgement |

The non-terminal tools required adding `RealtimeSession.send_function_result(call_id, output)`
— it appends a `function_call_output` conversation item and triggers a new response so the
model can speak the slots / confirmation. This capability did not exist before.

### 3b. External integrations / infrastructure tools

| Tool / Service | Module | Used for |
|----------------|--------|----------|
| **Twilio** (Voice + Media Streams) | `integrations/twilio/client.py` | Place the call; stream 8 kHz μ-law audio; hang up; signed stream token |
| **OpenAI Realtime API** (`gpt-realtime`) | `integrations/openai_realtime/client.py` | Speech-to-speech conversation + function calling |
| **Deepgram** (live STT) | `integrations/stt` | Candidate-side transcript tap during streaming |
| **STT fallback** | `integrations/stt` | Transcribe a recording when there's no live transcript (mock/legacy) |
| **LLM** (OpenAI / Anthropic via LangChain) | `llm/client.py` | Generate screening questions; post-call Q&A evaluation |
| **MS Graph** (Teams/Calendar) | `integrations/ms_graph/client.py` | Create the meeting + calendar invite when booking (mock link when no creds) |
| **LangGraph** | within each agent | Orchestrate the start-call / post-call / scheduling state graphs |

---

## 4. End-to-end flow

```
HR clicks "Start screening"  ──►  Agent 3 start graph
   validate_no_active_call → generate_questions (LLM) → initiate_call (Twilio) → persist(INITIATED)

Twilio answers ──► /webhooks/twilio/answer ──► (streaming) <Connect><Stream> to media-stream WS

  ┌─────────────────────  Media-stream bridge (media_stream.py)  ─────────────────────┐
  │  Twilio audio  ⇄  OpenAI Realtime (speech-to-speech)   Deepgram (transcript tap)  │
  │                                                                                    │
  │  greet → availability gate → screening Qs → JUDGE QUALIFICATION                    │
  │                                                                                    │
  │   ├─ not qualified → goodbye → end_screening(qualified=false)                      │
  │   └─ qualified → get_available_slots ──► offer free/taken slots                    │
  │                  → book_interview(interviewer_id,start_iso) ──► Agent 4 books      │
  │                  → confirm → end_screening(qualified=true, scheduled=true)         │
  └────────────────────────────────────────────────────────────────────────────────-─┘
                                   │ hang up (REST)
Twilio "completed" callback ──► Agent 3 post-call graph
   transcribe → llm_extract_qa → persist(COMPLETED) [soft-defer guard] → emit_analytics
```

`book_interview` → `interview_slots.book_slot()` → **re-checks the slot is still free** →
`schedule_interview()` (Agent 4): `validate_no_duplicate_round` (+ interviewer-conflict
guard) → `create_interview` → `send_calendar_invite` (MS Graph) → `emit_analytics`
(advances the application to `INTERVIEW_SCHEDULED`).

---

## 5. The slot engine (`app/services/interview_slots.py`)

Pure, offline-testable helpers + DB-backed API. All slot times are **company-local**
(`company_timezone`); everything stored/compared is **UTC**.

- `compute_booking_window(now_local) -> (start_date, end_date)` — the Mon–Fri / Friday-rollover rule.
- `expand_templates(...)` — expand each interviewer's recurring template across in-window
  weekdays; drop past times; sort.
- `filter_booked(...)` — drop slots overlapping an existing active interview (assumes 60-min interviews).
- `get_open_slots(db, requisition_id, now=None)` — join requisition → interviewers → slots,
  expand, drop booked → `SlotOption[]` (each with `interviewer_id`, `start_utc`, `start_local`,
  `label`, `duration_minutes`).
- `book_slot(db, ...)` — race-safe re-check, then delegate to Agent 4 (`round_type=L1`).

---

## 6. Database tables it interacts with

**11 tables.** (The platform has more; these are the ones this agent + its scheduling
feature + admin surface read or write.)

| # | Table | Model | Access | What for |
|---|-------|-------|:------:|----------|
| 1 | `call_logs` | `CallLog` | R/W | Call status, transcript, `question_set`, `ai_score`, `screening_answers`, **`qualified`** |
| 2 | `interviews` | `Interview` | R/W | Create the booked interview; conflict / duplicate-round checks; partial unique index |
| 3 | `interviewer_slots` | `InterviewerSlot` | R | Recurring weekly availability templates *(new)* |
| 4 | `requisition_interviewers` | `RequisitionInterviewer` | R/W | Which interviewers serve a requisition *(new; W via admin)* |
| 5 | `candidates` | `Candidate` | R | Name, phone (call target), email (invite) |
| 6 | `requisitions` | `Requisition` | R | Title/description for question generation; the role |
| 7 | `users` | `User` | R | Interviewer identity & email (for the invite) |
| 8 | `job_applications` | `JobApplication` | R/W | Stage transitions: SCREENING → SHORTLISTED / INTERVIEW_SCHEDULED |
| 9 | `application_status_history` | `ApplicationStatusHistory` | W | Append-only record of each stage change |
| 10 | `analytics_events` | `AnalyticsEvent` | W | `CALL_COMPLETED`, `INTERVIEW_SCHEDULED` events |
| 11 | `audit_logs` | `AuditLog` | W | Admin actions (assign/unassign interviewer, slot CRUD, scheduled interview) |

*Tables 3 and 4 are new in this feature; `call_logs.qualified` is a new column.*

---

## 7. Data model added by this feature

```
requisition_interviewers          interviewer_slots
  id (PK)                           id (PK)
  requisition_id  FK→requisitions   interviewer_id  FK→users
  interviewer_id  FK→users          slot_time        TIME (local, e.g. 16:30)
  created_at                        weekday_mask     SMALLINT  (Mon=bit0 … Sun=bit6; default Mon–Fri)
  UNIQUE(requisition_id,            duration_minutes INT (default 60)
         interviewer_id)            is_active        BOOL
                                    created_at / updated_at
                                    UNIQUE(interviewer_id, slot_time)

call_logs.qualified  BOOLEAN NULL   -- live in-call judgement (NULL = not decided live)

interviews — partial UNIQUE index  uq_interview_slot_per_interviewer
  ON (interviewer_id, scheduled_at)
  WHERE status IN ('SCHEDULED','RESCHEDULED') AND scheduled_at IS NOT NULL AND interviewer_id IS NOT NULL
  -- DB-level double-booking guard (app layer also re-checks)
```

**Migrations:** `0006_interviewer_slots.py` (two tables + partial index), `0007_call_qualified.py`
(the `qualified` column). Both idempotent/existence-guarded; head = `0007`.

> Postgres note: the index predicate compares the enum directly
> (`status IN ('SCHEDULED','RESCHEDULED')`). An earlier `status::text IN (...)` version
> failed with *"functions in index predicate must be marked IMMUTABLE"* — the enum→text
> cast isn't immutable.

---

## 8. API endpoints

**New (this feature)**

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/requisitions/{id}/interviewers` | HR/DM/Admin | List the interviewer panel |
| POST | `/requisitions/{id}/interviewers` | HR/DM/Admin (owner) | Assign an interviewer |
| DELETE | `/requisitions/{id}/interviewers/{interviewer_id}` | HR/DM/Admin (owner) | Unassign |
| GET | `/requisitions/{id}/open-slots` | HR/DM/Admin | Free bookable slots (powers UI + agent) |
| GET | `/interviewers/{id}/slots` | HR/DM/Admin | List an interviewer's recurring slots |
| POST | `/interviewers/{id}/slots` | Admin | Create a slot |
| PATCH | `/interviewers/{id}/slots/{slot_id}` | Admin | Edit / enable-disable a slot |
| DELETE | `/interviewers/{id}/slots/{slot_id}` | Admin | Delete a slot |

**Existing, reused**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/screening/start-call` | Start the screening call (Agent 3) |
| POST | `/interviews` | Manual scheduling (Agent 4) — now slot-aware in UI |
| POST | `/webhooks/twilio/answer` | Twilio answer → hand to media-stream bridge |
| WS | `/webhooks/twilio/media-stream` | Speech-to-speech bridge (token-verified) |
| POST | `/webhooks/twilio` | Status callback → post-call processing |

---

## 9. Configuration (env / `app/config.py`)

| Setting | Default | Used for |
|---------|---------|----------|
| `company_timezone` | `Asia/Kolkata` | Interpreting local slot times *(new)* |
| `voice_streaming_enabled` | `false` | **Must be `true`** for live in-call scheduling |
| `openai_realtime_model` | `gpt-realtime` | Realtime speech-to-speech model |
| `realtime_voice` | `alloy` | Agent voice |
| `realtime_silence_ms` | `320` | Turn-end detection (latency knob) |
| `company_name` / `screening_agent_name` | `Intelera` / — | Spoken intro |
| `call_score_threshold` | `70` | Post-call auto-shortlist threshold |
| Twilio / OpenAI / Deepgram / MS Graph creds | — | Live integrations (mock when absent) |

> The conversational scheduling runs **only on the Realtime streaming path**. The legacy
> turn-based IVR path keeps the old behaviour (qualify post-call, HR schedules manually).

---

## 10. Qualification, soft-defer & status guards

- The model records its judgement via `end_screening(qualified=…)`; the bridge persists it
  to `call_logs.qualified`.
- `persist_completed` (post-call): if `qualified is False`, the auto-SHORTLIST is **skipped**.
- `_move_application` has a **status-rank guard** (`NEW<SCREENING<SHORTLISTED<INTERVIEW_SCHEDULED<OFFERED<HIRED`)
  so a post-call shortlist can never regress a candidate the call already moved to
  `INTERVIEW_SCHEDULED`. Terminal exits (REJECTED/WITHDRAWN) are always allowed.

---

## 11. Frontend touchpoints

| File | Change |
|------|--------|
| `frontend/lib/types.ts` | `InterviewerSlot`, `RequisitionInterviewer`, `OpenSlot` |
| `frontend/lib/meta.ts` | `useRequisitionInterviewers`, `useInterviewerSlots`, `useOpenSlots` |
| `frontend/components/interviews/SlotPicker.tsx` | *(new)* selectable open-slot chips |
| `frontend/components/interviews/ScheduleInterviewModal.tsx` | Slot picker (manual fallback retained) |
| `frontend/components/admin/InterviewerSlotsPanel.tsx` | *(new)* admin slot CRUD (weekday + time) |
| `frontend/components/jobs/AssignInterviewersPanel.tsx` | *(new)* assign interviewers to a requisition |
| `frontend/app/admin/page.tsx` | "Interviewer Slots" tab |
| `frontend/app/jobs/[id]/page.tsx` | "Interview panel" on requisition detail |

---

## 12. File map

```
backend/app/
  agents/telephonic_screening.py     Agent 3 — graphs, realtime_instructions(), guards
  agents/interview_scheduling.py     Agent 4 — booking graph + interviewer-conflict guard
  services/interview_slots.py        slot engine (window/expand/filter, get_open_slots, book_slot)
  integrations/openai_realtime/client.py   Realtime client + 3 tools + send_function_result()
  api/routes/media_stream.py         speech-to-speech bridge + tool dispatch + _slots_for/_book
  api/routes/requisitions.py         interviewer-assignment + open-slots endpoints
  api/routes/users.py                interviewer slot CRUD
  api/routes/webhooks.py             Twilio answer / turn / status callbacks
  models/scheduling.py               RequisitionInterviewer, InterviewerSlot  (new)
  models/interview.py                CallLog (+qualified), Interview (+partial unique index)
  api/serializers.py                 requisition_interviewer_dict, interviewer_slot_dict
  schemas/api.py                     AssignInterviewerRequest, (Update)InterviewerSlotRequest
  config.py                          company_timezone
  alembic/versions/0006_*, 0007_*    migrations
  scripts/seed.py                    seeded panels + slots (Alice 16:30 & 20:30, Bob 10:00)
  tests/test_interview_slots.py      11 offline tests (pure window/expand/filter)
  tests/test_scheduling_api.py       DB-backed: endpoints, RBAC, booking + double-book guard
```

---

## 13. Verification status

- **Backend: 79/79 tests pass** (offline + DB-backed).
  - 11 offline slot-engine tests (window rule incl. Friday/weekend rollover, expansion, overlap).
  - 5 DB-backed tests: open-slots, panel listing, slot CRUD, admin-only RBAC (403), and
    **booking + double-book rejection**.
- Migrations `0006`/`0007` applied to real Postgres; tables, `qualified` column, and the
  partial unique index verified present; seed succeeds.
- **Frontend typechecks and builds** clean (all routes, including `/admin` and `/jobs/[id]`).

**Not yet exercised (needs live creds):** an actual phone call end-to-end requires Twilio +
OpenAI Realtime + Deepgram credentials, a public tunnel (ngrok), and `voice_streaming_enabled=true`.
The code path is wired and unit/DB-tested; only the live telephony leg is pending manual test.

---

## 14. Limitations / future work

- Live scheduling is Realtime-path-only; the IVR fallback does not negotiate slots.
- Booked-interview duration is assumed to be 60 minutes for conflict checks (we don't store per-interview length).
- Calendar invites use MS Graph; without creds a mock join link is generated.
- Slot windows are bounded to the current/next week by design (the product rule).
