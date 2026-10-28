param([string]$Hwnd = "0", [int]$Cmd = 57603)
# Posts a WM_COMMAND (menu command) to a background window. 57603 = ID_FILE_SAVE.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class PC {
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
}
'@
$h = [IntPtr][long]$Hwnd
[void][PC]::PostMessage($h, 0x0111, [IntPtr]$Cmd, [IntPtr]::Zero)
Start-Sleep -Seconds 5
Write-Output 'POSTED'
