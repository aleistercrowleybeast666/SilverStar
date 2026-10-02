param(
    [ValidateSet('Debug', 'Release')]
    [string]$Config = 'Debug',
    [string]$TargetProfile = 'SilverStar_F407',
    [ValidateSet('legacy', 'eskf_window_sram', 'auto')]
    [string]$MemoryLayout = 'legacy'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'read_firmware_identity.ps1')
$firmwareIdentity = FirmwareIdentity_Read -ProjectRoot $repoRoot
$targetName = $firmwareIdentity.build_target
$buildRoot = Join-Path $repoRoot (Join-Path 'build\FCCG' `
    (Join-Path $TargetProfile $Config))
if ($MemoryLayout -ne 'legacy') {
    $buildRoot = Join-Path $buildRoot $MemoryLayout
}
$elfPath = Join-Path $buildRoot ($targetName + '.elf')
$mapPath = Join-Path $buildRoot ($targetName + '.map')
$linkerPath = Join-Path $repoRoot 'STM32F407XX_FLASH.ld'
$failures = New-Object 'System.Collections.Generic.List[string]'
Write-Output 'FCCG_PROGRESS|ARTIFACT|PLAN|8'
Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|1|8|ELF_MAP_BIN_HEX'

function Add-ArtifactFailure {
    param([Parameter(Mandatory = $true)][string]$Message)

    $script:failures.Add($Message)
}

function Assert-ArtifactCondition {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not $Condition) {
        Add-ArtifactFailure -Message $Message
    }
}

function ConvertFrom-HexValue {
    param([Parameter(Mandatory = $true)][string]$Value)

    return [Convert]::ToUInt64($Value, 16)
}

function Get-MemoryName {
    param([Parameter(Mandatory = $true)][uint64]$Address)

    if (($Address -ge [uint64]0x10000000) -and
        ($Address -lt [uint64]0x10010000)) {
        return 'CCMRAM'
    }
    if (($Address -ge [uint64]0x20000000) -and
        ($Address -lt [uint64]0x20020000)) {
        return 'main SRAM'
    }
    if (($Address -ge [uint64]0x08000000) -and
        ($Address -lt [uint64]0x08080000)) {
        return 'FLASH'
    }
    return 'other'
}

function Get-SectionSize {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Sections,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($Sections.ContainsKey($Name)) {
        return [uint64]$Sections[$Name].Size
    }
    return [uint64]0
}

function Assert-SymbolRange {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Symbols,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][uint64]$Start,
        [Parameter(Mandatory = $true)][uint64]$Length,
        [Parameter(Mandatory = $true)][string]$MemoryName
    )

    if (-not $Symbols.ContainsKey($Name)) {
        Add-ArtifactFailure -Message "Required symbol is missing: $Name"
        return
    }
    $symbol = $Symbols[$Name]
    $end = [uint64]$symbol.Address + [uint64]$symbol.Size
    $rangeEnd = $Start + $Length
    Assert-ArtifactCondition `
        -Condition (($symbol.Address -ge $Start) -and ($end -le $rangeEnd)) `
        -Message ("Symbol {0} is outside {1}: address=0x{2:X8} size={3}" -f `
            $Name, $MemoryName, $symbol.Address, $symbol.Size)
}

$requiredArtifacts = @(
    $elfPath,
    $mapPath,
    (Join-Path $buildRoot ($targetName + '.hex')),
    (Join-Path $buildRoot ($targetName + '.bin'))
)
foreach ($artifact in $requiredArtifacts) {
    Assert-ArtifactCondition `
        -Condition (Test-Path -LiteralPath $artifact -PathType Leaf) `
        -Message "Missing firmware artifact: $artifact"
}

Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|1|8|ELF_MAP_BIN_HEX'
Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|2|8|ELF'
$nmCommand = Get-Command arm-none-eabi-nm -ErrorAction SilentlyContinue
$objdumpCommand = Get-Command arm-none-eabi-objdump -ErrorAction SilentlyContinue
Assert-ArtifactCondition -Condition ($null -ne $nmCommand) `
    -Message 'arm-none-eabi-nm is unavailable.'
Assert-ArtifactCondition -Condition ($null -ne $objdumpCommand) `
    -Message 'arm-none-eabi-objdump is unavailable.'

