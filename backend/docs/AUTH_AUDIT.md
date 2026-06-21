# Authentication & Authorization Audit — Recruitment System (ATS)

_Date: 2026-06-21 · Scope: backend (FastAPI) + frontend (Next.js) auth/authz_

---

## 1. Executive summary

A full audit of the authentication and authorization stack was performed, tracing
every request path from frontend → API → service → database, and reviewing all
route definitions, the JWT/bcrypt layer, the ORM models, migrations, seed data,
and environment configuration.

**Key finding: login is _not_ broken.** It was verified working end-to-end against
the live database (see §2). The codebase already had a sound auth foundation
(bcrypt, JWT, role-based access control on nearly every endpoint, signed-token
file access, Twilio-signature webhooks). Rather than fabricate a fix for a
non-existent defect, this engagement (a) documents the verified-correct state and
(b) closes the genuine gaps and adds the production hardening below.

**What changed:**
1. **Authorization** — added per-record **owner-only writes** (horizontal access control) on all mutating endpoints. Previously any HR/DM could edit any record by ID.
2. **Sessions** — added **refresh tokens with rotation, reuse-detection, and revocation**; shortened the access-token lifetime. Logout now actually revokes server-side.
3. **Hardening** — fail-fast on a weak `SECRET_KEY` in staging/production; tightened CORS; added security response headers.
4. **Tests** — added 18 auth/authz tests (login, token validation, RBAC, refresh rotation, ownership). Full suite: **63 passing**.

---

## 2. Root-cause analysis: "why is login broken?"

**Conclusion: no defect found. Login works correctly.** The likely real-world
trigger for a "login fails" report is operational — database not started,
migrations not applied, or seed not run — not a code bug.

Evidence gathered against the running stack (all read-only):

| Check | Result |
|---|---|
| Postgres container (`recruitment-system-db-1`, port 5434) | Up, healthy |
| Seed users present | 5 users, all `is_active=true` |
| Stored password format | `$2b$12$…`, 60 chars (valid bcrypt) |
| `bcrypt.checkpw("admin123", stored_hash)` | `True` |
| `POST /auth/login` valid creds (`admin`, `hr`) | `200` + JWT |
| `POST /auth/login` wrong password | `401 UNAUTHENTICATED` |
| `POST /auth/login` unknown user | `401 UNAUTHENTICATED` |

The login path itself is correct:
- `authenticate_user` (`app/core/auth.py`) normalizes email (`.lower().strip()`), rejects users with no `password_hash`, and verifies with bcrypt constant-time compare.
- Passwords are never stored in plaintext (`hash_password`/`verify_password` in `app/core/security.py`, bcrypt 4.3.0).
- JWT is HS256 signed with `SECRET_KEY`; `get_current_user` decodes, validates expiry, loads the user, and checks `is_active`.
- Sensitive fields (`phone`, `current_ctc`, `expected_ctc`) are encrypted at rest with AES-256-GCM.

**Operational runbook** (the actual "fix" if login appears broken):
```bash
cd backend
docker compose up -d db
alembic upgrade head
python -m scripts.seed     # admin@local.dev/admin123, hr@local.dev/hr123, dm@local.dev/dm123, ...
```

---

## 3. Full endpoint inventory & auth coverage

Legend — **Public**: no JWT (justified). **JWT**: any authenticated user.
**Role**: JWT + role gate. **+Owner**: JWT + role gate + per-record ownership check (new).

### Auth
| Method | Path | Protection | Notes |
|---|---|---|---|
| POST | `/auth/login` | Public | issues access + refresh |
| POST | `/auth/refresh` | Public* | *validated by the refresh token itself (rotation) — **new** |
| POST | `/auth/logout` | JWT | revokes the refresh token server-side — **hardened** |
| GET | `/auth/me` | JWT | |
| POST | `/auth/users` | Role: ADMIN | |

### Users / interviewers
| Method | Path | Protection |
|---|---|---|
| GET | `/users` | Role: ADMIN |
| GET | `/interviewers` | Role: HR, DM, ADMIN |
| POST | `/interviewers` | Role: ADMIN |

### Candidates
| Method | Path | Protection |
|---|---|---|
| POST | `/candidates` | Role: HR |
| GET | `/candidates` | Role: HR, DM, ADMIN (shared read) |
| GET | `/candidates/{id}` | Role: HR, DM, ADMIN (shared read) |
| PATCH | `/candidates/{id}` | Role: HR **+Owner** |
| POST | `/candidates/{id}/resume` | Role: HR **+Owner** |
| POST | `/candidates/{id}/confirm-skills` | Role: HR **+Owner** |
| GET | `/candidates/{id}/resume` | Role: HR, DM, ADMIN |
| POST | `/candidates/{id}/blacklist` | Role: HR, ADMIN **+Owner** |
| DELETE | `/candidates/{id}/blacklist` | Role: ADMIN |

