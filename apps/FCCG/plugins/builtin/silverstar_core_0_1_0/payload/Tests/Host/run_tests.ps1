param(
    [string]$HostCompiler = 'gcc'
)

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$outputDir = Join-Path $repoRoot 'build\FCCG\Host\Tests'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$script:hostExecutableCount = 0
$script:hostCheckCount = 0
$script:hostFailureCount = 0
$script:compilePassCaseCount = 0
$script:expectedCompileFailureCount = 0
$script:collectHostJobs = $true
$script:hostJobs = [System.Collections.Generic.List[object]]::new()
$script:progressCompleted = @{}
$script:progressTotals = @{}
$script:hostCompilerPath = ''
$script:hostCompilerVersion = ''
$script:hostCompilerTarget = ''
$silverstarAssertSource = "$repoRoot\Common\Src\silverstar_assert.c"
$multiInstanceFixtureInclude = `
    "-I$repoRoot\Tests\Host\Fixtures\MultiInstance\Inc"
$multiInstanceResourceFixture = `
    "$repoRoot\Tests\Host\Fixtures\MultiInstance\multi_instance_resources.c"
$detailLogPath = Join-Path $outputDir 'host-tests-detail.log'
if (Test-Path -LiteralPath $detailLogPath) {
    Remove-Item -LiteralPath $detailLogPath -Force
}

# FCCG generated configuration is force-included so Host Tests use the same selected-component feature gates as Make.
$includeArgs = @(
    '-include',
    "$repoRoot\Generated\Inc\project_flight_config.h",
    "-I$repoRoot\Tests\Host",
    "-I$repoRoot\APP\Inc",
    "-I$repoRoot\Algorithm\Common\Inc",
    "-I$repoRoot\Algorithm\Calibration\Inc",
    "-I$repoRoot\Algorithm\Alignment\Common\Inc",
    "-I$repoRoot\Algorithm\Alignment\GravityKnownYaw\Inc",
    "-I$repoRoot\Algorithm\Alignment\GravityMagTriad\Inc",
    "-I$repoRoot\Algorithm\INS\Coning2Sculling2\Inc",
    "-I$repoRoot\Algorithm\Estimator\KF6\Inc",
    "-I$repoRoot\Common\Inc",
    "-I$repoRoot\Modules\Inc",
    "-I$repoRoot\Protocol\Inc",
    "-I$repoRoot\Protocol\SSLOG\Inc",
    "-I$repoRoot\Interfaces\Inc",
    "-I$repoRoot\System\Inc",
    "-I$repoRoot\System\Alignment\Inc",
    "-I$repoRoot\System\Calibration\Inc",
    "-I$repoRoot\System\Indicator\Inc",
    "-I$repoRoot\System\Inertial\Inc",
    "-I$repoRoot\System\User",
    "-I$repoRoot\Targets\SilverStar_F407\Inc",
    "-I$repoRoot\Board\SilverStar_0_5\Services\Inc",
    "-I$repoRoot\Generated\Inc",
    "-I$repoRoot\FlightLogic\Deployment\MultiTrigger\Inc",
    "-I$repoRoot\FlightLogic\Landing\BarometerImuWindow\Inc",
    "-I$repoRoot\Platform\Inc",
    "-I$repoRoot\Platform\STM32F4\Inc",
    "-I$repoRoot\Devices\IMU\JY901B\Inc",
    "-I$repoRoot\Devices\IMU\JY901B\Adapter\Inc",
    "-I$repoRoot\Devices\GNSS\NEO_M9N\Inc",
    "-I$repoRoot\Devices\GNSS\NEO_M9N\Adapter\Inc",
    "-I$repoRoot\Devices\Telemetry\SX1281\Inc",
    "-I$repoRoot\Devices\Telemetry\SX1281\Adapter\Inc",
    "-I$repoRoot\Middlewares\Third_Party\SX1280lib"
)

function Invoke-HostCompiler {
    param(
        [Parameter(Mandatory = $true)][string[]]$CompilerArgs
    )

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $compilerOutput = @(& $script:hostCompilerPath @CompilerArgs 2>&1)
        $compileExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($null -eq $compileExit) {
        $compileExit = -1
    }
    return [pscustomobject]@{
        Output = $compilerOutput
        ExitCode = $compileExit
    }
}

function Write-HostCompileDiagnostic {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$CompilerArgs,
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [object[]]$CompilerOutput = @()
    )

    Write-Output "Host test compile diagnostic: name=$Name"
    Write-Output "Host compiler path: $($script:hostCompilerPath)"
    Write-Output "Host compiler version: $($script:hostCompilerVersion)"
    Write-Output "Host compiler target: $($script:hostCompilerTarget)"
    Write-Output "Host compiler return code: $ExitCode"
    Write-Output 'Host compiler arguments:'
    foreach ($argument in $CompilerArgs) {
        Write-Output "  $argument"
    }
    Write-Output 'GCC stdout/stderr:'
    if ($CompilerOutput.Count -eq 0) {
        Write-Output '  <empty>'
    }
    else {
        $CompilerOutput | Write-Output
    }
}

function Initialize-HostCompiler {
    if ([string]::IsNullOrWhiteSpace($HostCompiler)) {
        throw 'Host compiler path must not be empty.'
    }
    try {
        $compilerCommand = Get-Command -Name $HostCompiler `
            -CommandType Application -ErrorAction Stop | Select-Object -First 1
    }
    catch {
        throw "Host compiler is not executable: $HostCompiler. $($_.Exception.Message)"
    }
    $script:hostCompilerPath = $compilerCommand.Path
    $hostCompilerDirectory = Split-Path -Parent $script:hostCompilerPath
    Write-Output "Host compiler runtime directory: $hostCompilerDirectory"
    $env:PATH = $hostCompilerDirectory + [System.IO.Path]::PathSeparator + `
        $env:PATH
    foreach ($variableName in @(
        'GCC_EXEC_PREFIX',
        'COMPILER_PATH',
        'CPATH',
        'C_INCLUDE_PATH',
        'CPLUS_INCLUDE_PATH',
        'OBJC_INCLUDE_PATH',
        'LIBRARY_PATH',
        'DEPENDENCIES_OUTPUT',
        'SUNPRO_DEPENDENCIES'
    )) {
        $environmentPath = "Env:$variableName"
        if (Test-Path -LiteralPath $environmentPath) {
            Remove-Item -LiteralPath $environmentPath -Force
        }
    }

    Write-Output "Host compiler command: `"$($script:hostCompilerPath)`" --version"
    $versionResult = Invoke-HostCompiler -CompilerArgs @('--version')
    $versionResult.Output | Write-Output
    if ($versionResult.ExitCode -ne 0) {
        throw "Host compiler --version failed: $($script:hostCompilerPath)"
    }
    $script:hostCompilerVersion = [string]$versionResult.Output[0]

    Write-Output "Host compiler command: `"$($script:hostCompilerPath)`" -dumpmachine"
    $targetResult = Invoke-HostCompiler -CompilerArgs @('-dumpmachine')
    $targetResult.Output | Write-Output
    if (($targetResult.ExitCode -ne 0) -or ($targetResult.Output.Count -eq 0)) {
        throw "Host compiler -dumpmachine failed: $($script:hostCompilerPath)"
    }
    $script:hostCompilerTarget = ([string]$targetResult.Output[0]).Trim()
    if ($script:hostCompilerTarget -notmatch '(?i)(mingw|windows|cygwin|msys)') {
        throw ("Host compiler target is not runnable on this Windows host: " +
            "compiler=$($script:hostCompilerPath) " +
            "target=$($script:hostCompilerTarget)")
    }
}

function Invoke-RecordCatalogValidator {
    $validator = Join-Path $repoRoot `
        'Tools\validate_sslog_record_catalog.py'
    try {
        $pythonCommand = Get-Command -Name 'python' `
            -CommandType Application -ErrorAction Stop | Select-Object -First 1
    }
    catch {
        throw ("Python is required for the offline SSLOG Record Catalog " +
            "Host validator. $($_.Exception.Message)")
    }
    $validatorOutput = @(& $pythonCommand.Path $validator 2>&1)
    $validatorExit = $LASTEXITCODE
    $validatorOutput | Write-Output
    if ($validatorExit -ne 0) {
        throw "SSLOG Record Catalog Host validation failed."
    }
    $script:hostCheckCount++
}

