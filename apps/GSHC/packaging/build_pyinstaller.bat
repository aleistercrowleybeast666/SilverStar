@echo off
setlocal
set "APP_ROOT=%~dp0.."
set "SUITE_ROOT=%~dp0..\..\.."
set "SUITE_PYTHON=%SUITE_ROOT%\.venv\Scripts\python.exe"
if not exist "%SUITE_PYTHON%" (
  echo Create the monorepo environment with tools\setup_venv.ps1 first.
  exit /b 1
)
cd /d "%APP_ROOT%"
"%SUITE_PYTHON%" -m PyInstaller --noconfirm --clean --workpath "%SUITE_ROOT%\.work\package\GSHC\work" --distpath "%SUITE_ROOT%\.work\package\GSHC\dist" SilverStar_GSHC.spec
exit /b %ERRORLEVEL%
