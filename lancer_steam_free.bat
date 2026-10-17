@echo off
title Steam Auto Free Games Collector
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   STEAM AUTO FREE GAMES COLLECTOR
echo ========================================================
echo.
python main.py
if errorlevel 1 (
    echo.
    echo Une erreur est survenue lors de l'execution.
    pause
)
