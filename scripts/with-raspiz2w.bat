@echo off
REM ============================================================================
REM * @file    with-raspiz2w.bat
REM * @author  tCar Development Team
REM * @brief   Raspberry Pi deployment script for Windows
REM *          Provides commands for uploading files, managing services,
REM *          and SSH access to the Raspberry Pi running tCar system.
REM ============================================================================
REM * @attention
REM *
REM * Copyright (c) 2026 tCar Development Team. All rights reserved.
REM *
REM * This software is licensed under terms that can be found in the LICENSE file
REM * in the root directory of this software component.
REM * If no LICENSE file comes with this software, it is provided AS-IS.
REM *
REM ============================================================================

setlocal enabledelayedexpansion

set BASE_DIR=%~dp0..
set TARGET_DIR=/home/pi

REM Discover the current secondary Raspberry Pi address from the car router.
REM The Car device may receive a different DHCP address after every reboot.
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$r=Invoke-RestMethod -TimeoutSec 3 'http://192.168.66.1/test'; ($r.devices | Where-Object name -eq 'Car device' | Select-Object -First 1).ip"`) do set IP=%%i
if not defined IP (
  echo [ERROR] Car device was not found through http://192.168.66.1/test
  exit /b 1
)
echo [INFO] Car device: %IP%

if "%1"=="" goto show_help
if "%1"=="--reset" goto update_restart
if "%1"=="--ssh" goto ssh_terminal
if "%1"=="--reboot" goto reboot_only
if "%1"=="--format" goto format
if "%1"=="--log" goto view_log
if "%1"=="--help" goto show_help
goto show_help

:update_restart
echo [1/2] Uploading files to Raspberry Pi...
for /d /r "%BASE_DIR%\tCar" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
for /r "%BASE_DIR%\tCar" %%f in (*.pyc) do @if exist "%%f" del /q "%%f"
scp -r "%BASE_DIR%\tCar" pi@%IP%:%TARGET_DIR%
if !errorlevel! neq 0 (
  echo [ERROR] Upload failed!
  exit /b 1
)
echo [2/2] Restarting tCar service...
ssh pi@%IP% "sudo systemctl stop tcar.service"
timeout /t 2 /nobreak >nul
ssh pi@%IP% "sudo pkill -f 'python.*init.py' || true"
timeout /t 1 /nobreak >nul
ssh pi@%IP% "sudo systemctl start tcar.service"
echo [SUCCESS] Service restarted.
exit /b 0

:reboot_only
echo Rebooting Raspberry Pi...
ssh pi@%IP% "sudo reboot"
echo [SUCCESS] Reboot command sent.
exit /b 0

:ssh_terminal
echo ================================
echo Opening SSH Terminal
echo ================================
echo Press Ctrl+D or type 'exit' to return
echo ================================
ssh pi@%IP%
exit /b 0

:format
echo Formatting Raspberry Pi directory...
ssh pi@%IP% "sudo rm -rf ~/tCar"
echo [SUCCESS] Directory removed.
exit /b 0

:view_log
echo ================================
echo Viewing tcar.service real-time logs
echo ================================
echo Press Ctrl+C to exit log view
echo ================================
ssh pi@%IP% "sudo journalctl -u tcar.service -f"
exit /b 0

:show_help
echo.
echo Raspberry Pi Debug Script
echo ========================================================
echo.
echo Usage: with-raspiz2w.bat [OPTION]
echo.
echo Options:
echo  --reset  Upload and restart tCar service
echo  --ssh    Open SSH terminal to Raspberry Pi
echo  --log    View tcar.service real-time logs
echo  --reboot Reboot Raspberry Pi
echo  --format Remove ~/tcar directory on Raspberry Pi
echo  --help   Show this help message
echo.
echo Example: with-raspiz2w.bat --reset
echo.
exit /b 0
