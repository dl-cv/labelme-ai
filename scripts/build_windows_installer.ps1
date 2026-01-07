param(
    [string]$Python = "python",
    [string]$VenvDir = ".venv",
    [string]$ModelSourceDir = "",
    [switch]$NoDownloadModels,
    [switch]$SkipModelMd5,
    [switch]$SkipPyInstaller,
    [switch]$CleanPyInstaller,
    [ValidateSet("small", "fast")][string]$CompressionProfile = "small",
    [string]$ISCC = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# NOTE: Deprecated entrypoint. The build pipeline lives in `packaging/windows/`.
# Keep this wrapper for backward compatibility.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pkgScript = Join-Path $repoRoot "packaging\windows\build.ps1"
if (Test-Path $pkgScript) {
    Write-Host "[build] Redirecting to: $pkgScript"
    $argsToPass = @{
        Python             = $Python
        VenvDir            = $VenvDir
        ModelSourceDir     = $ModelSourceDir
        NoDownloadModels   = $NoDownloadModels
        SkipModelMd5       = $SkipModelMd5
        SkipPyInstaller    = $SkipPyInstaller
        CleanPyInstaller   = $CleanPyInstaller
        CompressionProfile = $CompressionProfile
        ISCC               = $ISCC
    }
    & $pkgScript @argsToPass
    exit $LASTEXITCODE
}
throw @"
[build] packaging/windows/build.ps1 not found.
Please use the new build pipeline under packaging/windows/.
"@
