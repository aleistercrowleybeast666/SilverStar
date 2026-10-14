param([string]$JavaHome = '', [string]$BuildRoot = $env:SILVERSTAR_ANDROID_BUILD_ROOT)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $BuildRoot) { $BuildRoot = Join-Path $root 'build' }
$classes = Join-Path $BuildRoot 'core-tests'
New-Item -ItemType Directory -Force -Path $classes | Out-Null
$javac = if ($JavaHome) { Join-Path $JavaHome 'bin/javac.exe' } else { 'javac' }
$java = if ($JavaHome) { Join-Path $JavaHome 'bin/java.exe' } else { 'java' }
$sources = @(Get-ChildItem -LiteralPath (Join-Path $root 'core/src/main/java') -Filter *.java -Recurse | ForEach-Object FullName)
$sources += @(Get-ChildItem -LiteralPath (Join-Path $root 'tests/core') -Filter *.java | ForEach-Object FullName)
& $javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d $classes $sources
if ($LASTEXITCODE -ne 0) { throw 'Core compilation failed' }
& $java -ea -cp $classes CoreTests (Join-Path $classes 'simulation-session.jsonl')
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed' }

& $java -ea -cp $classes TfTests $classes (Join-Path $root 'reference/shared-0.1.3/contracts/log_file_service_v1.json')
if ($LASTEXITCODE -ne 0) { throw 'TF mock tests failed' }