### Requisitions
| Method | Path | Protection |
|---|---|---|
| POST | `/requisitions` | Role: HR, DM |
| GET | `/requisitions` | Role: HR, DM, ADMIN (shared read) |
| GET | `/requisitions/{id}` | Role: HR, DM, ADMIN (shared read) |
| PATCH | `/requisitions/{id}` | Role: HR, DM **+Owner** (created_by / hiring_manager) |
| GET | `/requisitions/{id}/candidates` | Role: HR, DM, ADMIN |

### Interviews
| Method | Path | Protection |
|---|---|---|
| POST | `/interviews` | Role: HR |
| GET | `/interviews/{candidate_id}` | Role: HR, DM, ADMIN (shared read) |
| PATCH | `/interviews/{id}` | Role: HR **+Owner** (created_by) |
| POST | `/interviews/{id}/recording` | Role: HR **+Owner** (created_by) |
| POST | `/interviews/{id}/feedback` | Role: HR **+Owner** (created_by / interviewer) |
| GET | `/interviews/{id}/feedback` | Role: HR, DM, ADMIN |

### Screening / analytics / skills / meta
| Method | Path | Protection |
|---|---|---|
| POST | `/screening/start-call` | Role: HR |
| GET | `/screening/{candidate_id}/calls` | Role: HR, DM, ADMIN |
| GET | `/analytics/*` (5 routes) | Role: HR, DM, ADMIN |
| GET | `/skills` | JWT |
| POST | `/skills`, `/skills/{id}/aliases` | Role: ADMIN |
| GET | `/domains`, `/departments`, `/status-reasons` | JWT |

### Intentionally public (credential-gated by other means)
| Method | Path | Gate |
|---|---|---|
| GET | `/health`, `/` | none (health/metadata only) |
| GET | `/files/{token}` | signed, expiring, scoped JWT in the URL |
| POST | `/webhooks/twilio/*` (3) | `X-Twilio-Signature` HMAC verification |
| WS | `/webhooks/twilio/media-stream` | signed stream token |
| GET | `/integrations/gmail/callback` | signed OAuth `state` (CSRF) |

**Coverage result: every endpoint is authenticated, or intentionally public with a
non-JWT credential gate. No accidental auth bypass exists.**

---

## 4. Vulnerabilities / gaps found and fixes

### V1 — Missing horizontal access control (owner-only writes) · **High**
**Before:** Every mutating endpoint was role-gated but had **no per-record ownership
check** — any HR could edit/blacklist any candidate, any HR/DM could edit any
requisition, any HR could modify any interview by ID. The models carried
`uploaded_by` / `created_by` / `hiring_manager_id` / `interviewer_id` but they were
never consulted.

