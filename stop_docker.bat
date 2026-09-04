@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0stop_docker.ps1" %*
