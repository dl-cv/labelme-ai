param(
    [string]$Python = "python",
    [string]$VenvDir = ".venv",
    [string]$ModelSourceDir = "",
    [switch]$NoDownloadModels,
    [switch]$SkipModelMd5,
    [switch]$SkipPyInstaller,
    [switch]$CleanPyInstaller,
    [ValidateSet("small", "fast")][string]$CompressionProfile = "small",
    [switch]$InstallInnoSetup,
    [string]$ISCC = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$StepName) {
    if ($LASTEXITCODE -ne 0) {
        throw "[build] $StepName failed with exit code $LASTEXITCODE"
    }
}

function Resolve-RepoRoot {
    # packaging/windows/build.ps1 -> <repo_root>
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Ensure-VenvPython([string]$RepoRoot, [string]$PythonCmd, [string]$VenvPath) {
    $venvFull = Join-Path $RepoRoot $VenvPath
    $py = Join-Path $venvFull "Scripts\python.exe"
    if (-not (Test-Path $py)) {
        Write-Host "[build] Creating venv: $venvFull"
        & $PythonCmd -m venv $venvFull
    }
    if (-not (Test-Path $py)) {
        throw "Failed to create venv python at: $py"
    }
    return $py
}

function Get-AppVersion([string]$RepoRoot) {
    $initPy = Join-Path $RepoRoot "labelme\__init__.py"
    $content = Get-Content -LiteralPath $initPy -Raw
    $matches = [regex]::Matches($content, "__version__\s*=\s*['""]([^'""]+)['""]")
    if ($matches.Count -lt 1) {
        throw "Cannot find __version__ in $initPy"
    }
    return $matches[$matches.Count - 1].Groups[1].Value
}

function Resolve-ISCC([string]$ISCCOverride) {
    if ($ISCCOverride) {
        if (Test-Path $ISCCOverride) {
            return (Resolve-Path $ISCCOverride).Path
        }
        return ""
    }

    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 5\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }

    return ""
}

function Install-InnoSetup {
    Write-Host "[build] Inno Setup not found. Trying to install..."

    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if ($winget) {
        # Winget package id for Inno Setup.
        $args = @(
            "install",
            "--id", "JRSoftware.InnoSetup",
            "-e",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements"
        )
        Write-Host ("[build] Running: winget " + ($args -join " "))
        & $winget.Source @args
        return
    }

    $choco = Get-Command "choco.exe" -ErrorAction SilentlyContinue
    if ($choco) {
        $args = @("install", "innosetup", "-y", "--no-progress")
        Write-Host ("[build] Running: choco " + ($args -join " "))
        & $choco.Source @args
        return
    }

    throw @"
[build] Auto-install is not available (winget/choco not found).
Please install Inno Setup 6 manually (ISCC.exe), then re-run this script.
"@
}

$repoRoot = Resolve-RepoRoot
$pkgRoot = (Resolve-Path $PSScriptRoot).Path
Push-Location $repoRoot

try {
    $py = Ensure-VenvPython -RepoRoot $repoRoot -PythonCmd $Python -VenvPath $VenvDir

    Write-Host "[build] Upgrading pip/setuptools/wheel"
    & $py -m pip install --upgrade pip setuptools wheel
    Assert-LastExitCode "pip upgrade"

    $req = Join-Path $pkgRoot "requirements-win.txt"
    Write-Host "[build] Installing packaging requirements: $req"
    & $py -m pip install -r $req
    Assert-LastExitCode "pip install requirements"

    # Smoke test to catch missing deps before building an installer.
    Write-Host "[build] Smoke test: import labelme.dlcv.app"
    & $py -c "import labelme.dlcv.app"
    Assert-LastExitCode "smoke test"

    # Prepare offline models (copied into packaging/windows/_assets/models)
    $modelDir = Join-Path $pkgRoot "_assets\models"
    New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

    $prepareArgs = @("--model-dir", $modelDir)
    if ($ModelSourceDir) {
        $prepareArgs += @("--source-dir", $ModelSourceDir)
    }
    else {
        $defaultSource = "C:\dlcv\bin"
        if (Test-Path $defaultSource) {
            $prepareArgs += @("--source-dir", $defaultSource)
        }
    }
    if ($NoDownloadModels) { $prepareArgs += "--no-download" }
    if ($SkipModelMd5) { $prepareArgs += "--skip-md5" }

    Write-Host "[build] Preparing offline models: $($prepareArgs -join ' ')"
    & $py (Join-Path $repoRoot "scripts\prepare_models.py") @prepareArgs
    Assert-LastExitCode "prepare models"

    # Build app
    if (-not $SkipPyInstaller) {
        $spec = Join-Path $pkgRoot "labelmeai.spec"
        Write-Host "[build] Running PyInstaller (onedir): $spec"
        $pyiArgs = @($spec, "--noconfirm")
        if ($CleanPyInstaller) {
            $pyiArgs += "--clean"
        }
        & $py -m PyInstaller @pyiArgs
        Assert-LastExitCode "pyinstaller"
    }

    $distDir = Join-Path $repoRoot "dist\labelme"
    if (-not (Test-Path $distDir)) {
        throw "PyInstaller output not found: $distDir"
    }

    # Build installer
    $version = Get-AppVersion -RepoRoot $repoRoot
    $isccPath = Resolve-ISCC -ISCCOverride $ISCC
    if (-not $isccPath) {
        if ($InstallInnoSetup) {
            Install-InnoSetup
            $isccPath = Resolve-ISCC -ISCCOverride $ISCC
        }
    }
    if (-not $isccPath) {
        throw @"
Inno Setup compiler (ISCC.exe) not found.
Please install Inno Setup 6, then re-run this script.
Or pass -ISCC 'C:\Path\To\ISCC.exe'
Or run this script with -InstallInnoSetup to try winget/choco installation.
"@
    }

    $installerOut = Join-Path $repoRoot "installer_output"
    New-Item -ItemType Directory -Force -Path $installerOut | Out-Null

    $sourceAbs = (Resolve-Path $distDir).Path
    $iss = Join-Path $pkgRoot "LabelmeAI.iss"

    # NOTE: Some environments may lock newly created EXEs inside the repo folder
    # (AV/Indexing). Compile into a temp directory first, then copy to installer_output.
    $baseName = "LabelmeAI_Setup_{0}" -f $version
    # Use a unique temp directory to avoid failure when previous output is locked
    # by AV/indexer (common on Windows).
    $tempOut = Join-Path $env:TEMP ("labelmeai_installer_{0}_{1}_{2}" -f $version, $PID, (Get-Date -Format "yyyyMMdd_HHmmss"))
    New-Item -ItemType Directory -Force -Path $tempOut | Out-Null

    Write-Host "[build] Running Inno Setup ($CompressionProfile): $isccPath"
    & $isccPath $iss "/DAppVersion=$version" "/DSourceDir=$sourceAbs" "/DCompressionProfile=$CompressionProfile" "/O$tempOut" "/F$baseName"
    Assert-LastExitCode "inno setup"

    $setupExeTemp = Join-Path $tempOut ($baseName + ".exe")
    $setupExe = Join-Path $installerOut ($baseName + ".exe")
    if (-not (Test-Path $setupExeTemp)) {
        throw "Installer exe not found: $setupExeTemp"
    }
    Copy-Item -Force $setupExeTemp $setupExe
    Write-Host "[build] Done."
    Write-Host "[build] Installer: $setupExe"
}
finally {
    Pop-Location
}

