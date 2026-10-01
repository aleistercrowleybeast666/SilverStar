# Read the generated project's authoritative identity without invoking FCCG.
# Numeric release parts match the platform's version/build-ID contract.
function FirmwareIdentity_Read {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $descriptorPath = Join-Path $ProjectRoot 'SilverStar.ssproject'
    $descriptor = Get-Content -Raw -Encoding UTF8 -LiteralPath $descriptorPath | ConvertFrom-Json
    $identity = $descriptor.project
    if (($null -eq $identity) -or
        ($identity.firmware_version -isnot [string]) -or
        ($identity.firmware_version -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$')) {
        throw 'Project firmware identity is missing or invalid.'
    }
    $expectedTarget = 'SilverStar_' + $identity.firmware_version.Replace('.', '_')
    if (($identity.build_target -isnot [string]) -or
        ($identity.build_target -cne $expectedTarget)) {
        throw 'Project build target does not match its firmware version.'
    }
    return $identity
}
