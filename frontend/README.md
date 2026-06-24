# Talent OS — Frontend

A premium, enterprise-grade UI for the AI Recruitment Multi-Agent System + ATS.
Rebuilt from a basic CRUD dashboard into a modern recruiting operating system
(in the spirit of Ashby / Greenhouse / Linear), wired to the live FastAPI backend.

> **Stack:** Next.js 15 (App Router) · React 19 · TypeScript · Tailwind CSS v4 ·
> shadcn/ui (Radix) · Recharts · dnd-kit · next-themes · Framer Motion · lucide-react · sonner

---

## Highlights

- **Full design system** — shadcn/ui primitives on Radix, token-driven theming, **light + dark mode**.
- **Ashby/Greenhouse aesthetic** — calm neutral palette + indigo accent, soft shadows, `rounded-xl` cards, tabular numerals, generous spacing.
- **App shell** — collapsible sidebar, top bar with **⌘K command palette**, notifications, theme toggle, profile menu, and a floating **AI Assistant** slide-over.
- **13 pages** covering the full hiring workflow; everything backed by the real API except three clearly-labeled mock previews.
- **Drag-and-drop ATS pipeline** that persists stage moves to the database.
- Loading **skeletons**, **empty** + **error** states, keyboard/focus accessibility, and responsive layouts everywhere.

---

## Getting started

```bash
# from repo root, start the DB + backend first (see ../README.md)
docker compose up -d db
cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000

# frontend
cd ../frontend
npm install
cp .env.local.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                            # http://localhost:3000
```

**Dev logins (seeded):**

| Email | Password | Role |
| ----- | -------- | ---- |
| `admin@local.dev` | `admin123` | ADMIN |
| `hr@local.dev` | `hr123` | HR |
| `dm@local.dev` | `dm123` | DELIVERY_MANAGER |

> **Node version:** use **Node 24** (`nvm use`; see `../.nvmrc`) for `next dev`.
> Production `next start` runs fine on newer Node, but the dev server can misbehave on Node 25+.

---

## Pages

Routes live under the `(app)` route group (shared `AppShell` layout); login lives under `(auth)`.

| Route | Purpose | Data source |
| ----- | ------- | ----------- |
| `/login` | Split-screen sign-in with demo accounts | `POST /auth/login` |
| `/dashboard` | Executive KPIs, hiring funnel, source performance, **AI insights**, open-req health | `GET /analytics/dashboard?summary=true` |
| `/candidates` | Faceted candidate table, search (FTS), bulk select, CSV export, resume upload | `GET /candidates`, `POST /candidates` |
| `/candidates/[id]` | Premium profile: AI analysis, score breakdown, skills, **activity timeline**, tabs | `GET /candidates/{id}` |
| `/jobs` | Requisition list with status/domain filters, create job | `GET /requisitions` |
| `/jobs/[id]` | Spec, required skills, **ranked scored pipeline**, interviewer assignment | `GET /requisitions/{id}`, `/candidates`, `/interviewers` |
| `/pipeline` | **Drag-and-drop ATS Kanban** across stages; persists moves | `GET /applications`, `PATCH /applications/{id}` |
| `/interviews` | Month / agenda **calendar**, detail drawer, schedule, recording upload | `GET /interviews`, `POST /interviews` |
| `/evaluations` | AI analysis + structured human **scorecard** (1–5 ratings, recommendation) | `GET /interviews?analyzed`, `/interviews/{id}/feedback` |
| `/analytics` | Enterprise reporting: funnel, sources, time-to-hire, AI performance | `GET /analytics/*` |
| `/agents` | **AI Agents Center** — 7 LangGraph agents + live activity feed | `GET /analytics/dashboard`, recent entities |
| `/team` | Members, interviewers, recurring availability slots | `GET /users`, `/interviewers`, slot endpoints |
| `/settings` | Profile, **Gmail integration**, skills catalog | `/integrations/gmail/*`, `/skills` |
| `/talent-pool`, `/outreach`, `/offers` | **Preview** — mock data, no backend yet | `lib/mock.ts` |

The **AI Assistant** (floating button / ⌘ launcher) is a UI shell with real quick-actions
that deep-link into live workflows; the conversational reply is a labeled preview (no chat backend).

---

## Project structure

