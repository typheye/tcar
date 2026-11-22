@echo off
setlocal
where conda >nul 2>nul
if not errorlevel 1 goto conda
where py >nul 2>nul
if not errorlevel 1 goto python_launcher
python "%~dp0manage.py" %*
exit /b %errorlevel%

:conda
call conda run --no-capture-output -n base python "%~dp0manage.py" %*
exit /b %errorlevel%

:python_launcher
py -3 "%~dp0manage.py" %*
exit /b %errorlevel%
