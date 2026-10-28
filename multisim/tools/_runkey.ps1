param([string]$Hwnd = "0", [string]$Key = "{F5}", [string]$Png = "")
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
$h = [IntPtr][long]$Hwnd
[void][W]::ShowWindow($h, 9)
[void][W]::SetForegroundWindow($h)
Start-Sleep -Seconds 2
$ws = New-Object -ComObject WScript.Shell
$ws.SendKeys($Key)
Start-Sleep -Seconds 12
if ($Png) {
  Add-Type -AssemblyName System.Drawing
  $rect = New-Object W+RECT
  [void][W]::GetWindowRect($h, [ref]$rect)
  $w = $rect.Right - $rect.Left; $hh = $rect.Bottom - $rect.Top
  $bmp = New-Object System.Drawing.Bitmap $w, $hh
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  [void][W]::PrintWindow($h, $hdc, 2)
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  Write-Output ("PNG=" + $Png)
}
Write-Output 'DONE'