function Write-FccgProgressBegin {
    param(
        [Parameter(Mandatory = $true)][string]$Task,
        [Parameter(Mandatory = $true)][string]$Subject
    )

    $current = [int]$script:progressCompleted[$Task] + 1
    $total = [int]$script:progressTotals[$Task]
    Write-Output "FCCG_PROGRESS|$Task|BEGIN|$current|$total|$Subject"
}

function Write-FccgProgressDone {
    param(
        [Parameter(Mandatory = $true)][string]$Task,
        [Parameter(Mandatory = $true)][string]$Subject
    )

    $script:progressCompleted[$Task] = `
        [int]$script:progressCompleted[$Task] + 1
    $current = [int]$script:progressCompleted[$Task]
    $total = [int]$script:progressTotals[$Task]
    Write-Output "FCCG_PROGRESS|$Task|DONE|$current|$total|$Subject"
}

function Write-HostTestDetail {
    param([Parameter(Mandatory = $true)][string]$Text)

    [System.IO.File]::AppendAllText(
        $detailLogPath,
        $Text + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Output "FCCG_DETAIL|$Text"
}

function Invoke-HostTest {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Sources,
        [string[]]$ExtraCompilerArgs = @()
    )

    if ($script:collectHostJobs) {
        $script:hostJobs.Add([pscustomobject]@{
            Kind = 'HOST_TEST'
            Name = $Name
            Sources = @($Sources)
            ExtraCompilerArgs = @($ExtraCompilerArgs)
        })
        return
    }

    Write-FccgProgressBegin -Task 'HOST_TEST' -Subject $Name

    # A generated FCCG project contains only its selected component payloads.
    $fccgMissingSources = @($Sources | Where-Object {
        -not (Test-Path -LiteralPath $_)
    })
    if ($fccgMissingSources.Count -ne 0) {
        Write-Output ("Skipped host test {0}: unselected component sources {1}" -f $Name, ($fccgMissingSources -join ', '))
        return
    }

    $executable = Join-Path $outputDir ($Name + '.exe')
    $compilerArgs = @(
        '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-O2'
    ) + $ExtraCompilerArgs + $includeArgs + $Sources + @(
        $silverstarAssertSource, '-lm', '-o', $executable)

    $compileResult = Invoke-HostCompiler -CompilerArgs $compilerArgs
    if ($compileResult.ExitCode -ne 0) {
        Write-HostCompileDiagnostic -Name $Name -CompilerArgs $compilerArgs `
            -ExitCode $compileResult.ExitCode -CompilerOutput $compileResult.Output
        throw "Host test compile failed: $Name"
    }
    $compileResult.Output | Write-Output
    $testOutput = @(& $executable)
    $testExit = $LASTEXITCODE
    $testOutput | Write-Output
    foreach ($line in $testOutput) {
        if ($line -match ':\s+(\d+) checks,\s+(\d+) failures$') {
            $script:hostCheckCount += [int]$Matches[1]
            $script:hostFailureCount += [int]$Matches[2]
        }
    }
    if ($testExit -ne 0) {
        throw "Host test failed: $Name"
    }
    $script:hostExecutableCount++
    Write-FccgProgressDone -Task 'HOST_TEST' -Subject $Name
}

function Invoke-ExpectedCompileFailure {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Source,
        [string[]]$ExtraCompilerArgs = @()
    )

    if ($script:collectHostJobs) {
        $script:hostJobs.Add([pscustomobject]@{
            Kind = 'HOST_EXPECTED_FAILURE'
            Name = $Name
            Source = $Source
            ExtraCompilerArgs = @($ExtraCompilerArgs)
        })
        return
    }

    Write-FccgProgressBegin -Task 'HOST_EXPECTED_FAILURE' -Subject $Name

    $compilerArgs = @(
        '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-fsyntax-only'
    ) + $ExtraCompilerArgs + $includeArgs + @($Source)
    $compileResult = Invoke-HostCompiler -CompilerArgs $compilerArgs
    if ($compileResult.ExitCode -eq 0) {
        Write-HostCompileDiagnostic -Name $Name -CompilerArgs $compilerArgs `
            -ExitCode $compileResult.ExitCode -CompilerOutput $compileResult.Output
        throw "Expected host compile failure did not occur: $Name"
    }
    $diagnosticLine = $compileResult.Output | Where-Object {
        ([string]$_) -match '(?i)(static assertion failed|#error)'
    } | Select-Object -First 1
    if ($null -eq $diagnosticLine) {
        Write-HostCompileDiagnostic -Name $Name -CompilerArgs $compilerArgs `
            -ExitCode $compileResult.ExitCode -CompilerOutput $compileResult.Output
        throw "Expected host compile failure did not match a configuration gate: $Name"
    }
    $script:expectedCompileFailureCount++
    Write-Output "FCCG_EXPECTED_REJECTION|$Name"
    Write-HostTestDetail -Text ("Expected compile rejection: {0}" -f $Name)
    Write-HostTestDetail -Text ("Compiler: {0}" -f $script:hostCompilerPath)
    Write-HostTestDetail -Text ("Target: {0}" -f $script:hostCompilerTarget)
    foreach ($diagnostic in $compileResult.Output) {
        Write-HostTestDetail -Text ([string]$diagnostic)
    }
    Write-FccgProgressDone -Task 'HOST_EXPECTED_FAILURE' -Subject $Name
}

