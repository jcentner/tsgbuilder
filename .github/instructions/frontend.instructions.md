---
applyTo: "templates/index.html,static/js/main.js,static/js/setup.js,static/css/styles.css"
---

# Frontend — Copilot Instructions

These instructions apply when editing the web UI (HTML, JS, CSS).

## Architecture

- **`templates/index.html`** — Single-page Flask template. Contains the full HTML structure rendered by `web_app.py`.
- **`static/js/main.js`** — Core UI logic: SSE streaming from `/api/generate/stream` and `/api/answer/stream`, TSG rendering via `marked` + `DOMPurify`, copy/download, PII modal, warning banners, image handling, quality feedback, and session save/load.
- **`static/js/setup.js`** — Setup wizard: configuration form, validation via `/api/validate`, agent creation via `POST /api/create-agent`.
- **`static/css/styles.css`** — CSS custom properties for theming, component styles for the setup modal, TSG display, warnings, and PII modal.

## Key UI Flows

### TSG Generation
1. User pastes notes → frontend calls PII check → if clean, streams from `/api/generate/stream` via SSE
2. SSE events update stage progress indicators (Research → Write → Review)
3. Final TSG rendered as markdown; warnings displayed in banner below output
4. If `{{MISSING::...}}` placeholders exist, follow-up question inputs are shown

### PII Modal
- Shown when PII is detected in notes or follow-up answers
- Two actions: "Go Back & Edit" (returns to input) or "Redact & Continue" (uses API redaction)
- PII check also runs on follow-up answers at `/api/answer/stream`

### Setup Wizard
- Opens automatically if agents not configured (checked via `/api/status`)
- Validates config, creates agents via `POST /api/create-agent` JSON response, stores IDs in `.agent_ids.json`

### Session Save/Load
- **Persisted sessions** use a `session_id` (UUID) distinct from the pipeline `thread_id`. Client stores `currentSessionId` and sends it in generate/answer requests; the server echoes it back in the `result` SSE event.
- **Auto-save**: every successful run persists server-side; `onSessionAutoSaved()` shows a brief toast.
- **Explicit save** (💾): `saveSession()` → `POST /api/sessions` with notes + images (+ thread_id).
- **Sessions modal** (📂): `GET /api/sessions` list; `loadSession()` restores notes, images, TSG, warnings, and iteration state via `GET /api/sessions/<id>`; delete/rename via `DELETE` / `PUT /api/sessions/<id>/label`.
- **Unsaved-work guard**: `beforeunload` warns when notes/TSG exist but `currentSessionId` is null.
- Persisted-session endpoints are plural (`/api/sessions`), distinct from the in-memory `DELETE /api/session/<thread_id>` cleanup.
- **No native dialogs**: rename uses an inline editable field and delete uses a two-click confirm — `prompt()`/`confirm()` throw "not supported" in some embedded browser contexts.

## Conventions

- No build step — vanilla JS, no bundler, no framework
- Markdown rendering uses `marked.min.js` + `purify.min.js` (vendored in `static/js/`)
- SSE streaming uses native `EventSource` API
- CSS uses custom properties (variables) defined at `:root` in `styles.css`
- Review feedback is generated from the `warnings` array in the pipeline response (sourced from `accuracy_issues` + `suggestions`)

## Warnings Display

Warnings from the review stage (`accuracy_issues`, `suggestions`) appear in the feedback panel outside the rendered TSG content. Warnings must:
- Never block TSG display
- Never appear inside the rendered TSG content
- Let the user address or skip them during follow-up
