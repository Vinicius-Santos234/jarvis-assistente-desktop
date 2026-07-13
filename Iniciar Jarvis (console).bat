@echo off
rem Inicia o Jarvis COM janela de console - util para calibrar as palmas e
rem ver o que o reconhecimento de voz esta ouvindo ([voz] ouvi: "...").
title Jarvis (console)
cd /d "%~dp0"
"C:\Python310\python.exe" -u assistente.py
echo.
echo (janela encerrada - pressione uma tecla para fechar)
pause >nul
