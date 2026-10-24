# Fixed application helper. JSON data arrives on stdin, never as executable text.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$requestText = [Console]::In.ReadToEnd()
if ($requestText.Length -gt 65536) { throw 'MTP request exceeds bound' }
$request = $requestText | ConvertFrom-Json

$resolutionTrace = [System.Collections.Generic.List[object]]::new()
$exceptionChain = @()
function Result_Write($status, $detail, $destination = '') {
    @{status=$status; detail=$detail; destination=$destination;
      diagnostics=@{stage=$stage; resolution=@($resolutionTrace.ToArray()); exceptions=$exceptionChain}
    } | ConvertTo-Json -Depth 10 -Compress
}
function Destination_Check($path) {
    if ($path.Length -gt 4096 -or -not $path.StartsWith('::{20D04FE0-3AEA-1069-A2D8-08002B30309D}', [StringComparison]::OrdinalIgnoreCase) -or
        -not $path.ToLowerInvariant().Contains('{6ac27878-a6fa-4155-ba85-f98f491d4f33}')) { throw 'Select a WPD/MTP folder' }
}
function Child_Wait($folder, $name, $deadline) {
    while ([DateTime]::UtcNow -lt $deadline) {
        $item = $folder.ParseName($name)
        if ($null -ne $item) { return $item }
        Start-Sleep -Milliseconds 100
    }
    throw 'MTP item did not appear within the bounded wait'
}

