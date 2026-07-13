@echo off
title Medir Voz - Jarvis
cd /d "%~dp0"
echo Fale frases normais a distancia normal e observe a barra. Ctrl+C sai.
echo.
"C:\Python310\python.exe" -u medir_voz.py
echo.
echo (encerrado - pressione uma tecla para fechar)
pause >nul
