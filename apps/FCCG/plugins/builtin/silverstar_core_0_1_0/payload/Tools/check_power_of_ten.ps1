$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$script:checkCount = 0
$script:failures = New-Object 'System.Collections.Generic.List[string]'

$firstPartyPaths = @(
    'APP', 'Algorithm', 'Board', 'Common', 'Devices', 'FlightLogic',
    'Generated', 'Interfaces', 'Modules', 'OS\FreeRTOS', 'Platform',
    'Protocol', 'System', 'Targets'
)

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

function Get-CFunctions {
    param([Parameter(Mandatory = $true)][string]$SanitizedText)

    $lines = @($SanitizedText -split "`r?`n")
    $functions = New-Object 'System.Collections.Generic.List[object]'
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
                $assertionCount = ([regex]::Matches(
                    $functionText, '\bSILVERSTAR_ASSERT\s*\(')).Count
                $assertionCount += 2 * ([regex]::Matches(
                    $functionText,
                    '\bSILVERSTAR_ASSERT_OBJECT\s*\(')).Count
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
                        AssertionCount = ([regex]::Matches(
                            $functionText,
                            '\bSILVERSTAR_ASSERT\s*\(')).Count
                        Text = $functionText
                    })
                    $functions[$functions.Count - 1].AssertionCount +=
                        2 * ([regex]::Matches(
                            $functionText,
                            '\bSILVERSTAR_ASSERT_OBJECT\s*\(')).Count
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

$files = Get-FirstPartyCFiles
$progressTotal = $files.Count + 2
$progressCurrent = 0
Write-Output "FCCG_PROGRESS|POWER10|PLAN|$progressTotal"
$allFunctions = @()
$patternRules = @(
    @{ Name = 'goto/setjmp/longjmp'; Pattern = '\bgoto\b|\b(?:setjmp|longjmp)\s*\(' },
    @{ Name = 'dynamic allocation'; Pattern = '\b(?:malloc|calloc|realloc|free|pvPortMalloc|vPortFree)\s*\(' },
    @{ Name = 'finite while/do loop'; Pattern = '\bwhile\s*\(|\bdo\s*\{' },
    @{ Name = 'function-pointer declaration'; Pattern = '\(\s*\*\s*[A-Za-z_][A-Za-z0-9_]*\s*\)\s*\(' },
    @{ Name = 'forbidden formatter'; Pattern = '\b(?:printf|fprintf|sprintf|snprintf|vprintf|vsprintf|vsnprintf)\s*\(' }
)
$conditionalPattern = '^\s*#\s*(?:if|ifdef|ifndef|elif|else|endif)\b'
$protocolConditionalPattern = (
    '^\s*#\s*if\s+\(SILVERSTAR_PROTOCOL_' +
    '(?:TELEMETRY|MAINTENANCE|LOGGING)_ENABLED\s*!=\s*0U\)\s*$'
)
# EstimatorTask retains origin/Pure INS when the optional KF6 plugin is absent.
# Only this source may compile out its KF6 implementation using the build lock.
$estimatorConditionalPattern =
    '^\s*#\s*if\s+\(SYSTEM_BUILD_ESTIMATOR_ENABLED\s*(?:!=|==)\s*0U\)\s*$'

foreach ($file in $files) {
    $progressCurrent++
    $progressSubject = $file.FullName.Substring($repoRoot.Length + 1)
    Write-Output "FCCG_PROGRESS|POWER10|BEGIN|$progressCurrent|$progressTotal|$progressSubject"
    $rawText = Get-Content -Raw -LiteralPath $file.FullName
    $sanitized = Get-CSourceWithoutCommentsOrLiterals -Text $rawText
    $lines = @($sanitized -split "`r?`n")
    $relative = $file.FullName.Substring($repoRoot.Length + 1)

    foreach ($rule in $patternRules) {
        $diagnostics = Get-PatternDiagnostics -File $file -Lines $lines `
            -Pattern $rule.Pattern
        Add-PowerTenCheck -Condition ($diagnostics.Count -eq 0) `
            -Message ($rule.Name + " violation:`n  " +
                ($diagnostics -join "`n  "))
    }

    $conditionalDiagnostics = Get-PatternDiagnostics -File $file `
        -Lines $lines -Pattern $conditionalPattern -Approved {
            param($candidateFile, $line, $lineNumber)
            $candidateRelative = $candidateFile.FullName.Substring(
                $repoRoot.Length + 1)
            return (($line -match $protocolConditionalPattern) -or
                    (($candidateRelative -eq 'APP\Src\estimator_task.c') -and
                     ($line -match $estimatorConditionalPattern)) -or
                    ($line -match '^\s*#\s*(?:else|endif)\b'))
        }
    Add-PowerTenCheck -Condition ($conditionalDiagnostics.Count -eq 0) `
        -Message ("first-party C conditional compilation violation:`n  " +
            ($conditionalDiagnostics -join "`n  "))

    $doublePointerDiagnostics = Get-PatternDiagnostics -File $file `
        -Lines $lines -Pattern '\*\s*\*' -Approved {
            param($candidateFile, $line, $lineNumber)
            $candidateRelative = $candidateFile.FullName.Substring(
                $repoRoot.Length + 1)
            $idleHookOutput =
                '^\s*(?:StaticTask_t|StackType_t)\s+\*\*\s*' +
                '(?:task_control|stack)\s*,?\s*$'
            return (($candidateRelative -eq 'OS\FreeRTOS\freertos_hooks.c') -and
                ($line -match $idleHookOutput))
        }
    Add-PowerTenCheck -Condition ($doublePointerDiagnostics.Count -eq 0) `
        -Message ("double-pointer violation:`n  " +
            ($doublePointerDiagnostics -join "`n  "))

    $functionLines = @($lines | ForEach-Object {
        if ($_ -match '^\s*#') { '' } else { $_ }
    })
    $functions = @(Get-CFunctions -SanitizedText ($functionLines -join "`n"))
    foreach ($function in $functions) {
        $allFunctions += [pscustomobject]@{
            File = $relative
            Name = $function.Name
            StartLine = $function.StartLine
            EndLine = $function.EndLine
            CodeLines = $function.CodeLines
            AssertionCount = $function.AssertionCount
            Text = $function.Text
        }
    }
    Write-Output "FCCG_PROGRESS|POWER10|DONE|$progressCurrent|$progressTotal|$progressSubject"
}

