@echo off
setlocal
set "ROOT=%~dp0.."

echo [INFO] Cleaning build artifacts...

if exist "%ROOT%\build" (
  echo [INFO] Removing build/...
  rmdir /s /q "%ROOT%\build"
)
if exist "%ROOT%\dist" (
  echo [INFO] Removing dist/...
  rmdir /s /q "%ROOT%\dist"
)

echo [INFO] Removing Python cache files...
if exist "%ROOT%\src" (
  for /d /r "%ROOT%\src" %%d in (__pycache__ .pytest_cache .mypy_cache .egg-info) do (
    if exist "%%d" (
      rmdir /s /q "%%d"
      echo [DEL] %%d
    )
  )
  del /s /q "%ROOT%\src\*.pyc" "%ROOT%\src\*.pyo" 2>nul
)

echo [OK] Clean complete.
