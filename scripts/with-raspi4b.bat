@echo off
REM ============================================================================
REM * @file    with-raspi4b.bat
REM * @author  TurboPi Development Team
REM * @brief   Raspberry Pi deployment script for Windows
REM *          Provides commands for uploading files, managing services,
REM *          and SSH access to the Raspberry Pi running TurboPi system.
REM ============================================================================
REM * @attention
REM *
REM * Copyright (c) 2026 TurboPi Development Team. All rights reserved.
REM *
REM * This software is licensed under terms that can be found in the LICENSE file
REM * in the root directory of this software component.
REM * If no LICENSE file comes with this software, it is provided AS-IS.
REM *
REM ============================================================================

setlocal enabledelayedexpansion

set IP=192.168.66.5
@REM set IP=192.168.66.3
set BASE_DIR=%~dp0..
set TARGET_DIR=/home/pi

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
scp -r "%BASE_DIR%\TurboPi" pi@%IP%:%TARGET_DIR%
if !errorlevel! neq 0 (
  echo [ERROR] Upload failed!
  exit /b 1
)
echo [2/2] Restarting TurboPi service...
ssh pi@%IP% "sudo systemctl stop turbopi.service"
timeout /t 2 /nobreak >nul
ssh pi@%IP% "sudo pkill -f 'python.*init.py' || true"
timeout /t 1 /nobreak >nul
ssh pi@%IP% "sudo systemctl start turbopi.service"
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
ssh pi@%IP% "sudo rm -rf ~/TurboPi"
echo [SUCCESS] Directory removed.
exit /b 0

:view_log
echo ================================
echo Viewing turbopi.service real-time logs
echo ================================
echo Press Ctrl+C to exit log view
echo ================================
ssh pi@%IP% "sudo journalctl -u turbopi.service -f"
exit /b 0

:show_help
echo.
echo Raspberry Pi Debug Script
echo ========================================================
echo.
echo Usage: with-raspi4b.bat [OPTION]
echo.
echo Options:
echo  --reset  Upload and restart TurboPi service
echo  --ssh    Open SSH terminal to Raspberry Pi
echo  --log    View turbopi.service real-time logs
echo  --reboot Reboot Raspberry Pi
echo  --format Remove ~/turbopi directory on Raspberry Pi
echo  --help   Show this help message
echo.
echo Example: with-raspi4b.bat --reset
echo.
exit /b 0