function Invoke-ExpectedCompileSuccess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Source,
        [string[]]$ExtraCompilerArgs = @()
    )

    if ($script:collectHostJobs) {
        $script:hostJobs.Add([pscustomobject]@{
            Kind = 'HOST_COMPILE_PASS'
            Name = $Name
            Source = $Source
            ExtraCompilerArgs = @($ExtraCompilerArgs)
        })
        return
    }

    Write-FccgProgressBegin -Task 'HOST_COMPILE_PASS' -Subject $Name

    $compilerArgs = @(
        '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-fsyntax-only'
    ) + $ExtraCompilerArgs + $includeArgs + @($Source)
    $compileResult = Invoke-HostCompiler -CompilerArgs $compilerArgs
    if ($compileResult.ExitCode -ne 0) {
        Write-HostCompileDiagnostic -Name $Name -CompilerArgs $compilerArgs `
            -ExitCode $compileResult.ExitCode -CompilerOutput $compileResult.Output
        throw "Expected host compile success failed: $Name"
    }
    $compileResult.Output | Write-Output
    $script:compilePassCaseCount++
    Write-Output "Expected host compile success passed: $Name"
    Write-FccgProgressDone -Task 'HOST_COMPILE_PASS' -Subject $Name
}

Initialize-HostCompiler

$projectDocument = Get-Content -Raw -Encoding UTF8 -LiteralPath `
    (Join-Path $repoRoot 'SilverStar.ssproject') | ConvertFrom-Json
$hostFlightConfiguration = Get-Content -Raw -Encoding UTF8 -LiteralPath `
    (Join-Path $repoRoot 'Generated\Inc\project_flight_config.h')
$hostLoggingDeclarations = [regex]::Matches($hostFlightConfiguration,
    '(?m)^[ \t]*#[ \t]*define[ \t]+SILVERSTAR_PROTOCOL_LOGGING_ENABLED\b[^\r\n]*$')
$hostLoggingLiteral = [regex]::Match($hostFlightConfiguration,
    '(?m)^[ \t]*#[ \t]*define[ \t]+SILVERSTAR_PROTOCOL_LOGGING_ENABLED[ \t]+(?<value>[01])U[ \t]*$')
if (($hostLoggingDeclarations.Count -ne 1) -or (-not $hostLoggingLiteral.Success)) {
    throw 'Host logging selection must be exactly one generated literal 0U or 1U.'
}
$hostLoggingEnabled = $hostLoggingLiteral.Groups['value'].Value -eq '1'
if ((@($projectDocument.protocols.PSObject.Properties.Name) -notcontains 'logging') -or
    ($hostLoggingEnabled -ne ($null -ne $projectDocument.protocols.logging))) {
    throw 'Host logging selection differs from saved project protocol selection.'
}
if ($hostLoggingEnabled) {
    Invoke-RecordCatalogValidator
    $goldenDirectory = Join-Path $repoRoot 'Logs\Golden'
    New-Item -ItemType Directory -Force -Path $goldenDirectory | Out-Null
    $goldenFilename = ([string]$projectDocument.project.name) + '_golden.sslog'
    $env:SILVERSTAR_GOLDEN_OUTPUT = Join-Path $goldenDirectory $goldenFilename
}
else {
    $hostSourceGraph = Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'Generated\project_sources.mk')
    if (($hostSourceGraph -match 'Protocol/SSLOG/|Generated/Src/project_log_(?:config|decoder_profile)\.c') -or
        (Test-Path -LiteralPath (Join-Path $repoRoot 'Protocol\SSLOG')) -or
        (Test-Path -LiteralPath (Join-Path $repoRoot 'Generated\Src\project_log_decoder_profile.c')) -or
        (@(Get-ChildItem -LiteralPath $repoRoot -File -Filter '*.ssdecoder').Count -ne 0)) {
        throw 'Logging-disabled Host project retains SSLOG source, payload, or decoder package.'
    }
    Write-Output 'Host configuration: logging disabled; no codec, golden log, or storage-log acceptance is claimed.'
}

$hostPlatformMock = "$repoRoot\Tests\Host\host_platform_mock.c"
$sslogSources = @(
    "$repoRoot\Protocol\SSLOG\Src\sslog_protocol.c",
    "$repoRoot\Protocol\SSLOG\Src\sslog_records.c"
)

Invoke-HostTest -Name 'interfaces' -Sources @(
    "$repoRoot\Tests\Host\test_interfaces.c"
)

Invoke-HostTest -Name 'common_format' -Sources @(
    "$repoRoot\Tests\Host\test_common_format.c",
    "$repoRoot\Common\Src\common_format.c"
)

Invoke-HostTest -Name 'system_time' -Sources @(
    "$repoRoot\Tests\Host\test_system_time.c",
    "$repoRoot\System\Src\system_time.c"
)

$profileSources = @(
    "$repoRoot\Tests\Host\test_profiles.c",
    $hostPlatformMock,
    "$repoRoot\System\Src\system_navigation_profile.c",
    "$repoRoot\System\Src\system_estimator_profile.c",
    "$repoRoot\System\Src\system_log_policy.c",
    "$repoRoot\System\Src\system_profile.c",
    "$repoRoot\Protocol\SSLOG\Src\sslog_records.c",
    "$repoRoot\Generated\Src\project_log_config.c"
)
Invoke-HostTest -Name 'profiles_kf6' -Sources $profileSources

$estimatorNoiseOverrideArgs = @(
    '-DTEST_EXPECT_ESTIMATOR_NOISE_OVERRIDES=1',
    '-DSYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_OVERRIDE=0.8f',
    '-DSYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_OVERRIDE=0.9f',
    '-DSYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_OVERRIDE=1.1f',
    '-DSYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_OVERRIDE=0.7f',
    '-DSYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_OVERRIDE=1.2f',
    '-DSYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_OVERRIDE=0.08f',
    '-DSYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_OVERRIDE=3.5f'
)
Invoke-HostTest -Name 'profiles_estimator_noise_overrides' `
    -ExtraCompilerArgs $estimatorNoiseOverrideArgs -Sources $profileSources

$pureInsConfigDir = Join-Path $outputDir 'config_pure_ins'
New-Item -ItemType Directory -Force -Path $pureInsConfigDir | Out-Null
$pureInsConfigPath = Join-Path $pureInsConfigDir 'system_user_config.h'
$configText = Get-Content -Raw -LiteralPath `
    (Join-Path $repoRoot 'System\User\system_user_config.h')
$configText = $configText.Replace(
    '#define SYSTEM_BUILD_FUSION_ALGORITHM SYSTEM_FUSION_KF6',
    '#define SYSTEM_BUILD_FUSION_ALGORITHM SYSTEM_FUSION_NONE')
Set-Content -LiteralPath $pureInsConfigPath -Value $configText -NoNewline
Invoke-HostTest -Name 'profiles_pure_ins' -ExtraCompilerArgs @(
    "-I$pureInsConfigDir"
) -Sources $profileSources

Invoke-HostTest -Name 'attitude_alignment' -Sources @(
    "$repoRoot\Tests\Host\test_attitude_alignment.c",
    "$repoRoot\Algorithm\Alignment\Common\Src\attitude_alignment.c",
    "$repoRoot\Algorithm\Alignment\Common\Src\attitude_preflight.c",
    "$repoRoot\Algorithm\Alignment\GravityKnownYaw\Src\alignment_gravity_known_yaw.c",
    "$repoRoot\Algorithm\Alignment\GravityMagTriad\Src\attitude_triad.c",
    "$repoRoot\Algorithm\Common\Src\attitude_frame.c"
)

$alignmentStrategyCommonSources = @(
    "$repoRoot\Tests\Host\test_alignment_strategy.c",
    "$repoRoot\Algorithm\Alignment\Common\Src\attitude_alignment.c",
    "$repoRoot\Algorithm\Common\Src\attitude_frame.c"
)
Invoke-HostTest -Name 'alignment_strategy_gravity_known_yaw' `
    -ExtraCompilerArgs @(
        '-DTEST_ALIGNMENT_GRAVITY_KNOWN_YAW=1',
        "-I$repoRoot\Algorithm\Alignment\GravityKnownYaw\Inc"
    ) -Sources ($alignmentStrategyCommonSources + @(
        "$repoRoot\Algorithm\Alignment\GravityKnownYaw\Src\alignment_gravity_known_yaw.c",
        "$repoRoot\Algorithm\Alignment\GravityKnownYaw\Src\alignment_strategy_binding.c"
    ))
Invoke-HostTest -Name 'alignment_strategy_gravity_mag_triad' `
    -ExtraCompilerArgs @(
        '-DTEST_ALIGNMENT_GRAVITY_MAG=1',
        "-I$repoRoot\Algorithm\Alignment\GravityMagTriad\Inc"
    ) -Sources ($alignmentStrategyCommonSources + @(
        "$repoRoot\Algorithm\Alignment\GravityMagTriad\Src\attitude_triad.c",
        "$repoRoot\Algorithm\Alignment\GravityMagTriad\Src\alignment_strategy_binding.c"
    ))
Invoke-HostTest -Name 'alignment_strategy_hardware_quat6_known_yaw' `
    -ExtraCompilerArgs @(
        '-DTEST_ALIGNMENT_HW_QUAT=1',
        "-I$repoRoot\Algorithm\Alignment\HardwareQuat6AxisKnownYaw\Inc"
    ) -Sources ($alignmentStrategyCommonSources + @(
        "$repoRoot\Algorithm\Alignment\HardwareQuat6AxisKnownYaw\Src\alignment_strategy_binding.c"
    ))
Invoke-HostTest -Name 'alignment_strategy_hardware_quat9' `
    -ExtraCompilerArgs @(
        '-DTEST_ALIGNMENT_HW_QUAT=1',
        "-I$repoRoot\Algorithm\Alignment\HardwareQuat9Axis\Inc"
    ) -Sources ($alignmentStrategyCommonSources + @(
        "$repoRoot\Algorithm\Alignment\HardwareQuat9Axis\Src\alignment_strategy_binding.c"
    ))

$alignmentSystemSources = @(
    "$repoRoot\Tests\Host\test_system_alignment.c",
    "$repoRoot\Tests\Host\Fixtures\source_selector_lock_stub.c",
    $hostPlatformMock,
    "$repoRoot\Common\Src\common_format.c",
    "$repoRoot\System\Alignment\Src\system_alignment.c",
    "$repoRoot\System\Alignment\Src\system_alignment_source.c",
    "$repoRoot\System\Calibration\Src\system_calibration.c",
    "$repoRoot\Algorithm\Calibration\Src\imu_six_face_calibration.c"
)
Invoke-HostTest -Name 'system_alignment' -ExtraCompilerArgs @(
    '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=6U'
) -Sources $alignmentSystemSources
Invoke-HostTest -Name 'system_alignment_pure_ins' -ExtraCompilerArgs @(
    '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=6U',
    '-DSYSTEM_BUILD_ESTIMATOR_ENABLED=0U',
    '-DSYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_NONE'
) -Sources $alignmentSystemSources

Invoke-HostTest -Name 'system_inertial' -Sources @(
    "$repoRoot\Tests\Host\test_system_inertial.c",
    $hostPlatformMock,
    "$repoRoot\System\Inertial\Src\system_inertial.c",
    "$repoRoot\System\User\system_user_inertial_config.c"
)

Invoke-HostTest -Name 'imu_sample_bus' -Sources @(
    "$repoRoot\Tests\Host\test_imu_sample_bus.c",
    $hostPlatformMock,
    "$repoRoot\APP\Src\imu_sample_bus.c"
)

Invoke-HostTest -Name 'system_indicator' -ExtraCompilerArgs @(
    '-DSYSTEM_INDICATOR_GNSS_ENABLE=1U'
) -Sources @(
    "$repoRoot\Tests\Host\test_system_indicator.c",
    "$repoRoot\System\Indicator\Src\system_indicator.c"
)

$calibrationSources = @(
    "$repoRoot\Tests\Host\test_system_calibration.c",
    "$repoRoot\Tests\Host\Fixtures\source_selector_lock_stub.c",
    $hostPlatformMock,
    "$repoRoot\System\Calibration\Src\system_calibration.c",
    "$repoRoot\System\Calibration\Src\system_calibration_correction.c",
    "$repoRoot\Algorithm\Calibration\Src\imu_six_face_calibration.c"
)
Invoke-HostTest -Name 'system_calibration_default' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_DEFAULT_Y_POSITIVE=1',
    '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=6U'
) -Sources $calibrationSources
foreach ($direction in @(
    'SYSTEM_AXIS_DIRECTION_X_POSITIVE',
    'SYSTEM_AXIS_DIRECTION_X_NEGATIVE',
    'SYSTEM_AXIS_DIRECTION_Y_POSITIVE',
    'SYSTEM_AXIS_DIRECTION_Y_NEGATIVE',
    'SYSTEM_AXIS_DIRECTION_Z_POSITIVE',
    'SYSTEM_AXIS_DIRECTION_Z_NEGATIVE')) {
    Invoke-HostTest -Name ("system_calibration_" + $direction.ToLower()) `
        -ExtraCompilerArgs @("-DSYSTEM_IMU_STARTUP_GRAVITY_DIRECTION=$direction",
            '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=6U') `
        -Sources $calibrationSources
}

Invoke-HostTest -Name 'runtime_commands' -ExtraCompilerArgs @(
    '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=0U',
    '-DSILVERSTAR_PROTOCOL_LOGGING_ENABLED=0U'
) -Sources @(
    "$repoRoot\Tests\Host\test_runtime_commands.c",
    "$repoRoot\Common\Src\common_format.c",
    "$repoRoot\APP\Src\telemetry_task.c",
    "$repoRoot\Modules\Src\telemetry_service.c",
    "$repoRoot\System\Alignment\Src\system_alignment.c",
    "$repoRoot\System\Alignment\Src\system_alignment_source.c",
    "$repoRoot\System\Calibration\Src\system_calibration.c",
    "$repoRoot\System\Calibration\Src\system_calibration_correction.c",
    "$repoRoot\Algorithm\Calibration\Src\imu_six_face_calibration.c",
    "$repoRoot\Protocol\Src\air_protocol.c"
)
Invoke-HostTest -Name 'runtime_startup' -ExtraCompilerArgs @(
    '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=0U'
) -Sources @(
    "$repoRoot\Tests\Host\test_runtime_startup.c",
    "$repoRoot\APP\Src\app_tasks.c",
    "$repoRoot\System\Calibration\Src\system_calibration.c",
    "$repoRoot\System\Calibration\Src\system_calibration_correction.c",
    "$repoRoot\System\Indicator\Src\system_indicator.c",
    "$repoRoot\FlightLogic\Indicator\GpioStatus\Src\indicator_service.c",
    "$repoRoot\Algorithm\Calibration\Src\imu_six_face_calibration.c"
)
Invoke-HostTest -Name 'fault_hook' -ExtraCompilerArgs @(
    '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=0U'
) -Sources @(
    "$repoRoot\Tests\Host\test_fault_hook.c",
    "$repoRoot\APP\Src\app_tasks.c",
    "$repoRoot\System\Calibration\Src\system_calibration.c",
    "$repoRoot\System\Calibration\Src\system_calibration_correction.c",
    "$repoRoot\System\Indicator\Src\system_indicator.c",
    "$repoRoot\FlightLogic\Indicator\GpioStatus\Src\indicator_service.c",
    "$repoRoot\Algorithm\Calibration\Src\imu_six_face_calibration.c"
)
foreach ($mask in @(0, 2, 4, 6)) {
    Invoke-HostTest -Name "calibration_build_gate_$mask" -ExtraCompilerArgs @(
        "-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=$mask"
    ) -Sources @(
        "$repoRoot\Tests\Host\test_calibration_build_gate.c",
        "$repoRoot\System\Calibration\Src\system_calibration.c",
        "$repoRoot\System\Calibration\Src\system_calibration_correction.c",
        "$repoRoot\Algorithm\Calibration\Src\imu_six_face_calibration.c",
        "$repoRoot\Protocol\Src\air_protocol.c"
    )
    Invoke-HostTest -Name "telemetry_build_mask_$mask" -ExtraCompilerArgs @(
        "-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=$mask"
    ) -Sources @(
        "$repoRoot\Tests\Host\test_telemetry.c",
        "$repoRoot\Modules\Src\telemetry_service.c",
        "$repoRoot\System\Calibration\Src\system_calibration_correction.c",
        "$repoRoot\Protocol\Src\air_protocol.c"
    )
}

$capabilitySource = "$repoRoot\Tests\Host\test_build_capability_contract.c"
Invoke-ExpectedCompileSuccess -Name 'capability_jy901b_gravity_known_yaw' `
    -ExtraCompilerArgs @('-DTEST_EXPECT_DEFAULT_JY901B_PROFILE=1') `
    -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_missing_imu_noise' `
    -ExtraCompilerArgs @(
        '-include', "$repoRoot\Tests\Host\Fixtures\algorithm_noise_absent.h",
        '-DSYSTEM_SELECTED_IMU_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_missing_gnss_noise' `
    -ExtraCompilerArgs @(
        '-include', "$repoRoot\Tests\Host\Fixtures\algorithm_noise_absent.h",
        '-DSYSTEM_SELECTED_GNSS_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_missing_baro_noise' `
    -ExtraCompilerArgs @(
        '-include', "$repoRoot\Tests\Host\Fixtures\algorithm_noise_absent.h",
        '-DSYSTEM_SELECTED_BAROMETER_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileSuccess -Name 'capability_noise_overrides' `
    -ExtraCompilerArgs ($estimatorNoiseOverrideArgs + @(
        '-DSYSTEM_SELECTED_IMU_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE=0U',
        '-DSYSTEM_SELECTED_GNSS_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE=0U',
        '-DSYSTEM_SELECTED_BAROMETER_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE=0U'
    )) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_jy901b_gravity_mag_rejected' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_ALIGNMENT_BUILD_ALGORITHM=SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD',
        '-DSYSTEM_USER_MAGNETOMETER_ENABLE=1U',
        '-DJY901B_MAGNETOMETER_ADAPTER_ENABLE=1U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileSuccess -Name 'capability_future_triad' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_ALIGNMENT_BUILD_ALGORITHM=SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD',
        '-DSYSTEM_USER_MAGNETOMETER_ENABLE=1U',
        '-DJY901B_MAGNETOMETER_ADAPTER_ENABLE=1U',
        '-DSYSTEM_SELECTED_MAGNETOMETER_PHYSICAL_UNIT_AVAILABLE=1U',
        '-DSYSTEM_SELECTED_MAGNETOMETER_ABSOLUTE_VECTOR_QUALIFIED=1U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileSuccess -Name 'capability_jy901b_hw_quat_6axis_preflight' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_ALIGNMENT_BUILD_ALGORITHM=SYSTEM_ALIGNMENT_HW_QUAT_6AXIS_KNOWN_YAW'
    ) -Source $capabilitySource
Invoke-ExpectedCompileSuccess -Name 'capability_jy901b_hw_quat_9axis_preflight' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_ALIGNMENT_BUILD_ALGORITHM=SYSTEM_ALIGNMENT_HW_QUAT_9AXIS'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_hw_quat_6axis_preflight_unqualified' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_ALIGNMENT_BUILD_ALGORITHM=SYSTEM_ALIGNMENT_HW_QUAT_6AXIS_KNOWN_YAW',
        '-DSYSTEM_SELECTED_HARDWARE_QUATERNION_PREFLIGHT_ALIGNMENT_6AXIS_QUALIFIED=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_hw_quat_9axis_preflight_unqualified' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_ALIGNMENT_BUILD_ALGORITHM=SYSTEM_ALIGNMENT_HW_QUAT_9AXIS',
        '-DSYSTEM_SELECTED_HARDWARE_QUATERNION_PREFLIGHT_ALIGNMENT_9AXIS_QUALIFIED=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileSuccess -Name 'capability_jy901b_stillness_landing' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_STILLNESS'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_impact_unqualified' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS'
    ) -Source $capabilitySource
Invoke-ExpectedCompileSuccess -Name 'capability_future_impact_qualified' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS',
        '-DSYSTEM_SELECTED_IMU_LANDING_IMPACT_QUALIFIED=1U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileSuccess -Name 'capability_jy901b_baro_imu_window_landing' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_BARO_IMU_WINDOW'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_stillness_unqualified' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_STILLNESS',
        '-DSYSTEM_SELECTED_IMU_LANDING_STILLNESS_QUALIFIED=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_baro_imu_stillness_unqualified' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_BARO_IMU_WINDOW',
        '-DSYSTEM_SELECTED_IMU_LANDING_STILLNESS_QUALIFIED=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_deploy_without_action' `
    -ExtraCompilerArgs @('-DSYSTEM_USER_MISSION_ACTION_ENABLE=0U') `
    -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_required_baro_missing' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_USER_BAROMETER_ENABLE=0U',
        '-DSYSTEM_USER_ALIGNMENT_REQUIRED_MASK=(SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE|SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN)'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_required_gnss_missing' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_USER_GNSS_ENABLE=0U',
        '-DSYSTEM_USER_ALIGNMENT_REQUIRED_MASK=(SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE|SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN)'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_stillness_without_gyro' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_STILLNESS',
        '-DSYSTEM_SELECTED_IMU_GYRO_AVAILABLE=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_tilt_without_propagation' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_TILT',
        '-DSYSTEM_SELECTED_IMU_SOFTWARE_PROPAGATION_QUALIFIED=0U'
    ) -Source $capabilitySource