$symbols = @{}
$uartDmaSymbolCounts = @{}
if (($null -ne $nmCommand) -and
    (Test-Path -LiteralPath $elfPath -PathType Leaf)) {
    $nmOutput = @(& $nmCommand.Source -S --defined-only --radix=x `
        $elfPath 2>&1)
    Assert-ArtifactCondition -Condition ($LASTEXITCODE -eq 0) `
        -Message 'arm-none-eabi-nm failed to inspect the ELF.'
    foreach ($line in $nmOutput) {
        if ($line.ToString() -match `
            '^\s*(?<address>[0-9A-Fa-f]+)\s+(?<size>[0-9A-Fa-f]+)\s+(?<type>\S)\s+(?<name>.+?)\s*$') {
            $name = $Matches['name']
            if ([regex]::IsMatch($name, '^s_uart[1-6]_(?:rx_dma|tx_ring|tx_priority_ring)$')) {
                if (-not $uartDmaSymbolCounts.ContainsKey($name)) { $uartDmaSymbolCounts[$name] = 0 }
                $uartDmaSymbolCounts[$name]++
            }
            if (-not $symbols.ContainsKey($name)) {
                $symbols[$name] = [pscustomobject]@{
                    Address = ConvertFrom-HexValue -Value $Matches['address']
                    Size = ConvertFrom-HexValue -Value $Matches['size']
                    Type = $Matches['type']
                    Name = $name
                }
            }
        }
        elseif ($line.ToString() -match
            '^\s*(?<address>[0-9A-Fa-f]+)\s+(?<type>\S)\s+(?<name>\S+)\s*$') {
            $symbols[$Matches['name']] = [pscustomobject]@{
                Address = ConvertFrom-HexValue -Value $Matches['address']
                Size = [uint64]0
                Type = $Matches['type']
                Name = $Matches['name']
            }
        }
    }
    $forbiddenSymbols = @($symbols.Keys | Where-Object {
        $_ -match ('(?i)(?:^|_)(?:malloc|calloc|realloc|free|sbrk)(?:$|_)|' +
            '^pvPortMalloc$|^vPortFree$')
    } | Sort-Object -Unique)
    Assert-ArtifactCondition -Condition ($forbiddenSymbols.Count -eq 0) `
        -Message ('Runtime heap symbols entered ELF: ' +
            ($forbiddenSymbols -join ', '))
}

$sections = @{}
if (($null -ne $objdumpCommand) -and
    (Test-Path -LiteralPath $elfPath -PathType Leaf)) {
    $objdumpOutput = @(& $objdumpCommand.Source -h $elfPath 2>&1)
    Assert-ArtifactCondition -Condition ($LASTEXITCODE -eq 0) `
        -Message 'arm-none-eabi-objdump failed to inspect ELF sections.'
    foreach ($line in $objdumpOutput) {
        if ($line.ToString() -match `
            '^\s*\d+\s+(?<name>\S+)\s+(?<size>[0-9A-Fa-f]+)\s+(?<vma>[0-9A-Fa-f]+)\s+(?<lma>[0-9A-Fa-f]+)\s+') {
            $sections[$Matches['name']] = [pscustomobject]@{
                Name = $Matches['name']
                Size = ConvertFrom-HexValue -Value $Matches['size']
                Vma = ConvertFrom-HexValue -Value $Matches['vma']
                Lma = ConvertFrom-HexValue -Value $Matches['lma']
            }
        }
    }
}

Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|2|8|ELF'
Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|3|8|MAP'
$ccmStart = [uint64]0x10000000
$ccmLength = [uint64](64 * 1024)
$mainSramStart = [uint64]0x20000000
$mainSramLength = [uint64](128 * 1024)
$flashLength = [uint64](512 * 1024)

# The whitelist has one private CPU-only scratch object. Inspect the actual
# linked address and the startup-cleared bounds, not just requested flags.
$windowName = 's_eskf_window'
$backendPath = Join-Path $repoRoot 'Algorithm\Estimator\ESKF15\Src\navigation_eskf_backend.c'
$sourcesPath = Join-Path $repoRoot 'Generated\project_sources.mk'
$eskfSelected = (Test-Path -LiteralPath $sourcesPath -PathType Leaf) -and
    ((Get-Content -Raw -LiteralPath $sourcesPath) -match
        'Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend\.c')
$placementAware = (Test-Path -LiteralPath $backendPath -PathType Leaf) -and
    ((Get-Content -Raw -LiteralPath $backendPath) -match 'PLATFORM_ESKF_WINDOW_BSS')
if ($MemoryLayout -eq 'eskf_window_sram') {
    Assert-ArtifactCondition -Condition (($TargetProfile -eq 'SilverStar_F407') -and $eskfSelected) `
        -Message 'Experimental placement requires SilverStar_F407 and the selected ESKF15 backend.'
    Assert-ArtifactCondition -Condition $placementAware `
        -Message 'Preserved ESKF payload does not support experimental placement; use a fresh validation project.'
}

function ArtifactSha256_Get {
    param([Parameter(Mandatory = $true)][string]$Path)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $algorithm.ComputeHash([System.IO.File]::ReadAllBytes($Path))
        return ([System.BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
    }
    finally { $algorithm.Dispose() }
}
$autoDecision = $null
if ($MemoryLayout -eq 'auto') {
    $decisionPath = Join-Path $buildRoot 'memory_layout\decision.json'
    Assert-ArtifactCondition -Condition (Test-Path -LiteralPath $decisionPath -PathType Leaf) `
        -Message 'Auto memory decision is missing.'
    if (Test-Path -LiteralPath $decisionPath -PathType Leaf) {
        $autoDecision = Get-Content -Raw -LiteralPath $decisionPath | ConvertFrom-Json
        Assert-ArtifactCondition -Condition (($autoDecision.status -eq 'linked') -and
            ($autoDecision.elf_sha256 -eq (ArtifactSha256_Get -Path $elfPath))) `
            -Message 'Auto decision does not describe this linked ELF.'
        foreach ($property in $autoDecision.groups.PSObject.Properties) {
            $group = $property.Value
            $start = $mainSramStart; $length = $mainSramLength
            if ($group.region -eq 'CCMRAM') { $start = $ccmStart; $length = $ccmLength }
            Assert-SymbolRange -Symbols $symbols -Name $group.symbol -Start $start -Length $length -MemoryName $group.region
            if ($symbols.ContainsKey($group.symbol)) {
                $actual = $symbols[$group.symbol]
                $begin = $group.zero_bounds[0]; $end = $group.zero_bounds[1]
                Assert-ArtifactCondition -Condition ($symbols.ContainsKey($begin) -and $symbols.ContainsKey($end)) `
                    -Message 'Auto startup zero bounds are missing.'
                if ($symbols.ContainsKey($begin) -and $symbols.ContainsKey($end)) {
                    Assert-ArtifactCondition -Condition (($actual.Address -eq $group.address) -and
                        ($actual.Size -eq $group.size) -and (($actual.Address % $group.alignment) -eq 0) -and
                        ($actual.Address -ge $symbols[$begin].Address) -and
                        (($actual.Address + $actual.Size) -le $symbols[$end].Address)) `
                        -Message ('Auto symbol size/alignment/zero range differs: ' + $group.symbol)
                }
            }
            Write-Output ('  auto decision object={0} bytes={1} region={2} address=0x{3:X8}' -f `
                $group.symbol, $group.size, $group.region, [uint64]$group.address)
        }
    }
}
if ($eskfSelected -and ($placementAware -or ($MemoryLayout -ne 'legacy'))) {
    $startName = '_sccmram_bss'
    $endName = '_eccmram_bss'
    $memoryStart = $ccmStart
    $memoryLength = $ccmLength
    $memoryName = 'CCMRAM'
    if (($MemoryLayout -eq 'eskf_window_sram') -or
        (($MemoryLayout -eq 'auto') -and ($null -ne $autoDecision) -and
         ($autoDecision.assignment.eskf_window -eq 'RAM'))) {
        $startName = '_sbss'; $endName = '_ebss'
        $memoryStart = $mainSramStart; $memoryLength = $mainSramLength
        $memoryName = 'main SRAM'
    }
    Assert-SymbolRange -Symbols $symbols -Name $windowName -Start $memoryStart `
        -Length $memoryLength -MemoryName $memoryName
    Assert-ArtifactCondition -Condition ($symbols.ContainsKey($startName) -and $symbols.ContainsKey($endName)) `
        -Message 'Window startup clear bounds are missing.'
    if ($symbols.ContainsKey($windowName) -and $symbols.ContainsKey($startName) -and $symbols.ContainsKey($endName)) {
        $window = $symbols[$windowName]
        Assert-ArtifactCondition `
            -Condition (($window.Size -gt 0) -and (($window.Address % 8) -eq 0) -and
                ($window.Address -ge $symbols[$startName].Address) -and
                (($window.Address + $window.Size) -le $symbols[$endName].Address)) `
            -Message 'Window must be nonempty, 8-byte aligned, and fully inside startup-cleared BSS.'
        Write-Output ('  placement layout={0} object={1} address=0x{2:X8} bytes={3} region={4} zero={5}/{6}' -f `
            $MemoryLayout, $windowName, $window.Address, $window.Size, $memoryName, $startName, $endName)
    }
}
elseif ($eskfSelected) {
    Write-Output '  placement layout=legacy preserved_payload=unsupported experimental_audit=NOT_PROVEN'
}

Assert-ArtifactCondition -Condition $sections.ContainsKey('.ccmram_bss') `
    -Message 'ELF section .ccmram_bss is missing.'
if ($sections.ContainsKey('.ccmram_bss')) {
    $ccmBss = $sections['.ccmram_bss']
    Assert-ArtifactCondition -Condition ($ccmBss.Size -ne [uint64]0) `
        -Message 'ELF section .ccmram_bss is empty.'
    Assert-ArtifactCondition `
        -Condition (($ccmBss.Vma -ge $ccmStart) -and
            (($ccmBss.Vma + $ccmBss.Size) -le ($ccmStart + $ccmLength))) `
        -Message ('.ccmram_bss is outside the 64 KiB CCMRAM range: ' +
            ('vma=0x{0:X8} size={1}' -f $ccmBss.Vma, $ccmBss.Size))
}

