@echo off
rem Morning job: pull new IPOs from NSE, move statuses forward by date,
rem drop expired login tokens, and back up the database.
rem Run by Windows Task Scheduler ("IPO-PRO sync"). Output goes to logs\sync.log.
cd /d "%~dp0.."
if not exist logs mkdir logs
echo ===== %date% %time% >> logs\sync.log
".venv\Scripts\python.exe" manage.py sync_ipos >> logs\sync.log 2>&1
".venv\Scripts\python.exe" manage.py refresh_ipo_status >> logs\sync.log 2>&1
".venv\Scripts\python.exe" manage.py flushexpiredtokens >> logs\sync.log 2>&1
".venv\Scripts\python.exe" manage.py backup_db >> logs\sync.log 2>&1
