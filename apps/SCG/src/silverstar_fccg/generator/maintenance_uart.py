"""Derive a maintenance UART contract from its resolved CubeMX resource."""
import json
import re

from silverstar_fccg.project.resources import ResourceAssignments_Resolve

# Software framing/deadline bounds, not a list of UART/adapter baud capabilities.
MAINTENANCE_BAUD_MIN = 1200
MAINTENANCE_BAUD_MAX = 2000000


def MaintenanceUart_Profile(model, catalog):
    if model.protocols.get('maintenance') is None:
        return None
    result = ResourceAssignments_Resolve(model, catalog.ProjectView_Get(model))
    selected = [item for item in result.assignments
                if item.requirement.binding_macro == 'PROJECT_RESOURCE_CONSOLE_UART']
    if not selected:
        return None  # Other maintenance transports do not claim a UART rate.
    if not result.valid or len(selected) != 1:
        raise ValueError('Maintenance UART resource is not uniquely resolved: ' + '; '.join(result.errors))
    metadata = selected[0].provision.metadata
    baud = metadata.get('baud_rate')
    if (type(baud) is not int or not MAINTENANCE_BAUD_MIN <= baud <= MAINTENANCE_BAUD_MAX
            or metadata.get('word_length') != 8 or metadata.get('parity') != 'none'
            or metadata.get('stop_bits') != 1):
        raise ValueError('Maintenance UART requires a explicit CubeMX baud within1200..2000000 and8N1')
    if re.fullmatch(r'huart[1-9][0-9]*', str(metadata.get('handle'))) is None:
        raise ValueError('Maintenance UART HAL handle is not explicit')
    return dict(baudrate=baud, data_bits=8, parity='none', stop_bits=1,
                block_size=512, block_deadline_ms=30000, idle_timeout_ms=30000,
                minimum_wire_ms=(8210000 + baud - 1) // baud,
                handle=metadata['handle'], peripheral=metadata['peripheral'])


def MaintenanceUart_Declaration(model, catalog):
    profile = MaintenanceUart_Profile(model, catalog)
    return {k: v for k, v in profile.items() if k not in ('handle', 'peripheral')} if profile else None


def MaintenanceUart_Files(model, catalog):
    profile = MaintenanceUart_Profile(model, catalog)
    if profile is None:
        return {}
    # The checker reads actual user-owned output each build; it never edits it.
    return {'Tools/maintenance_uart.json': json.dumps(profile, indent=2),
            'Tools/check_maintenance_uart.ps1': CHECKER_SOURCE}


def MaintenanceUart_ResourcesAugment(files, model, catalog):
    profile = MaintenanceUart_Profile(model, catalog)
    if profile is None:
        return
    declaration = ('typedef enum { ProjectMaintenanceUartResult_Ok = 0, '
                   'ProjectMaintenanceUartResult_Mismatch } ProjectMaintenanceUartResult;\n'
                   'ProjectMaintenanceUartResult ProjectMaintenanceUart_Validate(void);\n\n')
    header = files['Generated/Inc/project_resources.h']
    prefix, mark, suffix = header.rpartition('#endif')
    if not mark:
        raise ValueError('Generated resource header guard is missing')
    files['Generated/Inc/project_resources.h'] = prefix + declaration + mark + suffix
    source = files['Generated/Src/project_resources.c']
    files['Generated/Src/project_resources.c'] = source.replace('#include "project_resources.h"',
        '#include "project_resources.h"\n#include "usart.h"', 1) + MaintenanceUart_RuntimeGuard(profile)


def MaintenanceUart_RuntimeGuard(profile):
    handle = profile['handle']
    return f'''
/* Configuration is initialized by CubeMX before task/Console startup. */
ProjectMaintenanceUartResult ProjectMaintenanceUart_Validate(void)
{{
    if (({handle}.Instance != {profile['peripheral']}) ||
        ({handle}.Init.BaudRate != {profile['baudrate']}U) ||
        ({handle}.Init.WordLength != UART_WORDLENGTH_8B) ||
        ({handle}.Init.Parity != UART_PARITY_NONE) ||
        ({handle}.Init.StopBits != UART_STOPBITS_1) ||
        ({handle}.Init.Mode != UART_MODE_TX_RX) ||
        ({handle}.Init.HwFlowCtl != UART_HWCONTROL_NONE))
    {{ return ProjectMaintenanceUartResult_Mismatch; }}
    return ProjectMaintenanceUartResult_Ok;
}}
'''


