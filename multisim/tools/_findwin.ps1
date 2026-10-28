param([string]$Match = "Multisim")
Add-Type @'
using System;
using System.Runtime.InteropServices;
public delegate bool EnumProc(IntPtr h, IntPtr p);
public class WEnum {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
}
'@
$out = New-Object System.Collections.ArrayList
$cb = [EnumProc]{ param($h,$x)
  $sb = New-Object System.Text.StringBuilder 400
  [void][WEnum]::GetWindowText($h,$sb,400)
  $t = $sb.ToString()
  if ($t -match $Match) { [void]$script:out.Add($h.ToString() + ' :: ' + $t) }
  return $true }
[void][WEnum]::EnumWindows($cb,[IntPtr]::Zero)
$script:out
