@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_PATH=%~dp0.venv\Scripts\python.exe"
set "SPEC_PATH=%~dp0SilverStar_FLP.spec"
if not defined SILVERSTAR_FLP_DIST_PATH set "SILVERSTAR_FLP_DIST_PATH=%~dp0dist"
if not defined SILVERSTAR_FLP_BUILD_PATH set "SILVERSTAR_FLP_BUILD_PATH=%~dp0build"
if not exist "%PYTHON_PATH%" (
    echo [ERROR] Missing .venv\Scripts\python.exe.
    echo Install the packaging dependencies described in README.md first.
    exit /b 1
)
if not exist "%SPEC_PATH%" (
    echo [ERROR] Missing SilverStar_FLP.spec.
    exit /b 1
)

"%PYTHON_PATH%" -m PyInstaller --noconfirm --clean --distpath "%SILVERSTAR_FLP_DIST_PATH%" --workpath "%SILVERSTAR_FLP_BUILD_PATH%" "%SPEC_PATH%"

set "BUILD_EXIT_CODE=%ERRORLEVEL%"
if not "%BUILD_EXIT_CODE%"=="0" exit /b %BUILD_EXIT_CODE%

echo Package created at: %SILVERSTAR_FLP_DIST_PATH%\SilverStar_FLP
exit /b 0
