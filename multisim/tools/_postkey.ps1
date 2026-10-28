param([string]$Hwnd = "0", [string]$Keys = "")
# Sends keys to a window WITHOUT activating it (PostMessage, background-safe).
# $Keys is a sequence of tokens separated by spaces:
#   F5, ^s (ctrl+s), text in {t:...} form not supported - plain chars sent as WM_CHAR-less WM_KEYDOWN
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class PK {
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
  public const uint WM_KEYDOWN = 0x0100;
  public const uint WM_KEYUP   = 0x0101;
}
'@
$h = [IntPtr][long]$Hwnd
function Send-VK([IntPtr]$h, [int]$vk) {
    [void][PK]::PostMessage($h, [PK]::WM_KEYDOWN, [IntPtr]$vk, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [void][PK]::PostMessage($h, [PK]::WM_KEYUP, [IntPtr]$vk, [IntPtr](0xC0000000 -bor 1))
    Start-Sleep -Milliseconds 80
}
$VK = @{ F5 = 0x74; S = 0x53; CONTROL = 0x11 }
foreach ($k in ($Keys -split '\s+')) {
    if ($k -eq '') { continue }
    if ($k -match '^\^(.+)$') {
        Send-VK $h $VK['CONTROL']
        Send-VK $h $VK[$Matches[1].ToUpper()]
        Send-VK $h $VK['CONTROL']
    } else {
        Send-VK $h $VK[$k.ToUpper()]
    }
}
Write-Output 'POSTED'
