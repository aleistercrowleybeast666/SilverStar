param(
    [ValidateSet('Flight', 'Ground')]
    [string]$TargetKind = 'Flight'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$script:checkCount = 0
$script:failures = New-Object 'System.Collections.Generic.List[string]'
$script:assertionRecommendations = 0

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
    param([Parameter(Mandatory = $true)][AllowEmptyString()][AllowNull()][string]$Text)

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
                # Preserve escaped physical newlines as well as source offsets.
                # Otherwise LF continuations merge lines and hide functions.
                if (($next -eq "`n") -or ($next -eq "`r")) {
                    [void]$builder.Append($next)
                } else {
                    [void]$builder.Append(' ')
                }
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

function Get-CSourceWithoutDirectives {
    param([string]$SanitizedText, [string]$RawText)

    $lines = @($SanitizedText -split "`r?`n")
    $rawLines = @($RawText -split "`r?`n")
    $continuation = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($continuation -or ($lines[$index] -match '^\s*#')) {
            # A physical backslash-newline splices even literal/comment text.
            # Blank the complete directive, retaining physical line locations.
            $continuation = $rawLines[$index].EndsWith('\')
            $lines[$index] = ''
        }
    }
    return ($lines -join "`n")
}

function Get-AssertionClosingParenthesis {
    param([string]$Text, [int]$Start)

    $depth = 0
    for ($index = $Start; $index -lt $Text.Length; $index++) {
        if ($Text[$index] -eq '(') { $depth++ }
        if ($Text[$index] -eq ')') {
            $depth--
            if ($depth -eq 0) { return $index }
        }
    }
    return -1
}

function Get-AssertionWithoutOuterParentheses {
    param([AllowEmptyString()][string]$Text)

    while (($Text.Length -ge 2) -and ($Text[0] -eq '(')) {
        $end = Get-AssertionClosingParenthesis $Text 0
        if ($end -ne ($Text.Length - 1)) { break }
        $Text = $Text.Substring(1, $Text.Length - 2)
    }
    return $Text
}

function Get-AssertionObjectOperand {
    param([string]$Text)

    $operand = Get-AssertionWithoutOuterParentheses $Text
    # Recognize a narrow C pointer-cast grammar, not arbitrary expressions.
    $pointerCast = '^\([A-Za-z_]\w*(?:\*+(?:const|volatile|restrict)?)+\)(.+)$'
    for ($index = 0; $index -lt $Text.Length; $index++) {
        $cast = [regex]::Match($operand, $pointerCast)
        if (-not $cast.Success) { break }
        $operand = Get-AssertionWithoutOuterParentheses $cast.Groups[1].Value
    }
    return $operand
}

function Get-AssertionWithoutSizeofOperands {
    param([string]$Text)

    $builder = New-Object System.Text.StringBuilder
    $start = 0
    foreach ($match in [regex]::Matches($Text, '\bsizeof\(')) {
        if ($match.Index -lt $start) { continue }
        $end = Get-AssertionClosingParenthesis $Text ($match.Index + 6)
        if ($end -lt 0) { continue }
        [void]$builder.Append($Text.Substring($start, $match.Index - $start))
        # Used only to detect predicates consisting solely of constants.
        [void]$builder.Append('0')
        $start = $end + 1
    }
    [void]$builder.Append($Text.Substring($start))
    return $builder.ToString()
}

function Test-AssertionForcedBooleanConstant {
    param([string]$Text)

    # Only outer logical operators and literal operands are classified.
    # Do not infer implications, aliases, guard dominance or nested logic.
    if ($Text -match '[?:]') { return $false }
    $orTerms = New-Object 'System.Collections.Generic.List[string]'
    $andTerms = New-Object 'System.Collections.Generic.List[string]'
    $orStart = 0
    $andStart = 0
    $depth = 0
    for ($index = 0; $index -lt ($Text.Length - 1); $index++) {
        if (($Text[$index] -eq '(') -or ($Text[$index] -eq '[')) { $depth++ }
        if (($Text[$index] -eq ')') -or ($Text[$index] -eq ']')) { $depth-- }
        if ($depth -ne 0) { continue }
        $operator = $Text.Substring($index, 2)
        if ($operator -eq '||') {
            $orTerms.Add($Text.Substring($orStart, $index - $orStart))
            $orStart = $index + 2
            $index++
        } elseif ($operator -eq '&&') {
            $andTerms.Add($Text.Substring($andStart, $index - $andStart))
            $andStart = $index + 2
            $index++
        }
    }
    if ($orTerms.Count -ne 0) {
        $orTerms.Add($Text.Substring($orStart))
        foreach ($term in $orTerms) {
            if ((Get-AssertionWithoutOuterParentheses $term) -match '^(?:1[UuLl]*|true)$') {
                return $true
            }
        }
    } elseif ($andTerms.Count -ne 0) {
        $andTerms.Add($Text.Substring($andStart))
        foreach ($term in $andTerms) {
            if ((Get-AssertionWithoutOuterParentheses $term) -match '^(?:0[UuLl]*|false)$') {
                return $true
            }
        }
    }
    return $false
}

function Get-MeaningfulAssertionCount {
    param([string]$FunctionText, [string[]]$StaticArrayNames)
    # This is a conservative syntactic eligibility count, not a proof of
    # semantic usefulness. Unknown predicates still require human review.
    $predicates = New-Object 'System.Collections.Generic.HashSet[string]'
    $fixedObjects = @($StaticArrayNames) + @([regex]::Matches($FunctionText,
        '(?m)^\s*(?:(?:static|const|volatile|unsigned|signed)\s+)*[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*\[[^\]]+\]\s*(?:[;=])|\b([A-Za-z_]\w*)\s*=\s*&[A-Za-z_]') |
        ForEach-Object { if ($_.Groups[1].Success) { $_.Groups[1].Value } else { $_.Groups[2].Value } })
    foreach ($match in [regex]::Matches($FunctionText,
            '\b(SILVERSTAR_ASSERT(?:_OBJECT)?)\s*\(')) {
        $start = $match.Index + $match.Length
        $depth = 0
        $end = $start
        for (; $end -lt $FunctionText.Length; $end++) {
            $c = $FunctionText[$end]
            if (($c -eq ',') -and ($depth -eq 0)) { break }
            if ($c -eq '(') { $depth++ }
            if ($c -eq ')') {
                if ($depth -eq 0) { break }
                $depth--
            }
        }
        $predicate = Get-AssertionWithoutOuterParentheses (
            $FunctionText.Substring($start, $end - $start) -replace '\s+', '')
        if ($match.Groups[1].Value -eq 'SILVERSTAR_ASSERT_OBJECT') {
            # A runtime pointer can provide one non-null contract. Natural
            # alignment of an already typed pointer supplies no extra credit.
            $predicate = Get-AssertionObjectOperand $predicate
            if (($predicate -match '^&|^(?:NULL|0[UuLl]*)$') -or
                ($fixedObjects -contains $predicate)) { continue }
            $predicate = $predicate + '!=NULL'
        }
        $nullComparison = [regex]::Match($predicate, '^(.+?)(?:!=|==)(?:NULL|0[UuLl]*)$')
        if (-not $nullComparison.Success) {
            $nullComparison = [regex]::Match($predicate, '^(?:NULL|0[UuLl]*)(?:!=|==)(.+)$')
        }
        if ($nullComparison.Success) {
            $operand = Get-AssertionObjectOperand $nullComparison.Groups[1].Value
            if (($operand -match '^&') -or ($fixedObjects -contains $operand)) { continue }
        }
        $constantView = Get-AssertionWithoutSizeofOperands $predicate
        $withoutConstants = $constantView -replace '\b(?:0[xX][0-9a-fA-F]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][+-]?[0-9]+)?[UuLlFf]*\b', ''
        $withoutConstants = $withoutConstants -replace '[()+!~<>=&|*/% -]', ''
        if ($withoutConstants.Length -eq 0 -or
            $predicate -match '^(?:true|false|TRUE|FALSE|NULL)$' -or
            $predicate -match '^&[A-Za-z_]\w*(?:\[[^\]]+\])?(?:!=|==)NULL$' -or
            $predicate -match '\+\+|--|(?<![=!<>])=(?!=)|\b_Alignof\b' -or
            (Test-AssertionForcedBooleanConstant $predicate)) { continue }
        $simple = $predicate
        if (@($fixedObjects | Where-Object { $simple -eq ($_ + '!=NULL') -or $simple -eq ($_ + '==NULL') }).Count -ne 0) { continue }
        if ($simple -match '^([A-Za-z_]\w*(?:(?:->|\.)\w+)*)(?:==|!=|<=|>=|<|>)\1$') { continue }
        # Only the standard pure numerical classification predicates are
        # mechanically eligible when the expression contains a function call.
        $calls = @([regex]::Matches($predicate, '\b([A-Za-z_]\w*)\(') |
            ForEach-Object { $_.Groups[1].Value })
        if (@($calls | Where-Object { $_ -notin @('isfinite', 'isnan', 'isinf', 'sizeof') }).Count -ne 0) { continue }
        [void]$predicates.Add($simple)
    }
    return $predicates.Count
}

function Get-CFunctions {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$SanitizedText)

    $lines = @($SanitizedText -split "`r?`n")
    $functions = New-Object 'System.Collections.Generic.List[object]'
    $staticArrayNames = @([regex]::Matches($SanitizedText,
        '(?m)^\s*static\s+[^;\r\n=]+?\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]+\])?\s*(?:;|=)') |
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

$files = Get-FirstPartyCFiles
$progressTotal = $files.Count + 2
$progressCurrent = 0
Write-Output "FCCG_PROGRESS|POWER10|PLAN|$progressTotal"
$allFunctions = @()
$utf8Decoder = New-Object System.Text.UTF8Encoding($false, $true)
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
    # PowerShell 5.1 otherwise uses the local Windows code page, which can
    # consume punctuation in UTF-8 C text and silently reduce scan coverage.
    try {
        $sourceBytes = [System.IO.File]::ReadAllBytes($file.FullName)
        $rawText = $utf8Decoder.GetString($sourceBytes)
        if (($rawText.Length -ne 0) -and ($rawText[0] -eq [char]0xFEFF)) {
            $rawText = $rawText.Substring(1)
        }
    } catch {
        Add-PowerTenFailure -Message "Source cannot be decoded as UTF-8: $progressSubject"
        Write-Output "FCCG_PROGRESS|POWER10|DONE|$progressCurrent|$progressTotal|$progressSubject"
        continue
    }
    $sanitized = Get-CSourceWithoutCommentsOrLiterals -Text $rawText
    $lines = @($sanitized -split "`r?`n")
    $relative = $file.FullName.Substring($repoRoot.Length + 1)
    # Hash the exact bytes scanned; do not depend on optional PowerShell cmdlets.
    $sourceHasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $sourceDigest = [System.BitConverter]::ToString(
            $sourceHasher.ComputeHash($sourceBytes)).Replace('-', '').ToLowerInvariant()
    } finally {
        $sourceHasher.Dispose()
    }
    Write-Output (('POWER10_SOURCE|{0}|{1}') -f $relative, $sourceDigest)

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
            $candidateRelative = Get-PowerTenRelativePath $candidateFile.FullName
            return (Test-PowerTenApprovedConditional $candidateRelative $line)
        }
    Add-PowerTenCheck -Condition ($conditionalDiagnostics.Count -eq 0) `
        -Message ("first-party C conditional compilation violation:`n  " +
            ($conditionalDiagnostics -join "`n  "))

    $doublePointerDiagnostics = Get-PatternDiagnostics -File $file `
        -Lines $lines -Pattern '\*\s*\*' -Approved {
            param($candidateFile, $line, $lineNumber)
            $candidateRelative = Get-PowerTenRelativePath $candidateFile.FullName
            return (Test-PowerTenApprovedDoublePointer $candidateRelative $line)
        }
    Add-PowerTenCheck -Condition ($doublePointerDiagnostics.Count -eq 0) `
        -Message ("double-pointer violation:`n  " +
            ($doublePointerDiagnostics -join "`n  "))

    $functionText = Get-CSourceWithoutDirectives $sanitized $rawText
    $functions = @(Get-CFunctions -SanitizedText $functionText)
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
    Write-Output (('POWER10_RULE5_FUNCTION|{0}|{1}|{2}|{3}|{4}|{5}') -f
        $TargetKind, $function.File, $function.StartLine, $function.Name,
        $function.CodeLines, $function.AssertionCount)
    Write-Output (('POWER10_FUNCTION_SCOPE|{0}|{1}|{2}|{3}|{4}') -f
        $TargetKind, $function.File, $function.StartLine, $function.EndLine, $function.Name)
    Add-PowerTenCheck -Condition ($function.CodeLines -le 60) -Message (
        '{0}:{1}: function {2} has {3} non-comment code lines (maximum 60)' -f
        $function.File, $function.StartLine, $function.Name,
        $function.CodeLines)
    # F Prime-inspired C adaptation: a review recommendation, not a density
    # acceptance gate. Typed status/error paths require manual contract review.
    if (($function.CodeLines -gt 10) -and ($function.AssertionCount -eq 0)) {
        $script:assertionRecommendations++
        Write-Output (('POWER10_RULE5_RECOMMENDATION|{0}|{1}|{2}|{3}|zero_runtime_candidates|nonblocking|manual_review_required') -f
            $function.File, $function.StartLine, $function.Name, $function.CodeLines)
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
$assertionTotal = 0
foreach ($function in $allFunctions) { $assertionTotal += $function.AssertionCount }
$density = if ($allFunctions.Count -ne 0) { $assertionTotal / $allFunctions.Count } else { 0.0 }
Write-Output (('POWER10_RULE5|{0}|files={1}|functions={2}|eligible_assertions={3}|average={4:F6}|informational|policy=fprime_inspired_c|semantic_review=required') -f
    $TargetKind, $files.Count, $allFunctions.Count, $assertionTotal, $density)
Add-PowerTenCheck -Condition ($allFunctions.Count -ne 0) `
    -Message 'First-party function scan is empty; source coverage is not established.'
Add-PowerTenCheck -Condition ($assertionTotal -gt 0) `
    -Message 'Entire current target has zero eligible runtime assertion candidates; first-release protection failed.'
Write-Output 'POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending'
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

$linkerName = if ($TargetKind -eq 'Ground') {
    $match = [regex]::Match($makefile, '(?m)\-T([^\s]+\.ld)')
    if (-not $match.Success) {
        Add-PowerTenFailure -Message 'Ground Makefile has no linker script.'
        ''
    } else {
        $match.Groups[1].Value
    }
} else {
    'STM32F407XX_FLASH.ld'
}
$linkerPath = Join-Path $repoRoot $linkerName
$linker = if (Test-Path -LiteralPath $linkerPath -PathType Leaf) {
    Get-Content -Raw -LiteralPath $linkerPath
} else {
    Add-PowerTenFailure -Message "Linker script is missing: $linkerName"
    ''
}
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

$successMessage = ("Power of Ten project text checks passed: {0} checks, {1} " +
    "first-party C files, {2} functions; {3} assertion recommendations. " +
    "Critical-contract review NOT PROVEN; manual acceptance pending.") -f $script:checkCount,
    $files.Count, $allFunctions.Count, $script:assertionRecommendations
Write-Host $successMessage -ForegroundColor Green
Write-Output "FCCG_PROGRESS|POWER10|DONE|$progressCurrent|$progressTotal|build_policy"
