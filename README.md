# FinTrack — Personal Finance & Subscription Tracker

A Python web application with an interactive dashboard and REST API for managing income,
expenses, monthly budgets and recurring bills. It
**automatically discovers subscriptions hidden in your bank statements**, forecasts
renewals, flags price increases and warns before you overspend.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 · PostgreSQL / SQLite · Pydantic v2 ·
JWT auth · Chart.js dashboard · pytest (56 tests, 98% coverage) · Git · Jenkins CI/CD ·
Docker · ruff · mypy

---

## Features

| Area | What it does |
|---|---|
| **Dashboard** | Web page at `/`: monthly income, expenses, remaining balance, savings rate, spending-by-category chart, budget usage bars, 6-month income vs. expense chart, upcoming bills, add/delete transactions, CSV upload, one-click subscription scan |
| **Auth** | Registration, OAuth2 password flow issuing JWTs, salted PBKDF2-SHA256 hashing, constant-time compare |
| **Transactions** | CRUD, filtering (date range, kind, category, merchant), pagination, merchant-name normalization |
| **CSV import** | Bulk-load bank statements; **idempotent** (re-uploading inserts nothing), partial success with per-row error reports |
| **Subscription detection** | Finds recurring charges (weekly / monthly / quarterly / yearly) with a confidence score, predicts next renewal, flags price changes, ignores cancelled plans |
| **Subscriptions** | Track plans, normalize all billing cycles to monthly cost, upcoming-renewal calendar with total due |
| **Budgets** | Monthly per-category limits with `ok` / `at_risk` / `warning` / `exceeded` status and month-end spend projection |
| **Analytics** | Monthly income/expense trend with month-over-month change, category share of spend, ranked top merchants: raw SQL with CTEs and window functions |
| **Ops** | `/health` probe, request-ID propagation, structured latency logging, Docker + Compose, Jenkins pipeline (lint → type check → tests → Docker image) |

## Architecture

```
   Dashboard (HTML + JS + Chart.js, served at /)
                 │
            HTTP (JSON)                          
                 │                               
   ┌─────────────▼──────────────┐   routers/   — validation, auth, HTTP status codes
   │  FastAPI routers + deps    │                (thin: no business logic)
   └─────────────┬──────────────┘
   ┌─────────────▼──────────────┐   services/  — business rules, transactions, SQL
   │  Service layer             │   recurrence.py is pure (no DB) → unit-testable
   └─────────────┬──────────────┘
   ┌─────────────▼──────────────┐   models.py  — SQLAlchemy ORM, constraints, indexes
   │  SQLAlchemy 2.0 ORM        │
   └─────────────┬──────────────┘
          PostgreSQL / SQLite
```

```
fintrack/
├── main.py            app factory, middleware, router wiring
├── config.py          12-factor settings from environment variables
├── models.py          users, categories, transactions, subscriptions, budgets
├── schemas.py         request/response contracts (Pydantic)
├── security.py        password hashing + JWT
├── deps.py            DI: DB session per request, current user, injectable clock
├── money.py / dates.py / merchants.py   domain utilities
├── routers/           auth, categories, transactions, subscriptions, budgets, reports
├── static/            dashboard page (index.html, app.js, styles.css)
└── services/          business logic + recurrence-detection algorithm + SQL analytics
tests/                 unit tests + API integration tests (in-memory DB per test)
scripts/seed_demo.py   generates a realistic year of bank data for demos
```

## Engineering decisions

1. **Money as integer cents.** Floats can't represent 0.10 exactly; all arithmetic is
   integer cents, and the API returns exact decimal strings (`"15.49"`).
2. **Recurrence detection algorithm (O(n log n)).** Group charges by normalized merchant,
   sort by date, take the **median** gap between charges (robust to one late payment,
   unlike the mean), map it to a billing cycle, then score
   `confidence = 0.6 × schedule regularity + 0.4 × amount stability`. Series that stopped
   charging are treated as cancelled. See [`services/recurrence.py`](fintrack/services/recurrence.py).
3. **Idempotent imports.** Each CSV row gets a SHA-256 content key backed by a
   `UNIQUE(user_id, dedupe_key)` constraint. The key includes the row's occurrence count
   within the file, so two identical coffees on the same day are both kept, but
   re-uploading the same file is a no-op. Existing-key lookups are chunked to respect
   database bound-parameter limits.
4. **Drift-free date math.** Renewals are computed as *anchor + n cycles*, never by
   repeatedly adding a month, so Jan 31 → Feb 28 → **Mar 31** (not Mar 28).
5. **Multi-tenant isolation.** Every query is scoped by `user_id`. Another user's resource
   returns **404, not 403**, so ids can't be probed.
