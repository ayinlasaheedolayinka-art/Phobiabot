@echo off
title Push Scout Bot to GitHub
cd /d "%~dp0"
echo Adding folder to Git safe directory...
"C:\Users\phobia\AppData\Local\Programs\Git\cmd\git.exe" config --global --add safe.directory "C:/Users/phobia/Desktop/scout bot"
"C:\Users\phobia\AppData\Local\Programs\Git\cmd\git.exe" config --global --add safe.directory *

echo Pushing Scout Bot to https://github.com/ayinlasaheedolayinka-art/Phobiabot ...
echo.
"C:\Users\phobia\AppData\Local\Programs\Git\cmd\git.exe" push -u origin main
echo.
pause