$protocolEnabled = @{ LOGGING = $true; MAINTENANCE = $true; TELEMETRY = $true }
$generatedConfigPath = Join-Path $repoRoot 'Generated\Inc\project_flight_config.h'
if (Test-Path -LiteralPath $generatedConfigPath -PathType Leaf) {
    $generatedConfig = Get-Content -Raw -LiteralPath $generatedConfigPath
    foreach ($protocol in @('LOGGING', 'MAINTENANCE', 'TELEMETRY')) {
        $definitions = [regex]::Matches($generatedConfig,
            ('(?m)^\s*#define\s+SILVERSTAR_PROTOCOL_' + $protocol +
             '_ENABLED\s+([01])U?\s*$'))
        Assert-ArtifactCondition -Condition ($definitions.Count -eq 1) `
            -Message "Generated $protocol selection must have exactly one literal 0/1 definition."
        if ($definitions.Count -eq 1) {
            $protocolEnabled[$protocol] = $definitions[0].Groups[1].Value -eq '1'
        }
    }
}
else { Add-ArtifactFailure -Message 'Generated protocol selection header is missing.' }
$loggingEnabled = $protocolEnabled.LOGGING
$requiredCcmSymbols = @(
    's_estimator',
    's_alignment_strategy',
    's_device_stack',
    's_ins_stack',
    's_estimator_stack',
    's_flight_stack',
    's_idle_task_stack'
)
foreach ($entry in @(
    @{ Protocol = 'MAINTENANCE'; Stack = 's_serial_stack' },
    @{ Protocol = 'TELEMETRY'; Stack = 's_telemetry_stack' }
)) {
    if ($protocolEnabled[$entry.Protocol]) { $requiredCcmSymbols += $entry.Stack }
    else {
        Assert-ArtifactCondition -Condition (-not $symbols.ContainsKey($entry.Stack)) `
            -Message ("Disabled {0} must not allocate task stack {1}." -f `
                $entry.Protocol, $entry.Stack)
    }
}
if ($protocolEnabled.TELEMETRY) { $requiredCcmSymbols += 's_capability_tx' }
if ($loggingEnabled) { $requiredCcmSymbols += 's_logger_stack' }
else {
    Assert-ArtifactCondition -Condition (-not $symbols.ContainsKey('s_logger_stack')) `
        -Message 'Disabled logging must not allocate a Logger task stack.'
}
foreach ($name in $requiredCcmSymbols) {
    Assert-SymbolRange -Symbols $symbols -Name $name -Start $ccmStart `
        -Length $ccmLength -MemoryName 'CCMRAM'
}

$requiredDmaSymbols = @(
    's_uart1_rx_dma',
    's_uart2_rx_dma',
    's_uart3_rx_dma',
    's_uart3_tx_ring',
    's_uart3_tx_priority_ring'
)
# Preserved pre-UART-hotfix payloads remain supported; every linked TX ring
# from the additive async UART implementation is audited when present.
foreach ($uartNumber in 1..6) {
    foreach ($suffix in @('rx_dma', 'tx_ring', 'tx_priority_ring')) {
        $name = 's_uart{0}_{1}' -f $uartNumber, $suffix
        if ($symbols.ContainsKey($name) -and ($requiredDmaSymbols -notcontains $name)) {
            $requiredDmaSymbols += $name
        }
    }
}
if ($loggingEnabled) { $requiredDmaSymbols += 's_aggregate_buffer' }
else {
    Assert-ArtifactCondition -Condition (-not $symbols.ContainsKey('s_aggregate_buffer')) `
        -Message 'Disabled logging must not allocate the log aggregation buffer.'
}
foreach ($name in $requiredDmaSymbols) {
    if ($uartDmaSymbolCounts.ContainsKey($name)) {
        Assert-ArtifactCondition -Condition ($uartDmaSymbolCounts[$name] -eq 1) `
            -Message ('UART DMA symbol is ambiguous: ' + $name)
    }
    Assert-SymbolRange -Symbols $symbols -Name $name -Start $mainSramStart `
        -Length $mainSramLength -MemoryName 'DMA-accessible main SRAM'
}

if (Test-Path -LiteralPath $mapPath -PathType Leaf) {
    $forbiddenMapEntries = @(Select-String -LiteralPath $mapPath -Pattern `
        '(?i)cmsis_os2\.o|heap_[1-5]\.o|Core[/\\]Src[/\\]sysmem\.o')
    Assert-ArtifactCondition -Condition ($forbiddenMapEntries.Count -eq 0) `
        -Message 'Forbidden OS/heap object appears in linker map.'
}

if (Test-Path -LiteralPath $linkerPath -PathType Leaf) {
    $linkerContent = Get-Content -Raw -LiteralPath $linkerPath
    Assert-ArtifactCondition `
        -Condition ($linkerContent -match '_Min_Heap_Size\s*=\s*0x0\s*;') `
        -Message 'The authoritative linker script does not keep heap at zero.'
}

Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|3|8|MAP'
$flashSectionNames = @(
    '.isr_vector', '.text', '.rodata', '.ARM.extab', '.ARM',
    '.preinit_array', '.init_array', '.fini_array', '.data', '.ccmram_data'
)
$flashUsed = [uint64]0
foreach ($name in $flashSectionNames) {
    $flashUsed += Get-SectionSize -Sections $sections -Name $name
}
$mainSramUsed = (Get-SectionSize -Sections $sections -Name '.data') +
    (Get-SectionSize -Sections $sections -Name '.dma_bss') +
    (Get-SectionSize -Sections $sections -Name '.bss') +
    (Get-SectionSize -Sections $sections -Name '._user_heap_stack')
$ccmUsed = (Get-SectionSize -Sections $sections -Name '.ccmram_data') +
    (Get-SectionSize -Sections $sections -Name '.ccmram_bss')

Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|4|8|FLASH'
Assert-ArtifactCondition -Condition ($flashUsed -le $flashLength) `
    -Message "FLASH overflow: used=$flashUsed capacity=$flashLength"
Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|4|8|FLASH'
Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|5|8|MAIN_SRAM'
Assert-ArtifactCondition -Condition ($mainSramUsed -le $mainSramLength) `
    -Message "Main SRAM overflow: used=$mainSramUsed capacity=$mainSramLength"
Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|5|8|MAIN_SRAM'
Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|6|8|CCMRAM'
Assert-ArtifactCondition -Condition ($ccmUsed -le $ccmLength) `
    -Message "CCMRAM overflow: used=$ccmUsed capacity=$ccmLength"
if ($MemoryLayout -eq 'auto') {
    Write-Output ("  historical logging budget used={0} maximum=102400 physical_capacity={1}" -f $mainSramUsed, $mainSramLength)
    if ($mainSramUsed -gt [uint64](100 * 1024)) {
        Write-Warning 'Auto layout exceeds the historical 100 KiB main-SRAM regression budget by relocating CPU-only objects. Physical overflow, DMA, stack reservation and startup checks remain blocking; budget spare is not stack margin.'
    }
}
else {
    Assert-ArtifactCondition -Condition ($mainSramUsed -le [uint64](100 * 1024)) `
        -Message ("Main SRAM exceeds the reviewed full-rate logging budget: " +
            "used=$mainSramUsed maximum=102400")
}

Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|6|8|CCMRAM'
Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|7|8|heap'
$flashRemaining = $flashLength - [Math]::Min($flashUsed, $flashLength)
$mainSramRemaining = $mainSramLength -
    [Math]::Min($mainSramUsed, $mainSramLength)
$ccmRemaining = $ccmLength - [Math]::Min($ccmUsed, $ccmLength)

Write-Output 'SilverStar memory report:'
Write-Output ('  FLASH     used={0} remaining={1} capacity={2}' -f `
    $flashUsed, $flashRemaining, $flashLength)
Write-Output ('  main SRAM used={0} remaining={1} capacity={2}' -f `
    $mainSramUsed, $mainSramRemaining, $mainSramLength)
Write-Output ('  CCMRAM    used={0} remaining={1} capacity={2}' -f `
    $ccmUsed, $ccmRemaining, $ccmLength)
Write-Output '  heap      reserved=0 runtime_symbols=0'

Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|7|8|heap'
Write-Output 'FCCG_PROGRESS|ARTIFACT|BEGIN|8|8|summary'
$largestStaticObjects = @($symbols.Values | Where-Object {
    ($_.Type -match '^[bBdD]$') -and
    ((Get-MemoryName -Address $_.Address) -ne 'other')
} | Sort-Object -Property @{ Expression = 'Size'; Descending = $true }, `
    @{ Expression = 'Name'; Descending = $false } | Select-Object -First 10)
Write-Output '  largest static objects:'
foreach ($symbol in $largestStaticObjects) {
    Write-Output ('    {0,-32} bytes={1,6} address=0x{2:X8} {3}' -f `
        $symbol.Name, $symbol.Size, $symbol.Address,
        (Get-MemoryName -Address $symbol.Address))
}

if ($failures.Count -ne 0) {
    Write-Output ("SilverStar artifact check failed: target={0} config={1} failures={2}" -f `
        $TargetProfile, $Config, $failures.Count)
    foreach ($failure in $failures) {
        Write-Output "FAIL: $failure"
    }
    exit 1
}

$elfSize = (Get-Item -LiteralPath $elfPath).Length
$binSize = (Get-Item -LiteralPath `
    (Join-Path $buildRoot ($targetName + '.bin'))).Length
Write-Output ("SilverStar artifact check passed: target={0} config={1} elf_bytes={2} bin_bytes={3} heap_symbols=0" -f `
    $TargetProfile, $Config, $elfSize, $binSize)
Write-Output 'FCCG_PROGRESS|ARTIFACT|DONE|8|8|summary'
