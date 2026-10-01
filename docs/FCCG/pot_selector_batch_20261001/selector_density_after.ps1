param(
    [ValidateSet('Flight', 'Ground')]
    [string]$TargetKind = 'Flight'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$script:checkCount = 0
$script:failures = New-Object 'System.Collections.Generic.List[string]'

$firstPartyPaths = if ($TargetKind -eq 'Ground') {
    @('Common', 'Devices', 'Generated', 'Ground', 'Platform')
} else {
    @(
        'APP', 'Algorithm', 'Board', 'Common', 'Devices', 'FlightLogic',
        'Generated', 'Interfaces', 'Modules', 'OS\FreeRTOS', 'Platform',
        'Protocol', 'System', 'Targets'
    )
}

$approvedInfiniteFunctions = @(
    'AppTask_Device', 'AppTask_Estimator', 'AppTask_Flight', 'AppTask_Ins',
    'AppTask_Logger', 'AppTask_Serial', 'AppTask_Telemetry',
    'SilverStarAssert_Fail', 'vApplicationMallocFailedHook',
    'vApplicationStackOverflowHook'
)

function Add-PowerTenFailure {
    param([Parameter(Mandatory = $true)][string]$Message)
    $script:failures.Add($Message)
}

function Add-PowerTenCheck {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $script:checkCount++
    if (-not $Condition) {
        Add-PowerTenFailure -Message $Message
    }
}

function Get-FirstPartyCFiles {
    $files = @()
    foreach ($relativePath in $firstPartyPaths) {
        $path = Join-Path $repoRoot $relativePath
        if (Test-Path -LiteralPath $path -PathType Container) {
            $files += Get-ChildItem -LiteralPath $path -Recurse -File `
                -Filter '*.c'
        }
    }
    return @($files | Sort-Object -Property FullName -Unique)
}

function Get-CSourceWithoutCommentsOrLiterals {
    param([Parameter(Mandatory = $true)][string]$Text)

    $builder = New-Object System.Text.StringBuilder
    $state = 'normal'
    for ($index = 0; $index -lt $Text.Length; $index++) {
        $character = $Text[$index]
        $next = if (($index + 1) -lt $Text.Length) {
            $Text[$index + 1]
        } else {
            [char]0
        }

        if ($state -eq 'line-comment') {
            if ($character -eq "`n") {
                [void]$builder.Append($character)
                $state = 'normal'
            } else {
                [void]$builder.Append(' ')
            }
            continue
        }
        if ($state -eq 'block-comment') {
            if (($character -eq '*') -and ($next -eq '/')) {
                [void]$builder.Append(' ')
                [void]$builder.Append(' ')
                $index++
                $state = 'normal'
            } elseif (($character -eq "`n") -or ($character -eq "`r")) {
                [void]$builder.Append($character)
            } else {
                [void]$builder.Append(' ')
            }
            continue
        }
        if (($state -eq 'string') -or ($state -eq 'character')) {
            $terminator = if ($state -eq 'string') { '"' } else { "'" }
            if (($character -eq '\') -and (($index + 1) -lt $Text.Length)) {
                [void]$builder.Append(' ')
                [void]$builder.Append(' ')
                $index++
            } elseif ($character -eq $terminator) {
                [void]$builder.Append(' ')
                $state = 'normal'
            } elseif (($character -eq "`n") -or ($character -eq "`r")) {
                [void]$builder.Append($character)
            } else {
                [void]$builder.Append(' ')
            }
            continue
        }

        if (($character -eq '/') -and ($next -eq '/')) {
            [void]$builder.Append(' ')
            [void]$builder.Append(' ')
            $index++
            $state = 'line-comment'
        } elseif (($character -eq '/') -and ($next -eq '*')) {
            [void]$builder.Append(' ')
            [void]$builder.Append(' ')
            $index++
            $state = 'block-comment'
        } elseif ($character -eq '"') {
            [void]$builder.Append(' ')
            $state = 'string'
        } elseif ($character -eq "'") {
            [void]$builder.Append(' ')
            $state = 'character'
        } else {
            [void]$builder.Append($character)
        }
    }
    return $builder.ToString()
}

function Get-BraceDelta {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Line)
    $openCount = ([regex]::Matches($Line, '\{')).Count
    $closeCount = ([regex]::Matches($Line, '\}')).Count
    return $openCount - $closeCount
}

function Get-MeaningfulAssertionCount {
    param([string]$FunctionText, [string[]]$StaticArrayNames)
    $count = 0
    foreach ($match in [regex]::Matches($FunctionText,
            '\bSILVERSTAR_ASSERT\s*\(\s*([^,\r\n]+)')) {
        if ($match.Groups[1].Value.Trim() -notmatch '^(?:0|1)(?:U|UL)?$') {
            $count++
        }
    }
    foreach ($match in [regex]::Matches($FunctionText,
            '\bSILVERSTAR_ASSERT_OBJECT\s*\(\s*([^,\r\n]+)')) {
        $object = $match.Groups[1].Value.Trim()
        if (($object -notmatch '^&') -and
            ($StaticArrayNames -notcontains $object)) {
            $count += 2
        }
    }
    return $count
}

