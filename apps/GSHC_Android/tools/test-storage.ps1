param([string]$JavaHome = '', [string]$BuildRoot = $env:SILVERSTAR_ANDROID_BUILD_ROOT)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $BuildRoot) { $BuildRoot = Join-Path $root 'build' }
$classes = Join-Path $BuildRoot 'storage-tests'
New-Item -ItemType Directory -Force -Path $classes | Out-Null
$javac = if ($JavaHome) { Join-Path $JavaHome 'bin/javac.exe' } else { 'javac' }
$java = if ($JavaHome) { Join-Path $JavaHome 'bin/java.exe' } else { 'java' }
$sources = @(Get-ChildItem -LiteralPath (Join-Path $root 'storage/src') -Filter *.java -Recurse | ForEach-Object FullName)
& $javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d $classes $sources
if ($LASTEXITCODE -ne 0) { throw 'Storage compilation failed' }
& $java -ea -cp $classes cn.silverstar.gshc.storage.StorageTests $classes
if ($LASTEXITCODE -ne 0) { throw 'Storage tests failed' }
