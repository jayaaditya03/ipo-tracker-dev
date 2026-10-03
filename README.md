# IPO Allotment Tracker

Track Indian IPO applications across every PAN in a family: apply to an issue with several PANs at once, record allotment results, and see hit rate, money blocked and listing gains in one place.

- **Backend:** Django 5 + Django REST Framework, JWT auth (SimpleJWT), PostgreSQL
- **Frontend:** Angular 20 (standalone components, signals), in [`frontend/`](frontend/)

## Features

- Email/password accounts with JWT access and refresh tokens.
- PANs are **encrypted at rest** (Fernet), stored with a keyed HMAC for uniqueness checks, and returned only in masked form (`XXXXX1234F`).
- **Real IPO data from NSE:** current, upcoming and recently closed mainboard and SME issues, with price band, lot size and registrar. NSE does not publish allotment and listing dates, so they are estimated from the SEBI T+3 timeline and marked "est." in the UI.
- **Bulk apply:** apply to one IPO with several PANs in one request. A PAN that already has an application for that IPO is skipped, and the rest still go through.
- SEBI rules are enforced: one application per PAN per issue (a database constraint) and the ₹2 lakh retail cap.
- **Automatic allotment checks across all your PANs:** one click asks the registrar for every pending PAN on an issue and records the result (allotted, partial or not allotted) in the audit log. Supported: **KFin, MUFG Intime and Bigshare**, which handle most issues. For other registrars the app links to their status page.
- Status changes go through one method that writes an append-only audit log, shown as the application's history.
- The dashboard's aggregate figures are computed in SQL.

## Setup

Prerequisites: Python 3.12+, PostgreSQL, Node 20+.

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
| `python manage.py sync_ipos` | Pulls current, upcoming and recent IPOs from NSE. Run it daily. `--past-days N` reaches further back (default 45). |
| `python manage.py refresh_ipo_status` | Updates each IPO's status (Open, Closed, Allotment out, Listed) from today's date. Run it daily. |
| `python manage.py check_allotments` | Asks registrars about every pending application whose allotment date has arrived. Run it a few times on allotment days. |
| `python manage.py seed_ipos` | Loads 6 made-up demo issues. Use it for offline demos only. |
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
frontend/   Angular app: core/ (API, auth, interceptor), pages/, shared/
```

## Scheduling (Windows)

Run the daily jobs with Task Scheduler, for example:

```powershell
$py  = "C:\path\to\ipo-tracker\.venv\Scripts\python.exe"
$dir = "C:\path\to\ipo-tracker"
schtasks /Create /TN "IPO sync"   /SC DAILY /ST 08:00 /TR "cmd /c cd /d $dir && $py manage.py sync_ipos"
schtasks /Create /TN "IPO checks" /SC DAILY /ST 19:00 /TR "cmd /c cd /d $dir && $py manage.py check_allotments"
```

On macOS or Linux, add the same two commands to `crontab -e`.

## How the data sources work

Neither NSE nor the registrars publish an official API. The app calls the same endpoints their public web pages use:

- **NSE** (`ipos/sources/nse.py`): needs a browser user-agent and the session cookies NSE's pages set.
- **Registrars** (`ipos/allotment/`): one adapter per registrar.

If a site changes, only its adapter breaks. The rest of the app keeps working, and the UI falls back to a link to the registrar. Requests are spaced at least a second apart per registrar, and only your own PANs are ever queried.
