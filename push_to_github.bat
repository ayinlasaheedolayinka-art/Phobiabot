@echo off
title Push Scout Bot to GitHub
cd /d "%~dp0"
echo Pushing Scout Bot to https://github.com/seedorphobia/Phobia ...
echo.
"C:\Users\%USERNAME%\AppData\Local\Programs\Git\cmd\git.exe" push -u origin main
echo.
pause
