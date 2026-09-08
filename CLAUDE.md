# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

The `backend/` and `frontend/` skeletons exist and boot (routers registered, auth/rate-limit/CORS wired, most route bodies still TODO stubs pending each owner's real implementation — see `guidelines/4_프롬프트_브리프.md` for who owns what). The specs in `guidelines/0`–`6` remain the binding source of truth for what gets built; read the relevant file(s) below before writing any code here, and follow them exactly rather than inventing an alternative structure. Each teammate works on their own branch (`feature/<name>`) and merges into `main` — check `git log`/`git branch -a` for what's already landed vs. still pending review before assuming a file's current content.

## What this project is

"신입 업무보조 챗봇 + 업무 적응도 리포트" — an onboarding assistant for new hires. A mentor (사수) uploads a handover document, assigns it to one newcomer (신입), and the newcomer can then chat with a RAG bot scoped to that document and check off a checklist. The mentor separately views an AI-generated "adaptation report" built from the newcomer's chat/checklist activity (never shown to the newcomer).

Three people are building this in parallel against the frozen specs in `guidelines/`:

| Owner | Modules | Spec sections |
|---|---|---|
| 조장 (lead) | Chatbot (RAG), checklist draft generation, adaptation report | `guidelines/4_프롬프트_브리프.md` §4-1 |
| 팀원 A | Document processing (chunk/embed), checklist edit/save/complete | §4-2 |
| 팀원 B | User/Assignment backend, entire React frontend | §4-3 |

## Source-of-truth documents (read before implementing)

- `guidelines/0_목적_사용법.md` — how to use these docs; **data model, API spec, tech stack, and folder structure are frozen and may only be changed by 조장** — do not improvise around them.
- `guidelines/1_시스템_개요.md` — system overview: user types, screen layout, module responsibilities, storage split, the cross-layer rules in §1-5/§1-7 (chatbot only searches the newcomer's *assigned* document; failed answers never mention "we'll improve the docs"; checklist completion is an unverified self-check by design, used as a report signal), and §1-8's seeded demo mode (3 pre-seeded companies, reachable without registering, for judges/voters).
- `guidelines/2_공통_데이터_모델.md` — the exact Pydantic models (`User`, `Assignment`, `DocumentChapter`, `DocumentChunk`, `ChatLog`, `ChecklistItem`, `AdaptationReport`, `ReportSection`) and their field names/types. Every module exchanges data using these; do not rename or add fields. `User` includes `email`/`password_hash` — never return `password_hash` in an API response.
- `guidelines/3_API_명세.md` — exact endpoints, request/response shapes, the common error format `{"error": true, "message": "..."}`, and the auth rules in §3-9 (every endpoint except `/user/register`/`/user/login` requires a `Bearer` token; the server verifies the token's `user_id`/`role` against the identity fields in the request, it doesn't just trust them).
- `guidelines/4_프롬프트_브리프.md` — per-owner requirement briefs (copy-paste ready); §4-1's chatbot/report/draft requirements are the most detailed spec for RAG behavior and report signal definitions.
- `guidelines/5_기술스택_폴더구조.md` — tech stack, the frozen folder layout, `main.py` router-registration pattern, env var names, HTTP status code mapping, git branch strategy, deployment plan (Vercel + Railway), and §5-9's cost/traffic defenses (rate limiting, request size caps, OpenAI billing hard limit).
- `guidelines/6_통합_체크포인트.md` — integration schedule, the 9-step end-to-end test scenario (§6-3) that must pass before submission, §6-5's explicit "not in 1차, revisit after 예선" list (email verification, password reset, refresh tokens) — don't implement those without checking with 조장 first — and §6-6's demo-seeding plan (`backend/scripts/seed_demo.py`, run once before the 9/18 deploy).

## Architecture (once implemented, per the frozen spec)

**Stack**: FastAPI backend, MySQL (structured data), ChromaDB local PersistentClient (embeddings, one collection per `document_id`), OpenAI API for LLM calls, LangGraph for multi-step logic (chat answer generation, checklist draft generation, report signal computation), React frontend.

**Backend layout** (`backend/`):
- `main.py` — single FastAPI app; each module registers its router with `app.include_router(...)`, calls `load_dotenv()` before any other import (env vars are read at module-import time throughout `core/`, so this must run first), and holds the three global exception handlers that normalize every error response to `{"error": true, "message": "..."}` regardless of whether it came from `HTTPException`, Pydantic validation (422), or a rate-limit hit (429) — don't let a router raise a raw, unhandled shape.
- `schemas/` — Pydantic models for API request/response bodies, one file per model group (`user.py`, `assignment.py`, `document.py`, `chat.py`, `checklist.py`, `report.py`). Frozen field names/types per guidelines §2.
- `models/` — the actual MySQL tables (SQLAlchemy ORM), 1:1 filenames and ownership with `schemas/`. Each file's classes inherit the shared `Base` from `core/database.py`; `main.py` imports every `models/*.py` module (so its classes register on `Base`) and calls `Base.metadata.create_all(bind=engine)` once at startup — add your model file's import there when you create it. `schemas/` (API shape) and `models/` (DB shape) both stay; don't collapse them into one.
- `core/` — shared `database.py` (MySQL engine/session + the shared `Base`), `chroma_client.py` (ChromaDB), `auth.py` (JWT issue/verify + password hashing + the `get_current_user` dependency, owned by 팀원 B), `rate_limit.py` (slowapi config, owned by 조장).
- `routers/` — one file per owner/domain (`user.py`, `assignment.py`, `document.py`, `checklist.py`, `checklist_draft.py`, `chat.py`, `report.py`). Files are individually owned — only touch your own router file.

**Frontend layout** (`frontend/src/`): `api/client.js` (shared axios instance), `services/router/*.js` (one file per backend router, 1:1 naming), `pages/{newcomer,hr}/`, `components/{newcomer,hr}/`, `styles/`.

**Key request-flow rule**: the chatbot and report modules never trust a `document_id` directly from the client — they look up `Assignment` by `newcomer_id` first to find the document the newcomer is actually scoped to, then restrict ChromaDB search / report aggregation to that scope. A newcomer with no `Assignment` gets a 404 from `/chat/ask`. The same discipline applies to `GET /document/{document_id}/chapters` (guidelines §3-9): being logged in isn't enough since chapter content is exposed — the caller must either own the document (mentor) or be assigned to it (newcomer), which requires `document.py` (팀원 A) to check `Assignment` (팀원 B's model) rather than trusting the path parameter alone.

**Checklist draft vs. save split**: `POST /checklist/draft` (조장's module) only *previews* AI-generated `{title, chapter_id}` candidates — it does not write to MySQL. Saving/editing (조장's draft output or a mentor's manual entries) always goes through `POST /checklist` and friends, owned by 팀원 A. Don't merge these two responsibilities into one module.

**Auth**: login (`POST /user/login`) issues a JWT; the frontend sends it as `Authorization: Bearer <token>` on every other request. Every router-level handler (other than register/login) depends on `core.auth.get_current_user` and must check that the token's `user_id`/`role` matches the identity fields in the request body/query — the request still carries `newcomer_id`/`mentor_id` as before (schemas are unchanged), but those values are no longer trusted at face value. This includes `GET /assignment?newcomer_id=`/`?mentor_id=` (guidelines §3-9) — only the newcomer/mentor named in the query may read their own assignment, not just anyone with a valid token. Email verification is explicitly out of scope for 1차 (§6-5) — `email` exists only as a unique login identifier.

**Reassignment**: `POST /assignment` on a newcomer who already has an active assignment updates that row in place (new `document_id`, same `assignment_id`) rather than inserting a new one, and leaves `Assignment.assigned_at` untouched — `/report/generate`'s default `period_start` for a first-time report reads `assigned_at`, so overwriting it would silently reset every newcomer's report window on reassignment (guidelines §2-2, §3-1).

**Cost defense**: `/chat/ask`, `/checklist/draft`, `/report/generate` call OpenAI directly and are rate-limited both per-`user_id` and per-IP (guidelines §5-9) — per-user alone isn't enough since account creation has no email verification gate. Cap `max_tokens` on every OpenAI call. The demo newcomer accounts (§1-8) are shared by many simultaneous visitors, so `core/rate_limit.py` keys them on `user_id` + visitor IP instead of `user_id` alone (via the `DEMO_USER_IDS` env var, populated after `seed_demo.py` runs) — otherwise every judge testing the same seeded company would draw down one shared 10/minute bucket.

**Document input**: `/document/upload` accepts either `file` (auto-parsed into chapters) or a pre-structured `chapters: list[{title, content}]` (from the mentor's "직접 입력" form — no auto-parsing, saved as-is). Both paths still run per-chapter chunking/embedding into `DocumentChunk`; the chunk-size heuristic itself stays 팀원 A's discretion regardless of input path (guidelines §3-2, §4-2).

## Commands (once the skeleton exists)

- Backend: `uvicorn main:app --reload` from `backend/`, fixed port `8000`.
- Env vars (see `guidelines/5_기술스택_폴더구조.md` §5-4 for the full list): `OPENAI_API_KEY`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `CHROMA_PERSIST_DIR`, `JWT_SECRET_KEY`, `JWT_EXPIRE_MINUTES`, `DEMO_USER_IDS`. Real values go in `.env` (gitignored); only `.env.example` is committed. An empty `JWT_SECRET_KEY=` line in `.env` is treated the same as unset (falls back to a dev default with a logged warning) — don't assume a blank value means "disabled".
- No test suite or lint config exists yet in this repo — check `backend/requirements.txt` / `frontend/package.json` once they're added rather than assuming a framework.

## Conventions specific to this repo

- Field names and types in `schemas/` are frozen by spec — do not rename or restructure them even if a different name reads better.
- Don't add new top-level API endpoints beyond `guidelines/3_API_명세.md` without flagging it to 조장 first (per §0's change-control rule); the one standing exception is adding your own router's `import`/`include_router` lines in `main.py`.
- Keep module boundaries per §1-5: checklist draft generation (조장) only reads `DocumentChapter` from MySQL — no ChromaDB access; checklist edit/save (팀원 A) is MySQL-only too.
- Chat failure responses must never imply the document will be improved/expanded — that framing is reserved for the HR-facing report only (§1-7, §4-1).
- Git branches: `feature/조장`, `feature/팀원A`, `feature/팀원B`, merged into `main`. Conflicts in `schemas/`, `core/`, `main.py` are resolved by 조장; conflicts inside a single owner's folder are resolved by that owner.
- Before implementing password reset, refresh tokens, or actual email-verification delivery, check `guidelines/6_통합_체크포인트.md` §6-5 — these are deliberately deferred past 1차, not forgotten.
