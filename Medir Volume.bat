@echo off
title Medir Volume - Jarvis
cd /d "%~dp0"
echo Bata palmas para ver o pico. Feche a janela ou aperte Ctrl+C para sair.
echo.
"C:\Python310\python.exe" -u ferramentas\medir_volume.py
echo.
echo (encerrado - pressione uma tecla para fechar)
pause >nul
