@echo off
title Instalar Jarvis na inicializacao do Windows
rem Cria um atalho na pasta Startup do usuario apontando para o supervisor
rem (invisivel, com reinicio automatico). Para desfazer, use o
rem "Remover Inicializacao.bat".
cd /d "%~dp0"
powershell -NoProfile -Command "$startup = [Environment]::GetFolderPath('Startup'); $s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startup 'Jarvis.lnk')); $s.TargetPath = 'C:\Python310\pythonw.exe'; $s.Arguments = '\"%~dp0nucleo\supervisor.py\"'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Jarvis - assistente de voz'; $s.Save(); Write-Host ('Atalho criado em ' + $startup)"
echo.
echo O Jarvis agora inicia junto com o Windows.
pause
