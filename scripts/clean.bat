@echo off
call "%~dp0pc.cmd" clean %*
exit /b %errorlevel%
