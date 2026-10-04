@echo off
rem Evening job: ask registrars about every pending application whose
rem allotment date has arrived. Run by Windows Task Scheduler ("IPO-PRO allotment checks").
rem Output goes to logs\checks.log.
cd /d "%~dp0.."
if not exist logs mkdir logs
echo ===== %date% %time% >> logs\checks.log
".venv\Scripts\python.exe" manage.py refresh_ipo_status >> logs\checks.log 2>&1
".venv\Scripts\python.exe" manage.py check_allotments >> logs\checks.log 2>&1