Invoke-ExpectedCompileFailure -Name 'capability_delay_without_time' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_DELAY',
        '-DSYSTEM_BUILD_MISSION_MONOTONIC_TIME_AVAILABLE=0U'
    ) -Source $capabilitySource

Invoke-HostTest -Name 'navigation_kf_replay' -Sources @(
    "$repoRoot\Tests\Host\test_navigation_kf_replay.c",
    "$repoRoot\Algorithm\Estimator\KF6\Src\navigation_kf.c",
    "$repoRoot\Algorithm\Estimator\KF6\Src\navigation_kf_replay.c",
    "$repoRoot\System\Src\system_time.c"
)

Invoke-HostTest -Name 'air_kf' -Sources @(
    "$repoRoot\Tests\Host\test_air_kf.c",
    "$repoRoot\Protocol\Src\air_protocol.c",
    "$repoRoot\Algorithm\Estimator\KF6\Src\navigation_kf.c",
    "$repoRoot\Algorithm\Common\Src\attitude_frame.c",
    "$repoRoot\System\Src\system_estimator_profile.c"
)

Invoke-HostTest -Name 'jy901b_device' -Sources @(
    "$repoRoot\Tests\Host\test_jy901b_device.c",
    $hostPlatformMock,
    "$repoRoot\Generated\Src\project_resources.c",
    "$repoRoot\Devices\IMU\JY901B\Src\jy901b_device.c"
)
Invoke-HostTest -Name 'jy901b_adapter' -Sources @(
    "$repoRoot\Tests\Host\test_jy901b_adapter.c",
    $hostPlatformMock,
    "$repoRoot\Generated\Src\project_resources.c",
    "$repoRoot\Devices\IMU\JY901B\Src\jy901b_device.c",
    "$repoRoot\Devices\IMU\JY901B\Adapter\Src\jy901b_imu_adapter.c",
    "$repoRoot\Devices\IMU\JY901B\Adapter\Src\jy901b_startup.c",
    "$repoRoot\Devices\IMU\JY901B\Adapter\Src\jy901b_sample_quality.c",
    "$repoRoot\Devices\IMU\JY901B\Adapter\Src\jy901b_barometer_adapter.c",
    "$repoRoot\System\Src\system_device_startup.c"
)
Invoke-HostTest -Name 'neo_m9n_device' -Sources @(
    "$repoRoot\Tests\Host\test_neo_m9n_device.c",
    "$repoRoot\Generated\Src\project_resources.c",
    "$repoRoot\Devices\GNSS\NEO_M9N\Src\neo_m9n_device.c",
    "$repoRoot\Devices\GNSS\NEO_M9N\Adapter\Src\neo_m9n_startup.c",
    "$repoRoot\System\Src\system_device_startup.c"
)
Invoke-HostTest -Name 'neo_m9n_adapter' -Sources @(
    "$repoRoot\Tests\Host\test_neo_m9n_adapter.c",
    $hostPlatformMock,
    "$repoRoot\Generated\Src\project_resources.c",
    "$repoRoot\Devices\GNSS\NEO_M9N\Src\neo_m9n_device.c",
    "$repoRoot\Devices\GNSS\NEO_M9N\Adapter\Src\neo_m9n_system_adapter.c",
    "$repoRoot\Devices\GNSS\NEO_M9N\Adapter\Src\neo_m9n_startup.c",
    "$repoRoot\System\Src\system_device_startup.c",
    "$repoRoot\System\Src\system_gnss_quality.c"
)
Invoke-HostTest -Name 'sx1281_device' -Sources @(
    "$repoRoot\Tests\Host\test_sx1281_device.c",
    "$repoRoot\Generated\Src\project_resources.c",
    "$repoRoot\Devices\Telemetry\SX1281\Src\sx1281_device.c"
)
Invoke-HostTest -Name 'jy901b_multi_instance' `
    -ExtraCompilerArgs @($multiInstanceFixtureInclude) -Sources @(
    "$repoRoot\Tests\Host\test_jy901b_multi_instance.c",
    $hostPlatformMock,
    $multiInstanceResourceFixture,
    "$repoRoot\Devices\IMU\JY901B\Src\jy901b_device.c"
)
Invoke-HostTest -Name 'neo_m9n_multi_instance' `
    -ExtraCompilerArgs @($multiInstanceFixtureInclude) -Sources @(
    "$repoRoot\Tests\Host\test_neo_m9n_multi_instance.c",
    $multiInstanceResourceFixture,
    "$repoRoot\Devices\GNSS\NEO_M9N\Src\neo_m9n_device.c"
)
Invoke-HostTest -Name 'sx1280_hal_multi_instance' `
    -ExtraCompilerArgs @($multiInstanceFixtureInclude) -Sources @(
    "$repoRoot\Tests\Host\test_sx1280_hal_multi_instance.c",
    "$repoRoot\Middlewares\Third_Party\SX1280lib\sx1280-hal.c"
)
Invoke-HostTest -Name 'sx1281_multi_instance' `
    -ExtraCompilerArgs @($multiInstanceFixtureInclude) -Sources @(
    "$repoRoot\Tests\Host\test_sx1281_multi_instance.c",
    $multiInstanceResourceFixture,
    "$repoRoot\Devices\Telemetry\SX1281\Src\sx1281_device.c"
)
Invoke-HostTest -Name 'source_selector' -ExtraCompilerArgs @(
    '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections'
) -Sources @(
    "$repoRoot\Tests\Host\test_source_selector.c",
    "$repoRoot\System\Src\system_source_selector.c"
)
Invoke-HostTest -Name 'board_power_service' -Sources @(
    "$repoRoot\Tests\Host\test_board_power_service.c",
    $hostPlatformMock,
    "$repoRoot\Board\SilverStar_0_5\Services\Src\power_service.c"
)
Invoke-HostTest -Name 'board_mission_action_service' -Sources @(
    "$repoRoot\Tests\Host\test_board_mission_action_service.c",
    "$repoRoot\Board\SilverStar_0_5\Services\Src\mission_action_service.c"
)

