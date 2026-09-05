[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$PythonArguments
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($env:CHAOSATLAS_STATE_ROOT) {
    $stateRoot = [System.IO.Path]::GetFullPath($env:CHAOSATLAS_STATE_ROOT)
} elseif ($env:LOCALAPPDATA) {
    $stateRoot = Join-Path $env:LOCALAPPDATA 'ChaosAtlas'
} else {
    $stateRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.local\state\chaosatlas'
}
$env:PYTHONPYCACHEPREFIX = Join-Path $stateRoot 'tmp\pycache'

$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }
& $python @PythonArguments
exit $LASTEXITCODE
