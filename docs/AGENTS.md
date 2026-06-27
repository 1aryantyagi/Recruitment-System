# Recruitment Platform — Agents

This document describes the seven pipeline agents that power the ATS workflow.
They live under `backend/app/agents/` and are orchestrated with **LangGraph
`StateGraph`**. LLM calls go through **LangChain** (`app/llm/client.py`) — not
LangChain's autonomous agent framework (`AgentExecutor`, ReAct, tool-calling
agents).

Built from the specifications in
[`product-req.md`](./product-req.md) (§7) and
[`technical-requirements.md`](./technical-requirements.md) (§7). See also
[`README.md`](./README.md) for project setup and stack overview.

> **Stack note.** Orchestration = LangGraph. LLM = LangChain (`ChatOpenAI` /
> `ChatAnthropic` + `with_structured_output`). Agents are chained via Python
> function calls and FastAPI `BackgroundTasks`, not a single mega-graph.

---

## Quick reference

| # | Agent | Module | Graph? | LLM? | Sync / Async | Primary trigger |
|---|--------|--------|--------|------|--------------|-----------------|
| 1 | Resume Intake | `resume_intake.py` | Yes | Yes | Sync | `POST /candidates`, Gmail poll |
| 2 | Resume Scoring | `resume_scoring.py` | Yes | No | Sync | After intake; `POST /requisitions` |
| 3 | Telephonic Screening | `telephonic_screening.py` | Yes (×2) | Yes | Mixed | `POST /screening/start-call`, Twilio webhooks |
| 4 | Interview Scheduling | `interview_scheduling.py` | Yes | No | Sync | `POST /interviews` |
| 5 | Interview Analysis | `interview_analysis.py` | Yes | Yes | Async | `POST /interviews/{id}/recording` |
| 6 | Feedback Collection | `feedback_collection.py` | Yes (notify only) | No | Chained / Sync | Agent 5 → notify; `POST /interviews/{id}/feedback` |
| 7 | Analytics | `analytics.py` | No | Optional | On-demand | `GET /analytics/*` |

---

## Architecture

```
API / Scheduler / Webhooks
        │
        ▼
┌───────────────────────────────────────┐
│  LangGraph StateGraph (.invoke())     │
│  validate → process → persist → emit  │
└───────────────────────────────────────┘
        │
        ├──► SQLAlchemy (PostgreSQL)
        ├──► Integrations (Twilio, MS Graph, STT, storage)
        └──► LangChain LLM (structured output / text)
```

### LangGraph vs LangChain

| Layer | Role | Used for |
|-------|------|----------|
| **LangGraph** | Workflow orchestration | Node functions, edges, conditional routing, `.compile()` + `.invoke()` |
| **LangChain** | Model client only | `complete_structured()` and `complete_text()` in `app/llm/client.py` |
| **Not used** | LangChain Agents | No `AgentExecutor`, ReAct, or tool-calling agent loops |
| **Not wired** | `MemorySaver` checkpointer | Defined in `common.py` but graphs compile without it |

---

## End-to-end pipeline

```
Upload / Gmail ──► Agent 1 (Intake) ──► Agent 2 (Scoring)
                                              ▲
New Requisition ──────────────────────────────┘

Screening start ──► Agent 3 start graph ──► Twilio (opening_line, next_turn)
                                                    │
Call completed ──► Agent 3 post-call graph ─────────┘

Schedule ──► Agent 4 (Scheduling)

Recording upload ──► [Background] Agent 5 (Analysis) ──► Agent 6 (Notify)

Feedback form ──► submit_feedback (no graph)

Dashboard ──► Agent 7 (SQL; optional LLM digest)
```

**Flow layer** (`app/services/flow.py`): runs Agent 3 post-call and Agent 5 in
background with a semaphore (max 4 concurrent LLM/STT jobs).

---

## Agent 1 — Resume Intake

**File:** `backend/app/agents/resume_intake.py`  
**Entry:** `run_intake()`  
**Triggers:** `POST /candidates`, `POST /candidates/{id}/resume`, Gmail scheduler (`poll_gmail`)

### State graph

```
START → validate ──skip──► END
           │
        continue
           ▼
        upload → extract_text → llm_extract → normalize → persist → emit_analytics → END
```

### Nodes

| Node | Purpose |
|------|---------|
| `validate` | File type, Gmail dedup |
| `upload` | Save file to storage |
| `extract_text` | PDF/DOCX text extraction |
| `llm_extract` | Structured resume parse (`ResumeExtraction`) |
| `normalize` | Skill alias resolution |
| `persist` | Create/update candidate + resume version |
| `emit_analytics` | `CANDIDATE_ADDED` event |

### LLM

- Tier: `extraction`
- Schema: `ResumeExtraction`
- Fallback: placeholder summary when LLM unavailable

---

## Agent 2 — Resume Scoring

**File:** `backend/app/agents/resume_scoring.py`  
**Entry:** `run_scoring_for_candidate()`, `run_scoring_for_requisition()`  
**Triggers:** After Agent 1; `POST /requisitions` (score pool vs new req)

### State graph

```
START → resolve_pairs → compute → persist → emit_analytics → END
```

### Scoring model (v1)

| Dimension | Weight |
|-----------|--------|
| Skills match | 40% |
| Experience fit | 20% |
| Skill depth | 20% |
| Location / work mode | 10% |
| Notice period | 10% |

