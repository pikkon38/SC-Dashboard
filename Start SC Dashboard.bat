@echo off
title Star Citizen Dashboard
cd /d "%~dp0companion"
where py >nul 2>nul && (py -3 sc_companion.py %*) || (python sc_companion.py %*)
pause
