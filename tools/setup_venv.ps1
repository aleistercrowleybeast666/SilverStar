$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
python -m venv (Join-Path $root ".venv")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $root ".venv/Scripts/python.exe") -m pip install -e "${root}[dev]"
exit $LASTEXITCODE
