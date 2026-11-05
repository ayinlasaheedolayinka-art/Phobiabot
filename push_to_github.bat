@echo off
title Push Scout Bot to GitHub
cd /d "%~dp0"

echo ========================================================
echo   Pushing Scout Bot to GitHub
echo   Repository: https://github.com/ayinlasaheedolayinka-art/Phobiabot
echo ========================================================
echo.

set GIT_EXE=C:\Git\cmd\git.exe
if not exist "%GIT_EXE%" (
    set GIT_EXE=C:\Users\phobia\AppData\Local\Programs\Git\cmd\git.exe
)

"%GIT_EXE%" config --global --add safe.directory "%~dp0"
"%GIT_EXE%" config --global --add safe.directory *

echo Running git push...
echo (If a browser window appears, click Authorize/Sign-in)
echo.
"%GIT_EXE%" push -u origin main

echo.
pause
