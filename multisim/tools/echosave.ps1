param([string]$Out = "")
$ErrorActionPreference = "Stop"
$work = Split-Path -Parent $PSScriptRoot
$tmp = Join-Path $work "_tmp"
if (-not $Out) { $Out = Join-Path $tmp "echo.ms14" }
$p = Get-Process multisim -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { Write-Output "NO_WINDOW"; exit 1 }
$ws = New-Object -ComObject WScript.Shell
[void]$ws.AppActivate($p.Id)
Start-Sleep -Milliseconds 800
# File -> Save As...  then type the target path
$ws.SendKeys("%f")
Start-Sleep -Milliseconds 600
$ws.SendKeys("a")
Start-Sleep -Seconds 2
$ws.SendKeys($Out)
Start-Sleep -Milliseconds 400
$ws.SendKeys("{ENTER}")
Start-Sleep -Seconds 3
if (Test-Path $Out) {
    Write-Output ("SAVED=" + $Out + " " + (Get-Item $Out).Length)
} else {
    Write-Output "SAVE_FAILED"
}
