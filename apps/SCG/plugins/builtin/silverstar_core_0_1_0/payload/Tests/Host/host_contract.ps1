# Host compile inputs follow the emitted SourceGraph. Each explicit -D/-U in a
# fixture replaces the corresponding graph definition, without duplicate -D.
function HostContract_DefinitionsGet {
    param([Parameter(Mandatory = $true)][string]$SourceGraph)
    $blocks = [regex]::Matches($SourceGraph, '(?m)^C_DEFS \+= \\\r?\n(?<body>(?:[ \t]+[^\r\n]+\r?\n?)+)')
    if ($blocks.Count -ne 1) { throw 'Host requires exactly one SourceGraph C_DEFS block.' }
    $definitions = [ordered]@{}
    foreach ($line in ($blocks[0].Groups['body'].Value -split '\r?\n')) {
        $token = $line.Trim().TrimEnd('\').Trim()
        if ($token.Length -eq 0) { continue }
        if ($token -notmatch '^(?<key>[A-Za-z_][A-Za-z0-9_]*)(?:=[^\s]+)?$') {
            throw "Invalid SourceGraph Host definition: $token"
        }
        $key = $Matches['key']
        if ($definitions.Contains($key)) { throw "Duplicate SourceGraph Host definition: $key" }
        $definitions[$key] = '-D' + $token
    }
    if ($definitions.Count -eq 0) { throw 'Empty SourceGraph Host definitions.' }
    return $definitions
}

function HostContract_CompilerArgsGet {
    param([string[]]$Overrides = @())
    $definitions = [ordered]@{}
    foreach ($key in $script:hostGraphDefinitions.Keys) {
        $definitions[$key] = $script:hostGraphDefinitions[$key]
    }
    $other = [System.Collections.Generic.List[string]]::new()
    foreach ($argument in $Overrides) {
        if ($argument -match '^-[DU](?<key>[A-Za-z_][A-Za-z0-9_]*)(?:=.*)?$') {
            $definitions[$Matches['key']] = $argument
        } else { $other.Add($argument) }
    }
    if (-not $definitions.Contains('SYSTEM_ALIGNMENT_BUILD_ALGORITHM')) {
        throw 'Host SourceGraph lacks its selected alignment algorithm.'
    }
    $alignment = ([string]$definitions['SYSTEM_ALIGNMENT_BUILD_ALGORITHM']).Split('=', 2)[1]
    $definitions['TEST_EXPECT_ALIGNMENT_ALGORITHM'] = '-DTEST_EXPECT_ALIGNMENT_ALGORITHM=' + $alignment
    return @($definitions.Values) + @($other)
}

# Named rejections are contracts, not acceptance of an arbitrary compiler error.
$script:hostExpectedDiagnostics = @{
    capability_missing_imu_noise = 'Selected IMU needs estimator noise recommendations or all E/N/U overrides'
    capability_missing_gnss_noise = 'Selected GNSS needs estimator floor recommendations or all floor overrides'
    capability_missing_baro_noise = 'Selected Barometer needs an estimator noise recommendation or override'
    capability_jy901b_gravity_mag_rejected = 'TRIAD requires an enabled, absolute-vector-qualified magnetometer'
    capability_first_release_triad_deferred = 'Magnetometer selection is deferred in the first SCG release'
    capability_hw_quat_6axis_preflight_unqualified = 'HW 6-axis alignment requires a qualified preflight source'
    capability_hw_quat_9axis_preflight_unqualified = 'HW 9-axis alignment requires a qualified preflight source'
    capability_impact_unqualified = 'Impact landing requires stillness- and impact-qualified IMU data'
    impact_capability_guard = 'Impact landing requires stillness- and impact-qualified IMU data'
    capability_jy901s_baro_imu_window_rejected = 'Baro/IMU landing requires qualified IMU and direct altitude'
    capability_selected_baro_imu_window_rejected = 'Baro/IMU landing requires qualified IMU and direct altitude'
    capability_stillness_unqualified = 'Stillness landing requires a stillness-qualified IMU'
    capability_baro_imu_stillness_unqualified = 'Baro/IMU landing requires qualified IMU and direct altitude'
    capability_deploy_without_action = 'The current flight profile requires a START action'
    capability_required_baro_missing = 'Required Barometer origin needs'
    capability_required_gnss_missing = 'Required GNSS origin needs a selected position source'
    capability_stillness_without_gyro = 'Stillness landing requires a stillness-qualified IMU'
    capability_tilt_without_propagation = 'TILT deploy requires selected gyro software propagation'
    capability_delay_without_time = 'DELAY deploy requires mission monotonic time'
}

function HostContract_ExpectedDiagnosticGet {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not $script:hostExpectedDiagnostics.ContainsKey($Name)) {
        throw "Expected rejection has no declared diagnostic: $Name"
    }
    return $script:hostExpectedDiagnostics[$Name]
}

function HostContract_DiskioValidate {
    param([Parameter(Mandatory = $true)][string]$SourceGraph)
    $sources = [regex]::Matches($SourceGraph,
        '(?m)^\s+(?:FATFS/Target/sd_diskio|Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight)\.c\s*\\?\s*$')
    if ($sources.Count -ne 1) {
        throw 'Storage Host requires exactly one authoritative diskio source.'
    }
}

