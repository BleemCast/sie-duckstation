# RSIL-DuckStation one-shot build script
# Usage: .\build.ps1
# Output: duckstation-rsil-windows-x64.zip in current directory
#
# Prerequisites: Visual Studio 2022 with C++ workload (installs MSVC + CMake)
# Qt is downloaded automatically by the script.

param(
    [string]$SourceDir = "duckstation",
    [string]$BuildDir = "build"
)

$ErrorActionPreference = "Stop"
$DepsTag = "release-20260614"
$DepsUrl = "https://github.com/duckstation/dependencies/releases/download/$DepsTag/duckstation-prebuilt-windows-x64.zip"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  RSIL-DuckStation Build" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Source:  $SourceDir"
Write-Host "  Build:   $BuildDir"
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# ---- Step 1: Verify source exists ----
if (-not (Test-Path "$SourceDir\CMakeLists.txt")) {
    Write-Host "ERROR: DuckStation source not found at $SourceDir" -ForegroundColor Red
    Write-Host "Extract duckstation-rsil-source-corrected.tar.gz first." -ForegroundColor Yellow
    exit 1
}

# Verify RSIL fixes are present
$scanner = Get-Content "$SourceDir\dep\rsil\src\MipsPatternScanner.cpp" -Raw -ErrorAction SilentlyContinue
if ($scanner -notmatch "analyze_branch_safety") {
    Write-Host "ERROR: D3 fix not found in integrated RSIL source." -ForegroundColor Red
    Write-Host "The source tarball is stale. Re-download duckstation-rsil-source-corrected.tar.gz" -ForegroundColor Yellow
    exit 1
}
Write-Host "[1/4] Source verified (D3/D10/D12/D13 fixes present)" -ForegroundColor Green

# ---- Step 2: Download prebuilt deps ----
$PrebuiltDir = "$SourceDir\dep\prebuilt"
if (-not (Test-Path "$PrebuiltDir\windows-x64")) {
    Write-Host ""
    Write-Host "[2/4] Downloading prebuilt deps ($DepsTag)..." -ForegroundColor Yellow
    $tmp = "$env:TEMP\duckstation-deps.zip"
    Invoke-WebRequest -Uri $DepsUrl -OutFile $tmp -UseBasicParsing
    New-Item -ItemType Directory -Force -Path $PrebuiltDir | Out-Null
    Expand-Archive -Path $tmp -DestinationPath $PrebuiltDir -Force
    Remove-Item $tmp
    if (-not (Test-Path "$PrebuiltDir\windows-x64")) {
        Write-Host "ERROR: Deps extracted but windows-x64 folder missing." -ForegroundColor Red
        Get-ChildItem -Recurse $PrebuiltDir | Select-Object -First 10
        exit 1
    }
    Write-Host "  OK: Deps at $PrebuiltDir\windows-x64" -ForegroundColor Green
} else {
    Write-Host "[2/4] Prebuilt deps already present" -ForegroundColor Green
}

# ---- Step 3: Configure + Build ----
Write-Host ""
Write-Host "[3/4] Configuring CMake (this takes ~2 min)..." -ForegroundColor Yellow

# Find cmake (VS 2022 installs it, or system PATH)
$cmake = (Get-Command cmake -ErrorAction SilentlyContinue).Source
if (-not $cmake) {
    $cmake = "& '${env:ProgramFiles}\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    if (-not (Test-Path $cmake.Trim("`"'& "))) {
        $cmake = "& '${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    }
}

# Find Qt from the prebuilt deps (DuckStation bundles it)
$qtPath = Get-ChildItem -Path "$PrebuiltDir\windows-x64" -Filter "Qt6Config.cmake" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($qtPath) {
    $qtDir = $qtPath.Directory.Parent.Parent.FullName
    Write-Host "  Found Qt at: $qtDir" -ForegroundColor DarkGray
}

$cmakeArgs = @(
    "-B", $BuildDir,
    "-S", $SourceDir,
    "-G", '"Visual Studio 17 2022"',
    "-A", "x64",
    "-DCMAKE_BUILD_TYPE=Release",
    "-DENABLE_VULKAN=ON",
    "-DENABLE_OPENGL=ON",
    "-DENABLE_QT=ON",
    "-DBUILD_NO_UI_FRONTEND=OFF",
    "-DUSE_SDL2=ON",
    "-DRSIL_HAS_SQLITE=ON",
    "-DRSIL_HAS_IMGUI=ON"
)
if ($qtDir) { $cmakeArgs += "-DCMAKE_PREFIX_PATH=$qtDir" }

$cmakeCmd = "cmake $($cmakeArgs -join ' ')"
Write-Host "  $cmakeCmd" -ForegroundColor DarkGray
Invoke-Expression $cmakeCmd
if ($LASTEXITCODE -ne 0) { Write-Host "CMake configure failed." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  Building (20-40 minutes, parallel)..." -ForegroundColor Yellow
cmake --build $BuildDir --config Release --parallel $env:NUMBER_OF_PROCESSORS
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed." -ForegroundColor Red; exit 1 }

# ---- Step 4: Package ----
Write-Host ""
Write-Host "[4/4] Packaging..." -ForegroundColor Yellow

$binDir = "$BuildDir\bin\Release"
if (-not (Test-Path $binDir)) { $binDir = "$BuildDir\bin" }
$pkg = "duckstation-rsil-windows-x64"
if (Test-Path $pkg) { Remove-Item -Recurse -Force $pkg }
New-Item -ItemType Directory -Force -Path $pkg | Out-Null

Get-ChildItem -Path $binDir -Filter "*.exe" | Copy-Item -Destination $pkg
Get-ChildItem -Path $binDir -Filter "*.dll" | Copy-Item -Destination $pkg

# Qt deployment
$windeployqt = Get-ChildItem -Path $binDir -Filter "windeployqt.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($windeployqt) {
    & $windeployqt.FullName --release --no-translations --no-quick-import --no-system-d3d-compiler --no-opengl-sw "$pkg\duckstation-qt.exe" 2>$null
}

# Data + RSIL config
if (Test-Path "$SourceDir\data") { Copy-Item "$SourceDir\data" $pkg -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$pkg\settings" | Out-Null
@"
[RSIL]
Telemetry = true
Graph = true
Predictor = true
PreRegister = true
Overlay = false
Persistence = true
Validator = false
"@ | Set-Content "$pkg\settings\rsil.ini"

Compress-Archive -Path "$pkg\*" -DestinationPath "$pkg.zip" -CompressionLevel Optimal
$size = [math]::Round((Get-Item "$pkg.zip").Length / 1MB, 2)

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Artifact: $(Resolve-Path $pkg.zip)" -ForegroundColor Green
Write-Host "  Size: $size MB" -ForegroundColor Green
Write-Host ""
Write-Host "  To use:" -ForegroundColor White
Write-Host "    1. Unzip $pkg.zip" -ForegroundColor White
Write-Host "    2. Run duckstation-qt.exe" -ForegroundColor White
Write-Host "    3. Load a PS1 game (Wipeout 2097, R4, NFS HS)" -ForegroundColor White
Write-Host "================================================" -ForegroundColor Green