Invoke-HostTest -Name 'sensor_quality' -Sources @(
    "$repoRoot\Tests\Host\test_sensor_quality.c",
    $hostPlatformMock,
    "$repoRoot\System\Src\system_gnss_quality.c",
    "$repoRoot\System\Src\system_barometer.c",
    "$repoRoot\System\Src\system_estimator_diagnostics.c"
)
Invoke-HostTest -Name 'estimator_barometer_pending' -Sources @(
    "$repoRoot\Tests\Host\test_estimator_barometer_pending.c",
    "$repoRoot\APP\Src\estimator_barometer_pending.c"
)
Invoke-HostTest -Name 'navigation_quality_supervisor' -Sources @(
    "$repoRoot\Tests\Host\test_navigation_quality_supervisor.c",
    $hostPlatformMock,
    "$repoRoot\Algorithm\Common\Src\navigation_quality.c",
    "$repoRoot\System\Src\system_navigation_health.c"
)
Invoke-HostTest -Name 'sensor_status' -Sources @(
    "$repoRoot\Tests\Host\test_sensor_status.c",
    $hostPlatformMock,
    "$repoRoot\System\Src\system_sensor_status.c"
)
Invoke-HostTest -Name 'device_native_log' -Sources (@(
    "$repoRoot\Tests\Host\test_device_native_log.c",
    "$repoRoot\APP\Src\device_native_log.c"
) + $sslogSources)
Invoke-HostTest -Name 'lifecycle' -Sources @(
    "$repoRoot\Tests\Host\test_lifecycle.c",
    $hostPlatformMock,
    "$repoRoot\FlightLogic\FlightCycle\Src\silverstar_flight_cycle.c"
)

