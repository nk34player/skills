param([string]$Hwnd = "0", [string]$Png = "")
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
$ws.SendKeys("{ESC}")     # close any menu
Start-Sleep -Milliseconds 400
$ws.SendKeys("%s")        # Simulate menu
Start-Sleep -Milliseconds 1500
# capture while menu is open
Add-Type -AssemblyName System.Drawing
$rect = New-Object FW+RECT
[void][FW]::GetWindowRect($h, [ref]$rect)
$w = $rect.Right - $rect.Left; $hh = $rect.Bottom - $rect.Top
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[void][FW]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ("PNG=" + $Png)
