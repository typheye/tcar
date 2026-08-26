param(
    [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ProjectRoot "build"
$DistRoot = Join-Path $ProjectRoot "dist"
$SourceRoot = Join-Path $ProjectRoot "src"

# Auto-activate conda environment if not already active
if ($env:CONDA_DEFAULT_ENV -ne "tcar") {
    $conda = Get-Command conda.exe -ErrorAction SilentlyContinue
    if (-not $conda) {
        Write-Error "Conda not found. Open Anaconda Prompt or run scripts\setup-conda.bat first."
        exit 1
    }
    Write-Host "Activating 'tcar' conda environment..." -ForegroundColor Yellow
    $installArg = if ($Install) { "-Install" } else { "" }
    & conda run --no-capture-output -n tcar powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\build.ps1" $installArg
    exit $LASTEXITCODE
}

function Invoke-PyInstallerSpec {
    param(
        [Parameter(Mandatory = $true)][string]$SpecPath,
        [Parameter(Mandatory = $true)][string]$DistPath,
        [Parameter(Mandatory = $true)][string]$WorkName
    )

    $WorkPath = Join-Path (Join-Path $BuildRoot "pyinstaller") $WorkName
    New-Item -ItemType Directory -Path $WorkPath -Force | Out-Null

    $Arguments = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath", $DistPath,
        "--workpath", $WorkPath,
        $SpecPath
    )
    Write-Host "python $($Arguments -join ' ')" -ForegroundColor Cyan
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for $SpecPath with exit code $LASTEXITCODE"
    }
}

try {
    & python -c "import PyInstaller, PyQt5, OpenGL, psutil"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing build dependency. Run scripts\setup-conda.bat first."
    }

    if (Test-Path $BuildRoot) { Remove-Item $BuildRoot -Recurse -Force }
    if (Test-Path $DistRoot)  { Remove-Item $DistRoot -Recurse -Force }
    New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null

    # Build tCarKit
    Invoke-PyInstallerSpec `
        -SpecPath (Join-Path $SourceRoot "tcarkit\tcarkit.spec") `
        -DistPath $DistRoot `
        -WorkName "tcarkit"

    # Smoke test
    $Expected = (Join-Path $DistRoot "tCarKit.exe")
    if (-not (Test-Path $Expected -PathType Leaf)) {
        throw "Expected output was not generated: $Expected"
    }
    Write-Host "tCarKit.exe built successfully: $((Get-Item $Expected).Length / 1KB) KB" -ForegroundColor Green

    if ($Install) {
        if (-not $env:CONDA_PREFIX) {
            throw "No active Conda environment. Activate 'tcar' before using -Install."
        }
        $ScriptsDir = Join-Path $env:CONDA_PREFIX "Scripts"
        New-Item -ItemType Directory -Path $ScriptsDir -Force | Out-Null
        Copy-Item $Expected $ScriptsDir -Force
        Write-Host "Installed tCarKit.exe to $ScriptsDir" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "Build complete:" -ForegroundColor Green
    Write-Host "  dist\tCarKit.exe"
}
catch {
    Write-Error $_
    exit 1
}
