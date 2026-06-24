# External Permissions & Scopes

Every third-party permission the Recruitment System needs, grounded in the actual
integration code under `backend/app/integrations/`. Each entry maps a permission to the
function that requires it and the feature it powers. Integrations fail **gracefully** (mock
mode / fail-open) when credentials or consent are missing, so a missing permission silently
degrades the related feature rather than crashing.

---

## Microsoft Graph — Teams & Calendar

App-only (client-credentials) flow — the app calls `acquire_token_for_client` with the
`.default` scope, so **all permissions below are _Application_ permissions and require admin
consent** in Entra ID (Azure AD).

**Credentials:** `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`
(absent → `is_mock()` is true and every Graph feature no-ops).

| Permission (Application) | Enables | Function |
|---|---|---|
| **Calendars.ReadWrite** | Create the Teams meeting + calendar invite when an interview is booked (`POST /users/{id}/events`, `isOnlineMeeting: true`) | `create_meeting()` |
| **Calendars.Read** | Real free/busy availability — dynamic interview scheduling (`POST /users/{id}/calendar/getSchedule`). *Superseded by Calendars.ReadWrite; list separately only if scoping minimally.* | `get_availability()` |
| **ChannelMessage.Read.All** | Read candidate feedback threads + replies from a Teams channel (`GET /teams/{id}/channels/{id}/messages`) | `list_channel_messages()` |
| **User.Read.All** | Resolve a Teams message author's AAD id → email, to verify the assigned interviewer (`GET /users/{id}`) | `get_user_email()` |
| **Channel.ReadBasic.All** | List a team's channels (admin setup helper) (`GET /teams/{id}/channels`) | `list_channels()` |

### Caveats
- **`ChannelMessage.Read.All` (app-only) is a Microsoft "protected API."** Beyond admin
  consent it needs a separate [app-only access request](https://learn.microsoft.com/graph/teams-protected-apis)
  (payment model or Evaluation Mode). It returns **403** until granted.
- **Application Access Policy.** Tenants can restrict which mailboxes an app may read/write
  calendars for (`New-ApplicationAccessPolicy`). Interviewers outside the policy return a
  per-schedule error → free/busy **fails open** (keeps internal-only slot filtering) for them.

---

## Google / Gmail — resume auto-ingestion & email replies

**Scope:** `https://www.googleapis.com/auth/gmail.modify`
(one scope covers both reading messages for resume polling and sending replies).

Use **one** of two auth setups:

1. **Service account + domain-wide delegation**
   `GOOGLE_SERVICE_ACCOUNT_JSON`, `GMAIL_IMPERSONATE_EMAIL`
   A Workspace admin must authorize the service-account **client ID** for the `gmail.modify`
   scope under **Admin Console → Security → API controls → Domain-wide delegation**.
2. **OAuth (user consent)**
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
   OAuth consent screen approving `gmail.modify`.

---

## Twilio — telephonic screening calls

Account capabilities/config (not API scopes) that must be enabled:

- Account credentials: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`.
- A **Voice-capable phone number**: `TWILIO_PHONE_NUMBER`.
- **Programmable Voice + Media Streams** — bidirectional `<Connect><Stream>` for the realtime
  audio bridge.
- **Voice Geographic Permissions** for the destination country (outbound dialing enabled).
- Publicly reachable webhook/WS URLs (ngrok in dev) for the answer URL, status callback, and
  the media-stream WebSocket.

---

## OpenAI

`OPENAI_API_KEY` with account access to:
- the configured chat model (LLM scoring / extraction / question generation),
- the **Realtime API** (`gpt-realtime`) — the live voice screening agent,
- transcription (Whisper) as STT fallback.

---

## Deepgram — speech-to-text

`DEEPGRAM_API_KEY` with access to the **`nova-2`** model (prerecorded + live streaming).

---

## Quick reference — minimum to run each feature

| Feature | Required permissions |
|---|---|
| Book interview + Teams meeting link | MS Graph **Calendars.ReadWrite** (admin consent) |
| Dynamic free/busy scheduling | MS Graph **Calendars.Read** (or ReadWrite) + Application Access Policy covering interviewer mailboxes |
| Read interview feedback from Teams | MS Graph **ChannelMessage.Read.All** (protected API) + **User.Read.All** |
| Resume auto-ingestion + replies | Gmail **gmail.modify** (service account w/ DWD or OAuth) |
| Telephonic screening calls | Twilio Voice number + Media Streams + geo permissions |
| Live voice agent | OpenAI key w/ Realtime API access |
| Transcription | Deepgram key (`nova-2`); OpenAI Whisper fallback |
