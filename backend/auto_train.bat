@echo off
title Sifra:Mind — Auto Training
color 0A

echo ==============================================
echo   SIFRA:MIND AUTOMATED TRAINING
echo ==============================================
echo.
echo Starting training session in the background...
echo Please do not close this window until training completes in ~10 mins.
echo.

:: Navigate to the backend folder smoothly regardless of how it was launched
cd /d "%~dp0backend"

:: Run the python script
python training_bot.py

echo.
echo ==============================================
echo   TRAINING COMPLETE
echo ==============================================
pause
