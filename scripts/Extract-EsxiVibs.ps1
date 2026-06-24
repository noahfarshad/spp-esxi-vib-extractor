<#
.SYNOPSIS
    Windows-friendly wrapper around extract_esxi_vibs.py. Extracts and groups
    ESXi VIBs from an HPE SPP by OS release, ready for PowerCLI Image Builder.

.DESCRIPTION
    The heavy lifting (reading VIB descriptors, detecting ESXi release, grouping)
    is done by the Python core. This wrapper just gives the Windows Image Builder
    workflow a native entry point and sane defaults.

    Prereq: Python 3.7-3.12 on PATH (the same Python you point PowerCLI at for
    Image Builder). No extra Python modules required -- the extractor uses only
    the standard library.

.PARAMETER SppPath
    Path to the extracted/mounted SPP directory (not the ISO/zip itself).

.PARAMETER OutPath
    Output directory for grouped VIBs + the manifest.

.PARAMETER Release
    Optional. Only copy this ESXi release (e.g. "9.0"). The manifest still
    covers everything found.

.PARAMETER ManifestOnly
    Only produce the CSV/JSON manifest; don't copy any files. Good for a quick
    "what ESXi content is in this SPP?" survey.

.EXAMPLE
    .\Extract-EsxiVibs.ps1 -SppPath "D:\spp-extracted" -OutPath ".\esxi-vibs"

.EXAMPLE
    .\Extract-EsxiVibs.ps1 -SppPath "D:\spp-extracted" -OutPath ".\out" -Release 9.0

.NOTES
    Author : Noah Farshad / essential.coach
    License : GPL-3.0
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SppPath,

    [Parameter(Mandatory = $true)]
    [string]$OutPath,

    [Parameter(Mandatory = $false)]
    [string]$Release,

    [Parameter(Mandatory = $false)]
    [switch]$ManifestOnly
)

$ErrorActionPreference = "Stop"

# Locate the Python core next to this script
$pyScript = Join-Path $PSScriptRoot "extract_esxi_vibs.py"
if (-not (Test-Path $pyScript)) {
    Write-Error "Could not find extract_esxi_vibs.py next to this wrapper."
    exit 1
}

# Find a usable python
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) { $python = $found.Source; break }
}
if (-not $python) {
    Write-Error "Python 3.7-3.12 not found on PATH. Install it (winget install Python.Python.3.12) and retry."
    exit 1
}

# Build argument list
$pyArgs = @($pyScript, "--spp", $SppPath, "--out", $OutPath)
if ($Release)      { $pyArgs += @("--release", $Release) }
if ($ManifestOnly) { $pyArgs += "--manifest-only" }

Write-Host "Running ESXi VIB extractor via $python ..." -ForegroundColor Cyan
& $python @pyArgs
$code = $LASTEXITCODE

if ($code -eq 0) {
    Write-Host "`nDone. Grouped output + manifest are in: $OutPath" -ForegroundColor Green
    Write-Host "Feed the per-release folder into Image Builder (see esxi-hpe-synergy-imagebuilder)." -ForegroundColor Green
} else {
    Write-Host "`nExtractor exited with code $code." -ForegroundColor Yellow
}
exit $code
