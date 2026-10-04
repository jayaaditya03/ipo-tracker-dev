# IPO-PRO

Track Indian IPO applications across every PAN in a family: apply to an issue with several PANs at once, record allotment results, and see hit rate, money blocked and listing gains in one place.

- **Backend:** Django 5 + Django REST Framework, JWT auth (SimpleJWT), PostgreSQL
- **Frontend:** Angular 21 on the [Mantis](https://github.com/codedthemes/mantis-free-angular-admin-template) admin theme (Bootstrap 5, ng-bootstrap), in [`frontend/`](frontend/). The theme is MIT-licensed; see [`frontend/LICENSE-MANTIS`](frontend/LICENSE-MANTIS).

## Features

- Email/password accounts with JWT access and refresh tokens.
- PANs are **encrypted at rest** (Fernet), stored with a keyed HMAC for uniqueness checks, and returned only in masked form (`XXXXX1234F`).
- **Real IPO data from NSE:** current, upcoming and recently closed mainboard and SME issues, with price band, lot size and registrar. NSE does not publish allotment and listing dates, so they are estimated from the SEBI T+3 timeline and marked "est." in the UI.
- **Bulk apply:** apply to one IPO with several PANs in one request. A PAN that already has an application for that IPO is skipped, and the rest still go through.
- SEBI rules are enforced: one application per PAN per issue (a database constraint) and the ₹2 lakh retail cap.
- **Automatic allotment checks across all your PANs:** one click asks the registrar for every pending PAN on an issue and records the result (allotted, partial or not allotted) in the audit log. Works on closed and already-listed issues too, for as long as the registrar keeps them on its site. Supported: **KFin, MUFG Intime and Bigshare**, which handle most issues. For other registrars the app links to their status page.
- Status changes go through one method that writes an append-only audit log, shown as the application's history.
- **Dashboard:** stat tiles, applications awaiting a result, and a per-applicant hit-rate table. The figures are computed in SQL.

## Setup

Prerequisites: Python 3.12+, PostgreSQL, Node 24 (its bundled npm 11 is needed for `npm ci` with this lockfile).

```bash
# 1. Database
psql -U postgres -c "CREATE USER ipo_user WITH PASSWORD 'devpassword' CREATEDB;"
psql -U postgres -c "CREATE DATABASE ipo_tracker OWNER ipo_user;"

# 2. Backend
python -m venv .venv
.venv/Scripts/activate            # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env              # then set FIELD_ENCRYPTION_KEY (command is in the file)
python manage.py migrate
python manage.py sync_ipos         # real IPOs from NSE (first run takes a few minutes)
python manage.py createsuperuser  # for /admin
python manage.py runserver        # http://localhost:8000

# 3. Frontend
cd frontend
npm install
npx ng serve                      # http://localhost:4200
```

`CREATEDB` is needed only so pytest can create its test database.

## Day-to-day

| Command | Purpose |
| --- | --- |
| `python manage.py sync_ipos` | Pulls current, upcoming and recent IPOs from NSE. Run it daily. `--past-days N` reaches further back (default 90). |
| `python manage.py refresh_ipo_status` | Updates each IPO's status (Open, Closed, Allotment out, Listed) from today's date. Run it daily. |
| `python manage.py check_allotments` | Asks registrars about every pending application whose allotment date has arrived. Run it a few times on allotment days. |
| `pytest` | Runs the backend test suite. |
| `ruff check .` | Lints the backend. |
| `cd frontend && npx ng build` | Builds the frontend for production. |

## API

All endpoints are under `/api/` and need `Authorization: Bearer <access>`, except register and login.

| Method | Path | |
| --- | --- | --- |
| POST | `/auth/register/`, `/auth/login/`, `/auth/refresh/` | Account and tokens |
| GET/PATCH | `/auth/me/` | Current user |
| CRUD | `/pans/` | Your PANs. Deleting a PAN that has applications deactivates it instead. |
| GET | `/ipos/`, `/ipos/{id}/`, `/ipos/open_now/` | IPO catalogue. Filters: `status`, `board`, `search` |
| CRUD | `/applications/` | Your applications. Filters: `status`, `ipo`, `pan`, `search` |
| POST | `/applications/bulk/` | `{ipo_id, pan_ids[], lots, category, mark_applied}` |
| POST | `/applications/check_pans/` | `{ipo_id, pan_ids[]}`. Checks any issue, including listed ones. Keeps only the applications the registrar confirms. |
| POST | `/applications/check/` | Optional `{ipo_id}` or `{application_ids[]}`. Checks allotment with the registrars, up to 25 PANs per call. |
| POST | `/applications/{id}/set_status/` | `{status, shares_allotted?, note?}` |
| GET | `/applications/{id}/events/` | Status history |
| GET | `/dashboard/summary/` | Totals, hit rate and a per-PAN breakdown |

List endpoints are paginated. Pass `?page_size=` for up to 100 rows per page.

## Project layout

```
accounts/   user model, PAN encryption (crypto.py), auth + PAN endpoints
ipos/       Registrar, IPO, Application, StatusEvent; views; management commands
config/     settings (read from .env), URLs, pagination
tests/      pytest suite
frontend/   Angular app: core/ (API, auth, interceptor), pages/, shared/, theme/ (Mantis layout)
```

## Scheduling (Windows)

Two scripts in `scripts/` run the daily jobs and append their output to `logs/`:

| Task | Script | Runs | Does |
| --- | --- | --- | --- |
| IPO-PRO sync | `scripts/daily-sync.cmd` | 08:00 | `sync_ipos` + `refresh_ipo_status` → `logs/sync.log` |
| IPO-PRO allotment checks | `scripts/daily-checks.cmd` | 21:00 | `refresh_ipo_status` + `check_allotments` → `logs/checks.log` |

Register them once, from the repo root in PowerShell:

```powershell
schtasks /Create /F /TN "IPO-PRO sync" /SC DAILY /ST 08:00 /TR "`"$PWD\scripts\daily-sync.cmd`""
schtasks /Create /F /TN "IPO-PRO allotment checks" /SC DAILY /ST 21:00 /TR "`"$PWD\scripts\daily-checks.cmd`""
```

The tasks run while you're signed in to Windows, and PostgreSQL must be running. Run one immediately with `schtasks /Run /TN "IPO-PRO sync"`, and remove one with `schtasks /Delete /TN "IPO-PRO sync"`. On macOS or Linux, run the same `manage.py` commands from `crontab -e`.

## How the data sources work

Neither NSE nor the registrars publish an official API. The app calls the same endpoints their public web pages use:

- **NSE** (`ipos/sources/nse.py`): needs a browser user-agent and the session cookies NSE's pages set.
- **Registrars** (`ipos/allotment/`): one adapter per registrar.

If a site changes, only its adapter breaks. The rest of the app keeps working, and the UI falls back to a link to the registrar. Requests are spaced at least a second apart per registrar, and only your own PANs are ever queried.