```
frontend/
├── app/
│   ├── layout.tsx                 # ThemeProvider → AuthProvider → TooltipProvider + <Toaster/>
│   ├── globals.css                # design tokens (oklch), light/dark, brand palette, utilities
│   ├── page.tsx                   # auth-aware redirect (/dashboard | /login)
│   ├── (auth)/login/page.tsx
│   └── (app)/
│       ├── layout.tsx             # renders <AppShell>
│       └── {dashboard,candidates,candidates/[id],jobs,jobs/[id],pipeline,
│              interviews,evaluations,analytics,agents,team,settings,
│              talent-pool,outreach,offers}/page.tsx
├── components/
│   ├── ui/                        # shadcn primitives (button, card, dialog, select, command, …)
│   ├── layout/                    # app-shell, sidebar, topbar, command-palette, theme-toggle, ai-assistant
│   ├── common/                    # page-header, kpi-card, stat, score, badges, avatar-name,
│   │                              #   states (empty/error/skeletons), chart-card, data-table, filter-bar
│   ├── candidates/                # upload-resumes-modal, blacklist-modal
│   ├── jobs/                      # create-job-modal, assign-interviewers-panel
│   ├── pipeline/                  # kanban-board (+ column/card)
│   ├── interviews/                # schedule/feedback modals, slot-picker, calendar, detail-sheet
│   └── theme-provider.tsx
└── lib/                           # api, auth, hooks, meta, types, utils  (reused, extended)
    ├── labels.ts                  # status/stage/recommendation → tone + label maps; PIPELINE_STAGES
    ├── nav.ts                     # role-aware sidebar + command-palette config
    └── mock.ts                    # sample data for the three preview pages
```

---

## Design system

**Theming** — All colors are semantic CSS variables (oklch) defined in `app/globals.css`
for `:root` (light) and `.dark`, mapped via Tailwind v4 `@theme inline`. Components use
tokens only (`bg-card`, `text-muted-foreground`, `bg-primary`, `border`, …) so dark mode is
automatic. Dark/light/system is toggled via `next-themes` (top-bar control).

**Primitives** (`components/ui/`) — hand-authored shadcn (new-york style) on Radix:
button, card, badge, input, textarea, label, select, dialog, sheet, tabs, tooltip,
dropdown-menu, popover, avatar, separator, skeleton, progress, switch, checkbox,
scroll-area, table, command, sonner.

**Shared building blocks** (`components/common/`) — `PageHeader`, `KpiCard`, `Stat`,
`ScoreRing`/`ScoreBar`, status `Badge`s, `AvatarName`, `EmptyState`/`ErrorState`/skeletons,
`ChartCard`/`ChartTooltip`, generic `DataTable<T>`, `FilterBar`.

**Data layer** (`lib/`) — the original typed fetch client (`api.ts` with token refresh),
`AuthProvider`/`useAuth`, `useFetch`/`useDebounce`, and the meta hooks
(`useSkills`/`useDomains`/`useInterviewers`/`useOpenSlots`/…) were **kept and extended**, not replaced.

---

## Backend endpoints added for this UI

Three small, well-scoped additions (no DB migration — existing tables; mirrors existing patterns):

| Endpoint | Purpose |
| -------- | ------- |
| `GET /applications` | Board-ready application list (candidate, requisition, score, owner, latest interview) — one call fills a Kanban board |
| `PATCH /applications/{id}` | Persist a stage move → updates status, writes `application_status_history`, emits `STATUS_CHANGED` analytics event |
| `GET /interviews` | Global interview list (joined candidate + requisition names) with `from`/`to`/`status`/`analyzed`/`needs_feedback` filters — powers the calendar and evaluations queue |

Files: `backend/app/api/routes/applications.py` (new, registered in `app/main.py`), the global
list added to `backend/app/api/routes/interviews.py`, and `UpdateApplicationStatusRequest` in
`backend/app/schemas/api.py`.

---

## Scripts

```bash
npm run dev     # dev server (use Node 24)
npm run build   # production build (type-check + lint + prerender)
npm run start   # serve the production build
npm run lint    # eslint
```

## Verification status

- `tsc --noEmit` — clean
- `next build` — all 18 routes compiled, linted, prerendered
- New backend endpoints tested live against seeded data (list → stage move persisted & reverted → global interviews + filters)
- Production server serves every route `200`

## Not yet wired (good next steps)

- **Talent Pool, Outreach, Offers** — currently mock previews (`lib/mock.ts`); need backend endpoints.
- **AI Agents** success-rate / queue figures are representative — add an agent-telemetry endpoint to make them real.
- **AI Assistant** chat — needs a backend conversational endpoint.
- **Notifications** in the top bar use placeholder data.
