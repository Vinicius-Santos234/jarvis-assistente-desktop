@echo off
title Parar Jarvis
echo Procurando o Jarvis em segundo plano...
powershell -NoProfile -Command "$todos = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and ($_.CommandLine -like '*assistente.py*' -or $_.CommandLine -like '*supervisor.py*') }); if ($todos.Count -gt 0) { $sup = @($todos | Where-Object { $_.CommandLine -like '*supervisor.py*' }); $ast = @($todos | Where-Object { $_.CommandLine -like '*assistente.py*' }); foreach ($p in ($sup + $ast)) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }; Write-Host ('Jarvis encerrado (' + $todos.Count + ' processo(s)).') } else { Write-Host 'Jarvis nao estava rodando.' }"
echo.
pause
