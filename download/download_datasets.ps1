param(
    [string]$Destination = $PSScriptRoot,
    [string]$PythonExe,
    [ValidateSet('3','4','6')][string[]]$Chapters = @('3','4','6'),
    [int]$Workers = 8,
    [int]$Retries = 10,
    [string]$Manifest = (Join-Path $PSScriptRoot 'download_manifest.json'),
    [switch]$VerifyOnly,
    [switch]$DownloadOnly
)
$ErrorActionPreference = 'Stop'
if (-not $PythonExe) {
    # Search this folder and its ancestors for a project virtual environment.
    $ancestor = Get-Item -LiteralPath $PSScriptRoot
    while ($ancestor) {
        $candidate = Join-Path $ancestor.FullName '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $PythonExe = $candidate
            break
        }
        $ancestor = $ancestor.Parent
    }
    if (-not $PythonExe) { $PythonExe = 'D:\Python3.11\python.exe' }
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw 'Python interpreter unavailable. Pass -PythonExe with the full path to your existing interpreter.'
}
$PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
if ($PythonExe -match '[\\/]WindowsApps[\\/]') {
    throw 'WindowsApps Python cannot be selected directly. Pass an existing project virtual environment.'
}
& $PythonExe -c 'import sys; print("Python:", sys.executable)'
if ($LASTEXITCODE -ne 0) { throw 'Selected Python cannot start; no fallback or installation was attempted.' }
$arguments = @('-u', (Join-Path $PSScriptRoot 'dataset_tools.py'), '--destination', $Destination,
               '--manifest', $Manifest, '--workers', "$Workers", '--retries', "$Retries", '--chapters') + $Chapters
if ($VerifyOnly) { $arguments += '--verify-only' }
if ($DownloadOnly) { $arguments += '--download-only' }
& $PythonExe @arguments
if ($LASTEXITCODE -ne 0) { throw "Download/verification failed (exit $LASTEXITCODE). Fix the reported issue and run the same command to resume." }
