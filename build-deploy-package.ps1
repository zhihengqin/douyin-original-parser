# 生成抖音原画解析服务的源码部署包（源码白名单，不含 .venv、.browsers、output、凭据）。
# 用法：右键"使用 PowerShell 运行"，或直接执行 .\build-deploy-package.ps1
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "没有找到项目虚拟环境：$Python。请先运行 deploy/windows/install.ps1（或确认项目 .venv 存在）。"
}

Write-Host '正在校验代码与单元测试……'
# PowerShell 5.1 会把原生命令写到 stderr 的日志当成错误记录，测试日志走的正是 stderr，
# 因此这里临时放宽错误处理，只依据退出码判断结果。
$PreviousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $Python -m unittest discover -s tests 2>&1 | Out-Null
$TestExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousPreference
if ($TestExitCode -ne 0) {
    Write-Host '单元测试未通过，已停止打包。请先执行以下命令查看失败原因：' -ForegroundColor Red
    Write-Host '  .venv/Scripts/python.exe -m unittest discover -s tests -v' -ForegroundColor Yellow
    exit 1
}
Write-Host '单元测试通过。' -ForegroundColor Green

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutputDir = Join-Path $ProjectRoot ('output/release-' + $Stamp)
& $Python (Join-Path $ProjectRoot 'package.py') --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) { throw '打包失败。' }

Write-Host ''
Write-Host '部署包已生成：' -ForegroundColor Green
Get-ChildItem -LiteralPath $OutputDir -File | ForEach-Object {
    Write-Host ('  {0}  ({1:N0} 字节)' -f $_.FullName, $_.Length)
}
Write-Host ''
Write-Host '上传到服务器（示例）：'
Write-Host ('  scp "{0}" root@172.31.0.4:/tmp/' -f (Join-Path $OutputDir 'douyin-original-parser-deploy.tar.gz'))
Write-Host ''
Write-Host '在服务器上执行升级（示例，三台都要）：'
Write-Host '  sudo bash /opt/software/python/deploy/linux/deploy.sh /tmp/douyin-original-parser-deploy.tar.gz'
Write-Host ''
Write-Host '首次部署请加 --install-units --create-account 参数。'
