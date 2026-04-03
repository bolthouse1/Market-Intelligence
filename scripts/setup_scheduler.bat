@echo off
echo Registering daily scan at 6:00 AM...
schtasks /create /tn "120VC_IntelScan" /tr "C:\Market_Intelligence\scripts\run_scan.bat" /sc daily /st 06:00 /f
echo.
echo Task scheduled. Verify with:
echo   schtasks /query /tn 120VC_IntelScan
