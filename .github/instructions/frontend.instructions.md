---
applyTo: "templates/index.html,static/js/main.js,static/js/setup.js,static/css/styles.css"
---

# Frontend — Copilot Instructions

These instructions apply when editing the web UI (HTML, JS, CSS).

## Architecture

- **`templates/index.html`** — Single-page Flask template. Contains the full HTML structure rendered by `web_app.py`.
- **`static/js/main.js`** — Core UI logic: SSE streaming from `/api/generate/stream` and `/api/answer/stream`, TSG rendering via `marked` + `DOMPurify`, copy/download, PII modal, warning banners, image handling.
- **`static/js/setup.js`** — Setup wizard: configuration form, validation via `/api/validate`, agent creation via `/api/setup/stream`.
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
- Validates config, creates agents via SSE stream, stores IDs in `.agent_ids.json`

## Conventions

- No build step — vanilla JS, no bundler, no framework
- Markdown rendering uses `marked.min.js` + `purify.min.js` (vendored in `static/js/`)
- SSE streaming uses native `EventSource` API
- CSS uses custom properties (variables) defined at `:root` in `styles.css`
- Warning banners are generated from the `warnings` array in the pipeline response (sourced from `accuracy_issues` + `suggestions`)

## Warnings Display

Warnings from the review stage (`accuracy_issues`, `suggestions`) appear as a banner between TSG output and follow-up questions. Warnings must:
- Never block TSG display
- Never appear inside the rendered TSG content
- Be dismissible by the user