function Get-CFunctions {
    param([Parameter(Mandatory = $true)][string]$SanitizedText)

    $lines = @($SanitizedText -split "`r?`n")
    $functions = New-Object 'System.Collections.Generic.List[object]'
    $staticArrayNames = @([regex]::Matches($SanitizedText,
        '(?m)^\s*static\s+[^;\r\n=]+?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[[^\]]+\]\s*;') |
        ForEach-Object { $_.Groups[1].Value })
    $globalDepth = 0
    $candidate = ''
    $candidateStart = 0
    $functionName = $null
    $functionStart = 0
    $functionDepth = 0

    for ($lineIndex = 0; $lineIndex -lt $lines.Count; $lineIndex++) {
        $line = $lines[$lineIndex]
        $trimmed = $line.Trim()

        if ($null -ne $functionName) {
            $functionDepth += Get-BraceDelta -Line $line
            if ($functionDepth -eq 0) {
                $functionLines = $lines[$functionStart..$lineIndex]
                $codeLineCount = @($functionLines |
                    Where-Object { $_.Trim().Length -ne 0 }).Count
                $functionText = $functionLines -join "`n"
                $assertionCount = Get-MeaningfulAssertionCount `
                    $functionText $staticArrayNames
                $functions.Add([pscustomobject]@{
                    Name = $functionName
                    StartLine = $functionStart + 1
                    EndLine = $lineIndex + 1
                    CodeLines = $codeLineCount
                    AssertionCount = $assertionCount
                    Text = $functionText
                })
                $functionName = $null
                $candidate = ''
            }
            continue
        }

        if ($globalDepth -ne 0) {
            $globalDepth += Get-BraceDelta -Line $line
            if ($globalDepth -eq 0) { $candidate = '' }
            continue
        }
        if ($trimmed.Length -eq 0) { continue }
        if ($candidate.Length -eq 0) { $candidateStart = $lineIndex }
        $candidate += ' ' + $trimmed

        $openIndex = $candidate.IndexOf('{')
        if ($openIndex -ge 0) {
            $header = $candidate.Substring(0, $openIndex).Trim()
            $match = [regex]::Match(
                $header, '([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*$')
            $blockedNames = @('if', 'for', 'while', 'switch')
            if ($match.Success -and
                ($blockedNames -notcontains $match.Groups[1].Value) -and
                ($header -notmatch '=')) {
                $functionName = $match.Groups[1].Value
                $functionStart = $candidateStart
                $functionDepth = Get-BraceDelta -Line $candidate
                if ($functionDepth -eq 0) {
                    $functionLines = $lines[$functionStart..$lineIndex]
                    $functionText = $functionLines -join "`n"
                    $functions.Add([pscustomobject]@{
                        Name = $functionName
                        StartLine = $functionStart + 1
                        EndLine = $lineIndex + 1
                        CodeLines = @($functionLines | Where-Object {
                            $_.Trim().Length -ne 0
                        }).Count
                        AssertionCount = Get-MeaningfulAssertionCount `
                            $functionText $staticArrayNames
                        Text = $functionText
                    })
                    $functionName = $null
                    $candidate = ''
                }
            } else {
                $globalDepth = Get-BraceDelta -Line $candidate
                if ($globalDepth -eq 0) { $candidate = '' }
            }
        } elseif ($candidate.Contains(';')) {
            $candidate = ''
        }
    }
    return $functions.ToArray()
}

function Get-PatternDiagnostics {
    param(
        [Parameter(Mandatory = $true)][System.IO.FileInfo]$File,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string[]]$Lines,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [scriptblock]$Approved
    )

    $diagnostics = @()
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index] -match $Pattern) {
            if (($null -ne $Approved) -and
                (& $Approved $File $Lines[$index] ($index + 1))) {
                continue
            }
            $relative = $File.FullName.Substring($repoRoot.Length + 1)
            $diagnostics += ('{0}:{1}: {2}' -f $relative,
                ($index + 1), $Lines[$index].Trim())
        }
    }
    return $diagnostics
}

function Get-PowerTenRelativePath {
    param([Parameter(Mandatory = $true)][string]$FullName)
    return ($FullName.Substring($repoRoot.Length + 1) -replace '\\', '/')
}

function Test-PowerTenApprovedConditional {
    param([string]$RelativePath, [string]$Line)
    $normalized = $RelativePath -replace '\\', '/'
    return (($Line -match $protocolConditionalPattern) -or
            (($normalized -eq 'APP/Src/estimator_task.c') -and
             ($Line -match $estimatorConditionalPattern)) -or
            ($Line -match '^\s*#\s*(?:else|endif)\b'))
}

function Test-PowerTenApprovedDoublePointer {
    param([string]$RelativePath, [string]$Line)
    $normalized = $RelativePath -replace '\\', '/'
    $idleHookOutput = '^\s*(?:StaticTask_t|StackType_t)\s+\*\*\s*' +
        '(?:task_control|stack)\s*,?\s*$'
    return (($normalized -eq 'OS/FreeRTOS/freertos_hooks.c') -and
        ($Line -match $idleHookOutput))
}


$repoRoot = 'D:\python_software\SilverStar\.work\SelectorSafety_70ce20d_20261001_v1\after\Flight_Controller'
$densityOutput = 'D:\python_software\SilverStar\docs\FCCG\pot_selector_batch_20261001\after_function_counts.json'

$rows = @()
foreach ($file in (Get-FirstPartyCFiles)) {
    $sanitized = Get-CSourceWithoutCommentsOrLiterals -Text (Get-Content -Raw -LiteralPath $file.FullName)
    $lines = @($sanitized -split "`r?`n" | ForEach-Object { if ($_ -match '^\s*#') { '' } else { $_ } })
    foreach ($function in (Get-CFunctions -SanitizedText ($lines -join "`n"))) {
        $rows += [pscustomobject]@{File=($file.FullName.Substring($repoRoot.Length + 1)); Name=$function.Name; CodeLines=$function.CodeLines; AssertionCount=$function.AssertionCount}
    }
}
$rows | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $densityOutput -Encoding UTF8
Write-Output ('FUNCTIONS=' + $rows.Count + ' ASSERTIONS=' + ($rows | Measure-Object AssertionCount -Sum).Sum)
