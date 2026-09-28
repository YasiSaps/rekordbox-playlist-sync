# rbsync installer for Windows.
#   irm https://raw.githubusercontent.com/YasiSaps/rekordbox-playlist-sync/main/install/install.ps1 | iex
# Installs into %LOCALAPPDATA%\rbsync, adds rbsync to your user PATH and a right-click "Send to" entry.
$ErrorActionPreference = 'Stop'

# Default: the latest published release (fall back to main if GitHub cannot be reached).
$Ref = $env:RBSYNC_REF
if (-not $Ref) {
    try {
        $Ref = (Invoke-RestMethod -TimeoutSec 10 -UseBasicParsing `
            'https://api.github.com/repos/YasiSaps/rekordbox-playlist-sync/releases/latest').tag_name
    } catch { $Ref = $null }
    if (-not $Ref) { $Ref = 'main' }
}
$Src  = "https://github.com/YasiSaps/rekordbox-playlist-sync/archive/$Ref.zip"
$Dest = Join-Path $env:LOCALAPPDATA 'rbsync'
$Bin  = Join-Path $Dest 'bin'

function Find-Python {
    $candidates = @(
        @{ Exe = 'py';      Args = @('-3') },
        @{ Exe = 'python';  Args = @() },
        @{ Exe = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $check = @($c.Args) + @('-c', 'import sys; print(sys.version_info >= (3, 9))')
            $ok = & $c.Exe @check 2>$null
            if ($ok -eq 'True') { return $c }
        } catch { }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Python 3.9+ is required." -ForegroundColor Yellow
    Write-Host "Install it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH')"
    Write-Host "or run:  winget install Python.Python.3.12   - then open a new PowerShell and run this again."
    return
}

function Invoke-Step([string]$What, [scriptblock]$Block) {
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "rbsync install failed while trying to $What (exit code $LASTEXITCODE)." }
}

Write-Host "Installing rbsync ($Ref) into $Dest ..." -ForegroundColor Cyan
$venvArgs = @($py.Args) + @('-m', 'venv', (Join-Path $Dest 'venv'))
Invoke-Step 'create the Python environment' { & $py.Exe @venvArgs }
$venvPy = Join-Path $Dest 'venv\Scripts\python.exe'
Invoke-Step 'update pip' { & $venvPy -m pip install --quiet --upgrade pip }
Invoke-Step 'download and install rbsync' { & $venvPy -m pip install --quiet --upgrade $Src }

New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Set-Content -Path (Join-Path $Bin 'rbsync.cmd') -Encoding ASCII -Value "@`"$Dest\venv\Scripts\rbsync.exe`" %*"

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not ($userPath -split ';' | Where-Object { $_ -eq $Bin })) {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ";$Bin").TrimStart(';'), 'User')
    Write-Host "Added $Bin to your PATH. Open a NEW PowerShell window to use 'rbsync'."
}

& (Join-Path $Dest 'venv\Scripts\rbsync.exe') integrate
Write-Host ""
& (Join-Path $Dest 'venv\Scripts\rbsync.exe') doctor
Write-Host ""
Write-Host "Done. Try:  rbsync plan `"Your Playlist.m3u8`"" -ForegroundColor Green
Write-Host "Uninstall: rbsync integrate --remove; then delete $Dest and remove it from PATH."
