param([string]$Hwnd = "0")
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
'@
$h = [IntPtr][long]$Hwnd
[void][W]::ShowWindow($h, 9)
[void][W]::SetForegroundWindow($h)
Start-Sleep -Seconds 2
$ws = New-Object -ComObject WScript.Shell
$ws.SendKeys("^s")
Start-Sleep -Seconds 5
Write-Output 'PRESSED'