6. **Query performance.** Composite indexes on `(user_id, occurred_on)` and
   `(user_id, merchant)` match the hot query paths; `selectinload` removes N+1 queries;
   budget status uses one `GROUP BY` instead of a query per budget.
7. **SQL analytics.** `LAG()` for month-over-month change, `SUM(SUM(x)) OVER ()` for share
   of total, `RANK()` for ties, all parameterized (no SQL injection) and portable across
   SQLite and PostgreSQL.
8. **Testability.** The app factory gives each test its own in-memory database, and "today"
   is an injected dependency, so date-based logic is deterministic.
9. **REST semantics.** `PUT` budgets is an idempotent upsert; `GET /upcoming` rolls stale
   renewal dates forward in memory instead of writing during a read.

## Quick start

```bash
python -m venv .venv
```
```bash
.venv\Scripts\activate        # Windows  (macOS/Linux: source .venv/bin/activate)
```
```bash
pip install -r requirements-dev.txt
```
```bash
python -m scripts.seed_demo
```
```bash
uvicorn fintrack.main:create_app --factory --reload
```

Open **http://localhost:8000** for the dashboard and sign in as
`demo@fintrack.dev` / `demo-password-123`.

To explore the API directly, open **http://localhost:8000/docs**, click **Authorize**,
log in with the same account, and try:

- `POST /api/v1/subscriptions/detect`: finds Netflix, Spotify, iCloud and Adobe (plus
  rent and utilities as recurring bills), and skips the Hulu plan that stopped charging
  and the irregular grocery and dining spend
- `GET /api/v1/subscriptions/upcoming?days=30`
- `GET /api/v1/budgets/status`
- `GET /api/v1/reports/monthly-trend`

### Deploy for free on Render

[`render.yaml`](render.yaml) deploys the app as a free Render web service: in the Render
dashboard choose **New → Blueprint** and select this repository. Every push to `main`
redeploys automatically. The free plan resets its disk on restart, so the hosted demo
recreates the demo account at startup (`FINTRACK_SEED_DEMO=true`) and sleeps after
15 minutes idle (the first visit afterwards takes up to a minute to wake it).

### With Docker (PostgreSQL)

```bash
docker compose up --build
```

### Tests and quality checks

```bash
pytest
```
```bash
ruff check . && mypy fintrack
```

## CI/CD with Jenkins

The [`Jenkinsfile`](Jenkinsfile) defines a declarative pipeline that runs on every push:

1. **Install**: create a virtualenv and install dependencies
2. **Lint**: `ruff check .`
3. **Type check**: `mypy fintrack`
4. **Test**: `pytest`, publishing JUnit results and failing below 90% coverage
5. **Build Docker image**: on `main` only

To use it, create a *Multibranch Pipeline* job in Jenkins pointing at this repository
(Linux agent with Python 3.11+ and Docker). A GitHub Actions workflow with the same
checks is also included in `.github/workflows/ci.yml`.

## API overview

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/token` | Log in (OAuth2 form) → JWT |
| GET | `/api/v1/auth/me` | Current user |
| GET/POST | `/api/v1/categories` | List / create categories |
| GET/POST | `/api/v1/transactions` | Filtered, paginated list / create |
| GET/PATCH/DELETE | `/api/v1/transactions/{id}` | Read / update / delete |
| POST | `/api/v1/transactions/import` | Upload CSV statement |
| GET/POST | `/api/v1/subscriptions` | List (filter by status) / create |
| GET/PATCH/DELETE | `/api/v1/subscriptions/{id}` | Read / update / delete |
| GET | `/api/v1/subscriptions/upcoming?days=30` | Renewal calendar + total due |
| GET | `/api/v1/subscriptions/summary` | Monthly/annual cost, breakdown by cycle |
| POST | `/api/v1/subscriptions/detect?apply=true` | Detect recurring charges (optionally track them) |
| GET/PUT | `/api/v1/budgets` | List / upsert category budget |
| GET | `/api/v1/budgets/status?month=YYYY-MM` | Spend vs. limit with projection |
| DELETE | `/api/v1/budgets/{id}` | Remove a budget |
| GET | `/api/v1/reports/dashboard?month=YYYY-MM` | Everything the dashboard shows, in one call |
| GET | `/api/v1/reports/monthly-trend` | Income, expenses, net, MoM change |
| GET | `/api/v1/reports/category-breakdown` | Spend and % share per category |
| GET | `/api/v1/reports/top-merchants` | Ranked merchants by spend |
| GET | `/health` | Liveness + DB connectivity |

## Possible extensions

Alembic migrations · Redis caching for reports · rate limiting · refresh tokens ·
background job for renewal reminder emails · deploy to AWS (ECS Fargate + RDS) ·
user-facing alerts by email.
