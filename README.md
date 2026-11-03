# AutonomaPI

**An autonomous API testing agent.** Point it at an OpenAPI/Swagger spec (or just a list of URLs) and it plans, executes and scores a full test suite for you — positive cases, adversarial fuzzing, auth-bypass and object-level authorization probes — while streaming its reasoning live to a dashboard.

> Stop hand-writing the same "send garbage, expect a 4xx" tests for every endpoint. AutonomaPI reads your API the way a QA/security engineer would, and tells you where it's actually broken.

---

## Table of Contents

- [Why AutonomaPI](#why-autonomapi)
- [Features](#features)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [Try it on the demo API](#try-it-on-the-demo-api)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [How verdicts are decided](#how-verdicts-are-decided)
- [Privacy & data masking](#privacy--data-masking)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Responsible use](#responsible-use)

---

## Why AutonomaPI

Writing API tests by hand is repetitive and easy to get shallow: most suites check the happy path and a couple of 400s. The bugs that hurt — an endpoint documented as protected that never checks the token, a `200 OK` that leaks a stack trace, an `UPDATE` that returns success but changes nothing — are exactly the ones a status-code-only check misses.

AutonomaPI automates the *thinking* a human tester does:

1. Understand the API's structure and which endpoints depend on each other.
2. Create real test data through those dependencies.
3. Attack each endpoint with schema-aware (and optionally LLM-designed) malicious input.
4. Read the responses, not just the status line.

## Features

| Area | What it does |
|---|---|
| **Three ways to load an API** | Swagger/OpenAPI **URL**, **file upload** (`.json` / `.yaml` / `.yml`, Swagger 2.0 & OpenAPI 3.x), or **Quick Test** — paste endpoint URLs and optional example bodies, no spec needed. |
| **Smart auth detection** | Reads `securitySchemes` (Bearer, Basic, API key in header/query, OAuth2/OIDC) and renders only the credential inputs the spec actually needs. Public endpoints are auto-bypassed. |
| **Dependency chaining** | Testing `DELETE /users/{id}`? The agent first calls `POST /users`, extracts the real `id` from the response, and wires it into the path — recursively for nested resources. |
| **Positive + negative fuzzing** | One schema-valid baseline per endpoint plus type mismatches, missing required fields, boundary violations (empty / 10k-char strings, negative & huge numbers), **SQL injection** and **XSS** probes. |
| **Optional LLM adversarial cases** | With a Gemini API key, the agent asks the model for *endpoint-specific* attacks (negative `quantity`, `role` → `admin`, unit/currency mixups…). Falls back to heuristics automatically on any failure. |
| **Auth-bypass probe** | Replays each protected request with credentials stripped. A `2xx` back is flagged as a critical leak. |
| **BOLA probe** | Replays path-param endpoints against a nonexistent/foreign object id to test object-level authorization. |
| **Response-body leak detection** | Scans even "successful" responses for stack traces, raw DB errors (`SQLSTATE`, `ORA-xxxxx`) and internal file paths. |
| **State-change verification** | After a successful `PUT`/`PATCH`/`DELETE`, re-fetches the resource with `GET` to confirm the change really happened (catches "returns 200 but does nothing"). |
| **Live dashboard** | WebSocket-streamed reasoning terminal, real-time test matrix and metric cards. |
| **Executive PDF report** | One-click PDF export of the run, generated entirely in the browser. |
| **On-box data masking** | Tokens, JWTs, emails, card-like numbers and sensitive JSON keys are scrubbed before logs, snippets or any LLM prompt. |

## How it works

```
 Spec URL / File / Quick URLs
            │
            ▼
   ┌─────────────────┐
   │   SpecParser    │  resolve $refs, flatten into EndpointSpec objects
   └────────┬────────┘
            ▼
   ┌─────────────────┐     ┌──────────────────┐
   │  AuthDetector   │     │ DependencyGraph  │  find creator endpoint,
   │ public/protected│     │ (chaining plan)  │  extract id for path params
   └────────┬────────┘     └─────────┬────────┘
            └──────────┬─────────────┘
                       ▼
            ┌─────────────────────┐        ┌────────────────────┐
            │     TestRunner      │◄───────│ PayloadGenerator   │ heuristic fuzzing
            │ (per-endpoint loop) │◄───────│ LLMCaseGenerator   │ optional Gemini
            └──────────┬──────────┘        └────────────────────┘
                       ▼
            AsyncHTTPExecutor  ──►  your API
                       │
        judge verdict → leak scan → state-change check
                       │
                       ▼
        WebSocket  /ws/runs/{id}  ──►  Next.js dashboard
```

For **every endpoint** the runner executes, in order:

1. **Dependency setup** – provision any ids needed by path params (fresh resource per case for `DELETE`, since each delete consumes it).
2. **Positive baseline** – a fully valid payload; expects `2xx`.
3. **Negative cases** – fuzzed/LLM-designed payloads; expect a `4xx` rejection.
4. **Auth bypass** – (protected endpoints only) same request with credentials removed.
5. **BOLA probe** – (endpoints with path params) same request against id `999999999`.

## Architecture

**Backend** — FastAPI, fully async (`httpx`), with a clean split:

| Module | Responsibility |
|---|---|
| `app/agent/spec_parser.py` | Swagger 2.0 / OpenAPI 3.x loader, `$ref` resolution, security-scheme & schema extraction |
| `app/agent/auth_detector.py` | Maps security schemes to UI fields; builds auth headers/query params; public vs. protected classification |
| `app/agent/dependency_graph.py` | Heuristic resource grouping and creator lookup to build ordered execution plans |
| `app/agent/payload_generator.py` | Faker + schema-driven positive payloads and deterministic negative fuzz set |
| `app/agent/llm_case_generator.py` | Optional Gemini-backed, field-aware adversarial cases (masked input only) |
| `app/agent/leak_detector.py` | Regex signatures for stack traces, DB errors and file paths in response bodies |
| `app/agent/masking.py` | `DataMasker` — scrubs secrets/PII from text, JSON and headers |
| `app/agent/reasoning_agent.py` | Narrates the agent's decisions into the live log |
| `app/executor/test_runner.py` | Orchestrates the run, scores results, emits events |
| `app/executor/http_client.py` | Single async HTTP chokepoint for every request |
| `app/api/routes/` | `upload` (spec ingestion), `run` (start/inspect runs), `stream` (WebSocket) |

**Frontend** — Next.js (App Router) + React + Tailwind CSS v4 + shadcn/ui-style components (Base UI). `hooks/use-run-stream.ts` consumes the WebSocket; `lib/pdf-report.ts` builds the report with jsPDF.

## Tech stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, httpx, Pydantic v2, PyYAML, Faker, python-dotenv
- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, Base UI, lucide-react, jsPDF + jspdf-autotable
- **Optional AI:** Google Gemini via plain REST (no SDK)
- **Realtime:** WebSockets

## Project structure

```
AutonomaPI/
├── backend/                 # FastAPI service (the agent)
│   ├── app/
│   │   ├── agent/           # parsing, auth, chaining, fuzzing, LLM, masking, leak detection
│   │   ├── api/routes/      # upload.py · run.py · stream.py
│   │   ├── core/            # settings, logging
│   │   ├── executor/        # test_runner.py · http_client.py
│   │   ├── schemas/         # Pydantic models (spec + test results)
│   │   ├── ws/              # WebSocket connection manager
│   │   ├── state.py         # in-process spec/run stores
│   │   └── main.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/                # Next.js dashboard
│   ├── app/                 # page.tsx, layout.tsx
│   ├── components/          # config-pane/, dashboard/, ui/
│   ├── hooks/               # use-run-stream.ts
│   └── lib/                 # api client, types, PDF report, formatters
├── sample-api/              # "ShopEase" demo API with an intentionally planted bug
├── run-all.bat              # Windows: launch backend + frontend together
└── README.md
```

## Quick start

### Prerequisites

- Python 3.10+
- Node.js 20+ and npm

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # Windows: copy .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

Health check: <http://localhost:8000/health>

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local     # Windows: copy .env.local.example .env.local
npm run dev
```

Open <http://localhost:3000>.

### One-click start (Windows)

After installing dependencies once, `run-all.bat` opens the backend and frontend in two terminals.

## Try it on the demo API

`sample-api/` is **ShopEase**, a small product/order API built as a test target. It contains one **intentional vulnerability**: `DELETE /products/{product_id}` is documented as requiring a bearer token but never actually checks it. AutonomaPI should catch this as a **CRITICAL_LEAK** via the auth-bypass probe.

```bash
cd sample-api
pip install -r requirements.txt
python -m uvicorn app:app --port 9000
```

Then in the dashboard:

1. **Spec URL** → `http://localhost:9000/openapi.json`
2. Enter the demo bearer token: `shopease-secret-token123`
3. Click **Launch Autonomous Test Run** and watch the reasoning terminal and test matrix.

The demo also exercises dependency chaining: `POST /products → {id} → GET/PUT/DELETE /products/{product_id}` and `POST /products → POST /orders → GET/DELETE /orders/{order_id}`. A pre-generated spec is available at `sample-api/shopease-openapi.json`.

## Configuration

### Backend — `backend/.env`

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed frontend origins |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Per-request timeout for test calls |
| `MAX_NEGATIVE_CASES_PER_ENDPOINT` | `50` | Cap on negative cases per endpoint |
| `GEMINI_API_KEY` | *(empty)* | Optional. Enables LLM-designed adversarial cases. Free key: <https://aistudio.google.com/app/apikey> |
| `GEMINI_MODEL` | see `.env.example` | Gemini model name used for case generation |

With no `GEMINI_API_KEY`, every endpoint uses the built-in heuristic fuzzer — the tool is fully functional offline.

### Frontend — `frontend/.env.local`

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | URL of the AutonomaPI backend |

## API reference

Interactive docs are served by FastAPI at <http://localhost:8000/docs>.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/api/specs/from-url` | Ingest a spec by URL — body `{ "url": "..." }` |
| `POST` | `/api/specs/from-file` | Ingest an uploaded `.json`/`.yaml`/`.yml` spec (multipart) |
| `POST` | `/api/specs/quick` | Build a spec from hand-described endpoints (optional shared bearer token, per-endpoint `public` flag, method auto-detect via `OPTIONS`) |
| `POST` | `/api/runs` | Start a run — body `{ "spec_id", "credentials": { scheme: secret } }` → `{ "run_id" }` |
| `GET` | `/api/runs/{run_id}` | Point-in-time snapshot: status, metrics, results |
| `WS` | `/ws/runs/{run_id}` | Live event stream: `log`, `result`, `metrics`, `status` |

## How verdicts are decided

| Case type | Expected | Verdict if met | Verdict if not |
|---|---|---|---|
| Positive baseline | `2xx` | `passed` | `failed` |
| Type mismatch / missing field / boundary | `4xx` | `passed` | `failed` (accepted malformed input, or `5xx`) |
| SQL injection / XSS / auth bypass / BOLA | `4xx` | `passed` | **`critical_leak`** if a `2xx` is returned |
| Any request | response received | — | `error` on timeout/connection failure |

A `passed` result is then **escalated to `critical_leak`** if the response body contains a leak signature (stack trace, DB error, internal path), or if a successful `PUT`/`PATCH`/`DELETE` isn't reflected by a follow-up `GET`. Escalation only ever makes a verdict stricter — never softer.

## Privacy & data masking

All masking is done locally, with no network calls, via `DataMasker`:

- Bearer tokens, JWTs, `sk-…` style keys, emails and 13–16 digit runs are replaced with `[MASKED]`.
- JSON keys such as `password`, `token`, `authorization`, `api_key`, `secret`, `ssn`, `cvv` are masked by key name.
- Response snippets and log lines are masked before they're stored or broadcast.
- The optional LLM only receives the endpoint's schema and a masked example body — **never credentials or live response data**.

## Known limitations

Being upfront about the current scope:

- **State is in-memory.** Specs and runs live in process memory (`app/state.py`), and WebSocket fan-out is in-process. It's built for single-instance dev/demo use; use Redis or a DB-backed run table before scaling to multiple workers. Restarting the backend clears all runs.
- **Structured specs only.** PDF/Markdown/free-text API docs are not parsed yet (JSON/YAML OpenAPI & Swagger only, plus Quick Test).
- **Heuristic dependency chaining.** Creators are found by resource name and `POST`/`GET` conventions, and ids by `id`/`uuid`-like response fields. Unconventional APIs may need Quick Test or may produce failed setup calls (logged as warnings).
- **Black-box checks only.** Verdicts are based on HTTP behavior; a `4xx` is treated as correct rejection, without validating the error body's contents.
- **Fixed signatures.** SQLi/XSS payloads and leak regexes are a pragmatic baseline, not a replacement for a full DAST/pen-test.
- **Credentials per run** are held in memory and are not persisted.
- **No automated test suite** is included yet.

## Roadmap

- [ ] PDF / Markdown / free-text API documentation ingestion
- [ ] Persistent run history (database) and multi-worker support
- [ ] CI mode: CLI runner with exit codes and JUnit/JSON output
- [ ] OAuth2 flows (token acquisition) instead of pasted tokens
- [ ] Rate-limit, mass-assignment and IDOR (cross-user) probes
- [ ] Unit/integration test suite for the agent modules

## Responsible use

AutonomaPI sends **real, intentionally hostile requests** (including destructive `DELETE`s and injection payloads) to whatever URLs you give it.

- Only test APIs **you own or have explicit written permission to test**.
- Prefer a **staging/test environment** — never point it at production data.
- Never commit your `.env` files or API keys; they are git-ignored in this repo.

---

*Built with FastAPI, Next.js, and a healthy distrust of 200 OK.*
