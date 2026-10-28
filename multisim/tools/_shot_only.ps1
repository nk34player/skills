param([string]$Hwnd = "0", [string]$Png = "")
# Captures a window WITHOUT bringing it to the foreground (user may be using the PC).
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
$h = [IntPtr][long]$Hwnd
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
