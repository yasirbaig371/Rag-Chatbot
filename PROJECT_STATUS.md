# Multi-Role RAG Chatbot — Project Status

## Current Status
- **Current phase:** Phase 8 — Final Verification & Deployment
- **Completed locally:** Phases 1–7, Phase 8 deployment preparation
- **Next action:** Revoke/rotate the exposed OpenRouter credential, configure production Render/Vercel/PostgreSQL values, run the production migration, deploy, and verify the live user flow.
- **Not done:** No cloud service, production database, or Vercel site has been deployed from this workspace.

## Phase Checklist
- [x] **Phase 1 — Database & scaffolding:** PostgreSQL/Alembic schema, five application tables, environment templates, and interactive admin bootstrap.
- [x] **Phase 2 — Backend auth & users:** registration, login, refresh rotation/reuse detection, logout, profile, password change, role dependencies, and tests.
- [x] **Phase 3 — Documents & RAG:** PDF validation and ingestion, status/hash/page metadata, Chroma persistence, access-controlled retrieval, citations, and tests.
- [x] **Phase 4 — Chat & admin APIs:** owned chat CRUD, RAG messages, admin users/roles/status, last-active-admin protections, statistics, and session summaries.
- [x] **Phase 5 — Frontend scaffolding & auth:** pinned React/Vite/Tailwind setup, login/register, protected routes, role-aware navigation, in-memory access token, single refresh retry.
- [x] **Phase 6 — User frontend:** scoped chat, document selector, sources, history, profile, and password updates.
- [x] **Phase 7 — Admin frontend:** dashboard, paginated/searchable user management, PDF upload/progress/status, visibility, deletion.
- [x] **Phase 8 — Local verification & deploy preparation:** tests/build, README, Dockerfile, Render blueprint, health check configuration.
- [ ] **Phase 8 — Live deployment:** requires credential rotation and owner-controlled provider/database configuration.

## Verification Results
- Backend: `cd backend && venv\Scripts\python.exe -m pytest -q` — **52 passed** against `rag_test_db` (final run: 26.85s).
- Backend syntax: `python -m compileall -q app tests` — passed.
- Route registration: chat and admin endpoint smoke checks — passed.
- Frontend: `npm run build` — passed using the pinned React 18.3.1, Vite 5.4.10, Axios 1.7.7, React Router 6.27.0 versions (final build: 16.88s).
- Browser smoke check: login and registration screens render; backend was not running during this UI-only check.
- Live RAG check: real text PDF → local embedding → temporary Chroma → supplied free-tier OpenRouter model returned an answer with document title and page citation. Temporary index removed.
- Dependency audit: `npm audit --omit=dev` reports four high advisories in pinned Axios/React Router dependencies. Versions remain as specified; review/approve a version change before production use.
- Install note: a Windows file lock interrupted `npm ci`; `npm install` restored dependencies and the production build passed afterward.

## Security and Operational Blockers
- A credential-shaped OpenRouter value was found in `backend/.env.example`; it was replaced with a placeholder. **Treat the exposed value as compromised and revoke/rotate it before further use.** Never send a replacement key in chat. The root `.gitignore` excludes `.env` files.
- `backend/.env.example` and `backend/.env` select `nvidia/nemotron-3-ultra-550b-a55b:free` to reduce model cost. OpenRouter free-model availability and limits can change.
- `RAG_DISTANCE_THRESHOLD=1.2` is an initial setting; calibrate it against representative documents and relevant/irrelevant questions before production.
- Live deployment, production migrations, backup/recovery testing, and production end-to-end verification remain owner-controlled tasks.
- Render Chroma/PDF persistence requires a mounted disk and a single backend instance. Coordinated PostgreSQL, PDF, and Chroma backups are required.

## Key Files
- Backend routes: `backend/app/api/routes/auth.py`, `users.py`, `documents.py`, `chat.py`, `admin.py`
- Backend services: `backend/app/services/pdf_service.py`, `chroma_service.py`, `rag_service.py`, `llm_service.py`
- Backend schemas: `backend/app/schemas/`
- Tests: `backend/tests/`
- Frontend: `frontend/src/`
- Deployment: `backend/Dockerfile`, `render.yaml`
- Setup and deployment instructions: `README.md`