$progressCurrent++
Write-Output "FCCG_PROGRESS|POWER10|BEGIN|$progressCurrent|$progressTotal|function_rules"
foreach ($function in $allFunctions) {
    Add-PowerTenCheck -Condition ($function.CodeLines -le 60) -Message (
        '{0}:{1}: function {2} has {3} non-comment code lines (maximum 60)' -f
        $function.File, $function.StartLine, $function.Name,
        $function.CodeLines)
    if ($function.CodeLines -gt 20) {
        Add-PowerTenCheck -Condition ($function.AssertionCount -ge 2) `
            -Message (('{0}:{1}: function {2} has {3} runtime assertions; ' +
                'functions over 20 lines require at least 2') -f
                $function.File, $function.StartLine, $function.Name,
                $function.AssertionCount)
    }
    $bodyWithoutHeader = $function.Text.Substring(
        [Math]::Min($function.Text.Length,
            $function.Text.IndexOf('{') + 1))
    $recursionPattern = '\b' + [regex]::Escape($function.Name) + '\s*\('
    Add-PowerTenCheck `
        -Condition (-not [regex]::IsMatch($bodyWithoutHeader, $recursionPattern)) `
        -Message ('{0}:{1}: direct recursion suspected in {2}' -f
            $function.File, $function.StartLine, $function.Name)

    if ($function.Text -match 'for\s*\(\s*;\s*;\s*\)') {
        Add-PowerTenCheck `
            -Condition ($approvedInfiniteFunctions -contains $function.Name) `
            -Message ('{0}:{1}: unapproved infinite loop in {2}' -f
                $function.File, $function.StartLine, $function.Name)
    }
}
Write-Output "FCCG_PROGRESS|POWER10|DONE|$progressCurrent|$progressTotal|function_rules"

$progressCurrent++
Write-Output "FCCG_PROGRESS|POWER10|BEGIN|$progressCurrent|$progressTotal|build_policy"
$makefile = Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'Makefile')
$requiredWarnings = @(
    '-Wall', '-Wextra', '-Wpedantic', '-Werror', '-Wconversion',
    '-Wsign-conversion', '-Wshadow', '-Wundef', '-Wformat=2',
    '-Wdouble-promotion', '-Wcast-align', '-Wcast-qual',
    '-Wstrict-prototypes', '-Wmissing-prototypes', '-Wswitch-enum', '-Wvla'
)
foreach ($warning in $requiredWarnings) {
    Add-PowerTenCheck -Condition ($makefile.Contains($warning)) `
        -Message "Makefile first-party warning policy is missing $warning"
}
Add-PowerTenCheck -Condition ($makefile -match 'FIRST_PARTY_C_SOURCES') `
    -Message 'Makefile does not maintain a first-party compiler class.'
Add-PowerTenCheck -Condition ($makefile -match 'power10-check') `
    -Message 'Makefile does not expose the power10-check target.'

$linker = Get-Content -Raw -LiteralPath (
    Join-Path $repoRoot 'STM32F407XX_FLASH.ld')
Add-PowerTenCheck -Condition ($linker -match '_Min_Heap_Size\s*=\s*0x0') `
    -Message 'The authoritative linker script does not keep heap size at zero.'
Add-PowerTenCheck -Condition ($makefile -notmatch '(?m)^\s*[^#\r\n]*sysmem\.c') `
    -Message 'A heap-support sysmem.c source is present in the build graph.'

if ($script:failures.Count -ne 0) {
    Write-Host "Power of Ten check FAILED ($($script:failures.Count) failures)." `
        -ForegroundColor Red
    foreach ($failure in $script:failures) {
        Write-Host "- $failure"
    }
    exit 1
}

$successMessage = ("Power of Ten check passed: {0} checks, {1} " +
    "first-party C files, {2} functions.") -f $script:checkCount,
    $files.Count, $allFunctions.Count
Write-Host $successMessage -ForegroundColor Green
Write-Output "FCCG_PROGRESS|POWER10|DONE|$progressCurrent|$progressTotal|build_policy"
