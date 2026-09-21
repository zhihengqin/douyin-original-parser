param(
    [string]$OutputDirectory = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = 'Stop'
& python (Join-Path $PSScriptRoot 'package.py') --output-dir $OutputDirectory
exit $LASTEXITCODE
