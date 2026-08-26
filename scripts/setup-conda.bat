@echo off
setlocal
set "ROOT=%~dp0.."

where conda >nul 2>nul
if errorlevel 1 (
    echo Conda was not found. Open Anaconda Prompt and retry.
    exit /b 1
)

call conda env list | findstr /R /C:"^tcar[ ]" >nul
if errorlevel 1 (
    call conda env create -f "%ROOT%\environment.yml"
) else (
    call conda env update -n tcar -f "%ROOT%\environment.yml" --prune
)
if errorlevel 1 exit /b %ERRORLEVEL%

call conda run --no-capture-output -n tcar powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\build.ps1"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo Ready. Run: conda activate tcar
echo Then run: dist\tCarKit.exe
