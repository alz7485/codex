# Run from PowerShell on Windows with Python 3.12 installed.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $buildPython = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
    if (-not (Test-Path $buildPython)) {
        & py -3.12 -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create build environment.' }
    }
    & $buildPython -m pip install -r requirements.txt 'pyinstaller>=6.16,<7'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install build dependencies.' }
    & $buildPython -m PyInstaller --onedir --windowed --clean --noconfirm --name E3DFormDesigner --icon app-icon.ico --add-data 'e3d_designer\assets;e3d_designer\assets' run_designer.py
    if ($LASTEXITCODE -ne 0) { throw 'Failed to build application.' }
    $destination = Join-Path $PSScriptRoot 'dist\E3DFormDesigner'
    foreach ($folder in @('examples', 'docs')) {
        Copy-Item $folder -Destination $destination -Recurse -Force
    }
    foreach ($file in @('app-icon.ico', 'app-icon.png', 'USER_GUIDE.txt', 'README.md', 'EXE_BUILD_ONEDIR.txt')) {
        Copy-Item $file -Destination $destination -Force
    }
    New-Item -ItemType Directory -Path (Join-Path $destination 'e3d_designer') -Force | Out-Null
    Copy-Item 'e3d_designer\assets' -Destination (Join-Path $destination 'e3d_designer') -Recurse -Force
    Write-Host "Build completed: $destination"
}
finally {
    Pop-Location
}
