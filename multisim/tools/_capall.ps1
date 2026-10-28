param([string]$Match = "ALL", [int]$ProcId = -1, [string]$OutDir = "_tmp")
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public delegate bool EnumProc(IntPtr h, IntPtr p);
public class WEnum3 {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
Add-Type -AssemblyName System.Drawing
# pass 1: collect handles only (minimal work inside the callback)
$script:handles = New-Object System.Collections.ArrayList
$cb = [EnumProc]{ param($h, $x)
    [void]$script:handles.Add($h.ToInt64())
    return $true }
[void][WEnum3]::EnumWindows($cb, [IntPtr]::Zero)

foreach ($v in $script:handles) {
    $h = [IntPtr]$v
    $proc = [uint32]0
    [void][WEnum3]::GetWindowThreadProcessId($h, [ref]$proc)
    if ($ProcId -ge 0 -and $proc -ne [uint32]$ProcId) { continue }
    if (-not [WEnum3]::IsWindowVisible($h)) { continue }
    $t = New-Object System.Text.StringBuilder 400
    [void][WEnum3]::GetWindowText($h, $t, 400)
    $txt = $t.ToString()
    $c = New-Object System.Text.StringBuilder 256
    [void][WEnum3]::GetClassName($h, $c, 256)
    if ($Match -ne "ALL" -and $txt -notmatch $Match -and $c.ToString() -notmatch $Match) { continue }
    $r = New-Object WEnum3+RECT
    [void][WEnum3]::GetWindowRect($h, [ref]$r)
    $w = $r.Right - $r.Left; $hh = $r.Bottom - $r.Top
    $info = $h.ToString() + " pid=" + $proc + " class=" + $c.ToString() + " " + $w + "x" + $hh + " :: " + $txt
    if ($w -ge 10 -and $hh -ge 10) {
        $bmp = New-Object System.Drawing.Bitmap $w, $hh
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $hdc = $g.GetHdc()
        [void][WEnum3]::PrintWindow($h, $hdc, 2)
        $g.ReleaseHdc($hdc); $g.Dispose()
        $f = Join-Path $OutDir ("cap_" + $v + ".png")
        $bmp.Save($f, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        Write-Output ($info + "  -> " + $f)
    } else {
        Write-Output ($info)
    }
}