$recoverySources = @(
    "$repoRoot\Tests\Host\test_flight_recovery.c",
    $hostPlatformMock,
    "$repoRoot\FlightLogic\FlightCycle\Src\silverstar_flight_recovery.c",
    "$repoRoot\FlightLogic\Deployment\MultiTrigger\Src\flight_deployment.c",
    "$repoRoot\FlightLogic\Landing\BarometerImuWindow\Src\flight_landing.c"
)
Invoke-HostTest -Name 'flight_recovery_apogee' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_APOGEE=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ',
    '-DSYSTEM_FLIGHT_DEPLOY_CONFIRM_MS=100U'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_apogee_immediate' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_APOGEE=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_tilt' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_TILT=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_TILT',
    '-DSYSTEM_FLIGHT_TILT_THRESHOLD_DEG=30.0f',
    '-DSYSTEM_FLIGHT_DEPLOY_CONFIRM_MS=100U'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_tilt_immediate' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_TILT=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_TILT',
    '-DSYSTEM_FLIGHT_TILT_THRESHOLD_DEG=30.0f'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_apogee_or_tilt' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_OR=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=(SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ|SYSTEM_DEPLOY_TRIGGER_TILT)',
    '-DSYSTEM_FLIGHT_TILT_THRESHOLD_DEG=30.0f'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_apogee_or_delay' `
    -ExtraCompilerArgs @(
        '-DTEST_EXPECT_PAIR=1',
        '-DTEST_EXPECTED_DEPLOY_MASK=(SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ|SYSTEM_DEPLOY_TRIGGER_DELAY)',
        '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=(SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ|SYSTEM_DEPLOY_TRIGGER_DELAY)',
        '-DSYSTEM_FLIGHT_DEPLOY_DELAY_MS=5000U'
    ) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_tilt_or_delay' `
    -ExtraCompilerArgs @(
        '-DTEST_EXPECT_PAIR=1',
        '-DTEST_EXPECTED_DEPLOY_MASK=(SYSTEM_DEPLOY_TRIGGER_TILT|SYSTEM_DEPLOY_TRIGGER_DELAY)',
        '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=(SYSTEM_DEPLOY_TRIGGER_TILT|SYSTEM_DEPLOY_TRIGGER_DELAY)',
        '-DSYSTEM_FLIGHT_TILT_THRESHOLD_DEG=30.0f',
        '-DSYSTEM_FLIGHT_DEPLOY_DELAY_MS=5000U'
    ) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_delay' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_DELAY=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_DELAY',
    '-DSYSTEM_FLIGHT_DEPLOY_DELAY_MS=5000U'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_all_triggers' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_ALL=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=(SYSTEM_DEPLOY_TRIGGER_TILT|SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ|SYSTEM_DEPLOY_TRIGGER_DELAY)',
    '-DSYSTEM_FLIGHT_TILT_THRESHOLD_DEG=30.0f',
    '-DSYSTEM_FLIGHT_DEPLOY_DELAY_MS=5000U'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_none_landing' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_NONE=1', '-DTEST_EXPECT_STILLNESS=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_NONE',
    '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_STILLNESS',
    '-DSYSTEM_FLIGHT_LANDING_CONFIRM_MS=100U'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_impact_landing' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_NONE=1', '-DTEST_EXPECT_IMPACT=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_NONE',
    '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS',
    '-DSYSTEM_FLIGHT_LANDING_IMPACT_INHIBIT_MS=100U',
    '-DSYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2=20.0f',
    '-DSYSTEM_FLIGHT_LANDING_CONFIRM_MS=100U',
    '-DSYSTEM_SELECTED_IMU_LANDING_IMPACT_QUALIFIED=1U'
) -Sources $recoverySources
Invoke-HostTest -Name 'flight_recovery_baro_imu_landing' -ExtraCompilerArgs @(
    '-DTEST_EXPECT_NONE=1', '-DTEST_EXPECT_BARO=1',
    '-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_NONE',
    '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_BARO_IMU_WINDOW',
    '-DSYSTEM_FLIGHT_LANDING_BARO_TRIGGER_WINDOW_MS=100U',
    '-DSYSTEM_FLIGHT_LANDING_BARO_TRIGGER_MIN_SAMPLES=3U',
    '-DSYSTEM_FLIGHT_LANDING_CANDIDATE_DURATION_MS=200U',
    '-DSYSTEM_FLIGHT_LANDING_BARO_MIN_SAMPLES=3U',
    '-DSYSTEM_FLIGHT_LANDING_IMU_MIN_SAMPLES=3U',
    '-DSYSTEM_FLIGHT_LANDING_MIN_COVERAGE_PERCENT=80U'
) -Sources $recoverySources

