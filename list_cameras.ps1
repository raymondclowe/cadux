Get-CimInstance -ClassName Win32_PnPEntity | Where-Object { $_.PNPClass -eq "Camera" -or $_.PNPClass -eq "Image" } | Select-Object Name, DeviceID, Status
