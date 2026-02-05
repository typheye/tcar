@echo off
setlocal enabledelayedexpansion

set IP=192.168.66.4

:menu
cls
echo.
echo     Raspberry Pi Debug
echo     IP: %IP%
echo     ========================================================
echo.
echo     1. Update ^& Reset    2. SSH Terminal    3. Update Only
echo     4. Reboot            5. Change IP       6. Exit
echo.
echo     ========================================================
echo.

choice /c 123456 /n /m "Select option [1-6]: "

if errorlevel 6 goto exit
if errorlevel 5 goto change_ip
if errorlevel 4 goto reboot_only
if errorlevel 3 goto update_only
if errorlevel 2 goto ssh_terminal
if errorlevel 1 goto update_reboot

:update_reboot
echo.
echo [1/2] Uploading files to Raspberry Pi...
scp -r "./TurboPi" pi@%IP%:/home/pi/
if !errorlevel! neq 0 (
    echo [ERROR] Upload failed!
    pause
    goto menu
)
echo [2/2] Reseting Raspberry Pi...
ssh pi@%IP% "sudo systemctl stop turbopi.service && sudo systemctl start turbopi.service"
echo [SUCCESS] Reset command sent.
pause
goto menu

:update_only
echo.
echo Uploading files to Raspberry Pi...
scp -r "./TurboPi" pi@%IP%:/home/pi/
if !errorlevel! equ 0 (
    echo [SUCCESS] Upload completed.
) else (
    echo [ERROR] Upload failed!
)
pause
goto menu

:reboot_only
echo.
echo Rebooting Raspberry Pi...
ssh pi@%IP% "sudo reboot"
echo [SUCCESS] Reboot command sent.
pause
goto menu

:ssh_terminal
echo.
echo ================================
echo     Opening SSH Terminal
echo ================================
echo Press Ctrl+D or type 'exit' to return
echo ================================
echo.
timeout /t 1 /nobreak >nul
ssh pi@%IP%
pause
goto menu

:change_ip
echo.
echo ================================
echo     Change IP Address
echo ================================
set /p NEW_IP="Enter new IP address (current: %IP%): "
if not "!NEW_IP!"=="" set IP=!NEW_IP!
echo IP address updated to: %IP%
pause
goto menu

:exit
echo.
echo Exiting program...
endlocal