Invoke-ExpectedCompileFailure -Name 'impact_capability_guard' `
    -ExtraCompilerArgs @(
        '-DSYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS',
        '-DSYSTEM_SELECTED_IMU_LANDING_IMPACT_QUALIFIED=0U'
    ) -Source "$repoRoot\Tests\Host\test_flight_config_compile.c"

if ($hostLoggingEnabled) {
Invoke-HostTest -Name 'lifecycle_logging' -Sources @(
    "$repoRoot\Tests\Host\test_lifecycle_logging.c",
    "$repoRoot\Tests\Host\Fixtures\source_selector_lock_stub.c",
    $hostPlatformMock,
    "$repoRoot\APP\Src\flight_task.c",
    "$repoRoot\APP\Src\logger_task.c",
    "$repoRoot\FlightLogic\FlightCycle\Src\silverstar_flight_cycle.c",
    "$repoRoot\System\Src\system_navigation_health.c",
    "$repoRoot\System\Alignment\Src\system_alignment.c"
)
}

$startupSources = @(
    "$repoRoot\Tests\Host\test_system_startup.c",
    "$repoRoot\System\Src\system_startup.c"
)
Invoke-HostTest -Name 'system_startup' -Sources $startupSources
Invoke-HostTest -Name 'system_startup_write_verify' -ExtraCompilerArgs @(
    '-DSYSTEM_GNSS_BOOT_WRITE_CONFIG=1U',
    '-DSYSTEM_GNSS_BOOT_VERIFY_CONFIG=1U'
) -Sources $startupSources
Invoke-HostTest -Name 'system_startup_async_no_explicit_verify' -ExtraCompilerArgs @(
    '-DSYSTEM_GNSS_BOOT_WRITE_CONFIG=1U',
    '-DSYSTEM_GNSS_BOOT_VERIFY_CONFIG=0U',
    '-DSYSTEM_IMU_BOOT_VERIFY_CONFIG=0U'
) -Sources $startupSources
Invoke-HostTest -Name 'system_startup_no_writes' -ExtraCompilerArgs @(
    '-DSYSTEM_GNSS_BOOT_WRITE_CONFIG=0U',
    '-DSYSTEM_IMU_BOOT_WRITE_CONFIG=0U'
) -Sources $startupSources

Invoke-HostTest -Name 'health' -Sources @(
    "$repoRoot\Tests\Host\test_health.c",
    $hostPlatformMock,
    "$repoRoot\System\Src\system_health.c",
    "$repoRoot\System\Src\system_navigation_profile.c"
)
Invoke-HostTest -Name 'console' -Sources @(
    "$repoRoot\Tests\Host\test_console.c",
    $hostPlatformMock,
    "$repoRoot\Common\Src\common_format.c",
    "$repoRoot\System\Src\system_console.c",
    "$repoRoot\System\Src\system_barometer.c",
    "$repoRoot\System\Src\system_estimator_diagnostics.c",
    "$repoRoot\System\Alignment\Src\system_alignment_source.c",
    "$repoRoot\Tests\Host\Fixtures\multi_instance_project_fixture.c"
)
Invoke-HostTest -Name 'telemetry' -Sources @(
    "$repoRoot\Tests\Host\test_telemetry.c",
    "$repoRoot\Modules\Src\telemetry_service.c",
    "$repoRoot\System\Calibration\Src\system_calibration_correction.c",
    "$repoRoot\Protocol\Src\air_protocol.c"
)

$projectSourcesPath = Join-Path $repoRoot 'Generated\project_sources.mk'
$estimatorBuildLines = @(Get-Content -LiteralPath $projectSourcesPath |
    Where-Object { $_ -match '^\s*SYSTEM_BUILD_ESTIMATOR_ENABLED=(0U|1U)\s*(?:\\)?\s*$' })
if ($estimatorBuildLines.Count -ne 1) {
    throw 'Generated source graph must define SYSTEM_BUILD_ESTIMATOR_ENABLED exactly once.'
}
$estimatorBuildValue = [regex]::Match(
    $estimatorBuildLines[0], 'SYSTEM_BUILD_ESTIMATOR_ENABLED=(0U|1U)').Groups[1].Value
$estimatorLoggerArgs = @("-DTEST_EXPECT_ESTIMATOR_CONFIG_ENABLED=$estimatorBuildValue")

# Exercise actual task preparation and the selected kernel. LTO discards only
# unused RTOS task loops; the origin collector, prepare and reset stay real.
$preparationFusionLines = @(Get-Content -LiteralPath $projectSourcesPath |
    Where-Object { $_ -match '^\s*SYSTEM_BUILD_FUSION_ALGORITHM=[A-Z0-9_]+\s*(?:\\)?\s*$' })
if ($preparationFusionLines.Count -ne 1) {
    throw 'Generated graph must define SYSTEM_BUILD_FUSION_ALGORITHM exactly once.'
}
$preparationFusion = [regex]::Match($preparationFusionLines[0],
    'SYSTEM_BUILD_FUSION_ALGORITHM=([A-Z0-9_]+)').Groups[1].Value
$preparationArgs = @('-flto', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
    '-DSILVERSTAR_PROTOCOL_LOGGING_ENABLED=0U',
    "-DSYSTEM_BUILD_ESTIMATOR_ENABLED=$estimatorBuildValue",
    "-DSYSTEM_BUILD_FUSION_ALGORITHM=$preparationFusion")
$preparationSources = @(
    "$repoRoot\Tests\Host\test_estimator_preparation.c", $hostPlatformMock,
    "$repoRoot\APP\Src\ins_task.c", "$repoRoot\APP\Src\estimator_bus.c",
    "$repoRoot\APP\Src\estimator_barometer_pending.c",
    "$repoRoot\Algorithm\Common\Src\attitude_frame.c",
    "$repoRoot\Algorithm\Common\Src\geodesy_local.c",
    "$repoRoot\Algorithm\Common\Src\navigation_quality.c",
    "$repoRoot\Algorithm\INS\Coning2Sculling2\Src\ins_mechanization.c",
    "$repoRoot\System\Src\system_estimator_diagnostics.c",
    "$repoRoot\System\Src\system_estimator_profile.c",
    "$repoRoot\System\Src\system_navigation_profile.c",
    "$repoRoot\System\Src\system_navigation_health.c",
    "$repoRoot\System\Src\system_gnss_quality.c",
    "$repoRoot\System\Src\system_barometer.c"
)
if ($preparationFusion -eq 'SYSTEM_FUSION_KF6') {
    $preparationSources += @(
        "$repoRoot\Algorithm\Estimator\KF6\Src\navigation_kf.c",
        "$repoRoot\Algorithm\Estimator\KF6\Src\navigation_kf_replay.c",
        "$repoRoot\Algorithm\Estimator\KF6\Src\navigation_integrity.c"
    )
}
elseif ($preparationFusion -eq 'SYSTEM_FUSION_ESKF15') {
    $preparationArgs += @('-DSYSTEM_BUILD_ESKF15_ENABLED=1U',
        "-I$repoRoot\Algorithm\Estimator\ESKF15\Inc")
    $preparationSources += @(
        "$repoRoot\Algorithm\Estimator\ESKF15\Src\navigation_eskf.c",
        "$repoRoot\Algorithm\Estimator\ESKF15\Src\navigation_eskf_replay.c",
        "$repoRoot\Algorithm\Estimator\ESKF15\Src\navigation_eskf_backend.c",
        "$repoRoot\System\Calibration\Src\system_calibration.c"
    )
}
Invoke-HostTest -Name 'estimator_preparation_actual' -ExtraCompilerArgs $preparationArgs `
    -Sources $preparationSources

