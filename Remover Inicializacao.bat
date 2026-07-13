@echo off
title Remover Jarvis da inicializacao do Windows
powershell -NoProfile -Command "$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Jarvis.lnk'; if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host 'Atalho removido. O Jarvis nao inicia mais com o Windows.' } else { Write-Host 'O Jarvis ja nao estava na inicializacao.' }"
echo.
pause