**Fix:** New helper `ensure_can_modify(user, *owner_ids)` in `app/core/auth.py`,
called inside each mutating route after the record is fetched:
- ADMIN may act on any record (where ADMIN is in the route's role gate).
- Otherwise the caller must be one of the record's owners.
- Records with **no owner** (e.g. email-ingested candidates, `uploaded_by IS NULL`)
  are treated as shared/org-owned and fall back to the role gate — so the team is
  never locked out of system-created records.
- **Reads remain shared** across the recruiting team (collaborative ATS model);
  only writes are owner-scoped.

**Applied to:** `PATCH /candidates/{id}`, `POST /candidates/{id}/resume`,
`POST /candidates/{id}/confirm-skills`, `POST /candidates/{id}/blacklist`,
`PATCH /requisitions/{id}`, `PATCH /interviews/{id}`,
`POST /interviews/{id}/recording`, `POST /interviews/{id}/feedback`.

**After:** A non-owner HR editing another user's candidate now receives
`403 UNAUTHORIZED`; the owner and ADMIN succeed; unowned records remain editable by
any in-role user.

### V2 — No refresh tokens / unrevocable sessions · **Medium**
**Before:** A single stateless 8-hour access JWT, no refresh mechanism, and
`logout` was a no-op (the token stayed valid until expiry — no server-side
revocation possible).

**Fix:** Full refresh-token system:
- New `refresh_tokens` table (`app/models/auth.py`, migration `0005`). Only the
  **SHA-256 hash** of each token is stored — a DB read never yields a usable token.
- Access-token TTL default shortened to **30 min**; refresh-token TTL **14 days**
  (both env-configurable; existing `.env` overrides still honored).
- `POST /auth/login` returns `{access_token, refresh_token, …}`.
- `POST /auth/refresh` validates + **rotates** (old token revoked, new pair issued).
- **Reuse detection:** presenting an already-revoked token is treated as theft and
  revokes the **entire token family** for that user, forcing re-login.
- `POST /auth/logout` revokes the presented refresh token.
- Frontend (`lib/api.ts`) transparently rotates on a `401` and retries the request
  once; concurrent 401s share one in-flight refresh.

### V3 — Weak default `SECRET_KEY` could ship to production · **Medium**
**Before:** `SECRET_KEY` defaulted to `dev-secret-change-me`; nothing prevented a
real deployment from running with a forgeable JWT secret.

**Fix:** A pydantic `model_validator` in `app/config.py` refuses to boot in
`staging`/`production` if `SECRET_KEY` is blank or a known dev default, or if
`ENCRYPTION_KEY` is unset. Development stays permissive.

### V4 — Permissive CORS & missing security headers · **Low**
**Before:** `allow_methods=["*"], allow_headers=["*"]`; no security response headers.

**Fix:** CORS scoped to `GET/POST/PATCH/DELETE/OPTIONS` and
`Authorization/Content-Type`; a middleware adds `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and (production only)
`Strict-Transport-Security`.

### V5 — Live secrets present in working-tree `.env` · **Informational (no code change)**
The repo-root `.env` contains live API keys (OpenAI, Twilio, Google, Microsoft,
Deepgram). It **is gitignored and not committed**, but the keys are real.
**Recommendation: rotate these keys** and inject them via a secrets manager in any
shared/deployed environment. `SECRET_KEY` should also be set to a strong unique
value (now enforced by V3).

---

## 5. Files changed

**New**
- `backend/app/models/auth.py` — `RefreshToken` model
- `backend/alembic/versions/0005_refresh_tokens.py` — migration
- `backend/tests/test_auth.py` — 18 auth/authz tests
- `backend/docs/AUTH_AUDIT.md` — this report

**Modified (backend)**
- `app/core/auth.py` — `ensure_can_modify`; refresh-token service (issue/rotate/revoke/revoke-all)
- `app/api/routes/auth.py` — login returns refresh; new `/auth/refresh`; logout revokes
- `app/api/routes/candidates.py`, `requisitions.py`, `interviews.py` — ownership checks
- `app/config.py` — refresh TTL, shorter access TTL, prod weak-secret validator
- `app/main.py` — CORS tightening + security-headers middleware
- `app/models/__init__.py` — register `RefreshToken`
- `app/schemas/api.py` — `RefreshRequest`, `LogoutRequest`

**Modified (frontend)**
- `lib/api.ts` — refresh-token storage, auto-refresh-on-401 + retry
- `lib/auth.tsx` — store both tokens on login; revoke on logout
- `lib/types.ts` — `refresh_token` on `LoginResponse`; `RefreshResponse`

---

## 6. Verification

```
$ python -m pytest
63 passed in 5.19s
```
- `tests/test_auth.py` (18): login success/failure, missing/garbage/expired/wrong-secret token → 401, RBAC 200/403, refresh rotation + reuse-detection + logout revocation, owner/non-owner/admin/unowned write checks.
- All pre-existing suites (`test_api`, `test_unit`, `test_detail_collection`, `test_gmail_auth`, `test_screening_conversation`) still pass — no regressions.

Manual end-to-end (TestClient against live DB), all confirmed:
- login → access + refresh; access token authorizes a protected route.
- `/auth/refresh` rotates; reused old token → `401` and revokes the family; logout → refresh no longer valid.
- non-owner HR `PATCH` another user's candidate → `403`; owner → `200`; unowned (`uploaded_by=NULL`) → any HR `200`.
- prod guard: `APP_ENV=production` + default `SECRET_KEY` → app refuses to boot.

---

## 7. Notes on design decisions

- **Shared read, owner-only write** was chosen (over strict per-user isolation)
  because an ATS is collaborative: the recruiting team works a shared candidate and
  requisition pool. Locking reads to the creator would break the product.
- **ADMIN cannot edit candidate _fields_** (`PATCH /candidates` is HR-only by
  existing design); the ADMIN ownership-override therefore applies only on endpoints
  where ADMIN is already in the role gate (e.g. blacklist). This preserves the
  existing role model rather than expanding ADMIN's surface.
- The access-token TTL default is now 30 min, but the repo `.env` still sets
  `ACCESS_TOKEN_EXPIRE_MINUTES=480`; with refresh tokens wired in the frontend,
  lowering that env value is safe and recommended for shorter exposure windows.
