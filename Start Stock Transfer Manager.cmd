@echo off
rem One-click start for Stock Transfer Manager.
rem Checks the Python environment and MySQL (starting the service if needed), then opens the app.
rem Options are passed through, for example:  "Start Stock Transfer Manager.cmd" -CheckOnly
title Stock Transfer Manager
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0UI\launch.ps1" %*
