param(
    [ValidateSet('Debug', 'Release')]
    [string]$Config = 'Debug',
    [string]$TargetProfile = 'SilverStar_F407'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$targetName = 'SilverStar_0_1_0'
$buildRoot = Join-Path $repoRoot (Join-Path 'build\FCCG' `
    (Join-Path $TargetProfile $Config))
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
            if (-not $symbols.ContainsKey($name)) {
                $symbols[$name] = [pscustomobject]@{
                    Address = ConvertFrom-HexValue -Value $Matches['address']
                    Size = ConvertFrom-HexValue -Value $Matches['size']
                    Type = $Matches['type']
                    Name = $name
                }
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

$loggingEnabled = $true
$generatedConfigPath = Join-Path $repoRoot 'Generated\Inc\project_flight_config.h'
if (Test-Path -LiteralPath $generatedConfigPath -PathType Leaf) {
    $generatedConfig = Get-Content -Raw -LiteralPath $generatedConfigPath
    $loggingDefinitions = [regex]::Matches($generatedConfig,
        '(?m)^\s*#define\s+SILVERSTAR_PROTOCOL_LOGGING_ENABLED\s+([01])U?\s*$')
    Assert-ArtifactCondition -Condition ($loggingDefinitions.Count -eq 1) `
        -Message 'Generated logging selection must have exactly one literal 0/1 definition.'
    if ($loggingDefinitions.Count -eq 1) {
        $loggingEnabled = $loggingDefinitions[0].Groups[1].Value -eq '1'
    }
}
$requiredCcmSymbols = @(
    's_estimator',
    's_alignment_strategy',
    's_device_stack',
    's_ins_stack',
    's_estimator_stack',
    's_flight_stack',
    's_serial_stack',
    's_telemetry_stack',
    's_idle_task_stack'
)
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
if ($loggingEnabled) { $requiredDmaSymbols += 's_aggregate_buffer' }
else {
    Assert-ArtifactCondition -Condition (-not $symbols.ContainsKey('s_aggregate_buffer')) `
        -Message 'Disabled logging must not allocate the log aggregation buffer.'
}
foreach ($name in $requiredDmaSymbols) {
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
Assert-ArtifactCondition -Condition ($mainSramUsed -le [uint64](100 * 1024)) `
    -Message ("Main SRAM exceeds the reviewed full-rate logging budget: " +
        "used=$mainSramUsed maximum=102400")

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
