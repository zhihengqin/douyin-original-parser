param(
    [string]$HostAddress = '0.0.0.0',
    [ValidateRange(1, 65535)] [int]$Port = 8765,
    [ValidateRange(1, 32)] [int]$MaxConcurrent = 6,
    [string]$CookieFile = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$VenvPython = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $VenvPython)) {
    throw "没有找到虚拟环境，请先运行 deploy\windows\install.ps1。"
}
Set-Location $ProjectRoot
$env:PYTHONUNBUFFERED = '1'
$Arguments = @('run.py', '--serve', '--host', $HostAddress, '--port', $Port, '--max-concurrent', $MaxConcurrent)
if ($CookieFile) { $Arguments += @('--cookie-file', $CookieFile) }
& $VenvPython @Arguments
exit $LASTEXITCODE
