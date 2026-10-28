param([string]$File = "")
Start-Process "C:\Program Files (x86)\National Instruments\Circuit Design Suite 14.2\multisim.exe" -ArgumentList ('"' + $File + '"')
Write-Output 'LAUNCHED'
