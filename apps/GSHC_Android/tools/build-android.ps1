param(
    [string[]]$BuildTasks = @(':app:assembleDebug', ':app:lintDebug', ':app:testDebugUnitTest'),
    [string]$ToolchainRoot = $env:SILVERSTAR_ANDROID_TOOLCHAIN_ROOT,
    [string]$CacheRoot = $env:SILVERSTAR_ANDROID_CACHE_ROOT,
    [string]$BuildRoot = $env:SILVERSTAR_ANDROID_BUILD_ROOT,
    [string]$JavaHome = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
if (-not $ToolchainRoot) { throw 'Provide -ToolchainRoot or SILVERSTAR_ANDROID_TOOLCHAIN_ROOT for the existing external SDK/Gradle. No automatic install.' }
$ToolchainRoot = (Resolve-Path -LiteralPath $ToolchainRoot).Path
if (-not $CacheRoot) { $CacheRoot = Split-Path -Parent $ToolchainRoot }
if (-not $BuildRoot) { $BuildRoot = Join-Path $projectRoot 'build' }
if (-not $JavaHome) { throw 'Provide -JavaHome or JAVA_HOME for an existing JDK17+.' }
$sdkRoot = Join-Path $ToolchainRoot 'android-sdk'
$gradleExe = Join-Path $ToolchainRoot 'gradle-8.13/bin/gradle.bat'
if (-not (Test-Path -LiteralPath (Join-Path $sdkRoot 'platforms/android-36/android.jar'))) { throw 'Android SDK36 is absent. Install only the previously authorized components described in docs/SDK_SETUP.md.' }
if (-not (Test-Path -LiteralPath $gradleExe)) { throw 'Verified Gradle8.13 installation is absent.' }
$env:JAVA_HOME = $JavaHome
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_USER_HOME = Join-Path $CacheRoot 'android-user'
$env:GRADLE_USER_HOME = Join-Path $CacheRoot 'gradle-user'
$env:TEMP = Join-Path $BuildRoot 'temp'
$env:TMP = $env:TEMP
foreach ($directory in @($env:ANDROID_USER_HOME, $env:GRADLE_USER_HOME, $env:TEMP)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
[System.IO.File]::WriteAllText((Join-Path $projectRoot 'local.properties'), ('sdk.dir=' + $sdkRoot.Replace('\','/') + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))
Push-Location -LiteralPath $projectRoot
try {
    & $gradleExe --offline --no-daemon --console=plain --continue "--project-cache-dir=$BuildRoot/gradle-project-cache" '-Pandroid.builder.sdkDownload=false' "-Psilverstar.buildRoot=$BuildRoot" "-Psilverstar.testCacheRoot=$CacheRoot" "-Psilverstar.debugKeyStore=$CacheRoot/android-user/debug.keystore" @BuildTasks
    if ($LASTEXITCODE -ne 0) { throw "Android build failed with exit $LASTEXITCODE" }
} finally { Pop-Location }
