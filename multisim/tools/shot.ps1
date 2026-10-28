# Open a Multisim file (copied into the workspace) and capture ONLY the Multisim window.
# usage: shot.ps1 <file.ms14> [out.png]
param(
    [Parameter(Mandatory = $true)][string]$File,
    [string]$Png = ""
)

$ErrorActionPreference = "Stop"
$exe = 'C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.2\multisim.exe'
$work = Split-Path -Parent $PSScriptRoot          # project root = workspace
$tmp = Join-Path $work "_tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$name = [System.IO.Path]::GetFileName($File)
$local = Join-Path $tmp $name
if (-not ([System.IO.Path]::GetFullPath($File) -eq [System.IO.Path]::GetFullPath($local))) {
    Copy-Item -LiteralPath $File -Destination $local -Force
}
if (-not $Png) { $Png = Join-Path $tmp ([System.IO.Path]::GetFileNameWithoutExtension($name) + ".png") }

Get-Process multisim -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process -FilePath $exe -ArgumentList ('"' + $local + '"')

# find the real document window by title (Multisim creates a splash window first)
$sig0 = @'
using System;
using System.Runtime.InteropServices;
public class WEnum {
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
'@
if (-not ("WEnum" -as [type])) { Add-Type -TypeDefinition $sig0 }
$stem = [System.IO.Path]::GetFileNameWithoutExtension($name)
$p = $null
$hwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    $script:hwnd = [IntPtr]::Zero
    $cb = [WEnum+EnumProc]{
        param($h, $x)
        $sb = New-Object System.Text.StringBuilder 400
        [void][WEnum]::GetWindowText($h, $sb, 400)
        if ($sb.ToString() -like ("*" + $script:stem + "*Multisim*")) { $script:hwnd = $h; return $false }
        return $true
    }
    [void][WEnum]::EnumWindows($cb, [IntPtr]::Zero)
    if ($script:hwnd -ne [IntPtr]::Zero) { break }
}
if ($script:hwnd -eq [IntPtr]::Zero) { Write-Output "NO_WINDOW"; exit 1 }
$h = $script:hwnd
$p = Get-Process multisim -ErrorAction SilentlyContinue | Select-Object -First 1

Start-Sleep -Seconds 6

$sig = @'
using System;
using System.Runtime.InteropServices;
public class W32 {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
'@
if (-not ("W32" -as [type])) { Add-Type -TypeDefinition $sig }
Add-Type -AssemblyName System.Drawing

[void][W32]::ShowWindow($h, 9)          # SW_RESTORE
[void][W32]::SetForegroundWindow($h)
Start-Sleep -Seconds 2

$r = New-Object W32+RECT
[void][W32]::GetWindowRect($h, [ref]$r)
$w = $r.Right - $r.Left
$hh = $r.Bottom - $r.Top
if ($w -le 0 -or $hh -le 0) { Write-Output "BAD_RECT"; exit 1 }

$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [W32]::PrintWindow($h, $hdc, 2)   # PW_RENDERFULLCONTENT
$g.ReleaseHdc($hdc)
$g.Dispose()
$bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()

Write-Output ("TITLE=" + $stem + " hwnd=" + $h)
Write-Output ("PNG=" + $Png + " " + $w + "x" + $hh + " printwindow=" + $ok)
