$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$VenvPath = Join-Path $ProjectRoot '.venv'

function Get-PythonCommand {
    foreach ($Candidate in @('python', 'py')) {
        try {
            $Version = & $Candidate -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>$null
            if ($LASTEXITCODE -eq 0) {
                $Parts = $Version.Trim().Split('.')
                if ([int]$Parts[0] -gt 3 -or ([int]$Parts[0] -eq 3 -and [int]$Parts[1] -ge 10)) {
                    return $Candidate
                }
            }
        } catch { }
    }
    throw '需要 Python 3.10 或更高版本，请先安装 Python 并加入 PATH。'
}

$Python = Get-PythonCommand
if (-not (Test-Path $VenvPath)) {
    & $Python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' }
}
$VenvPython = Join-Path $VenvPath 'Scripts/python.exe'
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw '更新 pip 失败。' }
& $VenvPython -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw '安装依赖失败。' }
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $ProjectRoot '.browsers'
& $VenvPython -m playwright install chromium --no-shell
if ($LASTEXITCODE -ne 0) { throw '安装 Chromium 失败。' }
Write-Host "安装完成：$VenvPython"
