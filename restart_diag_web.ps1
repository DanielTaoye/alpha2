$port = 7000
$conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
$pids = @()
if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
}

if ($pids -and $pids.Count -gt 0) {
    Write-Host ("[diag] Killing processes on port " + $port + ": " + ($pids -join ", "))
    foreach ($procId in $pids) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host ("[diag] No process found on port " + $port)
}

Write-Host "[diag] Starting Flask diagnostic web server..."

# 切换到项目根目录（脚本所在目录）
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# 直接启动（不依赖相对import），并固定端口7000
$env:DIAG_HOST = "127.0.0.1"
$env:DIAG_PORT = "7000"

Start-Process python -ArgumentList "backend\diagnose_web\app.py" -NoNewWindow
Write-Host "[diag] Started. Open: http://localhost:7000"


