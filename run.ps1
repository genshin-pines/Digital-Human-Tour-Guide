$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot

$bundledPython = 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$python = if (Test-Path $bundledPython) { $bundledPython } else { 'python' }

Write-Host ''
Write-Host '=========================================='
Write-Host ' 灵山 AI 数字人导游 - 阶段 4 启动器'
Write-Host '=========================================='
Write-Host ''
Write-Host '游客端:   http://127.0.0.1:8000/visitor'
Write-Host '管理后台: http://127.0.0.1:8000/admin'
Write-Host '健康检查: http://127.0.0.1:8000/api/health'
Write-Host '集成状态: http://127.0.0.1:8000/api/integrations'
Write-Host ''
Write-Host '如果端口 8000 被占用，请先关闭旧的运行窗口。'
Write-Host '按 Ctrl+C 可停止服务。'
Write-Host ''

Start-Job -ScriptBlock {
  Start-Sleep -Seconds 2
  $edge = Get-Command msedge -ErrorAction SilentlyContinue
  if ($edge) {
    Start-Process msedge -ArgumentList '--new-window', 'http://127.0.0.1:8000/visitor'
    Start-Process msedge -ArgumentList '--new-window', 'http://127.0.0.1:8000/admin'
  } else {
    Start-Process 'http://127.0.0.1:8000/visitor'
    Start-Process 'http://127.0.0.1:8000/admin'
  }
} | Out-Null
& $python "$PSScriptRoot\app.py" --host 127.0.0.1 --port 8000