function Destination_Resolve($shell, [string]$path) {
    # A BrowseForFolder result can be a valid virtual FolderItem even when
    # NameSpace(full parsing path) returns null in a different process.
    $direct = $shell.NameSpace($path)
    if ($null -ne $direct -and [string]$direct.Self.Path -ceq $path) {
        $resolutionTrace.Add(@{method='namespace'; result='exact'})
        return $direct
    }
    $resolutionTrace.Add(@{method='namespace'; result='null_or_different_identity'})
    $current = $shell.NameSpace(17)
    $visited = 0
    for ($depth = 0; $depth -lt 32; $depth++) {
        if ($null -eq $current) { throw [System.IO.IOException]::new('MTP parent folder could not be bound') }
        $matches = @()
        foreach ($item in $current.Items()) {
            $visited++
            if ($visited -gt 4096) { throw [System.IO.IOException]::new('MTP resolution item bound exceeded') }
            $candidate = [string]$item.Path
            if ($candidate.Length -eq 0 -or -not $item.IsFolder -or $item.IsFileSystem) { continue }
            if ($path -ceq $candidate -or $path.StartsWith($candidate + '\', [StringComparison]::Ordinal)) {
                $matches += $item
            }
        }
        if ($matches.Count -ne 1) {
            throw [System.IO.IOException]::new('MTP exact identity not uniquely reachable; reselect the destination')
        }
        $selected = $matches[0]
        $resolutionTrace.Add(@{method='parent_items'; depth=$depth; result='exact_identity_component'})
        $current = $selected.GetFolder
        if ($path -ceq [string]$selected.Path) {
            if ($null -eq $current -or [string]$current.Self.Path -cne $path) {
                throw [System.IO.IOException]::new('MTP selected item did not bind to the same folder identity')
            }
            return $current
        }
    }
    throw [System.IO.IOException]::new('MTP resolution depth bound exceeded')
}

$copySubmitted = $false
$stage = 'initializing'
try {
    $shell = New-Object -ComObject Shell.Application
    if ($request.operation -eq 'capability') {
        Result_Write 'available' 'Windows Shell COM created; device capability/readback not yet tested'
    } elseif ($request.operation -eq 'choose') {
        $folder = $shell.BrowseForFolder(0, [string]$request.title, 0, 17)
        if ($null -eq $folder) { Result_Write 'cancelled' 'No MTP folder selected' }
        else {
            $path = [string]$folder.Self.Path
            Destination_Check $path
            if ($folder.Self.IsFileSystem) { throw 'Use the ordinary filesystem export for this destination' }
            Result_Write 'selected' ([string]$folder.Title) $path
        }
    } elseif ($request.operation -eq 'copy') {
        $stage = 'validate_destination'
        Destination_Check ([string]$request.destination)
        if ($request.name -notmatch '^SilverStar_export_[A-Za-z0-9_]{1,80}$' -or
            $request.files.Count -lt 2 -or $request.files.Count -gt 129) { throw 'Invalid MTP package' }
        $folder = Destination_Resolve $shell ([string]$request.destination)
        if ($null -eq $folder -or $folder.Self.IsFileSystem) {
            throw [System.IO.IOException]::new('Selected virtual MTP folder could not be resolved')
        }
        if ($null -ne $folder.ParseName([string]$request.name)) { throw 'MTP destination already exists; never overwrite' }
        Add-Type -Path (Join-Path $PSScriptRoot 'windows_mtp_copy.cs')
        $deadline = [DateTime]::UtcNow.AddSeconds(840)
        $stage = 'create_package'
        $folder.NewFolder([string]$request.name)
        $newItem = Child_Wait $folder ([string]$request.name) $deadline
        $target = $newItem.GetFolder
        $sink = $shell.NameSpace([string]$request.readback)
        if ($null -eq $target -or $null -eq $sink) { throw 'MTP/readback folder unavailable' }
        foreach ($entry in $request.files) {
            $name = [string]$entry.name
            if ($name -notmatch '^[A-Za-z0-9_.-]{1,200}$' -or $name -in @('.', '..') -or
                $entry.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Invalid file declaration' }
            $source = Join-Path ([string]$request.package) $name
            $output = Join-Path ([string]$request.readback) $name
            if (Test-Path -LiteralPath $output) { throw 'Readback file already exists' }
            if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw 'Staging file changed' }
            if ($null -ne $target.ParseName($name)) { throw 'Never overwrite an MTP file' }
            # PerformOperations must complete before we start the reverse copy.
            # Mere visibility of an asynchronous CopyHere item is insufficient.
            if ([DateTime]::UtcNow -ge $deadline) { throw 'MTP transaction deadline exceeded' }
            $stage = 'upload:' + $name
            $copySubmitted = $true
            [SilverStar.MtpCopy]::CopyShellItems($source, $target.Self, $name)
            $remote = Child_Wait $target $name $deadline
            $stage = 'readback:' + $name
            [SilverStar.MtpCopy]::CopyShellItems($remote, [string]$request.readback, $name)
            $stage = 'verify:' + $name
            $verified = $false
            while ([DateTime]::UtcNow -lt $deadline) {
                if (Test-Path -LiteralPath $output -PathType Leaf) {
                    try {
                        $file = Get-Item -LiteralPath $output
                        if ($file.Length -eq $entry.size -and
                            (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant() -eq $entry.sha256) {
                            $verified = $true; break
                        }
                    } catch { } # The asynchronous copy may still own the readback file.
                }
                Start-Sleep -Milliseconds 100
            }
            if (-not $verified) { throw 'MTP copy/readback did not verify within the bound' }
        }
        Result_Write 'verified' 'Every copied file was read back and SHA-256 matched; no move/delete issued' ([string]$request.destination + '\' + [string]$request.name)
    } else { throw 'Unsupported MTP operation' }
} catch {
    $cause = $_.Exception
    for ($depth = 0; $depth -lt 8 -and $null -ne $cause; $depth++) {
        $exceptionChain += @{type=$cause.GetType().FullName; hresult=('0x{0:X8}' -f $cause.HResult);
                             message=$cause.Message.Substring(0, [Math]::Min(2048, $cause.Message.Length))}
        if ($null -eq $cause.InnerException) { break }
        $cause = $cause.InnerException
    }
    $diagnostic = ('stage={0}; HRESULT=0x{1:X8}; {2}' -f $stage, $cause.HResult, $cause.Message)
    if ($copySubmitted) {
        Result_Write 'uncertain' ('MTP not verified; submitted copy may continue; sources retained. ' + $diagnostic)
    } else { Result_Write 'failed' $diagnostic }
}
