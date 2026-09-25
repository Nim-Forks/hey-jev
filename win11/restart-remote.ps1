"""Kill any running hey-jev remote server and start a fresh one.
Usage: powershell -File restart-remote.ps1   (or: .\restart-remote.ps1)
"""
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $dir ".venv\Scripts\python.exe"
$runLog = Join-Path $env:TEMP "heyjev-remote.log"
$errLog = Join-Path $env:TEMP "heyjev-remote.err.log"
$pidFile = Join-Path $env:TEMP "heyjev-remote.pid"

# 1. kill every existing remote process
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*siri.py*--remote*" } |
    ForEach-Object {
        Write-Host "killing $($_.ProcessId)"
        try { Stop-Process -Id $_.ProcessId -Force } catch {}
    }
Start-Sleep -Seconds 1

# 2. start fresh
Remove-Item $runLog, $errLog -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $python `
    -ArgumentList "-u", "-X", "utf8", "siri.py", "--remote" `
    -WorkingDirectory $dir `
    -RedirectStandardOutput $runLog -RedirectStandardError $errLog `
    -PassThru -WindowStyle Hidden
$p.Id | Set-Content $pidFile

# 3. wait for /health
$ok = $false
foreach ($i in 1..10) {
    Start-Sleep -Milliseconds 800
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" `
            -UseBasicParsing -TimeoutSec 2
        if ($health.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
}

if ($ok) {
    Write-Host "[ok] remote server running, pid $((Get-Content $pidFile))"
    Get-Content $runLog | Select-Object -First 6
} else {
    Write-Host "[FAIL] server did not come up; stderr:"
    Get-Content $errLog -ErrorAction SilentlyContinue | Select-Object -First 20
    exit 1
}