$loggerSources = @(
    "$repoRoot\Tests\Host\test_logger.c",
    $hostPlatformMock,
    "$repoRoot\APP\Src\diagnostic_log.c",
    "$repoRoot\APP\Src\logger_bus.c",
    "$repoRoot\Common\Src\common_spsc_queue.c",
    "$repoRoot\System\Src\system_log_policy.c",
    "$repoRoot\System\Src\system_profile.c",
    "$repoRoot\System\Src\system_navigation_profile.c",
    "$repoRoot\System\Src\system_estimator_profile.c",
    "$repoRoot\Generated\Src\project_metadata.c",
    "$repoRoot\Generated\Src\project_log_decoder_profile.c",
    "$repoRoot\Generated\Src\project_log_config.c"
) + $sslogSources
Invoke-HostTest -Name 'logger' `
    -ExtraCompilerArgs $estimatorLoggerArgs -Sources $loggerSources
Invoke-HostTest -Name 'logger_streaming_actual' -ExtraCompilerArgs @(
    '-flto', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections'
) -Sources (@("$repoRoot\Tests\Host\test_logger_streaming.c", $hostPlatformMock) + $sslogSources)
if ($preparationFusion -eq 'SYSTEM_FUSION_ESKF15') {
    $backendSources = @($loggerSources | Where-Object {
        $_ -notmatch '(test_logger|diagnostic_log)\.c$'
    }) + @(
        "$repoRoot\Tests\Host\test_eskf_backend.c",
        "$repoRoot\Algorithm\Estimator\ESKF15\Src\navigation_eskf.c",
        "$repoRoot\Algorithm\Estimator\ESKF15\Src\navigation_eskf_replay.c",
        "$repoRoot\Algorithm\Estimator\ESKF15\Src\navigation_eskf_backend.c",
        "$repoRoot\Algorithm\Common\Src\geodesy_local.c",
        "$repoRoot\Algorithm\Common\Src\navigation_quality.c",
        "$repoRoot\APP\Src\estimator_bus.c",
        "$repoRoot\System\Src\system_navigation_health.c",
        "$repoRoot\System\Src\system_gnss_quality.c",
        "$repoRoot\System\Src\system_time.c",
        "$repoRoot\System\Calibration\Src\system_calibration.c"
    )
    Invoke-HostTest -Name 'eskf_backend_actual' -ExtraCompilerArgs @(
        '-flto', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
        '-DSYSTEM_BUILD_ESTIMATOR_ENABLED=0U', '-DSYSTEM_BUILD_ESKF15_ENABLED=1U',
        '-DSYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_ESKF15',
        "-I$repoRoot\Algorithm\Estimator\ESKF15\Inc"
    ) -Sources $backendSources
}
Invoke-HostTest -Name 'logger_estimator_noise_overrides' `
    -ExtraCompilerArgs ($estimatorNoiseOverrideArgs + $estimatorLoggerArgs) `
    -Sources $loggerSources

Invoke-HostTest -Name 'golden_sample' -Sources (@(
    "$repoRoot\Tests\Host\generate_golden_sample.c",
    "$repoRoot\Generated\Src\project_log_decoder_profile.c"
) + $sslogSources)

$script:collectHostJobs = $false
$plannedJobs = @($script:hostJobs | Where-Object {
    (($_.Kind -eq 'HOST_TEST') -and
        (@($_.Sources | Where-Object { -not (Test-Path -LiteralPath $_) }).Count -eq 0)) -or
    (($_.Kind -ne 'HOST_TEST') -and (Test-Path -LiteralPath $_.Source))
})
foreach ($taskKind in @(
    'HOST_TEST',
    'HOST_COMPILE_PASS',
    'HOST_EXPECTED_FAILURE'
)) {
    $total = @($plannedJobs | Where-Object { $_.Kind -eq $taskKind }).Count
    $script:progressCompleted[$taskKind] = 0
    $script:progressTotals[$taskKind] = $total
    if ($total -gt 0) {
        Write-Output "FCCG_PROGRESS|$taskKind|PLAN|$total"
    }
}
foreach ($skippedJob in @($script:hostJobs | Where-Object {
    ($_.Kind -eq 'HOST_TEST') -and
    (@($_.Sources | Where-Object { -not (Test-Path -LiteralPath $_) }).Count -ne 0)
})) {
    Write-Output ("Skipped host test {0}: unselected component sources" -f `
        $skippedJob.Name)
}
foreach ($job in $plannedJobs) {
    switch ($job.Kind) {
        'HOST_TEST' {
            Invoke-HostTest -Name $job.Name -Sources $job.Sources `
                -ExtraCompilerArgs $job.ExtraCompilerArgs
        }
        'HOST_COMPILE_PASS' {
            Invoke-ExpectedCompileSuccess -Name $job.Name `
                -Source $job.Source `
                -ExtraCompilerArgs $job.ExtraCompilerArgs
        }
        'HOST_EXPECTED_FAILURE' {
            Invoke-ExpectedCompileFailure -Name $job.Name `
                -Source $job.Source `
                -ExtraCompilerArgs $job.ExtraCompilerArgs
        }
    }
}

$alignmentRuntimeFiles = @(
    "$repoRoot\Modules\Src\telemetry_service.c",
    "$repoRoot\System\Src\system_health.c",
    "$repoRoot\FlightLogic\FlightCycle\Src\silverstar_flight_cycle.c",
    "$repoRoot\System\Indicator\Src\system_indicator.c"
)
foreach ($runtimeFile in $alignmentRuntimeFiles) {
    $largeLocal = Select-String -LiteralPath $runtimeFile `
        -Pattern '\bSystemAlignmentStatus\s+[A-Za-z_][A-Za-z0-9_]*\s*;'
    $fullStatusCall = Select-String -LiteralPath $runtimeFile `
        -Pattern '\bSystemAlignment_StatusGet\s*\('
    if (($null -ne $largeLocal) -or ($null -ne $fullStatusCall)) {
        throw "Full Alignment status returned to periodic runtime path: $runtimeFile"
    }
}
Write-Output 'Alignment periodic runtime stack audit passed.'

$storageIntegrityRunner = Join-Path $repoRoot 'Tests\Host\storage_integrity\run_storage_integrity.py'
$storageSourceGraph = Get-Content -LiteralPath "$repoRoot\Generated\project_sources.mk" -Raw
$storageFlightConfig = Get-Content -LiteralPath "$repoRoot\Generated\Inc\project_flight_config.h" -Raw
if (($storageFlightConfig -match '(?m)^#define\s+SILVERSTAR_PROTOCOL_LOGGING_ENABLED\s+1U\s*$') -and
    ($storageSourceGraph -match '(?m)^\s+Devices/Storage/SdSdioFatFs/Src/storage_service\.c\s*\\?\s*$') -and
    ($storageSourceGraph -match '(?m)^\s+FATFS/Target/sd_diskio\.c\s*\\?\s*$')) {
    & python $storageIntegrityRunner --project $repoRoot --compiler $script:hostCompilerPath
    if ($LASTEXITCODE -ne 0) { throw 'Storage byte-integrity tests failed.' }
}

$hostSummary = ("SilverStar host summary: executables={0} checks={1} " +
    "failures={2} compile_pass_cases={3} expected_compile_failures={4}") -f `
    $script:hostExecutableCount, $script:hostCheckCount, `
    $script:hostFailureCount, $script:compilePassCaseCount, `
    $script:expectedCompileFailureCount
Write-Output $hostSummary
Write-Output 'All SilverStar host tests passed.'
