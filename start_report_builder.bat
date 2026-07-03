@echo off
setlocal
cd /d "%~dp0"

if "%REPORT_BUILDER_PORT%"=="" set REPORT_BUILDER_PORT=8011
if "%PYTHON%"=="" (
  set PYTHON_CMD=python
) else (
  set PYTHON_CMD=%PYTHON%
)

echo Checking portable PASTA paths...
"%PYTHON_CMD%" tools\report_builder_server.py --check
if errorlevel 1 (
  echo.
  echo Portable path check failed. Review the messages above.
  pause
  exit /b 1
)

echo.
echo Starting PASTA report builder
echo Preferred port: %REPORT_BUILDER_PORT% ^(will try 8011-8020 when using the default^)
"%PYTHON_CMD%" tools\report_builder_server.py --port "%REPORT_BUILDER_PORT%"

echo.
pause