CHECKER_SOURCE = r'''# Read-only validation; ordinary firmware builds do not require Python.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$profile = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'maintenance_uart.json') | ConvertFrom-Json
$sources = @(Get-ChildItem -LiteralPath $root -Filter usart.c -Recurse -File | Where-Object {
    $_.FullName.Substring($root.Length) -notmatch '[/\\](build|\.work|Tests)[/\\]'
})
if ($sources.Count -ne 1) { throw 'Maintenance UART check requires one explicit CubeMX usart.c' }
$text = Get-Content -Raw -Encoding UTF8 -LiteralPath $sources[0].FullName
$text = [regex]::Replace($text, '(?s)/\*.*?\*/|//[^\n]*', '')
$handle = '\b' + [regex]::Escape($profile.handle)
$fields = @{ BaudRate = [string]$profile.baudrate; WordLength = 'UART_WORDLENGTH_8B'
    Parity = 'UART_PARITY_NONE'; StopBits = 'UART_STOPBITS_1'
    HwFlowCtl = 'UART_HWCONTROL_NONE'; Mode = 'UART_MODE_TX_RX' }
foreach ($name in $fields.Keys) {
    $found = [regex]::Matches($text, $handle + '\.Init\.' + $name + '\s*=\s*([^;]+);')
    if ($found.Count -ne 1 -or $found[0].Groups[1].Value.Trim().TrimEnd('u', 'U') -cne $fields[$name]) {
        throw ('Maintenance UART mismatch in actual CubeMX source: ' + $name)
    }
}
$iocs = @(Get-ChildItem -LiteralPath $root -Filter '*.ioc' -File)
if ($iocs.Count -ne 1) { throw 'Maintenance UART check requires one explicit project IOC' }
$lines = Get-Content -Encoding UTF8 -LiteralPath $iocs[0].FullName
$prefix = $profile.peripheral + '.BaudRate='
$values = @($lines | Where-Object { $_.StartsWith($prefix) } | ForEach-Object { $_.Substring($prefix.Length).Trim() })
if ($values.Count -ne 1 -or $values[0] -cne [string]$profile.baudrate) {
    throw 'Maintenance UART mismatch in CubeMX IOC baud'
}
$instances = [regex]::Matches($text, $handle + '\.Instance\s*=\s*([^;]+);')
if ($instances.Count -ne 1 -or $instances[0].Groups[1].Value.Trim() -cne $profile.peripheral) {
    throw 'Maintenance UART mismatch in actual CubeMX Instance'
}
# F1 uses 16x; F4 may explicitly select 8x. Unknown expressions fail closed.
$sampling = [regex]::Matches($text, $handle + '\.Init\.OverSampling\s*=\s*([^;]+);')
$mode = 'UART_OVERSAMPLING_16'
if ($sampling.Count -eq 1) { $mode = $sampling[0].Groups[1].Value.Trim() }
if ($sampling.Count -gt 1 -or $mode -cnotin @('UART_OVERSAMPLING_8', 'UART_OVERSAMPLING_16')) {
    throw 'Maintenance UART oversampling is not explicit'
}
$minimum = 16; $maximum = 65535
if ($mode -ceq 'UART_OVERSAMPLING_8') { $minimum = 8; $maximum = 32767 }
$clockKey = 'RCC.APB1Freq_Value='
if ($profile.peripheral -cin @('USART1', 'USART6')) { $clockKey = 'RCC.APB2Freq_Value=' }
$clocks = @($lines | Where-Object { $_.StartsWith($clockKey) } | ForEach-Object { $_.Substring($clockKey.Length).Trim() })
if ($clocks.Count -ne 1 -or $clocks[0] -notmatch '^\d+$') {
    throw 'Maintenance UART requires the imported CubeMX peripheral clock'
}
[long]$clock = $clocks[0]; [long]$baud = $profile.baudrate
if ($baud -lt 1200 -or $baud -gt 2000000) { throw 'Maintenance UART baud outside software deadline bounds' }
[long]$divisor = [math]::Floor(($clock + [math]::Floor($baud / 2)) / $baud)
if ($divisor -lt $minimum -or $divisor -gt $maximum -or
    [math]::Abs($clock - $baud * $divisor) * 100 -gt $baud * $divisor * 2) {
    throw 'Maintenance UART baud is not representable within 2 percent at the imported clock'
}
Write-Output ('Maintenance UART source/IOC matched ' + $baud + '/8N1; no source overwritten')
'''
