@echo off
rem Inicia o Jarvis em SEGUNDO PLANO (sem janela), sob o SUPERVISOR:
rem se o assistente cair por erro, ele reinicia sozinho.
rem Use "Parar Jarvis.bat" para encerrar.
cd /d "%~dp0"
start "" "C:\Python310\pythonw.exe" supervisor.py
