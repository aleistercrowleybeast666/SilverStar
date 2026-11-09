# Run from a committed SilverStar checkout. Each invocation requires fresh output paths.
param(
    [Parameter(Mandatory)][string] $Destination,
    [Parameter(Mandatory)][string] $Evidence,
    [Parameter(Mandatory)][string] $BuildWork,
    [Parameter(Mandatory)][string] $NoticeWitness,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string] $BuildTag
)
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $repository '.venv/Scripts/python.exe'
$noticePath = (Resolve-Path -LiteralPath $NoticeWitness).Path
$distPath = [IO.Path]::GetFullPath($Destination)
$receiptPath = [IO.Path]::GetFullPath($Evidence)
$buildPath = [IO.Path]::GetFullPath($BuildWork)
if ((Test-Path -LiteralPath $distPath) -or (Test-Path -LiteralPath $receiptPath) -or (Test-Path -LiteralPath $buildPath)) {
    throw 'Candidate output or evidence destination already exists.'
}
$null = New-Item -ItemType Directory -Path $distPath, $receiptPath
$cacheRoot = Split-Path $buildPath
$env:TEMP = Join-Path $cacheRoot 'temp'
$env:TMP = $env:TEMP
$env:PYINSTALLER_CONFIG_DIR = Join-Path $cacheRoot 'cache'
$null = New-Item -Force -ItemType Directory -Path $env:TEMP
$env:PYTHONUTF8 = '1'
$env:SILVERSTAR_PACKAGE_EVIDENCE = $receiptPath
Remove-Item Env:SILVERSTAR_REUSE_ANALYSIS -ErrorAction SilentlyContinue
Set-Location -LiteralPath $repository
$sourceHead = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot read source commit' }
$sourceHead | Set-Content -Encoding utf8 (Join-Path $receiptPath 'code-commit.txt')
& $python -B -m PyInstaller --noconfirm --workpath $buildPath --distpath $distPath tools/packaging/SilverStar_shared.spec *> (Join-Path $receiptPath 'pyinstaller.log')
$packExit = $LASTEXITCODE
Set-Content (Join-Path $receiptPath 'pyinstaller.exit') $packExit
if ($packExit -ne 0) { exit $packExit }
$archive = Join-Path $distPath ("SilverStar_0_1_3_" + $BuildTag + "_Windows_x64.zip")
& $python -B tools/packaging/stage_candidate.py (Join-Path $distPath 'SilverStar') $receiptPath $noticePath $archive *> (Join-Path $receiptPath 'stage.log')
$stageExit = $LASTEXITCODE
Set-Content (Join-Path $receiptPath 'stage.exit') $stageExit
exit $stageExit
