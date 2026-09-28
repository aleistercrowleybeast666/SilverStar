$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BatchPath = Join-Path $ProjectRoot "打包.bat"

if (-not (Test-Path -LiteralPath $BatchPath)) {
    throw "Packaging launcher not found: $BatchPath"
}

& $BatchPath
exit $LASTEXITCODE
