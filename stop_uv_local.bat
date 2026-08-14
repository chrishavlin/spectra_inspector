@echo off
rem Stop the backend and frontend started by start_uv_local.bat. Each service is
rem matched by the window title that start_uv_local.bat gave it and killed along
rem with the process tree below it (uv -> python -> uvicorn workers). taskkill
rem prints "No tasks running with the specified criteria" if a service is not
rem running.

taskkill /fi "WINDOWTITLE eq spectra-inspector-frontend*" /t /f
taskkill /fi "WINDOWTITLE eq spectra-inspector-server*" /t /f