function HostContract_JobPrepare {
    param([Parameter(Mandatory = $true)]$Job)
    # These legacy unit fixtures inject logical CAL/ALIGN interfaces and do not
    # inject the physical MPU epoch witness. Their original safety expectations
    # cover that declared logical fixture only, not the selected MCU epoch path.
    $logicalFixtures = @('test_system_alignment.c', 'test_system_calibration.c',
        'test_runtime_commands.c', 'test_runtime_startup.c', 'test_fault_hook.c',
        'test_calibration_build_gate.c', 'test_telemetry.c', 'test_system_inertial.c',
        'test_imu_sample_bus.c', 'test_lifecycle.c', 'test_lifecycle_logging.c',
        'test_estimator_preparation.c', 'test_optional_gnss_start.c', 'test_health.c')
    if ($Job.Kind -eq 'HOST_TEST' -and @($Job.Sources | Where-Object {
        $logicalFixtures -contains (Split-Path -Leaf $_)
    }).Count -gt 0) {
        $Job.ExtraCompilerArgs += '-DSYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED=0U'
        Write-Output "FCCG_HOST_FIXTURE|$($Job.Name)|logical interfaces; physical epoch path not exercised"
    }
    if ($Job.Name -in @('source_selector', 'barometer_cold', 'device_native_log')) {
        $Job.ExtraCompilerArgs += @('-include',
            "$repoRoot\Tests\Host\Fixtures\multi_instance_build_contract.h")
        if ($Job.Name -eq 'source_selector') {
            $Job.ExtraCompilerArgs += '-DSYSTEM_BUILD_BAROMETER_COLD_ENABLED=0U'
        }
        Write-Output "FCCG_HOST_FIXTURE|$($Job.Name)|ordinary multiple-instance provider mock; production compact instance limit not exercised"
    }
    if ($Job.Kind -eq 'HOST_TEST' -and @($Job.Sources | Where-Object {
        (Split-Path -Leaf $_) -eq 'test_system_startup.c'
    }).Count -gt 0) {
        $Job.ExtraCompilerArgs += '-DSYSTEM_BUILD_POWER_IMPLEMENTATION_AVAILABLE=1U'
        Write-Output "FCCG_HOST_FIXTURE|$($Job.Name)|mock power provider supplied; production power selection unchanged"
    }
    $required = @()
    if ($Job.Kind -eq 'HOST_TEST') { $required += $Job.Sources }
    else { $required += $Job.Source }
    # Brand-specific rows retain their real declared headers and remain in the
    # inventory. Missing selected payload is an error; unselected is inapplicable.
    if ($Job.Name -like 'capability_jy901b*' -or
        $Job.Name -eq 'capability_first_release_triad_deferred') {
        $required += @(
            "$repoRoot\Devices\IMU\JY901B\Inc\jy901b_imu_build_capabilities.h",
            "$repoRoot\Devices\IMU\JY901B\Adapter\Inc\jy901b_magnetometer_build_capabilities.h",
            "$repoRoot\Devices\IMU\JY901B\Adapter\Inc\jy901b_quaternion_build_capabilities.h"
        )
    }
    for ($index = 0; $index -lt $Job.ExtraCompilerArgs.Count; $index++) {
        if ($Job.ExtraCompilerArgs[$index] -eq '-include') {
            if (($index + 1) -ge $Job.ExtraCompilerArgs.Count) { throw "Missing fixture include: $($Job.Name)" }
            $required += $Job.ExtraCompilerArgs[$index + 1]
        }
    }
    $Job | Add-Member -NotePropertyName RequiredInputs -NotePropertyValue @($required) -Force
    $missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
    $unselectedProductInputs = @($missing | Where-Object {
        $relative = $_.Substring($repoRoot.Length + 1).Replace('\', '/')
        $relative -notlike 'Tests/*' -and $relative -notlike 'Generated/*' -and
        -not $script:hostSourceGraph.Contains($relative)
    })
    foreach ($path in $missing) {
        $relative = $path.Substring($repoRoot.Length + 1).Replace('\', '/')
        # Algorithm/device packages own some fixtures too. Their declared
        # product inputs establish applicability; absent selected inputs fail.
        if (($relative -like 'Tests/*' -and $unselectedProductInputs.Count -eq 0) -or $relative -like 'Generated/*' -or
            $script:hostSourceGraph.Contains($relative) -or
            (($relative -like 'Devices/IMU/JY901B/*') -and $script:hostSourceGraph.Contains('Devices/IMU/JY901B/'))) {
            throw "Missing applicable Host input for $($Job.Name): $relative"
        }
    }
    $Job | Add-Member -NotePropertyName MissingInputs -NotePropertyValue @($missing) -Force
    if ($missing.Count -gt 0) {
        Write-Output ("FCCG_HOST_NOT_APPLICABLE|{0}|unselected inputs: {1}" -f $Job.Name, ($missing -join ', '))
        $script:hostNotApplicableCount++
    }
}