**No LLM** — deterministic heuristics. Above-threshold pairs auto-create
`JobApplication` records.

---

## Agent 3 — Telephonic Screening

**File:** `backend/app/agents/telephonic_screening.py`  
**Entries:** `start_call()`, `process_call()`, plus `opening_line()` / `next_turn()`
for live conversation

### Start-call graph

```
START → validate → generate_questions → initiate_call → persist → END
```

| Node | Purpose |
|------|---------|
| `validate` | Block duplicate active calls |
| `generate_questions` | LLM or `DEFAULT_QUESTIONS` |
| `initiate_call` | Twilio outbound (mock if no creds) |
| `persist` | `CallLog` INITIATED, move app to SCREENING |

**Trigger:** `POST /screening/start-call`

### Post-call graph

```
START → transcribe → extract_qa → persist → emit_analytics → END
```

| Node | Purpose |
|------|---------|
| `transcribe` | Live transcript or STT from recording |
| `extract_qa` | `ScreeningEvaluation` per question |
| `persist` | COMPLETED; SHORTLISTED if score ≥ threshold |
| `emit_analytics` | `CALL_COMPLETED` event |

**Triggers:** Twilio status webhook (`completed`), mock mode via `BackgroundTasks`

### Live conversation (outside graphs)

| Function | Called from | Purpose |
|----------|-------------|---------|
| `opening_line()` | `POST /webhooks/twilio/answer` | Turn 0 script |
| `next_turn()` | `POST /webhooks/twilio/turn` | Per-turn reply + action |

Uses `ConversationDirective` (LLM) with scripted fallback.

---

## Agent 4 — Interview Scheduling

**File:** `backend/app/agents/interview_scheduling.py`  
**Entry:** `schedule_interview()`  
**Trigger:** `POST /interviews`

### State graph

```
START → validate → create_interview → send_invite → emit_analytics → END
```

| Node | Purpose |
|------|---------|
| `validate` | No duplicate active round |
| `create_interview` | `Interview` SCHEDULED |
| `send_invite` | MS Graph calendar event |
| `emit_analytics` | `INTERVIEW_SCHEDULED`; app → INTERVIEW_SCHEDULED |

**No LLM.**

---

## Agent 5 — Interview Analysis

**File:** `backend/app/agents/interview_analysis.py`  
**Entry:** `analyze_interview()`  
**Trigger:** `POST /interviews/{id}/recording` → `flow.run_interview_analysis` (202 + background)

### State graph

```
START → store_recording → transcribe → llm_analyze → persist → trigger_agent6 → END
```

| Node | Purpose |
|------|---------|
| `store_recording` | Save audio to storage |
| `transcribe` | STT |
| `llm_analyze` | `InterviewAnalysis` (4 dimensions + recommendation) |
| `persist` | Update interview + seed feedback draft |
| `trigger_agent6` | Chain feedback notification |

### LLM

- Tier: `analysis` (Claude Opus when Anthropic configured)
- Schema: `InterviewAnalysis`

---

## Agent 6 — Feedback Collection

**File:** `backend/app/agents/feedback_collection.py`

### Notify graph (auto-chained from Agent 5)

```
START → resolve_interviewer → send_notification → emit_analytics → END
```

**Entry:** `notify_for_interview()` — logs notification + `FEEDBACK_REQUESTED` event.

### Human feedback (no graph)

**Entry:** `submit_feedback()`  
**Trigger:** `POST /interviews/{id}/feedback`  
Upserts `InterviewFeedback`; emits `FEEDBACK_SUBMITTED` on submit.

---

## Agent 7 — Analytics

**File:** `backend/app/agents/analytics.py`  
**No LangGraph** — pure SQL aggregation.

| Function | Route | Description |
|----------|-------|-------------|
| `dashboard()` | `GET /analytics/dashboard` | Totals, funnel, sources, open reqs, time-to-hire |
| `funnel()` | `GET /analytics/funnel` | Pipeline stage counts |
| `sources()` | `GET /analytics/sources` | Hire rate by candidate source |
| `time_to_hire()` | `GET /analytics/time-to-hire` | Avg days to HIRED |
| `requisition_analytics()` | `GET /analytics/requisitions/{id}` | Per-req pipeline |
| `digest()` | `?summary=true` on dashboard | Optional LLM summary (`short` tier) |

---

## LLM usage matrix

| Agent | Function | Tier | Schema / output |
|-------|----------|------|-----------------|
| 1 | `llm_extract` | extraction | `ResumeExtraction` |
| 3 | `generate_questions` | short | `QuestionSet` |
| 3 | `next_turn` | short | `ConversationDirective` |
| 3 | `llm_extract_qa` | extraction | `ScreeningEvaluation` |
| 5 | `llm_analyze` | analysis | `InterviewAnalysis` |
| 7 | `digest` | short | free text |

Provider resolution: `ANTHROPIC_API_KEY` → Claude; else `OPENAI_API_KEY` → OpenAI.
See `app/llm/client.py`.

---

## Shared conventions (`common.py`)

- `normalize_skill()` — canonical skill resolution via aliases
- `map_proficiency()` — enum mapping for extracted proficiency
- `get_checkpointer()` — `MemorySaver` stub for future async durability (not used yet)
