@echo off
rem Morning job: pull new IPOs from NSE, then move statuses forward by date.
rem Run by Windows Task Scheduler ("IPO-PRO sync"). Output goes to logs\sync.log.
cd /d "%~dp0.."
if not exist logs mkdir logs
echo ===== %date% %time% >> logs\sync.log
".venv\Scripts\python.exe" manage.py sync_ipos >> logs\sync.log 2>&1
".venv\Scripts\python.exe" manage.py refresh_ipo_status >> logs\sync.log 2>&1
