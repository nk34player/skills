param([string]$Hwnd = "0", [string]$Keys = "")
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class FW {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
$h = [IntPtr][long]$Hwnd
[void][FW]::ShowWindow($h, 9)
[void][FW]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 1200
$ws = New-Object -ComObject WScript.Shell
$ws.SendKeys($Keys)
Start-Sleep -Seconds 3
Write-Output 'SENT'
